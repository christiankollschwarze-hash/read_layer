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
        self.assertEqual(kette.wirksame_vorgaenger("600", laeuft, set(S.STAGES)), ["190"])

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
        run.NEU["400"] = lambda w, b, f, wer: (self.gelaufen.append("400"),
                                               S.ergebnis(w, "400", "auto", wer="test"))
        run.NEU["410"] = lambda w, b, f, wer: (self.gelaufen.append("410"),
                                               S.ergebnis(w, "410", "auto", wer="test"))
        run.NEU["420"] = lambda w, b, f, wer: (self.gelaufen.append("420"),
                                               S.ergebnis(w, "420", "auto", wer="test"))
        run.NEU["500"] = lambda w, b, f, wer: (self.gelaufen.append("500"),
                                               S.ergebnis(w, "500", "auto", wer="test"))
        run.NEU["510"] = lambda w, b, f, wer: (self.gelaufen.append("510"),
                                               S.ergebnis(w, "510", "auto", wer="test"))
        run.NEU["530"] = lambda w, b, f, wer: (self.gelaufen.append("530"),
                                               S.ergebnis(w, "530", "auto", wer="test"))
        run.NEU["520"] = lambda w, b, f, wer: (self.gelaufen.append("520"),
                                               S.ergebnis(w, "520", "auto", wer="test"))
        run.NEU["540"] = lambda w, b, f, wer: (self.gelaufen.append("540"),
                                               S.ergebnis(w, "540", "auto", wer="test"))
        run.NEU["600"] = lambda w, b, f, wer: (self.gelaufen.append("600"),
                                               S.ergebnis(w, "600", "auto", wer="test"))
        self.e610 = "auto"
        run.NEU["610"] = lambda w, b, f, wer: (self.gelaufen.append("610"),
                                               S.ergebnis(w, "610", self.e610, wer="test",
                                                          ruecksprung=None if self.e610 == "auto" else "610"))
        run.NEU["615"] = lambda w, b, f, wer: (self.gelaufen.append("615"),         # Soll-Teil laut Bestellung
                                               S.ergebnis(w, "615", "auto", scope="en:text", wer="test"))
        for st in ("620", "630"):
            run.NEU[st] = lambda w, b, f, wer, st=st: (self.gelaufen.append(st),
                                                       S.ergebnis(w, st, "auto", wer="test"))
        run.NEU["700"] = lambda w, b, f, wer: (self.gelaufen.append("700"),
                                               S.ergebnis(w, "700", "auto", wer="test"))
        run.NEU["710"] = lambda w, b, f, wer: (self.gelaufen.append("710"),          # Test in test_s710
                                               S.ergebnis(w, "710", "auto", scope="en:epub", wer="test"))

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
        self.assertEqual(d["stages"]["710"]["teile"]["en:epub"]["zustand"], "frei")
        n = len(d["protokoll"])
        self.lauf()                                    # zweiter Lauf: alles frei, kein neuer Bedarf
        self.assertEqual(len(S.laden("u-test")["protokoll"]), n)

    def test_stopp_vorgaenger(self):
        self.e610 = "stopp"
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

    def test_meldung_stopp_befund_ruecksprung(self):
        """Aufraeumpaket 1: Stopp nennt Befunde, Ruecksprung und Fortsetzungsbefehl."""
        self.run.NEU["610"] = lambda w, b, f, wer: S.ergebnis(w, "610", "stopp", wer="test",
                                                               gruende=["breite = 832 (Soll >= 1000)"],
                                                               ruecksprung="600")
        rc, out = self.lauf()
        self.assertEqual(rc, 2)
        self.assertIn("1 Befund(e)", out)
        self.assertIn("- breite = 832 (Soll >= 1000)", out)
        self.assertIn("Ruecksprung -> 600", out)
        self.assertIn("--from 600", out)
        rc, out = self.lauf(start_from="615")              # Vorgaenger nicht frei: gleiche Meldung
        self.assertIn("- Gate 610 nicht frei (stopp)", out)
        self.assertIn("Ruecksprung -> 610", out)

    def test_meldung_mensch_teil(self):
        """Aufraeumpaket 1: Mensch an einem Teil -> Scope-Befund, Ruecksprung des Teils, Befehl mit --scope."""
        self.run.NEU["710"] = lambda w, b, f, wer: (
            S.ergebnis(w, "710", "auto", scope="de:taella", wer="test"),
            S.ergebnis(w, "710", "mensch", scope="en:epub", wer="test", gruende=["Paket bereit"],
                       ruecksprung="700"))
        rc, out = self.lauf()
        self.assertEqual(rc, 3, out)
        self.assertIn("- en:epub: Paket bereit", out)
        self.assertIn("Ruecksprung -> 700 (en:epub)", out)
        self.assertIn("--entscheiden 710 frei --scope en:epub", out)
        self.assertNotIn("--scope de:taella", out)

    def test_bestellung_geaendert_teil_offen(self):
        """Aufraeumpaket 4: freie Stage mit fehlendem Soll-Teil laeuft erneut (statt [skip] frei)."""
        soll = ["en:text"]
        alt = dict(self.run.SOLL_SCOPES)
        self.run.SOLL_SCOPES["615"] = lambda b: list(soll)
        self.run.NEU["615"] = lambda w, b, f, wer: (self.gelaufen.append("615"),
                                                    [S.ergebnis(w, "615", "auto", scope=sc, wer="test") for sc in soll])
        try:
            self.assertEqual(self.lauf()[0], 0)
            self.gelaufen.clear()
            self.lauf()
            self.assertNotIn("615", self.gelaufen)               # alles da -> skip
            soll.append("en:audio")                              # Bestellung um Audio-Variante erweitert
            rc, out = self.lauf()
            self.assertIn("615", self.gelaufen)
            self.assertIn("Teile laut Bestellung offen: en:audio", out)
            self.assertEqual(S.zustand("u-test", "615", scope="en:audio"), "frei")
        finally:
            self.run.SOLL_SCOPES.clear(); self.run.SOLL_SCOPES.update(alt)

    def test_soll_scopes_aus_bestellung(self):
        b = B(HOERSPIEL)
        self.assertEqual(self.run._soll_615(b), ["en:text", "de:text", "de:audio"])
        self.assertEqual(self.run._soll_700(b), ["en:text:taella", "de:text:taella",
                                                 "de:hoerbuch-premium:taella", "de:hoerspiel-premium:taella"])

    def _alt_machen(self, stage, wann="2026-01-01T00:00:00+00:00"):
        with S.aendern("u-test") as d:
            for t in [d["stages"][stage]] + list(d["stages"][stage]["teile"].values()):
                if t.get("gate"):
                    t["gate"]["wann"] = wann
                t["stand"] = wann

    def test_frische_kaskade(self):
        """Aufraeumpaket 7: juengeres Vorgaenger-Ergebnis -> freie Folgestage laeuft neu; gleiches
        Ergebnis beim Neulauf beendet die Kaskade."""
        self.assertEqual(self.lauf()[0], 0)
        self._alt_machen("610")
        self._alt_machen("615")
        self._alt_machen("620")
        S.ergebnis("u-test", "610", "auto", metriken={"breite": 1200}, wer="test")   # 610 neu, Ergebnis anders
        self.gelaufen.clear()
        rc, out = self.lauf()
        self.assertEqual(rc, 0, out)
        self.assertIn("615", self.gelaufen)
        self.assertIn("[neu] Stage 615 — veraltet: juengeres Ergebnis von 610", out)
        self.assertNotIn("620", self.gelaufen)          # 615 gleiches Ergebnis -> stand alt -> 620 aktuell
        self.assertNotIn("610", self.gelaufen)
        self.gelaufen.clear()
        self.lauf()
        self.assertNotIn("615", self.gelaufen)          # jetzt aktuell

    def test_710_nach_juengerem_700(self):
        """Aufraeumpaket 6: neue Produkte in 700 (Ergebnis geaendert) -> 710 laeuft neu, ohne --force;
        700 mit gleichem Ergebnis -> 710 bleibt frei (kein Leerlauf-Upload)."""
        self.assertEqual(self.lauf()[0], 0)
        self.gelaufen.clear()
        self.lauf()
        self.assertEqual([x for x in self.gelaufen if x in ("700", "710")], ["700"])
        self._alt_machen("710")
        self.run.NEU["700"] = lambda w, b, f, wer: (self.gelaufen.append("700"),
                                                    S.ergebnis(w, "700", "auto", wer="test",
                                                               metriken={"produkte": 2}))
        self.gelaufen.clear()
        rc, out = self.lauf()
        self.assertEqual(rc, 0, out)
        self.assertEqual([x for x in self.gelaufen if x in ("700", "710")], ["700", "710"])
        self.assertIn("[neu] Stage 710 — veraltet: juengeres Ergebnis von 700", out)

    def test_soll_710(self):
        b = B(TAELLA_DE + [{"sprache": "de", "inhalt": "text", "kanaele": ["epub"]}])
        self.assertEqual(self.run._soll_710(b), ["en:taella", "de:taella", "de:epub"])

    def test_bestellung_ungueltig(self):
        json.dump({"quellsprache": "xx", "produkte": []}, open(os.path.join(self.tmp.name, "book.json"), "w"))
        rc, out = self.lauf()
        self.assertEqual(rc, 2)
        self.assertEqual(self.gelaufen, [])


if __name__ == "__main__":
    unittest.main()
