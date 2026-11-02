"""STAGE 300 — Vorübersetzung (Umbau Phase 2, GATE_KATALOG.md Zeile 300, 02.11.2026)
Funktion:     Freie, zusammenhaengende Kapiteluebersetzung je bestellter Zielsprache als Kontextanker fuer 310.
              Nicht zur Auslieferung. Immer direkt aus der Ausgangssprache.
Wirkungsweise: Je Kapitel x Zielsprache ein DeepSeek-Aufruf je Abschnitt (Kapitel > Abschnittsgroesse wird an Knotengrenzen
              geteilt). Prompt mit Stil/setting und den im Kapitel vorkommenden Glossar-, Figuren- und Unuebersetzt-
              Eintraegen aus 210. Ergebnis je Kapitel x Sprache als Checkpoint work/ckpt/300/<kap>__<lg>.json
              (Eingang = Hash Kapiteltext + Profil-Ausschnitt + Modell + Abschnitt + Prompt-Version); Neulauf ohne
              Aenderung 0 $, Abbruch verliert nur das laufende Kapitel.
Eingang:      work/210_profil.json (Knoten + Profil), book.json (quellsprache, Zielsprachen aus Bestellung 095,
              voruebersetzung an/aus), Gate 190 (Kapitelzahl).
Ausgabe:      work/300_voruebersetzung.json (210 + meta.pretranslation[kapitel][sprache], meta.voruebersetzung),
              work/300_pruefung.json (je Kapitel x Sprache: Laenge, Sprache, Glossar-Treffer, abgeschnitten, Versuch).
Gate:         Kapitelzahl = 190 (Stopp, -> 200); Kapitel x Sprache fehlt (Aufruf gescheitert) -> Stopp; falsche Sprache -> Stopp;
              abgeschnitten (finish_reason length) / Laenge Ziel/Quelle ausserhalb 0,8–1,6 / Glossar-Treffer < 95 %
              -> 1x automatisch neu mit halbierten Abschnitten; danach weiter rot -> Kapitel ohne Anker (310 laeuft ohne,
              Hinweis); Mock im Live-Lauf -> Stopp. Sonst auto.
Kosten:       deepseek-v4-pro (config.MODELS pretranslator), ~0,8 ct je Kapitel x Sprache; usage_log Stage 300 mit Sprache.
Regler:       --ziel de,fr (Zielsprachen; schreibt Bestellung in book.json um, zeigt Kostendifferenz, setzt Stage-Liste neu;
              095 muss danach neu angenommen werden), --modell, --abschnitt N (Zeichen), --kapitel N|alle (neu erzeugen),
              --aus / --an (Stage abschalten: 310 ohne Anker), --laenge 0.8-1.6,
              --uebernehmen (vorhandene 300_voruebersetzung.json als Rohergebnis, ohne LLM), --trocken (Probe, schreibt nichts).
Aufruf:
  python -m pipeline.s300_voruebersetzung <werk> [Regler] [--wer CK]
Exit: 0 auto, 2 Stopp, 3 Mensch, 1 Fehler.
"""

import argparse
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import api_layer, bestellung, gate, manifest, mock, status, usage_log
from tools import sprache

STAGE = "300"
PROMPT_V = 2
ABSCHNITT = 40000          # Zeichen Quelltext je Aufruf
LAENGE = (0.8, 1.6)
LAENGE_MIN_QUELLE = 300    # darunter keine Laengenpruefung
GLOSSAR_MIN = 0.95
GLOSSAR_FEHL_MIN = 2       # Glossar rot erst ab 2 Fehltreffern (Einzelfall bei kleinen Kapiteln)
MAX_TOKENS = 32000


# ============================================================
# EINGANG
# ============================================================

