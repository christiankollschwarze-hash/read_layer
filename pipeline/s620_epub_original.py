"""STAGE 620 — ePub Original
Funktion:     EPUB3 der Originalfassung im SOMNIO-Layout.
Wirkungsweise: Kapitel aus work/modernized, Cover, Klappentext, Titelseite, Colophon; zipfile-Verpackung.
Komponenten:  pipeline/s620_epub_original.py, Pillow
Zulieferer:   s120 Modernisierung, s600 Klappentext, s610 Cover
Abnehmer:     Auslieferung (fassungen/en/output/<werk>.epub), s630 (Gleiche Bausteine)
(Nomenklatur seit 18.10.2026, Uebersicht: docs/Pipeline_Strang_Matrix.xlsx)

--- Bisherige Beschreibung ---

READ LAYER — Stage 11: EPUB-Setzung (Katalog-Format)
====================================================
Erzeugt ein valides EPUB3 nach dem Vorbild der Public-Domain-Library/
Standard-Ebooks-Schule (EPUB3, kein NCX, alles unter epub/), aber mit
SOMNIO-Branding.

ARCHITEKTUR — bewusst zweigeteilt:
  1. INHALTSGEWINNUNG  (_extract_chapters_*): liefert [(titel, [absatz, ...]), ...].
     Aktuell einsprachig aus raw.txt. Die zweisprachige Variante (EN/DE)
     dockt SPAETER genau hier an -- ohne die Verpackung anzufassen.
  2. VERPACKUNG  (build_epub): nimmt Metadaten + Kapitel und schreibt das EPUB.

Aufruf wie die anderen Stages:  run(book_id).
Ausgabe:  books/<book_id>/output/<book_slug>.epub
Gutenberg ist aus dem Claude-Container gesperrt -> echter raw.txt-Lauf laeuft lokal.
"""

import os, re, io, json, html, uuid, base64, zipfile, datetime
from config import config

STAGE = "620"

# Stabiler UUID-Namensraum fuer deterministische Identifier ueber Neulaeufe hinweg.
_NS = uuid.uuid5(uuid.NAMESPACE_DNS, "readlayer.somnio")

# --- Cover-Branding ------------------------------------------------------
BG_COLOR    = getattr(config, "COVER_BG", "#faf8f4")   # Source of Truth: config.COVER_BG
TITLE_COLOR = "#9e3324"   # patiniertes Zinnoberrot; eine Zeile zum Aendern
# Projektweites Hai-Logo (CK legt somniosus_draft1.svg hier ab):
LOGO_PATH   = os.path.join(config.BASE_DIR, "assets", "somnio_logo.svg")
IMPRINT     = "SOMNIO PUBLISHING"

# BCP-47-Sprachkennung (knapp gehalten; bei Bedarf erweitern)
_BCP47 = {"en": "en", "de": "de", "fr": "fr", "es": "es", "it": "it", "ru": "ru"}


# ============================================================
# 1) INHALTSGEWINNUNG
# ============================================================
def _strip_boilerplate(t: str) -> str:
    for mk in ("*** START OF THE PROJECT GUTENBERG", "*** START OF THIS PROJECT GUTENBERG"):
        i = t.find(mk)
        if i != -1:
            nl = t.find("\n", i); t = t[nl + 1:] if nl != -1 else t; break
    for mk in ("*** END OF THE PROJECT GUTENBERG", "*** END OF THIS PROJECT GUTENBERG"):
        i = t.find(mk)
        if i != -1:
            t = t[:i]; break
    # Sicherheitsnetz: Lizenz-/Nachspann-Bloecke, die manchmal trotzdem anhaengen.
    for mk in ("START: FULL LICENSE", "*** START OF THE FULL PROJECT GUTENBERG LICENSE",
               "THE FULL PROJECT GUTENBERG LICENSE", "End of the Project Gutenberg"):
        i = t.find(mk)
        if i != -1:
            t = t[:i]; break
    return t.strip()


_CHAP_RE = re.compile(r"^\s*(chapter|kapitel)\b", re.IGNORECASE)

def _is_heading_block(block: str) -> bool:
    """Ein Block ist eine Ueberschrift, wenn er einzeilig, kurz und ueberwiegend
    Grossbuchstaben ist (Gutenberg-Konvention) ODER mit 'Chapter/Kapitel' beginnt."""
    if "\n" in block:
        return False
    s = block.strip()
    if not s or len(s) > 60:
        return False
    if _CHAP_RE.match(s):
        return True
    # Echte Titel enden NICHT auf einen Punkt; Signaturen/Saetze schon
    # ("HENRY JEKYLL.", "HASTIE LANYON.", "H.J.", "1.F.", "DAMAGE.").
    if s.rstrip("\u201d\u2019\"' ").endswith("."):
        return False
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 2:
        return False
    upper = sum(1 for c in letters if c.isupper())
    return upper / len(letters) >= 0.8

_SMALL = {"a","an","and","the","of","or","to","in","on","at","by","for","with",
          "von","der","die","das","und","oder","im","zu"}

def _titlecase(s: str) -> str:
    """ALL-CAPS-Ueberschrift -> lesbare Schreibung. Gemischte Schreibung bleibt."""
    letters = [c for c in s if c.isalpha()]
    if not letters or sum(c.isupper() for c in letters) / len(letters) < 0.9:
        return s  # nicht durchgaengig Caps -> unveraendert lassen
    words = s.lower().split()
    out = []
    for i, w in enumerate(words):
        out.append(w if (w in _SMALL and i != 0) else (w[:1].upper() + w[1:]))
    return " ".join(out)

def _split_chapters(text: str):
    """Liefert [(titel, [absatz, ...]), ...]. Marker-Konvention zuerst, sonst Heuristik."""
    marker = config.MARKERS.get("chapter", "###CHAPTER###")
    chapters = []

    if marker in text:
        for seg in text.split(marker)[1:]:
            lines = seg.strip("\n").split("\n", 1)
            title = lines[0].strip()
            body = lines[1] if len(lines) > 1 else ""
            chapters.append((title or f"Chapter {len(chapters)+1}", _paragraphs(body)))
        if chapters:
            return chapters

    # Heuristik (blockbasiert):
    #  - Echte Ueberschrift = Caps-Block, dem substanzieller Fliesstext folgt
    #    (bevor die naechste Ueberschrift kommt). Das verwirft TOC-Listen
    #    (Ueberschrift folgt auf Ueberschrift) UND den Vorspann (Titel/Autor).
    #  - Caps-Bloecke OHNE folgenden Fliesstext (z.B. Signaturen) bleiben Absatz.
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    is_hr = lambda b: bool(re.fullmatch(r"[\*\u2014\-\s]{3,}", b))
    heads = [(_is_heading_block(b) and not is_hr(b)) for b in blocks]

    def _body_follows(i: int) -> bool:
        for j in range(i + 1, len(blocks)):
            if heads[j]:
                return False
            if not is_hr(blocks[j]) and len(blocks[j]) >= 120:
                return True
        return False

    cur = None
    started = False
    for i, b in enumerate(blocks):
        if heads[i] and _body_follows(i):
            cur = (_titlecase(b), [])
            chapters.append(cur)
            started = True
        elif not started:
            continue  # Vorspann / Inhaltsverzeichnis vor dem 1. echten Kapitel -> weg
        elif is_hr(b):
            if cur:
                cur[1].append("\u2014\u2014HR\u2014\u2014")
        else:
            cur[1].append(" ".join(l.strip() for l in b.split("\n")))

    if not chapters:
        chapters = [("", _paragraphs(text))]
    return chapters

