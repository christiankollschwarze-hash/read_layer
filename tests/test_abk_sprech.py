"""Abkuerzungen sprechen (Stage 400, REGELN_V 4) + Abgleich Satzgrenzen 200.  py -3.11 -m unittest tests.test_abk_sprech
Synthetische Werke; the-art-of-war nur als Muster der Faelle."""
import contextlib, io, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import status as S
from pipeline import s400_regie as P
from pipeline import sprechtext as ST
from tools import satzweise

CFG = os.path.dirname(os.path.abspath(config.__file__))


def sp(t, lg="en", **kw):
    return ST.sprechtext(t, lg, "s", **kw)


class TRegeln(unittest.TestCase):
    def test_en(self):
        self.assertEqual(sp("See the Chronicle, ch. 65."), "See the Chronicle, chapter sixty-five.")
        self.assertEqual(sp("See ch. IV and chap. xii."), "See chapter four and chapter twelve.")
        self.assertEqual(sp("Ch. 3 opens it."), "Chapter three opens it.")
        self.assertEqual(sp("p. 12 and pp. 12–14"), "page twelve and pages twelve to fourteen")
        self.assertEqual(sp("Classics, vol. V, p. xii."), "Classics, volume five, page twelve.")
        self.assertEqual(sp("i.e. the river, e.g. the sea"), "that is the river, for example the sea")
        self.assertEqual(sp("[I.e., the river]"), "[That is, the river]")
        self.assertEqual(sp("Cf. the other note."), "Compare the other note.")
        self.assertEqual(sp("op. cit. and loc. cit. and ibid."), "in the work cited and in the place cited and in the same place.")
        self.assertEqual(sp("ed. Legge, tr. Giles"), "edited by Legge, translated by Giles")
        self.assertEqual(sp("Life of Jackson, 1902 ed., vol. II"), "Life of Jackson, 1902 edition, volume two")
        self.assertEqual(sp("Henderson, vol. I. p. 4."), "Henderson, volume one, page four.")
        self.assertEqual(sp("Thucydides, 78 sqq. and 5 ff."), "Thucydides, 78 and following and 5 and following.")

    def test_satzende_und_komma(self):
        self.assertEqual(sp("salt, rice, etc."), "salt, rice, et cetera.")
        self.assertEqual(sp('"salt, rice, etc."]'), '"salt, rice, et cetera."]')
        self.assertEqual(sp("salt, etc., and rice"), "salt, et cetera, and rice")
        self.assertEqual(sp("as in chap."), "as in chapter.")

    @unittest.skipIf(ST._n2w is None, "num2words fehlt")
    def test_grosse_zahlen_bereich(self):
        self.assertEqual(sp("Tien, ch. 148-162."), "Tien, chapters one hundred and forty-eight to one hundred and sixty-two.")
        self.assertEqual(sp("vol. II, p. 490"), "volume two, page four hundred and ninety")

    def test_de(self):
        self.assertEqual(sp("Vgl. S. 12 ff. und Kap. 3.", "de"), "Vergleiche Seite zwölf folgende und Kapitel drei.")
        self.assertEqual(sp("z. B. hier, d. h. dort usw.", "de"), "zum Beispiel hier, das heißt dort und so weiter.")
        self.assertEqual(sp("Bd. 2, S. 12–14, Anm. 3", "de"), "Band zwei, Seiten zwölf bis vierzehn, Anmerkung drei")
        self.assertEqual(sp("hrsg. von Meier, Hg. Huber", "de"), "herausgegeben von Meier, herausgegeben Huber")
        self.assertEqual(sp("Kap. IV beginnt", "de"), "Kapitel vier beginnt")
        self.assertEqual(sp("Seite 12 f. lesen", "de"), "Seite 12 folgende lesen")

    def test_mehrdeutig_befund(self):
        for t in ("(ch. 99, f. 1) remarks", "the p. was here", "the ed. said", "ch. 34, ff. 4, 5"):
            s = sp(t)
            self.assertTrue(ST.abk_offen(s, "en"), (t, s))
        self.assertEqual(sp("(ch. 99, f. 1)"), "(chapter ninety-nine, f. 1)")
        # Initiale vor Name ist kein Befund
        self.assertEqual(ST.abk_offen(sp("J. S. Bach schrieb", "de"), "de"), [])
        self.assertEqual(ST.abk_offen(sp("by P. Smith"), "en"), [])
        # kein Fehlalarm in normalen Woertern
        self.assertEqual(sp("He stopped. If ever, then up."), "He stopped. If ever, then up.")
        self.assertEqual(ST.abk_offen("He stopped. If ever, then up.", "en"), [])

    @unittest.skipIf(ST._n2w is None, "num2words fehlt")
    def test_ordinal_erweitert(self):
        self.assertEqual(sp("the 6th day", erweitert=True), "the sixth day")

    def test_abbildung(self):
        t = "See p. 12 now."
        s, abb = ST.sprechtext_abb(t, "en", "s")
        self.assertEqual(s, "See page twelve now.")
        i = s.index("page twelve")
        self.assertEqual(ST.lesespan(abb, i, i + 11, len(s)), (t.index("p."), t.index("12") + 2))
        j = s.index("now")
        self.assertEqual(ST.lesespan(abb, j, j + 3, len(s)), (t.index("now"), t.index("now") + 3))

    def test_werktabelle(self):
        tab = ST.abk_tabelle("en", {"en": [{"abk": "f.", "wort": "folio", "bedingung": "zahl", "zahl_sprechen": True},
                                           {"abk": "fol.", "wort": "folio", "zahl_sprechen": True}]})
        self.assertEqual(sp("(ch. 99, f. 1) and 12 f.", abk=tab), "(chapter ninety-nine, folio one) and 12 and the following.")
        self.assertEqual(sp("fol. 3", abk=tab), "folio three")
        aus = ST.abk_tabelle("en", {"en": {"etc.": ""}})
        self.assertEqual(sp("salt, etc.", abk=aus), "salt, etc.")
        self.assertEqual(ST.abk_offen("salt, etc.", "en", aus), [])
        with self.assertRaises(ValueError):
            ST.abk_tabelle("en", {"en": [{"abk": "x.", "wort": "y", "bedingung": "quatsch"}]})


