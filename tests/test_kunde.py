"""AP Kunden-Cockpit, Punkt 1+2: Rollen/Anmeldung, Kunden-API, Sperre der internen Routen.
  py -3.11 -m unittest tests.test_kunde
"""
import http.client, json, os, sys, tempfile, threading, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import bestellung, s080_mandant as M
from cockpit import anmeldung as ANM, server as SRV, werk_api as WERK

KW = "geheim-1234567"
REG = {"standard": "CK",
       "nutzer": {"CK": {"rolle": "admin", "zugang": ANM.hash_kennwort(KW)},
                  "anna": {"rolle": "kurator", "zugang": ANM.hash_kennwort(KW)},
                  "demo": {"rolle": "verlag", "verlag": "demo", "mandanten": ["user:smoke"], "tarif": "pro",
                           "zugang": ANM.hash_kennwort(KW)},
                  "lisa": {"rolle": "autor", "zugang": ANM.hash_kennwort(KW)},
                  "ohne": {"rolle": "verlag"}},
       "mandanten": {"verlag:demo": {"tarif": "basic"}}}
WERKE = {"w-demo": "verlag:demo", "w-smoke": "user:smoke", "w-fremd": "verlag:anderer", "w-lisa": "user:lisa"}
VERBOTEN = ("usd", "$", "kosten", "stage", "modal", "chatterbox", "gemini", "elevenlabs", "whisper", "log",
            "pipeline", "engine", "modell", "work/", "authors/", "users/")


