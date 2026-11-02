"""Stage 530 Audio-Pruefungen.  py -3.11 -m unittest tests.test_s530"""
import contextlib, io, json, os, sys, tempfile, unittest, wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import manifest
from pipeline import status as S
from pipeline import s530_audio_pruefung as P

Q = {"c001_00001_h": ("h", "Chapter One", "Kapitel eins"),
     "c001_00002_s": ("s", "Alice sat by the river bank.", "Alice saß am Ufer des Flusses."),
     "c001_00003_dl": ("dl", "\"Who are you?\" said the Hatter.", "„Wer bist du?“, sagte der Hutmacher."),
     "c002_00001_h": ("h", "Chapter Two", "Kapitel zwei"),
     "c002_00002_dl": ("dl", "\"Hm,\" the cat said.", "„Hm“, sagte die Katze."),
     "c002_00003_s": ("s", "The end came soon.", "Das Ende kam bald.")}
FIG = ("c001_00003_dl", "c002_00002_dl")
PROD = [{"sprache": "de", "inhalt": "hoerbuch", "stufe": "premium", "kanaele": ["taella"]},
        {"sprache": "de", "inhalt": "hoerspiel", "stufe": "premium", "kanaele": ["taella"]}]
VOR, NACH = 0.3, 0.5          # Stille in den Roh-WAVs


