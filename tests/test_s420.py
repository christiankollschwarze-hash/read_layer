"""Stage 420 Sprecher.  py -3.11 -m unittest tests.test_s420"""
import contextlib, io, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import api_layer
from pipeline import status as S
from pipeline import s410_casting as C
from pipeline import s420_sprecher as P

Q = {"c001_00001_h": ("h", "Chapter One", "Kapitel eins"),
     "c001_00002_s": ("s", "Alice sat by the river.", "Alice saß am Fluss."),
     "c001_00003_dl": ("dl", "\"Who are you?\" said the Hatter.", "„Wer bist du?“, sagte der Hutmacher."),
     "c001_00004_dl": ("dl", "\"I am Alice,\" she said.", "„Ich bin Alice“, sagte sie."),
     "c002_00001_h": ("h", "Chapter Two", "Kapitel zwei"),
     "c002_00002_s": ("s", "The cat grinned.", "Die Katze grinste."),
     "c002_00003_dl": ("dl", "\"Hello,\" said the Cat.", "„Hallo“, sagte die Katze.")}
WER = {"c001_00003_dl": "Hatter", "c001_00004_dl": "Alice", "c002_00003_dl": "Cat"}
ROLLEN = {"de": {"premium": {"engine": "gemini", "inhalte": ["hoerbuch", "hoerspiel"],
                             "erzaehler": {"rolle": "erzaehler", "figur": None, "stimme": "Charon"},
                             "ensemble": [{"rolle": "figur", "figur": "Alice", "name_lg": "Alice", "stimme": "w"},
                                          {"rolle": "figur", "figur": "Hatter", "name_lg": "Hutmacher", "stimme": "m"}],
                             "statisten": [{"figur": "Cat", "name_lg": "Katze", "stimme": "Charon"}]}}}
HS = [{"sprache": "de", "inhalt": "hoerbuch", "stufe": "premium", "kanaele": ["taella"]},
      {"sprache": "de", "inhalt": "hoerspiel", "stufe": "premium", "kanaele": ["taella"]}]


