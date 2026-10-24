"""READ LAYER — Aussprache-Lexikon je Werk aus dem Glossar (Stage 210) bauen, 19.10.2026.
Lautschreibung NUR fuer die Vertonung (TTS-Text), Format wie Peter Pan / Baskerville:
  work/aussprache_<lg>.json  {"freigegeben": false, "ersatz": {"Tidewater": "Teidwoter", ...}}
Quelle: 210_profil.json -> characters + untranslated (Feld tts_<lg>, seit 19.10.2026) + Autorname.
Fehlt tts_<lg> (aeltere Profile), liefert DeepSeek Flash die Lautschreibung nach (~0,001 $/Werk).
Ein FREIGEGEBENES Lexikon wird nie ueberschrieben (Ausnahme --force); neue Lexika bleiben bis zur Hoerprobe gesperrt.

Aufruf:  py -3.11 tools/aussprache_lexikon.py <werk> [de] [--force]
         py -3.11 tools/aussprache_lexikon.py --alle [de]
"""
import glob, json, os, sys, time

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HIER)
from config import config
from pipeline import api_layer, usage_log

FORCE = "--force" in sys.argv
SPRACHNAME = {"de": "German", "en": "English", "fr": "French", "es": "Spanish", "it": "Italian"}

PROMPT = """You prepare a pronunciation lexicon for a {sprache} text-to-speech narrator reading the {sprache} edition of
"{titel}" by {autor} (original language: {quelle}). Names and terms below stay in the original language inside the
{sprache} text. For each, give a RESPELLING in ordinary {sprache} spelling that makes a {sprache} TTS voice pronounce it
as in the original (examples for German: Peter -> Pieter, John -> Dschonn, George -> Dschordsch, Tidewater -> Teidwoter,
Mr. -> Mister). Use "" if a {sprache} reader already says it correctly (e.g. Buck, Paris). Never translate, never explain.

TERMS: {begriffe}

Return ONLY JSON: {{"<term>": "<respelling or empty>", ...}}"""


def werk_dirs():
    return sorted(glob.glob(os.path.join(HIER, "authors", "*", "books", "*"))
                  + glob.glob(os.path.join(HIER, "users", "*", "works", "*")))


def bauen(werk, lg="de"):
    wd = werk if os.path.isdir(werk) else config.book_dir(werk)
    book_id = os.path.basename(wd)
    pp = os.path.join(wd, "work", "210_profil.json")
    ziel = os.path.join(wd, "work", f"aussprache_{lg}.json")
    if not os.path.exists(pp):
        return "kein_profil"
    if os.path.exists(ziel) and json.load(open(ziel, encoding="utf-8")).get("freigegeben") and not FORCE:
        return "freigegeben_bleibt"
    prof = json.load(open(pp, encoding="utf-8")).get("meta", {}).get("profile", {})
    begriffe, ersatz = [], {}
    for k in ("characters", "untranslated"):
        for name, e in (prof.get(k) or {}).items():
            if not isinstance(e, dict):
                continue
            if k == "characters" and e.get(lg) and e[lg] != name:
                continue                       # Name wird uebersetzt -> keine Fremdaussprache
            t = (e.get(f"tts_{lg}") or "").strip()
            if t and t != name:
                ersatz[name] = t
            elif f"tts_{lg}" not in e:
                begriffe.append(name)
    b = json.load(open(os.path.join(wd, "book.json"), encoding="utf-8")) if os.path.exists(os.path.join(wd, "book.json")) else {}
    autor = ""
    try:
        aj = os.path.join(config.author_dir(config.author_of(book_id)), "author.json")
        autor = json.load(open(aj, encoding="utf-8")).get("name_display", "")
    except Exception:
        pass
    if autor:
        begriffe.append(autor)
    quelle = b.get("originalsprache") or config.SOURCE_LANGUAGE
    if begriffe and quelle != lg:
        try:
            usage_log.set_context(book_id, "aussprache_lexikon")
        except Exception:
            pass
        roh = api_layer.call_model("validator", PROMPT.format(
            sprache=SPRACHNAME.get(lg, lg), titel=b.get("titel_original", book_id), autor=autor or "-",
            quelle=SPRACHNAME.get(quelle, quelle), begriffe=json.dumps(begriffe, ensure_ascii=False)), max_tokens=4000)
        for k, v in (api_layer.parse_json(roh) or {}).items():
            if k in begriffe and isinstance(v, str) and v.strip() and v.strip() != k:
                ersatz[k] = v.strip()
    daten = {"hinweis": "Lautschreibung NUR fuer die Vertonung (TTS-Text). Eintrag loeschen = Wort bleibt wie im Text. "
                        "Laengere Eintraege gelten vor kuerzeren. Nach Hoerprobe 'freigegeben': true setzen.",
             "stand": time.strftime("%Y-%m-%d") + ", automatisch aus 210_profil (tools/aussprache_lexikon.py)",
             "freigegeben": False, "ersatz": dict(sorted(ersatz.items()))}
    tmp = ziel + ".tmp"
    json.dump(daten, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, ziel)
    return f"{len(ersatz)} Eintraege"


if __name__ == "__main__":
    config.RUN_MODE = "live"
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--alle" in sys.argv:
        lg = args[0] if args else "de"
        for w in werk_dirs():
            try:
                print(f"[aussprache] {os.path.basename(w)}: {bauen(w, lg)}", flush=True)
            except Exception as ex:
                print(f"[aussprache] FEHLER {os.path.basename(w)}: {ex}", flush=True)
    else:
        if not args:
            sys.exit(__doc__)
        print(f"[aussprache] {args[0]}: {bauen(args[0], args[1] if len(args) > 1 else 'de')}")
