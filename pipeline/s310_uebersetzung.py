"""STAGE 310 — Uebersetzung
Funktion:     Satzgenaue, ID-gebundene Uebersetzung.
Wirkungsweise: Batches a 25 Saetze mit Stil, Glossar und Vorübersetzung als Kontext; bis 3 Versuche je Batch.
Komponenten:  pipeline/s310_uebersetzung.py, api_layer
Zulieferer:   s300 Vorübersetzung (work/300_voruebersetzung.json)
Abnehmer:     s320 Integritaet, s340 Wort-Alignment (work/310_uebersetzung.json)
(Nomenklatur seit 18.10.2026, Uebersicht: docs/Pipeline_Strang_Matrix.xlsx)

--- Bisherige Beschreibung ---

READ LAYER — Stage 03: Translator
=================================
Input:  data/work/<book_id>_stage02.json
Output: data/work/<book_id>_stage03.json

Aufgabe: Jeden uebersetzbaren Tag in alle Zielsprachen uebersetzen und
die Uebersetzung direkt ins content schreiben (neben "en" dann "de","fr",...).

Strategie: KAPITELWEISE im Batch, ID-GEBUNDEN.
  - Haelt den Kontextfaden ueber Satzgrenzen (Pronomen, Zeitformen, Ton).
  - Bekommt Vooruebersetzung (Stage 02) und Profil (Stage 01) als Kontext.
  - Immer direkt aus der Originalsprache.

Tag-Treue (Weg A): Jeder Satz traegt seine Tag-ID. Das Modell muss ein
Objekt {tag_id: uebersetzung} zurueckgeben. Zuordnung ueber die ID, NICHT
ueber die Position. Dadurch kann nichts verrutschen; fehlende IDs werden
einzeln gemeldet, der Rest korrekt zugeordnet.
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import api_layer


def _collect_translatable(data: dict, chapter: str = None) -> dict:
    src = config.SOURCE_LANGUAGE
    chapters = {}
    for tag_id, entry in data["content"].items():
        if entry.get("type") in config.NO_AUDIO_TYPES:
            continue
        if chapter and not tag_id.startswith(chapter):
            continue
        text = entry.get(src, "").strip()
        if not text:
            continue
        chapter_id = tag_id.split("_")[0]
        chapters.setdefault(chapter_id, []).append((tag_id, text))
    return chapters


def _build_prompt(items, target_lang, pretranslation, profile) -> str:
    src = config.SOURCE_LANGUAGE

    lines = "\n".join(
        f'  {json.dumps(tid)}: {json.dumps(s, ensure_ascii=False)}'
        for tid, s in items
    )

    context = ""
    if pretranslation:
        context = (
            f"\nFor context, here is a free translation of the whole chapter "
            f"in {target_lang} (do NOT copy it verbatim, use it only to keep "
            f"meaning and flow consistent):\n{pretranslation}\n"
        )

    glossary = profile.get("glossary", {})
    glossary_hint = ""
    if glossary:
        pairs = []
        for term, langs in glossary.items():
            if target_lang in langs:
                pairs.append(f'"{term}" -> "{langs[target_lang]}"')
        if pairs:
            glossary_hint = "\nUse these fixed translations:\n" + "\n".join(pairs) + "\n"

    # Stil-/Epochen-Kontext aus dem Profil — wird in JEDEN Chunk eingebettet, damit
    # die epochengerechte Wortwahl ueber alle Chunks konsistent bleibt (z.B. "calls"
    # = Besuche, nicht Anrufe). Das Modell hat kein Gedaechtnis ueber Chunks hinweg;
    # der Kontext "ueberlebt" nur durch Wiederholung in jedem Prompt.
    style = profile.get("style", {})
    style_bits = []
    if style.get("setting"):  style_bits.append(f"Setting/era: {style['setting']}")
    if style.get("tone"):     style_bits.append(f"Tone: {style['tone']}")
    if style.get("register"): style_bits.append(f"Register: {style['register']}")
    if style.get("notes"):    style_bits.append(f"Notes: {style['notes']}")
    style_hint = ""
    if style_bits:
        style_hint = ("\nKeep the translation faithful to the work's period and style. "
                      "Choose era-appropriate wording (e.g. avoid anachronistic modern "
                      "terms). Context:\n- " + "\n- ".join(style_bits) + "\n")

    return f"""Translate each sentence from {src} into {target_lang}.
