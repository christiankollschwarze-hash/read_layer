"""READ LAYER — Satzraender schneiden (Stoergeraeusche zwischen den Saetzen entfernen), 17.10.2026.
Schneidet jede Satz-WAV auf ihren Sprachanteil: erster Wortanfang - VOR bis letztes Wortende + NACH
(Wortzeiten aus Stage 58c), mit kurzer Ein-/Ausblendung. Pausen zwischen Saetzen setzt danach der Player (Stage 56).
Originale einmalig nach fassungen/<lg>/audio_ungeschnitten/.

Aufruf: python tools/raender_schneiden.py <book_id> <lg> [--vor 0.05] [--nach 0.12]
Danach Stage 58c erneut (Wortzeiten passen sonst nicht mehr).
"""
import json, os, shutil, sys, wave
import numpy as np

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HIER)
from config import config


def opt(name, d):
    return float(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else d


def main(book, lg):
    VOR, NACH = opt("--vor", 0.05), opt("--nach", 0.12)
    werk = config.book_dir(book)
    audio = os.path.join(werk, "fassungen", lg, "audio")
    roh = os.path.join(werk, "fassungen", lg, "audio_ungeschnitten")
    wt = json.load(open(os.path.join(werk, "work", f"520_wortzeiten_{lg}.json"), encoding="utf-8"))["tags"]
    os.makedirs(roh, exist_ok=True)
    n = ohne = 0
    weg_s = 0.0
    for name in sorted(f for f in os.listdir(audio) if f.endswith(".wav")):
        tag = name[:-4]
        w = wt.get(tag) or []
        if not w:
            ohne += 1
            continue
        q = os.path.join(roh, name)
        if not os.path.exists(q):
            shutil.copy2(os.path.join(audio, name), q)
        with wave.open(q) as f:
            p = f.getparams()
            x = np.frombuffer(f.readframes(p.nframes), dtype=np.int16).astype(np.float32)
        sr = p.framerate
        a = max(0, int((min(e["t0"] for e in w) - VOR) * sr))
        b = min(len(x), int((max(e["t1"] for e in w) + NACH) * sr))
        if b - a < int(0.1 * sr):
            ohne += 1
            continue
        y = x[a:b].copy()
        fi, fo = int(0.01 * sr), int(0.03 * sr)
        y[:fi] *= np.linspace(0, 1, fi)
        y[-fo:] *= np.linspace(1, 0, fo)
        weg_s += (len(x) - len(y)) / sr
        with wave.open(os.path.join(audio, name), "wb") as f:
            f.setparams(p)
            f.writeframes(np.clip(y, -32768, 32767).astype(np.int16).tobytes())
        n += 1
    open(os.path.join(roh, "SCHNITT.txt"), "w").write(f"audio/ = audio_ungeschnitten/ geschnitten: Wortanfang-{VOR}s bis Wortende+{NACH}s\n")
    print(f"[raender] {book} {lg}: {n} geschnitten, {ohne} ohne Wortzeiten unveraendert, {weg_s/60:.1f} min Rand entfernt")


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--") and not x.replace(".", "").isdigit()]
    main(a[0], a[1])
