"""Sucht Kauderwelsch/Nachklaenge am Satzrand: hoerbare Energie vor dem ersten bzw. nach dem letzten Wort
(Wortzeiten aus Stage 58c). Aufruf: python tools/nachklang_suchen.py <werkordner> [de|en ...]
Ausgabe: work/nachklang_<lang>.json, sortiert nach Laenge der verdaechtigen Strecke."""
import json, sys, wave
from pathlib import Path
import numpy as np

SCHWELLE_DB = -40.0   # Rahmen gilt als "Ton", wenn RMS darueber
RAHMEN = 0.02         # 20 ms
MIN_S = 0.25          # verdaechtig ab 250 ms Ton ausserhalb der Woerter

def rms_db(x):
    n = int(len(x) / RAHMEN_N) if RAHMEN_N else 0
    x = x[: n * RAHMEN_N].reshape(n, RAHMEN_N)
    r = np.sqrt((x.astype(np.float64) ** 2).mean(axis=1)) + 1e-9
    return 20 * np.log10(r)

def lies(p):
    global RAHMEN_N
    with wave.open(str(p)) as w:
        sr, n, sw, ch = w.getframerate(), w.getnframes(), w.getsampwidth(), w.getnchannels()
        a = np.frombuffer(w.readframes(n), dtype={2: np.int16, 4: np.int32}[sw])
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    a = a / float(np.iinfo({2: np.int16, 4: np.int32}[sw]).max)
    RAHMEN_N = int(sr * RAHMEN)
    return a, sr

def ton_s(db, von, bis):
    i0, i1 = max(0, int(von / RAHMEN)), max(0, int(bis / RAHMEN))
    return float((db[i0:i1] > SCHWELLE_DB).sum() * RAHMEN)

def main(werk, langs):
    for lang in langs:
        wt = json.loads((werk / "work" / f"520_wortzeiten_{lang}.json").read_text(encoding="utf-8"))["tags"]
        treffer = []
        for tag, e in wt.items():
            p = werk / "fassungen" / lang / "audio" / f"{tag}.wav"
            if not p.exists() or not e:
                continue
            a, sr = lies(p)
            db = rms_db(a)
            dauer = len(a) / sr
            erst = min(x["t0"] for x in e if x.get("t0") is not None)
            letzt = max(x["t1"] for x in e if x.get("t1") is not None)
            vor, nach = ton_s(db, 0, erst - 0.08), ton_s(db, letzt + 0.15, dauer)
            if vor >= MIN_S or nach >= MIN_S:
                treffer.append({"tag": tag, "vor_s": round(vor, 2), "nach_s": round(nach, 2),
                                "dauer_s": round(dauer, 2), "letztes_wort_ende": letzt})
        treffer.sort(key=lambda t: -(t["vor_s"] + t["nach_s"]))
        (werk / "work" / f"nachklang_{lang}.json").write_text(json.dumps(treffer, indent=1), encoding="utf-8")
        print(f"{lang}: {len(treffer)} verdaechtig von {len(wt)}")
        for t in treffer[:8]:
            print("  ", t)

if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2:] or ["de", "en"])
