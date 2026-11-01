"""Phase 2, Fundament 4: Bestellung je Werk aus book.json (Sprachen, Produkte, Fassung, Mandant, Rechte).

Einzige Quelle fuer Sprachpaar und Bestellung (Katalog: Sprachliste, Produktmodell 095, Querschnitt
Sprachen). Ersetzt config.SOURCE_LANGUAGE / TARGET_LANGUAGES / ALL_LANGUAGES in den Stages; die
Stages stellen beim Umbau auf diese Lesefunktion um:

    from pipeline import bestellung
    b = bestellung.lesen(werk)
    b.quellsprache                    # "en"
    b.zielsprachen                    # ["de"]  (bestellte Sprachen != Ausgangssprache)
    b.sprachen                        # ["en", "de"]  (Ausgangssprache + Ziele)
    b.audiosprachen()                 # Sprachen mit Hoerbuch/Hoerspiel
    b.audiosprachen("hoerspiel")
    b.produkte_fuer(inhalt="hoerbuch", kanal="extern")
    b.hat(kanal="epub", sprache="de")
    b.fassung, b.mandant, b.besitzer, b.rechte

book.json-Felder (Schema dieser Datei):
    quellsprache  "en" | "de" | "es" | "fr" | "it"        (aus 100/150; Altfeld: originalsprache)
    produkte      [{sprache, inhalt, stufe, kanaele, zusatz}]  (aus 095)
                  inhalt text | hoerbuch | hoerspiel; stufe None | basic | premium | drama;
                  kanaele taella | epub | extern; zusatz [] | ["sound_carpet"] (BETA)
    fassung       "modernisiert" | "original"              (aus 115)
    mandant       "somnio" | "user:<uid>" | "verlag:<id>"  (aus 080)
    besitzer      uid/Kennung des Besitzers                 (aus 080)
    rechte        {art, bearbeitung, drm_frei, versichert: {wer, wann} | None, hinweis}  (aus 090)
                  art gemeinfrei | eigene | lizenz | verlag

Altwerke ohne neue Felder: Werte werden abgeleitet (b.abgeleitet nennt die Felder), ohne `produkte`
gilt Text/TAELLA in Ausgangs- und Default-Zielsprache (en->de, sonst ->en). 095 schreibt die echte
Bestellung; `migrieren` schreibt quellsprache/fassung/mandant/besitzer/rechte (nie produkte).
"""
import argparse
import copy
import glob
import json
import os
import sys

from config import config
from pipeline.manifest import json_atomar

INHALTE = ("text", "hoerbuch", "hoerspiel")
STUFEN = ("basic", "premium", "drama")
KANAELE = ("taella", "epub", "extern")
ZUSAETZE = ("sound_carpet",)
BETA = ("sound_carpet",)
FASSUNGEN = ("modernisiert", "original")
RECHTE_ARTEN = ("gemeinfrei", "eigene", "lizenz", "verlag")
QUELLEN = ("gutenberg", "user_epub", "verlag_epub", "fremd_audio")   # Eingangsart (090)

# Gueltigkeitsmatrix (Katalog Produktmodell 095): (inhalt, stufe) -> erlaubte Kanaele
MATRIX = {
    ("text", None): ("taella", "epub"),
    ("hoerbuch", "basic"): ("taella", "epub", "extern"),
    ("hoerbuch", "premium"): ("taella", "extern"),   # Extern nur Plattformen mit Gemini-Audio (Gate 700/710)
    ("hoerspiel", "premium"): ("taella",),
    ("hoerspiel", "drama"): ("taella",),
}


def sprachliste():
    return tuple(getattr(config, "SPRACHLISTE", ("en", "de", "es", "fr", "it")))


def ziel_default(quelle):
    """Default-Zielsprache fuer Altwerke ohne Bestellung (bisheriges Verhalten EN<->DE)."""
    return ["de"] if quelle == "en" else ["en"]


def _lg(s):
    return (s or "").split("-")[0].strip().lower() or None


def werkordner(werk):
    return werk if os.path.isdir(werk) else config.book_dir(werk)


def _book_json(ordner):
    return os.path.join(ordner, "book.json")


def _roh(ordner):
    p = _book_json(ordner)
    if not os.path.exists(p):
        raise FileNotFoundError(f"book.json fehlt: {p}")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------ Normalisieren
