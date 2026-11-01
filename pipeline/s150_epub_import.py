"""STAGE 150 — ePub-Import (user_epub / verlag_epub; GATE_KATALOG.md, Phase 2 01.11.2026)
Funktion:     Bringt ein DRM-freies ePub ins Pipeline-Format: chapter-N.json, raw_modernized.txt, anhang.json,
              Cover, ingest_bericht.json, book.json (quelle, quellsprache, Mandant, Klappentext vorhanden ja/nein
              -> Modus 600). Quell-ePub wird nach <werk>/quelle/ gesichert (Grundlage fuer Neueinlesen).
Gate:         DRM-frei Pflicht; Kapitel >= 1; >= 5.000 Zeichen; Inhaltsanteil (Kapiteltext / Spine-Text) >= 80 %;
              Warnungen = 0; Sprache im OPF; Sprache in Sprachliste. auto bei allem gruen; Inhaltsanteil,
              Warnungen, Sprache fehlt / nicht in Sprachliste -> Mensch; Mandant verlag -> immer Mensch
              (Kapitelliste); DRM/kein Inhalt/zu kurz -> Stopp. Datei defekt -> Ruecksprung 090.
Regler:       --titel, --autor, --sprache, --behalten/--entfernen DATEI (Seitenliste, bleibt in book.json
              epub_import), --bilder/--fussnoten ja|nein, --cover epub|neu, --epub DATEI, --force (neu einlesen,
              leert den Kapitelordner).
Befunde 150:  Index erst nach erfolgreichem Einlesen (kein verwaister Eintrag); OPF ohne Sprache -> Mensch statt
              still en; per Dateiname entfernte Seite mit viel Text -> Warnung (Mensch); quelle/quellsprache/
              Mandant/Besitzer gesetzt (Rechte per 090 --versichern); Neueinlesen leert chapter-N.json und behaelt
              fremde book.json-Felder; Klappentext vorhanden -> book.json klappentext_vorhanden.
              Offen fuer 600/620: Klappentext uebernehmen/uebersetzen, Bilder/Fussnoten ins EPUB.
Kosten:       0 $ (kein LLM).

Aufruf:
  python -m pipeline.s150_epub_import <datei.epub> --user anna [--mandant verlag:x] [--titel ...]   Neuanlage
  python -m pipeline.s150_epub_import <werk> [--behalten about.xhtml] [--sprache de] [--force]       Gate/Regler
Exit: 0 auto, 2 Stopp, 3 Mensch.

--- Bisherige Beschreibung ---

READ LAYER — Stage 05: ePub-Ingest (privater TAELLA-Upload)
===========================================================
Bringt ein DRM-freies ePub eines TAELLA-Users ins Pipeline-Format.
Das Werk ist PRIVAT: es liegt unter users/<uid>/works/<book_id>/ und erscheint nie
im Katalog. Danach laeuft die Audio-Linie ab Stage 50 (Stage 11 entfaellt: der
Text des Users wird nicht modernisiert).

  05a Pruefen      ZIP/container.xml, DRM (encryption.xml, LCP), Sprache aus OPF
  05b Cover        OPF cover-image -> meta name=cover -> Bild auf Cover-Seite;
                   fehlt es: TAELLA-Cover mit Label "TAELLA-User: <name>"
  05c Klappentext  dc:description / se:long-description; fehlt er: leer
  05d Bereinigen   nur Inhaltsseiten behalten (Kapitel, Vorwort ...); Titelei,
                   Inhaltsverzeichnis, Impressum, Danksagung, Werbung, Logos raus
  05e Bilder       Illustrationen -> Anhang "Bilder", Anker am vorangehenden Satz
  05f Fussnoten    Fussnoten -> Anhang "Anmerkungen", Anker am Satz;
                   mituebersetzen ja, vertonen nein

Ausgabe (users/<uid>/works/<book_id>/):
  book.json, raw.txt (= raw_modernized.txt), raw_modernized.txt (###-Marken),
  images/cover_source.*, images/cover.png, images/cover_thumb.jpg,
  images/anhang/bild-N.*, work/modernized/chapter-N.json,
  work/anhang.json, work/ingest_bericht.json
Index: daten/index.json  books[<book_id>] = "user:<uid>"

Aufruf:
  python -m pipeline.s150_epub_import <datei.epub> --user MikeMustermann [--titel "..."] [--force]

Nur Standardbibliothek (+ Pillow optional fuer Cover-Konvertierung).
"""
import os, sys, re, json, zipfile, hashlib, html, shutil, posixpath
from html.parser import HTMLParser
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config

HR = "——HR——"

KEEP_TYPES = {"chapter", "part", "division", "volume", "prologue", "epilogue", "preface",
              "foreword", "introduction", "preamble", "conclusion", "afterword", "bodymatter",
              "z3998:fiction", "z3998:poem", "z3998:play"}
NOTE_TYPES = {"footnotes", "endnotes", "rearnotes", "footnote", "endnote", "rearnote", "note"}
SKIP_NAME = re.compile(r"(cover|title|toc|nav|contents|inhalt|copyright|imprint|impressum|colophon|"
                       r"acknowledg|danksag|donat|about|advert|\bads\b|license|lizenz|uncopyright|"
                       r"public-domain|halftitle|loi|lot|backcover|promo|newsletter)", re.I)
LOGO = re.compile(r"(logo|icon|badge|banner|ornament|separator|dingbat)", re.I)
BLOCK = {"p", "li", "dd", "dt", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "div",
         "figcaption", "td", "th", "pre", "section", "article", "aside", "header", "footer", "hgroup"}
TEXT_BLOCK = {"p", "li", "dd", "dt", "h4", "h5", "h6", "td", "th", "pre", "div", "blockquote"}


def _norm(s):
    return re.sub(r"\s+", " ", html.unescape(s or "")).strip()


