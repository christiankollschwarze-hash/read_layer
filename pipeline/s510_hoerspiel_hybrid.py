"""STAGE 510 — Hoerspiel-Hybrid (AP 62, 29.10.2026)
Funktion:  Je gemischtem Satz (Erzaehler + Figur laut sprecher.json): Erzaehler-Take = ganzer Satz mit
           Erzaehlerstimme (Gemini), Einschuebe ("sagte Alice") aus diesem Take, Figurenrede aus dem Erstlauf.
Schnitt:   Wortzeiten per MMS_FA: Modal-GPU (gpu_fa/schnitt_modal.py, L4/A10G/T4); CPU-Rueckfall bei Modal-Fehler.
Position:  nach 500 Vertonung, vor 520 Wortzeiten (520 misst die geaenderten Saetze neu).
Regeln:    - wiederaufnehmbar (work/_hybrid/<lg>/fertig.txt), Fortschritt sichtbar
           - Fehler (ausser Policy) stoppen die Batch: keine Teilfassung ohne Protokoll
           - Kein sauberer Schnitt -> Satz bleibt unveraendert (Protokoll "kein Schnitt")
           - Gemini-'policy'-Ablehnung -> Satz bleibt unveraendert, Protokoll "policy"
           - Sicherung der alten WAVs: fassungen/<lg>/audio_alt_<datum>_hybrid/
           - Aktiv nur fuer config.HYBRID_WERKE; config.HYBRID_TESTDIR leitet Schreibvorgaenge in einen Testordner
Protokoll: work/hybrid_<lg>.json (bzw. im Testordner)
"""
import concurrent.futures as cf
import datetime
import json
import os
import shutil
import time
import wave

import numpy as np

from config import config
from pipeline import tts_client

SR = 24000
LANG = {"en": "en-GB", "de": "de-DE"}
STIL = {
    "de": "German audiobook narration. Speak German only, with native German pronunciation and melody; never switch to English.",
    "en": "English audiobook narration. Speak British English only, with native English pronunciation.",
}


class PolicyError(RuntimeError):
    """Gemini lehnt den Text per 'policy' ab -> Satz bleibt unveraendert, kein Stopp."""


def _pfade(book):
    t = getattr(config, "HYBRID_TESTDIR", "")
    if t:
        base = os.path.join(t, book)
        return {"bd": os.path.join(base, "bd"), "work": os.path.join(base, "work"), "test": True}
    return {"bd": config.book_dir(book), "work": config.work_dir(book), "test": False}


def _audio_dir(book, lg, p, chapter=None):
    adir = os.path.join(p["bd"], "fassungen", lg, "audio")
    if p["test"]:
        src = os.path.join(config.book_dir(book), "fassungen", lg, "audio")
        os.makedirs(adir, exist_ok=True)
        n = 0
        for f in os.listdir(src):
            if f.endswith(".wav") and (not chapter or f.startswith(chapter + "_")):
                if not os.path.exists(os.path.join(adir, f)):
                    shutil.copy2(os.path.join(src, f), os.path.join(adir, f)); n += 1
        print(f"[510] Testordner {lg}: {n} Audio-Dateien kopiert (Produktion unberuehrt)", flush=True)
    return adir


def auswahl(book, lg, chapter=None):
    spr = json.load(open(os.path.join(config.work_dir(book), "sprecher.json"), encoding="utf-8"))
    A = {}
    for t, v in spr.items():
        if chapter and not t.startswith(chapter + "_"):
            continue
        segs = [g for g in v.get(lg, []) if g["t"].strip()]
        s = {g["s"] for g in segs}
        if "Erzaehler" in s and len(s) > 1:
            A[t] = segs
    return dict(sorted(A.items()))


