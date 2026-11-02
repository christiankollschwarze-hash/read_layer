"""Stage 340 Wort-Alignment (inkl. Verschiebung 345).  py -3.11 -m unittest tests.test_s340"""
import contextlib, io, json, os, re, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import api_layer
from pipeline import status as S
from pipeline import s340_wortalignment as P

Q = {"c001_00001_h": ("h", "Chapter IV", "Kapitel IV"),
     "c001_00002_s": ("s", "Margaret walked slowly to the old house.", "Margarete ging langsam zu dem alten Haus."),
     "c001_00003_s": ("s", "The door was open and the wind was cold.", "Die Tür war offen und der Wind war kalt."),
     "c002_00001_h": ("h", "Chapter V", "Kapitel V"),
     "c002_00002_s": ("s", "She knocked twice at the door.", "Sie klopfte zweimal an die Tür.")}
RICHTIG = {"c001_00001_h": ["Kapitel", "IV"],
           "c001_00002_s": ["Margarete", "ging", "langsam", "zu", "dem", "alten", "Haus"],
           "c001_00003_s": ["Die", "Tür", "war", "offen", "und", "der", "Wind", "war", "kalt"],
           "c002_00001_h": ["Kapitel", "V"],
           "c002_00002_s": ["Sie", "klopfte", "zweimal", "an", "die", "Tür"]}
VERSCHOBEN = ["Margarete", "langsam", "zu", "dem", "alten", "Haus", None]


def _spans(z, frags):
    out, cur = [], 0
    for i, f in enumerate(frags):
        if f:
            a = z.find(f, cur)
            a = z.find(f) if a < 0 else a
            out.append([i, [[a, a + len(f)]]])
            cur = a + len(f)
    return out


