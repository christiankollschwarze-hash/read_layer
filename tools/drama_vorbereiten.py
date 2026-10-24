"""
READ LAYER — Drama-Tor: Buehnenstueck deterministisch strukturieren (ersetzt Stage 50 fuer Dramen)
==================================================================================================
Input : raw_modernized.txt (Stage 11; Rollennamen stehen dort als eigene Absaetze "ROSALIND.")
Output: work/200_tagging.json   (Kapitel = Akte; je Satz ein Tag; Repliken mit "sprecher")
        raw_modernized.txt  (korrigierte Akt-Marken; Rollennamen bleiben fuer das EPUB erhalten)
        book.json modus = "drama"

Regeln (CK 11.10.2026):
- Rollennamen werden NIE vorgelesen; sie stehen als Feld "sprecher" am Tag (CC-/Mitlese-Anzeige).
- Akt-/Szenenueberschriften und Regieanweisungen liest der Erzaehler (type "s", rolle "regie").
- Falsch erkannte Kapitel (Rollenname als ###CHAPTER###, z. B. "Dennis", "Song") werden
  zurueck in Sprecherzeilen verwandelt; Kapitel sind nur ACT/EPILOGUE/PROLOGUE.

Aufruf: py -3.11 tools/drama_vorbereiten.py <book_id> [--trocken]
"""
import json
import os
import re
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from config import config  # noqa: E402

SPRECHER_RE = re.compile(r"[A-Z][A-Z .,'’&-]{1,40}\.")
KAPITEL_RE = re.compile(r"(act\b|epilogue|prologue|induction)", re.I)
REGIE_START = ("Enter", "Re-enter", "Exit", "Exeunt", "Manet", "Flourish", "SCENE", "Scene")
SATZ_RE = re.compile(r"(?<=[.!?…])[\"”’]?\s+(?=[\"“‘(\[]?[A-Z0-9])")


def saetze(text):
    teile = [t.strip() for t in SATZ_RE.split(text) if t and t.strip()]
    # zu kurze Bruchstuecke an den Vorgaenger haengen
    out = []
    for t in teile:
        if out and len(t) < 4:
            out[-1] += " " + t
        else:
            out.append(t)
    return out


def regie_abspalten(text):
    """'[_Coming forward._] Good masters ...' -> (['Coming forward.'], 'Good masters ...')"""
    regie = []

    def weg(m):
        regie.append(m.group(1).replace("_", "").strip())
        return " "
    rest = re.sub(r"\[([^\]]+)\]", weg, text)
    return regie, re.sub(r"\s+", " ", rest).strip()


def lesen(pfad):
    t = open(pfad, encoding="utf-8").read()
    M = config.MARKERS
    titel = autor = ""
    akte = []          # [(titel, [absaetze])]
    rest = []
    for z in t.splitlines():
        if z.startswith(M["title"]):
            titel = z[len(M["title"]):].strip()
        elif z.startswith(M["author"]):
            autor = z[len(M["author"]):].strip()
        elif z.startswith(M["chapter"]):
            rest += ["", z, ""]
        else:
            rest.append(z)
    for block in re.split(r"\n\s*\n", "\n".join(rest)):
        b = block.strip()
        if not b:
            continue
        for zeile_block in [b]:
            if zeile_block.startswith(M["chapter"]):
                name = zeile_block[len(M["chapter"]):].strip()
                if KAPITEL_RE.match(name) or not akte:
                    akte.append([name.title() if name.isupper() else name, []])
                else:
                    # falsch erkanntes Kapitel = Rollenname
                    akte[-1][1].append(name.upper().rstrip(".") + ".")
            else:
                akte[-1][1].append(zeile_block)
    return titel, autor, akte


