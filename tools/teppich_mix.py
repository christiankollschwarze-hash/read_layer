"""Klangteppich unter ein Hoerspiel legen: Naehe-Huellkurve (Pegel, Tiefpass, Hall, Breite),
'innen'-Filter, Ducking aus den bekannten Zeilen-Zeitstempeln. Sprachspur bleibt unveraendert.
Aufruf: python teppich_mix.py <skript.json> <zeilen_dir> <regie.json> <teppich.wav> <ausgabe_prefix>
"""
import sys, json, os, numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfiltfilt, sosfilt, resample_poly, fftconvolve

SR = 44100
PAUSE_SAME, PAUSE_CHANGE = 0.30, 0.45   # wie hoerspiel_test.py

def db(x): return 10 ** (x / 20)
def rms(x): return float(np.sqrt(np.mean(x ** 2)) + 1e-12)

skript, zdir, regie_p, bed_p, out = sys.argv[1:6]
data = json.load(open(skript, encoding="utf-8"))
regie = json.load(open(regie_p, encoding="utf-8"))
zeilen = data["zeilen"]

# ---- Sprachspur exakt wie hoerspiel_test.py, Zeitstempel mitschreiben
pre = regie.get("vorlauf_s", 2.0)
voice_parts, stamps, t, prev = [], [], pre, None
voice_parts.append(np.zeros(int(pre * SR)))
for i, (sp, text, _) in enumerate(zeilen, 1):
    sr, y = wavfile.read(os.path.join(zdir, f"{i:03d}_{sp}.wav"))
    y = y.astype(np.float64) / 32768
    y = resample_poly(y, 147, 80) if sr == 24000 else y
    if prev is not None:
        p = PAUSE_SAME if sp == prev else PAUSE_CHANGE
        voice_parts.append(np.zeros(int(p * SR))); t += int(p * SR) / SR
    stamps.append({"zeile": i, "sprecher": sp, "start": round(t, 3), "ende": round(t + len(y) / SR, 3)})
    voice_parts.append(y); t += len(y) / SR; prev = sp
post = regie.get("nachlauf_s", 3.0)
voice_parts.append(np.zeros(int(post * SR)))
voice = np.concatenate(voice_parts); N = len(voice)

# ---- Teppich laden, ausgleichen, loopen
sr, b = wavfile.read(bed_p)
b = b.astype(np.float64) / 32768
if b.ndim == 1: b = np.stack([b, b], 1)
if sr != SR: b = resample_poly(b, SR, sr, axis=0)
# Ende (Ausklang) abschneiden, wo es leise wird
blk = SR // 2
lv = np.array([rms(b[k:k + blk]) for k in range(0, len(b) - blk, blk)])
good = np.where(lv > db(-50))[0]
b = b[: (good[-1] + 1) * blk]
# langsamer Pegelausgleich (Fenster 3 s) -> gleichmaessiger Teppich
w = int(SR * 3)
env = np.sqrt(np.convolve((b ** 2).mean(1), np.ones(w) / w, mode="same")) + 1e-6
target = np.median(env)
g = np.clip(target / env, db(-6), db(6))
b = b * g[:, None]
# Loop mit 4-s-Kreuzblende
xf = int(SR * 4)
loop = b.copy()
while len(loop) < N:
    fade = np.linspace(0, 1, xf)[:, None]
    head = b[:xf] * np.sqrt(fade); tail = loop[-xf:] * np.sqrt(1 - fade)
    loop = np.concatenate([loop[:-xf], head + tail, b[xf:]])
bed = loop[:N].astype(np.float32); del loop, b
bed /= rms(bed)

