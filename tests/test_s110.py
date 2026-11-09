"""Stage 110 Wikidata.  py -3.11 -m unittest tests.test_s110"""
import contextlib, io, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import status as S
from pipeline import s110_wikidata as W

REG = {"standard": "CK", "nutzer": {"CK": {"rolle": "admin"}}, "mandanten": {}}


def zeit(j):
    return [{"mainsnak": {"datavalue": {"value": {"time": f"+{j}-01-01T00:00:00Z"}}}}]


def person(name, geb, tod):
    return {"labels": {"en": {"value": name}}, "descriptions": {"en": {"value": "writer"}},
            "claims": {"P569": zeit(geb), "P570": zeit(tod)}, "sitelinks": {"enwiki": {"title": name}}}


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.tmp.name
        self.alt = (config.author_dir, config.book_dir, config.work_dir, config.INDEX_PATH,
                    W._api_get, W._fallback_title)
        config.author_dir = lambda a: os.path.join(r, "authors", a)
        self.dir = os.path.join(r, "authors", "london-j", "books", "call-of-the-wild")
        os.makedirs(os.path.join(self.dir, "work"))
        config.book_dir = lambda b: self.dir
        config.work_dir = lambda b: os.path.join(self.dir, "work")
        config.INDEX_PATH = os.path.join(r, "index.json")
        json.dump({"books": {"call-of-the-wild": "london-j"}, "authors": {"london-j": ""}},
                  open(config.INDEX_PATH, "w"))
        json.dump({"name_display": "Jack London", "todesjahr": 1916, "verified": False},
                  open(os.path.join(r, "authors", "london-j", "author.json"), "w"))
        json.dump({"book_slug": "call-of-the-wild", "author_slug": "london-j", "quelle": "gutenberg",
                   "quellsprache": "en", "titel_original": "The Call of the Wild", "gutenberg_id": 215,
                   "fassungen": []}, open(os.path.join(self.dir, "book.json"), "w"))
        self.ents = {"Q45765": person("Jack London", 1876, 1916),
                     "Q1": person("Jack London Smith", 1900, 1980),
                     "Q2": person("Jack London", 1876, 1917),
                     "Q9": person("Jack London", 1950, 1990),
                     "Q215": {"labels": {"en": {"value": "The Call of the Wild"}},
                              "descriptions": {"en": {"value": "1903 novel by Jack London"}},
                              "claims": {"P577": zeit(1903)},
                              "sitelinks": {"enwiki": {"title": "The Call of the Wild"},
                                            "dewiki": {"title": "Ruf der Wildnis (Roman)"}}}}
        self.autoren = ["Q45765", "Q1"]
        self.werke = ["Q215"]
        self.fehler = None

        def api(params):
            if self.fehler:
                raise self.fehler
            if params["action"] == "wbsearchentities":
                ids = self.autoren if "London" in params["search"] and "Wild" not in params["search"] else self.werke
                return {"search": [{"id": i, "label": W._label_of(self.ents[i])} for i in ids]}
            return {"entities": {i: self.ents.get(i, {}) for i in params["ids"].split("|")}}
        W._api_get = api
        W._fallback_title = lambda t, lg: f"[{lg}] {t}"
        reg = os.path.join(r, "rollen.json")
        json.dump(REG, open(reg, "w"))
        os.environ["READLAYER_ROLLEN"] = reg
        os.environ.pop("READLAYER_NUTZER", None)

    def tearDown(self):
        (config.author_dir, config.book_dir, config.work_dir, config.INDEX_PATH,
         W._api_get, W._fallback_title) = self.alt
        os.environ.pop("READLAYER_ROLLEN", None)
        self.tmp.cleanup()

    def lauf(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return W.run("call-of-the-wild", jahr=2026, **kw)

    def aj(self):
        return json.load(open(os.path.join(config.author_dir("london-j"), "author.json")))

    def bj(self):
        return json.load(open(os.path.join(self.dir, "book.json")))

    def titel(self):
        return {f["sprache"]: (f["titel"], f["titel_quelle"]) for f in self.bj()["fassungen"]}

    def gruende(self):
        return " ".join(S.laden("call-of-the-wild")["stages"]["110"]["gate"]["gruende"])

    def test_eindeutig_auto(self):
        self.assertEqual(self.lauf(), "auto")
        self.assertTrue(self.aj()["verified"])
        self.assertEqual(self.aj()["wikidata_id"], "Q45765")
        self.assertEqual(self.titel(), {"en": ("The Call of the Wild", "original"),
                                        "de": ("Ruf der Wildnis", "wikidata")})
        self.assertEqual(self.bj()["erscheinungsjahr"], 1903)
        self.assertEqual(json.load(open(config.INDEX_PATH))["authors"]["london-j"], "Q45765")

    def test_mehrdeutig_mensch_dann_qid(self):
        self.autoren = ["Q45765", "Q2"]
        self.assertEqual(self.lauf(), "mensch")
        self.assertIn("2 Treffer", self.gruende())
        self.assertFalse(self.aj()["verified"])
        self.assertEqual(self.lauf(autor_qid="Q45765"), "auto")

    def test_pd_verletzt_stopp(self):
        json.dump({"name_display": "Jack London", "todesjahr": 1990}, open(
            os.path.join(config.author_dir("london-j"), "author.json"), "w"))
        self.autoren = ["Q9"]
        self.assertEqual(self.lauf(), "stopp")
        self.assertEqual(S.laden("call-of-the-wild")["stages"]["110"]["gate"]["ruecksprung"], "100")

    def test_kein_werk_mensch_titel_regler(self):
        self.werke = []
        self.assertEqual(self.lauf(), "mensch")
        self.assertEqual(self.titel()["de"], ("[de] The Call of the Wild", "llm"))
        self.assertEqual(self.lauf(titel={"de": "Der Ruf der Wildnis"}), "auto")
        self.assertEqual(self.titel()["de"], ("Der Ruf der Wildnis", "manuell"))

    def test_de_titel_gleich_original_mensch(self):
        self.ents["Q215"]["sitelinks"]["dewiki"] = {"title": "The Call of the Wild"}
        self.assertEqual(self.lauf(), "mensch")
        self.assertEqual(self.titel()["de"][1], "llm")

    def test_netzfehler_stopp(self):
        self.fehler = OSError("keine Verbindung")
        self.assertEqual(self.lauf(), "stopp")
        self.assertIn("neu abfragen", self.gruende())

    def test_verifiziert_titel_da_keine_abfrage(self):
        self.assertEqual(self.lauf(), "auto")
        self.fehler = OSError("darf nicht abgefragt werden")
        self.assertEqual(self.lauf(), "auto")


    def test_nachweis_hebt_pd_stopp_auf_und_kandidaten(self):
        json.dump({"name_display": "Jack London", "todesjahr": 1990}, open(
            os.path.join(config.author_dir("london-j"), "author.json"), "w"))
        self.autoren = ["Q9", "Q1"]
        self.assertEqual(self.lauf(), "stopp")
        k = json.load(open(os.path.join(self.dir, "work", "110_kandidaten.json")))
        self.assertEqual([c["wikidata_id"] for c in k["autor"]], ["Q9", "Q1"])
        self.assertTrue(k["autor"][0]["treffer"])
        self.assertEqual(self.lauf(nachweis={"art": "rechteinhaber", "rechte_art": "lizenz", "deckt": ["autor"]}), "auto")


if __name__ == "__main__":
    unittest.main()
