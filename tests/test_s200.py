"""Stage 200 Tagger.  py -3.11 -m unittest tests.test_s200"""
import contextlib, io, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import status as S
from pipeline import s200_tagging as T

K1 = "Mr. Holloway walked along the old road. He thought of the letter.\n\n\"Come home,\" she had written."
K2 = "The house stood empty. Approx. Three men waited by the gate."


def _sentences(text):
    """Saubere Rohsegmentierung (ein Knoten je Absatz, satzweise trennt nach)."""
    c = {}
    for i, a in enumerate(text.split("\n\n")):
        c[f"x{i:03d}p"] = {"type": "p", "en": ""}
        c[f"x{i:03d}s"] = {"type": "s", "en": a.strip()}
    return {"content": c}


class T200(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "werk")
        os.makedirs(os.path.join(self.dir, "work"))
        self.alt = (config.book_dir, config.work_dir, config.RUN_MODE, T._tag_robust, dict(config.MODELS))
        config.book_dir = lambda b: self.dir
        config.work_dir = lambda b: os.path.join(self.dir, "work")
        config.RUN_MODE = "live"
        self.aufrufe = []

        def fake(n, titel, text, tiefe=0):
            self.aufrufe.append(n)
            return _sentences(text)
        T._tag_robust = fake
        self.werk()

    def tearDown(self):
        config.book_dir, config.work_dir, config.RUN_MODE, T._tag_robust, m = self.alt
        config.MODELS.clear(); config.MODELS.update(m)
        self.tmp.cleanup()

    def werk(self, kap=(("Chapter 1", K1), ("Chapter 2", K2)), n190=None, **kw):
        b = {"book_slug": "w", "quelle": "gutenberg", "quellsprache": "en", "fassung": "modernisiert",
             "mandant": "somnio", "produkte": [{"sprache": "de", "inhalt": "text", "kanaele": ["taella"]}],
             "rechte": {"art": "gemeinfrei", "bearbeitung": True}}
        b.update(kw)
        with open(os.path.join(self.dir, "book.json"), "w", encoding="utf-8") as f:
            json.dump(b, f)
        z = ["###TITLE### Test", "###AUTHOR### Jane Doe"]
        for t, k in kap:
            z += [f"###CHAPTER### {t}", k]
        with open(os.path.join(self.dir, "raw_modernized.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(z) + "\n")
        S.ergebnis("w", "190", "auto", metriken={"kapitel": n190 or len(kap)}, wer="test")

    def lauf(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return T.run("w", wer="test", **kw)

    def aus(self):
        with open(os.path.join(self.dir, "work", "200_tagging.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_auto_und_checkpoint(self):
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(S.zustand("w", "200"), "frei")
        c = self.aus()["content"]
        self.assertEqual(c["c001_00001_h"], {"type": "h", "en": "Chapter 1"})
        texte = [e["en"] for e in c.values() if e["type"] in ("s", "dl")]
        self.assertIn("He thought of the letter.", texte)
        self.assertIn("\"Come home,\" she had written.", texte)
        self.assertEqual(self.aufrufe, [1, 2])
        g = self.lauf()
        self.assertEqual(self.aufrufe, [1, 2])           # zweiter Lauf aus Checkpoint, 0 $
        self.assertEqual(g.metriken["aus_checkpoint"], 2)
        self.lauf(kapitel=["2"])
        self.assertEqual(self.aufrufe, [1, 2, 2])

    def test_kapitel_geaendert_nur_dieses_neu(self):
        self.lauf()
        self.werk(kap=(("Chapter 1", K1), ("Chapter 2", K2 + " They left.")))
        self.lauf()
        self.assertEqual(self.aufrufe, [1, 2, 2])

    def test_kapitelzahl_190(self):
        self.werk(n190=3)
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual(g.ergebnis["ruecksprung"], "120")
        self.assertEqual(self.aufrufe, [])

    def test_treue_wiederholung_dann_auto(self):
        schlecht = [True]

        def fake(n, titel, text, tiefe=0):
            self.aufrufe.append(n)
            r = _sentences(text)
            if n == 1 and schlecht[0]:
                schlecht[0] = False
                r["content"].pop("x001s")              # Satz fehlt
            return r
        T._tag_robust = fake
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(self.aufrufe, [1, 1, 2])

    def test_treue_dauerhaft_mensch(self):
        def fake(n, titel, text, tiefe=0):
            self.aufrufe.append(n)
            r = _sentences(text)
            if n == 1:
                r["content"].pop("x001s")
            return r
        T._tag_robust = fake
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertEqual(self.aufrufe, [1, 1, 2])
        with open(os.path.join(self.dir, "work", "200_pruefung.json"), encoding="utf-8") as f:
            p = json.load(f)
        self.assertTrue(p["kapitel"][0]["abweichungen"])
        self.lauf()
        self.assertEqual(self.aufrufe, [1, 1, 2])        # kein dritter Versuch
        S.entscheiden("w", "200", "frei", "CK", "geprueft")
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto")  # Freigabe gilt bei unveraenderter Ausgabe
        self.assertEqual(S.zustand("w", "200"), "frei")

    def test_abkuerzung_je_werk(self):
        self.lauf()
        n = len(self.aus()["content"])
        self.lauf(abk=["Approx."])
        self.assertEqual(len(self.aus()["content"]), n - 1)
        with open(os.path.join(self.dir, "book.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["abkuerzungen"], ["approx"])
        self.assertEqual(self.aufrufe, [1, 2])           # nur Nachbearbeitung, kein LLM

    def test_korrekturen(self):
        self.lauf()
        c = self.aus()["content"]
        ids = [t for t, e in c.items() if t.startswith("c001") and e["type"] == "s"]
        g = self.lauf(zusammen=[ids[0]])
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())   # manuell = kein Mehrsatz
        c = self.aus()["content"]
        self.assertEqual(c[ids[0]]["en"], "Mr. Holloway walked along the old road. He thought of the letter.")
        self.assertNotIn("_m", c[ids[0]])
        g = self.lauf()                                    # Korrektur bleibt gespeichert
        self.assertEqual(self.aus()["content"][ids[0]]["en"], c[ids[0]]["en"])
        self.lauf(typ=[f"{ids[0]}=qt"])
        qt = ids[0][:-2] + "_qt"                           # Typ steht in der ID
        self.assertEqual(self.aus()["content"][qt]["type"], "qt")
        self.lauf(teilen=[f"{qt}@He thought"])
        self.assertEqual(self.aus()["content"][qt]["en"], "Mr. Holloway walked along the old road.")
        with self.assertRaises(ValueError):
            self.lauf(typ=[f"{qt}=xx"])
        with open(os.path.join(self.dir, "work", "200_korrekturen.json"), encoding="utf-8") as f:
            self.assertEqual([k["op"] for k in json.load(f)], ["zusammen", "typ", "teilen"])
        # Kapitel geaendert -> Korrekturen verworfen (Hinweis)
        self.werk(kap=(("Chapter 1", K1 + " Rain fell."), ("Chapter 2", K2)))
        g = self.lauf()
        self.assertEqual(len(g.pruef["korrekturen_verworfen"]), 3)

    def test_leer_und_unbekannt_stopp(self):
        def fake(n, titel, text, tiefe=0):
            r = _sentences(text)
            r["content"]["zz1"] = {"type": "s", "en": " "}
            r["content"]["zz2"] = {"type": "bogus", "en": "x"}
            return r
        T._tag_robust = fake
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual({p["name"] for p in g.fehler()} >= {"leere_knoten", "unbekannte_typen"}, True)

    def test_uebernehmen_trocken(self):
        self.lauf()
        os.remove(os.path.join(self.dir, "work", "ckpt", "200", "c001__en.json"))
        os.remove(os.path.join(self.dir, "work", "ckpt", "200", "c002__en.json"))
        os.remove(os.path.join(self.dir, "work", "status.json"))
        self.werk()
        g = self.lauf(uebernehmen=True, trocken=True)
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(g.metriken["aus_bestand"], 2)
        self.assertEqual(S.zustand("w", "200"), "offen")
        self.assertEqual(self.aufrufe, [1, 2])

    def test_mock_lauf(self):
        config.RUN_MODE = "mock"
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(g.metriken["modus"], "mock")
        self.assertEqual(self.aufrufe, [])

    def test_geteiltes_werk(self):
        self.werk(geteilt_in=["w-1", "w-2"])
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual(g.ergebnis["ruecksprung"], "195")

    def test_trennstelle(self):
        self.assertEqual(T.trennstelle("One. Two three four five.", "Two three four five."), "Two three")
        self.assertEqual(T.trennstelle("He ran. He ran home.", "He ran home."), "He ran home.")
        self.assertIsNone(T.trennstelle("abc", "x"))

    def test_mehrere_korrekturen_ein_lauf(self):
        self.lauf()
        ids = [t for t, e in self.aus()["content"].items() if t.startswith("c001") and e["type"] in ("s", "dl")]
        g = self.lauf(typ=[f"{ids[0]}=qt"], zusammen=[ids[1]])     # vorn Typ, dahinter zusammen: beide gueltig
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        c = self.aus()["content"]
        self.assertEqual(c[ids[0][:-2] + "_qt"]["type"], "qt")
        self.assertTrue(c[ids[1]]["en"].startswith("He thought of the letter. "))
        with self.assertRaises(ValueError):
            self.lauf(typ=[f"{ids[1]}=qt"], zusammen=[ids[1]])

    def test_mehrsatz_vorschlag_und_monitor(self):
        def fake(n, titel, text, tiefe=0):
            return {"content": {"a": {"type": "vs", "en": text.split("\n\n")[0]}, "b": {"type": "s", "en": "x"}}}
        T._tag_robust = fake
        self.werk(kap=(("Chapter 1", "One small line. Two small lines."),))
        self.lauf()
        vs = next(t for t, e in self.aus()["content"].items() if e["type"] == "vs")
        g = self.lauf(typ=[f"{vs}=s"])                    # Typ s -> zwei Saetze in einem Knoten
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        s = vs[:-3] + "_s"
        self.assertEqual(g.pruef["mehrsatz"], [{"id": s, "text": "One small line. Two small lines.", "saetze": 2,
                                                "vorschlag": "Two small"}])
        from cockpit import werk_api as W
        d = W._m200_daten("w")
        self.assertEqual((len(d["kapitel"]), d["mehrsatz"][0]["id"], d["modell"]), (1, s, config.MODELS["tagger"]))
        self.assertGreater(d["kapitel"][0]["kosten"], 0)
        t = W._m200_teil("w", {"k": ["1"]})
        self.assertEqual(t["zusaetzlich"], 1)                       # "x" nur in den Knoten
        self.assertTrue(any(n["mehrsatz"] and n["vorschlag"] == "Two small" for n in t["knoten"]))
        self.assertTrue(any(g_["aus"] for n in t["knoten"] for g_ in n["seg"]))
        a = W._m200_argv("w", {"teilen": [[s, "Two small"]], "abk": ["Mr."], "abk_weg": ["approx"], "lang": 300,
                                "kapitel": [1], "trocken": True}, "CK")
        self.assertEqual(a[6:], ["--kapitel=1", f"--teilen={s}@Two small", "--abk=Mr", "--abk-weg=approx",
                                 "--lang=300", "--trocken"])
        for e in ({"kapitel": [2]}, {"typ": {s: "h"}}, {"teilen": [[s, "x"]], "zusammen": [s]}, {"modell": "foo"}):
            with self.assertRaises(ValueError):
                W._m200_argv("w", e, "CK")
        g = self.lauf(teilen=[f"{s}@Two small"])
        self.assertEqual(g.pruef["mehrsatz"], [])                   # Rest-Mensch nur Treue (Zusatzknoten "x")

    def test_satzweise_werksprache(self):
        content = {"a": {"type": "s", "de": "Er kam. Sie ging."}}
        self.assertEqual(len(T._satzweise(content, None, "de")), 2)

    def test_treue_funktion(self):
        q, _ = T.treue("A b c d.", {"c001_00002_s": {"type": "s", "en": "A b c d."}}, "en")
        self.assertEqual(q, 1.0)
        q, bsp = T.treue("A b c d.", {"c001_00002_s": {"type": "s", "en": "A b d."}}, "en")
        self.assertAlmostEqual(q, 0.75)
        self.assertTrue(bsp)


if __name__ == "__main__":
    unittest.main()