def kapitel_knoten(data, src):
    """-> {kap: [knotentext, ...]} in Reihenfolge; Kapitel ohne uebersetzbaren Text mit leerer Liste."""
    kap = {}
    for tid, e in (data.get("content") or {}).items():
        cid = tid.split("_")[0]
        liste = kap.setdefault(cid, [])
        if not isinstance(e, dict) or e.get("type") in config.NO_AUDIO_TYPES:
            continue
        t = (e.get(src) or "").strip()
        if t:
            liste.append(t)
    return kap


def _kommt_vor(begriff, text_klein):
    b = (begriff or "").strip().lower()
    if not b:
        return False
    return re.search(r"(?<!\w)" + re.escape(b) + r"(?!\w)", text_klein) is not None


def profil_ausschnitt(profil, text, lg):
    """Nur Eintraege, die im Kapitel vorkommen. -> dict (fuer Prompt und Hash)."""
    tk = text.lower()
    st = profil.get("style") or {}
    aus = {"style": {k: st.get(k) for k in ("tone", "register", "setting", "notes") if st.get(k)},
           "glossary": {}, "characters": {}, "untranslated": []}
    for k, v in (profil.get("glossary") or {}).items():
        if _kommt_vor(k, tk) and isinstance(v, dict) and (v.get(lg) or "").strip():
            aus["glossary"][k] = v[lg].strip()
    for k, v in (profil.get("characters") or {}).items():
        if _kommt_vor(k, tk):
            ziel = (v.get(lg) or "").strip() if isinstance(v, dict) else ""
            aus["characters"][k] = ziel or k
    for k in (profil.get("untranslated") or {}):
        if _kommt_vor(k, tk):
            aus["untranslated"].append(k)
    return aus


def erwartet(aus):
    """Paare (Quellbegriff, erwartete Zielform) fuer den Glossar-Treffer."""
    p = [(k, v) for k, v in aus["glossary"].items()]
    p += [(k, v) for k, v in aus["characters"].items()]
    p += [(k, k) for k in aus["untranslated"]]
    return [(k, v) for k, v in p if (v or "").strip()]


def _gefunden(ziel, text_klein):
    z = ziel.strip().lower()
    if z in text_klein:
        return True
    w = [x for x in re.findall(r"[^\W\d_]+", z) if len(x) >= 4]
    return bool(w) and all(x[:max(4, len(x) - 2)] in text_klein for x in w)


# ============================================================
# PROMPT / LLM
# ============================================================

def _build_prompt(text, src, lg, aus):
    st = aus["style"]
    z = []
    if st.get("tone") or st.get("register"):
        z.append(f"Style: tone = {st.get('tone', '')}, register = {st.get('register', '')}.")
    if st.get("setting"):
        z.append(f"Setting: {st['setting']}")
    if st.get("notes"):
        z.append(f"Translator notes: {st['notes']}")
    if aus["characters"]:
        z.append("Character names (use exactly these forms in the translation):\n" +
                 "\n".join(f"- {k} -> {v}" for k, v in aus["characters"].items()))
    if aus["glossary"]:
        z.append("Glossary (use these renderings):\n" + "\n".join(f"- {k} -> {v}" for k, v in aus["glossary"].items()))
    if aus["untranslated"]:
        z.append("Keep these terms untranslated: " + ", ".join(aus["untranslated"]))
    hinweise = ("\n\n" + "\n\n".join(z)) if z else ""
    return f"""Translate the following text from {src} into {lg}.
Produce a single, coherent, natural translation of the whole passage, complete from the first to the last sentence.
This is a context reference, so prioritise fluent meaning over literal word order. Do not summarise or skip anything.{hinweise}

--- TEXT START ---
{text}
--- TEXT END ---

Return ONLY the translated text, no explanation."""


def abschnitte(knoten, groesse):
    """Knotenliste an Knotengrenzen in Abschnitte <= groesse Zeichen teilen."""
    teile, akt, n = [], [], 0
    for t in knoten:
        if akt and n + len(t) + 1 > groesse:
            teile.append(" ".join(akt))
            akt, n = [], 0
        akt.append(t)
        n += len(t) + 1
    if akt:
        teile.append(" ".join(akt))
    return teile


