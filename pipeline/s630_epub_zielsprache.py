"""STAGE 630 — ePub Zielsprache
Funktion:     EPUB3 je bestellter Zielsprache x Variante (Text / Audio mit Media Overlay).
Wirkungsweise: gleicher Ablauf und Baukasten wie 620 (pipeline/s620_epub_original.lauf, pipeline/epub_bau);
              Zieltext aus 330_rueckuebersetzung.json (Stand nach Reparatur), kein Rueckfall auf den
              Originalsatz (Fallback = 0, sonst Stopp -> 310); Absatzgrenzen ueber 190, geklebt -> Mensch;
              Drama-Rollennamen aus Profil 210.
Ausgabe:      fassungen/<lg>/output/<werk>_<lg>[_audio].epub; work/620_epub.json (gemeinsam mit 620);
              Gate 630 je Scope <lg>:<variante>.
Kosten:       0 $.
Aufruf:       python -m pipeline.s630_epub_zielsprache <werk> [Regler wie 620] [--wer CK]
"""

from pipeline import s620_epub_original as s620

STAGE = s620.STAGE_Z


def run(werk, wer=None, **kw):
    """Kettenaufruf 630 (alle bestellten Zielsprachen)."""
    return s620.lauf(werk, STAGE, wer=wer, **kw)


def main(argv=None):
    return s620.main(argv, stage=STAGE)


if __name__ == "__main__":
    raise SystemExit(main())
