"""STAGE 210 — Profil
Funktion:     Buchprofil: Stil, Figuren, Glossar, Unuebersetzbares, Idiome.
Wirkungsweise: Ganzer Text in einem DeepSeek-Pro-Aufruf, Kappung der Listen, Rettung abgeschnittenen JSONs.
Komponenten:  pipeline/s210_profil.py, api_layer
Zulieferer:   s200 Tagging (work/200_tagging.json)
Abnehmer:     s300 Vorübersetzung, s310 Uebersetzung (Glossar), s400 Regie (Aussprache)
(Nomenklatur seit 18.10.2026, Uebersicht: docs/Pipeline_Strang_Matrix.xlsx)

--- Bisherige Beschreibung ---

READ LAYER — Stage 01: Profiler
===============================
Input:  data/work/<book_id>_stage00.json
Output: data/work/<book_id>_stage01.json  (= 200_tagging + meta.profile)

Aufgabe: Aus dem getaggten Quelltext ein Buch-Profil erzeugen, das als
Single Source of Truth fuer alle nachfolgenden Stufen dient.

Fuenf Kategorien:
  style        - Tonfall, Register (steuert den Uebersetzungs-Stil)
  characters   - Eigennamen + Uebersetzungsentscheidung + Aussprache
  untranslated - Begriffe, die im Original bleiben (z.B. "Dauphin") + Aussprache
  glossary     - feste Begriffs-Entsprechungen je Zielsprache
  idioms       - Redewendungen mit gewaehlter Entsprechung (nicht woertlich)

Das Profil greift NICHT in den Content ein — es haengt unter meta.profile.
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import api_layer


# ============================================================
# QUELLTEXT EINSAMMELN
# ============================================================

def _collect_source_text(data: dict) -> str:
    """
    Fuegt alle Quelltext-Saetze (ohne leere p/skip/tt) zu einem
    zusammenhaengenden Text zusammen — Grundlage fuer die Profil-Analyse.
    """
    src = config.SOURCE_LANGUAGE
    parts = []
    for tag_id, entry in data["content"].items():
        if entry.get("type") in config.NO_AUDIO_TYPES:
            continue
        text = entry.get(src, "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts)


# ============================================================
# PROFILER-PROMPT
# ============================================================

def _build_profiler_prompt(data: dict, source_text: str) -> str:
    src = config.SOURCE_LANGUAGE
    targets = ", ".join(config.TARGET_LANGUAGES)
    title = data["meta"].get("title", "")
    author = data["meta"].get("author", "")

    return f"""You are a literary analyst preparing a translation brief for a multilingual audiobook.

Analyze the following work and produce a translation profile as JSON.
Source language: {src}. Target languages: {targets}.

Return ONLY this JSON structure, nothing else:
{{
  "style": {{
    "tone": "<overall tone in a few words>",
    "register": "<e.g. literary, archaic, colloquial>",
    "setting": "<time period and place of the story, and the technological/social context of that era — e.g. 'London, 1880s; gas lamps, horse carriages, no telephones in daily use'>",
    "notes": "<any guidance a translator should keep in mind>",
    "voice_note": "<delivery hint for the AUDIOBOOK NARRATOR ONLY — how to read this work aloud. CONDITIONAL RULE: if the work's own style is already plain, sober or matter-of-fact, describe its natural delivery faithfully (1:1, no artificial flattening). ONLY if the style is ornate, archaic, florid, whimsical, grandiose or otherwise prone to over-acting, explicitly instruct RESTRAINT — so the narrator does NOT perform or exaggerate that style but carries it calmly and lets the words do the work. The goal is a natural modern audiobook reader, never a theatrical declaimer. A few words, e.g. plain work -> 'clear, steady narration'; florid work -> 'calm, even delivery; do not perform the ornate style, let the dry wit sit in the text'>"
  }},
  "characters": {{
    "<name as in source>": {{
      "{config.TARGET_LANGUAGES[0]}": "<rendering or same if kept>",
      "pronunciation": "<IPA or empty>",
      "tts_{config.TARGET_LANGUAGES[0]}": "<respelling so a {config.TARGET_LANGUAGES[0]} text-to-speech voice says the KEPT name as in the original language (e.g. Peter -> Pieter, John -> Dschonn); empty if a {config.TARGET_LANGUAGES[0]} reader would already say it right>"
    }}
  }},
  "untranslated": {{
    "<term to keep in original>": {{
      "meaning": "<short gloss>",
      "pronunciation": "<IPA or empty>",
      "tts_{config.TARGET_LANGUAGES[0]}": "<respelling so a {config.TARGET_LANGUAGES[0]} text-to-speech voice says the term as in the original language (e.g. Tidewater -> Teidwoter); empty if already right>"
    }}
  }},
  "glossary": {{
    "<source term>": {{ {", ".join(f'"{l}": "<translation>"' for l in config.TARGET_LANGUAGES)} }}
  }},
  "idioms": {{
    "<source idiom>": {{
      "meaning": "<plain meaning>",
      {", ".join(f'"{l}": "<idiomatic equivalent or neutral paraphrase>"' for l in config.TARGET_LANGUAGES)}
    }}
  }}
}}

