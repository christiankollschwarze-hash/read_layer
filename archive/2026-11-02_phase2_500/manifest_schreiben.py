"""Schreibt work/500_vertonung.json (Audio-Manifest) aus vorhandenen Satz-WAVs (mehrstimmige Vertonung).
Aufruf: py -3.11 tools/manifest_schreiben.py <book_id>"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from config import config  # noqa
b = sys.argv[1]
data = json.load(open(config.work_path(b, "400_regie"), encoding="utf-8"))
man = {}
for lg in [config.SOURCE_LANGUAGE] + list(config.TARGET_LANGUAGES):
    adir = os.path.join(config.book_dir(b), "fassungen", lg, "audio")
    man[lg] = {tid: os.path.relpath(os.path.join(adir, f"{tid}.wav"), config.book_dir(b))
               for tid in data["content"] if os.path.exists(os.path.join(adir, f"{tid}.wav"))}
    print(f"[manifest] {lg}: {len(man[lg])} Satz-WAVs")
cast = {}
cp = os.path.join(config.work_dir(b), "casting.json")
if os.path.exists(cp):
    c = json.load(open(cp, encoding="utf-8"))["plan"]
    cast = {"erzaehler": c["erzaehler"].get("stimme"), **{e["figur"]: e.get("stimme") for e in c["ensemble"]}}
p = data.setdefault("production", {})
p["audio_manifest"] = man
p["audio_voice_used"] = "mehrstimmig"
p["besetzung"] = cast
json.dump(data, open(config.work_path(b, "500_vertonung"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("[manifest] ->", config.work_path(b, "500_vertonung"))
