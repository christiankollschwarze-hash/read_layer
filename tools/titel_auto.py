"""
READ LAYER — Laendertitel automatisch (Cockpit-Schritt "titel", 10.10.2026)
=========================================================================
Automatisiert die zweiphasige Werk-Titel-Stufe aus pipeline/s110_wikidata.py:
  1. propose_work  -> Wikidata-Kandidaten (wikidata_work_candidates.json)
  2. bester Kandidat: Titel-Ueberschneidung + Autor/Werkart in der Beschreibung,
     Film/Oper/Musical/Album abgewertet
  3. confirm_work  -> etablierte Laendertitel je Sprache (Wikidata-Sitelink),
     sonst Gemini/DeepSeek-Fallback (titel_pruefen=true -> am Cover-Tor kontrollieren)
Kein passender Kandidat -> nur Fallback-Titel je Zielsprache (titel_pruefen=true).

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


def waehle(cands, titel, nachname):
    best, best_s = None, 0.0
    for c in cands:
        ov = max(wd._title_overlap(c.get("label", ""), t) for t in _varianten(titel))
        if ov < 0.5:
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


_EN_FUNKTION = {"the", "of", "and", "a", "an", "in", "on", "to", "from", "with"}


def _de_pruefen(slug, titel):
    """Wikidata liefert als DE-Titel manchmal den englischen (dewiki-Lemma). Dann
    Uebersetzungsvorschlag holen und zum Pruefen markieren."""
    bp = os.path.join(config.book_dir(slug), "book.json")
    bj = json.load(open(bp, encoding="utf-8"))
    for lang in config.TARGET_LANGUAGES:
        f = next((x for x in bj.get("fassungen", []) if x.get("sprache") == lang), None)
        if not f or (f.get("titel") or "").strip().lower() != titel.strip().lower():
            continue
        if not (set(re.findall(r"[a-z]+", titel.lower())) & _EN_FUNKTION):
            continue
        vorschlag = wd._fallback_title(titel, lang) or titel
        wd._set_fassung_title(bj, lang, vorschlag, "llm", True)
        print(f"  ~ {lang}: Wikidata = Originaltitel -> Vorschlag \"{vorschlag}\" [PRUEFEN]")
    json.dump(bj, open(bp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def main(slug):
    bp = os.path.join(config.book_dir(slug), "book.json")
    bj = json.load(open(bp, encoding="utf-8"))
    titel = (bj.get("titel_original") or "").strip() or slug
    src = bj.get("originalsprache") or config.SOURCE_LANGUAGE
    if bj.get("work_wikidata_id"):
        print(f"[titel] {slug}: work_wikidata_id={bj['work_wikidata_id']} vorhanden -> bestaetigen")
        wd.confirm_work(slug, bj["work_wikidata_id"], force=True)
        _de_pruefen(slug, titel)
        return 0
    c = None
    try:
        for v in _varianten(titel):
            cands = _kandidaten(v, src)
            print(f"[titel] Suche \"{v}\": {len(cands)} Kandidaten")
            for k in cands:
                print(f"    {k['wikidata_id']}  {k['label']} — {k['beschreibung']}")
            c = waehle(cands, titel, _nachname(bj))
            if c:
                break
    except Exception as e:
        # Netzfehler -> NICHT auf geratene Titel ausweichen, Schritt scheitert und laeuft spaeter neu
        print(f"[FEHLER] Wikidata nicht erreichbar: {e}")
        return 1
    if c:
        print(f"[titel] gewaehlt: {c['wikidata_id']} {c['label']} — {c.get('beschreibung','')}")
        wd.confirm_work(slug, c["wikidata_id"], force=True)
        _de_pruefen(slug, titel)
        return 0
    # kein sicherer Treffer -> Fallback je Zielsprache, zum Pruefen markiert
    print("[titel] kein sicherer Wikidata-Treffer -> Uebersetzer-Fallback (pruefen)")
    bj = json.load(open(bp, encoding="utf-8"))
    for lang in config.ALL_LANGUAGES:
        if lang == src:
            wd._set_fassung_title(bj, lang, titel, "original", False)
        else:
            t = wd._fallback_title(titel, lang) or titel
            wd._set_fassung_title(bj, lang, t, "llm", True)
            print(f"  + {lang}: \"{t}\"  [llm -> PRUEFEN]")
    json.dump(bj, open(bp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    sys.exit(main(args[0]))
