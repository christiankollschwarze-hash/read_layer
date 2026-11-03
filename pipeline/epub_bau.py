"""ePub-Baukasten (Stages 620/630)
Funktion:     EPUB3 im SOMNIO-Layout aus fertigen Bausteinen: Kapitel (Absaetze aus Satzteilen), Metadaten,
              Klappentext, Kolophon, Anhang (Bilder/Fussnoten), Cover aus 615; Audio-Variante mit
              Media Overlay (SMIL je Kapitel). Dazu Lesen des fertigen EPUB (Gate) und epubcheck.
Wirkungsweise: rein deterministisch, kein LLM; Texte je Sprache der Sprachliste.
Komponenten:  pipeline/epub_bau.py, tools/satzweise.py, tools/epubcheck-5.4.0 (Java)
Zulieferer:   s620_epub_original / s630_epub_zielsprache (Eingaenge, Gate)
Abnehmer:     s620/s630
Datenmodell:  Kapitel = {"titel": str, "titel_id": str|None, "absaetze": [Absatz]}
              Absatz  = {"hr": True} | {"teile": [{"text": str, "id": str|None}], "rolle": str|None,
                                         "refs": [("fn"|"bild", nr)]}
"""

import html
import json
import os
import re
import subprocess
import tempfile
import uuid
import zipfile

from config import config

HR = "——HR——"
NS = uuid.uuid5(uuid.NAMESPACE_DNS, "readlayer.somnio")
BCP47 = {"en": "en", "de": "de", "fr": "fr", "es": "es", "it": "it"}
LOGO_PATH = os.path.join(config.BASE_DIR, "assets", "somnio_logo.svg")
EPUBCHECK = os.path.join(config.BASE_DIR, "tools", "epubcheck-5.4.0", "epubcheck.jar")
AKTIV_KLASSE = "-epub-media-overlay-active"

# ------------------------------------------------------------ Texte je Sprache
TEXTE = {
    "en": {"toc": "Contents", "about": "About this Book", "titelseite": "Title Page", "kolophon": "Colophon",
           "beginn": "Beginning", "kapitel": "Chapter {n}", "bilder": "Images", "noten": "Notes", "bild": "Image",
           "quelle": "This ebook is based on a transcription from {src}.",
           "pd": "The source text is in the public domain.",
           "mod": "The modernization and this edition are © {imprint}.",
           "eigene": "© {jahr} {inhaber}. All rights reserved.",
           "fremd": "All rights remain with the rights holder.",
           "original": "Based on the original ebook supplied by the rights holder."},
    "de": {"toc": "Inhalt", "about": "Über dieses Buch", "titelseite": "Titelseite", "kolophon": "Impressum",
           "beginn": "Beginn", "kapitel": "Kapitel {n}", "bilder": "Abbildungen", "noten": "Anmerkungen",
           "bild": "Abbildung",
           "quelle": "Dieses E-Book beruht auf einer Transkription von {src}.",
           "pd": "Der Quelltext ist gemeinfrei.",
           "mod": "Die Modernisierung und diese Ausgabe sind © {imprint}.",
           "eigene": "© {jahr} {inhaber}. Alle Rechte vorbehalten.",
           "fremd": "Alle Rechte liegen beim Rechteinhaber.",
           "original": "Grundlage ist das vom Rechteinhaber bereitgestellte Original-E-Book."},
    "fr": {"toc": "Table des matières", "about": "À propos de ce livre", "titelseite": "Page de titre",
           "kolophon": "Colophon", "beginn": "Début", "kapitel": "Chapitre {n}", "bilder": "Illustrations",
           "noten": "Notes", "bild": "Illustration",
           "quelle": "Ce livre numérique repose sur une transcription de {src}.",
           "pd": "Le texte source appartient au domaine public.",
           "mod": "La modernisation et cette édition sont © {imprint}.",
           "eigene": "© {jahr} {inhaber}. Tous droits réservés.",
           "fremd": "Tous les droits restent au titulaire des droits.",
           "original": "D’après le livre numérique original fourni par le titulaire des droits."},
    "es": {"toc": "Índice", "about": "Sobre este libro", "titelseite": "Portada", "kolophon": "Colofón",
           "beginn": "Inicio", "kapitel": "Capítulo {n}", "bilder": "Ilustraciones", "noten": "Notas",
           "bild": "Ilustración",
           "quelle": "Este libro electrónico se basa en una transcripción de {src}.",
           "pd": "El texto original es de dominio público.",
           "mod": "La modernización y esta edición son © {imprint}.",
           "eigene": "© {jahr} {inhaber}. Todos los derechos reservados.",
           "fremd": "Todos los derechos pertenecen al titular de los derechos.",
           "original": "Basado en el libro electrónico original facilitado por el titular de los derechos."},
    "it": {"toc": "Indice", "about": "Informazioni sul libro", "titelseite": "Frontespizio",
           "kolophon": "Colophon", "beginn": "Inizio", "kapitel": "Capitolo {n}", "bilder": "Illustrazioni",
           "noten": "Note", "bild": "Illustrazione",
           "quelle": "Questo ebook si basa su una trascrizione di {src}.",
           "pd": "Il testo originale è di pubblico dominio.",
           "mod": "La modernizzazione e questa edizione sono © {imprint}.",
           "eigene": "© {jahr} {inhaber}. Tutti i diritti riservati.",
           "fremd": "Tutti i diritti restano al titolare dei diritti.",
           "original": "Basato sull’ebook originale fornito dal titolare dei diritti."},
}


