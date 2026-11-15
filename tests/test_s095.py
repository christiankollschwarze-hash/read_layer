"""Stage 095 Produktwahl.  py -3.11 -m unittest tests.test_s095"""
import io, json, os, sys, tempfile, unittest, contextlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import s095_produktwahl as P, status as S

REG = {"standard": "CK", "nutzer": {"CK": {"rolle": "admin"}, "anna": {"rolle": "kurator"}}, "mandanten": {}}
W = "u-test"


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._wd, self._bd = config.work_dir, config.book_dir
        config.work_dir = lambda b: self.tmp.name
        config.book_dir = lambda b: self.tmp.name
        reg = os.path.join(self.tmp.name, "rollen.json")
        json.dump(REG, open(reg, "w"))
        os.environ["READLAYER_ROLLEN"] = reg
        open(os.path.join(self.tmp.name, "raw_modernized.txt"), "w").write("x" * 200000)

    def tearDown(self):
        config.work_dir, config.book_dir = self._wd, self._bd
        os.environ.pop("READLAYER_ROLLEN", None)
        self.tmp.cleanup()

    def buch(self, **d):
        base = {"quellsprache": "en", "gutenberg_id": 1, "quelle": "gutenberg",
                "rechte": {"art": "gemeinfrei", "bearbeitung": True}, "fassung": "modernisiert"}
        base.update(d)
        json.dump(base, open(os.path.join(self.tmp.name, "book.json"), "w"))

    def roh(self):
        return json.load(open(os.path.join(self.tmp.name, "book.json")))

    def lauf(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return P.run(W, **kw)

    def test_somnio_default_auto_mit_wunsch(self):
        self.buch(wunsch={"zielsprachen": ["fr", "de"]})
        self.assertEqual(self.lauf(), "auto")
        p = self.roh()["produkte"]
        self.assertEqual([x["sprache"] for x in p], ["en", "fr", "de"])
        d = S.laden(W)["stages"]
        self.assertEqual(d["310"]["zustand"], "offen")
        self.assertEqual(d["500"]["zustand"], "entfaellt")
        self.assertGreater(d["095"]["metriken"]["angebot_usd"]["summe"], 0)

    def test_user_mensch_mit_angebot(self):
        self.buch(mandant="user:anna", quelle="user_epub", rechte={"art": "eigene", "bearbeitung": True})
        self.assertEqual(self.lauf(), "mensch")
        self.assertIn("Kostenangebot", " ".join(S.laden(W)["stages"]["095"]["gate"]["gruende"]))

    def test_ungueltig_stopp(self):
        self.buch()
        self.assertEqual(self.lauf(produkte=[P.produkt_parsen("de:hoerspiel:premium:epub")]), "stopp")
        self.assertNotIn("produkte", self.roh())

    def test_hoerspiel_ergaenzt_erzaehler_und_beta_mensch(self):
        self.buch()
        e = self.lauf(produkte=[P.produkt_parsen("de:hoerspiel:drama:taella:+sound_carpet")])
        self.assertEqual(e, "mensch")
        p = self.roh()["produkte"]
        self.assertTrue(any(x["inhalt"] == "hoerbuch" and x["stufe"] == "premium" for x in p))
        self.assertIn("BETA", " ".join(S.laden(W)["stages"]["095"]["gate"]["gruende"]))

    def test_parsen_und_angebot_2027(self):
        p = P.produkt_parsen("de:text:taella,epub")
        self.assertIsNone(p["stufe"])
        with self.assertRaises(ValueError):
            P.produkt_parsen("de:hoerbuch")
        self.buch(produkte=[{"sprache": "de", "inhalt": "hoerbuch", "stufe": "premium", "kanaele": ["taella"]}])
        from pipeline import bestellung
        b = bestellung.lesen(W)
        a26 = P.angebot(b, 100000, heute="2026-12-31")
        a27 = P.angebot(b, 100000, heute="2027-01-01")
        self.assertAlmostEqual(a27["hoerbuch_premium_de"], 2 * a26["hoerbuch_premium_de"])

    def test_veraltet_nach_aenderung(self):
        self.buch()
        self.assertEqual(self.lauf(), "auto")
        self.assertFalse(P.veraltet(W))
        r = self.roh(); r["produkte"].append({"sprache": "de", "inhalt": "text", "kanaele": ["epub"]})
        json.dump(r, open(os.path.join(self.tmp.name, "book.json"), "w"))
        self.assertTrue(P.veraltet(W))

    def test_kurator_fremd_kein_regler(self):
        self.buch()
        with self.assertRaises(PermissionError):
            self.lauf(produkte=[P.produkt_parsen("de:text:taella")], wer="anna")

    def test_hoerspiel_eignung_mensch_und_metrik(self):
        self.buch()
        self.assertEqual(self.lauf(produkte=[P.produkt_parsen("de:hoerspiel:premium:taella")]), "mensch")
        st = S.laden(W)["stages"]["095"]
        self.assertEqual(st["metriken"]["hoerspiel_eignung"]["urteil"], "ungeeignet")
        self.assertIn("ungeeignet", " ".join(st["gate"]["gruende"]))
        dialog = "\n\n".join(f'"Where now, {n}?" asked Tom. "Home," said Anna. "Why?" asked Ben. "Late," said Mary.'
                              for n in range(400))
        open(os.path.join(self.tmp.name, "raw_modernized.txt"), "w").write(dialog)
        self.assertEqual(self.lauf(produkte=[P.produkt_parsen("de:hoerspiel:premium:taella")]), "auto")
        self.assertEqual(S.laden(W)["stages"]["095"]["metriken"]["hoerspiel_eignung"]["urteil"], "geeignet")

    def test_eignung_formen(self):
        from pipeline import hoerspiel_eignung as H
        drama = "\n".join(["ACT I", "SCENE I"] + [f"HAMLET.\nLine {i}.\nHORATIO.\nReply {i}.\nOPHELIA. Hm {i}."
                                                     for i in range(20)])
        self.assertEqual((H.bewerten(drama)["urteil"], H.bewerten(drama)["stufe"]), ("geeignet", "drama"))
        kommentar = " ".join(f'Tu Mu says: "The army must be {i} strong and well led."' for i in range(300))
        self.assertEqual(H.bewerten(kommentar)["urteil"], "ungeeignet")      # Zitate ohne Sprecherwechsel
        kanto = "\n".join(f"CANTO {r}\n" + "verse " * 50 for r in ["I", "II", "III", "IV", "V", "VI", "VII"] * 6)
        self.assertNotEqual(H.bewerten(kanto)["stufe"], "drama")
        self.assertEqual(H.bewerten(None)["urteil"], "unbekannt")

    def test_monitor_095(self):
        from cockpit import werk_api as Wa
        self.buch()
        self.lauf()
        a = Wa._m095_argv(W, {"produkte": [{"sprache": "en", "inhalt": "text", "kanaele": ["taella"]},
                                            {"sprache": "de", "inhalt": "hoerbuch", "stufe": "basic",
                                             "kanaele": ["taella", "epub"]}]}, "CK")
        self.assertEqual(a[4:], ["--wer", "CK", "--produkt=en:text:taella", "--produkt=de:hoerbuch:basic:taella,epub"])
        r = Wa._m095_teil(W, {"produkte": json.dumps([{"sprache": "de", "inhalt": "hoerspiel", "stufe": "drama",
                                                        "kanaele": ["taella"]}])})
        self.assertEqual(r["ergaenzt"], ["de:hoerbuch:premium:taella"])
        self.assertIn("540", r["stages"])
        with self.assertRaises(ValueError):
            Wa._m095_argv(W, {"produkte": [{"sprache": "de", "inhalt": "hoerspiel", "stufe": "premium",
                                             "kanaele": ["epub"]}]}, "CK")
        self.assertEqual(Wa._m095_argv(W, {"default": True}, "CK")[-1], "--default")


if __name__ == "__main__":
    unittest.main()
