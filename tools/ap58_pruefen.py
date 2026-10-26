"""AP 58 - Pruefungen Winnie-the-Pooh: text (Verse/Typ vs, Uebersetzung vollstaendig), kosten (Summe kosten.jsonl je Stage)."""
import os, sys, json, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
BOOK = "winnie-the-pooh"


def text():
    d = json.load(open(config.work_path(BOOK, "200_tagging"), encoding="utf-8"))["content"]
    vs = [k for k, e in d.items() if e.get("type") == "vs"]
    rest = [k for k, e in d.items() if config.VERS_MARKE in str(e.get("en", ""))]
    print(f"[ap58] Tags {len(d)}, Strophen vs {len(vs)} (Soll 18), Marke uebrig {len(rest)}")
    for name in ("400_regie", "310_uebersetzung"):
        p = config.work_path(BOOK, name)
        if os.path.exists(p):
            c = json.load(open(p, encoding="utf-8"))["content"]
            ohne = [k for k, e in c.items() if e.get("type") not in config.NO_AUDIO_TYPES and e.get("en") and not e.get("de")]
            vde = [k for k in c if c[k].get("type") == "vs" and c[k].get("de", "").count("\n") != c[k].get("en", "").count("\n")]
            print(f"[ap58] {name}: ohne DE {len(ohne)}, Strophen mit anderer Zeilenzahl {len(vde)}")
            break


def kosten():
    p = os.path.join(config.work_dir(BOOK), "kosten.jsonl")
    s = collections.defaultdict(float)
    if os.path.exists(p):
        for l in open(p, encoding="utf-8"):
            try:
                x = json.loads(l)
            except ValueError:
                continue
            s[str(x.get("stage"))] += x.get("usd", 0) or 0
    print("[ap58] Kosten je Stage:", ", ".join(f"{k} {v:.3f} $" for k, v in sorted(s.items())) or "-", f"| Summe {sum(s.values()):.2f} $")


if __name__ == "__main__":
    {"text": text, "kosten": kosten}[sys.argv[1] if len(sys.argv) > 1 else "text"]()
