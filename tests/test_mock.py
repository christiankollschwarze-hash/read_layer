"""Phase 2, Fundament 5: Mock-Erkennung.  py -3.11 -m unittest tests.test_mock"""
import os, sys, tempfile, unittest, wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import gate, mock, status as S


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._orig, self._modus = config.work_dir, config.RUN_MODE
        config.work_dir = lambda b: self.tmp.name
        config.RUN_MODE = "live"
        self.w = "u-test"

    def tearDown(self):
        config.work_dir, config.RUN_MODE = self._orig, self._modus
        self.tmp.cleanup()

    def p(self, name):
        return os.path.join(self.tmp.name, name)

    def test_erkennung(self):
        mock.wav(self.p("m.wav"))
        with wave.open(self.p("m.wav")) as w:            # gueltige WAV
            self.assertEqual(w.getnframes(), 2400)
        with wave.open(self.p("alt.wav"), "wb") as w:    # Alt-Mock s500
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(b"\0\0" * 2400)
        with wave.open(self.p("echt.wav"), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(b"\1\0" * 24000)
        open(self.p("t.mp3"), "wb").write(b"MOCK")
        open(self.p("a.pcm"), "wb").write(b"MOCK_AUDIO | lang=de | x")
        n, bsp = mock.zaehlen([self.p(x) for x in ("m.wav", "alt.wav", "echt.wav", "t.mp3", "a.pcm")])
        self.assertEqual(n, 4)
        self.assertNotIn("echt.wav", bsp)
        self.assertTrue(mock.ist_obj({"a": ["ok", "[MOCK:translator]"]}))
        self.assertTrue(mock.ist_text("[PRETRANSLATION DE] (mock context translation of chapter)"))
        self.assertFalse(mock.ist_text("Ein ganz normaler Satz über Mockturtle."))

    def test_gate_live_stopp(self):
        g = gate.Gate(self.w, "500", scope="c001/de")
        g.mock(3, ["a.wav"])
        self.assertEqual(g.entscheide(), "stopp")
        self.assertEqual(S.zustand(self.w, "500"), "stopp")

    def test_gate_mocklauf_hinweis(self):
        config.RUN_MODE = "mock"
        g = gate.Gate(self.w, "500")
        g.mock(3)
        self.assertEqual(g.entscheide(), "auto")
        self.assertEqual(S.laden(self.w)["stages"]["500"]["metriken"]["modus"], "mock")

    def test_kette_mock_vorgaenger(self):
        config.RUN_MODE = "mock"
        gate.Gate(self.w, "400").entscheide()
        self.assertTrue(gate.vorgaenger_frei(self.w, "410", ["400"]))   # im Mock-Lauf weiter
        config.RUN_MODE = "live"
        with self.assertRaises(gate.GateHalt) as c:
            gate.vorgaenger_frei(self.w, "410", ["400"])
        self.assertEqual(c.exception.exit_code, 2)
        self.assertEqual(S.laden(self.w)["stages"]["410"]["gate"]["ruecksprung"], "400")
        gate.Gate(self.w, "400").entscheide()                           # live neu -> frei
        self.assertTrue(gate.vorgaenger_frei(self.w, "410", ["400"]))


if __name__ == "__main__":
    unittest.main()
