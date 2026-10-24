"""
READ LAYER — Zentrale Konfiguration
====================================
Alle Parameter, die sich pro Titel, pro Sprache oder pro Lauf aendern,
stehen HIER — niemals hartcodiert in den Modulen.

Von 4 auf 7 Sprachen zu gehen ist eine Aenderung in dieser Datei,
kein Code-Umbau.
"""

import os

# .env-Datei laden (falls vorhanden), damit API-Keys nicht im Code stehen.
# Die .env liegt im Projekt-Wurzelverzeichnis (neben run.py).
try:
    from dotenv import load_dotenv
    _here = os.path.dirname(os.path.abspath(__file__))
    _root = os.path.dirname(_here)
    load_dotenv(os.path.join(_root, ".env"))
except ImportError:
    # python-dotenv nicht installiert -> Keys muessen als Umgebungsvariablen gesetzt sein
    pass

# ============================================================
# PFADE  (AUTOR-ZENTRIERT)
# ============================================================
# Basis ist das readlayer-Wurzelverzeichnis (ein Level ueber config/)
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Struktur: authors/<autor-slug>/books/<book-slug>/{raw.txt, work/, output/}
#   - Autor = eigene Entitaet (author.json), Werke liegen DARUNTER.
#   - Autor-Ordner = lesbarer Slug (wells-hg); Wikidata-Q-ID nur als Feld in author.json.
#   - index.json (Root) bildet ab: book_slug -> autor_slug  UND  autor_slug -> Q-ID.
# Vorteil: Autor/Werk-Beziehung sauber, App-Suche (alle Werke eines Autors) trivial,
#   Fehler pro Buch analysierbar, Buch/Autor loeschen = ein Ordner.
AUTHORS_DIR = os.path.join(BASE_DIR, "authors")
INDEX_PATH  = os.path.join(BASE_DIR, "daten", "index.json")
LOCAL_TTS_DIR = os.path.join(BASE_DIR, "models")

# OUTPUT_DIR bleibt als Name erhalten (run.py referenziert ihn).
OUTPUT_DIR = AUTHORS_DIR


# ---- Index-Map (zentrale Aufloesung) ------------------------------------
import json as _json

def _load_index() -> dict:
    """index.json laden. Struktur:
       {"books": {"<book_slug>": "<autor_slug>"},
        "authors": {"<autor_slug>": "<Q-ID>"}}"""
    if os.path.exists(INDEX_PATH):
        try:
            return _json.load(open(INDEX_PATH, encoding="utf-8"))
        except Exception:
            pass
    return {"books": {}, "authors": {}}

def _save_index(idx: dict) -> None:
    os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
    _json.dump(idx, open(INDEX_PATH, "w", encoding="utf-8"),
               ensure_ascii=False, indent=2)

def author_of(book_id: str) -> str:
    """Liefert den autor_slug zu einem book_slug (aus dem Index)."""
    idx = _load_index()
    a = idx.get("books", {}).get(book_id)
    if not a:
        raise KeyError(
            f"Buch '{book_id}' nicht im Index (index.json). "
            f"Erst anlegen (Anlege-Logik / Stage 08b).")
    return a

def author_dir(author_slug: str) -> str:
    """Wurzelordner eines Autors: authors/<autor-slug>/"""
    return os.path.join(AUTHORS_DIR, author_slug)

USERS_DIR = os.path.join(BASE_DIR, "users")   # private Uploads (TAELLA-User), nie im Katalog

def is_private(book_id: str) -> bool:
    """Privater User-Upload? Index-Eintrag 'user:<uid>' statt autor_slug."""
    try:
        return author_of(book_id).startswith("user:")
    except KeyError:
        return False

def book_dir(book_id: str) -> str:
    """Wurzelordner eines Buchs: authors/<autor>/books/<book_id>/
    Autor wird ueber den Index aufgeloest -> Stages brauchen nur book_id.
    Private Uploads (Index 'user:<uid>') liegen unter users/<uid>/works/<book_id>/ (17.10.2026).
    Sprachweiche (22.10.2026): wer den Werkordner aufloest, bekommt die Sprachrichtung des Werks
    (book.json "originalsprache") in SOURCE_LANGUAGE/TARGET_LANGUAGES gesetzt."""
    a = author_of(book_id)
    if a.startswith("user:"):
        pfad = os.path.join(USERS_DIR, a[5:], "works", book_id)
    else:
        pfad = os.path.join(author_dir(a), "books", book_id)
    _werk_sprachen_setzen(book_id, pfad)
    return pfad


