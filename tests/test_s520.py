"""Stage 520 Wortzeiten (inkl. 525).  py -3.11 -m unittest tests.test_s520"""
import contextlib, io, json, os, sys, tempfile, unittest, wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import manifest
from pipeline import status as S
from pipeline import s520_wortzeiten as P
from pipeline import s525_wortbruecke as s525

Q = {"c001_00001_h": ("h", "Chapter IV", "Kapitel IV"),
     "c001_00002_s": ("s", "Alice sat by the river bank.", "Alice saß am Ufer."),
     "c001_00003_dl": ("dl", "\"Who are you?\" said the Hatter.", "„Wer bist du?“, sagte der Hutmacher."),
     "c002_00001_s": ("s", "The end came soon.", "Das Ende kam bald.")}
SPRECH = {"c001_00001_h": ("Kapitel vier", [[8, 12, 8, 10]])}
FIG = ("c001_00003_dl",)
PROD = [{"sprache": "en", "inhalt": "text", "kanaele": ["taella"]},
        {"sprache": "de", "inhalt": "text", "kanaele": ["taella"]},
        {"sprache": "de", "inhalt": "hoerbuch", "stufe": "premium", "kanaele": ["taella"]},
        {"sprache": "de", "inhalt": "hoerspiel", "stufe": "premium", "kanaele": ["taella"]}]
ALIGN = {"c001_00001_h": [{"i": 0, "en": "Chapter", "en_span": [0, 7], "de": "Kapitel", "de_span": [0, 7]},
                          {"i": 1, "en": "IV", "en_span": [8, 10], "de": "IV", "de_span": [8, 10]}],
         "c001_00002_s": [{"i": 0, "en": "Alice", "en_span": [0, 5], "de": "Alice", "de_span": [0, 5]},
                          {"i": 1, "en": "sat", "en_span": [6, 9], "de": "saß", "de_span": [6, 9]},
                          {"i": 5, "en": "bank.", "en_span": [23, 28], "de": "Ufer", "de_span": [13, 17]}]}


