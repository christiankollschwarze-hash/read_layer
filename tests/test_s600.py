"""Stage 600 Klappentext.  py -3.11 -m unittest tests.test_s600"""
import contextlib, io, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import api_layer
from pipeline import status as S
from pipeline import s600_klappentext as P

SAETZE_EN = ["Margaret walked slowly to the old house by the river.",
             "The door was open, and the wind was very cold that night.",
             "She knocked twice at the door, but nobody came to open it.",
             "Inside, the clocks had all stopped at the same minute."]
SAETZE_DE = ["Margarete ging langsam zu dem alten Haus am Fluss.",
             "Die Tür war offen, und der Wind war sehr kalt in jener Nacht.",
             "Sie klopfte zweimal an die Tür, aber niemand kam, um sie zu öffnen.",
             "Drinnen waren alle Uhren in derselben Minute stehen geblieben."]
ZITAT = SAETZE_EN[1] + " " + SAETZE_EN[2]
EINORD = {"en": "A quiet ghost story about a house where time stands still and the wind keeps its secrets.",
          "de": "Eine leise Geistergeschichte über ein Haus, in dem die Zeit stillsteht und der Wind seine Geheimnisse hütet."}
AUTOR = {"en": "The author was born in 1850 and wrote many stories about the sea and the old houses of the coast.",
         "de": "Der Autor wurde 1850 geboren und schrieb viele Geschichten über das Meer und die alten Häuser der Küste."}
EPUB_KT = "Two sisters live in an old house by the river. Their mirror has started to keep its own time."


