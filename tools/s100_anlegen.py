"""STAGE 100 — Anlegen
Funktion:     Legt ein Werk aus der Gutenberg-Startliste an.
Wirkungsweise: Laedt den Gutenberg-Rohtext, legt Autor-/Werkordner, book.json und den Eintrag in daten/index.json an.
Komponenten:  tools/s100_anlegen.py, config/config.py
Zulieferer:   Cockpit-Startliste (cockpit/startliste.json), Gutenberg
Abnehmer:     s110 Wikidata, s120 Modernisierung, s600 Klappentext, s620 ePub Original
(Nomenklatur seit 18.10.2026, Uebersicht: docs/Pipeline_Strang_Matrix.xlsx)

--- Bisherige Beschreibung ---

READ LAYER — Anlege-Logik (Author First, idempotent)
====================================================
Liest eine Eingabe-Datei (JSON) mit neuen Buechern und legt die Struktur an:
  authors/<autor-slug>/author.json
  authors/<autor-slug>/books/<book-slug>/{book.json, raw.txt, work/, output/}
und pflegt index.json (book_slug->autor_slug, autor_slug->Q-ID).

Reihenfolge pro Buch (Author First):
  1. autor_slug bestimmen (aus Eingabe ODER Vorschlag aus Name; Kollision -> -2/-3)
  2. Autor vorhanden? NEIN -> author.json anlegen + Index. JA -> ueberspringen.
  3. Werk anlegen: Ordner + book.json (+ work/ output/) + Index.
  4. Rohtext kopieren -> raw.txt (falls raw_quelle angegeben & vorhanden).

IDEMPOTENT: schon vorhandene Autoren/Buecher werden nicht ueberschrieben (ausser --force).

AUFRUF (aus dem Projekt-Wurzelverzeichnis, neben run.py/config.py):
  python anlegen.py new_books.json
  python anlegen.py new_books.json --dry     # nur zeigen, was passieren wuerde
  python anlegen.py new_books.json --force    # vorhandene book.json/author.json ueberschreiben
"""

import os, sys, json, shutil
import urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config

DRY = "--dry" in sys.argv
FORCE = "--force" in sys.argv


def _author_json_template(slug, name, qid, birth=None, death=None):
    return {
        "wikidata_id": qid or "",
        "verified": False,
        "name_display": name,
        "name_sort": "",
        "geburtsjahr": birth, "todesjahr": death, "geburtsort": "",
        "wirkungssprache": "",
        "notable_works": [],
        "epoche": "", "stilrichtung": [], "bedeutung_kurz": "",
        "quelle_weich": "",
        "werke_im_bestand": []
    }


def _book_json_template(b, autor_slug):
    fassungen = []   # 18.10.2026: LibriVox-Fassung (fremdes EN-Audio) archiviert
    return {
        "book_slug": b["book_slug"],
        "author_slug": autor_slug,
        "author_wikidata_id": b.get("wikidata_id_autor", "") or "",
        "work_wikidata_id": b.get("wikidata_id_werk", "") or "",
        "publisher": "<eigenes-label>",
        "titel_original": b.get("titel_original", ""),
        "originalsprache": b.get("originalsprache", ""),
        "erscheinungsjahr": b.get("erscheinungsjahr"),
        "gutenberg_id": b.get("gutenberg_id", ""),
        "quell_uebersetzer": "", "quell_uebersetzer_todesjahr": None,
        "thema_codes": [], "bisac_codes": [], "genre_eigen": "",
        "ton": "", "schauplatz": "", "essenz": "",
        "leseprobe_zitat": "", "inhaltshinweise": [], "sicherheit": "",
        "bedeutung_werk": "",
        "fassungen": fassungen
    }


