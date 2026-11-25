"""AP Fish-Regie (25.11.2026): fish_motor, Stage 410 (Motor Fish), 430 Fish-Regie, 500/510 Fish-Pfad.
py -3.11 -m unittest tests.test_fish"""
import base64, contextlib, io, json, os, sys, unittest, wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import fish_motor as F
from pipeline import status as S
from pipeline import s410_casting as P
from tests.test_s410 import T410


class TFishMotor(unittest.TestCase):
    def test_motor(self):
        self.assertEqual(F.motor({}, "de"), "gemini")
        self.assertEqual(F.motor({"audio_motor": "fish"}, "en"), "fish")
        self.assertEqual(F.motor({"audio_motor": {"de": "fish"}}, "en"), "gemini")
        self.assertEqual(F.motor({"audio_motor": {"de": "fish"}}, "de"), "fish")
        self.assertEqual(F.motor({"audio_motor": "quatsch"}, "de"), "gemini")

    def test_grundhaltung(self):
        sb = {"name": "March Hare", "name_de": "Märzhase",
              "merkmale": {"tonlage": "hoch", "tempo": "schnell", "temperament": ["albern", "cholerisch"]}}
        g = F.grundhaltung("March Hare", sb)
        self.assertEqual(g, "voicing the March Hare: giddy, silly, irascible, fast, high-pitched")
        self.assertTrue(F.grundhaltung_ok(g))
        self.assertEqual(F.grundhaltung("Alice", {"name_de": "Alice", "merkmale": {}}), "voicing Alice")
        lang = {"merkmale": {"temperament": ["albern"] * 3, "tempo": "schnell"}}
        self.assertLessEqual(len(F.grundhaltung("X" * 110, lang)), F.GRUNDHALTUNG_MAX)
        self.assertFalse(F.grundhaltung_ok("[laughs] x"))

    def test_sse_und_wav(self):
        wav = F.wav_bytes(b"\x01\x00" * 2400)
        roh = bytearray(wav)
        roh[4:8] = b"\xff\xff\xff\xff"
        i = roh.find(b"data")
        roh[i + 4:i + 8] = b"\xff\xff\xff\xff"
        with wave.open(io.BytesIO(F.fix_wav(bytes(roh)))) as w:
            self.assertEqual(w.getnframes(), 2400)
        evs = [{"audio_base64": base64.b64encode(wav[:100]).decode(), "chunk_seq": 0, "chunk_audio_offset_sec": 0,
                "alignment": {"segments": [{"text": "Häs", "start": 0, "end": 0.05}]}},
               {"audio_base64": base64.b64encode(wav[100:]).decode(), "chunk_seq": 0, "chunk_audio_offset_sec": 0,
                "alignment": {"segments": [{"text": "Häs", "start": 0, "end": 0.05},
                                           {"text": "chen", "start": 0.05, "end": 0.1}]}},
               {"audio_base64": "", "chunk_seq": 1, "chunk_audio_offset_sec": 0.1,
                "alignment": {"segments": [{"text": "lief", "start": 0, "end": 0.04}]}}]
        s = "".join("data: " + json.dumps(e, ensure_ascii=False) + "\n\n" for e in evs).encode("utf-8")
        pcm, w, sr, n = F.sse_parsen(s)
        self.assertEqual((len(pcm), sr, n), (4800, 24000, 2))
        self.assertEqual([x["w"] for x in w], ["Häs", "chen", "lief"])
        self.assertEqual(w[2]["a"], 0.1)

    def test_modell_rueckfall(self):
        F._modell_pruefen({"x-model": "drama-3"})
        F._modell_pruefen({})
        with self.assertRaises(F.ModellRueckfall):
            F._modell_pruefen({"x-model": "s2.1-pro"})


class T430Overlay(unittest.TestCase):
    def test_overlay_plus(self):
        from pipeline import s430_fish_regie as R
        wr = {"betonung": 5, "emotion": 5, "tempo": 5}
        m = {"stimmung": "gespannt", "intensitaet": 2, "nonverbal": "—", "vortrag": "normal", "betonung": None}
        self.assertEqual(R.moment_text(m, wr), "tense")
        self.assertEqual(R.moment_text(m, wr, 1), "very tense")
        self.assertEqual(R.moment_text(dict(m, intensitaet=3), wr, 2), "extremely tense")   # Deckel 4
        self.assertEqual(R.anweisung_bauen("voicing X", m, wr, 1), "[voicing X; very tense]")
        self.assertTrue(R._regler_gueltig(dict(R.REGLER_STD)))
        self.assertFalse(R._regler_gueltig(dict(R.REGLER_STD, overlay_plus=3)))


