"""READ LAYER — Zieltext aus 400_regie nach 310_uebersetzung + 340_wortalignment uebernehmen (fuer neu eingepflegte/geaenderte Saetze).
Danach muss Stage 54a diese Saetze neu ausrichten (Align wird hier geloescht).
Aufruf: python tools/text_nachziehen.py <book_id> <c002,c009,...> [de]
"""
import json, os, shutil, sys
HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HIER)
from config import config  # noqa: E402

book, kap = sys.argv[1], sys.argv[2].split(",")
lg = sys.argv[3] if len(sys.argv) > 3 else "de"
s6 = json.load(open(config.work_path(book, "400_regie"), encoding="utf-8"))["content"]
n = {}
for stage in ("310_uebersetzung", "340_wortalignment"):
    p = config.work_path(book, stage)
    shutil.copy(p, p + ".bak_nachziehen")
    d = json.load(open(p, encoding="utf-8"))
    n[stage] = 0
    for t, e in d["content"].items():
        if t[:4] in kap and t in s6 and s6[t].get(lg) and e.get(lg) != s6[t][lg]:
            e[lg] = s6[t][lg]
            if stage == "340_wortalignment":
                e.pop("align", None)
            n[stage] += 1
        elif stage == "340_wortalignment" and t[:4] in kap and t in s6 and s6[t].get(lg) and not e.get("align"):
            n[stage] += 0
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"[nachziehen] {book} {kap} [{lg}]: 310_uebersetzung {n['310_uebersetzung']} geaendert, 340_wortalignment {n['340_wortalignment']} geaendert (Align geloescht)")
