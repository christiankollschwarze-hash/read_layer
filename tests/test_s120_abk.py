"""Stage 120 Schritt Abkuerzungen im Lesetext (Teil A2, 22.11.2026).  py -3.11 -m unittest tests.test_s120_abk
Synthetische Werke; the-art-of-war nur Muster."""
import json, os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import s120_abk as A
from pipeline import sprechtext as st
from tests import test_s120 as B
from tests.test_s120_fremd import FR1, FR2, roh_mit


class TLesetext(unittest.TestCase):
    def lt(self, s, lg="en", werk=None):
        return st.abk_lesetext(s, lg, st.abk_tabelle(lg, werk))

    def test_ziffern_bleiben(self):
        self.assertEqual(self.lt("See ch. 65 and pp. 12–14.")[0], "See chapter 65 and pages 12–14.")
        self.assertEqual(self.lt("Cf. chap. III, vol. I. p. 4.")[0], "Compare chapter III, volume I. page 4.")
        self.assertEqual(self.lt("Wars, sieges etc.")[0], "Wars, sieges et cetera.")
        self.assertEqual(self.lt("Siehe S. 12 ff. und S. 12–14, z. B. Kap. 3.", "de")[0],
                         "Siehe Seite 12 und folgende und Seiten 12–14, zum Beispiel Kapitel 3.")

    def test_bedingungen_wie_400(self):
        t, stellen, offen = self.lt("Ch. 34, ff. 4, 5 and f. 1; p. 12 f.; the letter p. was lost.")
        self.assertEqual([o["abk"] for o in offen], ["ff.", "f.", "p."])      # Folios, p. ohne Zahl -> Befund
        s = "Ch. 34, ff. 4, 5 and f. 1; p. 12 f.; the letter p. was lost."
        self.assertEqual([o["abk"] for o in offen], st.abk_offen(st.sprechtext(s, "en"), "en"))   # wie Gate 400
        self.assertIn("page 12 and the following", t)
        self.assertIn("the letter p. was lost", t)
        self.assertEqual(self.lt("J. S. Bach wrote.")[2], [])               # Initiale

    def test_werktabelle_und_bleibt(self):
        w = {"en": [{"abk": "f.", "wort": "folio", "plural": "folios", "bedingung": "zahl", "zahl_sprechen": True}]}
        t, stellen, offen = self.lt("See f. 1 and p. 3 f.", werk=w)
        self.assertEqual(t, "See folio 1 and page 3 and the following.")
        self.assertEqual([x["herkunft"] for x in stellen], ["werk", "sprache", "sprache"])
        self.assertEqual(self.lt("See ch. 4.", werk={"en": {"ch.": ""}})[0], "See ch. 4.")

    def test_hand_und_auslassen(self):
        s = "Folio f. 1 and f. 2."
        t, stellen, offen = st.abk_lesetext(s, "en", hand={("a" + "x", 9): "?"})
        self.assertEqual(len(offen), 2)
        key = offen[0]["key"]
        t, stellen, offen = st.abk_lesetext(s, "en", hand={(key, 0): "folio", (key, 1): ""})
        self.assertEqual(t, "Folio folio 1 and f. 2.")
        self.assertEqual((offen, stellen[0]["herkunft"]), ([], "hand"))
        self.assertEqual(st.abk_lesetext("Il dit p. 4 etc.", "en", auslassen=[(0, 16)])[0], "Il dit p. 4 etc.")

    def test_400_unveraendert(self):
        self.assertEqual(st.sprechtext("See pp. 12–14.", "en"), "See pages twelve to fourteen.")


