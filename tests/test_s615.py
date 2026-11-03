"""Stage 615 Cover final.  py -3.11 -m unittest tests.test_s615"""
import contextlib, io, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image, ImageDraw
from config import config
from pipeline import status as S
from pipeline import s615_cover_final as P

BG = P.BG_COLOR


def bild(w=1024, h=1536, oben=0.25, motiv=0.6, fmt="PNG"):
    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    y0 = h * oben
    d.ellipse((w * 0.35, y0, w * 0.65, y0 + h * motiv * 0.4), outline="black", width=12)
    d.line((w * 0.5, y0 + h * motiv * 0.4, w * 0.5, y0 + h * motiv), fill="black", width=12)
    buf = io.BytesIO()
    im.save(buf, fmt)
    return buf.getvalue()


class T615(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.r = self.tmp.name
        self.alt = (config.book_dir, config.work_dir, config.RUN_MODE, config.author_of)
        config.book_dir = lambda b: os.path.join(self.r, b)
        config.work_dir = lambda b: os.makedirs(os.path.join(self.r, b, "work"), exist_ok=True) or \
            os.path.join(self.r, b, "work")
        config.author_of = lambda b: ""
        config.RUN_MODE = "live"
        self.werk("w")

    def tearDown(self):
        config.book_dir, config.work_dir, config.RUN_MODE, config.author_of = self.alt
        self.tmp.cleanup()

    def werk(self, w, produkte=None, ill=True, gate610="auto", vermerke=True, **extra):
        os.makedirs(os.path.join(self.r, w, "work"), exist_ok=True)
        b = {"book_slug": w, "quelle": "gutenberg", "gutenberg_id": 1, "quellsprache": "en",
             "fassung": "modernisiert", "mandant": "somnio", "titel_original": "The House",
             "autor_name": "Jane Doe",
             "fassungen": [{"sprache": "en", "titel": "The House", "titel_quelle": "wikidata"},
                           {"sprache": "de", "titel": "Das Haus", "titel_quelle": "wikidata"}],
             "produkte": produkte or [{"sprache": "en", "inhalt": "text", "kanaele": ["epub"]},
                                      {"sprache": "de", "inhalt": "text", "kanaele": ["epub"]}],
             "rechte": {"art": "gemeinfrei", "bearbeitung": True, "versichert": {"wer": "t", "wann": "x"}}}
        b.update(extra)
        json.dump(b, open(os.path.join(self.r, w, "book.json"), "w", encoding="utf-8"))
        k = {"meta": {}}
        if vermerke:
            k["vermerke"] = {"modernisiert": {"en": "Gently modernized edition.",
                                              "de": "Sanft modernisierte Fassung."}}
        json.dump(k, open(os.path.join(self.r, w, "work", "600_klappentext.json"), "w", encoding="utf-8"))
        if ill:
            self.ablegen(w, bild())
        if gate610:
            S.ergebnis(w, "610", gate610, wer="test")

    def ablegen(self, w, data, name="cover.png"):
        os.makedirs(os.path.join(self.r, w, "images"), exist_ok=True)
        open(os.path.join(self.r, w, "images", name), "wb").write(data)

    def lauf(self, w="w", **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return {g.scope: g for g in P.run(w, wer="test", **kw)}

    def erg(self, gs):
        return {s: g.ergebnis["ergebnis"] for s, g in gs.items()}

    def man(self, w="w"):
        return json.load(open(config.work_path(w, "615_cover_final"), encoding="utf-8"))

    # ---------------------------------------------------------------- Grundfall
    def test_text_je_sprache_sichtfreigabe_und_resume(self):
        gs = self.lauf()
        self.assertEqual(self.erg(gs), {"en:text": "mensch", "de:text": "mensch"})
        self.assertIn("Sichtfreigabe", gs["en:text"].ergebnis["gruende"][-1])
        for lg in ("en", "de"):
            p = P.ausgabe_pfad("w", lg, "text")
            with Image.open(p) as im:
                self.assertEqual(im.size, (1000, 1500))
        m = self.man()["varianten"]
        self.assertEqual(m["de:text"]["titel"], "Das Haus")
        self.assertEqual(m["de:text"]["vermerke"], ["Sanft modernisierte Fassung."])
        self.assertEqual(S.zustand("w", "615"), "mensch")
        with contextlib.redirect_stdout(io.StringIO()):
            P.run("w", wer="CK", freigeben=True)
        self.assertEqual(S.zustand("w", "615"), "frei")
        mt = os.path.getmtime(P.ausgabe_pfad("w", "de", "text"))
        gs = self.lauf()
        self.assertEqual(set(self.erg(gs).values()), {"auto"})
        self.assertEqual(os.path.getmtime(P.ausgabe_pfad("w", "de", "text")), mt)   # unveraendert -> nicht neu

    def test_nach_freigabe_aenderung_auto(self):
        self.lauf()
        with contextlib.redirect_stdout(io.StringIO()):
            P.run("w", wer="CK", freigeben=True)
        h = self.man()["varianten"]["en:text"]["ausgabe_hash"]
        gs = self.lauf(transparenz=0.7)
        self.assertEqual(self.erg(gs)["en:text"], "auto", gs["en:text"].bericht())
        self.assertNotEqual(self.man()["varianten"]["en:text"]["ausgabe_hash"], h)

    def test_reihenteil_auto(self):
        self.werk("r-2", reihe="r", teil=2, teile_gesamt=3)
        gs = self.lauf("r-2")
        self.assertEqual(self.erg(gs)["en:text"], "auto", gs["en:text"].bericht())
        self.assertIn("Part 2 of 3.", self.man("r-2")["varianten"]["en:text"]["vermerke"])

    # ---------------------------------------------------------------- Stopps
    def test_gate_610_nicht_frei(self):
        self.werk("x", gate610="stopp")
        gs = self.lauf("x")
        self.assertEqual(self.erg(gs)["en:text"], "stopp")
        self.assertEqual(gs["en:text"].ergebnis["ruecksprung"], "610")
        self.assertFalse(os.path.exists(P.ausgabe_pfad("x", "en", "text")))

    def test_illustration_fehlt(self):
        self.werk("x", ill=False)
        self.assertEqual(self.erg(self.lauf("x"))["de:text"], "stopp")

    def test_autor_fehlt(self):
        self.werk("x", autor_name="")
        gs = self.lauf("x")
        self.assertEqual(self.erg(gs)["en:text"], "stopp")
        self.assertEqual(gs["en:text"].ergebnis["ruecksprung"], "110")

    def test_autor_eigene_optional(self):
        self.werk("x", autor_name="Unbekannt", quelle="user_epub",
                  rechte={"art": "eigene", "bearbeitung": True, "versichert": {"wer": "t", "wann": "x"}})
        gs = self.lauf("x")
        self.assertEqual(self.erg(gs)["en:text"], "mensch")
        self.assertTrue(any("ohne Autorzeile" in h for h in gs["en:text"].ergebnis["hinweise"]))

    def test_font_fehlt(self):
        alt = P.FONTS
        P.FONTS = {**alt, "bold": "fehlt.ttf"}
        try:
            self.assertEqual(self.erg(self.lauf())["en:text"], "stopp")
        finally:
            P.FONTS = alt

    def test_mock_illustration_live_stopp(self):
        im = Image.new("RGB", (1, 1), BG)
        buf = io.BytesIO(); im.save(buf, "PNG")
        self.ablegen("w", buf.getvalue())
        self.assertEqual(self.erg(self.lauf())["en:text"], "stopp")
        config.RUN_MODE = "mock"
        self.assertNotEqual(self.erg(self.lauf())["en:text"], "stopp")

    # ---------------------------------------------------------------- Titel
    def test_titel_fallback_mensch(self):
        self.werk("x", fassungen=[{"sprache": "en", "titel": "The House", "titel_quelle": "wikidata"}])
        gs = self.lauf("x")
        g = gs["de:text"]
        self.assertEqual(g.metriken["titel_quelle"], "fallback_original")
        self.assertTrue(any("Titelquelle de" in t for t in g.ergebnis["gruende"]))
        self.assertEqual(g.ergebnis["ruecksprung"], "110")

    def test_titel_quelle_original_ziel_mensch_und_pruefen(self):
        self.werk("x", quelle="user_epub", fassungen=[
            {"sprache": "en", "titel": "The House", "titel_quelle": "epub"},
            {"sprache": "de", "titel": "The House", "titel_quelle": "original"}])
        g = self.lauf("x")["de:text"]
        self.assertEqual(g.ergebnis["ruecksprung"], "310")
        self.werk("y", fassungen=[{"sprache": "en", "titel": "The House", "titel_quelle": "wikidata"},
                                  {"sprache": "de", "titel": "Das Haus", "titel_quelle": "llm", "titel_pruefen": True}])
        g = self.lauf("y")["de:text"]
        self.assertTrue(any("zur Pruefung" in t for t in g.ergebnis["gruende"]))

    def test_titel_manuell_schreibt_book_json(self):
        self.werk("x", fassungen=[{"sprache": "en", "titel": "The House", "titel_quelle": "wikidata"}])
        gs = self.lauf("x", titel_neu={"de": "Das Haus am See"})
        self.assertEqual(gs["de:text"].metriken["titel"], "Das Haus am See")
        bj = json.load(open(os.path.join(self.r, "x", "book.json"), encoding="utf-8"))
        de = next(f for f in bj["fassungen"] if f["sprache"] == "de")
        self.assertEqual((de["titel_quelle"], de["titel_pruefen"]), ("manuell", False))
        self.assertFalse(any("Titelquelle" in t for t in gs["de:text"].ergebnis["gruende"]))

    def test_langer_titel_zeilen_und_umbruch(self):
        lang = "The Extraordinary and Remarkably Long Chronicle of the Haunted Lighthouse Keeper's Daughter"
        self.werk("x", titel_original=lang, fassungen=[{"sprache": "en", "titel": lang, "titel_quelle": "wikidata"}],
                  produkte=[{"sprache": "en", "inhalt": "text", "kanaele": ["epub"]}])
        g = self.lauf("x")["en:text"]
        self.assertLessEqual(g.metriken["titel_zeilen"], 4)
        self.assertGreaterEqual(g.metriken["titel_schrift"], 48)
        g = self.lauf("x", umbruch={"en": "A|B|C|D|E"})["en:text"]
        self.assertEqual(g.metriken["titel_zeilen"], 5)
        self.assertTrue(any("titel_zeilen" in t for t in g.ergebnis["gruende"]))

    def test_ueberlappung_mensch(self):
        self.ablegen("w", bild(oben=0.02, motiv=0.9))
        g = self.lauf()["en:text"]
        self.assertGreater(g.metriken["ueberlappung"], 0.05)
        self.assertEqual(g.ergebnis["ruecksprung"], "610")
        g = self.lauf(position="unten")["en:text"]
        self.assertIn("ueberlappung", g.metriken)

    # ---------------------------------------------------------------- Vermerke
    def test_vermerke_altes_format_aus_bestellung(self):
        self.werk("x", vermerke=False)
        g = self.lauf("x")["de:text"]
        self.assertTrue(any("altes Format" in h for h in g.ergebnis["hinweise"]))
        self.assertEqual(self.man("x")["varianten"]["de:text"]["vermerke"], ["Sanft modernisierte Fassung."])

    def test_original_ohne_vermerk(self):
        self.werk("x", fassung="original")
        self.lauf("x")
        self.assertEqual(self.man("x")["varianten"]["en:text"]["vermerke"], [])

    # ---------------------------------------------------------------- Varianten
    def test_audio_wartet_auf_410_und_sprecher(self):
        self.werk("x", produkte=[{"sprache": "en", "inhalt": "text", "kanaele": ["epub"]},
                                 {"sprache": "en", "inhalt": "hoerbuch", "stufe": "basic", "kanaele": ["extern"]}])
        gs = self.lauf("x")
        self.assertNotIn("en:audio", gs)                     # 410 offen -> uebersprungen
        self.assertIn("en:quadrat", gs)
        with Image.open(P.ausgabe_pfad("x", "en", "quadrat")) as im:
            self.assertEqual(im.size, (3000, 3000))
        S.ergebnis("x", "410", "auto", wer="test")
        gs = self.lauf("x")
        self.assertEqual(self.erg(gs)["en:audio"], "stopp")  # 410 frei, aber keine freigegebene Stimme
        self.assertEqual(gs["en:audio"].ergebnis["ruecksprung"], "410")
        alt = P.sprecher
        P.sprecher = lambda w, lg: "Read by Ava · AI voice"
        try:
            gs = self.lauf("x")
        finally:
            P.sprecher = alt
        self.assertEqual(self.man("x")["varianten"]["en:audio"]["sprecher"], "Read by Ava · AI voice")
        self.assertEqual(self.man("x")["varianten"]["en:quadrat"]["sprecher"], "")

    def test_folgevarianten_nach_werkfreigabe_auto(self):
        self.lauf()
        with contextlib.redirect_stdout(io.StringIO()):
            P.run("w", wer="CK", freigeben=True)
        bj = json.load(open(os.path.join(self.r, "w", "book.json"), encoding="utf-8"))
        bj["produkte"].append({"sprache": "de", "inhalt": "text", "kanaele": ["extern"]})
        json.dump(bj, open(os.path.join(self.r, "w", "book.json"), "w", encoding="utf-8"))
        gs = self.lauf()
        self.assertEqual(self.erg(gs)["de:quadrat"], "auto", gs["de:quadrat"].bericht())

    def test_uebernahme_150_nicht_ueberzeichnet(self):
        self.werk("x", ill=False, gate610=None, quelle="user_epub", cover="images/cover_source.jpg")
        self.ablegen("x", bild(800, 1200, fmt="JPEG"), "cover_source.jpg")
        S.entfaellt("x", "610", "150")
        gs = self.lauf("x")
        g = gs["en:text"]
        self.assertEqual(g.metriken["herkunft"], "uebernahme")
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertTrue(any("Breite 800" in h for h in g.ergebnis["hinweise"]))
        with Image.open(P.ausgabe_pfad("x", "de", "text")) as im:
            self.assertEqual(im.size, (1000, 1500))

    def test_trocken_schreibt_nichts(self):
        gs = self.lauf(trocken=True)
        self.assertEqual(len(gs), 2)
        self.assertFalse(os.path.exists(P.ausgabe_pfad("w", "en", "text")))
        self.assertFalse(os.path.exists(config.work_path("w", "615_cover_final")))
        self.assertEqual(S.zustand("w", "615"), "offen")

    def test_kette_neu(self):
        import run
        self.assertIn("615", run.UMGEBAUT)
        self.assertIn("615", run.NEU)
        self.assertNotIn("615", run.ALT)


if __name__ == "__main__":
    unittest.main()
