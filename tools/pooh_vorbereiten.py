"""AP 58 (26.10.2026) - Winnie-the-Pooh anlegen und Quelltext vorbereiten (ohne Modernisierung).
Liest _epub_import/winnie-the-pooh/pg67098.txt (Gutenberg #67098) und schreibt deterministisch:
  - Autor milne-aa + Werk winnie-the-pooh (tools/s100_anlegen), book.json mit Rechte-Vermerk + glossar_fest
  - work/modernized/chapter-N.json (Originaltext 1:1, Einleitung + 10 Kapitel; Zeilen entfasert)
  - raw_modernized.txt (wie s120) -> run.py erkennt Stage 120 als erledigt
Lieder/Verse: eingerueckte Bloecke -> je Strophe ein Absatz "<VERS_MARKE>zeile\\nzeile" (s200 macht Typ vs).
Schilder/Notizen in Grossbuchstaben + Rabbits Plan -> normale Absaetze (Tagger: qt).
Kein API-Aufruf, keine Kosten. Aufruf: python tools/pooh_vorbereiten.py [--force]
"""
import os, re, sys, json, subprocess
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
from config import config

BOOK, AUTOR = "winnie-the-pooh", "milne-aa"
QUELLE = os.path.join(BASE, "_epub_import", "winnie-the-pooh", "pg67098.txt")
FORCE = "--force" in sys.argv

TITEL = ["Introduction",
 "Chapter I: In Which We Are Introduced to Winnie-the-Pooh and Some Bees, and the Stories Begin",
 "Chapter II: In Which Pooh Goes Visiting and Gets into a Tight Place",
 "Chapter III: In Which Pooh and Piglet Go Hunting and Nearly Catch a Woozle",
 "Chapter IV: In Which Eeyore Loses a Tail and Pooh Finds One",
 "Chapter V: In Which Piglet Meets a Heffalump",
 "Chapter VI: In Which Eeyore Has a Birthday and Gets Two Presents",
 "Chapter VII: In Which Kanga and Baby Roo Come to the Forest, and Piglet Has a Bath",
 "Chapter VIII: In Which Christopher Robin Leads an Expotition to the North Pole",
 "Chapter IX: In Which Piglet Is Entirely Surrounded by Water",
 "Chapter X: In Which Christopher Robin Gives Pooh a Party, and We Say Good-bye"]

GLOSSAR = {  # feste DE-Namen (eigene Uebersetzung, Figurennamen)
 "Winnie-the-Pooh": {"de": "Winnie-der-Pu"}, "Pooh": {"de": "Pu"}, "Edward Bear": {"de": "Eduard Bär"},
 "Piglet": {"de": "Ferkel"}, "Eeyore": {"de": "I-Ah"}, "Owl": {"de": "Eule"}, "Kanga": {"de": "Känga"},
 "Roo": {"de": "Ruh"}, "Baby Roo": {"de": "Baby Ruh"}, "Rabbit": {"de": "Kaninchen"},
 "Christopher Robin": {"de": "Christopher Robin"}, "Heffalump": {"de": "Heffalump"},
 "Woozle": {"de": "Wusel"}, "Hundred Acre Wood": {"de": "Hundertsechzig-Morgen-Wald"},
 "HUNNY": {"de": "HUNIG"}, "Expotition": {"de": "Expotition"}}


