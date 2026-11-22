"""Stage 120 Schritt Fremdsprache (Teil B, 22.11.2026).  py -3.11 -m unittest tests.test_s120_fremd
Synthetische Werke; the-art-of-war (Amiot-Zitate) nur Muster."""
import json, os, re, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import s120_fremd as F
from pipeline import s120_modernisierung as M
from tests import test_s120 as B

FR1 = "Faites en sorte que tous ceux que vous devez commander soient persuadés de votre attention."
FR2 = "Attaquez à découvert, mais soyez vainqueur en secret et sans aucun bruit."
TITEL = ("The seventh volume of _Mémoires concernant l’histoire, les sciences, les arts des Chinois_ "
         "is devoted to the Art of War.")


def roh_mit(*absaetze):
    t = B.roh()
    return t.replace("CHAPTER II.\n", "\n\n".join(absaetze) + "\n\nCHAPTER II.\n", 1)


class TErkennung(unittest.TestCase):
    def test_zitat_gruppe_und_titel(self):
        kap = [("I", [TITEL, "He quotes it as follows:", FR1 + " " + FR2, "It is a poor translation of the text."])]
        for ersatz in (False, True):
            z = F.erkennen(kap, "en", F.regler({}), ersatz)
            self.assertEqual(len(z), 1, (ersatz, z))
            self.assertEqual(z[0]["sprache"], "fr")
            self.assertEqual([s["text"] for s in z[0]["stellen"]], [FR1, FR2])
            self.assertEqual(z[0]["kapitel"], 1)

    def test_englisch_kein_alarm(self):
        kap = [("I", ["Such is the art of manœuvering.", "[1] See Col. Henderson, op. cit. vol. I. p. 426.",
                      "Sun Tzŭ said: The art of war is of vital importance to the State."])]
        for ersatz in (False, True):
            self.assertEqual(F.erkennen(kap, "en", F.regler({}), ersatz), [])

    @unittest.skipIf(F.verfahren() != "lingua", "lingua fehlt")
    def test_kurzes_zitat(self):
        z = F.erkennen([("I", ["She looked at him.", "Je ne regrette rien."])], "en", F.regler({}))
        self.assertEqual([(x["sprache"], x["stellen"][0]["text"]) for x in z], [("fr", "Je ne regrette rien.")])

    def test_regler(self):
        with self.assertRaises(ValueError):
            F.regler({"fremd_regler": {"vorgabe": "egal"}})
        self.assertEqual(F.regler({"fremd_regler": {"schwelle": 0.8}})["schwelle"], 0.8)

    def test_anwenden_handtext_andere_satzzahl(self):
        kap = [("I", ["Vorher. " + FR1 + " " + FR2 + " Nachher."])]
        d = {"zitate": [{"id": "z1", "kapitel": 1, "sprache": "fr", "entscheidung": "uebertragen",
                         "stellen": [{"absatz": 0, "text": FR1}, {"absatz": 0, "text": FR2}],
                         "uebertragung": ["Act openly, win in secret."]}]}
        neu, fehlt = F.anwenden(kap, d)
        self.assertEqual(neu[0][1][0], "Vorher. Act openly, win in secret. Nachher.")
        self.assertEqual(fehlt, [])