def llm(werk, knoten, src, lg, aus, groesse, modell=None):
    """-> {"abschnitte": [text], "finish": [reason], "abschnitt": groesse}"""
    out, fin = [], []
    alt = config.MODELS.get("pretranslator")
    if modell:
        config.MODELS["pretranslator"] = modell
    usage_log.set_context(werk, STAGE, sprache=lg)
    try:
        for teil in abschnitte(knoten, groesse):
            info = {}
            if config.RUN_MODE == "mock":
                r = api_layer.call_model("pretranslator", "", target_lang=lg)
            else:
                r = api_layer.call_model("pretranslator", _build_prompt(teil, src, lg, aus),
                                         max_tokens=MAX_TOKENS, info=info)
            out.append((r or "").strip())
            fin.append(info.get("finish_reason"))
    finally:
        config.MODELS["pretranslator"] = alt
    return {"abschnitte": out, "finish": fin, "abschnitt": groesse}


# ============================================================
# PRUEFUNG JE KAPITEL x SPRACHE
# ============================================================

def pruefen(quelle, daten, lg, aus, laenge=LAENGE):
    text = "\n\n".join(daten.get("abschnitte") or [])
    tk = text.lower()
    r = {"zeichen_quelle": len(quelle), "zeichen_ziel": len(text), "versuch": daten.get("versuch", 1),
         "abschnitte": len(daten.get("abschnitte") or []), "mock": mock.ist_text(text)}
    r["abgeschnitten"] = any(f == "length" for f in daten.get("finish") or [])
    r["laenge"] = round(len(text) / len(quelle), 3) if quelle else None
    r["laenge_ok"] = len(quelle) < LAENGE_MIN_QUELLE or (r["laenge"] is not None and laenge[0] <= r["laenge"] <= laenge[1])
    erk, _a = sprache.erkennen(text)
    r["sprache"] = erk
    r["sprache_ok"] = erk in (None, lg)
    paare = erwartet(aus)
    fehlt = [f"{k} -> {v}" for k, v in paare if not _gefunden(v, tk)]
    r["glossar"] = {"soll": len(paare), "fehlt": fehlt,
                    "quote": round(1 - len(fehlt) / len(paare), 3) if paare else 1.0}
    r["glossar_ok"] = not paare or r["glossar"]["quote"] >= GLOSSAR_MIN or len(fehlt) < GLOSSAR_FEHL_MIN
    r["rot"] = [k for k, ok in (("abgeschnitten", not r["abgeschnitten"]), ("laenge", r["laenge_ok"]),
                                 ("glossar", r["glossar_ok"])) if not ok]
    return r


def _schlechter(a, b):
    """True, wenn Pruefung a schlechter als b ist."""
    return (len(a["rot"]), len(a["glossar"]["fehlt"])) > (len(b["rot"]), len(b["glossar"]["fehlt"]))


# ============================================================
# REGLER ZIELSPRACHEN (Sprachpaar)
# ============================================================

