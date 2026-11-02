"""STAGE 530 — Audio-Pruefungen (neu als Stage, GATE_KATALOG.md Zeile 530, Phase 2, 02.11.2026)
Funktion:     Macht aus der Rohfassung die Endfassung je Audiosprache und Spur: Hoerbuch fassungen/<lg>/audio/
              (Manifest 500) -> audio_final/, Hoerspiel fassungen/<lg>/hoerspiel/ (Manifest 510, nur Saetze mit
              Figurenanteil, Rest = audio_final/) -> hoerspiel_final/. Je Satz: Raender aus FA-Wortzeiten (MMS_FA,
              Modal mit CPU-Rueckfall) auf Rand vor/nach geschnitten, Tempo (atempo) einmal angewandt; je Kapitel:
              Lautheit auf LUFS-Ziel normiert, Spitzenpegel begrenzt (ffmpeg ebur128). Danach Sprachpruefung je
              Satz (Whisper: erkannte Sprache + CER gegen Sprechtext); gekippte Saetze -> bis 2x automatisch neu in
              500 bzw. 510, danach Hoerliste. Rohfassungen bleiben unberuehrt.
Wirkungsweise: Manifest work/530_pruefung_<lg>.json (Schluessel <spur>/<tid>): Eingangs-Hash (WAV 500/510 + Sprechtext
              + Tempo + Raender), FA-Raender (w0/w1, eigener Hash), Tempo, Rand, Dauer, Sprachergebnis (je Datei-Hash
              der Endfassung); meta.kapitel je <spur>/<kap> (Hash, LUFS vor/nach, Verstaerkung, Spitze). Nur geaenderte
              Saetze/Kapitel werden neu gebaut bzw. geprueft (geaenderte WAV -> automatisch neu).
Eingang:      fassungen/<lg>/audio + work/500_vertonung.json (Gate 500 frei), fassungen/<lg>/hoerspiel +
              work/510_overlay.json (Gate 510 frei), work/400_regie.json (Sprechtext, Lexikon wie 500), book.json
              (Bestellung, pruefung_regler).
Ausgabe:      fassungen/<lg>/audio_final/<tid>.wav, fassungen/<lg>/hoerspiel_final/<tid>.wav,
              work/530_pruefung_<lg>.json, work/530_hoerliste.json (gekippt / Verdacht / ohne FA / Kapitel ausserhalb).
Gate:         je Sprache x Spur: Spur bestellt, Gate 500/510 frei, WAV + Manifest aktuell fuer jeden Satz, ffmpeg/FA/
              Whisper verfuegbar, Mock im Live-Lauf = 0 -> sonst Stopp; gekippt = 0 nach Wiederholung, Verdacht <= 2 %,
              ohne FA-Raender <= 1 %, Rand <= 0,15 s, LUFS Ziel +- Toleranz, Spitze <= -1 dBTP -> sonst Mensch
              (Hoerliste); gleicher Name in >= 3 Verdachtssaetzen -> Hinweis (Ruecksprung 400). Mensch-Freigabe gilt bei
              gleichem ausgabe_hash.
Kosten:       usage_log Stage 530 (Modal-Sekunden FA + Whisper, je Sprache); CPU 0 $.
Regler:       book.json pruefung_regler: --tempo [LG=]F (Standard: Chatterbox Adapter-Tempo, Gemini 1,0), --vor/--nach S,
              --rand-max, --lufs, --lufs-tol, --peak-max, --fa modal|cpu, --sprache modal|cpu|aus, --stichprobe P (%),
              --cer-verdacht, --p-min, --kurz-s, --verdacht-max, --ohne-fa-max, --versuche, --nachvertonen an|aus;
              dazu --satz ID (neu), --kapitel c001,c002, --lang, --spur hoerbuch|hoerspiel, --neu, --trocken.
Aufruf:       py -3.11 -m pipeline.s530_audio_pruefung <werk> [Regler] [--wer CK]
Exit: 0 auto, 2 Stopp, 3 Mensch, 1 Fehler.
"""
import argparse
import collections
import difflib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import bestellung, gate, manifest, mock, status, usage_log
from pipeline import s420_sprecher as s420
from pipeline import s500_vertonung_gemini as s500
from pipeline import s502_vertonung_chatterbox as cb
from pipeline import s510_hoerspiel_hybrid as s510

STAGE = "530"
SR = 24000
VERSION = 1
SPUREN = ("hoerbuch", "hoerspiel")
QUELLE = {"hoerbuch": "500", "hoerspiel": "510"}
FINAL = {"hoerbuch": "audio_final", "hoerspiel": "hoerspiel_final"}
EIN, AUS = 0.01, 0.03            # Ein-/Ausblendung an den Raendern (s)
GAIN_MAX = 20.0                  # dB
REGLER_STD = {"tempo": {}, "vor": 0.05, "nach": 0.12, "rand_max": 0.15, "lufs": -18.0, "lufs_tol": 1.0,
              "peak_max": -1.0, "fa": "modal", "sprache": "modal", "stichprobe": 100, "cer_verdacht": 0.35,
              "p_min": 0.5, "kurz_s": 1.0, "verdacht_max": 0.02, "ohne_fa_max": 0.01, "versuche": 2,
              "nachvertonen": True}
