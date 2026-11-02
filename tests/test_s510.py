"""Stage 510 Hoerspiel-Overlay.  py -3.11 -m unittest tests.test_s510"""
import contextlib, io, json, os, struct, sys, tempfile, unittest, wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import manifest, mock
from pipeline import status as S
from pipeline import s410_casting as C
from pipeline import s500_vertonung_gemini as P5
from pipeline import s510_hoerspiel_hybrid as P

Q = {"c001_00001_h": ("h", "Chapter One", "Kapitel eins"),
     "c001_00002_s": ("s", "Alice sat by the river bank.", "Alice saß am Ufer des Flusses."),
     "c001_00003_dl": ("dl", "\"Who are you?\" said the Hatter.", "„Wer bist du?“, sagte der Hutmacher."),
     "c001_00004_dl": ("dl", "\"I do not know.\"", "„Ich weiß es nicht.“"),
     "c002_00001_h": ("h", "Chapter Two", "Kapitel zwei"),
     "c002_00002_dl": ("dl", "\"Hm,\" the cat said.", "„Hm“, sagte die Katze.")}
SEG = {"c001_00003_dl": [{"t": "„Wer bist du?“,", "s": "Hutmacher"}, {"t": " sagte der Hutmacher.", "s": "Erzaehler"}],
       "c001_00004_dl": [{"t": "„Ich weiß es nicht.“", "s": "Alice"}],
       "c002_00002_dl": [{"t": "„Hm“,", "s": "Katze"}, {"t": " sagte die Katze.", "s": "Erzaehler"}]}
PROD = [{"sprache": "de", "inhalt": "hoerbuch", "stufe": "premium", "kanaele": ["taella"]},
        {"sprache": "de", "inhalt": "hoerspiel", "stufe": "premium", "kanaele": ["taella"]}]
FIG = ("c001_00003_dl", "c001_00004_dl")


def rollen(korr=None, puck="Puck"):
    hut = {"rolle": "ensemble", "figur": "Hutmacher", "stimme": "hut", "gemini_id": puck}
    if korr:
        hut["korrektur"] = korr
    return {"de": {"premium": {"engine": "gemini", "inhalte": ["hoerbuch", "hoerspiel"],
                               "erzaehler": {"rolle": "erzaehler", "figur": None, "stimme": "herr_a",
                                             "gemini_id": "Charon", "modell": "m"},
                               "ensemble": [hut, {"rolle": "ensemble", "figur": "Alice", "stimme": "al",
                                                  "gemini_id": "Kore"}],
                               "statisten": [{"figur": "Katze"}]}}}


