"""READ LAYER - AP 61 (28.10.2026): Hoerspiel-Hybrid ins Werk einbauen (Variante C aus AP 60, CK-abgenommen).
Je Satz mit Erzaehler + Figur (sprecher.json): Erzaehler-Take = ganzer Satz mit Erzaehlerstimme (Gemini, Sprachfeld gesetzt),
Einschuebe ("sagte Alice") aus diesem Take, Figurenrede aus der bestehenden Fassung (Erstlauf); Schnitt per MMS_FA (CPU).
Reine Figuren- und reine Erzaehlsaetze bleiben unveraendert.

Aufruf:
  py -3.11 tools/hybrid_einbau.py <werk> <lg> --liste    Auswahl + Kostenschaetzung (kostenlos)
  py -3.11 tools/hybrid_einbau.py <werk> <lg> --takes    nur Erzaehler-Takes erzeugen (Gemini, wiederaufnehmbar)
  py -3.11 tools/hybrid_einbau.py <werk> <lg> --los      Takes (fehlende) + Montage + Einbau in fassungen/<lg>/audio
--los sichert jedes alte WAV nach fassungen/<lg>/audio_alt_<datum>_hybrid/, nimmt die Saetze aus den Wortzeiten
(58c misst neu), schreibt work/hybrid_<lg>.json (Schnittprotokoll). Satz ohne sauberen Schnitt bleibt alt.
"""
import base64, concurrent.futures as cf, datetime, json, os, shutil, sys, time, wave
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from config import config  # noqa: E402
import requests  # noqa: E402

SR = 24000
LANG = {"en": "en-GB", "de": "de-DE"}
URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
MODELL = config.MODELS.get("tts", "gemini-3.8-flash-tts")
STIL = {"de": "German audiobook narration. Speak German only, with native German pronunciation and melody; never switch to English.",
        "en": "English audiobook narration. Speak British English only, with native English pronunciation."}


def auswahl(book, lg):
    spr = json.load(open(os.path.join(config.work_dir(book), "sprecher.json"), encoding="utf-8"))
    A = {}
    for t, v in spr.items():
        segs = [g for g in v.get(lg, []) if g["t"].strip()]
        s = {g["s"] for g in segs}
        if "Erzaehler" in s and len(s) > 1:
            A[t] = segs
    return dict(sorted(A.items()))


