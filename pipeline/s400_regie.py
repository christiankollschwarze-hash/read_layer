"""STAGE 400 — Regie
Funktion:     Deterministische Audio-Regie je Satz.
Wirkungsweise: Regler Betonung/Emotion/Tempo aus book.json -> Stil-Stichworte, Pausen, Aussprachehinweise aus dem Profil.
Komponenten:  pipeline/s400_regie.py
Zulieferer:   s330 Rueckuebersetzung (work/330_rueckuebersetzung.json)
Abnehmer:     s410 Casting, s500 Vertonung, s630 ePub Zielsprache, s700 Guard, s710 Cloud-Export (work/400_regie.json)
(Nomenklatur seit 18.10.2026, Uebersicht: docs/Pipeline_Strang_Matrix.xlsx)

--- Bisherige Beschreibung ---

READ LAYER — Stage 56 (Audio-Regie, REGLER-basiert) [ersetzt SSML + Phoneme + LLM-Regie]
========================================================================================
Input:  authors/<autor>/books/<book>/work/330_rueckuebersetzung.json (Profil: untranslated)
        authors/<autor>/books/<book>/book.json (audio_regler, audio_pron_skip)
        authors/<autor>/author.json (wirkungssprache)
Output: authors/<autor>/books/<book>/work/400_regie.json (Checkpoint '400_regie')

WENDE 15.06.2026: Die frueher per LLM "frei formulierte" buchspezifische Regie war
UNKONTROLLIERBAR und hat im Deutschen eine auffaellige Substantiv-Betonung erzeugt.
ERSETZT durch drei deterministische REGLER auf Werkebene (book.json -> "audio_regler"):

    "audio_regler": { "betonung": 1-10, "emotion": 1-10, "tempo": 1-10 }

  - betonung niedrig -> "even, level word stress; do not emphasize nouns" (= Gegenmittel)
  - emotion  niedrig -> nuechtern ... hoch -> ausdrucksstark
  - tempo    niedrig -> bedaechtig ... hoch -> lebendig
Je 3 Stufen (1-3 niedrig / 4-7 mittel=neutral / 8-10 hoch). Fehlt -> {5,5,5}.
Gemini = VORLESER (Feinprosodie), nicht mehr REGISSEUR. Rahmen setzt der Mensch.

AUSSPRACHE-HINWEISE (Variante D, aus profile.untranslated):
Entwicklung 15.06.2026:
  - Teil 1: Hinweis NUR an Saetze haengen, die den Begriff tatsaechlich enthalten
    (frueher global -> wurde in fremden Saetzen mitvertont).
  - Teil 2 (nach Gatekeeper-Test tts_probe --pron-test): BEFEHLSFORM statt Zitat-Form.
    Alt "pronounce \u201cX\u201d as [IPA]" wurde vom Modell gelegentlich VORGELESEN.
    Neu: "Pronounce the proper noun X in <Wirkungssprache>." -> im Hoertest NICHT
    mitgelesen, Aussprache korrekt. "proper noun(s)" deckt Mehrwort-Eigennamen
    (z.B. "Sleepy Hollow") ab; Singular/Plural automatisch. Sprache = wirkungssprache
    des Autors (author.json), nicht hart "English".
  - SPERRLISTE book.json "audio_pron_skip": Begriffe, die GAR KEINEN Hinweis brauchen
    (klare Eigennamen, die das Modell ohnehin richtig spricht) -> Netz gegen Mitlesen.

Die PAUSEN-DRAMATURGIE (compute_pause_ms -> production.pause_after_ms) bleibt UNVERAENDERT.

UMBAU 08.10.2026 (Gemini 3.8 TTS, config.TTS_BACKEND = "gemini_api"):
  Die Regie landet jetzt in speech_metadata.style. Google: style KURZ halten,
  Stichworte statt Saetze, keine Meta-Anweisungen -- lange Regie-Bloecke erhoehen
  das Abdriften der Stimme. Daher zweiter Satz Formulierungen (_*_38): dieselben
  drei Regler, aber als knappe Stil-Stichworte, komma-getrennt.
  Bei TTS_BACKEND = "cloud_tts" bleiben die alten Saetze exakt wie bisher.
"""

