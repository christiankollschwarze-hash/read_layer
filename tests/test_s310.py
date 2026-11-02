"""Stage 310 Übersetzung.  py -3.11 -m unittest tests.test_s310"""
import contextlib, io, json, os, re, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import api_layer
from pipeline import status as S
from pipeline import s310_uebersetzung as P

Q = {"c001_00001_h": ("h", "Chapter IV"),
     "c001_00002_s": ("s", "Margaret walked slowly to the old house by the river."),
     "c001_00003_s": ("s", "The door was open, and the wind was very cold that night."),
     "c001_00004_dl": ("dl", "\"Who is there?\" she asked."),
     "c002_00001_h": ("h", "Chapter V"),
     "c002_00002_s": ("s", "She knocked twice at the door, but nobody came to open it.")}
DE = {"c001_00001_h": "Kapitel IV",
      "c001_00002_s": "Margarete ging langsam zu dem alten Haus am Fluss.",
      "c001_00003_s": "Die Tür war offen, und der Wind war sehr kalt in jener Nacht.",
      "c001_00004_dl": "„Wer ist da?“, fragte sie.",
      "c002_00001_h": "Kapitel V",
      "c002_00002_s": "Sie klopfte zweimal an die Tür, aber niemand kam, um sie zu öffnen."}