def _strip_tags(s):
    t = _norm(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+([,.;:!?\u2019])", r"\1", t)


# ---------------------------------------------------------------- 05a Pruefen
class EpubFehler(Exception):
    pass


def oeffnen(path):
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise EpubFehler("Keine gueltige ePub-Datei (kein ZIP).")
    names = set(z.namelist())
    if "META-INF/container.xml" not in names:
        raise EpubFehler("container.xml fehlt.")
    if any(n.lower().endswith("license.lcpl") for n in names):
        raise EpubFehler("DRM (Readium LCP) - kann nicht verarbeitet werden.")
    if "META-INF/encryption.xml" in names:
        enc = z.read("META-INF/encryption.xml").decode("utf-8", "ignore")
        # Font-Obfuscation (IDPF/Adobe) ist kein DRM; alles andere schon
        algos = set(re.findall(r'Algorithm="([^"]+)"', enc))
        harmlos = {"http://www.idpf.org/2008/embedding", "http://ns.adobe.com/pdf/enc#RC"}
        refs = re.findall(r'<(?:\w+:)?CipherReference[^>]*URI="([^"]+)"', enc)
        nur_fonts = all(r.lower().endswith((".otf", ".ttf", ".woff", ".woff2")) for r in refs)
        if not (algos <= harmlos or nur_fonts):
            raise EpubFehler("DRM (verschluesselte Inhalte) - kann nicht verarbeitet werden.")
    cont = z.read("META-INF/container.xml").decode("utf-8", "ignore")
    m = re.search(r'full-path="([^"]+)"', cont)
    if not m:
        raise EpubFehler("OPF-Pfad nicht gefunden.")
    return z, m.group(1)


def opf_lesen(z, opf_path):
    o = z.read(opf_path).decode("utf-8", "ignore")
    base = posixpath.dirname(opf_path)
    items = {}
    for it in re.findall(r"<item\s[^>]*?/?>", o, re.S):
        a = dict(re.findall(r'([\w:-]+)="([^"]*)"', it))
        if "id" in a and "href" in a:
            a["path"] = posixpath.normpath(posixpath.join(base, html.unescape(a["href"])))
            items[a["id"]] = a
    spine = [re.search(r'idref="([^"]+)"', r).group(1) for r in re.findall(r"<itemref\s[^>]*>", o)]

    def dc(tag):
        return [_strip_tags(x) for x in re.findall(r"<dc:%s[^>]*>(.*?)</dc:%s>" % (tag, tag), o, re.S)]

    titles = dc("title")
    # Haupttitel: EPUB3 title-type main
    main = None
    for tid, txt in re.findall(r'<dc:title[^>]*id="([^"]+)"[^>]*>(.*?)</dc:title>', o, re.S):
        if re.search(r'refines="#%s"[^>]*property="title-type"[^>]*>\s*main' % re.escape(tid), o):
            main = _strip_tags(txt)
    long_desc = re.findall(r'<meta[^>]*property="se:long-description"[^>]*>(.*?)</meta>', o, re.S)
    cover_meta = re.search(r'<meta[^>]*name="cover"[^>]*content="([^"]+)"', o) or \
        re.search(r'<meta[^>]*content="([^"]+)"[^>]*name="cover"', o)
    guide_cover = re.search(r'<reference[^>]*type="cover"[^>]*href="([^"]+)"', o)
    return {
        "raw": o, "base": base, "items": items, "spine": spine,
        "titel": main or (titles[0] if titles else ""), "titel_alle": titles,
        "autor": ", ".join(dc("creator")), "sprache": (dc("language") or [""])[0],
        "beschreibung": (dc("description") or [""])[0],
        "lange_beschreibung": _strip_tags(html.unescape(long_desc[0])) if long_desc else "",
        "cover_meta": cover_meta.group(1) if cover_meta else None,
        "guide_cover": posixpath.normpath(posixpath.join(base, guide_cover.group(1).split("#")[0])) if guide_cover else None,
    }


# ---------------------------------------------------------------- 05b Cover
def cover_finden(z, opf):
    for it in opf["items"].values():
        if "cover-image" in it.get("properties", ""):
            return it["path"], "opf:cover-image"
    if opf["cover_meta"] and opf["cover_meta"] in opf["items"]:
        return opf["items"][opf["cover_meta"]]["path"], "opf:meta-cover"
    kandidaten = []
    if opf["guide_cover"]:
        kandidaten.append(opf["guide_cover"])
    for idref in opf["spine"][:2]:
        it = opf["items"].get(idref)
        if it and SKIP_NAME.search(it["href"]) and "cover" in it["href"].lower():
            kandidaten.append(it["path"])
    for p in kandidaten:
        try:
            s = z.read(p).decode("utf-8", "ignore")
        except KeyError:
            continue
        m = re.search(r'<(?:img[^>]*src|image[^>]*(?:xlink:)?href)="([^"]+)"', s)
        if m:
            return posixpath.normpath(posixpath.join(posixpath.dirname(p), m.group(1))), "cover-seite"
    return None, None


def cover_erzeugen(ziel_png, titel, autor, label):
    """TAELLA-Standardcover: weiss, streng typografisch, roter Punkt, User-Label."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return False
    W, H = 1600, 2400
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)

    def font(size, serif=False):
        for f in (["georgia.ttf", "DejaVuSerif.ttf"] if serif else ["arial.ttf", "DejaVuSans.ttf"]):
            try:
                return ImageFont.truetype(f, size)
            except OSError:
                pass
        return ImageFont.load_default()

    def wrap(text, f, maxw):
        zeilen, z_ = [], ""
        for w in text.split():
            t = (z_ + " " + w).strip()
            if d.textlength(t, font=f) <= maxw:
                z_ = t
            else:
                zeilen.append(z_); z_ = w
        if z_:
            zeilen.append(z_)
        return zeilen

    y = 520
    ft = font(130, serif=True)
    for z_ in wrap(titel, ft, W - 320):
        d.text((160, y), z_, font=ft, fill="black"); y += 160
    d.ellipse((160, y + 30, 200, y + 70), fill=(225, 30, 30))   # roter Punkt
    d.text((160, y + 120), autor, font=font(70, serif=True), fill="black")
    d.text((160, H - 200), label, font=font(44), fill=(90, 90, 90))
    im.save(ziel_png)
    return True


def cover_ablegen(z, src, bdir, titel, autor, label):
    img_dir = os.path.join(bdir, "images")
    os.makedirs(img_dir, exist_ok=True)
    info = {"quelle": None, "datei": None, "erzeugt": False}
    png = os.path.join(img_dir, "cover.png")
    if src:
        ext = os.path.splitext(src)[1].lower() or ".jpg"
        ziel = os.path.join(img_dir, "cover_source" + ext)
        open(ziel, "wb").write(z.read(src))
        info.update(quelle=src, datei="images/cover_source" + ext)
        try:
            from PIL import Image
            im = Image.open(ziel).convert("RGB")
            info["groesse"] = list(im.size)
            im.save(png)
            th = im.copy(); th.thumbnail((400, 600)); th.save(os.path.join(img_dir, "cover_thumb.jpg"), quality=85)
        except Exception as e:
            info["hinweis"] = f"Pillow fehlt/Fehler ({e}) - cover.png nicht erzeugt"
    else:
        info["erzeugt"] = cover_erzeugen(png, titel, autor, label)
        info["datei"] = "images/cover.png" if info["erzeugt"] else None
        if info["erzeugt"]:
            try:
                from PIL import Image
                th = Image.open(png); th.thumbnail((400, 600)); th.save(os.path.join(img_dir, "cover_thumb.jpg"), quality=85)
            except Exception:
                pass
    return info


# ---------------------------------------------------------------- 05d Parser
class Kapitelparser(HTMLParser):
    """Zerlegt eine XHTML-Datei in Ueberschriften, Absaetze, Bilder, Fussnoten-Anker."""

    def __init__(self, notiz_ids):
        super().__init__(convert_charrefs=True)
        self.notiz_ids = notiz_ids          # ids von Fussnotentexten (ueberspringen + verlinken)
        self.stack = []                     # (tag, attrs)
        self.buf = None
        self.paras = []                     # {"text", "refs":[...]}
        self.headings = []
        self.events = []                    # ("bild", attrs) | ("hr",)
        self.skip_depth = 0
        self.head_depth = 0
        self.in_ref = None
        self.ref_text = ""
        self.cur_refs = []
        self.first_p_seen = False
        self.figcap = None

    # Hilfen
    def _types(self, attrs):
        a = dict(attrs)
        return set((a.get("epub:type", "") + " " + a.get("role", "").replace("doc-", "")).split())

    def _flush(self):
        if self.buf is not None:
            t = _norm(self.buf)
            if t:
                if self.head_depth and not self.first_p_seen:
                    self.headings.append(t)
                else:
                    self.paras.append({"text": t, "refs": self.cur_refs})
                    self.first_p_seen = True
            self.buf = None
            self.cur_refs = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "head", "title"):
            self.skip_depth += 1
        if self.skip_depth:
            self.stack.append((tag, a, True)); return
        types = self._types(attrs)
        skip = bool(types & NOTE_TYPES) or (a.get("id") in self.notiz_ids and tag in ("aside", "li", "div", "section", "p"))
        if skip:
            self.skip_depth += 1
            self.stack.append((tag, a, True)); return
        if tag in ("h1", "h2", "h3", "hgroup") and not self.first_p_seen:
            self.head_depth += 1
        if tag == "figcaption" or (tag in ("p", "div", "span") and self.events and
                                   re.search(r"caption|legend|bildunter", a.get("class", ""), re.I)):
            self._flush(); self.figcap = ""
            self.stack.append((tag, a, False)); return
        if tag in BLOCK:
            self._flush()
            if tag in TEXT_BLOCK or tag in ("h1", "h2", "h3"):
                self.buf = ""
        if tag == "br" and self.buf is not None:
            self.buf += " "
        if tag == "hr":
            self._flush(); self.paras.append({"text": HR, "refs": []})
        if tag in ("img", "image"):
            src = a.get("src") or a.get("xlink:href") or a.get("href") or ""
            if src and not LOGO.search(src + " " + a.get("alt", "") + " " + a.get("class", "")):
                anker = self.paras[-1]["text"] if self.paras else None
                self.events.append({"src": src, "alt": a.get("alt", ""), "nach_absatz": len(self.paras) - 1,
                                    "anker_text": (anker or "")[-80:]})
        if tag == "a":
            href = a.get("href", "")
            frag = href.split("#")[-1] if "#" in href else ""
            if ("noteref" in types) or (frag and frag in self.notiz_ids):
                self.in_ref = frag; self.ref_text = ""
        self.stack.append((tag, a, False))

    def handle_endtag(self, tag):
        # passendes oeffnendes Tag suchen (tolerant)
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                t, a, skipped = self.stack[i]
                del self.stack[i:]
                break
        else:
            return
        if tag in ("script", "style", "head", "title"):
            self.skip_depth = max(0, self.skip_depth - 1); return
        if skipped:
            if self.skip_depth and not (tag in ("script", "style", "head", "title")):
                # nur echte Skip-Container zaehlen herunter
                types = self._types(a.items())
                if bool(types & NOTE_TYPES) or (a.get("id") in self.notiz_ids and tag in ("aside", "li", "div", "section", "p")):
                    self.skip_depth = max(0, self.skip_depth - 1)
            return
        if tag == "a" and self.in_ref is not None:
            if self.buf is not None:
                self.cur_refs.append({"id": self.in_ref, "pos": len(_norm(self.buf))})
            self.in_ref = None
            return
        if self.figcap is not None and (tag == "figcaption" or re.search(r"caption|legend|bildunter", a.get("class", ""), re.I)):
            if self.events and self.figcap:
                self.events[-1]["bildunterschrift"] = _norm(self.figcap)
            self.figcap = None; return
        if tag in BLOCK:
            self._flush()
        if tag in ("h1", "h2", "h3", "hgroup") and self.head_depth:
            self.head_depth -= 1

    def handle_data(self, data):
        if self.skip_depth:
            return
        if self.figcap is not None:
            self.figcap += data; return
        if self.in_ref is not None:
            self.ref_text += data; return        # Fussnotenziffer nicht in den Lesetext
        if self.buf is None:
            if data.strip():
                self.buf = data                  # loser Text direkt im Container
            return
        self.buf += data


class Notizsammler(HTMLParser):
    """Sammelt Fussnotentexte: Elemente mit epub:type footnote/endnote/rearnote/note
    (bzw. role doc-footnote/doc-endnote) oder Ziele von noteref-Links."""

    def __init__(self, ziel_ids):
        super().__init__(convert_charrefs=True)
        self.ziel_ids = ziel_ids
        self.offen = []          # [id, tiefe, text]
        self.tiefe = 0
        self.notizen = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tiefe += 1 if tag not in ("br", "img", "hr", "meta", "link") else 0
        t = set((a.get("epub:type", "") + " " + a.get("role", "").replace("doc-", "")).split())
        nid = a.get("id")
        if nid and ((t & {"footnote", "endnote", "rearnote", "note"}) or nid in self.ziel_ids):
            if tag not in ("a", "span", "sup"):
                self.offen.append([nid, self.tiefe, ""])

    def handle_endtag(self, tag):
        if tag in ("br", "img", "hr", "meta", "link"):
            return
        if self.offen and self.offen[-1][1] == self.tiefe:
            nid, _, txt = self.offen.pop()
            txt = re.sub(r"^\s*[\d\*†‡]+[\.\)]?\s*", "", _norm(txt))
            txt = re.sub(r"\s*(↩|↑|back|zurück)\s*$", "", txt, flags=re.I)
            if txt:
                self.notizen[nid] = txt
        self.tiefe -= 1

    def handle_data(self, data):
        for o in self.offen:
            o[2] += data


# ---------------------------------------------------------------- Klassifizieren
def seite_klassifizieren(z, item):
    """-> 'inhalt' | 'notizen' | 'weg' (+ Grund)"""
    try:
        s = z.read(item["path"]).decode("utf-8", "ignore")
    except KeyError:
        return "weg", "Datei fehlt", ""
    if "nav" in item.get("properties", ""):
        return "weg", "Inhaltsverzeichnis (nav)", s
    body = s[s.find("<body"):] if "<body" in s else s
    kopf = body[:4000]
    types = set()
    for v in re.findall(r'(?:epub:type|role)="([^"]+)"', kopf):
        types |= set(v.replace("doc-", "").split())
    if types & {"footnotes", "endnotes", "rearnotes"}:
        return "notizen", "Fussnoten-/Endnotenseite", s
    if types & KEEP_TYPES:
        return "inhalt", "epub:type " + ",".join(sorted(types & KEEP_TYPES)), s
    if types - {"frontmatter", "backmatter", "z3998:fiction"}:
        return "weg", "epub:type " + ",".join(sorted(types)), s
    if SKIP_NAME.search(item["href"]):
        return "weg", "Dateiname " + item["href"], s
    text = _strip_tags(body)
    if re.search(r"project gutenberg license|end of (the )?project gutenberg", text, re.I):
        return "weg", "Gutenberg-Lizenztext", s
    absaetze = [x for x in re.findall(r"<p[^>]*>(.*?)</p>", body, re.S) if len(_strip_tags(x)) > 120]
    if len(text) < 600 and not absaetze:
        return "weg", f"zu kurz ({len(text)} Zeichen, kein Fliesstext)", s
    return "inhalt", "Fliesstext", s


def kapitel_titel(headings, fallback):
    if not headings:
        return fallback
    if len(headings) >= 2 and len(headings[0]) <= 8:   # Ordinal + Titel
        return f"{headings[0]}. {headings[1]}"
    return headings[0]


# ---------------------------------------------------------------- Hauptlauf
STAGE = "150"
MIN_ZEICHEN = 5000
MIN_INHALTSANTEIL = 0.80
VERDACHT_ZEICHEN = 3000          # per Dateiname entfernte Seite mit so viel Fliesstext -> Warnung
OPT_STANDARD = {"bilder": True, "fussnoten": True, "cover": "epub", "seiten": {}}


def _dump(pfad, obj):
    from pipeline.manifest import json_atomar
    json_atomar(pfad, obj, indent=2)


def _schreib_text(pfad, text):
    tmp = f"{pfad}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, pfad)


def importieren(epub_path, bdir, book_id, user_name, titel=None, autor=None, sprache=None, opt=None):
    """Kern 150: ePub -> chapter-N.json, raw(_modernized).txt, anhang.json, Cover, ingest_bericht.json.
    Schreibt nichts, wenn kein Inhalt gefunden wird (EpubFehler). Rueckgabe (bericht, felder fuer book.json)."""
    opt = dict(OPT_STANDARD, **(opt or {}))
    zwang = opt.get("seiten") or {}
    bericht = {"datei": os.path.basename(epub_path), "zeit": datetime.now().isoformat(timespec="seconds"),
               "user": user_name, "entfernt": [], "inhalt": [], "notizseiten": [], "warnungen": [],
               "optionen": opt}
    z, opf_path = oeffnen(epub_path)
    opf = opf_lesen(z, opf_path)
    with open(epub_path, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    opf_sprache = (opf["sprache"] or "").split("-")[0].lower() or None
    sprache = (sprache or opf_sprache or "en").lower()
    titel = titel or opf["titel"] or os.path.splitext(os.path.basename(epub_path))[0]
    autor = autor or opf["autor"] or "Unbekannt"
    label = f"TÆLLA-User: {user_name}"
    bericht.update(titel=titel, titel_kandidaten=opf["titel_alle"], autor=autor, sprache=sprache,
                   opf_sprache=opf_sprache, book_id=book_id, sha256=sha)

    # 05d Seiten klassifizieren (+ Zeichen je Spine-Seite fuer den Inhaltsanteil)
    seiten, spine_zeichen = [], 0
    for idref in opf["spine"]:
        it = opf["items"].get(idref)
        if not it or not it.get("media-type", "").startswith("application/xhtml"):
            continue
        art, grund, s = seite_klassifizieren(z, it)
        body = s[s.find("<body"):] if "<body" in s else s
        n_txt = len(_strip_tags(re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body, flags=re.S)))
        z_ = zwang.get(it["href"]) or zwang.get(posixpath.basename(it["href"]))
        if z_ != "entfernen":
            spine_zeichen += n_txt              # per Regler entfernte Seiten zaehlen nicht zum Spine
        if z_ == "behalten" and art != "inhalt":
            art, grund = "inhalt", f"Regler: behalten (vorher {grund})"
        elif z_ == "entfernen" and art != "weg":
            art, grund = "weg", f"Regler: entfernt (vorher {grund})"
        elif art == "weg" and grund.startswith("Dateiname") and n_txt >= VERDACHT_ZEICHEN:
            bericht["warnungen"].append(f"Seite {it['href']} per Dateiname entfernt, hat aber {n_txt} Zeichen "
                                        f"Text – pruefen (Regler --behalten {it['href']})")
        seiten.append((it, art, grund, s))
        rec = {"datei": it["href"], "grund": grund, "zeichen": n_txt}
        {"inhalt": bericht["inhalt"], "notizen": bericht["notizseiten"], "weg": bericht["entfernt"]}[art].append(rec)

    # 05f Fussnoten sammeln (Ziele aller noteref-/Anker-Links)
    ziel_ids = set()
    for it, art, _, s in seiten:
        if art != "inhalt":
            continue
        for m in re.finditer(r"<a\s[^>]*>", s):
            tag = m.group(0)
            href = re.search(r'href="([^"]*#([^"]+))"', tag)
            if href and ("noteref" in tag or re.search(r"(fn|note|footnote|endnote)", href.group(2), re.I)):
                ziel_ids.add(href.group(2))
    notizen = {}
    for idx_s, (it, art, grund, s) in enumerate(seiten):
        ns = Notizsammler(ziel_ids); ns.feed(s); notizen.update(ns.notizen)
        if art == "weg" and ns.notizen and zwang.get(it["href"]) != "entfernen":
            seiten[idx_s] = (it, "notizen", "Anmerkungsseite (Link-Ziele)", s)
            bericht["entfernt"] = [e for e in bericht["entfernt"] if e["datei"] != it["href"]]
            bericht["notizseiten"].append({"datei": it["href"], "grund": "Anmerkungsseite (Link-Ziele)"})

    # Cover bestimmen (Ablage erst nach erfolgreichem Parsen)
    src, wie = (None, None) if opt.get("cover") == "neu" else cover_finden(z, opf)

    # Kapitel parsen (Bilder erst sammeln, schreiben nach Erfolg)
    kapitel, bilder, fussnoten, bild_daten = [], [], [], []
    fn_nr = {}
    for it, art, _, s in seiten:
        if art != "inhalt":
            continue
        p = Kapitelparser(set(notizen.keys())); p.feed(s); p._flush()
        k_nr = len(kapitel) + 1
        paras = list(p.paras)
        texte = [x["text"] for x in paras]
        if not [t for t in texte if t != HR]:
            bericht["warnungen"].append(f"leer nach Bereinigung: {it['href']}"); continue
        if opt.get("bilder"):
            for ev in p.events:
                pfad = posixpath.normpath(posixpath.join(posixpath.dirname(it["path"]), ev["src"]))
                if pfad == src:
                    continue
                try:
                    daten = z.read(pfad)
                except KeyError:
                    bericht["warnungen"].append(f"Bild fehlt: {pfad}"); continue
                n = len(bilder) + 1
                ext = os.path.splitext(pfad)[1].lower()
                bild_daten.append((f"bild-{n}{ext}", daten))
                bilder.append({"nr": n, "datei": f"images/anhang/bild-{n}{ext}", "kapitel": k_nr,
                               "nach_absatz": ev["nach_absatz"], "anker_text": ev["anker_text"],
                               "alt": ev["alt"], "bildunterschrift": ev.get("bildunterschrift", "")})
        if opt.get("fussnoten"):
            for ai, para in enumerate(paras):
                for r in para["refs"]:
                    if r["id"] not in notizen:
                        bericht["warnungen"].append(f"Fussnote ohne Text: {r['id']}"); continue
                    if r["id"] not in fn_nr:
                        fn_nr[r["id"]] = len(fn_nr) + 1
                        fussnoten.append({"nr": fn_nr[r["id"]], "text": notizen[r["id"]], "kapitel": k_nr,
                                          "absatz": ai, "anker_text": para["text"][max(0, r["pos"] - 80):r["pos"]]})
        kapitel.append({"title": kapitel_titel(p.headings, f"Kapitel {k_nr}"), "paragraphs": texte,
                        "quelle": it["href"]})

    if not kapitel:
        raise EpubFehler("Kein Inhalt gefunden.")

    # ---- Ausgabe (erst jetzt wird geschrieben)
    mod_dir = os.path.join(bdir, "work", "modernized")
    os.makedirs(mod_dir, exist_ok=True)
    alt = [f for f in os.listdir(mod_dir) if re.match(r"chapter-\d+(\.original)?\.json$", f)]
    for f in alt:                                   # Befund: --force liess alte chapter-N.json liegen
        os.remove(os.path.join(mod_dir, f))
    bericht["kapitel_geleert"] = len(alt)
    img_dir = os.path.join(bdir, "images", "anhang")
    if os.path.isdir(img_dir):
        for f in os.listdir(img_dir):
            if f.startswith("bild-"):
                os.remove(os.path.join(img_dir, f))
    if bild_daten:
        os.makedirs(img_dir, exist_ok=True)
        for name, daten in bild_daten:
            with open(os.path.join(img_dir, name), "wb") as f:
                f.write(daten)
    cov = cover_ablegen(z, src, bdir, titel, autor, label)
    cov["gefunden_ueber"] = wie
    bericht["cover"] = cov
    kt = opf["lange_beschreibung"] or opf["beschreibung"]
    klappentext = {sprache: kt} if kt else {}
    bericht["klappentext"] = "vorhanden" if kt else "keiner im ePub"

    M = config.MARKERS
    zeilen = [f'{M["title"]} {titel}', f'{M["author"]} {autor}', ""]
    for i, k in enumerate(kapitel, 1):
        _dump(os.path.join(mod_dir, f"chapter-{i}.json"), {"title": k["title"], "paragraphs": k["paragraphs"]})
        zeilen += [f'{M["chapter"]} {k["title"]}', ""]
        for t in k["paragraphs"]:
            if t != HR:
                zeilen += [t, ""]
    text = "\n".join(zeilen).strip() + "\n"
    _schreib_text(os.path.join(bdir, "raw_modernized.txt"), text)
    _schreib_text(os.path.join(bdir, "raw.txt"), text)
    _dump(os.path.join(bdir, "work", "anhang.json"), {
        "bilder": bilder, "fussnoten": fussnoten,
        "regeln": {"bilder": "Anhang 'Bilder' am Werkende, Link am vorangehenden Satz",
                   "fussnoten": "Anhang 'Anmerkungen' am Werkende, Link am Satz; uebersetzen ja, vertonen nein"}})

    zeichen = sum(len(t) for k in kapitel for t in k["paragraphs"] if t != HR)
    umfang = {"kapitel": len(kapitel), "zeichen": zeichen, "einheiten_50k": -(-zeichen // 50000),
              "bilder": len(bilder), "fussnoten": len(fussnoten), "spine_zeichen": spine_zeichen,
              "inhaltsanteil": round(zeichen / spine_zeichen, 3) if spine_zeichen else None}
    bericht.update(kapitel=[{"nr": i, "titel": k["title"], "absaetze": len(k["paragraphs"]), "quelle": k["quelle"]}
                            for i, k in enumerate(kapitel, 1)], umfang=umfang)
    _dump(os.path.join(bdir, "work", "ingest_bericht.json"), bericht)
    felder = {
        "book_slug": book_id, "autor_name": autor, "label": label, "publisher": label,
        "titel_original": titel, "originalsprache": sprache, "quellsprache": sprache,
        "quelle_epub": {"datei": os.path.basename(epub_path), "sha256": sha},
        "cover": cov.get("datei"), "klappentext": klappentext,
        "klappentext_vorhanden": bool(kt), "umfang": umfang, "epub_import": opt,
    }
    print(f"[150] {book_id}: {len(kapitel)} Kapitel, {zeichen:,} Zeichen, Inhaltsanteil "
          f"{umfang['inhaltsanteil']}, {len(bilder)} Bilder, {len(fussnoten)} Fussnoten")
    print(f"      Cover: {cov.get('gefunden_ueber') or 'neu erzeugt'} | Klappentext: {bericht['klappentext']}")
    print(f"      entfernt: {', '.join(e['datei'] for e in bericht['entfernt']) or '-'}")
    for w in bericht["warnungen"]:
        print(f"      WARNUNG: {w}")
    return bericht, felder


def _book_mischen(bdir, felder, neu_basis=None):
    """Import-Felder in book.json uebernehmen; alle anderen Felder (Rechte, Mandant, Produkte, Titel je
    Sprache, Casting-Verweise ...) bleiben erhalten (Befund: Neueinlesen ueberschrieb book.json)."""
    p = os.path.join(bdir, "book.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            b = json.load(f)
    else:
        b = dict(neu_basis or {})
    b.update(felder)
    fass = [x for x in b.get("fassungen", []) if isinstance(x, dict)]
    eintrag = next((x for x in fass if x.get("sprache") == felder["quellsprache"]), None)
    if eintrag is None:
        fass.append({"sprache": felder["quellsprache"], "titel": felder["titel_original"],
                     "titel_quelle": "epub", "titel_pruefen": False})
    elif eintrag.get("titel_quelle") in (None, "epub"):
        eintrag.update(titel=felder["titel_original"], titel_quelle="epub")
    b["fassungen"] = fass
    _dump(p, b)
    return b


def epub_finden(ordner, roh):
    d = (roh.get("quelle_epub") or {}).get("datei")
    if d:
        for p in (os.path.join(ordner, "quelle", d), os.path.join(ordner, d)):
            if os.path.exists(p):
                return p
    return None


def pruefen(g, ordner, roh, b):
    """Gate 150 aus ingest_bericht.json + Ausgabedateien."""
    bp = os.path.join(ordner, "work", "ingest_bericht.json")
    try:
        with open(bp, encoding="utf-8") as f:
            ber = json.load(f)
    except (OSError, ValueError):
        g.pflicht("bericht", False, ruecksprung="150", text="ingest_bericht.json fehlt – ePub neu einlesen (--force)")
        return
    um = ber.get("umfang") or roh.get("umfang") or {}
    mod = os.path.join(ordner, "work", "modernized")
    n_dat = len([f for f in os.listdir(mod) if re.match(r"chapter-\d+\.json$", f)]) if os.path.isdir(mod) else 0
    n = um.get("kapitel") or 0
    g.pflicht("drm_frei", True, text="ePub lesbar, DRM-frei (eingelesen)")
    g.min("kapitel", n, 1, bei_fehler="stopp", ruecksprung="150")
    g.pflicht("kapitel_dateien", n_dat == n and os.path.exists(os.path.join(ordner, "raw_modernized.txt")),
              wert=n_dat, ruecksprung="150",
              text=f"chapter-N.json {n_dat} = Kapitel {n}, raw_modernized.txt " +
                   ("da" if os.path.exists(os.path.join(ordner, "raw_modernized.txt")) else "fehlt"))
    g.min("zeichen", um.get("zeichen") or 0, MIN_ZEICHEN, bei_fehler="stopp", ruecksprung="150")
    anteil = um.get("inhaltsanteil")
    if anteil is None:
        g.hinweis("inhaltsanteil", False, text="Inhaltsanteil unbekannt (Altbericht) – --force misst ihn")
    else:
        g.min("inhaltsanteil", anteil, MIN_INHALTSANTEIL, bei_fehler="mensch", ruecksprung="150")
    w = ber.get("warnungen") or []
    g.pruefe("warnungen", not w, len(w), "= 0", "mensch", "150",
             f"Warnungen im Bericht: {len(w)}" + (f" ({'; '.join(w[:5])})" if w else ""))
    opf = ber.get("opf_sprache", ber.get("sprache"))
    ueberschrieben = (roh.get("epub_import") or {}).get("sprache_regler")
    g.pflicht("sprache_opf", bool(opf) or bool(ueberschrieben), wert=opf, bei_fehler="mensch", ruecksprung="150",
              text="Sprache im OPF " + (repr(opf) if opf else "fehlt (en angenommen) – Regler --sprache"))
    q = b.quellsprache
    g.pflicht("sprache", q in bestellung_sprachliste(), wert=q, bei_fehler="mensch", ruecksprung="150",
              text=f"Quellsprache {q!r} " + ("in Sprachliste" if q in bestellung_sprachliste()
                                              else "nicht in Sprachliste – Anfrage, Stopp bis freigeschaltet"))
    g.metrik("klappentext_vorhanden", bool(roh.get("klappentext_vorhanden", bool(roh.get("klappentext")))))
    g.metrik("bilder", um.get("bilder"))
    g.metrik("fussnoten", um.get("fussnoten"))
    g.metrik("entfernt", [e["datei"] for e in ber.get("entfernt", [])])
    g.metrik("mandant", b.mandant)
    return ber


def bestellung_sprachliste():
    from pipeline import bestellung
    return bestellung.sprachliste()


def _gate(werk, slug, ordner, wer):
    from pipeline import bestellung, gate
    b = bestellung.lesen(werk)
    g = gate.Gate(slug, STAGE, ruecksprung="150", wer=wer)
    ber = pruefen(g, ordner, b.roh, b)
    verlag = b.mandant_art == "verlag"
    liste = "; ".join(f"{k['nr']} {k['titel']}" for k in (ber or {}).get("kapitel", [])[:40])
    e = g.entscheide(mensch_immer=verlag, mensch_grund=f"Mandant verlag: Kapitelliste pruefen – {liste}")
    print(g.bericht())
    return e


def run(werk, wer=None, force=False, titel=None, autor=None, sprache=None, behalten=None, entfernen=None,
        bilder=None, fussnoten=None, cover=None, epub=None):
    """Gate 150 fuer ein vorhandenes ePub-Werk (Kette). Regler/--force -> neu einlesen aus der Quelldatei
    (Werkordner/quelle/<datei>), sonst Pruefung der vorhandenen Ausgabe. Rueckgabe auto | mensch | stopp."""
    from pipeline import bestellung, gate, s080_mandant
    wer = s080_mandant.nutzer(wer)
    ordner = bestellung.werkordner(werk)
    slug = os.path.basename(os.path.normpath(ordner))
    roh = bestellung.lesen(werk).roh
    regler = any(x not in (None, [], ()) for x in (titel, autor, sprache, behalten, entfernen, bilder, fussnoten,
                                                   cover, epub))
    if regler or force:
        s080_mandant.darf(werk, "bestellen", wer)
        opt = dict(OPT_STANDARD, **(roh.get("epub_import") or {}))
        opt["seiten"] = dict(opt.get("seiten") or {})
        for d in behalten or []:
            opt["seiten"][d] = "behalten"
        for d in entfernen or []:
            opt["seiten"][d] = "entfernen"
        if bilder is not None:
            opt["bilder"] = bool(bilder)
        if fussnoten is not None:
            opt["fussnoten"] = bool(fussnoten)
        if cover:
            opt["cover"] = cover
        if sprache:
            opt["sprache_regler"] = sprache
        pfad = epub or epub_finden(ordner, roh)
        g = gate.Gate(slug, STAGE, ruecksprung="150", wer=wer)
        if not pfad:
            g.pflicht("epub_datei", False, ruecksprung="150",
                      text=f"Quell-ePub {(roh.get('quelle_epub') or {}).get('datei')!r} nicht im Werkordner/quelle – "
                           f"Regler --epub DATEI")
            e = g.entscheide(); print(g.bericht()); return e
        try:
            _, felder = importieren(pfad, ordner, slug, roh.get("owner_name") or roh.get("besitzer") or "user",
                                    titel=titel or (roh.get("epub_import") or {}).get("titel_regler"),
                                    autor=autor or (roh.get("epub_import") or {}).get("autor_regler"),
                                    sprache=sprache or opt.get("sprache_regler"), opt=opt)
        except EpubFehler as ex:
            g.pflicht("epub", False, wert=str(ex), ruecksprung="090",
                      text=f"ePub abgelehnt: {ex} (Datei defekt/DRM -> 090)")
            e = g.entscheide(); print(g.bericht()); return e
        if titel:
            felder["epub_import"]["titel_regler"] = titel
        if autor:
            felder["epub_import"]["autor_regler"] = autor
        _quelle_sichern(pfad, ordner)
        _book_mischen(ordner, felder)
    return _gate(werk, slug, ordner, wer)


def _quelle_sichern(pfad, ordner):
    """Quell-ePub nach <werk>/quelle/ kopieren (Grundlage fuer Neueinlesen per Regler)."""
    ziel = os.path.join(ordner, "quelle", os.path.basename(pfad))
    if os.path.abspath(pfad) != os.path.abspath(ziel):
        os.makedirs(os.path.dirname(ziel), exist_ok=True)
        shutil.copy2(pfad, ziel)


def neu_anlegen(epub_path, user, titel=None, autor=None, sprache=None, force=False, mandant=None, wer=None,
                opt=None):
    """Neuanlage aus einer ePub-Datei (TAELLA-Upload) + Gate 150. Index erst nach erfolgreichem Einlesen.
    Rueckgabe (book_id, ergebnis)."""
    from pipeline import s080_mandant
    user_name = user.strip()
    uid = re.sub(r"[^a-z0-9]", "", config.slugify(user_name)) or "user"
    z, opf_path = oeffnen(epub_path)            # DRM/defekt -> EpubFehler vor jeder Ablage
    opf = opf_lesen(z, opf_path)
    t = titel or opf["titel"] or os.path.splitext(os.path.basename(epub_path))[0]
    book_id = f"u-{uid}-{config.slugify(t)}"
    bdir = os.path.join(config.USERS_DIR, uid, "works", book_id)
    if os.path.exists(os.path.join(bdir, "book.json")) and not force:
        print(f"[150] {book_id} existiert schon -> python -m pipeline.s150_epub_import {book_id} --force")
        return book_id, None
    o = dict(OPT_STANDARD, **(opt or {}))
    if sprache:
        o["sprache_regler"] = sprache
    if titel:
        o["titel_regler"] = titel
    if autor:
        o["autor_regler"] = autor
    _, felder = importieren(epub_path, bdir, book_id, user_name, titel, autor, sprache, o)
    mandant = mandant or f"user:{uid}"
    quelle = "verlag_epub" if mandant.startswith("verlag:") else "user_epub"
    basis = {"author_slug": "", "herkunft": "privat_upload", "owner_uid": uid, "owner_name": user_name,
             "quelle": quelle, "mandant": mandant, "besitzer": uid, "fassungen": [],
             "angelegt": datetime.now().isoformat(timespec="seconds")}
    _quelle_sichern(epub_path, bdir)
    _book_mischen(bdir, felder, basis)
    idx = config._load_index()                  # Befund: Index erst nach erfolgreichem Einlesen
    idx.setdefault("books", {})[book_id] = f"user:{uid}"
    config._save_index(idx)
    e = _gate(book_id, book_id, bdir, s080_mandant.nutzer(wer))
    print(f"\nWeiter: python -m pipeline.s090_eingang {book_id} --versichern eigene ; python run.py {book_id}")
    return book_id, e


def main(argv=None):
    import argparse
    from pipeline import gate
    ap = argparse.ArgumentParser(description="Stage 150 ePub-Import")
    ap.add_argument("ziel", help="ePub-Datei (Neuanlage) oder Book-ID/Werkordner (Gate/Neueinlesen)")
    ap.add_argument("--user", help="Neuanlage: Nutzername")
    ap.add_argument("--mandant", help="Neuanlage: user:<uid> | verlag:<id>")
    ap.add_argument("--wer")
    ap.add_argument("--titel")
    ap.add_argument("--autor")
    ap.add_argument("--sprache", help="Sprache ueberschreiben (statt OPF)")
    ap.add_argument("--behalten", action="append", default=[], metavar="DATEI", help="Seite erzwingen: behalten")
    ap.add_argument("--entfernen", action="append", default=[], metavar="DATEI", help="Seite erzwingen: entfernen")
    ap.add_argument("--bilder", choices=("ja", "nein"))
    ap.add_argument("--fussnoten", choices=("ja", "nein"))
    ap.add_argument("--cover", choices=("epub", "neu"), help="Cover uebernehmen oder neu (TAELLA-Standard)")
    ap.add_argument("--epub", help="Quell-ePub fuer Neueinlesen (sonst <werk>/quelle/<datei>)")
    ap.add_argument("--force", action="store_true", help="Neu einlesen (leert den Kapitelordner)")
    a = ap.parse_args(argv)
    jn = lambda v: None if v is None else v == "ja"
    try:
        if a.ziel.lower().endswith(".epub") and os.path.isfile(a.ziel):
            opt = {"seiten": {**{d: "behalten" for d in a.behalten}, **{d: "entfernen" for d in a.entfernen}}}
            if a.bilder:
                opt["bilder"] = jn(a.bilder)
            if a.fussnoten:
                opt["fussnoten"] = jn(a.fussnoten)
            if a.cover:
                opt["cover"] = a.cover
            _, e = neu_anlegen(a.ziel, a.user or "user", a.titel, a.autor, a.sprache, a.force, a.mandant, a.wer, opt)
            return 0 if e is None else gate.EXIT[e]
        e = run(a.ziel, a.wer, a.force, a.titel, a.autor, a.sprache, a.behalten, a.entfernen,
                jn(a.bilder), jn(a.fussnoten), a.cover, a.epub)
        return gate.EXIT[e]
    except EpubFehler as e:
        print(f"[150] ABGELEHNT: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