WHISPER_CPU = getattr(config, "WHISPER_CPU_MODELL", "small")


# ============================================================ Ablage
def pfad(werk, lg):
    return config.work_path(werk, f"530_pruefung_{lg}")


def final_dir(werk, lg, spur):
    return os.path.join(config.book_dir(werk), "fassungen", lg, FINAL[spur])


def hoerliste_pfad(werk):
    return os.path.join(config.work_dir(werk), "530_hoerliste.json")


def _json(p, leer=None):
    if not os.path.exists(p):
        return leer
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def kap_von(tid):
    return str(tid).split("_")[0]


# ============================================================ Audio
def tempo_anwenden(x, faktor):
    """atempo (ffmpeg, Tonhoehe bleibt); 1,0 = unveraendert."""
    if abs(float(faktor) - 1.0) < 1e-6 or not len(x):
        return x
    with tempfile.TemporaryDirectory() as d:
        q, z = os.path.join(d, "q.wav"), os.path.join(d, "z.wav")
        s510.schreiben(q, x)
        cb.atempo(q, z, faktor)
        return s510.lesen(z)


def lautheit(y):
    """(integrierte Lautheit LUFS, True Peak dBTP) per ffmpeg ebur128."""
    if not len(y):
        return -70.0, -70.0
    with tempfile.TemporaryDirectory() as d:
        q = os.path.join(d, "k.wav")
        s510.schreiben(q, y)
        r = subprocess.run(["ffmpeg", "-nostats", "-hide_banner", "-i", q, "-af", "ebur128=peak=true", "-f", "null", "-"],
                           capture_output=True, text=True)
    t = r.stderr
    i = re.findall(r"I:\s+(-?[\d.]+|-inf) LUFS", t)
    p = re.findall(r"Peak:\s+(-?[\d.]+|-inf) dBFS", t)
    f = lambda v: -70.0 if (not v or v[-1] == "-inf") else max(-70.0, float(v[-1]))
    return f(i), f(p)


def begrenzen(y, grenze_db, halb_ms=2.0):
    """Spitzenbegrenzer: Verstaerkung je Sample <= grenze/|y|, gegen Nachbarn (Minimum +-2w) und geglaettet
    (Mittel +-w) – an jeder Spitze bleibt die Verstaerkung <= noetig, ohne harte Spruenge."""
    lim = 10 ** (grenze_db / 20)
    a = np.abs(y)
    if not len(y) or a.max() <= lim:
        return y
    w = max(1, int(halb_ms / 1000 * SR))
    g = np.minimum(1.0, lim / np.maximum(a, 1e-9)).astype(np.float32)
    pad = np.pad(g, (2 * w, 2 * w), constant_values=1.0)
    gm = g.copy()
    for k in range(4 * w + 1):
        np.minimum(gm, pad[k:k + len(g)], out=gm)
    c = np.concatenate([[0.0], np.cumsum(np.pad(gm, (w, w), constant_values=1.0), dtype=np.float64)])
    gs = ((c[2 * w + 1:] - c[:-(2 * w + 1)]) / (2 * w + 1)).astype(np.float32)
    return (y * gs).astype(np.float32)


def raender(zeit):
    """FA-Wortzeiten -> (erster Wortanfang, letztes Wortende) in s oder None."""
    z = [x for x in (zeit or []) if x]
    return (min(a for a, _ in z), max(b for _, b in z)) if z else None


def schneiden(x, w, vor, nach, tempo):
    """Satz auf Sprachanteil schneiden; Raender so, dass sie nach dem Tempo vor/nach s betragen."""
    if not w:
        return x, None
    a = max(0, int((w[0] - vor * tempo) * SR))
    b = min(len(x), int((w[1] + nach * tempo) * SR))
    if b - a < int(0.1 * SR):
        return x, None
    y = x[a:b].astype(np.float32).copy()
    fi, fo = min(int(EIN * SR), len(y)), min(int(AUS * SR), len(y))
    y[:fi] *= np.linspace(0, 1, fi, dtype=np.float32)
    y[len(y) - fo:] *= np.linspace(1, 0, fo, dtype=np.float32)
    r_vor = (w[0] - a / SR) / tempo
    r_nach = (b / SR - w[1]) / tempo
    return y, (round(r_vor, 3), round(r_nach, 3))


# ============================================================ Werkzeuge (patchbar)
def werkzeuge_pruefen(fa, sprache, brauche_fa, brauche_sprache):
    """Vor jeder Ausgabe: ffmpeg, FA (torch bzw. modal), Whisper (faster_whisper bzw. modal). -> [Fehlertexte]."""
    fe = []
    if not shutil.which("ffmpeg"):
        fe.append("ffmpeg fehlt")
    if brauche_fa:
        e = s510.aligner_pruefen(fa, False)
        if e:
            fe.append(f"FA ({fa}): {e}")
    if brauche_sprache and sprache != "aus":
        try:
            if sprache == "modal":
                import modal  # noqa: F401
            else:
                import faster_whisper  # noqa: F401
        except Exception as e:
            fe.append(f"Whisper ({sprache}): {type(e).__name__}: {str(e)[:80]}")
    return fe