def text(lg, schluessel, **kw):
    t = TEXTE.get(lg, TEXTE["en"])[schluessel]
    return t.format(**kw) if kw else t


def esc(s):
    return html.escape(str(s), quote=False)


def esc_attr(s):
    return html.escape(str(s), quote=True)


CORE_CSS = """@charset "utf-8";
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

LOCAL_CSS = """@charset "utf-8";
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

ZUSATZ_CSS = """
.noteref, .bildref{ font-size: .75em; vertical-align: super; text-decoration: none; }
.rolle{ font-variant: small-caps; }
.anhang figure{ margin: 2em 0; text-align: center; }
.anhang img{ max-width: 100%; }
.anhang ol li{ margin: .5em 0; }
.kolophon-vermerk{ font-style: italic; }
.""" + AKTIV_KLASSE + """{ background-color: #f3e6c8; }
"""


# ------------------------------------------------------------ Signet
def signet_svg(color="#8a7f70", width=130):
    """Hai-Signet (nur Imprint SOMNIO) mit festen Massen."""
    if not os.path.exists(LOGO_PATH):
        return ""
    with open(LOGO_PATH, encoding="utf-8") as f:
        raw = f.read()
    m = re.search(r'viewBox="([^"]+)"', raw)
    vb = m.group(1) if m else "0 0 1280 714"
    try:
        _, _, vbw, vbh = (float(x) for x in vb.split())
        height = max(1, round(width * vbh / vbw))
    except ValueError:
        height = round(width * 0.56)
    g = re.search(r"(<g\b.*?</g>)", raw, re.S)
    inner = re.sub(r'fill="#0{3,6}"', f'fill="{color}"', g.group(1) if g else "")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" class="signet" width="{width}" height="{height}" '
            f'viewBox="{vb}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="SOMNIO">{inner}</svg>')


# ------------------------------------------------------------ Mobil-Absaetze
def mobil_teilen(absatz, laenge):
    """Absatz -> Liste von Teilstuecken (je Liste von Satzteilen), Schnitt nur an Satzgrenzen."""
    teile = absatz["teile"]
    if not laenge:
        return [teile]
    out, cur, n = [], [], 0
    for t in teile:
        lt = len(t["text"])
        if cur and n + 1 + lt > laenge:
            out.append(cur)
            cur, n = [], 0
        cur.append(t)
        n += lt + (1 if n else 0)
    if cur:
        out.append(cur)
    return out


# ------------------------------------------------------------ XHTML
def _seite(lang, titel, body, typ="bodymatter", css=True, wurzel="../"):
    links = (f'\t\t<link href="{wurzel}css/core.css" rel="stylesheet" type="text/css"/>\n' if css else "") + \
        f'\t\t<link href="{wurzel}css/local.css" rel="stylesheet" type="text/css"/>\n'
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
            'epub:prefix="z3998: http://www.daisy.org/z3998/2012/vocab/structure/#" '
            f'xml:lang="{lang}" lang="{lang}">\n'
            f"\t<head>\n\t\t<title>{esc(titel)}</title>\n{links}\t</head>\n"
            f'\t<body epub:type="{typ}">\n{body}\n\t</body>\n</html>\n')


