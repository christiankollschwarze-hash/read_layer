"""Stage 610 Cover.  py -3.11 -m unittest tests.test_s610"""
import contextlib, io, json, os, shutil, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image, ImageDraw, ImageFont
from config import config
from pipeline import status as S
from pipeline import s610_cover as P

BG = P.BG_COLOR


def bild(w=1024, h=1536, motiv=0.7, bg=BG, text=None, fmt="PNG"):
    im = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(im)
    oben = h * (1 - motiv) / 2
    d.ellipse((w * 0.35, oben, w * 0.65, oben + h * motiv * 0.4), outline="black", width=12)
    d.line((w * 0.5, oben + h * motiv * 0.4, w * 0.5, oben + h * motiv), fill="black", width=12)
    if text:
        try:
            f = ImageFont.truetype("DejaVuSans-Bold.ttf", 90)
        except OSError:
            f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 90)
        d.text((w * 0.12, h * 0.05), text, fill="black", font=f)
    buf = io.BytesIO()
    im.save(buf, fmt)
    return buf.getvalue()


GUT, KLEIN = bild(), bild(motiv=0.3)


class T610(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.r = self.tmp.name
        self.alt = (config.book_dir, config.work_dir, config.RUN_MODE, config.author_of, P._api,
                    P.usage_log.log, P.time.sleep, getattr(config, "GEMINI_API_KEY", None))
        config.book_dir = lambda b: os.path.join(self.r, b)
        config.work_dir = lambda b: P.os.makedirs(os.path.join(self.r, b, "work"), exist_ok=True) or \
            os.path.join(self.r, b, "work")
        config.author_of = lambda b: ""
        config.RUN_MODE = "live"
        config.GEMINI_API_KEY = "x"
        P.usage_log.log = lambda *a, **k: None
        P.time.sleep = lambda s: None
        self.antworten = []                  # Liste von bytes | "text" | ("jpg", bytes)
        self.aufrufe = 0

        def api(prompt, model, key):
            self.aufrufe += 1
            self.prompt = prompt
            a = self.antworten.pop(0) if len(self.antworten) > 1 else self.antworten[0]
            if a == "text":
                return None, None, "I cannot draw that.", {}
            if isinstance(a, tuple):
                return a[1], "image/jpeg", "", {}
            return a, "image/png", "", {}
        P._api = api
        self.werk("w")

    def tearDown(self):
        (config.book_dir, config.work_dir, config.RUN_MODE, config.author_of, P._api,
         P.usage_log.log, P.time.sleep, config.GEMINI_API_KEY) = self.alt
        self.tmp.cleanup()

    def werk(self, w, mandant="somnio", quelle="gutenberg", gate600=True, **extra):
        os.makedirs(os.path.join(self.r, w, "work"), exist_ok=True)
        b = {"book_slug": w, "quelle": quelle, "gutenberg_id": 1, "quellsprache": "en", "fassung": "modernisiert",
             "mandant": mandant, "titel_original": "The House", "autor_name": "Jane Doe",
             "produkte": [{"sprache": "en", "inhalt": "text", "kanaele": ["taella"]}],
             "rechte": {"art": "gemeinfrei", "bearbeitung": True, "versichert": {"wer": "t", "wann": "x"}}}
        b.update(extra)
        with open(os.path.join(self.r, w, "book.json"), "w", encoding="utf-8") as f:
            json.dump(b, f)
        with open(os.path.join(self.r, w, "work", "600_klappentext.json"), "w", encoding="utf-8") as f:
            json.dump({"meta": {"ton": "leise", "genre": "Geistergeschichte"}}, f)
        if gate600:
            S.ergebnis(w, "600", "auto", wer="test")

    def lauf(self, w="w", **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return P.run(w, wer="test", **kw)

    def man(self, w="w"):
        return json.load(open(config.work_path(w, "610_cover"), encoding="utf-8"))

    def bild_ablegen(self, w, data, name="cover.png"):
        os.makedirs(os.path.join(self.r, w, "images"), exist_ok=True)
        with open(os.path.join(self.r, w, "images", name), "wb") as f:
            f.write(data)

    # ---------------------------------------------------------------- Erzeugen
    def test_erzeugt_auto_und_resume(self):
        self.antworten = [GUT]
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(self.aufrufe, 1)
        self.assertIn("Jane Doe", self.prompt)
        self.assertIn("leise, Geistergeschichte", self.prompt)
        m = self.man()
        self.assertEqual(m["herkunft"], "erzeugt")
        self.assertEqual(m["versuche"][0]["ergebnis"], "bild")
        self.assertEqual(S.zustand("w", "610"), "frei")
        g = self.lauf()
        self.assertEqual(self.aufrufe, 1)                 # unveraenderte Eingaenge -> kein Aufruf
        self.assertEqual(g.ergebnis["ergebnis"], "auto")

    def test_motiv_aendert_hash(self):
        self.antworten = [GUT]
        self.lauf()
        self.lauf(motiv="a lighthouse")
        self.assertEqual(self.aufrufe, 2)
        self.assertIn("The motif is: a lighthouse.", self.prompt)

    def test_rot_einmal_neu_dann_gruen(self):
        self.antworten = [KLEIN, GUT]
        g = self.lauf()
        self.assertEqual(self.aufrufe, 2)
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(g.metriken["reparatur"], 1)

    def test_rot_zweimal_mensch(self):
        self.antworten = [KLEIN]
        g = self.lauf()
        self.assertEqual(self.aufrufe, 2)
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertTrue(any("motiv_hoehe" in x for x in g.ergebnis["gruende"]))

    def test_nur_text_mensch(self):
        self.antworten = ["text"]
        g = self.lauf()
        self.assertEqual(self.aufrufe, P.VERSUCHE_TEXT)
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertIn("nur Text", g.ergebnis["gruende"][0])
        self.assertIsNone(P.bild_pfad("w"))
        self.assertEqual(len(self.man()["versuche"]), P.VERSUCHE_TEXT)

    def test_jpeg_ersetzt_png(self):
        self.bild_ablegen("w", GUT)
        self.antworten = [("jpg", bild(fmt="JPEG"))]
        self.lauf(neu=True)
        self.assertTrue(P.bild_pfad("w").endswith("cover.jpg"))
        self.assertFalse(os.path.exists(os.path.join(self.r, "w", "images", "cover.png")))
        self.lauf()
        self.assertEqual(self.aufrufe, 1)                 # .jpg wird erkannt

    # ---------------------------------------------------------- Gate-Faelle
    def test_gate600_stopp(self):
        self.werk("v", gate600=False)
        self.antworten = [GUT]
        g = self.lauf("v")
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual(g.ergebnis["ruecksprung"], "600")
        self.assertEqual(self.aufrufe, 0)

    def test_autor_pflicht(self):
        self.werk("v", autor_name="Unbekannt")
        g = self.lauf("v")
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual(g.ergebnis["ruecksprung"], "110")
        self.werk("e", autor_name="", rechte={"art": "eigene", "bearbeitung": True})
        self.antworten = [GUT]
        g = self.lauf("e")
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertIn(", a novel,", self.prompt)

    def test_mock_im_live_stopp(self):
        self.bild_ablegen("w", P.mock_bild())
        P.manifest.json_atomar(config.work_path("w", "610_cover"),
                               {"herkunft": "bestand", "bild_hash": P.manifest.hash_datei(P.bild_pfad("w"))})
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual(self.aufrufe, 0)

    def test_mock_lauf(self):
        config.RUN_MODE = "mock"
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertTrue(P.ist_mock(P.bild_pfad("w")))
        self.assertEqual(self.aufrufe, 0)
        config.RUN_MODE = "live"
        self.antworten = [GUT]
        g = self.lauf()                                   # Mock-Bild wird live ersetzt
        self.assertEqual(self.aufrufe, 1)
        self.assertEqual(g.ergebnis["ergebnis"], "auto")

    def test_altes_mock_png_erkannt(self):
        self.bild_ablegen("w", base64_1x1())
        self.assertTrue(P.ist_mock(P.bild_pfad("w")))

    # ------------------------------------------------------------- Herkunft
    def test_uebernahme_150_entfaellt(self):
        self.werk("u", quelle="user_epub", cover="images/cover_source.jpg")
        g = self.lauf("u")
        self.assertEqual(g.ergebnis["ergebnis"], "entfaellt")
        self.assertEqual(S.zustand("u", "610"), "entfaellt")
        self.assertEqual(self.man("u")["herkunft"], "epub")
        self.assertEqual(self.aufrufe, 0)

    def test_bestand_gutenberg(self):
        self.bild_ablegen("w", GUT)
        g = self.lauf()
        self.assertEqual(self.aufrufe, 0)
        self.assertEqual(g.metriken["herkunft"], "bestand")
        self.assertEqual(g.ergebnis["ergebnis"], "auto")

    def test_bestand_rot_neu(self):
        self.bild_ablegen("w", KLEIN)
        self.antworten = [GUT]
        g = self.lauf()
        self.assertEqual(self.aufrufe, 1)
        self.assertEqual(g.metriken["herkunft"], "erzeugt")

    def test_user_epub_ohne_manifest_erzeugt_und_mensch(self):
        self.werk("u", mandant="user:x", quelle="user_epub", cover="images/cover.png")
        self.bild_ablegen("u", GUT)                       # Platzhalter aus 150 wird nicht uebernommen
        self.antworten = [GUT]
        g = self.lauf("u")
        self.assertEqual(self.aufrufe, 1)
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        S.entscheiden("u", "610", "frei", wer="CK", grund="ok", rolle="admin")
        g = self.lauf("u")
        self.assertEqual(g.ergebnis["ergebnis"], "auto")  # Freigabe gilt bei gleichem bild_hash
        self.assertEqual(self.aufrufe, 1)

    def test_reihen_erbe(self):
        self.werk("r-1")
        self.bild_ablegen("r-1", GUT)
        self.werk("r-2", reihe="r", teil=2, teile_gesamt=2)
        g = self.lauf("r-2")
        self.assertEqual(g.metriken["herkunft"], "erbe")
        self.assertEqual(self.aufrufe, 0)
        self.assertEqual(g.ergebnis["ergebnis"], "auto")
        self.werk("s-2", reihe="s", teil=2)
        g = self.lauf("s-2")
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.antworten = [GUT]
        g = self.lauf("s-2", erbe="aus")
        self.assertEqual(g.metriken["herkunft"], "erzeugt")

    def test_upload(self):
        p = os.path.join(self.r, "eigen.png")
        open(p, "wb").write(GUT)
        g = self.lauf(bild=p)
        self.assertEqual(g.metriken["herkunft"], "upload")
        self.assertEqual(self.aufrufe, 0)
        g = self.lauf()
        self.assertEqual(g.metriken["herkunft"], "upload")

    def test_varianten_waehlen(self):
        self.antworten = [KLEIN, GUT]
        g = self.lauf(varianten=2)
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertIn("gruen: [2]", g.ergebnis["gruende"][0])
        g = self.lauf(waehle=2)
        self.assertEqual(g.metriken["herkunft"], "variante")
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())

    def test_trocken_schreibt_nichts(self):
        self.bild_ablegen("w", GUT)
        g = self.lauf(trocken=True)
        self.assertEqual(g.ergebnis["ergebnis"], "auto")
        self.assertFalse(os.path.exists(config.work_path("w", "610_cover")))
        self.assertNotEqual(S.zustand("w", "610"), "frei")

    # ---------------------------------------------------------- Bildmetriken
    def test_metriken(self):
        self.bild_ablegen("w", GUT)
        m = P.pruefen(P.bild_pfad("w"))
        self.assertEqual(P.rot_liste(m), [], m)
        self.bild_ablegen("w", bild(1024, 1024))
        self.assertIn("format", P.rot_liste(P.pruefen(P.bild_pfad("w"))))
        self.bild_ablegen("w", bild(bg="#808080"))
        self.assertIn("randfarbe", P.rot_liste(P.pruefen(P.bild_pfad("w"))))
        self.bild_ablegen("w", bild(600, 900))
        self.assertIn("breite", P.rot_liste(P.pruefen(P.bild_pfad("w"))))

    @unittest.skipUnless(shutil.which("tesseract"), "tesseract fehlt")
    def test_text_im_bild(self):
        self.bild_ablegen("w", bild(text="THE HOUSE"))
        m = P.pruefen(P.bild_pfad("w"))
        self.assertIn("text_im_bild", P.rot_liste(m), m)


def base64_1x1():
    import base64
    return base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAAB"
                            "JRU5ErkJggg==")


if __name__ == "__main__":
    unittest.main()
