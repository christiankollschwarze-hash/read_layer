"""Schneidet Kauderwelsch nach dem letzten Wort ab (Klasse 'schneiden' aus nachklang_klassen_<lang>.json):
Ende = letztes Wort (58c t1) + 120 ms, 30 ms Ausblendung. Original nach fassungen/<lang>/audio_vor_nachklang/.
Aufruf: python tools/nachklang_schneiden.py <werkordner> [<app-audio-ordner-basis>] [de|en ...]"""
import json, shutil, sys, wave
from pathlib import Path
import numpy as np

def schneide(p, ende_s):
    with wave.open(str(p)) as w:
        par = w.getparams(); a = np.frombuffer(w.readframes(par.nframes), dtype=np.int16).copy()
    n = min(len(a) // par.nchannels, int(ende_s * par.framerate)) * par.nchannels
    a = a[:n].astype(np.float32)
    f = int(0.03 * par.framerate) * par.nchannels
    a[-f:] *= np.linspace(1, 0, f)
    with wave.open(str(p), "wb") as w:
        w.setparams(par); w.writeframes(a.astype(np.int16).tobytes())

werk = Path(sys.argv[1]); app = Path(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2] in ("de", "en") else None
for lang in [x for x in sys.argv[2:] if x in ("de", "en")] or ["de", "en"]:
    tags = json.loads((werk / "work" / f"nachklang_klassen_{lang}.json").read_text())["schneiden"]
    wt = json.loads((werk / "work" / f"520_wortzeiten_{lang}.json").read_text(encoding="utf-8"))["tags"]
    bak = werk / "fassungen" / lang / "audio_vor_nachklang"; bak.mkdir(exist_ok=True)
    for t in tags:
        p = werk / "fassungen" / lang / "audio" / f"{t}.wav"
        if not (bak / p.name).exists(): shutil.copy2(p, bak / p.name)
        schneide(p, max(e["t1"] for e in wt[t]) + 0.12)
        if app: shutil.copy2(p, app / "audio" / lang / p.name)
    print(f"{lang}: {len(tags)} geschnitten")
