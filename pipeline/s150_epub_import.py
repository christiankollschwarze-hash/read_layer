"""STAGE 150 — ePub-Import
Funktion:     Bringt ein DRM-freies User-ePub ins Pipeline-Format (TAELLA-Upload).
Wirkungsweise: Prueft ZIP/DRM/Sprache, klassifiziert Seiten, parst Kapitel, uebernimmt Cover, Klappentext, Bilder, Fussnoten.
Komponenten:  pipeline/s150_epub_import.py
Zulieferer:   User-ePub (users/<uid>/works/<id>/)
Abnehmer:     s200 Tagging (raw_modernized.txt, Kapitel-Checkpoints), s710 Cloud-Export (privater Bereich)
(Nomenklatur seit 18.10.2026, Uebersicht: docs/Pipeline_Strang_Matrix.xlsx)

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
def run(epub_path, user, titel=None, force=False):
    user_name = user.strip()
    uid = re.sub(r"[^a-z0-9]", "", config.slugify(user_name)) or "user"
    bericht = {"datei": os.path.basename(epub_path), "zeit": datetime.now().isoformat(timespec="seconds"),
               "user": user_name, "entfernt": [], "inhalt": [], "notizseiten": [], "warnungen": []}

    # 05a
    z, opf_path = oeffnen(epub_path)
    opf = opf_lesen(z, opf_path)
    sha = hashlib.sha256(open(epub_path, "rb").read()).hexdigest()
    sprache = (opf["sprache"] or "en").split("-")[0].lower()
    titel = titel or opf["titel"] or os.path.splitext(os.path.basename(epub_path))[0]
    autor = opf["autor"] or "Unbekannt"
    book_id = f"u-{uid}-{config.slugify(titel)}"
    label = f"TÆLLA-User: {user_name}"
    bericht.update(titel=titel, titel_kandidaten=opf["titel_alle"], autor=autor, sprache=sprache,
                   book_id=book_id, sha256=sha)

    bdir = os.path.join(config.USERS_DIR, uid, "works", book_id)
    if os.path.exists(os.path.join(bdir, "book.json")) and not force:
        print(f"[05] {book_id} existiert schon -> --force zum Neuaufbau"); return book_id
    # --force: Dateien werden ueberschrieben (kein Loeschen des Ordners)
    os.makedirs(os.path.join(bdir, "work", "modernized"), exist_ok=True)

    # Index (vor book_dir-Aufrufen anderer Stages)
    idx = config._load_index()
    idx.setdefault("books", {})[book_id] = f"user:{uid}"
    config._save_index(idx)

    # 05b Cover
    src, wie = cover_finden(z, opf)
    cov = cover_ablegen(z, src, bdir, titel, autor, label)
    cov["gefunden_ueber"] = wie
    bericht["cover"] = cov
    cover_bild = src

    # 05c Klappentext
    kt = opf["lange_beschreibung"] or opf["beschreibung"]
    klappentext = {sprache: kt} if kt else {}
    bericht["klappentext"] = "vorhanden" if kt else "keiner im ePub"

    # 05d Seiten klassifizieren
    seiten = []
    for idref in opf["spine"]:
        it = opf["items"].get(idref)
        if not it or not it.get("media-type", "").startswith("application/xhtml"):
            continue
        art, grund, s = seite_klassifizieren(z, it)
        seiten.append((it, art, grund, s))
        rec = {"datei": it["href"], "grund": grund}
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
        if art == "weg" and ns.notizen:          # reine Anmerkungsseite, z.B. EPUB2 ohne epub:type
            seiten[idx_s] = (it, "notizen", "Anmerkungsseite (Link-Ziele)", s)
            bericht["entfernt"] = [e for e in bericht["entfernt"] if e["datei"] != it["href"]]
            bericht["notizseiten"].append({"datei": it["href"], "grund": "Anmerkungsseite (Link-Ziele)"})

    # Kapitel parsen
    kapitel, bilder, fussnoten = [], [], []
    fn_nr = {}
    img_dir = os.path.join(bdir, "images", "anhang")
    for it, art, _, s in seiten:
        if art != "inhalt":
            continue
        p = Kapitelparser(set(notizen.keys())); p.feed(s); p._flush()
        k_nr = len(kapitel) + 1
        paras = [x for x in p.paras]
        # Bilder (05e)
        for ev in p.events:
            pfad = posixpath.normpath(posixpath.join(posixpath.dirname(it["path"]), ev["src"]))
            if pfad == cover_bild:
                continue
            try:
                daten = z.read(pfad)
            except KeyError:
                bericht["warnungen"].append(f"Bild fehlt: {pfad}"); continue
            n = len(bilder) + 1
            os.makedirs(img_dir, exist_ok=True)
            ext = os.path.splitext(pfad)[1].lower()
            open(os.path.join(img_dir, f"bild-{n}{ext}"), "wb").write(daten)
            bilder.append({"nr": n, "datei": f"images/anhang/bild-{n}{ext}", "kapitel": k_nr,
                           "nach_absatz": ev["nach_absatz"], "anker_text": ev["anker_text"],
                           "alt": ev["alt"], "bildunterschrift": ev.get("bildunterschrift", "")})
        # Fussnoten-Anker (05f)
        for ai, para in enumerate(paras):
            for r in para["refs"]:
                if r["id"] not in notizen:
                    bericht["warnungen"].append(f"Fussnote ohne Text: {r['id']}"); continue
                if r["id"] not in fn_nr:
                    fn_nr[r["id"]] = len(fn_nr) + 1
                    fussnoten.append({"nr": fn_nr[r["id"]], "text": notizen[r["id"]], "kapitel": k_nr,
                                      "absatz": ai, "anker_text": para["text"][max(0, r["pos"] - 80):r["pos"]]})
        titel_k = kapitel_titel(p.headings, f"Kapitel {k_nr}")
        texte = [x["text"] for x in paras]
        if not [t for t in texte if t != HR]:
            bericht["warnungen"].append(f"leer nach Bereinigung: {it['href']}"); continue
        kapitel.append({"title": titel_k, "paragraphs": texte, "quelle": it["href"]})

    if not kapitel:
        raise EpubFehler("Kein Inhalt gefunden.")

    # Ausgabe
    M = config.MARKERS
    zeilen = [f'{M["title"]} {titel}', f'{M["author"]} {autor}', ""]
    for i, k in enumerate(kapitel, 1):
        json.dump({"title": k["title"], "paragraphs": k["paragraphs"]},
                  open(os.path.join(bdir, "work", "modernized", f"chapter-{i}.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        zeilen += [f'{M["chapter"]} {k["title"]}', ""]
        for t in k["paragraphs"]:
            if t != HR:
                zeilen += [t, ""]
    text = "\n".join(zeilen).strip() + "\n"
    open(os.path.join(bdir, "raw_modernized.txt"), "w", encoding="utf-8").write(text)
    open(os.path.join(bdir, "raw.txt"), "w", encoding="utf-8").write(text)

    json.dump({"bilder": bilder, "fussnoten": fussnoten,
               "regeln": {"bilder": "Anhang 'Bilder' am Werkende, Link am vorangehenden Satz",
                          "fussnoten": "Anhang 'Anmerkungen' am Werkende, Link am Satz; uebersetzen ja, vertonen nein"}},
              open(os.path.join(bdir, "work", "anhang.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    zeichen = sum(len(t) for k in kapitel for t in k["paragraphs"] if t != HR)
    book = {
        "book_slug": book_id, "author_slug": "", "autor_name": autor,
        "herkunft": "privat_upload", "owner_uid": uid, "owner_name": user_name,
        "label": label, "publisher": label,
        "titel_original": titel, "originalsprache": sprache,
        "quelle_epub": {"datei": os.path.basename(epub_path), "sha256": sha},
        "cover": cov.get("datei"), "klappentext": klappentext,
        "umfang": {"kapitel": len(kapitel), "zeichen": zeichen,
                   "einheiten_50k": -(-zeichen // 50000), "bilder": len(bilder), "fussnoten": len(fussnoten)},
        "fassungen": [{"sprache": sprache, "titel": titel, "titel_quelle": "epub", "titel_pruefen": False}],
        "angelegt": bericht["zeit"],
    }
    json.dump(book, open(os.path.join(bdir, "book.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    bericht.update(kapitel=[{"nr": i, "titel": k["title"], "absaetze": len(k["paragraphs"]), "quelle": k["quelle"]}
                            for i, k in enumerate(kapitel, 1)],
                   umfang=book["umfang"])
    json.dump(bericht, open(os.path.join(bdir, "work", "ingest_bericht.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    print(f"[05] {book_id}: {len(kapitel)} Kapitel, {zeichen:,} Zeichen "
          f"({book['umfang']['einheiten_50k']} Einheiten), {len(bilder)} Bilder, {len(fussnoten)} Fussnoten")
    print(f"     Cover: {cov.get('gefunden_ueber') or 'neu erzeugt'} | Klappentext: {bericht['klappentext']}")
    print(f"     entfernt: {', '.join(e['datei'] for e in bericht['entfernt']) or '-'}")
    for w in bericht["warnungen"]:
        print(f"     WARNUNG: {w}")
    return book_id


if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    if not args or args[0].startswith("--"):
        print(__doc__); sys.exit(1)
    def opt(name):
        return args[args.index(name) + 1] if name in args else None
    try:
        run(args[0], opt("--user") or "user", titel=opt("--titel"), force="--force" in args)
    except EpubFehler as e:
        print(f"[05] ABGELEHNT: {e}"); sys.exit(2)
