"""Phase 2, Fundament 4: Tests fuer pipeline/bestellung.py.  py -3.11 -m unittest tests.test_bestellung"""
import json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import bestellung as B


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ordner = os.path.join(self.tmp.name, "authors", "x", "books", "w")
        os.makedirs(self.ordner)
        self._orig = config.book_dir
        config.book_dir = lambda b: self.ordner

    def tearDown(self):
        config.book_dir = self._orig
        self.tmp.cleanup()

    def _bj(self, d):
        with open(os.path.join(self.ordner, "book.json"), "w", encoding="utf-8") as f:
            json.dump(d, f)

    def test_altwerk_gutenberg(self):
        self._bj({"book_slug": "w", "originalsprache": "en-GB", "gutenberg_id": 11})
        b = B.lesen("w")
        self.assertEqual((b.quellsprache, b.zielsprachen, b.sprachen), ("en", ["de"], ["en", "de"]))
        self.assertEqual(b.fassung, "modernisiert")
        self.assertEqual(b.mandant, "somnio")
        self.assertEqual(b.rechte["art"], "gemeinfrei")
        self.assertIn("produkte", b.abgeleitet)
        self.assertEqual(b.audiosprachen(), [])
        self.assertEqual(b.fehler(), [])

    def test_altwerk_de_und_user(self):
        o = os.path.join(self.tmp.name, "users", "u7", "works", "w2")
        os.makedirs(o)
        with open(os.path.join(o, "book.json"), "w", encoding="utf-8") as f:
            json.dump({"originalsprache": "de", "herkunft": "privat_upload", "rechte": "eigene"}, f)
        b = B.lesen(o)
        self.assertEqual((b.quellsprache, b.zielsprachen), ("de", ["en"]))
        self.assertEqual((b.mandant, b.besitzer, b.fassung), ("user:u7", "u7", "original"))
        self.assertTrue(b.rechte["bearbeitung"])

    def test_bestellung(self):
        self._bj({"quellsprache": "en", "fassung": "modernisiert", "mandant": "somnio",
                  "rechte": {"art": "gemeinfrei", "bearbeitung": True},
                  "produkte": [
                      {"sprache": "en", "inhalt": "text", "kanaele": ["taella", "epub"]},
                      {"sprache": "de", "inhalt": "Hoerbuch", "stufe": "basic", "kanaele": "extern"},
                      {"sprache": "fr", "inhalt": "hoerspiel", "stufe": "drama", "kanaele": ["taella"],
                       "zusatz": ["sound_carpet"]}]})
        b = B.lesen("w")
        self.assertEqual(b.abgeleitet, [])
        self.assertEqual(b.zielsprachen, ["de", "fr"])
        self.assertEqual(b.audiosprachen(), ["de", "fr"])
        self.assertEqual(b.audiosprachen("hoerspiel"), ["fr"])
        self.assertTrue(b.hat(kanal="extern", sprache="de"))
        self.assertFalse(b.hat(kanal="epub", sprache="de"))
        self.assertEqual(b.kanaele("en"), ["taella", "epub"])
        self.assertEqual(len(b.beta()), 1)
        self.assertEqual(b.fehler(), [])

    def test_matrix(self):
        n = B.produkt_norm
        self.assertEqual(B.produkt_fehler(n({"sprache": "de", "inhalt": "text", "kanaele": ["taella"]})), [])
        self.assertTrue(B.produkt_fehler(n({"sprache": "de", "inhalt": "text", "kanaele": ["extern"]})))
        self.assertTrue(B.produkt_fehler(n({"sprache": "de", "inhalt": "hoerbuch", "stufe": "premium",
                                            "kanaele": ["epub"]})))
        self.assertTrue(B.produkt_fehler(n({"sprache": "de", "inhalt": "hoerspiel", "stufe": "basic",
                                            "kanaele": ["taella"]})))
        self.assertTrue(B.produkt_fehler(n({"sprache": "de", "inhalt": "hoerbuch", "stufe": "basic",
                                            "kanaele": ["taella"], "zusatz": ["sound_carpet"]})))
        self.assertTrue(B.produkt_fehler(n({"sprache": "ja", "inhalt": "text", "kanaele": ["taella"]})))

    def test_fehler_bearbeitungsrecht(self):
        self._bj({"quellsprache": "en", "fassung": "modernisiert", "rechte": {"art": "lizenz"},
                  "produkte": []})
        f = B.lesen("w").fehler()
        self.assertTrue(any("Bearbeitungsrecht" in x for x in f))
        self.assertTrue(any("keine Produkte" in x for x in f))

    def test_schreiben_und_config(self):
        self._bj({"book_slug": "w", "originalsprache": "en"})
        with self.assertRaises(ValueError):
            B.schreiben("w", produkte=[{"sprache": "de", "inhalt": "text", "kanaele": ["extern"]}])
        with self.assertRaises(ValueError):
            B.schreiben("w", farbe="rot")
        B.schreiben("w", quellsprache="de",
                    produkte=[{"sprache": "es", "inhalt": "text", "kanaele": ["epub"]}])
        roh = json.load(open(os.path.join(self.ordner, "book.json"), encoding="utf-8"))
        self.assertEqual(roh["originalsprache"], "en")              # Altfeld bleibt unberuehrt
        config._werk_sprachen_setzen("w", self.ordner)
        self.assertEqual((config.SOURCE_LANGUAGE, config.TARGET_LANGUAGES, config.ALL_LANGUAGES),
                         ("de", ["es"], ["de", "es"]))
        config._WERK_SPRACHEN_CACHE.pop("w", None)

    def test_migrieren(self):
        self._bj({"book_slug": "w", "originalsprache": "en", "gutenberg_id": 5, "rechte": "gemeinfrei"})
        neu = B.migrieren("w")
        self.assertEqual(neu["quellsprache"], "en")
        self.assertNotIn("produkte", neu)
        self.assertNotIn("quellsprache", json.load(open(os.path.join(self.ordner, "book.json"))))
        B.migrieren("w", schreiben_=True)
        self.assertEqual(B.migrieren("w"), {})
        b = B.lesen("w")
        self.assertEqual(b.abgeleitet, ["produkte"])
        self.assertEqual(b.rechte["art"], "gemeinfrei")


if __name__ == "__main__":
    unittest.main()