class T340(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.tmp.name
        self.d = os.path.join(r, "w")
        os.makedirs(os.path.join(self.d, "work"))
        self.alt = (config.book_dir, config.work_dir, config.RUN_MODE, api_layer.call_model, config.BASE_DIR,
                    P.PRUEFALIGNER)
        config.book_dir = lambda b: self.d
        config.work_dir = lambda b: os.path.join(self.d, "work")
        config.BASE_DIR = r
        config.RUN_MODE = "live"
        self.aufrufe = []          # (ids, mit_hinweis)
        self.antworten = {}        # id -> Liste von Antworten (je Aufruf eine, letzte bleibt)
        self.pa_aufrufe = []
        self.pa_fehler = False

        def fake(task, prompt, **kw):
            assert task == "aligner"
            bl = re.findall(r'^ID "(c\d+_\d+_\w+)"$', prompt, re.M)
            self.aufrufe.append((bl, "CHECK for ID" in prompt))
            out = {}
            for tid in bl:
                l = self.antworten.get(tid)
                frags = (l.pop(0) if len(l) > 1 else l[0]) if l else RICHTIG[tid]
                if frags == "FEHLT":
                    continue
                out[tid] = {str(i): f for i, f in enumerate(frags)}
            return json.dumps(out, ensure_ascii=False)
        api_layer.call_model = fake

        def pa(werk, lg, paare):
            self.pa_aufrufe.append([p["id"] for p in paare])
            if self.pa_fehler:
                raise RuntimeError("modal weg")
            return {p["id"]: _spans(p["z"], RICHTIG[p["id"]]) for p in paare}
        P.PRUEFALIGNER = pa
        self.werk()

    def tearDown(self):
        (config.book_dir, config.work_dir, config.RUN_MODE, api_layer.call_model, config.BASE_DIR,
         P.PRUEFALIGNER) = self.alt
        self.tmp.cleanup()

    def werk(self, de=None, gate330=True):
        b = {"book_slug": "w", "quelle": "gutenberg", "quellsprache": "en", "fassung": "modernisiert",
             "mandant": "somnio", "produkte": [{"sprache": "de", "inhalt": "text", "kanaele": ["taella"]}],
             "rechte": {"art": "gemeinfrei", "bearbeitung": True, "versichert": {"wer": "t", "wann": "x"}}}
        with open(os.path.join(self.d, "book.json"), "w", encoding="utf-8") as f:
            json.dump(b, f)
        de = de or {}
        data = {"book_id": "w", "meta": {},
                "content": {k: {"type": t, "en": q, "de": de.get(k, z)} for k, (t, q, z) in Q.items()}}
        with open(os.path.join(self.d, "work", "330_rueckuebersetzung.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        if gate330:
            S.ergebnis("w", "330", "auto", wer="test")

    def lauf(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return P.run("w", wer="test", **kw)

    def aus(self):
        with open(os.path.join(self.d, "work", "340_wortalignment.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_auto_checkpoint_felder(self):
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(len(self.aufrufe), 2)                       # je Kapitel ein Batch
        e = self.aus()["content"]["c001_00002_s"]
        self.assertEqual(e["align"], e["align_de"])                  # Altschnittstelle = erste Zielsprache
        self.assertEqual(e["align_de"][1], {"i": 1, "en": "walked", "en_span": [9, 15], "de": "ging",
                                            "de_span": [10, 14], "source": "direct"})
        self.assertIn("de", e["align_h"])
        self.assertEqual(g.metriken["je_sprache"]["de"]["inhalt_mit_anker"], 1.0)
        n, npa = len(self.aufrufe), len(self.pa_aufrufe)
        self.lauf()
        self.assertEqual((len(self.aufrufe), len(self.pa_aufrufe)), (n, npa))   # Checkpoint 0 $

    def test_geaenderter_satz_nur_dieser(self):
        self.lauf()
        n = len(self.aufrufe)
        neu = "Sie klopfte zweimal an die Tür."
        self.werk(de={"c002_00002_s": neu.replace("zweimal", "zweimal laut")})
        RICHTIG_ALT = RICHTIG["c002_00002_s"]
        self.lauf()
        self.assertEqual([x[0] for x in self.aufrufe[n:]], [["c002_00002_s"]])
        self.assertEqual(self.pa_aufrufe[-1], ["c002_00002_s"])
        self.assertEqual(RICHTIG["c002_00002_s"], RICHTIG_ALT)

    def test_unresolved_repariert(self):
        schlecht = ["Ihr", "pochte", "zweimal", "an", "die", "Tor"]            # 3 unaufgeloest (Rand)
        self.antworten = {"c002_00002_s": [schlecht, RICHTIG["c002_00002_s"]]}
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(g.metriken["unresolved_repariert"], 1)
        self.assertTrue(self.aufrufe[-1][1])                                 # Nachforderung mit Hinweis
        al = self.aus()["content"]["c002_00002_s"]["align_de"]
        self.assertEqual([w["source"] for w in al], ["direct"] * 6)

    def test_fehlt_stopp(self):
        self.antworten = {"c002_00002_s": ["FEHLT"]}
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp", g.bericht())
        self.assertEqual(g.metriken["nachgefordert"], 1)
        self.assertEqual(g.pruef["de"][0]["befund"], ["fehlt"])

    def test_verschoben_nachlauf_uebernommen(self):
        self.antworten = {"c001_00002_s": [VERSCHOBEN, RICHTIG["c001_00002_s"]]}
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual((g.metriken["verschoben_versucht"], g.metriken["verschoben_uebernommen"]), (1, 1))
        self.assertEqual(self.aus()["content"]["c001_00002_s"]["align_de"][1]["de"], "ging")

    def test_verschoben_bleibt_mensch(self):
        self.antworten = {"c001_00002_s": [VERSCHOBEN]}                     # Nachlauf liefert wieder dasselbe
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch", g.bericht())
        self.assertIn("verschoben", g.pruef["de"][0]["befund"])
        self.assertEqual(g.pruef["de"][0]["nachlauf"]["ergebnis"], "verworfen")
        self.assertIn("de", self.aus()["content"]["c001_00002_s"]["verschiebung"])
        n = len(self.aufrufe)
        self.lauf()
        self.assertEqual(len(self.aufrufe), n)                               # Nachlauf nur 1x

    def test_doppelt_nachlauf(self):
        dop = ["Die", "Tür", "war", "offen", "und", "Die", "Wind", "war", "kalt"]   # the..the -> gleiches "Die"
        self.antworten = {"c001_00003_s": [dop, RICHTIG["c001_00003_s"]]}
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(g.metriken["verschoben_uebernommen"], 1)
        self.assertEqual(self.aus()["content"]["c001_00003_s"]["align_de"][5]["de"], "der")

    def test_manueller_anker(self):
        self.antworten = {"c001_00002_s": [VERSCHOBEN]}
        self.lauf()
        anker = [f"c001_00002_s:{i}={f}" for i, f in enumerate(RICHTIG["c001_00002_s"])]
        g = self.lauf(anker_regler=anker)
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        al = self.aus()["content"]["c001_00002_s"]["align_de"]
        self.assertEqual((al[2]["de"], al[2]["source"]), ("langsam", "manuell"))
        with self.assertRaises(ValueError):
            self.lauf(anker_regler=["c001_00002_s:1=gibtsnicht"])

    def test_inhaltswort_ohne_anker_mensch(self):
        self.antworten = {"c002_00002_s": [["Sie", None, None, "an", "die", None]]}
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch", g.bericht())
        self.assertLess(g.metriken["inhalt_de"], 0.95)

    def test_pruefaligner_fehler_mensch_und_aus(self):
        self.pa_fehler = True
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch", g.bericht())
        g = self.lauf(pruefaligner="aus")
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.pa_fehler = False
        g = self.lauf()                                                      # holt Pruefung nach, ohne LLM
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())

    def test_gate_330_stopp(self):
        S.ergebnis("w", "330", "stopp", wer="test", gruende=["x"])
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual(self.aufrufe, [])

    def test_mock_stopp(self):
        self.werk(de={"c001_00002_s": "[MOCK] Margarete"})
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp", g.bericht())

    def test_uebernehmen_und_trocken(self):
        self.lauf()
        for f in os.listdir(os.path.join(self.d, "work", "ckpt", "340")):
            os.remove(os.path.join(self.d, "work", "ckpt", "340", f))
        n = len(self.aufrufe)
        mt = os.path.getmtime(os.path.join(self.d, "work", "340_wortalignment.json"))
        g = self.lauf(trocken=True)
        self.assertEqual(len(self.aufrufe), n)
        self.assertEqual(os.path.getmtime(os.path.join(self.d, "work", "340_wortalignment.json")), mt)
        self.werk(de={"c002_00002_s": "Sie klopfte zweimal laut an die Tür."})
        g = self.lauf(uebernehmen=True)
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual([x[0] for x in self.aufrufe[n:]], [["c002_00002_s"]])   # nur geaenderter Satz
        self.assertEqual(g.metriken["altbestand"], 4)

    def test_normieren(self):
        q, z = "Ashworth said Ashworth.", "Ashworth sagte es Ashworth."
        al = [{"i": 0, "en": "Ashworth", "en_span": [0, 8], "de": "Ashworth", "de_span": [0, 8], "source": "direct"},
              {"i": 1, "en": "said", "en_span": [9, 13], "de": "Sagte", "de_span": [9, 14], "source": "direct"},
              {"i": 2, "en": "Ashworth.", "en_span": [14, 23], "de": "Ashworth", "de_span": [0, 8],
               "source": "direct"}]
        self.assertEqual(P.doppelt(al, "de"), [2])
        P.normieren(al, q, z, "en", "de")
        self.assertEqual((al[1]["de"], al[2]["de_span"]), ("sagte", [18, 26]))
        self.assertEqual(P.doppelt(al, "de"), [])

    def test_ziel_spans_525_kompatibel(self):
        self.lauf()
        from pipeline import s525_wortbruecke as s525
        e = self.aus()["content"]["c001_00003_s"]
        config.SOURCE_LANGUAGE, config.TARGET_LANGUAGES = "en", ["de"]
        self.assertEqual(s525.ziel_spans(e["align"], e["de"]), P.ziel_spans(e["align_de"], e["de"], lg="de"))


if __name__ == "__main__":
    unittest.main()
