"""Pruefung im Lauf (gpu_tts/cb_pruefung.py) lokal auf einen Probeordner anwenden (CPU) - zum Eichen gegen CK-Gehoer.
Aufruf: py -3.11 tools/probe_pruefen.py <paketname> <probeordner>
  z. B.  py -3.11 tools/probe_pruefen.py u-mikemustermann-peter-and-wendy_de_testA <werk>\\work\\_tts_probe\\de_b8_probe_A"""
import json, os, sys, wave
import numpy as np
import torch
HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HIER, "gpu_tts"))
from cb_pruefung import Pruefer

paket, ordner = sys.argv[1], sys.argv[2]
texte = {j["id"]: j["text"] for j in json.load(open(os.path.join(HIER, "gpu_tts", paket, "jobs.json"), encoding="utf-8"))["jobs"]}
pr = Pruefer("cpu")
treffer = {}
for x in sorted(os.listdir(ordner)):
    if not x.endswith(".wav") or x[:-4] not in texte:
        continue
    with wave.open(os.path.join(ordner, x)) as w:
        sr = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    b = pr.pruefe(texte[x[:-4]], torch.from_numpy(a).unsqueeze(0), sr)
    if b["grund"]:
        treffer[x[:-4]] = b
        print(f"{x[:-4]}: {b['grund']} (Dauer {b['dauer']} s, letztes Wort {b['letzt']} s) | {texte[x[:-4]][:60]}")
print(f"[probe_pruefen] {len(treffer)} auffaellig")
json.dump(treffer, open(os.path.join(ordner, "_pruefung.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