Translate directly from the source, never through a third language.

Each sentence has a unique ID. Return the translation under the SAME ID.
You MUST return every ID exactly once — including very short ones like "See?",
"Why not?" or "Just think!". Never merge two sentences into one entry, and
never split one sentence into two entries. Keep one translation per ID.
{style_hint}{context}{glossary_hint}
Return ONLY a JSON object mapping each ID to its translation, nothing else:
{{ "<id1>": "<translation>", "<id2>": "<translation>", ... }}

There are exactly {len(items)} IDs to translate.

Sentences (as JSON, id -> source text):
{{
{lines}
}}"""


def _translate_batch(items, target_lang, pretranslation, profile):
    """Uebersetzt EINEN Batch (Liste von (tag_id, text)). Gibt dict{tag_id:text}."""
    wanted = [tid for tid, _ in items]

    if config.RUN_MODE == "mock":
        sentences = [s for _, s in items]
        raw = api_layer.call_model(
            "translator", "", target_lang=target_lang, sentences=sentences
        )
        try:
            parsed = api_layer.parse_json(raw)
            lst = parsed.get("translations", []) if isinstance(parsed, dict) else []
            return {tid: lst[i] for i, tid in enumerate(wanted) if i < len(lst)}
        except Exception as e:
            print(f"      ! JSON-Fehler ({target_lang}, mock): {e}")
            return {}

    prompt = _build_prompt(items, target_lang, pretranslation, profile)
    raw = api_layer.call_model("translator", prompt, max_tokens=8000)
    try:
        parsed = api_layer.parse_json(raw)
        if isinstance(parsed, dict) and "translations" in parsed and isinstance(parsed["translations"], dict):
            parsed = parsed["translations"]
        return parsed if isinstance(parsed, dict) else {}
    except Exception as e:
        print(f"      ! JSON-Fehler ({target_lang}): {e}")
        return {}


def translate_chapter(items, target_lang, pretranslation, profile):
    """items = [(tag_id, source_text), ...]
    Zerlegt grosse Kapitel in Batches (robust fuer einkapitlige/lange Werke).
    Gibt (translations:dict{tag_id:text}, missing:list[tag_id]) zurueck."""
    wanted = [tid for tid, _ in items]
    batch_size = getattr(config, "TRANSLATE_BATCH_SIZE", 25)

    translations = {}
    n_batches = (len(items) + batch_size - 1) // batch_size
    for bi in range(n_batches):
        batch = items[bi * batch_size:(bi + 1) * batch_size]
        # Retry pro Batch gegen leere/abgeschnittene LLM-Antworten
        got = {}
        for attempt in range(1, 4):
            got = _translate_batch(batch, target_lang, pretranslation, profile)
            # genug, wenn die meisten des Batches da sind
            if got and len([1 for tid, _ in batch if got.get(tid, "").strip()]) >= max(1, int(len(batch) * 0.5)):
                break
            if attempt < 3:
                print(f"      Batch {bi+1}/{n_batches} ({target_lang}) duenn/leer, Versuch {attempt+1} ...")
        for tid, val in got.items():
            if isinstance(val, str) and val.strip():
                translations[tid] = val.strip()
        if n_batches > 1:
            done = len([t for t in wanted if t in translations])
            print(f"      Batch {bi+1}/{n_batches}: {done}/{len(items)} gesamt ({target_lang})")

    clean = {}
    for tid in wanted:
        val = translations.get(tid, "")
        if isinstance(val, str) and val.strip():
            clean[tid] = val.strip()

    missing = [tid for tid in wanted if tid not in clean]
    if missing:
        preview = [m[-8:] for m in missing[:5]]
        more = "..." if len(missing) > 5 else ""
        print(f"      ! Fehlende Tags ({target_lang}): {len(missing)} von "
              f"{len(items)} -> {preview}{more}")
    return clean, missing


_AUF_VOR = set(" \t\n([{\u2014\u2013-/\u00a0")
_ZEICHEN_NACH = set(" \t\n,.;:!?\u2026")


def anfuehrung_de(text: str) -> str:
    """24.10.2026 (Smoke #8): deutsche Anfuehrungszeichen vereinheitlichen.
    Doppelt: " “ ” -> „ (oeffnend) / “ (schliessend). Einfach (nur paarig): ' ‘ ’ -> ‚…‘.
    Apostrophe im Wort (geht's) bleiben. Idempotent; Guillemets bleiben unberuehrt."""
    if not text or not any(c in text for c in "\"\u201c\u201d'\u2018\u2019"):
        return text
    import re as _re
    out, offen = [], False
    for i, c in enumerate(text):
        if c == "\u201e":
            offen = True
            out.append(c)
            continue
        if c not in "\"\u201c\u201d":
            out.append(c)
            continue
        vor = text[i - 1] if i else " "
        nach = text[i + 1] if i + 1 < len(text) else " "
        if not offen and vor in _AUF_VOR and nach not in _ZEICHEN_NACH:
            out.append("\u201e")
            offen = True
        else:
            out.append("\u201c")
            offen = False
    t = "".join(out)
    t = _re.sub(r"(?<![\w])['\u2018\u2019\u201a](?=\w)(.+?)(?<=[\w.!?,\u2026])['\u2018\u2019](?![\w])",
                "\u201a\\1\u2018", t)
    return t


def run(book_id: str, chapter: str = None) -> dict:
    # Wenn ein 310_uebersetzung schon existiert, darauf AUFSETZEN (bereits uebersetzte
    # Kapitel bleiben erhalten); sonst von 300_voruebersetzung starten.
    base = config.work_path(book_id, "310_uebersetzung")
    in_path = base if os.path.exists(base) else config.work_path(book_id, "300_voruebersetzung")
    print(f"[stage53] Lese: {in_path}{' | NUR Kapitel '+chapter if chapter else ''}")
    with open(in_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    profile = data["meta"].get("profile", {})
    pretrans = data["meta"].get("pretranslation", {})
    chapters = _collect_translatable(data, chapter)

    print(f"[stage53] Kapitel: {len(chapters)} | Zielsprachen: {config.TARGET_LANGUAGES}")

    errors = []
    for chapter_id, items in chapters.items():
        print(f"    {chapter_id}: {len(items)} Saetze")
        for lang in config.TARGET_LANGUAGES:
            pre = pretrans.get(chapter_id, {}).get(lang, "")
            translations, missing = translate_chapter(items, lang, pre, profile)
            for tag_id, translation in translations.items():
                if tag_id in data["content"]:
                    data["content"][tag_id][lang] = translation
            if missing:
                errors.append((chapter_id, lang, len(missing)))

    if "de" in config.TARGET_LANGUAGES:   # Smoke #8: „…“ / ‚…‘ einheitlich
        n_q = 0
        for e in data["content"].values():
            if isinstance(e, dict) and isinstance(e.get("de"), str):
                neu = anfuehrung_de(e["de"])
                n_q += neu != e["de"]
                e["de"] = neu
        if n_q:
            print(f"[stage53] Anfuehrungszeichen DE vereinheitlicht: {n_q} Saetze")

    out_path = config.work_path(book_id, "310_uebersetzung")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[stage53] Geschrieben: {out_path}")
    if errors:
        print(f"[stage53] WARNUNG — fehlende Tags bei: {errors}")
        print(f"[stage53] Hinweis: Befehl erneut laufen lassen fuellt fehlende nach.")
    else:
        print(f"[stage53] Alle Kapitel/Sprachen vollstaendig uebersetzt.")
    return data


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    book = args[0] if args else "jekyll-and-hyde"
    ch = None
    if "--chapter" in sys.argv:
        i = sys.argv.index("--chapter")
        ch = sys.argv[i+1] if i+1 < len(sys.argv) else None
    run(book, chapter=ch)