def _paragraphs(body: str):
    out = []
    for block in re.split(r"\n\s*\n", body):
        b = block.strip()
        if b:
            out.append(" ".join(l.strip() for l in b.split("\n")))
    return out

def _rewrap(text: str) -> str:
    """Entfasert hart umbrochenen Text zu echten Absatz-Bloecken.
    Feste Regel fuer ALLE Titel -- robust gegen normal UND doppelt
    zeilengeschaltete Gutenberg-Dateien:
      - normal (wenige Leerzeilen): Leerzeile = Absatzgrenze, Zeilen verbinden.
      - doppelt (Leerzeile nach jeder Zeile): Fuell-Heuristik -- eine kurze
        Schlusszeile beendet den Absatz; 2+ Leerzeilen sind harte Grenzen.
    Ueberschriften (kurze Caps-Zeilen) bleiben eigene Bloecke.
    Ausgabe: Bloecke durch genau eine Leerzeile getrennt."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    nonempty = [l for l in lines if l.strip()]
    if not nonempty:
        return text
    blanks = sum(1 for l in lines if not l.strip())
    double_spaced = blanks >= 0.6 * len(nonempty)
    lens = sorted(len(l.rstrip()) for l in nonempty)
    wrapw = lens[int(len(lens) * 0.9)]          # 90%-Perzentil der Zeilenlaenge
    thresh = max(40, int(wrapw * 0.66))         # "kurze" Zeile -> Absatzende

    blocks, cur, blank_run = [], [], 0
    def flush():
        if cur:
            blocks.append(" ".join(cur)); cur.clear()

    for l in lines:
        s = l.strip()
        if not s:
            blank_run += 1
            if not double_spaced:
                flush()
            elif blank_run >= 2:
                flush()
            continue
        blank_run = 0
        if _is_heading_block(s):     # Ueberschrift steht allein
            flush(); blocks.append(s); continue
        cur.append(s)
        if double_spaced and len(l.rstrip()) < thresh:
            flush()                  # kurze Schlusszeile beendet den Absatz
    flush()
    return "\n\n".join(blocks)


def _extract_chapters_from_raw(book_id: str):
    rp = config.raw_path(book_id)
    if not os.path.exists(rp):
        raise FileNotFoundError(f"Kein Rohtext: {rp}")
    text = _strip_boilerplate(open(rp, encoding="utf-8", errors="ignore").read())
    text = _rewrap(text)             # FESTE REGEL: entfasern vor der Kapitel-Erkennung
    return _split_chapters(text)


# Mobil-Absaetze: lange Absaetze an Satzgrenzen in handygerechte Haeppchen teilen.
MOBILE_MAX_CHARS = 320

def _split_for_mobile(paragraphs, max_chars: int = MOBILE_MAX_CHARS):
    out = []
    for p in paragraphs:
        if p == "\u2014\u2014HR\u2014\u2014" or len(p) <= max_chars:
            out.append(p); continue
        sentences = re.split(r"(?<=[.!?\u201d\u2019])\s+", p)
        chunk = ""
        for s in sentences:
            if chunk and len(chunk) + len(s) + 1 > max_chars:
                out.append(chunk); chunk = s
            else:
                chunk = (chunk + " " + s).strip()
        if chunk:
            out.append(chunk)
    return out


def _is_modernized(book_id: str) -> bool:
    """True, wenn ein modernisierter Text vorliegt (work/modernized/chapter-*.json).
    22.10.2026: eigenes Werk (rechte=eigene) ist nie "modernisiert" (Kapitel stammen aus dem Import)."""
    if config.eigene_rechte(book_id):
        return False
    mod_dir = os.path.join(config.work_dir(book_id), "modernized")
    return (os.path.isdir(mod_dir) and
            any(re.fullmatch(r"chapter-\d+\.json", f) for f in os.listdir(mod_dir)))


# ============================================================
# FRONT-MATTER-STRIPPER (gemeinsam fuer EPUB + Audio-Quelle)
# Entfernt den werkinternen Titelblock am Anfang des ERSTEN Kapitels
# (doppelter Titel, "by Autor", Attribution, Epigraph), der sonst getaggt+
# vertont und im EPUB doppelt gezeigt wird. Konservativ: greift nur bei
# bestaetigtem Titel/Autor-Duplikat und nie ueber den ersten echten Absatz.
# ============================================================
_FM_MIN_PROSE = 200     # ein "echter" Erzaehl-Absatz ist lang
_FM_SCAN_LIMIT = 15     # nur ganz am Anfang suchen

def _fm_norm(s: str) -> str:
    return re.sub(r"[^\w]", "", (s or "").lower())

def strip_leading_front_matter(paragraphs, title: str = "", author: str = ""):
    """Liefert die Absatzliste OHNE fuehrenden Titelblock. Strippt nur, wenn ein
    Titel- oder 'by Autor'-Duplikat den Block bestaetigt; hoert am ersten echten
    (>= _FM_MIN_PROSE Zeichen) Prosa-Absatz auf; tut nichts, wenn keiner kommt."""
    hr = "\u2014\u2014HR\u2014\u2014"
    paras = list(paragraphs)
    prose_start = None
    for i, p in enumerate(paras[:_FM_SCAN_LIMIT]):
        if p and p != hr and len(p) >= _FM_MIN_PROSE and re.search(r"[a-z\u00e0-\u00ff]", p):
            prose_start = i
            break
    if not prose_start:                 # 0 oder None -> nichts strippen
        return paras
    head = paras[:prose_start]
    tnorm = _fm_norm(title)
    confirmed = any(
        (tnorm and _fm_norm(p) == tnorm) or re.match(r"(?i)^\s*by\s+\w", p or "")
        for p in head
    )
    return paras[prose_start:] if confirmed else paras

def strip_trailing_end_marker(paragraphs):
    """Entfernt einen blanken Schluss-Marker ('THE END', 'FINIS') am Werkende.
    Echter Inhalt (z.B. 'Postscript'-Abschnitte) bleibt stehen."""
    paras = list(paragraphs)
    while paras:
        last = paras[-1].strip().rstrip(".")
        if last.upper() in ("THE END", "FINIS", "END") and len(last) <= 8:
            paras.pop()
        else:
            break
    return paras


def _load_chapters(book_id: str):
    """Kapitel fuer EPUB/Uebersetzung: modernisierten Text bevorzugen (work/modernized/),
    sonst Rohtext. Danach IMMER Mobil-Absaetze anwenden (Default)."""
    mod_dir = os.path.join(config.work_dir(book_id), "modernized")
    chapters = None
    s6 = config.work_path(book_id, "400_regie")
    if os.path.exists(s6) and (json.load(open(s6, encoding="utf-8")).get("meta") or {}).get("modus") == "drama":
        # Drama: Akte/Repliken aus dem bereinigten 400_regie (gleiche Gliederung wie die Uebersetzung)
        from pipeline.s630_epub_zielsprache import _build_chapters_from_stage06
        chapters = _build_chapters_from_stage06(book_id, config.SOURCE_LANGUAGE)
    if chapters is None and os.path.isdir(mod_dir):
        files = [f for f in os.listdir(mod_dir) if re.fullmatch(r"chapter-\d+\.json", f)]
        if files:
            files.sort(key=lambda f: int(re.search(r"\d+", f).group()))
            chapters = []
            for f in files:
                d = json.load(open(os.path.join(mod_dir, f), encoding="utf-8"))
                chapters.append((d["title"], d["paragraphs"]))
    if chapters is None:
        chapters = _extract_chapters_from_raw(book_id)

    # Front-Matter NUR im ersten Kapitel entfernen (Titelblock + Schluss-Marker).
    if chapters:
        try:
            meta = _gather_meta(book_id)
            t0, p0 = chapters[0]
            p0 = strip_leading_front_matter(p0, meta.get("title", ""), meta.get("author", ""))
            chapters[0] = (t0, p0)
            lt, lp = chapters[-1]
            chapters[-1] = (lt, strip_trailing_end_marker(lp))
        except Exception:
            pass

    return [(t, _split_for_mobile(paras)) for t, paras in chapters]




def _find_raster_cover(book_id: str):
    """Sucht ein von Stage 12 erzeugtes Cover-Bild. Liefert dict oder None."""
    img_dir = os.path.join(config.book_dir(book_id), "images")
    for name, media in (("cover.png", "image/png"), ("cover.jpg", "image/jpeg"),
                        ("cover.jpeg", "image/jpeg"), ("cover.webp", "image/webp")):
        p = os.path.join(img_dir, name)
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return {"name": name, "media": media, "data": open(p, "rb").read()}
    return None


# ============================================================
# 2) VERPACKUNG — XHTML-Bausteine
# ============================================================
def _esc(s: str) -> str:
    return html.escape(s, quote=False)

_HTML_OPEN = ('<?xml version="1.0" encoding="utf-8"?>\n'
              '<html xmlns="http://www.w3.org/1999/xhtml" '
              'xmlns:epub="http://www.idpf.org/2007/ops" '
              'epub:prefix="z3998: http://www.daisy.org/z3998/2012/vocab/structure/#" '
              'xml:lang="{lang}">\n')

def _chapter_xhtml(idx: int, title: str, paragraphs, lang: str) -> str:
    head_title = _esc(title) if title else f"Chapter {idx}"
    body = []
    for p in paragraphs:
        if p == "\u2014\u2014HR\u2014\u2014":
            body.append("\t\t\t<hr/>")
        else:
            body.append(f"\t\t\t<p>{_esc(p)}</p>")
    # Kein sichtbarer Titel hier -- der steht auf dem eigenen Kapitel-Titelblatt.
    return (_HTML_OPEN.format(lang=lang) +
            f"\t<head>\n\t\t<title>{head_title}</title>\n"
            '\t\t<link href="../css/core.css" rel="stylesheet" type="text/css"/>\n'
            '\t\t<link href="../css/local.css" rel="stylesheet" type="text/css"/>\n'
            "\t</head>\n"
            '\t<body epub:type="bodymatter z3998:fiction">\n'
            f'\t\t<section id="chapter-{idx}-body">\n'
            + "\n".join(body) +
            "\n\t\t</section>\n\t</body>\n</html>\n")

def _chapter_title_xhtml(idx: int, title: str, lang: str) -> str:
    """Eigenes Kapitel-Titelblatt: prominenter Titel, Hai-Signet klein unten mittig."""
    head_title = _esc(title) if title else f"Chapter {idx}"
    signet = _logo_inline_svg("#8a7f70")  # reduziertes Graubraun
    return (_HTML_OPEN.format(lang=lang) +
            f"\t<head>\n\t\t<title>{head_title}</title>\n"
            '\t\t<link href="../css/core.css" rel="stylesheet" type="text/css"/>\n'
            '\t\t<link href="../css/local.css" rel="stylesheet" type="text/css"/>\n'
            "\t</head>\n"
            '\t<body epub:type="bodymatter z3998:fiction">\n'
            f'\t\t<section id="chapter-{idx}" epub:type="chapter" class="chapter-title-page">\n'
            f'\t\t\t<h1 epub:type="title">{head_title}</h1>\n'
            f'\t\t\t{signet}\n'
            "\t\t</section>\n\t</body>\n</html>\n")

def _blurb_xhtml(stage09: dict, lang: str, lang_attr: str, modernized: bool = False) -> str:
    """Klappentext-Seite (Vorsatz). Sprache = Output-Sprache; Fallback Quellsprache."""
    blurb = stage09.get("blurb", {})
    def pick(sent):
        return (sent.get(lang) or sent.get(config.SOURCE_LANGUAGE)
                or (next(iter(sent.values()), "") if sent else ""))
    koeder     = [pick(s) for s in blurb.get("koeder", []) if pick(s)]
    einordnung = [pick(s) for s in blurb.get("einordnung", []) if pick(s)]
    autorb     = [pick(s) for s in blurb.get("autor", []) if pick(s)]

    body = ['\t\t\t<section epub:type="frontmatter" class="blurb">']
    for q in koeder:
        body.append(f'\t\t\t\t<p class="epigraph">{_esc(q)}</p>')
    if koeder and (einordnung or autorb):
        body.append("\t\t\t\t<hr/>")
    for p in einordnung:
        body.append(f"\t\t\t\t<p>{_esc(p)}</p>")
    if autorb:
        body.append("\t\t\t\t<hr/>")
        for p in autorb:
            body.append(f'\t\t\t\t<p class="author-note">{_esc(p)}</p>')
    if modernized:
        note = _MOD_NOTE.get(lang, _MOD_NOTE["en"])
        body.append(f'\t\t\t\t<p class="mod-note">{_esc(note)}</p>')
    body.append("\t\t\t</section>")

    return (_HTML_OPEN.format(lang=lang_attr) +
            "\t<head>\n\t\t<title>About</title>\n"
            '\t\t<link href="../css/core.css" rel="stylesheet" type="text/css"/>\n'
            '\t\t<link href="../css/local.css" rel="stylesheet" type="text/css"/>\n'
            "\t</head>\n"
            '\t<body epub:type="frontmatter">\n'
            + "\n".join(body) +
            "\n\t</body>\n</html>\n")

_MOD_NOTE = {
    "en": "A gently modernized edition \u2014 clearer sentences and contemporary "
          "vocabulary, with the story left intact.",
    "de": "Eine behutsam modernisierte Ausgabe \u2014 klarere S\u00e4tze und "
          "zeitgem\u00e4\u00dfes Vokabular, die Geschichte unangetastet.",
}

def _titlepage_xhtml(title: str, author: str, lang: str) -> str:
    return (_HTML_OPEN.format(lang=lang) +
            "\t<head>\n\t\t<title>Titlepage</title>\n"
            '\t\t<link href="../css/core.css" rel="stylesheet" type="text/css"/>\n'
            '\t\t<link href="../css/local.css" rel="stylesheet" type="text/css"/>\n'
            "\t</head>\n"
            '\t<body epub:type="frontmatter">\n'
            '\t\t<section id="titlepage" epub:type="titlepage">\n'
            f'\t\t\t<h1 epub:type="title">{_esc(title)}</h1>\n'
            f'\t\t\t<p epub:type="z3998:author">{_esc(author)}</p>\n'
            '\t\t\t<p class="imprint">SOMNIO</p>\n'
            "\t\t</section>\n\t</body>\n</html>\n")

def _cover_xhtml(lang: str, cover_file: str = "cover.svg") -> str:
    return (_HTML_OPEN.format(lang=lang) +
            "\t<head>\n\t\t<title>Cover</title>\n"
            '\t\t<link href="../css/local.css" rel="stylesheet" type="text/css"/>\n'
            "\t</head>\n"
            '\t<body epub:type="cover">\n'
            '\t\t<section id="cover" epub:type="cover">\n'
            f'\t\t\t<img src="../images/{cover_file}" alt="Cover" class="cover-image"/>\n'
            "\t\t</section>\n\t</body>\n</html>\n")

_COLOPHON = {
    "en": {"head": "Colophon",
           "source": "This ebook is based on a transcription from {src}.",
           "rights": "The source text is believed to be in the public domain. "
                     "This edition is produced by SOMNIO and dedicated to the public "
                     "domain where applicable.",
           "source_mod": "This is a gently modernized edition, revised by SOMNIO from a "
                         "public-domain text transcribed by {src}.",
           "rights_mod": "The modernization and this edition are \u00a9 SOMNIO. "
                         "The underlying source text is in the public domain.",
           "gutenberg": "Project Gutenberg",
           "rights_own": "\u00a9 {year} SOMNIO. All rights reserved."},
    "de": {"head": "Impressum",
           "source": "Dieses E-Book basiert auf einer Transkription von {src}.",
           "rights": "Der Quelltext gilt als gemeinfrei. Diese Ausgabe wurde von "
                     "SOMNIO erstellt und, soweit zutreffend, der Gemeinfreiheit gewidmet.",
           "source_mod": "Dies ist eine behutsam modernisierte Ausgabe, von SOMNIO auf "
                         "Basis eines gemeinfreien, von {src} transkribierten Textes \u00fcberarbeitet.",
           "rights_mod": "Die Modernisierung und diese Ausgabe sind \u00a9 SOMNIO. "
                         "Der zugrunde liegende Quelltext ist gemeinfrei.",
           "gutenberg": "Project Gutenberg",
           "rights_own": "\u00a9 {year} SOMNIO. Alle Rechte vorbehalten."},
}

def _colophon_xhtml(title: str, author: str, source_url: str, lang: str,
                    modernized: bool = False, own_year=None) -> str:
    L = _COLOPHON.get(lang, _COLOPHON["en"])
    s_key = "source_mod" if modernized else "source"
    r_key = "rights_mod" if modernized else "rights"
    rights_txt = L[r_key]
    if own_year is not None:                  # 22.10.2026: eigenes Werk -> keine Gemeinfreiheit, keine Quelle
        source_url = ""
        rights_txt = L["rights_own"].replace("{year}", str(own_year))
    if source_url:
        link = f'<a href="{_esc(source_url)}">{L["gutenberg"]}</a>'
        src = "\t\t\t<p>" + L[s_key].replace("{src}", link) + "</p>\n"
    else:
        src = ""
    return (_HTML_OPEN.format(lang=lang) +
            f"\t<head>\n\t\t<title>{_esc(L['head'])}</title>\n"
            '\t\t<link href="../css/core.css" rel="stylesheet" type="text/css"/>\n'
            '\t\t<link href="../css/local.css" rel="stylesheet" type="text/css"/>\n'
            "\t</head>\n"
            '\t<body epub:type="backmatter">\n'
            '\t\t<section id="colophon" epub:type="colophon">\n'
            f'\t\t\t<h2 epub:type="title">{_esc(L["head"])}</h2>\n'
            '\t\t\t<p class="imprint">SOMNIO</p>\n'
            f"\t\t\t<p><i>{_esc(title)}</i><br/>{_esc(author)}</p>\n"
            f"{src}"
            f'\t\t\t<p>{_esc(rights_txt)}</p>\n'
            "\t\t</section>\n\t</body>\n</html>\n")

def _nav_xhtml(title: str, chapters, lang: str, has_blurb: bool = False) -> str:
    items = []
    if has_blurb:
        items.append('\t\t\t\t<li><a href="text/blurb.xhtml">About this Book</a></li>')
    items.append('\t\t\t\t<li><a href="text/titlepage.xhtml">Titlepage</a></li>')
    for i, (ctitle, _) in enumerate(chapters, 1):
        label = _esc(ctitle) if ctitle else f"Chapter {i}"
        items.append(f'\t\t\t\t<li><a href="text/chapter-{i}-title.xhtml">{label}</a></li>')
    items.append('\t\t\t\t<li><a href="text/colophon.xhtml">Colophon</a></li>')
    toc = "\n".join(items)
    return (_HTML_OPEN.format(lang=lang) +
            "\t<head>\n\t\t<title>Table of Contents</title>\n"
            '\t\t<link href="css/local.css" rel="stylesheet" type="text/css"/>\n'
            "\t</head>\n"
            '\t<body epub:type="frontmatter">\n'
            '\t\t<nav id="toc" epub:type="toc">\n'
            '\t\t\t<h2 epub:type="title">Table of Contents</h2>\n'
            f"\t\t\t<ol>\n{toc}\n\t\t\t</ol>\n"
            "\t\t</nav>\n"
            '\t\t<nav id="landmarks" epub:type="landmarks" hidden="hidden">\n'
            "\t\t\t<ol>\n"
            '\t\t\t\t<li><a href="text/titlepage.xhtml" epub:type="title-page">Titlepage</a></li>\n'
            '\t\t\t\t<li><a href="text/chapter-1-title.xhtml" epub:type="bodymatter">Beginning</a></li>\n'
            "\t\t\t</ol>\n\t\t</nav>\n"
            "\t</body>\n</html>\n")

def _wrap(t: str, limit: int):
    words, lines, cur = t.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= limit or not cur:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines

def _logo_fragment(x, y, w, h, color):
    """Hai-Signet aus assets/somnio_logo.svg als verschachteltes <svg> (eingefaerbt)."""
    if not os.path.exists(LOGO_PATH):
        return ""
    raw = open(LOGO_PATH, encoding="utf-8").read()
    m = re.search(r'viewBox="([^"]+)"', raw)
    vb = m.group(1) if m else "0 0 1280 714"
    g = re.search(r"(<g\b.*?</g>)", raw, re.S)
    inner = g.group(1) if g else ""
    inner = re.sub(r'fill="#0{3,6}"', f'fill="{color}"', inner)
    return (f'<svg x="{x}" y="{y}" width="{w}" height="{h}" viewBox="{vb}" '
            f'preserveAspectRatio="xMidYMid meet">{inner}</svg>')

def _logo_inline_svg(color: str, width: int = 130) -> str:
    """Eigenstaendiges Signet fuers Kapitel-Titelblatt mit FESTEN Maszen
    (manche Reader rechnen height aus dem viewBox nicht aus -> sonst Hoehe 0)."""
    if not os.path.exists(LOGO_PATH):
        return ""
    raw = open(LOGO_PATH, encoding="utf-8").read()
    m = re.search(r'viewBox="([^"]+)"', raw)
    vb = m.group(1) if m else "0 0 1280 714"
    try:
        _, _, vbw, vbh = (float(x) for x in vb.split())
        height = max(1, round(width * vbh / vbw))
    except Exception:
        height = round(width * 0.56)
    g = re.search(r"(<g\b.*?</g>)", raw, re.S)
    inner = re.sub(r'fill="#0{3,6}"', f'fill="{color}"', g.group(1) if g else "")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" class="signet" width="{width}" height="{height}" viewBox="{vb}" '
            f'preserveAspectRatio="xMidYMid meet" role="img" aria-label="SOMNIO">{inner}</svg>')

LANG_LABEL = {
    "en": "English Edition", "de": "Deutsche Ausgabe", "fr": "\u00c9dition fran\u00e7aise",
    "es": "Edici\u00f3n espa\u00f1ola", "it": "Edizione italiana",
}

_FONT_DIR = os.path.join(config.BASE_DIR, "assets", "fonts")
# Font-Aufloesung: gebuendelt (assets/fonts) -> Windows-Georgia -> System-DejaVu -> PIL-Default.
_FONT_CANDIDATES = {
    "bold":  [os.path.join(_FONT_DIR, "DejaVuSerif-Bold.ttf"), "C:/Windows/Fonts/georgiab.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"],
    "reg":   [os.path.join(_FONT_DIR, "DejaVuSerif.ttf"), "C:/Windows/Fonts/georgia.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"],
    "ital":  [os.path.join(_FONT_DIR, "DejaVuSerif-Italic.ttf"), "C:/Windows/Fonts/georgiai.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf"],
}

def _hex_rgb(c: str):
    c = c.lstrip("#")
    return tuple(int(c[i:i+2], 16) for i in (0, 2, 4))

def _cover_font(style: str, size: int):
    from PIL import ImageFont
    for path in _FONT_CANDIDATES.get(style, []):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

def _compose_cover_raster(title: str, author: str, cover: dict | None, lang: str = "en",
                          sprecher: str = "", imprint: str = "") -> bytes | None:
    """Komponiert das Cover als RASTER (JPEG) mit Pillow -- Illustration + Titel
    (sprachbewusst) + Autor + Sprachlabel + Wortmarke. Das ist das cover-image,
    das App-Reader fuers Regal-Thumbnail nutzen (SVG wird dort nicht gerendert).
    Liefert JPEG-Bytes; None, wenn Pillow fehlt (Aufrufer faellt dann auf SVG zurueck)."""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None

    W, H = 1000, 1500
    C = _hex_rgb(TITLE_COLOR)
    bg = _hex_rgb(BG_COLOR)

    if cover:
        from io import BytesIO
        base = Image.open(BytesIO(cover["data"])).convert("RGBA")
        scale = max(W / base.width, H / base.height)          # cover/slice auf 2:3
        base = base.resize((round(base.width * scale), round(base.height * scale)))
        l = (base.width - W) // 2; t = (base.height - H) // 2
        base = base.crop((l, t, l + W, t + H))
    else:
        base = Image.new("RGBA", (W, H), (*bg, 255))

    d = ImageDraw.Draw(base)

    def scrim(box, alpha):
        x0, y0, x1, y1 = box
        ov = Image.new("RGBA", (max(1, x1 - x0), max(1, y1 - y0)), (*bg, int(255 * alpha)))
        base.alpha_composite(ov, (x0, y0))

    def center(y, s, font):
        bb = d.textbbox((0, 0), s, font=font)
        d.text((W // 2 - (bb[2] - bb[0]) / 2, y), s, font=font, fill=C)

    # --- Titel oben links: Schriftgroesse so waehlen, dass die breiteste Zeile passt ---
    avail = W - 110
    tlines, fs = _wrap(title, 16), 84
    for size in (84, 72, 64, 56, 48):
        fb = _cover_font("bold", size)
        lines = _wrap(title, 16)
        widest = max((d.textbbox((0, 0), l, font=fb)[2] for l in lines), default=0)
        if widest <= avail:
            tlines, fs = lines, size; break
    fb = _cover_font("bold", fs)
    lh = int(fs * 1.12); top = 70
    scrim((40, top - 10, W - 40, top + len(tlines) * lh + 30), 0.55)
    for i, line in enumerate(tlines):
        d.text((70, top + i * lh), line, font=fb, fill=C)

    # --- Fuss zentriert: Autor -> Sprachlabel (kursiv) -> Sprecher (kursiv) -> Verlag ---
    scrim((40, 1150, W - 40, 1430), 0.55)
    center(1170, author, _cover_font("reg", 44))
    label = LANG_LABEL.get(lang)
    if label:
        center(1236, label, _cover_font("ital", 28))
    if sprecher:
        sf = _cover_font("ital", 28)
        while d.textbbox((0, 0), sprecher, font=sf)[2] > W - 140 and sf.size > 18:
            sf = _cover_font("ital", sf.size - 2)
        center(1278, sprecher, sf)
    center(1340, imprint or IMPRINT, _cover_font("reg", 32))

    from io import BytesIO
    buf = BytesIO()
    base.convert("RGB").save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def _compose_cover_svg(title: str, author: str, cover: dict | None, lang: str = "en") -> str:
    """Selbsttragendes Cover-SVG (2:3): vollflaechiges Bild (base64) ODER Creme,
    darueber Titel (links oben), Autor -> Sprachlabel -> Wortmarke -> Hai (unten)."""
    W, H = 1000, 1500
    C = TITLE_COLOR
    out = ['<?xml version="1.0" encoding="utf-8"?>',
           f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           f'viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet">']

    if cover:
        b64 = base64.b64encode(cover["data"]).decode("ascii")
        out.append(f'<image x="0" y="0" width="{W}" height="{H}" '
                   f'preserveAspectRatio="xMidYMid slice" '
                   f'xlink:href="data:{cover["media"]};base64,{b64}"/>')
    else:
        out.append(f'<rect width="{W}" height="{H}" fill="{BG_COLOR}"/>')

    # --- Titel: links oben, prominent, mit dezentem Creme-Schleier ---
    tlines = _wrap(title, 16)
    fs = 84 if max(len(l) for l in tlines) <= 14 else 72
    lh = int(fs * 1.12)
    top = 120
    scrim_h = len(tlines) * lh + 50
    out.append(f'<rect x="40" y="{top - lh + 18}" width="{W-80}" height="{scrim_h}" '
               f'rx="14" fill="{BG_COLOR}" fill-opacity="0.55"/>')
    spans = "".join(f'<tspan x="70" dy="{0 if i==0 else lh}">{_esc(l)}</tspan>'
                    for i, l in enumerate(tlines))
    out.append(f'<text x="70" y="{top}" text-anchor="start" font-family="Georgia, serif" '
               f'font-weight="bold" font-size="{fs}" fill="{C}">{spans}</text>')

    # --- Fuss: Autor -> Sprachlabel -> Wortmarke -> Hai-Signet, zentriert ---
    out.append(f'<rect x="40" y="1165" width="{W-80}" height="310" rx="14" '
               f'fill="{BG_COLOR}" fill-opacity="0.5"/>')
    out.append(f'<text x="{W//2}" y="1222" text-anchor="middle" font-family="Georgia, serif" '
               f'font-size="44" fill="{C}">{_esc(author)}</text>')
    label = LANG_LABEL.get(lang)
    if label:
        out.append(f'<text x="{W//2}" y="1276" text-anchor="middle" font-family="Georgia, serif" '
                   f'font-style="italic" font-size="28" fill="{C}" fill-opacity="0.85">'
                   f'{_esc(label)}</text>')
    out.append(f'<text x="{W//2}" y="1328" text-anchor="middle" font-family="Georgia, serif" '
               f'font-size="32" letter-spacing="4" fill="{C}">{_esc(IMPRINT)}</text>')
    # Hai zentriert UNTER der Wortmarke
    logo = _logo_fragment((W - 100) // 2, 1352, 100, 56, C)
    if logo:
        out.append(logo)

    out.append('</svg>\n')
    return "\n".join(out)

_CORE_CSS = """@charset "utf-8";
@namespace epub "http://www.idpf.org/2007/ops";