class T410Fish(T410):
    def test_fish_casting(self):
        self.werk(produkte=self.HS, extra={"audio_motor": "fish"})
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch", g.bericht())
        bs = P.laden("w")["rollen"]["en"]["premium"]
        self.assertEqual(bs["engine"], "fish")
        self.assertNotIn("fish_grundhaltung", bs["erzaehler"])
        ens = {e["figur"]: e for e in bs["ensemble"]}
        self.assertEqual(ens["Alice"]["fish_grundhaltung"], "voicing Alice: curious, high-pitched, young")
        self.assertEqual(ens["Alice"]["fish_grundhaltung_quelle"], "auto")
        self.assertTrue(ens["Alice"]["vc_ziel"].endswith("w_jung/klon_en.wav"))
        self.assertIsNone(ens["Alice"]["gemini_id"])
        S.entscheiden("w", "410", "frei", "CK", "Hoerprobe ok")
        self.assertEqual(self.lauf().ergebnis["ergebnis"], "auto")
        self.assertTrue(P.freigegeben(P.laden("w")))
        with self.assertRaises(ValueError):                       # freigegeben -> nur mit Grund
            self.lauf(regler={"grundhaltung": ["Hatter=voicing the Hatter: theatrical"]})
        g = self.lauf(regler={"grundhaltung": ["Hatter=voicing the Hatter: theatrical", "Alice=-"]}, grund="CK")
        c = P.laden("w")
        ens = {e["figur"]: e for e in c["rollen"]["en"]["premium"]["ensemble"]}
        self.assertEqual(ens["Hatter"]["fish_grundhaltung"], "voicing the Hatter: theatrical")
        self.assertEqual(ens["Alice"]["fish_grundhaltung_quelle"], "ohne")
        self.assertFalse(P.freigegeben(c))                         # Grundhaltung im Freigabe-Hash

    def test_gemini_unveraendert(self):
        self.werk(produkte=self.HS)
        self.lauf()
        bs = P.laden("w")["rollen"]["en"]["premium"]
        self.assertEqual(bs["engine"], "gemini")
        self.assertNotIn("fish_grundhaltung", bs["ensemble"][0])