Rules:
- Only include entries that genuinely occur in the text. Empty categories stay as {{}}.
- HARD LIMITS (the whole JSON must stay short): characters max 40 (named, recurring figures only),
  untranslated max 25, glossary max 60 (only terms whose translation must stay consistent), idioms max 40.
  Each key appears ONCE. Never repeat an entry, never list ordinary words. Stop when the limits are reached.
- For idioms, prefer an idiomatic equivalent; if none exists, give a neutral paraphrase.
- Decide per character whether the name is translated or kept; reflect that in the entry.

WORK TITLE: {title}
AUTHOR: {author}

--- TEXT START ---
{source_text}
--- TEXT END ---"""


# ============================================================
# MOCK-PROFIL (strukturtreu, leer)
# ============================================================

def _mock_profile(data: dict) -> dict:
    """
    Liefert ein strukturell korrektes, aber leeres Profil.
    Beweist den Datenfluss, ohne echte Analyse vorzutaeuschen.
    """
    return {
        "style":        {"tone": "mock-tone", "register": "mock-register", "notes": "", "voice_note": "calm, even, understated narration"},
        "characters":   {},
        "untranslated": {},
        "glossary":     {},
        "idioms":       {},
    }


# ============================================================
# PROFILER
# ============================================================

def build_profile(data: dict) -> dict:
    if config.RUN_MODE == "mock":
        return _mock_profile(data)
    source_text = _collect_source_text(data)
    prompt = _build_profiler_prompt(data, source_text)
    raw = api_layer.call_model("profiler", prompt, max_tokens=24000)   # 17.10.: Grenzen im Prompt, kein Endlos-Glossar
    global _RAW
    _RAW = raw
    try:
        prof = api_layer.parse_json(raw)
    except ValueError:
        prof = _abgeschnitten_retten(raw)
        print("[stage51] WARNUNG: Antwort abgeschnitten (Wiederholungsschleife?) -> vollstaendige Eintraege gerettet")
    return _kappen(prof)


_RAW = ""
GRENZEN = {"characters": 40, "untranslated": 25, "glossary": 60, "idioms": 40}


def _kappen(prof: dict) -> dict:
    """Obergrenzen im Code durchsetzen (DeepSeek haelt Listen-Grenzen im Prompt nicht zuverlaessig ein)."""
    for k, n in GRENZEN.items():
        v = prof.get(k)
        if isinstance(v, dict) and len(v) > n:
            prof[k] = dict(list(v.items())[:n])
    return prof


def _abgeschnitten_retten(raw: str) -> dict:
    """Abgeschnittenes JSON: an der letzten Stelle kappen, an der ein Objekt '}' vollstaendig endet,
    offene Klammern schliessen. Prueft von hinten bis zu 3000 Kandidaten."""
    s = raw[raw.find("{"):]
    ends = [i for i, c in enumerate(s) if c == "}"]
    for i in reversed(ends[-3000:]):
        teil = s[:i + 1]
        stapel, im_str, esc = [], False, False
        for c in teil:
            if im_str:
                if esc: esc = False
                elif c == "\\": esc = True
                elif c == '"': im_str = False
                continue
            if c == '"': im_str = True
            elif c in "{[": stapel.append(c)
            elif c in "}]" and stapel: stapel.pop()
        if im_str:
            continue
        zu = "".join("}" if c == "{" else "]" for c in reversed(stapel))
        try:
            return json.loads(teil.rstrip().rstrip(",") + zu)
        except Exception:
            continue
    raise ValueError("stage51: Profil nicht rettbar")


# ============================================================
# HAUPTPROZESS
# ============================================================

def run(book_id: str) -> dict:
    in_path = config.work_path(book_id, "200_tagging")
    print(f"[stage51] Lese: {in_path}")
    with open(in_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"[stage51] Erstelle Buch-Profil ({config.RUN_MODE}-Modus)...")
    profile = build_profile(data)
    # AP 58: feste Begriffe aus book.json ("glossar_fest": {Begriff: {lg: Ziel}}) ueberschreiben das LLM-Glossar
    try:
        _bj = json.load(open(os.path.join(config.book_dir(book_id), "book.json"), encoding="utf-8"))
        _fest = _bj.get("glossar_fest") or {}
        if _fest:
            profile.setdefault("glossary", {}).update(_fest)
            print(f"[stage51] glossar_fest aus book.json: {len(_fest)} Begriffe")
    except (OSError, ValueError):
        pass

    # Profil unter meta haengen — Content bleibt unberuehrt
    data["meta"]["profile"] = profile

    # Kurze Zusammenfassung ausgeben
    print(f"[stage51] Profil-Kategorien:")
    for key in ["style", "characters", "untranslated", "glossary", "idioms"]:
        val = profile.get(key, {})
        count = len(val) if isinstance(val, dict) else 0
        print(f"    {key:13s}: {count} Eintraege")

    if _RAW:
        open(config.work_path(book_id, "210_profil_raw").replace(".json", ".txt"), "w", encoding="utf-8").write(_RAW)
    out_path = config.work_path(book_id, "210_profil")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[stage51] Geschrieben: {out_path}")
    return data


if __name__ == "__main__":
    book = sys.argv[1] if len(sys.argv) > 1 else "aesop_three_fables"
    run(book)