def ziel_setzen(werk, ziele, wer=None):
    """Zielsprachen neu: Produkte der alten Zielsprachen werden auf die neuen uebertragen. -> Bericht (str)."""
    from pipeline import kette, s095_produktwahl as s095
    b = bestellung.lesen(werk)
    src = b.quellsprache
    ziele = [z.strip().lower() for z in ziele if z.strip()]
    falsch = [z for z in ziele if z not in bestellung.sprachliste() or z == src]
    if falsch:
        raise ValueError(f"Zielsprache ungueltig (Sprachliste {bestellung.sprachliste()}, != Ausgangssprache {src}): {falsch}")
    alt = [z for z in b.zielsprachen if z != src]
    if ziele == alt:
        return "Zielsprachen unveraendert"
    vorlage = [p for p in b.produkte if alt and p["sprache"] == alt[0]] or \
        [bestellung.produkt_norm({"sprache": "", "inhalt": "text", "kanaele": ["taella"]})]
    neu = [dict(p) for p in b.produkte if p["sprache"] == src or p["sprache"] in ziele]
    for z in ziele:
        if z not in alt:
            neu += [dict(p, sprache=z) for p in vorlage]
    z_ = s095.zeichen(werk)
    vorher = (s095.angebot(b, z_) or {}).get("summe")
    bestellung.schreiben(werk, produkte=neu)
    b2 = bestellung.lesen(werk)
    nachher = (s095.angebot(b2, z_) or {}).get("summe")
    kette.bedarf_setzen(werk, wer=wer or STAGE)
    diff = None if vorher is None or nachher is None else round(nachher - vorher, 2)
    return (f"Zielsprachen {alt} -> {ziele}; Kostenangebot {vorher} $ -> {nachher} $"
            + (f" (Differenz {diff:+} $)" if diff is not None else "")
            + "; Stage-Liste neu gesetzt; 095 bei naechstem Kettenlauf neu annehmen")


# ============================================================
# LAUF
# ============================================================

def _parse_laenge(s):
    a, b = s.replace(",", ".").split("-", 1)
    return float(a), float(b)


