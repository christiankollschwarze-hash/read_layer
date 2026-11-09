"""STAGE 110 — Wikidata (nur Gutenberg; GATE_KATALOG.md, Phase 2 01.11.2026)
Funktion:     Verifizierte Autor-Fakten (author.json verified) und Werktitel je Sprache (book.json
              fassungen[].titel/titel_quelle) + Werk-Q-ID + erscheinungsjahr (P577).
Gate:         Autor: Kandidaten mit Namens- und Todesjahr-Treffer (+-1 zu Gutendex); genau 1 -> auto
              bestaetigt; 0/mehrere -> Mensch (Kandidatenliste). PD mit Wikidata-Todesjahr verletzt -> Stopp
              (Ruecksprung 100). Werk: Jaccard Titel >= Schwelle -> Wikidata-Titel auto; LLM-Titel oder kein
              Kandidat -> Mensch. Titel je Sprache = Quellsprache + bestellte Zielsprachen (book.json).
              Wikidata nicht erreichbar -> Stopp (neu abfragen).
Regler:       --autor-qid Q, --werk-qid Q, --titel de="..." (mehrfach), --jaccard 0.5, --neu,
              PD-Nachweis --pd-url | --rechteinhaber [eigene|lizenz] | --pd-quelle (--deckt autor,uebersetzer)
              (Monitor 110, 04.11.2026; Nachweis erfuellt pd_wikidata). Kandidaten -> work/110_kandidaten.json.
Befunde 110:  Autor-Teil laeuft jetzt in der Kette (vorher nie vom Cockpit); Sanity-Pruefung Autor ueber
              Name + Todesjahr; Schreibvorgaenge atomar; Abgleich Todesjahr Wikidata <-> Gutendex (Hinweis);
              Fallback-Titel per DeepSeek (api_layer "translator"), nicht Gemini.
Kosten:       Wikidata 0 $; Fallback-Titel DeepSeek, Bruchteil eines Cents je Sprache.

Aufruf (Kette):  python -m pipeline.s110_wikidata <werk> [--autor-qid Q42] [--werk-qid Q183883]
                 [--titel de="Der Ruf der Wildnis"] [--neu] [--wer CK]
Altweg:          --author <slug> --propose|--confirm Q  /  --work <slug> --propose|--confirm Q
Exit: 0 auto, 2 Stopp, 3 Mensch.

--- Bisherige Beschreibung ---

READ LAYER — Stage 08b: Wikidata-Anreicherung des Autors (zweiphasig)
=====================================================================
Reichert ein bereits durch anlegen.py angelegtes author.json um harte
Wikidata-Fakten an. Menschliche Bestaetigung ist die Huerde ZWISCHEN den
beiden Phasen -- kein interaktives input(), sondern zwei CLI-Aufrufe.

PHASE 1 — Vorschlag:
  python s110_wikidata.py --author wells-hg --propose
    -> wbsearchentities holt Kandidaten zum name_display aus author.json
    -> EIN wbgetentities ueber alle Kandidaten (Label, Beschreibung, P569/P570)
    -> nummerierte Liste mit Lebensdaten (zum Unterscheiden), abgelegt als
       authors/<slug>/wikidata_candidates.json

PHASE 2 — Bestaetigung:
  python s110_wikidata.py --author wells-hg --confirm Q42878
    -> wbgetentities fuer die bestaetigte Q-ID
    -> HART: P569/P570 (Lebensjahre), P19 (Geburtsort), P800 (notable works)
    -> WEICH: Wikipedia-Sitelink -> quelle_weich
    -> schreibt in author.json (verified=True) und setzt index.json authors[slug]=Q-ID

Felder werden 1:1 auf das anlegen.py-Schema gemappt -- KEIN neues Feld erfunden:
  wikidata_id, verified, geburtsjahr, todesjahr, geburtsort,
  notable_works, quelle_weich.

WERK-TITEL (zweite, parallele Phase -- Laendertitel je Fassung):
  python s110_wikidata.py --work jekyll-and-hyde --propose
    -> wbsearchentities auf titel_original -> Werk-Kandidaten (Roman/Film/Oper
       unterscheidbar an Jahr+Beschreibung) -> books/<slug>/wikidata_work_candidates.json
  python s110_wikidata.py --work jekyll-and-hyde --confirm Q183883
    -> wbgetentities props=sitelinks -> je Zielsprache der etablierte Titel
       (Klammer-Zusatz wie "(roman)" gestrippt). Haerte-Hierarchie pro Sprache:
         1. Wikidata-Sitelink   -> titel_quelle="wikidata"  (hart, kein Marker)
         2. Gemini-Fallback     -> titel_quelle="llm", titel_pruefen=True  (weich)
         3. Quellsprache        -> titel_original, titel_quelle="original"
    -> schreibt book.json.fassungen[] (additiv pro sprache, nur Titel-Felder)
       + book.json.work_wikidata_id. Sprachen = config.ALL_LANGUAGES.

RUN_MODE:
  "mock" -> feste Beispieldaten (Wikidata + Gemini aus dem Claude-Container gesperrt).
            Dient nur zum Testen des Schreib-/Mapping-Pfads.
  "live" -> echte Wikidata-API (kein Key noetig). Laeuft lokal bei CK.
"""

import os, sys, json, re, argparse, time
import urllib.request, urllib.parse

def _find_root(start: str) -> str:
    """Aufwaerts den Ordner suchen, der das config-Paket enthaelt.
    Funktioniert egal ob diese Datei in der Wurzel oder in pipeline/ liegt."""
    d = start
    while True:
        if os.path.isdir(os.path.join(d, "config")):
            return d
        parent = os.path.dirname(d)
        if parent == d:          # Dateisystem-Wurzel erreicht -> Fallback
            return start
        d = parent