def _satzteil(t):
    return f'<span id="{esc_attr(t["id"])}">{esc(t["text"])}</span>' if t.get("id") else esc(t["text"])


def _ref(art, nr, lg):
    if art == "fn":
        return f'<a epub:type="noteref" class="noteref" href="anhang.xhtml#fn-{nr}">{nr}</a>'
    return f'<a class="bildref" href="anhang.xhtml#bild-{nr}">[{esc(text(lg, "bild"))} {nr}]</a>'


def kapitel_xhtml(idx, kap, lang, mobil, mit_titel=False):
    titel = kap.get("titel") or text(lang, "kapitel", n=idx)
    zeilen = []
    if mit_titel:                                      # Audio-Variante: Titel im Kapitel (SMIL je Dokument)
        hid = f' id="{esc_attr(kap["titel_id"])}"' if kap.get("titel_id") else ""
        zeilen.append(f'\t\t\t<h1 epub:type="title"><span{hid}>{esc(titel)}</span></h1>')
    for a in kap["absaetze"]:
        if a.get("hr"):
            zeilen.append("\t\t\t<hr/>")
            continue
        stuecke = mobil_teilen(a, mobil)
        for i, st in enumerate(stuecke):
            inhalt = " ".join(_satzteil(t) for t in st)
            if i == 0 and a.get("rolle"):
                inhalt = f'<span class="rolle">{esc(a["rolle"])}.</span> ' + inhalt
            if i == len(stuecke) - 1:
                inhalt += "".join(_ref(r[0], r[1], lang) for r in a.get("refs") or [])
            zeilen.append(f"\t\t\t<p>{inhalt}</p>")
    body = (f'\t\t<section id="chapter-{idx}-body" epub:type="chapter">\n' + "\n".join(zeilen) +
            "\n\t\t</section>")
    return _seite(lang, titel, body, "bodymatter z3998:fiction")


def kapitel_titel_xhtml(idx, kap, lang, signet):
    titel = kap.get("titel") or text(lang, "kapitel", n=idx)
    body = (f'\t\t<section id="chapter-{idx}" epub:type="chapter" class="chapter-title-page">\n'
            f'\t\t\t<h1 epub:type="title">{esc(titel)}</h1>\n' + (f"\t\t\t{signet}\n" if signet else "") +
            "\t\t</section>")
    return _seite(lang, titel, body, "bodymatter z3998:fiction")


def cover_xhtml(lang, datei):
    body = ('\t\t<section id="cover" epub:type="cover">\n'
            f'\t\t\t<img src="../images/{datei}" alt="Cover" class="cover-image"/>\n\t\t</section>')
    return _seite(lang, "Cover", body, "cover", css=False)


def klappentext_xhtml(lang, blurb):
    z = ['\t\t<section epub:type="frontmatter" class="blurb">']
    for q in blurb.get("koeder") or []:
        z.append(f'\t\t\t<p class="epigraph">{esc(q)}</p>')
    ein, au = blurb.get("einordnung") or [], blurb.get("autor") or []
    if blurb.get("koeder") and (ein or au):
        z.append("\t\t\t<hr/>")
    z += [f"\t\t\t<p>{esc(p)}</p>" for p in ein]
    if au:
        z.append("\t\t\t<hr/>")
        z += [f'\t\t\t<p class="author-note">{esc(p)}</p>' for p in au]
    z.append("\t\t</section>")
    return _seite(lang, text(lang, "about"), "\n".join(z), "frontmatter")


def titelseite_xhtml(lang, titel, autor, imprint):
    body = ('\t\t<section id="titlepage" epub:type="titlepage">\n'
            f'\t\t\t<h1 epub:type="title">{esc(titel)}</h1>\n' +
            (f'\t\t\t<p epub:type="z3998:author">{esc(autor)}</p>\n' if autor else "") +
            (f'\t\t\t<p class="imprint">{esc(imprint)}</p>\n' if imprint else "") + "\t\t</section>")
    return _seite(lang, text(lang, "titelseite"), body, "frontmatter")


