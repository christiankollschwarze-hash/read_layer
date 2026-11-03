"""Phase 3, P3-1: Tests fuer cockpit/werk_api.py (Einzeltitel-Ansicht).
  py -3.11 -m unittest tests.test_cockpit_werk
"""
import json, os, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import bestellung, status as S
from cockpit import werk_api as A

PROD = [{"sprache": "en", "inhalt": "text", "kanaele": ["taella"]},
        {"sprache": "de", "inhalt": "text", "kanaele": ["taella"]}]


def B():
    return bestellung.Bestellung(dict(quellsprache="en", produkte=PROD, fassung="modernisiert", herkunft="privat_upload",
                                      mandant="user:anna", besitzer="anna",
                                      rechte={"art": "gemeinfrei", "bearbeitung": True}))


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._wd, self._lesen = config.work_dir, bestellung.lesen
        config.work_dir = lambda b: self.tmp.name
        bestellung.lesen = lambda w: B()
        reg = os.path.join(self.tmp.name, "rollen.json")
        with open(reg, "w", encoding="utf-8") as f:
            json.dump({"standard": "CK", "nutzer": {"CK": {"rolle": "admin"}, "anna": {"rolle": "kurator"},
                                                     "bob": {"rolle": "kurator"}}}, f)
        self._env = os.environ.get("READLAYER_ROLLEN")
        os.environ["READLAYER_ROLLEN"] = reg
        self.w = "u-test"

    def tearDown(self):
        config.work_dir, bestellung.lesen = self._wd, self._lesen
        if self._env is None:
            os.environ.pop("READLAYER_ROLLEN", None)
        else:
            os.environ["READLAYER_ROLLEN"] = self._env
        self.tmp.cleanup()

    def _stand(self):
        from pipeline import kette
        S.bedarf_setzen(self.w, kette.bedarf(B()))
        for s in ("080", "090", "095", "150", "115", "120", "190", "195", "200", "210", "300"):
            S.ergebnis(self.w, s, "auto")
        S.ergebnis(self.w, "310", "auto", scope="c001/de")
        S.ergebnis(self.w, "310", "mensch", gruende=["Treue 98 %"], ruecksprung="300", scope="c002/de",
                   metriken={"treue": 0.98, "liste": [1, 2], "klein": {"a": 1}, "gross": {"a": [1]}})

    def test_lesen_schreibt_nichts(self):
        d = A.werk(self.w)                                   # ohne status.json: nichts anlegen
        self.assertFalse(os.path.exists(S.pfad(self.w)))
        self.assertFalse(d["status_vorhanden"])
        self._stand()
        lies = lambda: open(S.pfad(self.w), "rb").read()
        roh = lies()
        A.werk(self.w)
        self.assertEqual(roh, lies())

    def test_stages_befunde_naechster(self):
        self._stand()
        d = A.werk(self.w)
        st = {s["stage"]: s for s in d["stages"]}
        self.assertEqual([s["stage"] for s in d["stages"]], S.STAGES)
        self.assertEqual(st["310"]["zustand"], "mensch")
        self.assertEqual(st["310"]["befunde"], ["c002/de: Treue 98 %"])
        self.assertEqual(st["310"]["ruecksprung_ziele"], [{"ziel": "300", "scope": "c002/de"}])
        self.assertEqual(st["310"]["teile"]["c002/de"]["metriken"], {"treue": 0.98, "liste": "1, 2", "klein": "a=1", "gross": "{a}"})
        self.assertFalse(st["500"]["bestellt"])
        self.assertEqual(st["500"]["zustand"], "entfaellt")
        self.assertEqual(st["310"]["vorgaenger"], ["300"])
        self.assertEqual(d["naechster"], {"stage": "310", "zustand": "mensch", "ruecksprung": "300", "grund": "mensch"})
        self.assertTrue(d["rechte"]["override"]["ok"])
        self.assertIn("095", [s["stage"] for s in d["stages"] if s["regler"]])

    def test_aktionen(self):
        self._stand()
        self.assertFalse(A.aktion(self.w, "entscheiden", "310", "CK", "", scope="c002/de", nach="frei")["ok"])
        r = A.aktion(self.w, "entscheiden", "310", "CK", "gegengehoert", scope="c002/de", nach="frei")
        self.assertEqual(r, {"ok": True, "zustand": "frei"})
        self.assertEqual(S.zustand(self.w, "310"), "frei")
        p = S.laden(self.w)["protokoll"][-1]
        self.assertEqual((p["aktion"], p["wer"], p["rolle"], p["grund"]), ("entscheidung", "CK", "admin", "gegengehoert"))
        r = A.aktion(self.w, "entscheiden", "310", "CK", "x", nach="frei")        # nicht mensch
        self.assertFalse(r["ok"])
        r = A.aktion(self.w, "override", "310", "anna", "x", nach="stopp")          # Kurator: kein Override
        self.assertFalse(r["ok"])
        self.assertIn("admin", r["fehler"])
        r = A.aktion(self.w, "zuruecksetzen", "310", "bob", "x")                    # fremdes Werk
        self.assertFalse(r["ok"])
        self.assertTrue(A.aktion(self.w, "zuruecksetzen", "310", "anna", "neu", scope="c002/de")["ok"])
        self.assertEqual(S.zustand(self.w, "310", "c002/de"), "offen")
        self.assertTrue(A.aktion(self.w, "override", "320", "CK", "Smoke", nach="frei")["ok"])
        self.assertEqual(S.laden(self.w)["stages"]["320"]["override"]["grund"], "Smoke")

    def test_lauf_argv(self):
        self.assertEqual(A.lauf_argv(self.w, "fortsetzen", "CK")[1:], ["run.py", self.w, "--wer", "CK"])
        self.assertEqual(A.lauf_argv(self.w, "ab", "CK", von="300", live=True)[1:],
                         ["run.py", self.w, "--from", "300", "--live", "--wer", "CK"])
        self.assertEqual(A.lauf_argv(self.w, "nur", "CK", von="615")[3:5], ["--only", "615"])
        with self.assertRaises(ValueError):
            A.lauf_argv(self.w, "ab", "CK", von="999")
        with self.assertRaises(ValueError):
            A.lauf_argv(self.w, "bulk", "CK")

    def test_regler_argv(self):
        argv, akt = A.regler_argv(self.w, "615", {"--titel": "de=Die Spiegelschwestern\nen=--force", "--schrift": "84",
                                                  "--position": "unten", "--neu": True, "--trocken": False,
                                                  "--transparenz": "0,7"}, "CK")
        self.assertEqual(akt, "lauf")
        self.assertEqual(argv[1:], ["-m", "pipeline.s615_cover_final", self.w, "--wer", "CK",
                                    "--titel=de=Die Spiegelschwestern", "--titel=en=--force", "--schrift=84",
                                    "--position=unten", "--neu", "--transparenz=0.7"])
        self.assertEqual(A.regler_argv(self.w, "095", {"--produkt": "de:text:taella"}, "CK")[1], "bestellen")
        for st, w in (("615", {"--force": True}), ("615", {"--position": "mitte"}), ("500", {}),
                      ("410", {"--max-ensemble": "x"})):
            with self.assertRaises(ValueError):
                A.regler_argv(self.w, st, w, "CK")
        self.assertTrue(A.regler(self.w, "710", {"--bitrate": "96k"}, "CK", nur_vorschau=True)["cmd"].endswith("--bitrate=96k"))
        self.assertFalse(A.regler(self.w, "095", {"--default": True}, "bob")["ok"])     # Rechte vor Start

    def test_unterprozess_exit3_ist_mensch(self):
        L = A.Laeufe()
        A_LOG = A.LOGDIR
        A.LOGDIR = self.tmp.name
        try:
            L.start("u-zwei", [sys.executable, "-c", "import time; time.sleep(2)"], "lang")
            with self.assertRaises(RuntimeError):
                L.start("u-zwei", [sys.executable, "-c", "pass"], "zweiter")
            self.assertTrue(L.stop("u-zwei"))
            L.start(self.w, [sys.executable, "-c", "print('hallo'); import sys; sys.exit(3)"], "test")
            for _ in range(100):
                if not L.state(self.w)["laeuft"]:
                    break
                time.sleep(0.05)
            st = L.state(self.w)
            self.assertEqual((st["exit"], st["deutung"]), (3, "mensch"))
            self.assertIn("hallo", st["log"])
        finally:
            A.LOGDIR = A_LOG

    def test_ampel(self):
        self._stand()
        self.assertEqual(A.ampel(self.w)["farbe"], "mensch")                     # 310 wartet
        S.ergebnis(self.w, "300", "stopp", gruende=["x"])
        self.assertEqual(A.ampel(self.w)["farbe"], "stopp")
        S.start(self.w, "320")                                                      # Lauf ausserhalb Cockpit
        a = A.ampel(self.w)
        self.assertEqual((a["farbe"], a["laufend"][0]["stage"]), ("produktion", "320"))
        alt = time.time() - 3600                                                    # 1 h keine Aktivitaet
        for p in [self.tmp.name] + [os.path.join(self.tmp.name, f) for f in os.listdir(self.tmp.name)]:
            os.utime(p, (alt, alt))
        self.assertEqual(A.ampel(self.w)["farbe"], "still")
        A.LAEUFE.jobs[self.w] = {"exit": None, "art": "run.py fortsetzen", "cmd": "", "log": os.path.join(self.tmp.name, "x.log"), "start": "", "ende": None}
        try:
            self.assertEqual(A.ampel(self.w)["farbe"], "produktion")               # Cockpit-Lauf gilt immer
        finally:
            A.LAEUFE.jobs.pop(self.w)
        S.ergebnis(self.w, "320", "auto")
        S.ergebnis(self.w, "300", "auto")
        S.entscheiden(self.w, "310", "frei", "CK", "ok", scope="c002/de")
        self.assertEqual(A.werk(self.w)["ampel"]["farbe"], "bereit")


if __name__ == "__main__":
    unittest.main()
