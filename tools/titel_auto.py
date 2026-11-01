"""
READ LAYER — Laendertitel automatisch (Cockpit-Schritt "titel", 10.10.2026)
=========================================================================
Automatisiert die zweiphasige Werk-Titel-Stufe aus pipeline/s110_wikidata.py:
  1. propose_work  -> Wikidata-Kandidaten (wikidata_work_candidates.json)
  2. bester Kandidat: Titel-Ueberschneidung + Autor/Werkart in der Beschreibung,
     Film/Oper/Musical/Album abgewertet
  3. confirm_work  -> etablierte Laendertitel je Sprache (Wikidata-Sitelink),
     sonst DeepSeek-Fallback (titel_pruefen=true -> Gate 110 Mensch)
Seit Phase 2 (01.11.2026) laeuft der Ablauf als Gate 110 in pipeline/s110_wikidata.run; dieses Modul
liefert nur noch die Kandidatenwahl (waehle, _kandidaten, _varianten, _nachname).

Aufruf:  python tools/titel_auto.py <book_slug>
"""
import os
import re
import sys
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from config import config  # noqa: E402
from pipeline import s110_wikidata as wd  # noqa: E402

WERK = ("novel", "novella", "short story", "story", "book", "literary work", "play", "poem", "tale",
        "essay", "fairy tale", "fable", "collection", "memoir", "treatise", "epic", "roman", "erzählung")
NICHT = ("film", "movie", "opera", "musical", "album", "song", "episode", "television", "tv series",
         "video game", "painting", "ballet", "band", "single", "disambiguation", "comic", "character")


def _nachname(bj):
    try:
        aj = json.load(open(os.path.join(config.author_dir(config.author_of(bj["book_slug"])), "author.json"),
                            encoding="utf-8"))
        name = aj.get("name_display") or ""
    except Exception:
        name = bj.get("author_slug", "").split("-")[0]
    return (name.split()[-1] if name.split() else "").lower()


def _varianten(titel):
    """Suchbegriffe: voller Titel, dann ohne Zusatz nach Komma/Doppelpunkt/Klammer."""
    v = [titel]
    kurz = re.split(r"[,:;(]", titel)[0].strip()
    if kurz and kurz != titel:
        v.append(kurz)
    return v


def _kandidaten(suchwort, src):
    hits = wd._api_get({"action": "wbsearchentities", "search": suchwort, "language": src,
                        "type": "item", "limit": 7}).get("search", [])
    if not hits:
        return []
    detail = wd._api_get({"action": "wbgetentities", "ids": "|".join(h["id"] for h in hits),
                          "props": "labels|descriptions", "languages": "|".join(wd.LABEL_LANGS)}).get("entities", {})
    return [{"wikidata_id": h["id"], "label": wd._label_of(detail.get(h["id"], {})) or h.get("label", ""),
             "beschreibung": wd._description_of(detail.get(h["id"], {})) or h.get("description", "")}
            for h in hits]


def waehle(cands, titel, nachname, schwelle=0.5):
    """Bester Werk-Kandidat: Jaccard >= schwelle (Regler 110), Autor/Werkart in der Beschreibung."""
    best, best_s = None, 0.0
    for c in cands:
        ov = max(wd._title_overlap(c.get("label", ""), t) for t in _varianten(titel))
        if ov < schwelle:
            continue
        b = (c.get("beschreibung") or "").lower()
        s = ov
        if nachname and nachname in b:
            s += 0.6
        if any(w in b for w in WERK):
            s += 0.4
        if any(w in b for w in NICHT):
            s -= 1.0
        if s > best_s:
            best, best_s = c, s
    return best if best_s >= 0.9 else None


def main(slug):
    """Cockpit-Schritt "titel": seit Phase 2 = Gate 110 (pipeline.s110_wikidata.run)."""
    from pipeline import gate
    return gate.EXIT[wd.run(slug)]


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    sys.exit(main(args[0]))
