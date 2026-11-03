"""Stage 540 Trennung.  py -3.11 -m unittest tests.test_s540"""
import contextlib, io, json, os, sys, tempfile, unittest, wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import manifest, mock, trennung
from pipeline import status as S
from pipeline import s410_casting as C
from pipeline import s540_trennung as P

Q = {"c001_00001_h": ("h", "Kapitel eins"),
     "c001_00002_s": ("s", "Alice saß am Ufer des Flusses."),
     "c001_00003_dl": ("dl", "„Wer bist du?“, sagte der Hutmacher."),
     "c001_00004_dl": ("dl", "„Ich weiß es nicht.“"),
     "c001_00005_s": ("s", "Die Sonne schien hell."),
     "c002_00001_s": ("s", "Es war ein langer Tag."),
     "c002_00002_dl": ("dl", "„Komm mit“, sagte der Hutmacher."),
     "c002_00003_dl": ("dl", "„Gern“, sagte Alice.")}
SEG = {"c001_00003_dl": [("„Wer bist du?“,", "Hutmacher"), (" sagte der Hutmacher.", "Erzaehler")],
       "c001_00004_dl": [("„Ich weiß es nicht.“", "Alice")],
       "c002_00002_dl": [("„Komm mit“,", "Hutmacher"), (" sagte der Hutmacher.", "Erzaehler")],
       "c002_00003_dl": [("„Gern“,", "Alice"), (" sagte Alice.", "Erzaehler")]}
PROD = [{"sprache": "de", "inhalt": "hoerbuch", "stufe": "premium", "kanaele": ["taella"]},
        {"sprache": "de", "inhalt": "hoerspiel", "stufe": "premium", "kanaele": ["taella"]}]
V = {"erz": [1, 0, 0, 0], "getrennt": [0.2, 0.98, 0, 0], "nah": [0.75, 0.66, 0, 0], "weg": [0, 0, 1, 0]}


def rollen(korr=None):
    hut = {"rolle": "ensemble", "figur": "Hutmacher", "stimme": "hut", "gemini_id": "Puck"}
    if korr:
        hut["korrektur"] = korr
    return {"de": {"premium": {"engine": "gemini", "inhalte": ["hoerbuch", "hoerspiel"],
                               "erzaehler": {"rolle": "erzaehler", "figur": None, "stimme": "herr_a",
                                             "gemini_id": "Charon"},
                               "ensemble": [hut, {"rolle": "ensemble", "figur": "Alice", "stimme": "al",
                                                  "gemini_id": "Kore"}]}}}


