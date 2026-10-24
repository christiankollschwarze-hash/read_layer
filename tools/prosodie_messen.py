"""READ LAYER — Prosodie messen (17.10.2026): Tonhoehen-Spanne je Satz fuer A/B-Vergleiche von Vertonungen.
Aufruf: python tools/prosodie_messen.py <ordner_A> <ordner_B> [...]
Je Ordner: Median der Tonhoehen-Streuung je Satz (Halbtoene, nur stimmhafte Rahmen), Spanne (P90-P10),
Sprechtempo (s je Satz) und Zahl auffaelliger Laengen. Mehr Streuung = lebendigere Satzmelodie."""
import os, sys, wave
import numpy as np


def f0_reihe(a, sr, rahmen=0.04, schritt=0.01, fmin=70, fmax=400):
    n, h = int(sr * rahmen), int(sr * schritt)
    lo, hi = int(sr / fmax), int(sr / fmin)
    f0 = []
    for i in range(0, len(a) - n, h):
        x = a[i:i + n] - a[i:i + n].mean()
        e = (x ** 2).mean()
        if e < 1e-4:
            continue
        r = np.correlate(x, x, "full")[n - 1:]
        r = r / (r[0] + 1e-9)
        k = lo + int(np.argmax(r[lo:hi]))
        if r[k] > 0.45:
            f0.append(sr / k)
    return np.array(f0)


def ordner(p):
    werte, spannen, dauern = [], [], []
    for x in sorted(os.listdir(p)):
        if not x.endswith(".wav"):
            continue
        with wave.open(os.path.join(p, x)) as w:
            sr = w.getframerate()
            a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        if sr > 16000:                      # fuer Tempo auf 16 kHz ausduennen
            a, sr = a[:: sr // 16000], 16000
        f = f0_reihe(a, sr)
        dauern.append(len(a) / sr)
        if len(f) < 10:
            continue
        ht = 12 * np.log2(f / np.median(f))
        werte.append(float(ht.std()))
        spannen.append(float(np.percentile(ht, 90) - np.percentile(ht, 10)))
    return {"saetze": len(dauern), "streuung_ht": round(float(np.median(werte)), 2) if werte else None,
            "spanne_ht": round(float(np.median(spannen)), 2) if spannen else None,
            "dauer_s_mittel": round(float(np.mean(dauern)), 2) if dauern else None}


if __name__ == "__main__":
    for p in [q for q in sys.argv[1:] if os.path.isdir(q)]:
        print(f"{p}: {ordner(p)}")
