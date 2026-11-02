"""Stage 210 Profil.  py -3.11 -m unittest tests.test_s210"""
import contextlib, io, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import api_layer
from pipeline import status as S
from pipeline import s210_profil as P

SAETZE = ["Mr. Holloway walked to Dunmore.", "Margaret waited.", "Holloway knocked.", "Margaret opened the door.",
          "\"The Dauphin is here,\" said Holloway."]


def profil(**kw):
    p = {"style": {"tone": "quiet", "register": "literary", "voice_note": "clear, steady narration"},
         "characters": {"Mr. Holloway": {"de": "Mr. Holloway", "pronunciation": "ˈhɒləweɪ"},
                        "Margaret": {"de": "Margarete", "pronunciation": "ˈmɑːɡrət"}},
         "untranslated": {"Dauphin": {"meaning": "heir", "pronunciation": "doˈfɛ̃"}},
         "glossary": {"door": {"de": "Tür"}},
         "idioms": {}}
    p.update(kw)
    return p


class T210(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.tmp.name
        self.dirs = {w: os.path.join(r, w) for w in ("w", "w-2")}
        for d in self.dirs.values():
            os.makedirs(os.path.join(d, "work"))
        self.alt = (config.book_dir, config.work_dir, config.RUN_MODE, api_layer.call_model, config.BASE_DIR)
        config.book_dir = lambda b: self.dirs[b]
        config.work_dir = lambda b: os.path.join(self.dirs[b], "work")
        config.BASE_DIR = r
        config.RUN_MODE = "live"
        self.antworten, self.aufrufe = [], []

        def fake(task, prompt, **kw):
            self.aufrufe.append(prompt)
            a = self.antworten.pop(0) if self.antworten else profil()
            return a if isinstance(a, str) else json.dumps(a)
        api_layer.call_model = fake
        self.werk("w")

    def tearDown(self):
        config.book_dir, config.work_dir, config.RUN_MODE, api_layer.call_model, config.BASE_DIR = self.alt
        self.tmp.cleanup()

    def werk(self, w, saetze=SAETZE, produkte=None, **kw):
        b = {"book_slug": w, "quelle": "gutenberg", "quellsprache": "en", "fassung": "modernisiert", "mandant": "somnio",
             "produkte": produkte or [{"sprache": "de", "inhalt": "text", "kanaele": ["taella"]}],
             "rechte": {"art": "gemeinfrei", "bearbeitung": True}}
        b.update(kw)
        with open(os.path.join(self.dirs[w], "book.json"), "w", encoding="utf-8") as f:
            json.dump(b, f)
        c = {"c001_00001_h": {"type": "h", "en": "Chapter 1"}}
        for i, t in enumerate(saetze, 2):
            c[f"c001_{i:05d}_s"] = {"type": "s", "en": t}
        with open(os.path.join(self.dirs[w], "work", "200_tagging.json"), "w", encoding="utf-8") as f:
            json.dump({"book_id": w, "meta": {"title": "T", "author": "A", "chapters": {"c001": "Chapter 1"}},
                       "content": c}, f)

    def lauf(self, w="w", **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return P.run(w, wer="test", **kw)

    def aus(self, w="w"):
        with open(os.path.join(self.dirs[w], "work", "210_profil.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_auto_und_checkpoint(self):
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(self.aus()["meta"]["profile"]["characters"]["Margaret"]["de"], "Margarete")
        self.assertIn('"de": "<rendering in de', self.aufrufe[0])
        self.lauf()
        self.assertEqual(len(self.aufrufe), 1)            # Checkpoint, 0 $
        self.lauf(neu=True)
        self.assertEqual(len(self.aufrufe), 2)

    def test_glossar_luecke_stopp(self):
        self.antworten = [profil(glossary={"door": {"fr": "porte"}})]
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")

    def test_bereich_fehlt_stopp(self):
        p = profil()
        del p["idioms"]
        self.antworten = [p]
        self.assertEqual(self.lauf().ergebnis["ergebnis"], "stopp")

    def test_gerettet_wiederholung(self):
        roh = json.dumps(profil())
        self.antworten = [roh[:-1], profil()]
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(g.metriken["llm_aufrufe"], 2)
        self.antworten = [roh[:-1]] * 2
        g = self.lauf(neu=True)
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")

    def test_figur_nicht_im_text_und_freigabe(self):
        self.antworten = [profil(characters={"Queen of Sheba": {"de": "Königin von Saba", "pronunciation": "x"}})]
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        S.entscheiden("w", "210", "frei", "CK", "Anspielung, ok")
        self.assertEqual(self.lauf().ergebnis["ergebnis"], "auto")
        g = self.lauf(figur_weg=["Queen of Sheba"])
        self.assertEqual(g.ergebnis["ergebnis"], "auto")
        self.assertNotIn("Queen of Sheba", self.aus()["meta"]["profile"]["characters"])

    def test_regler_fest(self):
        g = self.lauf(glossar=["door:de=Pforte"], figur=["Margaret:de=Grete,pronunciation=g"], voice_note="ruhig")
        p = self.aus()["meta"]["profile"]
        self.assertEqual(p["glossary"]["door"]["de"], "Pforte")
        self.assertEqual(p["characters"]["Margaret"], {"de": "Grete", "pronunciation": "g"})
        self.assertEqual(p["style"]["voice_note"], "ruhig")
        self.assertEqual(len(self.aufrufe), 1)
        self.assertEqual(g.ergebnis["ergebnis"], "auto")

    def test_kappung_mensch(self):
        g = self.lauf(grenze={"glossary": "1"})
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertIn("kappung", [p["name"] for p in g.fehler()])

    def test_hoerspiel_immer_mensch(self):
        self.werk("w", produkte=[{"sprache": "en", "inhalt": "hoerspiel", "stufe": "premium", "kanaele": ["taella"]},
                                 {"sprache": "en", "inhalt": "hoerbuch", "stufe": "premium", "kanaele": ["taella"]}])
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        S.entscheiden("w", "210", "frei", "CK", "Figuren ok")
        self.assertEqual(self.lauf().ergebnis["ergebnis"], "auto")

    def test_reihe(self):
        self.werk("w", reihe="r", teil=1, teile_gesamt=2)
        self.assertEqual(self.lauf().ergebnis["ergebnis"], "auto")
        rp = P.reihe_lesen("r")
        self.assertIn("Margaret", rp["characters"])
        # Teil 2: Namensvariante "Margaret Holloway" ~ bekannte Figur -> Mensch; geerbte Werte fest
        self.werk("w-2", saetze=SAETZE + ["Margaret Holloway smiled.", "Margaret Holloway left."], reihe="r", teil=2,
                  teile_gesamt=2)
        self.antworten = [profil(characters={"Margaret": {"de": "Maggie", "pronunciation": "m"},
                                             "Margaret Holloway": {"de": "M. H.", "pronunciation": "x"}})]
        g = self.lauf("w-2")
        self.assertEqual(g.ergebnis["ergebnis"], "mensch", g.bericht())
        self.assertEqual(self.aus("w-2")["meta"]["profile"]["characters"]["Margaret"]["de"], "Margarete")
        self.assertEqual(g.metriken["neue_figuren"], 1)
        # Erbe abschalten
        g = self.lauf("w-2", reihe_erbe=False)
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())

    def test_reihe_teil2_ohne_reihenprofil_stopp(self):
        self.werk("w-2", reihe="x", teil=2, teile_gesamt=2)
        self.assertEqual(self.lauf("w-2").ergebnis["ergebnis"], "stopp")

    def test_mock(self):
        config.RUN_MODE = "mock"
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        config.RUN_MODE = "live"
        os.remove(os.path.join(self.dirs["w"], "work", "status.json"))
        g = self.lauf()                                    # Mock-Checkpoint im Live-Lauf -> Stopp
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")

    def test_varianten(self):
        self.assertIn("Ashworth", P._varianten("Mr. Gideon Ashworth"))
        self.assertIn("Cheshire Cat", P._varianten("The Cheshire Cat"))
        self.assertEqual(P.figur_treffer("LADY MACBETH", "Lady Macbeth. lady macbeth"), 2)


if __name__ == "__main__":
    unittest.main()