def produkt_norm(p):
    """Ein Produkt auf Schema bringen (Kleinschreibung, Listen, stufe None bei Text)."""
    inhalt = (p.get("inhalt") or "").strip().lower()
    stufe = p.get("stufe")
    stufe = (stufe or "").strip().lower() or None
    if inhalt == "text":
        stufe = None
    kan = p.get("kanaele", p.get("kanal")) or []
    if isinstance(kan, str):
        kan = [kan]
    zus = p.get("zusatz") or []
    if isinstance(zus, str):
        zus = [zus]
    return {"sprache": _lg(p.get("sprache")), "inhalt": inhalt, "stufe": stufe,
            "kanaele": [k.strip().lower() for k in kan], "zusatz": [z.strip().lower() for z in zus]}


def produkt_fehler(p, quellsprache=None):
    """Gueltigkeit eines (normalisierten) Produkts -> Liste von Fehlertexten (leer = gueltig)."""
    f = []
    if p["sprache"] not in sprachliste():
        f.append(f"Sprache {p['sprache']!r} nicht in Sprachliste {sprachliste()}")
    if p["inhalt"] not in INHALTE:
        f.append(f"Inhalt {p['inhalt']!r} unbekannt")
        return f
    if p["inhalt"] != "text" and p["stufe"] not in STUFEN:
        f.append(f"Stufe {p['stufe']!r} unbekannt fuer {p['inhalt']}")
        return f
    erlaubt = MATRIX.get((p["inhalt"], p["stufe"]))
    if erlaubt is None:
        f.append(f"{p['inhalt']} {p['stufe']} ist keine gueltige Kombination")
        return f
    if not p["kanaele"]:
        f.append("kein Kanal")
    for k in p["kanaele"]:
        if k not in KANAELE:
            f.append(f"Kanal {k!r} unbekannt")
        elif k not in erlaubt:
            f.append(f"{p['inhalt']} {p['stufe'] or ''} nicht im Kanal {k}".replace("  ", " "))
    for z in p["zusatz"]:
        if z not in ZUSAETZE:
            f.append(f"Zusatz {z!r} unbekannt")
        elif z == "sound_carpet" and p["inhalt"] != "hoerspiel":
            f.append("Sound-Carpet nur mit Hoerspiel")
    return f


def rechte_norm(r, roh=None):
    roh = roh or {}
    leer = {"art": None, "bearbeitung": None, "drm_frei": None, "versichert": None, "hinweis": None}
    if isinstance(r, dict):
        out = dict(leer)
        out.update({k: r.get(k) for k in leer if k in r})
        if out["art"]:
            out["art"] = str(out["art"]).strip().lower()
        return out
    if isinstance(r, str) and r.strip():
        art = r.strip().lower()
        out = dict(leer, art=art)
        if art in ("gemeinfrei", "eigene"):
            out["bearbeitung"] = True
        if roh.get("rechte_hinweis"):
            out["hinweis"] = roh.get("rechte_hinweis")
        return out
    if roh.get("gutenberg_id"):
        return dict(leer, art="gemeinfrei", bearbeitung=True, drm_frei=True)
    return dict(leer)