def wav(p, sprach_s=1.2, amp=0.1, seed=1):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    r = np.random.default_rng(seed)
    x = np.concatenate([np.zeros(int(24000 * VOR)), r.normal(0, amp, int(24000 * sprach_s)),
                        np.zeros(int(24000 * NACH))])
    with wave.open(p, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def dauer(p):
    with wave.open(p) as w:
        return w.getnframes() / w.getframerate()


class T530(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.tmp.name
        self.d = os.path.join(r, "a", "books", "w")
        self.wd = os.path.join(self.d, "work")
        os.makedirs(self.wd)
        self.alt = (config.book_dir, config.work_dir, config.RUN_MODE, config.BASE_DIR, P.fa_zeiten, P.sprache,
                    P.werkzeuge_pruefen, P.nachvertonen)
        config.book_dir = lambda b: self.d
        config.work_dir = lambda b: self.wd
        config.BASE_DIR = r
        config.RUN_MODE = "live"
        self.fa_jobs, self.wh_jobs, self.nv, self.fe = [], [], [], []
        self.kippt, self.fa_leer, self.reparieren = {}, set(), False
        P.fa_zeiten = self.fa
        P.sprache = self.whisper
        P.werkzeuge_pruefen = lambda *a: list(self.fe)
        P.nachvertonen = self.nachvertonen
        self.werk()

    def tearDown(self):
        (config.book_dir, config.work_dir, config.RUN_MODE, config.BASE_DIR, P.fa_zeiten, P.sprache,
         P.werkzeuge_pruefen, P.nachvertonen) = self.alt
        self.tmp.cleanup()

    # ---------------------------------------------------------- Attrappen
    def fa(self, jobs, werk, lg, art):
        out = {}
        for key, p, w in jobs:
            self.fa_jobs.append(key)
            d = dauer(p) - VOR - NACH
            n = len(w) or 1
            out[key] = [None] * len(w) if key in self.fa_leer else \
                [(VOR + i * d / n, VOR + (i + 1) * d / n) for i in range(len(w))]
        return out

    def whisper(self, jobs, werk, lg, art):
        out = {}
        for key, p in jobs:
            self.wh_jobs.append(key)
            if self.kippt.get(key):
                out[key] = {"top": "en", "p": 0.05, "text": Q[key][1], "dauer": 2.0}
            else:
                out[key] = {"top": lg, "p": 0.98, "text": Q[key][2], "dauer": 2.0}
        return out

    def nachvertonen(self, werk, spur, lg, ids, wer):
        self.nv.append((spur, sorted(ids)))
        name = "500_vertonung" if spur == "hoerbuch" else "510_overlay"
        m = manifest.Manifest("w", name, stage=P.QUELLE[spur])
        for t in ids:
            p = self.a(t) if spur == "hoerbuch" else self.h(t)
            wav(p, 1.3, seed=len(self.nv) + 7)
            m.setzen(f"de/{t}", "n", datei=p, q="neu")
            if self.reparieren:
                self.kippt.pop(t, None)
        m.speichern()
        return "auto"

    def a(self, t):
        return os.path.join(self.d, "fassungen", "de", "audio", f"{t}.wav")

    def h(self, t):
        return os.path.join(self.d, "fassungen", "de", "hoerspiel", f"{t}.wav")

    def f(self, t, spur="hoerbuch"):
        return os.path.join(self.d, "fassungen", "de", P.FINAL[spur], f"{t}.wav")

    def werk(self, produkte=None, engine="gemini", adapter=None, gates=("500", "510"), ohne=(), mock=()):
        b = {"book_slug": "w", "quelle": "gutenberg", "quellsprache": "en", "fassung": "modernisiert",
             "mandant": "somnio", "produkte": produkte or PROD,
             "rechte": {"art": "gemeinfrei", "bearbeitung": True, "versichert": {"wer": "t", "wann": "x"}}}
        self.schreib(os.path.join(self.d, "book.json"), b)
        content = {k: {"type": t, "en": q, "de": z} for k, (t, q, z) in Q.items()}
        sp = {k: {"de": z} for k, (t, q, z) in Q.items()}
        self.schreib(os.path.join(self.wd, "400_regie.json"),
                     {"book_id": "w", "meta": {}, "content": content, "ansagen": {},
                      "production": {"sprechtext": sp, "direction": {}, "pause_after_ms": {}}})
        for n in ("500_vertonung.json", "510_overlay.json"):
            if os.path.exists(os.path.join(self.wd, n)):
                os.remove(os.path.join(self.wd, n))
        m = manifest.Manifest("w", "500_vertonung", stage="500")
        for i, k in enumerate(Q):
            if k in ohne:
                continue
            wav(self.a(k), 0.8 + 0.1 * i, seed=i)
            m.setzen(f"de/{k}", "h", datei=self.a(k), engine=engine, q="mock" if k in mock else "neu")
        m.meta["je_sprache"] = {"de": {"engine": engine, "adapter": adapter}}
        m.speichern()
        m = manifest.Manifest("w", "510_overlay", stage="510")
        for i, k in enumerate(FIG):
            wav(self.h(k), 1.0 + 0.1 * i, seed=20 + i)
            m.setzen(f"de/{k}", "h", datei=self.h(k), q="neu")
        m.speichern()
        for g in gates:
            S.ergebnis("w", g, "auto", wer="test")

    def schreib(self, p, o):
        with open(p, "w", encoding="utf-8") as f:
            json.dump(o, f, ensure_ascii=False)

    def man(self):
        with open(os.path.join(self.wd, "530_pruefung_de.json"), encoding="utf-8") as f:
            return json.load(f)

    def lauf(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return P.run("w", wer="test", **kw)

    # ---------------------------------------------------------- Hilfen
    def test_cer_urteil_namen(self):
        rg = P.REGLER_STD
        self.assertEqual(P.cer("Alice saß.", "alice sass"), 0.0)
        self.assertGreater(P.cer("Alice saß am Ufer.", "Alice sat by the bank."), 0.35)
        self.assertEqual(P.urteil({"top": "de", "p": 0.9, "text": "Das Ende kam bald", "dauer": 2}, "Das Ende kam bald.",
                                  "de", rg)[0], "ok")
        self.assertEqual(P.urteil({"top": "en", "p": 0.1, "text": "x", "dauer": 2}, "Das Ende kam bald.", "de", rg)[0],
                         "gekippt")
        self.assertEqual(P.urteil({"top": "en", "p": 0.1, "text": "ja", "dauer": 0.5}, "Ja.", "de", rg)[0], "verdacht")
        self.assertEqual(P.urteil({"fehler": "x"}, "Ja.", "de", rg)[0], "verdacht")
        self.assertEqual(P.namen(["Er sah Holmes.", "Dann kam Holmes.", "Holmes? Ja, Holmes."]), {"Holmes": 3})

    def test_schneiden_raender(self):
        x = np.ones(24000 * 3, np.float32)
        y, r = P.schneiden(x, (1.0, 2.0), 0.05, 0.12, 1.0)
        self.assertAlmostEqual(len(y) / 24000, 1.17, places=2)
        self.assertEqual(r, (0.05, 0.12))
        y, r = P.schneiden(x, (1.0, 2.0), 0.05, 0.12, 0.9)
        self.assertEqual(r, (0.05, 0.12))                                    # Raender nach Tempo
        self.assertEqual(P.schneiden(x, None, 0.05, 0.12, 1.0), (x, None))

    def test_begrenzen(self):
        y = np.random.default_rng(3).normal(0, 0.05, 24000).astype(np.float32)
        y[12000] = 0.99
        z = P.begrenzen(y, -2.0)
        self.assertLessEqual(np.abs(z).max(), 10 ** (-2 / 20) + 1e-4)
        self.assertAlmostEqual(float(np.abs(z[:6000]).mean()), float(np.abs(y[:6000]).mean()), places=4)
        self.assertIs(P.begrenzen(y * 0.1, -2.0).dtype, np.dtype(np.float32))

    # ---------------------------------------------------------- Lauf
    def test_auto_beide_spuren(self):
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        for t in Q:
            self.assertTrue(os.path.exists(self.f(t)))
            self.assertLess(dauer(self.f(t)), dauer(self.a(t)))                 # Raender geschnitten
        self.assertEqual(sorted(os.listdir(os.path.dirname(self.f(FIG[0], "hoerspiel")))),
                         sorted(f"{t}.wav" for t in FIG))
        m = self.man()
        e = m["eintraege"]["hoerbuch/c001_00002_s"]
        self.assertEqual((e["rand"], e["tempo"]), ([0.05, 0.12], 1.0))
        for k, v in m["meta"]["kapitel"].items():
            self.assertLessEqual(abs(v["lufs"] + 18), 1.0, (k, v))
            self.assertLessEqual(v["peak"], -1.0)
        self.assertEqual(set(m["meta"]["kapitel"]), {"hoerbuch/c001", "hoerbuch/c002", "hoerspiel/c001",
                                                    "hoerspiel/c002"})
        self.assertEqual(len(self.wh_jobs), len(Q) + len(FIG))
        self.assertTrue(os.path.exists(self.a("c001_00002_s")))                  # Rohfassung bleibt

    def test_wiederlauf_nichts_neu_dann_geaenderte_wav(self):
        self.lauf()
        n_fa, n_wh = len(self.fa_jobs), len(self.wh_jobs)
        mt = os.path.getmtime(self.f("c002_00003_s"))
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual((len(self.fa_jobs), len(self.wh_jobs)), (n_fa, n_wh))
        self.assertEqual(os.path.getmtime(self.f("c002_00003_s")), mt)
        wav(self.a("c001_00002_s"), 2.0, seed=99)                                  # neue WAV 500
        m = manifest.Manifest("w", "500_vertonung", stage="500")
        m.setzen("de/c001_00002_s", "h2", datei=self.a("c001_00002_s"), engine="gemini", q="neu")
        m.speichern()
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(self.fa_jobs[n_fa:], ["c001_00002_s"])
        self.assertEqual(os.path.getmtime(self.f("c002_00003_s")), mt)            # anderes Kapitel unberuehrt
        self.assertEqual(self.wh_jobs[n_wh:], ["c001_00001_h", "c001_00002_s", "c001_00003_dl"])  # Kapitel c001 neu

    def test_tempo_chatterbox_einmal(self):
        self.werk(produkte=[PROD[0]], engine="chatterbox")
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        e = self.man()["eintraege"]["hoerbuch/c001_00002_s"]
        self.assertEqual(e["tempo"], 0.91)
        soll = 0.9 / 0.91 + 0.17                                                   # Sprachanteil + Raender
        self.assertAlmostEqual(dauer(self.f("c001_00002_s")), soll, delta=0.05)
        d1 = dauer(self.f("c001_00002_s"))
        self.lauf()
        self.assertEqual(dauer(self.f("c001_00002_s")), d1)                        # nicht doppelt
        g = self.lauf(regler={"tempo": {"de": 1.0}})
        self.assertAlmostEqual(dauer(self.f("c001_00002_s")), 1.07, delta=0.02)
        self.assertNotIn("hoerspiel/c001", self.man()["meta"]["kapitel"])

    def test_gekippt_nachvertonen_repariert(self):
        self.kippt = {"c002_00003_s": True}
        self.reparieren = True
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(self.nv, [("hoerbuch", ["c002_00003_s"])])
        self.assertEqual(self.man()["meta"]["nachvertont"], {"hoerbuch/c002_00003_s": 1})

    def test_gekippt_bleibt_mensch(self):
        self.kippt = {"c002_00003_s": True}
        g = self.lauf()
        self.assertEqual((g.ergebnis["ergebnis"], g.ergebnis["ruecksprung"]), ("mensch", "500"), g.bericht())
        self.assertEqual(len(self.nv), 2)
        with open(P.hoerliste_pfad("w"), encoding="utf-8") as f:
            h = json.load(f)
        self.assertEqual([x["id"] for x in h["de"]["hoerbuch"]["gekippt"]], ["c002_00003_s"])
        self.lauf()
        self.assertEqual(len(self.nv), 2)                                         # Versuche verbraucht

    def test_gekippt_hoerbuch_zieht_hoerspiel_nach(self):
        self.kippt = {"c002_00002_dl": True}
        self.reparieren = True
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(self.nv, [("hoerbuch", ["c002_00002_dl"]), ("hoerspiel", ["c002_00002_dl"])])

    def test_verdacht_mensch_und_freigabe_gilt(self):
        self.kippt = {"c001_00001_h": True}                                        # kurz -> nur Verdacht
        g = self.lauf(regler={"kurz_s": 5.0})
        self.assertEqual(g.ergebnis["ergebnis"], "mensch", g.bericht())
        self.assertEqual(self.nv, [])
        S.entscheiden("w", "530", "frei", wer="smoke-fixture", grund="Test")
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertTrue(any("Mensch-Freigabe gilt" in h for h in g.ergebnis["hinweise"]))

    def test_ohne_fa_mensch(self):
        self.fa_leer = {"c001_00002_s"}
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch", g.bericht())
        self.assertIsNone(self.man()["eintraege"]["hoerbuch/c001_00002_s"]["rand"])

    def test_stopps(self):
        S.ergebnis("w", "510", "stopp", wer="test")
        g = self.lauf()
        self.assertEqual((g.ergebnis["ergebnis"], g.ergebnis["ruecksprung"]), ("stopp", "510"))
        self.werk(ohne=("c002_00003_s",))
        g = self.lauf()
        self.assertEqual((g.ergebnis["ergebnis"], g.ergebnis["ruecksprung"]), ("stopp", "500"), g.bericht())
        self.werk(mock=("c002_00003_s",))
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp", g.bericht())

    def test_werkzeug_fehlt_stopp_ohne_ausgabe(self):
        self.fe = ["FA (modal): ModuleNotFoundError"]
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertFalse(os.path.exists(os.path.join(self.d, "fassungen", "de", "audio_final")))

    def test_trocken_schreibt_nichts(self):
        self.fe = ["Whisper (modal): fehlt"]
        g = self.lauf(trocken=True)
        self.assertFalse(os.path.exists(os.path.join(self.d, "fassungen", "de", "audio_final")))
        self.assertFalse(os.path.exists(os.path.join(self.wd, "530_pruefung_de.json")))
        self.assertTrue(any("Werkzeug fehlt" in h for h in g.ergebnis["hinweise"]))
        self.assertEqual(g.metriken["je_spur"]["de/hoerbuch"]["fa_offen"], len(Q))

    def test_sprache_aus_und_regler_ungueltig(self):
        g = self.lauf(regler={"sprache": "aus"})
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(self.wh_jobs, [])
        self.assertTrue(any("Sprachpruefung aus" in h for h in g.ergebnis["hinweise"]))
        g = self.lauf(regler={"nach": 0.3})
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")

    def test_verwaister_hoerspielsatz_geloescht(self):
        self.lauf()
        m = manifest.Manifest("w", "510_overlay", stage="510")
        m.entfernen("de/c002_00002_dl")
        m.speichern()
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertFalse(os.path.exists(self.f("c002_00002_dl", "hoerspiel")))
        self.assertNotIn("hoerspiel/c002_00002_dl", self.man()["eintraege"])

    def test_cli(self):
        with contextlib.redirect_stdout(io.StringIO()):
            rc = P.main(["w", "--wer", "test", "--trocken", "--spur", "hoerbuch"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