def fa_zeiten(jobs, werk, lg, art):
    """jobs [(key, wav, woerter)] -> {key: [(t0, t1)|None]}; Modal mit CPU-Rueckfall, Modal-Sekunden geloggt."""
    if not jobs:
        return {}
    t0 = time.time()
    out = s510.zeiten(jobs, werk, lg, art)
    if art == "modal":
        usage_log.log_gpu(werk, STAGE, time.time() - t0, extra={"sprache": lg, "teil": "fa"})
    return out


def _wav16(p):
    x = s510.lesen(p)
    n = int(round(len(x) * 16000 / SR))
    y = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32) if len(x) else x
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())
    return b.getvalue()


def sprache_cpu(jobs, lg):
    from faster_whisper import WhisperModel
    m = WhisperModel(WHISPER_CPU, device="cpu", compute_type="int8")
    out = {}
    for key, p in jobs:
        out[key] = _whisper(m, io.BytesIO(_wav16(p)), lg)
    return out


def _whisper(m, quelle, lg):
    """Erkannte Sprache (frei) + Abschrift in der Zielsprache (fuer CER)."""
    from faster_whisper.audio import decode_audio
    a = decode_audio(quelle, sampling_rate=16000)
    segs, info = m.transcribe(a, language=None, beam_size=1, without_timestamps=True,
                              condition_on_previous_text=False, vad_filter=False)
    list(segs)
    probs = dict(info.all_language_probs or [])
    segs, _ = m.transcribe(a, language=lg, beam_size=1, without_timestamps=True,
                           condition_on_previous_text=False, vad_filter=False)
    return {"top": info.language, "p": round(float(probs.get(lg, 0.0)), 4),
            "text": " ".join(s.text.strip() for s in segs), "dauer": round(len(a) / 16000, 2)}


def sprache_modal(jobs, werk, lg):
    from gpu_sprache.sprache_modal import app, pruefen
    t0 = time.time()
    arbeit = [{"key": k, "wav": _wav16(p), "lg": lg} for k, p in jobs]
    out = {}
    with app.run():
        for res in pruefen.map([arbeit[i:i + 60] for i in range(0, len(arbeit), 60)]):
            out.update(res)
    usage_log.log_gpu(werk, STAGE, time.time() - t0, extra={"sprache": lg, "teil": "whisper"})
    return out


def sprache(jobs, werk, lg, art):
    """jobs [(key, wav)] -> {key: {top, p, text, dauer} | {fehler}}; Modal mit CPU-Rueckfall."""
    if not jobs:
        return {}
    if art == "modal":
        try:
            return sprache_modal(jobs, werk, lg)
        except Exception as e:
            print(f"[530] Modal-Whisper nicht nutzbar -> CPU: {type(e).__name__}: {str(e)[:120]}")
    return sprache_cpu(jobs, lg)


# ============================================================ Sprachurteil
def _norm(s):
    s = unicodedata.normalize("NFKC", str(s or "")).lower().replace("ß", "ss")
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def cer(soll, ist):
    a, b = _norm(soll), _norm(ist)
    if not a:
        return 0.0
    return round(1 - difflib.SequenceMatcher(None, a, b, autojunk=False).ratio(), 4)


def urteil(r, soll, lg, rg):
    """Whisper-Ergebnis -> (stufe ok|verdacht|gekippt, cer)."""
    if not r or r.get("fehler"):
        return "verdacht", None
    c = cer(soll, r.get("text"))
    kurz = (r.get("dauer") or 0) < float(rg["kurz_s"]) or len(_norm(soll).split()) < 3
    fremd = r.get("top") != lg and float(r.get("p") or 0) < float(rg["p_min"])
    if fremd and not kurz:
        return "gekippt", c
    if fremd or c >= float(rg["cer_verdacht"]):
        return "verdacht", c
    return "ok", c


def stichprobe(tid, prozent):
    if prozent >= 100:
        return True
    return int(manifest.hash_text(tid)[:6], 16) % 100 < prozent


def namen(saetze):
    """Grossgeschriebene Woerter (nicht am Satzanfang) in >= 3 Saetzen -> {name: n}."""
    z = collections.Counter()
    for s in saetze:
        w = re.findall(r"\w+", s or "")
        z.update({x for x in w[1:] if x[:1].isupper() and len(x) > 2})
    return {k: v for k, v in z.most_common(10) if v >= 3}


# ============================================================ Regler
def _regler(roh):
    rg = json.loads(json.dumps(REGLER_STD))
    rg.update({k: v for k, v in (roh.get("pruefung_regler") or {}).items() if k in REGLER_STD})
    return rg


def regler_anwenden(rg, aend):
    rg = dict(rg)
    for k, v in (aend or {}).items():
        if v is None:
            continue
        rg[k] = {**(rg.get(k) or {}), **v} if k == "tempo" else v
    return rg


