"""READ LAYER - AP 62 Test: Stufe 510 fuer EIN Kapitel im Testordner tests/ap62/<werk>/. Produktion bleibt unberuehrt.
Aufruf:  py -3.11 tools/hybrid_test_ap62.py <werk> <kapitel> <lg[,lg]> [liste|los]
  liste = nur Auswahl + Kostenschaetzung (kein Gemini, kein Modal)
  los   = Takes (Gemini), Schnitt (Modal, CPU-Rueckfall), Montage in den Testordner
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from config import config  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    book, chapter, langs = sys.argv[1], sys.argv[2], sys.argv[3].split(",")
    modus = sys.argv[4] if len(sys.argv) > 4 else "liste"
    config.HYBRID_TESTDIR = os.path.join(ROOT, "tests", "ap62", book)
    from pipeline.s510_hoerspiel_hybrid import run  # noqa: E402
    for lg in langs:
        run(book, chapter=chapter, lang=lg, force=True, liste=(modus == "liste"))
    print("[ap62-test] fertig:", modus, "-> Ergebnis unter", config.HYBRID_TESTDIR)
