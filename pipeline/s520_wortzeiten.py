"""STAGE 520 — Wortzeiten inkl. 525 Wortbruecke (Phase 2, 03.11.2026, GATE_KATALOG.md Zeile 520)
Funktion:     Wort-Zeitstempel fuer das Karaoke-Highlighting der TAELLA-App, je Audiosprache mit TAELLA-Audioprodukt und
              Spur: Hoerbuch (fassungen/<lg>/audio_final/) und Hoerspiel (fassungen/<lg>/hoerspiel_final/), beide aus
              530. Danach (Teil der Stage, ein Gate) die Wortbruecke 525: je Anker aus 340 die Wortzeit im Quell-Audio (t)
              und im Ziel-Audio (tz), Hoerspiel ths/tzhs.
Wirkungsweise: Forced Alignment (MMS_FA, pipeline/fa_mms.py; Modal mit CPU-Rueckfall ueber s510.zeiten) je Endfassung auf
              dem gesprochenen Text (Sprechtext 400 + Aussprache-Lexikon wie 500). Rueckabbildung je Lautwort ueber die
              Herkunft der Lexikon-Ersetzungen und die 400-Abbildung (Sprechtext-Span -> Lesetext-Span) auf die
              \\S+-Tokens des Lesetexts ("Chapter IV" gesprochen "four" -> Token "IV"). Hash je Satz (Datei-Hash 530 +
              FA-Text + Lesetext + Abbildung): nur neue/geaenderte Saetze werden gemessen (geaenderte WAV -> automatisch
              neu). Auffaelliger Satz (ohne Zeiten, Lautwoerter unter Schwelle, ausserhalb der Dauer, nicht monoton) ->
              1x automatisch neu auf CPU (wenn Modal), danach Pruefliste.
Eingang:      work/530_pruefung_<lg>.json + Endfassungen (Gate 530 frei), work/400_regie.json (Lesetext, Sprechtext,
              Abbildung, Ansagen), work/340_wortalignment.json (Anker, Gate 340 frei, wenn 340 im Bedarf), Lexikon
              work/aussprache_<lg>.json (freigegeben), book.json (Bestellung, wortzeiten_regler).
Ausgabe:      work/520_wortzeiten_<lg>.json bzw. 520_wortzeiten_<lg>_hoerspiel.json
                {sprache, spur, einheit, version, tags {tid: [{i, t0, t1}]}, saetze {tid: {h, fa, laut, laut_zeit,
                 dauer, befund, unplausibel, versuch, manuell?}}, meta}
              (i = \\S+-Token im Lesetext der Sprache = s340-Index in der Quellsprache; Sekunden clip-relativ in der
              Endfassung 530 – Tempo ist dort schon angewandt, playbackRate der App bleibt unabhaengig);
              work/525_wortbruecke.json {quelle, ziel, tags, messung, hoerspiel, je_ziel {lg: {tags, messung,
              hoerspiel}}} (tags/messung = erste Zielsprache, Altschnittstelle 710); work/520_pruefung.json (Pruefliste);
              work/520_korrekturen.json (manuelle Wortzeiten mit Satz-Hash).
Gate:         je Sprache x Spur: Audio mit TAELLA bestellt, 400 vorhanden, Regler gueltig, Gate 530 (und 340) frei,
              Endfassung 530 aktuell je Satz (Teillauf: ausserhalb Auswahl nur Hinweis), Lesetext 400 = Text 340, FA
              verfuegbar -> sonst Stopp; Saetze ohne Wortzeiten = 0, Lautwoerter mit Zeit >= 98 %, ausserhalb Dauer = 0,
              nicht monoton = 0, unplausible Wortdauer (0,03–2,0 s) <= 1 % -> sonst Mensch; je Zielsprache Anker mit Zeit
              >= 95 % (Ruecksprung 340) -> sonst Mensch. Mensch-Freigabe gilt bei gleichem ausgabe_hash.
Kosten:       usage_log Stage 520 (Modal-Sekunden FA je Sprache); CPU 0 $.
Regler:       book.json wortzeiten_regler: --fa modal|cpu, --wiederholen an|aus, --interpolation an|aus (525),
              --lautwoerter-min, --anker-min, --wortdauer-min, --wortdauer-max, --unplausibel-max, --toleranz-s;
              dazu --zeit LG:TID:I=T0,T1 (Wortzeit manuell, mit --spur), --satz ID (neu messen), --kapitel c001,c002,
              --lang, --spur hoerbuch|hoerspiel, --neu, --trocken.
Aufruf:       py -3.11 -m pipeline.s520_wortzeiten <werk> [Regler] [--wer CK]
Exit: 0 auto, 2 Stopp, 3 Mensch, 1 Fehler.
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import bestellung, gate, kette, manifest, status, usage_log
from pipeline import s420_sprecher as s420
from pipeline import s500_vertonung_gemini as s500
from pipeline import s510_hoerspiel_hybrid as s510
from pipeline import s525_wortbruecke as s525
from pipeline import sprechtext as st
from pipeline.fa_mms import Aligner as _Aligner  # noqa: F401  (Altschnittstelle tools/ap60_c.py)

STAGE = "520"
VERSION = 1
SPUREN = ("hoerbuch", "hoerspiel")
ZUSATZ = {"hoerbuch": "", "hoerspiel": "_hoerspiel"}
FINAL = {"hoerbuch": "audio_final", "hoerspiel": "hoerspiel_final"}
EINHEIT = "sekunden_clip_relativ_endfassung_530"
REGLER_STD = {"fa": "modal", "wiederholen": True, "interpolation": True, "lautwoerter_min": 0.98, "anker_min": 0.95,
              "wortdauer_min": 0.03, "wortdauer_max": 2.0, "unplausibel_max": 0.01, "toleranz_s": 0.05}
AUFFAELLIG = ("ohne_zeiten", "lautwoerter", "dauer", "monoton")


# ============================================================ Ablage
def pfad(werk, lg, spur="hoerbuch"):
    return config.work_path(werk, f"{STAGE}_wortzeiten_{lg}{ZUSATZ[spur]}")


def bruecke_pfad(werk):
    return config.work_path(werk, "525_wortbruecke")


def pruef_pfad(werk):
    return os.path.join(config.work_dir(werk), "520_pruefung.json")


def korr_pfad(werk):
    return os.path.join(config.work_dir(werk), "520_korrekturen.json")


def _json(p, leer=None):
    if not p or not os.path.exists(p):
        return leer
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def kap_von(tid):
    return str(tid).split("_")[0]


# ============================================================ Text: gesprochen -> Lesetext
def saetze_text(data, lg):
    """{tid: (lesetext, sprechtext, abbildung)} je Audio-Einheit (Ansagen + Knoten) wie 500."""
    content = data.get("content") or {}
    prod = data.get("production") or {}
    sp, ab = prod.get("sprechtext") or {}, prod.get("abbildung") or {}
    out = {}
    for k in (data.get("ansagen") or {}).get(lg) or []:
        lese = str(k.get("text") or "").strip()
        out[k["id"]] = (lese, k.get("sprechtext") or lese, k.get("abbildung") or [])
    for tid, e in content.items():
        if not isinstance(e, dict) or e.get("type", "s") in config.NO_AUDIO_TYPES:
            continue
        lese = str(e.get(lg) or "").strip()
        s = (sp.get(tid) or {}).get(lg)
        if s is None:
            if not lese:
                continue
            s, a = st.sprechtext_abb(lese, lg, e.get("type"))
        else:
            a = (ab.get(tid) or {}).get(lg) or []
        out[tid] = (lese, s, a)
    return out


def _ersatz(werk, lg):
    """Aussprache-Lexikon wie 500 (tools.tts_paket.lexikon, nur freigegeben) -> {Begriff: Ersatz}."""
    try:
        from tools.tts_paket import lexikon
        return lexikon(config.book_dir(werk), lg) or {}
    except Exception:
        return {}


def _verteilen(n, a, b):
    """n Zeichen eines Ersatzblocks anteilig auf die Herkunft [a, b) verteilen (Wort fuer Wort statt ganzer Block)."""
    return [(a + (j * (b - a)) // n, max(a + (j * (b - a)) // n + 1, a + -(-(j + 1) * (b - a) // n)))
            for j in range(n)]


def lex_spur(sprech, ers):
    """Lexikon wie tools.tts_paket.lex_text, mit Herkunft je Zeichen -> (FA-Text, [(s0, s1)] im Sprechtext);
    in Ersatzbloecken anteilig verteilt ("SIE SOLL AUFHOEREN" -> "Sie soll aufhoeren": Wort auf Wort)."""
    sp = st._Spur(sprech or "")
    for k in sorted(ers or {}, key=len, reverse=True):
        sp.sub(re.compile(r"(?<![\w])" + re.escape(k) + r"(?![\w])"), lambda m, v=ers[k]: v)
    out, i, h = [], 0, sp.h
    while i < len(h):
        a, b, blk = h[i]
        j = i + 1
        while blk is not None and j < len(h) and h[j][2] == blk:
            j += 1
        out += _verteilen(j - i, a, b) if blk is not None else [(a, b)]
        i = j
    return sp.t, out


def lese_karte(sprech, abb):
    """Je Sprechtext-Zeichen der Lesetext-Span (l0, l1) aus der 400-Abbildung [[s0, s1, l0, l1], ...]
    (Bloecke = Ersetzung, s0 == s1 = Loeschung vor s0; Rest 1:1 fortlaufend)."""
    bl = sorted((tuple(int(v) for v in x) for x in (abb or [])), key=lambda x: (x[0], x[1] != x[0]))
    out, pos, i, k, n = [], 0, 0, 0, len(sprech or "")
    while i < n:
        while k < len(bl) and (bl[k][0] < i or (bl[k][0] == i and bl[k][1] == i)):
            if bl[k][0] == i:
                pos = bl[k][3]
            k += 1
        if k < len(bl) and bl[k][0] == i and bl[k][1] > i:
            s0, s1, l0, l1 = bl[k]
            m = min(s1, n) - s0
            out += _verteilen(m, l0, l1) if l1 > l0 else [(l0, l1)] * m
            pos, i, k = l1, s0 + m, k + 1
            continue
        out.append((pos, pos + 1))
        pos += 1
        i += 1
    return out


def vorbereiten(lese, sprech, abb, ers):
    """-> (FA-Text, Lautwoerter [{w, c0, c1 (FA-Text), l0, l1 (Lesetext)}])."""
    fa_text, herk = lex_spur(sprech, ers)
    karte = lese_karte(sprech, abb)
    n_l = len(lese)
    laut = s525.lautwoerter(fa_text)
    for x in laut:
        hs = herk[x["c0"]:x["c1"]] or [(0, 1)]
        a, b = min(h[0] for h in hs), max(h[1] for h in hs)
        ks = karte[a:max(b, a + 1)]
        if ks:
            l0, l1 = min(k[0] for k in ks), max(k[1] for k in ks)
        else:
            l0, l1 = a, max(b, a + 1)
        x["l0"], x["l1"] = max(0, min(l0, n_l)), max(0, min(l1, n_l))
    return fa_text, laut


def binden(laut, zeiten, lese):
    """Lautwort-Zeiten -> [{i, t0, t1}] je \\S+-Token des Lesetexts (Token mit groesster Ueberdeckung des
    Lesetext-Spans, sonst naechster Token); mehrere Lautwoerter je Token = ein Fenster."""
    sp = s525.token_spans(lese)
    if not sp:
        return []
    treffer = {}
    for x, z in zip(laut, zeiten or []):
        if not z:
            continue
        a, b = x["l0"], max(x["l1"], x["l0"] + 1)
        k = max(range(len(sp)), key=lambda k: (min(b, sp[k][1]) - max(a, sp[k][0]),
                                               -min(abs(a - sp[k][1]), abs(sp[k][0] - b))))
        t0, t1 = float(z[0]), float(z[1])
        if k in treffer:
            treffer[k] = [min(treffer[k][0], t0), max(treffer[k][1], t1)]
        else:
            treffer[k] = [t0, t1]
    return [{"i": k, "t0": round(v[0], 3), "t1": round(v[1], 3)} for k, v in sorted(treffer.items())]


def befund(eintr, n_laut, n_zeit, dauer, rg):
    """-> ([Befunde], Anzahl unplausibler Wortdauern)."""
    b = []
    if n_laut and not eintr:
        b.append("ohne_zeiten")
    if n_laut and n_zeit / n_laut < float(rg["lautwoerter_min"]):
        b.append("lautwoerter")
    if dauer is not None and any(e["t1"] > float(dauer) + float(rg["toleranz_s"]) for e in eintr):
        b.append("dauer")
    if any(e["t1"] < e["t0"] for e in eintr) or any(eintr[k]["t0"] < eintr[k - 1]["t0"] - 1e-3
                                                     for k in range(1, len(eintr))):
        b.append("monoton")
    unpl = sum(1 for e in eintr if not float(rg["wortdauer_min"]) <= e["t1"] - e["t0"] <= float(rg["wortdauer_max"]))
    return b, unpl


def auswerten(s, zeit, rg, art):
    eintr = binden(s["laut"], zeit, s["lese"])
    n_laut = len(s["laut"])
    n_zeit = sum(1 for z in (zeit or []) if z)
    bf, unpl = befund(eintr, n_laut, n_zeit, s["dauer"], rg)
    return {"tags": eintr, "info": {"h": s["h"], "fa": art, "laut": n_laut, "laut_zeit": n_zeit, "dauer": s["dauer"],
                                    "befund": bf, "unplausibel": unpl, "versuch": 1}}


# ============================================================ FA (patchbar)
def fa_zeiten(jobs, werk, lg, art):
    """jobs [(key, wav, woerter)] -> {key: [(t0, t1)|None]}; Modal mit CPU-Rueckfall, Modal-Sekunden geloggt."""
    if not jobs:
        return {}
    t0 = time.time()
    out = s510.zeiten(jobs, werk, lg, art)
    if art == "modal":
        usage_log.log_gpu(werk, STAGE, time.time() - t0, extra={"sprache": lg, "teil": "fa"})
    return out


def werkzeuge_pruefen(art):
    e = s510.aligner_pruefen(art, False)
    return [f"FA ({art}): {e}"] if e else []


# ============================================================ Regler
def _regler(roh):
    rg = dict(REGLER_STD)
    rg.update({k: v for k, v in (roh.get("wortzeiten_regler") or {}).items() if k in REGLER_STD})
    return rg


def _regler_gueltig(rg):
    try:
        return (rg["fa"] in ("modal", "cpu") and 0 < float(rg["lautwoerter_min"]) <= 1
                and 0 < float(rg["anker_min"]) <= 1 and 0 <= float(rg["unplausibel_max"]) <= 1
                and 0 <= float(rg["wortdauer_min"]) < float(rg["wortdauer_max"]) <= 10
                and 0 <= float(rg["toleranz_s"]) <= 1)
    except (KeyError, TypeError, ValueError):
        return False


def _spuren(b):
    """{lg: [spur]}: Audiosprachen mit TAELLA-Audioprodukt; Hoerspielspur, wenn Hoerspiel bestellt."""
    hs = s420._ziele(b)
    return {lg: ["hoerbuch"] + (["hoerspiel"] if lg in hs else []) for lg in (kette.sprachen(STAGE, b) or [])}


# ============================================================ Korrekturen (Wortzeit manuell)
def korrektur_setzen(werk, lg, spur, tid, i, t0, t1, wer):
    """Manuelle Wortzeit fuer Token i; gilt nur fuer den aktuellen Satz-Hash (neue WAV/neuer Text -> verworfen)."""
    aus = _json(pfad(werk, lg, spur), {}) or {}
    h = ((aus.get("saetze") or {}).get(tid) or {}).get("h")
    if not h:
        raise ValueError(f"{lg}/{spur}/{tid}: noch keine Wortzeiten – erst messen")
    if not 0 <= float(t0) < float(t1):
        raise ValueError(f"Wortzeit {t0}-{t1} ungueltig")
    k = _json(korr_pfad(werk), {}) or {}
    e = k.setdefault(f"{lg}/{spur}/{tid}", {"h": h, "zeiten": {}})
    if e.get("h") != h:
        e.update(h=h, zeiten={})
    e["zeiten"][str(int(i))] = [round(float(t0), 3), round(float(t1), 3)]
    e.update(wer=wer, wann=time.strftime("%Y-%m-%dT%H:%M:%S"))
    manifest.json_atomar(korr_pfad(werk), k, indent=1)


def _korrigieren(eintr, zeiten):
    d = {e["i"]: e for e in eintr}
    for i, (t0, t1) in zeiten.items():
        d[int(i)] = {"i": int(i), "t0": float(t0), "t1": float(t1)}
    return [d[i] for i in sorted(d)]


# ============================================================ Lauf
def run(werk, wer=None, regler=None, saetze=None, kapitel=None, nur_lang=None, nur_spur=None, neu=False,
        trocken=False, zeiten_man=None):
    wer = wer or "pipeline"
    g = gate.Gate(werk, STAGE, ruecksprung="520", wer=wer)
    b = bestellung.lesen(werk)
    rg = _regler(dict(b.roh))
    if regler and any(v is not None for v in regler.values()):
        rg.update({k: v for k, v in regler.items() if v is not None})
        if not trocken:
            b = bestellung.feld_setzen(werk, wortzeiten_regler=rg)
    sp = _spuren(b)
    if nur_lang:
        sp = {k: v for k, v in sp.items() if k == nur_lang}
    if nur_spur:
        sp = {k: [s for s in v if s == nur_spur] for k, v in sp.items()}
    g.metrik("spuren", sp)
    g.metrik("regler", rg)
    ip, ip340 = config.work_path(werk, "400_regie"), config.work_path(werk, "340_wortalignment")
    ok = g.pflicht("audio", any(sp.values()), ruecksprung="095", text="TAELLA-Audioprodukt bestellt")
    ok = g.pflicht("eingang", os.path.exists(ip), ruecksprung="400", text="400_regie.json vorhanden") and ok
    ok = g.pflicht("regler", _regler_gueltig(rg), wert=rg, text="Regler im Bereich") and ok
    vor = ["530"] + (["340"] if "340" in kette.bedarf(b) else [])
    for v in vor:
        z = status.zustand(werk, v)
        if trocken:
            g.hinweis(f"gate_{v}", z in status.FREI, text=f"Gate {v}: {z}")
        else:
            ok = g.pflicht(f"gate_{v}", z in status.FREI, wert=z, ruecksprung=v, text=f"Gate {v} frei ({z})") and ok
    if not ok:
        g.entscheide(schreiben=not trocken)
        return g
    if zeiten_man and not trocken:
        for lg, tid, i, t0, t1 in zeiten_man:
            korrektur_setzen(werk, lg, nur_spur or "hoerbuch", tid, i, t0, t1, wer)
    data = _json(ip)
    d340 = _json(ip340)
    c340 = (d340 or {}).get("content") or {}
    saetze, kap = set(saetze or []), set(kapitel or [])
    teil = bool(saetze or kap or nur_lang or nur_spur or trocken)

    # ---- Planung
    plan = {}
    for lg in sorted(sp):
        texte = saetze_text(data, lg)
        ers = _ersatz(werk, lg)
        mp = config.work_path(werk, f"530_pruefung_{lg}")
        m5 = manifest.Manifest(werk, f"530_pruefung_{lg}", stage="530") if os.path.exists(mp) else None
        reihe = [u["id"] for u in s500.einheiten(data, lg)[0]]
        for spur in sp[lg]:
            ids = [t for t in reihe if m5 and f"{spur}/{t}" in m5.eintraege] if spur == "hoerspiel" else reihe
            fehlt, abweich, soll = [], [], {}
            for t in ids:
                key = f"{spur}/{t}"
                e = (m5.get(key) if m5 else None) or {}
                if not e or not m5.datei_aktuell(key):
                    fehlt.append(t)
                    continue
                lese, sprech, abb = texte.get(t, ("", "", []))
                if t in c340 and str(c340[t].get(lg) or "").strip() != lese:
                    abweich.append(t)
                fa_text, laut = vorbereiten(lese, sprech, abb, ers)
                soll[t] = {"wav": m5._abs(e["datei"]), "dauer": e.get("dauer"), "lese": lese, "laut": laut,
                           "h": manifest.hash_obj({"d": e["datei_hash"], "t": fa_text, "l": lese, "a": abb,
                                                   "v": VERSION})}
            alt = _json(pfad(werk, lg, spur), {}) or {}
            if "saetze" not in alt:                       # Altformat ohne Hash -> alles neu
                alt = {}
            auswahl = {t for t in ids if kap_von(t) in kap or t in saetze} if (kap or saetze) else None
            info = alt.get("saetze") or {}
            offen = [t for t in soll if (auswahl is None or t in auswahl)
                     and (neu or t in saetze or (info.get(t) or {}).get("h") != soll[t]["h"])]
            plan[(lg, spur)] = {"ids": ids, "fehlt": fehlt, "abweich": abweich, "soll": soll, "alt": alt,
                                "auswahl": auswahl, "offen": offen}

    # ---- Werkzeuge vor jeder Ausgabe
    brauche = any(p["offen"] for p in plan.values())
    fe = werkzeuge_pruefen(rg["fa"]) if brauche else []
    if trocken:
        for x in fe:
            g.hinweis("werkzeug", False, text=f"Werkzeug fehlt: {x} (live Stopp)")
    elif fe:
        g.pflicht("werkzeug", False, wert=fe, ruecksprung="520", text="Werkzeuge verfuegbar – " + "; ".join(fe))
        g.entscheide(schreiben=True)
        return g

    # ---- Messen
    korr = _json(korr_pfad(werk), {}) or {}
    korr_alt = len(korr)
    pruef, je, ausgaben = {}, {}, {}
    for (lg, spur), p in plan.items():
        soll = p["soll"]
        if trocken:
            je[f"{lg}/{spur}"] = {"saetze": len(p["ids"]), "fehlt": len(p["fehlt"]), "offen": len(p["offen"])}
            g.hinweis(f"abdeckung_{lg}_{spur}", not p["fehlt"], wert=len(p["fehlt"]),
                      text=f"{lg}/{spur}: {len(p['ids']) - len(p['fehlt'])}/{len(p['ids'])} Saetze mit aktueller "
                           f"Endfassung 530; zu messen {len(p['offen'])}")
            continue
        jobs = [(t, soll[t]["wav"], [x["w"] for x in soll[t]["laut"]]) for t in p["offen"] if soll[t]["laut"]]
        zeit = fa_zeiten(jobs, werk, lg, rg["fa"]) if jobs else {}
        erg = {t: auswerten(soll[t], zeit.get(t), rg, rg["fa"]) for t in p["offen"]}
        wdh = [t for t, r in erg.items() if set(r["info"]["befund"]) & set(AUFFAELLIG) and soll[t]["laut"]]
        if wdh and rg["fa"] == "modal" and rg.get("wiederholen"):
            try:
                z2 = fa_zeiten([(t, soll[t]["wav"], [x["w"] for x in soll[t]["laut"]]) for t in wdh], werk, lg, "cpu")
            except Exception as ex:
                g.hinweis(f"wiederholen_{lg}_{spur}", False, wert=len(wdh),
                          text=f"{lg}/{spur}: Neumessung CPU nicht moeglich ({type(ex).__name__}) – {len(wdh)} Saetze")
            else:
                for t in wdh:
                    r2 = auswerten(soll[t], z2.get(t), rg, "cpu")
                    r2["info"]["versuch"] = 2
                    if len(r2["info"]["befund"]) <= len(erg[t]["info"]["befund"]):
                        erg[t] = r2
                    else:
                        erg[t]["info"]["versuch"] = 2
        tags = dict(p["alt"].get("tags") or {})
        info = dict(p["alt"].get("saetze") or {})
        for t, r in erg.items():
            tags[t], info[t] = r["tags"], r["info"]
        for t in [t for t in list(info) if t not in soll and t not in p["fehlt"]]:
            tags.pop(t, None)
            info.pop(t, None)
        for t in list(tags):
            k = f"{lg}/{spur}/{t}"
            if k not in korr:
                continue
            if t in soll and korr[k].get("h") == soll[t]["h"] == (info.get(t) or {}).get("h"):
                tags[t] = _korrigieren(tags[t], korr[k].get("zeiten") or {})
                info[t]["manuell"] = sorted(int(i) for i in (korr[k].get("zeiten") or {}))
            elif t in soll:
                korr.pop(k)
                g.hinweis(f"korrektur_{lg}_{spur}_{t}", False, text=f"{lg}/{spur}/{t}: manuelle Wortzeit verworfen "
                          f"(Satz geaendert)")
        reihe = [t for t in p["ids"] if t in tags]
        aus = {"sprache": lg, "spur": spur, "einheit": EINHEIT, "version": VERSION,
               "tags": {t: tags[t] for t in reihe}, "saetze": {t: info[t] for t in reihe if t in info},
               "meta": {"fa": rg["fa"], "regler": rg}}
        manifest.json_atomar(pfad(werk, lg, spur), aus, indent=1)
        ausgaben[f"{lg}/{spur}"] = aus
        je[f"{lg}/{spur}"] = {"saetze": len(p["ids"]), "gemessen": len(erg),
                              "cpu_neu": sum(1 for r in erg.values() if r["info"]["versuch"] == 2)}
    if not trocken and len(korr) != korr_alt:
        manifest.json_atomar(korr_pfad(werk), korr, indent=1)

    for (lg, spur), p in plan.items():
        pruef.setdefault(lg, {})[spur] = _gate_spur(g, lg, spur, p, ausgaben.get(f"{lg}/{spur}"), rg, trocken, teil)

    # ---- 525 Wortbruecke
    if d340 and not trocken:
        br = bruecke(werk, b, d340, rg)
        for lg, x in br.get("je_ziel", {}).items():
            q, txt = x["anker_quote"], f"{lg}: Anker mit Wortzeit {x['anker_quote']:.1%} (Quelle {br['quelle']})"
            if teil:
                g.hinweis(f"anker_zeit_{lg}", q >= float(rg["anker_min"]), wert=q, text=txt)
            else:
                g.pruefe(f"anker_zeit_{lg}", q >= float(rg["anker_min"]), q, f">= {rg['anker_min']}", "mensch",
                         "340", txt)
        if not br.get("je_ziel"):
            g.hinweis("bruecke", True, text="525 entfaellt (keine Zielsprache mit Ankern und Audio)")
        ausgaben["525"] = {lg: x["tags"] for lg, x in br.get("je_ziel", {}).items()}
    if not rg.get("interpolation"):
        g.hinweis("interpolation", False, text="525: Interpolation aus")

    aus_hash = manifest.hash_obj({k: v.get("tags") if isinstance(v, dict) and "tags" in v else v
                                  for k, v in ausgaben.items()})
    g.metrik("ausgabe_hash", aus_hash)
    g.metrik("je_spur", je)
    st0 = status.laden(werk)["stages"].get(STAGE) or {}
    if st0.get("zustand") == "frei" and (st0.get("gate") or {}).get("ergebnis") == "mensch" \
            and (st0.get("metriken") or {}).get("ausgabe_hash") == aus_hash:
        for x in g.pruefungen:
            if not x["ok"] and x["bei_fehler"] == "mensch":
                x["bei_fehler"] = "hinweis"
                x["text"] = (x.get("text") or x["name"]) + " [Mensch-Freigabe gilt, Wortzeiten unveraendert]"
    if not trocken:
        manifest.json_atomar(pruef_pfad(werk), pruef, indent=1)
    g.entscheide(schreiben=not trocken)
    g.pruefliste = pruef
    return g


def _gate_spur(g, lg, spur, p, aus, rg, trocken, teil):
    pre, ids, n = f"{lg}/{spur}", p["ids"], len(p["ids"]) or 1
    if p["abweich"]:
        g.pflicht(f"text_340_{lg}_{spur}", False, wert=len(p["abweich"]), ruecksprung="400",
                  text=f"{pre}: Lesetext 400 weicht von 340 ab in {len(p['abweich'])} Saetzen – "
                       f"{', '.join(p['abweich'][:3])}")
    if trocken:
        return {"fehlt": p["fehlt"][:200], "abweich": p["abweich"][:200]}
    fehlt = [t for t in p["fehlt"] if not p.get("auswahl") or t in p["auswahl"]]
    rest = [t for t in p["fehlt"] if t not in fehlt]
    if fehlt:
        g.pflicht(f"eingang_{lg}_{spur}", False, wert=len(fehlt), ruecksprung="530",
                  text=f"{pre}: {len(fehlt)} Saetze ohne aktuelle Endfassung 530 – {', '.join(fehlt[:3])}")
    if rest:
        g.hinweis(f"eingang_rest_{lg}_{spur}", False, wert=len(rest),
                  text=f"{pre}: {len(rest)} Saetze ausserhalb der Auswahl ohne aktuelle Endfassung 530")
    info = (aus or {}).get("saetze") or {}
    fertig = [t for t in ids if t in p["soll"] and (info.get(t) or {}).get("h") == p["soll"][t]["h"]]
    if teil:
        g.hinweis(f"abdeckung_{lg}_{spur}", len(fertig) == len(ids), wert=len(ids) - len(fertig),
                  text=f"{pre}: {len(fertig)}/{len(ids)} Saetze mit aktuellen Wortzeiten (Teillauf)")
    else:
        g.pflicht(f"abdeckung_{lg}_{spur}", len(fertig) == len(ids), wert=round(len(fertig) / n, 4),
                  ruecksprung="520", text=f"{pre}: Wortzeiten je Satz {len(fertig)}/{len(ids)}")
    inf = [info[t] for t in fertig]
    mit = lambda b_: [t for t in fertig if b_ in info[t]["befund"]]
    ohne, dauer, mono = mit("ohne_zeiten"), mit("dauer"), mit("monoton")
    laut = sum(x["laut"] for x in inf)
    q = round(sum(x["laut_zeit"] for x in inf) / laut, 4) if laut else 1.0
    woerter = sum(len((aus or {}).get("tags", {}).get(t) or []) for t in fertig)
    unpl = round(sum(x["unplausibel"] for x in inf) / woerter, 4) if woerter else 0.0
    bsp = lambda l: f" – {', '.join(l[:3])}" if l else ""
    g.pruefe(f"ohne_zeiten_{lg}_{spur}", not ohne, len(ohne), "= 0", "mensch", "530",
             f"{pre}: Saetze ohne Wortzeiten {len(ohne)}{bsp(ohne)}")
    g.pruefe(f"lautwoerter_{lg}_{spur}", q >= float(rg["lautwoerter_min"]), q, f">= {rg['lautwoerter_min']}",
             "mensch", "530", f"{pre}: Lautwoerter mit Zeit {q:.1%}")
    g.pruefe(f"dauer_{lg}_{spur}", not dauer, len(dauer), "= 0", "mensch", "530",
             f"{pre}: Wortzeit ausserhalb der Audiodauer {len(dauer)}{bsp(dauer)}")
    g.pruefe(f"monoton_{lg}_{spur}", not mono, len(mono), "= 0", "mensch", "520",
             f"{pre}: nicht monoton {len(mono)}{bsp(mono)}")
    g.max(f"wortdauer_{lg}_{spur}", unpl, float(rg["unplausibel_max"]), ruecksprung="530")
    auff = [t for t in fertig if set(info[t]["befund"]) & set(AUFFAELLIG)]
    zeile = lambda t: {"id": t, "text": p["soll"][t]["lese"], "datei": p["soll"][t]["wav"],
                       "befund": info[t]["befund"], "fa": info[t]["fa"], "versuch": info[t]["versuch"]}
    return {"auffaellig": [zeile(t) for t in auff][:300], "fehlt": p["fehlt"][:200], "abweich": p["abweich"][:200],
            "lautwoerter": q, "unplausibel": unpl}


# ============================================================ 525 Wortbruecke (Teil der Stage)
def bruecke(werk, b, d340, rg):
    """Je Zielsprache mit Ankern (align_<lg>) Wortzeiten je Anker aus 520 -> work/525_wortbruecke.json."""
    src = b.quellsprache
    content = d340.get("content") or {}
    ziele = [lg for lg in (b.zielsprachen or []) if lg != src
             and any(isinstance(v, dict) and v.get(f"align_{lg}") for v in content.values())]

    def lade(lg, spur):
        a = _json(pfad(werk, lg, spur))
        return None if a is None else (a.get("tags") or {})

    zq, hq = lade(src, "hoerbuch"), lade(src, "hoerspiel")
    je = {}
    for lg in ziele:
        zz, hz = lade(lg, "hoerbuch"), lade(lg, "hoerspiel")
        if zq is None and zz is None:
            continue
        tags = {}
        for tid, v in content.items():
            al = v.get(f"align_{lg}") if isinstance(v, dict) else None
            if not al:
                continue
            tags[tid] = s525.bruecke_satz(v.get(src, ""), v.get(lg, ""), al, (zq or {}).get(tid),
                                          zz.get(tid) if zz is not None and tid in zz else None,
                                          bool(rg.get("interpolation")), (hq or {}).get(tid), (hz or {}).get(tid),
                                          lg=lg)
        m = s525.messen(tags, content, src, q_audio=zq is not None, z_audio=zz is not None)
        hs = {"saetze_quelle": sum(1 for t in (hq or {}) if t in tags),
              "saetze_ziel": sum(1 for t in (hz or {}) if t in tags),
              "anker_ths": sum(1 for ws in tags.values() for w in ws if w.get("ths")),
              "anker_tzhs": sum(1 for ws in tags.values() for w in ws if w.get("tzhs"))}
        q = round(m["anker_mit_zeit"] / m["anker"], 4) if m["anker"] else 1.0
        je[lg] = {"tags": tags, "messung": m, "hoerspiel": hs, "anker_quote": q}
    if not je:
        return {"quelle": src, "je_ziel": {}}
    erst = je[next(iter(je))]
    out = {"quelle": src, "ziel": next(iter(je)), "version": VERSION, "interpolation": bool(rg.get("interpolation")),
           "tags": erst["tags"], "messung": {"nachher": erst["messung"]}, "hoerspiel": erst["hoerspiel"],
           "je_ziel": {lg: {k: x[k] for k in ("tags", "messung", "hoerspiel", "anker_quote")} for lg, x in je.items()}}
    with open(bruecke_pfad(werk), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    return {"quelle": src, "je_ziel": je}


# ============================================================ CLI
def _zeit_arg(x):
    """LG:TID:I=T0,T1 -> (lg, tid, i, t0, t1)."""
    try:
        links, rechts = x.split("=", 1)
        lg, tid, i = links.split(":")
        t0, t1 = rechts.split(",")
        return lg, tid, int(i), float(t0), float(t1)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--zeit {x!r}: Form LG:TID:I=T0,T1")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 520 Wortzeiten (inkl. 525 Wortbruecke)")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--fa", choices=("modal", "cpu"))
    ap.add_argument("--wiederholen", choices=("an", "aus"))
    ap.add_argument("--interpolation", choices=("an", "aus"))
    for k in ("lautwoerter-min", "anker-min", "wortdauer-min", "wortdauer-max", "unplausibel-max", "toleranz-s"):
        ap.add_argument(f"--{k}", type=float)
    ap.add_argument("--zeit", action="append", type=_zeit_arg, metavar="LG:TID:I=T0,T1")
    ap.add_argument("--satz", action="append")
    ap.add_argument("--kapitel")
    ap.add_argument("--lang")
    ap.add_argument("--spur", choices=SPUREN)
    ap.add_argument("--neu", action="store_true")
    ap.add_argument("--trocken", action="store_true")
    a = ap.parse_args(argv)
    an = lambda v: None if v is None else v == "an"
    regler = {"fa": a.fa, "wiederholen": an(a.wiederholen), "interpolation": an(a.interpolation),
              "lautwoerter_min": a.lautwoerter_min, "anker_min": a.anker_min, "wortdauer_min": a.wortdauer_min,
              "wortdauer_max": a.wortdauer_max, "unplausibel_max": a.unplausibel_max, "toleranz_s": a.toleranz_s}
    wer = a.wer or "pipeline"
    try:
        if (any(v is not None for v in regler.values()) or a.zeit) and not a.trocken:
            from pipeline import s080_mandant
            s080_mandant.darf(a.werk, "entscheiden", wer)
        g = run(a.werk, wer, regler=regler, saetze=a.satz, kapitel=a.kapitel.split(",") if a.kapitel else None,
                nur_lang=a.lang, nur_spur=a.spur, neu=a.neu, trocken=a.trocken, zeiten_man=a.zeit)
    except gate.GateHalt as e:
        print(e)
        return e.exit_code
    except (ValueError, PermissionError, RuntimeError) as e:
        print(f"[520] Fehler: {e}")
        return 1
    print(g.bericht())
    return gate.EXIT[g.ergebnis["ergebnis"]]


if __name__ == "__main__":
    sys.exit(main())
