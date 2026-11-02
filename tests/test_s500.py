"""Stage 500 Vertonung.  py -3.11 -m unittest tests.test_s500"""
import contextlib, io, json, os, struct, sys, tempfile, unittest, wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import audio_fa, mock
from pipeline import status as S
from pipeline import s410_casting as C
from pipeline import s500_vertonung_gemini as P
from pipeline import s502_vertonung_chatterbox as CB

Q = {"c001_00001_h": ("h", "Chapter One", "Kapitel eins"),
     "c001_00002_s": ("s", "Alice sat by the river bank.", "Alice saß am Ufer des Flusses."),
     "c001_00003_s": ("s", "She was very tired of sitting.", "Sie war des Sitzens sehr müde."),
     "c001_00004_dl": ("dl", "\"Who are you?\" said the Hatter.", "„Wer bist du?“, sagte der Hutmacher."),
     "c001_00005_p": ("p", "", ""),
     "c002_00001_h": ("h", "Chapter Two", "Kapitel zwei"),
     "c002_00002_s": ("s", "The cat grinned at her.", "Die Katze grinste sie an.")}
AUDIO = [k for k, v in Q.items() if v[0] != "p"]
PREM = [{"sprache": "de", "inhalt": "hoerbuch", "stufe": "premium", "kanaele": ["taella"]}]
BASIC = [{"sprache": "de", "inhalt": "hoerbuch", "stufe": "basic", "kanaele": ["taella"]}]


def rollen(stufe="premium", adapter=None, gid="Charon"):
    eng = C.ENGINE[stufe]
    erz = {"rolle": "erzaehler", "figur": None, "stimme": "herr_a", "modell": "m"}
    if eng == "gemini":
        erz["gemini_id"] = gid
    else:
        erz["referenz"] = "stimmen_archiv/herr_a/klon_de.wav"
    bs = {"engine": eng, "inhalte": ["hoerbuch"], "erzaehler": erz}
    if adapter:
        bs["adapter"] = adapter
    return {"de": {stufe: bs}}


