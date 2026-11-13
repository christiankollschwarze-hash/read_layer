"""STAGE 330 — Rueckuebersetzung (Umbau Phase 2, GATE_KATALOG.md Zeile 330, 02.11.2026)
Funktion:     Qualitaets-Score je Satz x Zielsprache per Rueckuebersetzung, Reparatur geflaggter Saetze, Gate.
Wirkungsweise: Je Kapitel x Zielsprache: Ziel -> Quellsprache zurueck (Rolle translator, Regler --modell-rueck),
              Bewertung 0-100 gegen das Original (Rolle validator, Regler --modell-bewertung). Checkpoint
              work/ckpt/330/<kap>__<lg>.json mit Hash je Satz (Quelle + Ziel aus 320): Neulauf bewertet nur neue/
              geaenderte Saetze. Nicht bewertbare Saetze 1x automatisch neu. Geflaggter Satz (Score < Schwelle) ->
              1x automatisch neu uebersetzt wie in 310 (Einzelsatz mit Nachbarn, Profil-Ausschnitt, Rueckuebersetzung
              als Hinweis), neu bewertet; bessere Fassung bleibt. Ausgabe = Stand nach Reparatur (Abnehmer 340/400/600/
              620/630/700 lesen 330, nicht 310).
Eingang:      work/320_integritaet.json (Gate 320 frei), work/310_pruefung.json (Ausreisserliste, Umfang "ausreisser"),
              work/330_korrekturen.json (manuelle Saetze / angenommene Flags), book.json (Zielsprachen aus 095, Mandant).
Ausgabe:      work/330_rueckuebersetzung.json (Durchreichung mit reparierten Zieltexten + meta.quality_report
              {threshold, average_score, scored_count, flagged [[id, lg, score]], not_scored [[id, lg]], je_sprache,
              repariert, angenommen, umfang} + meta.rueckuebersetzung), work/330_pruefung.json (je Sprache Liste
              id/Quelle/Ziel/Rueck/Score/Befund).
Gate:         je Zielsprache: Flags nach Reparatur <= 3 % (ab 300 bewerteten Saetzen), darunter <= 10 -> sonst Mensch;
              nicht bewertbar <= 1 % -> sonst Mensch; Durchschnitt >= 92 nur Hinweis; gehaeufte Namens-/Glossarbegriffe
              in Flags -> Hinweis (Ruecksprung 210); Mandant verlag -> immer Mensch; Gate 320 nicht frei -> Stopp;
              Mock im Live-Lauf -> Stopp. Mensch-Freigabe gilt bei gleichem ausgabe_hash.
Kosten:       usage_log Stage 330 mit Sprache; kosten_schaetzen() fuer den Monitor.
Regler:       --schwelle 90, --flag-max 0.03, --modell-rueck, --modell-bewertung, --umfang alle|ausreisser
              (--stichprobe P %), --kapitel N|alle (neu bewerten), --satz ID (neu uebersetzen + bewerten),
              --satz-text ID=TEXT (manuell), --annehmen ID (Flag annehmen; beide mit --lang bei mehreren Zielsprachen),
              --lang LG, --uebernehmen (vorhandene 330_rueckuebersetzung.json als Rohergebnis), --trocken (Probe).
              --schwelle/--flag-max/--umfang/--stichprobe gelten je Werk (book.json rueck_*), Monitor 330 (09.11.2026).
              --lang wirkt nur auf Regler/Neubewertung dieser Sprache; andere Sprachen laufen ueber den Checkpoint
              unveraendert mit (vorher fielen sie aus Ausgabe und 330_pruefung.json heraus).
              330_pruefung.json fuehrt auch reparierte Saetze (befund "repariert", score_vorher, ziel_vorher).
Aufruf:       python -m pipeline.s330_rueckuebersetzung <werk> [Regler] [--wer CK]
Exit: 0 auto, 2 Stopp, 3 Mensch, 1 Fehler.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import api_layer, bestellung, gate, manifest, mock, status, usage_log
from pipeline import s300_voruebersetzung as s300
from pipeline import s310_uebersetzung as s310

STAGE = "330"
PROMPT_V = 1
BATCH = 25
SCHWELLE = 90
FLAG_MAX = 0.03
FLAG_AB = 300
FLAG_KLEIN = 10
NICHT_BEWERTBAR_MAX = 0.01
SCHNITT_HINWEIS = 92
HAEUFUNG = 3
KOSTEN_RUECK = (1.5, 1.2)    # (Eingabe, Ausgabe) Token je Ziel-Token: Rueckuebersetzung
KOSTEN_BEW = (2.6, 0.05)     # je Ziel-Token: Original + Rueck rein, nur Score raus
REPARATUR_ANTEIL = 0.05      # geschaetzter Anteil geflaggter Saetze (Reparatur wie 310 + Neubewertung)


def kosten_schaetzen(zeichen, m_rueck=None, m_bew=None, n_ziele=1, reparatur=REPARATUR_ANTEIL):
    """Schaetzung Rueckuebersetzen + Bewerten in $ (Peak-Preis, ohne Cache; Token ~ Zeichen/4)."""
    pr = getattr(config, "PREISE", {})
    r = pr.get(m_rueck or config.MODELS.get("backtranslator") or config.MODELS.get("translator")) or {}
    b = pr.get(m_bew or config.MODELS.get("validator")) or {}
    tok = zeichen / 4
    einmal = (tok * KOSTEN_RUECK[0] * r.get("in", 0) + tok * KOSTEN_RUECK[1] * r.get("out", 0)
              + tok * KOSTEN_BEW[0] * b.get("in", 0) + tok * KOSTEN_BEW[1] * b.get("out", 0)) / 1e6
    rep = reparatur * (s310.kosten_schaetzen(zeichen) + einmal) if reparatur else 0
    return n_ziele * (einmal + rep)


# ============================================================
# EINGANG
# ============================================================

def saetze(data, src, lg):
    """-> {kap: [(id, quelle, ziel)]} (uebersetzbare Knoten mit Zieltext)."""
    kap = {}
    for tid, e in (data.get("content") or {}).items():
        cid = tid.split("_")[0]
        kap.setdefault(cid, [])
        if not isinstance(e, dict) or e.get("type") in config.NO_AUDIO_TYPES:
            continue
        q, z = (e.get(src) or "").strip(), (e.get(lg) or "").strip()
        if q and z:
            kap[cid].append((tid, q, z))
    return kap


def satz_hash(q, z):
    return manifest.hash_text(q + "\u0001" + z)


def _stichprobe(tid, prozent):
    return int(manifest.hash_text(tid)[:6], 16) % 100 < prozent


def _ausreisser(werk):
    try:
        with open(os.path.join(config.work_dir(werk), "310_pruefung.json"), encoding="utf-8") as f:
            p = json.load(f)
        return {lg: {x["id"] for x in l if isinstance(x, dict) and x.get("id")} for lg, l in p.items()}
    except (OSError, ValueError, AttributeError):
        return {}


# ============================================================
# LLM
# ============================================================

def _safe(raw):
    try:
        p = api_layer.parse_json(raw)
        return p if isinstance(p, dict) else {}
    except Exception:
        return {}


def _rolle(rolle, modell, fn):
    alt = config.MODELS.get(rolle)
    if modell:
        config.MODELS[rolle] = modell
    try:
        return fn()
    finally:
        config.MODELS[rolle] = alt


def rueck(werk, items, src, lg, modell=None):
    """items [(id, zieltext)] -> {id: rueckuebersetzung}."""
    if not items:
        return {}
    usage_log.set_context(werk, STAGE, sprache=lg)
    if config.RUN_MODE == "mock":
        raw = api_layer.call_model("translator", "", target_lang=src, sentences=[t for _, t in items])
        lst = _safe(raw).get("translations", [])
        return {tid: lst[i] for i, (tid, _) in enumerate(items) if i < len(lst)}
    lines = "\n".join(f"  {json.dumps(tid)}: {json.dumps(t, ensure_ascii=False)}" for tid, t in items)
    prompt = f"""Translate each sentence from {lg} into {src}. Translate literally enough to preserve the meaning.
