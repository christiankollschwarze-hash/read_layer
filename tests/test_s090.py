"""Stage 090 Eingangsweiche.  py -3.11 -m unittest tests.test_s090"""
import io, json, os, sys, tempfile, unittest, contextlib, zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import s090_eingang as E, status as S

REG = {"standard": "CK", "nutzer": {"CK": {"rolle": "admin"}, "anna": {"rolle": "kurator"}}, "mandanten": {}}


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "u-test-werk")
        os.makedirs(self.dir)
        self._wd, self._bd = config.work_dir, config.book_dir
        config.work_dir = lambda b: self.dir
        config.book_dir = lambda b: self.dir
        reg = os.path.join(self.tmp.name, "rollen.json")
        json.dump(REG, open(reg, "w"))
        os.environ["READLAYER_ROLLEN"] = reg
        os.environ.pop("READLAYER_NUTZER", None)

    def tearDown(self):
        config.work_dir, config.book_dir = self._wd, self._bd
        os.environ.pop("READLAYER_ROLLEN", None)
        self.tmp.cleanup()

    def buch(self, d):
        json.dump(d, open(os.path.join(self.dir, "book.json"), "w"))

    def roh(self):
        return json.load(open(os.path.join(self.dir, "book.json")))

    def lauf(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return E.run("u-test-werk", **kw)

    def gruende(self):
        return " ".join(S.laden("u-test-werk")["stages"]["090"]["gate"]["gruende"])

    def test_user_epub_ohne_versicherung_stopp(self):
        self.buch({"originalsprache": "en", "herkunft": "privat_upload", "owner_uid": "anna",
                   "quelle_epub": {"datei": "x.epub"}, "rechte": "eigene"})
        self.assertEqual(self.lauf(), "stopp")
        self.assertIn("Rechte-Versicherung", self.gruende())
        self.assertNotIn("quelle", self.roh())

    def test_versichern_auto_quelle_geschrieben(self):
        self.buch({"originalsprache": "en", "herkunft": "privat_upload", "owner_uid": "anna",
                   "quelle_epub": {"datei": "x.epub"}})
        self.assertEqual(self.lauf(versichern="eigene", bearbeitung=True), "auto")
        r = self.roh()
        self.assertEqual(r["quelle"], "user_epub")
        self.assertEqual(r["rechte"]["versichert"]["wer"], "CK")
        self.assertTrue(r["rechte"]["bearbeitung"])
        self.assertEqual(S.zustand("u-test-werk", "090"), "frei")

    def test_gutenberg(self):
        self.buch({"originalsprache": "en", "gutenberg_id": 215})
        self.assertEqual(self.lauf(), "auto")
        self.assertEqual(self.roh()["quelle"], "gutenberg")
        self.buch({"originalsprache": "en", "quelle": "gutenberg", "gutenberg_id": "abc"})
        self.assertEqual(self.lauf(), "stopp")
        self.assertEqual(self.lauf(gutenberg_id=215), "auto")

    def test_fremd_audio_immer_stopp(self):
        self.buch({"originalsprache": "en", "quelle": "fremd_audio", "gutenberg_id": 215})
        self.assertEqual(self.lauf(), "stopp")
        self.assertIn("geparkt", self.gruende())

    def test_verlag_epub_braucht_verlagsmandant(self):
        v = {"art": "verlag", "versichert": {"wer": "CK", "wann": "2026-11-01"}, "drm_frei": True}
        self.buch({"originalsprache": "de", "quelle": "verlag_epub", "rechte": v})
        self.assertEqual(self.lauf(), "stopp")
        self.buch({"originalsprache": "de", "quelle": "verlag_epub", "rechte": v, "mandant": "verlag:hanser"})
        self.assertEqual(self.lauf(), "auto")

    def test_drm_datei(self):
        p = os.path.join(self.dir, "drm.epub")
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("META-INF/container.xml", '<rootfile full-path="o.opf"/>')
            z.writestr("META-INF/encryption.xml",
                       '<EncryptionMethod Algorithm="http://www.w3.org/2001/04/xmlenc#aes128-cbc"/>'
                       '<CipherReference URI="text/c1.xhtml"/>')
        self.buch({"originalsprache": "en", "quelle": "user_epub", "quelle_epub": {"datei": "drm.epub"},
                   "rechte": {"art": "eigene", "versichert": {"wer": "CK", "wann": "x"}}})
        self.assertEqual(self.lauf(), "stopp")
        self.assertIn("DRM", self.gruende())

    def test_ziel_und_rechte_kurator(self):
        self.buch({"originalsprache": "en", "gutenberg_id": 1, "audio_quelle": "librivox"})
        with self.assertRaises(ValueError):
            self.lauf(ziel=["en"])
        self.assertEqual(self.lauf(ziel=["de", "fr"]), "auto")
        self.assertEqual(self.roh()["wunsch"]["zielsprachen"], ["de", "fr"])
        self.assertTrue(S.laden("u-test-werk")["stages"]["090"].get("hinweise"))
        with self.assertRaises(PermissionError):
            self.lauf(ziel=["de"], wer="anna")          # fremdes Werk (somnio)


if __name__ == "__main__":
    unittest.main()