def kolophon_xhtml(lang, meta):
    z = ['\t\t<section id="colophon" epub:type="colophon">',
         f'\t\t\t<h2 epub:type="title">{esc(text(lang, "kolophon"))}</h2>']
    if meta.get("imprint"):
        z.append(f'\t\t\t<p class="imprint">{esc(meta["imprint"])}</p>')
    z.append(f"\t\t\t<p><i>{esc(meta['titel'])}</i>" + (f"<br/>{esc(meta['autor'])}" if meta.get("autor") else "")
             + "</p>")
    for v in meta.get("vermerke") or []:
        z.append(f'\t\t\t<p class="kolophon-vermerk">{esc(v)}</p>')
    if meta.get("quelle_url"):
        link = f'<a href="{esc_attr(meta["quelle_url"])}">Project Gutenberg</a>'
        z.append("\t\t\t<p>" + esc(text(lang, "quelle", src="\x00")).replace("\x00", link) + "</p>")
    for zeile in meta.get("kolophon") or []:
        z.append(f"\t\t\t<p>{esc(zeile)}</p>")
    z.append("\t\t</section>")
    return _seite(lang, text(lang, "kolophon"), "\n".join(z), "backmatter")


def anhang_xhtml(lang, bilder, noten):
    z = ['\t\t<section id="anhang" class="anhang" epub:type="appendix">']
    if bilder:
        z.append(f'\t\t\t<h2>{esc(text(lang, "bilder"))}</h2>')
        for b in bilder:
            cap = f"<figcaption>{esc(b['unterschrift'])}</figcaption>" if b.get("unterschrift") else ""
            z.append(f'\t\t\t<figure id="bild-{b["nr"]}"><img src="../images/anhang/{esc_attr(b["name"])}" '
                     f'alt="{esc_attr(b.get("alt") or text(lang, "bild") + " " + str(b["nr"]))}"/>{cap}</figure>')
    if noten:
        z.append(f'\t\t\t<h2>{esc(text(lang, "noten"))}</h2>\n\t\t\t<ol>')
        for n in noten:
            z.append(f'\t\t\t\t<li id="fn-{n["nr"]}" epub:type="footnote">{esc(n["text"])}</li>')
        z.append("\t\t\t</ol>")
    z.append("\t\t</section>")
    return _seite(lang, text(lang, "bilder" if bilder and not noten else "noten"), "\n".join(z), "backmatter")


def nav_xhtml(lang, kapitel, hat_blurb, hat_anhang, audio):
    li = []
    if hat_blurb:
        li.append(f'<li><a href="text/blurb.xhtml">{esc(text(lang, "about"))}</a></li>')
    li.append(f'<li><a href="text/titlepage.xhtml">{esc(text(lang, "titelseite"))}</a></li>')
    for i, k in enumerate(kapitel, 1):
        ziel = f"chapter-{i}.xhtml" if audio else f"chapter-{i}-title.xhtml"
        li.append(f'<li><a href="text/{ziel}">{esc(k.get("titel") or text(lang, "kapitel", n=i))}</a></li>')
    if hat_anhang:
        li.append(f'<li><a href="text/anhang.xhtml">{esc(text(lang, "noten" if hat_anhang == "noten" else "bilder"))}'
                  '</a></li>')
    li.append(f'<li><a href="text/colophon.xhtml">{esc(text(lang, "kolophon"))}</a></li>')
    erstes = "chapter-1.xhtml" if audio else "chapter-1-title.xhtml"
    body = ('\t\t<nav id="toc" epub:type="toc">\n'
            f'\t\t\t<h2 epub:type="title">{esc(text(lang, "toc"))}</h2>\n\t\t\t<ol>\n' +
            "\n".join("\t\t\t\t" + x for x in li) + "\n\t\t\t</ol>\n\t\t</nav>\n"
            '\t\t<nav id="landmarks" epub:type="landmarks" hidden="hidden">\n\t\t\t<ol>\n'
            f'\t\t\t\t<li><a href="text/titlepage.xhtml" epub:type="titlepage">{esc(text(lang, "titelseite"))}</a></li>\n'
            f'\t\t\t\t<li><a href="text/{erstes}" epub:type="bodymatter">{esc(text(lang, "beginn"))}</a></li>\n'
            "\t\t\t</ol>\n\t\t</nav>")
    return _seite(lang, text(lang, "toc"), body, "frontmatter", css=False, wurzel="")


