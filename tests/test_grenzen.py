"""Zentraler Begrenzer (pipeline/grenzen.py).  py -3.11 -m unittest tests.test_grenzen"""
import datetime as dt, os, subprocess, sys, tempfile, threading, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import grenzen as G
from pipeline import usage_log


class TG(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.alt = (config.GRENZEN_DIR, config.GRENZEN)
        config.GRENZEN_DIR = self.tmp.name
        config.GRENZEN = {"x": {"gleichzeitig": 3, "ttl_s": 60}, "t": {"rpm_ziel": 600, "rpd": 5},
                          "ohne": {}}

    def tearDown(self):
        config.GRENZEN_DIR, config.GRENZEN = self.alt
        self.tmp.cleanup()

    def test_platz_threads(self):
        aktiv, spitze, lock = [0], [0], threading.Lock()
        def arbeit():
            with G.platz("x"):
                with lock:
                    aktiv[0] += 1; spitze[0] = max(spitze[0], aktiv[0])
                time.sleep(0.05)
                with lock:
                    aktiv[0] -= 1
        th = [threading.Thread(target=arbeit) for _ in range(12)]
        [t.start() for t in th]; [t.join() for t in th]
        self.assertLessEqual(spitze[0], 3)
        self.assertEqual(spitze[0], 3)
        self.assertEqual(G.stand()["x"]["belegt"], 0)

    def test_platz_prozesse(self):
        # zweiter Prozess haelt alle Plaetze -> hier kein Platz bis zum Freigeben
        code = ("import sys,time;sys.path.insert(0,%r);from config import config;config.GRENZEN_DIR=%r;"
                "config.GRENZEN={'x':{'gleichzeitig':3,'ttl_s':60}};from pipeline import grenzen as G;"
                "import contextlib;s=contextlib.ExitStack();[s.enter_context(G.platz('x')) for _ in range(3)];"
                "print('voll',flush=True);time.sleep(1.5);s.close()") % (config.BASE_DIR, self.tmp.name)
        p = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
        self.assertEqual(p.stdout.readline().strip(), "voll")
        with self.assertRaises(TimeoutError):
            with G.platz("x", warte_max=0.5):
                pass
        t0 = time.time()
        with G.platz("x", warte_max=10):
            pass
        self.assertGreater(time.time() - t0, 0.3)
        p.wait(); p.stdout.close()

    def test_ablauf(self):
        config.GRENZEN["x"]["ttl_s"] = 0.2
        [G.platz("x").__enter__() for _ in range(3)]   # "abgestuerzt": nie freigegeben
        time.sleep(0.3)
        with G.platz("x", warte_max=2):
            pass

    def test_ohne_grenze(self):
        with G.platz("ohne"):
            pass
        G.takt("ohne")

    def test_takt_rpd(self):
        t0 = time.time()
        for _ in range(5):
            G.takt("t")
        self.assertGreater(time.time() - t0, 0.3)          # 600 RPM = 0,1 s Abstand
        self.assertEqual(G.rest_heute("t"), 0)
        with self.assertRaises(G.TagesgrenzeError) as e:
            G.takt("t")
        self.assertIsNotNone(e.exception.reset)

    def test_tageswechsel(self):
        G.takt("t")
        d = G._lesen("t"); d["tag"] = "2000-01-01"; d["heute"] = 99; G._schreiben("t", d)
        self.assertEqual(G.rest_heute("t"), 5)
        G.takt("t")
        self.assertEqual(G.rest_heute("t"), 4)

    def test_pazifik(self):
        u = lambda s: dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc)
        self.assertEqual(G.tag_pazifik(u("2026-11-22T07:59")), "2026-11-21")   # 08:59 MEZ
        self.assertEqual(G.tag_pazifik(u("2026-11-22T08:00")), "2026-11-22")   # 09:00 MEZ
        self.assertEqual(G.tag_pazifik(u("2026-07-01T06:59")), "2026-06-30")   # 08:59 MESZ
        self.assertEqual(G.naechster_reset(u("2026-11-22T12:00")), u("2026-11-23T08:00"))

    def test_429(self):
        vor = G.zaehler().get("x", 0)
        G.melde_429("x")
        self.assertEqual(G.zaehler()["x"], vor + 1)
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, "protokoll.jsonl")))
        self.assertTrue(3.7 <= G.pause_429(0) <= 6.3 and G.pause_429(10) <= 150)

    def test_env(self):
        os.environ["READLAYER_GRENZE_X"] = "7"
        try:
            self.assertEqual(G.wert("x", "gleichzeitig"), 7)
        finally:
            del os.environ["READLAYER_GRENZE_X"]

    def test_usage_kontext_je_thread(self):
        usage_log.set_context("haupt", "310", sprache="de")
        out = {}
        def neben():
            usage_log.set_context("neben", "310", sprache="fr")
            out["n"] = usage_log._kontext()[0:3:2]
        t = threading.Thread(target=neben); t.start(); t.join()
        self.assertEqual(out["n"][0], "neben")
        self.assertEqual(usage_log._kontext()[0], "haupt")
        self.assertEqual(usage_log._kontext()[2].get("sprache"), "de")

    def test_plaetze_und_modal_map(self):
        from pipeline import spuren
        config.GRENZEN["modal"] = {"gleichzeitig": 3, "ttl_s": 60}
        with G.plaetze("modal", 5) as m:
            self.assertEqual(m, 3)
            self.assertEqual(G.stand()["modal"]["belegt"], 3)
        self.assertEqual(G.stand()["modal"]["belegt"], 0)
        wellen = []
        class Fn:
            def map(self, welle, kwargs=None):
                wellen.append(len(welle))
                return [x * (kwargs or {}).get("f", 1) for x in welle]
        with G.platz("modal"):                                   # ein Platz belegt -> Wellen zu 2
            out = list(spuren.modal_map(Fn(), range(7), kwargs={"f": 10}))
        self.assertEqual(out, [x * 10 for x in range(7)])
        self.assertEqual(wellen, [2, 2, 2, 1])
        self.assertEqual(G.stand()["modal"]["belegt"], 0)

    def test_spuren_parallel(self):
        from pipeline import spuren
        aktiv, spitze, lock = [0], [0], threading.Lock()
        def fn(x):
            with lock:
                aktiv[0] += 1; spitze[0] = max(spitze[0], aktiv[0])
            time.sleep(0.02)
            with lock:
                aktiv[0] -= 1
            return x * 2
        erg, info = spuren.parallel(None, "999", list(range(20)), fn, 5, fortschritt_an=False, text=False)
        self.assertEqual(erg, [x * 2 for x in range(20)])
        self.assertEqual(spitze[0], 5)
        self.assertEqual(info["spuren"], 5)
        def kaputt(x):
            if x == 3:
                raise EnvironmentError("weg")
            return x
        with self.assertRaises(EnvironmentError):
            spuren.parallel(None, "999", list(range(10)), kaputt, 4, fortschritt_an=False, text=False)


if __name__ == "__main__":
    unittest.main()