body{
	margin: 0 5%;
	font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
	line-height: 1.5;
	text-align: justify;
	hyphens: auto;
	-epub-hyphens: auto;
}
p{ margin: 0; text-indent: 1em; }
h2 + p, hr + p, section > p:first-of-type{ text-indent: 0; }
h1, h2{
	text-align: center;
	font-weight: normal;
	font-variant: small-caps;
	line-height: 1.2;
	margin: 2em 0 1.5em;
	hyphens: none;
	-epub-hyphens: none;
}
h1{ font-size: 1.6em; }
h2{ font-size: 1.3em; }
hr{
	border: none;
	border-top: 1px solid currentColor;
	width: 25%;
	margin: 1.5em auto;
}
a{ color: inherit; }
"""

_LOCAL_CSS = """@charset "utf-8";
@namespace epub "http://www.idpf.org/2007/ops";

section[epub|type~="titlepage"]{ text-align: center; margin-top: 25%; }
section[epub|type~="titlepage"] h1{ font-size: 2em; margin-bottom: 1em; }
p[epub|type~="z3998:author"]{ text-indent: 0; font-size: 1.2em; margin-top: 1em; }
.imprint{
	text-indent: 0;
	letter-spacing: .35em;
	color: #9a3b1b;
	margin-top: 3em;
}
section[epub|type~="cover"]{ margin: 0; padding: 0; text-align: center; }
.cover-image{ max-width: 100%; max-height: 100vh; }
nav#toc ol{ list-style: none; padding-left: 0; line-height: 2; }
section[epub|type~="colophon"]{ text-align: center; }
section[epub|type~="colophon"] p{ text-indent: 0; margin: 1em 0; }