def _regler_gueltig(rg):
    try:
        return (rg["fa"] in ("modal", "cpu") and rg["sprache"] in ("modal", "cpu", "aus")
                and all(0.5 <= float(v) <= 2.0 for v in (rg.get("tempo") or {}).values())
                and 0 <= float(rg["vor"]) <= float(rg["rand_max"]) and 0 <= float(rg["nach"]) <= float(rg["rand_max"])
                and -30 <= float(rg["lufs"]) <= -10 and 0 < float(rg["lufs_tol"]) <= 3
                and -6 <= float(rg["peak_max"]) <= 0 and 0 <= int(rg["stichprobe"]) <= 100
                and 0 < float(rg["cer_verdacht"]) <= 1 and 0 <= float(rg["p_min"]) <= 1
                and 0 <= float(rg["verdacht_max"]) <= 1 and 0 <= float(rg["ohne_fa_max"]) <= 1
                and 0 <= int(rg["versuche"]) <= 3)
    except (KeyError, TypeError, ValueError):
        return False


def tempo_fuer(rg, lg, m5):
    """Regler je Sprache bzw. '*'; sonst Chatterbox -> Adapter-Tempo, Gemini -> 1,0 (Engine aus Manifest 500)."""
    t = (rg.get("tempo") or {}).get(lg)
    if t is None:
        t = (rg.get("tempo") or {}).get("*")
    if t is None:
        js = (m5.meta.get("je_sprache") or {}).get(lg) or {}
        t = cb.lora_werte((js.get("adapter") or {}).get("name"))[1] if js.get("engine") == "chatterbox" else 1.0
    return float(t)


# ============================================================ Lauf
def _spuren(b):
    """{lg: [spur]}: Hoerbuchspur je Audiosprache (500), Hoerspielspur je Hoerspiel-Sprache (510)."""
    out = {lg: ["hoerbuch"] for lg in s500._stufen(b)}
    for lg in s420._ziele(b):
        out.setdefault(lg, ["hoerbuch"]).append("hoerspiel")
    return out


def _quellen(werk):
    m5, _ = s500._manifest(werk, False)
    m51 = manifest.Manifest(werk, "510_overlay", stage="510") \
        if os.path.exists(config.work_path(werk, "510_overlay")) else None
    return {"hoerbuch": m5, "hoerspiel": m51}


def nachvertonen(werk, spur, lg, ids, wer):
    """Gekippte Saetze in 500 bzw. 510 neu erzeugen. -> Ergebnis der Stage (auto/mensch/stopp)."""
    mod = s500 if spur == "hoerbuch" else s510
    g = mod.run(werk, wer=wer, saetze=sorted(ids), nur_lang=lg)
    return (g.ergebnis or {}).get("ergebnis")


