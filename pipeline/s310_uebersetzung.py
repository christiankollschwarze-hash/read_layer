"""STAGE 310 — Übersetzung (Umbau Phase 2, GATE_KATALOG.md Zeile 310, 02.11.2026)
Funktion:     Satzgenaue, ID-gebundene Uebersetzung jedes Knotens in jede bestellte Zielsprache.
Wirkungsweise: Je Kapitel x Zielsprache Batches (Standard 25 Saetze) mit Stil/setting, den im Batch vorkommenden Figuren-,
              Glossar-, Unuebersetzt- und Redewendungs-Eintraegen aus 210 und dem passenden Ausschnitt der Vorübersetzung
              300 (nicht mehr das ganze Kapitel je Batch). Checkpoint je Kapitel x Sprache work/ckpt/310/<kap>__<lg>.json mit
              Hash je Satz: Neulauf uebersetzt nur neue/geaenderte Saetze; Kontextwechsel (Profil-Ausschnitt, Modell,
              Prompt-Version) -> Kapitel neu. Fehlende IDs bis 2x gezielt als Einzelsatz mit Nachbarn nachgefordert;
              auffaellige Saetze 1x einzeln neu (mit Befund als Hinweis), bessere Fassung bleibt.
Eingang:      work/300_voruebersetzung.json (Knoten, Profil, Anker), book.json (quellsprache, Zielsprachen aus 095,
              uebersetzung_anker, Titel je Sprache), work/310_korrekturen.json (manuelle Saetze / angenommene Befunde).
Ausgabe:      work/310_uebersetzung.json (Format unveraendert: content[id][lg]; meta.uebersetzung), work/310_pruefung.json
              (Liste je Sprache: Satz, Quelle, Ziel, Befund), ePub-Weg: Werktitel je Zielsprache in book.json fassungen[].
Gate:         Abdeckung 100 % (nach 2 Nachforderungen Luecke -> Stopp); je Satz: Sprache = Zielsprache, keine Kopie der Quelle
              (ausser Namen/Ausrufe), Laenge 0,5–2,0 (Ausreisser <= 2 %), Satzzahl Ziel <= Quelle (Verschmelzungsverdacht,
              zusammen mit Laenge > 1,6), Glossar/Namen/Unuebersetzt >= 98 %, Ueberschrift behaelt Kapitelnummer (Schema)
              -> 1x automatisch einzeln neu, danach Mensch (Liste); ePub-Weg: Werktitel je Zielsprache vorhanden (sonst
              1 Aufruf, Pruefung am Cover-Gate 615); Mock im Live-Lauf -> Stopp. Mensch-Freigabe gilt bei gleichem ausgabe_hash.
Kosten:       deepseek-v4-pro (config.MODELS translator); usage_log Stage 310 mit Sprache.
Regler:       --ziel de,fr (wie 300), --modell, --batch N, --kapitel N|alle, --satz ID (neu uebersetzen, mehrfach),
              --satz-text ID=TEXT (manuell, Sprache mit --lang), --annehmen ID (Befund annehmen), --anker an|aus,
              --laenge 0.5-2.0, --lang LG (nur diese Zielsprache), --uebernehmen (vorhandene 310_uebersetzung.json als
              Rohergebnis, ohne LLM), --trocken (Probe, schreibt nichts). Glossar/Namen: Regler in 210 (--glossar/--figur).
Aufruf:
  python -m pipeline.s310_uebersetzung <werk> [Regler] [--wer CK]
Exit: 0 auto, 2 Stopp, 3 Mensch, 1 Fehler.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import api_layer, bestellung, gate, manifest, mock, status, usage_log
from pipeline import s300_voruebersetzung as s300
from tools import satzweise, sprache

STAGE = "310"
PROMPT_V = 2
BATCH = 25
LAENGE = (0.5, 2.0)
LAENGE_MIN_QUELLE = 40
AUSREISSER_MAX = 0.02
GLOSSAR_MIN = 0.98
VERSCHMELZ_LAENGE = 1.6
SPRACHE_MIN_WOERTER = 8
ANKER_RAND = 400


# ============================================================
# EINGANG
# ============================================================

def saetze(data, src):
    """-> {kap: [(id, quelltext, typ)]} (uebersetzbare Knoten in Reihenfolge)."""
    kap = {}
    for tid, e in (data.get("content") or {}).items():
        cid = tid.split("_")[0]
        kap.setdefault(cid, [])
        if not isinstance(e, dict) or e.get("type") in config.NO_AUDIO_TYPES:
            continue
        t = (e.get(src) or "").strip()
        if t:
            kap[cid].append((tid, t, e.get("type")))
    return kap


def profil_ausschnitt(profil, text, lg):
    aus = s300.profil_ausschnitt(profil, text, lg)
    tk = text.lower()
    aus["idioms"] = {k: (v.get(lg) or v.get("meaning") or "").strip()
                     for k, v in (profil.get("idioms") or {}).items()
                     if isinstance(v, dict) and s300._kommt_vor(k, tk) and (v.get(lg) or v.get("meaning"))}
    return aus


def anker_ausschnitt(anker, quelle_gesamt, von, bis):
    """Proportionaler Ausschnitt der Vorübersetzung fuer die Zeichen [von, bis) des Kapitels (+ Rand)."""
    if not anker or not quelle_gesamt:
        return ""
    r = len(anker) / len(quelle_gesamt)
    a = max(0, int(von * r) - ANKER_RAND)
    b = min(len(anker), int(bis * r) + ANKER_RAND)
    if a > 0:
        m = re.search(r"[.!?…]\s+", anker[a:b])
        a = a + m.end() if m else a
    if b < len(anker):
        m = list(re.finditer(r"[.!?…][\"”“»«’']?\s", anker[a:b]))
        b = a + m[-1].end() if m else b
    return anker[a:b].strip()


# ============================================================
# PROMPT / LLM
# ============================================================

def _build_prompt(items, src, lg, aus, anker="", nachbarn=None, hinweis=None):
    lines = "\n".join(f"  {json.dumps(tid)}: {json.dumps(s, ensure_ascii=False)}" for tid, s in items)
    st = aus.get("style") or {}
    bits = [f"{k.capitalize()}: {st[k]}" for k in ("setting", "tone", "register", "notes") if st.get(k)]
    teile = []
    if bits:
        teile.append("Keep the translation faithful to the work's period and style. Choose era-appropriate wording "
                     "(avoid anachronistic modern terms). Context:\n- " + "\n- ".join(bits))
    if aus.get("characters"):
        teile.append("Character names (use exactly these forms):\n" +
                     "\n".join(f'"{k}" -> "{v}"' for k, v in aus["characters"].items()))
    if aus.get("glossary"):
        teile.append("Use these fixed translations:\n" + "\n".join(f'"{k}" -> "{v}"' for k, v in aus["glossary"].items()))
    if aus.get("untranslated"):
        teile.append("Keep these terms untranslated: " + ", ".join(f'"{k}"' for k in aus["untranslated"]))
    if aus.get("idioms"):
        teile.append("Idioms (render the meaning idiomatically):\n" +
                     "\n".join(f'"{k}" -> "{v}"' for k, v in aus["idioms"].items()))
    if any("_vs" in tid for tid, _ in items):
        teile.append("IDs containing '_vs' are song/verse stanzas: translate them as verse in "
                     f"{lg} -- same number of lines (keep every \\n), keep rhyme, rhythm and playfulness; "
                     "meaning may move freely within the stanza.")
    if anker:
        teile.append(f"For context, here is a free translation of this passage in {lg} (do NOT copy it verbatim, "
                     f"use it only to keep meaning and flow consistent):\n{anker}")
    if nachbarn:
        teile.append("Surrounding sentences (context only, do NOT return them):\n" +
                     "\n".join(f"- {q}" + (f"  =>  {z}" if z else "") for q, z in nachbarn))
    if hinweis:
        teile.append(f"A previous attempt had a problem: {hinweis}. Fix it.")
    kontext = ("\n" + "\n\n".join(teile) + "\n") if teile else ""
    return f"""Translate each sentence from {src} into {lg}.
