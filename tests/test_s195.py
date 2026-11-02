"""Stage 195 Teilung.  py -3.11 -m unittest tests.test_s195"""
import contextlib, io, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import bestellung, kette, s120_modernisierung as M
from pipeline import status as S
from pipeline import s195_teilung as T

REG = {"standard": "CK", "nutzer": {"CK": {"rolle": "admin"}}, "mandanten": {}}


class Teilung(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "books")
        self.adir = os.path.join(self.tmp.name, "autor")
        os.makedirs(self.adir)
        with open(os.path.join(self.adir, "author.json"), "w") as f:
            json.dump({"name_display": "Jane Doe"}, f)
        self.idx = {"books": {"w": "doe"}, "authors": {}}
        self.alt = (config.book_dir, config.work_dir, config.RUN_MODE, config.author_of, config.author_dir,
                    config._load_index, config._save_index)
        config.book_dir = lambda b: os.path.join(self.root, b)
        config.work_dir = lambda b: os.path.join(self.root, b, "work")
        config.author_of = lambda b: self.idx["books"][b]
        config.author_dir = lambda s: self.adir
        config._load_index = lambda: json.loads(json.dumps(self.idx))
        config._save_index = lambda i: self.idx.update(i)
        config.RUN_MODE = "live"
        reg = os.path.join(self.tmp.name, "rollen.json")
        with open(reg, "w") as f:
            json.dump(REG, f)
        os.environ["READLAYER_ROLLEN"] = reg
        os.environ.pop("READLAYER_NUTZER", None)

    def tearDown(self):
        (config.book_dir, config.work_dir, config.RUN_MODE, config.author_of, config.author_dir,
         config._load_index, config._save_index) = self.alt
        os.environ.pop("READLAYER_ROLLEN", None)
        self.tmp.cleanup()

    def werk(self, groessen, struktur=()):
        d = os.path.join(self.root, "w")
        md = os.path.join(d, "work", "modernized")
        os.makedirs(md, exist_ok=True)
        b = {"book_slug": "w", "quelle": "gutenberg", "quellsprache": "en", "fassung": "modernisiert",
             "mandant": "somnio", "titel_original": "Test", "glossar_fest": {"de": {"Moor": "Moor"}},
             "produkte": [{"sprache": "en", "inhalt": "text", "kanaele": ["taella"]}],
             "rechte": {"art": "gemeinfrei", "bearbeitung": True}}
        with open(os.path.join(d, "book.json"), "w") as f:
            json.dump(b, f)
        for i, z in enumerate(groessen, 1):
            titel = f"Part Two. Chapter {i}" if i in struktur else f"Chapter {i}"
            text = ("The moor was quiet tonight. " * (z // 28 + 1))[:z - len(titel)].strip()
            with open(os.path.join(md, f"chapter-{i}.json"), "w") as f:
                json.dump({"title": titel, "paragraphs": [text], "fassung": "modernisiert"}, f)
        with contextlib.redirect_stdout(io.StringIO()):
            M._write_marked_source("w", md)
        for s in ("080", "090", "095", "100", "110", "115", "120", "190"):
            S.ergebnis("w", s, "auto", metriken={"modus": "live", **({"kapitel": len(groessen)} if s == "120" else {})})
        S.bedarf_setzen("w", [x for x in S.STAGES if x != "150"])

    def lauf(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            g = T.run("w", "CK", **kw)
        return g.ergebnis["ergebnis"], g

    def vorschlag(self):
        return json.load(open(os.path.join(self.root, "w", "work", "195_teilung.json")))

    def test_optimum(self):
        self.assertEqual(T.optimum([5, 1, 1, 1, 1, 1], 2), [0, 1])
        self.assertEqual(T.optimum([1] * 9, 3), [0, 3, 6])

    def test_unter_grenze_auto(self):
        self.werk([1000] * 4)
        e, g = self.lauf()
        self.assertEqual(e, "auto", g.bericht())
        self.assertEqual(len(self.vorschlag()["teile"]), 1)

    def test_ueber_grenze_mensch_vorschlag(self):
        self.werk([1000] * 4)
        e, g = self.lauf(grenze=2500)
        self.assertEqual(e, "mensch", g.bericht())
        v = self.vorschlag()
        self.assertEqual([(t["kapitel_von"], t["kapitel_bis"]) for t in v["teile"]], [(1, 2), (3, 4)])
        self.assertEqual(v["herkunft"], "optimum")

    def test_gliederung_bevorzugt(self):
        self.werk([1000] * 20, struktur={10})
        e, g = self.lauf(grenze=15000)
        v = self.vorschlag()
        self.assertEqual(v["herkunft"], "gliederung")
        self.assertEqual(v["teile"][1]["kapitel_von"], 10)

    def test_gliederung_zu_ungleich(self):
        self.werk([1000] * 20, struktur={6})
        self.lauf(grenze=15000)
        v = self.vorschlag()
        self.assertEqual((v["herkunft"], v["teile"][1]["kapitel_von"]), ("optimum", 11))

    def test_schnitte_manuell(self):
        self.werk([1000] * 6)
        e, g = self.lauf(grenze=2500, schnitte=[3, 5])
        v = self.vorschlag()
        self.assertEqual(e, "mensch")
        self.assertEqual([t["kapitel_von"] for t in v["teile"]], [1, 3, 5])
        self.assertEqual(v["herkunft"], "manuell")

    def test_ablehnen_weiter_mit_warnung(self):
        self.werk([1000] * 4)
        self.lauf(grenze=2500)
        e, g = self.lauf(ablehnen=True)
        self.assertEqual(e, "auto")
        self.assertTrue(any("abgelehnt" in h for h in g.ergebnis["hinweise"]))
        e, _ = self.lauf()                          # Entscheidung bleibt bestehen
        self.assertEqual(e, "auto")

    def test_einzelkapitel_ueber_grenze(self):
        self.werk([5000, 500, 500])
        e, g = self.lauf(grenze=3000)
        self.assertEqual(e, "mensch")
        self.assertIn("kapitel_ueber_grenze", {p["name"] for p in g.fehler()})

    def test_annehmen_legt_teile_an(self):
        self.werk([1000] * 4)
        self.lauf(grenze=2500, namen={2: "Die Rückkehr"})
        e, g = self.lauf(annehmen=True)
        self.assertEqual(e, "auto", g.bericht())
        self.assertEqual(self.idx["books"]["w-1"], "doe")
        b2 = json.load(open(os.path.join(self.root, "w-2", "book.json")))
        self.assertEqual((b2["reihe"], b2["teil"], b2["teile_gesamt"], b2["kapitel_von"]), ("w", 2, 2, 3))
        self.assertEqual(b2["teil_titel"], "Die Rückkehr")
        self.assertEqual(b2["glossar_fest"], {"de": {"Moor": "Moor"}})
        self.assertEqual(json.load(open(os.path.join(self.root, "w-2", "work", "modernized",
                                                     "chapter-1.json")))["title"], "Chapter 3")
        self.assertFalse(os.path.exists(os.path.join(self.root, "w-2", "work", "modernized", "chapter-3.json")))
        self.assertEqual(S.zustand("w-2", "190"), "frei")
        self.assertEqual(S.zustand("w-2", "195"), "frei")
        rm = open(os.path.join(self.root, "w-2", "raw_modernized.txt"), encoding="utf-8").read()
        self.assertEqual(rm.count("###CHAPTER###"), 2)
        b = bestellung.lesen("w")
        self.assertEqual(b.roh["geteilt_in"], ["w-1", "w-2"])
        self.assertFalse({"200", "600", "700"} & kette.bedarf(b))
        e, g = self.lauf()                          # zweiter Lauf legt nichts neu an
        self.assertEqual(e, "auto")

    def test_text_geaendert_neuer_vorschlag(self):
        self.werk([1000] * 4)
        self.lauf(grenze=2500)
        self.lauf(ablehnen=True)
        with open(os.path.join(self.root, "w", "raw_modernized.txt"), "a") as f:
            f.write("\nmehr\n")
        e, g = self.lauf()
        self.assertEqual(e, "mensch")
        self.assertIsNone(self.vorschlag()["entscheidung"])


if __name__ == "__main__":
    unittest.main()