def run(werk, wer=None, regler=None, saetze=None, kapitel=None, nur_lang=None, nur_spur=None, neu=False, trocken=False):
    wer = wer or "pipeline"
    g = gate.Gate(werk, STAGE, ruecksprung="530", wer=wer)
    b = bestellung.lesen(werk)
    rg = _regler(dict(b.roh))
    if regler and any(v is not None for v in regler.values()):
        rg = regler_anwenden(rg, regler)
        if not trocken:
            b = bestellung.feld_setzen(werk, pruefung_regler=rg)
    sp = _spuren(b)
    if nur_lang:
        sp = {k: v for k, v in sp.items() if k == nur_lang}
    if nur_spur:
        sp = {k: [s for s in v if s == nur_spur] for k, v in sp.items()}
    g.metrik("spuren", sp)
    g.metrik("regler", rg)
    ip = config.work_path(werk, "400_regie")
    ok = g.pflicht("audio", any(sp.values()), ruecksprung="095", text="Audio (Hoerbuch/Hoerspiel) bestellt")
    ok = g.pflicht("eingang", os.path.exists(ip), ruecksprung="400", text="400_regie.json vorhanden") and ok
    ok = g.pflicht("regler", _regler_gueltig(rg), wert=rg, text="Regler im Bereich") and ok
    vor = {"500"} | ({"510"} if any("hoerspiel" in v for v in sp.values()) else set())
    for v in sorted(vor):
        z = status.zustand(werk, v)
        if trocken:
            g.hinweis(f"gate_{v}", z in status.FREI, text=f"Gate {v}: {z}")
        else:
            ok = g.pflicht(f"gate_{v}", z in status.FREI, wert=z, ruecksprung=v, text=f"Gate {v} frei ({z})") and ok
    if not ok:
        g.entscheide(schreiben=not trocken)
        return g
    data = _json(ip)
    q = _quellen(werk)
    saetze, kap = set(saetze or []), set(kapitel or [])
    teil = bool(saetze or kap or nur_lang or nur_spur or trocken)

    # ---- Planung
    plan = {}
    for lg in sorted(sp):
        units, _ = s500.einheiten(data, lg)
        lex, _ = s500._lexikon(werk, lg)
        tts = {u["id"]: lex(u["text"]) for u in units}
        tempo = tempo_fuer(rg, lg, q["hoerbuch"])
        m = manifest.Manifest(werk, f"530_pruefung_{lg}", stage=STAGE)
        for spur in sp[lg]:
            mq = q[spur]
            if spur == "hoerspiel":
                ids = [u["id"] for u in units if mq and f"{lg}/{u['id']}" in mq.eintraege]
            else:
                ids = [u["id"] for u in units]
            fehlt, mocks, soll = [], 0, {}
            for t in ids:
                k = f"{lg}/{t}"
                e = (mq.get(k) if mq else None) or {}
                if not e or not mq.datei_aktuell(k):
                    fehlt.append(t)
                    continue
                if e.get("q") == "mock":
                    mocks += 1
                soll[t] = {"quelle": mq._abs(e["datei"]), "q_hash": e["datei_hash"], "text": tts[t],
                           "fa": manifest.hash_obj({"d": e["datei_hash"], "t": tts[t], "v": VERSION}),
                           "ein": manifest.hash_obj({"d": e["datei_hash"], "t": tts[t], "tempo": tempo,
                                                     "r": [rg["vor"], rg["nach"]], "v": VERSION})}
            auswahl = {t for t in ids if kap_von(t) in kap or t in saetze} if (kap or saetze) else None
            plan[(lg, spur)] = {"m": m, "ids": ids, "fehlt": fehlt, "mock": mocks, "soll": soll, "tempo": tempo,
                                "auswahl": auswahl}

    # ---- Werkzeuge vor jeder Ausgabe
    def offen_fa(p, lg, spur):
        m = p["m"]
        return [t for t in p["soll"] if neu or t in saetze
                or ((m.get(f"{spur}/{t}") or {}).get("fa_hash") != p["soll"][t]["fa"])]
    brauche_fa = any(offen_fa(p, lg, spur) for (lg, spur), p in plan.items())
    fe = werkzeuge_pruefen(rg["fa"], rg["sprache"], brauche_fa, True)
    if trocken:
        for x in fe:
            g.hinweis("werkzeug", False, text=f"Werkzeug fehlt: {x} (live Stopp)")
    elif fe:
        g.pflicht("werkzeug", False, wert=fe, ruecksprung="530", text="Werkzeuge verfuegbar – " + "; ".join(fe))
        g.entscheide(schreiben=True)
        return g

    # ---- Bauen + Pruefen, gekippte Saetze bis rg['versuche'] x neu in 500/510
    hoer, je = {}, {}
    nachvertont = collections.defaultdict(set)
    for (lg, spur), p in plan.items():
        if trocken:
            nfa = len(offen_fa(p, lg, spur))
            je[f"{lg}/{spur}"] = {"saetze": len(p["ids"]), "fehlt": len(p["fehlt"]), "fa_offen": nfa,
                                  "tempo": p["tempo"]}
            g.hinweis(f"abdeckung_{lg}_{spur}", not p["fehlt"], wert=len(p["fehlt"]),
                      text=f"{lg}/{spur}: {len(p['ids']) - len(p['fehlt'])}/{len(p['ids'])} Saetze mit aktueller "
                           f"Roh-WAV ({QUELLE[spur]}); FA offen {nfa}; Tempo {p['tempo']}")
            continue
        runde = 0
        while True:
            _bauen(werk, lg, spur, p, rg, saetze, kap, neu)
            gek = _sprache_pruefen(werk, lg, spur, p, rg)
            n_vt = p["m"].meta.setdefault("nachvertont", {})
            wieder = sorted(t for t in gek if n_vt.get(f"{spur}/{t}", 0) < int(rg["versuche"]))
            if not (wieder and rg.get("nachvertonen") and runde < int(rg["versuche"])):
                break
            runde += 1
            for t in wieder:
                n_vt[f"{spur}/{t}"] = n_vt.get(f"{spur}/{t}", 0) + 1
            p["m"].speichern()
            erg = nachvertonen(werk, spur, lg, wieder, wer)
            nachvertont[(lg, spur)] |= set(wieder)
            if erg != "auto":
                g.hinweis(f"nachvertonen_{lg}_{spur}", False, wert=len(wieder), text=f"{lg}/{spur}: Nachvertonung "
                          f"{QUELLE[spur]} -> {erg} (Gate {QUELLE[spur]} pruefen, z. B. Kostenfreigabe) – "
                          f"{len(wieder)} gekippte Saetze bleiben")
                break
            q = _quellen(werk)
            _soll_neu(p, q[spur], lg, rg)
            if spur == "hoerbuch" and (lg, "hoerspiel") in plan:
                betr = nachvertont[(lg, spur)] & set((plan[(lg, "hoerspiel")]["ids"]))
                if betr:
                    nachvertonen(werk, "hoerspiel", lg, betr, wer)
                    _soll_neu(plan[(lg, "hoerspiel")], _quellen(werk)["hoerspiel"], lg, rg)
        je[f"{lg}/{spur}"] = {"saetze": len(p["ids"]), "tempo": p["tempo"],
                              "nachvertont": len(nachvertont[(lg, spur)])}
    for (lg, spur), p in plan.items():
        hoer.setdefault(lg, {})[spur] = _gate_spur(g, werk, lg, spur, p, rg, trocken, teil)
    n_mock = sum(p["mock"] for p in plan.values())
    g.mock(n_mock, ruecksprung="500")
    alle = {f"{lg}/{spur}/{t}": (p["m"].get(f"{spur}/{t}") or {}).get("datei_hash")
            for (lg, spur), p in plan.items() for t in p["ids"]}
    aus_hash = manifest.hash_obj(alle)
    g.metrik("ausgabe_hash", aus_hash)
    g.metrik("je_spur", je)
    st0 = status.laden(werk)["stages"].get(STAGE) or {}
    if st0.get("zustand") == "frei" and (st0.get("gate") or {}).get("ergebnis") == "mensch" \
            and (st0.get("metriken") or {}).get("ausgabe_hash") == aus_hash:
        for x in g.pruefungen:
            if not x["ok"] and x["bei_fehler"] == "mensch":
                x["bei_fehler"] = "hinweis"
                x["text"] = (x.get("text") or x["name"]) + " [Mensch-Freigabe gilt, Endfassung unveraendert]"
    if not trocken:
        for p in {id(p["m"]): p for p in plan.values()}.values():
            p["m"].meta.update({"regler": rg, "version": VERSION})
            p["m"].speichern()
        manifest.json_atomar(hoerliste_pfad(werk), hoer, indent=1)
    g.entscheide(schreiben=not trocken)
    g.hoerliste = hoer
    return g


