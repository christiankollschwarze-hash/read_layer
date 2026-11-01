"""AP 63: Referenztext fuer Stimmen-Hoerproben (Klon-Vorlage Chatterbox).
Quelle EN: Aesop, "The North Wind and the Sun" (authors/aesop/books/aesop-s-fables-a-new-translation/raw.txt).
DE: ueber Stufe 310 (translate_chapter) uebersetzt. Angehaengt: je eine Frage und ein Ausruf (Satzmelodie).
Ausgabe: stimmen_archiv/_texte/nordwind_en.txt, nordwind_de.txt, nordwind.json
Aufruf: py -3.11 tools/referenztext_nordwind.py   (ein LLM-Aufruf, < 1 Cent)
"""
import json, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from config import config
from pipeline.s310_uebersetzung import translate_chapter, anfuehrung_de

RAW = os.path.join(ROOT, "authors", "aesop", "books", "aesop-s-fables-a-new-translation", "raw.txt")
ZIEL = os.path.join(ROOT, "stimmen_archiv", "_texte")
ZUSATZ_EN = ["Who would have thought that the gentle Sun could win such a contest?",
             "What a warm and wonderful day it turned out to be!"]


def fabel():
    t = open(RAW, encoding="utf-8").read()
    i = t.index("The North Wind and the Sun disputed")
    j = t.index("Persuasion is better than Force.", i) + len("Persuasion is better than Force.")
    body = re.sub(r"\s+", " ", t[i:j]).strip()
    return [s.strip() for s in re.split(r"(?<=[.;!?])\s+(?=[A-Z])", body) if s.strip()]


def main():
    config.RUN_MODE = "live"
    en = ["The North Wind and the Sun."] + fabel() + ZUSATZ_EN
    items = [(f"n{k:02d}", s) for k, s in enumerate(en)]
    de, fehlt = translate_chapter(items, "de", "", {})
    if fehlt:
        sys.exit(f"[nordwind] Uebersetzung unvollstaendig: {fehlt}")
    de_l = [anfuehrung_de(de[tid]) for tid, _ in items]
    os.makedirs(ZIEL, exist_ok=True)
    open(os.path.join(ZIEL, "nordwind_en.txt"), "w", encoding="utf-8").write(" ".join(en) + "\n")
    open(os.path.join(ZIEL, "nordwind_de.txt"), "w", encoding="utf-8").write(" ".join(de_l) + "\n")
    json.dump({"quelle": "Aesop, The North Wind and the Sun (Gutenberg: Aesop's Fables, A New Translation)",
               "zweck": "Referenz-Hoerprobe fuer Stimmenklon (15-20 s)",
               "en": en, "de": de_l}, open(os.path.join(ZIEL, "nordwind.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("[nordwind] EN:", " ".join(en))
    print("[nordwind] DE:", " ".join(de_l))


if __name__ == "__main__":
    main()
