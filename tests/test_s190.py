"""Stage 190 Eingangsvertrag.  py -3.11 -m unittest tests.test_s190"""
import contextlib, io, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import status as S
from pipeline import s190_vertrag as V

TEXT = "Mr. Holloway walked along the old road toward Dunmore, thinking of the letter Margaret had sent. " * 3


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.tmp.name
        self.dir = os.path.join(r, "werk")
        self.adir = os.path.join(r, "autor")
        os.makedirs(os.path.join(self.dir, "work", "modernized"))
        os.makedirs(self.adir)
        self.alt = (config.book_dir, config.work_dir, config.RUN_MODE, config.author_of, config.author_dir)
        config.book_dir = lambda b: self.dir
        config.work_dir = lambda b: os.path.join(self.dir, "work")
        config.author_of = lambda b: "x"
        config.author_dir = lambda s: self.adir
        config.RUN_MODE = "live"
        with open(os.path.join(self.adir, "author.json"), "w") as f:
            json.dump({"name_display": "Jane Doe"}, f)

    def tearDown(self):
        (config.book_dir, config.work_dir, config.RUN_MODE, config.author_of, config.author_dir) = self.alt
        self.tmp.cleanup()

    def werk(self, n=2, raw=None, kap_120=None, frei=True, **kw):
        b = {"book_slug": "w", "quelle": "gutenberg", "quellsprache": "en", "fassung": "modernisiert",
             "mandant": "somnio", "titel_original": "Test",
             "produkte": [{"sprache": "en", "inhalt": "text", "kanaele": ["taella"]}],
             "rechte": {"art": "gemeinfrei", "bearbeitung": True}}
        b.update(kw)
        with open(os.path.join(self.dir, "book.json"), "w") as f:
            json.dump(b, f)
        zeilen = ["###TITLE### Test", "###AUTHOR### Jane Doe", ""]
        for i in range(1, n + 1):
            d = {"title": f"Chapter {i}", "paragraphs": [TEXT, TEXT + str(i)], "fassung": "modernisiert"}
            with open(os.path.join(self.dir, "work", "modernized", f"chapter-{i}.json"), "w") as f:
                json.dump(d, f)
            zeilen += [f"###CHAPTER### Chapter {i}", "", TEXT, "", TEXT + str(i), ""]
        with open(os.path.join(self.dir, "raw_modernized.txt"), "w", encoding="utf-8") as f:
            f.write(raw if raw is not None else "\n".join(zeilen))
        for s in V.VORSTUFEN:
            if s == "120":
                S.ergebnis("w", s, "auto" if frei else "mensch",
                           metriken={"kapitel": n if kap_120 is None else kap_120, "modus": "live"})
            elif s == "150":
                S.bedarf_setzen("w", [x for x in S.STAGES if x != "150"])
            else:
                S.ergebnis("w", s, "auto", metriken={"modus": "live"})

    def lauf(self):
        with contextlib.redirect_stdout(io.StringIO()):
            g = V.run("w", "CK")
        return g.ergebnis["ergebnis"], {p["name"] for p in g.fehler()}, g

    def test_auto(self):
        self.werk()
        e, f, g = self.lauf()
        self.assertEqual(e, "auto", g.bericht())
        self.assertEqual(S.zustand("w", "190"), "frei")
        self.assertEqual(g.metriken["kapitel"], 2)

    def test_vorstufe_offen(self):
        self.werk(frei=False)
        e, f, g = self.lauf()
        self.assertEqual((e, g.ergebnis["ruecksprung"]), ("stopp", "120"))
        self.assertIn("gate_120", f)

    def test_kapitelzahl_120(self):
        self.werk(kap_120=3)
        e, f, _ = self.lauf()
        self.assertEqual(e, "stopp")
        self.assertIn("kapitelzahl", f)

    def test_checkpoint_luecke(self):
        self.werk(n=3)
        os.remove(os.path.join(self.dir, "work", "modernized", "chapter-2.json"))
        e, f, _ = self.lauf()
        self.assertEqual(e, "stopp")
        self.assertIn("checkpoints", f)

    def test_textabweichung(self):
        self.werk()
        p = os.path.join(self.dir, "raw_modernized.txt")
        t = open(p).read().replace("Holloway walked along the old road", "X", 2)
        open(p, "w").write(t)
        e, f, g = self.lauf()
        self.assertEqual((e, g.ergebnis["ruecksprung"]), ("stopp", "120"))
        self.assertIn("textabweichung", f)

    def test_kleine_abweichung_ok(self):
        self.werk(n=10)
        p = os.path.join(self.dir, "raw_modernized.txt")
        t = open(p).read().replace("Holloway", "Hollaway", 1)
        open(p, "w").write(t)
        e, f, g = self.lauf()
        self.assertEqual(e, "auto", g.bericht())

    def test_abgeleitete_felder(self):
        self.werk()
        b = json.load(open(os.path.join(self.dir, "book.json")))
        del b["fassung"], b["quelle"]
        json.dump(b, open(os.path.join(self.dir, "book.json"), "w"))
        e, f, g = self.lauf()
        self.assertEqual((e, g.ergebnis["ruecksprung"]), ("stopp", "090"))
        self.assertTrue({"quelle", "feld_fassung"} <= f)

    def test_autor_falsch(self):
        self.werk()
        json.dump({"name_display": "John Roe"}, open(os.path.join(self.adir, "author.json"), "w"))
        e, f, _ = self.lauf()
        self.assertIn("marke_autor", f)

    def test_epub_autor_aus_book(self):
        self.werk(quelle="user_epub", fassung="original", autor_name="Jane Doe",
                  rechte={"art": "eigene", "bearbeitung": False})
        os.remove(os.path.join(self.adir, "author.json"))
        e, f, g = self.lauf()
        self.assertEqual(e, "auto", g.bericht())

    def test_einkapitel_ohne_titel(self):
        self.werk(n=1)
        p = os.path.join(self.dir, "work", "modernized", "chapter-1.json")
        d = json.load(open(p)); d["title"] = ""; json.dump(d, open(p, "w"))
        r = os.path.join(self.dir, "raw_modernized.txt")
        t = open(r).read().replace("###CHAPTER### Chapter 1", "###CHAPTER### ")
        open(r, "w").write(t)
        e, f, g = self.lauf()
        self.assertEqual(e, "auto", g.bericht())

    def test_mock_live(self):
        self.werk()
        p = os.path.join(self.dir, "raw_modernized.txt")
        open(p, "a").write("\n[MOCK:MOD] x\n")
        e, f, _ = self.lauf()
        self.assertEqual(e, "stopp")
        self.assertIn("mock", f)

    def test_raw_fehlt(self):
        self.werk()
        os.remove(os.path.join(self.dir, "raw_modernized.txt"))
        e, f, g = self.lauf()
        self.assertEqual((e, g.ergebnis["ruecksprung"]), ("stopp", "120"))


if __name__ == "__main__":
    unittest.main()