def run(werk, wer=None, modell=None, abschnitt=None, kapitel=None, aus=None, laenge=None, ziel=None,
        uebernehmen=False, trocken=False):
    wer = wer or "pipeline"
    if ziel and not trocken:
        from pipeline import s080_mandant
        s080_mandant.darf(werk, "bestellen", wer)
        print(f"[300] {ziel_setzen(werk, ziel, wer)}")
    if aus is not None and not trocken:
        bestellung.feld_setzen(werk, voruebersetzung=bool(aus))
    g = gate.Gate(werk, STAGE, ruecksprung="300", wer=wer)
    b = bestellung.lesen(werk)
    src = b.quellsprache or config.SOURCE_LANGUAGE
    ziele = [z for z in (b.zielsprachen or []) if z != src]
    abschnitt = int(abschnitt or b.roh.get("voruebersetzung_abschnitt") or ABSCHNITT)
    laenge = laenge or LAENGE
    modell_eff = modell or config.MODELS.get("pretranslator")
    an = b.roh.get("voruebersetzung", True) is not False
    g.metrik("zielsprachen", ziele)
    g.metrik("modell", modell_eff)
    g.metrik("abschnitt", abschnitt)

    ip = config.work_path(werk, "210_profil")
    if not g.pflicht("profil", os.path.exists(ip), ruecksprung="210", text="210_profil.json vorhanden"):
        g.entscheide(schreiben=not trocken)
        return g
    with open(ip, encoding="utf-8") as f:
        data = json.load(f)
    profil = (data.get("meta") or {}).get("profile") or {}
    kap = kapitel_knoten(data, src)
    g.metrik("kapitel", len(kap))
    soll = ((status.laden(werk)["stages"].get("190") or {}).get("metriken") or {}).get("kapitel")
    if soll is not None:
        g.gleich("kapitel", len(kap), soll, ruecksprung="200")
    else:
        g.hinweis("kapitel_190", False, text="Kapitelzahl aus Gate 190 fehlt (nicht abgeglichen)")

    op = config.work_path(werk, "300_voruebersetzung")
    alt_pt = {}
    if (uebernehmen or trocken) and os.path.exists(op):
        with open(op, encoding="utf-8") as f:
            alt_pt = (json.load(f).get("meta") or {}).get("pretranslation") or {}
    if trocken and not alt_pt:
        g.pflicht("bestand", False, text="300_voruebersetzung.json fehlt (Probe ohne LLM)")
        g.entscheide(schreiben=False)
        return g

    if kapitel == ["alle"]:
        neu_k = set(kap)
    else:
        neu_k = {f"c{int(k):0{config.CHAPTER_DIGITS}d}" for k in (kapitel or [])}

    ck = manifest.Checkpoint(werk, STAGE)
    pt, pruef, fehlend, falsch, ohne = {}, {}, [], [], {lg: [] for lg in ziele}
    n_llm = n_neu = n_wdh = n_mock = 0
    for cid, knoten in kap.items():
        pt[cid] = {}
        quelle = " ".join(knoten)
        for lg in ziele:
            if not an or not knoten:
                pt[cid][lg] = ""
                if knoten:
                    ohne[lg].append(cid)
                continue
            aus_ = profil_ausschnitt(profil, quelle, lg)
            h = manifest.hash_obj([PROMPT_V, src, lg, knoten, aus_, modell_eff, abschnitt])
            if trocken:
                t = (alt_pt.get(cid) or {}).get(lg)
                daten = {"abschnitte": [t], "finish": [None], "versuch": 1} if t else None
            else:
                daten = None if cid in neu_k else ck.lesen(cid, lg, h)
                if daten is None and uebernehmen and cid not in neu_k and (alt_pt.get(cid) or {}).get(lg):
                    daten = {"abschnitte": [alt_pt[cid][lg]], "finish": [None], "versuch": 2,
                             "modell": "bestand", "abschnitt": abschnitt}
                    ck.schreiben(cid, lg, h, daten, herkunft="bestand")
                if daten is None:
                    try:
                        daten = dict(llm(werk, knoten, src, lg, aus_, abschnitt, modell), versuch=1, modell=modell_eff)
                    except Exception as e:                     # Aufruf gescheitert -> Kapitel fehlt
                        print(f"    [300] {cid}/{lg}: Aufruf gescheitert: {str(e)[:160]}")
                        fehlend.append(f"{cid}/{lg}")
                        continue
                    n_llm += len(daten["abschnitte"])
                    n_neu += 1
                    ck.schreiben(cid, lg, h, daten, herkunft="neu")
            if daten is None:
                fehlend.append(f"{cid}/{lg}")
                continue
            r = pruefen(quelle, daten, lg, aus_, laenge)
            if r["mock"]:
                n_mock += 1
            # 1x automatisch neu mit halbierten Abschnitten
            if r["rot"] and r["sprache_ok"] and daten.get("versuch", 1) < 2 and not trocken and not r["mock"]:
                halb = max(200, min(abschnitt, math.ceil(len(quelle) / (2 * max(1, len(daten["abschnitte"]))))))
                try:
                    d2 = dict(llm(werk, knoten, src, lg, aus_, halb, modell), versuch=2, modell=modell_eff)
                    n_llm += len(d2["abschnitte"])
                    n_wdh += 1
                    r2 = pruefen(quelle, d2, lg, aus_, laenge)
                    if _schlechter(r, r2) or not r2["rot"]:
                        daten, r = d2, r2
                    else:
                        daten = dict(daten, versuch=2)
                        r["versuch"] = 2
                    ck.schreiben(cid, lg, h, daten, herkunft="wiederholung")
                except Exception as e:
                    print(f"    [300] {cid}/{lg}: Wiederholung gescheitert: {str(e)[:160]}")
            pruef.setdefault(cid, {})[lg] = r
            if r["mock"] and mock.aktiv():
                pt[cid][lg] = "\n\n".join(daten["abschnitte"])
                continue
            if not r["sprache_ok"]:
                falsch.append(f"{cid}/{lg} ({r['sprache']})")
            if r["rot"]:
                ohne[lg].append(cid)
                r["ohne_anker"] = True
                pt[cid][lg] = ""
            else:
                pt[cid][lg] = "\n\n".join(daten["abschnitte"])
        if n_neu and not trocken:
            print(f"    {cid}: {', '.join(lg + (' ohne Anker' if cid in ohne[lg] else '') for lg in ziele)}")

    # Gate
    g.pflicht("vollstaendig", not fehlend, wert=len(fehlend), ruecksprung="300",
              text="Kapitel x Sprache vollstaendig" + (f"; fehlt: {fehlend[:8]}" if fehlend else ""))
    g.pflicht("sprache", not falsch, wert=len(falsch), ruecksprung="300",
              text="Zielsprache erkannt" + (f"; falsch: {falsch[:8]}" if falsch else ""))
    if not an:
        g.hinweis("abgeschaltet", False, text="Vorübersetzung abgeschaltet (--aus): 310 laeuft ohne Anker")
    for lg in ziele:
        if an and ohne[lg]:
            g.hinweis(f"ohne_anker_{lg}", False, wert=len(ohne[lg]),
                      text=f"{lg}: {len(ohne[lg])} Kapitel ohne Anker nach Wiederholung (310 ohne Anker): {ohne[lg][:10]}")
    g.mock(0 if mock.aktiv() else n_mock, ruecksprung="300")
    ls = sorted(r["laenge"] for k in pruef.values() for r in k.values() if r["laenge"] is not None
                and r["zeichen_quelle"] >= LAENGE_MIN_QUELLE)
    if ls:
        g.metrik("laenge", {"min": ls[0], "median": ls[len(ls) // 2], "max": ls[-1]})
    qs = [r["glossar"]["quote"] for k in pruef.values() for r in k.values() if r["glossar"]["soll"]]
    if qs:
        g.metrik("glossar_quote_min", min(qs))
    g.metrik("llm_aufrufe", n_llm)
    g.metrik("neu", n_neu)
    g.metrik("wiederholt", n_wdh)
    g.metrik("ohne_anker", ohne)

    if not trocken:
        data.setdefault("meta", {})["pretranslation"] = pt
        data["meta"]["voruebersetzung"] = {"modell": modell_eff, "abschnitt": abschnitt, "an": an,
                                           "ohne_anker": ohne, "prompt_v": PROMPT_V}
        manifest.json_atomar(op, data, indent=2)
        manifest.json_atomar(os.path.join(config.work_dir(werk), "300_pruefung.json"), pruef, indent=1)
        ck.aufraeumen([(c, lg) for c in kap for lg in ziele])
    g.entscheide(schreiben=not trocken)
    g.pruef = pruef
    return g


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 300 Vorübersetzung")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--ziel", help="Zielsprachen, z. B. de,fr (schreibt Bestellung um)")
    ap.add_argument("--modell")
    ap.add_argument("--abschnitt", type=int, help=f"Zeichen Quelltext je Aufruf (Standard {ABSCHNITT})")
    ap.add_argument("--kapitel", action="append", metavar="N|alle", help="Kapitel neu erzeugen (mehrfach)")
    ap.add_argument("--aus", action="store_true", help="Stage abschalten: 310 ohne Anker")
    ap.add_argument("--an", action="store_true", help="Stage wieder einschalten")
    ap.add_argument("--laenge", help="Laengenschwelle Ziel/Quelle, z. B. 0.8-1.6")
    ap.add_argument("--uebernehmen", action="store_true", help="vorhandene 300_voruebersetzung.json als Rohergebnis (ohne LLM)")
    ap.add_argument("--trocken", action="store_true", help="Probe am Bestand: nichts schreiben, kein LLM")
    a = ap.parse_args(argv)
    aus = False if a.aus else (True if a.an else None)
    kap = ["alle"] if a.kapitel and "alle" in a.kapitel else a.kapitel
    try:
        g = run(a.werk, a.wer, a.modell, a.abschnitt, kap, aus, _parse_laenge(a.laenge) if a.laenge else None,
                a.ziel.split(",") if a.ziel else None, a.uebernehmen, a.trocken)
    except gate.GateHalt as e:
        print(e)
        return e.exit_code
    except (ValueError, PermissionError) as e:
        print(f"[300] Fehler: {e}")
        return 1
    print(g.bericht())
    return gate.EXIT[g.ergebnis["ergebnis"]]


if __name__ == "__main__":
    sys.exit(main())
