"""
READ LAYER — Regal (Genre-Filter fuer den TAELLA-Book-Shop), 10.10.2026
======================================================================
Bildet das freie Genre aus Stage 20 (work/600_klappentext.json meta.genre / meta.subgenres)
auf wenige feste Regale ab. Die App kennt nur die Regal-Schluessel und ihre Namen.

Aufruf (Katalog nachtraeglich anreichern):  python tools/regal.py [DEMO_DIR]
export_demo.py ruft regal_von(slug) fuer neue Eintraege auf.
"""
import os
import sys
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from config import config  # noqa: E402

# Reihenfolge = Prioritaet beim Abgleich (spezifisch vor allgemein)
REGALE = [
    ("krimi",     ["krimi", "kriminal", "detektiv", "spionage", "true crime", "thriller", "mystery"]),
    ("grusel",    ["horror", "schauer", "geister", "gothic", "grusel", "unheimlich"]),
    ("fantastik", ["fantasy", "science", "phantast", "utopi", "dystopi"]),
    ("maerchen",  ["märchen", "maerchen", "fabel", "legende", "bilderbuch", "kinder", "jugend", "tiergeschichte"]),
    ("buehne",    ["theater", "drama", "tragödie", "tragoedie", "komödie", "komoedie", "schauspiel"]),
    ("abenteuer", ["abenteuer", "western", "seefahrt", "reise"]),
    ("sachbuch",  ["philosoph", "sachbuch", "memoiren", "autobiograf", "essay", "bericht", "einleitung", "brief"]),
]
ALLGEMEIN = {"roman", "belletristik", "klassiker", "erzählung", "erzaehlung", "literatur", ""}


def _match(text):
    t = (text or "").lower()
    for key, worte in REGALE:
        if any(w in t for w in worte):
            return key
    return None


def regal_aus_meta(meta):
    genre = (meta or {}).get("genre") or ""
    subs = (meta or {}).get("subgenres") or []
    if genre.strip().lower() not in ALLGEMEIN:
        k = _match(genre)
        if k:
            return k
    # allgemeines Genre ("Roman") -> erstes passendes Subgenre entscheidet
    for s in subs:
        k = _match(s)
        if k and k != "sachbuch":
            return k
    return "roman"


def regal_von(slug):
    try:
        d = json.load(open(config.work_path(slug, "600_klappentext"), encoding="utf-8"))
    except Exception:
        return {"regal": "roman", "genre": ""}
    meta = d.get("meta", {})
    return {"regal": regal_aus_meta(meta), "genre": meta.get("genre") or ""}


if __name__ == "__main__":
    demo = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(ROOT), "taella-app", "public", "demo")
    kp = os.path.join(demo, "katalog.json")
    kat = json.load(open(kp, encoding="utf-8"))
    for w in kat.get("werke", []):
        w.update(regal_von(w["slug"]))
        print(f"{w['regal']:10} {w['genre'][:28]:29} {w['slug']}")
    json.dump(kat, open(kp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
