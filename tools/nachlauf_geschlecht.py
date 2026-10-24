"""READ LAYER — Nachlauf 19.10.2026: Felder fuer die Klappentext-Erzaehlerstimme im Bestand ergaenzen.
  autor_geschlecht      -> authors/<autor>/author.json      (Wikidata P21, kostenlos)
  hauptfigur_geschlecht -> work/600_klappentext.json meta  (DeepSeek Flash, Textprobe wie Stage 600, ~0,0005 $/Werk)
Regel: claude/PROZESS_klappentext_erzaehler.md

Aufruf:  py -3.11 tools/nachlauf_geschlecht.py [--nur-autoren | --nur-werke] [--force]
"""
import glob, json, os, sys
from concurrent.futures import ThreadPoolExecutor

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HIER)
from config import config
from pipeline import api_layer, usage_log
from pipeline import s110_wikidata as wd
from pipeline import s600_klappentext as kt

FORCE = "--force" in sys.argv
WERTE = {"weiblich", "maennlich", "unklar"}


def _schreiben(pfad, daten):
    tmp = pfad + ".tmp"
    json.dump(daten, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    os.replace(tmp, pfad)


def autoren():
    offen = {}
    for p in sorted(glob.glob(os.path.join(HIER, "authors", "*", "author.json"))):
        a = json.load(open(p, encoding="utf-8"))
        q = a.get("wikidata_id")
        if q and (FORCE or not a.get("autor_geschlecht")):
            offen[q] = p
    print(f"[autoren] {len(offen)} offen")
    ids = list(offen)
    n_ok = 0
    for i in range(0, len(ids), 50):
        teil = ids[i:i + 50]
        ent = wd._api_get({"action": "wbgetentities", "ids": "|".join(teil), "props": "claims"}).get("entities", {})
        for q in teil:
            g = wd.geschlecht_aus(ent.get(q, {})) if ent.get(q) else ""
            p = offen[q]
            a = json.load(open(p, encoding="utf-8"))
            a["autor_geschlecht"] = g or "unbekannt"
            _schreiben(p, a)
            n_ok += bool(g)
    print(f"[autoren] fertig: {n_ok}/{len(ids)} mit Geschlecht aus Wikidata")


PROMPT = ("Bestimme das Geschlecht der zentralen Figur dieses Werks, um die die Handlung kreist "
          "(Ich-Erzaehler zaehlt; Tiere nach erzaehltem Geschlecht). Ohne klare Hauptfigur: 'unklar'.\n"
          "Bekannte Hauptfiguren laut Metadaten: {figuren}\n\n{probe}\n\n"
          'Antworte NUR mit JSON: {{"hauptfigur_geschlecht": "weiblich" | "maennlich" | "unklar"}}')


def werk(p):
    d = json.load(open(p, encoding="utf-8"))
    meta = d.setdefault("meta", {})
    if meta.get("hauptfigur_geschlecht") in WERTE and not FORCE:
        return "skip"
    book_dir = os.path.dirname(os.path.dirname(p))
    book_id = os.path.basename(book_dir)
    try:
        usage_log.set_context(book_id, "nachlauf_geschlecht")
    except Exception:
        pass
    try:
        body = kt._strip_boilerplate(kt._load_source_text(book_id))
        probe = kt._sample(body)
    except Exception:
        probe = meta.get("essenz", "")
    roh = api_layer.call_model("validator", PROMPT.format(
        figuren=", ".join(meta.get("hauptfiguren", [])) or "-", probe=probe), max_tokens=200)
    g = (api_layer.parse_json(roh) or {}).get("hauptfigur_geschlecht", "unklar")
    meta["hauptfigur_geschlecht"] = g if g in WERTE else "unklar"
    _schreiben(p, d)
    return meta["hauptfigur_geschlecht"]


def werke():
    pfade = sorted(glob.glob(os.path.join(HIER, "authors", "*", "books", "*", "work", "600_klappentext.json"))
                   + glob.glob(os.path.join(HIER, "users", "*", "works", "*", "work", "600_klappentext.json")))
    print(f"[werke] {len(pfade)} Klappentexte")
    erg = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for p, r in zip(pfade, pool.map(lambda x: _sicher(werk, x), pfade)):
            erg[r] = erg.get(r, 0) + 1
    print(f"[werke] fertig: {erg}")


def _sicher(f, x):
    try:
        return f(x)
    except Exception as ex:
        print(f"  FEHLER {x}: {ex}")
        return "fehler"


if __name__ == "__main__":
    config.RUN_MODE = "live"
    if "--nur-werke" not in sys.argv:
        autoren()
    if "--nur-autoren" not in sys.argv:
        werke()