# ---- Slug-Bildung -------------------------------------------------------
import re as _re, unicodedata as _ud

def slugify(text: str) -> str:
    """Kleinschreibung, Umlaute/Akzente -> ASCII, nur a-z0-9-, Bindestriche."""
    t = text.strip().lower()
    # deutsche Umlaute bewusst lesbar
    t = (t.replace("ä","ae").replace("ö","oe").replace("ü","ue")
           .replace("ß","ss"))
    # restliche Akzente entfernen (e' -> e)
    t = "".join(c for c in _ud.normalize("NFKD", t) if not _ud.combining(c))
    t = _re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t or "unbekannt"

def suggest_author_slug(name_display: str) -> str:
    """Vorschlag: 'H. G. Wells' -> 'wells-hg'. Bei 'Charles Dickens' -> 'dickens-c'.
    NUR Vorschlag -- die Anlege-Logik laesst Ueberschreiben zu."""
    parts = [p for p in _re.split(r"\s+", name_display.strip()) if p]
    if not parts:
        return "unbekannt"
    nachname = parts[-1]
    initialen = "".join(p[0] for p in parts[:-1] if p and p[0].isalpha())
    base = slugify(nachname)
    if initialen:
        base = f"{base}-{slugify(initialen)}"
    return base

def unique_author_slug(name_display: str) -> str:
    """Eindeutiger Slug-Vorschlag (haengt bei Kollision -2, -3 ... an).
    Kollision = Slug existiert im Index, zeigt aber auf ANDERE Q-ID."""
    base = suggest_author_slug(name_display)
    idx = _load_index().get("authors", {})
    if base not in idx:
        return base
    n = 2
    while f"{base}-{n}" in idx:
        n += 1
    return f"{base}-{n}" 


# ============================================================
# SPRACHEN
# ============================================================
# Sprachweiche je Werk (CK 22.10.2026): nur EN und DE. Die Originalsprache des Werks
# (book.json "originalsprache") ist die Quelle, die jeweils andere das Ziel.
# Gesetzt wird beim Aufloesen des Werkordners (book_dir); ohne Werk gilt EN -> DE.
WERK_SPRACHPAARE = {"en": ["de"], "de": ["en"]}
SOURCE_LANGUAGE = "en"                        # Ausgangssprache des aktuellen Titels
TARGET_LANGUAGES = ["de"]   # Zielsprachen
# Alle Sprachen, die im JSON gefuehrt werden (Quelle + Ziele):
ALL_LANGUAGES = [SOURCE_LANGUAGE] + TARGET_LANGUAGES
_WERK_SPRACHEN_CACHE = {}

def _werk_sprachen_setzen(book_id, pfad):
    """Setzt SOURCE_LANGUAGE/TARGET_LANGUAGES/ALL_LANGUAGES aus book.json des Werks."""
    global SOURCE_LANGUAGE, TARGET_LANGUAGES, ALL_LANGUAGES
    src = _WERK_SPRACHEN_CACHE.get(book_id)
    if src is None:
        src = "en"
        try:
            with open(os.path.join(pfad, "book.json"), encoding="utf-8") as f:
                o = (_json.load(f).get("originalsprache") or "en").split("-")[0].lower()
            if o in WERK_SPRACHPAARE:
                src = o
        except (OSError, ValueError):
            pass
        _WERK_SPRACHEN_CACHE[book_id] = src
    SOURCE_LANGUAGE = src
    TARGET_LANGUAGES = list(WERK_SPRACHPAARE[src])
    ALL_LANGUAGES = [SOURCE_LANGUAGE] + TARGET_LANGUAGES

def werk_sprachen(book_id):
    """(quelle, [ziele]) eines Werks; setzt sie zugleich als aktuelle Sprachen."""
    book_dir(book_id)
    return SOURCE_LANGUAGE, list(TARGET_LANGUAGES)

def align_keys():
    """Schluessel im Wort-Alignment (340): Quell-Span, Ziel-Fragment, Ziel-Span.
    EN-Werk: en_span, de, de_span (wie bisher) - DE-Werk: de_span, en, en_span."""
    tgt = TARGET_LANGUAGES[0]
    return f"{SOURCE_LANGUAGE}_span", tgt, f"{tgt}_span"


