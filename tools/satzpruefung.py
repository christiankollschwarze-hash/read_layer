"""READ LAYER — Satzpruefung nach der Fertigstellung (Standardprozess seit 17.10.2026).
Prueft jede Satz-WAV gegen ihre Wortzeiten (Stage 58c) und den Text (400_regie):
  - Ton nach dem letzten Wort (Nachklang/Kauderwelsch) -> 'schneiden': wird hinter letztem Wort + 120 ms gekappt
  - Woerter verschmiert (letztes Wort endet viel spaeter als erwartet), Ton vor dem ersten Wort
    oder Satz viel zu kurz (abgebrochen/verschluckt) -> 'neu'
Aufruf: python tools/satzpruefung.py <book_id> <lg> [--schneiden] [--tags a,b]
Ergebnis: work/satzpruefung_<lg>.json {"schneiden": [...], "neu": [...], "geschnitten": n}
Originale gekappter Saetze -> fassungen/<lg>/audio_vor_pruefung/. Wortzeiten bleiben gueltig (nur das Ende faellt weg).
'neu' -> tools/cb_neu.py <book_id> <lg> liste --pruefung (Neuvertonung)."""
import json, os, shutil, sys, wave
import numpy as np

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HIER)
from config import config

SCHWELLE_DB, RAHMEN, MIN_S = -40.0, 0.02, 0.25
MS_JE_ZEICHEN = 0.070          # nach Drosselung (gemessen Peter Pan, atempo 0,73); fuer 0,91 etwas weniger


def lies(p):
    with wave.open(p) as w:
        par = w.getparams()
        a = np.frombuffer(w.readframes(par.nframes), dtype=np.int16)
    return a, par


def ton_s(a, sr, von, bis):
    n = int(sr * RAHMEN)
    i0, i1 = max(0, int(von * sr)), max(0, int(bis * sr))
    x = a[i0:i1].astype(np.float64) / 32768
    k = len(x) // n
    if k <= 0:
        return 0.0
    r = np.sqrt((x[:k * n].reshape(k, n) ** 2).mean(1)) + 1e-9
    return float((20 * np.log10(r) > SCHWELLE_DB).sum() * RAHMEN)


def kappen(p, ende_s):
    a, par = lies(p)
    n = min(len(a), int(ende_s * par.framerate))
    x = a[:n].astype(np.float32)
    f = min(n, int(0.03 * par.framerate))
    x[n - f:] *= np.linspace(1, 0, f)
    with wave.open(p, "wb") as w:
        w.setparams(par)
        w.writeframes(x.astype(np.int16).tobytes())


def main(book, lg, schneiden=False, nur=None):
    wd = config.work_dir(book)
    werk = config.book_dir(book)
    wt = json.load(open(os.path.join(wd, f"520_wortzeiten_{lg}.json"), encoding="utf-8"))["tags"]
    content = json.load(open(config.work_path(book, "400_regie"), encoding="utf-8"))["content"]
    audio = os.path.join(werk, "fassungen", lg, "audio")
    erg = {"schneiden": [], "neu": [], "details": {}}
    for tag, e in wt.items():
        if nur and tag not in nur:
            continue
        p = os.path.join(audio, f"{tag}.wav")
        e = [x for x in e if x.get("t0") is not None and x.get("t1") is not None]
        if not os.path.exists(p) or not e:
            continue
        a, par = lies(p)
        sr, dauer = par.framerate, par.nframes / par.framerate
        erst, letzt = min(x["t0"] for x in e), max(x["t1"] for x in e)
        vor, nach = ton_s(a, sr, 0, erst - 0.08), ton_s(a, sr, letzt + 0.15, dauer)
        erw = max(0.4, len((content.get(tag, {}).get(lg) or "")) * MS_JE_ZEICHEN)
        zu_kurz = dauer < 0.45 * erw and erw > 2.0          # Satz abgebrochen/verschluckt (CK 17.10.: c003_00124_dl)
        if vor < MIN_S and nach < MIN_S and not zu_kurz:
            continue
        klasse = "neu" if (zu_kurz or letzt > erw * 1.6 + 0.6 or vor >= MIN_S) else "schneiden"
        erg[klasse].append(tag)
        erg["details"][tag] = {"vor_s": round(vor, 2), "nach_s": round(nach, 2), "dauer_s": round(dauer, 2),
                               "letztes_wort": letzt, "erwartet_s": round(erw, 2)}
    n = 0
    if schneiden and erg["schneiden"]:
        bak = os.path.join(werk, "fassungen", lg, "audio_vor_pruefung")
        os.makedirs(bak, exist_ok=True)
        for t in erg["schneiden"]:
            p = os.path.join(audio, f"{t}.wav")
            if not os.path.exists(os.path.join(bak, f"{t}.wav")):
                shutil.copy2(p, bak)
            kappen(p, erg["details"][t]["letztes_wort"] + 0.12)
            n += 1
    erg["geschnitten"] = n
    json.dump(erg, open(os.path.join(wd, f"satzpruefung_{lg}.json"), "w", encoding="utf-8"), indent=1)
    print(f"[satzpruefung] {book} {lg}: {len(wt)} Saetze | schneiden {len(erg['schneiden'])} (gekappt {n}) | neu {len(erg['neu'])}")
    return erg


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    nur = None
    if "--tags" in sys.argv:
        nur = set(sys.argv[sys.argv.index("--tags") + 1].split(","))
        a = [x for x in a if x != sys.argv[sys.argv.index("--tags") + 1]]
    main(a[0], a[1], "--schneiden" in sys.argv, nur)
