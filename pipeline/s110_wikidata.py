"""STAGE 110 — Wikidata
Funktion:     Verifizierte Autor-Fakten und Werktitel je Zielsprache.
Wirkungsweise: Zweiphasig --propose/--confirm (Mensch waehlt Q-ID); Titel aus Sitelinks, sonst DeepSeek-Fallback mit titel_pruefen.
Komponenten:  pipeline/s110_wikidata.py, tools/titel_auto.py (Cockpit), api_layer (Fallback)
Zulieferer:   s100 Anlegen (book.json)
Abnehmer:     s600 Klappentext (author.json), s620/s630 ePub (Titel), s710 Cloud-Export (Katalog)
(Nomenklatur seit 18.10.2026, Uebersicht: docs/Pipeline_Strang_Matrix.xlsx)

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
        sys.exit(f"author.json hat kein name_display ({author_path}).")

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
        sys.exit(f"Q-ID {qid} nicht gefunden.")

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

    json.dump(aj, open(author_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

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
        sys.exit(f"author.json fehlt: {path}\n"
                 f"Erst anlegen.py laufen lassen (Autor-Skelett).")
    return json.load(open(path, encoding="utf-8"))


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
        sys.exit(f"book.json fehlt: {p}\nErst anlegen.py laufen lassen (Werk-Skelett).")
    return json.load(open(p, encoding="utf-8"))


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


def _sanity_check_work(qid: str, ent_label: str, titel_original: str, force: bool):
    """Plausibilitaet: heisst die bestaetigte Q-ID ueberhaupt wie das Werk?
    Faengt verwechselte Q-IDs ab (z.B. 'Der Faenger im Roggen' auf Jekyll),
    BEVOR falsche Titel ins book.json wandern. Abbruch ausser bei --force."""
    overlap = _title_overlap(ent_label, titel_original)
    if overlap < 0.34 and not force:
        sys.exit(
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


def confirm_work(book_slug: str, qid: str, force: bool = False):
    bj = _read_book(book_slug)
    titel_original = (bj.get("titel_original") or "").strip() or book_slug
    src = bj.get("originalsprache") or config.SOURCE_LANGUAGE

    print(f"Hole Laendertitel fuer {qid} ...")
    ent = _api_get({
        "action": "wbgetentities",
        "ids": qid,
        "props": "labels|sitelinks",
        "languages": "|".join(LABEL_LANGS),
    }).get("entities", {}).get(qid)
    if not ent:
        sys.exit(f"Q-ID {qid} nicht gefunden.")

    # Plausibilitaet: passt die Entitaet ueberhaupt zum Werk? (faengt verwechselte Q-IDs ab)
    _sanity_check_work(qid, _label_of(ent), titel_original, force)

    sitelinks = ent.get("sitelinks", {})
    langs = config.ALL_LANGUAGES
    print(f"  Zielsprachen (config.ALL_LANGUAGES): {', '.join(langs)} | Quellsprache: {src}")

    flagged = 0
    for lang in langs:
        if lang == src:
            _set_fassung_title(bj, lang, titel_original, "original", False)
            print(f"  + {lang}: \"{titel_original}\"  [original]")
            continue
        sl = sitelinks.get(f"{lang}wiki")
        title = _strip_paren_suffix(sl.get("title", "")) if sl else ""
        if title:
            _set_fassung_title(bj, lang, title, "wikidata", False)
            print(f"  + {lang}: \"{title}\"  [wikidata]")
        else:
            fb = _fallback_title(titel_original, lang)
            _set_fassung_title(bj, lang, fb, "llm", True)
            flagged += 1
            print(f"  + {lang}: \"{fb}\"  [llm -> PRUEFEN]")

    bj["work_wikidata_id"] = qid
    json.dump(bj, open(_book_path(book_slug), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    print(f"\nbook.json aktualisiert: work_wikidata_id={qid}, "
          f"{len(langs)} Fassungs-Titel gesetzt ({flagged} zu pruefen).")
    if flagged:
        print("HINWEIS: 'llm'-Titel mit titel_pruefen=true beim Cover-Review kontrollieren.")


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
def main():
    ap = argparse.ArgumentParser(description="Stage 08b — Wikidata-Anreicherung (Autor + Werk-Titel)")
    target = ap.add_mutually_exclusive_group(required=True)
    target.add_argument("--author", help="autor-slug (Ordner unter authors/)")
    target.add_argument("--work",   help="book-slug (Werk-Titel je Fassung holen)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--propose", action="store_true", help="Phase 1: Kandidaten vorschlagen")
    g.add_argument("--confirm", metavar="Q-ID", help="Phase 2: Q-ID bestaetigen + schreiben")
    ap.add_argument("--limit", type=int, default=7, help="Anzahl Kandidaten (Phase 1)")
    ap.add_argument("--force", action="store_true",
                    help="Werk-Confirm trotz Titel-Abweichung erzwingen (Sanity-Check umgehen)")
    args = ap.parse_args()

    if config.RUN_MODE == "mock":
        print(">>> RUN_MODE=mock — feste Beispieldaten, keine echte Wikidata-Abfrage.\n")

    # 22.10.2026: eigene Werke / Autor "unbekannt" -> keine Wikidata-Abfrage (CK)
    if args.work and config.eigene_rechte(args.work):
        print(f"[110] '{args.work}' ist ein eigenes Werk (book.json rechte=eigene) -> keine Wikidata-Abfrage.")
        return
    if args.author:
        _ap = os.path.join(config.author_dir(args.author), "author.json")
        try:
            _abfrage = json.load(open(_ap, encoding="utf-8")).get("wikidata_abfrage", True)
        except (OSError, ValueError):
            _abfrage = True
        if args.author == "unbekannt" or _abfrage is False:
            print(f"[110] Autor '{args.author}' ohne Wikidata-Abfrage (wikidata_abfrage=false).")
            return

    if args.work:
        if args.propose: propose_work(args.work, limit=args.limit)
        else:            confirm_work(args.work, args.confirm, force=args.force)
    else:
        if args.propose: propose(args.author, limit=args.limit)
        else:            confirm(args.author, args.confirm)


if __name__ == "__main__":
    main()
