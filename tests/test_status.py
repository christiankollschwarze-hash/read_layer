"""Phase 2, Fundament 1: Tests fuer pipeline/status.py (temporaerer Werkordner).
  py -3.11 -m unittest tests.test_status
"""
import json, os, sys, tempfile, threading, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import status as S


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = config.work_dir
        config.work_dir = lambda b: self.tmp.name
        self.w = "u-test"

    def tearDown(self):
        config.work_dir = self._orig
        self.tmp.cleanup()

    def test_ablauf(self):
        S.bedarf_setzen(self.w, ["080", "090", "095", "150", "200", "310"])
        self.assertEqual(S.zustand(self.w, "300"), "entfaellt")
        self.assertTrue(S.ist_frei(self.w, "300"))
        S.start(self.w, 200)
        self.assertEqual(S.zustand(self.w, "200"), "laeuft")
        self.assertEqual(S.ergebnis(self.w, "200", "mensch", {"treue": 0.98}, ["Treue < 99,5 %"], "200"), "mensch")
        self.assertEqual(S.versuch(self.w, "200"), 1)
        with self.assertRaises(RuntimeError):
            S.entscheiden(self.w, "310", "frei", "CK", "x")
        S.entscheiden(self.w, "200", "frei", "CK", "Gegenueberstellung ok")
        self.assertTrue(S.ist_frei(self.w, "200"))
        d = json.load(open(S.pfad(self.w), encoding="utf-8"))
        self.assertEqual(d["protokoll"][-1]["aktion"], "entscheidung")
        self.assertEqual(d["stages"]["200"]["metriken"]["treue"], 0.98)

    def test_teile(self):
        S.ergebnis(self.w, "310", "auto", scope="c001/de")
        S.ergebnis(self.w, "310", "stopp", ["Luecke"], scope="c002/de")
        self.assertEqual(S.zustand(self.w, "310"), "stopp")
        S.zuruecksetzen(self.w, "310", "CK", "neu", scope="c002/de")
        self.assertEqual(S.zustand(self.w, "310"), "offen")
        S.ergebnis(self.w, "310", "auto", scope="c002/de")
        self.assertEqual(S.zustand(self.w, "310"), "frei")

    def test_override(self):
        S.ergebnis(self.w, "320", "stopp", gruende=["ID fehlt"], ruecksprung="310")
        with self.assertRaises(PermissionError):
            S.override(self.w, "320", "CK", "kurator", "x")
        S.override(self.w, "320", "CK", "admin", "Test")
        self.assertTrue(S.ist_frei(self.w, "320"))
        self.assertEqual(S.laden(self.w)["stages"]["320"]["override"]["von"], "stopp")
        self.assertEqual(S.main([self.w, "--override", "330", "--wer", "gast", "--rolle", "admin", "--grund", "x"]), 2)  # 080: Rolle aus Register

    def test_parallel(self):
        def lauf(n):
            for _ in range(10):
                S.versuch(self.w, "500", scope=f"s{n}")
        th = [threading.Thread(target=lauf, args=(i,)) for i in range(4)]
        [t.start() for t in th]; [t.join() for t in th]
        d = S.laden(self.w)
        self.assertEqual(sorted(t["versuche"] for t in d["stages"]["500"]["teile"].values()), [10] * 4)
        self.assertFalse(os.path.exists(S.pfad(self.w) + ".lock"))

    def test_unbekannte_stage(self):
        with self.assertRaises(ValueError):
            S.start(self.w, "345")

    def test_uebersicht_nur_aktuelle_befunde(self):
        """Aufraeumpaket 2: frei/entfaellt ohne alte Fehlertexte; neuer Lauf loescht Befunde des Vorlaufs."""
        S.bedarf_setzen(self.w, ["340", "640", "700"])
        S.ergebnis(self.w, "340", "mensch", gruende=["Pruefaligner nicht erreichbar"], ruecksprung="340")
        S.entscheiden(self.w, "340", "frei", wer="CK", grund="ok")
        S.ergebnis(self.w, "640", "stopp", gruende=["Fehler: No module named 'faster_whisper'"], ruecksprung="640")
        S.start(self.w, "640")
        self.assertIsNone(S.laden(self.w)["stages"]["640"]["gate"])
        S.ergebnis(self.w, "640", "auto", scope="de")
        S.ergebnis(self.w, "700", "mensch", scope="de:text:taella", gruende=["Klappentext fehlt"], ruecksprung="600")
        u = S.uebersicht(self.w)
        z = {l.split()[0]: l for l in u.splitlines()[1:]}
        self.assertNotIn("Pruefaligner", z["340"])
        self.assertNotIn("faster_whisper", z["640"])
        self.assertIn("de:text:taella: Klappentext fehlt -> 600", z["700"])

    def test_stand_nur_bei_ergebnisaenderung(self):
        """Aufraeumpaket 7: 'stand' wechselt nur bei geaendertem Ergebnis (fluechtige Metriken zaehlen nicht)."""
        S.bedarf_setzen(self.w, ["410"])
        orig = S.jetzt
        try:
            S.jetzt = lambda: "2026-11-03T10:00:00+01:00"
            S.ergebnis(self.w, "410", "auto", metriken={"figuren": 3, "dauer_s": 1.0})
            S.jetzt = lambda: "2026-11-03T12:00:00+00:00"
            S.ergebnis(self.w, "410", "auto", metriken={"figuren": 3, "dauer_s": 9.0})
            self.assertEqual(S.stand(self.w, "410").isoformat(), "2026-11-03T10:00:00+01:00")
            self.assertEqual(S.gelaufen(self.w, "410").isoformat(), "2026-11-03T12:00:00+00:00")
            S.zuruecksetzen(self.w, "410", wer="t", grund="neu")
            S.ergebnis(self.w, "410", "auto", metriken={"figuren": 4})
            self.assertEqual(S.stand(self.w, "410").isoformat(), "2026-11-03T12:00:00+00:00")
            self.assertIsNone(S.stand(self.w, "500"))
        finally:
            S.jetzt = orig


if __name__ == "__main__":
    unittest.main()
