"""Stage 620/630 ePub.  py -3.11 -m unittest tests.test_s620"""
import contextlib, io, json, os, shutil, subprocess, sys, tempfile, unittest, zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image
from config import config
from pipeline import epub_bau as B
from pipeline import status as S
from pipeline import s620_epub_original as P
from pipeline import s630_epub_zielsprache as Z

K1 = [["The house stood at the end of the lane. Nobody moved the mirror."],
      ["Ros came in from the garden.", "She stopped dead."]]
K2 = [["The glazier arrived the next morning."]]
SAETZE = {  # tid: (typ, en, de)
    "c001_00001_h": ("h", "Chapter One", "Kapitel Eins"),
    "c001_00002_s": ("s", "The house stood at the end of the lane.", "Das Haus stand am Ende der Gasse."),
    "c001_00003_s": ("s", "Nobody moved the mirror.", "Niemand rückte den Spiegel."),
    "c001_00004_p": ("p", "", ""),
    "c001_00005_s": ("s", "Ros came in from the garden.", "Ros kam aus dem Garten."),
    "c001_00006_p": ("p", "", ""),
    "c001_00007_s": ("s", "She stopped dead.", "Sie blieb stehen."),
    "c002_00001_h": ("h", "Chapter Two", "Kapitel Zwei"),
    "c002_00002_s": ("s", "The glazier arrived the next morning.", "Der Glaser kam am nächsten Morgen."),
}


def ok_check(pfad, timeout=300):
    return {"werkzeug": True, "fehler": 0, "warnungen": 0, "meldungen": []}


