"""Phase 2, Fundament 6: Tests fuer pipeline/kette.py und run.py.  py -3.11 -m unittest tests.test_kette"""
import io, json, os, sys, tempfile, unittest, contextlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import bestellung, kette, status as S


def B(produkte, quelle="en", **roh):
    return bestellung.Bestellung(dict(quellsprache=quelle, produkte=produkte, fassung="modernisiert",
                                      rechte={"art": "gemeinfrei", "bearbeitung": True}, **roh))


TEXT_EPUB_EN = [{"sprache": "en", "inhalt": "text", "kanaele": ["epub"]}]
TAELLA_DE = [{"sprache": "en", "inhalt": "text", "kanaele": ["taella"]},
             {"sprache": "de", "inhalt": "text", "kanaele": ["taella"]}]
HOERSPIEL = TAELLA_DE + [{"sprache": "de", "inhalt": "hoerbuch", "stufe": "premium", "kanaele": ["taella"]},
                         {"sprache": "de", "inhalt": "hoerspiel", "stufe": "premium", "kanaele": ["taella"]}]


class Bedarf(unittest.TestCase):
    def test_reines_text_epub(self):
        s = kette.bedarf(B(TEXT_EPUB_EN, gutenberg_id=1))
        for st in ("100", "110", "120", "190", "600", "610", "615", "620", "700", "710"):
            self.assertIn(st, s)
        for st in ("150", "200", "210", "300", "330", "340", "400", "500", "520", "630", "640", "650"):
            self.assertNotIn(st, s)

    def test_taella_uebersetzung(self):
        s = kette.bedarf(B(TAELLA_DE, herkunft="privat_upload"))
        self.assertTrue({"150", "200", "210", "300", "310", "320", "330", "340", "640"} <= s)
        self.assertFalse({"100", "110", "400", "500", "520", "620", "630"} & s)

    def test_hoerspiel(self):
        b = B(HOERSPIEL)
        s = kette.bedarf(b)
        self.assertTrue({"400", "410", "420", "500", "510", "530", "520", "540"} <= s)
        self.assertNotIn("650", s)
        self.assertEqual(kette.sprachen("500", b), ["de"])
        self.assertEqual(kette.sprachen("520", b), ["de"])
        self.assertEqual(kette.sprachen("710", b), ["en", "de"])
        self.assertIsNone(kette.sprachen("310", b))

    def test_epub3_hoerbuch(self):
        b = B([{"sprache": "de", "inhalt": "hoerbuch", "stufe": "basic", "kanaele": ["epub"]}])
        s = kette.bedarf(b)
        self.assertTrue({"650", "630", "300"} <= s)
        self.assertNotIn("520", s)
        self.assertEqual(kette.sprachen("630", b), ["de"])


class Vorgaenger(unittest.TestCase):
    def test_entfaellt_faellt_weg(self):
        laeuft = kette.bedarf(B(TEXT_EPUB_EN))
        self.assertEqual(kette.wirksame_vorgaenger("620", laeuft, set(S.STAGES)), ["615"])
        self.assertEqual(kette.wirksame_vorgaenger("600", laeuft, set(S.STAGES)), [])

    def test_nicht_gebaut_wird_ersetzt(self):
        laeuft = set(S.STAGES)
        in_kette = laeuft - {"190", "195", "115", "100", "110", "150", "095", "090", "080"}
        self.assertEqual(kette.wirksame_vorgaenger("200", laeuft, in_kette), ["120"])
        self.assertEqual(kette.wirksame_vorgaenger("120", laeuft, in_kette), [])
        in_kette -= {"530", "650"}
        self.assertEqual(kette.wirksame_vorgaenger("620", laeuft, in_kette), ["500", "510", "615"])

    def test_700_alle_davor(self):
        laeuft = kette.bedarf(B(TAELLA_DE))
        v = kette.wirksame_vorgaenger("700", laeuft, set(S.STAGES))
        self.assertIn("640", v)
        self.assertNotIn("710", v)
        self.assertNotIn("500", v)


