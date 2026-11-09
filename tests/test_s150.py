"""Stage 150 ePub-Import.  py -3.11 -m unittest tests.test_s150"""
import contextlib, io, json, os, sys, tempfile, unittest, zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import status as S
from pipeline import s150_epub_import as E

REG = {"standard": "CK", "nutzer": {"CK": {"rolle": "admin"}}, "mandanten": {}}
SATZ = "It was a quiet evening in the old house, and the mirror in the hall kept its own time. "


def seite(titel, text, typ=None):
    t = f' epub:type="{typ}"' if typ else ""
    ps = "".join(f"<p>{x}</p>" for x in text)
    return (f'<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" '
            f'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>{titel}</title></head>'
            f'<body><section{t}><h1>{titel}</h1>{ps}</section></body></html>')


def epub(pfad, seiten, sprache="en", drm=False, beschreibung="Two sisters and a mirror."):
    lang = f"<dc:language>{sprache}</dc:language>" if sprache else ""
    items = "".join(f'<item id="s{i}" href="{n}" media-type="application/xhtml+xml"/>' for i, (n, _) in enumerate(seiten))
    spine = "".join(f'<itemref idref="s{i}"/>' for i in range(len(seiten)))
    opf = (f'<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
           f'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>The Mirror Test</dc:title>'
           f'<dc:creator>Ann Author</dc:creator>{lang}<dc:description>{beschreibung}</dc:description></metadata>'
           f'<manifest>{items}</manifest><spine>{spine}</spine></package>')
    with zipfile.ZipFile(pfad, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", '<container><rootfiles><rootfile full-path="OEBPS/c.opf"/>'
                                             '</rootfiles></container>')
        if drm:
            z.writestr("META-INF/encryption.xml", '<encryption><EncryptedData><EncryptionMethod '
                       'Algorithm="http://www.w3.org/2001/04/xmlenc#aes128-cbc"/><CipherData><CipherReference '
                       'URI="OEBPS/k1.xhtml"/></CipherData></EncryptedData></encryption>')
        z.writestr("OEBPS/c.opf", opf)
        for n, inhalt in seiten:
            z.writestr("OEBPS/" + n, inhalt)
    return pfad