def _write_json(path, data):
    if DRY:
        print(f"    [dry] wuerde schreiben: {os.path.relpath(path, config.BASE_DIR)}")
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def anlege_buch(b, idx):
    titel = b.get("titel_original", "(ohne Titel)")
    book_slug = b.get("book_slug") or config.slugify(titel)
    name = b.get("autor_name", "").strip()
    qid = b.get("wikidata_id_autor", "") or ""

    print(f"\n[{book_slug}]  \"{titel}\"  — Autor: {name or '(unbekannt)'}")

    # --- 1. autor_slug bestimmen ---
    autor_slug = (b.get("autor_slug") or "").strip()
    if not autor_slug:
        # Vorschlag; Kollision nur, wenn Slug existiert UND auf andere Q-ID zeigt
        cand = config.suggest_author_slug(name) if name else "unbekannt"
        existing_qid = idx["authors"].get(cand)
        if existing_qid is not None and qid and existing_qid != qid:
            autor_slug = config.unique_author_slug(name)
            print(f"    Slug-Kollision: '{cand}' belegt -> '{autor_slug}'")
        else:
            autor_slug = cand
    print(f"    autor_slug = {autor_slug}")

    # --- 2. Autor anlegen falls neu ---
    author_path = os.path.join(config.author_dir(autor_slug), "author.json")
    if os.path.exists(author_path) and not FORCE:
        print(f"    Autor existiert -> ueberspringe author.json")
    else:
        _write_json(author_path, _author_json_template(
            autor_slug, name, qid,
            birth=b.get("_birth_year"), death=b.get("_death_year")))
        print(f"    + author.json")
    idx["authors"][autor_slug] = qid  # Index pflegen (Q-ID ggf. leer)

    # --- 3. Werk anlegen ---
    bdir = os.path.join(config.author_dir(autor_slug), "books", book_slug)
    book_path = os.path.join(bdir, "book.json")
    if os.path.exists(book_path) and not FORCE:
        print(f"    Werk existiert -> ueberspringe book.json")
    else:
        _write_json(book_path, _book_json_template(b, autor_slug))
        if not DRY:
            os.makedirs(os.path.join(bdir, "work"), exist_ok=True)
            os.makedirs(os.path.join(bdir, "output"), exist_ok=True)
        print(f"    + book.json (+ work/ output/)")
    idx["books"][book_slug] = autor_slug  # Index pflegen

    # --- 3b. werke_im_bestand am Autor ergaenzen ---
    if not DRY and os.path.exists(author_path):
        aj = json.load(open(author_path, encoding="utf-8"))
        if book_slug not in aj.get("werke_im_bestand", []):
            aj.setdefault("werke_im_bestand", []).append(book_slug)
            json.dump(aj, open(author_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # --- 4. Rohtext einlegen ---
    quelle = b.get("raw_quelle", "")
    txt_url = b.get("txt_url", "")
    ziel = os.path.join(bdir, "raw.txt")
    if os.path.exists(ziel) and not FORCE:
        print(f"    raw.txt existiert -> ueberspringe")
    elif quelle and os.path.exists(quelle):
        # lokale Datei kopieren
        if DRY:
            print(f"    [dry] wuerde Rohtext kopieren: {quelle} -> raw.txt")
        else:
            shutil.copy2(quelle, ziel)
            print(f"    + raw.txt (aus {os.path.basename(quelle)})")
    elif txt_url:
        # von Gutenberg (txt_url) herunterladen -- laeuft NUR lokal (Gutenberg-Zugang)
        if DRY:
            print(f"    [dry] wuerde herunterladen: {txt_url} -> raw.txt")
        else:
            try:
                import urllib.request
                req = urllib.request.Request(txt_url, headers={"User-Agent": "ReadLayer/1.0"})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = resp.read().decode("utf-8", errors="replace")
                open(ziel, "w", encoding="utf-8").write(data)
                print(f"    + raw.txt (heruntergeladen, {len(data)} Zeichen)")
            except Exception as e:
                print(f"    ! Download fehlgeschlagen ({type(e).__name__}: {e})")
                print(f"      URL: {txt_url} -- spaeter manuell einlegen")
    elif quelle:
        print(f"    ! raw_quelle nicht gefunden: {quelle} (spaeter manuell einlegen)")
    else:
        print(f"    (keine raw_quelle/txt_url -> raw.txt spaeter einlegen)")


GUTENDEX_API = "https://gutendex.com/books/"


def _display_name(gutendex_name: str) -> str:
    """Gutendex liefert 'Nachname, Vorname' (Sortierform).
    Dreht zu 'Vorname Nachname' fuer name_display. Bei nur einem Teil
    (Pseudonyme wie 'Twain, Mark' -> 'Mark Twain') ebenso. Mehrteilige
    Nachnamen ('Doyle, Arthur Conan' -> 'Arthur Conan Doyle') korrekt.
    Falls kein Komma: unveraendert lassen (schon richtig herum)."""
    if "," in gutendex_name:
        nach, vor = gutendex_name.split(",", 1)
        return f"{vor.strip()} {nach.strip()}".strip()
    return gutendex_name.strip()


def _book_from_gutendex(gid: str) -> dict:
    """Holt Werk-Metadaten von Gutendex (NUR Werk-Ebene + Autorname als
    Vorschlag). Harte Autorfakten kommen spaeter aus Stage 01 (Wikidata).
    Baut dasselbe Buch-Dict, das sonst aus der JSON-Eingabe kaeme."""
    url = GUTENDEX_API + str(gid)
    req = urllib.request.Request(url, headers={"User-Agent": "ReadLayer/1.0"})
    import time
    last = None
    for attempt in range(1, 5):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                d = json.load(resp)
            break
        except Exception as e:
            last = e
            print(f"    Versuch {attempt}/4 fehlgeschlagen ({type(e).__name__}); neuer Versuch ...")
            time.sleep(attempt * 3)
    else:
        raise last

    title = d.get("title", "").strip()
    langs = d.get("languages", []) or []
    lang = langs[0] if langs else ""

    authors = d.get("authors", []) or []
    if authors:
        raw_name = authors[0].get("name", "")
        name = _display_name(raw_name)
        death = authors[0].get("death_year")
        birth = authors[0].get("birth_year")
    else:
        name, death, birth = "", None, None

    # text/plain utf-8 Link finden
    txt_url = ""
    for k, v in (d.get("formats", {}) or {}).items():
        if k.startswith("text/plain") and "utf-8" in k.lower():
            txt_url = v
            break
    if not txt_url:  # Fallback: irgendein text/plain
        for k, v in (d.get("formats", {}) or {}).items():
            if k.startswith("text/plain"):
                txt_url = v
                break

    return {
        "book_slug": config.slugify(title),
        "autor_name": name,
        "_birth_year": birth,        # Vorbefuellung, Wikidata bestaetigt spaeter
        "_death_year": death,
        "titel_original": title,
        "originalsprache": lang,
        "erscheinungsjahr": None,    # Gutendex liefert kein verlaessliches Jahr
        "gutenberg_id": str(gid),
        "txt_url": txt_url,
    }


def main():
    # --- Modus B: Anlage per Gutenberg-ID (zieht Metadaten von Gutendex) ---
    if "--gutenberg" in sys.argv:
        gi = sys.argv.index("--gutenberg")
        try:
            gid = sys.argv[gi + 1]
        except IndexError:
            print("Aufruf: python s100_anlegen.py --gutenberg <id> [--dry] [--force]")
            sys.exit(1)
        print(f"Hole Metadaten von Gutendex fuer ID {gid} ...")
        try:
            b = _book_from_gutendex(gid)
        except Exception as e:
            print(f"! Gutendex-Abruf fehlgeschlagen ({type(e).__name__}: {e})")
            sys.exit(1)
        print(f"  Titel : {b['titel_original']}")
        print(f"  Autor : {b['autor_name']}  (*{b.get('_birth_year')} +{b.get('_death_year')})")
        print(f"  Sprache: {b['originalsprache']} | slug: {b['book_slug']}")
        if DRY:
            print(">>> DRY-RUN: es wird nichts geschrieben.\n")
        idx = config._load_index()
        anlege_buch(b, idx)
        if not DRY:
            config._save_index(idx)
            print(f"\nIndex aktualisiert: {os.path.relpath(config.INDEX_PATH, config.BASE_DIR)}")
        print("\nFertig." + ("  (DRY-RUN)" if DRY else ""))
        return

    # --- Modus A: Anlage per JSON-Eingabe (unveraendert) ---
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("Aufruf: python s100_anlegen.py <eingabe.json> [--dry] [--force]")
        print("   oder: python s100_anlegen.py --gutenberg <id> [--dry] [--force]")
        sys.exit(1)
    data = json.load(open(args[0], encoding="utf-8"))
    books = data.get("books", [])
    if not books:
        print("Keine Buecher in der Eingabe-Datei ('books'-Liste leer).")
        return

    if DRY:
        print(">>> DRY-RUN: es wird nichts geschrieben.\n")
    idx = config._load_index()
    print(f"Lege {len(books)} Buch/Buecher an ...")
    for b in books:
        anlege_buch(b, idx)
    if not DRY:
        config._save_index(idx)
        print(f"\nIndex aktualisiert: {os.path.relpath(config.INDEX_PATH, config.BASE_DIR)}")
    print("\nFertig." + ("  (DRY-RUN)" if DRY else ""))


if __name__ == "__main__":
    main()