def wav(p, s, seed=1):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    x = np.random.default_rng(seed).normal(0, 0.05, int(24000 * s))
    with wave.open(p, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


class T540(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.tmp.name
        self.d = os.path.join(r, "a", "books", "w")
        self.wd = os.path.join(self.d, "work")
        os.makedirs(self.wd)
        self.alt = (config.book_dir, config.work_dir, config.RUN_MODE, config.BASE_DIR, P.gpu_messen,
                    P.werkzeuge_pruefen, trennung.praat_merkmale, P.nachrunde_kette)
        config.book_dir = lambda b: self.d
        config.work_dir = lambda b: self.wd
        config.BASE_DIR = r
        config.RUN_MODE = "live"
        self.modus, self.ref, self.hb_zwei, self.fehler, self.messungen, self.fe = {}, {}, False, 0, 0, []
        self.kette = []
        P.gpu_messen = self.gpu
        P.werkzeuge_pruefen = lambda art: list(self.fe)
        trennung.praat_merkmale = lambda x: {"stimmhaft_s": round(len(x) / 24000 * 0.9, 2), "f0_hz": 120.0,
                                             "vtl_cm": 17.0}
        P.nachrunde_kette = self.fake_kette
        self.werk()

    def tearDown(self):
        (config.book_dir, config.work_dir, config.RUN_MODE, config.BASE_DIR, P.gpu_messen,
         P.werkzeuge_pruefen, trennung.praat_merkmale, P.nachrunde_kette) = self.alt
        self.tmp.cleanup()

    # ---------------------------------------------------------- Attrappen
    def korr_jetzt(self, f):
        return P._korr(P._ensemble(C.laden("w"), "de").get(f))["formant_faktor"]

    def gpu(self, paket, art):
        self.messungen += 1
        if self.fehler:
            self.fehler -= 1
            raise RuntimeError("Modal weg")
        erg = os.path.join(paket, "ergebnis")
        os.makedirs(erg, exist_ok=True)
        with open(os.path.join(paket, "manifest.json"), encoding="utf-8") as fh:
            man = json.load(fh)["segmente"]
        ids, emb = [], []
        for s in man:
            if s["typ"] == "en":
                v = V["erz"]
            elif s["typ"] == "ref":
                v = self.ref.get(s["figur"], V["getrennt"])
            else:
                m = self.modus.get(s["figur"], "getrennt")
                if m == "ab105":
                    m = "getrennt" if self.korr_jetzt(s["figur"]) >= 1.05 else "nah"
                v = V[m]
            ids.append(s["id"])
            emb.append(np.array(v, float))
        np.savez(os.path.join(erg, "embeddings.npz"), ids=np.array(ids), emb=np.stack(emb))
        with open(os.path.join(paket, "spur_ref.json"), encoding="utf-8") as fh:
            ref = json.load(fh)
        hs = [[a, b, "S0" if lab == "Erzaehler" else "S1"] for a, b, lab, _ in ref["hs"]]
        ende = ref["hb"][-1][1] if ref["hb"] else 10
        hb = [[0.0, ende, "S0"]] + ([[ende, ende * 2, "S1"]] if self.hb_zwei else [])
        with open(os.path.join(erg, "diar.json"), "w", encoding="utf-8") as fh:
            json.dump({"pyannote": {"hs": hs, "hb": hb}}, fh)
        return erg, 12.0

    def fake_kette(self, werk, wer):
        """510 -> 530 -> 520 nach Korrektur: 510-Meta nachfuehren (wie ein echter 510-Lauf)."""
        self.kette.append(True)
        m = manifest.Manifest("w", "510_overlay", stage="510")
        ens = P._ensemble(C.laden("w"), "de")
        m.meta["je_sprache"]["de"]["figuren"] = {f: {"stimme": e["stimme"], "korrektur": e.get("korrektur")}
                                                 for f, e in ens.items()}
        m.speichern()
        return [("510", "auto"), ("530", "auto"), ("520", "auto")]

    def schreib(self, p, o):
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(o, fh, ensure_ascii=False)

    def f(self, t, art="audio_final"):
        return os.path.join(self.d, "fassungen", "de", art, f"{t}.wav")

    def werk(self, rl=None, gates=("410", "420", "510", "530", "520"), korr510=None, ohne520=()):
        b = {"book_slug": "w", "quelle": "gutenberg", "quellsprache": "de", "fassung": "original",
             "mandant": "somnio", "produkte": PROD, "trennung_regler": {"redezeit_min": 1.0},
             "rechte": {"art": "gemeinfrei", "bearbeitung": True, "versichert": {"wer": "t", "wann": "x"}}}
        self.schreib(os.path.join(self.d, "book.json"), b)
        content = {k: {"type": t, "de": z} for k, (t, z) in Q.items()}
        self.schreib(os.path.join(self.wd, "400_regie.json"),
                     {"book_id": "w", "meta": {}, "content": content, "ansagen": {},
                      "production": {"sprechtext": {k: {"de": z} for k, (t, z) in Q.items()}, "abbildung": {},
                                     "direction": {}, "pause_after_ms": {}}})
        rl = rl or rollen()
        self.schreib(os.path.join(self.wd, "casting.json"),
                     {"schema": 2, "rollen": rl, "freigabe": {"wer": "CK", "hash": C.kern(rl)}})
        self.schreib(os.path.join(self.wd, "420_sprecher.json"),
                     {"saetze": {t: {"de": {"seg": [{"t": a, "s": s} for a, s in v], "q": "llm"}}
                                 for t, v in SEG.items()}})
        m5 = manifest.Manifest("w", "530_pruefung_de", stage="530")
        m51 = manifest.Manifest("w", "510_overlay", stage="510")
        tags = {}
        for i, (k, (t, z)) in enumerate(Q.items()):
            wav(self.f(k), 2.0, seed=i)
            m5.setzen(f"hoerbuch/{k}", "e", datei=self.f(k), dauer=2.0)
            if k in SEG:
                wav(self.f(k, "hoerspiel_final"), 3.0, seed=20 + i)
                m5.setzen(f"hoerspiel/{k}", "e", datei=self.f(k, "hoerspiel_final"), dauer=3.0)
                figs = sorted({s for _, s in SEG[k] if s != "Erzaehler"})
                m51.setzen(f"de/{k}", "h", datei=self.f(k, "hoerspiel_final"), q="neu", figuren=figs,
                           schnitt=[{"k": n, "q": "erz" if s == "Erzaehler" else s, "a": 0, "b": 1.0}
                                    for n, (_, s) in enumerate(SEG[k])])
                for fg in figs:
                    wav(os.path.join(self.wd, "_510", "de", "takes", f"{k}__{fg}.wav"), 1.5, seed=40 + i)
                n = len(z.split())
                if k not in ohne520:
                    tags[k] = [{"i": j, "t0": round(0.1 + j * 2.8 / n, 3), "t1": round(0.1 + (j + 1) * 2.8 / n, 3)}
                               for j in range(n)]
        m5.speichern()
        ens = P._ensemble({"rollen": rl}, "de")
        m51.meta["je_sprache"] = {"de": {"figuren": {f: {"stimme": e["stimme"],
                                                         "korrektur": (korr510 or {}).get(f, e.get("korrektur"))}
                                                     for f, e in ens.items()}}}
        m51.speichern()
        self.schreib(os.path.join(self.wd, "520_wortzeiten_de_hoerspiel.json"), {"tags": tags})
        for g in gates:
            S.ergebnis("w", g, "auto", wer="test")

    def lauf(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return P.run("w", wer="test", **kw)

    def aus(self):
        with open(P.pfad("w", "de"), encoding="utf-8") as fh:
            return json.load(fh)

    def fehler_von(self, g):
        return {x["name"]: x for x in g.pruefungen if not x["ok"]}

    # ---------------------------------------------------------- Hilfen
    def test_regionen_wortzeiten(self):
        segs = [{"t": "„Wer bist du?“,", "s": "Hut"}, {"t": " sagte der Hutmacher.", "s": "Erzaehler"}]
        lese = "„Wer bist du?“, sagte der Hutmacher."
        tags = [{"i": i, "t0": i * 0.5, "t1": i * 0.5 + 0.4} for i in range(6)]
        r, q = P.regionen(segs, {"Hut": {}}, lese, lese, [], tags, 3.0)
        self.assertEqual(q, "wortzeiten")
        self.assertEqual([x["q"] for x in r], ["Hut", "Erzaehler"])
        self.assertEqual(r[0]["t0"], 0.0)
        self.assertAlmostEqual(r[0]["t1"], 1.45)                 # Mitte zwischen Wort 3 (1,4) und 4 (1,5)
        self.assertEqual(r[1]["t1"], 2.95)

    def test_regionen_schnitt_rueckfall_und_statist(self):
        segs = [{"t": "„Hm“,", "s": "Katze"}, {"t": " sagte die Katze.", "s": "Erzaehler"}]
        prot = [{"k": 0, "q": "Hut", "a": 0, "b": 1}, {"k": 1, "q": "erz", "a": 2, "b": 5}]
        r, q = P.regionen(segs, {"Hut": {}}, "x", "x", [], None, 2.0, prot)
        self.assertEqual(q, "schnitt")
        self.assertEqual([(x["q"], x["t0"], x["t1"]) for x in r], [("Hut", 0.0, 0.5), ("Erzaehler", 0.5, 2.0)])
        r, q = P.regionen(segs, {"Hut": {}}, "„Hm“, sagte die Katze.", "", [], [{"i": 0, "t0": 0, "t1": 1}], 2)
        self.assertEqual({x["q"] for x in r}, {"Erzaehler"})        # Statist -> Erzaehler

    # ---------------------------------------------------------- Lauf
    def test_getrennt_auto_und_wiederverwendung(self):
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        a = self.aus()
        self.assertEqual(set(a["figuren"]), {"Hutmacher", "Alice"})
        self.assertEqual(a["figuren"]["Hutmacher"]["urteil"], "ok")
        self.assertEqual(a["kontrolle"]["sprecher"], 1)
        self.assertEqual(a["schwelle"], 0.599)
        self.assertTrue(os.path.exists(os.path.join(self.d, a["figuren"]["Alice"]["hoerprobe"]["datei"])))
        self.assertNotIn("pruefung", json.dumps(C.laden("w")))   # keine Pruefergebnisse in casting.json
        with open(os.path.join(self.wd, "kosten.jsonl"), encoding="utf-8") as fh:
            self.assertEqual(json.loads(fh.readline())["stage"], "540")
        g = self.lauf()
        self.assertEqual(self.messungen, 1)                      # gleicher Eingang -> keine neue Messung
        self.assertEqual(g.ergebnis["ergebnis"], "auto")
        self.lauf(neu=True)
        self.assertEqual(self.messungen, 2)

    def test_nachrunde_dann_getrennt(self):
        self.modus["Hutmacher"] = "ab105"
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(len(self.kette), 1)
        self.assertEqual(self.korr_jetzt("Hutmacher"), 1.05)
        e = P._ensemble(C.laden("w"), "de")["Hutmacher"]
        self.assertIn("540 Nachrunde", e["korrektur_protokoll"][-1]["grund"])
        self.assertTrue(C.freigegeben(C.laden("w")))             # Korrektur bricht die Casting-Freigabe nicht
        self.assertEqual(self.aus()["figuren"]["Hutmacher"]["nachrunden"], 1)
        self.assertEqual(self.messungen, 2)

    def test_nachrunde_reicht_nicht_mensch(self):
        self.modus["Hutmacher"] = "nah"
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch", g.bericht())
        f = self.fehler_von(g)["figur_de_Hutmacher"]
        self.assertEqual(f["ruecksprung"], "410")
        self.assertEqual(self.aus()["figuren"]["Hutmacher"]["urteil"], "umbesetzen")
        # annehmen trotz Befund -> auto (Protokoll)
        with contextlib.redirect_stdout(io.StringIO()):
            P.annehmen("w", "Hutmacher", "de", "CK", "klingt gut")
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(self.aus()["figuren"]["Hutmacher"]["urteil"], "angenommen")

    def test_an_der_grenze_mensch_ohne_nachrunde(self):
        self.werk(rl=rollen(korr={"formant_faktor": 1.10, "tonhoehe_ht": 0}))
        self.modus["Hutmacher"] = "nah"
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertEqual(self.kette, [])
        self.assertEqual(self.aus()["figuren"]["Hutmacher"]["urteil"], "grenze")

    def test_naeher_am_erzaehler_umbesetzen(self):
        self.ref["Alice"] = V["weg"]
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertEqual(self.aus()["figuren"]["Alice"]["urteil"], "umbesetzen")
        self.assertEqual(self.kette, [])

    def test_nachrunde_aus(self):
        self.modus["Hutmacher"] = "nah"
        g = self.lauf(regler={"nachrunde": False})
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertEqual(self.kette, [])
        self.assertEqual(self.fehler_von(g)["figur_de_Hutmacher"]["ruecksprung"], "510")

    def test_nachrunde_haengt_in_510(self):
        self.modus["Hutmacher"] = "nah"
        P.nachrunde_kette = lambda w, wer: [("510", "mensch")]
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertIn("Nachrunde haengt", self.fehler_von(g)["figur_de_Hutmacher"]["text"])

    def test_kontrolle_zwei_sprecher_mensch(self):
        self.hb_zwei = True
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertEqual(self.fehler_von(g)["kontrolle_de"]["ruecksprung"], "500")

    def test_messfehler_einmal_neu_dann_stopp(self):
        self.fehler = 1
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(self.messungen, 2)
        self.fehler = 2
        g = self.lauf(neu=True)
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertIn("messung_de", self.fehler_von(g))

    def test_redezeit_zu_kurz_hinweis(self):
        g = self.lauf(regler={"redezeit_min": 30.0})
        self.assertEqual(g.ergebnis["ergebnis"], "auto")
        self.assertEqual(self.aus()["figuren"]["Alice"]["urteil"], "zu_kurz")

    def test_ohne_wortzeiten_schnitt_hinweis(self):
        self.werk(ohne520=("c001_00004_dl",))
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto")
        self.assertIn("wortzeiten_de", {x["name"] for x in g.pruefungen if not x["ok"]})
        self.assertEqual(self.aus()["quellen_regionen"], {"wortzeiten": 3, "schnitt": 1})

    def test_gate_520_nicht_frei_stopp(self):
        S.ergebnis("w", "520", "mensch", wer="test")
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual(self.messungen, 0)

    def test_korrektur_neuer_als_510_stopp(self):
        self.werk(rl=rollen(korr={"formant_faktor": 1.05, "tonhoehe_ht": 0}), korr510={"Hutmacher": None})
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual(self.fehler_von(g)["korrektur_de"]["ruecksprung"], "510")

    def test_werkzeug_fehlt_stopp(self):
        self.fe = ["HF_TOKEN fehlt"]
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual(self.messungen, 0)

    def test_mock_endfassung_im_live_lauf_stopp(self):
        mock.wav(self.f("c001_00004_dl", "hoerspiel_final"))
        m5 = manifest.Manifest("w", "530_pruefung_de", stage="530")
        m5.setzen("hoerspiel/c001_00004_dl", "e", datei=self.f("c001_00004_dl", "hoerspiel_final"), dauer=0.1)
        m5.speichern()
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")

    def test_trocken_schreibt_nichts(self):
        g = self.lauf(trocken=True)
        self.assertEqual(self.messungen, 0)
        self.assertFalse(os.path.exists(P.pfad("w", "de")))
        self.assertIn("messung_de", {x["name"] for x in g.pruefungen})

    def test_mensch_freigabe_gilt_bei_gleichem_ergebnis(self):
        self.ref["Alice"] = V["weg"]
        self.lauf()
        S.entscheiden("w", "540", "frei", "test", "gehoert", rolle="admin")
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())


if __name__ == "__main__":
    unittest.main()