class T120(unittest.TestCase):
    setUp, tearDown = B.T.setUp, B.T.tearDown
    werk, lauf, kap, gate = B.T.werk, B.T.lauf, B.T.kap, B.T.gate

    def ueb_fake(self):
        orig = M._call_model
        self.ueb = 0

        def f(prompt, modell=None, temperatur=None):
            if "QUOTATION:" in prompt:
                self.ueb += 1
                q = prompt.split("QUOTATION:", 1)[1]
                return "\n".join(f"[{m.group(1)}] EN{m.group(1)}: {m.group(2)[:12]}"
                                 for m in re.finditer(r"^\[(\d+)\] (.*)$", q, re.M))
            return orig(prompt, modell, temperatur)
        M._call_model = f

    def fremd(self):
        with open(os.path.join(self.dir, "work", "120_fremd.json"), encoding="utf-8") as f:
            return json.load(f)

    def raw(self):
        with open(os.path.join(self.dir, "raw_modernized.txt"), encoding="utf-8") as f:
            return f.read()

    def test_uebertragen_annehmen_ruecknahme(self):
        self.werk(roh_mit("He quotes it as follows:", FR1 + " " + FR2), fassung="original")
        self.ueb_fake()
        self.assertEqual(self.lauf(), "mensch")
        z = self.fremd()["zitate"]
        self.assertEqual(len(z), 1)
        zid = z[0]["id"]
        self.assertEqual(z[0]["entscheidung"], "offen")
        self.assertIn(FR1, self.raw())
        self.assertEqual(self.ueb, 0)
        # uebertragen -> LLM, eingesetzt, noch nicht angenommen
        self.assertEqual(self.lauf(fremd={"entscheidung": [f"{zid}=uebertragen"]}), "mensch")
        self.assertEqual(self.ueb, 1)
        self.assertNotIn(FR1, self.raw())
        self.assertIn("EN1: Faites en so", self.raw())
        k = self.kap(1)
        self.assertTrue(any(FR1 in p for p in k["paragraphs_vor_fremd"]))
        self.assertEqual(self.fremd()["zitate"][0]["stellen"][0]["text"], FR1)     # Original bleibt
        self.assertEqual(self.lauf(fremd={"annehmen": ["alle"]}), "auto")
        self.assertEqual(self.lauf(), "auto")                                       # Resume: kein neuer Aufruf
        self.assertEqual(self.ueb, 1)
        # Ruecknahme: Original behalten -> Original wieder im Text
        self.assertEqual(self.lauf(fremd={"entscheidung": [f"{zid}=behalten"]}), "auto")
        self.assertIn(FR1, self.raw())
        self.assertNotIn("paragraphs_vor_fremd", self.kap(1))

    def test_handtext_und_kein(self):
        self.werk(roh_mit(FR1 + " " + FR2), fassung="original")
        self.ueb_fake()
        self.lauf()
        zid = self.fremd()["zitate"][0]["id"]
        self.assertEqual(self.lauf(fremd={"text": [f"{zid}=Make all believe you protect them. || Attack openly."]}),
                         "auto")
        self.assertIn("Make all believe you protect them. Attack openly.", self.raw())
        self.assertEqual(self.ueb, 0)
        self.assertEqual(self.lauf(fremd={"entscheidung": [f"{zid}=kein"]}), "auto")
        self.assertIn(FR1, self.raw())

    def test_vorgabe_behalten_und_200_markiert(self):
        self.werk(roh_mit("He quotes it as follows:", FR1 + " " + FR2), fassung="modernisiert",
                  fremd_regler={"vorgabe": "alle_behalten"})
        self.assertEqual(self.lauf(), "auto")
        self.assertEqual(self.fremd()["zitate"][0]["entscheidung"], "behalten")
        content = {"c001_00001_s": {"type": "s", "en": "He quotes it as follows:"},
                   "c001_00002_qt": {"type": "qt", "en": FR1}, "c001_00003_qt": {"type": "qt", "en": FR2}}
        self.assertEqual(F.knoten_markieren("w", content, "en"), 2)
        self.assertEqual(content["c001_00002_qt"]["sprache_satz"], "fr")
        self.assertNotIn("sprache_satz", content["c001_00001_s"])
        self.assertEqual(F.satz_sprache(content["c001_00002_qt"], "de"), "fr")

    def test_monitor_daten_argv(self):
        from cockpit import werk_api as W
        self.werk(roh_mit(FR1 + " " + FR2), fassung="original")
        self.lauf()
        d = W._m120_daten("w")["fremd"]
        self.assertEqual(len(d["zitate"]), 1)
        z = d["zitate"][0]
        self.assertEqual(z["saetze"], [FR1, FR2])
        self.assertEqual(d["offen"]["offen"], [z["id"]])
        a = W._m120_argv("w", {"fremd": {z["id"]: "behalten"}, "fremd_text": {z["id"]: "A.  || B."},
                               "fremd_annehmen": ["alle"], "fremd_regler": {"schwelle": 0.7, "vorgabe": "alle_behalten"}},
                         "CK")
        self.assertIn(f"--fremd={z['id']}=behalten", a)
        self.assertIn(f"--fremd-text={z['id']}=A. || B.", a)
        self.assertIn("--fremd-annehmen=alle", a)
        self.assertIn("--fremd-schwelle=0.7", a)
        self.assertIn("--fremd-vorgabe=alle_behalten", a)
        with self.assertRaises(ValueError):
            W._m120_argv("w", {"fremd": {z["id"]: "weg"}}, "CK")

    def test_cli_fehler(self):
        self.werk(roh_mit(FR1 + " " + FR2), fassung="original")
        with self.assertRaises(ValueError):
            self.lauf(fremd={"entscheidung": ["zunbekannt=behalten"]})
        self.assertEqual(M.main(["w", "--fremd-vorgabe", "alle_uebertragen", "--wer", "CK"]) in (0, 3), True)


class TKette(unittest.TestCase):
    """Knoten mit sprache_satz (120 "Original behalten"): 310 kopiert ohne LLM, 400 spricht in der Satzsprache."""

    def test_310_original_bleibt(self):
        from tests import test_s310 as T3
        t = T3.T310("test_auto_checkpoint_ausschnitt")
        t.setUp()
        try:
            p = os.path.join(t.d, "work", "300_voruebersetzung.json")
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            d["content"]["c001_00003_s"] = {"type": "qt", "en": FR1, "sprache_satz": "fr"}
            with open(p, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)
            g = t.lauf()
            self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
            self.assertEqual(t.aus()["c001_00003_s"]["de"], FR1)
            self.assertTrue(all("c001_00003_s" not in a.split("Sentences (as JSON")[-1] for a in t.aufrufe))
        finally:
            t.tearDown()

    def test_400_sprache_und_hinweis(self):
        from tests import test_abk_sprech as TA
        t = TA.T400Abk("test_cli_fehler")
        t.setUp()
        try:
            p = os.path.join(t.d, "work", "330_rueckuebersetzung.json")
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            d["content"]["c001_00003_s"] = {"type": "qt", "en": "Je ne regrette rien, p. 12.",
                                            "de": "Je ne regrette rien, p. 12.", "sprache_satz": "fr"}
            with open(p, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)
            t.lauf()
            with open(os.path.join(t.d, "work", "400_regie.json"), encoding="utf-8") as f:
                prod = json.load(f)["production"]
            self.assertEqual(prod["sprache"]["c001_00003_s"], {"en": "fr", "de": "fr"})
            self.assertIn("in French", prod["direction"]["c001_00003_s"]["de"])
            self.assertEqual(prod["sprechtext"]["c001_00003_s"]["de"], "Je ne regrette rien, p. douze.")
            from pipeline import s500_vertonung_gemini as S5
            with open(os.path.join(t.d, "work", "400_regie.json"), encoding="utf-8") as f:
                u = {x["id"]: x for x in S5.einheiten(json.load(f), "de")[0]}
            self.assertEqual(u["c001_00003_s"]["sprache"], "fr")
            self.assertNotIn("sprache", u["c001_00002_s"])
        finally:
            t.tearDown()


if __name__ == "__main__":
    unittest.main()