class TAbgleich200(unittest.TestCase):
    """Jede Sprech-Abkuerzung trennt in 200 keinen Satz (satzweise.ABK + config/abk_<lg>.txt)."""

    def test_listen(self):
        for lg in ("en", "de"):
            with open(os.path.join(CFG, f"abk_{lg}.txt"), encoding="utf-8") as f:
                txt = {z.strip().lower() for z in f if z.strip() and not z.startswith("#")}
            bekannt = satzweise.ABK | txt
            for e in ST.abk_eintraege_lesen(lg):
                for teil in (t.strip().lower() for t in e["abk"].split(".") if t.strip()):
                    if len(teil) > 1:
                        self.assertIn(teil, bekannt, f"{lg}: {e['abk']} fehlt in 200")

    def test_satz_zerfaellt_nicht(self):
        abk = [z.strip() for z in open(os.path.join(CFG, "abk_en.txt"), encoding="utf-8")
               if z.strip() and not z.startswith("#")]
        for t in ("It is given at the beginning of chap. XI, but occurs later.", "See vol. II, p. 4 there.",
                  "Henderson, op. cit. Vol. I, p. 426.", "See ibid. Section 4 again.", "Cf. ed. Legge for this."):
            self.assertEqual(satzweise.teile_text(t, "en", abk), [t], t)
        self.assertEqual(satzweise.teile_text("Vgl. Anm. Drei hier. Dann weiter.", "de",
                                              ["anm", "hg", "hrsg", "f", "ff"]),
                         ["Vgl. Anm. Drei hier.", "Dann weiter."])


Q = {"c001_00001_h": ("h", "Chapter I", "Kapitel I"),
     "c001_00002_s": ("s", "See ch. 65 and p. 12.", "Siehe Kap. 65 und S. 12 ff."),
     "c001_00003_s": ("s", "The note (f. 1) is old.", "Die Notiz ist alt, vgl. Anm. 2.")}