def strukturieren(akte):
    cd, sd = config.CHAPTER_DIGITS, config.SEQUENCE_DIGITS
    content, kapitel, figuren = {}, {}, {}
    for ki, (titel, absaetze) in enumerate(akte, 1):
        kid = f"c{ki:0{cd}d}"
        kapitel[kid] = titel
        seq = 1

        def neu(typ, text, **extra):
            nonlocal seq
            tid = f"{kid}_{seq:0{sd}d}_{typ}"
            content[tid] = dict({"type": typ, config.SOURCE_LANGUAGE: text}, **extra)
            seq += 1
            return tid

        neu("h", titel)
        sprecher = None
        replik = 0
        for a in absaetze:
            a1 = re.sub(r"\s+", " ", a).strip()
            if SPRECHER_RE.fullmatch(a1) and a1.upper() == a1:
                sprecher = a1[:-1].strip()
                replik += 1
                figuren[sprecher] = figuren.get(sprecher, 0) + 1
                continue
            if a1.startswith(REGIE_START) or (a1.startswith("[") and a1.endswith("]")):
                regie, _ = regie_abspalten(a1) if a1.startswith("[") else ([a1], "")
                for r in regie:
                    neu("s", r, rolle="regie")
                if a1.startswith(("SCENE", "Scene")):
                    sprecher = None
                continue
            regie, rede = regie_abspalten(a1)
            for r in regie:
                neu("s", r, rolle="regie")
            if not rede:
                continue
            if sprecher:
                for s in saetze(rede):
                    neu("dl", s, sprecher=sprecher, replik=replik)
            else:
                for s in saetze(rede):
                    neu("s", s, rolle="regie")
    return content, kapitel, figuren


def main(book_id, trocken=False):
    bdir = config.book_dir(book_id)
    src = os.path.join(bdir, "raw_modernized.txt")
    titel, autor, akte = lesen(src)
    content, kapitel, figuren = strukturieren(akte)
    n_dl = sum(1 for v in content.values() if v["type"] == "dl")
    print(f"[drama] {titel} — {autor}")
    print(f"[drama] Kapitel: {', '.join(kapitel.values())}")
    print(f"[drama] {len(content)} Tags, davon {n_dl} Repliksaetze, "
          f"{sum(1 for v in content.values() if v.get('rolle') == 'regie')} Regie")
    print("[drama] Figuren: " + ", ".join(f"{k} {v}" for k, v in sorted(figuren.items(), key=lambda x: -x[1])))
    if trocken:
        return
    wd = config.work_dir(book_id)
    sich = os.path.join(wd, "_vor_drama_" + time.strftime("%Y%m%d_%H%M"))
    os.makedirs(sich, exist_ok=True)
    for f in os.listdir(wd):
        if re.fullmatch(r"stage0[0-8][ab]?\.json|340_wortalignment\.json|casting\.json|sprecher\.json", f):
            shutil.move(os.path.join(wd, f), os.path.join(sich, f))
    shutil.copy2(src, os.path.join(sich, "raw_modernized.txt"))
    # korrigierte Quelle (Akte richtig, Rollennamen bleiben fuer das EPUB)
    M = config.MARKERS
    zeilen = [f'{M["title"]} {titel}', f'{M["author"]} {autor}', ""]
    for name, absaetze in akte:
        zeilen += [f'{M["chapter"]} {name}', ""]
        for a in absaetze:
            zeilen += [a, ""]
    open(src, "w", encoding="utf-8").write("\n".join(zeilen).strip() + "\n")
    daten = {"book_id": book_id,
             "meta": {"title": titel, "author": autor, "source_language": config.SOURCE_LANGUAGE,
                      "target_languages": config.TARGET_LANGUAGES, "chapters": kapitel,
                      "modus": "drama", "figuren": figuren},
             "content": content}
    json.dump(daten, open(config.work_path(book_id, "200_tagging"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    bp = os.path.join(bdir, "book.json")
    b = json.load(open(bp, encoding="utf-8"))
    b["modus"] = "drama"
    json.dump(b, open(bp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[drama] Alte Stände gesichert in {sich}")
    print(f"[drama] 200_tagging.json geschrieben; weiter mit: run.py {book_id} --line audio --from 51 --to 400 --live")


if __name__ == "__main__":
    main(sys.argv[1], trocken="--trocken" in sys.argv)
