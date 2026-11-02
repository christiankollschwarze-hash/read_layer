"""Stage 410 Casting.  py -3.11 -m unittest tests.test_s410"""
import contextlib, io, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import api_layer, legacy_tor, trennung
from pipeline import status as S
from pipeline import voice_registry as vr
from pipeline import s410_casting as P

Q = {"c001_00001_h": ("h", "Chapter One", "Kapitel eins"),
     "c001_00002_s": ("s", "Alice sat by the river.", "Alice saß am Fluss."),
     "c001_00003_dl": ("dl", "\"Who are you?\" said the Hatter.", "„Wer bist du?“, sagte der Hutmacher."),
     "c001_00004_dl": ("dl", "\"I am Alice,\" she said.", "„Ich bin Alice“, sagte sie.")}
FIG = {"Alice": {"de": "Alice", "gender": "f", "pronunciation": "ˈælɪs"},
       "Hatter": {"de": "Hutmacher", "gender": "m"},
       "Cat": {"de": "Katze", "gender": "m"}}
REG = {"herr_a": {"id": "voice_herr", "status": "freigegeben", "rolle_typ": "erzaehler", "grundton_hz": 95,
                  "merkmale": {"geschlecht": "m", "alter": "alt", "tonlage": "tief", "klangfarbe": ["warm"],
                               "temperament": ["ruhig"]}},
       "w_jung": {"id": "voice_wj", "status": "kandidat", "rolle_typ": "figur", "grundton_hz": 210,
                  "merkmale": {"geschlecht": "w", "alter": "jung", "tonlage": "hoch", "klangfarbe": ["hell"],
                               "temperament": ["neugierig"]}},
       "m_mittel": {"id": "voice_mm", "status": "kandidat", "rolle_typ": "figur", "grundton_hz": 130,
                    "merkmale": {"geschlecht": "m", "alter": "mittel", "tonlage": "mittel", "klangfarbe": ["nasal"],
                                 "temperament": ["albern"]}},
       "alt_weg": {"id": "voice_x", "status": "abgelehnt", "rolle_typ": "erzaehler",
                   "merkmale": {"geschlecht": "m", "alter": "alt", "tonlage": "tief"}}}


def sb(genre="abenteuer", erz_m=None, figuren=True):
    d = {"erzaehler": {"erzaehlform": "allwissend", "genre_stimme": genre,
                       "merkmale": erz_m or {"geschlecht": "m", "alter": "alt", "tonlage": "tief",
                                             "klangfarbe": ["warm"], "temperament": ["ruhig"]}}}
    if figuren:
        d["figuren"] = [
            {"name": "Alice", "gewicht": "haupt", "dialog_anteil_prozent": 50, "kurz": "neugieriges Maedchen",
             "merkmale": {"geschlecht": "w", "alter": "jung", "tonlage": "hoch", "klangfarbe": ["hell"],
                          "temperament": ["neugierig"]}},
            {"name": "hatter", "gewicht": "neben", "dialog_anteil_prozent": 30,
             "merkmale": {"geschlecht": "m", "alter": "mittel", "tonlage": "mittel", "klangfarbe": ["nasal"],
                          "temperament": ["albern"]}},
            {"name": "Cat", "gewicht": "statist", "dialog_anteil_prozent": 1, "merkmale": {"geschlecht": "m"}},
            {"name": "Queen", "gewicht": "neben", "dialog_anteil_prozent": 10, "merkmale": {"geschlecht": "w"}}]
    return d


