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


if __name__ == "__main__":
    unittest.main()