class T600(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.tmp.name
        self.d = os.path.join(r, "w")
        os.makedirs(os.path.join(self.d, "work"))
        self.alt = (config.book_dir, config.work_dir, config.RUN_MODE, api_layer.call_model, config.BASE_DIR,
                    P.autor_laden)
        config.book_dir = lambda b: self.d
        config.work_dir = lambda b: os.path.join(self.d, "work")
        config.BASE_DIR = r
        config.RUN_MODE = "live"
        P.autor_laden = lambda w: dict(self.autor)
        self.autor = {"name_display": "Jane Doe", "verified": True, "geburtsjahr": 1850, "todesjahr": 1910}
        self.aufrufe = []
        self.meta = {"genre": "Geistergeschichte", "ton": "leise", "essenz": "Ein Haus, in dem die Zeit steht.",
                     "leseprobe_zitat": ZITAT, "sicherheit": "unkritisch", "hauptfigur_geschlecht": "weiblich",
                     "hauptfiguren": ["Margaret"]}
        self.einord = [dict(EINORD)]
        self.autor_b = [dict(AUTOR)]
        self.ueb = None                  # Uebersetzer: Funktion (satz, lg) -> text

        def fake(task, prompt, **kw):
            if "Analysiere und fuelle das Schema" in prompt:
                self.aufrufe.append("meta")
                return json.dumps(self.meta, ensure_ascii=False)
            if "Schreibe die Bloecke" in prompt:
                self.aufrufe.append("bloecke")
                return json.dumps({"einordnung": self.einord, "autor": self.autor_b}, ensure_ascii=False)
            if "Saetze (JSON-Liste)" in prompt:
                self.aufrufe.append("uebersetzen")
                lst = json.loads(prompt.split("Saetze (JSON-Liste):\n", 1)[1].split("\n\nAntworte")[0])
                f = self.ueb or (lambda s, lg: "Deutsch: Das ist die Übersetzung von dem Satz und er ist gut.")
                return json.dumps({"de": [f(s, "de") for s in lst]}, ensure_ascii=False)
            raise AssertionError(prompt[:200])
        api_layer.call_model = fake
        self.werk()

    def tearDown(self):
        (config.book_dir, config.work_dir, config.RUN_MODE, api_layer.call_model, config.BASE_DIR,
         P.autor_laden) = self.alt
        self.tmp.cleanup()

    def werk(self, mandant="somnio", quelle="gutenberg", fassung="modernisiert", gates=True, **extra):
        b = {"book_slug": "w", "quelle": quelle, "quellsprache": "en", "fassung": fassung, "mandant": mandant,
             "titel_original": "The House", "produkte": [{"sprache": "de", "inhalt": "text", "kanaele": ["taella"]}],
             "rechte": {"art": "gemeinfrei", "bearbeitung": True, "versichert": {"wer": "t", "wann": "x"}}}
        b.update(extra)
        with open(os.path.join(self.d, "book.json"), "w", encoding="utf-8") as f:
            json.dump(b, f, ensure_ascii=False)
        with open(os.path.join(self.d, "raw_modernized.txt"), "w", encoding="utf-8") as f:
            f.write("###TITLE### The House\n###CHAPTER### 1\n" + " ".join(SAETZE_EN) + "\n")
        content = {f"c001_{i + 1:05d}_s": {"type": "s", "en": e, "de": d}
                   for i, (e, d) in enumerate(zip(SAETZE_EN, SAETZE_DE))}
        with open(os.path.join(self.d, "work", "330_rueckuebersetzung.json"), "w", encoding="utf-8") as f:
            json.dump({"book_id": "w", "meta": {}, "content": content}, f, ensure_ascii=False)
        if gates:
            S.ergebnis("w", "190", "auto", wer="test")
            S.ergebnis("w", "330", "auto", wer="test")

    def lauf(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return P.run("w", wer="test", **kw)

    def aus(self):
        with open(os.path.join(self.d, "work", "600_klappentext.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_erzeugen_auto_koeder_aus_330_vermerk_hash(self):
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        a = self.aus()
        self.assertEqual([k["de"] for k in a["blurb"]["koeder"]], SAETZE_DE[1:3])
        self.assertEqual(a["meta"]["koeder_ids"], ["c001_00002_s", "c001_00003_s"])
        self.assertEqual(a["vermerke"]["modernisiert"]["de"], "Sanft modernisierte Fassung.")
        self.assertEqual(a["meta"]["genre_gruppe"], "Horror")
        self.assertEqual(a["herkunft"], "erzeugt")
        self.assertEqual(self.aufrufe, ["meta", "bloecke"])
        self.lauf()
        self.assertEqual(self.aufrufe, ["meta", "bloecke"])          # Eingangs-Hash: 0 $
        self.assertEqual(S.zustand("w", "600"), "frei")

    def test_teil_vermerk_und_original(self):
        self.werk(fassung="original", teil=2, teile_gesamt=3,
                  rechte={"art": "gemeinfrei", "bearbeitung": False, "versichert": {"wer": "t", "wann": "x"}})
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        v = self.aus()["vermerke"]
        self.assertNotIn("modernisiert", v)
        self.assertEqual(v["teil"], {"en": "Part 2 of 3.", "de": "Teil 2 von 3."})

    def test_sprache_nachuebersetzt(self):
        self.einord = [{"en": EINORD["en"], "de": EINORD["en"]}]
        self.ueb = lambda s, lg: EINORD["de"]
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(self.aus()["blurb"]["einordnung"][0]["de"], EINORD["de"])
        self.assertIn("uebersetzen", self.aufrufe)
        self.assertTrue(any("nachuebersetzt" in h for h in g.ergebnis["hinweise"]))

    def test_sprache_bleibt_falsch_mensch(self):
        self.einord = [{"en": EINORD["en"], "de": EINORD["en"]}]
        self.ueb = lambda s, lg: s
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertEqual(self.aufrufe.count("uebersetzen"), 1)

    def test_lizenztext_neu_dann_mensch(self):
        self.einord = [{"en": "Read it free at www.gutenberg.org today, it is a fine story.",
                        "de": "Lies es kostenlos auf www.gutenberg.org, es ist eine schöne Geschichte."}]
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertEqual(self.aufrufe, ["meta", "bloecke", "meta", "bloecke"])

    def test_koeder_nicht_woertlich_neu(self):
        self.meta["leseprobe_zitat"] = "This passage does not appear anywhere in the whole book at all."
        aufrufe = []

        def meta_wechsel():
            aufrufe.append(1)
            if len(aufrufe) > 1:
                self.meta["leseprobe_zitat"] = ZITAT
        alt = api_layer.call_model

        def fake(task, prompt, **kw):
            if "Analysiere" in prompt:
                meta_wechsel()
            return alt(task, prompt, **kw)
        api_layer.call_model = fake
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(self.aufrufe.count("meta"), 2)

    def test_koeder_manuell_waehlen(self):
        self.meta["leseprobe_zitat"] = "Nicht im Text vorhanden, ganz und gar nicht im Werk zu finden."
        with contextlib.redirect_stdout(io.StringIO()):
            g = P.run("w", wer="test", koeder=SAETZE_EN[3])
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(self.aus()["blurb"]["koeder"][0]["de"], SAETZE_DE[3])

    def test_autor_jahr_ungedeckt_mensch_110(self):
        self.autor = {"name_display": "Jane Doe", "verified": True, "geburtsjahr": 1851}
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertEqual(g.ergebnis["ruecksprung"], "110")

    def test_autor_ort_ungedeckt(self):
        self.autor_b = [{"en": "Jane Doe was born in 1850 in Liverpool and wrote about the sea.",
                         "de": "Jane Doe wurde 1850 in Liverpool geboren und schrieb über das Meer."}]
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertTrue(any("Liverpool" in x for x in g.ergebnis["gruende"]))

    def test_sicherheit_mensch(self):
        self.meta["sicherheit"] = "pruefen"
        self.assertEqual(self.lauf().ergebnis["ergebnis"], "mensch")

    def test_markup_entfernt(self):
        self.einord = [{"en": "A _quiet_ ghost story -- about a *house* where time stands still and the wind waits.",
                        "de": "Eine _leise_ Geistergeschichte -- über ein *Haus*, in dem die Zeit stillsteht und der Wind wartet."}]
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        t = self.aus()["blurb"]["einordnung"][0]["de"]
        self.assertNotIn("_", t)
        self.assertNotIn("*", t)
        self.assertIn("–", t)

    def test_uebernehmen_user_epub(self):
        self.werk(quelle="user_epub", fassung="original", klappentext={"en": EPUB_KT},
                  rechte={"art": "eigene", "bearbeitung": False, "versichert": {"wer": "t", "wann": "x"}})
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        a = self.aus()
        self.assertEqual(a["modus"], "uebernehmen")
        self.assertEqual(a["herkunft"], "epub")
        self.assertEqual([s["en"] for s in a["blurb"]["einordnung"]],
                         ["Two sisters live in an old house by the river.",
                          "Their mirror has started to keep its own time."])
        self.assertEqual(a["blurb"]["koeder"], [])
        self.assertEqual(self.aufrufe, ["meta", "uebersetzen"])

    def test_erzeugen_user_epub_immer_mensch(self):
        self.werk(quelle="user_epub", fassung="original",
                  rechte={"art": "eigene", "bearbeitung": False, "versichert": {"wer": "t", "wann": "x"}})
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertEqual(self.aus()["blurb"]["autor"], self.autor_b and self.aus()["blurb"]["autor"])

    def test_verlag_ohne_klappentext_stopp(self):
        self.werk(mandant="verlag:v1", quelle="verlag_epub", fassung="original",
                  rechte={"art": "verlag", "bearbeitung": False, "versichert": {"wer": "t", "wann": "x"}})
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual(g.ergebnis["ruecksprung"], "150")
        self.assertEqual(self.aufrufe, [])

    def test_verlag_uebernehmen_immer_mensch(self):
        self.werk(mandant="verlag:v1", quelle="verlag_epub", fassung="original", klappentext={"en": EPUB_KT},
                  rechte={"art": "verlag", "bearbeitung": False, "versichert": {"wer": "t", "wann": "x"}})
        self.assertEqual(self.lauf().ergebnis["ergebnis"], "mensch")

    def test_gate_330_nicht_frei_stopp(self):
        os.remove(S.pfad("w"))
        S.ergebnis("w", "190", "auto", wer="test")
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual(g.ergebnis["ruecksprung"], "330")
        self.assertEqual(self.aufrufe, [])

    def test_genre_unbekannt_hinweis_und_manuell(self):
        self.meta["genre"] = "Unerhoerte Gattung"
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto")
        self.assertEqual(self.aus()["meta"]["genre_gruppe"], "Sonstiges")
        self.assertTrue(any("nicht in Liste" in h for h in g.ergebnis["hinweise"]))
        self.lauf(genre="Abenteuerroman")
        self.assertEqual(self.aus()["meta"]["genre_gruppe"], "Abenteuer")
        self.assertEqual(self.aufrufe.count("meta"), 1)

    def test_ersetzen_und_mensch_freigabe_gilt(self):
        self.meta["sicherheit"] = "pruefen"
        self.assertEqual(self.lauf().ergebnis["ergebnis"], "mensch")
        S.entscheiden("w", "600", "frei", "test", "ok", rolle="admin")
        self.assertEqual(self.lauf().ergebnis["ergebnis"], "auto")
        neu = "Eine stille Geschichte über ein Haus am Fluss, in dem die Zeit für immer stehen geblieben ist."
        g = self.lauf(ersetzen={("einordnung", 0, "de"): neu})
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")              # Ausgabe geaendert -> neu freigeben
        self.assertEqual(self.aus()["blurb"]["einordnung"][0]["de"], neu)

    def test_genre_gruppen(self):
        self.assertEqual(P.genre_gruppe("Literarische Phantastik"), ("Fantastik", True))
        self.assertEqual(P.genre_gruppe("Kriminalroman"), ("Krimi", True))
        self.assertEqual(P.genre_gruppe(""), ("Sonstiges", False))

    def test_mock_dann_live_neu(self):
        config.RUN_MODE = "mock"
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(self.aufrufe, [])
        config.RUN_MODE = "live"
        S.ergebnis("w", "190", "auto", wer="test")
        S.ergebnis("w", "330", "auto", wer="test")
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(self.aufrufe, ["meta", "bloecke"])

    def test_trocken_ohne_bestand(self):
        g = self.lauf(trocken=True)
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertFalse(os.path.exists(os.path.join(self.d, "work", "600_klappentext.json")))


if __name__ == "__main__":
    unittest.main()