# Rechte je Werk (CK 22.10.2026): book.json "rechte" = "gemeinfrei" (Default, fehlt das Feld)
# oder "eigene" (eigenes Werk: keine PD-/Todesjahr-Pruefung, keine Wikidata-Abfrage,
# Impressum "Alle Rechte vorbehalten" statt Gemeinfreiheit).
def werk_rechte(book_id):
    """'eigene' | 'gemeinfrei' aus book.json des Werks."""
    try:
        with open(os.path.join(book_dir(book_id), "book.json"), encoding="utf-8") as f:
            r = (_json.load(f).get("rechte") or "gemeinfrei").strip().lower()
    except (OSError, ValueError, KeyError):
        r = "gemeinfrei"
    return "eigene" if r.startswith("eigen") else "gemeinfrei"

def eigene_rechte(book_id):
    return werk_rechte(book_id) == "eigene"


# ============================================================
# MODELL-ROUTING
# ============================================================
# Welches Modell fuer welche Aufgabe. Austauschbar ohne Code-Aenderung.
# CK 12.10.2026: Gemini nur noch fuer Bild und TTS (inkl. Voice Design); alle Textaufgaben auf DeepSeek.
DEEPSEEK_MAX_OUT = 64000   # Obergrenze max_tokens fuer DeepSeek (17.10.2026: 16000 schnitt das Profil von Peter Pan ab; v4 erlaubt bis 384k)
MODELS = {
    "tagger":        "deepseek-v4-flash",      # Stage 50: Segmentierung (12.10.2026, vorher gemini-2.5-flash-lite)
    "profiler":      "deepseek-v4-pro",        # Stage 51: Buch-Profil (12.10.2026, vorher gemini-2.5-pro)
    "pretranslator": "deepseek-v4-pro",        # Stage 02: Kontext-Vooruebersetzung
    "translator":    "deepseek-v4-pro",        # Stage 03: Satzgenaue Uebersetzung
    "validator":     "deepseek-v4-flash",      # Stage 55: Pruefung (12.10.2026, vorher gemini-2.5-flash = Kostenfalle durch Denk-Token)
    "ssml":          "deepseek-v4-flash",      # Stage 56: Audio-Regie (12.10.2026, vorher gemini-2.5-flash)
    "tts":           "gemini-3.8-flash-tts",   # Stage 40/58: Sprachsynthese (08.10.2026, vorher gemini-2.5-pro-tts)
                                               # Alternative billiger: "gemini-3.8-flash-lite-tts"
    "aligner":       "deepseek-v4-flash",      # Stage 54a: Wort/Phrasen-Alignment (reasoning-frei, robustes JSON)
}

# TTS-Backend (pipeline/tts_client.py):
#   "gemini_api" = Gemini-API / Interactions-Endpoint, Key GEMINI_API_KEY.
#                  PFLICHT fuer gemini-3.8-*-tts (gibt es NICHT in Cloud Text-to-Speech).
#                  Steuerung: wortgetreuer Text + KURZER style (speech_metadata).
#   "cloud_tts"  = alter Weg (Cloud Text-to-Speech, Service-Account) -- nur fuer
#                  gemini-2.5-*-tts / gemini-3.1-flash-tts-preview. Zum Zurueckschalten
#                  BEIDES aendern: TTS_BACKEND = "cloud_tts" und MODELS["tts"] = "gemini-2.5-pro-tts".
TTS_BACKEND = "gemini_api"

# Sprache festigen (12.10.2026, CK: Erzaehlerin kippte in Alice DE ins Franzoesische/Englische).
# Wird jedem Gemini-TTS-Aufruf der Sprache als style vorangestellt (kurz halten).
TTS_SPRACH_STIL = {
    "de": "Native German speaker, standard German (Hochdeutsch) pronunciation throughout.",
    "en": "Native British English speaker.",
}

