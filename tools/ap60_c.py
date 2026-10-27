"""READ LAYER - AP 60 Variante C (27.10.2026): Hybrid-Hoerprobe, 0 $ (lokal, CPU, keine API).
Erzaehlerspur = tests/ap60/<lg>/B_basis/<tid>.wav (ganzer Satz, Erzaehlerstimme),
Figurenrede   = Rede-Segmente aus der Referenz tests/ap60/<lg>/ref/<tid>.wav (Erstlauf, Segment einzeln vertont).
Schnitt je Satz-ID + Segmentindex per MMS_FA (pipeline.s520_wortzeiten._Aligner, CPU), Grenze = Mitte der Luecke.
Ausgabe: tests/ap60/ergebnis/<lg>_C_hybrid.wav (Pause 0,6 s, Lautheit -18 LUFS wie A/B/Referenz).
Aufruf: py -3.11 tools/ap60_c.py
"""
import json, os, sys, wave
from pathlib import Path
import numpy as np

LESER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LESER))
from pipeline.s520_wortzeiten import _Aligner  # noqa: E402
from pipeline.s525_wortbruecke import lautwoerter  # noqa: E402

T = LESER / "tests/ap60"
SR, PAUSE_S, LUFS = 24000, 0.6, -18.0
P = json.loads((T / "passage.json").read_text(encoding="utf-8"))
AL = _Aligner()


def lesen(p):
    with wave.open(str(p), "rb") as w:
        sr, n = w.getframerate(), w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype("float32") / 32768
    if n > 1:
        x = x.reshape(-1, n).mean(1)
    if sr != SR:
        x = np.interp(np.arange(0, len(x), sr / SR), np.arange(len(x)), x).astype("float32")
    return x


def grenzen(pfad, segs, n):
    """segs = [{"t","s"}] -> [(a,b)] Samples je Segment oder None."""
    woerter, zu = [], []
    for j, g in enumerate(segs):
        for lw in lautwoerter(g["t"]):
            woerter.append(lw["w"]); zu.append(j)
    zeit = AL.ausrichten(pfad, woerter)
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


def fade(x, ms=12):
    k = min(len(x) // 2, int(SR * ms / 1000))
    if k > 0:
        x = x.copy(); r = np.linspace(0, 1, k, dtype="float32"); x[:k] *= r; x[-k:] *= r[::-1]
    return x


def lautheit(x):
    try:
        import pyloudnorm as pyln
        return pyln.normalize.loudness(x, pyln.Meter(SR).integrated_loudness(x), LUFS)
    except Exception as e:
        print("[ap60c] pyloudnorm fehlt -> RMS-Angleich:", e)
        ziel = 10 ** ((LUFS + 3) / 20)
        return x * (ziel / max(1e-6, float(np.sqrt(np.mean(x ** 2)))))


for lg in ("de", "en"):
    teile, protokoll = [], []
    for s in P["saetze"]:
        tid, segs = s["tid"], s[lg]
        pb, pr = T / lg / "B_basis" / f"{tid}.wav", T / lg / "ref" / f"{tid}.wav"
        xb, xr = lesen(pb), lesen(pr)
        gb, gr = grenzen(pb, segs, len(xb)), grenzen(pr, segs, len(xr))
        satz = []
        for k, g in enumerate(segs):
            quelle = "erz" if g["s"] == "Erzaehler" else "ref"
            gg = gb[k] if quelle == "erz" else gr[k]
            if gg is None:   # Notfall: andere Quelle
                quelle = "ref" if quelle == "erz" else "erz"
                gg = gr[k] if quelle == "ref" else gb[k]
            if gg is None:
                protokoll.append(f"{tid}#{k}: kein Schnitt"); continue
            satz.append(fade((xb if quelle == "erz" else xr)[gg[0]:gg[1]]))
            protokoll.append(f"{tid}#{k} {g['s']:<10} <- {quelle} {gg[0] / SR:.2f}-{gg[1] / SR:.2f}s")
        teile += satz + [np.zeros(int(SR * PAUSE_S), "float32")]
    x = lautheit(np.concatenate(teile[:-1]))
    ziel = T / "ergebnis" / f"{lg}_C_hybrid.wav"
    ziel.parent.mkdir(exist_ok=True)
    with wave.open(str(ziel), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    (T / "ergebnis" / f"{lg}_C_schnitte.txt").write_text("\n".join(protokoll), encoding="utf-8")
    print(f"[ap60c] {lg}: {ziel.name} {len(x) / SR:.1f} s")
