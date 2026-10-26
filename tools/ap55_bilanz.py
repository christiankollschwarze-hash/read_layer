"""AP 55: Bilanz 345 je Werk - markierte Saetze vor/nach dem letzten Nachlauf + 525-Messung."""
import json, os, sys
sys.path.insert(0, ".")
from config import config
WERKE = ["die-spiegelschwestern", "call-of-the-wild", "alice-s-adventures-in-wonderland", "the-legend-of-sleepy-hollow",
         "as-you-like-it", "jekyll-and-hyde", "peter-and-wendy", "the-hound-of-the-baskervilles"]
for w in WERKE:
    p = config.work_path(w, "345_verschiebung")
    if not os.path.exists(p):
        print(f"{w:34s} kein 345-Bericht"); continue
    b = json.load(open(p, encoding="utf-8"))
    prot = b.get("nachlauf", {})
    ue = sum(1 for x in prot.values() if x["ergebnis"] == "uebernommen")
    m = json.load(open(config.work_path(w, "525_wortbruecke"), encoding="utf-8"))["messung"]["nachher"]["prozent"]
    print(f"{w:34s} markiert {len(b['markiert']):3d} -> {b.get('nach_nachlauf', {}).get('markiert', '-'):>3} | "
          f"uebernommen {ue}/{len(prot)} | Anker+Quelle+Ziel {m['anker_und_beide_zeiten']} %")
