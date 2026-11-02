"""Stage 300 Vorübersetzung.  py -3.11 -m unittest tests.test_s300"""
import contextlib, io, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import api_layer
from pipeline import status as S
from pipeline import s300_voruebersetzung as P
from tools import sprache

EN = ("Margaret walked slowly to the old house by the river, and she was thinking of the long winter "
      "that had passed. The door was open, and the wind was cold. She knocked twice, but nobody came. ")
DE = ("Margarete ging langsam zu dem alten Haus am Fluss, und sie dachte an den langen Winter, der vergangen war. "
      "Die Tür war offen, und der Wind war kalt. Sie klopfte zweimal, aber niemand kam. ")
FR = ("Marguerite marchait lentement vers la vieille maison près de la rivière, et elle pensait à l'hiver qui "
      "était passé. La porte était ouverte et le vent était froid. Elle a frappé deux fois, mais personne n'est venu. ")


def profil():
    return {"style": {"tone": "quiet", "register": "literary", "setting": "England, 1890s"},
            "characters": {"Margaret": {"de": "Margarete", "fr": "Marguerite"}},
            "untranslated": {}, "glossary": {"door": {"de": "Tür", "fr": "porte"}}, "idioms": {}}


class T300(unittest.TestCase):
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
        self.antworten, self.aufrufe = [], []

        def fake(task, prompt, **kw):
            self.aufrufe.append(prompt)
            a = self.antworten.pop(0) if self.antworten else "AUTO"
            if isinstance(a, str):
                a = (a, None)
            if "info" in kw:
                kw["info"]["finish_reason"] = a[1] or "stop"
            # Laenge proportional zum Abschnitt (DE ~1,1x)
            if a[0] == "AUTO":
                teil = prompt.split("--- TEXT START ---\n", 1)[1].split("\n--- TEXT END", 1)[0]
                return (DE * 20)[:int(len(teil) * 1.1)]
            return a[0]
        api_layer.call_model = fake
        self.werk()

    def tearDown(self):
        config.book_dir, config.work_dir, config.RUN_MODE, api_layer.call_model, config.BASE_DIR = self.alt
        self.tmp.cleanup()

    def werk(self, ziele=("de",), kapitel=2, text=EN * 2, **kw):
        b = {"book_slug": "w", "quelle": "gutenberg", "quellsprache": "en", "fassung": "modernisiert",
             "mandant": "somnio", "produkte": [{"sprache": z, "inhalt": "text", "kanaele": ["taella"]} for z in ziele],
             "rechte": {"art": "gemeinfrei", "bearbeitung": True}}
        b.update(kw)
        with open(os.path.join(self.d, "book.json"), "w", encoding="utf-8") as f:
            json.dump(b, f)
        c = {}
        for k in range(1, kapitel + 1):
            c[f"c{k:03d}_00001_h"] = {"type": "h", "en": f"Chapter {k}"}
            c[f"c{k:03d}_00002_s"] = {"type": "s", "en": text}
        with open(os.path.join(self.d, "work", "210_profil.json"), "w", encoding="utf-8") as f:
            json.dump({"book_id": "w", "meta": {"profile": profil()}, "content": c}, f)

    def lauf(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return P.run("w", wer="test", **kw)

    def aus(self):
        with open(os.path.join(self.d, "work", "300_voruebersetzung.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_sprache_erkennen(self):
        self.assertEqual(sprache.erkennen(EN)[0], "en")
        self.assertEqual(sprache.erkennen(DE)[0], "de")
        self.assertEqual(sprache.erkennen(FR)[0], "fr")
        self.assertIsNone(sprache.erkennen("Peter Pan.")[0])

    def test_auto_und_checkpoint(self):
        self.antworten = ["AUTO", "AUTO"]
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertTrue(self.aus()["meta"]["pretranslation"]["c001"]["de"].startswith("Margarete"))
        self.assertIn("Margaret -> Margarete", self.aufrufe[0])
        self.assertIn("door -> Tür", self.aufrufe[0])
        self.assertIn("England, 1890s", self.aufrufe[0])
        self.lauf()
        self.assertEqual(len(self.aufrufe), 2)              # Checkpoints, 0 $
        self.antworten = ["AUTO"]
        self.lauf(kapitel=["2"])
        self.assertEqual(len(self.aufrufe), 3)

    def test_abgeschnitten_wiederholung_halbiert(self):
        self.antworten = [("AUTO", "length"), "AUTO", "AUTO", "AUTO"]
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(g.metriken["wiederholt"], 1)
        self.assertEqual(len(self.aufrufe), 4)              # c001: 1 + 2 halbe Abschnitte, c002: 1
        self.assertEqual(g.pruef["c001"]["de"]["versuch"], 2)
        self.assertEqual(g.pruef["c001"]["de"]["abschnitte"], 2)
        self.assertEqual(g.metriken["ohne_anker"], {"de": []})

    def test_laenge_rot_ohne_anker(self):
        kurz = DE[:120]
        self.antworten = [kurz, kurz, kurz, "AUTO"]
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(g.metriken["ohne_anker"], {"de": ["c001"]})
        self.assertEqual(self.aus()["meta"]["pretranslation"]["c001"]["de"], "")
        self.assertTrue(any("ohne Anker" in h for h in g.ergebnis["hinweise"]))
        n = len(self.aufrufe)
        self.lauf()                                          # Wiederholung schon verbraucht -> kein neuer Aufruf
        self.assertEqual(len(self.aufrufe), n)

    def test_glossar_rot(self):
        ohne = DE.replace("Margarete", "Greta").replace("Tür", "Pforte")
        self.antworten = [ohne * 2, ohne * 2, ohne, "AUTO"]
        g = self.lauf()
        self.assertEqual(g.pruef["c001"]["de"]["rot"], ["glossar"])
        self.assertIn("c001", g.metriken["ohne_anker"]["de"])

    def test_falsche_sprache_stopp(self):
        self.antworten = [EN * 2, "AUTO"]
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp", g.bericht())
        self.assertTrue(any("falsch" in x for x in g.ergebnis["gruende"]))

    def test_aufruf_gescheitert_stopp_dann_resume(self):
        def kaputt(task, prompt, **kw):
            raise RuntimeError("Netz weg")
        api_layer.call_model = kaputt
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertIn("fehlt", " ".join(g.ergebnis["gruende"]))

    def test_kapitelzahl_190(self):
        S.ergebnis("w", "190", "auto", metriken={"kapitel": 3}, wer="test")
        self.antworten = ["AUTO", "AUTO"]
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual(g.ergebnis["ruecksprung"], "200")

    def test_zwei_sprachen_und_aus(self):
        self.werk(ziele=("de", "fr"))
        self.antworten = ["AUTO", FR * 2, "AUTO", FR * 2]
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        pt = self.aus()["meta"]["pretranslation"]
        self.assertTrue(pt["c002"]["fr"].startswith("Marguerite"))
        g = self.lauf(aus=False)
        self.assertEqual(g.ergebnis["ergebnis"], "auto")
        self.assertEqual(self.aus()["meta"]["pretranslation"]["c001"]["de"], "")
        self.assertEqual(len(self.aufrufe), 4)

    def test_ziel_regler(self):
        txt = P.ziel_setzen("w", ["fr"], wer="CK")
        self.assertIn("['de'] -> ['fr']", txt)
        with open(os.path.join(self.d, "book.json"), encoding="utf-8") as f:
            b = json.load(f)
        self.assertEqual([p["sprache"] for p in b["produkte"]], ["fr"])
        with self.assertRaises(ValueError):
            P.ziel_setzen("w", ["en"])

    def test_uebernehmen_und_trocken(self):
        self.antworten = ["AUTO", "AUTO"]
        self.lauf()
        for f in os.listdir(os.path.join(self.d, "work", "ckpt", "300")):
            os.remove(os.path.join(self.d, "work", "ckpt", "300", f))
        g = self.lauf(uebernehmen=True)
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(len(self.aufrufe), 2)
        g = self.lauf(trocken=True)
        self.assertEqual(g.ergebnis["ergebnis"], "auto")
        self.assertEqual(len(self.aufrufe), 2)

    def test_mock_im_live_stopp(self):
        self.antworten = ["[PRETRANSLATION DE] (mock context translation of chapter)"] * 2
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")


if __name__ == "__main__":
    unittest.main()
