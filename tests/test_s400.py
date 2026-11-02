"""Stage 400 Regie + Sprechtext-Regeln.  py -3.11 -m unittest tests.test_s400"""
import contextlib, io, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import status as S
from pipeline import s400_regie as P
from pipeline import sprechtext as ST

Q = {"c001_00001_h": ("h", "Chapter IV", "Kapitel IV"),
     "c001_00002_s": ("s", "Margaret walked to the house of Henry VIII.", "Margarete ging zum Haus von Heinrich VIII."),
     "c001_00003_dl": ("dl", "\"Who is there?\" she asked.", "„Wer ist da?“, fragte sie."),
     "c001_00004_p": ("p", "", ""),
     "c002_00001_h": ("h", "V.", "V."),
     "c002_00002_s": ("s", "Then I knocked at the door of Blankenese.", "Dann klopfte ich an die Tür in Blankenese.")}
PROFIL = {"characters": {"Margaret": {"de": "Margarete", "pronunciation": "ˈmɑːɡrət"}},
          "untranslated": {"Blankenese": {"meaning": "district"}}}


class TSprech(unittest.TestCase):
    def test_regeln(self):
        self.assertEqual(ST.sprechtext("Chapter IV", "en", "h"), "Chapter Four")
        self.assertEqual(ST.sprechtext("CHAPTER IV", "en", "h"), "CHAPTER FOUR")
        self.assertEqual(ST.sprechtext("Kapitel IV", "de", "h"), "Kapitel vier")
        self.assertEqual(ST.sprechtext("IX. Der Nimmervogel", "de", "h"), "Neun. Der Nimmervogel")
        self.assertEqual(ST.sprechtext("XIV", "en", "h"), "Fourteen")
        self.assertEqual(ST.sprechtext("I Remember", "en", "h"), "I Remember")
        self.assertEqual(ST.sprechtext("Henry VIII was king.", "en"), "Henry the Eighth was king.")
        self.assertEqual(ST.sprechtext("Heinrich VIII. war König.", "de"), "Heinrich der Achte war König.")
        self.assertEqual(ST.sprechtext("Then I went, and so did I.", "en"), "Then I went, and so did I.")
        self.assertEqual(ST.sprechtext("World War II", "en"), "World War Two")
        self.assertEqual(ST.sprechtext("_Hamburg, 7:15 Uhr_", "de"), "Hamburg, sieben Uhr fünfzehn")
        self.assertEqual(ST.sprechtext("des 19. Jahrhunderts", "de"), "des neunzehnten Jahrhunderts")
        self.assertEqual(ST.sprechtext("am 16.08.2007", "de"), "am sechzehnten achten 2007")
        self.assertEqual(ST.sprechtext("1860-1935", "en"), "1860 to 1935")
        self.assertEqual(ST.roemisch_offen("the XIV battalion"), ["XIV"])
        self.assertEqual(ST.roemisch_offen("Then I went"), [])
        self.assertEqual(ST.roemisch_offen("V.", True), ["V"])

    def test_abbildung(self):
        t = "_Henry VIII_ came in 1860."
        sp, abb = ST.sprechtext_abb(t, "en", "s")
        self.assertEqual(sp, "Henry the Eighth came in 1860.")
        i = sp.index("the Eighth")
        self.assertEqual(ST.lesespan(abb, i, i + 10, len(sp)), (t.index("VIII"), t.index("VIII") + 4))
        j = sp.index("came")
        self.assertEqual(ST.lesespan(abb, j, j + 4, len(sp)), (t.index("came"), t.index("came") + 4))
        h = sp.index("Henry")
        self.assertEqual(ST.lesespan(abb, h, h + 5, len(sp)), (1, 6))

    @unittest.skipIf(ST._n2w is None, "num2words fehlt")
    def test_erweitert(self):
        t = "It was 1860 & 50% of 1,000 men left at 7:05."
        sp = ST.sprechtext(t, "en", "s", erweitert=True)
        self.assertEqual(sp, "It was eighteen sixty and fifty percent of one thousand men left at seven oh five.")
        self.assertEqual(ST.reste(sp), [])
        self.assertEqual(ST.sprechtext("Found 16.08.2007, 03:20, 28–31 August.", "en", "s", erweitert=True),
                         "Found the sixteenth of August two thousand and seven, three twenty, "
                         "twenty-eight to thirty-one August.")
        sp, abb = ST.sprechtext_abb(t, "en", "s", erweitert=True)
        k = sp.index("and")
        self.assertEqual(ST.lesespan(abb, k, k + 3, len(sp)), (t.index("&") - 1, t.index("&") + 2))