def kap(i, n=40):
    return (f"k{i}.xhtml", seite(f"Chapter {i}", [SATZ * 2] * n, "chapter"))


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.tmp.name
        self.alt = (config.USERS_DIR, config.INDEX_PATH)
        config.USERS_DIR = os.path.join(r, "users")
        config.INDEX_PATH = os.path.join(r, "index.json")
        reg = os.path.join(r, "rollen.json")
        json.dump(REG, open(reg, "w"))
        os.environ["READLAYER_ROLLEN"] = reg
        os.environ.pop("READLAYER_NUTZER", None)
        self.r = r

    def tearDown(self):
        config.USERS_DIR, config.INDEX_PATH = self.alt
        os.environ.pop("READLAYER_ROLLEN", None)
        self.tmp.cleanup()

    def still(self, f, *a, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return f(*a, **kw)

    def neu(self, seiten, **kw):
        p = epub(os.path.join(self.r, "in.epub"), seiten, **{k: v for k, v in kw.items() if k in ("sprache", "drm")})
        return self.still(E.neu_anlegen, p, "anna", **{k: v for k, v in kw.items() if k not in ("sprache", "drm")})

    BID = "u-anna-the-mirror-test"

    def ordner(self):
        return os.path.join(config.USERS_DIR, "anna", "works", self.BID)

    def bj(self):
        return json.load(open(os.path.join(self.ordner(), "book.json")))

    def gruende(self):
        return " ".join(S.laden(self.BID)["stages"]["150"]["gate"]["gruende"])

    def test_monitor_150(self):
        from cockpit import werk_api as W
        about = ("about-the-war.xhtml", seite("About the War", [SATZ * 2] * 40))
        self.neu([kap(1), about, kap(2)])
        d = W._m150_daten(self.BID)
        self.assertTrue(d["epub"])
        self.assertEqual([x["datei"] for x in d["seiten"]], ["k1.xhtml", "about-the-war.xhtml", "k2.xhtml"])
        self.assertEqual(d["seiten"][1]["art"], "weg")
        self.assertEqual(len(d["warnungen"]), 1)
        t = W._m150_teil(self.BID, {"datei": "about-the-war.xhtml"})
        self.assertIn("About the War", t["text"])
        a = W._m150_argv(self.BID, {"behalten": ["about-the-war.xhtml"], "sprache": "en"}, "CK")
        self.assertIn("--behalten=about-the-war.xhtml", a)
        with self.assertRaises(ValueError):
            W._m150_argv(self.BID, {"entfernen": ["gibtsnicht.xhtml"]}, "CK")

    def test_neuanlage_auto(self):
        bid, e = self.neu([("titel.xhtml", seite("Title", ["The Mirror Test"])), kap(1), kap(2)])
        self.assertEqual((bid, e), (self.BID, "auto"))
        b = self.bj()
        self.assertEqual((b["quelle"], b["mandant"], b["quellsprache"]), ("user_epub", "user:anna", "en"))
        self.assertTrue(b["klappentext_vorhanden"])
        self.assertTrue(os.path.exists(os.path.join(self.ordner(), "quelle", "in.epub")))
        self.assertEqual(json.load(open(config.INDEX_PATH))["books"][self.BID], "user:anna")
        self.assertEqual(S.zustand(self.BID, "150"), "frei")

    def test_opf_ohne_sprache_mensch_regler(self):
        self.assertEqual(self.neu([kap(1), kap(2)], sprache="")[1], "mensch")
        self.assertIn("Sprache im OPF fehlt", self.gruende())
        self.assertEqual(self.still(E.run, self.BID, sprache="en"), "auto")

    def test_verdaechtige_seite_mensch_behalten(self):
        about = ("about-the-war.xhtml", seite("About the War", [SATZ * 2] * 40))
        self.assertEqual(self.neu([kap(1), about, kap(2)])[1], "mensch")
        self.assertIn("per Dateiname entfernt", self.gruende())
        self.assertEqual(self.still(E.run, self.BID, behalten=["about-the-war.xhtml"]), "auto")
        self.assertEqual(self.bj()["umfang"]["kapitel"], 3)

    def test_drm_nichts_angelegt(self):
        with self.assertRaises(E.EpubFehler):
            self.neu([kap(1)], drm=True)
        self.assertFalse(os.path.exists(config.INDEX_PATH))

    def test_kein_inhalt_kein_index(self):
        with self.assertRaises(E.EpubFehler):
            self.neu([("toc.xhtml", seite("Contents", ["1"]))])
        self.assertFalse(os.path.exists(config.INDEX_PATH))
        self.assertFalse(os.path.exists(self.ordner()))

    def test_zu_kurz_stopp(self):
        self.assertEqual(self.neu([kap(1, n=5)])[1], "stopp")

    def test_inhaltsanteil_mensch(self):
        kol = ("x.xhtml", seite("Colophon", [SATZ * 2] * 60, "colophon"))
        self.assertEqual(self.neu([kap(1), kap(2), kol])[1], "mensch")
        self.assertIn("inhaltsanteil", self.gruende())

    def test_neueinlesen_leert_kapitel_und_behaelt_felder(self):
        self.neu([kap(1), kap(2), kap(3)])
        p = os.path.join(self.ordner(), "book.json")
        b = self.bj(); b["rechte"] = {"art": "eigene"}; json.dump(b, open(p, "w"))
        self.assertEqual(self.still(E.run, self.BID, entfernen=["k3.xhtml"]), "auto")
        mod = os.listdir(os.path.join(self.ordner(), "work", "modernized"))
        self.assertEqual(sorted(mod), ["chapter-1.json", "chapter-2.json"])
        self.assertEqual(self.bj()["rechte"], {"art": "eigene"})

    def test_verlag_immer_mensch(self):
        self.assertEqual(self.neu([kap(1), kap(2)], mandant="verlag:v1")[1], "mensch")
        self.assertEqual(self.bj()["quelle"], "verlag_epub")
        self.assertIn("Kapitelliste", self.gruende())

    def test_kette_ohne_regler_nur_pruefung(self):
        self.neu([kap(1), kap(2)])
        os.remove(os.path.join(self.ordner(), "work", "modernized", "chapter-2.json"))
        self.assertEqual(self.still(E.run, self.BID), "stopp")


if __name__ == "__main__":
    unittest.main()