# ------------------------------------------------------------ Media Overlay
def uhr(s):
    s = max(0.0, float(s))
    h, rest = divmod(s, 3600)
    m, sek = divmod(rest, 60)
    return f"{int(h)}:{int(m):02d}:{sek:06.3f}"


def smil(idx, audio_name, clips):
    pars = [f'\t\t\t<par id="par-{i}"><text src="../text/chapter-{idx}.xhtml#{esc_attr(tid)}"/>'
            f'<audio src="../audio/{esc_attr(audio_name)}" clipBegin="{a:.3f}s" clipEnd="{e:.3f}s"/></par>'
            for i, (tid, a, e) in enumerate(clips, 1)]
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<smil xmlns="http://www.w3.org/ns/SMIL" xmlns:epub="http://www.idpf.org/2007/ops" version="3.0">\n'
            f'\t<body>\n\t\t<seq id="seq-{idx}" epub:textref="../text/chapter-{idx}.xhtml" epub:type="chapter">\n'
            + "\n".join(pars) + "\n\t\t</seq>\n\t</body>\n</smil>\n")


# ------------------------------------------------------------ OPF + ZIP
def _opf(meta, manifest, spine, dauern):
    lang = BCP47.get(meta["lang"], meta["lang"])
    m = [f'\t\t<dc:identifier id="uid">urn:uuid:{meta["uuid"]}</dc:identifier>',
         f'\t\t<meta property="dcterms:modified">{meta["geaendert"]}</meta>',
         f'\t\t<dc:title id="title">{esc(meta["titel"])}</dc:title>',
         f'\t\t<dc:language>{lang}</dc:language>']
    if meta.get("autor"):
        m += [f'\t\t<dc:creator id="author">{esc(meta["autor"])}</dc:creator>',
              f'\t\t<meta property="file-as" refines="#author">{esc(meta.get("autor_sort") or meta["autor"])}</meta>',
              '\t\t<meta property="role" refines="#author" scheme="marc:relators">aut</meta>']
    if meta.get("publisher"):
        m.append(f'\t\t<dc:publisher>{esc(meta["publisher"])}</dc:publisher>')
    if meta.get("rechte"):
        m.append(f'\t\t<dc:rights>{esc(meta["rechte"])}</dc:rights>')
    if meta.get("quelle_url"):
        m.append(f'\t\t<dc:source>{esc(meta["quelle_url"])}</dc:source>')
    m.append('\t\t<meta name="cover" content="cover-image"/>')
    if dauern:
        for sid, d in dauern.items():
            m.append(f'\t\t<meta property="media:duration" refines="#{sid}">{uhr(d)}</meta>')
        m.append(f'\t\t<meta property="media:duration">{uhr(sum(dauern.values()))}</meta>')
        m.append(f'\t\t<meta property="media:active-class">{AKTIV_KLASSE}</meta>')
        if meta.get("sprecher"):
            m.append(f'\t\t<meta property="media:narrator">{esc(meta["sprecher"])}</meta>')
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<package xmlns="http://www.idpf.org/2007/opf" dir="ltr" unique-identifier="uid" version="3.0" '
            f'xml:lang="{lang}">\n'
            '\t<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n' + "\n".join(m) + "\n\t</metadata>\n"
            "\t<manifest>\n" + "\n".join(manifest) + "\n\t</manifest>\n"
            "\t<spine>\n" + "\n".join(spine) + "\n\t</spine>\n</package>\n")


