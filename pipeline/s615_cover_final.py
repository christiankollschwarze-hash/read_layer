"""STAGE 615 — Cover final
Funktion:     Fertiges Cover je Fassung (Illustration + Titel + Autor + Wortmarke) ohne EPUB-Export.
Wirkungsweise: nutzt dieselbe Komposition wie s620 (_compose_cover_raster, _gather_meta);
              Sprecherzeile nur bei aktueller Vertonung (s620._sprecher_zeile).
Komponenten:  pipeline/s615_cover_final.py, pipeline/s620_epub_original.py
Zulieferer:   s610 Cover (images/cover.png), Titel DE (book.json fassungen), s600 Klappentext
Abnehmer:     Cockpit (Schritt cover_final, Tor Cover), tools/export_app.py, tools/export_demo.py
(Nomenklatur seit 18.10.2026, Uebersicht: docs/Pipeline_Strang_Matrix.xlsx; neu seit 18.10.2026)

Ausgabe:      fassungen/<lang>/output/cover_final_<lang>.jpg  (je Fassung EN/DE)
Fertig, wenn: beide cover_final_<lang>.jpg existieren und juenger als images/cover.png sind.

Aufruf:  py -3.11 -m pipeline.s615_cover_final <slug> [--lang=en,de]
         (oder ueber run.py <slug> --line epub --from 615 --to 615)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from config import config  # noqa: E402
from pipeline import s620_epub_original as s620  # noqa: E402


def run(slug, langs=("en", "de"), lang=None):
    ok = True
    for lang in langs:
        meta = s620._gather_meta(slug, lang)
        if not meta.get("cover"):
            print(f"[cover_final] [FEHLER] keine Illustration (images/cover.png) fuer {slug}")
            return False
        raster = s620._compose_cover_raster(meta["title"], meta["author"], meta["cover"], lang,
                                            meta.get("sprecher", ""), meta.get("imprint", ""))
        if not raster:
            print("[cover_final] [FEHLER] Pillow fehlt -> pip install pillow")
            return False
        out_dir = os.path.join(config.book_dir(slug), "fassungen", lang, "output")
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, f"cover_final_{lang}.jpg")
        with open(out, "wb") as f:
            f.write(raster)
        print(f"[cover_final] {lang}: '{meta['title']}' / {meta['author']}"
              f"{' / ' + meta['sprecher'] if meta.get('sprecher') else ''} -> {out}")
    return ok


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    langs = ("en", "de")
    for a in sys.argv[1:]:
        if a.startswith("--lang"):
            langs = tuple(a.split("=", 1)[1].split(",")) if "=" in a else langs
    if not args:
        print(__doc__); sys.exit(1)
    sys.exit(0 if run(args[0], langs) else 1)
