"""Stage 700 Auslieferungs-Vertrag.  py -3.11 -m unittest tests.test_s700"""
import contextlib, hashlib, io, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import manifest, status as S
from pipeline import s700_guard as P

RECHTE = {"art": "gemeinfrei", "bearbeitung": True, "versichert": {"wer": "t", "wann": "x"}}
TEXT_EPUB = [{"sprache": "en", "inhalt": "text", "kanaele": ["epub"]}]


def dump(o, p):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(o, f)


def leise(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


class Basis(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.r = self.tmp.name
        self.alt = (config.book_dir, config.work_dir, config.RUN_MODE, config.author_of)
        config.book_dir = lambda b: os.path.join(self.r, b)
        config.work_dir = lambda b: os.makedirs(os.path.join(self.r, b, "work"), exist_ok=True) or \
            os.path.join(self.r, b, "work")
        config.author_of = lambda b: ""
        config.RUN_MODE = "live"

    def tearDown(self):
        config.book_dir, config.work_dir, config.RUN_MODE, config.author_of = self.alt
        self.tmp.cleanup()


class T700(Basis):
    def werk(self, w="w", produkte=TEXT_EPUB, mandant="somnio"):
        d = os.path.join(self.r, w)
        dump({"book_slug": w, "quelle": "gutenberg", "gutenberg_id": 1, "quellsprache": "en", "fassung": "original",
              "mandant": mandant, "produkte": produkte, "rechte": RECHTE}, os.path.join(d, "book.json"))
        os.makedirs(os.path.join(d, "work", "modernized"), exist_ok=True)
        S.ergebnis(w, "190", "auto", wer="test")
        k = {"blurb": {"koeder": [], "einordnung": [{"en": "A quiet tale."}], "autor": []}, "vermerke": {}, "meta": {"genre": "novel", "ton": "ruhig"}}
        dump(k, config.work_path(w, "600_klappentext"))
        h600 = manifest.hash_obj({"b": k["blurb"], "v": k["vermerke"],
                                  "m": {"genre": "novel", "hauptfigur_geschlecht": None, "ton": "ruhig"}})
        S.ergebnis(w, "600", "auto", metriken={"ausgabe_hash": h600}, wer="test")
        S.ergebnis(w, "610", "auto", wer="test")
        var = {}
        for v in ("text", "quadrat"):
            p = os.path.join(d, "fassungen", "en", "output", f"cover_final_en{'' if v == 'text' else '_' + v}.jpg")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            data = b"\xff\xd8JPEG" + v.encode()
            open(p, "wb").write(data)
            h = hashlib.sha256(data).hexdigest()
            var[f"en:{v}"] = {"datei": os.path.relpath(p, d), "ausgabe_hash": h}
            S.ergebnis(w, "615", "auto", metriken={"ausgabe_hash": h}, scope=f"en:{v}", wer="test")
        dump({"schema": 1, "varianten": var}, config.work_path(w, "615_cover_final"))
        p = os.path.join(d, "fassungen", "en", "output", f"{w}_en.epub")
        open(p, "wb").write(b"PK epub")
        dump({"schema": 1, "varianten": {"en:text": {"datei": os.path.relpath(p, d), "eingang_hash": "e1",
                                                     "ausgabe_hash": manifest.hash_datei(p)}}},
             config.work_path(w, "620_epub"))
        S.ergebnis(w, "620", "auto", metriken={"eingang_hash": "e1"}, scope="en:text", wer="test")
        return d

    def lauf(self, w="w", **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return {g.scope: g for g in P.run(w, wer="test", **kw)}

    def guard(self, w="w"):
        return json.load(open(P.pfad(w), encoding="utf-8"))

    def test_text_epub_auto_und_lieferbar(self):
        self.werk()
        gs = self.lauf()
        g = gs["en:text:epub"]
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        x = self.guard()["produkte"]["en:text:epub"]
        self.assertTrue(x["liefern"])
        self.assertEqual([a["stage"] for a in x["artefakte"]], ["190", "600", "615", "620"])
        self.assertEqual(S.zustand("w", "700"), "frei")
        self.assertEqual(P.lieferbar("w", lg="en", kanal="epub"), ["en:text:epub"])
        self.assertEqual(P.lieferbar("w", kanal="taella"), [])

    def test_cover_veraendert_stopp_615(self):
        d = self.werk()
        open(os.path.join(d, "fassungen", "en", "output", "cover_final_en.jpg"), "ab").write(b"x")
        g = self.lauf()["en:text:epub"]
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual(g.ergebnis["ruecksprung"], "615")
        self.assertEqual(P.lieferbar("w"), [])

    def test_epub_fehlt_stopp_620(self):
        d = self.werk()
        os.replace(os.path.join(d, "fassungen", "en", "output", "w_en.epub"), os.path.join(d, "weg.epub"))
        g = self.lauf()["en:text:epub"]
        self.assertEqual((g.ergebnis["ergebnis"], g.ergebnis["ruecksprung"]), ("stopp", "620"))

    def test_veraltet_gegen_vorstufe(self):
        self.werk()
        with S.aendern("w") as d:
            d["stages"]["600"]["gate"]["wann"] = "2999-01-01T00:00:00+01:00"
        g = self.lauf()["en:text:epub"]
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertIn("veraltet", " ".join(g.ergebnis["gruende"]))
        self.assertEqual(g.ergebnis["ruecksprung"], "615")

    def test_klappentext_geaendert_ohne_neues_gate(self):
        self.werk()
        k = json.load(open(config.work_path("w", "600_klappentext"), encoding="utf-8"))
        k["blurb"]["einordnung"][0]["en"] = "Edited by hand."
        dump(k, config.work_path("w", "600_klappentext"))
        g = self.lauf()["en:text:epub"]
        self.assertEqual((g.ergebnis["ergebnis"], g.ergebnis["ruecksprung"]), ("stopp", "600"))

    def test_premium_extern_zurueckhalten_und_liefern(self):
        self.werk(produkte=TEXT_EPUB + [{"sprache": "en", "inhalt": "hoerbuch", "stufe": "premium",
                                         "kanaele": ["extern"]}])
        gs = self.lauf()
        self.assertEqual(gs["en:text:epub"].ergebnis["ergebnis"], "auto")
        g = gs["en:hoerbuch-premium:extern"]
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertIn("nicht zugelassen", " ".join(g.ergebnis["gruende"]))
        self.assertEqual(S.zustand("w", "700"), "stopp")
        self.assertEqual(P.lieferbar("w"), ["en:text:epub"])
        with self.assertRaises(ValueError):
            P.zurueckhalten("w", "en:hoerbuch-premium:extern", "CK", "")
        P.zurueckhalten("w", "en:hoerbuch-premium:extern", "CK", "ACX nimmt kein Gemini-Audio")
        self.lauf()
        self.assertEqual(S.zustand("w", "700"), "frei")
        self.assertEqual(S.zustand("w", "700", scope="en:hoerbuch-premium:extern"), "entfaellt")
        x = self.guard()
        self.assertFalse(x["produkte"]["en:hoerbuch-premium:extern"]["liefern"])
        self.assertEqual(x["ergebnis"], "auto")
        self.assertEqual(P.lieferbar("w"), ["en:text:epub"])
        P.liefern("w", "en:hoerbuch-premium:extern", "CK")
        self.lauf()
        self.assertEqual(S.zustand("w", "700"), "stopp")

    def test_nicht_mehr_bestellt_entfaellt(self):
        self.werk(produkte=TEXT_EPUB + [{"sprache": "en", "inhalt": "text", "kanaele": ["taella"]}])
        self.lauf()
        self.assertEqual(S.zustand("w", "700", scope="en:text:taella"), "stopp")   # 640 fehlt
        b = json.load(open(os.path.join(self.r, "w", "book.json"), encoding="utf-8"))
        b["produkte"] = TEXT_EPUB
        dump(b, os.path.join(self.r, "w", "book.json"))
        self.lauf()
        self.assertEqual(S.zustand("w", "700", scope="en:text:taella"), "entfaellt")
        self.assertEqual(S.zustand("w", "700"), "frei")

    def test_verlag_mensch_dann_frei(self):
        self.werk(mandant="verlag:v1")
        g = self.lauf()["en:text:epub"]
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertIn("Endabnahme", g.ergebnis["gruende"][-1])
        S.entscheiden("w", "700", "frei", "CK", "abgenommen", scope="en:text:epub")
        g = self.lauf()["en:text:epub"]
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())

    def test_mock_gate_live_stopp(self):
        self.werk()
        with S.aendern("w") as d:
            d["stages"]["600"]["metriken"]["modus"] = "mock"
        g = self.lauf()["en:text:epub"]
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertIn("Mock", " ".join(g.ergebnis["gruende"]))

    def test_trocken_schreibt_nichts(self):
        self.werk()
        self.lauf(trocken=True)
        self.assertFalse(os.path.exists(P.pfad("w")))
        self.assertEqual(S.zustand("w", "700"), "offen")

    def test_id_deckung_und_hash_330(self):
        self.werk(produkte=[{"sprache": "en", "inhalt": "text", "kanaele": ["epub"]},
                            {"sprache": "de", "inhalt": "text", "kanaele": ["epub"]}])
        c = {"c001_00001_s": {"type": "s", "en": "One.", "de": "Eins."},
             "c001_00002_s": {"type": "s", "en": "Two.", "de": ""},
             "c001_00003_p": {"type": "p", "en": "", "de": ""}}
        dump({"content": c, "meta": {"quality_report": {"flagged": []}}}, config.work_path("w", "330_rueckuebersetzung"))
        from pipeline import bestellung, kette
        b = bestellung.lesen("w")
        pr = P.Pruefer("w", b, kette.bedarf(b))
        idd = pr.id_deckung()
        self.assertEqual((idd["ok"], idd["ids"], idd["fehlt"]), (False, 2, {"de": ["c001_00002_s"]}))
        h = manifest.hash_obj({"de": {t: c[t]["de"] for t in c}} | {"_flags": []})
        S.ergebnis("w", "330", "auto", metriken={"ausgabe_hash": h}, wer="test")
        pr = P.Pruefer("w", b, kette.bedarf(b))
        self.assertEqual(pr.text("de")["befunde"], [])
        g = self.lauf()["en:text:epub"]
        self.assertEqual((g.ergebnis["ergebnis"], g.ergebnis["ruecksprung"]), ("stopp", "310"))

    def test_bestellung_ungueltig(self):
        self.werk(produkte=[{"sprache": "en", "inhalt": "hoerspiel", "stufe": "basic", "kanaele": ["taella"]}])
        gs = self.lauf()
        self.assertEqual(gs[None].ergebnis["ruecksprung"], "095")

    def test_kette_neu(self):
        import run
        self.assertIn("700", run.NEU)
        self.assertIn("700", run.UMGEBAUT)
        self.assertNotIn("700", run.ALT)
        self.assertIn("700", run.IMMER)


class T700Kreuz650(Basis):
    """Hash-Formel 650 in 700 = Formel der Stage (echter 650-Lauf)."""
    def test_hoerbuch_650(self):
        from tests import test_s650 as t
        from pipeline import s410_casting as s410, s650_hoerbuch
        alt = s410.stimme
        s410.stimme = lambda w, lg, *a, **k: "herr_a"
        try:
            h = t.T650("test_epub_kapitel_zeitmarken_format_620")
            h.r = self.r
            t.T650.werk(h, kanaele=("epub", "extern"))
            leise(s650_hoerbuch.run, "w", wer="test")
            leise(s650_hoerbuch.run, "w", wer="CK", freigeben=True)
        finally:
            s410.stimme = alt
        from pipeline import bestellung, kette
        b = bestellung.lesen("w")
        pr = P.Pruefer("w", b, kette.bedarf(b))
        for prof in ("epub", "extern"):
            a = pr.hoerbuch("en", prof)
            self.assertEqual(a["befunde"], [], prof)
        self.assertEqual(pr.endfassung("en", "hoerbuch")["befunde"], [])


class T700Kreuz615(Basis):
    """Hash 615 in 700 = Stage 615 (echter Lauf mit Sichtfreigabe)."""
    def test_cover_615(self):
        from tests import test_s615 as t
        from pipeline import s615_cover_final
        h = t.T615("test_text_je_sprache_sichtfreigabe_und_resume")
        h.r = self.r
        t.T615.werk(h, "w")
        leise(s615_cover_final.run, "w", wer="test")
        leise(s615_cover_final.run, "w", wer="CK", freigeben=True)
        from pipeline import bestellung, kette
        b = bestellung.lesen("w")
        pr = P.Pruefer("w", b, kette.bedarf(b))
        for lg in ("en", "de"):
            self.assertEqual(pr.cover(lg, "text")["befunde"], [], lg)


if __name__ == "__main__":
    unittest.main()