def bauen(meta, kapitel, ziel, cover, mobil=0, blurb=None, bilder=(), noten=(), audio=None):
    """Schreibt das EPUB nach `ziel`.
    meta: titel, autor, autor_sort, lang, uuid, geaendert, publisher, imprint, rechte, quelle_url, vermerke,
          kolophon (Zeilen), sprecher. cover: (bytes, media, endung). bilder: [{nr, name, data, media, alt,
          unterschrift}]. noten: [{nr, text}]. audio: {idx: {name, data, media, dauer, clips: [(id, a, e)]}}."""
    lang = BCP47.get(meta["lang"], meta["lang"])
    hat_audio = bool(audio)
    signet = signet_svg() if meta.get("imprint") == "SOMNIO" else ""
    files = {"META-INF/container.xml": (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">\n'
        '\t<rootfiles>\n\t\t<rootfile full-path="epub/content.opf" media-type="application/oebps-package+xml"/>\n'
        "\t</rootfiles>\n</container>\n").encode("utf-8")}
    files["epub/css/core.css"] = CORE_CSS.encode("utf-8")
    files["epub/css/local.css"] = (LOCAL_CSS + ZUSATZ_CSS).encode("utf-8")
    cdata, cmedia, cend = cover
    files[f"epub/images/cover.{cend}"] = cdata
    manifest = ['\t\t<item href="css/core.css" id="core.css" media-type="text/css"/>',
                '\t\t<item href="css/local.css" id="local.css" media-type="text/css"/>',
                '\t\t<item href="toc.xhtml" id="toc" media-type="application/xhtml+xml" properties="nav"/>',
                f'\t\t<item href="images/cover.{cend}" id="cover-image" media-type="{cmedia}" '
                'properties="cover-image"/>']
    hat_anhang = "noten" if noten else ("bilder" if bilder else None)
    files["epub/toc.xhtml"] = nav_xhtml(lang, kapitel, bool(blurb), hat_anhang, hat_audio).encode("utf-8")

    seiten = [("cover", "cover.xhtml", cover_xhtml(lang, f"cover.{cend}"), None)]
    if blurb:
        seiten.append(("blurb", "blurb.xhtml", klappentext_xhtml(lang, blurb), None))
    seiten.append(("titlepage", "titlepage.xhtml",
                   titelseite_xhtml(lang, meta["titel"], meta.get("autor"), meta.get("imprint")), None))
    dauern = {}
    for i, k in enumerate(kapitel, 1):
        if not hat_audio:
            seiten.append((f"chapter-{i}-title", f"chapter-{i}-title.xhtml", kapitel_titel_xhtml(i, k, lang, signet),
                           None))
        mo = None
        if hat_audio and i in audio:
            a = audio[i]
            mo = f"smil-{i}"
            files[f"epub/smil/chapter-{i}.smil"] = smil(i, a["name"], a["clips"]).encode("utf-8")
            files[f"epub/audio/{a['name']}"] = a["data"]
            manifest.append(f'\t\t<item href="smil/chapter-{i}.smil" id="{mo}" media-type="application/smil+xml"/>')
            manifest.append(f'\t\t<item href="audio/{esc_attr(a["name"])}" id="audio-{i}" media-type="{a["media"]}"/>')
            dauern[mo] = float(a["dauer"])
        seiten.append((f"chapter-{i}", f"chapter-{i}.xhtml", kapitel_xhtml(i, k, lang, mobil, hat_audio), mo))
    if bilder or noten:
        seiten.append(("anhang", "anhang.xhtml", anhang_xhtml(lang, bilder, noten), None))
        for b in bilder:
            files[f"epub/images/anhang/{b['name']}"] = b["data"]
            manifest.append(f'\t\t<item href="images/anhang/{esc_attr(b["name"])}" id="bild-{b["nr"]}" '
                            f'media-type="{b["media"]}"/>')
    seiten.append(("colophon", "colophon.xhtml", kolophon_xhtml(lang, meta), None))

    spine = []
    for pid, name, data, mo in seiten:
        files[f"epub/text/{name}"] = data.encode("utf-8")
        props = ' properties="svg"' if "<svg" in data else ""
        mo_attr = f' media-overlay="{mo}"' if mo else ""
        manifest.append(f'\t\t<item href="text/{name}" id="{pid}" media-type="application/xhtml+xml"{props}{mo_attr}/>')
        spine.append(f'\t\t<itemref idref="{pid}"/>')
    files["epub/content.opf"] = _opf(meta, manifest, spine, dauern).encode("utf-8")

    os.makedirs(os.path.dirname(os.path.abspath(ziel)), exist_ok=True)
    with zipfile.ZipFile(ziel, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype", (2026, 1, 1, 0, 0, 0)), b"application/epub+zip",
                   compress_type=zipfile.ZIP_STORED)
        for arc, data in files.items():
            komp = zipfile.ZIP_STORED if arc.startswith("epub/audio/") else zipfile.ZIP_DEFLATED
            z.writestr(zipfile.ZipInfo(arc, (2026, 1, 1, 0, 0, 0)), data, compress_type=komp)
    return ziel


