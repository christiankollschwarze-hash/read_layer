"""Modellvergleich Stage 420 (Sprecherzuordnung) ohne Schreiben in work/ (26.11.2026, EU-Variante D).
Aufruf: python tools/test_regie_mistral.py <werk> c006,c011 [lg=de] -- Modelle per MODELLE=a,b
Ergebnis: Claude outputs/regie_test/<werk>_<kap>_<lg>.json + Uebereinstimmung je Modell vs. work/sprecher.json."""
import json, os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from config import config
from pipeline import s420_sprecher as S, s410_casting as s410, bestellung, usage_log

werk, kap = sys.argv[1], sys.argv[2].split(",")
lg = sys.argv[3] if len(sys.argv) > 3 else "de"
modelle = os.environ.get("MODELLE", "deepseek-flash,mistral-large-2512").split(",")
b = bestellung.lesen(werk)
src = b.quellsprache or config.SOURCE_LANGUAGE
stufe = S._ziele(b).get(lg)
cast = S.besetzung(s410.laden(werk), lg, stufe)
data = json.load(open(config.work_path(werk, "400_regie"), encoding="utf-8"))
content = data["content"]; sprech = (data.get("production") or {}).get("sprechtext") or {}
ref_alt = json.load(open(os.path.join(config.work_dir(werk), "sprecher.json"), encoding="utf-8"))
txt = lambda t, e, l: ((sprech.get(t) or {}).get(l) if (sprech.get(t) or {}).get(l) is not None else e.get(l, ""))
items = []
for k in kap:
    alles = [(t, e) for t, e in content.items() if t.startswith(k) and isinstance(e, dict)]
    eintr = [(t, e) for t, e in alles if e.get("type") in S.TYPEN]
    for t, e in S.auswahl(eintr, [lg, src], alles):
        items.append((t, txt(t, e, lg), e.get(src) if src != lg else None))
items = items[:int(os.environ.get("LIMIT", "100000"))]
config.SPUREN[S.STAGE] = int(os.environ.get("SPUREN", "2"))
print(f"{werk} {kap} {lg}: {len(items)} Kandidaten, Besetzung {len(cast)}")
rg = {"teil": int(os.environ.get("TEIL", "40"))}
ergebnis = {}
for m in modelle:
    usage_log.set_context(werk, "420test", sprache=lg)
    t0 = time.time(); rg["modell"] = m
    out, n = S.zuordnen(items, cast, lg, src, None, rg, lambda tid: [])
    ergebnis[m] = {t: [x["s"] for x in (r or {}).get("seg", [])] for t, r in out.items()}
    rf = sum(1 for r in out.values() if r and r.get("q") == "rueckfall")
    print(f"  {m}: {len(out)} Saetze, {n} Aufrufe, Rueckfaelle {rf}, {time.time()-t0:.0f}s")
def vgl(a, b_):
    ids = [t for t, _, _ in items if a.get(t) or b_.get(t)]
    g = sum(1 for t in ids if a.get(t) == b_.get(t)); return g, len(ids)
ref = {t: [x["s"] for x in (v.get(lg) or [])] for t, v in ref_alt.items() if isinstance(v, dict)}
p420 = config.work_path(werk, "420_sprecher")
if os.path.exists(p420):                                  # aktueller Produktionsstand (DeepSeek) hat Vorrang
    s420 = json.load(open(p420, encoding="utf-8")).get("saetze") or {}
    ref = {t: [x["s"] for x in ((v.get(lg) or {}).get("seg") or [])] for t, v in s420.items() if isinstance(v, dict)}
for m in modelle:
    g, n = vgl(ergebnis[m], ref); print(f"  {m} vs. Produktion (420/sprecher.json): {g}/{n} gleich ({100*g/max(n,1):.0f} %)")
if len(modelle) == 2:
    a, c = modelle
    g, n = vgl(ergebnis[a], ergebnis[c]); print(f"  {a} vs. {c}: {g}/{n} gleich ({100*g/max(n,1):.0f} %)")
    abw = [(t, ref.get(t), ergebnis[a].get(t), ergebnis[c].get(t)) for t, _, _ in items
           if ergebnis[a].get(t) != ergebnis[c].get(t)]
else:
    abw = []
ziel = os.path.join(ROOT, "Claude outputs", "regie_test"); os.makedirs(ziel, exist_ok=True)
fn = os.path.join(ziel, f"{werk}_{'_'.join(kap)}_{lg}.json")
json.dump({"items": {t: x for t, x, _ in items}, "ergebnis": ergebnis, "bisher": {t: ref.get(t) for t, _, _ in items},
           "abweichungen": abw}, open(fn, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("Datei:", fn)