import sys
import os
import json
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config


# Tag-Typen, die eine EIGENE Regie bekommen (Rest erbt 's')
DIRECTION_TYPES = ["s", "dl", "h"]

# Sprachcode -> englischer Sprachname (fuer die Aussprache-Befehlsform)
LANG_NAME = {"en": "English", "de": "German", "fr": "French", "es": "Spanish",
             "it": "Italian", "ru": "Russian", "nl": "Dutch", "pt": "Portuguese"}


def _audio_languages():
    return config.ALL_LANGUAGES


# ============================================================
# PAUSEN-DRAMATURGIE (unveraendert)
# ============================================================

def compute_pause_ms(entry: dict, lang: str) -> int:
    """Dramaturgische Pause NACH diesem Tag, in ms. Basis = Typ-Wert,
    verfeinert durch das Schluss-Satzzeichen der jeweiligen Sprachfassung."""
    typ = entry.get("type", "s")
    base = config.PAUSE_AFTER_MS.get(typ, config.PAUSE_AFTER_MS["s"])
    text = str(entry.get(lang, "")).strip()
    if text:
        last = text[-1]
        if last in '"\u201d\u00bb' and len(text) >= 2:
            last = text[-2]
        base += config.PAUSE_BY_PUNCTUATION.get(last, 0)
    return max(0, base)


# ============================================================
# WIRKUNGSSPRACHE + SPERRLISTE
# ============================================================

def _author_wirkungssprache(book_id: str) -> str:
    """Liest wirkungssprache aus author.json (authors/<autor>/author.json)."""
    bdir = config.book_dir(book_id)
    author_dir = os.path.dirname(os.path.dirname(bdir))  # .../books/<book> -> .../<autor>
    apath = os.path.join(author_dir, "author.json")
    try:
        aj = json.load(open(apath, encoding="utf-8"))
        return (aj.get("wirkungssprache") or "en").strip()
    except Exception:
        return "en"


def _load_pron_skip(book_id: str) -> set:
    """Liest book.json 'audio_pron_skip' (Liste von Begriffen, die KEINEN
    Aussprache-Hinweis bekommen) -> Set kleingeschriebener Begriffe."""
    path = os.path.join(config.book_dir(book_id), "book.json")
    try:
        bj = json.load(open(path, encoding="utf-8"))
        skip = bj.get("audio_pron_skip") or []
        return {str(s).strip().lower() for s in skip if str(s).strip()}
    except Exception:
        return set()


# ============================================================
# AUSSPRACHE-HINWEISE -- pro Satz, Befehlsform, Wirkungssprache, Sperrliste
# ============================================================

def _pron_for_text(text: str, untranslated: dict, skip_set: set,
                   lang_name: str) -> str:
    """Aussprache-Hinweis NUR fuer Begriffe, die in DIESEM Satz vorkommen und
    NICHT auf der Sperrliste stehen. Befehlsform (im Hoertest nicht mitgelesen):
      1 Begriff  -> ' Pronounce the proper noun X in <Sprache>.'
      mehrere    -> ' Pronounce the proper nouns X, Y and Z in <Sprache>.'"""
    if not untranslated or not text:
        return ""
    low = text.lower()
    hits = []
    for term in untranslated:
        if not term:
            continue
        tl = term.lower()
        if tl in skip_set:
            continue
        # Ganzwort-Treffer (08.10.2026): vorher Teilstring -> "ho" traf "hoch", "Hof" ...
        if re.search(r"(?<!\w)" + re.escape(tl) + r"(?!\w)", low):
            hits.append(term)
    if not hits:
        return ""
    if _is_38():
        # 3.8: als Stil-Stichwort (wird nicht vorgelesen, da style != Transkript)
        return f"; {', '.join(hits)} pronounced as in {lang_name}"
    if len(hits) == 1:
        return f" Pronounce the proper noun {hits[0]} in {lang_name}."
    joined = ", ".join(hits[:-1]) + " and " + hits[-1]
    return f" Pronounce the proper nouns {joined} in {lang_name}."


# ============================================================
# REGLER -> REGIE (deterministisch, ersetzt die LLM-Regie)
# ============================================================

