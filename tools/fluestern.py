"""READ LAYER — Fluestern per Audiotrick (23.10.2026, v2): WORLD-Vocoder.
v2 (CK: Hauchlaute zu tief, klingt nach Roboter): Synthese mit f0=0 (reines Rauschen, kein Takt des alten Grundtons),
Formanten leicht nach oben (Fluestern hebt F1/F2), steilerer Hochpass, Hoehenanhebung ab 2 kHz.
Aufruf: python tools/fluestern.py <ein.wav> <aus.wav> [--formant 1.08] [--hochpass 700] [--hoehen 7] [--pegel -10] [--hauch 1.0]
STANDARD (CK 23.10. 12:27): Variante 6_v2_formant108_hell, 4 dB leiser.
  --formant  Faktor Formantverschiebung (1.0 = keine)   --hoehen dB Anhebung ab 2 kHz
  --hauch    1.0 = reines Fluestern; <1 = Hauchstimme (Restgrundton bleibt)
"""
import sys
import numpy as np, soundfile as sf, pyworld as pw
from scipy.signal import butter, sosfilt


def _formant(sp, faktor):
    if abs(faktor - 1) < 1e-3:
        return sp
    n = sp.shape[1]
    quelle = np.clip(np.arange(n) / faktor, 0, n - 1)   # Huellkurve nach oben strecken
    return np.stack([np.interp(quelle, np.arange(n), z) for z in sp])


def fluestern(x, sr, formant=1.08, hochpass=700, hoehen=7.0, pegel=-10, hauch=1.0):
    x = x.astype(np.float64)
    f0, t = pw.harvest(x, sr, f0_floor=60, f0_ceil=500)
    sp = _formant(pw.cheaptrick(x, f0, t, sr), formant)
    if hauch >= 0.999:
        y = pw.synthesize(np.zeros_like(f0), sp, np.ones_like(sp), sr)   # rein stimmlos
    else:
        ap = np.clip(pw.d4c(x, f0, t, sr) * (1 - hauch) + hauch, 0, 1)
        y = pw.synthesize(f0, sp, ap, sr)
    y = sosfilt(butter(4, hochpass, "highpass", fs=sr, output="sos"), y)
    if hoehen:
        hp = sosfilt(butter(2, 2000, "highpass", fs=sr, output="sos"), y)
        y = y + (10 ** (hoehen / 20) - 1) * hp
    r0, r1 = np.sqrt(np.mean(x ** 2)) + 1e-9, np.sqrt(np.mean(y ** 2)) + 1e-9
    return np.clip(y * (r0 / r1) * 10 ** (pegel / 20), -1, 1).astype(np.float32)


if __name__ == "__main__":
    a = sys.argv[1:]
    o = lambda k, d: float(a[a.index(k) + 1]) if k in a else d
    x, sr = sf.read(a[0])
    if x.ndim > 1:
        x = x.mean(axis=1)
    sf.write(a[1], fluestern(x, sr, o("--formant", 1.08), o("--hochpass", 700), o("--hoehen", 7.0),
                             o("--pegel", -10), o("--hauch", 1.0)), sr)
    print("[fluestern]", a[1])
