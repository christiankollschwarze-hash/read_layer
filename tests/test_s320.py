"""Stage 320 Integritaet.  py -3.11 -m unittest tests.test_s320"""
import contextlib, copy, io, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import status as S
from pipeline import s320_integritaet as P

REF = {"c001_00001_h": {"type": "h", "en": ""},
       "c001_00002_s": {"type": "s", "en": "Margaret walked home."},
       "c001_00003_p": {"type": "p", "en": ""},
       "c002_00001_s": {"type": "s", "en": "The door was open."}}
DE = {"c001_00002_s": "Margarete ging heim.", "c002_00001_s": "Die Tür war offen."}


class T320(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.tmp.name
        self.d = os.path.join(r, "w")
        os.makedirs(os.path.join(self.d, "work"))
        self.alt = (config.book_dir, config.work_dir, config.BASE_DIR)
        config.book_dir = lambda b: self.d
        config.work_dir = lambda b: os.path.join(self.d, "work")
        config.BASE_DIR = r
        b = {"book_slug": "w", "quelle": "gutenberg", "quellsprache": "en", "fassung": "modernisiert",
             "mandant": "somnio", "titel_original": "The House",
             "produkte": [{"sprache": "de", "inhalt": "text", "kanaele": ["taella"]}],
             "rechte": {"art": "gemeinfrei", "bearbeitung": True, "versichert": {"wer": "t", "wann": "x"}}}
        self.schreib("book.json", b, top=True)
        self.schreib("200_tagging.json", {"meta": {}, "content": REF})
        c = copy.deepcopy(REF)
        for k, v in DE.items():
            c[k]["de"] = v
        self.c = c
        self.schreib("310_uebersetzung.json", {"meta": {"profile": {}}, "content": c})
        for s in ("300", "310"):
            S.ergebnis("w", s, "auto", wer="test")

    def tearDown(self):
        config.book_dir, config.work_dir, config.BASE_DIR = self.alt
        self.tmp.cleanup()

    def schreib(self, name, d, top=False):
        p = os.path.join(self.d, name) if top else os.path.join(self.d, "work", name)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)

    def lauf(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return P.run("w", wer="test", **kw)

    def neu310(self, f):
        c = copy.deepcopy(self.c)
        f(c)
        self.schreib("310_uebersetzung.json", {"meta": {}, "content": c})

    def test_sauber_auto(self):
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto")
        with open(os.path.join(self.d, "work", "320_integritaet.json"), encoding="utf-8") as f:
            d = json.load(f)
        self.assertTrue(d["meta"]["integrity_report"]["clean"])
        self.assertEqual(d["content"]["c001_00002_s"]["de"], DE["c001_00002_s"])
        self.assertEqual(S.zustand("w", "320"), "frei")

    def test_leer_und_fehlt_ruecksprung_310(self):
        self.neu310(lambda c: (c["c001_00002_s"].update(de=" "), c["c002_00001_s"].pop("de")))
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual(g.ergebnis["ruecksprung"], "310")
        self.assertEqual(g.bericht_daten["leer"]["de"], ["c001_00002_s"])
        self.assertEqual(g.bericht_daten["fehlt"]["de"], ["c002_00001_s"])

    def test_id_menge_ruecksprung_200(self):
        self.neu310(lambda c: c.pop("c001_00003_p"))
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual(g.ergebnis["ruecksprung"], "200")
        self.assertEqual(g.bericht_daten["ids_fehlen"], ["c001_00003_p"])

    def test_quelltext_geaendert(self):
        self.neu310(lambda c: c["c002_00001_s"].update(en="The door was shut."))
        g = self.lauf()
        self.assertEqual(g.ergebnis["ruecksprung"], "200")
        self.assertEqual(g.bericht_daten["quelltext_geaendert"], ["c002_00001_s"])

    def test_unbestellte_sprache(self):
        self.neu310(lambda c: c["c002_00001_s"].update(fr="La porte était ouverte."))
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertIn("fr", g.bericht_daten["unbestellt"])

    def test_sequenz_und_idform(self):
        r = dict(REF)
        r["c002_00003_s"] = {"type": "s", "en": "Gap."}
        r["x1"] = {"type": "s", "en": "Bad id."}
        self.schreib("200_tagging.json", {"meta": {}, "content": r})
        self.neu310(lambda c: (c.update(c002_00003_s={"type": "s", "en": "Gap.", "de": "Lücke."}),
                               c.update(x1={"type": "s", "en": "Bad id.", "de": "Falsch."})))
        g = self.lauf()
        self.assertEqual(g.ergebnis["ruecksprung"], "200")
        self.assertEqual(g.bericht_daten["id_form"], ["x1"])
        self.assertEqual(g.bericht_daten["sequenz_luecken"][0]["fehlend"], [2])

    def test_vorgaenger_nicht_frei(self):
        S.ergebnis("w", "310", "mensch", wer="test")
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual(g.ergebnis["ruecksprung"], "310")

    def test_trocken_schreibt_nichts(self):
        S.ergebnis("w", "310", "mensch", wer="test")
        g = self.lauf(trocken=True)
        self.assertEqual(g.ergebnis["ergebnis"], "auto")
        self.assertFalse(os.path.exists(os.path.join(self.d, "work", "320_integritaet.json")))

    def test_kein_weiter_schalter(self):
        with open(P.__file__, encoding="utf-8") as f:
            self.assertNotIn("os.environ", f.read())


if __name__ == "__main__":
    unittest.main()