# 1-3 = niedrig, 4-7 = mittel (neutral, keine Sonderanweisung), 8-10 = hoch
def _band(v) -> str:
    try:
        v = int(v)
    except (TypeError, ValueError):
        v = 5
    if v <= 3:
        return "low"
    if v >= 8:
        return "high"
    return "mid"


_BETONUNG = {
    "low": "Use even, level word stress; do not emphasize nouns or individual "
           "words -- read with natural, everyday delivery.",
    "mid": "",
    "high": "Give the meaningful words clear, deliberate emphasis.",
}
_EMOTION = {
    "low": "Keep the tone neutral, matter-of-fact and restrained.",
    "mid": "",
    "high": "Let genuine feeling and expression come through in the voice.",
}
_TEMPO = {
    "low": "Speak at a slow, unhurried, measured pace.",
    "mid": "",
    "high": "Speak at a lively, brisk pace.",
}

_BASE = {
    "s": "Read this as a calm audiobook narrator.",
    "dl": "Read this line of dialogue as spoken by a person, within the narration's mood.",
    "h": "Read this chapter heading clearly and plainly.",
}


# --- Gemini 3.8: knappe Stil-Stichworte (speech_metadata.style) ---
_BETONUNG_38 = {"low": "even word stress, no emphasis on nouns", "mid": "",
                "high": "clear emphasis on key words"}
_EMOTION_38 = {"low": "neutral and restrained", "mid": "",
               "high": "expressive, heartfelt"}
_TEMPO_38 = {"low": "slow, measured pace", "mid": "",
             "high": "lively, brisk pace"}
_BASE_38 = {
    "s": "calm audiobook narration",
    "dl": "natural spoken dialogue within the narration's mood",
    "h": "clear, plain chapter heading",
}


def _is_38() -> bool:
    return getattr(config, "TTS_BACKEND", "gemini_api") == "gemini_api"


def _compose_38(base: str, reglers: dict) -> str:
    parts = [base]
    for phrase in (_TEMPO_38[_band(reglers.get("tempo", 5))],
                   _EMOTION_38[_band(reglers.get("emotion", 5))],
                   _BETONUNG_38[_band(reglers.get("betonung", 5))]):
        if phrase:
            parts.append(phrase)
    return ", ".join(parts)


def _compose(base: str, reglers: dict) -> str:
    """Setzt aus Basis + den drei Regler-Stufen eine Regie-Zeile zusammen.
    'Mittel' liefert leere Strings -> faellt sauber weg."""
    parts = [base]
    for phrase in (_TEMPO[_band(reglers.get("tempo", 5))],
                   _EMOTION[_band(reglers.get("emotion", 5))],
                   _BETONUNG[_band(reglers.get("betonung", 5))]):
        if phrase:
            parts.append(phrase)
    return " ".join(parts)


def directions_from_reglers(reglers: dict) -> dict:
    """{typ: regie} aus den drei Reglern. OEFFENTLICH -- das Gatekeeper-Tool
    tts_probe.py importiert das, damit der Probelauf exakt dieselbe Regie
    erzeugt wie der echte Stage-58-Lauf (kein Auseinanderdriften)."""
    if _is_38():
        return {t: _compose_38(_BASE_38[t], reglers) for t in DIRECTION_TYPES}
    return {t: _compose(_BASE[t], reglers) for t in DIRECTION_TYPES}


def _load_reglers(book_id: str) -> dict:
    """Liest audio_regler aus book.json. Fehlt es -> {5,5,5} (neutral)."""
    path = os.path.join(config.book_dir(book_id), "book.json")
    r = {}
    try:
        bj = json.load(open(path, encoding="utf-8"))
        r = bj.get("audio_regler") or {}
    except Exception:
        r = {}
    return {
        "betonung": int(r.get("betonung", 5)),
        "emotion": int(r.get("emotion", 5)),
        "tempo": int(r.get("tempo", 5)),
    }


def _direction_for_type(typ: str, base_directions: dict) -> str:
    """Regie fuer einen Tag-Typ; unbekannte Audio-Typen erben die Erzaehler-Regie."""
    return base_directions.get(typ, base_directions["s"])