def B(w):
    if w not in WERKE:
        raise KeyError(w)
    m = WERKE[w]
    return bestellung.Bestellung(dict(quellsprache="en", mandant=m, besitzer=m.split(":", 1)[1], fassung="modernisiert",
                                      herkunft="privat_upload", rechte={"art": "gemeinfrei", "bearbeitung": True},
                                      produkte=[{"sprache": "de", "inhalt": "text", "kanaele": ["taella"]},
                                                {"sprache": "de", "inhalt": "hoerbuch", "stufe": "basic",
                                                 "kanaele": ["taella"]}]))


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        reg = os.path.join(cls.tmp.name, "rollen.json")
        with open(reg, "w", encoding="utf-8") as f:
            json.dump(REG, f)
        os.environ["READLAYER_ROLLEN"] = reg
        cls._lesen, cls._liste = bestellung.lesen, WERK.werke_liste
        bestellung.lesen = B
        WERK.werke_liste = lambda: [{"book_id": w, "titel": "Titel " + w, "autor": "Autor", "privat": False,
                                     "ampel": "gruen"} for w in WERKE]
        cls.srv = SRV.ThreadingHTTPServer(("127.0.0.1", 0), SRV.H)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        bestellung.lesen, WERK.werke_liste = cls._lesen, cls._liste
        os.environ.pop("READLAYER_ROLLEN", None)
        cls.tmp.cleanup()

    def tearDown(self):
        SRV.LOKAL = ("127.0.0.1", "::1", "::ffff:127.0.0.1")

    def req(self, pfad, methode="GET", body=None, cookie=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Content-Type": "application/json"}
        if cookie:
            h["Cookie"] = cookie
        c.request(methode, pfad, body=json.dumps(body) if body is not None else None, headers=h)
        r = c.getresponse()
        roh = r.read()
        return r.status, roh, r.getheader("Set-Cookie")

    def anmelden(self, wer, kw=KW):
        st, roh, sc = self.req("/api/anmelden", "POST", {"nutzer": wer, "kennwort": kw})
        return st, (sc or "").split(";")[0], json.loads(roh)

    # ---------------------------------------------------------------- Rollen (s080)
    def test_rollen_und_tarif(self):
        self.assertTrue(M.ist_kunde("demo") and M.ist_kunde("lisa"))
        self.assertFalse(M.ist_kunde("CK") or M.ist_kunde("anna"))
        self.assertEqual(M.tarif("demo"), "pro")
        self.assertEqual(M.tarif("lisa"), "pay-per-job")
        self.assertTrue(M.eigenes_werk("w-demo", "demo") and M.eigenes_werk("w-smoke", "demo"))
        self.assertFalse(M.eigenes_werk("w-fremd", "demo"))
        self.assertTrue(M.eigenes_werk("w-lisa", "lisa"))
        self.assertFalse(M.eigenes_werk("w-demo", "lisa"))
        self.assertFalse(M.eigenes_werk("gibt-es-nicht", "demo"))

    # ---------------------------------------------------------------- Anmeldung
    def test_anmeldung_falsch_und_ohne_zugang(self):
        self.assertEqual(self.anmelden("demo", "falsch")[0], 401)
        self.assertEqual(self.anmelden("ohne", "")[0], 401)
        self.assertEqual(self.anmelden("niemand")[0], 401)

    def test_abmelden(self):
        st, ck, d = self.anmelden("demo")
        self.assertEqual((st, d["kunde"]), (200, True))
        self.assertEqual(self.req("/api/kunde/ich", cookie=ck)[0], 200)
        self.req("/api/abmelden", "POST", {}, cookie=ck)
        self.assertEqual(self.req("/api/kunde/ich", cookie=ck)[0], 403)        # lokal, ohne Sitzung, kein ?als

    # ---------------------------------------------------------------- Sperre interner Routen
    def test_kunde_403_auf_internen_routen(self):
        _, ck, _ = self.anmelden("demo")
        for p in ("/", "/werk", "/monitor", "/api/werkliste", "/api/werke", "/api/nutzer", "/api/ampel",
                  "/api/hilfe", "/api/werk/w-demo", "/api/werk/w-demo/monitor/410", "/api/werk/w-demo/lauf",
                  "/datei?p=config/rollen.json", "/paket.zip?p=config", "/api/upload"):
            self.assertEqual(self.req(p, cookie=ck)[0], 403, p)
        for p in ("/api/werk/w-demo/aktion", "/api/werk/w-demo/lauf", "/api/werk/w-demo/stop", "/api/upload"):
            self.assertEqual(self.req(p, "POST", {"wer": "CK"}, cookie=ck)[0], 403, p)

    def test_von_aussen_ohne_anmeldung_401(self):
        SRV.LOKAL = ()
        for p in ("/", "/api/werk/w-demo", "/datei?p=config/rollen.json", "/api/kunde/werke"):
            self.assertEqual(self.req(p)[0], 401, p)
        self.assertEqual(self.req("/kunde")[0], 200)

    def test_kurator_sitzung_kann_wer_nicht_faelschen(self):
        _, ck, d = self.anmelden("anna")
        self.assertFalse(d["kunde"])
        self.assertEqual(self.req("/api/kunde/werke", cookie=ck)[0], 403)      # intern != Kunde
        orig, gesehen = WERK.werk, []
        WERK.werk = lambda b, wer=None: gesehen.append(wer) or {"ok": True}
        try:
            self.assertEqual(self.req("/api/werk/w-demo?wer=CK", cookie=ck)[0], 200)
        finally:
            WERK.werk = orig
        self.assertEqual(gesehen, ["anna"])                                     # Sitzung schlaegt ?wer=

    # ---------------------------------------------------------------- Kunden-API
    def test_kunde_sieht_nur_eigene_werke(self):
        _, ck, _ = self.anmelden("demo")
        st, roh, _ = self.req("/api/kunde/werke", cookie=ck)
        ids = sorted(w["id"] for w in json.loads(roh)["werke"])
        self.assertEqual(ids, ["w-demo", "w-smoke"])
        self.assertEqual(self.req("/api/kunde/werk/w-fremd", cookie=ck)[0], 404)
        self.assertEqual(self.req("/api/kunde/werk/gibt-es-nicht", cookie=ck)[0], 404)
        st, roh, _ = self.req("/api/kunde/werk/w-demo", cookie=ck)
        d = json.loads(roh)
        self.assertEqual(st, 200)
        self.assertIn({"sprache": "Deutsch", "produkt": "Hörbuch (Standard)"}, d["produkte"])

    def test_admin_lokal_kundensicht_als(self):
        st, roh, _ = self.req("/api/kunde/werke?als=demo")
        self.assertEqual(st, 200)
        self.assertEqual(len(json.loads(roh)["werke"]), 2)
        self.assertEqual(self.req("/api/kunde/werke?als=anna")[0], 403)        # anna ist keine Kundin

    def test_kunden_antworten_ohne_verbotene_begriffe(self):
        _, ck, _ = self.anmelden("demo")
        for p in ("/api/kunde/ich", "/api/kunde/werke", "/api/kunde/werk/w-demo", "/api/kunde/werk/w-fremd"):
            txt = self.req(p, cookie=ck)[1].decode("utf-8").lower()
            for v in VERBOTEN:
                self.assertNotIn(v, txt, f"{p}: {v!r}")


if __name__ == "__main__":
    unittest.main()