# ------------------------------------------------------------ Bestellung
class Bestellung:
    def __init__(self, roh, ordner=None):
        self.ordner = ordner
        self.roh = roh
        self.abgeleitet = []
        self.hinweise = []

        q = _lg(roh.get("quellsprache"))
        if not q:
            q = _lg(roh.get("originalsprache"))
            if q:
                self.abgeleitet.append("quellsprache")
            else:
                q = "en"
                self.abgeleitet.append("quellsprache")
                self.hinweise.append("quellsprache/originalsprache fehlt -> en angenommen")
        self.quellsprache = q

        if isinstance(roh.get("produkte"), list):
            self.produkte = [produkt_norm(p) for p in roh["produkte"]]
        else:
            self.abgeleitet.append("produkte")
            self.produkte = [produkt_norm({"sprache": lg, "inhalt": "text", "kanaele": ["taella"]})
                             for lg in [q] + ziel_default(q)]

        fa = (roh.get("fassung") or "").strip().lower() or None
        if not fa:
            self.abgeleitet.append("fassung")
            mod = str(roh.get("modernisierung") or "").lower()
            if mod.startswith("keine") or mod in ("nein", "original", "false"):
                fa = "original"
            elif roh.get("herkunft") in ("privat_upload", "eigenwerk"):
                fa = "original"
            elif roh.get("gutenberg_id"):
                fa = "modernisiert"
        self.fassung = fa

        m = (roh.get("mandant") or "").strip() or None
        bes = roh.get("besitzer") or None
        if not m:
            self.abgeleitet.append("mandant")
            uid = roh.get("owner_uid")
            if not uid and ordner:
                t = os.path.normpath(ordner).split(os.sep)
                if len(t) >= 4 and t[-2] == "works" and t[-4] == "users":
                    uid = t[-3]
            m = f"user:{uid}" if uid else "somnio"
        if not bes:
            bes = m.split(":", 1)[1] if ":" in m else m
        self.mandant = m
        self.besitzer = bes

        if not isinstance(roh.get("rechte"), dict):
            self.abgeleitet.append("rechte")
        self.rechte = rechte_norm(roh.get("rechte"), roh)

    # ---- Sprachen
    @property
    def zielsprachen(self):
        out = []
        for p in self.produkte:
            if p["sprache"] and p["sprache"] != self.quellsprache and p["sprache"] not in out:
                out.append(p["sprache"])
        return out

    @property
    def sprachen(self):
        return [self.quellsprache] + self.zielsprachen

    def audiosprachen(self, inhalt=None):
        inh = (inhalt,) if inhalt else ("hoerbuch", "hoerspiel")
        out = []
        for p in self.produkte:
            if p["inhalt"] in inh and p["sprache"] not in out:
                out.append(p["sprache"])
        return [lg for lg in self.sprachen if lg in out] + [lg for lg in out if lg not in self.sprachen]

    @property
    def mandant_art(self):
        return self.mandant.split(":", 1)[0]

    # ---- Produkte
    def produkte_fuer(self, sprache=None, inhalt=None, stufe=None, kanal=None):
        return [p for p in self.produkte
                if (sprache is None or p["sprache"] == sprache)
                and (inhalt is None or p["inhalt"] == inhalt)
                and (stufe is None or p["stufe"] == stufe)
                and (kanal is None or kanal in p["kanaele"])]

    def hat(self, **k):
        return bool(self.produkte_fuer(**k))

    def kanaele(self, sprache=None):
        out = []
        for p in self.produkte_fuer(sprache=sprache):
            for k in p["kanaele"]:
                if k not in out:
                    out.append(k)
        return out

    def beta(self):
        return [p for p in self.produkte if any(z in BETA for z in p["zusatz"])]

    # ---- Pruefung (Grundlage Gate 095/190)
    def fehler(self):
        f = []
        if self.quellsprache not in sprachliste():
            f.append(f"quellsprache {self.quellsprache!r} nicht in Sprachliste")
        if not self.produkte:
            f.append("keine Produkte bestellt")
        for i, p in enumerate(self.produkte):
            f += [f"produkte[{i}]: {t}" for t in produkt_fehler(p, self.quellsprache)]
        if self.fassung not in FASSUNGEN:
            f.append(f"fassung {self.fassung!r} ungueltig")
        if not (self.mandant == "somnio" or self.mandant.startswith(("user:", "verlag:"))):
            f.append(f"mandant {self.mandant!r} ungueltig")
        if self.rechte.get("art") not in RECHTE_ARTEN:
            f.append(f"rechte.art {self.rechte.get('art')!r} ungueltig")
        if self.fassung == "modernisiert" and self.rechte.get("bearbeitung") is not True:
            f.append("fassung modernisiert ohne Bearbeitungsrecht")
        return f

    def als_dict(self):
        return {"quellsprache": self.quellsprache, "zielsprachen": self.zielsprachen,
                "sprachen": self.sprachen, "audiosprachen": self.audiosprachen(),
                "produkte": copy.deepcopy(self.produkte), "fassung": self.fassung,
                "mandant": self.mandant, "besitzer": self.besitzer, "rechte": dict(self.rechte),
                "abgeleitet": list(self.abgeleitet), "hinweise": list(self.hinweise)}


def lesen_ordner(ordner):
    return Bestellung(_roh(ordner), ordner)


def lesen(werk):
    """Bestellung eines Werks (Book-ID oder Werkordner)."""
    return lesen_ordner(werkordner(werk))


# ------------------------------------------------------------ Schreiben
FELDER = ("quellsprache", "produkte", "fassung", "mandant", "besitzer", "rechte", "quelle", "wunsch")


