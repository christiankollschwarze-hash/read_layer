"""Modellvergleich Sprecherzuordnung (CK 12.10.2026): DeepSeek (aktuelles MODELS["caster"])
gegen die vorhandene Gemini-2.5-Pro-Zuordnung (work/sprecher.json).
Aufruf: py -3.11 tools/vergleich_57b.py <book_id> c006,c011 [--modell or:kimi-k3]
  --modell or:<suchwort>  -> OpenRouter-Modell, dessen ID das Suchwort enthaelt (z. B. or:kimi-k3, or:qwen3.5-plus)
  --modell <id>           -> direkt (z. B. deepseek-v4-flash)
Schreibt work/sprecher_vergleich_<modell>.json (sprecher.json bleibt unberuehrt) und eine Auswertung."""
import json, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from config import config  # noqa

a = [x for x in sys.argv[1:]]
modell = a[a.index("--modell") + 1] if "--modell" in a else config.MODELS["caster"]
if modell.startswith("or:"):
    import requests
    such = modell[3:].lower()
    ids = [m["id"] for m in requests.get("https://openrouter.ai/api/v1/models", timeout=60).json()["data"]]
    treffer = sorted([i for i in ids if such in i.lower()], key=len)
    if not treffer:
        sys.exit(f"[vergleich] Kein OpenRouter-Modell mit '{such}'. Verfuegbar z. B.: "
                 + ", ".join(i for i in ids if re.search(r"kimi|qwen|minimax", i))[:1500])
    modell = "or/" + treffer[0]
config.MODELS["caster"] = modell
print(f"[vergleich] Modell: {modell}")
os.environ["READLAYER_57B_OUT"] = "sprecher_vergleich_" + re.sub(r"[^a-z0-9.]+", "_", modell.lower()) + ".json"
from pipeline import s420_sprecher as s57b  # noqa

book, kap = a[0], a[1].split(",")
os.environ.setdefault("READLAYER_BOOK", book)
wd = config.work_dir(book)
ref = json.load(open(os.path.join(wd, "sprecher.json"), encoding="utf-8"))
neu = s57b.run(book, kapitel=kap, neu=True)
data = json.load(open(config.work_path(book, "400_regie"), encoding="utf-8"))
for lg in ("en", "de"):
    n = gleich = nur_ref = nur_neu = 0
    abw = []
    for tid, e in data["content"].items():
        if tid[:4] not in kap or e.get("type") not in s57b.TYPEN:
            continue
        r = [x["s"] for x in (ref.get(tid) or {}).get(lg, [])]
        d = [x["s"] for x in (neu.get(tid) or {}).get(lg, [])]
        if not r and not d:
            continue
        n += 1
        if r and not d: nur_ref += 1
        elif d and not r: nur_neu += 1
        elif r == d: gleich += 1
        else: abw.append((tid, r, d))
    print(f"\n[vergleich] {modell} {lg}: {n} Saetze mit Rede | gleich {gleich} ({100*gleich/max(n,1):.0f} %) | "
          f"abweichend {len(abw)} | nur Gemini {nur_ref} | nur DeepSeek {nur_neu}")
    for tid, r, d in abw[:12]:
        print(f"   {tid}: Gemini {r} | DeepSeek {d}")