def wav(p, sek=1.0, amp=3000):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    n = max(1, int(24000 * sek))
    with wave.open(p, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(struct.pack(f"<{n}h", *([amp, -amp] * (n // 2) + [0] * (n % 2))))


class T510(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.tmp.name
        self.d = os.path.join(r, "a", "books", "w")
        self.wd = os.path.join(self.d, "work")
        os.makedirs(self.wd)
        self.alt = (config.book_dir, config.work_dir, config.RUN_MODE, config.BASE_DIR, P5.synth, P5.PAUSE,
                    P.zeiten, P.aligner_pruefen, P.korrigieren)
        config.book_dir = lambda b: self.d
        config.work_dir = lambda b: self.wd
        config.BASE_DIR = r
        config.RUN_MODE = "live"
        P5.PAUSE = 0
        self.calls, self.korr, self.policy, self.luecke, self.amp, self.lang = [], [], set(), {}, 3000, 1.0
        P5.synth = self.synth
        P.zeiten = self.zeiten
        P.aligner_pruefen = lambda art, k: self.fa_fehlt if hasattr(self, "fa_fehlt") else None
        P.korrigieren = self.korrigieren
        self.werk()

    def tearDown(self):
        (config.book_dir, config.work_dir, config.RUN_MODE, config.BASE_DIR, P5.synth, P5.PAUSE,
         P.zeiten, P.aligner_pruefen, P.korrigieren) = self.alt
        self.tmp.cleanup()

    # ---------------------------------------------------------- Attrappen
    def synth(self, text, style, out, voice, lg):
        self.calls.append((text, voice))
        if text in self.policy:
            raise RuntimeError("blocked by policy")
        wav(out, 0.06 * len(text) * self.lang, self.amp)

    def zeiten(self, jobs, werk, lg, art):
        self.arten = getattr(self, "arten", []) + [art]
        out = {}
        for key, p, w in jobs:
            d = P5.wav_dauer(p)
            n = len(w) or 1
            z = [(i * d / n + 0.01, (i + 1) * d / n - 0.01) for i in range(len(w))]
            t, q = key.split("|")
            if q != "erz" and self.luecke.get(t):
                self.luecke[t] -= 1
                z = [None] * len(w)
            out[key] = z
        return out

    def korrigieren(self, x, sr, f=1.0, ht=0.0):
        self.korr.append((f, ht))
        return x

    def werk(self, produkte=None, seg=None, rl=None, frei=True, gates=("400", "410", "420", "500"), budget=5.0,
             erz500="herr_a", ohne500=()):
        b = {"book_slug": "w", "quelle": "gutenberg", "quellsprache": "en", "fassung": "modernisiert",
             "mandant": "somnio", "produkte": produkte or PROD, "hoerspiel_regler": {"budget": budget},
             "rechte": {"art": "gemeinfrei", "bearbeitung": True, "versichert": {"wer": "t", "wann": "x"}}}
        self.schreib(os.path.join(self.d, "book.json"), b)
        content = {k: {"type": t, "en": q, "de": z} for k, (t, q, z) in Q.items()}
        sp = {k: {"de": z} for k, (t, q, z) in Q.items()}
        self.schreib(os.path.join(self.wd, "400_regie.json"),
                     {"book_id": "w", "meta": {}, "content": content, "ansagen": {},
                      "production": {"sprechtext": sp, "direction": {}, "pause_after_ms": {}}})
        rl = rl or rollen()
        self.schreib(os.path.join(self.wd, "casting.json"),
                     {"schema": 2, "rollen": rl, "freigabe": {"wer": "CK", "hash": C.kern(rl)} if frei else None})
        s = {t: {"de": {"seg": v, "q": "llm"}} for t, v in (SEG if seg is None else seg).items()}
        self.schreib(os.path.join(self.wd, "420_sprecher.json"), {"saetze": s})
        if erz500 != "herr_a" or ohne500 or not os.path.exists(os.path.join(self.wd, "500_vertonung.json")):
            if os.path.exists(os.path.join(self.wd, "500_vertonung.json")):
                os.remove(os.path.join(self.wd, "500_vertonung.json"))
            m = manifest.Manifest("w", "500_vertonung", stage="500")
            for k, (t, q, z) in Q.items():
                if k in ohne500:
                    continue
                p = self.a(f"{k}.wav")
                wav(p, 0.06 * len(z))
                m.setzen(f"de/{k}", "h", datei=p, engine="gemini", stimme=erz500, q="neu")
            m.meta["je_sprache"] = {"de": {"engine": "gemini", "stimme": erz500}}
            m.speichern()
        for g in gates:
            S.ergebnis("w", g, "auto", wer="test")

    def schreib(self, p, o):
        with open(p, "w", encoding="utf-8") as f:
            json.dump(o, f, ensure_ascii=False)

    def lesen(self, n):
        with open(os.path.join(self.wd, n), encoding="utf-8") as f:
            return json.load(f)

    def lauf(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return P.run("w", wer="test", **kw)

    def a(self, *t):
        return os.path.join(self.d, "fassungen", "de", "audio", *t)

    def h(self, *t):
        return os.path.join(self.d, "fassungen", "de", "hoerspiel", *t)

    def e(self, t):
        return self.lesen("510_overlay.json")["eintraege"][f"de/{t}"]

    def freigeben(self):
        S.entscheiden("w", "510", "frei", "test", "Stichprobe gehoert", rolle="admin")

    # ---------------------------------------------------------- Tests
    def test_bau_mensch_dann_freigabe_auto(self):
        h500 = manifest.hash_datei(self.a("c001_00003_dl.wav"))
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch", g.bericht())        # Hoerspiel-Freigabe immer Mensch
        for t in FIG:
            self.assertTrue(os.path.exists(self.h(f"{t}.wav")), t)
            self.assertEqual(self.e(t)["q"], "neu")
            self.assertIsNone(self.e(t)["pruefung"])
        self.assertFalse(os.path.exists(self.h("c002_00002_dl.wav")))            # Statist -> Erzaehler
        self.assertFalse(os.path.exists(self.h("c001_00002_s.wav")))
        self.assertEqual(sorted(self.calls), [("Ich weiß es nicht.", "Kore"), ("Wer bist du?", "Puck")])
        self.assertEqual(manifest.hash_datei(self.a("c001_00003_dl.wav")), h500)  # Hoerbuchspur unberuehrt
        sch = self.e("c001_00003_dl")["schnitt"]
        self.assertEqual([x["q"] for x in sch], ["Hutmacher", "erz"])
        pr = self.lesen("510_pruefung.json")["de"]
        self.assertEqual(sorted(pr["stichprobe"]), ["Alice", "Hutmacher"])
        self.freigeben()
        n = len(self.calls)
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(len(self.calls), n)
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto")

    def test_korrektur_nur_neu_schneiden(self):
        self.lauf()
        n = len(self.calls)
        self.werk(rl=rollen(korr={"formant_faktor": 1.05, "tonhoehe_ht": 1.0}))
        g = self.lauf()
        self.assertEqual(len(self.calls), n)                                      # Take wiederverwendet, 0 $
        self.assertEqual(self.korr, [(1.05, 1.0)])
        self.assertEqual(g.metriken["offen"], {"de": 1})

    def test_korrektur_ohne_praat_stopp(self):
        self.werk(rl=rollen(korr={"formant_faktor": 1.05}))
        self.fa_fehlt = "ModuleNotFoundError: parselmouth"
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual(self.calls, [])

    def test_kosten_mensch_und_freigabe(self):
        self.werk(budget=0.0)
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertIn("--kosten-freigeben", g.bericht())
        self.assertEqual(self.calls, [])
        g = self.lauf(kosten_freigeben=1.0)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.lesen("510_kosten.json")["freigaben"][0]["takes"], 2)

    def test_casting_nicht_frei_stopp(self):
        self.werk(frei=False)
        self.assertEqual(self.lauf().ergebnis["ergebnis"], "stopp")

    def test_gate_420_nicht_frei_stopp(self):
        S.ergebnis("w", "420", "stopp", wer="test")
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual(self.calls, [])

    def test_nur_hoerbuch_stopp(self):
        self.werk(produkte=PROD[:1])
        self.assertEqual(self.lauf().ergebnis["ergebnis"], "stopp")

    def test_figur_ohne_gemini_id_stopp(self):
        self.werk(rl=rollen(puck=None))
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertIn("Hutmacher", g.bericht())

    def test_erzaehler_500_anders_stopp(self):
        self.werk(erz500="frau_b")
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual(self.calls, [])

    def test_satz_ohne_500_stopp(self):
        self.werk(ohne500=("c001_00004_dl",))
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertIn("ohne aktuelle Hoerbuch-WAV 500", g.bericht())

    def test_fa_fehlt_stopp_vor_ausgabe(self):
        self.fa_fehlt = "ModuleNotFoundError: torch"
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual(self.calls, [])

    def test_kein_schnitt_reparatur(self):
        self.luecke = {"c001_00003_dl": 1}
        self.lauf()
        e = self.e("c001_00003_dl")
        self.assertEqual((e["q"], e["pruefung"], e["versuche"]), ("neu", None, 1))
        self.assertEqual(sum(1 for c in self.calls if c[1] == "Puck"), 2)

    def test_kein_schnitt_dauerhaft_erzaehlerfassung(self):
        self.luecke = {"c001_00003_dl": 9}
        g = self.lauf()
        e = self.e("c001_00003_dl")
        self.assertEqual((e["q"], e["pruefung"], e["versuche"]), ("erzaehler", "kein_schnitt", 2))
        self.assertEqual(manifest.hash_datei(self.h("c001_00003_dl.wav")),
                         manifest.hash_datei(self.a("c001_00003_dl.wav")))
        self.assertEqual(self.arten, ["modal", "modal", "cpu"])                    # 2. Wiederholung CPU-Schnitt
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertTrue(self.lesen("510_pruefung.json")["de"]["auffaellig"])

    def test_policy_erzaehlerfassung(self):
        self.policy = {"Wer bist du?"}
        g = self.lauf()
        e = self.e("c001_00003_dl")
        self.assertEqual((e["q"], e["pruefung"]), ("erzaehler", "policy"))
        self.assertIn("1 Policy-Ablehnungen", g.bericht())

    def test_naht_auffaellig(self):
        self.amp = 20000
        g = self.lauf(regler={"lautheit": False})
        e = self.e("c001_00003_dl")
        self.assertEqual((e["q"], e["pruefung"]), ("neu", "naht"))
        self.assertGreater(e["werte"]["naht_db"], 3)
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")

    def test_lautheit_gleicht_an(self):
        self.amp = 20000
        self.lauf()
        self.assertIsNone(self.e("c001_00003_dl")["pruefung"])

    def test_dauer_ausserhalb(self):
        self.lang = 4.0
        self.lauf()
        e = self.e("c001_00004_dl")
        self.assertEqual(e["pruefung"], "dauer")
        self.assertGreater(e["werte"]["dauer_q"], 1.5)

    def test_geaendertes_segment_nur_dieser_satz(self):
        self.lauf()
        n = len(self.calls)
        seg = dict(SEG, c001_00004_dl=[{"t": "„Ich weiß es wirklich nicht.“", "s": "Alice"}])
        Q["c001_00004_dl"] = ("dl", "\"I do not know.\"", "„Ich weiß es wirklich nicht.“")
        try:
            self.werk(seg=seg)
            g = self.lauf()
        finally:
            Q["c001_00004_dl"] = ("dl", "\"I do not know.\"", "„Ich weiß es nicht.“")
        self.assertEqual(self.calls[n:], [("Ich weiß es wirklich nicht.", "Kore")])
        self.assertEqual(g.metriken["offen"], {"de": 1})

    def test_verwaister_satz_entfernt(self):
        self.lauf()
        self.werk(seg={k: v for k, v in SEG.items() if k != "c001_00004_dl"})
        self.lauf()
        self.assertFalse(os.path.exists(self.h("c001_00004_dl.wav")))
        self.assertNotIn("de/c001_00004_dl", self.lesen("510_overlay.json")["eintraege"])

    def test_behalten_und_bauen(self):
        P.entscheidung_setzen("w", "test", behalten=["de/c001_00003_dl"])
        self.lauf()
        e = self.e("c001_00003_dl")
        self.assertEqual((e["q"], e["takes"]), ("behalten", {}))
        self.assertNotIn(("Wer bist du?", "Puck"), self.calls)
        P.entscheidung_setzen("w", "test", bauen=["de/c001_00003_dl"])
        self.lauf()
        self.assertEqual(self.e("c001_00003_dl")["q"], "neu")

    def test_grenze_manuell(self):
        P.entscheidung_setzen("w", "test", grenzen={"de/c001_00003_dl": {"1": [1.3, 2.0]}})
        self.lauf()
        s = self.e("c001_00003_dl")["schnitt"]
        self.assertEqual((s[1]["a"], s[1]["b"]), (1.3, 2.0))

    def test_trocken_schreibt_nichts(self):
        g = self.lauf(trocken=True)
        self.assertEqual(self.calls, [])
        self.assertFalse(os.path.exists(os.path.join(self.wd, "510_overlay.json")))
        self.assertEqual(g.metriken["takes_neu"], {"de": 2})
        self.assertGreater(g.metriken["kosten_usd"], 0)

    def test_mock_dann_live(self):
        config.RUN_MODE = "mock"
        g = self.lauf()
        self.assertEqual(self.e("c001_00003_dl")["q"], "mock")
        self.assertTrue(mock.ist_datei(self.h("c001_00003_dl.wav")))
        config.RUN_MODE = "live"
        g = self.lauf()
        self.assertEqual(self.e("c001_00003_dl")["q"], "neu")
        self.assertEqual(len(self.calls), 2)

    def test_probe(self):
        g = self.lauf(probe=1)
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertEqual(len(self.lesen("510_pruefung.json")["de"]["probe"]), 1)

    def test_grenzen_rechnung(self):
        z = [(0.1, 0.3), (0.4, 0.6), (1.0, 1.2)]
        gz = P.grenzen(z, [0, 0, 1], 24000 * 2, [0, 1])
        self.assertEqual(gz[0], (0, int(0.8 * 24000)))
        self.assertEqual(gz[1], (int(0.8 * 24000), 48000))

    def test_run_py_registriert(self):
        import run
        self.assertIn("510", run.UMGEBAUT)
        self.assertIn("510", run.NEU)


if __name__ == "__main__":
    unittest.main()