def schreiben(werk, **felder):
    """Setzt Bestellfelder in book.json (atomar). Unbekannte Felder -> ValueError.
    Produkte werden normalisiert und geprueft; ungueltige -> ValueError (nichts geschrieben)."""
    ordner = werkordner(werk)
    unbekannt = set(felder) - set(FELDER)
    if unbekannt:
        raise ValueError(f"unbekannte Bestellfelder: {sorted(unbekannt)}")
    roh = _roh(ordner)
    if "quellsprache" in felder:
        felder["quellsprache"] = _lg(felder["quellsprache"])
        if felder["quellsprache"] not in sprachliste():
            raise ValueError(f"quellsprache {felder['quellsprache']!r} nicht in Sprachliste")
    if "produkte" in felder:
        felder["produkte"] = [produkt_norm(p) for p in felder["produkte"]]
        f = [t for p in felder["produkte"] for t in produkt_fehler(p)]
        if f:
            raise ValueError("ungueltige Produkte: " + "; ".join(f))
    if "fassung" in felder and felder["fassung"] not in FASSUNGEN:
        raise ValueError(f"fassung {felder['fassung']!r} ungueltig")
    if "rechte" in felder:
        felder["rechte"] = rechte_norm(felder["rechte"], roh)
    if "quelle" in felder and felder["quelle"] not in QUELLEN:
        raise ValueError(f"quelle {felder['quelle']!r} ungueltig")
    if "wunsch" in felder and not isinstance(felder["wunsch"], dict):
        raise ValueError("wunsch muss ein Objekt sein")
    roh.update(felder)
    json_atomar(_book_json(ordner), roh, indent=2)
    _config_cache_loeschen(roh.get("book_slug") or os.path.basename(ordner))
    return lesen_ordner(ordner)


def feld_setzen(werk, **felder):
    """Nicht-Bestellfelder in book.json setzen (z. B. gutenberg_id aus 090), atomar."""
    ordner = werkordner(werk)
    roh = _roh(ordner)
    roh.update(felder)
    json_atomar(_book_json(ordner), roh, indent=2)
    return lesen_ordner(ordner)


def _config_cache_loeschen(book_id):
    c = getattr(config, "_WERK_SPRACHEN_CACHE", None)
    if isinstance(c, dict):
        c.pop(book_id, None)


def migrieren(werk, schreiben_=False):
    """Altwerk: abgeleitete Werte fuer quellsprache/fassung/mandant/besitzer/rechte festschreiben.
    produkte bleiben 095 vorbehalten. Rueckgabe {feld: neuer Wert} (leer = nichts zu tun)."""
    ordner = werkordner(werk)
    b = lesen_ordner(ordner)
    neu = {}
    for feld in ("quellsprache", "fassung", "mandant", "rechte"):
        if feld in b.abgeleitet and getattr(b, feld) is not None:
            neu[feld] = getattr(b, feld)
    if "besitzer" not in b.roh:
        neu["besitzer"] = b.besitzer
    if neu and schreiben_:
        schreiben(ordner, **neu)
    return neu


def alle_werkordner():
    return sorted(os.path.dirname(p) for p in
                  glob.glob(os.path.join(config.AUTHORS_DIR, "*", "books", "*", "book.json"))
                  + glob.glob(os.path.join(config.USERS_DIR, "*", "works", "*", "book.json")))


# ------------------------------------------------------------ CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description="Bestellung je Werk (book.json): anzeigen, pruefen, migrieren")
    ap.add_argument("werk", nargs="?", help="Book-ID oder Werkordner")
    ap.add_argument("--alle", action="store_true", help="alle Werke (nur mit --migrieren/--pruefen)")
    ap.add_argument("--pruefen", action="store_true", help="Fehlerliste; Exit 2 bei Fehlern")
    ap.add_argument("--migrieren", action="store_true", help="abgeleitete Felder anzeigen (Probelauf)")
    ap.add_argument("--schreiben", action="store_true", help="mit --migrieren: in book.json schreiben")
    a = ap.parse_args(argv)
    ordner = alle_werkordner() if a.alle else ([werkordner(a.werk)] if a.werk else [])
    if not ordner:
        ap.error("Werk oder --alle angeben")
    rc = 0
    for o in ordner:
        name = os.path.basename(o)
        try:
            if a.migrieren:
                neu = migrieren(o, schreiben_=a.schreiben)
                if neu or not a.alle:
                    print(f"{name}: {json.dumps(neu, ensure_ascii=False) if neu else 'nichts zu tun'}"
                          + (" -> geschrieben" if neu and a.schreiben else ""))
            elif a.pruefen:
                f = lesen_ordner(o).fehler()
                if f:
                    rc = 2
                    print(f"{name}: " + "; ".join(f))
                elif not a.alle:
                    print(f"{name}: ok")
            else:
                print(json.dumps(lesen_ordner(o).als_dict(), ensure_ascii=False, indent=1))
        except (OSError, ValueError) as e:
            rc = 2
            print(f"{name}: FEHLER {e}", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())
