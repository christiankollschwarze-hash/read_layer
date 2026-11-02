"""Stage 330 Rueckuebersetzung.  py -3.11 -m unittest tests.test_s330"""
import contextlib, io, json, os, re, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import api_layer
from pipeline import status as S
from pipeline import s330_rueckuebersetzung as P

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
BESSER = "Die Tür stand offen, und der Wind war in jener Nacht sehr kalt."


class T330(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.tmp.name
        self.d = os.path.join(r, "w")
        os.makedirs(os.path.join(self.d, "work"))
        self.alt = (config.book_dir, config.work_dir, config.RUN_MODE, api_layer.call_model, config.BASE_DIR,
                    getattr(config, "FLAG_MAX_KLEIN", 10))
        config.book_dir = lambda b: self.d
        config.work_dir = lambda b: os.path.join(self.d, "work")
        config.BASE_DIR = r
        config.RUN_MODE = "live"
        self.aufrufe = []         # (rolle, art, ids)
        self.scores = {}          # Zieltext -> Score (Standard 95)
        self.ohne_score = set()   # ids ohne Bewertung (immer)

        def fake(task, prompt, **kw):
            teil = prompt.split("(as JSON")[-1]
            ids = re.findall(r'^\s+"(c\d+_\d+_\w+)":', teil, re.M)
            if task == "validator":
                self.aufrufe.append(("validator", "bewertung", ids))
                paare = dict(re.findall(r'^\s+"(c\d+_\d+_\w+)": \{ "original": .*?"back": (".*?") \}$', teil, re.M))
                out = {}
                for i in ids:
                    if i in self.ohne_score:
                        continue
                    back = json.loads(paare[i])
                    out[i] = self.scores.get(back.replace("BACK:", ""), 95)
                return json.dumps(out)
            if prompt.startswith("Translate each sentence from de into en"):
                self.aufrufe.append(("translator", "rueck", ids))
                texte = dict(re.findall(r'^\s+"(c\d+_\d+_\w+)": (".*")$', teil, re.M))
                return json.dumps({i: "BACK:" + json.loads(texte[i]) for i in ids}, ensure_ascii=False)
            self.aufrufe.append(("translator", "reparatur", ids))
            return json.dumps({i: BESSER for i in ids}, ensure_ascii=False)
        api_layer.call_model = fake
        self.werk()

    def tearDown(self):
        (config.book_dir, config.work_dir, config.RUN_MODE, api_layer.call_model, config.BASE_DIR,
         config.FLAG_MAX_KLEIN) = self.alt
        self.tmp.cleanup()

    def werk(self, mandant="somnio", de=None, gate320=True):
        b = {"book_slug": "w", "quelle": "gutenberg", "quellsprache": "en", "fassung": "modernisiert",
             "mandant": mandant, "produkte": [{"sprache": "de", "inhalt": "text", "kanaele": ["taella"]}],
             "rechte": {"art": "gemeinfrei", "bearbeitung": True, "versichert": {"wer": "t", "wann": "x"}}}
        with open(os.path.join(self.d, "book.json"), "w", encoding="utf-8") as f:
            json.dump(b, f)
        de = dict(DE, **(de or {}))
        prof = {"style": {"setting": "England"}, "characters": {"Margaret": {"de": "Margarete"}},
                "untranslated": {}, "glossary": {"door": {"de": "Tür"}}, "idioms": {}}
        data = {"book_id": "w", "meta": {"profile": prof},
                "content": {k: {"type": t, "en": q, "de": de[k]} for k, (t, q) in Q.items()}}
        with open(os.path.join(self.d, "work", "320_integritaet.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        if gate320:
            S.ergebnis("w", "320", "auto", wer="test")

    def lauf(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return P.run("w", wer="test", **kw)

    def aus(self):
        with open(os.path.join(self.d, "work", "330_rueckuebersetzung.json"), encoding="utf-8") as f:
            return json.load(f)

    def art(self, a):
        return [x for x in self.aufrufe if x[1] == a]

    def test_auto_checkpoint(self):
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(len(self.art("rueck")), 2)              # je Kapitel ein Batch
        qr = self.aus()["meta"]["quality_report"]
        self.assertEqual(qr["scored_count"], 6)
        self.assertEqual(qr["flagged"], [])
        n = len(self.aufrufe)
        self.lauf()
        self.assertEqual(len(self.aufrufe), n)                   # Checkpoint 0 $

    def test_geaenderter_satz_nur_dieser(self):
        self.lauf()
        n = len(self.aufrufe)
        self.werk(de={"c002_00002_s": "Sie klopfte dreimal an die Tür, doch niemand öffnete."})
        self.lauf()
        neu = self.aufrufe[n:]
        self.assertEqual([x[2] for x in neu if x[1] == "rueck"], [["c002_00002_s"]])

    def test_flag_repariert(self):
        self.scores = {DE["c001_00003_s"]: 40}
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(g.metriken["repariert"], 1)
        self.assertEqual(self.aus()["content"]["c001_00003_s"]["de"], BESSER)
        rep = self.art("reparatur")
        self.assertEqual(rep[0][2], ["c001_00003_s"])
        n = len(self.aufrufe)
        self.lauf()
        self.assertEqual(len(self.aufrufe), n)                   # Reparatur nur 1x

    def test_flag_bleibt_mensch_und_annehmen(self):
        config.FLAG_MAX_KLEIN = 0
        self.scores = {DE["c001_00003_s"]: 40, BESSER: 30}       # Reparatur schlechter -> alte bleibt
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch", g.bericht())
        self.assertEqual(self.aus()["content"]["c001_00003_s"]["de"], DE["c001_00003_s"])
        self.assertEqual(g.pruef["de"][0]["id"], "c001_00003_s")
        self.assertEqual(self.aus()["meta"]["quality_report"]["flagged"], [["c001_00003_s", "de", 40]])
        n = len(self.aufrufe)
        g = self.lauf(annehmen=["c001_00003_s"])
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(len(self.aufrufe), n)

    def test_kleines_werk_unter_grenze_auto(self):
        self.scores = {DE["c001_00003_s"]: 40, BESSER: 30}
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())   # 1 Flag <= 10
        self.assertEqual(g.metriken["flags_de"], 1)

    def test_manuell(self):
        g = self.lauf(satz_text=["c001_00002_s=Margarete schritt langsam zum alten Haus am Fluss."])
        self.assertEqual(self.aus()["content"]["c001_00002_s"]["de"], "Margarete schritt langsam zum alten Haus am Fluss.")
        self.assertEqual(g.ergebnis["ergebnis"], "auto")

    def test_satz_neu(self):
        self.lauf()
        g = self.lauf(saetze_neu=["c002_00002_s"])
        self.assertEqual(self.aus()["content"]["c002_00002_s"]["de"], BESSER)
        self.assertEqual(g.metriken["reparatur_versuche"], 1)

    def test_nicht_bewertbar_mensch(self):
        self.ohne_score = {"c001_00002_s"}
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch", g.bericht())
        self.assertEqual(g.metriken["nachbewertet"], 1)          # 1x automatisch neu
        self.assertEqual(self.aus()["meta"]["quality_report"]["not_scored"], [["c001_00002_s", "de"]])

    def test_gate_320_stopp(self):
        S.ergebnis("w", "320", "stopp", wer="test", gruende=["x"])
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual(self.aufrufe, [])

    def test_verlag_mensch(self):
        self.werk(mandant="verlag:x")
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch", g.bericht())

    def test_mock_stopp(self):
        self.werk(de={"c001_00002_s": "[MOCK] Margarete"})
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp", g.bericht())

    def test_umfang_ausreisser(self):
        with open(os.path.join(self.d, "work", "310_pruefung.json"), "w", encoding="utf-8") as f:
            json.dump({"de": [{"id": "c001_00003_s"}]}, f)
        g = self.lauf(umfang="ausreisser", stichprobe=0)
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual([x[2] for x in self.art("rueck")], [["c001_00003_s"]])
        self.assertEqual(self.aus()["meta"]["quality_report"]["je_sprache"]["de"]["ungeprueft"], 5)

    def test_trocken_bestand(self):
        self.lauf()
        os.remove(os.path.join(self.d, "work", "ckpt", "330", "c001__de.json"))
        n = len(self.aufrufe)
        mt = os.path.getmtime(os.path.join(self.d, "work", "330_rueckuebersetzung.json"))
        g = self.lauf(trocken=True)
        self.assertEqual(len(self.aufrufe), n)
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(os.path.getmtime(os.path.join(self.d, "work", "330_rueckuebersetzung.json")), mt)


if __name__ == "__main__":
    unittest.main()