# ------------------------------------------------------------ Lesen (Gate)
_ENTF = re.compile(r'<a [^>]*class="(?:noteref|bildref)"[^>]*>.*?</a>|<span class="rolle">.*?</span>', re.S)


def _rein(x):
    x = _ENTF.sub(" ", x)
    x = re.sub(r"<[^>]+>", " ", x)
    return re.sub(r"\s+", " ", html.unescape(x)).strip()


def lesen(pfad):
    """Fertiges EPUB -> {sprache, kapitel: [text], kolophon, noterefs, bildrefs, noten, bilder, smil: {i: [...]},
    audio_dateien: {i: name}}."""
    out = {"kapitel": [], "smil": {}, "noterefs": 0, "bildrefs": 0, "noten": 0, "bilder": 0, "kolophon": "",
           "sprache": None, "titel": None}
    with zipfile.ZipFile(pfad) as z:
        namen = set(z.namelist())
        opf = z.read("epub/content.opf").decode("utf-8")
        m = re.search(r"<dc:language>([^<]+)</dc:language>", opf)
        out["sprache"] = m.group(1) if m else None
        m = re.search(r"<dc:title[^>]*>([^<]+)</dc:title>", opf)
        out["titel"] = html.unescape(m.group(1)) if m else None
        i = 1
        while f"epub/text/chapter-{i}.xhtml" in namen:
            x = z.read(f"epub/text/chapter-{i}.xhtml").decode("utf-8")
            body = re.search(r"<section[^>]*>(.*)</section>", x, re.S).group(1)
            body = re.sub(r"<h1.*?</h1>", " ", body, flags=re.S)
            out["noterefs"] += len(re.findall(r'class="noteref"', body))
            out["bildrefs"] += len(re.findall(r'class="bildref"', body))
            out["kapitel"].append(_rein(body))
            sm = f"epub/smil/chapter-{i}.smil"
            if sm in namen:
                s = z.read(sm).decode("utf-8")
                out["smil"][i] = [(t, float(a), float(e)) for t, a, e in re.findall(
                    r'<text src="[^"#]*#([^"]+)"/><audio src="[^"]+" clipBegin="([\d.]+)s" clipEnd="([\d.]+)s"/>', s)]
            i += 1
        if "epub/text/colophon.xhtml" in namen:
            out["kolophon"] = _rein(z.read("epub/text/colophon.xhtml").decode("utf-8"))
        if "epub/text/anhang.xhtml" in namen:
            a = z.read("epub/text/anhang.xhtml").decode("utf-8")
            out["noten"] = len(re.findall(r'<li id="fn-', a))
            out["bilder"] = len(re.findall(r'<figure id="bild-', a))
    return out


def epubcheck(pfad, timeout=300):
    """-> {werkzeug, fehler, warnungen, meldungen}. Werkzeug fehlt -> werkzeug False."""
    if not os.path.exists(EPUBCHECK):
        return {"werkzeug": False, "fehler": None, "warnungen": None, "meldungen": ["epubcheck.jar fehlt"]}
    fd, js = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        r = subprocess.run(["java", "-jar", EPUBCHECK, pfad, "--json", js, "-q"], stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=timeout)
        try:
            with open(js, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return {"werkzeug": False, "fehler": None, "warnungen": None,
                    "meldungen": [(r.stderr or r.stdout or "epubcheck ohne Ergebnis")[:300]]}
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"werkzeug": False, "fehler": None, "warnungen": None, "meldungen": [f"epubcheck: {e}"[:300]]}
    finally:
        try:
            os.remove(js)
        except OSError:
            pass
    msgs = d.get("messages") or []
    fe = [x for x in msgs if x.get("severity") in ("ERROR", "FATAL")]
    wa = [x for x in msgs if x.get("severity") == "WARNING"]
    kurz = [f'{x.get("ID")} {x.get("message")} ({(x.get("locations") or [{}])[0].get("path", "")})'[:200]
            for x in (fe + wa)[:10]]
    return {"werkzeug": True, "fehler": len(fe), "warnungen": len(wa), "meldungen": kurz}