class T430(T410):
    def vorbereiten(self):
        from pipeline import s430_fish_regie as R
        self.werk(produkte=self.HS, extra={"audio_motor": "fish", "audio_regler": {"betonung": 5, "emotion": 8,
                                                                                  "tempo": 5}})
        self.lauf()
        S.entscheiden("w", "410", "frei", "CK", "ok")
        self.lauf()
        sp = {"schema": 1, "saetze": {
            "c001_00003_dl": {"en": {"seg": [{"t": "\"Who are you?\" ", "s": "Hatter"},
                                             {"t": "said the Hatter.", "s": "Erzaehler"}]}},
            "c001_00004_dl": {"en": {"seg": [{"t": "\"I am Alice,\" ", "s": "Alice"},
                                             {"t": "she said.", "s": "Erzaehler"}]}}}}
        with open(os.path.join(self.d, "work", "420_sprecher.json"), "w", encoding="utf-8") as f:
            json.dump(sp, f)
        for st in ("420",):
            S.ergebnis("w", st, "auto", wer="test")
        self.antworten = [json.dumps({"c001_00003_dl_00": {"s": "gespannt", "i": 3, "n": "staunen", "b": "you",
                                                           "v": "normal"},
                                      "c001_00004_dl_00": {"s": "quatsch", "i": 2}})]
        self.n_llm = 0
        return R

    def test_fish_regie(self):
        R = self.vorbereiten()
        with contextlib.redirect_stdout(io.StringIO()):
            g = R.run("w", wer="test")
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertTrue(any("Moment ungueltig" in h for h in g.ergebnis["hinweise"]))
        d = R.laden("w")["sprachen"]["en"]
        bt = {x["id"]: x for x in d["beitraege"]}
        h = bt["c001_00003_dl_00"]
        self.assertEqual(h["fig"], "Hatter")
        gh = P.laden("w")["rollen"]["en"]["premium"]
        gh = {e["figur"]: e for e in gh["ensemble"]}["Hatter"]["fish_grundhaltung"]
        self.assertEqual(h["anweisung"], f"[{gh}; extremely tense] [gasps]")   # emotion 8 -> Stufe +1
        self.assertEqual(h["text_fish"], "\"Who are <emphasis>you</emphasis>?\"")
        self.assertEqual(bt["c001_00003_dl_01"]["anweisung"], "")              # Erzaehler ohne Tag
        self.assertTrue(bt["c001_00004_dl_00"]["anweisung"].startswith("[voicing Alice"))
        self.assertEqual(bt["c001_00002_s_00"]["fig"], "Erzaehler")
        self.assertEqual({x["block"] for x in d["beitraege"]}, {1})
        self.assertEqual(self.n_llm, 1)
        with contextlib.redirect_stdout(io.StringIO()):            # Wiederholung: Checkpoint, kein LLM
            R.run("w", wer="test")
        self.assertEqual(self.n_llm, 1)
        R.anweisung_setzen("w", "en", "c001_00004_dl_00", "[voicing Alice: indignant]")
        with contextlib.redirect_stdout(io.StringIO()):
            R.run("w", wer="test")
        bt = {x["id"]: x for x in R.laden("w")["sprachen"]["en"]["beitraege"]}
        self.assertEqual(bt["c001_00004_dl_00"]["anweisung"], "[voicing Alice: indignant]")
        self.assertIn("[voicing Alice: indignant] \"I am Alice,\"", R.block_text(list(bt.values())))

    def test_500_fish(self):
        import numpy as np, re as _re
        from pipeline import s500_vertonung_gemini as V
        from pipeline import manifest
        R = self.vorbereiten()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(R.run("w", wer="test").ergebnis["ergebnis"], "auto")
        aufrufe = []

        def tts(text, ref):
            aufrufe.append(text)
            sauber = _re.sub(r"<[^>]+>|\[[^\]]*\]", " ", text)
            ww, t, y = [], 0.05, []
            for w in sauber.split():
                ww.append({"w": w, "a": round(t, 3), "b": round(t + 0.3, 3)})
                y += [np.sin(np.arange(int(0.3 * 24000)) / 5) * 0.3, np.zeros(int(0.1 * 24000))]
                t += 0.4
            y = np.concatenate([np.zeros(int(0.05 * 24000))] + y).astype("float32")
            return F.wav_bytes((y * 32767).astype("<i2").tobytes()), ww, {"bytes": len(text.encode())}
        alt = (F.tts_zeitmarken, F.fish_id, getattr(config, "KOSTEN_KLEINBETRAG_USD", None))
        F.tts_zeitmarken, F.fish_id = tts, lambda st, lg, anlegen=False: "fid_test"
        config.KOSTEN_KLEINBETRAG_USD = 0.0
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                g = V.run("w", wer="test")
            self.assertEqual(g.ergebnis["ergebnis"], "mensch", g.bericht())        # Kosten nicht freigegeben
            self.assertEqual(aufrufe, [])
            with contextlib.redirect_stdout(io.StringIO()):
                g = V.run("w", wer="test", kosten_freigeben=1.0)
            self.assertNotEqual(g.ergebnis["ergebnis"], "stopp", g.bericht())
            self.assertEqual(len(aufrufe), 1)                                        # ein Block
            self.assertIn("[voicing Alice", aufrufe[0])
            m = manifest.Manifest("w", "500_vertonung")
            e = m.get("en/c001_00003_dl")
            self.assertEqual(e["engine"], "fish")
            sp = e["spannen"]
            self.assertEqual([x["fig"] for x in sp], ["Hatter", "Erzaehler"])
            self.assertGreater(sp[0]["b"], 0.4)
            self.assertAlmostEqual(sp[1]["a"], sp[0]["b"])
            self.assertTrue(os.path.exists(os.path.join(self.d, "fassungen", "en", "audio", "c001_00002_s.wav")))
            with contextlib.redirect_stdout(io.StringIO()):                          # Resume: kein neuer Aufruf
                V.run("w", wer="test", kosten_freigeben=1.0)
            self.assertEqual(len(aufrufe), 1)
            with contextlib.redirect_stdout(io.StringIO()):                          # Satz neu -> Block neu
                V.run("w", wer="test", kosten_freigeben=1.0, saetze=["c001_00004_dl"])
            self.assertEqual(len(aufrufe), 2)
            # ---- 510 Fish -> VC (VC im Test = Identitaet ueber den Mock-Zweig von vc_lauf)
            from pipeline import s510_hoerspiel_hybrid as H, s511_vc_fish as VC, mock as MK
            if S.zustand("w", "500") not in S.FREI:
                S.entscheiden("w", "500", "frei", "CK", "Test")
            orig = VC.vc_lauf

            def vc_lauf(*a, **k):
                alt_a = MK.aktiv
                MK.aktiv = lambda: True
                try:
                    return orig(*a, **k)
                finally:
                    MK.aktiv = alt_a
            VC.vc_lauf = vc_lauf
            alt_ap, alt_ko = VC.werkzeug, H.korrigieren
            VC.werkzeug = lambda vc, k: None
            H.korrigieren = lambda x, sr, f=1.0, ht=0.0: x * 0.9
            alt_k = config.KOSTEN_KLEINBETRAG_USD
            config.KOSTEN_KLEINBETRAG_USD = 1.0
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    g = H.run("w", wer="test")
            finally:
                VC.vc_lauf, config.KOSTEN_KLEINBETRAG_USD = orig, alt_k
                VC.werkzeug, H.korrigieren = alt_ap, alt_ko
            self.assertEqual(g.ergebnis["ergebnis"], "mensch", g.bericht())        # Hoerspiel-Freigabe Mensch
            m1 = manifest.Manifest("w", "510_overlay")
            e = m1.get("en/c001_00003_dl")
            self.assertEqual(e["engine"], "fish-vc")
            self.assertEqual(e["figuren"], ["Hatter"])
            self.assertTrue(os.path.exists(os.path.join(self.d, "fassungen", "en", "hoerspiel", "c001_00003_dl.wav")))
            with open(os.path.join(self.d, "work", "510_pruefung.json"), encoding="utf-8") as f:
                pr = json.load(f)["en"]
            self.assertEqual({x["fig"] for x in pr["beitraege"]}, {"Hatter", "Alice"})
            S.entscheiden("w", "510", "frei", "CK", "angehoert")
            VC.werkzeug, H.korrigieren = (lambda vc, k: None), (lambda x, sr, f=1.0, ht=0.0: x * 0.9)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    g = H.run("w", wer="test")
            finally:
                VC.werkzeug, H.korrigieren = alt_ap, alt_ko
            self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())          # Freigabe gilt (Hash gleich)
            # ---- Cockpit-Daten (Monitore 410/430/500/510)
            from cockpit import werk_api as W
            d = W._m430_daten("w")
            self.assertIn("en", d["sprachen"])
            t = W._m430_teil("w", {"lg": "en", "kap": "c001"})
            self.assertTrue(any(x["fig"] == "Hatter" for x in t["beitraege"]))
            a = W._m430_argv("w", {"anweisung": {"en/c001_00003_dl_00": "[voicing x]"}}, "CK")
            self.assertIn("--anweisung=en/c001_00003_dl_00=[voicing x]", a)
            a = W._m430_argv("w", {"probe": {"lg": "en", "id": "c001_00003_dl_00"}}, "CK")
            self.assertIn("pipeline.fish_probe", a)
            d4 = W._m410_daten("w")
            gr = [x for x in d4["gruppen"] if x["lg"] == "en"][0]
            self.assertTrue(gr.get("fish"))
            z = [x for x in gr["zeilen"] if x.get("figur") == "Hatter"][0]
            self.assertTrue(z["fish_grundhaltung"].startswith("voicing"))
            a = W._m410_argv("w", {"grundhaltung": {"Hatter": "voicing the Hatter: theatrical"}, "grund": "t"}, "CK")
            self.assertIn("--grundhaltung=Hatter=voicing the Hatter: theatrical", a)
            a = W._m410_argv("w", {"fish_probe": {"lg": "en", "figur": "Hatter", "vc": True}}, "CK")
            self.assertEqual(a[2:5], ["pipeline.fish_probe", "w", "figur"])
            with contextlib.redirect_stdout(io.StringIO()):
                d5 = W._m500_daten("w")
            self.assertEqual(d5["sprachen"]["en"]["motor"], "fish")
            self.assertTrue(d5["sprachen"]["en"]["bloecke"])
            fw = d5["sprachen"]["en"]["fish_weg"]                        # Weiche im Monitor (AP Fish-Modal)
            self.assertEqual((fw["weg"], fw["wahl"]), ("api", "auto"))
            self.assertIn("schwelle", fw)
            self.assertIn("--fish-weg=en=modal", W._m500_argv("w", {"fish_weg": {"en": "modal"}}, "CK"))
            with self.assertRaises(ValueError):
                W._m500_argv("w", {"fish_weg": {"en": "quatsch"}}, "CK")
            with contextlib.redirect_stdout(io.StringIO()):
                d51 = W._m510_daten("w")
            self.assertEqual(d51["sprachen"]["en"]["motor"], "fish")
            self.assertTrue(d51["sprachen"]["en"]["fish_beitraege"])
            a = W._m510_argv("w", {"lang": "en", "korrektur": {"Hatter": "1.05,1"}, "grund": "Abstand"}, "CK")
            self.assertIn("--korrektur=Hatter:en=1.05,1", a)
        finally:
            F.tts_zeitmarken, F.fish_id, config.KOSTEN_KLEINBETRAG_USD = alt

    def test_bloecke(self):
        from pipeline import s430_fish_regie as R
        bts = []
        for i in range(30):
            bts.append({"id": f"c001_{i:05d}_s_00", "tid": f"c001_{i:05d}_s", "fig": "Erzaehler", "typ": "s",
                        "text": "x" * 300, "absatz": i % 7 == 0, "anweisung": ""})
        bts.append({"id": "c002_00001_s_00", "tid": "c002_00001_s", "fig": "Erzaehler", "typ": "s", "text": "y",
                    "absatz": True, "anweisung": ""})
        bl = R.bloecke_bilden(bts, 2000, 2500)
        self.assertTrue(all(b["zeichen"] <= 2500 for b in bl))
        self.assertEqual(bl[-1]["kap"], "c002")
        self.assertTrue(all(bts[[x["id"] for x in bts].index(b["ids"][0])]["absatz"] for b in bl[1:-1]))