# ============================================================
# HAUPTPROZESS
# ============================================================

def _qualitaets_stopp(data):
    """QF-6 (18.10.2026): Stopp, wenn Stage 55 zu viele Saetze unter der Schwelle meldet."""
    qr = data.get("meta", {}).get("quality_report", {})
    n_flag = len(qr.get("flagged", []))
    n_bew = qr.get("scored_count", 0) or 0
    if not n_bew or os.environ.get("READLAYER_WEITER") == "1":
        return
    anteil = n_flag / n_bew
    grenze = getattr(config, "FLAG_MAX_ANTEIL", 0.03)
    if anteil > grenze:
        raise RuntimeError(
            f"Stage 55: {n_flag} von {n_bew} Saetzen unter Score {qr.get('threshold')} "
            f"({anteil:.1%} > {grenze:.0%}). Liste in 330_rueckuebersetzung.json -> meta.quality_report.flagged "
            f"pruefen/nacharbeiten oder bewusst weiter mit READLAYER_WEITER=1.")


def run(book_id: str) -> dict:
    in_path = config.work_path(book_id, "330_rueckuebersetzung")
    print(f"[stage56] Lese: {in_path}")
    with open(in_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    _qualitaets_stopp(data)   # QF-6

    profile = data["meta"].get("profile", {})
    untranslated = profile.get("untranslated", {})
    langs = _audio_languages()

    # 1) REGLER -> Regie (ersetzt die alte LLM-Regie komplett)
    reglers = _load_reglers(book_id)
    base_directions = directions_from_reglers(reglers)

    # 2) Aussprache-Kontext: Wirkungssprache + Sperrliste
    author_lang = _author_wirkungssprache(book_id)
    lang_name = LANG_NAME.get(author_lang, author_lang)
    skip_set = _load_pron_skip(book_id)

    print(f"[stage56] Regler (book.json): betonung={reglers['betonung']} "
          f"emotion={reglers['emotion']} tempo={reglers['tempo']} "
          f"(1-3 niedrig / 4-7 mittel / 8-10 hoch)")
    for t, d in base_directions.items():
        print(f"  [{t}] {d}")
    if untranslated:
        print(f"[stage56] Aussprache: {len(untranslated)} Begriff(e), Befehlsform "
              f"in {author_lang} ({lang_name}); Sperrliste: {len(skip_set)} Begriff(e)")

    production = data.setdefault("production", {})
    direction_layer = production.setdefault("direction", {})
    pause_layer = production.setdefault("pause_after_ms", {})
    production.pop("ssml", None)  # alte SSML-Schicht entfernen, falls vorhanden

    dir_count = 0
    pause_count = 0
    pron_hits = 0
    for tag_id, entry in data["content"].items():
        typ = entry.get("type", "s")

        pause_layer[tag_id] = {}
        for lang in langs:
            pause_layer[tag_id][lang] = compute_pause_ms(entry, lang)
        pause_count += 1

        if typ in config.NO_AUDIO_TYPES:
            continue
        regie = _direction_for_type(typ, base_directions)
        direction_layer[tag_id] = {}
        for lang in langs:
            txt = str(entry.get(lang, "")).strip()
            pron = _pron_for_text(txt, untranslated, skip_set, lang_name)
            if pron:
                pron_hits += 1
            direction_layer[tag_id][lang] = regie + pron
        dir_count += 1

    print(f"[stage56] Regie-Eintraege: {dir_count} "
          f"({len(direction_layer)} Tags x {len(langs)} Sprachen)")
    print(f"[stage56] Aussprache-Hinweis tatsaechlich gesetzt: {pron_hits} "
          f"Schnipsel-Sprachen (nur wo Begriff vorkommt + nicht gesperrt)")
    print(f"[stage56] Pausen gesetzt: {pause_count} "
          f"({len(pause_layer)} Tags x {len(langs)} Sprachen)")

    out_path = config.work_path(book_id, "400_regie")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[stage56] Geschrieben: {out_path} (Checkpoint '400_regie')")
    return data


if __name__ == "__main__":
    book = sys.argv[1] if len(sys.argv) > 1 else "aesop_three_fables"
    run(book)
