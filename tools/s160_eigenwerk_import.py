"""STAGE 160 — Eigenwerk-Import
Funktion:     Legt ein eigenes Werk (eigene Rechte, nicht gemeinfrei) aus einem Markdown-Export an.
Wirkungsweise: Liest den Markdown-Export (Claude-Doc "Exportieren -> Markdown"), legt Werk unter dem
              Autor "unbekannt" an, schreibt book.json (rechte = "eigene", originalsprache aus Aufruf),
              raw.txt (Original-Markdown), raw_modernized.txt (###-Marken) und
              work/modernized/chapter-N.json. Stage 120 (Modernisierung) entfaellt wie beim ePub-Import.
Komponenten:  tools/s160_eigenwerk_import.py, config/config.py (werk_rechte)
Zulieferer:   Markdown-Export eines eigenen Texts (z. B. _epub_import/<slug>.md)
Abnehmer:     s200 Tagging (raw_modernized.txt), s600 Klappentext, s620 ePub Original (Impressum eigene Rechte)
(angelegt 22.10.2026, Werk "Die Spiegelschwestern")

Markdown-Konvention:
  # Titel                  -> Werktitel (Zeile danach mit "*...* · @..." = Doc-Kopf, wird verworfen)
  ## Kapitelname           -> Kapitel (Prolog, Kapitel 1 ..., Epilog)
  **Name**\\ / *Ort, Zeit*  -> Kopfzeilen des Kapitels, bleiben als eigene Absaetze
  ---                      -> Szenenwechsel (HR in chapter-N.json, nicht in raw_modernized.txt)
  **ENDE** am Schluss      -> verworfen
  *kursiv* -> _kursiv_ (Pipeline-Konvention), **fett** -> Text

Aufruf:
  python tools/s160_eigenwerk_import.py _epub_import/die-spiegelschwestern.md --sprache de
         [--slug die-spiegelschwestern] [--autor unbekannt] [--jahr 2026] [--quelle <URL>] [--dry] [--force]
"""
import os, sys, re, json, shutil, argparse
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config

HR = "\u2014\u2014HR\u2014\u2014"


def _inline(t):
    t = t.rstrip("\\").strip()
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"_\1_", t)
    return re.sub(r"\s+", " ", t).strip()


def parse_markdown(text):
    """-> (titel, [{"title", "paragraphs"}])"""
    titel, kapitel, cur, block = "", [], None, []

    def flush():
        nonlocal block
        if cur is not None and block:
            # Kopfzeilen mit hartem Umbruch (Backslash) -> je Zeile ein Absatz
            if any(l.rstrip().endswith("\\") for l in block[:-1]):
                for l in block:
                    if l.strip():
                        cur["paragraphs"].append(_inline(l))
            else:
                p = _inline(" ".join(l.strip() for l in block))
                if p:
                    cur["paragraphs"].append(p)
        block = []

    for line in text.splitlines():
        s = line.strip()
        if s.startswith("# ") and not titel:
            titel = s[2:].strip(); continue
        if s.startswith("## "):
            flush()
            cur = {"title": s[3:].strip(), "paragraphs": []}
            kapitel.append(cur); continue
        if cur is None:
            continue                                   # Doc-Kopf vor dem ersten Kapitel
        if not s:
            flush(); continue
        if s in ("---", "***", "* * *"):
            flush(); cur["paragraphs"].append(HR); continue
        block.append(line)
    flush()

    for k in kapitel:                                   # Schluss: **ENDE**, Rand-HR weg
        p = k["paragraphs"]
        while p and (p[-1] == HR or p[-1].strip().upper() in ("ENDE", "THE END", "END")):
            p.pop()
        while p and p[0] == HR:
            p.pop(0)
    return titel, [k for k in kapitel if [x for x in k["paragraphs"] if x != HR]]


