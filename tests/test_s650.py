"""Stage 650 Hoerbuch-Assembler.  py -3.11 -m unittest tests.test_s650"""
import contextlib, io, json, os, subprocess, sys, tempfile, unittest, wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import manifest, mock
from pipeline import s410_casting as s410
from pipeline import status as S
from pipeline import s650_hoerbuch as P

C = {"c001_00001_h": ("h", "Chapter One"), "c001_00002_s": ("s", "Alice sat by the river."),
     "c001_00003_s": ("s", "She was tired."), "c002_00001_h": ("h", "Chapter Two"),
     "c002_00002_s": ("s", "The end came soon.")}
ANS = [{"id": "ansage_titel", "type": "ansage", "position": "anfang", "text": "The Mill.", "pause_after_ms": 700},
       {"id": "ansage_autor", "type": "ansage", "position": "anfang", "text": "by Jane Doe.", "pause_after_ms": 1200},
       {"id": "ansage_sprecher", "type": "ansage", "position": "anfang", "text": "Read by an AI voice.",
        "pause_after_ms": 1500},
       {"id": "ansage_ende", "type": "ansage", "position": "ende", "text": "The End.", "pause_after_ms": 0}]


def dump(o, p):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(o, f)


def wav(p, sek=1.0, seed=1):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    x = np.random.default_rng(seed).normal(0, 0.05, int(24000 * sek))
    with wave.open(p, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


class T650(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.r = self.tmp.name
        self.alt = (config.book_dir, config.work_dir, config.RUN_MODE, config.author_of, s410.stimme)
        config.book_dir = lambda b: os.path.join(self.r, b)
        config.work_dir = lambda b: os.makedirs(os.path.join(self.r, b, "work"), exist_ok=True) or \
            os.path.join(self.r, b, "work")
        config.author_of = lambda b: ""
        config.RUN_MODE = "live"
        s410.stimme = lambda w, lg, *a, **k: "herr_a"

    def tearDown(self):
        config.book_dir, config.work_dir, config.RUN_MODE, config.author_of, s410.stimme = self.alt
        self.tmp.cleanup()

    def werk(self, w="w", kanaele=("epub",), ansagen=ANS, g530="auto", kap190=2, cover=True):
        d = os.path.join(self.r, w)
        dump({"book_slug": w, "quelle": "gutenberg", "gutenberg_id": 1, "quellsprache": "en", "fassung": "original",
              "mandant": "somnio", "titel_original": "The Mill", "autor_name": "Jane Doe",
              "fassungen": [{"sprache": "en", "titel": "The Mill", "titel_quelle": "wikidata"}],
              "produkte": [{"sprache": "en", "inhalt": "hoerbuch", "stufe": "basic", "kanaele": list(kanaele)}],
              "rechte": {"art": "gemeinfrei", "bearbeitung": True, "versichert": {"wer": "t", "wann": "x"}}},
             os.path.join(d, "book.json"))
        dump({"content": {t: {"type": ty, "en": tx} for t, (ty, tx) in C.items()},
              "production": {"pause_after_ms": {t: {"en": 400} for t in C}}, "ansagen": {"en": list(ansagen)}},
             os.path.join(d, "work", "400_regie.json"))
        m = manifest.Manifest(w, "530_pruefung_en", stage="530")
        for i, t in enumerate(list(C) + [a["id"] for a in ansagen]):
            p = os.path.join(d, "fassungen", "en", "audio_final", f"{t}.wav")
            wav(p, 0.8 + 0.1 * (i % 3), seed=i + 1)
            m.setzen(f"hoerbuch/{t}", "x", datei=p, dauer=1.0)
        m.speichern()
        self.m5 = m
        if g530:
            S.ergebnis(w, "530", g530, wer="test")
        if kap190:
            S.ergebnis(w, "190", "auto", metriken={"kapitel": kap190}, wer="test")
        if cover and "extern" in kanaele:
            from PIL import Image
            p = os.path.join(d, "fassungen", "en", "output", "cover_final_en_quadrat.jpg")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            Image.new("RGB", (300, 300), "white").save(p)
            S.ergebnis(w, "615", "auto", wer="test", scope="en:quadrat")

    def lauf(self, w="w", **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return {g.scope: g for g in P.run(w, wer="test", **kw)}

    def man(self, w="w"):
        with open(P.pfad(w, "en"), encoding="utf-8") as f:
            return json.load(f)

    def probe(self, p):
        r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", p],
                           capture_output=True, text=True)
        return json.loads(r.stdout)

    # ---------------------------------------------------------------- Grundfall
    def test_epub_kapitel_zeitmarken_format_620(self):
        self.werk()
        g = self.lauf()["en"]
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        m = self.man()
        self.assertEqual([k["kapitel"] for k in m["kapitel"]], ["anfang", "c001", "c002", "ende"])
        k1 = m["kapitel"][1]
        self.assertEqual(sorted(k1["saetze"]), ["c001_00001_h", "c001_00002_s", "c001_00003_s"])
        a, b = k1["saetze"]["c001_00001_h"]
        self.assertAlmostEqual(a, 0.5, places=2)                     # Kopf-Stille epub
        a2, _ = k1["saetze"]["c001_00002_s"]
        self.assertAlmostEqual(a2 - b, 0.4, places=2)                # Pause aus 400
        self.assertLessEqual(max(e for _, e in k1["saetze"].values()), k1["dauer"])
        p = os.path.join(self.r, "w", k1["datei"])
        self.assertTrue(p.endswith(os.path.join("hoerbuch", "epub", "02_c001.mp3")))
        s = self.probe(p)["streams"][0]
        self.assertEqual((s["sample_rate"], s["channels"]), ("24000", 1))
        e = m["profile"]["epub"]["kapitel"][1]
        self.assertLessEqual(abs(e["lufs"] + 18), 1.0)
        self.assertEqual(S.zustand("w", "650", scope="en"), "frei")
        from pipeline import s620_epub_original as s620
        kap = [{"titel_id": "c001_00001_h", "absaetze": [{"teile": [{"id": "c001_00002_s"}, {"id": "c001_00003_s"}]}]},
               {"titel_id": "c002_00001_h", "absaetze": [{"teile": [{"id": "c002_00002_s"}]}]}]
        out, fehl, met = s620.audio_kapitel("w", "en", kap)
        self.assertEqual((fehl, met["smil_abdeckung"]), ([], 1.0))

    def test_resume_nur_geaendertes_kapitel(self):
        self.werk()
        self.lauf()
        m = self.man()
        mt = {k["kapitel"]: os.path.getmtime(os.path.join(self.r, "w", k["datei"])) for k in m["kapitel"]}
        self.lauf()
        self.assertEqual(mt, {k["kapitel"]: os.path.getmtime(os.path.join(self.r, "w", k["datei"]))
                              for k in self.man()["kapitel"]})
        p = os.path.join(self.r, "w", "fassungen", "en", "audio_final", "c002_00002_s.wav")
        wav(p, 1.5, seed=99)
        m5 = manifest.Manifest("w", "530_pruefung_en")
        m5.setzen("hoerbuch/c002_00002_s", "y", datei=p)
        m5.speichern()
        self.lauf()
        neu = {k["kapitel"]: os.path.getmtime(os.path.join(self.r, "w", k["datei"])) for k in self.man()["kapitel"]}
        self.assertEqual([k for k in neu if neu[k] != mt[k]], ["c002"])

    # ---------------------------------------------------------------- Extern
    def test_extern_hoerprobe_freigabe_tags_cover_m4b(self):
        self.werk(kanaele=("epub", "extern"))
        with contextlib.redirect_stdout(io.StringIO()):
            P.main(["w", "--wer", "CK", "--ausgabe", "beide"])
        self.assertEqual(S.zustand("w", "650", scope="en"), "mensch")
        self.assertTrue(os.path.exists(os.path.join(self.r, "w", "work", "_650", "en", "hoerprobe_extern.mp3")))
        m = self.man()
        self.assertEqual(m["profil"], "epub")
        ex = m["profile"]["extern"]["kapitel"][1]
        d = self.probe(os.path.join(self.r, "w", ex["datei"]))
        a = [s for s in d["streams"] if s["codec_type"] == "audio"][0]
        self.assertEqual(a["sample_rate"], "44100")
        self.assertTrue(any(s["codec_type"] == "video" for s in d["streams"]))       # Cover
        tags = {k.lower(): v for k, v in d["format"].get("tags", {}).items()}
        self.assertEqual((tags.get("album"), tags.get("artist")), ("The Mill", "Jane Doe"))
        self.assertIn("herr_a", tags.get("comment", ""))
        self.assertLessEqual(ex["peak"], -3.0)
        m4 = os.path.join(self.r, "w", m["profile"]["extern"]["m4b"]["datei"])
        r = subprocess.run(["ffprobe", "-v", "error", "-show_chapters", "-of", "json", m4], capture_output=True, text=True)
        self.assertEqual(len(json.loads(r.stdout)["chapters"]), 4)
        with contextlib.redirect_stdout(io.StringIO()):
            P.main(["w", "--wer", "CK", "--freigeben"])
        self.assertEqual(S.zustand("w", "650", scope="en"), "frei")
        self.assertEqual(self.lauf()["en"].ergebnis["ergebnis"], "auto")        # einmal je Werk x Sprache

    def test_extern_ohne_cover_stopp(self):
        self.werk(kanaele=("extern",), cover=False)
        g = self.lauf()["en"]
        self.assertEqual((g.ergebnis["ergebnis"], g.ergebnis["ruecksprung"]), ("stopp", "615"))

    # ---------------------------------------------------------------- Stopps / Mensch
    def test_luecke_mock_530_kapitel(self):
        self.werk()
        os.remove(os.path.join(self.r, "w", "fassungen", "en", "audio_final", "c001_00003_s.wav"))
        g = self.lauf()["en"]
        self.assertEqual((g.ergebnis["ergebnis"], g.ergebnis["ruecksprung"]), ("stopp", "530"))
        self.werk("m")
        p = os.path.join(self.r, "m", "fassungen", "en", "audio_final", "c001_00002_s.wav")
        mock.wav(p)
        m5 = manifest.Manifest("m", "530_pruefung_en")
        m5.setzen("hoerbuch/c001_00002_s", "x", datei=p)
        m5.speichern()
        self.assertEqual(self.lauf("m")["en"].ergebnis["ergebnis"], "stopp")
        self.werk("g", g530="mensch")
        self.assertEqual(self.lauf("g")["en"].ergebnis["ruecksprung"], "530")
        self.werk("k", kap190=3)
        g = self.lauf("k")["en"]
        self.assertEqual((g.ergebnis["ergebnis"], g.ergebnis["ruecksprung"]), ("stopp", "400"))

    def test_ansagen_fehlen_mensch_und_aus(self):
        self.werk(ansagen=[a for a in ANS if a["id"] != "ansage_ende"])
        g = self.lauf()["en"]
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertIn("ansage_ende", g.ergebnis["gruende"][0])
        with contextlib.redirect_stdout(io.StringIO()):
            P.main(["w", "--wer", "CK", "--ansagen", "aus"])
        m = self.man()
        self.assertEqual([k["kapitel"] for k in m["kapitel"]], ["c001", "c002"])
        self.assertEqual(sorted(os.listdir(P.ausgabe_dir("w", "en", "epub"))), ["01_c001.mp3", "02_c002.mp3"])

    def test_profil_regler_und_trocken(self):
        self.werk()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(P.main(["w", "--trocken"]), 0)
        self.assertFalse(os.path.exists(P.pfad("w", "en")))
        with contextlib.redirect_stdout(io.StringIO()):
            P.main(["w", "--wer", "CK", "--profil", "epub:kopf=1.0", "--profil", "epub:bitrate=96k"])
        k = self.man()["kapitel"][1]
        self.assertAlmostEqual(k["saetze"]["c001_00001_h"][0], 1.0, places=2)
        self.assertEqual(self.man()["profile"]["epub"]["werte"]["bitrate"], "96k")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(P.main(["w", "--wer", "CK", "--profil", "epub:quatsch=1"]), 1)


if __name__ == "__main__":
    unittest.main()
