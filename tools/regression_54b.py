"""AP 54b Regression: Manifest (s710._build_manifest) alt vs. neu, Call of the Wild.
Erlaubt sind nur: neue Felder t/tz/zspans und de_span an von s525 reparierten Ankern."""
import importlib.util, json, sys, copy
sys.path.insert(0, ".")
from config import config
def lade(pfad, name):
    sp = importlib.util.spec_from_file_location(name, pfad); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
werk = sys.argv[1] if len(sys.argv) > 1 else "call-of-the-wild"
alt = lade("archive/2026-10-26_54b/pipeline/s710_cloud_export.py", "s710_alt")
neu = lade("pipeline/s710_cloud_export.py", "s710_neu")
src, _ = neu._load_content_source(werk)
lg = config.SOURCE_LANGUAGE
_, k_tgt, k_span = config.align_keys()
a = alt._build_manifest(werk, lg, "x", copy.deepcopy(src), {})
n = neu._build_manifest(werk, lg, "x", copy.deepcopy(src), {})
for m in (a, n): m.pop("erstellt", None)
br = neu._lade_bruecke(werk)
rep = {(t, w["i"]) for t, ws in br.items() for w in ws if w["sq"] == "repariert"}
fremd = 0; neu_span = 0; mit_t = mit_tz = 0
assert len(a["saetze"]) == len(n["saetze"])
for sa, sn in zip(a["saetze"], n["saetze"]):
    if {k: v for k, v in sa.items() if k != "align"} != {k: v for k, v in sn.items() if k != "align"}: fremd += 1
    for wa, wn in zip(sa.get("align", []), sn.get("align", [])):
        mit_t += "t" in wn; mit_tz += "tz" in wn
        wn = {k: v for k, v in wn.items() if k not in ("t", "tz", "zspans", "ths", "tzhs")}
        if wa != wn:
            if (sn["tag_id"], wn["i"]) in rep and {k: v for k, v in wn.items() if k != k_span} == wa: neu_span += 1
            else: fremd += 1; print("ABWEICHUNG", sn["tag_id"], wa, wn) if fremd < 5 else None
print(f"Regression {werk}: Knoten {len(n['saetze'])} | Anker mit t {mit_t} | mit tz {mit_tz} | reparierte Spans {neu_span} | fremde Abweichungen {fremd}")
print("OK" if fremd == 0 else "FEHLER")
