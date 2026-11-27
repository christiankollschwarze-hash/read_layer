"""Segment-Lautheit + Kapitel-Mastering (pipeline/lautheit.py, Stage 520).  aus tests/: py -3.11 -m unittest test_lautheit"""
import os, sys, unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import lautheit as L
from pipeline import s520_audio_pruefung as P

SR = 24000
RG = dict(P.REGLER_STD, segment_lautheit=True)


def sprache(s, db=-25.0, seed=1):
    """Sprachaehnliches Signal: Rauschen, 4-Hz-Silbenhuellkurve, auf etwa db LUFS skaliert."""
    r = np.random.default_rng(seed)
    n = int(s * SR)
    x = r.normal(0, 1, n)
    x = np.convolve(x, np.ones(6) / 6, mode="same")            # etwas tiefpassig
    t = np.arange(n) / SR
    x *= 0.55 + 0.45 * np.sin(2 * np.pi * 4 * t) ** 2
    x = x.astype(np.float32)
    return (x * 10 ** ((db - L.lufs(x)) / 20)).astype(np.float32) if n >= 0.4 * SR else x * 0.05


class TLautheit(unittest.TestCase):
    def test_langes_segment_auf_ziel(self):
        x = np.concatenate([sprache(5, -16, 1), sprache(5, -27, 2)])
        sp = [{"id": "a", "fig": L.ERZ, "a": 0.0, "b": 5.0}, {"id": "b", "fig": "Fig", "a": 5.0, "b": 10.0}]
        kal = L.kalibrierung([(s["fig"], x[int(s["a"] * SR):int(s["b"] * SR)]) for s in sp], 3.0)
        y, prot = L.segmente_normieren(x, sp, kal, {}, RG)
        self.assertAlmostEqual(L.lufs(y[int(0.2 * SR):int(4.8 * SR)]), -19.0, delta=0.5)
        self.assertAlmostEqual(L.lufs(y[int(5.2 * SR):]), -19.0, delta=0.5)
        self.assertEqual([p["fig"] for p in prot], [L.ERZ, "Fig"])

    def test_kurzsegment_gleiche_skala(self):
        lang = [sprache(4, -22, s) for s in (3, 4, 5)]
        kurz = sprache(1.5, -26, 6)
        stuecke = [("Fig", y) for y in lang] + [("Fig", kurz)]
        kal = L.kalibrierung(stuecke, 3.0)
        p_kurz = L.pegel(kurz, "Fig", kal, 3.0)
        self.assertAlmostEqual(p_kurz, L.lufs(kurz), delta=1.0)     # RMS + Kalibrierung ~ LUFS
        x = np.concatenate(lang + [kurz])
        a = 0.0
        sp = []
        for i, y in enumerate(lang + [kurz]):
            sp.append({"id": str(i), "fig": "Fig", "a": a, "b": a + len(y) / SR})
            a += len(y) / SR
        y, _ = L.segmente_normieren(x, sp, kal, {}, RG)
        k0 = int(sp[3]["a"] * SR) + int(0.05 * SR)
        self.assertAlmostEqual(L.lufs(y[k0:]), -19.0, delta=1.0)

    def test_offset_fluestern_und_kappung(self):
        tab = L.offset_tabelle({"lautheit_offsets": {"vortrag": {"fluestern": -3.0}}})
        self.assertEqual(tab["vortrag"]["fluestern"], -3.0)
        x = np.concatenate([sprache(4, -25, 1), sprache(4, -45, 2)])
        sp = [{"id": "f", "fig": "Fig", "a": 0.0, "b": 4.0}, {"id": "z", "fig": "Fig", "a": 4.0, "b": 8.0}]
        kal = {None: 2.5}
        y, prot = L.segmente_normieren(x, sp, kal, {"f": -3.0}, RG)
        self.assertAlmostEqual(L.lufs(y[int(0.2 * SR):int(3.8 * SR)]), -22.0, delta=0.5)
        self.assertEqual(prot[1]["gain"], float(RG["segment_gain_max"]))   # -45 -> +10 gekappt

    def test_naht_ohne_sprung(self):
        x = np.concatenate([sprache(4, -16, 1), sprache(4, -28, 2)])
        sp = [{"id": "a", "fig": "A", "a": 0.0, "b": 4.0}, {"id": "b", "fig": "B", "a": 4.0, "b": 8.0}]
        g = L.huellkurve(len(x), [(0, 4 * SR), (4 * SR, 8 * SR)], [-3.0, 9.0])
        sprung = np.abs(np.diff(20 * np.log10(g))).max()
        self.assertLess(sprung, 0.05)                               # 12 dB ueber 20 ms verteilt
        y, _ = L.segmente_normieren(x, sp, {None: 2.5}, {}, RG)
        self.assertTrue(np.isfinite(y).all())

    def test_kurzes_segment_vom_nachbarn(self):
        g, _ = L.gains([({"id": "a", "fig": "A"}, sprache(4, -25, 1)), ({"id": "b", "fig": "A"}, np.zeros(100))],
                       {None: 2.5}, {}, RG)
        self.assertEqual(g[0], g[1])

    def test_spannen_hoerspiel(self):
        e5 = {"spannen": [{"id": "e", "fig": L.ERZ, "a": 0.0, "b": 2.0}, {"id": "f", "fig": "F", "a": 2.0, "b": 4.0}]}
        e51 = {"schnitt": [{"id": "f", "fig": "F", "a": 2.0, "b": 4.0, "q": 1.5}], "figuren": ["F"]}
        sp = L.spannen_hoerspiel(e5, e51, 5.0)
        self.assertEqual([(s["fig"], round(s["a"], 3), round(s["b"], 3)) for s in sp], [(L.ERZ, 0.0, 2.0), ("F", 2.0, 5.0)])
        self.assertEqual(L.spannen_hoerspiel({}, {"figuren": ["F"]}, 3.0)[0]["fig"], "F")
        self.assertEqual(L.spannen_hoerbuch({}, 3.0)[0]["fig"], L.ERZ)

    def test_mastern_true_peak(self):
        x = np.concatenate([sprache(6, -19, 1), sprache(6, -12, 2), sprache(6, -19, 3)])
        x[SR * 7] = 0.99                                               # Einzelspitze
        z, info = L.mastern(x, -19.0, -3.0, RG)
        lu, tp = P.lautheit(z)
        self.assertLessEqual(tp, -3.0 + 0.05)
        self.assertAlmostEqual(lu, -19.0, delta=1.0)
        self.assertTrue(info["kompression"])
        self.assertEqual(len(z), len(x))

    def test_regler(self):
        self.assertFalse(P.REGLER_STD["segment_lautheit"])
        rg = P._regler({"pruefung_regler": {"segment_lautheit": True}})
        self.assertEqual(rg["peak_max"], P.SEGMENT_PEAK)
        self.assertTrue(P._regler_gueltig(rg))
        self.assertEqual(P._regler({})["peak_max"], -1.0)               # aus: unveraendert
        self.assertFalse(P._regler_gueltig(dict(rg, segment_lufs=-5)))

    def test_begrenzen_mit_spitzen_unveraendert_ohne(self):
        y = sprache(2, -10, 4)
        self.assertTrue(np.array_equal(P.begrenzen(y, -3.0), P.begrenzen(y, -3.0, spitzen=np.abs(y))))

    def test_schneiden_mit_start(self):
        x = np.concatenate([np.zeros(SR), sprache(2, -20, 5), np.zeros(SR)])
        y, rand = P.schneiden(x, (1.0, 3.0), 0.05, 0.12, 1.0)
        y2, rand2, start = P.schneiden(x, (1.0, 3.0), 0.05, 0.12, 1.0, mit_start=True)
        self.assertTrue(np.array_equal(y, y2))
        self.assertEqual(rand, rand2)
        self.assertGreater(start, 0.5)


if __name__ == "__main__":
    unittest.main()
