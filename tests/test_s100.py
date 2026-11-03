"""Stage 100 Werk anlegen.  py -3.11 -m unittest tests.test_s100"""
import contextlib, io, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import status as S
from tools import s100_anlegen as A

REG = {"standard": "CK", "nutzer": {"CK": {"rolle": "admin"}}, "mandanten": {}}
TEXT = ("Header\n*** START OF THE PROJECT GUTENBERG EBOOK X ***\n" + "Wort " * 2000 +
        "\n*** END OF THE PROJECT GUTENBERG EBOOK X ***\nLizenz\n")
GDX = {"title": "The Test Book", "languages": ["en"],
       "authors": [{"name": "Muster, Max", "birth_year": 1850, "death_year": 1910}],
       "translators": [], "formats": {"text/plain; charset=utf-8": "https://gutenberg.test/1.txt"}}


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.tmp.name
        self.alt = (config.author_dir, config.book_dir, config.work_dir, config.INDEX_PATH, A._holen)
        config.author_dir = lambda a: os.path.join(r, "authors", a)
        self.dir = os.path.join(r, "authors", "muster-m", "books", "the-test-book")
        config.book_dir = lambda b: self.dir
        config.work_dir = lambda b: os.path.join(self.dir, "work")
        config.INDEX_PATH = os.path.join(r, "daten", "index.json")
        self.abrufe = []

        def holen(url, timeout=90, versuche=4):
            self.abrufe.append(url)
            if "gutendex" in url:
                return json.dumps(GDX).encode()
            if "kaputt" in url:
                raise OSError("Netz weg")
            return TEXT.encode()
        A._holen = holen
        reg = os.path.join(r, "rollen.json")
        json.dump(REG, open(reg, "w"))
        os.environ["READLAYER_ROLLEN"] = reg
        os.environ.pop("READLAYER_NUTZER", None)

    def tearDown(self):
        (config.author_dir, config.book_dir, config.work_dir, config.INDEX_PATH, A._holen) = self.alt
        os.environ.pop("READLAYER_ROLLEN", None)
        self.tmp.cleanup()

    def still(self, f, *a, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return f(*a, **kw)

    def gate(self):
        return S.laden("the-test-book")["stages"]["100"]["gate"]

    def neu(self):
        return self.still(A.neu_anlegen, 1)

    def test_neuanlage_auto(self):
        self.assertEqual(self.neu(), "auto")
        b = json.load(open(os.path.join(self.dir, "book.json")))
        self.assertEqual((b["quelle"], b["quellsprache"]), ("gutenberg", "en"))
        idx = json.load(open(config.INDEX_PATH))
        self.assertEqual(idx["books"]["the-test-book"], "muster-m")
        self.assertEqual(S.zustand("the-test-book", "100"), "frei")

    def test_download_fehler_stopp_ohne_halbe_datei(self):
        GDX["formats"] = {"text/plain": "https://kaputt.test/1.txt"}
        try:
            self.assertEqual(self.neu(), "stopp")
        finally:
            GDX["formats"] = {"text/plain; charset=utf-8": "https://gutenberg.test/1.txt"}
        self.assertFalse(os.path.exists(os.path.join(self.dir, "raw.txt")))
        self.assertIn("Rohtext nicht geladen", " ".join(self.gate()["gruende"]))

    def test_marken_fehlen_stopp_vorhanden_auto(self):
        self.neu()
        open(os.path.join(self.dir, "raw.txt"), "w").write("Wort " * 2000)
        self.assertEqual(self.still(A.run, "the-test-book"), "stopp")
        self.assertEqual(self.still(A.run, "the-test-book", textquelle="vorhanden"), "auto")

    def test_zu_kurz_stopp(self):
        self.neu()
        open(os.path.join(self.dir, "raw.txt"), "w").write(TEXT.replace("Wort " * 2000, "kurz"))
        self.assertEqual(self.still(A.run, "the-test-book"), "stopp")

    def test_pd_zu_jung_mensch_todesjahr_regler(self):
        self.neu()
        ap = os.path.join(config.author_dir("muster-m"), "author.json")
        aj = json.load(open(ap)); aj["todesjahr"] = 1960; json.dump(aj, open(ap, "w"))
        self.assertEqual(self.still(A.run, "the-test-book", jahr=2026), "mensch")
        aj["todesjahr"] = None; json.dump(aj, open(ap, "w"))
        self.assertEqual(self.still(A.run, "the-test-book", jahr=2026), "mensch")
        self.assertEqual(self.still(A.run, "the-test-book", todesjahr=1900, jahr=2026), "auto")
        self.assertEqual(json.load(open(ap))["todesjahr_quelle"]["wer"], "CK")

    def test_uebersetzer_ohne_todesjahr_mensch(self):
        self.neu()
        b = json.load(open(os.path.join(self.dir, "book.json")))
        b["quell_uebersetzer"] = "Ue Bersetzer"; json.dump(b, open(os.path.join(self.dir, "book.json"), "w"))
        self.assertEqual(self.still(A.run, "the-test-book", jahr=2026), "mensch")
        self.assertEqual(self.still(A.run, "the-test-book", uebersetzer_todesjahr=1920, jahr=2026), "auto")

    def test_sprache_nicht_in_liste_mensch(self):
        self.neu()
        b = json.load(open(os.path.join(self.dir, "book.json")))
        b["quellsprache"] = "fi"; b["originalsprache"] = "fi"
        json.dump(b, open(os.path.join(self.dir, "book.json"), "w"))
        self.assertEqual(self.still(A.run, "the-test-book"), "mensch")

    def test_index_defekt_stopp_und_kein_verlust(self):
        self.neu()
        open(config.INDEX_PATH, "w").write("{kaputt")
        with self.assertRaises(config.IndexDefekt):
            config._load_index()
        self.assertEqual(self.still(A.run, "the-test-book"), "stopp")
        self.assertEqual(open(config.INDEX_PATH).read(), "{kaputt")

    def test_raw_fehlt_wird_nachgeladen(self):
        self.neu()
        os.remove(os.path.join(self.dir, "raw.txt"))
        self.abrufe.clear()
        self.assertEqual(self.still(A.run, "the-test-book"), "auto")
        self.assertEqual(self.abrufe, ["https://gutenberg.test/1.txt"])

    def test_rahmen(self):
        s, e, kern = A.text_rahmen("a\n***START OF THE PROJECT GUTENBERG EBOOK y***\nK\n***END OF THE PROJECT GUTENBERG EBOOK y***")
        self.assertEqual((s, e, kern.strip()), (True, True, "K"))


    # ---- Eingangsart user_txt (mitgebrachte TXT, 03.11.2026)
    def _txt(self, inhalt="Kapitel 1\n\n" + "Wort " * 2000):
        p = os.path.join(self.tmp.name, "eigen.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write(inhalt)
        return p

    def test_txt_neuanlage(self):
        e, slug = self.still(A.neu_anlegen_txt, self._txt(), "The Test Book", "Max Muster", "en", 1910)
        self.assertEqual((e, slug), ("auto", "the-test-book"))
        self.assertEqual(self.abrufe, [])                                   # kein Gutendex, kein Download
        b = json.load(open(os.path.join(self.dir, "book.json")))
        self.assertEqual((b["quelle"], b["quellsprache"], b["textquelle"]["art"]), ("user_txt", "en", "datei"))
        self.assertTrue(open(os.path.join(self.dir, "raw.txt"), encoding="utf-8").read().startswith("Kapitel 1"))
        g = self.gate()
        self.assertEqual(g["ergebnis"], "auto")
        a = json.load(open(os.path.join(self.tmp.name, "authors", "muster-m", "author.json")))
        self.assertEqual((a["name_display"], a["todesjahr"]), ("Max Muster", 1910))
        from pipeline import bestellung
        bb = bestellung.lesen(self.dir)
        self.assertEqual((bb.fehler(), bb.fassung, bb.rechte["art"]), ([], "modernisiert", "gemeinfrei"))

    def test_txt_ohne_todesjahr_mensch(self):
        e, _ = self.still(A.neu_anlegen_txt, self._txt(), "The Test Book", "Max Muster", "en")
        self.assertEqual(e, "mensch")
        self.assertTrue(any("Todesjahr" in x for x in self.gate()["gruende"]))

    def test_txt_fehler(self):
        with self.assertRaises(ValueError):
            A.neu_anlegen_txt(self._txt(), "", "X", "en")
        with self.assertRaises(ValueError):
            A.neu_anlegen_txt(self._txt(), "T", "X", "xx")
        with self.assertRaises(FileNotFoundError):
            A.neu_anlegen_txt("/gibt/es/nicht.txt", "T", "X", "en")
        e, _ = self.still(A.neu_anlegen_txt, self._txt("zu kurz"), "The Test Book", "Max Muster", "en", 1910)
        self.assertEqual(e, "stopp")


if __name__ == "__main__":
    unittest.main()