def _soll_neu(p, mq, lg, rg):
    """Nach Nachvertonung: Eingaenge der Spur neu einlesen."""
    for t in list(p["soll"]):
        k = f"{lg}/{t}"
        e = (mq.get(k) if mq else None) or {}
        if not e or not mq.datei_aktuell(k):
            p["soll"].pop(t)
            p["fehlt"].append(t)
            continue
        s = p["soll"][t]
        s.update(quelle=mq._abs(e["datei"]), q_hash=e["datei_hash"],
                 fa=manifest.hash_obj({"d": e["datei_hash"], "t": s["text"], "v": VERSION}),
                 ein=manifest.hash_obj({"d": e["datei_hash"], "t": s["text"], "tempo": p["tempo"],
                                        "r": [rg["vor"], rg["nach"]], "v": VERSION}))


def _bauen(werk, lg, spur, p, rg, saetze, kap, neu):
    """FA fuer offene Saetze, dann je betroffenem Kapitel: schneiden, Tempo, Lautheit -> Endfassung."""
    m, soll, tempo = p["m"], p["soll"], p["tempo"]
    zd = final_dir(werk, lg, spur)
    # FA-Raender
    jobs = []
    for t, s in soll.items():
        e = m.get(f"{spur}/{t}") or {}
        if neu or t in saetze or e.get("fa_hash") != s["fa"]:
            jobs.append((t, s["quelle"], s510.woerter(s["text"])))
    zeit = fa_zeiten(jobs, werk, lg, rg["fa"]) if jobs else {}
    fa = {t: raender(zeit.get(t)) for t, _, _ in jobs}
    # Kapitel
    kapitel = collections.OrderedDict()
    for t in p["ids"]:
        if t in soll:
            kapitel.setdefault(kap_von(t), []).append(t)
    km = m.meta.setdefault("kapitel", {})
    for k, tids in kapitel.items():
        if kap and k not in kap and not (set(tids) & saetze):
            continue
        kh = manifest.hash_obj({"s": [(t, soll[t]["ein"]) for t in tids],
                                "l": [rg["lufs"], rg["peak_max"]], "v": VERSION})
        alt = km.get(f"{spur}/{k}") or {}
        aktuell = all(m.get(f"{spur}/{t}") and m.datei_aktuell(f"{spur}/{t}") for t in tids)
        if alt.get("hash") == kh and aktuell and not neu and not (set(tids) & saetze) and not (set(tids) & set(fa)):
            continue
        stuecke, info = {}, {}
        for t in tids:
            e = m.get(f"{spur}/{t}") or {}
            w = fa[t] if t in fa else (tuple(e["w"]) if e.get("w") else None)
            x = s510.lesen(soll[t]["quelle"])
            y, rand = schneiden(x, w, float(rg["vor"]), float(rg["nach"]), tempo)
            y = tempo_anwenden(y, tempo)
            stuecke[t] = y
            info[t] = {"w": list(w) if w else None, "rand": rand}
        roh = np.concatenate([stuecke[t] for t in tids]) if tids else np.zeros(0, np.float32)
        lu, pk = lautheit(roh)
        gain = max(-GAIN_MAX, min(GAIN_MAX, float(rg["lufs"]) - lu))
        ges = roh * 10 ** (gain / 20)
        begrenzt = pk + gain > float(rg["peak_max"])
        if begrenzt:
            ges = begrenzen(ges, float(rg["peak_max"]) - 1.0)
        lu2, pk2 = lautheit(ges)
        pos = 0
        for t in tids:
            y = ges[pos:pos + len(stuecke[t])]
            pos += len(stuecke[t])
            z = os.path.join(zd, f"{t}.wav")
            s510.schreiben(z, y)
            alt_e = m.get(f"{spur}/{t}") or {}
            m.setzen(f"{spur}/{t}", soll[t]["ein"], datei=z, fa_hash=soll[t]["fa"], w=info[t]["w"],
                     rand=info[t]["rand"], tempo=tempo, quelle_hash=soll[t]["q_hash"], kapitel=k,
                     dauer=round(len(y) / SR, 3), sprache=alt_e.get("sprache"))
        km[f"{spur}/{k}"] = {"hash": kh, "lufs_vor": round(lu, 2), "gain_db": round(gain, 2), "begrenzt": begrenzt,
                             "lufs": round(lu2, 2), "peak": round(pk2, 2), "saetze": len(tids)}
        m.speichern()
    # Verwaiste Endfassungen (Satz nicht mehr in der Spur)
    for key in [k for k in m.eintraege if k.startswith(f"{spur}/")]:
        t = key.split("/", 1)[1]
        if t not in p["ids"]:
            d = m._abs((m.get(key) or {}).get("datei") or "")
            if d and os.path.exists(d):
                os.remove(d)
            m.entfernen(key)
    m.speichern()