def _take(text, voice, lg, ziel):
    """Erzaehler-Take als WAV. Wirft PolicyError bei 'policy', sonst RuntimeError."""
    try:
        pcm = tts_client.synthesize_bytes(text, STIL[lg], voice, LANG[lg], fmt="l16")
    except Exception as e:
        if "policy" in str(e).lower():
            raise PolicyError(str(e)[:200]) from e
        raise
    if pcm[:4] == b"RIFF":
        pcm = pcm[pcm.find(b"data") + 8:]
    os.makedirs(os.path.dirname(ziel), exist_ok=True)
    with wave.open(ziel + ".tmp", "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm)
    os.replace(ziel + ".tmp", ziel)


def lesen(p):
    with wave.open(p, "rb") as w:
        sr, n = w.getframerate(), w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype("float32") / 32768
    if n > 1:
        x = x.reshape(-1, n).mean(1)
    if sr != SR:
        x = np.interp(np.arange(0, len(x), sr / SR), np.arange(len(x)), x).astype("float32")
    return x


def _woerter(segs):
    from pipeline.s525_wortbruecke import lautwoerter
    woerter, zu = [], []
    for j, g in enumerate(segs):
        for lw in lautwoerter(g["t"]):
            woerter.append(lw["w"]); zu.append(j)
    return woerter, zu


def _grenzen(zeit, zu, n_samples, nseg):
    """Schnittgrenzen je Segment in Samples, aus Wortzeiten (Sekunden)."""
    ab = []
    for j in range(nseg):
        z = [zeit[i] for i in range(len(zeit)) if zu[i] == j and zeit[i]]
        ab.append((min(a for a, _ in z), max(b for _, b in z)) if z else None)
    out = []
    for j, z in enumerate(ab):
        if z is None:
            out.append(None); continue
        vor = next((ab[i] for i in range(j - 1, -1, -1) if ab[i]), None)
        nach = next((ab[i] for i in range(j + 1, len(ab)) if ab[i]), None)
        a = 0.0 if vor is None else (vor[1] + z[0]) / 2
        b = n_samples / SR if nach is None else (z[1] + nach[0]) / 2
        out.append((int(a * SR), min(n_samples, int(b * SR))))
    return out


def montage(ze, za, zu, pe, pa, segs):
    """Setzt Erzaehler-Stuecke (aus pe, Zeiten ze) und Figurenstuecke (aus pa, Zeiten za) zusammen.
    Gibt (audio|None, protokoll) zurueck; None = kein sauberer Schnitt."""
    xe, xa = lesen(pe), lesen(pa)
    ge = _grenzen(ze, zu, len(xe), len(segs))
    ga = _grenzen(za, zu, len(xa), len(segs))
    teile, prot = [], []
    for k, g in enumerate(segs):
        x, gg, q = (xe, ge[k], "erz") if g["s"] == "Erzaehler" else (xa, ga[k], "alt")
        if gg is None or gg[1] - gg[0] < SR * 0.15:
            return None, f"#{k} kein Schnitt"
        y = x[gg[0]:gg[1]].copy()
        kk = min(len(y) // 2, int(SR * 0.012))
        r = np.linspace(0, 1, kk, dtype="float32"); y[:kk] *= r; y[-kk:] *= r[::-1]
        teile.append(y); prot.append(f"#{k}{q}")
    # Lautheit: Erzaehler-Stuecke an die Figurenstuecke angleichen (RMS je Quelle)
    rms = lambda v: float(np.sqrt(np.mean(v ** 2))) + 1e-6
    ref = rms(xa)
    y = np.concatenate([t * (ref / rms(xe)) if p.endswith("erz") else t for t, p in zip(teile, prot)])
    return y, " ".join(prot)


def _zeiten_cpu(jobs):
    from pipeline.s520_wortzeiten import _Aligner
    AL = _Aligner()
    return {key: (AL.ausrichten(pe, W), AL.ausrichten(q, W)) for key, pe, q, W in jobs}


def _zeiten_modal(jobs, book, lg):
    from gpu_fa.schnitt_modal import app, vol, zeiten
    stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    prefix = f"s510/{book}/{lg}/{stamp}"
    arbeit = []
    with app.run():
        with vol.batch_upload(force=True) as b:
            for key, pe, q, W in jobs:
                b.put_file(pe, f"/{prefix}/{key}_erz.wav")
                b.put_file(q, f"/{prefix}/{key}_alt.wav")
                arbeit.append({"key": key, "erz": f"/{prefix}/{key}_erz.wav",
                               "alt": f"/{prefix}/{key}_alt.wav", "woerter": W})
        chunks = [arbeit[i:i + 40] for i in range(0, len(arbeit), 40)]
        out = {}
        for res in zeiten.map(chunks):
            out.update(res)
    return out


def _lauf(book, lg, chapter=None, liste=False):
    p = _pfade(book)
    A = auswahl(book, lg, chapter)
    prod_adir = os.path.join(config.book_dir(book), "fassungen", lg, "audio")
    edir = os.path.join(p["work"], "_hybrid", lg, "erz")
    sek = 0.0
    for t in A:
        f = os.path.join(prod_adir, f"{t}.wav")
        if os.path.exists(f):
            with wave.open(f) as w:
                sek += w.getnframes() / w.getframerate()
    offen = [t for t in A if not os.path.exists(os.path.join(edir, f"{t}.wav"))]
    voice = json.load(open(os.path.join(config.work_dir(book), "casting.json"), encoding="utf-8"))["plan"]["erzaehler"]["id"]
    model = config.MODELS.get("tts", "gemini-3.8-flash-tts")
    usd = sek * len(offen) / max(1, len(A)) * 25 / 1e6 * config.PREISE[model]["out"]
    print(f"[510] {book} [{lg}] Kapitel {chapter or 'alle'}: {len(A)} gemischte Saetze, {sek / 60:.1f} min Audio; "
          f"Takes offen {len(offen)} -> ~{usd:.2f} $ (Schaetzung Gemini)", flush=True)
    if liste:
        return
    adir = _audio_dir(book, lg, p, chapter)

    # --- 1. Takes (Gemini) -------------------------------------------------
    texte = {t: " ".join(g["t"].strip() for g in A[t]) for t in offen}
    policy, t0 = [], time.time()
    with cf.ThreadPoolExecutor(getattr(config, "TTS_PARALLEL", 8)) as ex:
        fu = {ex.submit(_take, texte[t], voice, lg, os.path.join(edir, f"{t}.wav")): t for t in offen}
        for i, f in enumerate(cf.as_completed(fu), 1):
            t = fu[f]
            try:
                f.result()
            except PolicyError as e:
                policy.append(t); print(f"  policy {t}: {e}", flush=True)
            except Exception as e:
                for g in fu:
                    g.cancel()
                raise RuntimeError(f"[510] gestoppt bei {t}: {e}") from e
            if i % 25 == 0 or i == len(offen):
                print(f"  Takes {i}/{len(offen)} ({time.time() - t0:.0f} s)", flush=True)

    # --- 2. Sicherung und Wiederaufnahme -----------------------------------
    heute = datetime.date.today().strftime("%Y%m%d")
    sich_root = os.path.join(p["bd"], "fassungen", lg)
    da = sorted(d for d in os.listdir(sich_root) if d.startswith("audio_alt_") and d.endswith("_hybrid"))
    sich = os.path.join(sich_root, da[0] if da else f"audio_alt_{heute}_hybrid")
    os.makedirs(sich, exist_ok=True)
    gp = os.path.join(p["work"], "_hybrid", lg, "fertig.txt")
    erledigt = set(open(gp, encoding="utf-8").read().split()) if os.path.exists(gp) else set()
    for t in A:   # Altlauf ohne fertig.txt: Satz gilt als fertig, wenn er sich von seiner Sicherung unterscheidet
        q, pa = os.path.join(sich, f"{t}.wav"), os.path.join(adir, f"{t}.wav")
        if os.path.exists(q) and os.path.exists(pa) and os.path.getsize(q) != os.path.getsize(pa):
            erledigt.add(t)

    # --- 3. Schnittzeiten (Modal, CPU-Rueckfall) --------------------------
    jobs, bereit = [], {}
    for t, segs in A.items():
        if t in erledigt or t in policy:
            continue
        pe, pa = os.path.join(edir, f"{t}.wav"), os.path.join(adir, f"{t}.wav")
        if not (os.path.exists(pe) and os.path.exists(pa)):
            continue
        q = os.path.join(sich, f"{t}.wav")
        if not os.path.exists(q):
            shutil.copy2(pa, q)
        W, zu = _woerter(segs)
        bereit[t] = zu
        jobs.append((t, pe, q, W))
    zeit = {}
    if jobs:
        print(f"[510] Montage: {len(erledigt)} fertig, {len(jobs)} zu schneiden; Sicherung {sich}", flush=True)
        if getattr(config, "HYBRID_SCHNITT", "modal") == "modal":
            try:
                zeit = _zeiten_modal(jobs, book, lg)
                print(f"[510] Schnittzeiten auf Modal: {len(zeit)} Saetze", flush=True)
            except Exception as e:
                print(f"[510] Modal nicht nutzbar -> CPU-Rueckfall: {str(e)[:200]}", flush=True)
        if not zeit:
            zeit = _zeiten_cpu(jobs)
            print(f"[510] Schnittzeiten auf CPU: {len(zeit)} Saetze", flush=True)

    # --- 4. Montage --------------------------------------------------------
    fg = open(gp, "a", encoding="utf-8")
    prot, fertig, alt = {}, [], []
    for t in A:
        if t in erledigt:
            fertig.append(t); continue
        if t in policy:
            alt.append(t); prot[t] = "policy: Satz bleibt unveraendert"; continue
        if t not in zeit:
            alt.append(t); prot[t] = "fehlt"; continue
        pe, q = os.path.join(edir, f"{t}.wav"), os.path.join(sich, f"{t}.wav")
        pa = os.path.join(adir, f"{t}.wav")
        ze, za = zeit[t]
        # Fehler hier stoppen die Batch (kein stilles Weiterlaufen)
        y, pr = montage(ze, za, bereit[t], pe, q, A[t])   # immer aus der Sicherung = Erstlauf
        prot[t] = pr
        if y is None:
            alt.append(t); continue
        with wave.open(pa + ".tmp", "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())
        os.replace(pa + ".tmp", pa)
        fertig.append(t); fg.write(t + "\n"); fg.flush()
        if len(fertig) % 25 == 0:
            print(f"  Montage {len(fertig)}/{len(A)}", flush=True)
    fg.close()

    # --- 5. Wortzeiten zuruecksetzen (520 misst neu), nur Produktion ------
    if not p["test"]:
        from config import config as cfg
        wp = cfg.work_path(book, f"520_wortzeiten_{lg}")
        if os.path.exists(wp) and fertig:
            shutil.copy2(wp, wp + f".bak_hybrid_{heute}")
            w = json.load(open(wp, encoding="utf-8"))
            for t in fertig:
                w.get("tags", {}).pop(t, None)
            json.dump(w, open(wp, "w", encoding="utf-8"), ensure_ascii=False)

    os.makedirs(p["work"], exist_ok=True)
    json.dump({"datum": heute, "modell": model, "eingebaut": len(fertig), "policy": policy,
               "alt_gelassen": alt, "protokoll": prot, "sicherung": os.path.relpath(sich, p["bd"])},
              open(os.path.join(p["work"], f"hybrid_{lg}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[510] {book} [{lg}] fertig: eingebaut {len(fertig)}, Policy {len(policy)}, alt {len(alt)}", flush=True)


def run(book_id, chapter=None, lang=None, force=False, liste=False, **_):
    if not force and book_id not in getattr(config, "HYBRID_WERKE", []):
        print(f"[510] {book_id}: nicht in HYBRID_WERKE - uebersprungen", flush=True)
        return
    for lg in ([lang] if lang else ["de", "en"]):
        _lauf(book_id, lg, chapter, liste)
