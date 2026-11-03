"""AP 710c: baut mit dem Testwerk aus tests/test_s710.py (plus Hoerspielspur und EPUB) ein echtes 710-Paket
(Ziel Lokal) in <ordner>/public und laesst es fuer tools/test_loader_710c.mjs liegen.
Aufruf: python tools/paket_710c_testwerk.py <ordner>"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config  # noqa: E402
from pipeline import manifest  # noqa: E402
from tests import test_s710 as T  # noqa: E402


def main(ordner):
    t = T.T710("test_erstlauf_mensch_dann_freigeben")
    t.setUp()
    try:
        w = "w"
        t.werk(produkte=T.PRODUKTE + [{"sprache": "de", "inhalt": "hoerspiel", "stufe": "premium", "kanaele": ["taella"]},
                                      {"sprache": "en", "inhalt": "text", "kanaele": ["epub"]}])
        d = os.path.join(t.r, w)
        m = manifest.Manifest(w, "530_pruefung_de", stage="530")
        p = os.path.join(d, "fassungen", "de", "hoerspiel_final", "c001_00002_s.wav")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write(b"RIFFhs")
        m.setzen("hoerspiel/c001_00002_s", "e", datei=p)
        m.speichern()
        T.dump({"tags": {"c001_00002_s": [{"i": 0, "t0": 0.0, "t1": 0.2}]}},
               config.work_path(w, "520_wortzeiten_de_hoerspiel"))
        T.dump({"saetze": {"c001_00002_s": {"de": {"seg": [{"t": "Ein Dollar.", "s": "Buck"}]}}}},
               config.work_path(w, "420_sprecher"))
        t.epub_620()
        pub = os.path.join(os.path.abspath(ordner), "public")
        gs = t.lauf(ziel=T.P.Lokal(pub), freigeben=True)
        for g in gs.values():
            print(g.bericht())
        return 0 if all(g.ergebnis["ergebnis"] == "auto" for g in gs.values()) else 2
    finally:
        t.tearDown()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
