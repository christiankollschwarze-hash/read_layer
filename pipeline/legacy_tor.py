"""Altmodul (bis Phase 2: pipeline/gate.py, umbenannt 01.11.2026). Wird mit 410/500/510 abgeloest.
AP 63: Hoerspiel-Gate je Werk. book.json "hoerspiel": "offen" | "ja" | "nein".
Fehlt der Eintrag, gilt None -> Legacy-Verhalten (besetzung_modus / HYBRID_WERKE)."""
import json
import os

from config import config


def tts_engine(book_id, lang):
    """AP 63: Engine je Werk und Sprache aus book.json "tts": {"de": "gemini", "en": "chatterbox"}.
    Ohne Eintrag: Legacy (DE = config.TTS_ENGINE_DE, sonst gemini)."""
    try:
        p = os.path.join(config.book_dir(book_id), "book.json")
        t = json.load(open(p, encoding="utf-8")).get("tts") or {}
    except Exception:
        t = {}
    if lang in t and t[lang] in ("gemini", "thorsten", "chatterbox"):
        return t[lang]
    if lang == "de" and getattr(config, "TTS_ENGINE_DE", "gemini") == "thorsten":
        return "thorsten"
    return "gemini"


def hoerspiel_gate(book_id):
    try:
        p = os.path.join(config.book_dir(book_id), "book.json")
        v = json.load(open(p, encoding="utf-8")).get("hoerspiel")
    except Exception:
        return None
    return v if v in ("offen", "ja", "nein") else None


# ---------------- AP 63: Stimmen-Gate ----------------
# book.json "stimme": "<archiv-name>" oder {"de": "<archiv-name>", "en": "<archiv-name>"}
# Archiv-Name = Ordner in stimmen_archiv/ (Design) oder stimmen_archiv/_gemini_standard/ (30 Standardstimmen).
# Pflicht nur fuer Werke mit "tts"-Eintrag (neues Schema); Altwerke unveraendert.
ARCHIV = os.path.join(config.BASE_DIR, "stimmen_archiv")


def _bj(book_id):
    try:
        return json.load(open(os.path.join(config.book_dir(book_id), "book.json"), encoding="utf-8"))
    except Exception:
        return {}


def stimme(book_id, lang):
    s = _bj(book_id).get("stimme")
    if isinstance(s, dict):
        s = s.get(lang)
    return (s or "").strip() or None


def _ordner(name):
    for b in (os.path.join(ARCHIV, "_gemini_standard", name), os.path.join(ARCHIV, name)):
        if name and os.path.isdir(b):
            return b
    return None


def gemini_voice(name):
    """Archiv-Name -> Gemini-Stimme: Standardname oder Design-ID aus steckbrief.json."""
    if name and os.path.isdir(os.path.join(ARCHIV, "_gemini_standard", name)):
        return name
    p = os.path.join(ARCHIV, name or "-", "steckbrief.json")
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8")).get("id") or None
    return None


def ref_clip(name, lang):
    """Referenz fuer Chatterbox-Klon: klon_<lang>.wav (Nordwind), sonst hoerprobe.wav, sonst muster_<lang>.wav."""
    o = _ordner(name)
    if not o:
        return None
    for f in (f"klon_{lang}.wav", "hoerprobe.wav", f"muster_{lang}.wav"):
        if os.path.exists(os.path.join(o, f)):
            return os.path.join(o, f)
    return None


def stimmen_pruefung(book_id, lang):
    """None = ok; sonst Meldung. Nur fuer Werke mit "tts"-Eintrag."""
    if "tts" not in _bj(book_id):
        return None
    name = stimme(book_id, lang)
    if not name:
        n_std = len([d for d in os.listdir(os.path.join(ARCHIV, "_gemini_standard"))
                     if os.path.isdir(os.path.join(ARCHIV, "_gemini_standard", d))])
        return (f"{book_id} [{lang}]: keine Sprecherstimme gewaehlt. book.json \"stimme\" setzen "
                f"(Cockpit: Sprecherauswahl; {n_std} Gemini-Standardstimmen + Archiv-Designs).")
    if not _ordner(name):
        return f"{book_id} [{lang}]: Stimme '{name}' nicht im stimmen_archiv gefunden."
    eng = tts_engine(book_id, lang)
    if eng == "gemini" and not gemini_voice(name):
        return f"{book_id} [{lang}]: Stimme '{name}' hat keine Gemini-ID (steckbrief.json)."
    if eng == "chatterbox" and not ref_clip(name, lang):
        return f"{book_id} [{lang}]: Stimme '{name}' hat keine Hoerprobe fuer den Klon."
    return None
