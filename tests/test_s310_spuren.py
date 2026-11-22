"""Stage 310 parallele Spuren + Fortschritt (22.11.2026).  py -3.11 -m unittest tests.test_s310_spuren"""
import contextlib, io, json, os, re, sys, tempfile, threading, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import api_layer, fortschritt
from pipeline import s310_uebersetzung as P

N_KAP, N_SATZ = 6, 30          # 6 Kapitel x 30 Saetze, Batch 10 -> 18 Batches


class T310Spuren(unittest.TestCase):
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
        self.lock = threading.Lock()
        self.aktiv = self.spitze = 0
        self.aufrufe = []
        self.abbruch_bei = None

        def fake(task, prompt, **kw):
            with self.lock:
                self.aktiv += 1
                self.spitze = max(self.spitze, self.aktiv)
                self.aufrufe.append(kw.get("modell"))
                n = len(self.aufrufe)
            try:
                if self.abbruch_bei and n >= self.abbruch_bei:
                    raise EnvironmentError("Abbruch (Test)")
                time.sleep(0.03)
                ids = re.findall(r'^\s+"(c\d+_\d+_\w+)":', prompt.split("Sentences (as JSON")[-1], re.M)
                return json.dumps({i: f"Das ist der Satz Nummer {i} auf Deutsch, recht lang." for i in ids})
            finally:
                with self.lock:
                    self.aktiv -= 1
        api_layer.call_model = fake
        b = {"book_slug": "w", "quelle": "gutenberg", "quellsprache": "en", "fassung": "modernisiert",
             "mandant": "somnio", "titel_original": "T", "uebersetzung_batch": 10,
             "produkte": [{"sprache": "de", "inhalt": "text", "kanaele": ["taella"]}],
             "rechte": {"art": "gemeinfrei", "bearbeitung": True, "versichert": {"wer": "t", "wann": "x"}}}
        with open(os.path.join(self.d, "book.json"), "w", encoding="utf-8") as f:
            json.dump(b, f)
        content = {f"c{k:03d}_{i:05d}_s": {"type": "s", "en": f"This is sentence number {i} in chapter {k}, quite long."}
                   for k in range(1, N_KAP + 1) for i in range(1, N_SATZ + 1)}
        data = {"book_id": "w", "meta": {"profile": {}, "pretranslation": {}}, "content": content}
        with open(os.path.join(self.d, "work", "300_voruebersetzung.json"), "w", encoding="utf-8") as f:
            json.dump(data, f)

    def tearDown(self):
        config.book_dir, config.work_dir, config.RUN_MODE, api_layer.call_model, config.BASE_DIR = self.alt
        self.tmp.cleanup()

    def lauf(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return P.run("w", wer="test", **kw)

    def ergebnis(self):
        with open(os.path.join(self.d, "work", "310_uebersetzung.json"), encoding="utf-8") as f:
            return {k: v.get("de") for k, v in json.load(f)["content"].items()}

    def test_gleiches_ergebnis_und_grenze(self):
        g1 = self.lauf(spuren=1)
        e1 = self.ergebnis()
        self.assertEqual(self.spitze, 1)
        import shutil
        shutil.rmtree(os.path.join(self.d, "work", "ckpt"))
        self.spitze = 0
        t0 = time.time()
        g4 = self.lauf(spuren=4)
        self.assertEqual(self.ergebnis(), e1)                      # gleiche IDs, gleiche Texte, gleiche Reihenfolge
        self.assertEqual(list(self.ergebnis()), list(e1))
        self.assertEqual(self.spitze, 4)
        self.assertEqual(g4.ergebnis, g1.ergebnis)
        m = {k: v for k, v in g4.metriken.items()}
        self.assertEqual(m["spuren"], 4)
        self.assertEqual(m["saetze_offen"], N_KAP * N_SATZ)
        self.assertEqual(m["llm"], 18)
        self.assertIn("laufzeit_s", m)
        with open(os.path.join(self.d, "book.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["uebersetzung_spuren"], 4)

    def test_modell_je_aufruf(self):
        alt = config.MODELS["translator"]
        self.lauf(spuren=3, modell="deepseek-v4-flash")
        self.assertEqual(set(self.aufrufe), {"deepseek-v4-flash"})
        self.assertEqual(config.MODELS["translator"], alt)          # nicht mehr global umgeschrieben

    def test_wiederaufnahme(self):
        self.abbruch_bei = 7
        with self.assertRaises(EnvironmentError):
            self.lauf(spuren=1)
        ck = os.listdir(os.path.join(self.d, "work", "ckpt", "310"))
        self.assertEqual(len(ck), 2)                                # 2 Kapitel (je 3 Batches) fertig gesichert
        f = fortschritt.lesen("w", "310")
        self.assertEqual(f["zustand"], "abbruch")
        self.abbruch_bei = None
        self.aufrufe.clear()
        self.lauf(spuren=4)
        self.assertEqual(len(self.aufrufe), 12)                     # nur die 4 offenen Kapitel
        self.assertEqual(len(self.ergebnis()), N_KAP * N_SATZ)

    def test_fortschritt_und_schaetzung(self):
        alt, fortschritt.MIN_DAUER = fortschritt.MIN_DAUER, 0
        self.addCleanup(setattr, fortschritt, "MIN_DAUER", alt)
        self.lauf(spuren=2)
        f = fortschritt.lesen("w", "310")
        self.assertEqual((f["zustand"], f["erledigt"], f["gesamt"], f["einheit"]), ("fertig", 180, 180, "Saetze"))
        self.assertIsNone(f["erwartet_s"])                          # erster Lauf: keine Schaetzung
        r = fortschritt.raten("310")
        self.assertEqual(len(r), 1)
        self.assertTrue(r[0]["s_je_1000z"] > 0)
        import shutil
        shutil.rmtree(os.path.join(self.d, "work", "ckpt"))
        self.lauf(spuren=2)
        f = fortschritt.lesen("w", "310")
        self.assertIsNotNone(f["erwartet_s"])
        self.assertTrue(f["erwartet_fertig"])

    def test_neulauf_ohne_llm(self):
        self.lauf(spuren=4)
        self.aufrufe.clear()
        g = self.lauf()
        self.assertEqual(self.aufrufe, [])
        self.assertEqual(g.metriken["saetze_offen"], 0)

    def test_trocken(self):
        self.lauf(spuren=4)
        self.aufrufe.clear()
        self.lauf(trocken=True)
        self.assertEqual(self.aufrufe, [])


if __name__ == "__main__":
    unittest.main()