Each sentence has a unique ID. Return the translation under the SAME ID.
Return every ID exactly once. Never merge or split sentences.
Return ONLY a JSON object mapping each ID to its translation:
{{ "<id1>": "<translation>", ... }}

There are exactly {len(items)} IDs.

Sentences (as JSON, id -> text):
{{
{lines}
}}"""
    try:
        raw = _rolle("translator", modell, lambda: api_layer.call_model("translator", prompt, max_tokens=16000))
    except EnvironmentError:
        raise
    except Exception as e:
        print(f"      ! Rueckuebersetzung gescheitert ({lg}): {str(e)[:120]}")
        return {}
    p = _safe(raw)
    if isinstance(p.get("translations"), dict):
        p = p["translations"]
    return {tid: p[tid].strip() for tid, _ in items if isinstance(p.get(tid), str) and p[tid].strip()}


def bewerte(werk, items, src, lg, modell=None):
    """items [(id, original, rueck)] -> {id: score int}."""
    if not items:
        return {}
    usage_log.set_context(werk, STAGE, sprache=lg)
    if config.RUN_MODE == "mock":
        s = _safe(api_layer.call_model("validator", "")).get("score", 95)
        return {tid: int(s) for tid, _, _ in items}
    blocks = "\n".join(f'  {json.dumps(tid)}: {{ "original": {json.dumps(o, ensure_ascii=False)}, '
                       f'"back": {json.dumps(b, ensure_ascii=False)} }}' for tid, o, b in items)
    prompt = f"""You are a translation quality assessor.