# ---- drei Klangfassungen
def lp(x, f, order=4): return sosfiltfilt(butter(order, f, "low", fs=SR, output="sos"), x, axis=0)
near = bed
mid = (bed[:, 0] + bed[:, 1]) / 2
far_dry = lp(np.stack([0.75 * mid + 0.25 * bed[:, 0], 0.75 * mid + 0.25 * bed[:, 1]], 1), 1800)
rng = np.random.default_rng(1)
L = int(SR * 1.6); ir = rng.standard_normal((L, 2)) * np.exp(-np.arange(L) / (SR * 0.35))[:, None]
ir /= np.sqrt((ir ** 2).sum(0))
far_wet = np.stack([fftconvolve(far_dry[:, c], ir[:, c])[:N] for c in range(2)], 1)
far = (0.55 * far_dry + 0.45 * far_wet).astype(np.float32); del far_dry, far_wet
inside = lp(mid, 450, 6).astype(np.float32); inside = np.stack([inside, inside], 1); del mid
for x in (far, inside): x /= rms(x)

# ---- Huellkurven aus Regiepunkten
def anchor_time(p):
    s = stamps[p["zeile"] - 1]; text = zeilen[p["zeile"] - 1][1]
    f = p["bei"]
    if isinstance(f, str):
        k = text.find(f)
        if k < 0: raise SystemExit(f"Ankertext nicht gefunden: Zeile {p['zeile']}: {f}")
        f = k / len(text)
    return s["start"] + f * (s["ende"] - s["start"])
pts = sorted((anchor_time(p), p["naehe"], p.get("innen", 0)) for p in regie["punkte"])
tt = np.arange(N) / SR
pt_t = [0.0] + [p[0] for p in pts] + [N / SR]
nahe = np.interp(tt, pt_t, [pts[0][1]] + [p[1] for p in pts] + [pts[-1][1]])
innen = np.interp(tt, pt_t, [pts[0][2]] + [p[2] for p in pts] + [pts[-1][2]])

# Pegel relativ zur Stimme: nah -12 dB, weit -23 dB unter Stimm-RMS; 0 -> stumm
vr = rms(np.concatenate([v for v in voice_parts if len(v) and np.any(v)]))
gain_db = -23 + 11 * nahe
gain = db(gain_db) * vr * np.clip(nahe / 0.08, 0, 1)        # unter 0.08 ausblenden
wn, wf = np.sqrt(nahe), np.sqrt(1 - nahe)
outside = near * wn[:, None] + far * wf[:, None]
mixbed = outside.astype(np.float32) * np.sqrt(1 - innen)[:, None] + inside * db(2) * np.sqrt(innen)[:, None]

# Ducking aus Zeitstempeln (-6 dB, 150 ms Anlauf, 500 ms Ausklang)
duck = np.zeros(N)
for s in stamps:
    duck[int(s["start"] * SR):int(s["ende"] * SR)] = 1
k_a, k_r = int(SR * 0.15), int(SR * 0.5)
d = np.convolve(duck, np.ones(k_a) / k_a, mode="same")
d = np.maximum(d, np.convolve(duck, np.ones(k_r) / k_r, mode="full")[:N])
d = np.clip(d, 0, 1)
duckg = db(-6 * d)
# Ein-/Ausblenden am Rand
fi = np.clip(tt / 2.0, 0, 1); fo = np.clip((N / SR - tt) / 2.5, 0, 1)
bedfinal = mixbed * (gain * duckg * fi * fo).astype(np.float32)[:, None]; del mixbed, outside, near, far, inside

mix = np.stack([voice, voice], 1) + bedfinal
peak = np.abs(mix).max(); mix *= db(-1) / peak
voice_only = np.stack([voice, voice], 1) * db(-1) / peak

def save(path, x): wavfile.write(path, SR, (np.clip(x, -1, 1) * 32767).astype(np.int16))
save(out + "_mit_teppich.wav", mix)
save(out + "_teppich_spur.wav", bedfinal * db(-1) / peak)
json.dump({"sample_rate": SR, "vorlauf_s": pre, "zeilen": stamps}, open(out + "_zeitstempel.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"Dauer {N/SR/60:.2f} min, Stimme-RMS {20*np.log10(vr):.1f} dBFS")
for p in pts: print(f"  {p[0]:7.1f}s naehe={p[1]:.2f} innen={p[2]}")