def _sprache_pruefen(werk, lg, spur, p, rg):
    """Whisper je Endfassung (nur neue Datei-Hashes, Stichprobe); -> gekippte tids."""
    m = p["m"]
    if rg["sprache"] == "aus":
        return []
    jobs = []
    for t in p["soll"]:
        e = m.get(f"{spur}/{t}") or {}
        if not e or not stichprobe(t, int(rg["stichprobe"])):
            continue
        if (e.get("sprache") or {}).get("datei_hash") != e.get("datei_hash"):
            jobs.append((t, m._abs(e["datei"])))
    res = sprache(jobs, werk, lg, rg["sprache"]) if jobs else {}
    for t, _ in jobs:
        e = m.get(f"{spur}/{t}")
        r = res.get(t) or {"fehler": "kein Ergebnis"}
        st, c = urteil(r, p["soll"][t]["text"], lg, rg)
        e["sprache"] = {"datei_hash": e["datei_hash"], "stufe": st, "cer": c, "top": r.get("top"), "p": r.get("p"),
                        "text": (r.get("text") or r.get("fehler") or "")[:300]}
    m.speichern()
    return [t for t in p["soll"] if ((m.get(f"{spur}/{t}") or {}).get("sprache") or {}).get("stufe") == "gekippt"]


def _gate_spur(g, werk, lg, spur, p, rg, trocken, teil):
    m, ids, q = p["m"], p["ids"], QUELLE[spur]
    n = len(ids) or 1
    if trocken:
        return {"fehlt": p["fehlt"][:200]}
    pre = f"{lg}/{spur}"
    fehlt = [t for t in p["fehlt"] if not p.get("auswahl") or t in p["auswahl"]]
    rest = [t for t in p["fehlt"] if t not in fehlt]
    if fehlt:
        g.pflicht(f"eingang_{lg}_{spur}", False, wert=len(fehlt), ruecksprung=q,
                  text=f"{pre}: {len(fehlt)} Saetze ohne aktuelle Roh-WAV {q} – {', '.join(fehlt[:3])}")
    if rest:
        g.hinweis(f"eingang_rest_{lg}_{spur}", False, wert=len(rest),
                  text=f"{pre}: {len(rest)} Saetze ausserhalb der Auswahl ohne aktuelle Roh-WAV {q}")
    fertig = [t for t in ids if m.get(f"{spur}/{t}") and m.datei_aktuell(f"{spur}/{t}")
              and (m.get(f"{spur}/{t}") or {}).get("eingang") == (p["soll"].get(t) or {}).get("ein")]
    if teil:
        g.hinweis(f"abdeckung_{lg}_{spur}", len(fertig) == len(ids), wert=len(ids) - len(fertig),
                  text=f"{pre}: {len(fertig)}/{len(ids)} Saetze mit aktueller Endfassung (Teillauf)")
    else:
        g.pflicht(f"abdeckung_{lg}_{spur}", len(fertig) == len(ids), wert=round(len(fertig) / n, 4), ruecksprung="530",
                  text=f"{pre}: Endfassung je Satz {len(fertig)}/{len(ids)}")
    ein = [m.get(f"{spur}/{t}") for t in fertig]
    ohne_fa = [t for t, e in zip(fertig, ein) if not e.get("rand")]
    g.max(f"ohne_fa_{lg}_{spur}", round(len(ohne_fa) / n, 4), float(rg["ohne_fa_max"]), ruecksprung=q)
    rmax = max([max(e["rand"]) for e in ein if e.get("rand")] or [0.0])
    g.max(f"rand_{lg}_{spur}", round(rmax, 3), float(rg["rand_max"]), ruecksprung="530")
    km = m.meta.get("kapitel") or {}
    kaps = {k: v for k, v in km.items() if k.startswith(f"{spur}/")}
    aus_l = [k.split("/", 1)[1] for k, v in kaps.items() if abs(v["lufs"] - float(rg["lufs"])) > float(rg["lufs_tol"])]
    aus_p = [k.split("/", 1)[1] for k, v in kaps.items() if v["peak"] > float(rg["peak_max"]) + 0.05]
    g.max(f"lufs_{lg}_{spur}", len(aus_l), 0, ruecksprung="530")
    g.max(f"spitze_{lg}_{spur}", len(aus_p), 0, ruecksprung="530")
    sp = {t: (e.get("sprache") or {}) for t, e in zip(fertig, ein)}
    gepr = [t for t, s in sp.items() if s.get("datei_hash") == (m.get(f"{spur}/{t}") or {}).get("datei_hash")]
    gek = [t for t in gepr if sp[t].get("stufe") == "gekippt"]
    ver = [t for t in gepr if sp[t].get("stufe") == "verdacht"]
    if rg["sprache"] == "aus":
        g.hinweis(f"sprache_{lg}_{spur}", False, text=f"{pre}: Sprachpruefung aus")
    else:
        g.pruefe(f"gekippt_{lg}_{spur}", not gek, len(gek), "= 0 nach Wiederholung", "mensch", q,
                 f"{pre}: gekippte Saetze {len(gek)}" + (f" – {', '.join(gek[:3])}" if gek else ""))
        g.max(f"verdacht_{lg}_{spur}", round(len(ver) / (len(gepr) or 1), 4), float(rg["verdacht_max"]),
              ruecksprung=q)
        nm = namen(p["soll"][t]["text"] for t in ver + gek)
        if nm:
            g.hinweis(f"namen_{lg}_{spur}", False, wert=nm, text=f"{pre}: wiederholte Namen in Verdachtssaetzen "
                      f"{', '.join(nm)} – Aussprache in 400 pruefen")
    zeile = lambda t: {"id": t, "text": p["soll"][t]["text"], "datei": (m.get(f"{spur}/{t}") or {}).get("datei"),
                       "sprache": sp.get(t)}
    return {"gekippt": [zeile(t) for t in gek], "verdacht": [zeile(t) for t in ver][:200],
            "ohne_fa": ohne_fa[:200], "kapitel_lufs": aus_l, "kapitel_spitze": aus_p, "fehlt": p["fehlt"][:200],
            "nachvertont": dict(m.meta.get("nachvertont") or {})}