def wav(p, s=1.5, seed=1):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    x = np.random.default_rng(seed).normal(0, 0.05, int(24000 * s))
    with wave.open(p, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


class T520(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.tmp.name
        self.d = os.path.join(r, "a", "books", "w")
        self.wd = os.path.join(self.d, "work")
        os.makedirs(self.wd)
        self.alt = (config.book_dir, config.work_dir, config.RUN_MODE, config.BASE_DIR, P.fa_zeiten,
                    P.werkzeuge_pruefen)
        config.book_dir = lambda b: self.d
        config.work_dir = lambda b: self.wd
        config.BASE_DIR = r
        config.RUN_MODE = "live"
        self.jobs, self.leer, self.cpu_leer, self.zu_lang, self.fe = [], set(), set(), set(), []
        P.fa_zeiten = self.fa
        P.werkzeuge_pruefen = lambda art: list(self.fe)
        self.werk()

    def tearDown(self):
        (config.book_dir, config.work_dir, config.RUN_MODE, config.BASE_DIR, P.fa_zeiten,
         P.werkzeuge_pruefen) = self.alt
        self.tmp.cleanup()

    # ---------------------------------------------------------- Attrappen
    def fa(self, jobs, werk, lg, art):
        out = {}
        for key, p, w in jobs:
            self.jobs.append((key, art))
            with wave.open(p) as f:
                d = f.getnframes() / f.getframerate()
            if key in self.zu_lang:
                d += 1.0
            n = len(w) or 1
            leer = key in self.leer if art == "modal" else key in self.cpu_leer
            out[key] = [None] * len(w) if leer else [(0.1 + i * (d - 0.2) / n, 0.1 + (i + 1) * (d - 0.2) / n)
                                                     for i in range(len(w))]
        return out

    def f(self, t, spur="hoerbuch"):
        return os.path.join(self.d, "fassungen", "de", P.FINAL[spur], f"{t}.wav")

    def schreib(self, p, o):
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(o, fh, ensure_ascii=False)

    def werk(self, gates=("530", "340"), ohne=(), de340=None):
        b = {"book_slug": "w", "quelle": "gutenberg", "quellsprache": "en", "fassung": "modernisiert",
             "mandant": "somnio", "produkte": PROD,
             "rechte": {"art": "gemeinfrei", "bearbeitung": True, "versichert": {"wer": "t", "wann": "x"}}}
        self.schreib(os.path.join(self.d, "book.json"), b)
        content = {k: {"type": t, "en": q, "de": z} for k, (t, q, z) in Q.items()}
        sp = {k: {"de": SPRECH.get(k, (z, []))[0]} for k, (t, q, z) in Q.items()}
        ab = {k: {"de": v[1]} for k, v in SPRECH.items()}
        self.schreib(os.path.join(self.wd, "400_regie.json"),
                     {"book_id": "w", "meta": {}, "content": content, "ansagen": {},
                      "production": {"sprechtext": sp, "abbildung": ab, "direction": {}, "pause_after_ms": {}}})
        c340 = {k: dict(v, align_de=ALIGN.get(k, [])) for k, v in content.items()}
        if de340:
            c340[de340[0]]["de"] = de340[1]
        self.schreib(os.path.join(self.wd, "340_wortalignment.json"), {"content": c340, "meta": {}})
        m = manifest.Manifest("w", "530_pruefung_de", stage="530")
        for i, k in enumerate(Q):
            if k in ohne:
                continue
            wav(self.f(k), 1.2 + 0.1 * i, seed=i)
            m.setzen(f"hoerbuch/{k}", "e", datei=self.f(k), dauer=round(1.2 + 0.1 * i, 3))
        for k in FIG:
            wav(self.f(k, "hoerspiel"), 1.6, seed=9)
            m.setzen(f"hoerspiel/{k}", "e", datei=self.f(k, "hoerspiel"), dauer=1.6)
        m.speichern()
        for g in gates:
            S.ergebnis("w", g, "auto", wer="test")

    def aus(self, spur="hoerbuch"):
        with open(P.pfad("w", "de", spur), encoding="utf-8") as fh:
            return json.load(fh)

    def lauf(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return P.run("w", wer="test", **kw)

    def fehler(self, g):
        return {x["name"] for x in g.pruefungen if not x["ok"]}

    # ---------------------------------------------------------- Hilfen
    def test_abbildung_und_lexikon(self):
        fa, laut = P.vorbereiten("Kapitel IV", "Kapitel vier", [[8, 12, 8, 10]], {})
        self.assertEqual(fa, "Kapitel vier")
        self.assertEqual([(x["w"], x["l0"], x["l1"]) for x in laut], [("kapitel", 0, 7), ("vier", 8, 10)])
        fa, laut = P.vorbereiten("sagte der Hutmacher.", "sagte der Hutmacher.", [], {"Hutmacher": "Huht-macher"})
        self.assertEqual(fa, "sagte der Huht-macher.")
        self.assertEqual([(x["w"], x["l0"], x["l1"]) for x in laut][2:], [("huht", 10, 14), ("macher", 14, 19)])
        e = P.binden(laut, [(0, .2), (.2, .4), (.4, .6), (.6, .9)], "sagte der Hutmacher.")
        self.assertEqual([x["i"] for x in e], [0, 1, 2])
        self.assertEqual((e[2]["t0"], e[2]["t1"]), (0.4, 0.9))
        # Loeschung (s0 == s1): "1888" -> Sprechtext ohne Klammer
        self.assertEqual(P.lese_karte("ab", [[1, 1, 1, 3]]), [(0, 1), (3, 4)])

    def test_befund(self):
        rg = P.REGLER_STD
        ok = [{"i": 0, "t0": 0.1, "t1": 0.4}, {"i": 1, "t0": 0.4, "t1": 0.8}]
        self.assertEqual(P.befund(ok, 2, 2, 1.0, rg), ([], 0))
        self.assertEqual(P.befund([], 2, 0, 1.0, rg)[0], ["ohne_zeiten", "lautwoerter"])
        self.assertIn("dauer", P.befund(ok, 2, 2, 0.5, rg)[0])
        self.assertIn("monoton", P.befund(list(reversed(ok)), 2, 2, 1.0, rg)[0])
        self.assertEqual(P.befund([{"i": 0, "t0": 0.1, "t1": 0.11}], 1, 1, 1.0, rg)[1], 1)

    # ---------------------------------------------------------- Lauf
    def test_volllauf_auto_und_bruecke(self):
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        a = self.aus()
        self.assertEqual(list(a["tags"]), list(Q))
        self.assertEqual(a["einheit"], P.EINHEIT)
        self.assertEqual([x["i"] for x in a["tags"]["c001_00001_h"]], [0, 1])    # "vier" -> Token "IV"
        self.assertEqual(a["saetze"]["c001_00002_s"]["fa"], "modal")
        self.assertEqual(list(self.aus("hoerspiel")["tags"]), list(FIG))
        with open(P.bruecke_pfad("w"), encoding="utf-8") as fh:
            br = json.load(fh)
        self.assertEqual((br["quelle"], br["ziel"]), ("en", "de"))
        self.assertEqual(br["je_ziel"]["de"]["anker_quote"], 1.0)
        w = br["tags"]["c001_00001_h"][1]
        self.assertTrue(w["tz"] and w["t"] is None)
        self.assertTrue(os.path.exists(P.pruef_pfad("w")))

    def test_hash_nur_geaendert_neu(self):
        self.lauf()
        self.jobs.clear()
        g = self.lauf()
        self.assertEqual(self.jobs, [])
        self.assertEqual(g.ergebnis["ergebnis"], "auto")
        t = "c001_00002_s"
        wav(self.f(t), 1.9, seed=42)
        m = manifest.Manifest("w", "530_pruefung_de", stage="530")
        m.setzen(f"hoerbuch/{t}", "e2", datei=self.f(t), dauer=1.9)
        m.speichern()
        self.lauf()
        self.assertEqual(self.jobs, [(t, "modal")])

    def test_auffaellig_cpu_neu(self):
        self.leer = {"c001_00002_s"}
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        i = self.aus()["saetze"]["c001_00002_s"]
        self.assertEqual((i["fa"], i["versuch"], i["befund"]), ("cpu", 2, []))
        self.cpu_leer = {"c002_00001_s"}
        self.leer = {"c002_00001_s"}
        g = self.lauf(saetze=["c002_00001_s"], kapitel=None)
        self.assertIn("ohne_zeiten_de_hoerbuch", self.fehler(g))
        g = self.lauf(regler={"fa": None})
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertIn("ohne_zeiten_de_hoerbuch", self.fehler(g))
        with open(P.pruef_pfad("w"), encoding="utf-8") as fh:
            pr = json.load(fh)
        self.assertEqual(pr["de"]["hoerbuch"]["auffaellig"][0]["id"], "c002_00001_s")

    def test_ausserhalb_dauer_mensch(self):
        self.zu_lang = {"c001_00002_s"}
        g = self.lauf(regler={"wiederholen": False})
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertIn("dauer_de_hoerbuch", self.fehler(g))

    def test_stopp(self):
        S.ergebnis("w", "530", "stopp", wer="test")
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual(self.jobs, [])
        self.werk(ohne=("c002_00001_s",))
        os.remove(self.f("c002_00001_s")) if os.path.exists(self.f("c002_00001_s")) else None
        m = manifest.Manifest("w", "530_pruefung_de", stage="530")
        m.entfernen("hoerbuch/c002_00001_s")
        m.speichern()
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertIn("eingang_de_hoerbuch", self.fehler(g))
        g = self.lauf(kapitel=["c001"])
        self.assertNotIn("eingang_de_hoerbuch", self.fehler(g))

    def test_text_340_weicht_ab(self):
        self.werk(de340=("c001_00002_s", "Alice saß am Fluss."))
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertIn("text_340_de_hoerbuch", self.fehler(g))

    def test_werkzeug_fehlt(self):
        self.fe = ["FA (modal): ImportError"]
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertFalse(os.path.exists(P.pfad("w", "de")))

    def test_trocken_schreibt_nichts(self):
        g = self.lauf(trocken=True)
        self.assertEqual(self.jobs, [])
        self.assertFalse(os.path.exists(P.pfad("w", "de")))
        self.assertFalse(os.path.exists(P.bruecke_pfad("w")))
        self.assertIn("abdeckung_de_hoerbuch", {x["name"] for x in g.pruefungen})

    def test_korrektur(self):
        self.lauf()
        t = "c001_00002_s"
        with contextlib.redirect_stdout(io.StringIO()):
            P.run("w", wer="test", zeiten_man=[("de", t, 2, 0.5, 0.7)])
        e = {x["i"]: x for x in self.aus()["tags"][t]}
        self.assertEqual((e[2]["t0"], e[2]["t1"]), (0.5, 0.7))
        self.assertEqual(self.aus()["saetze"][t]["manuell"], [2])
        wav(self.f(t), 1.9, seed=43)
        m = manifest.Manifest("w", "530_pruefung_de", stage="530")
        m.setzen(f"hoerbuch/{t}", "e3", datei=self.f(t), dauer=1.9)
        m.speichern()
        g = self.lauf()
        self.assertIn(f"korrektur_de_hoerbuch_{t}", self.fehler(g))
        self.assertNotIn("manuell", self.aus()["saetze"][t])
        with open(P.korr_pfad("w"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), {})

    def test_mensch_freigabe_gilt(self):
        self.zu_lang = {"c001_00002_s"}
        g = self.lauf(regler={"wiederholen": False})
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        S.entscheiden("w", "520", "frei", wer="test", grund="geprueft")
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())

    def test_messen_anker_mit_zeit(self):
        tags = {"c001_00002_s": [{"i": 0, "t": None, "tq": None, "zspans": [[0, 5]], "tz": [[0, .2]], "sq": "340"},
                                 {"i": 1, "t": None, "tq": None, "zspans": [[6, 9]], "tz": None, "sq": "340"}]}
        content = {"c001_00002_s": {"en": "Alice sat by the river bank."}}
        m = s525.messen(tags, content, "en", q_audio=False, z_audio=True)
        self.assertEqual((m["anker"], m["anker_mit_zeit"]), (2, 1))


if __name__ == "__main__":
    unittest.main()