class Kette(unittest.TestCase):
    """run.py mit Attrappen-Stages: Start nur bei freiem Vorgaenger, Exit-Codes, Bedarf in status.json."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._wd, self._bd = config.work_dir, config.book_dir
        config.work_dir = lambda b: self.tmp.name
        config.book_dir = lambda b: self.tmp.name
        json.dump({"quellsprache": "en", "produkte": TEXT_EPUB_EN, "fassung": "original",
                   "rechte": {"art": "eigene", "bearbeitung": True, "drm_frei": True,
                              "versichert": {"wer": "CK", "wann": "2026-11-01T12:00:00"}},
                   "herkunft": "privat_upload"},
                  open(os.path.join(self.tmp.name, "book.json"), "w"))
        import run
        self.run = run
        self._alt, self._ws = dict(run.ALT), config.werk_sprachen
        config.werk_sprachen = lambda b: ("en", [])
        self.gelaufen = []
        self.ausgabe = set()

        def stage(key, ok=True):
            def aufruf(w, lg, b, f):
                self.gelaufen.append(key)
                if ok:
                    self.ausgabe.add(key)
            return (aufruf, lambda w, lg=None, b=None: key in self.ausgabe)
        for k in list(run.ALT):
            run.ALT[k] = stage(k)
        self.stage = stage
        self._neu = dict(run.NEU)
        # 150 ePub-Import als Attrappe (eigenes Gate, Test in test_s150)
        run.NEU["150"] = lambda w, b, f, wer: (self.gelaufen.append("150"),
                                               S.ergebnis(w, "150", "auto", wer="test"))
        # 120 Modernisierung als Attrappe (eigenes Gate, Test in test_s120)
        run.NEU["120"] = lambda w, b, f, wer: (self.gelaufen.append("120"),
                                               S.ergebnis(w, "120", "auto", wer="test"))
        # 190 Eingangsvertrag als Attrappe (eigenes Gate, Test in test_s190)
        run.NEU["190"] = lambda w, b, f, wer: (self.gelaufen.append("190"),
                                               S.ergebnis(w, "190", "auto", wer="test"))
        run.NEU["195"] = lambda w, b, f, wer: (self.gelaufen.append("195"),
                                               S.ergebnis(w, "195", "auto", wer="test"))
        run.NEU["200"] = lambda w, b, f, wer: (self.gelaufen.append("200"),
                                               S.ergebnis(w, "200", "auto", wer="test"))
        run.NEU["210"] = lambda w, b, f, wer: (self.gelaufen.append("210"),
                                               S.ergebnis(w, "210", "auto", wer="test"))
        run.NEU["300"] = lambda w, b, f, wer: (self.gelaufen.append("300"),
                                               S.ergebnis(w, "300", "auto", wer="test"))
        run.NEU["310"] = lambda w, b, f, wer: (self.gelaufen.append("310"),
                                               S.ergebnis(w, "310", "auto", wer="test"))
        run.NEU["320"] = lambda w, b, f, wer: (self.gelaufen.append("320"),
                                               S.ergebnis(w, "320", "auto", wer="test"))
        run.NEU["330"] = lambda w, b, f, wer: (self.gelaufen.append("330"),
                                               S.ergebnis(w, "330", "auto", wer="test"))
        run.NEU["340"] = lambda w, b, f, wer: (self.gelaufen.append("340"),
                                               S.ergebnis(w, "340", "auto", wer="test"))

    def tearDown(self):
        self.run.ALT.clear(); self.run.ALT.update(self._alt)
        self.run.NEU.clear(); self.run.NEU.update(self._neu)
        config.work_dir, config.book_dir, config.werk_sprachen = self._wd, self._bd, self._ws
        self.tmp.cleanup()

    def lauf(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = self.run.run_pipeline("u-test", **kw)
        return rc, out.getvalue()

    def test_ganze_kette_text_epub(self):
        rc, out = self.lauf()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.gelaufen, ["150", "120", "190", "195", "600", "610", "615", "620", "700", "710"])
        d = S.laden("u-test")
        self.assertEqual(d["stages"]["310"]["zustand"], "entfaellt")
        self.assertEqual(d["stages"]["620"]["zustand"], "frei")
        self.assertEqual(d["stages"]["710"]["teile"]["en"]["zustand"], "frei")
        n = len(d["protokoll"])
        self.lauf()                                    # zweiter Lauf: alles frei, kein neuer Bedarf
        self.assertEqual(len(S.laden("u-test")["protokoll"]), n)

    def test_stopp_vorgaenger(self):
        self.run.ALT["610"] = self.stage("610", ok=False)
        rc, out = self.lauf()
        self.assertEqual(rc, 2, out)
        self.assertEqual(S.zustand("u-test", "610"), "stopp")
        self.assertNotIn("615", self.gelaufen)
        rc, out = self.lauf(start_from="615")
        self.assertEqual(rc, 2)
        self.assertIn("Gate 610 nicht frei", out)
        self.assertEqual(S.laden("u-test")["stages"]["615"]["gate"]["ruecksprung"], "610")

    def test_mensch_entscheidung(self):
        self.lauf(stop_to="610")
        S.ergebnis("u-test", "610", "mensch", gruende=["Sichtpruefung"])
        rc, out = self.lauf(start_from="615")
        self.assertEqual(rc, 2)
        S.entscheiden("u-test", "610", "frei", wer="CK", grund="ok")
        rc, out = self.lauf(start_from="615")
        self.assertEqual(rc, 0, out)

    def test_bestellung_ungueltig(self):
        json.dump({"quellsprache": "xx", "produkte": []}, open(os.path.join(self.tmp.name, "book.json"), "w"))
        rc, out = self.lauf()
        self.assertEqual(rc, 2)
        self.assertEqual(self.gelaufen, [])


if __name__ == "__main__":
    unittest.main()