def main():
    ap = argparse.ArgumentParser(description="Stage 160 - eigenes Werk aus Markdown anlegen")
    ap.add_argument("md")
    ap.add_argument("--sprache", required=True, choices=sorted(config.WERK_SPRACHPAARE))
    ap.add_argument("--slug")
    ap.add_argument("--titel")
    ap.add_argument("--autor", default="unbekannt", help="autor_slug (Default: unbekannt)")
    ap.add_argument("--jahr", type=int, default=datetime.now().year)
    ap.add_argument("--quelle", default="", help="Herkunft des Texts (z. B. Claude-Doc-URL)")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    text = open(a.md, encoding="utf-8").read()
    titel, kapitel = parse_markdown(text)
    titel = a.titel or titel
    if not titel or not kapitel:
        sys.exit("! Kein Titel (# ...) oder keine Kapitel (## ...) gefunden.")
    slug = a.slug or config.slugify(titel)
    n_abs = sum(1 for k in kapitel for p in k["paragraphs"] if p != HR)
    zeichen = sum(len(p) for k in kapitel for p in k["paragraphs"] if p != HR)
    print(f'[160] "{titel}" -> {a.autor}/{slug} | {len(kapitel)} Kapitel, {n_abs} Absaetze, {zeichen} Zeichen')
    for i, k in enumerate(kapitel, 1):
        print(f'      {i:2d} {k["title"]:<12} {len([p for p in k["paragraphs"] if p != HR]):4d} Abs.  '
              f'{k["paragraphs"].count(HR)} HR')

    idx = config._load_index()
    if idx["books"].get(slug, a.autor) != a.autor:
        sys.exit(f"! Slug '{slug}' gehoert schon zu Autor '{idx['books'][slug]}'.")
    adir = config.author_dir(a.autor)
    bdir = os.path.join(adir, "books", slug)
    if os.path.exists(os.path.join(bdir, "book.json")) and not a.force:
        sys.exit(f"! Werk existiert schon ({bdir}). --force zum Ueberschreiben.")
    if a.dry:
        print(">>> DRY-RUN, nichts geschrieben."); return

    os.makedirs(os.path.join(bdir, "work", "modernized"), exist_ok=True)
    os.makedirs(os.path.join(bdir, "output"), exist_ok=True)

    # Autor (Werke unbekannter Autorschaft / eigene Werke ohne Autorangabe)
    ap_ = os.path.join(adir, "author.json")
    aj = json.load(open(ap_, encoding="utf-8")) if os.path.exists(ap_) else {
        "wikidata_id": "", "verified": False, "name_display": "", "name_sort": "",
        "geburtsjahr": None, "todesjahr": None, "werke_im_bestand": []}
    if a.autor == "unbekannt":
        aj["name_display"] = aj.get("name_display") or "Unbekannt"
        aj["name_display_de"] = aj.get("name_display_de") or "Unbekannt"
        aj["name_display_en"] = aj.get("name_display_en") or "Unknown"
        aj["wikidata_abfrage"] = False
    if slug not in aj.setdefault("werke_im_bestand", []):
        aj["werke_im_bestand"].append(slug)
    json.dump(aj, open(ap_, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    book = {
        "book_slug": slug, "author_slug": a.autor,
        "author_wikidata_id": "", "work_wikidata_id": "",
        "publisher": "<eigenes-label>",
        "titel_original": titel, "originalsprache": a.sprache,
        "erscheinungsjahr": a.jahr, "gutenberg_id": "",
        "rechte": "eigene",
        "rechte_hinweis": "Eigenes Werk, nicht gemeinfrei. Keine PD-/Todesjahr-Pruefung, keine Wikidata-Abfrage.",
        "herkunft": "eigenwerk", "quelle": a.quelle, "quelle_datei": os.path.basename(a.md),
        "quell_uebersetzer": "", "quell_uebersetzer_todesjahr": None,
        "thema_codes": [], "bisac_codes": [], "genre_eigen": "",
        "ton": "", "schauplatz": "", "essenz": "",
        "leseprobe_zitat": "", "inhaltshinweise": [], "sicherheit": "",
        "bedeutung_werk": "",
        "umfang": {"kapitel": len(kapitel), "absaetze": n_abs, "zeichen": zeichen,
                   "einheiten_50k": -(-zeichen // 50000)},
        "fassungen": [{"sprache": a.sprache, "titel": titel, "titel_quelle": "original",
                       "titel_pruefen": False}],
        "angelegt": datetime.now().isoformat(timespec="seconds"),
    }
    bp = os.path.join(bdir, "book.json")
    if os.path.exists(bp):                              # --force: Felder anderer Stages erhalten
        alt = json.load(open(bp, encoding="utf-8"))
        alt.update({k: v for k, v in book.items() if k not in ("fassungen",)})
        if not alt.get("fassungen"):
            alt["fassungen"] = book["fassungen"]
        book = alt
    json.dump(book, open(bp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    shutil.copy2(a.md, os.path.join(bdir, "raw.txt"))
    M = config.MARKERS
    zeilen = [f'{M["title"]} {titel}', f'{M["author"]} {aj.get("name_display") or a.autor}', ""]
    mdir = os.path.join(bdir, "work", "modernized")
    for f in os.listdir(mdir):
        if re.fullmatch(r"chapter-\d+\.json", f):
            os.remove(os.path.join(mdir, f))
    for i, k in enumerate(kapitel, 1):
        json.dump({"title": k["title"], "paragraphs": k["paragraphs"]},
                  open(os.path.join(mdir, f"chapter-{i}.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        zeilen += [f'{M["chapter"]} {k["title"]}', ""]
        zeilen += [x for p in k["paragraphs"] if p != HR for x in (p, "")]
    open(os.path.join(bdir, "raw_modernized.txt"), "w", encoding="utf-8").write("\n".join(zeilen).strip() + "\n")

    idx["books"][slug] = a.autor
    idx["authors"].setdefault(a.autor, "")
    config._save_index(idx)
    print(f"[160] fertig: {os.path.relpath(bdir, config.BASE_DIR)} (book.json, raw.txt, raw_modernized.txt, "
          f"{len(kapitel)} chapter-N.json), Index aktualisiert.")


if __name__ == "__main__":
    main()