class T400(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.tmp.name
        self.d = os.path.join(r, "a", "books", "w")
        os.makedirs(os.path.join(self.d, "work"))
        self.alt = (config.book_dir, config.work_dir, config.RUN_MODE, config.BASE_DIR, config.TTS_BACKEND)
        config.book_dir = lambda b: self.d
        config.work_dir = lambda b: os.path.join(self.d, "work")
        config.BASE_DIR = r
        config.RUN_MODE = "live"
        config.TTS_BACKEND = "gemini_api"
        with open(os.path.join(r, "a", "author.json"), "w", encoding="utf-8") as f:
            json.dump({"name_display": "Jane Doe", "wirkungssprache": "en"}, f)
        self.werk()

    def tearDown(self):
        (config.book_dir, config.work_dir, config.RUN_MODE, config.BASE_DIR, config.TTS_BACKEND) = self.alt
        self.tmp.cleanup()

    def werk(self, stufe="basic", inhalt="hoerbuch", regler=None, de=None, gates=("330", "340"), extra=None):
        b = {"book_slug": "w", "quelle": "gutenberg", "quellsprache": "en", "fassung": "modernisiert",
             "mandant": "somnio", "titel_original": "The House",
             "fassungen": [{"sprache": "de", "titel": "Das Haus"}],
             "produkte": [{"sprache": "de", "inhalt": "text", "kanaele": ["taella"]},
                          {"sprache": "de", "inhalt": inhalt, "stufe": stufe, "kanaele": ["taella"]}],
             "rechte": {"art": "gemeinfrei", "bearbeitung": True, "versichert": {"wer": "t", "wann": "x"}}}
        if regler:
            b["audio_regler"] = regler
        b.update(extra or {})
        with open(os.path.join(self.d, "book.json"), "w", encoding="utf-8") as f:
            json.dump(b, f)
        de = de or {}
        data = {"book_id": "w", "meta": {"profile": PROFIL, "title": "The House"},
                "content": {k: {"type": t, "en": q, "de": de.get(k, z)} for k, (t, q, z) in Q.items()}}
        with open(os.path.join(self.d, "work", "330_rueckuebersetzung.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        for g in gates:
            S.ergebnis("w", g, "auto", wer="test")

    def lauf(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return P.run("w", wer="test", **kw)

    def aus(self):
        with open(os.path.join(self.d, "work", "400_regie.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_auto_basic(self):
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        d = self.aus()
        p = d["production"]
        self.assertEqual(p["sprechtext"]["c001_00001_h"]["de"], "Kapitel vier")
        self.assertEqual(p["sprechtext"]["c002_00001_h"]["de"], "Fünf.")
        self.assertIn("der Achte", p["sprechtext"]["c001_00002_s"]["de"])
        self.assertIn("c001_00002_s", p["abbildung"])
        self.assertNotIn("en", p["sprechtext"]["c001_00001_h"])          # nur bestellte Audiosprache
        self.assertIn("c001_00004_p", p["pause_after_ms"])
        self.assertEqual(p["direction"], {})                              # Basic: keine Regie
        self.assertEqual(d["content"]["c001_00001_h"]["de"], "Kapitel IV")  # Lesetext unveraendert
        a = {k["art"]: k for k in d["ansagen"]["de"]}
        self.assertEqual(a["titel"]["sprechtext"], "Das Haus.")
        self.assertEqual(a["autor"]["sprechtext"], "von Jane Doe.")
        self.assertIn("KI-Stimme", a["sprecher"]["sprechtext"])
        self.assertIn("{sprecher}", a["sprecher"]["vorlage"])
        self.assertEqual(a["ende"]["position"], "ende")
        self.assertTrue(any("ohne Aussprache" in h for h in g.ergebnis["hinweise"]))   # Blankenese: nur Hinweis

    def test_premium_aussprache_mensch(self):
        self.werk(stufe="premium")
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertTrue(any("ohne Aussprache 1" in x for x in g.ergebnis["gruende"]))
        d = self.aus()["production"]["direction"]
        self.assertIn("Blankenese pronounced as in English", d["c002_00002_s"]["de"])
        self.assertIn("Margarete", d["c001_00002_s"]["de"])
        self.assertIn("direction", self.aus()["ansagen"]["de"][0])
        # Aussprache manuell -> auto
        g = self.lauf(aussprache=["Blankenese=BLAHN-ke-nay-ze"])
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertIn("Blankenese pronounced BLAHN-ke-nay-ze", self.aus()["production"]["direction"]["c002_00002_s"]["de"])

    def test_pron_skip(self):
        self.werk(stufe="premium", extra={"audio_pron_skip": ["Blankenese"]})
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertNotIn("Blankenese", self.aus()["production"]["direction"]["c002_00002_s"]["de"])

    def test_gates_stopp(self):
        self.werk(gates=("330",))
        S.zuruecksetzen("w", "340", wer="test", grund="t")
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertFalse(os.path.exists(os.path.join(self.d, "work", "400_regie.json")))

    def test_regler_ungueltig(self):
        self.werk(regler={"betonung": 12, "emotion": 5, "tempo": 5})
        self.assertEqual(self.lauf().ergebnis["ergebnis"], "stopp")

    def test_regler_cli(self):
        g = self.lauf(regler={"tempo": 9, "betonung": None, "emotion": None})
        self.assertEqual(g.ergebnis["ergebnis"], "auto")
        with open(os.path.join(self.d, "book.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["audio_regler"]["tempo"], 9)

    def test_keine_audiosprache(self):
        self.werk(inhalt="text", stufe=None)
        self.assertEqual(self.lauf().ergebnis["ergebnis"], "stopp")

    def test_leer_stopp(self):
        self.werk(de={"c001_00003_dl": ""})
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual(g.ergebnis["ruecksprung"], "310")

    def test_roemisch_mensch_manuell_freigabe(self):
        self.werk(de={"c002_00002_s": "Dann klopfte das XIV Bataillon."})
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertEqual(g.pruef["de"]["fehler"]["roemisch"][0]["id"], "c002_00002_s")
        # Mensch-Freigabe -> gleiche Ausgabe -> auto
        S.entscheiden("w", "400", "frei", wer="CK", grund="ok", rolle="admin")
        self.assertEqual(self.lauf().ergebnis["ergebnis"], "auto")
        # manueller Sprechtext
        S.zuruecksetzen("w", "400", wer="test", grund="t")
        g = self.lauf(sprechtext_man=["c002_00002_s=Dann klopfte das vierzehnte Bataillon."])
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        p = self.aus()["production"]
        self.assertEqual(p["sprechtext"]["c002_00002_s"]["de"], "Dann klopfte das vierzehnte Bataillon.")

    @unittest.skipIf(ST._n2w is None, "num2words fehlt")
    def test_reste_erweitert(self):
        self.werk(de={"c002_00002_s": "Es war 1860 & kalt."})
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(g.metriken["repariert"], 1)
        self.assertEqual(self.aus()["production"]["sprechtext"]["c002_00002_s"]["de"],
                         "Es war achtzehnhundertsechzig und kalt.")

    def test_mock_stopp(self):
        self.werk(de={"c002_00002_s": "[MOCK] x"})
        self.assertEqual(self.lauf().ergebnis["ergebnis"], "stopp")

    def test_trocken(self):
        g = self.lauf(trocken=True)
        self.assertEqual(g.ergebnis["ergebnis"], "auto")
        self.assertFalse(os.path.exists(os.path.join(self.d, "work", "400_regie.json")))

    def test_style_lang(self):
        self.werk(stufe="premium", extra={"audio_pron_skip": ["Blankenese"]})
        g = self.lauf(style_max=20)
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertTrue(any("Style" in x for x in g.ergebnis["gruende"]))


if __name__ == "__main__":
    unittest.main()