class TFishWeg(unittest.TestCase):
    """AP Fish-Modal 25.11.2026: Weiche fish_weg api|modal|auto."""
    class B:
        def __init__(self, roh=None, art="somnio"):
            self.roh, self.mandant_art = roh or {}, art

    def setUp(self):
        self.alt = (config.FISH_MODAL_FREI, config.FISH_MODAL_AB_ZEICHEN)
        config.FISH_MODAL_AB_ZEICHEN = 60000

    def tearDown(self):
        config.FISH_MODAL_FREI, config.FISH_MODAL_AB_ZEICHEN = self.alt

    def test_auto_schwelle(self):
        config.FISH_MODAL_FREI = True
        self.assertEqual(F.weg(self.B(), "de", 59999)["weg"], "api")
        w = F.weg(self.B(), "de", 60000)
        self.assertEqual((w["weg"], w["wahl"]), ("modal", "auto"))
        self.assertIn("60000", w["grund"])
        self.assertEqual(F.weg(self.B({"fish_weg": "api"}), "de", 10 ** 6)["weg"], "api")
        self.assertEqual(F.weg(self.B({"fish_weg": {"de": "modal"}}), "de", 10)["weg"], "modal")
        self.assertEqual(F.weg(self.B({"fish_weg": {"de": "modal"}}), "en", 10)["weg"], "api")
        self.assertEqual(F.weg(self.B({"fish_weg": "quatsch"}), "de", 10)["wahl"], "auto")

    def test_einzel_und_kunde(self):
        config.FISH_MODAL_FREI = True
        self.assertEqual(F.weg(self.B(), "de", 10 ** 6, einzel=True)["weg"], "api")
        for art in ("verlag", "user"):
            w = F.weg(self.B({"fish_weg": "api"}, art), "de", 10, einzel=True)
            self.assertEqual(w["weg"], "modal")
            self.assertIn("Kundenwerk", w["grund"])
            self.assertIsNone(w["stopp"])

    def test_nicht_freigegeben(self):
        config.FISH_MODAL_FREI = False
        w = F.weg(self.B(), "de", 10 ** 6)
        self.assertEqual(w["weg"], "api")
        self.assertIn("Fallback", w["grund"])
        w = F.weg(self.B(art="verlag"), "de", 10)
        self.assertEqual(w["weg"], "modal")
        self.assertTrue(w["stopp"])

    def test_schaetzung_bericht(self):
        from pipeline import s503_vertonung_fish as V
        sch = F.modal_schaetzung(60000, "H100")
        self.assertAlmostEqual(sch["audio_s"], 3593, delta=5)
        self.assertGreater(sch["usd"], 0)
        self.assertGreater(sch["kaltstart_usd"], 0)
        ber = V.bericht_lesen("GPU NVIDIA H100 80GB HBM3, 81559 MiB\nMODELL drama-3 {}\nKALTSTART 212.5 s (Server 180.0 s)"
                              "\nTTS 100.0 s RTF 0.210\nAUDIO 476.0 s\nWALL 330.2 s")
        self.assertEqual((ber["gpu"], ber["modell"], ber["kalt_s"], ber["wall_s"], ber["rtf"]),
                         ("H100", "drama-3", 212.5, 330.2, 0.21))

    def test_modal_jobs_woerter(self):
        from pipeline import s503_vertonung_fish as V
        j = V._modal_jobs({"text": "[voicing Alice; very tense] Grüß dich, <emphasis>Hatter</emphasis>!",
                           "soll": "h", "ids": ["x"]}, 1)
        self.assertEqual(j["key"], "h_v1")
        self.assertEqual(j["seed"], 2)
        self.assertEqual([w["l"] for w in j["woerter"]], ["gruss", "dich", "hatter"])
        self.assertEqual([w["w"] for w in j["woerter"]], ["Grüß", "dich", "Hatter"])