def take(text, voice, lg, ziel):
    pl = {"model": MODELL,
          "input": [{"type": "user_input", "content": [{"type": "text", "text": text,
                     "annotations": [{"type": "speech_metadata", "style": STIL[lg]}]}]}],
          "response_format": {"type": "audio", "mime_type": "audio/l16", "sample_rate": SR},
          "generation_config": {"speech_config": [{"voice": voice, "language": LANG[lg]}]}}
    for v in range(6):
        r = requests.post(URL, headers={"x-goog-api-key": config.GEMINI_API_KEY}, json=pl, timeout=300)
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(10 * (v + 1)); continue
        if r.status_code >= 400:
            raise RuntimeError(f"{r.status_code}: {r.text[:200]}")
        b = _audio(r.json())
        if not b:
            time.sleep(2); continue
        pcm = base64.b64decode(b)
        if pcm[:4] == b"RIFF":
            pcm = pcm[pcm.find(b"data") + 8:]
        os.makedirs(os.path.dirname(ziel), exist_ok=True)
        with wave.open(ziel + ".tmp", "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm)
        os.replace(ziel + ".tmp", ziel)
        return len(pcm) / 2 / SR
    raise RuntimeError("kein Audio")


def _audio(o):
    if isinstance(o, dict):
        if o.get("type") == "audio" and isinstance(o.get("data"), str):
            return o["data"]
        o = list(o.values())
    if isinstance(o, list):
        for v in o:
            x = _audio(v)
            if x:
                return x
    return None


def lesen(p):
    with wave.open(p, "rb") as w:
        sr, n = w.getframerate(), w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype("float32") / 32768
    if n > 1:
        x = x.reshape(-1, n).mean(1)
    if sr != SR:
        x = np.interp(np.arange(0, len(x), sr / SR), np.arange(len(x)), x).astype("float32")
    return x


def montage(AL, lautwoerter, pe, pa, segs):
    def grenzen(p, n):
        woerter, zu = [], []
        for j, g in enumerate(segs):
            for lw in lautwoerter(g["t"]):
                woerter.append(lw["w"]); zu.append(j)
        zeit = AL.ausrichten(p, woerter)
        ab = []
        for j in range(len(segs)):
            z = [zeit[i] for i in range(len(woerter)) if zu[i] == j and zeit[i]]
            ab.append((min(a for a, _ in z), max(b for _, b in z)) if z else None)
        out = []
        for j, z in enumerate(ab):
            if z is None:
                out.append(None); continue
            vor = next((ab[i] for i in range(j - 1, -1, -1) if ab[i]), None)
            nach = next((ab[i] for i in range(j + 1, len(ab)) if ab[i]), None)
            a = 0.0 if vor is None else (vor[1] + z[0]) / 2
            b = n / SR if nach is None else (z[1] + nach[0]) / 2
            out.append((int(a * SR), min(n, int(b * SR))))
        return out
    xe, xa = lesen(pe), lesen(pa)
    ge, ga = grenzen(pe, len(xe)), grenzen(pa, len(xa))
    teile, prot = [], []
    for k, g in enumerate(segs):
        x, gg, q = (xe, ge[k], "erz") if g["s"] == "Erzaehler" else (xa, ga[k], "alt")
        if gg is None or gg[1] - gg[0] < SR * 0.15:
            return None, f"#{k} kein Schnitt"
        y = x[gg[0]:gg[1]].copy()
        kk = min(len(y) // 2, int(SR * 0.012))
        r = np.linspace(0, 1, kk, dtype="float32"); y[:kk] *= r; y[-kk:] *= r[::-1]
        teile.append(y); prot.append(f"#{k}{q}")
    # Lautheit: Erzaehler-Stuecke an die Figurenstuecke der alten Fassung angleichen (RMS je Quelle)
    rms = lambda v: float(np.sqrt(np.mean(v ** 2))) + 1e-6
    ref = rms(xa)
    y = np.concatenate([t * (ref / rms(xe)) if p.endswith("erz") else t for t, p in zip(teile, prot)])
    return y, " ".join(prot)


def main(book, lg, modus):
    A = auswahl(book, lg)
    bd = config.book_dir(book)
    adir = os.path.join(bd, "fassungen", lg, "audio")
    edir = os.path.join(config.work_dir(book), "_hybrid", lg, "erz")
    sek = 0.0
    for t in A:
        p = os.path.join(adir, f"{t}.wav")
        if os.path.exists(p):
            with wave.open(p) as w:
                sek += w.getnframes() / w.getframerate()
    offen = [t for t in A if not os.path.exists(os.path.join(edir, f"{t}.wav"))]
    usd = sek * len(offen) / max(1, len(A)) * 25 / 1e6 * config.PREISE[MODELL]["out"]
    print(f"[hybrid] {book} [{lg}]: {len(A)} gemischte Saetze, {sek / 60:.0f} min Audio; Takes offen {len(offen)} -> ~{usd:.2f} $")
    if modus == "liste":
        return
    cast = json.load(open(os.path.join(config.work_dir(book), "casting.json"), encoding="utf-8"))["plan"]
    voice = cast["erzaehler"]["id"]
    texte = {t: " ".join(g["t"].strip() for g in A[t]) for t in offen}
    fehler = []
    t0 = time.time()
    with cf.ThreadPoolExecutor(getattr(config, "TTS_PARALLEL", 8)) as ex:
        fu = {ex.submit(take, texte[t], voice, lg, os.path.join(edir, f"{t}.wav")): t for t in offen}
        for i, f in enumerate(cf.as_completed(fu), 1):
            try:
                f.result()
            except Exception as e:
                fehler.append(fu[f]); print("  Fehler", fu[f], str(e)[:120])
            if i % 50 == 0:
                print(f"  Takes {i}/{len(offen)}", flush=True)
    print(f"[hybrid] Takes fertig ({time.time() - t0:.0f} s), Fehler {len(fehler)}")
    if modus == "takes":
        return
    from pipeline.s520_wortzeiten import _Aligner
    from pipeline.s525_wortbruecke import lautwoerter
    AL = _Aligner()
    heute = datetime.date.today().strftime("%Y%m%d")
    # Wiederaufnahme: vorhandene Hybrid-Sicherung weiterverwenden (Erstlauf), sonst neu mit Datum
    da = sorted(d for d in os.listdir(os.path.join(bd, "fassungen", lg)) if d.startswith("audio_alt_") and d.endswith("_hybrid"))
    sich = os.path.join(bd, "fassungen", lg, da[0] if da else f"audio_alt_{heute}_hybrid")
    os.makedirs(sich, exist_ok=True)
    gp = os.path.join(config.work_dir(book), "_hybrid", lg, "fertig.txt")
    erledigt = set(open(gp, encoding="utf-8").read().split()) if os.path.exists(gp) else set()
    for t in A:   # Altlauf ohne fertig.txt: Satz gilt als fertig, wenn er sich von seiner Sicherung unterscheidet
        q, pa = os.path.join(sich, f"{t}.wav"), os.path.join(adir, f"{t}.wav")
        if os.path.exists(q) and os.path.exists(pa) and os.path.getsize(q) != os.path.getsize(pa):
            erledigt.add(t)
    print(f"[hybrid] Montage: {len(erledigt)} schon fertig, {len(A) - len(erledigt)} offen; Sicherung {sich}", flush=True)
    fg = open(gp, "a", encoding="utf-8")
    prot, fertig, alt = {}, [], []
    for i, (t, segs) in enumerate(A.items(), 1):
        if t in erledigt:
            fertig.append(t); continue
        pe, pa = os.path.join(edir, f"{t}.wav"), os.path.join(adir, f"{t}.wav")
        if not (os.path.exists(pe) and os.path.exists(pa)):
            alt.append(t); prot[t] = "fehlt"; continue
        q = os.path.join(sich, f"{t}.wav")
        if not os.path.exists(q):
            shutil.copy2(pa, q)
        try:
            y, p = montage(AL, lautwoerter, pe, q, segs)   # immer aus der Sicherung = Erstlauf
        except Exception as e:
            y, p = None, f"Fehler {str(e)[:80]}"
        prot[t] = p
        if y is None:
            alt.append(t); continue
        with wave.open(pa + ".tmp", "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())
        os.replace(pa + ".tmp", pa)
        fertig.append(t); fg.write(t + "\n"); fg.flush()
        if i % 25 == 0:
            print(f"  Montage {i}/{len(A)}", flush=True)
    fg.close()
    wp = config.work_path(book, f"520_wortzeiten_{lg}")
    if os.path.exists(wp) and fertig:
        shutil.copy2(wp, wp + f".bak_hybrid_{heute}")
        w = json.load(open(wp, encoding="utf-8"))
        for t in fertig:
            w.get("tags", {}).pop(t, None)
        json.dump(w, open(wp, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump({"datum": heute, "modell": MODELL, "eingebaut": len(fertig), "alt_gelassen": alt, "protokoll": prot,
               "sicherung": os.path.relpath(sich, bd)}, open(os.path.join(config.work_dir(book), f"hybrid_{lg}.json"), "w",
              encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[hybrid] eingebaut {len(fertig)}, alt gelassen {len(alt)}; Sicherung {sich}")


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    m = next((x[2:] for x in sys.argv[1:] if x in ("--liste", "--takes", "--los")), "liste")
    if len(a) < 2:
        sys.exit(__doc__)
    main(a[0], a[1], m)