def _anlegen():
    eing = os.path.join(BASE, "cache", "ap58_pooh_anlegen.json")
    os.makedirs(os.path.dirname(eing), exist_ok=True)
    json.dump({"books": [{"book_slug": BOOK, "autor_slug": AUTOR, "autor_name": "A. A. Milne",
                "titel_original": "Winnie-the-Pooh", "originalsprache": "en", "erscheinungsjahr": 1926,
                "gutenberg_id": "67098", "raw_quelle": QUELLE, "_birth_year": 1882, "_death_year": 1956}]},
              open(eing, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    subprocess.run([sys.executable, os.path.join(BASE, "tools", "s100_anlegen.py"), eing], check=True, cwd=BASE)
    bp = os.path.join(config.book_dir(BOOK), "book.json")
    b = json.load(open(bp, encoding="utf-8"))
    b.update({
        "rechte": "gemeinfrei",
        "gemeinfrei_eu_ab": "2027-01-01",
        "veroeffentlichen_ab": "2027-01-01",
        "rechte_hinweis": "Milne +1956: EU gemeinfrei erst ab 1.1.2027 -> produzieren ja, veroeffentlichen ab 2027. "
                          "Shepard-Illustrationen bis 2046 geschuetzt -> eigene Bilder (One-Line), nichts nach Shepard/Disney.",
        "illustrator_original": "Ernest H. Shepard (nicht verwendet)",
        "modernisierung": "keine (Original 1:1, AP 58)",
        "glossar_fest": GLOSSAR,
        "fassungen": [{"sprache": "en", "titel": "Winnie-the-Pooh", "titel_quelle": "original", "titel_pruefen": False},
                      {"sprache": "de", "titel": "Winnie-der-Pu", "titel_quelle": "eigene_uebersetzung", "titel_pruefen": True}],
        "besetzung_modus": "ensemble",
    })
    json.dump(b, open(bp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("[pooh] book.json: Rechte-Vermerk + glossar_fest")


def _zeilen():
    t = open(QUELLE, encoding="utf-8").read().replace("\r\n", "\n")
    L = t.split("\n")
    a = next(i for i, l in enumerate(L) if l.strip() == "INTRODUCTION")
    e = max(i for i, l in enumerate(L) if l.strip() == "Printed in Canada")
    return L[a:e]


def _bloecke(L):
    b, cur = [], []
    for l in L:
        if l.strip():
            cur.append(l.rstrip())
        elif cur:
            b.append(cur); cur = []
    if cur:
        b.append(cur)
    return b


def _ist_vers(bl):
    if not all(l.startswith("    ") for l in bl):
        return False
    t = " ".join(bl)
    if re.fullmatch(r"[\s*]+", t):
        return False
    if re.match(r"\s*\d+\.", bl[0]):          # Rabbits Plan
        return False
    if not re.search(r"[a-z]", re.sub(r"_[^_]*_", "", t)) and len(bl) <= 3:  # Schild in Grossbuchstaben
        return False
    return True


def kapitel():
    L = _zeilen()
    kap, cur = [], None
    bl = _bloecke(L)
    i = 0
    while i < len(bl):
        x = bl[i]; t = " ".join(s.strip() for s in x)
        if t == "INTRODUCTION":
            cur = {"title": TITEL[0], "paragraphs": []}; kap.append(cur); i += 1; continue
        m = re.fullmatch(r"CHAPTER ([IVX]+)", t)
        if m:
            cur = {"title": TITEL[len(kap)], "paragraphs": []}; kap.append(cur); i += 2; continue  # Untertitel-Block ueberspringen
        if t == "CONTENTS":   # Inhaltsverzeichnis bis zum Kapitel I ueberspringen
            while not re.fullmatch(r"CHAPTER I", " ".join(s.strip() for s in bl[i])):
                i += 1
            continue
        if t in ("WINNIE-THE-POOH", "A. A. M."):
            if t == "A. A. M.":
                cur["paragraphs"].append("A. A. M.")
            i += 1; continue
        if re.fullmatch(r"[\s*]+", t):
            cur["paragraphs"].append("——HR——"); i += 1; continue
        if "this" in t and "take" in t and "flying" in t and len(x) == 3:   # Ferkels Wortsalat (Kap. VII)
            cur["paragraphs"].append('"If this is flying I shall never really take to it."'); i += 1; continue
        if _ist_vers(x):
            # Strophen: Leerzeile trennt bereits; eingerueckte Zeilen = eine Strophe
            zeilen = [s.strip() for s in x]
            cur["paragraphs"].append(config.VERS_MARKE + "\n".join(zeilen))
            i += 1; continue
        if re.match(r"\s*\d+\.", x[0]):   # Plan-Punkt, Fortsetzungszeilen entfasern
            cur["paragraphs"].append(" ".join(s.strip() for s in x)); i += 1; continue
        cur["paragraphs"].append(re.sub(r"\s+", " ", " ".join(s.strip() for s in x)).strip())
        i += 1
    return kap


def main():
    _anlegen()
    kap = kapitel()
    mod = os.path.join(config.work_dir(BOOK), "modernized")
    os.makedirs(mod, exist_ok=True)
    nv = 0
    for n, k in enumerate(kap, 1):
        p = os.path.join(mod, f"chapter-{n}.json")
        if os.path.exists(p) and not FORCE:
            print(f"  chapter-{n}.json existiert"); continue
        json.dump(k, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        v = sum(1 for x in k["paragraphs"] if x.startswith(config.VERS_MARKE)); nv += v
        print(f"  [{n}] {k['title'][:60]}: {len(k['paragraphs'])} Absaetze, {v} Strophen")
    from pipeline import s120_modernisierung as s120
    print("[pooh] Quelle ->", s120._write_marked_source(BOOK, mod))
    print(f"[pooh] {len(kap)} Kapitel, {nv} Strophen (Typ vs)")


if __name__ == "__main__":
    main()