class _T503Modal:
    """500 Motor Fish ueber den Modal-Weg (modal run durch Fake ersetzt: schreibt out/<key>.wav/json + bericht).
    Methoden werden an T430 gehaengt (keine doppelten Erbtests)."""

    def test_500_fish_modal(self):
        import numpy as np, subprocess as sp_
        from pipeline import s500_vertonung_gemini as V, s503_vertonung_fish as W, manifest
        R = self.vorbereiten()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(R.run("w", wer="test").ergebnis["ergebnis"], "auto")
        laeufe = []
        klon = os.path.join(self.d, "klon.wav")
        with open(klon, "wb") as f:
            f.write(F.wav_bytes(b"\0\0" * 2400))

        def fake_run(cmd, cwd=None, **k):
            paket = cmd[cmd.index("--paket") + 1]
            d = os.path.join(config.BASE_DIR, "gpu_fish", paket)
            with open(os.path.join(d, "jobs.json"), encoding="utf-8") as f:
                jobs = json.load(f)
            laeufe.append([j["key"] for j in jobs["jobs"]])
            os.makedirs(os.path.join(d, "out"), exist_ok=True)
            for j in jobs["jobs"]:
                ww, t, y = [], 0.05, [np.zeros(int(0.05 * 24000))]
                for w in j["woerter"]:
                    ww.append({"w": w["w"], "a": round(t, 3), "b": round(t + 0.3, 3)})
                    y += [np.sin(np.arange(int(0.3 * 24000)) / 5) * 0.3, np.zeros(int(0.1 * 24000))]
                    t += 0.4
                y = np.concatenate(y).astype("float32")
                with open(os.path.join(d, "out", j["key"] + ".wav"), "wb") as f:
                    f.write(F.wav_bytes((y * 32767).astype("<i2").tobytes()))
                with open(os.path.join(d, "out", j["key"] + ".json"), "w", encoding="utf-8") as f:
                    json.dump({"woerter": ww, "info": {"bytes": len(j["text"].encode())}}, f)
            with open(os.path.join(d, "bericht.txt"), "w", encoding="utf-8") as f:
                f.write("GPU NVIDIA H100\nMODELL drama-3 {}\nWALL 12.0 s\n")
            return sp_.CompletedProcess(cmd, 0)

        alt = (W.subprocess.run, F.klon_clip, F.fish_id, F.tts_zeitmarken, config.FISH_MODAL_FREI,
               getattr(config, "KOSTEN_KLEINBETRAG_USD", None))
        W.subprocess.run, F.klon_clip = fake_run, lambda st, lg: klon
        F.fish_id = lambda st, lg, anlegen=False: "fid_test"
        F.tts_zeitmarken = lambda *a, **k: self.fail("API darf auf dem Modal-Weg nicht gerufen werden")
        config.KOSTEN_KLEINBETRAG_USD = 0.0
        try:
            config.FISH_MODAL_FREI = False                                   # nicht freigegeben -> api-Fallback
            V.fish_weg_setzen("w", ["modal"], "test")
            with contextlib.redirect_stdout(io.StringIO()):
                g = V.run("w", wer="test", trocken=True)
            self.assertEqual(g.metriken["kosten_je_sprache"]["en"]["weg"], "api")
            config.FISH_MODAL_FREI = True
            with contextlib.redirect_stdout(io.StringIO()):
                g = V.run("w", wer="test", kosten_freigeben=5.0)
            self.assertNotEqual(g.ergebnis["ergebnis"], "stopp", g.bericht())
            self.assertEqual(len(laeufe), 1)                                 # ein Stapel je Sprache
            m = manifest.Manifest("w", "500_vertonung")
            self.assertEqual(m.meta["fish_weg"]["en"]["weg"], "modal")
            self.assertEqual(m.meta["je_sprache"]["en"]["weg"], "modal")
            e = m.get("en/c001_00003_dl")
            self.assertEqual([x["fig"] for x in e["spannen"]], ["Hatter", "Erzaehler"])
            blk = [k for k in m.eintraege if "/_fish/" in k]
            self.assertTrue(blk)
            self.assertEqual({(m.get(k) or {}).get("weg") for k in blk}, {"modal"})
            soll_modal = {k: m.eintraege[k] for k in blk}
            V.fish_weg_setzen("w", ["api"], "test")                          # Wegwechsel: kein Neuvertonen
            F.tts_zeitmarken = lambda *a, **k: self.fail("Wegwechsel darf nicht neu vertonen")
            with contextlib.redirect_stdout(io.StringIO()):
                V.run("w", wer="test", kosten_freigeben=5.0)
            self.assertEqual(len(laeufe), 1)
            m = manifest.Manifest("w", "500_vertonung")
            self.assertEqual({k: m.eintraege[k] for k in blk}, soll_modal)
        finally:
            (W.subprocess.run, F.klon_clip, F.fish_id, F.tts_zeitmarken, config.FISH_MODAL_FREI,
             config.KOSTEN_KLEINBETRAG_USD) = alt
            import shutil
            shutil.rmtree(os.path.join(config.BASE_DIR, "gpu_fish", "w_en_500"), ignore_errors=True)

    def test_kundenwerk_stopp(self):
        from pipeline import s500_vertonung_gemini as V, bestellung
        R = self.vorbereiten()
        with contextlib.redirect_stdout(io.StringIO()):
            R.run("w", wer="test")
        alt = (config.FISH_MODAL_FREI, bestellung.Bestellung.mandant_art)
        config.FISH_MODAL_FREI = False
        bestellung.Bestellung.mandant_art = property(lambda self: "verlag")
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                g = V.run("w", wer="test", trocken=True)
            self.assertTrue(any(x["name"] == "weg_en" and not x["ok"] for x in g.pruefungen), g.bericht())
        finally:
            config.FISH_MODAL_FREI, bestellung.Bestellung.mandant_art = alt


if __name__ == "__main__":
    unittest.main()


for _n in ("test_500_fish_modal", "test_kundenwerk_stopp"):
    setattr(T430, _n, getattr(_T503Modal, _n))