def wav(p, sek=1.0, amp=3000):
    n = max(1, int(24000 * sek))
    with wave.open(p, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(struct.pack(f"<{n}h", *([amp, -amp] * (n // 2) + [0] * (n % 2))))


class T500(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.tmp.name
        self.d = os.path.join(r, "a", "books", "w")
        self.wd = os.path.join(self.d, "work")
        os.makedirs(self.wd)
        os.makedirs(os.path.join(r, "stimmen_archiv", "herr_a"))
        wav(os.path.join(r, "stimmen_archiv", "herr_a", "klon_de.wav"), 3)
        self.alt = (config.book_dir, config.work_dir, config.RUN_MODE, config.BASE_DIR, P.synth, P.pruefer_fabrik,
                    audio_fa.fa_cut, audio_fa.slice_block, CB.modal_lauf, P.PAUSE, CB.paket_bauen)
        config.book_dir = lambda b: self.d
        config.work_dir = lambda b: self.wd
        config.BASE_DIR = r
        config.RUN_MODE = "live"
        P.PAUSE = 0
        self.calls, self.grund, self.leer, self.flag, self.modal, self.kapp = [], {}, False, False, [], []
        P.synth = self.synth
        P.pruefer_fabrik = lambda ms: self
        audio_fa.fa_cut = self.fa_cut
        audio_fa.slice_block = self.slice_block
        CB.modal_lauf = self.modal_lauf
        CB.paket_bauen = self.paket_bauen
        self.werk()

    def tearDown(self):
        (config.book_dir, config.work_dir, config.RUN_MODE, config.BASE_DIR, P.synth, P.pruefer_fabrik,
         audio_fa.fa_cut, audio_fa.slice_block, CB.modal_lauf, P.PAUSE, CB.paket_bauen) = self.alt
        self.tmp.cleanup()

    # ---------------------------------------------------------- Attrappen
    def synth(self, text, style, out, voice, lg):
        self.calls.append((text, style, voice))
        wav(out, 0.0 if self.leer else 0.06 * len(text), 0 if self.leer else 3000)

    def fa_cut(self, bwav, saetze, **kw):
        n = len(saetze) - 1
        st = "FLAG" if self.flag else "OK"
        return {"net": {"ok": True}, "cuts": [0.1 * (i + 1) for i in range(n)],
                "boundaries": [{"after_id": s["id"], "status": st, "reason": "x"} for s in saetze[:-1]]}

    def slice_block(self, bwav, cuts, pfade):
        for p in pfade:
            wav(p, 0.5)
        return [(p, True) for p in pfade]

    def pruefe(self, text, p):                      # FA-Pruefer-Attrappe
        g = self.grund.get(text)
        if isinstance(g, list):
            g = g.pop(0) if g else None
        return {"grund": g, "letzt": 0.3, "dauer": 1.0}

    def kappen(self, p, ende):
        self.kapp.append(os.path.basename(p))

    _echt_paket = staticmethod(CB.paket_bauen)

    def paket_bauen(self, *a, **kw):
        return T500._echt_paket(*a, **kw)

    def modal_lauf(self, werk, lg, batch=8, fp16=False, tag=None):
        with open(os.path.join(CB.paket_dir(werk, lg), "jobs.json"), encoding="utf-8") as f:
            d = json.load(f)
        self.modal.append(d)
        z = os.path.join(self.d, d["ziel"])
        os.makedirs(z, exist_ok=True)
        for j in d["jobs"]:
            wav(os.path.join(z, f"{j['id']}.wav"), 0.06 * len(j["text"]))
        return {"kapitel_details": [{"befund": dict(self.grund_cb) if hasattr(self, "grund_cb") else {}}]}

    def werk(self, produkte=None, extra=None, gates=("400", "410"), frei=True, rl=None, sprech=None, ansagen=None):
        b = {"book_slug": "w", "quelle": "gutenberg", "quellsprache": "en", "fassung": "modernisiert",
             "mandant": "somnio", "produkte": produkte or PREM, "vertonung_regler": {"budget": 5.0},
             "rechte": {"art": "gemeinfrei", "bearbeitung": True, "versichert": {"wer": "t", "wann": "x"}}}
        b.update(extra or {})
        self.schreib(os.path.join(self.d, "book.json"), b)
        content = {k: {"type": t, "en": q, "de": z} for k, (t, q, z) in Q.items()}
        sp = {k: {"de": (sprech or {}).get(k, z)} for k, (t, q, z) in Q.items() if t != "p"}
        di = {k: {"de": "calm audiobook narration" + ("; Alice pronounced as in English" if "Alice" in z else "")}
              for k, (t, q, z) in Q.items() if t != "p"}
        pa = {k: {"de": 400} for k in Q}
        self.schreib(os.path.join(self.wd, "400_regie.json"),
                     {"book_id": "w", "meta": {}, "content": content, "ansagen": ansagen or {},
                      "production": {"sprechtext": sp, "direction": di, "pause_after_ms": pa}})
        rl = rl or rollen()
        c = {"schema": 2, "rollen": rl, "freigabe": {"wer": "CK", "hash": C.kern(rl)} if frei else None}
        self.schreib(os.path.join(self.wd, "casting.json"), c)
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

    # ---------------------------------------------------------- Tests
    def test_gemini_auto_bloecke_manifest(self):
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        for t in AUDIO:
            self.assertTrue(os.path.exists(self.a(f"{t}.wav")), t)
        m = self.lesen("500_vertonung.json")
        self.assertEqual(m["schema"], 1)
        e = m["eintraege"]["de/c001_00002_s"]
        self.assertEqual((e["engine"], e["stimme"], e["q"], e["block"]), ("gemini", "herr_a", "neu", True))
        self.assertEqual(e["pause_ms"], 400)
        blk = [c for c in self.calls if "So weit, so gut." in c[0]]
        self.assertEqual(len(blk), 1)
        self.assertIn("Alice pronounced as in English", blk[0][1])      # Aussprache aus 400 im Block-Stil
        self.assertEqual(blk[0][2], "Charon")
        self.assertEqual(S.zustand("w", "500"), "frei")
        n = len(self.calls)
        g = self.lauf()                                                   # zweiter Lauf: nichts offen
        self.assertEqual(len(self.calls), n)
        self.assertEqual(g.ergebnis["ergebnis"], "auto")

    def test_geaenderter_sprechtext_nur_dieser_satz(self):
        self.lauf()
        n = len(self.calls)
        self.werk(sprech={"c002_00002_s": "Die Katze grinste sie breit an."})
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual([c[0] for c in self.calls[n:]], ["Die Katze grinste sie breit an."])
        self.lauf(saetze=["c001_00001_h"])                               # --satz: neu vertonen
        self.assertEqual(self.calls[-1][0], "Kapitel eins.")

    def test_stimmwechsel_alles_neu(self):
        self.lauf()
        n = len(self.calls)
        self.werk(rl=rollen(gid="Kore"))
        self.lauf()
        self.assertEqual({c[2] for c in self.calls[n:]}, {"Kore"})
        self.assertEqual(len(self.calls[n:]), len(self.calls[:n]))

    def test_kosten_mensch_und_freigabe(self):
        self.werk(extra={"mandant": "user:x"})
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch", g.bericht())
        self.assertIn("Kostenschaetzung", " ".join(g.ergebnis["gruende"]))
        self.assertEqual(self.calls, [])
        usd = g.metriken["kosten_usd"]
        g = self.lauf(kosten_freigeben=usd / 10)
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertEqual(self.calls, [])
        g = self.lauf(kosten_freigeben=usd + 0.01)
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(self.lesen("500_kosten.json")["freigaben"][0]["wer"], "test")

    def test_budget_standard_null(self):
        self.werk(extra={"vertonung_regler": {}})
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertEqual(self.calls, [])

    def test_budget_somnio(self):
        g = self.lauf(regler={"budget": 0.0})
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertIn("ueber Budget", " ".join(g.ergebnis["gruende"]))

    def test_casting_nicht_frei_stopp(self):
        self.werk(frei=False)
        g = self.lauf()
        self.assertEqual((g.ergebnis["ergebnis"], g.ergebnis["ruecksprung"]), ("stopp", "410"))
        self.assertEqual(self.calls, [])

    def test_fa_pruefer_fehlt_stopp_vor_kosten(self):
        def kaputt(ms):
            raise ImportError("torch")
        P.pruefer_fabrik = kaputt
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual(self.calls, [])

    def test_auffaellig_2x_neu_dann_mensch(self):
        self.grund = {"Die Katze grinste sie an.": ["zu_kurz", "zu_kurz", "zu_kurz"]}
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch", g.bericht())
        self.assertEqual(sum(1 for c in self.calls if c[0] == "Die Katze grinste sie an."), 3)
        h = self.lesen("500_pruefung.json")["de"]["auffaellig"]
        self.assertEqual([x["id"] for x in h], ["c002_00002_s"])
        self.assertEqual(h[0]["versuche"], 2)

    def test_auffaellig_repariert(self):
        self.grund = {"Die Katze grinste sie an.": ["verschmiert", None]}
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())

    def test_nachklang_gekappt(self):
        self.grund = {"Kapitel zwei": ["nachklang"]}
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertIn("c002_00001_h.wav", self.kapp)

    def test_leer_stopp(self):
        self.leer = True
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp", g.bericht())
        self.assertTrue(any("leere WAVs" in x for x in g.ergebnis["gruende"]))

    def test_block_fallback_hinweis(self):
        self.flag = True
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertTrue(any("Solo-Fallback" in h for h in g.ergebnis["hinweise"]))
        self.assertEqual(self.lesen("500_vertonung.json")["eintraege"]["de/c001_00002_s"]["q"], "fallback")

    def test_ansagen(self):
        self.werk(ansagen={"de": [{"id": "ansage_titel", "position": "anfang", "text": "Alice.", "sprechtext": "Alice.",
                                   "direction": "clear", "pause_after_ms": 1500},
                                  {"id": "ansage_ende", "position": "ende", "text": "Ende.", "sprechtext": "Ende."}]})
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertTrue(os.path.exists(self.a("ansage_titel.wav")))
        self.assertEqual(self.calls[0][0], "Alice.")

    def test_probe_mensch(self):
        g = self.lauf(probe=1)
        self.assertEqual(g.ergebnis["ergebnis"], "mensch", g.bericht())
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(self.lesen("500_pruefung.json")["de"]["probe"]), 1)

    def test_mock_lauf_dann_live_neu(self):
        config.RUN_MODE = "mock"
        g = self.lauf()
        self.assertEqual(self.calls, [])
        self.assertTrue(mock.ist_datei(self.a("c001_00002_s.wav")))
        config.RUN_MODE = "live"
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertFalse(mock.ist_datei(self.a("c001_00002_s.wav")))

    def test_uebernahme_altbestand(self):
        os.makedirs(self.a())
        for t in AUDIO:
            wav(self.a(f"{t}.wav"), 1.0)
        self.schreib(os.path.join(self.wd, "500_vertonung.json"),
                     {"production": {"audio_manifest": {"de": {}}, "audio_voice_used": "Charon"}})
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(self.calls, [])
        self.assertTrue(os.path.exists(os.path.join(self.wd, "500_vertonung_v1.json")))
        self.assertTrue(any("Altbestand uebernommen" in h for h in g.ergebnis["hinweise"]))

    def test_altbestand_andere_stimme_neu(self):
        os.makedirs(self.a())
        for t in AUDIO:
            wav(self.a(f"{t}.wav"), 1.0)
        self.werk(extra={"tts": {"de": "gemini"}, "stimme": {"de": "frau_b"}})
        g = self.lauf()
        self.assertTrue(self.calls)
        self.assertTrue(any("nicht uebernommen" in h for h in g.ergebnis["hinweise"]))

    def test_uebernahme_chatterbox_beleg(self):
        rl = rollen("basic", {"name": "mix_v1", "version": "1"})
        os.makedirs(self.a())
        for t in AUDIO:
            wav(self.a(f"{t}.wav"), 1.0)
        self.werk(produkte=BASIC, rl=rl)
        g = self.lauf(trocken=True)                 # kein Beleg
        self.assertTrue(any("nicht uebernommen" in h and "unbekannt" in h for h in g.ergebnis["hinweise"]))
        j = os.path.join(config.BASE_DIR, "gpu_tts", "w_de")
        os.makedirs(j)
        self.schreib(os.path.join(j, "jobs.json"), {"ref": "herr_a", "lora": "ramona_v1", "jobs": []})
        g = self.lauf(trocken=True)                 # anderer Adapter
        self.assertTrue(any("ramona_v1" in h for h in g.ergebnis["hinweise"]))
        self.schreib(os.path.join(j, "jobs.json"), {"ref": "herr_a", "lora": "mix_v1", "jobs": []})
        self.schreib(os.path.join(self.wd, "500_vertonung.json"),
                     {"production": {"audio_manifest": {"de": {}}, "audio_voice_used": "Charon"}})
        g = self.lauf(trocken=True)                 # Belege uneindeutig
        self.assertTrue(any("nicht uebernommen" in h for h in g.ergebnis["hinweise"]))
        os.remove(os.path.join(self.wd, "500_vertonung.json"))
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(self.modal, [])

    def test_trocken_schreibt_nichts(self):
        g = self.lauf(trocken=True)
        self.assertEqual(self.calls, [])
        self.assertFalse(os.path.exists(os.path.join(self.wd, "500_vertonung.json")))
        self.assertTrue(any("wuerden vertont" in h for h in g.ergebnis["hinweise"]))

    def test_zwei_engines_stopp_und_regler(self):
        self.werk(produkte=BASIC + [{"sprache": "de", "inhalt": "hoerspiel", "stufe": "premium",
                                      "kanaele": ["taella"]}])
        g = self.lauf()
        self.assertEqual((g.ergebnis["ergebnis"], g.ergebnis["ruecksprung"]), ("stopp", "095"))
        g = self.lauf(regler={"engine": {"de": "gemini"}})
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())

    # ---------------------------------------------------------- Chatterbox
    def test_chatterbox_modal(self):
        self.werk(produkte=BASIC, rl=rollen("basic", {"name": "mix_v1", "version": "1"}))
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(len(self.modal), 1)
        d = self.modal[0]
        self.assertEqual((d["lora"], d["ref"]), ("mix_v1", "herr_a"))
        self.assertEqual(len(d["jobs"]), len(AUDIO))
        self.assertTrue(os.path.exists(os.path.join(CB.paket_dir("w", "de"), "ref.wav")))
        self.assertTrue(os.path.exists(os.path.join(self.d, "fassungen", "de", "audio", "c001_00002_s.wav")))
        self.assertFalse(os.path.exists(os.path.join(self.d, "fassungen", "de", "audio_chatterbox_roh")))
        e = self.lesen("500_vertonung.json")["eintraege"]["de/c001_00002_s"]
        self.assertEqual((e["engine"], e["adapter"]["version"]), ("chatterbox", "1"))
        self.lauf()
        self.assertEqual(len(self.modal), 1)                              # nichts offen -> kein GPU-Lauf

    def test_chatterbox_rest_auffaellig_neuer_lauf(self):
        self.werk(produkte=BASIC, rl=rollen("basic", {"name": "mix_v1", "version": "1"}))
        self.grund_cb = {"c002_00002_s": "zu_kurz"}
        g = self.lauf()
        self.assertEqual(len(self.modal), 3)                              # 1 + 2 Wiederholungen nur fuer den Satz
        self.assertEqual([j["id"] for j in self.modal[1]["jobs"]], ["c002_00002_s"])
        self.assertEqual(g.ergebnis["ergebnis"], "mensch", g.bericht())

    def test_adapter_nicht_frei_stopp(self):
        self.werk(produkte=BASIC, rl=rollen("basic", {"name": "ramona_v1", "version": "1"}))
        g = self.lauf()
        self.assertEqual((g.ergebnis["ergebnis"], g.ergebnis["ruecksprung"]), ("stopp", "410"))
        self.werk(produkte=BASIC, rl=rollen("basic", {"name": "mix_v1", "version": "9"}))
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertTrue(any("nicht verfuegbar" in x for x in g.ergebnis["gruende"]))
        self.assertEqual(self.modal, [])

    def test_run_registrierung(self):
        import run
        self.assertIn("500", run.UMGEBAUT)
        self.assertIn("500", run.NEU)
        self.assertNotIn("500", run.ALT)


if __name__ == "__main__":
    unittest.main()
