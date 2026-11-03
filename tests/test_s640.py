"""Stage 640 Teaser.  py -3.11 -m unittest tests.test_s640"""
import contextlib, io, json, os, sys, tempfile, unittest, wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import mock
from pipeline import s410_casting as s410
from pipeline import status as S
from pipeline import s640_teaser as P

VOR, NACH = 0.3, 0.5
K600 = {"koeder": [{"en": "The night was dark and the river ran high past the old mill.",
                    "de": "Die Nacht war dunkel und der Fluss stieg hoch an der alten Muehle vorbei."}],
        "einordnung": [{"en": "A _quiet_ classic about loss and courage in a small town.",
                        "de": "Ein leiser Klassiker ueber Verlust und Mut in einer kleinen Stadt."}],
        "autor": [{"en": "Jane Doe wrote it in her last years by the sea.",
                   "de": "Jane Doe schrieb es in ihren letzten Jahren am Meer."}]}


def dump(o, p):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(o, f)


def wav(p, sek, amp=0.1, seed=1):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    r = np.random.default_rng(seed)
    x = np.concatenate([np.zeros(int(24000 * VOR)), r.normal(0, amp, int(24000 * sek)), np.zeros(int(24000 * NACH))])
    with wave.open(p, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


class T640(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.r = self.tmp.name
        self.alt = (config.book_dir, config.work_dir, config.RUN_MODE, config.author_of, P.synth_gemini,
                    P.synth_chatterbox, P.fa_zeiten, P.sprache_pruefen, P.werkzeuge, s410.nutzbar)
        config.book_dir = lambda b: os.path.join(self.r, b)
        config.work_dir = lambda b: os.makedirs(os.path.join(self.r, b, "work"), exist_ok=True) or \
            os.path.join(self.r, b, "work")
        config.author_of = lambda b: ""
        config.RUN_MODE = "live"
        self.calls, self.cb_calls, self.kippt, self.faellt, self.fe = [], [], {}, set(), []
        P.synth_gemini = self.gemini
        P.synth_chatterbox = self.chatterbox
        P.fa_zeiten = lambda jobs, w, lg, art: {k: [(VOR, VOR + self.sek(t))] for k, p, t in jobs}
        P.sprache_pruefen = self.whisper
        P.werkzeuge = lambda rg: list(self.fe)
        s410.nutzbar = lambda name, lg, engine, reg=None, std=None: (
            True, {"gemini_id": f"G-{name}", "modell": "m"} if engine == "gemini" else {"referenz": None}, "")
        self.werk("w")

    def tearDown(self):
        (config.book_dir, config.work_dir, config.RUN_MODE, config.author_of, P.synth_gemini, P.synth_chatterbox,
         P.fa_zeiten, P.sprache_pruefen, P.werkzeuge, s410.nutzbar) = self.alt
        self.tmp.cleanup()

    # ---------------------------------------------------------------- Hilfen
    def sek(self, text):
        n = len(" ".join(text)) if isinstance(text, list) else len(text)
        return max(0.6, n * 0.065 - VOR - NACH + 0.2)

    def gemini(self, werk, lg, jobs, info):
        out = {}
        for tid, text, st, ziel in jobs:
            self.calls.append((lg, tid, st, info["gemini_id"]))
            if (lg, tid) in self.faellt:
                continue
            wav(ziel, self.sek(text), seed=len(self.calls))
            out[tid] = ziel
        return out

    def chatterbox(self, werk, lg, jobs, info, rd):
        self.cb_calls.append((lg, [j[0] for j in jobs], info["stimme"]))
        out = {}
        for tid, text, st, ziel in jobs:
            wav(os.path.join(rd, f"{tid}.wav"), self.sek(text))
            out[tid] = os.path.join(rd, f"{tid}.wav")
        return out, {}

    def whisper(self, jobs, werk, lg, art):
        out = {}
        for k, p in jobs:
            n = self.kippt.get((lg, k), 0)
            if n:
                self.kippt[(lg, k)] = n - 1
                out[k] = {"top": "xx", "p": 0.01, "text": "zzz", "dauer": 3.0}
            else:
                with open(config.work_path(werk, "600_klappentext"), encoding="utf-8") as f:
                    bl = json.load(f)["blurb"]
                txt = next(s["text"] for s in P.saetze(bl, lg) if s["id"] == k)
                out[k] = {"top": lg, "p": 0.99, "text": txt, "dauer": 3.0}
        return out

    def werk(self, w, produkte=None, mandant="somnio", k600=None, meta=None, g600="auto"):
        os.makedirs(os.path.join(self.r, w, "work"), exist_ok=True)
        b = {"book_slug": w, "quelle": "gutenberg", "gutenberg_id": 1, "quellsprache": "en", "fassung": "modernisiert",
             "mandant": mandant, "titel_original": "The Mill",
             "produkte": produkte or [{"sprache": "en", "inhalt": "text", "kanaele": ["taella"]},
                                      {"sprache": "de", "inhalt": "text", "kanaele": ["taella"]}],
             "rechte": {"art": "gemeinfrei", "bearbeitung": True, "versichert": {"wer": "t", "wann": "x"}}}
        dump(b, os.path.join(self.r, w, "book.json"))
        self.k600(w, k600, meta)
        if g600:
            S.ergebnis(w, "600", g600, wer="test")

    def k600(self, w="w", blurb=None, meta=None):
        d = {"schema": 2, "autor": "Jane Doe", "wirkungssprache": "en", "blurb": blurb or K600,
             "meta": meta or {"genre": "Krimi", "genre_gruppe": "Krimi", "ton": "dark, tense",
                              "hauptfigur_geschlecht": "weiblich"}}
        dump(d, os.path.join(self.r, w, "work", "600_klappentext.json"))

    def casting(self, w, lg, stufe, stimme="erz_x", gid="Charon", ref=None):
        rollen = {lg: {stufe: {"erzaehler": {"stimme": stimme, "gemini_id": gid, "referenz": ref}, "ensemble": []}}}
        c = {"schema": s410.SCHEMA, "rollen": rollen, "freigabe": {"hash": s410.kern(rollen)}}
        dump(c, os.path.join(self.r, w, "work", "casting.json"))

    def lauf(self, w="w", **kw):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            gs = {g.scope: g for g in P.run(w, wer="test", **kw)}
        self.out = out.getvalue()
        return gs

    def erg(self, gs):
        return {s: g.ergebnis["ergebnis"] for s, g in gs.items()}

    def man(self, w="w"):
        with open(config.work_path(w, "640_teaser"), encoding="utf-8") as f:
            return json.load(f)

    # ---------------------------------------------------------------- Stimme
    def test_genre_zuordnung(self):
        f = lambda gr, hf=None, ag=None: P.genre_geschlecht({"genre_gruppe": gr, "hauptfigur_geschlecht": hf},
                                                             {"autor_geschlecht": ag})[0]
        self.assertEqual(f("Krimi", "weiblich"), "maennlich")
        self.assertEqual(f("Roman allgemein", "weiblich"), "weiblich")
        self.assertEqual(f("Roman allgemein", "unklar"), "maennlich")
        self.assertEqual(f("Kinder & Jugend", "maennlich"), "maennlich")
        self.assertEqual(f("Liebe", "maennlich"), "weiblich")
        self.assertEqual(f("Sachtext", None, "maennlich"), "maennlich")
        self.assertEqual(f("Lyrik"), "weiblich")
        self.assertEqual(P.genre_geschlecht({"genre": "Spionageroman"}, {})[0], "maennlich")

    def test_sprachen_nur_taella(self):
        self.werk("t", produkte=[{"sprache": "en", "inhalt": "text", "kanaele": ["taella"]},
                                 {"sprache": "de", "inhalt": "text", "kanaele": ["epub"]}])
        self.assertEqual(list(self.lauf("t")), ["en"])

    # ---------------------------------------------------------------- Grundfall
    def test_grundfall_genre_gemini_und_resume(self):
        gs = self.lauf()
        self.assertEqual(self.erg(gs), {"en": "auto", "de": "auto"}, gs["en"].bericht())
        self.assertEqual({c[3] for c in self.calls}, {"G-herr_a"})          # Krimi -> maennlich
        self.assertTrue(all("dark, tense" in c[2] for c in self.calls))
        for lg in ("en", "de"):
            td, ad = P.blurb_dirs("w", lg)
            self.assertEqual(sorted(os.listdir(ad)), ["autor_01.mp3", "einordnung_01.mp3", "koeder_01.mp3",
                                                      "manifest.json"])
            with open(os.path.join(td, "blurb.json"), encoding="utf-8") as f:
                bj = json.load(f)
            self.assertEqual([s["id"] for s in bj["snippets"]], ["koeder_01", "einordnung_01", "autor_01"])
            with open(os.path.join(ad, "manifest.json"), encoding="utf-8") as f:
                am = json.load(f)
            self.assertEqual((am["engine"], am["voice"], am["voice_quelle"]), ("gemini", "herr_a", "genre"))
        e = self.man()["eintraege"]["en/einordnung_01"]
        self.assertEqual(e["text"], "A quiet classic about loss and courage in a small town.")
        self.assertLessEqual(max(e["rand"]), 0.15)
        self.assertLessEqual(abs(e["lufs"] + 18), 1.0)
        self.assertLessEqual(e["peak"], -1.0)
        self.assertIn("Markup-Reste", " ".join(gs["en"].ergebnis["hinweise"]))
        self.assertEqual(S.zustand("w", "640"), "frei")
        # Resume: nichts neu
        self.calls.clear()
        self.assertEqual(self.erg(self.lauf()), {"en": "auto", "de": "auto"})
        self.assertEqual(self.calls, [])
        # geaenderter Satz -> nur dieser neu
        neu = json.loads(json.dumps(K600))
        neu["autor"][0]["de"] = "Jane Doe schrieb es spaet am Meer, in einem kleinen Haus."
        self.k600(blurb=neu)
        self.lauf()
        self.assertEqual([(c[0], c[1]) for c in self.calls], [("de", "autor_01")])

    def test_aussprachehinweis_nur_zielsprache_mit_autor(self):
        self.lauf()
        st = {(c[0], c[1]): c[2] for c in self.calls}
        self.assertIn("Jane Doe pronounced as in English", st[("de", "autor_01")])
        self.assertNotIn("pronounced", st[("en", "autor_01")])
        self.assertNotIn("pronounced", st[("de", "koeder_01")])

    def test_audio_bestellt_erzaehler_aus_casting(self):
        prod = [{"sprache": "en", "inhalt": "hoerbuch", "stufe": "premium", "kanaele": ["taella"]},
                {"sprache": "de", "inhalt": "text", "kanaele": ["taella"]}]
        self.werk("a", produkte=prod)
        gs = self.lauf("a")
        self.assertEqual(gs["en"].ergebnis["ergebnis"], "stopp")              # 410 nicht frei
        self.assertEqual(gs["en"].ergebnis["ruecksprung"], "410")
        S.ergebnis("a", "410", "auto", wer="test")
        self.casting("a", "en", "premium")
        gs = self.lauf("a")
        self.assertEqual(self.erg(gs), {"en": "auto", "de": "auto"})
        st = {c[0]: c[3] for c in self.calls}
        self.assertEqual(st, {"en": "Charon", "de": "G-herr_a"})
        self.assertEqual(self.man("a")["meta"]["en"]["quelle"], "casting")

    def test_chatterbox_basic(self):
        prod = [{"sprache": "en", "inhalt": "hoerbuch", "stufe": "basic", "kanaele": ["taella"]}]
        self.werk("c", produkte=prod)
        S.ergebnis("c", "410", "auto", wer="test")
        self.casting("c", "en", "basic", stimme=s410.CB_STANDARD, gid=None)
        gs = self.lauf("c")
        self.assertEqual(self.erg(gs), {"en": "auto"}, gs["en"].bericht())
        self.assertEqual(self.cb_calls, [("en", ["koeder_01", "einordnung_01", "autor_01"], s410.CB_STANDARD)])
        self.assertEqual(self.calls, [])
        self.assertEqual(self.man("c")["meta"]["en"]["stil"], "")

    # ---------------------------------------------------------------- Pruefung / Wiederholung
    def test_auffaellig_2x_neu_dann_mensch_annehmen(self):
        self.kippt[("en", "koeder_01")] = 9
        gs = self.lauf()
        self.assertEqual(gs["en"].ergebnis["ergebnis"], "mensch")
        self.assertIn("koeder_01 (gekippt)", gs["en"].ergebnis["gruende"][0])
        self.assertEqual(sum(1 for c in self.calls if c[:2] == ("en", "koeder_01")), 3)
        self.assertEqual(self.man()["eintraege"]["en/koeder_01"]["versuche"], 3)
        self.assertEqual(gs["de"].ergebnis["ergebnis"], "auto")
        # erneuter Lauf: keine weiteren Versuche
        self.calls.clear()
        self.assertEqual(self.lauf()["en"].ergebnis["ergebnis"], "mensch")
        self.assertEqual(self.calls, [])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(P.main(["w", "--wer", "CK", "--annehmen", "en:koeder_01", "--grund", "klingt gut"]), 0)
        self.assertEqual(S.zustand("w", "640", scope="en"), "frei")
        # neue Datei (--satz) -> Annahme gilt nicht mehr, Zaehler neu
        self.kippt[("en", "koeder_01")] = 1
        gs = self.lauf(satz={"en/koeder_01"})
        self.assertEqual(gs["en"].ergebnis["ergebnis"], "auto")
        self.assertEqual(self.man()["eintraege"]["en/koeder_01"]["versuche"], 2)

    def test_dauer_auffaellig(self):
        alt = self.gemini

        def kurz(werk, lg, jobs, info):
            out = alt(werk, lg, jobs, info)
            for tid, text, st, ziel in jobs:
                if lg == "en" and tid == "einordnung_01":
                    wav(ziel, 0.4)
            return out
        P.synth_gemini = kurz
        gs = self.lauf()
        self.assertEqual(gs["en"].ergebnis["ergebnis"], "mensch")
        self.assertIn("einordnung_01 (dauer)", gs["en"].ergebnis["gruende"][0])
        self.assertEqual(gs["en"].metriken["auffaellig_dauer"], 1)

    def test_satz_ohne_audio_stopp(self):
        self.faellt.add(("de", "autor_01"))
        gs = self.lauf()
        self.assertEqual(gs["de"].ergebnis["ergebnis"], "stopp")
        self.assertIn("Abdeckung 2/3", gs["de"].ergebnis["gruende"][0])
        self.faellt.clear()
        self.calls.clear()
        self.assertEqual(self.lauf()["de"].ergebnis["ergebnis"], "auto")
        self.assertEqual([c[:2] for c in self.calls], [("de", "autor_01")])

    # ---------------------------------------------------------------- Stopps / Mandant / Mock
    def test_gate600_klappentext_werkzeuge(self):
        self.werk("x", g600="mensch")
        self.assertEqual(self.erg(self.lauf("x")), {"en": "stopp", "de": "stopp"})
        self.assertEqual(self.calls, [])
        self.werk("y", k600={"koeder": [], "einordnung": [], "autor": []})
        g = self.lauf("y")["en"]
        self.assertEqual((g.ergebnis["ergebnis"], g.ergebnis["ruecksprung"]), ("stopp", "600"))
        self.fe = ["ffmpeg fehlt"]
        self.assertEqual(self.lauf()["en"].ergebnis["ergebnis"], "stopp")

    def test_stimme_nicht_nutzbar_stopp(self):
        s410.nutzbar = lambda *a, **k: (False, {}, "nicht im Archiv")
        g = self.lauf()["en"]
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertIn("nicht im Archiv", g.ergebnis["gruende"][0])

    def test_verlag_mensch_freigabe_gilt(self):
        self.werk("v", mandant="verlag:x")
        self.assertEqual(self.erg(self.lauf("v")), {"en": "mensch", "de": "mensch"})
        for lg in ("en", "de"):
            S.entscheiden("v", "640", "frei", wer="CK", grund="ok", scope=lg)
        self.lauf("v")
        self.assertEqual(S.zustand("v", "640", scope="en"), "frei")

    def test_mock_lauf_und_mock_im_live(self):
        config.RUN_MODE = "mock"
        gs = self.lauf()
        self.assertEqual(self.erg(gs), {"en": "auto", "de": "auto"})
        self.assertEqual(self.calls, [])
        p = os.path.join(P.blurb_dirs("w", "en")[1], "koeder_01.mp3")
        self.assertTrue(mock.ist_datei(p))
        config.RUN_MODE = "live"
        gs = self.lauf()
        self.assertEqual(self.erg(gs), {"en": "auto", "de": "auto"})
        self.assertEqual(len(self.calls), 6)
        self.assertFalse(mock.ist_datei(p))

    # ---------------------------------------------------------------- Ablage / Regler
    def test_altdatei_verwaist_kosten(self):
        dump({"languages": ["en"], "snippets": 3, "done": 3},
                  config.work_path("w", "640_teaser"))
        ad = P.blurb_dirs("w", "en")[1]
        os.makedirs(ad)
        with open(os.path.join(ad, "koeder_02.mp3"), "wb") as f:
            f.write(b"MOCK")
        gs = self.lauf(nur_kosten=True)
        self.assertGreater(gs["en"].metriken["kosten_schaetzung_usd"], 0)
        self.assertIn("Kostenschaetzung", self.out)
        self.assertEqual(self.calls, [])
        self.lauf()
        self.assertTrue(os.path.exists(config.work_path("w", "640_teaser_alt")))
        self.assertEqual(self.man()["schema"], 1)
        self.assertFalse(os.path.exists(os.path.join(ad, "koeder_02.mp3")))
        # Satz entfaellt in 600 -> Datei und Eintrag weg
        neu = {k: v for k, v in K600.items() if k != "autor"}
        self.k600(blurb=neu)
        self.lauf()
        self.assertNotIn("en/autor_01", self.man()["eintraege"])
        self.assertFalse(os.path.exists(os.path.join(ad, "autor_01.mp3")))

    def test_regler_stimme_stil(self):
        with contextlib.redirect_stdout(io.StringIO()):
            rc = P.main(["w", "--wer", "CK", "--stimme", "de=frau_b", "--stil", "*=slow and soft", "--sprache", "de"])
        self.assertEqual(rc, 0)
        self.assertEqual({c[3] for c in self.calls}, {"G-frau_b"})
        self.assertTrue(all(c[2].startswith("slow and soft") for c in self.calls))
        self.assertEqual(self.man()["meta"]["de"]["quelle"], "manuell")
        # Regler weg -> Genre-Stimme, neu vertont
        self.calls.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            P.main(["w", "--wer", "CK", "--stimme", "de=weg", "--sprache", "de"])
        self.assertEqual({c[3] for c in self.calls}, {"G-herr_a"})


if __name__ == "__main__":
    unittest.main()