Translate directly from the source, never through a third language.

Each sentence has a unique ID. Return the translation under the SAME ID.
You MUST return every ID exactly once -- including very short ones like "See?",
"Why not?" or "Just think!". Never merge two sentences into one entry, and
never split one sentence into two entries. Keep one translation per ID.
{kontext}
Return ONLY a JSON object mapping each ID to its translation, nothing else:
{{ "<id1>": "<translation>", "<id2>": "<translation>", ... }}

There are exactly {len(items)} IDs to translate.

Sentences (as JSON, id -> source text):
{{
{lines}
}}"""


def llm(werk, items, src, lg, aus, anker="", nachbarn=None, hinweis=None, modell=None):
    """-> {id: text} (nur nicht-leere Strings)."""
    if not items:
        return {}
    alt = config.MODELS.get("translator")
    if modell:
        config.MODELS["translator"] = modell
    usage_log.set_context(werk, STAGE, sprache=lg)
    try:
        if config.RUN_MODE == "mock":
            raw = api_layer.call_model("translator", "", target_lang=lg, sentences=[s for _, s in items])
            lst = (api_layer.parse_json(raw) or {}).get("translations", [])
            return {tid: lst[i] for i, (tid, _) in enumerate(items) if i < len(lst)}
        raw = api_layer.call_model("translator", _build_prompt(items, src, lg, aus, anker, nachbarn, hinweis),
                                   max_tokens=8000)
    except EnvironmentError:
        raise
    except Exception as e:                       # Netz/API: Saetze bleiben offen -> Nachforderung bzw. Luecke
        print(f"      ! Aufruf gescheitert ({lg}): {str(e)[:120]}")
        return {}
    finally:
        config.MODELS["translator"] = alt
    try:
        p = api_layer.parse_json(raw)
    except Exception as e:
        print(f"      ! JSON-Fehler ({lg}): {str(e)[:100]}")
        return {}
    if isinstance(p, dict) and isinstance(p.get("translations"), dict):
        p = p["translations"]
    if not isinstance(p, dict):
        return {}
    return {k: v.strip() for k, v in p.items() if isinstance(v, str) and v.strip()}


# ============================================================
# PRUEFUNG JE SATZ
# ============================================================

def _norm(s):
    return re.sub(r"[\W_]+", " ", (s or "").lower()).strip()


_ROEM = re.compile(r"\b[IVXLCDM]{1,7}\b")


def _nummern(s):
    """Kapitelnummern als int (arabisch und roemisch; 'I' allein ausgenommen, Pronomen)."""
    n = {int(x) for x in re.findall(r"\d+", s or "")}
    n |= {_roem_int(x) for x in _ROEM.findall(s or "") if x != "I" and _roem_int(x)}
    return n


def schema_ok(q, z):
    """Ueberschrift: jede Nummer der Quelle steht (arabisch oder roemisch) auch im Ziel."""
    return _nummern(q) <= _nummern(z)


def pruefe_satz(q, z, typ, src, lg, aus, laenge=LAENGE):
    """-> Liste Befunde (leer = ok)."""
    b = []
    if not (z or "").strip():
        return ["fehlt"]
    if mock.ist_text(z):
        return []
    erk, _a = sprache.erkennen(z, min_woerter=SPRACHE_MIN_WOERTER)
    if erk and erk != lg:
        b.append(f"sprache:{erk}")
    funktion = sum(1 for w in sprache.woerter(q) if w in sprache.STOPP.get(src, ()))
    if funktion >= 2 and _norm(q) == _norm(z):
        b.append("kopie")
    r = len(z) / len(q) if q else 1.0
    if len(q) >= LAENGE_MIN_QUELLE and not (laenge[0] <= r <= laenge[1]):
        b.append(f"laenge:{r:.2f}")
    if typ != "vs" and len(q) >= LAENGE_MIN_QUELLE:
        nq = len(satzweise.satzgrenzen(q, src)) + 1
        nz = len(satzweise.satzgrenzen(z, lg)) + 1
        if nz > nq and r > VERSCHMELZ_LAENGE:
            b.append(f"verschmelzung:{nz}>{nq}")
    paare = s300.erwartet(profil_ausschnitt_satz(aus, q))
    zk = z.lower()
    fehlt = [f"{k}->{v}" for k, v in paare if not s300._gefunden(v, zk)]
    if fehlt:
        b.append("glossar:" + "; ".join(fehlt[:3]))
    if typ == "h" and not schema_ok(q, z):
        b.append("schema")
    return b


def profil_ausschnitt_satz(aus, q):
    """Kapitel-Ausschnitt auf die im Satz vorkommenden Eintraege einschraenken."""
    qk = q.lower()
    return {"glossary": {k: v for k, v in aus.get("glossary", {}).items() if s300._kommt_vor(k, qk)},
            "characters": {k: v for k, v in aus.get("characters", {}).items() if s300._kommt_vor(k, qk)},
            "untranslated": [k for k in aus.get("untranslated", []) if s300._kommt_vor(k, qk)]}


_ROEM_GUELTIG = re.compile(r"^M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")


def _roem_int(s):
    w = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    if not s or not _ROEM_GUELTIG.match(s):
        return None
    n = 0
    for i, c in enumerate(s):
        n += -w[c] if i + 1 < len(s) and w[s[i + 1]] > w[c] else w[c]
    return n


def _rang(befunde):
    return (sum(1 for x in befunde if not x.startswith("glossar")), len(befunde))


# ============================================================
# KORREKTUREN / TITEL
# ============================================================

def _korr_pfad(werk):
    return os.path.join(config.work_dir(werk), "310_korrekturen.json")


def korrekturen_lesen(werk):
    try:
        with open(_korr_pfad(werk), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def korrektur_setzen(werk, lg, tid, q, text=None, annehmen=False, wer=None):
    k = korrekturen_lesen(werk)
    e = k.setdefault(lg, {}).setdefault(tid, {})
    e.update({"q": manifest.hash_text(q), "wer": wer, "wann": manifest.jetzt()})
    if text is not None:
        e["text"] = text
    if annehmen:
        e["angenommen"] = True
    manifest.json_atomar(_korr_pfad(werk), k, indent=1)


def titel_pruefen(werk, b, src, ziele, trocken, modell=None):
    """ePub-Weg: Werktitel je Zielsprache. -> (fehlend, neu uebersetzt)."""
    fass = {f.get("sprache"): f for f in b.roh.get("fassungen") or [] if isinstance(f, dict)}
    orig = (b.roh.get("titel_original") or (fass.get(src) or {}).get("titel") or "").strip()
    fehlt = [lg for lg in ziele if not (fass.get(lg) or {}).get("titel")]
    if trocken or not fehlt or not orig:
        return fehlt, []
    neu = []
    for lg in fehlt:
        usage_log.set_context(werk, STAGE, sprache=lg)
        if config.RUN_MODE == "mock":
            t = f"[MOCK:titel {lg}] {orig}"
        else:
            t = api_layer.call_model("translator", f"Translate this book title from {src} into {lg} as a publisher "
                                     f"would title the translated edition. Return ONLY the title.\n\n{orig}",
                                     max_tokens=200).strip().strip('"“”„')
        if t:
            e = fass.setdefault(lg, {"sprache": lg})
            e.update({"titel": t, "titel_quelle": "310", "titel_pruefen": True})
            neu.append(lg)
    if neu:
        alle = [f for f in b.roh.get("fassungen") or [] if isinstance(f, dict) and f.get("sprache") not in fass]
        bestellung.feld_setzen(werk, fassungen=alle + list(fass.values()))
    return [lg for lg in fehlt if lg not in neu], neu


# ============================================================
# LAUF
# ============================================================

def _parse_bereich(s):
    a, b = s.replace(",", ".").split("-", 1)
    return float(a), float(b)


def uebersetze_kapitel(werk, liste, src, lg, aus, anker, ck_alt, batch, modell, neu_ids, zaehler):
    """Fehlende/geaenderte Saetze in Batches uebersetzen. -> {id: {q, t, v}} (v = Versuche Einzelsatz)."""
    gesamt = " ".join(q for _t, q, _y in liste)
    hq = {tid: manifest.hash_text(q) for tid, q, _y in liste}
    res = {}
    offen = []
    for tid, q, _y in liste:
        alt = (ck_alt or {}).get(tid)
        if alt and alt.get("q") == hq[tid] and tid not in neu_ids and alt.get("t"):
            res[tid] = alt
        else:
            offen.append(tid)
    pos, p = {}, 0
    for tid, q, _y in liste:
        pos[tid] = (p, p + len(q))
        p += len(q) + 1
    qtext = {tid: q for tid, q, _y in liste}
    # zusammenhaengende Batches ueber die offenen Saetze
    for i in range(0, len(offen), batch):
        teil = offen[i:i + batch]
        a = anker_ausschnitt(anker, gesamt, pos[teil[0]][0], pos[teil[-1]][1])
        got = llm(werk, [(t, qtext[t]) for t in teil], src, lg, aus, a, modell=modell)
        zaehler["llm"] += 1
        for t in teil:
            if got.get(t):
                res[t] = {"q": hq[t], "t": got[t], "v": 0}
    return res


def _nachbarn(liste, idx, res):
    out = []
    for j in (idx - 1, idx + 1):
        if 0 <= j < len(liste):
            t, q, _y = liste[j]
            out.append((q, (res.get(t) or {}).get("t")))
    return out


def run(werk, wer=None, modell=None, batch=None, kapitel=None, saetze_neu=None, satz_text=None, annehmen=None,
        anker=None, laenge=None, nur_lang=None, ziel=None, uebernehmen=False, trocken=False):
    wer = wer or "pipeline"
    if ziel and not trocken:
        from pipeline import s080_mandant
        s080_mandant.darf(werk, "bestellen", wer)
        print(f"[310] {s300.ziel_setzen(werk, ziel, wer)}")
    if anker is not None and not trocken:
        bestellung.feld_setzen(werk, uebersetzung_anker=bool(anker))
    g = gate.Gate(werk, STAGE, ruecksprung="310", wer=wer)
    b = bestellung.lesen(werk)
    src = b.quellsprache or config.SOURCE_LANGUAGE
    ziele = [z for z in (b.zielsprachen or []) if z != src]
    if nur_lang:
        ziele = [z for z in ziele if z == nur_lang]
    batch = int(batch or b.roh.get("uebersetzung_batch") or getattr(config, "TRANSLATE_BATCH_SIZE", BATCH))
    laenge = laenge or LAENGE
    modell_eff = modell or config.MODELS.get("translator")
    mit_anker = b.roh.get("uebersetzung_anker", True) is not False
    g.metrik("zielsprachen", ziele)
    g.metrik("modell", modell_eff)
    g.metrik("batch", batch)
    g.metrik("anker", mit_anker)

    ip = config.work_path(werk, "300_voruebersetzung")
    if not g.pflicht("voruebersetzung", os.path.exists(ip), ruecksprung="300", text="300_voruebersetzung.json vorhanden"):
        g.entscheide(schreiben=not trocken)
        return g
    with open(ip, encoding="utf-8") as f:
        data = json.load(f)
    meta = data.get("meta") or {}
    profil = meta.get("profile") or {}
    pt = meta.get("pretranslation") or {}
    kap = saetze(data, src)
    alle_ids = [t for l in kap.values() for t, _q, _y in l]
    g.metrik("kapitel", len(kap))
    g.metrik("saetze", len(alle_ids))

    # Manuelle Regler (je eine Zielsprache)
    qmap = {t: q for l in kap.values() for t, q, _y in l}
    lg_regler = nur_lang or (ziele[0] if len(ziele) == 1 else None)
    if (satz_text or annehmen) and not trocken:
        if not lg_regler:
            raise ValueError("--satz-text/--annehmen brauchen --lang bei mehreren Zielsprachen")
        for x in satz_text or []:
            tid, t = x.split("=", 1)
            if tid not in qmap:
                raise ValueError(f"unbekannte ID {tid}")
            korrektur_setzen(werk, lg_regler, tid, qmap[tid], text=t.strip(), wer=wer)
        for tid in annehmen or []:
            if tid not in qmap:
                raise ValueError(f"unbekannte ID {tid}")
            korrektur_setzen(werk, lg_regler, tid, qmap[tid], annehmen=True, wer=wer)
    korr = korrekturen_lesen(werk)

    alt310 = {}
    op = config.work_path(werk, "310_uebersetzung")
    if (uebernehmen or trocken) and os.path.exists(op):
        with open(op, encoding="utf-8") as f:
            alt310 = json.load(f).get("content") or {}
    if trocken and not alt310:
        g.pflicht("bestand", False, text="310_uebersetzung.json fehlt (Probe ohne LLM)")
        g.entscheide(schreiben=False)
        return g

    if kapitel == ["alle"]:
        neu_k = set(kap)
    else:
        neu_k = {f"c{int(k):0{config.CHAPTER_DIGITS}d}" for k in (kapitel or [])}
    neu_ids = set(saetze_neu or [])

    ck = manifest.Checkpoint(werk, STAGE)
    z = {"llm": 0, "nachgefordert": 0, "einzeln": 0}
    luecken, befunde, pruef = {}, {}, {}
    n_mock = 0
    for lg in ziele:
        luecken[lg], befunde[lg] = [], []
        for cid, liste in kap.items():
            if not liste:
                continue
            quelle = " ".join(q for _t, q, _y in liste)
            aus = profil_ausschnitt(profil, quelle, lg)
            kontext = manifest.hash_obj([PROMPT_V, src, lg, aus, modell_eff])
            hq = {t: manifest.hash_text(q) for t, q, _y in liste}
            anker_txt = (pt.get(cid) or {}).get(lg, "") if mit_anker else ""
            if trocken:
                res = {t: {"q": hq[t], "t": (alt310.get(t) or {}).get(lg, ""), "v": 1} for t, _q, _y in liste
                       if (alt310.get(t) or {}).get(lg)}
            else:
                alt = None if cid in neu_k else ck.lesen(cid, lg, kontext)
                alt = (alt or {}).get("saetze") or {}
                if uebernehmen and cid not in neu_k:
                    for t, _q, _y in liste:
                        v = (alt310.get(t) or {}).get(lg)
                        if v and t not in alt and t not in neu_ids:
                            alt[t] = {"q": hq[t], "t": v, "v": 1}
                res = uebersetze_kapitel(werk, liste, src, lg, aus, anker_txt, alt, batch, modell, neu_ids, z)
                # fehlende IDs: bis 2x einzeln mit Nachbarn
                for _runde in range(2):
                    fehlt = [i for i, (t, _q, _y) in enumerate(liste) if t not in res]
                    for i in fehlt:
                        t, q, _y = liste[i]
                        got = llm(werk, [(t, q)], src, lg, aus, nachbarn=_nachbarn(liste, i, res), modell=modell)
                        z["llm"] += 1
                        z["nachgefordert"] += 1
                        if got.get(t):
                            res[t] = {"q": hq[t], "t": got[t], "v": 0}
                # auffaellige Saetze: 1x einzeln neu
                for i, (t, q, y) in enumerate(liste):
                    e = res.get(t)
                    if not e or e.get("v", 0) >= 1:
                        continue
                    bf = pruefe_satz(q, e["t"], y, src, lg, aus, laenge)
                    if bf and bf != ["fehlt"]:
                        got = llm(werk, [(t, q)], src, lg, aus, nachbarn=_nachbarn(liste, i, res),
                                  hinweis=f"{', '.join(bf)} (previous: {e['t'][:300]})", modell=modell)
                        z["llm"] += 1
                        z["einzeln"] += 1
                        if got.get(t) and _rang(pruefe_satz(q, got[t], y, src, lg, aus, laenge)) < _rang(bf):
                            e = {"q": hq[t], "t": got[t]}
                    e["v"] = 1
                    res[t] = e
                ck.schreiben(cid, lg, kontext, {"saetze": res})
            # Korrekturen + Befunde
            kk = korr.get(lg) or {}
            for t, q, y in liste:
                k = kk.get(t)
                if k and k.get("q") == hq[t] and k.get("text"):
                    res[t] = {"q": hq[t], "t": k["text"], "v": 1, "manuell": True}
                e = res.get(t)
                if not e:
                    luecken[lg].append(t)
                    continue
                if mock.ist_text(e["t"]):
                    n_mock += 1
                data["content"][t][lg] = e["t"]
                if e.get("manuell") or (k and k.get("q") == hq[t] and k.get("angenommen")):
                    continue
                bf = pruefe_satz(q, e["t"], y, src, lg, aus, laenge)
                if bf:
                    befunde[lg].append({"id": t, "quelle": q, "ziel": e["t"], "befund": bf})

    # Anfuehrungszeichen DE (Smoke #8)
    if "de" in ziele:
        for e in data["content"].values():
            if isinstance(e, dict) and isinstance(e.get("de"), str):
                e["de"] = anfuehrung_de(e["de"])

    # Titel ePub-Weg
    from pipeline import s090_eingang
    epub = s090_eingang.eingangsart(b.roh)[0] in ("user_epub", "verlag_epub")
    if epub:
        t_fehlt, t_neu = titel_pruefen(werk, b, src, ziele, trocken, modell)
        z["llm"] += len(t_neu)
        g.pflicht("werktitel", not t_fehlt, wert=t_fehlt or None, ruecksprung="310",
                  text="Werktitel je Zielsprache" + (f" fehlt: {t_fehlt}" if t_fehlt else "") +
                  (f" (neu uebersetzt {t_neu}, Pruefung am Cover-Gate 615)" if t_neu else ""))

    # Gate
    n = max(1, len(alle_ids))
    for lg in ziele:
        bf = befunde[lg]
        art = lambda p: [x for x in bf if any(b_.startswith(p) for b_ in x["befund"])]
        g.pflicht(f"abdeckung_{lg}", not luecken[lg], wert=len(luecken[lg]), ruecksprung="310",
                  text=f"{lg}: Abdeckung " + ("100 %" if not luecken[lg] else f"Luecken {len(luecken[lg])}: {luecken[lg][:6]}"))
        for name, pre, schwelle in (("sprache", "sprache", 0), ("kopie", "kopie", 0), ("verschmelzung", "verschmelzung", 0),
                                    ("schema", "schema", 0)):
            l = art(pre)
            g.pruefe(f"{name}_{lg}", len(l) <= schwelle, wert=len(l), schwelle=f"<= {schwelle}", bei_fehler="mensch",
                     text=f"{lg}: {name} {len(l)}" + (f" {[x['id'] for x in l[:5]]}" if l else ""))
        l = art("laenge")
        g.pruefe(f"laenge_{lg}", len(l) / n <= AUSREISSER_MAX, wert=round(len(l) / n, 4), schwelle=f"<= {AUSREISSER_MAX}",
                 bei_fehler="mensch", text=f"{lg}: Laengen-Ausreisser {len(l)}/{n}" + (f" {[x['id'] for x in l[:5]]}" if l else ""))
        l = art("glossar")
        g.pruefe(f"glossar_{lg}", 1 - len(l) / n >= GLOSSAR_MIN, wert=round(1 - len(l) / n, 4), schwelle=f">= {GLOSSAR_MIN}",
                 bei_fehler="mensch", ruecksprung="210",
                 text=f"{lg}: Glossar/Namen eingehalten {1 - len(l) / n:.1%}" + (f" {[x['id'] for x in l[:5]]}" if l else ""))
        pruef[lg] = bf
        g.metrik(f"befunde_{lg}", len(bf))
    g.mock(0 if mock.aktiv() else n_mock, ruecksprung="310")
    if not mit_anker:
        g.hinweis("anker", False, text="Anker abgeschaltet (--anker aus)")
    ohne = (meta.get("voruebersetzung") or {}).get("ohne_anker") or {}
    if any(ohne.get(lg) for lg in ziele):
        g.hinweis("ohne_anker", False, text=f"Kapitel ohne Anker aus 300: { {lg: len(ohne.get(lg) or []) for lg in ziele} }")
    for k_, v in z.items():
        g.metrik(k_, v)

    meta["uebersetzung"] = {"modell": modell_eff, "batch": batch, "anker": mit_anker, "prompt_v": PROMPT_V}
    data["meta"] = meta
    aus_hash = manifest.hash_obj({lg: {t: (data["content"][t] or {}).get(lg) for t in alle_ids} for lg in ziele})
    g.metrik("ausgabe_hash", aus_hash)
    st = status.laden(werk)["stages"].get(STAGE) or {}
    freigegeben = st.get("zustand") == "frei" and (st.get("gate") or {}).get("ergebnis") == "mensch" \
        and (st.get("metriken") or {}).get("ausgabe_hash") == aus_hash
    if freigegeben:
        for p in g.pruefungen:
            if not p["ok"] and p["bei_fehler"] == "mensch":
                p["bei_fehler"] = "hinweis"
                p["text"] += " [Mensch-Freigabe gilt, Ausgabe unveraendert]"
    if not trocken:
        manifest.json_atomar(op, data, indent=2)
        manifest.json_atomar(os.path.join(config.work_dir(werk), "310_pruefung.json"), pruef, indent=1)
        if not nur_lang:
            ck.aufraeumen([(c, lg) for c, l in kap.items() if l for lg in ziele])
    g.entscheide(schreiben=not trocken)
    g.pruef = pruef
    return g


# ============================================================
# ANFUEHRUNGSZEICHEN DE (unveraendert)
# ============================================================

_AUF_VOR = set(" \t\n([{—–-/ ")
_ZEICHEN_NACH = set(" \t\n,.;:!?…")


def anfuehrung_de(text: str) -> str:
    """24.10.2026 (Smoke #8): deutsche Anfuehrungszeichen vereinheitlichen.
    Doppelt: " “ ” -> „ (oeffnend) / “ (schliessend). Einfach (nur paarig): ' ‘ ’ -> ‚…‘.
    Apostrophe im Wort (geht's) bleiben. Idempotent; Guillemets bleiben unberuehrt."""
    if not text or not any(c in text for c in "\"“”'‘’"):
        return text
    out, offen = [], False
    for i, c in enumerate(text):
        if c == "„":
            offen = True
            out.append(c)
            continue
        if c not in "\"“”":
            out.append(c)
            continue
        vor = text[i - 1] if i else " "
        nach = text[i + 1] if i + 1 < len(text) else " "
        if not offen and vor in _AUF_VOR and nach not in _ZEICHEN_NACH:
            out.append("„")
            offen = True
        else:
            out.append("“")
            offen = False
    t = "".join(out)
    t = re.sub(r"(?<![\w])['‘’‚](?=\w)(.+?)(?<=[\w.!?,…])['‘’](?![\w])",
               "‚\\1‘", t)
    return t


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 310 Übersetzung")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--ziel", help="Zielsprachen, z. B. de,fr (schreibt Bestellung um)")
    ap.add_argument("--modell")
    ap.add_argument("--batch", type=int)
    ap.add_argument("--kapitel", action="append", metavar="N|alle")
    ap.add_argument("--satz", action="append", metavar="ID", help="Satz neu uebersetzen")
    ap.add_argument("--satz-text", action="append", metavar="ID=TEXT", help="Satz manuell ersetzen")
    ap.add_argument("--annehmen", action="append", metavar="ID", help="Befund annehmen")
    ap.add_argument("--anker", choices=["an", "aus"])
    ap.add_argument("--laenge", help="z. B. 0.5-2.0")
    ap.add_argument("--lang", help="nur diese Zielsprache")
    ap.add_argument("--uebernehmen", action="store_true")
    ap.add_argument("--trocken", action="store_true")
    a = ap.parse_args(argv)
    kap = ["alle"] if a.kapitel and "alle" in a.kapitel else a.kapitel
    try:
        g = run(a.werk, a.wer, a.modell, a.batch, kap, a.satz, a.satz_text, a.annehmen,
                None if a.anker is None else a.anker == "an", _parse_bereich(a.laenge) if a.laenge else None,
                a.lang, a.ziel.split(",") if a.ziel else None, a.uebernehmen, a.trocken)
    except gate.GateHalt as e:
        print(e)
        return e.exit_code
    except (ValueError, PermissionError) as e:
        print(f"[310] Fehler: {e}")
        return 1
    print(g.bericht())
    return gate.EXIT[g.ergebnis["ergebnis"]]


if __name__ == "__main__":
    sys.exit(main())