/* Kapitel-Titelblatt: Titel oben mittig, Signet unten mittig.
   space-between + Padding degradiert sauber, falls ein Reader flex/vh ignoriert. */
.chapter-title-page{
	min-height: 90vh;
	display: flex;
	flex-direction: column;
	align-items: center;
	justify-content: space-between;
	text-align: center;
	padding: 26vh 0 8vh;
}
.chapter-title-page h1{ margin: 0; }
/* feste Maesse stehen im SVG selbst -> hier nur Wirkung */
.signet{ display: block; margin: 2em auto 0; opacity: .8; }

/* Klappentext-Vorsatz */
.blurb{ margin-top: 8%; }
.blurb p{ text-indent: 0; margin: 1em 0; }
.blurb .epigraph{ font-style: italic; margin: 1em 1.5em; }
.blurb .author-note{ font-size: .95em; }
.blurb .mod-note{ font-size: .85em; font-style: italic; color: #6b5f50; margin-top: 1.5em; }
"""


# ============================================================
# 2) VERPACKUNG — OPF + ZIP
# ============================================================
def _opf(meta: dict, manifest_items, spine_items) -> str:
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lang = _BCP47.get(meta["lang"], meta["lang"])

    src = f'\t\t<dc:source>{_esc(meta["source_url"])}</dc:source>\n' if meta.get("source_url") else ""
    year = f'\t\t<dc:date>{meta["year"]}-01-01T00:00:00Z</dc:date>\n' if meta.get("year") else ""

    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<package xmlns="http://www.idpf.org/2007/opf" dir="ltr" '
            'unique-identifier="uid" version="3.0" '
            f'xml:lang="{lang}">\n'
            '\t<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
            f'\t\t<dc:identifier id="uid">urn:uuid:{meta["uuid"]}</dc:identifier>\n'
            f'\t\t<meta property="dcterms:modified">{now}</meta>\n'
            f'\t\t<dc:title id="title">{_esc(meta["title"])}</dc:title>\n' +
            (f'\t\t<meta property="file-as" refines="#title">{_esc(meta["title_sort"])}</meta>\n'
             if meta.get("title_sort") else "") +
            f'\t\t<dc:creator id="author">{_esc(meta["author"] or "Unbekannt")}</dc:creator>\n'
            f'\t\t<meta property="file-as" refines="#author">{_esc(meta["author_sort"] or meta["author"] or "Unbekannt")}</meta>\n'
            '\t\t<meta property="role" refines="#author" scheme="marc:relators">aut</meta>\n'
            f'\t\t<dc:language>{lang}</dc:language>\n'
            f'\t\t<dc:publisher>{_esc(meta["publisher"])}</dc:publisher>\n'
            f'\t\t<dc:rights>{_esc(meta["rights"])}</dc:rights>\n'
            '\t\t<meta name="cover" content="cover-image"/>\n'   # Legacy: Apple Books/Kindle-Thumbnail
            f"{year}{src}"
            '\t</metadata>\n'
            '\t<manifest>\n' + "\n".join(manifest_items) + '\n\t</manifest>\n'
            '\t<spine>\n' + "\n".join(spine_items) + '\n\t</spine>\n'
            '</package>\n')


def build_epub(meta: dict, chapters, out_path: str) -> str:
    """Schreibt das EPUB aus Metadaten + Kapiteln. Sprachunabhaengig.
    Reihenfolge: Cover -> [Klappentext] -> Titelseite ->
                 (Kapitel-Titelblatt + Kapitel-Inhalt)* -> Colophon."""
    lang = _BCP47.get(meta["lang"], meta["lang"])
    files = {}  # arcname -> bytes

    files["mimetype"] = b"application/epub+zip"
    files["META-INF/container.xml"] = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">\n'
        '\t<rootfiles>\n'
        '\t\t<rootfile full-path="epub/content.opf" media-type="application/oebps-package+xml"/>\n'
        '\t</rootfiles>\n</container>\n').encode("utf-8")

    # Cover: RASTER (JPEG) bevorzugt -> App-Reader thumbnailen kein SVG.
    # Faellt Pillow aus, degradiert es sauber auf das Vektor-SVG (bisheriges Verhalten).
    raster = _compose_cover_raster(meta["title"], meta["author"], meta.get("cover"), meta["lang"],
                                   meta.get("sprecher", ""), meta.get("imprint", ""))
    if raster:
        cover_file, cover_media, cover_id = "cover.jpg", "image/jpeg", "cover-image"
        files["epub/images/cover.jpg"] = raster
        # Fertiges Cover (Bild + Typografie) auch fuer App/Demo ablegen (tools/export_app.py)
        try:
            with open(os.path.join(os.path.dirname(out_path), f"cover_final_{meta['lang']}.jpg"), "wb") as f:
                f.write(raster)
        except Exception as e:
            print(f"[stage30] HINWEIS: cover_final nicht geschrieben ({e})")
    else:
        cover_file, cover_media, cover_id = "cover.svg", "image/svg+xml", "cover-image"
        files["epub/images/cover.svg"] = _compose_cover_svg(
            meta["title"], meta["author"], meta.get("cover"), meta["lang"]).encode("utf-8")
        print("[stage30] HINWEIS: Pillow nicht verfuegbar -> SVG-Cover statt Raster. "
              "App-Reader zeigen dann KEIN Regal-Thumbnail. Beheben: pip install pillow.")
    files["epub/css/core.css"]  = _CORE_CSS.encode("utf-8")
    files["epub/css/local.css"] = _LOCAL_CSS.encode("utf-8")

    has_blurb = bool(meta.get("blurb_html"))
    files["epub/toc.xhtml"] = _nav_xhtml(meta["title"], chapters, lang, has_blurb).encode("utf-8")

    # --- geordnete Inhalts-Dokumente (id, dateiname, xhtml) ---
    pages = [("cover", "cover.xhtml", _cover_xhtml(lang, cover_file))]
    if has_blurb:
        pages.append(("blurb", "blurb.xhtml", meta["blurb_html"]))
    pages.append(("titlepage", "titlepage.xhtml",
                  _titlepage_xhtml(meta["title"], meta["author"], lang)))
    for i, (ctitle, paras) in enumerate(chapters, 1):
        pages.append((f"chapter-{i}-title", f"chapter-{i}-title.xhtml",
                      _chapter_title_xhtml(i, ctitle, lang)))
        pages.append((f"chapter-{i}", f"chapter-{i}.xhtml",
                      _chapter_xhtml(i, ctitle, paras, lang)))
    pages.append(("colophon", "colophon.xhtml",
                  _colophon_xhtml(meta["title"], meta["author"], meta.get("source_url", ""),
                                  lang, meta.get("modernized", False), meta.get("own_year"))))

    # statische Manifest-Eintraege (CSS, Nav, Cover-Bild)
    manifest = [
        '\t\t<item href="css/core.css" id="core.css" media-type="text/css"/>',
        '\t\t<item href="css/local.css" id="local.css" media-type="text/css"/>',
        '\t\t<item href="toc.xhtml" id="toc" media-type="application/xhtml+xml" properties="nav"/>',
        f'\t\t<item href="images/{cover_file}" id="{cover_id}" '
        f'media-type="{cover_media}" properties="cover-image"/>',
    ]
    spine = []
    for pid, name, data in pages:
        files[f"epub/text/{name}"] = data.encode("utf-8")
        props = ' properties="svg"' if "<svg" in data else ""   # 24.10.2026: Inline-SVG (OPF-014)
        manifest.append(f'\t\t<item href="text/{name}" id="{pid}" '
                        f'media-type="application/xhtml+xml"{props}/>')
        spine.append(f'\t\t<itemref idref="{pid}"/>')

    files["epub/content.opf"] = _opf(meta, manifest, spine).encode("utf-8")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with zipfile.ZipFile(out_path, "w") as z:
        # mimetype MUSS zuerst und UNKOMPRIMIERT stehen (EPUB-Spec)
        z.writestr(zipfile.ZipInfo("mimetype"), files.pop("mimetype"),
                   compress_type=zipfile.ZIP_STORED)
        for arc, data in files.items():
            z.writestr(arc, data, compress_type=zipfile.ZIP_DEFLATED)
    return out_path


# ============================================================
# METADATEN aus book.json / author.json
# ============================================================
def _derive_sort_name(name: str) -> str:
    parts = name.split()
    return f"{parts[-1]}, {' '.join(parts[:-1])}" if len(parts) > 1 else name

def _fassung_title(bj: dict, lang: str) -> str:
    """Laendertitel DIESER Fassung (aus Stage 08b --work in book.json.fassungen[]),
    sonst Originaltitel. Fallback IMMER auf titel_original -> nie leer, nie falsch."""
    for f in bj.get("fassungen", []):
        if f.get("sprache") == lang and (f.get("titel") or "").strip():
            return f["titel"].strip()
    return (bj.get("titel_original") or "").strip()


_GELESEN = {"de": "Gelesen von", "en": "Read by", "fr": "Lu par", "es": "Leído por", "it": "Letto da"}
_KI = {"de": "KI-Stimme", "en": "AI voice", "fr": "voix IA", "es": "voz IA", "it": "voce IA"}


def _sprecher_zeile(bj: dict, bdir: str, lang: str) -> str:
    """Sprecherzeile fuers Cover (18.10.2026): nur fuer die aktuelle Vertonung mit designter
    Stimme. LibriVox-Spur und Thorsten sind abgeloest -> nie mehr auf dem Cover.
    Quelle: fassungen[lang].sprecher, sonst audio_voice -- nur wenn Audio dieser Sprache vorliegt."""
    f = next((x for x in bj.get("fassungen", []) if x.get("sprache") == lang), {}) or {}
    if str(f.get("audio_quelle") or "").startswith(("librivox", "thorsten")):
        return ""
    adir = os.path.join(bdir, "fassungen", lang, "audio")
    if not (os.path.isdir(adir) and any(n.endswith(".wav") for n in os.listdir(adir))):
        return ""
    av = bj.get("audio_voice") if isinstance(bj.get("audio_voice"), str) else ""
    stimme = f.get("sprecher") or av
    if not stimme or stimme.lower() == "thorsten":
        return ""
    gel = _GELESEN.get(lang, "Read by")
    return f"{gel} {stimme} \u00b7 {_KI.get(lang, 'AI voice')}"


def _gather_meta(book_id: str, lang: str | None = None) -> dict:
    """Metadaten fuer EINE Fassung. lang=None -> Originalsprache (Stage 30).
    Stage 31 (Uebersetzung) uebergibt lang=<ziel> -> Titel kommt aus der Fassung."""
    bdir = config.book_dir(book_id)
    bj = json.load(open(os.path.join(bdir, "book.json"), encoding="utf-8"))
    aj = {}
    ap = os.path.join(config.author_dir(config.author_of(book_id)), "author.json")
    if os.path.exists(ap):
        aj = json.load(open(ap, encoding="utf-8"))

    lang   = lang or bj.get("originalsprache") or config.SOURCE_LANGUAGE
    title  = _fassung_title(bj, lang) or book_id          # Laendertitel -> sonst Original
    author = aj.get(f"name_display_{lang}") or aj.get("name_display") or bj.get("author_slug", "")
    # 18.10.2026: Gutenberg-Schreibweise "H. G. (Herbert George) Wells" -> "H. G. Wells"
    author = re.sub(r"\s*\([^)]*\)", "", author).strip() or author
    # 24.10.2026 (Smoke #2): User-ePub ohne author_slug -> Autor aus book.json, sonst "Unbekannt"
    author = author or (bj.get("autor_name") or "").strip() or "Unbekannt"
    publisher = bj.get("publisher", "")
    if not publisher or publisher == "<eigenes-label>":
        publisher = "SOMNIO"
    imprint = "SOMNIO PUBLISHING" if publisher == "SOMNIO" else publisher.upper()
    sprecher = _sprecher_zeile(bj, bdir, lang)
    gid = str(bj.get("gutenberg_id", "")).strip()
    source_url = f"https://www.gutenberg.org/ebooks/{gid}" if gid else ""
    # 22.10.2026: eigenes Werk (book.json rechte=eigene) -> "Alle Rechte vorbehalten", keine Quelle
    eigen = str(bj.get("rechte") or "").lower().startswith("eigen")
    own_year = (bj.get("erscheinungsjahr") or datetime.datetime.now().year) if eigen else None
    if eigen:
        source_url = ""
        rights = _COLOPHON.get(lang, _COLOPHON["en"])["rights_own"].replace("{year}", str(own_year))
    else:
        rights = "The source text is believed to be in the public domain."

    return {
        "title": title,
        "title_sort": title,
        "author": author,
        "author_sort": aj.get("name_sort") or _derive_sort_name(author),
        "lang": lang,
        "year": bj.get("erscheinungsjahr"),
        "publisher": publisher,
        "imprint": imprint,
        "sprecher": sprecher,
        "rights": rights,
        "own_year": own_year,
        "source_url": source_url,
        "uuid": uuid.uuid5(_NS, book_id),
        "cover": _find_raster_cover(book_id),
        "modernized": _is_modernized(book_id),
    }


def run(book_id: str):
    chapters = _load_chapters(book_id)
    meta = _gather_meta(book_id)

    # Klappentext-Vorsatz in der Output-Sprache (aus 600_klappentext.json), falls vorhanden.
    sp = config.work_path(book_id, "600_klappentext")
    if os.path.exists(sp):
        try:
            stage09 = json.load(open(sp, encoding="utf-8"))
            meta["blurb_html"] = _blurb_xhtml(stage09, meta["lang"],
                                              _BCP47.get(meta["lang"], meta["lang"]),
                                              meta.get("modernized", False))
        except Exception as e:
            print(f"[stage11] HINWEIS: Klappentext uebersprungen ({type(e).__name__}).")

    # Sprach-Ebene (FASSUNG): books/<buch>/fassungen/<lang>/output/<slug>.epub
    out_dir = os.path.join(config.book_dir(book_id), "fassungen", meta["lang"], "output")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{book_id}.epub")
    build_epub(meta, chapters, out_path)

    n_titled = sum(1 for t, _ in chapters if t)
    n_paras = sum(len(p) for _, p in chapters)
    print(f"[stage11] EPUB -> {out_path}")
    print(f"[stage11] Kapitel: {len(chapters)} (mit Titel: {n_titled}), "
          f"Absaetze: {n_paras}, Klappentext: {'ja' if meta.get('blurb_html') else 'nein'}, "
          f"Sprache: {meta['lang']}")
    if n_titled == 0:
        print("[stage11] HINWEIS: keine Kapitel-Titel erkannt -> Heuristik pruefen "
              "(oder ###CHAPTER###-Marker setzen).")
    return out_path


if __name__ == "__main__":
    import sys
    run(sys.argv[1] if len(sys.argv) > 1 else "jekyll-and-hyde")
