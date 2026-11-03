"""Stage 710 Auslieferung (AP 710a).  py -3.11 -m unittest tests.test_s710"""
import base64, contextlib, hashlib, io, json, os, shutil, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import manifest, status as S
from pipeline import s700_guard
from pipeline import s710_cloud_export as P

RECHTE = {"art": "gemeinfrei", "bearbeitung": True, "versichert": {"wer": "t", "wann": "x"}}
PRODUKTE = [{"sprache": "en", "inhalt": "text", "kanaele": ["taella"]},
            {"sprache": "de", "inhalt": "hoerbuch", "stufe": "basic", "kanaele": ["taella"]}]


def dump(o, p):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(o, f)


def fake_mp3(q, z, br):
    os.makedirs(os.path.dirname(z), exist_ok=True)
    with open(q, "rb") as f, open(z, "wb") as g:
        g.write(b"MP3" + br.encode() + f.read())


class T710(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.r = self.tmp.name
        self.alt = (config.book_dir, config.work_dir, config.RUN_MODE, config.author_of,
                    getattr(config, "AUSLIEFERUNG_ZIEL", "gcs"), P._mp3)
        config.book_dir = lambda b: os.path.join(self.r, b)
        config.work_dir = lambda b: os.makedirs(os.path.join(self.r, b, "work"), exist_ok=True) or \
            os.path.join(self.r, b, "work")
        config.author_of = lambda b: "autor"
        config.RUN_MODE = "live"
        config.AUSLIEFERUNG_ZIEL = "lokal"
        P._mp3 = fake_mp3
        self.pub = os.path.join(self.r, "public")

    def tearDown(self):
        (config.book_dir, config.work_dir, config.RUN_MODE, config.author_of, config.AUSLIEFERUNG_ZIEL,
         P._mp3) = self.alt
        self.tmp.cleanup()

    # ------------------------------------------------------------ Werk
    def werk(self, w="w", produkte=PRODUKTE, mandant="somnio", g700="auto"):
        d = os.path.join(self.r, w)
        dump({"book_slug": w, "quelle": "gutenberg", "gutenberg_id": 1, "quellsprache": "en", "fassung": "original",
              "mandant": mandant, "produkte": produkte, "rechte": RECHTE, "titel_original": "The Tale",
              "fassungen": [{"sprache": "de", "titel": "Die Geschichte", "titel_quelle": "110"}]},
             os.path.join(d, "book.json"))
        content = {"c001_00001_h": {"type": "h", "en": "Chapter One", "de": "Kapitel eins"},
                   "c001_00002_s": {"type": "s", "en": "One dollar.", "de": "Ein Dollar."},
                   "c001_00003_s": {"type": "s", "en": "That was all.", "de": "Das war alles."}}
        meta = {"title": "The Tale", "author": "O. Henry", "chapters": {"c001": "One"}}
        dump({"meta": meta, "content": content}, config.work_path(w, "330_rueckuebersetzung"))
        c340 = {t: dict(e, align_de=[{"i": 0, "en_span": [0, 3], "de": "Ein", "de_span": [0, 3], "source": "direct"}])
                for t, e in content.items()}
        dump({"meta": meta, "content": c340}, config.work_path(w, "340_wortalignment"))
        dump({"meta": meta, "content": content,
              "production": {"pause_after_ms": {t: {"de": 400, "en": 300} for t in content}}},
             config.work_path(w, "400_regie"))
        dump({"je_ziel": {"de": {"tags": {"c001_00002_s": [{"i": 0, "t": [0.1, 0.4], "tz": [[0.0, 0.3]]}]}}}},
             config.work_path(w, "525_wortbruecke"))
        m = manifest.Manifest(w, "530_pruefung_de", stage="530")
        for t in content:
            p = os.path.join(d, "fassungen", "de", "audio_final", f"{t}.wav")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").write(b"RIFF" + t.encode())
            m.setzen(f"hoerbuch/{t}", "e", datei=p)
        m.speichern()
        dump({"tags": {t: [{"i": 0, "t0": 0.0, "t1": 0.2}] for t in content}}, config.work_path(w, "520_wortzeiten_de"))
        dump({"blurb": {"koeder": [{"en": "A.", "de": "A."}], "einordnung": [], "autor": []}, "vermerke": {}},
             config.work_path(w, "600_klappentext"))
        for lg, var in (("en", ""), ("de", "_audio")):
            p = os.path.join(d, "fassungen", lg, "output", f"cover_final_{lg}{var}.jpg")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").write(b"\xff\xd8" + lg.encode())
            dump({"saetze": [lg]}, os.path.join(d, "fassungen", lg, "blurb", "text", "blurb.json"))
            os.makedirs(os.path.join(d, "fassungen", lg, "blurb", "audio"), exist_ok=True)
            open(os.path.join(d, "fassungen", lg, "blurb", "audio", "k1.mp3"), "wb").write(b"T" + lg.encode())
        prod = {}
        for p in produkte:
            for k in p["kanaele"]:
                sc = s700_guard.scope_name(bestellung_norm(p), k)
                prod[sc] = {"sprache": p["sprache"], "inhalt": p["inhalt"], "stufe": p.get("stufe"), "kanal": k,
                            "zurueckgehalten": None}
                S.ergebnis(w, "700", g700, scope=sc, wer="test")
        dump({"produkte": prod}, s700_guard.pfad(w))
        return d

    def lauf(self, w="w", **kw):
        kw.setdefault("ziel", P.Lokal(self.pub))
        with contextlib.redirect_stdout(io.StringIO()):
            return {g.scope: g for g in P.run(w, wer="test", **kw)}

    def pub_json(self, rel):
        return json.load(open(os.path.join(self.pub, *rel.split("/")), encoding="utf-8"))

    # ------------------------------------------------------------ Tests
    def test_erstlauf_mensch_dann_freigeben(self):
        self.werk()
        gs = self.lauf()
        self.assertEqual(set(gs), {"en:taella", "de:taella"})
        for g in gs.values():
            self.assertEqual(g.ergebnis["ergebnis"], "mensch", g.bericht())
            self.assertIn("erstes Freischalten", " ".join(g.ergebnis["gruende"]))
        self.assertFalse(os.path.exists(os.path.join(self.pub, "demo", "katalog.json")))
        en = self.pub_json("demo/w/manifest_en.json")
        de = self.pub_json("demo/w/manifest_de.json")
        self.assertEqual(en["schema"], 2)
        self.assertEqual(P.schema_pruefen(en), [])
        self.assertEqual(en["sprachen"], ["en", "de"])
        n = next(x for x in en["saetze"] if x["tag_id"] == "c001_00002_s")
        self.assertEqual(n["align_de"][0]["t"], [0.1, 0.4])
        self.assertEqual(n["align"], n["align_de"])
        self.assertEqual(n["align_de"][0]["de_span"], [0, 3])
        self.assertTrue(all(x["audio_path"] == "" for x in en["saetze"]))
        self.assertEqual(de["audio_count"], 3)
        self.assertTrue(de["audio_vollstaendig"])
        self.assertEqual(de["titel"], "Die Geschichte")
        self.assertEqual(next(x for x in de["saetze"] if x["tag_id"] == "c001_00002_s")["pause_after_ms"], 400)
        self.assertTrue(open(os.path.join(self.pub, "demo", "w", "audio", "de", "c001_00002_s.mp3"), "rb")
                        .read().startswith(b"MP3128k"))
        for f in ("cover_en.jpg", "cover_de.jpg", "blurb.json", "wordtimes_de.json", "teaser/de/audio/k1.mp3",
                  "teaser/en/text/blurb.json"):
            self.assertTrue(os.path.exists(os.path.join(self.pub, "demo", "w", *f.split("/"))), f)
        self.assertEqual(self.pub_json("demo/w/wordtimes_de.json")["tags"]["c001_00002_s"], [0.0])
        self.assertEqual(S.zustand("w", "710", scope="de:taella"), "mensch")
        gs = self.lauf(freigeben=True)
        self.assertEqual({g.ergebnis["ergebnis"] for g in gs.values()}, {"auto"})
        kat = self.pub_json("demo/katalog.json")
        e = kat["werke"][0]
        self.assertEqual((e["werk_id"], e["sprachen"], e["status"]), ("autor_w", ["en", "de"], "sichtbar"))
        self.assertEqual(e["audio_vorhanden"], {"en": False, "de": True})
        self.assertEqual(S.zustand("w", "710"), "frei")
        exp = json.load(open(P.pfad("w"), encoding="utf-8"))
        ze = exp["ziele"][P.Lokal(self.pub).kennung()]
        self.assertIn("audio/de/c001_00002_s.mp3", ze["scopes"]["de:taella"]["dateien"])
        self.assertIn("blurb.json", ze["scopes"][P.WERK]["dateien"])

    def test_nur_geaendertes_und_verwaistes(self):
        d = self.werk()
        self.lauf(freigeben=True)
        Z = P.Lokal(self.pub)
        self.lauf(ziel=Z)
        self.assertEqual((Z.hochgeladen, Z.geloescht), (0, 0))
        p = os.path.join(d, "fassungen", "de", "audio_final", "c001_00003_s.wav")
        open(p, "wb").write(b"RIFF neu")
        m = manifest.Manifest("w", "530_pruefung_de")
        m.setzen("hoerbuch/c001_00003_s", "e2", datei=p)
        m.speichern()
        os.remove(os.path.join(d, "fassungen", "de", "blurb", "audio", "k1.mp3"))
        Z = P.Lokal(self.pub)
        gs = self.lauf(ziel=Z)
        self.assertEqual(Z.geloescht, 1)
        self.assertEqual(Z.hochgeladen, 1)          # nur die MP3 (Manifest unveraendert)
        self.assertFalse(os.path.exists(os.path.join(self.pub, "demo", "w", "teaser", "de", "audio", "k1.mp3")))
        self.assertEqual(gs["de:taella"].ergebnis["ergebnis"], "auto")
        # Ziel von aussen veraendert -> wieder hochgeladen
        q = os.path.join(self.pub, "demo", "w", "cover_en.jpg")
        open(q, "wb").write(b"kaputt")
        Z = P.Lokal(self.pub)
        self.lauf(ziel=Z)
        self.assertEqual(Z.hochgeladen, 1)
        self.assertEqual(open(q, "rb").read(), b"\xff\xd8en")

    def test_gate_700_nicht_frei(self):
        self.werk(g700="stopp")
        gs = self.lauf()
        self.assertEqual(gs["en:taella"].ergebnis["ergebnis"], "stopp")
        self.assertEqual(gs["en:taella"].ergebnis["ruecksprung"], "700")
        self.assertFalse(os.path.exists(os.path.join(self.pub, "demo", "w")))

    def test_zurueckgehalten_rest_wird_geliefert(self):
        self.werk()
        S.entfaellt("w", "700", "zurueckgehalten", scope="de:hoerbuch-basic:taella")
        g = json.load(open(s700_guard.pfad("w"), encoding="utf-8"))
        g["produkte"]["de:hoerbuch-basic:taella"]["zurueckgehalten"] = {"wer": "CK"}
        dump(g, s700_guard.pfad("w"))
        gs = self.lauf(freigeben=True)
        self.assertEqual(gs["en:taella"].ergebnis["ergebnis"], "auto", gs["en:taella"].bericht())
        self.assertEqual(gs["de:taella"].ergebnis["ergebnis"], "stopp")
        self.assertEqual(self.pub_json("demo/katalog.json")["werke"][0]["sprachen"], ["en"])

    def test_audio_luecke_stopp_530(self):
        self.werk()
        m = manifest.Manifest("w", "530_pruefung_de")
        m.entfernen("hoerbuch/c001_00003_s")
        m.speichern()
        gs = self.lauf()
        g = gs["de:taella"]
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertEqual(g.ergebnis["ruecksprung"], "530")
        self.assertEqual(gs["en:taella"].ergebnis["ergebnis"], "mensch")

    def test_wortzeiten_luecke_stopp_520(self):
        self.werk()
        dump({"tags": {"c001_00002_s": [{"i": 0, "t0": 0.0}]}}, config.work_path("w", "520_wortzeiten_de"))
        g = self.lauf()["de:taella"]
        self.assertEqual((g.ergebnis["ergebnis"], g.ergebnis["ruecksprung"]), ("stopp", "520"))

    def test_privat(self):
        self.werk(mandant="user:u1")
        gs = self.lauf()
        self.assertEqual({g.ergebnis["ergebnis"] for g in gs.values()}, {"auto"})
        self.assertTrue(os.path.exists(os.path.join(self.pub, "privat", "u1", "w", "manifest_de.json")))
        self.assertEqual(self.pub_json("privat/u1/katalog.json")["werke"][0]["werk_id"], "w")
        self.assertFalse(os.path.exists(os.path.join(self.pub, "demo", "katalog.json")))

    def test_verlag_mensch_bei_aenderung(self):
        d = self.werk(mandant="verlag:v1")
        gs = self.lauf(freigeben=True)
        self.assertEqual({g.ergebnis["ergebnis"] for g in gs.values()}, {"auto"})
        gs = self.lauf()
        self.assertEqual({g.ergebnis["ergebnis"] for g in gs.values()}, {"auto"})
        open(os.path.join(d, "fassungen", "en", "output", "cover_final_en.jpg"), "wb").write(b"\xff\xd8neu")
        gs = self.lauf()
        self.assertEqual(gs["en:taella"].ergebnis["ergebnis"], "mensch")
        self.assertEqual(gs["de:taella"].ergebnis["ergebnis"], "auto")

    def test_zurueckziehen(self):
        self.werk()
        self.lauf(freigeben=True)
        with self.assertRaises(ValueError):
            self.lauf(zurueckziehen=True)
        gs = self.lauf(zurueckziehen=True, grund="Rechte pruefen")
        self.assertEqual({g.ergebnis["ergebnis"] for g in gs.values()}, {"auto"})
        self.assertEqual(self.pub_json("demo/katalog.json")["werke"], [])
        self.assertIn("zurueckgezogen", " ".join(gs["en:taella"].ergebnis["hinweise"]))
        self.lauf(freigeben=True)
        self.assertEqual(len(self.pub_json("demo/katalog.json")["werke"]), 1)

    def test_katalog_generation(self):
        self.werk()

        class Konflikt(P.Lokal):
            n = 0

            def katalog_schreiben(s, rel, obj, gen):
                s.n += 1
                if s.n <= s.grenze:
                    raise P.KatalogKonflikt(rel)
                return super().katalog_schreiben(rel, obj, gen)
        Z = Konflikt(self.pub)
        Z.grenze = 1
        gs = self.lauf(ziel=Z, freigeben=True)
        self.assertEqual(gs["en:taella"].ergebnis["ergebnis"], "auto")
        Z = Konflikt(self.pub)
        Z.grenze = 5
        gs = self.lauf(ziel=Z)
        self.assertEqual(gs["en:taella"].ergebnis["ergebnis"], "stopp")
        self.assertIn("Generation", " ".join(gs["en:taella"].ergebnis["gruende"]))
        # Lokal: fremde Aenderung seit dem Lesen -> Konflikt
        Z = P.Lokal(self.pub)
        kat, gen = Z.katalog_lesen("demo/katalog.json")
        with self.assertRaises(P.KatalogKonflikt):
            Z.katalog_schreiben("demo/katalog.json", kat, gen + 1)

    def test_md5_abweichung_und_uploadfehler(self):
        self.werk()

        class Kaputt(P.Lokal):
            def hochladen(s, quelle, rel, ctype=None):
                if rel.endswith("cover_de.jpg"):
                    return s.schreiben(b"falsch", rel)
                return super().hochladen(quelle, rel, ctype)
        g = self.lauf(ziel=Kaputt(self.pub))["de:taella"]
        self.assertEqual(g.ergebnis["ergebnis"], "stopp")
        self.assertIn("cover_de.jpg", " ".join(g.ergebnis["gruende"]))

        class Fehler(P.Lokal):
            n = 0

            def hochladen(s, quelle, rel, ctype=None):
                if rel.endswith("cover_en.jpg"):
                    s.n += 1
                    if s.n == 1:
                        raise OSError("Netz")      # 1x neu -> ok
                return super().hochladen(quelle, rel, ctype)
        shutil.rmtree(os.path.join(self.pub, "demo"))
        os.remove(P.pfad("w"))
        Z = Fehler(self.pub)
        g = self.lauf(ziel=Z)["en:taella"]
        self.assertEqual(Z.n, 2)
        self.assertNotIn("upload", [p["name"] for p in g.fehler()])

    def test_epub_kanal_folgt_710b_und_altcheckpoint(self):
        self.werk(produkte=PRODUKTE + [{"sprache": "en", "inhalt": "text", "kanaele": ["epub"]}])
        dump({"x": 1}, config.work_path("w", "710_cloud_export_de"))
        gs = self.lauf()
        self.assertEqual(gs["en:epub"].ergebnis["ergebnis"], "mensch")
        self.assertIn("710b", " ".join(gs["en:epub"].ergebnis["gruende"]))
        self.assertTrue(os.path.exists(config.work_path("w", "710_cloud_export_de_alt")))

    def test_dry_und_fremdes_ziel_ohne_status(self):
        self.werk()
        self.lauf(dry=True)
        self.assertFalse(os.path.exists(os.path.join(self.pub, "demo")))
        self.assertEqual(S.zustand("w", "710", scope="en:taella"), "offen")
        config.AUSLIEFERUNG_ZIEL = "gcs"
        self.lauf()                                   # Lokal ist nicht Standardziel -> kein Status
        self.assertEqual(S.zustand("w", "710", scope="en:taella"), "offen")
        self.assertTrue(os.path.exists(os.path.join(self.pub, "demo", "w", "manifest_en.json")))

    def test_gcs_adapter(self):
        class Blob:
            def __init__(s, b, n):
                s.b, s.name = b, n

            def upload_from_string(s, data, content_type=None, if_generation_match=None):
                alt = s.b.daten.get(s.name)
                if if_generation_match is not None and (alt[1] if alt else 0) != if_generation_match:
                    raise type("PreconditionFailed", (Exception,), {})()
                data = data.encode() if isinstance(data, str) else data
                s.b.daten[s.name] = (data, (alt[1] if alt else 0) + 1)

            def upload_from_filename(s, p, content_type=None):
                s.upload_from_string(open(p, "rb").read())

            def delete(s):
                if s.name not in s.b.daten:
                    raise type("NotFound", (Exception,), {})()
                del s.b.daten[s.name]

            def download_as_text(s):
                return s.b.daten[s.name][0].decode()

            @property
            def generation(s):
                return s.b.daten[s.name][1]

            @property
            def md5_hash(s):
                return base64.b64encode(hashlib.md5(s.b.daten[s.name][0]).digest()).decode()

            @property
            def size(s):
                return len(s.b.daten[s.name][0])

        class Bucket:
            name = "b"

            def __init__(s):
                s.daten = {}

            def blob(s, n):
                return Blob(s, n)

            def get_blob(s, n):
                return Blob(s, n) if n in s.daten else None

        class Client:
            def __init__(s):
                s.bk = Bucket()

            def bucket(s, n):
                return s.bk

            def list_blobs(s, bk, prefix=""):
                return [Blob(bk, n) for n in list(bk.daten) if n.startswith(prefix)]
        self.werk()
        Z = P.GCS("b", client=Client())
        gs = self.lauf(ziel=Z, freigeben=True)
        self.assertEqual(Z.kennung(), "gcs:b")
        self.assertIn("werke/autor_w/manifest_de.json", Z.b.daten)
        self.assertIn("catalog.json", Z.b.daten)
        self.assertEqual(json.loads(Z.b.daten["catalog.json"][0])["werke"][0]["pfad"], "werke/autor_w/")
        self.assertEqual(Z.inventar("werke/autor_w")["werke/autor_w/cover_en.jpg"],
                         (hashlib.md5(b"\xff\xd8en").hexdigest(), 4))
        with self.assertRaises(P.KatalogKonflikt):
            Z.katalog_schreiben("catalog.json", {}, 99)
        Z.loeschen("gibt/es/nicht")
        self.assertEqual(gs["de:taella"].ergebnis["ergebnis"], "auto")
        self.assertEqual(S.zustand("w", "710", scope="de:taella"), "offen")  # Standardziel lokal -> kein Status


def bestellung_norm(p):
    from pipeline import bestellung
    return bestellung.produkt_norm(p)


if __name__ == "__main__":
    unittest.main()
