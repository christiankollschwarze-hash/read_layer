"""Phase 2, Fundament 5: Kosten-Log mit neuer Stage-Nr.  py -3.11 -m unittest tests.test_usage_log"""
import json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import usage_log as U


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = config.work_dir
        config.work_dir = lambda b: self.tmp.name
        U.set_context(None, None)

    def tearDown(self):
        config.work_dir = self._orig
        U.set_context(None, None)
        self.tmp.cleanup()

    def rows(self):
        p = os.path.join(self.tmp.name, "kosten.jsonl")
        return [json.loads(l) for l in open(p, encoding="utf-8")]

    def test_norm(self):
        self.assertEqual(U.stage_norm("500_de"), ("500", {"sprache": "de"}))
        self.assertEqual(U.stage_norm("345_verschiebung")[0], "340")
        self.assertEqual(U.stage_norm("345_verschiebung")[1]["teil"], "345_verschiebung")
        self.assertEqual(U.stage_norm("55"), ("330", {"stage_alt": "55"}))
        self.assertEqual(U.stage_norm("57b")[0], "420")
        self.assertEqual(U.stage_norm("502")[0], "500")
        self.assertEqual(U.stage_norm("aussprache_lexikon")[0], "400")
        self.assertEqual(U.stage_norm(None, "caster")[0], "410")
        self.assertEqual(U.stage_norm("xyz")[0], None)
        self.assertEqual(U.stage_norm("310"), ("310", {}))

    def test_log_kontext(self):
        U.set_context("w", "310", sprache="de")
        U.log("deepseek-v4-pro", "deepseek", {"prompt_tokens": 1000, "completion_tokens": 100}, {"task": "translator"})
        r = self.rows()[0]
        self.assertEqual((r["stage"], r["sprache"], r["task"]), ("310", "de", "translator"))
        self.assertIsNotNone(r["usd"])

    def test_log_ohne_stage_task_rueckfall(self):
        os.environ["READLAYER_BOOK"] = "w"
        try:
            U.log("gemini-3.8-flash-tts", "gemini", {"promptTokenCount": 10, "candidatesTokenCount": 250},
                  {"task": "tts"})
            U.log("deepseek-v4-pro", "deepseek", {"prompt_tokens": 1}, {"task": "unbekannt"})
        finally:
            del os.environ["READLAYER_BOOK"]
        r = self.rows()
        self.assertEqual((r[0]["stage"], r[0]["stage_quelle"]), ("500", "task"))
        self.assertEqual(r[1]["stage"], "?")

    def test_gpu_und_stueck(self):
        usd = U.log_gpu("w", "345", 3600, gpu="T4")
        self.assertAlmostEqual(usd, config.MODAL_T4_USD_H)
        U.log_stueck("gemini-voice-design", 1, book_id="w", stage="410", extra={"stimme": "x"})
        r = self.rows()
        self.assertEqual((r[0]["stage"], r[0]["teil"], r[0]["gpu_s"]), ("340", "345", 3600))
        self.assertEqual((r[1]["stage"], r[1]["stueck"], r[1]["usd"]), ("410", 1, None))

    def test_kontext_temporaer(self):
        U.set_context("w", "500")
        with U.kontext("w", "410", teil="voice_design"):
            U.log("gemini-3.8-flash-tts", "gemini", {"candidatesTokenCount": 25}, {"task": "tts"})
        U.log("gemini-3.8-flash-tts", "gemini", {"candidatesTokenCount": 25}, {"task": "tts"})
        r = self.rows()
        self.assertEqual([x["stage"] for x in r], ["410", "500"])
        self.assertEqual(r[0]["teil"], "voice_design")

    def test_summe_altzeilen(self):
        alt = [{"stage": "55", "modell": "deepseek-v4-flash", "in": 1, "usd": 0.1},
               {"stage": None, "task": "caster", "modell": "gemini-2.5-pro", "usd": 0.2},
               {"stage": "345_pruefaligner", "modell": "modal-T4 awesome_co", "sekunden": 10, "usd": 0.01},
               {"stage": "500_de", "modell": "gemini-3.8-flash-tts", "usd": 0.3}]
        with open(os.path.join(self.tmp.name, "kosten.jsonl"), "w", encoding="utf-8") as f:
            for z in alt:
                f.write(json.dumps(z) + "\n")
        s = U.summe("w")
        self.assertEqual(set(s["stages"]), {"330", "410", "340", "500"})
        self.assertEqual(s["stages"]["340"]["gpu_s"], 10)
        self.assertEqual(U.summe("w", "500")["gesamt"]["usd"], 0.3)


if __name__ == "__main__":
    unittest.main()