class T410(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.r = self.tmp.name
        self.d = os.path.join(r, "a", "books", "w")
        os.makedirs(os.path.join(self.d, "work"))
        self.alt = (config.book_dir, config.work_dir, config.RUN_MODE, config.BASE_DIR,
                    getattr(config, "LORA_ADAPTER", None), getattr(config, "TTS_LORA", None),
                    vr.REGISTER, vr.STIMMEN_DIR, legacy_tor.ARCHIV, api_layer.call_model,
                    trennung.erzaehler_profil, trennung.stimm_profil)
        config.book_dir = lambda b: self.d
        config.work_dir = lambda b: os.path.join(self.d, "work")
        config.BASE_DIR = r
        config.RUN_MODE = "live"
        config.TTS_LORA = {"de": "mix_v1"}
        config.LORA_ADAPTER = {"mix_v1": {"version": "1", "freigegeben": True, "datei": "gpu_lora/mix_v1.st"},
                               "test_v0": {"version": "0", "freigegeben": False, "datei": "gpu_lora/mix_v1.st"}}
        os.makedirs(os.path.join(r, "gpu_lora"))
        open(os.path.join(r, "gpu_lora", "mix_v1.st"), "w").close()
        arch = os.path.join(r, "stimmen_archiv")
        vr.STIMMEN_DIR = arch
        vr.REGISTER = os.path.join(arch, "stimmen.json")
        legacy_tor.ARCHIV = arch
        for n in REG:
            os.makedirs(os.path.join(arch, n))
            for lg in ("de", "en"):
                open(os.path.join(arch, n, f"klon_{lg}.wav"), "w").close()
        os.makedirs(os.path.join(arch, "_gemini_standard", "Charon"))
        open(os.path.join(arch, "_gemini_standard", "Charon", "klon_de.wav"), "w").close()
        with open(os.path.join(arch, "_gemini_standard", "standard.json"), "w", encoding="utf-8") as f:
            json.dump({"Charon": {"geschlecht": "m", "grundton_hz": 100}}, f)
        vr.speichern(json.loads(json.dumps(REG)))
        self.antworten, self.n_llm = [json.dumps(sb())], 0

        def llm(task, prompt, **kw):
            self.n_llm += 1
            self.prompt = prompt
            return self.antworten[min(self.n_llm - 1, len(self.antworten) - 1)]
        api_layer.call_model = llm
        prof = {"herr_a": {"f0_hz": 95, "vtl_cm": 17.5}, "w_jung": {"f0_hz": 210, "vtl_cm": 14.5},
                "m_mittel": {"f0_hz": 96, "vtl_cm": 17.4}}
        trennung.erzaehler_profil = lambda wd, lg, stimme=None, **k: dict(prof.get(stimme, {}))
        trennung.stimm_profil = lambda name, lg="de": dict(prof.get(name, {}))
        with open(os.path.join(r, "a", "author.json"), "w", encoding="utf-8") as f:
            json.dump({"name_display": "Jane Doe"}, f)
        self.werk()

    def tearDown(self):
        (config.book_dir, config.work_dir, config.RUN_MODE, config.BASE_DIR, la, tl,
         vr.REGISTER, vr.STIMMEN_DIR, legacy_tor.ARCHIV, api_layer.call_model,
         trennung.erzaehler_profil, trennung.stimm_profil) = self.alt
        config.LORA_ADAPTER, config.TTS_LORA = la, tl
        self.tmp.cleanup()

    def werk(self, produkte=None, extra=None, gates=("400",)):
        b = {"book_slug": "w", "quelle": "gutenberg", "quellsprache": "en", "fassung": "modernisiert",
             "mandant": "somnio", "titel_original": "The House",
             "produkte": produkte or [{"sprache": "de", "inhalt": "hoerbuch", "stufe": "basic", "kanaele": ["taella"]}],
             "rechte": {"art": "gemeinfrei", "bearbeitung": True, "versichert": {"wer": "t", "wann": "x"}}}
        b.update(extra or {})
        with open(os.path.join(self.d, "book.json"), "w", encoding="utf-8") as f:
            json.dump(b, f)
        data = {"book_id": "w", "meta": {"title": "The House", "profile": {"characters": FIG,
                                                                         "style": {"voice_note": "calm"}}},
                "content": {k: {"type": t, "en": q, "de": z} for k, (t, q, z) in Q.items()}}
        with open(os.path.join(self.d, "work", "400_regie.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        for g in gates:
            S.ergebnis("w", g, "auto", wer="test")

    def lauf(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return P.run("w", wer="test", **kw)

    def bj(self):
        with open(os.path.join(self.d, "book.json"), encoding="utf-8") as f:
            return json.load(f)

    HS = [{"sprache": "en", "inhalt": "hoerbuch", "stufe": "premium", "kanaele": ["taella"]},
          {"sprache": "en", "inhalt": "hoerspiel", "stufe": "premium", "kanaele": ["taella"]}]

    # ------------------------------------------------------------------
    def test_hoerbuch_basic_auto(self):
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        c = P.laden("w")
        bs = c["rollen"]["de"]["basic"]
        self.assertEqual(bs["erzaehler"]["stimme"], "herr_a")
        self.assertEqual(bs["erzaehler"]["quelle"], "genre")
        self.assertTrue(bs["erzaehler"]["referenz"].endswith("herr_a/klon_de.wav"))
        self.assertEqual(bs["adapter"], {"name": "mix_v1", "version": "1"})
        self.assertEqual(bs["ensemble"], [])
        self.assertTrue(P.freigegeben(c))
        self.assertEqual(c["tor"], "freigegeben")
        self.assertEqual(c["plan"]["erzaehler"]["stimme"], "herr_a")
        self.assertEqual(self.bj()["casting"], "work/casting.json")
        self.assertEqual(P.stimme("w", "de"), "herr_a")
        self.assertEqual(legacy_tor.stimme("w", "de"), "herr_a")
        self.assertNotIn("CHARACTER LIST", self.prompt)          # Hoerbuch: nur Erzaehler
        self.assertEqual(self.n_llm, 1)
        g = self.lauf()                                           # Wiederholung: kein LLM, gleich
        self.assertEqual((g.ergebnis["ergebnis"], self.n_llm), ("auto", 1))

    def test_hoerspiel_immer_mensch_dann_freigabe(self):
        self.werk(produkte=self.HS)
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "mensch", g.bericht())
        self.assertTrue(any("zu nah: hatter" in x.lower() or "zu nah: Hatter" in x for x in g.ergebnis["gruende"]),
                        g.ergebnis["gruende"])
        self.assertTrue(any("nicht in 210: 1" in h for h in g.ergebnis["hinweise"]))
        bs = P.laden("w")["rollen"]["en"]["premium"]
        ens = {e["figur"]: e for e in bs["ensemble"]}
        self.assertEqual(ens["Alice"]["stimme"], "w_jung")
        self.assertEqual(ens["Alice"]["gemini_id"], "voice_wj")
        self.assertEqual(ens["Hatter"]["stimme"], "m_mittel")
        self.assertIn("korrektur", ens["Hatter"])
        self.assertEqual([s["figur"] for s in bs["statisten"]], ["Cat"])
        self.assertIsNone(P.stimme("w", "en"))                   # noch nicht freigegeben
        self.assertIn("CHARACTER LIST", self.prompt)
        S.entscheiden("w", "410", "frei", "CK", "Hoerprobe ok")
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        c = P.laden("w")
        self.assertTrue(P.freigegeben(c))
        self.assertEqual(P.stimme("w", "en", figur="Alice"), "w_jung")
        self.assertEqual(vr.laden()["w_jung"]["status"], "freigegeben")
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto")
        # H-6: freigegeben -> Aenderung nur mit --neu --grund
        with self.assertRaises(ValueError):
            self.lauf(regler={"figur": ["Alice=m_mittel"]})
        with self.assertRaises(ValueError):
            self.lauf(neu=True)
        g = self.lauf(neu=True, grund="Umbesetzung Test", regler={"statist": ["Hatter"]})
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        c = P.laden("w")
        self.assertFalse(P.freigegeben(c))
        self.assertEqual(c["protokoll"][-1]["aktion"], "neu")
        self.assertIn("Hatter", [s["figur"] for s in c["rollen"]["en"]["premium"]["statisten"]])

    def test_korrektur_ohne_neu(self):
        self.werk(produkte=self.HS)
        self.lauf()
        S.entscheiden("w", "410", "frei", "CK", "ok")
        self.lauf()
        P.korrektur_setzen("w", "Hatter", "en", 1.08, 0, wer="540", grund="Nachrunde")
        c = P.laden("w")
        self.assertTrue(P.freigegeben(c))
        e = [x for x in c["rollen"]["en"]["premium"]["ensemble"] if x["figur"] == "Hatter"][0]
        self.assertEqual(e["korrektur"]["formant_faktor"], 1.08)
        self.assertEqual(c["protokoll"][-1]["aktion"], "korrektur")
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto")
        e = [x for x in P.laden("w")["rollen"]["en"]["premium"]["ensemble"] if x["figur"] == "Hatter"][0]
        self.assertEqual(e["korrektur"]["formant_faktor"], 1.08)      # bleibt

    def test_erzaehler_unbesetzt_stopp(self):
        self.antworten = [json.dumps(sb(genre="anderes", erz_m={"geschlecht": "w", "alter": "kind"}))]
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertTrue(any("Erzaehler besetzt (unbesetzt" in x for x in g.ergebnis["gruende"]))
        g = self.lauf(regler={"erzaehler": ["Charon"]})              # Vorgabe Standardstimme (Klon de)
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertTrue(any("Passung" in h for h in g.ergebnis["hinweise"]))
        self.assertEqual(self.bj()["casting_regler"]["erzaehler"], {"*": "Charon"})
        self.assertEqual(self.n_llm, 1)

    def test_premium_vorgabe_gemini(self):
        self.werk(produkte=[{"sprache": "de", "inhalt": "hoerbuch", "stufe": "premium", "kanaele": ["taella"]}],
                  extra={"erzaehler_stimme": "Charon"})
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        e = P.laden("w")["rollen"]["de"]["premium"]["erzaehler"]
        self.assertEqual((e["stimme"], e["gemini_id"], e["quelle"]), ("Charon", "Charon", "vorgabe_altfeld"))

    def test_unnutzbar_und_adapter_stopp(self):
        self.werk(extra={"erzaehler_stimme": "alt_weg"})
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertTrue(any("abgelehnt" in x for x in g.ergebnis["gruende"]))
        self.werk(extra={"tts_lora": "test_v0"})
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertTrue(any("nicht freigegeben" in x for x in g.ergebnis["gruende"]))

    def test_gerettet_mensch(self):
        self.antworten = ['{"erzaehler": {"erzaehlform": "allwissend", "genre_stimme": "abenteuer", '
                          '"merkmale": {"geschlecht": "m", "alter": "alt"}}, "hinweise": "abgeschni']
        g = self.lauf()
        self.assertEqual(self.n_llm, 2)
        self.assertEqual(g.ergebnis["ergebnis"], "mensch")
        self.assertTrue(any("gerettet" in x for x in g.ergebnis["gruende"]))

    def test_mock_dann_live_stopp(self):
        config.RUN_MODE = "mock"
        self.werk(produkte=self.HS)
        g = self.lauf()
        self.assertEqual(self.n_llm, 0)
        self.assertNotEqual(g.ergebnis["ergebnis"], "stopp", g.bericht())
        config.RUN_MODE = "live"
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertTrue(any("mock" in x for x in g.ergebnis["gruende"]))

    def test_gate400_stopp_und_trocken(self):
        S.zuruecksetzen("w", "400", "test", "test")
        g = self.lauf()
        self.assertEqual((g.ergebnis["ergebnis"], g.ergebnis["ruecksprung"]), ("stopp", "400"))
        g = self.lauf(trocken=True)
        self.assertFalse(os.path.exists(P.casting_pfad("w")))

    def test_altfassung_v1(self):
        alt = {"werk": "w", "tor": "freigegeben", "steckbriefe": sb(),
               "plan": {"erzaehler": {"stimme": "herr_a", "id": "voice_herr"},
                        "ensemble": [{"figur": "Alice", "stimme": "w_jung", "korrektur": {"en": {"formant_faktor": 1.05}}}],
                        "statisten": []}}
        with open(P.casting_pfad("w"), "w", encoding="utf-8") as f:
            json.dump(alt, f)
        self.werk(produkte=self.HS)
        g = self.lauf()
        self.assertEqual(self.n_llm, 0)
        self.assertTrue(os.path.exists(os.path.join(self.d, "work", "casting_v1.json")))
        c = P.laden("w")
        bs = c["rollen"]["en"]["premium"]
        self.assertEqual((bs["erzaehler"]["stimme"], bs["erzaehler"]["quelle"]), ("herr_a", "uebernommen"))
        a = [e for e in bs["ensemble"] if e["figur"] == "Alice"][0]
        self.assertEqual((a["stimme"], a["korrektur"]["formant_faktor"]), ("w_jung", 1.05))
        self.assertTrue(any("Schema 1" in h for h in g.ergebnis["hinweise"]))

    def test_teaser_sprache_und_reihe(self):
        self.werk(produkte=[{"sprache": "en", "inhalt": "text", "kanaele": ["taella"]},
                            {"sprache": "de", "inhalt": "hoerbuch", "stufe": "basic", "kanaele": ["taella"]}],
                  extra={"reihe": "r1", "teil": 1})
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        c = P.laden("w")
        self.assertEqual(c["rollen"]["en"]["basic"]["inhalte"], ["teaser"])
        self.assertEqual(c["rollen"]["en"]["basic"]["erzaehler"]["stimme"], "herr_a")
        with open(P.reihe_pfad("r1"), encoding="utf-8") as f:
            rp = json.load(f)
        self.assertEqual(rp["rollen"]["de"]["basic"]["erzaehler"]["stimme"], "herr_a")
        # Teil 2 erbt die Reihenstimme
        os.remove(P.casting_pfad("w"))
        S.zuruecksetzen("w", "410", "test", "test")
        self.antworten = [json.dumps(sb(genre="anderes"))]
        self.werk(produkte=[{"sprache": "de", "inhalt": "hoerbuch", "stufe": "basic", "kanaele": ["taella"]}],
                  extra={"reihe": "r1", "teil": 2})
        g = self.lauf()
        self.assertEqual(g.ergebnis["ergebnis"], "auto", g.bericht())
        self.assertEqual(P.laden("w")["rollen"]["de"]["basic"]["erzaehler"]["quelle"], "reihe")

    def test_cli(self):
        with contextlib.redirect_stdout(io.StringIO()):
            rc = P.main(["w", "--wer", "CK", "--schwelle", "60"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.bj()["casting_regler"]["schwelle"], 60)


if __name__ == "__main__":
    unittest.main()