# DE-Stimme fuer Stage 58, wenn KEINE LibriVox-Aufnahme die Fassung liefert (10.10.2026):
#   "thorsten"    = lokal, Piper de_DE-thorsten-high (s501_vertonung_thorsten), gratis, limitfrei
#   "gemini"      = Gemini-TTS (s500_vertonung_gemini), dramatisiert, kostet
#   spaeter: "kartoffelbox" (Chatterbox-Finetune, MIT) -- noch nicht eingerichtet
TTS_ENGINE_DE = "thorsten"
# Chatterbox-LoRA je Sprache (CK 18.10.2026): mix_v1 = Standard fuer Deutsch (Single Speaker + Erzaehler).
# book.json "tts_lora" uebersteuert je Werk ("aus" = ohne Adapter).
TTS_LORA = {"de": "mix_v1"}

# Preise fuer den Kostenzaehler (pipeline/usage_log.py), USD je 1 Mio. Token.
# DeepSeek: Spitzenpreise (Nebenzeit rechnet usage_log automatisch zum halben Preis), Stand 10.10.2026.
# Gemini: Developer-API-Preisliste laut CK, Stand 10.10.2026. "ab" = Preiswechsel zum Datum,
# "gross" = Aufschlag ab Schwelle Eingabe-Token je Aufruf. Fehlt ein Modell, werden nur Token gezaehlt.
PREISE = {
    "deepseek-v4-pro":       {"in": 1.32, "cache": 0.044, "out": 3.96},
    "deepseek-v4-flash":     {"in": 0.30, "cache": 0.006, "out": 1.20},
    "deepseek-flash":        {"in": 0.30, "cache": 0.006, "out": 1.20},
    "gemini-2.5-pro":        {"in": 1.25, "out": 10.00,
                              "gross": {"schwelle": 200000, "in": 2.50, "out": 15.00}},
    "gemini-2.5-flash":      {"in": 0.30, "out": 2.50},      # Audio-Eingabe 1,00 (nicht genutzt)
    "gemini-2.5-flash-lite": {"in": 0.10, "out": 0.40},      # Audio-Eingabe 0,30 (nicht genutzt)
    "gemini-3.8-flash":      {"in": 0.375, "out": 1.875, "ab": {"2027-01-01": {"in": 0.75, "out": 3.75}}},
    "gemini-3.7-flash":      {"in": 0.375, "out": 1.875, "ab": {"2027-01-01": {"in": 0.75, "out": 3.75}}},
    "gemini-3.6-flash":      {"in": 1.35, "out": 6.75, "ab": {"2027-01-01": {"in": 2.70, "out": 13.50}}},
    # Bildausgabe: 30 $ je 1 Mio. Ausgabe-Token = 0,034-0,050 $ je 1K-Bild (1.120-2.000 Token),
    # bestaetigt durch Preisliste 10.10.2026. Fehlgeschlagene/blockierte Anfragen kosten nichts.
    "gemini-2.5-flash-image":{"in": 0.30, "out": 30.00},
    # TTS (Einfuehrungspreis bis 31.12.2026, danach doppelt): 25 Audio-Token/s -> ca. 0,81 $ je Audiostunde
    "gemini-3.8-flash-tts":  {"in": 0.50, "out": 9.00, "ab": {"2027-01-01": {"in": 1.00, "out": 18.00}}},
}

# Ueberlauf (08.10.2026): Ist Googles Tageskontingent leer (Tier 1: 100 Abrufe/Tag
# fuer gemini-3.8-flash-tts), schaltet tts_client fuer den Rest des Laufs auf fal.ai
# um -- gleiches Modell, gleiche Stimmen, aber ca. 3x teurer ($0.045 / 1000 Zeichen).
# "" = kein Ueberlauf (Lauf bricht dann sauber ab).
TTS_OVERFLOW = "fal"

# Blockgroesse fuer Stage 58 (Saetze pro TTS-Abruf). Groesser = weniger Abrufe.
# Vorher 6/8/10. Neu groesser wegen 100-Abrufe-Grenze; an c004 testen.
TTS_BLOCK_MIN, TTS_BLOCK_IDEAL, TTS_BLOCK_MAX = 15, 20, 25

# TTS-Stimme (eine der 30 Gemini-Stimmen, z.B. Kore, Puck, Charon, Zephyr)
TTS_VOICE = "Charon"

# Drosselung zwischen TTS-Calls (Sekunden), um Rate-Limits zu vermeiden.
# Preview-TTS-Modelle haben enge Limits. Bei "quota exceeded" erhoehen.
TTS_DELAY_SECONDS = 6