For each ID, compare the BACK-translation (from {lg} back to {src}) against
the ORIGINAL. Score how well the meaning was preserved, 0-100 (integer).

Return ONLY a JSON object mapping each ID to its integer score:
{{ "<id1>": <score>, "<id2>": <score>, ... }}

There are exactly {len(items)} IDs.

Pairs (as JSON, id -> {{original, back}}):
{{
{blocks}
}}"""
    try:
        raw = _rolle("validator", modell, lambda: api_layer.call_model("validator", prompt, max_tokens=8192))
    except EnvironmentError:
        raise
    except Exception as e:
        print(f"      ! Bewertung gescheitert ({lg}): {str(e)[:120]}")
        return {}
    p = _safe(raw)
    if isinstance(p.get("scores"), dict):
        p = p["scores"]
    out = {}
    for tid, _, _ in items:
        v = p.get(tid)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[tid] = max(0, min(100, int(v)))
        elif isinstance(v, str) and v.strip().isdigit():
            out[tid] = max(0, min(100, int(v.strip())))
    return out


def rueck_und_bewerten(werk, items, src, lg, batch, m_rueck, m_bew, z):
    """items [(id, quelle, ziel)] -> {id: (rueck|None, score|None)}."""
    out = {}
    for i in range(0, len(items), batch):
        teil = items[i:i + batch]
        r = rueck(werk, [(t, zt) for t, _q, zt in teil], src, lg, m_rueck)
        z["llm"] += 1
        sc_items = [(t, q, r[t]) for t, q, _zt in teil if t in r]
        s = bewerte(werk, sc_items, src, lg, m_bew) if sc_items else {}
        z["llm"] += 1 if sc_items else 0
        for t, _q, _zt in teil:
            out[t] = (r.get(t), s.get(t))
    return out


# ============================================================
# KORREKTUREN
# ============================================================

def _korr_pfad(werk):
    return os.path.join(config.work_dir(werk), "330_korrekturen.json")


def korrekturen_lesen(werk):
    try:
        with open(_korr_pfad(werk), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def korrektur_setzen(werk, lg, tid, h, text=None, annehmen=False, wer=None):
    k = korrekturen_lesen(werk)
    e = k.setdefault(lg, {}).setdefault(tid, {})
    e.update({"h": h, "wer": wer, "wann": manifest.jetzt()})
    if text is not None:
        e["text"] = text
    if annehmen:
        e["angenommen"] = True
    manifest.json_atomar(_korr_pfad(werk), k, indent=1)


# ============================================================
# LAUF
# ============================================================

def _alt330(werk):
    p = config.work_path(werk, "330_rueckuebersetzung")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    qr = (d.get("meta") or {}).get("quality_report") or {}
    flag = {(x[0], x[1]): x[2] for x in qr.get("flagged") or [] if isinstance(x, (list, tuple)) and len(x) >= 3}
    ns = {(x[0], x[1]) for x in qr.get("not_scored") or [] if isinstance(x, (list, tuple)) and len(x) >= 2}
    return {"content": d.get("content") or {}, "flag": flag, "ns": ns,
            "schwelle": qr.get("threshold", SCHWELLE), "schnitt": qr.get("average_score")}


def _vom_bestand(alt, tid, lg, q, z, schwelle):
    """Altbestand -> Checkpoint-Eintrag (ohne Rueckuebersetzung) oder None."""
    if not alt:
        return None
    e = alt["content"].get(tid) or {}
    if (e.get(lg) or "").strip() != z:
        return None
    if (tid, lg) in alt["ns"]:
        return None
    s = alt["flag"].get((tid, lg))
    return {"h": satz_hash(q, z), "r": None, "s": s if s is not None else max(schwelle, alt["schwelle"]),
            "alt": True, "v": 1}


def run(werk, wer=None, schwelle=None, flag_max=None, m_rueck=None, m_bew=None, umfang=None, stichprobe=None,
        kapitel=None, saetze_neu=None, satz_text=None, annehmen=None, nur_lang=None, uebernehmen=False, trocken=False,
        batch=None):
    wer = wer or "pipeline"
    if not trocken:                              # Regler je Werk (Monitor 330)
        fe = {}
        if schwelle is not None:
            fe["rueck_schwelle"] = int(schwelle)
        if flag_max is not None:
            fe["rueck_flag_max"] = float(flag_max)
        if umfang:
            fe["rueck_umfang"] = umfang
        if stichprobe is not None:
            fe["rueck_stichprobe"] = float(stichprobe)
        if fe:
            bestellung.feld_setzen(werk, **fe)
    g = gate.Gate(werk, STAGE, ruecksprung="310", wer=wer)
    b = bestellung.lesen(werk)
    src = b.quellsprache or config.SOURCE_LANGUAGE
    ziele = [z for z in (b.zielsprachen or []) if z != src]
    if nur_lang and nur_lang not in ziele:
        raise ValueError(f"--lang {nur_lang}: keine bestellte Zielsprache {ziele}")
    schwelle = int(schwelle if schwelle is not None else b.roh.get("rueck_schwelle") or
                   getattr(config, "VALIDATION_THRESHOLD", SCHWELLE))
    flag_max = float(flag_max if flag_max is not None else b.roh.get("rueck_flag_max")
                     or getattr(config, "FLAG_MAX_ANTEIL", FLAG_MAX))
    flag_ab = int(getattr(config, "FLAG_ANTEIL_AB_SAETZEN", FLAG_AB))
    flag_klein = int(getattr(config, "FLAG_MAX_KLEIN", FLAG_KLEIN))
    umfang = umfang or b.roh.get("rueck_umfang") or "alle"
    stichprobe = float(stichprobe if stichprobe is not None else b.roh.get("rueck_stichprobe") or 10)
    batch = int(batch or getattr(config, "BACKTRANS_BATCH_SIZE", BATCH))
    m_rueck_eff = m_rueck or config.MODELS.get("backtranslator") or config.MODELS.get("translator")
    m_bew_eff = m_bew or config.MODELS.get("validator")
    for k, v in (("zielsprachen", ziele), ("schwelle", schwelle), ("umfang", umfang), ("modell_rueck", m_rueck_eff),
                 ("modell_bewertung", m_bew_eff)):
        g.metrik(k, v)
    if umfang == "ausreisser":
        g.metrik("stichprobe", stichprobe)

    ip = config.work_path(werk, "320_integritaet")
    if not g.pflicht("integritaet", os.path.exists(ip), ruecksprung="320", text="320_integritaet.json vorhanden"):
        g.entscheide(schreiben=not trocken)
        return g
    z320 = status.zustand(werk, "320")
    if trocken:
        g.hinweis("gate_320", z320 in status.FREI, text=f"Gate 320: {z320}")
    else:
        g.pflicht("gate_320", z320 in status.FREI, wert=z320, ruecksprung="320", text=f"Gate 320 frei ({z320})")
    ok_z = g.pflicht("zielsprachen", bool(ziele), ruecksprung="095", text="Bestellung nennt mindestens eine Zielsprache")
    if not ok_z or (not trocken and z320 not in status.FREI):
        g.entscheide(schreiben=not trocken)
        return g
    with open(ip, encoding="utf-8") as f:
        data = json.load(f)
    meta = data.setdefault("meta", {})
    profil = meta.get("profile") or {}

    alt = _alt330(werk) if (uebernehmen or trocken) else None
    if trocken and not alt:
        g.pflicht("bestand", False, text="330_rueckuebersetzung.json fehlt (Probe ohne LLM)")
        g.entscheide(schreiben=False)
        return g

    # Manuelle Regler
    lg_regler = nur_lang or (ziele[0] if len(ziele) == 1 else None)
    if (satz_text or annehmen) and not trocken:
        if not lg_regler:
            raise ValueError("--satz-text/--annehmen brauchen --lang bei mehreren Zielsprachen")
        hmap = {t: satz_hash(q, zt) for l in saetze(data, src, lg_regler).values() for t, q, zt in l}
        for x in satz_text or []:
            tid, t = x.split("=", 1)
            if tid not in hmap:
                raise ValueError(f"unbekannte ID {tid}")
            korrektur_setzen(werk, lg_regler, tid, hmap[tid], text=t.strip(), wer=wer)
        for tid in annehmen or []:
            if tid not in hmap:
                raise ValueError(f"unbekannte ID {tid}")
            korrektur_setzen(werk, lg_regler, tid, hmap[tid], annehmen=True, wer=wer)
    korr = korrekturen_lesen(werk)
    aus_310 = _ausreisser(werk) if umfang == "ausreisser" else {}

    if kapitel == ["alle"]:
        neu_k = None
    else:
        neu_k = {f"c{int(k):0{config.CHAPTER_DIGITS}d}" for k in (kapitel or [])}
    neu_ids = set(saetze_neu or [])

    ck = manifest.Checkpoint(werk, STAGE)
    z = {"llm": 0, "neu_bewertet": 0, "nachbewertet": 0, "repariert": 0, "reparatur_versuche": 0}
    qr_flag, qr_ns, alle_scores, pruef, je_sprache, ck_soll = [], [], [], {}, {}, []
    n_mock, n_angenommen, n_manuell = 0, 0, 0
    haeufung = {}
    for lg in ziele:
        kap = saetze(data, src, lg)
        mit_lg = not nur_lang or lg == nur_lang          # --lang: Neubewertung nur dieser Sprache
        neu_lg = neu_ids if mit_lg else set()
        flags_lg, ns_lg, sc_lg, pruef[lg] = [], [], [], []
        n_lg, n_ungeprueft = 0, 0
        kontext = manifest.hash_obj([PROMPT_V, src, lg, m_rueck_eff, m_bew_eff])
        for cid, liste in kap.items():
            if not liste:
                continue
            ck_soll.append((cid, lg))
            quelle = " ".join(q for _t, q, _z in liste)
            aus = s310.profil_ausschnitt(profil, quelle, lg)
            frisch = mit_lg and (neu_k is None or cid in neu_k)
            if trocken:
                altck = {}
            else:
                altck = ({} if frisch else (ck.lesen(cid, lg, kontext) or {}).get("saetze")) or {}
            res = {}
            offen = []
            for t, q, zt in liste:
                h = satz_hash(q, zt)
                if umfang == "ausreisser" and t not in aus_310.get(lg, set()) and not _stichprobe(t, stichprobe) \
                        and t not in neu_lg:
                    res[t] = {"h": h, "ungeprueft": True}
                    continue
                e = altck.get(t)
                if e and e.get("h") == h and t not in neu_lg:
                    res[t] = e
                    continue
                e = _vom_bestand(alt, t, lg, q, zt, schwelle) if (uebernehmen or trocken) and t not in neu_lg else None
                if e:
                    res[t] = e
                    continue
                offen.append((t, q, zt))
            if offen and not trocken:
                got = rueck_und_bewerten(werk, offen, src, lg, batch, m_rueck_eff, m_bew_eff, z)
                z["neu_bewertet"] += len(offen)
                # nicht bewertbar -> 1x neu
                nach = [(t, q, zt) for t, q, zt in offen if got[t][1] is None]
                if nach:
                    got2 = rueck_und_bewerten(werk, nach, src, lg, batch, m_rueck_eff, m_bew_eff, z)
                    z["nachbewertet"] += len(nach)
                    for t, _q, _zt in nach:
                        if got2[t][1] is not None:
                            got[t] = got2[t]
                for t, q, zt in offen:
                    r, s = got[t]
                    res[t] = {"h": satz_hash(q, zt), "r": r, "s": s, "v": 0}
            # Reparatur: geflaggt (oder --satz) -> 1x neu uebersetzen wie 310
            if not trocken:
                for i, (t, q, zt) in enumerate(liste):
                    e = res.get(t) or {}
                    if e.get("ungeprueft") or e.get("s") is None:
                        continue
                    erzwungen = t in neu_lg
                    if not erzwungen and (e.get("v", 0) >= 1 or e["s"] >= schwelle):
                        continue
                    nb = s310._nachbarn(liste, i, {x: {"t": y} for x, _q, y in liste})
                    hinweis = (f"the back-translation of your previous version reads '{(e.get('r') or '')[:300]}' "
                               f"(meaning score {e['s']}/100, previous: '{zt[:300]}'); preserve the original meaning")
                    alt_stage, s310.STAGE = s310.STAGE, STAGE      # Kosten der Reparatur unter 330
                    try:
                        neu = s310.llm(werk, [(t, q)], src, lg, aus, nachbarn=nb, hinweis=hinweis)
                    finally:
                        s310.STAGE = alt_stage
                    z["llm"] += 1
                    z["reparatur_versuche"] += 1
                    e["v"] = 1
                    t2 = neu.get(t)
                    if t2 and t2 != zt:
                        g2 = rueck_und_bewerten(werk, [(t, q, t2)], src, lg, batch, m_rueck_eff, m_bew_eff, z)
                        r2, s2 = g2[t]
                        if s2 is not None and (erzwungen or s2 > e["s"]):
                            e.update({"t2": t2, "r2": r2, "s2": s2})
                            z["repariert"] += 1
                    res[t] = e
                ck.schreiben(cid, lg, kontext, {"saetze": res})
            # Ergebnis + Korrekturen
            kk = korr.get(lg) or {}
            for t, q, zt in liste:
                e = res.get(t) or {}
                if e.get("ungeprueft"):
                    n_ungeprueft += 1
                    continue
                n_lg += 1
                k = kk.get(t) if (kk.get(t) or {}).get("h") == e.get("h") else None
                ziel, sc, rr = (e["t2"], e.get("s2"), e.get("r2")) if e.get("t2") else (zt, e.get("s"), e.get("r"))
                if k and k.get("text"):
                    ziel, n_manuell = k["text"], n_manuell + 1
                if mock.ist_text(ziel) or (rr and mock.ist_text(rr)):
                    n_mock += 1
                data["content"][t][lg] = ziel
                if k and k.get("text"):
                    continue
                if sc is None:
                    ns_lg.append(t)
                    pruef[lg].append({"id": t, "quelle": q, "ziel": ziel, "rueck": rr, "score": None,
                                      "befund": "nicht_bewertbar"})
                    continue
                if not e.get("alt") or e.get("t2"):
                    sc_lg.append(sc)
                if sc >= schwelle and e.get("t2"):
                    pruef[lg].append({"id": t, "quelle": q, "ziel": ziel, "ziel_vorher": zt, "rueck": rr, "score": sc,
                                      "score_vorher": e.get("s"), "befund": "repariert"})
                    continue
                if sc < schwelle:
                    if k and k.get("angenommen"):
                        n_angenommen += 1
                        continue
                    flags_lg.append((t, sc))
                    pruef[lg].append({"id": t, "quelle": q, "ziel": ziel, "ziel_vorher": zt if e.get("t2") else None,
                                      "rueck": rr, "score": sc, "score_vorher": e.get("s") if e.get("t2") else None,
                                      "befund": "flag"})
                    ql = q.lower()
                    for begriff, _v in s300.erwartet(s310.profil_ausschnitt_satz(aus, q)):
                        if s300._kommt_vor(begriff, ql):
                            haeufung.setdefault((lg, begriff), []).append(t)
        qr_flag += [[t, lg, s] for t, s in flags_lg]
        qr_ns += [[t, lg] for t in ns_lg]
        alle_scores += sc_lg
        schnitt = round(sum(sc_lg) / len(sc_lg), 1) if sc_lg else None
        if schnitt is None and alt and n_lg:
            schnitt = alt.get("schnitt")                         # Altbestand ohne Einzelscores
        je_sprache[lg] = {"bewertet": n_lg, "ungeprueft": n_ungeprueft, "flags": len(flags_lg),
                          "nicht_bewertbar": len(ns_lg), "durchschnitt": schnitt}
        # Gate je Sprache
        nb = max(1, n_lg - len(ns_lg))
        if n_lg - len(ns_lg) >= flag_ab:
            ok, soll, wert = len(flags_lg) / nb <= flag_max, f"<= {flag_max:.0%}", round(len(flags_lg) / nb, 4)
        else:
            ok, soll, wert = len(flags_lg) <= flag_klein, f"<= {flag_klein} (unter {flag_ab} Saetzen)", len(flags_lg)
        g.pruefe(f"flags_{lg}", ok, wert=wert, schwelle=soll, bei_fehler="mensch",
                 text=f"{lg}: Flags nach Reparatur {len(flags_lg)}/{nb} (Score < {schwelle}, Soll {soll})"
                 + (f" {[t for t, _ in flags_lg[:6]]}" if flags_lg else ""))
        anteil_ns = len(ns_lg) / max(1, n_lg)
        g.pruefe(f"nicht_bewertbar_{lg}", anteil_ns <= NICHT_BEWERTBAR_MAX, wert=round(anteil_ns, 4),
                 schwelle=f"<= {NICHT_BEWERTBAR_MAX:.0%}", bei_fehler="mensch",
                 text=f"{lg}: nicht bewertbar {len(ns_lg)}/{n_lg}" + (f" {ns_lg[:6]}" if ns_lg else ""))
        g.hinweis(f"durchschnitt_{lg}", schnitt is None or schnitt >= SCHNITT_HINWEIS, wert=schnitt,
                  text=f"{lg}: Durchschnitts-Score {schnitt} (Anzeige, Soll >= {SCHNITT_HINWEIS})")
        if n_ungeprueft:
            g.hinweis(f"umfang_{lg}", True, text=f"{lg}: Umfang ausreisser – {n_ungeprueft} Saetze nicht geprueft")

    for (lg, begriff), ids in sorted(haeufung.items()):
        if len(ids) >= HAEUFUNG:
            g.hinweis(f"haeufung_{lg}_{begriff}", False, wert=len(ids),
                      text=f"{lg}: '{begriff}' in {len(ids)} geflaggten Saetzen – Glossar/Namen in 210 pruefen "
                           f"(Ruecksprung 210) {ids[:4]}")
    g.mock(0 if mock.aktiv() else n_mock, ruecksprung="310")
    for k_, v in z.items():
        g.metrik(k_, v)
    g.metrik("angenommen", n_angenommen)
    g.metrik("manuell", n_manuell)
    g.metrik("je_sprache", je_sprache)

    avg = round(sum(alle_scores) / len(alle_scores), 1) if alle_scores else 0
    meta["quality_report"] = {"threshold": schwelle, "average_score": avg, "scored_count": len(alle_scores),
                              "flagged": qr_flag, "not_scored": qr_ns, "je_sprache": je_sprache,
                              "repariert": z["repariert"], "angenommen": n_angenommen, "umfang": umfang,
                              "geprueft": manifest.jetzt()}
    meta["rueckuebersetzung"] = {"modell_rueck": m_rueck_eff, "modell_bewertung": m_bew_eff, "prompt_v": PROMPT_V,
                                 "batch": batch}
    ids = [t for t, e in (data.get("content") or {}).items() if isinstance(e, dict)]
    aus_hash = manifest.hash_obj({lg: {t: (data["content"][t] or {}).get(lg) for t in ids} for lg in ziele}
                                 | {"_flags": qr_flag})
    g.metrik("ausgabe_hash", aus_hash)
    st = status.laden(werk)["stages"].get(STAGE) or {}
    if st.get("zustand") == "frei" and (st.get("gate") or {}).get("ergebnis") == "mensch" \
            and (st.get("metriken") or {}).get("ausgabe_hash") == aus_hash:
        for p in g.pruefungen:
            if not p["ok"] and p["bei_fehler"] == "mensch":
                p["bei_fehler"] = "hinweis"
                p["text"] += " [Mensch-Freigabe gilt, Ausgabe unveraendert]"
        verlag = False
    else:
        verlag = b.mandant_art == "verlag"
    if not trocken:
        manifest.json_atomar(config.work_path(werk, "330_rueckuebersetzung"), data, indent=2)
        manifest.json_atomar(os.path.join(config.work_dir(werk), "330_pruefung.json"), pruef, indent=1)
        ck.aufraeumen(ck_soll)
    g.entscheide(mensch_immer=verlag, mensch_grund="Mandant verlag: Freigabe Uebersetzungsqualitaet" if verlag else None,
                 schreiben=not trocken)
    g.pruef = pruef
    return g


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 330 Rueckuebersetzung")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--schwelle", type=int)
    ap.add_argument("--flag-max", type=float, help="max. Flag-Anteil, z. B. 0.03")
    ap.add_argument("--modell-rueck")
    ap.add_argument("--modell-bewertung")
    ap.add_argument("--umfang", choices=["alle", "ausreisser"])
    ap.add_argument("--stichprobe", type=float, help="Prozent zusaetzlich bei --umfang ausreisser")
    ap.add_argument("--batch", type=int)
    ap.add_argument("--kapitel", action="append", metavar="N|alle")
    ap.add_argument("--satz", action="append", metavar="ID", help="Satz neu uebersetzen und bewerten")
    ap.add_argument("--satz-text", action="append", metavar="ID=TEXT", help="Satz manuell ersetzen")
    ap.add_argument("--annehmen", action="append", metavar="ID", help="Flag annehmen")
    ap.add_argument("--lang", help="nur diese Zielsprache")
    ap.add_argument("--uebernehmen", action="store_true")
    ap.add_argument("--trocken", action="store_true")
    a = ap.parse_args(argv)
    kap = ["alle"] if a.kapitel and "alle" in a.kapitel else a.kapitel
    try:
        if (a.satz_text or a.annehmen) and not a.trocken:
            from pipeline import s080_mandant
            s080_mandant.darf(a.werk, "entscheiden", a.wer or "pipeline")
        g = run(a.werk, a.wer, a.schwelle, a.flag_max, a.modell_rueck, a.modell_bewertung, a.umfang, a.stichprobe,
                kap, a.satz, a.satz_text, a.annehmen, a.lang, a.uebernehmen, a.trocken, a.batch)
    except gate.GateHalt as e:
        print(e)
        return e.exit_code
    except (ValueError, PermissionError) as e:
        print(f"[330] Fehler: {e}")
        return 1
    print(g.bericht())
    return gate.EXIT[g.ergebnis["ergebnis"]]


if __name__ == "__main__":
    sys.exit(main())
