"""Probe 20.11.2026: Satzpruefung 500 Modal-GPU gegen CPU an N vorhandenen WAVs eines Werks (schreibt nichts).
Aufruf:  py -3.11 tools/test_pruef_modal.py the-art-of-war --lang de --n 40
"""
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import s500_vertonung_gemini as P

ap = argparse.ArgumentParser()
ap.add_argument("werk")
ap.add_argument("--lang", default="de")
ap.add_argument("--n", type=int, default=40)
a = ap.parse_args()
data = json.load(open(config.work_path(a.werk, "400_regie"), encoding="utf-8"))
units, _ = P.einheiten(data, a.lang)
lex, _ = P._lexikon(a.werk, a.lang)
adir = P.audio_dir(a.werk, a.lang)
jobs = []
for u in units:
    pf = os.path.join(adir, f"{u['id']}.wav")
    if os.path.exists(pf):
        jobs.append((u["id"], lex(u["text"]), pf))
    if len(jobs) >= a.n:
        break
if not jobs:
    sys.exit("keine WAVs mit Text im Manifest gefunden")
pr = P.pruefer_fabrik(P.MS_GEMINI)
t0 = time.time(); gpu = P.pruefen_modal(jobs, a.werk, a.lang, P.MS_GEMINI); tg = time.time() - t0
t0 = time.time(); cpu = {k: dict(pr.pruefe(x, p)) for k, x, p in jobs}; tc = time.time() - t0
gleich = sum(1 for k in cpu if (gpu.get(k) or {}).get("grund") == cpu[k]["grund"])
print(f"{len(jobs)} Saetze: Modal {tg:.0f} s (inkl. Start/Upload), CPU {tc:.0f} s; Befund gleich {gleich}/{len(jobs)}")
for k in cpu:
    if (gpu.get(k) or {}).get("grund") != cpu[k]["grund"]:
        print(f"  {k}: modal={gpu.get(k)} cpu={cpu[k]}")
