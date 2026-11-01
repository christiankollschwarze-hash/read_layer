"""Stage 080 Mandant & Rechte.  py -3.11 -m unittest tests.test_s080"""
import io, json, os, sys, tempfile, unittest, contextlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import s080_mandant as M, status as S

REG = {"standard": "CK",
       "nutzer": {"CK": {"rolle": "admin"},
                  "anna": {"rolle": "kurator"},
                  "bob": {"rolle": "kurator", "uid": "anna", "grenzen": ["lauf"]},
                  "hanser": {"rolle": "verlag", "verlag": "hanser"}},
       "mandanten": {"somnio": {"imprint": "SOMNIO"}, "verlag:hanser": {"imprint": "Hanser"}}}


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._wd, self._bd = config.work_dir, config.book_dir
        config.work_dir = lambda b: self.tmp.name
        config.book_dir = lambda b: self.tmp.name
        reg = os.path.join(self.tmp.name, "rollen.json")
        json.dump(REG, open(reg, "w"))
        os.environ["READLAYER_ROLLEN"] = reg
        os.environ.pop("READLAYER_NUTZER", None)
        self.buch({"quellsprache": "en", "owner_uid": "anna", "rechte": {"art": "eigene", "bearbeitung": True}})

    def tearDown(self):
        config.work_dir, config.book_dir = self._wd, self._bd
        os.environ.pop("READLAYER_ROLLEN", None)
        self.tmp.cleanup()

    def buch(self, d):
        json.dump(d, open(os.path.join(self.tmp.name, "book.json"), "w"))

    def lauf(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return M.run("u-test", **kw)

    def test_admin_auto_und_mandant_geschrieben(self):
        self.assertEqual(self.lauf(), "auto")
        b = json.load(open(os.path.join(self.tmp.name, "book.json")))
        self.assertEqual((b["mandant"], b["besitzer"]), ("user:anna", "anna"))
        st = S.laden("u-test")["stages"]["080"]
        self.assertEqual(st["zustand"], "frei")
        self.assertEqual((st["wer"], st["metriken"]["rolle"]), ("CK", "admin"))

    def test_kurator_eigenes_und_fremdes_werk(self):
        self.assertEqual(self.lauf(wer="anna"), "auto")
        self.buch({"quellsprache": "en", "mandant": "somnio"})
        self.assertEqual(self.lauf(wer="anna"), "stopp")
        self.assertEqual(S.zustand("u-test", "080"), "stopp")

    def test_unbekannt_und_grenzen(self):
        self.assertEqual(self.lauf(wer="mallory"), "stopp")
        self.assertFalse(M.pruefen("u-test", "entscheiden", "bob")[0])
        self.assertTrue(M.pruefen("u-test", "lauf", "bob")[0])
        self.assertFalse(M.pruefen("u-test", "override", "anna")[0])
        self.assertTrue(M.pruefen("u-test", "override", "CK")[0])

    def test_verlag_und_imprint(self):
        self.buch({"quellsprache": "en", "mandant": "verlag:hanser"})
        self.assertTrue(M.pruefen("u-test", "lauf", "hanser")[0])
        self.assertFalse(M.pruefen("u-test", "lauf", "anna")[0])
        self.assertEqual(M.imprint("u-test"), "Hanser")
        self.buch({"quellsprache": "en", "gutenberg_id": 1})
        self.assertEqual(M.imprint("u-test"), "SOMNIO")

    def test_mandant_setzen_nur_admin(self):
        self.assertEqual(self.lauf(wer="anna", mandant="somnio"), "stopp")
        self.assertEqual(self.lauf(mandant="verlag:hanser"), "auto")
        b = json.load(open(os.path.join(self.tmp.name, "book.json")))
        self.assertEqual((b["mandant"], b["besitzer"]), ("verlag:hanser", "hanser"))
        self.assertEqual(S.laden("u-test")["protokoll"][-1]["aktion"], "mandant")

    def test_status_cli_rolle_aus_register(self):
        S.ergebnis("u-test", "310", "mensch", gruende=["x"])
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = S.main(["u-test", "--override", "310", "--wer", "anna", "--rolle", "admin", "--grund", "g"])
        self.assertEqual(rc, 2)
        self.assertIn("nur fuer admin", err.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            rc = S.main(["u-test", "--entscheiden", "310", "frei", "--wer", "anna", "--grund", "ok"])
        self.assertEqual(rc, 0)
        self.assertEqual(S.laden("u-test")["protokoll"][-1]["rolle"], "kurator")


if __name__ == "__main__":
    unittest.main()