# ============================================================ CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 530 Audio-Pruefungen")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--tempo", action="append", metavar="[LG=]F")
    for k in ("vor", "nach", "rand-max", "lufs", "lufs-tol", "peak-max", "cer-verdacht", "p-min", "kurz-s",
              "verdacht-max", "ohne-fa-max"):
        ap.add_argument(f"--{k}", type=float)
    for k in ("stichprobe", "versuche"):
        ap.add_argument(f"--{k}", type=int)
    ap.add_argument("--fa", choices=("modal", "cpu"))
    ap.add_argument("--sprache", choices=("modal", "cpu", "aus"))
    ap.add_argument("--nachvertonen", choices=("an", "aus"))
    ap.add_argument("--satz", action="append")
    ap.add_argument("--kapitel")
    ap.add_argument("--lang")
    ap.add_argument("--spur", choices=SPUREN)
    ap.add_argument("--neu", action="store_true")
    ap.add_argument("--trocken", action="store_true")
    a = ap.parse_args(argv)
    tempo = None
    if a.tempo:
        tempo = {}
        for x in a.tempo:
            k, _, v = x.rpartition("=")
            tempo[k or "*"] = float(v)
    regler = {"tempo": tempo, "vor": a.vor, "nach": a.nach, "rand_max": a.rand_max, "lufs": a.lufs,
              "lufs_tol": a.lufs_tol, "peak_max": a.peak_max, "cer_verdacht": a.cer_verdacht, "p_min": a.p_min,
              "kurz_s": a.kurz_s, "verdacht_max": a.verdacht_max, "ohne_fa_max": a.ohne_fa_max,
              "stichprobe": a.stichprobe, "versuche": a.versuche, "fa": a.fa, "sprache": a.sprache,
              "nachvertonen": None if a.nachvertonen is None else a.nachvertonen == "an"}
    wer = a.wer or "pipeline"
    try:
        if any(v is not None for v in regler.values()) and not a.trocken:
            from pipeline import s080_mandant
            s080_mandant.darf(a.werk, "entscheiden", wer)
        g = run(a.werk, wer, regler=regler, saetze=a.satz, kapitel=a.kapitel.split(",") if a.kapitel else None,
                nur_lang=a.lang, nur_spur=a.spur, neu=a.neu, trocken=a.trocken)
    except gate.GateHalt as e:
        print(e)
        return e.exit_code
    except (ValueError, PermissionError, RuntimeError) as e:
        print(f"[530] Fehler: {e}")
        return 1
    print(g.bericht())
    return gate.EXIT[g.ergebnis["ergebnis"]]

if __name__ == "__main__":
    sys.exit(main())