class T620(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.r = self.tmp.name
        self.alt = (config.book_dir, config.work_dir, config.RUN_MODE, config.author_of, B.epubcheck)
        config.book_dir = lambda b: os.path.join(self.r, b)
        config.work_dir = lambda b: os.makedirs(os.path.join(self.r, b, "work"), exist_ok=True) or \
            os.path.join(self.r, b, "work")
        config.author_of = lambda b: ""
        config.RUN_MODE = "live"
        B.epubcheck = ok_check
        self.werk("w")

    def tearDown(self):
        config.book_dir, config.work_dir, config.RUN_MODE, config.author_of, B.epubcheck = self.alt
        self.tmp.cleanup()

    # ---------------------------------------------------------------- Fixture
    def j(self, w, rel, obj):
        p = os.path.join(self.r, w, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)

    def werk(self, w, produkte=None, saetze=None, kapitel=(K1, K2), anhang=None, profil=None, **extra):
        b = {"book_slug": w, "quelle": "gutenberg", "gutenberg_id": 7, "quellsprache": "en",
             "fassung": "modernisiert", "mandant": "somnio", "titel_original": "The House", "autor_name": "Jane Doe",
             "fassungen": [{"sprache": "en", "titel": "The House", "titel_quelle": "wikidata"},
                           {"sprache": "de", "titel": "Das Haus", "titel_quelle": "wikidata"}],
             "produkte": produkte or [{"sprache": "en", "inhalt": "text", "kanaele": ["epub"]},
                                      {"sprache": "de", "inhalt": "text", "kanaele": ["epub"]}],
             "rechte": {"art": "gemeinfrei", "bearbeitung": True, "versichert": {"wer": "t", "wann": "x"}}}
        b.update(extra)
        self.j(w, "book.json", b)
        titel = ["Chapter One", "Chapter Two"]
        for n, paras in enumerate(kapitel, 1):
            self.j(w, f"work/modernized/chapter-{n}.json",
                   {"title": titel[n - 1], "paragraphs": [" ".join(p) for p in paras]})
        sz = saetze or SAETZE
        self.j(w, "work/200_tagging.json", {"content": {t: {"type": v[0], "en": v[1]} for t, v in sz.items()}})
        self.j(w, "work/330_rueckuebersetzung.json",
               {"meta": {"profile": profil or {}},
                "content": {t: {"type": v[0], "en": v[1], **({"de": v[2]} if v[2] else {}), **(v[3] if len(v) > 3 else {})}
                            for t, v in sz.items()}})
        self.j(w, "work/600_klappentext.json", {
            "blurb": {"koeder": [{"en": "Nobody moved the mirror.", "de": "Niemand rückte den Spiegel."}],
                      "einordnung": [{"en": "A quiet ghost story.", "de": "Eine leise Geistergeschichte."}],
                      "autor": [{"en": "Jane Doe wrote it.", "de": "Jane Doe schrieb es."}]},
            "vermerke": {"modernisiert": {"en": "Gently modernized edition.", "de": "Sanft modernisierte Fassung."}}})
        self.j(w, "work/anhang.json", anhang or {"bilder": [], "fussnoten": []})
        if profil:
            self.j(w, "work/210_profil.json", profil)
        for lg in ("en", "de"):
            for var in ("text", "audio"):
                p = os.path.join(self.r, w, "fassungen", lg, "output", f"cover_final_{lg}{'_audio' if var == 'audio' else ''}.jpg")
                os.makedirs(os.path.dirname(p), exist_ok=True)
                Image.new("RGB", (100, 150), "#faf8f4").save(p, "JPEG")
                S.ergebnis(w, "615", "auto", wer="test", scope=f"{lg}:{var}")
        for s in ("190", "330", "600"):
            S.ergebnis(w, s, "auto", wer="test")

    def lauf(self, w="w", stage="620", **kw):
        fn = P.run if stage == "620" else Z.run
        with contextlib.redirect_stdout(io.StringIO()):
            return {g.scope: g for g in fn(w, wer="test", **kw)}

    def erg(self, gs):
        return {s: g.ergebnis["ergebnis"] for s, g in gs.items()}

    def man(self, w="w"):
        return json.load(open(P.manifest_pfad(w), encoding="utf-8"))["varianten"]

    def xhtml(self, pfad, name):
        with zipfile.ZipFile(pfad) as z:
            return z.read(f"epub/text/{name}").decode("utf-8")

    # ---------------------------------------------------------------- Grundfall
    def test_text_beide_sprachen(self):
        gq, gz = self.lauf(), self.lauf(stage="630")
        self.assertEqual(self.erg(gq), {"en:text": "auto"}, gq["en:text"].bericht())
        self.assertEqual(self.erg(gz), {"de:text": "auto"}, gz["de:text"].bericht())
        pde = P.ausgabe_pfad("w", "de", "text")
        self.assertTrue(pde.endswith("w_de.epub"))
        r = B.lesen(pde)
        self.assertEqual(r["sprache"], "de")
        self.assertEqual(r["titel"], "Das Haus")
        self.assertIn("Sanft modernisierte Fassung.", r["kolophon"])
        self.assertIn("Project Gutenberg", r["kolophon"])
        self.assertNotIn("garden", " ".join(r["kapitel"]))
        self.assertEqual(len(r["kapitel"]), 2)
        self.assertIn("Kapitel Eins", self.xhtml(pde, "chapter-1-title.xhtml"))
        with zipfile.ZipFile(pde) as z:
            self.assertIn("Inhalt", z.read("epub/toc.xhtml").decode("utf-8"))
        self.assertIn("Eine leise Geistergeschichte.", self.xhtml(pde, "blurb.xhtml"))
        m = self.man()
        self.assertEqual(set(m), {"en:text", "de:text"})            # 620 und 630 teilen die Datei
        self.assertEqual(m["de:text"]["metriken"]["textabgleich"], 1.0)
        self.assertEqual(S.zustand("w", "620"), "frei")
        self.assertEqual(S.zustand("w", "630"), "frei")

    def test_absaetze_aus_190(self):
        self.lauf(stage="630")
        x = self.xhtml(P.ausgabe_pfad("w", "de", "text"), "chapter-1.xhtml")
        self.assertIn("<p>Das Haus stand am Ende der Gasse. Niemand rückte den Spiegel.</p>", x)
        self.assertIn("<p>Ros kam aus dem Garten. Sie blieb stehen.</p>", x)     # 190 vor p-Marke
        self.assertEqual(x.count("<p>"), 2)

    def test_resume_und_aenderung(self):
        self.lauf(stage="630")
        p = P.ausgabe_pfad("w", "de", "text")
        mt = os.path.getmtime(p)
        gs = self.lauf(stage="630")
        self.assertEqual(self.erg(gs)["de:text"], "auto")
        self.assertTrue(gs["de:text"].metriken.get("unveraendert"))
        self.assertEqual(os.path.getmtime(p), mt)
        sz = dict(SAETZE)
        sz["c002_00002_s"] = ("s", "The glazier arrived the next morning.", "Der Glaser erschien morgens.")
        self.werk("w", saetze=sz)
        gs = self.lauf(stage="630")
        self.assertFalse(gs["de:text"].metriken.get("unveraendert"))
        self.assertIn("erschien", " ".join(B.lesen(p)["kapitel"]))

    def test_neu_baut(self):
        self.lauf()
        gs = self.lauf(neu=True)
        self.assertFalse(gs["en:text"].metriken.get("unveraendert"))

    # ---------------------------------------------------------------- Stopps
    def test_fallback_stopp_310(self):
        sz = dict(SAETZE)
        sz["c001_00003_s"] = ("s", "Nobody moved the mirror.", "")
        self.werk("w", saetze=sz)
        gs = self.lauf(stage="630")
        g = gs["de:text"]
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual(g.ergebnis["ruecksprung"], "310")
        self.assertEqual(g.metriken["fallback_ids"], ["c001_00003_s"])
        self.assertFalse(os.path.exists(P.ausgabe_pfad("w", "de", "text")))

    def test_klappentext_sprache_fehlt(self):
        self.j("w", "work/600_klappentext.json", {"blurb": {"koeder": [{"en": "x"}]}})
        gs = self.lauf(stage="630")
        self.assertEqual(gs["de:text"].ergebnis["ergebnis"], "stopp")
        self.assertEqual(gs["de:text"].ergebnis["ruecksprung"], "600")

    def test_gate_615_und_600(self):
        S.ergebnis("w", "615", "mensch", wer="test", scope="en:text", ruecksprung="615")
        gs = self.lauf()
        self.assertEqual(gs["en:text"].ergebnis["ruecksprung"], "615")
        S.ergebnis("w", "615", "auto", wer="test", scope="en:text")
        S.ergebnis("w", "600", "stopp", wer="test", ruecksprung="600")
        gs = self.lauf()
        self.assertEqual(gs["en:text"].ergebnis["ergebnis"], "stopp")
        self.assertEqual(gs["en:text"].ergebnis["ruecksprung"], "600")

    def test_gate_330_nur_ziel(self):
        S.ergebnis("w", "330", "mensch", wer="test", ruecksprung="330")
        self.assertEqual(self.erg(self.lauf())["en:text"], "auto")
        self.assertEqual(self.lauf(stage="630")["de:text"].ergebnis["ruecksprung"], "330")

    def test_epubcheck_fehler_und_fehlend(self):
        B.epubcheck = lambda p, timeout=300: {"werkzeug": True, "fehler": 2, "warnungen": 0, "meldungen": ["RSC-005"]}
        g = self.lauf()["en:text"]
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertFalse(os.path.exists(P.ausgabe_pfad("w", "en", "text")))
        B.epubcheck = lambda p, timeout=300: {"werkzeug": False, "fehler": None, "warnungen": None, "meldungen": []}
        self.assertEqual(self.lauf()["en:text"].ergebnis["ergebnis"], "stopp")

    def test_kapitelzahl(self):
        self.j("w", "work/modernized/chapter-3.json", {"title": "Three", "paragraphs": ["Extra."]})
        g = self.lauf(stage="630")["de:text"]
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")

    # ---------------------------------------------------------------- Mensch
    def test_geklebt_mensch_freigabe(self):
        sz = {k: v for k, v in SAETZE.items() if not k.endswith("_p")}
        sz["c001_00002_s"] = ("s", "The house stood at the end of the road.", "Das Haus stand am Ende der Straße.")
        self.werk("w", saetze=sz)
        gs = self.lauf(stage="630")
        g = gs["de:text"]
        self.assertEqual(g.ergebnis["ergebnis"], "mensch", g.bericht())
        self.assertEqual(g.metriken["geklebt_kapitel"], [1])
        self.assertTrue(os.path.exists(P.ausgabe_pfad("w", "de", "text")))
        with contextlib.redirect_stdout(io.StringIO()):
            Z.run("w", wer="CK", freigeben=True)
        self.assertEqual(S.zustand("w", "630"), "frei")
        self.assertEqual(self.erg(self.lauf(stage="630"))["de:text"], "auto")

    def test_verlag_mensch(self):
        self.werk("v", mandant="verlag:x")
        self.assertEqual(self.erg(self.lauf("v"))["en:text"], "mensch")

    # ---------------------------------------------------------------- Kolophon / Rechte
    def test_user_epub_eigene_rechte(self):
        self.werk("u", quelle="user_epub", gutenberg_id=None, mandant="user:x", fassung="original",
                  rechte={"art": "eigene", "bearbeitung": True, "versichert": {"wer": "u", "wann": "x"}},
                  produkte=[{"sprache": "en", "inhalt": "text", "kanaele": ["epub"]}])
        self.j("u", "work/600_klappentext.json", {"blurb": {"koeder": [{"en": "x."}]}})
        g = self.lauf("u")["en:text"]
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        k = B.lesen(P.ausgabe_pfad("u", "en", "text"))["kolophon"]
        self.assertIn("All rights reserved", k)
        self.assertIn("original ebook", k)
        self.assertNotIn("Gutenberg", k)
        self.assertNotIn("modernized", k)

    def test_teil_vermerk_und_zusatz(self):
        self.werk("t", teil=2, teile_gesamt=3, reihe="r")
        self.lauf("t", regler={"kolophon": {"en": "Sonderausgabe."}})
        k = B.lesen(P.ausgabe_pfad("t", "en", "text"))["kolophon"]
        self.assertIn("Part 2 of 3", k)
        self.assertIn("Sonderausgabe.", k)

    # ---------------------------------------------------------------- Anhang / Mobil / Drama
    def test_anhang(self):
        img = os.path.join(self.r, "w", "images", "anhang", "bild-1.png")
        os.makedirs(os.path.dirname(img))
        Image.new("RGB", (10, 10)).save(img)
        self.werk("w", anhang={"bilder": [{"nr": 1, "datei": "images/anhang/bild-1.png", "kapitel": 1, "nach_absatz": 0,
                                           "alt": "Haus", "bildunterschrift": "Das Haus"}],
                               "fussnoten": [{"nr": 1, "text": "A note.", "text_de": "Eine Notiz.", "kapitel": 2,
                                              "absatz": 0}]})
        g = self.lauf(stage="630")["de:text"]
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        p = P.ausgabe_pfad("w", "de", "text")
        r = B.lesen(p)
        self.assertEqual((r["bilder"], r["noten"], r["bildrefs"], r["noterefs"]), (1, 1, 1, 1))
        self.assertIn("Eine Notiz.", self.xhtml(p, "anhang.xhtml"))
        self.assertEqual(self.man()["de:text"]["metriken"]["textabgleich"], 1.0)
        g = self.lauf(stage="630", regler={"bilder": "aus", "fussnoten": "aus"})["de:text"]
        self.assertEqual(B.lesen(p)["bilder"], 0)

    def test_mobil_teilung(self):
        lang = " ".join(f"Sentence number {i} is here." for i in range(30))
        self.werk("m", kapitel=([[lang]], K2), produkte=[{"sprache": "en", "inhalt": "text", "kanaele": ["epub"]}])
        self.lauf("m")
        p = P.ausgabe_pfad("m", "en", "text")
        n = self.xhtml(p, "chapter-1.xhtml").count("<p>")
        self.assertGreater(n, 1)
        self.assertEqual(self.man("m")["en:text"]["metriken"]["textabgleich"], 1.0)
        self.lauf("m", regler={"mobil": "aus"})
        self.assertEqual(self.xhtml(p, "chapter-1.xhtml").count("<p>"), 1)

    def test_drama_rollen_aus_210(self):
        sz = {"c001_00001_h": ("h", "Act One", "Erster Akt"),
              "c001_00002_dl": ("dl", "Who goes there?", "Wer da?", {"sprecher": "FIRST LORD", "replik": 1}),
              "c001_00003_dl": ("dl", "A friend.", "Ein Freund.", {"sprecher": "DUKE", "replik": 2}),
              "c002_00001_h": ("h", "Act Two", "Zweiter Akt"),
              "c002_00002_s": ("s", "Exit.", "Ab.")}
        self.werk("d", saetze=sz, kapitel=([["Who goes there?"], ["A friend."]], [["Exit."]]),
                  profil={"characters": {"FIRST LORD": {"de": "ERSTER EDELMANN"}, "DUKE": {"de": "HERZOG"}}})
        g = self.lauf("d", stage="630")["de:text"]
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        x = self.xhtml(P.ausgabe_pfad("d", "de", "text"), "chapter-1.xhtml")
        self.assertIn('<span class="rolle">ERSTER EDELMANN.</span> Wer da?', x)
        self.assertIn('<span class="rolle">HERZOG.</span>', x)

    # ---------------------------------------------------------------- Audio
    def audio_werk(self, w="a", zeiten=None, dauer=10.0):
        self.werk(w, produkte=[{"sprache": "en", "inhalt": "hoerbuch", "stufe": "basic", "kanaele": ["epub"]},
                               {"sprache": "de", "inhalt": "hoerbuch", "stufe": "basic", "kanaele": ["epub"]}])
        for lg in ("en", "de"):
            kap = []
            for kid in ("c001", "c002"):
                rel = f"fassungen/{lg}/hoerbuch/{kid}.mp3"
                p = os.path.join(self.r, w, rel)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                open(p, "wb").write(b"\xff\xfb\x90\x00" * 100)
                ids = [t for t, v in SAETZE.items() if t.startswith(kid) and v[0] != "p"]
                z = zeiten if zeiten is not None else {t: [i * 1.0, i * 1.0 + 0.9] for i, t in enumerate(ids)}
                kap.append({"kapitel": kid, "datei": rel, "dauer": dauer, "saetze": z})
            self.j(w, f"work/650_hoerbuch_{lg}.json", {"kapitel": kap})
            S.ergebnis(w, "650", "auto", wer="test", scope=lg)
        self.j(w, "work/casting.json", {})

    def test_audio_smil(self):
        self.audio_werk()
        import pipeline.s615_cover_final as s615
        alt = s615.sprecher
        s615.sprecher = lambda w, lg: "Read by Herr B · AI voice"
        try:
            gq, gz = self.lauf("a"), self.lauf("a", stage="630")
        finally:
            s615.sprecher = alt
        self.assertEqual(self.erg(gq), {"en:audio": "auto"}, gq["en:audio"].bericht())
        self.assertEqual(self.erg(gz), {"de:audio": "auto"}, gz["de:audio"].bericht())
        p = P.ausgabe_pfad("a", "de", "audio")
        self.assertTrue(p.endswith("a_de_audio.epub"))
        r = B.lesen(p)
        self.assertEqual(sum(len(v) for v in r["smil"].values()), 7)
        with zipfile.ZipFile(p) as z:
            opf = z.read("epub/content.opf").decode("utf-8")
            self.assertIn('media-overlay="smil-1"', opf)
            self.assertIn('media:duration', opf)
            self.assertIn('<span id="c001_00002_s">Das Haus', z.read("epub/text/chapter-1.xhtml").decode("utf-8"))
            self.assertIn("epub/audio/chapter-1.mp3", z.namelist())

    def test_audio_zeitmarke_fehlt_und_650_offen(self):
        self.audio_werk(zeiten={"c001_00002_s": [0, 1]})
        import pipeline.s615_cover_final as s615
        alt = s615.sprecher
        s615.sprecher = lambda w, lg: "Read by X"
        try:
            g = self.lauf("a")["en:audio"]
            self.assertEqual(g.ergebnis["ergebnis"], "stopp")
            self.assertEqual(g.ergebnis["ruecksprung"], "650")
            S.ergebnis("a", "650", "mensch", wer="test", scope="en", ruecksprung="650")
            self.assertEqual(self.lauf("a"), {})                        # wartet auf 650
        finally:
            s615.sprecher = alt

    # ---------------------------------------------------------------- Sonstiges
    def test_trocken_und_ohne_bestellung(self):
        gs = self.lauf(trocken=True)
        self.assertEqual(self.erg(gs)["en:text"], "auto")
        self.assertFalse(os.path.exists(P.ausgabe_pfad("w", "en", "text")))
        self.assertFalse(os.path.exists(P.manifest_pfad("w")))
        self.werk("n", produkte=[{"sprache": "en", "inhalt": "text", "kanaele": ["taella"]}])
        self.assertEqual(self.lauf("n"), {})

    def test_mock_cover_live_stopp(self):
        from pipeline import mock
        p = os.path.join(self.r, "w", "fassungen", "en", "output", "cover_final_en.jpg")
        with open(p, "ab") as f:
            f.write(mock.MARKER if isinstance(mock.MARKER, bytes) else mock.MARKER.encode())
        g = self.lauf()["en:text"]
        self.assertEqual(g.ergebnis["ergebnis"], "stopp", g.bericht())

    @unittest.skipUnless(shutil.which("java") and os.path.exists(B.EPUBCHECK), "epubcheck/Java fehlt")
    def test_echtes_epubcheck(self):
        B.epubcheck = self.alt[4]
        g = self.lauf(stage="630")["de:text"]
        ec = self.man()["de:text"]["metriken"]["epubcheck"]
        self.assertEqual(g.ergebnis["ergebnis"], "auto", (g.bericht(), ec))
        self.assertTrue(ec["werkzeug"])
        self.assertEqual(ec["fehler"], 0, ec)

    @unittest.skipUnless(shutil.which("java") and os.path.exists(B.EPUBCHECK), "epubcheck/Java fehlt")
    def test_echtes_epubcheck_audio_und_anhang(self):
        B.epubcheck = self.alt[4]
        self.audio_werk()
        import pipeline.s615_cover_final as s615
        alt = s615.sprecher
        s615.sprecher = lambda w, lg: "Read by X"
        try:
            g = self.lauf("a", stage="630")["de:audio"]
        finally:
            s615.sprecher = alt
        self.assertEqual(g.ergebnis["ergebnis"], "auto", (g.bericht(), g.metriken.get("epubcheck_meldungen")))
        img = os.path.join(self.r, "w", "images", "anhang", "bild-1.png")
        os.makedirs(os.path.dirname(img))
        Image.new("RGB", (10, 10)).save(img)
        self.werk("w", anhang={"bilder": [{"nr": 1, "datei": "images/anhang/bild-1.png", "kapitel": 1,
                                           "nach_absatz": 1, "alt": "", "bildunterschrift": ""}],
                               "fussnoten": [{"nr": 1, "text": "A note.", "kapitel": 1, "absatz": 0}]})
        g = self.lauf()["en:text"]
        self.assertEqual(g.ergebnis["ergebnis"], "auto", (g.bericht(), g.metriken.get("epubcheck_meldungen")))


if __name__ == "__main__":
    unittest.main()
