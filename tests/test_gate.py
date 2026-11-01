"""Phase 2, Fundament 2: Tests fuer pipeline/gate.py.  py -3.11 -m unittest tests.test_gate"""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import gate, status as S


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = config.work_dir
        config.work_dir = lambda b: self.tmp.name
        self.w = "u-test"

    def tearDown(self):
        config.work_dir = self._orig
        self.tmp.cleanup()

    def g(self, **kw):
        return gate.Gate(self.w, "310", **kw)

    def test_auto(self):
        g = self.g()
        g.min("glossar", 0.99, 0.98)
        g.hinweis("ueberlang", False, 2)
        self.assertEqual(g.entscheide(), "auto")
        st = S.laden(self.w)["stages"]["310"]
        self.assertEqual(st["zustand"], "frei")
        self.assertEqual(st["hinweise"], ["ueberlang = 2"])

    def test_reparatur_dann_mensch(self):
        g = self.g(ruecksprung="310"); g.bereich("laenge", 2.5, 0.5, 2.0, bei_fehler="reparatur")
        self.assertEqual(g.entscheide(), "reparatur")
        self.assertEqual(S.zustand(self.w, "310"), "offen")
        g = self.g(ruecksprung="310"); g.bereich("laenge", 2.5, 0.5, 2.0, bei_fehler="reparatur")
        self.assertEqual(g.entscheide(), "mensch")
        with self.assertRaises(gate.GateHalt) as c:
            g.halt()
        self.assertEqual(c.exception.exit_code, 3)
        self.assertEqual(S.laden(self.w)["stages"]["310"]["gate"]["ruecksprung"], "310")

    def test_audio_zwei_versuche_dann_stopp(self):
        for erwartet in ("reparatur", "reparatur", "stopp"):
            g = gate.Gate(self.w, "500", scope="c001/de", reparatur_max=2)
            g.pflicht("abdeckung", False, wert=3, bei_fehler="reparatur_stopp", ruecksprung="500")
            self.assertEqual(g.entscheide(), erwartet)
        self.assertEqual(S.zustand(self.w, "500"), "stopp")

    def test_stopp_vor_reparatur_und_mensch_immer(self):
        g = self.g(); g.pflicht("sprache", False, bei_fehler="stopp", ruecksprung="200")
        g.bereich("laenge", 9, 0.5, 2.0, bei_fehler="reparatur")
        self.assertEqual(g.entscheide(), "stopp")
        self.assertEqual(g.ergebnis["ruecksprung"], "200")
        g = gate.Gate(self.w, "330"); g.min("score", 95, 90)
        self.assertEqual(g.entscheide(mensch_immer=True, mensch_grund="Mandant verlag"), "mensch")
        self.assertEqual(S.laden(self.w)["stages"]["330"]["gate"]["gruende"], ["Mandant verlag"])

    def test_vorgaenger(self):
        S.ergebnis(self.w, "300", "auto")
        S.bedarf_setzen(self.w, ["300", "310", "320"])        # 200 entfaellt
        self.assertTrue(gate.vorgaenger_frei(self.w, "310", ["200", "300"]))
        self.assertEqual(S.zustand(self.w, "310"), "laeuft")
        with self.assertRaises(gate.GateHalt):
            gate.vorgaenger_frei(self.w, "320", ["310"])
        st = S.laden(self.w)["stages"]["320"]
        self.assertEqual((st["zustand"], st["gate"]["ruecksprung"]), ("stopp", "310"))
        S.override(self.w, "310", "CK", "admin", "Test")
        self.assertTrue(gate.vorgaenger_frei(self.w, "320", ["310"]))

    def test_beenden(self):
        with self.assertRaises(SystemExit) as c:
            gate.beenden(["auto", "mensch", "auto"])
        self.assertEqual(c.exception.code, 3)
        with self.assertRaises(SystemExit) as c:
            gate.beenden("auto")
        self.assertEqual(c.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
