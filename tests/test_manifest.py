"""Phase 2, Fundament 3: Tests fuer pipeline/manifest.py.  py -3.11 -m unittest tests.test_manifest"""
import json, os, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import manifest as M


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work = os.path.join(self.tmp.name, "werk", "work")
        os.makedirs(self.work)
        self._orig = config.work_dir
        config.work_dir = lambda b: self.work
        self.w = "u-test"

    def tearDown(self):
        config.work_dir = self._orig
        self.tmp.cleanup()

    def test_hash(self):
        self.assertEqual(M.hash_text("Ä b\r\n"), M.hash_text("Ä b"))
        self.assertEqual(M.hash_obj({"a": 1, "b": "x"}), M.hash_obj({"b": "x", "a": 1}))
        self.assertNotEqual(M.hash_obj({"a": 1}), M.hash_obj({"a": 2}))

    def test_manifest_datei(self):
        wav = os.path.join(self.tmp.name, "werk", "fassungen", "de", "audio", "c001-00001.wav")
        os.makedirs(os.path.dirname(wav)); open(wav, "wb").write(b"RIFF1")
        m = M.Manifest(self.w, "500_vertonung")
        h = M.hash_obj({"sprechtext": "Hallo.", "stimme": "x"})
        self.assertTrue(m.braucht_neu("c001-00001", h))
        m.setzen("c001-00001", h, datei=wav, dauer=1.2)
        m.speichern()
        m2 = M.Manifest(self.w, "500_vertonung")
        self.assertEqual(m2.get("c001-00001")["datei"], "fassungen/de/audio/c001-00001.wav")
        self.assertFalse(m2.braucht_neu("c001-00001", h))
        self.assertTrue(m2.datei_aktuell("c001-00001", wav))
        self.assertTrue(m2.braucht_neu("c001-00001", M.hash_obj({"sprechtext": "Hallo!", "stimme": "x"})))
        time.sleep(0.01); open(wav, "wb").write(b"RIFF2")        # Datei extern geaendert
        self.assertFalse(m2.datei_aktuell("c001-00001"))
        os.remove(wav)
        self.assertFalse(m2.datei_aktuell("c001-00001"))

    def test_abgleich(self):
        m = M.Manifest(self.w, "340_wortalignment")
        m.setzen("a", "h1"); m.setzen("b", "h2"); m.setzen("c", "h3")
        r = m.abgleich({"a": "h1", "b": "hX", "d": "h4"})
        self.assertEqual((r["gleich"], r["geaendert"], r["neu"], r["verwaist"]), (["a"], ["b"], ["d"], ["c"]))

    def test_altdatei(self):
        json.dump({"foo": 1}, open(os.path.join(self.work, "520_wortzeiten_de.json"), "w"))
        with self.assertRaises(RuntimeError):
            M.Manifest(self.w, "520_wortzeiten_de")

    def test_checkpoint(self):
        ck = M.Checkpoint(self.w, "310")
        self.assertIsNone(ck.lesen("c001", "de", "h"))
        ck.schreiben("c001", "de", "h", {"t1": "Satz"})
        ck.schreiben("c002", "de", "h2", {"t2": "x"})
        ck.schreiben("c001", "fr", "h", {"t1": "Phrase"})
        self.assertEqual(ck.lesen("c001", "de", "h"), {"t1": "Satz"})
        self.assertIsNone(ck.lesen("c001", "de", "neu"))              # Vorstufe geaendert
        with self.assertRaises(KeyError):
            ck.sammeln({("c001", "de"): "h", ("c003", "de"): "h"})
        self.assertEqual(len(ck.sammeln({("c001", "de"): "h", ("c002", "de"): "h2"})), 2)
        self.assertEqual(ck.aufraeumen([("c001", "de"), ("c002", "de")]), [("c001", "fr")])
        self.assertEqual(ck.liste(), [("c001", "de"), ("c002", "de")])


if __name__ == "__main__":
    unittest.main()
