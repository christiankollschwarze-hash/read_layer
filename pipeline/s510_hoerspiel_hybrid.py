"""STAGE 510 — Hoerspiel-Overlay (Umbau Phase 2, GATE_KATALOG.md Zeile 510, 02.11.2026)
Funktion:     Hoerspielspur je bestellter Hoerspiel-Sprache: jeder Satz mit Figurenanteil (420) wird neu gebaut –
              Figurenrede als Gemini-Take in der Figurenstimme aus casting.json (Abstandskorrektur je Figur x Sprache
              per Praat), Erzaehlerstuecke aus der Hoerbuchspur 500, Schnitt per Forced Alignment (MMS_FA, Modal oder
              CPU). Reine Figurensaetze bestehen nur aus Figurenstuecken. Hoerbuchspur bleibt unberuehrt.
Wirkungsweise: Manifest work/510_overlay.json je Sprache/Satz mit Eingangs-Hash (Segmente 420, Sprechtext 400 inkl.
              Lexikon, 500-WAV, Stimm-IDs, Korrektur, Naht-Regler, Entscheidungen): nur neue/geaenderte Saetze werden
              gebaut; Takes werden wiederverwendet, solange Text + Stimme gleich sind (Korrektur/Schnitt neu = 0 $).
              Vor jedem kostenpflichtigen Lauf Kostenschaetzung wie 500 (Somnio im Budget -> auto, Standard 0 $,
              sonst Mensch: --kosten-freigeben USD). Pruefung je Satz: FA-Woerter je Segment, Stueck >= 0,15 s,
              Nahtsprung <= 3 dB, Dauer 0,7–1,5 x Satz 500, Policy; auffaellig -> bis 2x neu (neuer Take, danach
              CPU-Schnitt), bis dahin Erzaehlerfassung aus 500 eingesetzt.
Eingang:      work/420_sprecher.json (Segmente; Gate 420 frei), work/400_regie.json (Sprechtext), work/casting.json
              Schema 2 freigegeben (rollen[lg][stufe]: Erzaehler, ensemble[] gemini_id + korrektur), work/500_vertonung.json
              (Hoerbuchspur, Gate 500 frei), work/aussprache_<lg>.json (Lexikon), work/510_entscheidungen.json.
Ausgabe:      fassungen/<lg>/hoerspiel/<tag>.wav (nur Saetze mit Figurenanteil; uebrige Saetze = fassungen/<lg>/audio),
              work/510_overlay.json (Manifest, Schnittprotokoll), work/_510/<lg>/takes/ (Takes), work/510_pruefung.json
              (Hoerliste + Ensemble-Stichprobe je Figur), work/510_kosten.json (Freigaben).
Gate:         Hoerspiel bestellt, Gate 400/410/420/500 frei, Casting freigegeben, Engine Gemini, Figurenstimmen
              nutzbar, Erzaehler 500 = casting, Satz 500 vorhanden, FA-Schnitt (und Praat bei Korrektur) verfuegbar,
              Abdeckung + Aktualitaet, Mock im Live-Lauf = 0 -> sonst Stopp; Kosten ueber Budget, auffaellig > 1 %
              -> Mensch; Hoerspiel-Freigabe immer Mensch (Ensemble-Stichprobe), gilt bei gleichem ausgabe_hash.
Kosten:       usage_log Stage 510 mit Sprache (Gemini-TTS in tts_client); Modal-Schnitt im Cent-Bereich.
Regler:       book.json hoerspiel_regler: --schnitt modal|cpu, --ueberblend MS, --lautheit an|aus, --budget,
              --auffaellig-max, --naht-db, --stueck-min, --dauer-min/--dauer-max, --fa-min, --versuche; dazu
              --behalten LG/TID (Erzaehlerfassung behalten), --bauen LG/TID (Behalten aufheben), --grenze LG/TID:K=A-B
              (Schnittgrenze Segment K in s, 'weg' = aufheben), --korrektur FIGUR:LG=F[,HT] --grund TEXT (an 410),
              --satz ID (neu bauen inkl. Takes), --kapitel, --lang, --neu, --probe N, --kosten-freigeben USD, --trocken.
Aufruf:       py -3.11 -m pipeline.s510_hoerspiel_hybrid <werk> [Regler] [--wer CK]
Exit: 0 auto, 2 Stopp, 3 Mensch, 1 Fehler.
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import bestellung, gate, manifest, mock, status, usage_log
from pipeline import s410_casting as s410
from pipeline import s420_sprecher as s420
from pipeline import s500_vertonung_gemini as s500

STAGE = "510"
SR = 24000
ERZ = s420.ERZ
VERSION = 1
REGLER_STD = {"schnitt": "modal", "ueberblend_ms": 12, "lautheit": True,
              "budget": float(getattr(config, "BUDGET_510_USD", 0.0)), "auffaellig_max": 0.01, "naht_db": 3.0,
              "stueck_min": 0.15, "dauer_min": 0.7, "dauer_max": 1.5, "fa_min": 0.9, "versuche": 2}
STIL_FIGUR = ("Character dialogue in an audio drama. Speak this line in character, naturally, as spoken "
              "dialogue – not as narration.")
RETRIES = 3
_ANF = re.compile(r"[\"„“”«»‚‘’‹›]")


class PolicyError(RuntimeError):
    """Gemini lehnt den Text per 'policy' ab."""


# ============================================================ Ablage
def pfad(werk):
    return config.work_path(werk, "510_overlay")


def hoerspiel_dir(werk, lg):
    return os.path.join(config.book_dir(werk), "fassungen", lg, "hoerspiel")


def take_dir(werk, lg):
    return os.path.join(config.work_dir(werk), "_510", lg, "takes")


def entsch_pfad(werk):
    return os.path.join(config.work_dir(werk), "510_entscheidungen.json")


def _json(p, leer=None):
    if not os.path.exists(p):
        return leer
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def entscheidungen(werk):
    d = _json(entsch_pfad(werk), {}) or {}
    d.setdefault("behalten", {})
    d.setdefault("grenzen", {})
    return d


def entscheidung_setzen(werk, wer, behalten=(), bauen=(), grenzen=None):
    d = entscheidungen(werk)
    for k in behalten:
        d["behalten"][k] = {"wer": wer, "wann": status.jetzt()}
    for k in bauen:
        d["behalten"].pop(k, None)
    for k, v in (grenzen or {}).items():
        if v is None:
            d["grenzen"].pop(k, None)
        else:
            d["grenzen"][k] = v
    d.setdefault("protokoll", []).append({"wann": status.jetzt(), "wer": wer, "behalten": list(behalten),
                                          "bauen": list(bauen), "grenzen": grenzen or {}})
    manifest.json_atomar(entsch_pfad(werk), d, indent=1)
    return d


# ============================================================ Audio-Bausteine
def lesen(p):
    with wave.open(p, "rb") as w:
        sr, n = w.getframerate(), w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype("float32") / 32768
    if n > 1:
        x = x.reshape(-1, n).mean(1)
    if sr != SR and len(x):
        x = np.interp(np.arange(0, len(x), sr / SR), np.arange(len(x)), x).astype("float32")
    return x


def schreiben(p, y):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with wave.open(p + ".tmp", "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())
    os.replace(p + ".tmp", p)


def _rms(v):
    return float(np.sqrt(np.mean(np.square(v)))) + 1e-9 if len(v) else 1e-9


def _db(v):
    return 20 * np.log10(_rms(v))


def korrigieren(x, sr, formant_faktor=1.0, tonhoehe_ht=0.0):
    """Abstandskorrektur (Praat 'Change gender'); Grenzen 0,94–1,10 / ±2 HT (CK 16.10.2026, pipeline/trennung.py)."""
    formant_faktor = min(1.10, max(0.94, float(formant_faktor)))
    tonhoehe_ht = min(2.0, max(-2.0, float(tonhoehe_ht)))
    if abs(formant_faktor - 1) < 1e-3 and abs(tonhoehe_ht) < 1e-3:
        return x
    import parselmouth
    from parselmouth.praat import call
    snd = parselmouth.Sound(np.asarray(x, np.float64), sr)
    f0 = snd.to_pitch_ac(time_step=0.01, pitch_floor=60, pitch_ceiling=600).selected_array["frequency"]
    med = float(np.median(f0[f0 > 0])) if (f0 > 0).sum() >= 3 else 0.0
    neu_med = med * 2 ** (tonhoehe_ht / 12) if med else 0.0
    out = call(snd, "Change gender", 60, 600, float(formant_faktor), neu_med, 1.0, 1.0)
    y = out.values[0].astype(np.float32)
    n = len(x)
    y = y[:n] if len(y) >= n else np.pad(y, (0, n - len(y)))
    r1, r2 = np.sqrt(np.mean(y ** 2)), np.sqrt(np.mean(np.asarray(x) ** 2))
    return (y * (r2 / r1) if r1 > 0 else y).astype(np.float32)


def _korr_aktiv(k):
    return bool(k) and (abs(float(k.get("formant_faktor", 1.0)) - 1) >= 1e-3
                        or abs(float(k.get("tonhoehe_ht", 0.0))) >= 1e-3)


# ============================================================ Forced Alignment (Schnitt)
def aligner_pruefen(art, korrektur):
    """Vor jeder Ausgabe: FA (torch lokal bzw. modal) und bei Korrektur parselmouth. -> Fehlertext oder None."""
    try:
        if art == "modal":
            import modal  # noqa: F401
        else:
            import torch  # noqa: F401
            import torchaudio  # noqa: F401
        if korrektur:
            import parselmouth  # noqa: F401
        return None
    except Exception as e:
        return f"{type(e).__name__}: {str(e)[:80]}"


def zeiten_cpu(jobs, werk=None, lg=None):
    from pipeline.s520_wortzeiten import _Aligner
    al = _Aligner()
    return {key: al.ausrichten(p, w) for key, p, w in jobs}


def zeiten_modal(jobs, werk, lg):
    from gpu_fa.schnitt_modal import app, vol, zeiten
    prefix = f"s510/{werk}/{lg}/{time.strftime('%Y%m%d%H%M%S')}"
    arbeit = []
    with app.run():
        with vol.batch_upload(force=True) as b:
            for i, (key, p, w) in enumerate(jobs):
                ziel = f"/{prefix}/{i:05d}.wav"
                b.put_file(p, ziel)
                arbeit.append({"key": key, "wav": ziel, "woerter": w})
        out = {}
        for res in zeiten.map([arbeit[i:i + 40] for i in range(0, len(arbeit), 40)]):
            out.update(res)
    return out


def zeiten(jobs, werk, lg, art):
    """jobs [(key, wav, woerter)] -> {key: [(t0, t1)|None je Wort]}; Modal mit CPU-Rueckfall."""
    if not jobs:
        return {}
    if art == "modal":
        try:
            return zeiten_modal(jobs, werk, lg)
        except Exception as e:
            print(f"[510] Modal-Schnitt nicht nutzbar -> CPU: {type(e).__name__}: {str(e)[:120]}")
    return zeiten_cpu(jobs, werk, lg)


def woerter(text):
    from pipeline.s525_wortbruecke import lautwoerter
    return [x["w"] for x in lautwoerter(text)]


def grenzen(zeit, zu, n_samples, idxs):
    """Schnittgrenzen {k: (a, b)} in Samples je Segment k (Mitte zwischen Nachbarwoertern), None = kein Schnitt."""
    ab = {}
    for k in idxs:
        z = [zeit[i] for i in range(len(zu)) if zu[i] == k and i < len(zeit) and zeit[i]]
        ab[k] = (min(a for a, _ in z), max(b for _, b in z)) if z else None
    out, reihe = {}, list(idxs)
    for j, k in enumerate(reihe):
        z = ab[k]
        if z is None:
            out[k] = None
            continue
        vor = next((ab[i] for i in reversed(reihe[:j]) if ab[i]), None)
        nach = next((ab[i] for i in reihe[j + 1:] if ab[i]), None)
        a = 0.0 if vor is None else (vor[1] + z[0]) / 2
        b = n_samples / SR if nach is None else (z[1] + nach[0]) / 2
        out[k] = (max(0, int(a * SR)), min(n_samples, int(b * SR)))
    return out


def abdeckung_seg(zeit, zu, k):
    n = [i for i in range(len(zu)) if zu[i] == k]
    return sum(1 for i in n if i < len(zeit) and zeit[i]) / len(n) if n else 1.0


# ============================================================ Satz-Plan
def figur_text(segs, figur, lex):
    return " ".join(_ANF.sub("", lex(g["t"])).strip(" ,;") for g in segs if g["s"] == figur).strip()


def satz_plan(segs, besetzt, lex):
    """Segmente -> Quellen je Segment ('erz' oder Figur) + Wortlisten je Quelle."""
    seg = []
    for g in segs:
        q = g["s"] if g["s"] in besetzt else "erz"            # Statisten/unbekannt -> Erzaehler
        w = woerter(lex(g["t"]))
        seg.append({"q": q, "t": g["t"], "w": w})
    quellen = list(dict.fromkeys(s["q"] for s in seg if s["w"]))
    # Erzaehlerquelle (500) kennt alle Woerter des Satzes, Figuren-Take nur seine eigenen
    w_q = {}
    for q in quellen:
        ww, zu = [], []
        for k, s in enumerate(seg):
            if q == "erz" or s["q"] == q:
                ww += s["w"]
                zu += [k] * len(s["w"])
        w_q[q] = (ww, zu)
    return seg, w_q


def montage(seg, w_q, wavs, zt, rg, korr, manuell=None):
    """-> (audio | None, grund, protokoll, werte). wavs {quelle: pfad} (+ 'erz' = Lautheitsbezug),
    zt {quelle: zeiten}, manuell {k: [a, b]} s in der Quelle."""
    xs = {q: lesen(p) for q, p in wavs.items()}
    gz, prot, teile = {}, [], []
    for q, (ww, zu) in w_q.items():
        gz[q] = grenzen(zt.get(q) or [], zu, len(xs[q]), sorted(set(zu)))
    fa_min = 1.0
    for k, s in enumerate(seg):
        if not s["w"]:
            continue
        q = s["q"]
        ww, zu = w_q[q]
        g = (manuell or {}).get(str(k))
        g = (int(g[0] * SR), int(g[1] * SR)) if g else gz[q].get(k)
        cov = abdeckung_seg(zt.get(q) or [], zu, k)
        fa_min = min(fa_min, cov)
        if g is None:
            return None, "kein_schnitt", prot, {"segment": k}
        if g[1] - g[0] < SR * float(rg["stueck_min"]):
            return None, "kein_schnitt", prot, {"segment": k, "stueck_s": round((g[1] - g[0]) / SR, 3)}
        if cov < float(rg["fa_min"]):
            return None, "fa", prot, {"segment": k, "fa": round(cov, 3)}
        y = xs[q][g[0]:g[1]].copy()
        if q != "erz" and _korr_aktiv(korr.get(q)):
            y = korrigieren(y, SR, korr[q].get("formant_faktor", 1.0), korr[q].get("tonhoehe_ht", 0.0))
        teile.append((q, y))
        prot.append({"k": k, "q": q, "a": round(g[0] / SR, 3), "b": round(g[1] / SR, 3)})
    if not teile:
        return None, "kein_schnitt", prot, {}
    ref = _rms(xs["erz"]) if "erz" in xs else None
    out, naht = [], 0.0
    kk = int(SR * float(rg["ueberblend_ms"]) / 1000)
    for i, (q, y) in enumerate(teile):
        if rg["lautheit"] and ref and q != "erz":
            y = y * (ref / _rms(y))
        k2 = min(len(y) // 2, kk)
        if k2:
            r = np.linspace(0, 1, k2, dtype="float32")
            y[:k2] *= r
            y[-k2:] *= r[::-1]
        if i and teile[i - 1][0] != q:
            naht = max(naht, abs(_db(y) - _db(out[-1])))
        out.append(y)
    y = np.concatenate(out)
    werte = {"naht_db": round(naht, 2), "fa_min": round(fa_min, 3), "dauer": round(len(y) / SR, 3)}
    if naht > float(rg["naht_db"]):
        return y, "naht", prot, werte
    return y, None, prot, werte


# ============================================================ Takes (Gemini)
def take(text, out, voice, lg):
    """Ein Figuren-Take; PolicyError bei Ablehnung, sonst bis RETRIES Versuche."""
    from pipeline import tts_client
    os.makedirs(os.path.dirname(out), exist_ok=True)
    for i in range(1, RETRIES + 1):
        try:
            s500.synth(text, STIL_FIGUR, out, voice, lg)
            time.sleep(s500._pause())
            return
        except tts_client.QuotaError:
            raise
        except Exception as e:
            if "policy" in str(e).lower():
                raise PolicyError(str(e)[:200]) from e
            if i == RETRIES:
                raise
            time.sleep(i * 3 if s500._pause() else 0)


def take_hash(text, info):
    return manifest.hash_obj({"t": text, "id": info.get("gemini_id"), "s": info.get("stimme"), "m": info.get("modell"),
                              "st": STIL_FIGUR})


# ============================================================ Regler
def _regler(roh):
    r = json.loads(json.dumps(REGLER_STD))
    for k, v in (roh.get("hoerspiel_regler") or {}).items():
        if k in REGLER_STD:
            r[k] = v
    return r


def regler_anwenden(rg, aend):
    rg = json.loads(json.dumps(rg))
    for k in REGLER_STD:
        if aend.get(k) is not None:
            rg[k] = aend[k]
    return rg


def _regler_gueltig(rg):
    try:
        return (rg["schnitt"] in ("modal", "cpu") and 0 <= int(rg["ueberblend_ms"]) <= 100
                and rg["lautheit"] in (True, False) and float(rg["budget"]) >= 0
                and 0 <= float(rg["auffaellig_max"]) <= 1 and 0 < float(rg["naht_db"]) <= 20
                and 0 < float(rg["stueck_min"]) <= 2 and 0 < float(rg["dauer_min"]) < float(rg["dauer_max"])
                and 0 < float(rg["fa_min"]) <= 1 and 0 <= int(rg["versuche"]) <= 3)
    except Exception:
        return False


# ============================================================ Lauf
def _pf(g, trocken, name, ok, wert=None, ruecksprung=None, text=None):
    if trocken:
        return g.hinweis(name, ok, wert=wert, text=text)
    return g.pflicht(name, ok, wert=wert, ruecksprung=ruecksprung, text=text)


def run(werk, wer=None, regler=None, saetze=None, kapitel=None, nur_lang=None, neu=False, probe=None,
        kosten_freigeben=None, trocken=False):
    wer = wer or "pipeline"
    g = gate.Gate(werk, STAGE, ruecksprung="510", wer=wer)
    b = bestellung.lesen(werk)
    rg = _regler(dict(b.roh))
    if regler and any(v is not None for v in regler.values()):
        rg = regler_anwenden(rg, regler)
        if not trocken:
            b = bestellung.feld_setzen(werk, hoerspiel_regler=rg)
    ziele = s420._ziele(b)
    g.metrik("hoerspielsprachen", ziele)
    g.metrik("regler", rg)
    ip, sp = config.work_path(werk, "400_regie"), s420.pfad(werk)
    ok = g.pflicht("hoerspiel", bool(ziele), ruecksprung="095", text="Hoerspiel bestellt")
    ok = g.pflicht("eingang", os.path.exists(ip) and os.path.exists(sp), ruecksprung="420",
                   text="400_regie.json + 420_sprecher.json vorhanden") and ok
    ok = g.pflicht("regler", _regler_gueltig(rg), wert=rg, text="Regler im Bereich") and ok
    for v in ("400", "410", "420", "500"):
        z = status.zustand(werk, v)
        if trocken:
            g.hinweis(f"gate_{v}", z in status.FREI, text=f"Gate {v}: {z}")
        else:
            ok = g.pflicht(f"gate_{v}", z in status.FREI, wert=z, ruecksprung=v, text=f"Gate {v} frei ({z})") and ok
    c = s410.laden(werk)
    frei = s410.freigegeben(c)
    if trocken and c and c.get("schema") == s410.SCHEMA:
        g.hinweis("casting", frei, text="Casting freigegeben" + ("" if frei else " – nein (Probe)"))
    else:
        ok = g.pflicht("casting", frei, ruecksprung="410", text="casting.json (Schema 2) freigegeben") and ok
    if not ok:
        g.entscheide(schreiben=not trocken)
        return g
    data = _json(ip)
    spr = (_json(sp) or {}).get("saetze") or {}
    m500, _ = s500._manifest(werk, False)                     # Altformat 500 -> leeres Manifest (nur lesen)
    m = manifest.Manifest(werk, "510_overlay", stage=STAGE)
    ent = entscheidungen(werk)
    saetze, kap = set(saetze or []), set(kapitel or [])

    # ---- Planung je Sprache
    plan, je_sprache = {}, {}
    for lg in sorted(ziele):
        stufe = ziele[lg]
        engine = s410.ENGINE.get(stufe)
        if not g.pflicht(f"engine_{lg}", engine == "gemini", ruecksprung="095",
                         text=f"{lg}: Hoerspiel-Stufe {stufe} mit Gemini ({engine})"):
            continue
        bs = (((c or {}).get("rollen") or {}).get(lg) or {}).get(stufe) or {}
        erz = bs.get("erzaehler") or {}
        ens = {e["figur"]: e for e in bs.get("ensemble") or [] if e.get("figur")}
        m5 = (m500.meta.get("je_sprache") or {}).get(lg) or {}
        _pf(g, trocken,
            f"erzaehler_{lg}", bool(erz.get("stimme")) and m5.get("stimme") == erz.get("stimme")
            and m5.get("engine") == "gemini", ruecksprung="500",
            text=f"{lg}: Hoerbuchspur 500 mit Erzaehler aus casting ({m5.get('engine')} {m5.get('stimme')} "
                 f"/ casting {erz.get('stimme')})")
        units, _alt = s500.einheiten(data, lg)
        lex, n_lex = s500._lexikon(werk, lg)
        tts = {u["id"]: lex(u["text"]) for u in units}
        figuren_genutzt, sel = set(), {}
        for tid in sorted(spr):
            segs = ((spr[tid] or {}).get(lg) or {}).get("seg")
            if not segs or tid not in tts:
                continue
            seg, w_q = satz_plan(segs, ens, lex)
            figs = [q for q in w_q if q != "erz"]
            if figs:
                sel[tid] = (segs, seg, w_q, figs)
                figuren_genutzt |= set(figs)
        ohne = sorted(f for f in figuren_genutzt if not (ens[f].get("gemini_id")))
        if not g.pflicht(f"stimmen_{lg}", not ohne, ruecksprung="410",
                         text=f"{lg}: Figurenstimmen mit Gemini-ID" + (f" – fehlt: {', '.join(ohne)}" if ohne else
                                                                      f" ({len(figuren_genutzt)} Figuren)")):
            continue
        korr = {f: ens[f].get("korrektur") or {} for f in figuren_genutzt}
        soll, takes_soll, texte, ohne500 = {}, {}, {}, []
        for tid, (segs, seg, w_q, figs) in sel.items():
            k5 = f"{lg}/{tid}"
            e5 = m500.get(k5) or {}
            if not e5 or not m500.datei_aktuell(k5) or (e5.get("q") == "mock" and not mock.aktiv()):
                ohne500.append(tid)
                if not trocken:
                    continue
            texte[tid] = {f: figur_text(segs, f, lex) for f in figs}
            takes_soll[tid] = {f: take_hash(texte[tid][f], ens[f]) for f in figs}
            soll[tid] = manifest.hash_obj({
                "seg": [[x["t"], x["s"]] for x in segs], "t": tts[tid], "erz": e5.get("datei_hash"),
                "takes": takes_soll[tid], "korr": {f: korr[f] for f in figs if _korr_aktiv(korr[f])},
                "n": [rg["ueberblend_ms"], rg["lautheit"]], "beh": f"{lg}/{tid}" in ent["behalten"],
                "gr": ent["grenzen"].get(f"{lg}/{tid}"), "v": VERSION})
        offen = []
        for tid in soll:
            k = f"{lg}/{tid}"
            mock_alt = (m.get(k) or {}).get("q") == "mock" and not mock.aktiv()
            if neu or tid in saetze or mock_alt or m.braucht_neu(k, soll[tid]) or not m.datei_aktuell(k):
                if kap and tid[:4] not in kap and tid not in saetze:
                    continue
                offen.append(tid)
        if nur_lang and lg != nur_lang:
            offen = []
        if probe:
            offen = offen[:int(probe)]
        tdir = take_dir(werk, lg)
        take_neu = {}
        for tid in offen:
            if f"{lg}/{tid}" in ent["behalten"]:
                continue
            alt_t = (m.get(f"{lg}/{tid}") or {}).get("takes") or {}
            for f in sel[tid][3]:
                p = os.path.join(tdir, f"{tid}__{f}.wav")
                if neu or tid in saetze or alt_t.get(f) != takes_soll[tid][f] or not os.path.exists(p) \
                        or (mock.ist_datei(p) and not mock.aktiv()):
                    take_neu.setdefault(tid, []).append(f)
        zeichen = sum(len(texte[t][f]) for t, fs in take_neu.items() for f in fs)
        plan[lg] = dict(stufe=stufe, erz=erz, ens=ens, korr=korr, units=units, tts=tts, sel=sel, soll=soll,
                        takes_soll=takes_soll, texte=texte, offen=offen, take_neu=take_neu, ohne500=ohne500,
                        zeichen=zeichen, usd=s500.kosten("gemini", zeichen), n_lex=n_lex, tdir=tdir)
    usd = round(sum(p["usd"] for p in plan.values()), 4)
    n_takes = sum(len(fs) for p in plan.values() for fs in p["take_neu"].values())
    n_offen = sum(len(p["offen"]) for p in plan.values())
    g.metrik("kosten_usd", usd)
    g.metrik("offen", {lg: len(p["offen"]) for lg, p in plan.items()})
    g.metrik("takes_neu", {lg: sum(len(v) for v in p["take_neu"].values()) for lg, p in plan.items()})
    if g.fehler():
        g.entscheide(schreiben=not trocken)
        return g

    # ---- Kostenfreigabe / Schnitt-Werkzeuge vor dem Lauf
    if n_offen and not mock.aktiv() and not trocken:
        if n_takes:
            frei_k = kosten_freigeben is not None and usd <= float(kosten_freigeben)
            im_budget = b.mandant_art == "somnio" and usd <= float(rg["budget"])
            txt = (f"Kostenschaetzung {usd:.2f} $ fuer {n_takes} Figuren-Takes ("
                   + ", ".join(f"{lg} {sum(len(v) for v in p['take_neu'].values())} Takes/{p['zeichen']} Z. "
                               f"~{p['usd']:.2f} $" for lg, p in plan.items() if p["take_neu"]) + ")")
            if not (frei_k or im_budget):
                g.pruefe("kosten", False, wert=usd, bei_fehler="mensch", ruecksprung="510",
                         text=txt + (f" ueber Budget {float(rg['budget']):.2f} $" if b.mandant_art == "somnio"
                                     else f" – Mandant {b.mandant_art}")
                         + f" – Freigabe: py -3.11 -m pipeline.s510_hoerspiel_hybrid {werk} --kosten-freigeben "
                           f"{usd:.2f} --wer CK" + (f" (Freigabe {float(kosten_freigeben):.2f} $ reicht nicht)"
                                                     if kosten_freigeben is not None else ""))
                g.entscheide(schreiben=True)
                return g
            g.hinweis("kosten", True, wert=usd, text=txt + (" – freigegeben" if frei_k else " – im Budget"))
            if frei_k:
                p_ = os.path.join(config.work_dir(werk), "510_kosten.json")
                d = _json(p_, {"freigaben": []}) or {"freigaben": []}
                d["freigaben"].append({"wann": status.jetzt(), "wer": wer, "usd": usd,
                                       "grenze": float(kosten_freigeben), "takes": n_takes})
                manifest.json_atomar(p_, d, indent=1)
        braucht_korr = any(_korr_aktiv(k) for p in plan.values() for k in p["korr"].values())
        fe = aligner_pruefen(rg["schnitt"], braucht_korr)
        if fe:
            g.pflicht("schnitt_werkzeug", False, ruecksprung="510",
                      text=f"FA-Schnitt{' / Praat-Korrektur' if braucht_korr else ''} nicht verfuegbar ({fe})")
            g.entscheide(schreiben=True)
            return g
    elif trocken and n_offen:
        g.hinweis("kosten", False, wert=usd, text=f"Probe: {n_offen} Saetze wuerden gebaut, {n_takes} Takes, "
                                                  f"~{usd:.2f} $")

    # ---- Bau + Pruefung je Sprache
    pruef, ausfall = {}, None
    for lg, p in plan.items():
        n_bau = 0
        if p["offen"] and not trocken and ausfall is None:
            usage_log.set_context(werk, STAGE, sprache=lg)
            print(f"[510] {lg}: {len(p['offen'])} Hoerspiel-Saetze, {sum(map(len, p['take_neu'].values()))} Takes")
            try:
                n_bau = _bauen(werk, lg, p, m, m500, rg, ent)
            except Exception as e:
                ausfall = f"{lg}: {type(e).__name__}: {str(e)[:160]}"
                print(f"[510] Abbruch {ausfall}")
            m.speichern()
        # verwaiste Hoerspiel-Saetze (keine Figur mehr) entfernen
        if not trocken and not (kap or probe or saetze):
            for k in [k for k in m.eintraege if k.startswith(f"{lg}/") and k.split("/", 1)[1] not in p["sel"]]:
                e = m.entfernen(k)
                if e and e.get("datei") and os.path.exists(m._abs(e["datei"])):
                    os.remove(m._abs(e["datei"]))
        pruef[lg] = _gate_sprache(g, m, lg, p, rg, trocken, probe, kap, nur_lang)
        je_sprache[lg] = {"stufe": p["stufe"], "erzaehler": p["erz"].get("stimme"),
                          "figuren": {f: {"stimme": p["ens"][f].get("stimme"), "gemini_id": p["ens"][f].get("gemini_id"),
                                          "korrektur": p["korr"].get(f) or None} for f in sorted(p["korr"])},
                          "saetze": len(p["sel"]), "gebaut": n_bau, "lexikon": p["n_lex"],
                          "rest": f"fassungen/{lg}/audio"}
    if ausfall:
        g.pflicht("lauf", False, ruecksprung="510", text=f"Hoerspiel-Bau abgebrochen – {ausfall}")
    alle = [f"{lg}/{t}" for lg, p in plan.items() for t in p["sel"]]
    g.mock(sum(1 for k in alle if (m.get(k) or {}).get("q") == "mock"), ruecksprung="510")
    aus_hash = manifest.hash_obj({k: (m.get(k) or {}).get("datei_hash") for k in alle})
    g.metrik("ausgabe_hash", aus_hash)
    g.metrik("je_sprache", je_sprache)
    st0 = status.laden(werk)["stages"].get(STAGE) or {}
    bestaetigt = (st0.get("zustand") == "frei" and (st0.get("metriken") or {}).get("ausgabe_hash") == aus_hash
                  and not probe)
    if bestaetigt:
        for x in g.pruefungen:
            if not x["ok"] and x["bei_fehler"] == "mensch" and x["name"] != "kosten":
                x["bei_fehler"] = "hinweis"
                x["text"] += " [Mensch-Freigabe gilt, Hoerspiel unveraendert]"
    if not trocken:
        m.meta.update({"je_sprache": je_sprache, "ausgabe_hash": aus_hash, "regler": rg})
        if plan:
            m.speichern()
        manifest.json_atomar(os.path.join(config.work_dir(werk), "510_pruefung.json"), pruef, indent=1)
    grund = (f"Probe {probe} Saetze je Sprache – anhoeren (work/510_pruefung.json), dann Volllauf" if probe else
             "Hoerspiel-Freigabe: Ensemble-Stichprobe je Figur anhoeren (work/510_pruefung.json → stichprobe)")
    g.entscheide(mensch_immer=bool(probe) or (bool(alle) and not bestaetigt), mensch_grund=grund,
                 schreiben=not trocken)
    g.pruef = pruef
    return g


def _bauen(werk, lg, p, m, m500, rg, ent):
    """Takes erzeugen, schneiden, montieren, pruefen (bis N x neu); schreibt Manifest-Eintraege. -> Anzahl gebaut."""
    hdir, tdir, offen = hoerspiel_dir(werk, lg), p["tdir"], p["offen"]
    befund, versuche, protok, werte, geschrieben = {}, {t: 0 for t in offen}, {}, {}, set()
    erz_p = {t: m500._abs(m500.get(f"{lg}/{t}")["datei"]) for t in offen}
    beh = [t for t in offen if f"{lg}/{t}" in ent["behalten"]]
    bau = [t for t in offen if t not in beh]

    def tp(t, f):
        return os.path.join(tdir, f"{t}__{f}.wav")

    def takes_erzeugen(ids, alle=False):
        for t in ids:
            for f in (p["sel"][t][3] if alle else p["take_neu"].get(t, [])):
                if mock.aktiv():
                    os.makedirs(tdir, exist_ok=True)
                    mock.wav(tp(t, f))
                    continue
                try:
                    take(p["texte"][t][f], tp(t, f), p["ens"][f]["gemini_id"], lg)
                except PolicyError as e:
                    befund[t] = "policy"
                    print(f"  policy {t} ({f}): {e}")
                    break

    def schneiden(ids, art):
        ids = [t for t in ids if befund.get(t) != "policy"]
        if mock.aktiv() or not ids:
            return
        jobs = [(f"{t}|{q}", erz_p[t] if q == "erz" else tp(t, q), ww)
                for t in ids for q, (ww, _zu) in p["sel"][t][2].items()]
        zt = zeiten(jobs, werk, lg, art)
        for t in ids:
            _segs, seg, w_q, _figs = p["sel"][t]
            wavs = {q: tp(t, q) for q in w_q if q != "erz"}
            wavs["erz"] = erz_p[t]
            y, gr, prot, w = montage(seg, w_q, wavs, {q: zt.get(f"{t}|{q}") for q in w_q}, rg, p["korr"],
                                     ent["grenzen"].get(f"{lg}/{t}"))
            if y is not None and gr is None:
                q_ = len(y) / SR / (s500.wav_dauer(erz_p[t]) or 1.0)
                if not (float(rg["dauer_min"]) <= q_ <= float(rg["dauer_max"])):
                    gr, w["dauer_q"] = "dauer", round(q_, 3)
            alt = befund.get(t, "fehlt")
            if y is not None and RANG.get(gr, 9) < RANG.get(alt, 9):
                schreiben(os.path.join(hdir, f"{t}.wav"), y)
                geschrieben.add(t)
                befund[t], protok[t], werte[t] = gr, prot, w
            elif t not in geschrieben:
                befund[t], protok[t], werte[t] = gr, prot, w

    takes_erzeugen(bau)
    schneiden(bau, rg["schnitt"])
    for runde in range(int(rg["versuche"])):
        schlecht = [t for t in bau if befund.get(t) is not None]
        if not schlecht or mock.aktiv():
            break
        for t in schlecht:
            versuche[t] += 1
        if runde == 0 or rg["schnitt"] == "cpu":           # neuer Take
            for t in schlecht:
                if befund[t] == "policy":
                    befund[t] = "fehlt"
            takes_erzeugen(schlecht, alle=True)
        schneiden(schlecht, "cpu" if runde > 0 else rg["schnitt"])   # danach CPU-Schnitt
    n = 0
    for t in offen:
        k = f"{lg}/{t}"
        out = os.path.join(hdir, f"{t}.wav")
        gr = None
        if mock.aktiv():
            os.makedirs(hdir, exist_ok=True)
            mock.wav(out)
            q = "mock"
        elif t in beh:
            os.makedirs(hdir, exist_ok=True)
            shutil.copy2(erz_p[t], out)
            q = "behalten"
        elif t in geschrieben:
            q, gr = "neu", befund.get(t)
        else:
            os.makedirs(hdir, exist_ok=True)
            shutil.copy2(erz_p[t], out)                       # Erzaehlerfassung bleibt eingesetzt
            q, gr = "erzaehler", befund.get(t) or "fehlt"
        m.setzen(k, p["soll"][t], datei=out, q=q, pruefung=gr, versuche=versuche.get(t, 0),
                 takes={} if t in beh else {f: p["takes_soll"][t][f] for f in p["sel"][t][3]},
                 figuren=p["sel"][t][3], schnitt=protok.get(t), werte=werte.get(t),
                 dauer=s500.wav_dauer(out), erz500=(m500.get(k) or {}).get("datei_hash"))
        n += 1
    return n


RANG = {None: 0, "naht": 1, "dauer": 2, "fa": 3, "kein_schnitt": 4, "policy": 5, "fehlt": 6}


def _gate_sprache(g, m, lg, p, rg, trocken, probe, kap, nur_lang):
    sel = p["sel"]
    fehlt, veraltet, ausf, policy = [], [], [], []
    for tid in sel:
        k = f"{lg}/{tid}"
        e = m.get(k)
        if tid in p["ohne500"] or not e or not m.datei_aktuell(k):
            fehlt.append(tid)
        elif e.get("eingang") != p["soll"].get(tid):
            veraltet.append(tid)
        elif e.get("pruefung"):
            ausf.append(tid)
            if e["pruefung"] == "policy":
                policy.append(tid)
    n = len(sel) or 1
    teil = bool(probe or kap or (nur_lang and nur_lang != lg) or trocken)
    if p["ohne500"]:
        _pf(g, trocken, f"satz500_{lg}", False, wert=len(p["ohne500"]), ruecksprung="500",
                  text=f"{lg}: {len(p['ohne500'])} Saetze ohne aktuelle Hoerbuch-WAV 500 – "
                       f"{', '.join(p['ohne500'][:3])}")
    if teil:
        g.hinweis(f"abdeckung_{lg}", not fehlt and not veraltet, wert=len(fehlt) + len(veraltet),
                  text=f"{lg}: {len(fehlt) + len(veraltet)} von {len(sel)} Hoerspiel-Saetzen ohne aktuelles Audio "
                       f"({'Probe' if probe else 'Teillauf' if not trocken else 'Probe trocken'})")
    else:
        g.pflicht(f"abdeckung_{lg}", not fehlt, wert=round(1 - len(fehlt) / n, 4), ruecksprung="510",
                  text=f"{lg}: Abdeckung Hoerspiel-WAV je Satz mit Figurenanteil {len(sel) - len(fehlt)}/{len(sel)}"
                       + (f" – fehlt: {', '.join(fehlt[:3])}" if fehlt else ""))
        g.pflicht(f"aktualitaet_{lg}", not veraltet, wert=len(veraltet), ruecksprung="510",
                  text=f"{lg}: Aktualitaet (Segmente 420, Sprechtext 400, Stimmen/Korrektur casting, WAV 500)"
                       + (f" – veraltet: {', '.join(veraltet[:3])}" if veraltet else ""))
    if policy:
        g.hinweis(f"policy_{lg}", False, wert=len(policy), text=f"{lg}: {len(policy)} Policy-Ablehnungen "
                  f"(Erzaehlerfassung eingesetzt)")
    g.max(f"auffaellig_{lg}", round(len(ausf) / n, 4), float(rg["auffaellig_max"]), ruecksprung="510")

    def zeile(t):
        e = m.get(f"{lg}/{t}") or {}
        segs = p["sel"][t][0]
        return {"id": t, "seg": [f"[{x['s']}] {x['t']}" for x in segs], "grund": e.get("pruefung"),
                "q": e.get("q"), "datei": e.get("datei"), "werte": e.get("werte"), "versuche": e.get("versuche")}
    stich = {}
    for t in sel:
        e = m.get(f"{lg}/{t}") or {}
        if e.get("q") != "neu" or e.get("pruefung"):
            continue
        for f in p["sel"][t][3]:
            if len(stich.setdefault(f, [])) < 3:
                stich[f].append(zeile(t))
    return {"erzaehler": p["erz"].get("stimme"), "auffaellig": [zeile(t) for t in ausf], "fehlt": fehlt[:200],
            "veraltet": veraltet[:200], "stichprobe": stich, "probe": [zeile(t) for t in p["offen"]] if probe else []}


# ============================================================ CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 510 Hoerspiel-Overlay")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--schnitt", choices=("modal", "cpu"))
    ap.add_argument("--ueberblend", type=int, metavar="MS")
    ap.add_argument("--lautheit", choices=("an", "aus"))
    for k in ("budget", "auffaellig-max", "naht-db", "stueck-min", "dauer-min", "dauer-max", "fa-min"):
        ap.add_argument(f"--{k}", type=float)
    for k in ("versuche", "probe"):
        ap.add_argument(f"--{k}", type=int)
    ap.add_argument("--behalten", action="append", metavar="LG/TID")
    ap.add_argument("--bauen", action="append", metavar="LG/TID")
    ap.add_argument("--grenze", action="append", metavar="LG/TID:K=A-B|weg")
    ap.add_argument("--korrektur", metavar="FIGUR:LG=F[,HT]")
    ap.add_argument("--grund")
    ap.add_argument("--satz", action="append")
    ap.add_argument("--kapitel")
    ap.add_argument("--lang")
    ap.add_argument("--neu", action="store_true")
    ap.add_argument("--kosten-freigeben", type=float, metavar="USD")
    ap.add_argument("--trocken", action="store_true")
    a = ap.parse_args(argv)
    wer = a.wer or "pipeline"
    regler = {"schnitt": a.schnitt, "ueberblend_ms": a.ueberblend, "lautheit": {"an": True, "aus": False}.get(a.lautheit),
              "budget": a.budget, "auffaellig_max": a.auffaellig_max, "naht_db": a.naht_db,
              "stueck_min": a.stueck_min, "dauer_min": a.dauer_min, "dauer_max": a.dauer_max, "fa_min": a.fa_min,
              "versuche": a.versuche}
    try:
        aend = a.behalten or a.bauen or a.grenze or a.korrektur
        if (a.kosten_freigeben is not None or aend or any(v is not None for v in regler.values())) and not a.trocken:
            from pipeline import s080_mandant
            s080_mandant.darf(a.werk, "entscheiden", wer)
        if a.korrektur:
            fig, rest = a.korrektur.rsplit(":", 1)
            lg, w = rest.split("=", 1)
            f_, ht = (w.split(",") + ["0"])[:2]
            s410.korrektur_setzen(a.werk, fig, lg, formant=None if f_ == "weg" else float(f_), tonhoehe=float(ht),
                                  wer=wer, grund=a.grund or "")
        if a.behalten or a.bauen or a.grenze:
            gr = {}
            for x in a.grenze or []:
                k, rest = x.split(":", 1)
                seg, ab = rest.split("=", 1)
                if ab == "weg":
                    gr.setdefault(k, None)
                else:
                    a0, b0 = (float(v) for v in ab.split("-"))
                    alt = (entscheidungen(a.werk)["grenzen"].get(k) or {}) if gr.get(k) is None else gr[k]
                    gr[k] = dict(alt, **{seg: [a0, b0]})
            entscheidung_setzen(a.werk, wer, a.behalten or (), a.bauen or (), gr)
        g = run(a.werk, wer, regler=regler, saetze=a.satz, kapitel=a.kapitel.split(",") if a.kapitel else None,
                nur_lang=a.lang, neu=a.neu, probe=a.probe, kosten_freigeben=a.kosten_freigeben, trocken=a.trocken)
    except gate.GateHalt as e:
        print(e)
        return e.exit_code
    except (ValueError, PermissionError, RuntimeError) as e:
        print(f"[510] Fehler: {e}")
        return 1
    print(g.bericht())
    return gate.EXIT[g.ergebnis["ergebnis"]]


if __name__ == "__main__":
    sys.exit(main())