class T400Abk(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.tmp.name
        self.d = os.path.join(r, "a", "books", "w")
        os.makedirs(os.path.join(self.d, "work"))
        self.alt = (config.book_dir, config.work_dir, config.RUN_MODE, config.BASE_DIR)
        config.book_dir = lambda b: self.d
        config.work_dir = lambda b: os.path.join(self.d, "work")
        config.BASE_DIR = r
        config.RUN_MODE = "live"
        with open(os.path.join(r, "a", "author.json"), "w", encoding="utf-8") as f:
            json.dump({"name_display": "Jane Doe", "wirkungssprache": "en"}, f)
        b = {"book_slug": "w", "quelle": "gutenberg", "quellsprache": "en", "fassung": "original",
             "mandant": "somnio", "titel_original": "The House", "fassungen": [{"sprache": "de", "titel": "Das Haus"}],
             "produkte": [{"sprache": "en", "inhalt": "hoerbuch", "stufe": "basic", "kanaele": ["taella"]},
                          {"sprache": "de", "inhalt": "hoerbuch", "stufe": "basic", "kanaele": ["taella"]}],
             "rechte": {"art": "gemeinfrei", "bearbeitung": True, "versichert": {"wer": "t", "wann": "x"}}}
        with open(os.path.join(self.d, "book.json"), "w", encoding="utf-8") as f:
            json.dump(b, f)
        data = {"book_id": "w", "meta": {"profile": {}, "title": "The House"},
                "content": {k: {"type": t, "en": q, "de": z} for k, (t, q, z) in Q.items()}}
        with open(os.path.join(self.d, "work", "330_rueckuebersetzung.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        for g in ("330", "340"):
            S.ergebnis("w", g, "auto", wer="test")

    def tearDown(self):
        (config.book_dir, config.work_dir, config.RUN_MODE, config.BASE_DIR) = self.alt
        self.tmp.cleanup()

    def lauf(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return P.run("w", wer="test", **kw)

    def test_gate_und_werktabelle(self):
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch", g.bericht())
        f = g.pruef["en"]["fehler"]["abkuerzung"]
        self.assertEqual([x["id"] for x in f], ["c001_00003_s"])
        self.assertEqual(g.pruef["de"]["fehler"]["abkuerzung"], [])
        with open(os.path.join(self.d, "work", "400_regie.json"), encoding="utf-8") as fh:
            d = json.load(fh)
        p = d["production"]["sprechtext"]
        self.assertEqual(p["c001_00002_s"]["en"], "See chapter sixty-five and page twelve.")
        self.assertEqual(p["c001_00002_s"]["de"], "Siehe Kapitel fünfundsechzig und Seite zwölf folgende.")
        self.assertEqual(p["c001_00003_s"]["de"], "Die Notiz ist alt, vergleiche Anmerkung zwei.")
        self.assertEqual(d["meta"]["regie"]["regeln_v"], 5)
        # in die Werktabelle uebernehmen -> auto
        g = self.lauf(abk_sprech=["en:f.=folio"])
        with open(os.path.join(self.d, "book.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["abk_sprech"], {"en": [{"abk": "f.", "wort": "folio"}]})
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        with open(os.path.join(self.d, "work", "400_regie.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["production"]["sprechtext"]["c001_00003_s"]["en"], "The note (folio one) is old.")
        # loeschen
        self.lauf(abk_sprech=["en:f.=-"])
        with open(os.path.join(self.d, "book.json"), encoding="utf-8") as fh:
            self.assertFalse(json.load(fh).get("abk_sprech"))

    def test_cli_fehler(self):
        with self.assertRaises(ValueError):
            P.abk_werk_setzen({}, ["f.=folio"])
        with self.assertRaises(ValueError):
            P.abk_werk_setzen({}, ["xx:f.=folio"])
        self.assertEqual(P.abk_werk_setzen({"en": [{"abk": "f.", "wort": "a", "bedingung": "zahl"}]}, ["en:f.=b"]),
                         {"en": [{"bedingung": "zahl", "abk": "f.", "wort": "b"}]})
        self.assertEqual(P.abk_werk_setzen({"en": [{"abk": "f.", "wort": "a"}]}, ["en:f.=-"]), {})


if __name__ == "__main__":
    unittest.main()
