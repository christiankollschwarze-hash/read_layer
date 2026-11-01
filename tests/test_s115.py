"""Stage 115 Modernisierungs-Weiche.  py -3.11 -m unittest tests.test_s115"""
import contextlib, io, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import status as S
from pipeline import s115_fassung as F

REG = {"standard": "CK", "nutzer": {"CK": {"rolle": "admin"}}, "mandanten": {}}


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.tmp.name
        self.alt = (config.book_dir, config.work_dir)
        self.dir = os.path.join(r, "werk")
        os.makedirs(os.path.join(self.dir, "work"))
        config.book_dir = lambda b: self.dir
        config.work_dir = lambda b: os.path.join(self.dir, "work")
        with open(os.path.join(self.dir, "raw.txt"), "w") as f:
            f.write("x" * 200000)
        reg = os.path.join(r, "rollen.json")
        json.dump(REG, open(reg, "w"))
        os.environ["READLAYER_ROLLEN"] = reg
        os.environ.pop("READLAYER_NUTZER", None)

    def tearDown(self):
        config.book_dir, config.work_dir = self.alt
        os.environ.pop("READLAYER_ROLLEN", None)
        self.tmp.cleanup()

    def book(self, **kw):
        b = {"book_slug": "w", "quellsprache": "en", "quelle": "gutenberg", "gutenberg_id": 1,
             "mandant": "somnio", "rechte": {"art": "gemeinfrei", "bearbeitung": True}}
        b.update(kw)
        json.dump({k: v for k, v in b.items() if v is not None},
                  open(os.path.join(self.dir, "book.json"), "w"))

    def lauf(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return F.run("w", **kw)

    def bj(self):
        return json.load(open(os.path.join(self.dir, "book.json")))

    def met(self):
        return S.laden("w")["stages"]["115"]["metriken"]

    def test_gutenberg_default_auto(self):
        self.book()
        self.assertEqual(self.lauf(), "auto")
        self.assertEqual(self.bj()["fassung"], "modernisiert")
        self.assertEqual(self.met()["vermerk"], "Sanft modernisierte Fassung")

    def test_ohne_bearbeitungsrecht_stopp(self):
        self.book(rechte={"art": "lizenz", "bearbeitung": False})
        self.assertEqual(self.lauf(), "stopp")
        self.assertNotIn("fassung", self.bj())

    def test_user_epub_default_original_auto(self):
        self.book(quelle="user_epub", mandant="user:max", gutenberg_id=None,
                  rechte={"art": "eigene", "bearbeitung": True})
        self.assertEqual(self.lauf(), "auto")
        self.assertEqual(self.bj()["fassung"], "original")
        self.assertIsNone(self.met()["vermerk"])

    def test_user_optin_mensch_mit_angebot(self):
        self.book(quelle="user_epub", mandant="user:max", gutenberg_id=None,
                  rechte={"art": "eigene", "bearbeitung": True})
        self.assertEqual(self.lauf(modernisieren=True), "mensch")
        self.assertEqual(self.bj()["fassung"], "modernisiert")
        self.assertAlmostEqual(self.met()["angebot_usd"], 0.14)

    def test_verlag_immer_mensch(self):
        self.book(quelle="verlag_epub", mandant="verlag:abc", gutenberg_id=None,
                  rechte={"art": "verlag", "bearbeitung": False})
        self.assertEqual(self.lauf(), "mensch")
        self.assertEqual(self.bj()["fassung"], "original")

    def test_quellsprache_ohne_prompt_original(self):
        self.book(quellsprache="de")
        self.assertEqual(self.lauf(), "auto")
        self.assertEqual(self.bj()["fassung"], "original")

    def test_book_json_bleibt_und_wechsel_hinweis(self):
        self.book(fassung="original")
        self.assertEqual(self.lauf(), "auto")
        self.assertEqual(self.bj()["fassung"], "original")
        open(os.path.join(self.dir, "raw_modernized.txt"), "w").write("x")
        self.assertEqual(self.lauf(modernisieren=True), "auto")
        self.assertEqual(self.bj()["fassung"], "modernisiert")
        h = " ".join(S.laden("w")["stages"]["115"].get("hinweise") or [])
        self.assertIn("120 neu", h)


if __name__ == "__main__":
    unittest.main()