# ============================================================
# QUALITAETS-SCHWELLEN
# ============================================================
VALIDATION_THRESHOLD = 90   # Mindest-Score (0-100) bei Rueckuebersetzung
FLAG_MAX_ANTEIL      = 0.03  # QF-6: max. Anteil Saetze unter Schwelle (Stage 55), sonst Stopp vor 56
# QF-6: Pruefstopps (54 -> vor 55, 55 -> vor 56) uebergehen mit Umgebungsvariable READLAYER_WEITER=1
MAX_REWORK_PASSES    = 2     # Wie oft ein durchgefallener Chunk nachbearbeitet wird


# ============================================================
# TAG-SCHEMA
# ============================================================
# Format: c<NNN>_<prefix><NNNNN>  — reines ASCII, sortierbar, lesbar
CHAPTER_DIGITS  = 3   # c001 .. c999
SEQUENCE_DIGITS = 5   # 00001 .. 99999

# Gueltige Tag-Typen und ihre Praefixe
TAG_TYPES = {
    "s":    "s",     # narrative sentence (default)
    "h":    "h",     # chapter heading / section title
    "dl":   "dl",    # dialog line (standalone quote)
    "qt":   "qt",    # block quotation, inscription, sign
    "p":    "p",     # paragraph break (no audio, text = "")
    "fn":   "fn",    # footnote
    "ep":   "ep",    # epigraph
    "tt":   "tt",    # title page element
    "skip": "skip",  # decorative separators, page numbers (no audio)
}
# Typen ohne Audio (werden im TTS-Schritt uebersprungen)
NO_AUDIO_TYPES = ["p", "tt", "skip"]


# ============================================================
# PAUSEN-DRAMATURGIE (Audio-Regie)
# ============================================================
# Dramaturgische Stille NACH einem Tag, in Millisekunden.
# Gehoert NICHT ins Audio selbst (Schnipsel bleiben wortgenau geschnitten),
# sondern ins Manifest — der Player/Zusammenbau fuegt die Stille ein.
# So bleibt maximale Granularitaet fuers Alignment UND steuerbare Dramaturgie.
PAUSE_AFTER_MS = {
    "h":    900,   # nach Ueberschrift: laenger, Erwartung aufbauen
    "s":    350,   # normaler Satz: kurzer Atemzug
    "dl":   450,   # nach Dialogzeile: etwas mehr Raum
    "qt":   600,   # nach Zitat/Inschrift: wirken lassen
    "ep":   700,   # nach Epigraph
    "fn":   300,   # Fussnote
    "p":    800,   # Absatzgrenze: deutliche Pause (kein Audio, nur Stille)
    "tt":   500,   # Titelseite
    "skip": 0,     # kein Audio, keine Pause
}
# Satzende-Verfeinerung: zusaetzliche ms je nach Schluss-Satzzeichen
PAUSE_BY_PUNCTUATION = {
    ".": 0,    # Standard (bereits im Typ-Wert enthalten)
    "!": 150,  # Ausruf: etwas nachklingen
    "?": 200,  # Frage: laenger offen lassen
    ":": -100, # Doppelpunkt leitet weiter -> kuerzer
    ";": -50,
    ",": -150, # haengt weiter -> deutlich kuerzer
}


# ============================================================
# MARKUP-KONVENTION (manuelle Vorbereitung)
# ============================================================
MARKERS = {
    "title":    "###TITLE###",
    "author":   "###AUTHOR###",
    "chapter":  "###CHAPTER###",
    "footnote": "###FOOTNOTE###",
    "epigraph": "###EPIGRAPH###",
}


# ============================================================
# COVER / DARSTELLUNG
# ============================================================
# Eine Quelle fuer die Cover-Hintergrundfarbe: Bild-Hintergrund (Stage 21),
# Fallback-Flaeche und Lesbarkeits-Schleier (Stage 30) lesen ALLE hieraus.
COVER_BG = "#faf8f4"   # warmes Weiss -- Source of Truth fuer Bild, Fallback, Schleier


# ============================================================
# LAUF-MODUS
# ============================================================
# "mock"  = simulierte API-Antworten (kein Key noetig, kein Kosten, schnelle Tests)
# "live"  = echte API-Calls (Keys noetig, kostet Geld, echte Qualitaet)
RUN_MODE = "live"