class T420(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.tmp.name
        self.d = os.path.join(r, "a", "books", "w")
        self.wd = os.path.join(self.d, "work")
        os.makedirs(self.wd)
        self.alt = (config.book_dir, config.work_dir, config.RUN_MODE, config.BASE_DIR, api_layer.call_model)
        config.book_dir = lambda b: self.d
        config.work_dir = lambda b: self.wd
        config.BASE_DIR = r
        config.RUN_MODE = "live"
        self.aufrufe, self.kaputt, self.unsicher, self.anders, self.fehler = [], set(), set(), set(), 0
        api_layer.call_model = self.fake
        self.werk()

    def tearDown(self):
        (config.book_dir, config.work_dir, config.RUN_MODE, config.BASE_DIR, api_layer.call_model) = self.alt
        self.tmp.cleanup()

    # ---------------------------------------------------------- Attrappen
    def fake(self, task, prompt, **kw):
        if self.fehler:
            self.fehler -= 1
            return "kein json"
        teil = prompt.split("LINES (in reading order):", 1)[1]
        out, ids = {}, []
        for z in teil.strip().splitlines():
            j = json.loads(z)
            ids.append(j["id"])
            a = {}
            for lg in ("de", "en"):
                if lg not in j:
                    continue
                s = WER.get(j["id"])
                if lg == "en" and j["id"] in self.anders:
                    s = "Alice"
                seg = P.mock_seg(j[lg], s)
                if seg and j["id"] in self.kaputt and lg == "de":
                    seg = [{"t": "falsch", "s": s}]
                if seg and j["id"] in self.unsicher:
                    for x in seg:
                        if x["s"] != P.ERZ:
                            x["u"] = 1
                if seg:
                    a[lg] = seg
            if a:
                out[j["id"]] = a
        self.aufrufe.append(ids)
        return json.dumps(out, ensure_ascii=False)

    def werk(self, produkte=None, extra=None, gates=("400", "410"), frei=True, sprech=None, meta=None, rollen=None):
        b = {"book_slug": "w", "quelle": "gutenberg", "quellsprache": "en", "fassung": "modernisiert",
             "mandant": "somnio", "produkte": produkte or HS,
             "rechte": {"art": "gemeinfrei", "bearbeitung": True, "versichert": {"wer": "t", "wann": "x"}}}
        b.update(extra or {})
        self.schreib(os.path.join(self.d, "book.json"), b)
        content = {k: {"type": t, "en": q, "de": z} for k, (t, q, z) in Q.items()}
        sp = {k: {"de": (sprech or {}).get(k, z)} for k, (t, q, z) in Q.items()}
        self.schreib(os.path.join(self.wd, "400_regie.json"),
                     {"book_id": "w", "meta": meta or {}, "content": content, "production": {"sprechtext": sp}})
        rollen = rollen or ROLLEN
        c = {"schema": 2, "rollen": rollen, "freigabe": {"wer": "CK", "hash": C.kern(rollen)} if frei else None}
        self.schreib(os.path.join(self.wd, "casting.json"), c)
        for g in gates:
            S.ergebnis("w", g, "auto", wer="test")

    def schreib(self, p, o):
        with open(p, "w", encoding="utf-8") as f:
            json.dump(o, f, ensure_ascii=False)

    def lesen(self, n):
        with open(os.path.join(self.wd, n), encoding="utf-8") as f:
            return json.load(f)

    def lauf(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return P.run("w", wer="test", **kw)

    # ---------------------------------------------------------- Tests
    def test_auto_und_ausgabe(self):
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        a = self.lesen("420_sprecher.json")
        seg = a["saetze"]["c001_00003_dl"]["de"]["seg"]
        self.assertEqual([x["s"] for x in seg], ["Hatter", "Erzaehler"])
        self.assertEqual(a["saetze"]["c002_00003_dl"]["de"]["seg"][0]["s"], "Cat")      # Statist bleibt Figur
        self.assertNotIn("c001_00002_s", a["saetze"])                                 # ganz Erzaehler
        alt = self.lesen("sprecher.json")
        self.assertEqual(alt["c001_00004_dl"]["de"][0]["s"], "Alice")
        self.assertEqual(alt["c001_00004_dl"]["en"][0]["s"], "Alice")                  # Referenz fuer Altabnehmer
        self.assertEqual(g.metriken["konsistenz_de"], 1.0)
        self.assertEqual(S.zustand("w", "420"), "frei")
        self.assertEqual(g.metriken["llm_aufrufe"], 2)

    def test_checkpoint_und_aenderung(self):
        self.lauf()
        n = len(self.aufrufe)
        g = self.lauf()
        self.assertEqual(len(self.aufrufe), n, "unveraendert -> kein LLM")
        self.assertEqual(g.ergebnis["ergebnis"], "auto")
        self.werk(sprech={"c001_00004_dl": "„Ich bin Alice!“, sagte sie."})
        g = self.lauf()
        self.assertEqual(self.aufrufe[-1], ["c001_00004_dl"])
        self.assertIn("Alice!", self.lesen("420_sprecher.json")["saetze"]["c001_00004_dl"]["de"]["seg"][0]["t"])
        self.lauf(saetze=["c002_00003_dl"])
        self.assertEqual(self.aufrufe[-1], ["c002_00003_dl"])

    def test_casting_nicht_frei_stopp(self):
        self.werk(frei=False)
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual(g.ergebnis["ruecksprung"], "410")
        self.assertEqual(self.aufrufe, [])
        S.zuruecksetzen("w", "410", "test", "x")
        self.werk(gates=("400",))
        self.assertEqual(self.lauf().ergebnis["ruecksprung"], "410")

    def test_kaputt_einzeln_neu_dann_rueckfall(self):
        self.fehler = 1                                 # erster Teil kaputt -> einzeln neu
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertTrue(all(len(x) == 1 for x in self.aufrufe[0:3]))
        self.kaputt = {"c002_00003_dl"}
        g = self.lauf(neu=True)
        self.assertEqual(g.ergebnis["ergebnis"], "mensch", g.bericht())
        r = self.lesen("420_sprecher.json")["saetze"]["c002_00003_dl"]["de"]
        self.assertEqual(r["rf"], "rekonstruktion")
        self.assertEqual(r["seg"][0]["s"], "Erzaehler")
        self.assertEqual(self.lesen("420_pruefung.json")["de"]["rueckfall"][0]["id"], "c002_00003_dl")

    def test_keine_antwort_stopp(self):
        self.fehler = 99
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertIn("Abdeckung", " ".join(g.ergebnis["gruende"]))

    def test_unsicher_und_konsistenz_mensch(self):
        self.unsicher = {"c001_00004_dl"}
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertTrue(any("unsicher_de" in t for t in g.ergebnis["gruende"]))
        self.unsicher, self.anders = set(), {"c001_00003_dl"}
        g = self.lauf(neu=True)
        self.assertTrue(any("konsistenz_de" in t for t in g.ergebnis["gruende"]), g.bericht())

    def test_uebernahme_alt(self):
        alt = {"c001_00003_dl": {"de": [{"t": "„Wer bist du?“,", "s": "Hatter"}, {"t": "sagte der Hutmacher.", "s": "Erzaehler"}],
                                 "en": [{"t": "\"Who are you?\"", "s": "Hatter"}, {"t": "said the Hatter.", "s": "Erzaehler"}]},
               "c001_00004_dl": {"de": [{"t": "„Ich bin Alice“,", "s": "Alice"}, {"t": " sagte sie.", "s": "Erzaehler"}]}}
        self.schreib(os.path.join(self.wd, "sprecher.json"), alt)
        g = self.lauf()
        self.assertEqual(self.aufrufe, [["c002_00002_s", "c002_00003_dl"]], "nur Kapitel 2 neu")
        self.assertIn("uebernommen", " ".join(g.ergebnis["hinweise"]))
        self.assertEqual(self.lesen("420_sprecher.json")["saetze"]["c001_00003_dl"]["de"]["q"], "uebernommen")
        self.assertTrue(os.path.exists(os.path.join(self.wd, "sprecher_v1.json")))

    def test_drama(self):
        self.werk(meta={"modus": "drama"})
        dat = self.lesen("400_regie.json")
        dat["content"]["c001_00003_dl"]["sprecher"] = "HATTER"
        dat["content"]["c002_00003_dl"]["sprecher"] = "Dormouse"
        self.schreib(os.path.join(self.wd, "400_regie.json"), dat)
        g = self.lauf()
        self.assertEqual(self.aufrufe, [])
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertTrue(any("Drama-Rollennamen" in t for t in g.ergebnis["gruende"]))
        self.assertEqual(self.lesen("420_sprecher.json")["saetze"]["c001_00003_dl"]["de"]["seg"][0]["s"], "Hatter")

    def test_korrektur_cli(self):
        self.lauf()
        with contextlib.redirect_stdout(io.StringIO()):
            rc = P.main(["w", "--sprecher", "c001_00004_dl:0=Hatter", "--wer", "CK"])
        self.assertEqual(rc, 0)
        r = self.lesen("420_sprecher.json")["saetze"]["c001_00004_dl"]["de"]
        self.assertEqual((r["q"], r["seg"][0]["s"]), ("manuell", "Hatter"))
        with contextlib.redirect_stdout(io.StringIO()):
            rc = P.main(["w", "--segmente", 'c001_00002_s=[{"t":"Alice saß am Fluss.","s":"Nobody"}]', "--wer", "CK"])
        self.assertEqual(rc, 0)
        self.assertIn("veraltet", " ".join(S.laden("w")["stages"]["420"]["hinweise"]))

    def test_verlag_mensch_und_regler(self):
        self.werk(extra={"mandant": "verlag:x"})
        g = self.lauf(regler={"teil": 1})
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertEqual(len(self.aufrufe), 5)
        self.assertEqual(json.load(open(os.path.join(self.d, "book.json")))["sprecher_regler"]["teil"], 1)

    def test_mock_und_trocken(self):
        g = self.lauf(trocken=True)
        self.assertFalse(os.path.exists(os.path.join(self.wd, "420_sprecher.json")))
        self.assertEqual(self.aufrufe, [])
        config.RUN_MODE = "mock"
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(self.aufrufe, [])
        config.RUN_MODE = "live"
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp", "Mock-Zuordnung im Live-Lauf")

    def test_kein_hoerspiel(self):
        self.werk(produkte=HS[:1])
        self.assertEqual(self.lauf().ergebnis["ergebnis"], "stopp")

    def test_kette(self):
        import run
        self.assertIn("420", run.UMGEBAUT)
        self.assertIn("420", run.NEU)
        self.assertNotIn("420", run.ALT)


if __name__ == "__main__":
    unittest.main()