class T120(unittest.TestCase):
    setUp, tearDown = B.T.setUp, B.T.tearDown
    werk, lauf, kap, gate = B.T.werk, B.T.lauf, B.T.kap, B.T.gate

    def abk(self):
        with open(A.pfad("w"), encoding="utf-8") as f:
            return json.load(f)

    def raw(self):
        with open(os.path.join(self.dir, "raw_modernized.txt"), encoding="utf-8") as f:
            return f.read()

    def test_modernisiert_ausschreiben_und_resume(self):
        self.werk(roh_mit("See ch. 65 and pp. 12–14, etc."))
        self.assertEqual(self.lauf(), "auto")
        self.assertIn("See chapter 65 and pages 12–14, et cetera.", self.raw())
        d = self.abk()
        self.assertTrue(d["aktiv"])
        self.assertEqual([s["wort"] for s in d["stellen"]], ["chapter", "pages", "et cetera."])
        k = self.kap(1)
        self.assertTrue(any("ch. 65" in p for p in k["paragraphs_vor_fremd"]))
        a = self.aufrufe
        self.assertEqual(self.lauf(), "auto")                               # Resume: Basis, kein LLM, gleiches Ergebnis
        self.assertEqual(self.aufrufe, a)
        self.assertIn("See chapter 65", self.raw())

    def test_original_unveraendert(self):
        self.werk(roh_mit("See ch. 65."), fassung="original")
        self.assertEqual(self.lauf(), "auto")
        self.assertIn("See ch. 65.", self.raw())
        self.assertFalse(self.abk()["aktiv"])
        self.assertNotIn("paragraphs_vor_fremd", self.kap(1))

    def test_befund_hand_werktabelle_ruecknahme(self):
        self.werk(roh_mit("Folio f. 1 and f. 2 and ch. 3."))
        self.assertEqual(self.lauf(), "mensch")
        g = self.gate()
        self.assertIn("abk_offen", json.dumps(g))
        b = self.abk()["befunde"]
        self.assertEqual([x["abk"] for x in b], ["f.", "f."])
        self.assertIn("[f.] 1", b[0]["kontext"])
        # Hand: erste ausschreiben, zweite bleibt
        self.assertEqual(self.lauf(abk={"entscheidung": [f"{b[0]['id']}=folio", f"{b[1]['id']}="]}), "auto")
        self.assertIn("Folio folio 1 and f. 2 and chapter 3.", self.raw())
        # Werktabelle statt Hand
        self.assertEqual(self.lauf(abk={"entscheidung": [f"{b[0]['id']}=offen", f"{b[1]['id']}=offen"],
                                        "werk": ["en:f.=folio"]}), "auto")
        self.assertIn("Folio folio 1 and folio 2", self.raw())
        with open(os.path.join(self.dir, "book.json")) as f:
            self.assertEqual(json.load(f)["abk_sprech"]["en"][0]["abk"], "f.")
        # Ruecknahme: abgeschaltet -> Basis wieder
        self.assertEqual(self.lauf(abk={"lesetext": False}), "auto")
        self.assertIn("Folio f. 1 and f. 2 and ch. 3.", self.raw())
        self.assertFalse(self.abk()["aktiv"])

    def test_behaltenes_zitat_bleibt(self):
        fr = "Voyez le ch. 4 de ce livre pour les détails de cette affaire."
        self.werk(roh_mit("He quotes it as follows:", FR1 + " " + FR2 + " " + fr, "See ch. 5."),
                  fremd_regler={"vorgabe": "alle_behalten"})
        self.lauf()
        r = self.raw()
        self.assertIn("See chapter 5.", r)
        if any(fr in s["text"] for z in json.load(open(os.path.join(self.dir, "work", "120_fremd.json")))["zitate"]
               for s in z["stellen"]):
            self.assertIn(fr, r)

    def test_monitor_daten_argv(self):
        from cockpit import werk_api as W
        self.werk(roh_mit("Folio f. 1 and ch. 3."))
        self.lauf()
        d = W._m120_daten("w")["abk"]
        self.assertTrue(d["aktiv"])
        self.assertEqual(len(d["befunde"]), 1)
        self.assertEqual(d["stellen"][0]["wort"], "chapter")
        i = d["befunde"][0]["id"]
        argv = W._m120_argv("w", {"abk": {i: "folio"}, "abk_werk": ["en:f.=folio"], "abk_lesetext": "aus"}, "CK")
        self.assertIn(f"--abk={i}=folio", argv)
        self.assertIn("--abk-werk=en:f.=folio", argv)
        self.assertIn("--abk-lesetext=aus", argv)
        with self.assertRaises(ValueError):
            W._m120_argv("w", {"abk": {"9:9:x#0": "y"}}, "CK")


if __name__ == "__main__":
    unittest.main()
