"""Stage 120 Modernisierung.  py -3.11 -m unittest tests.test_s120"""
import contextlib, io, json, os, re, sys, tempfile, textwrap, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import status as S
from pipeline import s120_modernisierung as M

REG = {"standard": "CK", "nutzer": {"CK": {"rolle": "admin"}}, "mandanten": {}}
SATZ = ("Mr. Holloway walked slowly along the old road toward Dunmore, thinking of the letter that "
        "Margaret had sent him from London in the spring. ")


def roh(contents=True, extra=""):
    t = "The Project Gutenberg eBook of Test\n\n*** START OF THE PROJECT GUTENBERG EBOOK TEST ***\n\nTEST\n\n"
    if contents:
        t += "CONTENTS\n\n CHAPTER I.  The Road\n\n CHAPTER II.  The Letter\n\n\n\n"
    for n in ("I", "II"):
        t += f"CHAPTER {n}.\n\n" + "\n\n".join(textwrap.fill(SATZ * 2 + f"Part {i}.", 70)
                                               for i in range(4)) + "\n\n"
    t += extra + "*** END OF THE PROJECT GUTENBERG EBOOK TEST ***\nlicense text\n"
    return t


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.tmp.name
        self.dir = os.path.join(r, "werk")
        os.makedirs(os.path.join(self.dir, "work"))
        self.alt = (config.book_dir, config.work_dir, config.RUN_MODE, M._call_model, config.author_of)
        config.book_dir = lambda b: self.dir
        config.work_dir = lambda b: os.path.join(self.dir, "work")
        config.author_of = lambda b: "x"
        config.RUN_MODE = "live"
        self.aufrufe = 0
        self.wandel = lambda n, s: s.replace("slowly", "slow")
        self.weglassen = set()

        def fake(prompt, modell=None, temperatur=None):
            self.aufrufe += 1
            aus = []
            for m in re.finditer(r"^\[(\d+)\] (.*)$", prompt, re.M):
                n = int(m.group(1))
                if n in self.weglassen:
                    continue
                aus.append(f"[{n}] {self.wandel(n, m.group(2))}")
            return "\n".join(aus)
        M._call_model = fake
        reg = os.path.join(r, "rollen.json")
        with open(reg, "w") as f:
            json.dump(REG, f)
        os.environ["READLAYER_ROLLEN"] = reg
        os.environ.pop("READLAYER_NUTZER", None)

    def tearDown(self):
        config.book_dir, config.work_dir, config.RUN_MODE, M._call_model, config.author_of = self.alt
        os.environ.pop("READLAYER_ROLLEN", None)
        self.tmp.cleanup()

    def werk(self, text=None, **kw):
        with open(os.path.join(self.dir, "raw.txt"), "w") as f:
            f.write(roh() if text is None else text)
        b = {"book_slug": "w", "quelle": "gutenberg", "quellsprache": "en", "fassung": "modernisiert",
             "mandant": "somnio", "titel_original": "Test",
             "rechte": {"art": "gemeinfrei", "bearbeitung": True}}
        b.update(kw)
        with open(os.path.join(self.dir, "book.json"), "w") as f:
            json.dump(b, f)

    def lauf(self, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return M.run("w", **kw)

    def kap(self, n, orig=False):
        p = os.path.join(self.dir, "work", "modernized", f"chapter-{n}{'.original' if orig else ''}.json")
        with open(p) as f:
            return json.load(f)

    def gate(self):
        return S.laden("w")["stages"]["120"]

    def test_auto_und_resume(self):
        self.werk()
        self.assertEqual(self.lauf(), "auto")
        k = self.kap(1)
        self.assertIn("slow along", k["paragraphs"][0])
        self.assertNotIn("slowly", k["paragraphs"][0])
        self.assertTrue(k["quelle_hash"])
        self.assertIn("slowly", self.kap(1, orig=True)["paragraphs"][0])
        raw = open(os.path.join(self.dir, "raw_modernized.txt")).read()
        self.assertEqual(raw.count("###CHAPTER###"), 2)
        self.assertEqual(len(self.gate()["metriken"]["stichprobe"]), 5)
        n = self.aufrufe
        self.assertEqual(self.lauf(), "auto")
        self.assertEqual(self.aufrufe, n)

    def test_luecke_nachgefordert(self):
        self.werk()
        erst = {"n": 0}
        orig = M._call_model

        def einmal(prompt, modell=None, temperatur=None):
            erst["n"] += 1
            self.weglassen = {1} if erst["n"] == 1 else set()
            return orig(prompt, modell, temperatur)
        M._call_model = einmal
        self.assertEqual(self.lauf(), "auto")
        self.assertEqual(self.kap(1)["fehlend"], [])

    def test_luecke_bleibt_stopp(self):
        self.werk()
        self.weglassen = {2}
        self.assertEqual(self.lauf(), "stopp")
        self.assertEqual(self.kap(1)["fehlend"], [2])
        self.weglassen = set()
        self.assertEqual(self.lauf(), "auto")          # Resume fordert nur die Luecke nach
        self.assertEqual(self.kap(1)["fehlend"], [])

    def test_ohne_inhaltsverzeichnis_mensch_vor_llm(self):
        self.werk(roh(contents=False))
        self.assertEqual(self.lauf(), "mensch")
        self.assertEqual(self.aufrufe, 0)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "raw_modernized.txt")))
        self.assertEqual(self.lauf(kapitel_ok=True), "auto")
        self.assertEqual(self.lauf(), "auto")

    def test_laenge_mensch(self):
        self.werk()
        self.wandel = lambda n, s: s + " " + s
        self.assertEqual(self.lauf(), "mensch")

    def test_eigennamen_mensch(self):
        self.werk()
        self.wandel = lambda n, s: s.replace("Margaret", "she").replace("Dunmore", "town").replace("London", "town")
        self.assertEqual(self.lauf(), "mensch")

    def test_lizenzrest_stopp(self):
        self.werk(roh().replace("CHAPTER II.\n\n", "CHAPTER II.\n\nThis eBook is from Project Gutenberg and "
                                "may be copied freely under the terms of the license. " * 2 + "\n\n"))
        self.assertEqual(self.lauf(), "stopp")
        self.assertEqual(self.gate()["gate"]["ruecksprung"], "100")

    def test_original_ohne_llm(self):
        self.werk(fassung="original")
        self.assertEqual(self.lauf(), "auto")
        self.assertEqual(self.aufrufe, 0)
        self.assertIn("slowly", self.kap(1)["paragraphs"][0])
        self.assertEqual(self.kap(1)["fassung"], "original")

    def test_epub_original_bleibt(self):
        self.werk(quelle="user_epub", mandant="user:x",
                  rechte={"art": "eigene", "bearbeitung": True})
        d = os.path.join(self.dir, "work", "modernized")
        os.makedirs(d)
        for i in (1, 2):
            with open(os.path.join(d, f"chapter-{i}.json"), "w") as f:
                json.dump({"title": f"Chapter {i}", "paragraphs": [SATZ * 2] * 3}, f)
        with open(os.path.join(self.dir, "work", "ingest_bericht.json"), "w") as f:
            json.dump({"kapitel": [{"nr": 1, "titel": "Chapter 1"}, {"nr": 2, "titel": "Chapter 2"}]}, f)
        self.assertEqual(self.lauf(), "auto")
        self.assertIn("slow along", self.kap(2)["paragraphs"][0])
        self.assertIn("slowly", self.kap(2, orig=True)["paragraphs"][0])
        self.assertEqual(self.lauf(), "auto")          # Original wird aus .original.json gelesen

    def test_altbestand_abweichend_mensch(self):
        self.werk()
        d = os.path.join(self.dir, "work", "modernized")
        os.makedirs(d)
        for i in (1, 2, 3):
            with open(os.path.join(d, f"chapter-{i}.json"), "w") as f:
                json.dump({"title": "Alt", "paragraphs": ["alt"]}, f)
        self.assertEqual(self.lauf(), "mensch")
        self.assertEqual(self.aufrufe, 0)
        self.assertEqual(self.kap(1)["title"], "Alt")
        self.assertEqual(self.lauf(force=True), "auto")
        self.assertFalse(os.path.exists(os.path.join(d, "chapter-3.json")))

    def test_altbestand_uebernommen(self):
        self.werk()
        self.assertEqual(self.lauf(), "auto")
        d = os.path.join(self.dir, "work", "modernized")
        for i in (1, 2):                                  # alter Stand: ohne quelle_hash
            k = self.kap(i)
            k["paragraphs"][3] = self.kap(i, orig=True)["paragraphs"][3]   # still eingesetztes Original
            with open(os.path.join(d, f"chapter-{i}.json"), "w") as f:
                json.dump({"title": k["title"], "paragraphs": k["paragraphs"]}, f)
        n = self.aufrufe
        self.assertEqual(self.lauf(), "auto")
        self.assertEqual(self.aufrufe - n, 2)            # nur die zwei unveraenderten Absaetze
        self.assertEqual(self.gate()["metriken"]["altbestand_uebernommen"], 2)
        self.assertEqual(self.kap(1)["param"], M.ALT_PARAM)

    def test_absatz_manuell(self):
        self.werk()
        self.lauf()
        self.assertEqual(self.lauf(absatz_text=["1:2=Margaret walked to Dunmore and London, as told." * 3]), "mensch")
        self.assertEqual(self.kap(1)["manuell"], [1])
        self.assertTrue(self.kap(1)["paragraphs"][1].startswith("Margaret walked"))

    def test_fremd_geaenderte_quelle_bleibt(self):
        self.werk()
        self.lauf()
        p = os.path.join(self.dir, "raw_modernized.txt")
        with open(p, "a") as f:
            f.write("ROSALIND.\n")                       # z. B. drama_vorbereiten
        self.assertEqual(self.lauf(), "mensch")
        self.assertTrue(open(p).read().endswith("ROSALIND.\n"))
        self.assertEqual(self.lauf(force=True), "auto")
        self.assertFalse(open(p).read().endswith("ROSALIND.\n"))


if __name__ == "__main__":
    unittest.main()
