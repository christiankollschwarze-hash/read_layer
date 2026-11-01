"""STAGE 100 — Werk anlegen (Gutenberg; GATE_KATALOG.md, Phase 2 01.11.2026)
Funktion:     Legt ein Gutenberg-Werk an bzw. vervollstaendigt es: author.json, book.json, raw.txt,
              Eintrag in daten/index.json. Laeuft bei quelle = gutenberg (nach 095, vor 110).
Gate:         Index lesbar + Eintrag stimmig; raw.txt da; Gutenberg START/END-Marken; Laenge >= 5.000
              Zeichen (zwischen den Marken); Quellsprache in Sprachliste; EU-PD (Todesjahr Autor bzw.
              Uebersetzer + 70 < Jahr).
              auto bei allem gruen · Sprache nicht in Sprachliste -> Mensch (Anfrage) · Todesjahr fehlt/zu
              jung -> Mensch · Index defekt, Download/Marken/Laenge, author.json fehlt -> Stopp (Exit != 0).
Regler:       --gutenberg ID (Neuanlage aus Gutendex), --slug / --autor-slug, --textquelle URL|DATEI|vorhanden,
              --todesjahr N (Autor, manuell), --uebersetzer-todesjahr N, --force (Neu laden).
Befunde 100:  Download-Fehler -> Stopp statt Exit 0; Download atomar (keine halbe raw.txt);
              config._load_index wirft bei defekter Datei (kein Index-Verlust), Speichern atomar;
              PD-/Sprach-/Laengenpruefung in der Stage; Uebersetzer aus Gutendex; erscheinungsjahr
              kommt aus 110 (Wikidata P577), Gutendex liefert keins. Gutenberg-Rahmen entfernt weiter 120.
Kosten:       0 $ (kein LLM).

Aufruf:
  python tools/s100_anlegen.py --gutenberg 215 [--slug x] [--autor-slug y] [--dry]   Neuanlage + Gate
  python tools/s100_anlegen.py <werk> [--textquelle vorhanden] [--todesjahr 1916] [--force] [--wer CK]
  python tools/s100_anlegen.py <eingabe.json> [--dry] [--force]                        Altweg (JSON-Liste)
Exit: 0 auto, 2 Stopp, 3 Mensch, 1 Fehler.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import bestellung, gate, s080_mandant
from pipeline.manifest import json_atomar

STAGE = "100"
MIN_ZEICHEN = 5000
PD_JAHRE = 70
GUTENDEX_API = "https://gutendex.com/books/"
START = re.compile(r"\*{3}\s*START OF (?:THE |THIS )?PROJECT GUTENBERG", re.I)
ENDE = re.compile(r"\*{3}\s*END OF (?:THE |THIS )?PROJECT GUTENBERG", re.I)
TEXTARTEN = ("gutenberg", "url", "datei")


def _lj(pfad):
    with open(pfad, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------ Gutendex / Download
def _holen(url, timeout=90, versuche=4):
    """Bytes einer URL (mit Wiederholung). Tests ersetzen diese Funktion."""
    req = urllib.request.Request(url, headers={"User-Agent": "ReadLayer/1.0"})
    last = None
    for i in range(1, versuche + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as e:
            last = e
            if i < versuche:
                print(f"    Versuch {i}/{versuche} fehlgeschlagen ({type(e).__name__}); neuer Versuch ...")
                time.sleep(i * 3)
    raise last


def _display_name(gutendex_name):
    """'Nachname, Vorname' -> 'Vorname Nachname' ('Doyle, Arthur Conan' -> 'Arthur Conan Doyle')."""
    if "," in gutendex_name:
        nach, vor = gutendex_name.split(",", 1)
        return f"{vor.strip()} {nach.strip()}".strip()
    return gutendex_name.strip()


def gutendex(gid):
    """Werk-Metadaten (Werk-Ebene + Autorname/-jahre als Vorschlag; harte Fakten aus 110)."""
    d = json.loads(_holen(GUTENDEX_API + str(gid)).decode("utf-8"))
    title = (d.get("title") or "").strip()
    langs = d.get("languages") or []
    autoren = d.get("authors") or []
    a = autoren[0] if autoren else {}
    ue = (d.get("translators") or [])
    t = ue[0] if ue else {}
    txt_url = ""
    fm = d.get("formats") or {}
    for k, v in fm.items():
        if k.startswith("text/plain") and "utf-8" in k.lower():
            txt_url = v
            break
    if not txt_url:
        txt_url = next((v for k, v in fm.items() if k.startswith("text/plain")), "")
    return {
        "book_slug": config.slugify(title),
        "autor_name": _display_name(a.get("name", "")) if a else "",
        "_birth_year": a.get("birth_year"),
        "_death_year": a.get("death_year"),
        "titel_original": title,
        "originalsprache": langs[0] if langs else "",
        "erscheinungsjahr": None,          # Gutendex liefert kein Jahr -> 110 (P577)
        "gutenberg_id": str(gid),
        "txt_url": txt_url,
        "quell_uebersetzer": _display_name(t.get("name", "")) if t else "",
        "quell_uebersetzer_todesjahr": t.get("death_year") if t else None,
    }


def text_laden(quelle, ziel):
    """raw.txt aus URL oder lokaler Datei, atomar. Fehler -> Exception (Gate: Stopp)."""
    if re.match(r"^https?://", quelle or ""):
        data = _holen(quelle, timeout=60).decode("utf-8", errors="replace")
    elif quelle and os.path.isfile(quelle):
        with open(quelle, encoding="utf-8", errors="replace") as f:
            data = f.read()
    else:
        raise FileNotFoundError(f"Textquelle {quelle!r} nicht gefunden")
    tmp = f"{ziel}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data)
    os.replace(tmp, ziel)
    return len(data)


# ------------------------------------------------------------ Anlage (Autor, Werk, Index)
def _author_json_template(name, qid, birth=None, death=None):
    return {
        "wikidata_id": qid or "", "verified": False,
        "name_display": name, "name_sort": "",
        "geburtsjahr": birth, "todesjahr": death, "geburtsort": "",
        "wirkungssprache": "", "notable_works": [],
        "epoche": "", "stilrichtung": [], "bedeutung_kurz": "",
        "quelle_weich": "", "werke_im_bestand": [],
    }


def _book_json_template(b, autor_slug):
    lg = (b.get("originalsprache") or "").split("-")[0].lower()
    d = {
        "book_slug": b["book_slug"], "author_slug": autor_slug,
        "author_wikidata_id": b.get("wikidata_id_autor", "") or "",
        "work_wikidata_id": b.get("wikidata_id_werk", "") or "",
        "publisher": "<eigenes-label>",
        "titel_original": b.get("titel_original", ""),
        "originalsprache": b.get("originalsprache", ""),
        "erscheinungsjahr": b.get("erscheinungsjahr"),
        "gutenberg_id": b.get("gutenberg_id", ""),
        "quell_uebersetzer": b.get("quell_uebersetzer", "") or "",
        "quell_uebersetzer_todesjahr": b.get("quell_uebersetzer_todesjahr"),
        "thema_codes": [], "bisac_codes": [], "genre_eigen": "",
        "ton": "", "schauplatz": "", "essenz": "",
        "leseprobe_zitat": "", "inhaltshinweise": [], "sicherheit": "",
        "bedeutung_werk": "", "fassungen": [],
    }
    if b.get("gutenberg_id"):
        d["quelle"] = "gutenberg"
    if lg:
        d["quellsprache"] = lg
    if b.get("txt_url"):
        d["textquelle"] = {"art": "gutenberg", "quelle": b["txt_url"]}
    return d


def anlege_buch(b, idx, dry=False, force=False):
    """Autor (falls neu), Werk, Index, raw.txt. Rueckgabe (autor_slug, book_slug, download_fehler)."""
    titel = b.get("titel_original", "(ohne Titel)")
    book_slug = b.get("book_slug") or config.slugify(titel)
    name = (b.get("autor_name") or "").strip()
    qid = b.get("wikidata_id_autor", "") or ""
    print(f"\n[{book_slug}]  \"{titel}\"  — Autor: {name or '(unbekannt)'}")

    def schreib(pfad, data):
        if dry:
            print(f"    [dry] wuerde schreiben: {os.path.relpath(pfad, config.BASE_DIR)}")
        else:
            json_atomar(pfad, data, indent=2)

    autor_slug = (b.get("autor_slug") or "").strip()
    if not autor_slug:
        cand = config.suggest_author_slug(name) if name else "unbekannt"
        vorhanden = idx["authors"].get(cand)
        if vorhanden is not None and qid and vorhanden != qid:
            autor_slug = config.unique_author_slug(name)
            print(f"    Slug-Kollision: '{cand}' belegt -> '{autor_slug}'")
        else:
            autor_slug = cand
    print(f"    autor_slug = {autor_slug}")

    author_path = os.path.join(config.author_dir(autor_slug), "author.json")
    if os.path.exists(author_path) and not force:
        print("    Autor existiert -> ueberspringe author.json")
    else:
        schreib(author_path, _author_json_template(name, qid, b.get("_birth_year"), b.get("_death_year")))
        print("    + author.json")
    idx["authors"].setdefault(autor_slug, qid)
    if qid:
        idx["authors"][autor_slug] = qid

    bdir = os.path.join(config.author_dir(autor_slug), "books", book_slug)
    book_path = os.path.join(bdir, "book.json")
    if os.path.exists(book_path) and not force:
        print("    Werk existiert -> ueberspringe book.json")
    else:
        schreib(book_path, _book_json_template(b, autor_slug))
        if not dry:
            os.makedirs(os.path.join(bdir, "work"), exist_ok=True)
            os.makedirs(os.path.join(bdir, "output"), exist_ok=True)
        print("    + book.json (+ work/ output/)")
    idx["books"][book_slug] = autor_slug

    if not dry and os.path.exists(author_path):
        aj = _lj(author_path)
        if book_slug not in aj.get("werke_im_bestand", []):
            aj.setdefault("werke_im_bestand", []).append(book_slug)
            json_atomar(author_path, aj, indent=2)

    fehler = None
    quelle = b.get("raw_quelle") or b.get("txt_url") or ""
    ziel = os.path.join(bdir, "raw.txt")
    if os.path.exists(ziel) and not force:
        print("    raw.txt existiert -> ueberspringe")
    elif not quelle:
        print("    (keine raw_quelle/txt_url -> raw.txt spaeter einlegen)")
    elif dry:
        print(f"    [dry] wuerde Rohtext laden: {quelle} -> raw.txt")
    else:
        try:
            n = text_laden(quelle, ziel)
            print(f"    + raw.txt ({n} Zeichen)")
        except Exception as e:
            fehler = f"{type(e).__name__}: {e}"
            print(f"    ! Rohtext nicht geladen ({fehler})")
    return autor_slug, book_slug, fehler


# ------------------------------------------------------------ Gate 100
def text_rahmen(text):
    """(start, ende, kern) – Marken gefunden?, Text zwischen den Marken (sonst ganzer Text)."""
    s, e = START.search(text), ENDE.search(text)
    kern = text
    if s:
        nl = text.find("\n", s.end())
        kern = text[nl + 1 if nl >= 0 else s.end():]
    if e:
        m = ENDE.search(kern)
        kern = kern[:m.start()] if m else kern
    return bool(s), bool(e), kern


def _author_pfad(roh, ordner):
    a = roh.get("author_slug")
    if a:
        return os.path.join(config.author_dir(a), "author.json")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.normpath(ordner))), "author.json")


def pd_pruefen(g, aj, roh, jahr=None):
    """EU-PD: Todesjahr Autor bzw. Uebersetzer + 70 < Jahr. Fehlt/zu jung -> Mensch."""
    jahr = jahr or datetime.date.today().year
    tj = (aj or {}).get("todesjahr")
    if tj in (None, ""):
        g.pflicht("pd_autor", False, wert=None, bei_fehler="mensch", ruecksprung="100",
                  text="Todesjahr Autor fehlt (Regler --todesjahr oder Freigabe durch CK)")
    else:
        g.pflicht("pd_autor", int(tj) + PD_JAHRE < jahr, wert=int(tj), bei_fehler="mensch", ruecksprung="100",
                  text=f"EU-PD Autor: Todesjahr {tj} + {PD_JAHRE} < {jahr}")
    ue = (roh.get("quell_uebersetzer") or "").strip()
    if ue:
        utj = roh.get("quell_uebersetzer_todesjahr")
        if utj in (None, ""):
            g.pflicht("pd_uebersetzer", False, bei_fehler="mensch", ruecksprung="100",
                      text=f"Todesjahr Uebersetzer {ue} fehlt (Regler --uebersetzer-todesjahr)")
        else:
            g.pflicht("pd_uebersetzer", int(utj) + PD_JAHRE < jahr, wert=int(utj), bei_fehler="mensch",
                      ruecksprung="100", text=f"EU-PD Uebersetzer {ue}: Todesjahr {utj} + {PD_JAHRE} < {jahr}")


def pruefen(g, werk, ordner, roh, b, download_fehler=None, jahr=None):
    slug = os.path.basename(os.path.normpath(ordner))
    # Index
    try:
        idx = config._load_index()
        g.pflicht("index_lesbar", True, text="daten/index.json lesbar")
        a = roh.get("author_slug")
        eintrag = idx["books"].get(slug)
        if eintrag is None and a:
            idx["books"][slug] = a
            idx["authors"].setdefault(a, "")
            config._save_index(idx)
            g.hinweis("index_eintrag", False, wert=a, text=f"Index-Eintrag {slug} -> {a} fehlte, ergaenzt")
        else:
            g.pflicht("index_eintrag", eintrag == a, wert=eintrag, ruecksprung="100",
                      text=f"Index {slug} -> {eintrag!r} (book.json author_slug {a!r})")
    except config.IndexDefekt as e:
        g.pflicht("index_lesbar", False, wert=str(e), ruecksprung="100", text=f"Index defekt: {e}")
    # Autor
    ap = _author_pfad(roh, ordner)
    aj = None
    if os.path.exists(ap):
        try:
            aj = _lj(ap)
        except Exception as e:
            g.pflicht("author_json", False, wert=str(e), ruecksprung="100", text=f"author.json defekt: {e}")
    if aj is not None or not os.path.exists(ap):
        g.pflicht("author_json", aj is not None, ruecksprung="100",
                  text="author.json " + ("vorhanden" if aj is not None else "fehlt"))
    # Rohtext
    if download_fehler:
        g.pflicht("download", False, wert=download_fehler, ruecksprung="100",
                  text=f"Rohtext nicht geladen: {download_fehler} (Regler --textquelle / --force)")
    raw = os.path.join(ordner, "raw.txt")
    tq = roh.get("textquelle") or {}
    art = tq.get("art") or "gutenberg"
    g.metrik("textquelle", art)
    if not os.path.exists(raw):
        g.pflicht("raw_txt", False, ruecksprung="100", text="raw.txt fehlt (Regler --textquelle / --force)")
    else:
        with open(raw, encoding="utf-8", errors="replace") as f:
            text = f.read()
        g.pflicht("raw_txt", True, wert=len(text), text=f"raw.txt da ({len(text)} Zeichen)")
        s, e, kern = text_rahmen(text)
        mt = f"Gutenberg-Marken START {'ja' if s else 'nein'} / END {'ja' if e else 'nein'}"
        if art == "datei":
            g.hinweis("marken", s and e, wert=f"{s}/{e}", text=mt + " (lokale Datei)")
        else:
            g.pflicht("marken", s and e, wert=f"{s}/{e}", ruecksprung="100",
                      text=mt + " – unvollstaendig? --force; bereinigte Datei: --textquelle vorhanden")
        g.min("laenge", len(kern.strip()), MIN_ZEICHEN, bei_fehler="stopp", ruecksprung="100")
    # Sprache
    q = b.quellsprache
    g.pflicht("sprache", q in bestellung.sprachliste(), wert=q, bei_fehler="mensch", ruecksprung="100",
              text=f"Quellsprache {q!r} " + ("in Sprachliste" if q in bestellung.sprachliste()
                                              else "nicht in Sprachliste – Anfrage, Stopp bis freigeschaltet"))
    if "quellsprache" in b.abgeleitet and not roh.get("originalsprache"):
        g.hinweis("sprache_quelle", False, text="Quellsprache nicht angegeben (en angenommen)")
    # PD
    pd_pruefen(g, aj, roh, jahr)
    g.hinweis("erscheinungsjahr", bool(roh.get("erscheinungsjahr")), wert=roh.get("erscheinungsjahr"),
              text="erscheinungsjahr leer (folgt aus 110, Wikidata P577)")


def run(werk, wer=None, force=False, textquelle=None, todesjahr=None, uebersetzer_todesjahr=None,
        jahr=None):
    """Gate 100 fuer ein vorhandenes Werk (book.json). Laedt raw.txt nach, wenn sie fehlt oder --force.
    Rueckgabe auto | mensch | stopp."""
    wer = s080_mandant.nutzer(wer)
    ordner = bestellung.werkordner(werk)
    roh = bestellung.lesen(werk).roh
    jetzt = datetime.datetime.now().isoformat(timespec="seconds")
    if force or textquelle or todesjahr is not None or uebersetzer_todesjahr is not None:
        s080_mandant.darf(werk, "bestellen", wer)
    if todesjahr is not None:
        ap = _author_pfad(roh, ordner)
        aj = _lj(ap) if os.path.exists(ap) else None
        if aj is None:
            raise FileNotFoundError(f"author.json fehlt: {ap}")
        aj["todesjahr"] = int(todesjahr)
        aj["todesjahr_quelle"] = {"art": "manuell", "wer": wer, "wann": jetzt}
        json_atomar(ap, aj, indent=2)
    if uebersetzer_todesjahr is not None:
        roh = bestellung.feld_setzen(werk, quell_uebersetzer_todesjahr=int(uebersetzer_todesjahr)).roh

    raw = os.path.join(ordner, "raw.txt")
    fehler = None
    tq = None
    if textquelle == "vorhanden":
        if not os.path.exists(raw):
            raise FileNotFoundError("--textquelle vorhanden: raw.txt fehlt")
        tq = {"art": "datei", "quelle": "raw.txt", "wer": wer, "wann": jetzt}
    elif textquelle:
        art = "url" if re.match(r"^https?://", textquelle) else "datei"
        tq = {"art": art, "quelle": textquelle, "wer": wer, "wann": jetzt}
    if tq:
        roh = bestellung.feld_setzen(werk, textquelle=tq).roh
    if (textquelle and textquelle != "vorhanden") or force or not os.path.exists(raw):
        quelle = (roh.get("textquelle") or {}).get("quelle")
        try:
            if not quelle or quelle == "raw.txt":
                quelle = gutendex(roh.get("gutenberg_id"))["txt_url"]
                if not quelle:
                    raise ValueError("Gutendex liefert keinen text/plain-Link")
                roh = bestellung.feld_setzen(werk, textquelle={"art": "gutenberg", "quelle": quelle}).roh
            n = text_laden(quelle, raw)
            print(f"[100] raw.txt geladen ({n} Zeichen) aus {quelle}")
        except Exception as e:
            fehler = f"{type(e).__name__}: {e}"

    b = bestellung.lesen(werk)
    g = gate.Gate(werk, STAGE, ruecksprung="100", wer=wer)
    pruefen(g, werk, ordner, b.roh, b, fehler, jahr)
    e = g.entscheide()
    print(g.bericht())
    return e


def neu_anlegen(gid, slug=None, autor_slug=None, wer=None, dry=False, force=False):
    """--gutenberg ID: Gutendex -> Autor/Werk/Index/raw.txt, danach Gate 100. Rueckgabe Ergebnis."""
    print(f"Hole Metadaten von Gutendex fuer ID {gid} ...")
    b = gutendex(gid)
    if slug:
        b["book_slug"] = slug
    if autor_slug:
        b["autor_slug"] = autor_slug
    print(f"  Titel  : {b['titel_original']}")
    print(f"  Autor  : {b['autor_name']}  (*{b.get('_birth_year')} +{b.get('_death_year')})")
    if b.get("quell_uebersetzer"):
        print(f"  Uebers.: {b['quell_uebersetzer']}  (+{b.get('quell_uebersetzer_todesjahr')})")
    print(f"  Sprache: {b['originalsprache']} | slug: {b['book_slug']}")
    idx = config._load_index()
    a, s, fehler = anlege_buch(b, idx, dry=dry, force=force)
    if dry:
        print("\nFertig (DRY-RUN).")
        return None
    config._save_index(idx)
    werk = os.path.join(config.author_dir(a), "books", s)
    gg = gate.Gate(s, STAGE, ruecksprung="100", wer=s080_mandant.nutzer(wer))
    bb = bestellung.lesen(werk)
    pruefen(gg, werk, werk, bb.roh, bb, fehler)
    e = gg.entscheide()
    print(gg.bericht())
    print(f"\nWeiter: python run.py {s}")
    return e


def json_eingabe(pfad, dry=False, force=False):
    """Altweg: JSON-Liste {'books': [...]} anlegen (z. B. tools/pooh_vorbereiten.py). Ohne Gate."""
    with open(pfad, encoding="utf-8") as f:
        books = json.load(f).get("books", [])
    if not books:
        print("Keine Buecher in der Eingabe-Datei ('books'-Liste leer).")
        return 0
    idx = config._load_index()
    fehler = 0
    for b in books:
        fehler += bool(anlege_buch(b, idx, dry=dry, force=force)[2])
    if not dry:
        config._save_index(idx)
    print("\nFertig." + ("  (DRY-RUN)" if dry else "") + (f"  {fehler} Rohtext-Fehler" if fehler else ""))
    return 1 if fehler else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 100 Werk anlegen (Gutenberg)")
    ap.add_argument("werk", nargs="?", help="Book-ID/Werkordner oder Eingabe-JSON (Altweg)")
    ap.add_argument("--gutenberg", metavar="ID", help="Neuanlage aus Gutendex")
    ap.add_argument("--slug")
    ap.add_argument("--autor-slug")
    ap.add_argument("--textquelle", help="URL | lokale Datei | vorhanden (raw.txt bereinigt/lokal)")
    ap.add_argument("--todesjahr", type=int, help="Todesjahr Autor manuell (PD)")
    ap.add_argument("--uebersetzer-todesjahr", type=int)
    ap.add_argument("--force", action="store_true", help="Neu laden (raw.txt; Neuanlage: Dateien ueberschreiben)")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--wer")
    a = ap.parse_args(argv)
    try:
        if a.gutenberg:
            e = neu_anlegen(a.gutenberg, a.slug, a.autor_slug, a.wer, a.dry, a.force)
            return 0 if e is None else gate.EXIT[e]
        if not a.werk:
            ap.error("werk oder --gutenberg ID noetig")
        if a.werk.endswith(".json") and os.path.isfile(a.werk):
            return json_eingabe(a.werk, a.dry, a.force)
        e = run(a.werk, a.wer, a.force, a.textquelle, a.todesjahr, a.uebersetzer_todesjahr)
        return gate.EXIT[e]
    except config.IndexDefekt as e:
        print(f"! Index defekt: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
