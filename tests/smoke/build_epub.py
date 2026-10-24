"""Smoke-Test: baut tests/smoke/spiegelschwestern.epub (EPUB 3, DRM-frei) aus the_mirror_sisters.txt.
Eigenes Werk (CK/Claude 24.10.2026), keine Rechte Dritter. Zitat: Lewis Carroll, Through the Looking-Glass (1871, gemeinfrei).
Aufruf: py -3.11 tests\\smoke\\build_epub.py   (nur Standardbibliothek, deterministisch)"""
import html, os, re, zipfile

HIER = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HIER, "the_mirror_sisters.txt")
OUT = os.path.join(HIER, "spiegelschwestern.epub")
UID = "urn:uuid:5c1d2e7a-7b3f-4c1e-9a55-24102026a001"
MODIFIED = "2026-10-24T00:00:00Z"   # fest -> gleiche Bytes je Bau


def lesen():
    meta, kap = {}, []
    for zeile in open(SRC, encoding="utf-8").read().splitlines():
        m = re.match(r"^(TITLE|AUTHOR|DESCRIPTION):\s*(.*)$", zeile)
        if m and not kap:
            meta[m.group(1).lower()] = m.group(2).strip()
        elif zeile.startswith("## "):
            kap.append({"titel": zeile[3:].strip(), "absaetze": []})
        elif zeile.strip() and kap:
            kap[-1]["absaetze"].append(zeile.strip())
    return meta, kap


def xhtml(titel, body):
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
            'xml:lang="en" lang="en">\n<head>\n<meta charset="utf-8"/>\n'
            f'<title>{html.escape(titel)}</title>\n</head>\n<body>\n{body}\n</body>\n</html>\n')


def main():
    meta, kap = lesen()
    e = html.escape
    dateien = {}
    for i, k in enumerate(kap, 1):
        ps = "\n".join(f"<p>{e(p, quote=False)}</p>" for p in k["absaetze"])
        dateien[f"OEBPS/chapter-{i}.xhtml"] = xhtml(
            k["titel"], f'<section epub:type="chapter" id="chapter-{i}">\n<h1>{e(k["titel"])}</h1>\n{ps}\n</section>')
    nav_li = "\n".join(f'<li><a href="chapter-{i}.xhtml">{e(k["titel"])}</a></li>' for i, k in enumerate(kap, 1))
    dateien["OEBPS/nav.xhtml"] = xhtml("Contents", f'<nav epub:type="toc" id="toc">\n<h1>Contents</h1>\n<ol>\n{nav_li}\n</ol>\n</nav>')
    items = "\n".join(f'<item id="c{i}" href="chapter-{i}.xhtml" media-type="application/xhtml+xml"/>'
                      for i in range(1, len(kap) + 1))
    spine = "\n".join(f'<itemref idref="c{i}"/>' for i in range(1, len(kap) + 1))
    dateien["OEBPS/content.opf"] = f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid" xml:lang="en">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="uid">{UID}</dc:identifier>
<dc:title>{e(meta["title"])}</dc:title>
<dc:creator>{e(meta["author"])}</dc:creator>
<dc:language>en</dc:language>
<dc:description>{e(meta["description"])}</dc:description>
<dc:rights>Own work. All rights reserved.</dc:rights>
<meta property="dcterms:modified">{MODIFIED}</meta>
</metadata>
<manifest>
<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
{items}
</manifest>
<spine>
{spine}
</spine>
</package>
'''
    container = ('<?xml version="1.0" encoding="utf-8"?>\n'
                 '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
                 '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>\n'
                 '</container>\n')
    with zipfile.ZipFile(OUT, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype", (2026, 10, 24, 0, 0, 0)), "application/epub+zip",
                   compress_type=zipfile.ZIP_STORED)
        for name, inhalt in [("META-INF/container.xml", container)] + sorted(dateien.items()):
            z.writestr(zipfile.ZipInfo(name, (2026, 10, 24, 0, 0, 0)), inhalt.encode("utf-8"),
                       compress_type=zipfile.ZIP_DEFLATED)
    w = [sum(len(p.split()) for p in k["absaetze"]) for k in kap]
    print(f"[smoke] {OUT}: {len(kap)} Kapitel, Woerter {w}")


if __name__ == "__main__":
    main()