sys.path.insert(0, _find_root(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline.manifest import json_atomar

WD_API = "https://www.wikidata.org/w/api.php"
UA     = {"User-Agent": "ReadLayer/1.0 (https://somnio-publishing.net; title lookup, low volume)"}

# Sprachen fuer Labels/Beschreibungen (Quellsprache zuerst, dann Deutsch als Fallback)
LABEL_LANGS = [config.SOURCE_LANGUAGE, "de", "en"]


# ============================================================
# HTTP / API
# ============================================================
def _api_get(params: dict) -> dict:
    """GET auf die Wikidata-API. Im mock-Modus: feste Fixtures."""
    params = {**params, "format": "json"}
    if config.RUN_MODE == "mock":
        return _mock_response(params)
    import time
    import urllib.error
    url = WD_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA)
    # 11.10.2026: Wikidata drosselt (HTTP 429) bei Serienlaeufen -> Takt + Wiederholung mit Wartezeit
    for versuch in range(6):
        warte = 1.0 - (time.time() - _api_get.letzter)
        if warte > 0:
            time.sleep(warte)
        _api_get.letzter = time.time()
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or versuch == 5:
                raise
            ra = e.headers.get("Retry-After") if e.headers else None
            pause = int(ra) if ra and str(ra).isdigit() else 15 * (versuch + 1)
            print(f"    [wikidata] HTTP {e.code} -> warte {pause}s (Versuch {versuch + 1}/6)")
            time.sleep(pause)


_api_get.letzter = 0.0


# ============================================================
# CLAIM-PARSING (defensiv -- fehlende Properties sind normal)
# ============================================================
def _claims(entity: dict, pid: str) -> list:
    return entity.get("claims", {}).get(pid, [])

GESCHLECHT_QID = {"Q6581072": "weiblich", "Q1052281": "weiblich",      # female, trans woman
                  "Q6581097": "maennlich", "Q2449503": "maennlich"}    # male, trans man


def geschlecht_aus(entity: dict) -> str:
    """19.10.2026: P21 (sex or gender) -> 'weiblich' | 'maennlich' | '' (fuer die Klappentext-Erzaehlerstimme)."""
    v = _first_value(entity, "P21")
    return GESCHLECHT_QID.get(v.get("id", ""), "") if isinstance(v, dict) else ""


def _first_value(entity: dict, pid: str):
    for c in _claims(entity, pid):
        dv = c.get("mainsnak", {}).get("datavalue", {})
        if dv:
            return dv.get("value")
    return None

def _all_ids(entity: dict, pid: str) -> list:
    """Alle verlinkten Q-IDs einer Property (z.B. P800 notable works)."""
    out = []
    for c in _claims(entity, pid):
        v = c.get("mainsnak", {}).get("datavalue", {}).get("value", {})
        if isinstance(v, dict) and v.get("id"):
            out.append(v["id"])
    return out

def _year_from_time(timeval) -> int | None:
    """Wikidata-Zeit '+1850-11-13T00:00:00Z' / '-0399-...' -> Jahr (int, ggf. negativ)."""
    if not isinstance(timeval, dict):
        return None
    m = re.match(r"([+-])(\d+)-", timeval.get("time", ""))
    if not m:
        return None
    year = int(m.group(2))
    return -year if m.group(1) == "-" else year

def _label_of(entity: dict) -> str:
    labels = entity.get("labels", {})
    for lang in LABEL_LANGS:
        if lang in labels:
            return labels[lang].get("value", "")
    # irgendein vorhandenes Label
    for v in labels.values():
        return v.get("value", "")
    return ""

def _description_of(entity: dict) -> str:
    descs = entity.get("descriptions", {})
    for lang in LABEL_LANGS:
        if lang in descs:
            return descs[lang].get("value", "")
    return ""


def _resolve_labels(qids: list) -> dict:
    """Q-IDs -> {qid: label}. Ein gebuendelter wbgetentities-Call (max 50)."""
    out = {}
    qids = [q for q in dict.fromkeys(qids) if q]  # dedupe, Reihenfolge halten
    for i in range(0, len(qids), 50):
        batch = qids[i:i + 50]
        data = _api_get({
            "action": "wbgetentities",
            "ids": "|".join(batch),
            "props": "labels",
            "languages": "|".join(LABEL_LANGS),
        })
        for qid, ent in data.get("entities", {}).items():
            out[qid] = _label_of(ent)
    return out


def _author_language_qid(ent: dict) -> str:
    """Sprache des Autors: P103 (Muttersprache) bevorzugt, sonst erstes P1412
    (gesprochene/geschriebene Sprachen). Liefert die Sprach-Q-ID."""
    p103 = _first_value(ent, "P103")
    if isinstance(p103, dict) and p103.get("id"):
        return p103["id"]
    for q in _all_ids(ent, "P1412"):
        return q
    return ""

def _resolve_lang_code(lang_qid: str) -> str:
    """Sprach-Q-ID -> ISO-639-1-Code via P218 (z.B. Q1860 -> 'en')."""
    if not lang_qid:
        return ""
    ent = _api_get({
        "action": "wbgetentities",
        "ids": lang_qid,
        "props": "claims",
    }).get("entities", {}).get(lang_qid, {})
    code = _first_value(ent, "P218")
    return code.lower() if isinstance(code, str) else ""


# ============================================================
# PHASE 1 — VORSCHLAG
# ============================================================
def propose(author_slug: str, limit: int = 7):
    author_path = _author_path(author_slug)
    aj = _read_author(author_path)
    name = aj.get("name_display", "").strip()
    if not name:
        raise ValueError(f"author.json hat kein name_display ({author_path}).")

    print(f"Suche Wikidata-Kandidaten fuer: \"{name}\"\n")

    search = _api_get({
        "action": "wbsearchentities",
        "search": name,
        "language": config.SOURCE_LANGUAGE,
        "type": "item",
        "limit": limit,
    })
    hits = search.get("search", [])
    if not hits:
        print("Keine Treffer. Namensschreibung pruefen oder --propose mit anderem name_display.")
        return

    # Lebensdaten zum Unterscheiden gleichnamiger Personen nachladen (ein Call).
    ids = [h["id"] for h in hits]
    detail = _api_get({
        "action": "wbgetentities",
        "ids": "|".join(ids),
        "props": "labels|descriptions|claims",
        "languages": "|".join(LABEL_LANGS),
    }).get("entities", {})

    candidates = []
    for h in hits:
        qid = h["id"]
        ent = detail.get(qid, {})
        geb = _year_from_time(_first_value(ent, "P569"))
        tod = _year_from_time(_first_value(ent, "P570"))
        cand = {
            "wikidata_id": qid,
            "label": _label_of(ent) or h.get("label", ""),
            "beschreibung": _description_of(ent) or h.get("description", ""),
            "geburtsjahr": geb,
            "todesjahr": tod,
        }
        candidates.append(cand)
        lebens = f"{geb if geb is not None else '?'}–{tod if tod is not None else '?'}"
        print(f"  [{qid}]  {cand['label']}  ({lebens})")
        if cand["beschreibung"]:
            print(f"           {cand['beschreibung']}")

    out_path = os.path.join(config.author_dir(author_slug), "wikidata_candidates.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump({"name": name, "candidates": candidates},
              open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nKandidaten gespeichert: {os.path.relpath(out_path, config.BASE_DIR)}")
    print(f"Bestaetigen mit:  python s110_wikidata.py --author {author_slug} --confirm <Q-ID>")


# ============================================================
# PHASE 2 — BESTAETIGUNG
# ============================================================
def confirm(author_slug: str, qid: str):
    author_path = _author_path(author_slug)
    aj = _read_author(author_path)

    print(f"Hole harte Fakten fuer {qid} ...")
    ent = _api_get({
        "action": "wbgetentities",
        "ids": qid,
        "props": "labels|claims|sitelinks",
        "languages": "|".join(LABEL_LANGS),
    }).get("entities", {}).get(qid)
    if not ent:
        raise LookupError(f"Q-ID {qid} nicht gefunden.")

    geb = _year_from_time(_first_value(ent, "P569"))
    tod = _year_from_time(_first_value(ent, "P570"))

    # P19 (Geburtsort) + P800 (notable works) sind Q-IDs -> Labels aufloesen
    geburtsort_id = None
    p19 = _first_value(ent, "P19")
    if isinstance(p19, dict):
        geburtsort_id = p19.get("id")
    work_ids = _all_ids(ent, "P800")

    label_map = _resolve_labels(([geburtsort_id] if geburtsort_id else []) + work_ids)
    geburtsort = label_map.get(geburtsort_id, "") if geburtsort_id else ""
    notable    = [label_map.get(w, w) for w in work_ids]

    quelle_weich = _wikipedia_url(ent)

    # Wirkungssprache (fuer Namensaussprache in Stage 10): P103 -> P1412 -> P218-Code
    wirkungssprache = _resolve_lang_code(_author_language_qid(ent))

    # --- ins author.json schreiben (harte Fakten autoritativ, da Mensch bestaetigt) ---
    aj["wikidata_id"]  = qid
    aj["verified"]     = True
    aj["geburtsjahr"]  = geb
    aj["todesjahr"]    = tod
    if geschlecht_aus(ent):
        aj["autor_geschlecht"] = geschlecht_aus(ent)   # 19.10.2026: Wikidata P21
    if geburtsort:
        aj["geburtsort"] = geburtsort
    if notable:
        aj["notable_works"] = notable
    if quelle_weich:
        aj["quelle_weich"] = quelle_weich
    # wirkungssprache nur setzen, wenn leer (manuell Eingetragenes nicht ueberschreiben)
    if wirkungssprache and not aj.get("wirkungssprache"):
        aj["wirkungssprache"] = wirkungssprache
    # name_display NICHT ueberschreiben (kuratiert); nur fuellen falls leer
    if not aj.get("name_display"):
        aj["name_display"] = _label_of(ent)

    json_atomar(author_path, aj, indent=2)

    # --- Index pflegen: authors[slug] = Q-ID ---
    idx = config._load_index()
    idx.setdefault("authors", {})[author_slug] = qid
    config._save_index(idx)

    lebens = f"{geb if geb is not None else '?'}–{tod if tod is not None else '?'}"
    print(f"  + verified  {qid}  ({lebens})")
    if geburtsort: print(f"  + geburtsort: {geburtsort}")
    if notable:    print(f"  + notable_works: {', '.join(notable)}")
    if wirkungssprache: print(f"  + wirkungssprache: {wirkungssprache}")
    if quelle_weich: print(f"  + quelle_weich: {quelle_weich}")
    print(f"\nauthor.json aktualisiert + Index: authors[{author_slug}] = {qid}")


def _wikipedia_url(ent: dict) -> str:
    """Bevorzugt Quellsprache-Wikipedia, dann de, dann irgendeine."""
    sitelinks = ent.get("sitelinks", {})
    for lang in LABEL_LANGS:
        key = f"{lang}wiki"
        if key in sitelinks:
            title = sitelinks[key].get("title", "")
            return f"https://{lang}.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
    for key, sl in sitelinks.items():
        if key.endswith("wiki") and not key.endswith("wikiquote"):
            lang = key[:-4]
            title = sl.get("title", "")
            return f"https://{lang}.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
    return ""


# ============================================================
# HILFSFUNKTIONEN
# ============================================================
def _author_path(author_slug: str) -> str:
    return os.path.join(config.author_dir(author_slug), "author.json")

def _read_author(path: str) -> dict:
    if not os.path.exists(path):
        raise FileNotFoundError(f"author.json fehlt: {path} (erst Stage 100)")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# WERK-TITEL — PHASE 1 (VORSCHLAG) + PHASE 2 (BESTAETIGUNG)
# Holt je Zielsprache den etablierten Laendertitel aus Wikidata-Sitelinks;
# fehlt eine Sprache -> Gemini-Fallback (markiert "pruefen").
# ============================================================
_PAREN_SUFFIX = re.compile(r"\s*\([^()]*\)\s*$")   # "Titel (roman)" -> "Titel"

def _strip_paren_suffix(title: str) -> str:
    """Entfernt EINEN abschliessenden Klammer-Zusatz (Wikipedia-Disambiguierung).
    Klammern MITTEN im Titel bleiben erhalten."""
    return _PAREN_SUFFIX.sub("", title or "").strip()


def _book_path(book_slug: str) -> str:
    return os.path.join(config.book_dir(book_slug), "book.json")

def _read_book(book_slug: str) -> dict:
    p = _book_path(book_slug)
    if not os.path.exists(p):
        raise FileNotFoundError(f"book.json fehlt: {p} (erst Stage 100)")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# Stopwoerter (Artikel/Konjunktionen), die fuer den Titel-Abgleich nicht zaehlen.
_TITLE_STOP = {"the", "a", "an", "of", "and", "or", "to", "in", "on",
               "der", "die", "das", "ein", "eine", "und", "von", "zu", "im",
               "le", "la", "les", "du", "de", "et", "l", "el", "los", "y"}

def _title_tokens(s: str) -> set:
    """Normalisiert einen Titel auf eine Menge bedeutungstragender Tokens
    (klein, ohne Satzzeichen, ohne Stopwoerter)."""
    words = re.findall(r"\w+", (s or "").lower(), re.UNICODE)
    return {w for w in words if w and w not in _TITLE_STOP and len(w) > 1}

def _title_overlap(a: str, b: str) -> float:
    """Jaccard-Aehnlichkeit zweier Titel ueber ihre bedeutungstragenden Tokens.
    1.0 = identisch, 0.0 = nichts gemeinsam."""
    ta, tb = _title_tokens(a), _title_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


class WerkUnplausibel(ValueError):
    pass


def _sanity_check_work(qid: str, ent_label: str, titel_original: str, force: bool):
    """Plausibilitaet: heisst die bestaetigte Q-ID ueberhaupt wie das Werk?
    Faengt verwechselte Q-IDs ab (z.B. 'Der Faenger im Roggen' auf Jekyll),
    BEVOR falsche Titel ins book.json wandern. Abbruch ausser bei --force."""
    overlap = _title_overlap(ent_label, titel_original)
    if overlap < 0.34 and not force:
        raise WerkUnplausibel(
            f"\nSTOP: {qid} heisst \"{ent_label}\" — dein titel_original ist "
            f"\"{titel_original}\".\nDie stimmen kaum ueberein (Overlap {overlap:.0%}) "
            f"— vermutlich die FALSCHE Wikidata-Entitaet (Film/anderes Werk?).\n"
            f"Erst mit --propose die richtige Q-ID suchen. Wenn du sicher bist: "
            f"nochmal mit --force.")
    if overlap < 0.34:
        print(f"  WARNUNG: {qid} (\"{ent_label}\") passt kaum zu \"{titel_original}\" "
              f"(Overlap {overlap:.0%}) — wegen --force trotzdem uebernommen.")


def _fallback_title(titel_original: str, lang: str) -> str:
    """Weicher Fallback: Originaltitel per Uebersetzer-Modell in die Zielsprache
    uebertragen. Ergebnis wird IMMER mit titel_pruefen=True markiert (LLM raet bei
    obskuren Titeln). Im Container gesperrt -> Mock liefert Platzhalter."""
    if config.RUN_MODE == "mock":
        return f"[{lang}] {titel_original}"
    from pipeline import api_layer
    name = LANG_NAME.get(lang, lang)
    prompt = (f"Translate the following literary work TITLE into {name}. "
              f"If an established {name} title for this work exists, use it. "
              f"Return ONLY the title text -- no quotes, no notes, no explanation.\n\n"
              f"{titel_original}")
    return (api_layer.call_model("translator", prompt, temperature=0.2) or "").strip()


# Sprachnamen fuer den Fallback-Prompt (englisch, wie in Stage 10/teaser_tts).
LANG_NAME = {"de": "German", "en": "English", "fr": "French",
             "ru": "Russian", "es": "Spanish", "it": "Italian"}


def propose_work(book_slug: str, limit: int = 7):
    bj = _read_book(book_slug)
    titel = (bj.get("titel_original") or "").strip() or book_slug
    src   = bj.get("originalsprache") or config.SOURCE_LANGUAGE

    print(f"Suche Wikidata-Werke fuer: \"{titel}\"\n")
    search = _api_get({
        "action": "wbsearchentities",
        "search": titel,
        "language": src,
        "type": "item",
        "limit": limit,
    })
    hits = search.get("search", [])
    if not hits:
        print("Keine Treffer. titel_original pruefen oder Schreibweise anpassen.")
        return

    ids = [h["id"] for h in hits]
    detail = _api_get({
        "action": "wbgetentities",
        "ids": "|".join(ids),
        "props": "labels|descriptions|claims",
        "languages": "|".join(LABEL_LANGS),
    }).get("entities", {})

    candidates = []
    for h in hits:
        qid = h["id"]
        ent = detail.get(qid, {})
        jahr = _year_from_time(_first_value(ent, "P577"))   # Erscheinungsdatum
        cand = {
            "wikidata_id": qid,
            "label": _label_of(ent) or h.get("label", ""),
            "beschreibung": _description_of(ent) or h.get("description", ""),
            "jahr": jahr,
        }
        candidates.append(cand)
        jstr = f", {jahr}" if jahr is not None else ""
        print(f"  [{qid}]  {cand['label']}{jstr}")
        if cand["beschreibung"]:
            print(f"           {cand['beschreibung']}")

    out_path = os.path.join(config.book_dir(book_slug), "wikidata_work_candidates.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump({"titel_original": titel, "candidates": candidates},
              open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nKandidaten gespeichert: {os.path.relpath(out_path, config.BASE_DIR)}")
    print(f"WICHTIG: den ROMAN waehlen, nicht Film/Oper/Musical.")
    print(f"Bestaetigen mit:  python s110_wikidata.py --work {book_slug} --confirm <Q-ID>")


def _set_fassung_title(bj: dict, lang: str, titel: str, quelle: str, pruefen: bool):
    """Schreibt die Titel-Felder additiv in book.json.fassungen[] (match auf 'sprache').
    Legt den Eintrag an, falls er fehlt; ruehrt formate/status NICHT an."""
    fassungen = bj.setdefault("fassungen", [])
    entry = next((f for f in fassungen if f.get("sprache") == lang), None)
    if entry is None:
        entry = {"sprache": lang}
        fassungen.append(entry)
    entry["titel"]        = titel
    entry["titel_quelle"] = quelle          # wikidata | llm | original
    entry["titel_pruefen"] = pruefen        # True nur beim LLM-Fallback


def confirm_work(book_slug: str, qid: str, force: bool = False, langs=None):
    """Laendertitel je Sprache (langs; Standard: Quellsprache + bestellte Zielsprachen aus book.json)
    und Erscheinungsjahr (P577). Rueckgabe {sprache: titel_quelle}."""
    bj = _read_book(book_slug)
    titel_original = (bj.get("titel_original") or "").strip() or book_slug
    src = bj.get("originalsprache") or config.SOURCE_LANGUAGE

    print(f"Hole Laendertitel fuer {qid} ...")
    ent = _api_get({
        "action": "wbgetentities",
        "ids": qid,
        "props": "labels|sitelinks|claims",
        "languages": "|".join(LABEL_LANGS),
    }).get("entities", {}).get(qid)
    if not ent:
        raise LookupError(f"Q-ID {qid} nicht gefunden.")

    # Plausibilitaet: passt die Entitaet ueberhaupt zum Werk? (faengt verwechselte Q-IDs ab)
    _sanity_check_work(qid, _label_of(ent), titel_original, force)

    sitelinks = ent.get("sitelinks", {})
    from pipeline import bestellung
    bb = bestellung.lesen(config.book_dir(book_slug))
    src = bb.quellsprache                      # nicht config.SOURCE_LANGUAGE (global, werkfremd)
    if langs is None:
        langs = bb.sprachen
    print(f"  Sprachen: {', '.join(langs)} | Quellsprache: {src}")

    quellen = {}
    flagged = 0
    for lang in langs:
        if lang == src:
            _set_fassung_title(bj, lang, titel_original, "original", False)
            quellen[lang] = "original"
            print(f"  + {lang}: \"{titel_original}\"  [original]")
            continue
        sl = sitelinks.get(f"{lang}wiki")
        title = _strip_paren_suffix(sl.get("title", "")) if sl else ""
        if title:
            _set_fassung_title(bj, lang, title, "wikidata", False)
            quellen[lang] = "wikidata"
            print(f"  + {lang}: \"{title}\"  [wikidata]")
        else:
            fb = _fallback_title(titel_original, lang)
            _set_fassung_title(bj, lang, fb, "llm", True)
            quellen[lang] = "llm"
            flagged += 1
            print(f"  + {lang}: \"{fb}\"  [llm -> PRUEFEN]")

    bj["work_wikidata_id"] = qid
    jahr = _year_from_time(_first_value(ent, "P577"))
    if jahr and not bj.get("erscheinungsjahr"):
        bj["erscheinungsjahr"] = jahr          # Befund 100: Gutendex liefert kein Jahr
    json_atomar(_book_path(book_slug), bj, indent=2)

    print(f"\nbook.json aktualisiert: work_wikidata_id={qid}, "
          f"{len(langs)} Fassungs-Titel gesetzt ({flagged} zu pruefen).")
    if flagged:
        print("HINWEIS: 'llm'-Titel mit titel_pruefen=true -> Gate 110 Mensch.")
    return quellen


# ============================================================
# GATE 110 (Phase 2, 01.11.2026) — Kette: Autor + Werk automatisch, Mensch nur bei Unklarheit
# ============================================================
STAGE = "110"
JACCARD = 0.5
PD_JAHRE = 70
TITEL_OK = ("original", "wikidata", "manuell")


def autor_kandidaten(name, limit=7):
    """Wikidata-Personen zum Namen mit Lebensjahren (ein Suchaufruf + ein wbgetentities)."""
    hits = _api_get({"action": "wbsearchentities", "search": name, "language": config.SOURCE_LANGUAGE,
                     "type": "item", "limit": limit}).get("search", [])
    if not hits:
        return []
    detail = _api_get({"action": "wbgetentities", "ids": "|".join(h["id"] for h in hits),
                       "props": "labels|descriptions|claims",
                       "languages": "|".join(LABEL_LANGS)}).get("entities", {})
    out = []
    for h in hits:
        ent = detail.get(h["id"], {})
        out.append({"wikidata_id": h["id"], "label": _label_of(ent) or h.get("label", ""),
                    "beschreibung": _description_of(ent) or h.get("description", ""),
                    "geburtsjahr": _year_from_time(_first_value(ent, "P569")),
                    "todesjahr": _year_from_time(_first_value(ent, "P570"))})
    return out


def _tokens(s):
    return set(re.findall(r"\w+", (s or "").lower(), re.UNICODE))


def autor_treffer(kandidaten, name, todesjahr):
    """Katalog: Namens- und Todesjahr-Treffer (+-1 zu Gutendex)."""
    teile = [t for t in re.findall(r"\w+", (name or "").lower()) if len(t) > 1]
    nach = teile[-1] if teile else ""
    out = []
    for c in kandidaten:
        if not nach or nach not in _tokens(c.get("label")):
            continue
        if todesjahr is None or c.get("todesjahr") is None or abs(int(c["todesjahr"]) - int(todesjahr)) > 1:
            continue
        out.append(c)
    return out


def kandidaten_merken(slug, art, liste):
    """Kandidatenlisten fuer den Monitor 110 (work/110_kandidaten.json, je art autor|werk)."""
    import datetime
    try:
        p = os.path.join(config.work_dir(slug), "110_kandidaten.json")
        d = {}
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        d[art] = liste
        d[art + "_wann"] = datetime.datetime.now().isoformat(timespec="seconds")
        json_atomar(p, d, indent=2)
    except Exception as e:                      # Monitor-Hilfe, nie Gate-relevant
        print(f"    (Kandidatenliste nicht gespeichert: {e})")


def _pd_nachweis(slug):
    """PD-/Rechte-Nachweis, der den Autor deckt (Baustein 100+110, book.json rechte.nachweise)."""
    try:
        from pipeline import bestellung
        from tools import s100_anlegen as S100
        roh = bestellung.lesen(slug).roh
        nw = [n for n in S100.nachweise(roh) if "autor" in (n.get("deckt") or [])]
        return S100.nachweis_text(nw[-1]) if nw else None
    except Exception:
        return None


def _autor_ohne_abfrage(aslug, aj):
    return aslug == "unbekannt" or (aj or {}).get("wikidata_abfrage") is False


def autor_teil(g, aslug, autor_qid=None, neu=False, jahr=None, slug=None):
    """Autor verifizieren (auto bei genau 1 Treffer), PD mit Wikidata-Todesjahr pruefen."""
    import datetime
    jahr = jahr or datetime.date.today().year
    ap = _author_path(aslug)
    try:
        aj = _read_author(ap)
    except (FileNotFoundError, ValueError) as e:
        g.pflicht("author_json", False, wert=str(e), ruecksprung="100", text=f"author.json: {e}")
        return
    if _autor_ohne_abfrage(aslug, aj):
        g.hinweis("autor_abfrage", False, text=f"Autor {aslug!r} ohne Wikidata-Abfrage (wikidata_abfrage=false)")
        return
    tj_gutendex = aj.get("todesjahr")
    if autor_qid:
        confirm(aslug, autor_qid)
        g.metrik("autor_quelle", "manuell")
    elif neu or not (aj.get("verified") and aj.get("wikidata_id")):
        kand = autor_kandidaten(aj.get("name_display") or "")
        treffer = autor_treffer(kand, aj.get("name_display"), tj_gutendex)
        g.metrik("autor_kandidaten", len(kand))
        g.metrik("autor_treffer", len(treffer))
        if slug:
            ids = {c["wikidata_id"] for c in treffer}
            kandidaten_merken(slug, "autor", [dict(c, treffer=c["wikidata_id"] in ids) for c in kand])
        liste = "; ".join(f"{c['wikidata_id']} {c['label']} ({c.get('geburtsjahr') or '?'}–"
                          f"{c.get('todesjahr') or '?'})" for c in kand[:7]) or "keine"
        if len(treffer) != 1:
            g.pflicht("autor_eindeutig", False, wert=len(treffer), bei_fehler="mensch", ruecksprung="110",
                      text=f"Autor {aj.get('name_display')!r} (+{tj_gutendex}): {len(treffer)} Treffer mit Name + "
                           f"Todesjahr ±1 – Kandidaten: {liste}; Regler --autor-qid Q…")
            return
        confirm(aslug, treffer[0]["wikidata_id"])
        g.metrik("autor_quelle", "wikidata_auto")
        g.pflicht("autor_eindeutig", True, wert=1, text=f"Autor eindeutig: {treffer[0]['wikidata_id']}")
    else:
        g.metrik("autor_quelle", "bereits_verifiziert")
    aj = _read_author(ap)
    g.metrik("autor_qid", aj.get("wikidata_id"))
    tj = aj.get("todesjahr")
    nw = _pd_nachweis(slug) if slug else None
    if nw:
        g.pflicht("pd_wikidata", True, wert=tj, text=f"PD Autor per Nachweis: {nw}"
                  + (f" (Wikidata-Todesjahr {tj})" if tj is not None else " (Wikidata ohne Todesjahr)"))
    elif tj is None:
        g.pflicht("pd_wikidata", False, bei_fehler="mensch", ruecksprung="110",
                  text=f"Wikidata {aj.get('wikidata_id')}: kein Todesjahr (P570) – PD-Nachweis im Monitor")
    else:
        g.pflicht("pd_wikidata", int(tj) + PD_JAHRE < jahr, wert=int(tj), ruecksprung="100",
                  text=f"EU-PD (Wikidata): Todesjahr {tj} + {PD_JAHRE} < {jahr}")
        if tj_gutendex is not None and abs(int(tj) - int(tj_gutendex)) > 1:
            g.hinweis("todesjahr_abgleich", False, wert=f"{tj_gutendex}/{tj}",
                      text=f"Todesjahr Gutendex/manuell {tj_gutendex} ≠ Wikidata {tj}")


_EN_FUNKTION = {"the", "of", "and", "a", "an", "in", "on", "to", "from", "with"}


def _gleich_original_markieren(book_slug, titel, langs, src):
    """Wikidata liefert als Zieltitel manchmal den Originaltitel (Lemma) -> LLM-Vorschlag, pruefen."""
    bj = _read_book(book_slug)
    geaendert = False
    for lang in langs:
        if lang == src:
            continue
        f = next((x for x in bj.get("fassungen", []) if x.get("sprache") == lang), None)
        if not f or f.get("titel_quelle") != "wikidata" or (f.get("titel") or "").strip().lower() != titel.strip().lower():
            continue
        if src == "en" and not (_tokens(titel) & _EN_FUNKTION):
            continue
        _set_fassung_title(bj, lang, _fallback_title(titel, lang) or titel, "llm", True)
        geaendert = True
    if geaendert:
        json_atomar(_book_path(book_slug), bj, indent=2)


def werk_teil(g, book_slug, b, werk_qid=None, neu=False, titel=None, jaccard=JACCARD):
    """Werk-Q-ID + Titel je Sprache. Wikidata-Titel -> auto; LLM-Titel / kein Kandidat -> Mensch."""
    langs, src = b.sprachen, b.quellsprache
    titel_original = (b.roh.get("titel_original") or "").strip() or book_slug
    fass = {f.get("sprache"): f for f in b.roh.get("fassungen", []) if isinstance(f, dict)}
    fehlt = [lg for lg in langs if not (fass.get(lg) or {}).get("titel")]
    qid = werk_qid or b.roh.get("work_wikidata_id")
    if werk_qid or neu or fehlt:
        if werk_qid:
            confirm_work(book_slug, werk_qid, force=True, langs=langs)
            g.metrik("werk_quelle", "manuell")
        elif qid and not neu:
            confirm_work(book_slug, qid, force=True, langs=langs)
            _gleich_original_markieren(book_slug, titel_original, langs, src)
            g.metrik("werk_quelle", "vorhanden")
        else:
            from tools import titel_auto
            c, alle = None, {}
            for v in titel_auto._varianten(titel_original):
                kl = titel_auto._kandidaten(v, src)
                for k in kl:
                    alle.setdefault(k["wikidata_id"], dict(k, jaccard=round(max(
                        _title_overlap(k.get("label", ""), t) for t in titel_auto._varianten(titel_original)), 2)))
                c = titel_auto.waehle(kl, titel_original, titel_auto._nachname(b.roh), schwelle=jaccard)
                if c:
                    break
            kandidaten_merken(book_slug, "werk", sorted(alle.values(), key=lambda k: -k["jaccard"]))
            if c:
                ov = max(_title_overlap(c["label"], t) for t in titel_auto._varianten(titel_original))
                g.metrik("werk_jaccard", round(ov, 2))
                confirm_work(book_slug, c["wikidata_id"], force=True, langs=langs)
                _gleich_original_markieren(book_slug, titel_original, langs, src)
                g.metrik("werk_quelle", "wikidata_auto")
            else:
                bj = _read_book(book_slug)
                for lang in langs:
                    if lang == src:
                        _set_fassung_title(bj, lang, titel_original, "original", False)
                    elif not (fass.get(lang) or {}).get("titel") or neu:
                        _set_fassung_title(bj, lang, _fallback_title(titel_original, lang) or titel_original,
                                           "llm", True)
                json_atomar(_book_path(book_slug), bj, indent=2)
                g.metrik("werk_quelle", "kein_kandidat")
                g.pflicht("werk_kandidat", False, bei_fehler="mensch", ruecksprung="110",
                          text=f"kein Wikidata-Werk mit Jaccard ≥ {jaccard} zu {titel_original!r} – "
                               f"Regler --werk-qid Q… oder --titel")
    if titel:
        bj = _read_book(book_slug)
        for lang, t in titel.items():
            _set_fassung_title(bj, lang, t, "manuell", False)
        json_atomar(_book_path(book_slug), bj, indent=2)
    bj = _read_book(book_slug)
    fass = {f.get("sprache"): f for f in bj.get("fassungen", []) if isinstance(f, dict)}
    g.metrik("werk_qid", bj.get("work_wikidata_id") or None)
    qu = {}
    for lang in langs:
        f = fass.get(lang) or {}
        q = f.get("titel_quelle") if f.get("titel") else None
        qu[lang] = q
        g.pflicht(f"titel_{lang}", q in TITEL_OK, wert=q, bei_fehler="mensch", ruecksprung="110",
                  text=f"Titel {lang}: {f.get('titel')!r} [{q or 'fehlt'}]"
                       + ("" if q in TITEL_OK else " – pruefen, Regler --titel " + lang + "=…"))
    g.metrik("titelquelle", qu)


def pruefen(g, slug, b, autor_qid=None, werk_qid=None, titel=None, jaccard=JACCARD, neu=False, jahr=None):
    try:
        autor_teil(g, b.roh.get("author_slug") or config.author_of(slug), autor_qid, neu, jahr, slug=slug)
        werk_teil(g, slug, b, werk_qid, neu, titel, jaccard)
    except (OSError, LookupError, ValueError) as e:
        g.pflicht("abfrage", False, wert=f"{type(e).__name__}: {e}", ruecksprung="110",
                  text=f"Wikidata-Abfrage fehlgeschlagen ({type(e).__name__}: {e}) – neu abfragen (--neu)")


def run(werk, wer=None, autor_qid=None, werk_qid=None, titel=None, jaccard=JACCARD, neu=False, jahr=None,
        nachweis=None):
    """Gate 110 (nur Gutenberg). nachweis = {art, url, quelle, deckt, rechte_art} (Monitor 110).
    Rueckgabe auto | mensch | stopp."""
    from pipeline import bestellung, gate, s080_mandant
    wer = s080_mandant.nutzer(wer)
    if autor_qid or werk_qid or titel or neu or nachweis:
        s080_mandant.darf(werk, "bestellen", wer)
    if nachweis:
        from tools import s100_anlegen as S100
        S100.nachweis_setzen(werk, nachweis.get("art"), wer, nachweis.get("url"), nachweis.get("quelle"),
                             nachweis.get("deckt") or ("autor",), nachweis.get("rechte_art"))
    ordner = bestellung.werkordner(werk)
    slug = os.path.basename(os.path.normpath(ordner))
    b = bestellung.lesen(werk)
    g = gate.Gate(slug, STAGE, ruecksprung="110", wer=wer)
    g.metrik("jaccard_schwelle", jaccard)
    if config.eigene_rechte(slug):
        g.hinweis("eigenes_werk", False, text="eigenes Werk (rechte=eigene) – keine Wikidata-Abfrage")
    else:
        pruefen(g, slug, b, autor_qid, werk_qid, titel, jaccard, neu, jahr)
    e = g.entscheide()
    print(g.bericht())
    return e


# ============================================================
# MOCK (nur RUN_MODE='mock' -- Wikidata im Container gesperrt)
# ============================================================
def _mock_response(params: dict) -> dict:
    action = params.get("action")
    if action == "wbsearchentities":
        s = (params.get("search") or "").lower()
        if "jekyll" in s or "hyde" in s:          # Werk-Suche
            return {"search": [
                {"id": "Q183883", "label": "Strange Case of Dr Jekyll and Mr Hyde",
                 "description": "1886 novella by Robert Louis Stevenson"},
                {"id": "Q580409", "label": "Dr. Jekyll and Mr. Hyde",
                 "description": "1931 film by Rouben Mamoulian"},
            ]}
        return {"search": [                        # Autor-Suche (unveraendert)
            {"id": "Q173746", "label": "Robert Louis Stevenson",
             "description": "Scottish novelist, poet, and travel writer"},
            {"id": "Q9999999", "label": "Robert Stevenson",
             "description": "Scottish civil engineer"},
        ]}
    if action == "wbgetentities":
        ids = params.get("ids", "").split("|")
        ents = {}
        for qid in ids:
            ents[qid] = _MOCK_ENTITIES.get(qid, {"labels": {}, "claims": {}, "sitelinks": {}})
        return {"entities": ents}
    return {}

_MOCK_ENTITIES = {
    "Q173746": {
        "labels": {"en": {"value": "Robert Louis Stevenson"}},
        "descriptions": {"en": {"value": "Scottish novelist, poet, and travel writer"}},
        "claims": {
            "P569": [{"mainsnak": {"datavalue": {"value": {"time": "+1850-11-13T00:00:00Z"}}}}],
            "P570": [{"mainsnak": {"datavalue": {"value": {"time": "+1894-12-03T00:00:00Z"}}}}],
            "P19":  [{"mainsnak": {"datavalue": {"value": {"id": "Q23436"}}}}],
            "P103": [{"mainsnak": {"datavalue": {"value": {"id": "Q1860"}}}}],
            "P800": [{"mainsnak": {"datavalue": {"value": {"id": "Q183883"}}}},
                     {"mainsnak": {"datavalue": {"value": {"id": "Q174596"}}}}],
        },
        "sitelinks": {
            "enwiki": {"title": "Robert Louis Stevenson"},
            "dewiki": {"title": "Robert Louis Stevenson"},
        },
    },
    "Q9999999": {
        "labels": {"en": {"value": "Robert Stevenson"}},
        "descriptions": {"en": {"value": "Scottish civil engineer"}},
        "claims": {
            "P569": [{"mainsnak": {"datavalue": {"value": {"time": "+1772-06-08T00:00:00Z"}}}}],
            "P570": [{"mainsnak": {"datavalue": {"value": {"time": "+1850-07-12T00:00:00Z"}}}}],
        },
    },
    "Q23436":  {"labels": {"en": {"value": "Edinburgh"}}},
    "Q183883": {"labels": {"en": {"value": "Strange Case of Dr Jekyll and Mr Hyde"}},
                "descriptions": {"en": {"value": "1886 novella by Robert Louis Stevenson"}},
                "claims": {
                    "P577": [{"mainsnak": {"datavalue": {"value": {"time": "+1886-01-05T00:00:00Z"}}}}],
                },
                "sitelinks": {
                    "enwiki": {"title": "Strange Case of Dr Jekyll and Mr Hyde"},
                    "dewiki": {"title": "Der seltsame Fall des Dr. Jekyll und Mr. Hyde"},
                    "frwiki": {"title": "L'Étrange Cas du docteur Jekyll et de M. Hyde"},
                }},
    "Q580409": {"labels": {"en": {"value": "Dr. Jekyll and Mr. Hyde"}},
                "descriptions": {"en": {"value": "1931 film by Rouben Mamoulian"}},
                "claims": {
                    "P577": [{"mainsnak": {"datavalue": {"value": {"time": "+1931-12-31T00:00:00Z"}}}}],
                }},
    "Q174596": {"labels": {"en": {"value": "Treasure Island"}}},
    "Q1860":   {"labels": {"en": {"value": "English"}},
                "claims": {"P218": [{"mainsnak": {"datavalue": {"value": "en"}}}]}},
}


# ============================================================
# CLI
# ============================================================
def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 110 Wikidata (Autor + Werktitel)")
    ap.add_argument("werk", nargs="?", help="Book-ID/Werkordner (Gate 110)")
    ap.add_argument("--wer")
    ap.add_argument("--autor-qid")
    ap.add_argument("--werk-qid")
    ap.add_argument("--titel", action="append", default=[], metavar="LG=TITEL",
                    help="Titel je Sprache ueberschreiben, z. B. de=\"Der Ruf der Wildnis\"")
    ap.add_argument("--jaccard", type=float, default=JACCARD)
    ap.add_argument("--neu", action="store_true", help="Neu abfragen (auch bei verifiziertem Autor/Titeln)")
    ap.add_argument("--pd-url", help="Nachweis: PD-Beleg-URL")
    ap.add_argument("--rechteinhaber", nargs="?", const="eigene", choices=("eigene", "lizenz"))
    ap.add_argument("--pd-quelle", help="Nachweis: PD ueber andere Quelle")
    ap.add_argument("--deckt", default="autor", help="Nachweis deckt: autor,uebersetzer")
    ap.add_argument("--author", help="Altweg: autor-slug")
    ap.add_argument("--work", help="Altweg: book-slug")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--propose", action="store_true")
    g.add_argument("--confirm", metavar="Q-ID")
    ap.add_argument("--limit", type=int, default=7)
    ap.add_argument("--force", action="store_true", help="Altweg: Werk-Confirm trotz Titel-Abweichung")
    args = ap.parse_args(argv)

    if config.RUN_MODE == "mock":
        print(">>> RUN_MODE=mock — feste Beispieldaten, keine echte Wikidata-Abfrage.\n")
    if args.werk:
        from pipeline import gate
        titel = {}
        for t in args.titel:
            lg, _, v = t.partition("=")
            if not v.strip():
                ap.error(f"--titel {t!r}: Form LG=TITEL")
            titel[lg.strip().lower()] = v.strip()
        nachweis = None
        if args.rechteinhaber or args.pd_quelle or args.pd_url:
            nachweis = {"art": "rechteinhaber" if args.rechteinhaber else ("andere_quelle" if args.pd_quelle else "url"),
                        "url": args.pd_url, "quelle": args.pd_quelle, "rechte_art": args.rechteinhaber,
                        "deckt": [x.strip() for x in (args.deckt or "").split(",") if x.strip()]}
        try:
            return gate.EXIT[run(args.werk, args.wer, args.autor_qid, args.werk_qid, titel or None,
                                 args.jaccard, args.neu, nachweis=nachweis)]
        except (ValueError, PermissionError) as e:
            print(f"! {e}")
            return 2
    if not (args.author or args.work) or not (args.propose or args.confirm):
        ap.error("werk oder --author/--work mit --propose/--confirm")
    if args.work and config.eigene_rechte(args.work):
        print(f"[110] '{args.work}' ist ein eigenes Werk (book.json rechte=eigene) -> keine Wikidata-Abfrage.")
        return 0
    if args.author:
        try:
            aj = _read_author(_author_path(args.author))
        except (OSError, ValueError):
            aj = {}
        if _autor_ohne_abfrage(args.author, aj):
            print(f"[110] Autor '{args.author}' ohne Wikidata-Abfrage (wikidata_abfrage=false).")
            return 0
    if args.work:
        if args.propose:
            propose_work(args.work, limit=args.limit)
        else:
            confirm_work(args.work, args.confirm, force=args.force)
    elif args.propose:
        propose(args.author, limit=args.limit)
    else:
        confirm(args.author, args.confirm)
    return 0


if __name__ == "__main__":
    sys.exit(main())