# API-Keys werden NUR im live-Modus gelesen (aus Umgebungsvariablen / .env)
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
GEMINI_API_KEY   = os.environ.get("GEMINI_API_KEY", "").strip()
OPENROUTER_API_KEY = (os.environ.get("OPENROUTER_API_KEY") or os.environ.get("open_router") or "").strip()   # Modelltests: MODELS-Eintrag "or/<anbieter>/<modell>"
FAL_KEY          = (os.environ.get("FAL_KEY") or os.environ.get("FAL.AI_API_KEY") or "").strip()
GCS_BUCKET       = os.environ.get("GCS_BUCKET", "readlayer-taella-content").strip()


# ============================================================
# HILFSFUNKTIONEN
# ============================================================
def _ensure(d: str) -> str:
    """Ordner anlegen, falls noch nicht vorhanden; Pfad zurueckgeben."""
    os.makedirs(d, exist_ok=True)
    return d

def work_dir(book_id: str) -> str:
    """Zwischenstand-Ordner eines Buchs: books/<book_id>/work/"""
    return _ensure(os.path.join(book_dir(book_id), "work"))

def output_dir(book_id: str) -> str:
    """Ausgabe-Ordner eines Buchs: books/<book_id>/output/"""
    return _ensure(os.path.join(book_dir(book_id), "output"))

def work_path(book_id: str, stage: str) -> str:
    """Pfad fuer einen Zwischenstand: books/<book_id>/work/<stage>.json
    (Signatur unveraendert -> Stages muessen nicht angepasst werden.)"""
    return os.path.join(work_dir(book_id), f"{stage}.json")

def output_path(book_id: str, suffix: str = "final.json") -> str:
    """Pfad fuer finale Auslieferung: books/<book_id>/output/<suffix>"""
    return os.path.join(output_dir(book_id), suffix)

def raw_path(book_id: str, suffix: str = "marked.txt") -> str:
    """Pfad fuer Roh-/Marked-Text: books/<book_id>/raw.txt
    (Suffix-Parameter bleibt fuer Abwaertskompatibilitaet erhalten, wird aber
    ignoriert -- der Rohtext heisst im Buchordner einheitlich 'raw.txt'.)"""
    return os.path.join(_ensure(book_dir(book_id)), "raw.txt")


# ============================================================
# MODUL ALS 'config'-OBJEKT VERFUEGBAR MACHEN
# ============================================================
# Erlaubt das in run.py und den Stages genutzte Muster:  from config import config
# -> "config" verweist dann auf dieses Modul selbst, sodass config.work_path(...) etc.
#    unveraendert funktionieren. (Kein Umbau der Stages noetig.)
import sys as _sys
config = _sys.modules[__name__]


# ============================================================
# CASTING / STIMMEN-ARCHIV (Stage 57, seit 11.10.2026)
# ============================================================
# Register aller designten Stimmen (Samenbank), werkuebergreifend.
STIMMEN_DIR = os.path.join(BASE_DIR, "stimmen_archiv")
MODELS["caster"] = MODELS["profiler"]          # Figuren-Steckbriefe + Stage 57b (seit 12.10.2026 DeepSeek)
CASTING_AKTIV = False          # True = Stage 57 fuer ALLE Werke; sonst nur book.json besetzung_modus
CASTING_AUTO_DESIGN = False    # True = fehlende Stimmen im Pipeline-Lauf automatisch designen
CASTING_SCHWELLE = 70          # Mindest-Passung (0-100) fuer Wiederverwendung aus dem Archiv
CASTING_MIN_F0_ABSTAND = 0.12  # Grundton-Mindestabstand zu Ensemble-Stimmen gleichen Geschlechts
CASTING_MAX_ENSEMBLE = 15      # max. eigene Figurenstimmen je Werk (ohne Erzaehler)
CASTING_MIN_ANTEIL = 2.0       # min. Dialoganteil in % fuer eine eigene Stimme
CASTING_GENRE_ERZAEHLER = {    # Erzaehler je Genre (CK, 11.10.2026)
    "maerchen": "grossmutter_a",
    "abenteuer": "herr_a",
    "krimi": "herr_a",
    "grosses_werk": "herr_b",
}

TTS_PARALLEL = 8               # gleichzeitige Gemini-TTS-Anfragen (Tier 2 seit 11.10.2026)