class T310(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.tmp.name
        self.d = os.path.join(r, "w")
        os.makedirs(os.path.join(self.d, "work"))
        self.alt = (config.book_dir, config.work_dir, config.RUN_MODE, api_layer.call_model, config.BASE_DIR)
        config.book_dir = lambda b: self.d
        config.work_dir = lambda b: os.path.join(self.d, "work")
        config.BASE_DIR = r
        config.RUN_MODE = "live"
        self.aufrufe = []
        self.ersatz = {}          # id -> Liste Antworten (Folgeaufrufe)
        self.weglassen = set()

        def fake(task, prompt, **kw):
            self.aufrufe.append(prompt)
            ids = re.findall(r'^\s+"(c\d+_\d+_\w+)":', prompt.split("Sentences (as JSON")[-1], re.M)
            out = {}
            for i in ids:
                if i in self.weglassen:
                    self.weglassen.discard(i)
                    continue
                l = self.ersatz.get(i)
                out[i] = l.pop(0) if l else DE[i]
            return json.dumps(out, ensure_ascii=False)
        api_layer.call_model = fake
        self.werk()

    def tearDown(self):
        config.book_dir, config.work_dir, config.RUN_MODE, api_layer.call_model, config.BASE_DIR = self.alt
        self.tmp.cleanup()

    def werk(self, ziele=("de",), quelle="gutenberg", anker="Margarete ging langsam. Die Tür war offen. Sie klopfte."):
        b = {"book_slug": "w", "quelle": quelle, "quellsprache": "en", "fassung": "modernisiert",
             "mandant": "somnio", "titel_original": "The House",
             "produkte": [{"sprache": z, "inhalt": "text", "kanaele": ["taella"]} for z in ziele],
             "rechte": {"art": "gemeinfrei", "bearbeitung": True, "versichert": {"wer": "t", "wann": "x"}}}
        with open(os.path.join(self.d, "book.json"), "w", encoding="utf-8") as f:
            json.dump(b, f)
        prof = {"style": {"setting": "England, 1890s"}, "characters": {"Margaret": {"de": "Margarete"}},
                "untranslated": {}, "glossary": {"door": {"de": "Tür"}}, "idioms": {}}
        data = {"book_id": "w", "meta": {"profile": prof, "pretranslation": {"c001": {"de": anker}, "c002": {"de": ""}}},
                "content": {k: {"type": t, "en": q} for k, (t, q) in Q.items()}}
        with open(os.path.join(self.d, "work", "300_voruebersetzung.json"), "w", encoding="utf-8") as f:
            json.dump(data, f)

    def lauf(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return P.run("w", wer="test", **kw)

    def aus(self):
        with open(os.path.join(self.d, "work", "310_uebersetzung.json"), encoding="utf-8") as f:
            return json.load(f)["content"]

    def test_auto_checkpoint_ausschnitt(self):
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(self.aus()["c001_00002_s"]["de"], DE["c001_00002_s"])
        self.assertEqual(len(self.aufrufe), 2)                      # je Kapitel ein Batch
        self.assertIn('"Margaret" -> "Margarete"', self.aufrufe[0])
        self.assertIn("free translation", self.aufrufe[0])
        self.assertNotIn("free translation", self.aufrufe[1])       # c002 ohne Anker
        self.lauf()
        self.assertEqual(len(self.aufrufe), 2)                      # Checkpoint 0 $
        # geaenderter Satz -> nur dieser neu
        with open(os.path.join(self.d, "work", "300_voruebersetzung.json"), encoding="utf-8") as f:
            d = json.load(f)
        d["content"]["c002_00002_s"]["en"] = "She knocked three times at the door, but nobody came."
        with open(os.path.join(self.d, "work", "300_voruebersetzung.json"), "w", encoding="utf-8") as f:
            json.dump(d, f)
        self.lauf()
        self.assertEqual(len(self.aufrufe), 3)
        self.assertIn("c002_00002_s", self.aufrufe[2])
        self.assertNotIn("c002_00001_h", self.aufrufe[2].split("Sentences (as JSON")[-1])

    def test_fehlende_id_nachgefordert(self):
        self.weglassen = {"c001_00003_s"}
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(g.metriken["nachgefordert"], 1)
        self.assertIn("Surrounding sentences", self.aufrufe[1])

    def test_luecke_stopp(self):
        self.ersatz = {"c001_00003_s": ["", "", ""]}
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp", g.bericht())
        self.assertIn("Luecken", " ".join(g.ergebnis["gruende"]))

    def test_kopie_repariert(self):
        self.ersatz = {"c001_00003_s": [Q["c001_00003_s"][1]]}
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(g.metriken["einzeln"], 1)
        self.assertIn("previous attempt had a problem", self.aufrufe[-2])

    def test_kopie_bleibt_mensch_und_annehmen(self):
        kopie = Q["c001_00003_s"][1]
        self.ersatz = {"c001_00003_s": [kopie, kopie]}
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch", g.bericht())
        self.assertEqual(g.pruef["de"][0]["id"], "c001_00003_s")
        n = len(self.aufrufe)
        g = self.lauf(annehmen=["c001_00003_s"])
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(len(self.aufrufe), n)                      # keine neue Wiederholung

    def test_manuell(self):
        g = self.lauf(satz_text=["c001_00002_s=Margarete schritt langsam zum alten Haus am Fluss."])
        self.assertEqual(self.aus()["c001_00002_s"]["de"], "Margarete schritt langsam zum alten Haus am Fluss.")
        self.assertEqual(g.ergebnis["ergebnis"], "auto")

    def test_schema_und_glossar(self):
        self.assertTrue(P.schema_ok("CHAPTER IV", "Kapitel 4"))
        self.assertFalse(P.schema_ok("CHAPTER IV", "Kapitel V"))
        self.assertTrue(P.schema_ok("Chapter I", "Kapitel"))      # 'I' allein ist keine Nummer
        aus = P.profil_ausschnitt({"glossary": {"door": {"de": "Tür"}}, "characters": {}}, "the door", "de")
        self.assertIn("glossar:door->Tür", P.pruefe_satz("The door was open, really.", "Das Portal stand offen.",
                                                           "s", "en", "de", aus))

    def test_sprache_falsch_mensch(self):
        fr = "La porte était ouverte et le vent était très froid dans la nuit."
        self.ersatz = {"c001_00003_s": [fr, fr]}
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertTrue(any("sprache" in x for x in g.ergebnis["gruende"]))

    def test_epub_titel(self):
        self.werk(quelle="user_epub")
        self.ersatz = {}
        orig = api_layer.call_model

        def mit_titel(task, prompt, **kw):
            if prompt.startswith("Translate this book title"):
                self.aufrufe.append(prompt)
                return "Das Haus"
            return orig(task, prompt, **kw)
        api_layer.call_model = mit_titel
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        with open(os.path.join(self.d, "book.json"), encoding="utf-8") as f:
            f_ = {x["sprache"]: x for x in json.load(f)["fassungen"]}
        self.assertEqual(f_["de"]["titel"], "Das Haus")
        self.assertEqual(f_["de"]["titel_quelle"], "310")

    def test_uebernehmen_trocken(self):
        self.lauf()
        n = len(self.aufrufe)
        import shutil
        shutil.rmtree(os.path.join(self.d, "work", "ckpt"))
        g = self.lauf(uebernehmen=True)
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(len(self.aufrufe), n)
        g = self.lauf(trocken=True)
        self.assertEqual(g.ergebnis["ergebnis"], "auto")
        self.assertEqual(len(self.aufrufe), n)

    def test_anker_ausschnitt(self):
        q = "A. " * 100 + "B. " * 100
        a = "Eins. " * 100 + "Zwei. " * 100
        t = P.anker_ausschnitt(a, q, len(q) // 2, len(q))
        self.assertIn("Zwei", t)
        self.assertLess(len(t), len(a))


if __name__ == "__main__":
    unittest.main()
