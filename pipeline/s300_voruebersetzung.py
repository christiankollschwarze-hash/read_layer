"""STAGE 300 — Vorübersetzung
Funktion:     Freie Kapiteluebersetzung als Kontextanker.
Wirkungsweise: Je Kapitel und Zielsprache ein DeepSeek-Pro-Aufruf; Warnung bei vermutlich abgeschnittener Antwort.
Komponenten:  pipeline/s300_voruebersetzung.py, api_layer
Zulieferer:   s210 Profil (work/210_profil.json)
Abnehmer:     s310 Uebersetzung (work/300_voruebersetzung.json)
(Nomenklatur seit 18.10.2026, Uebersicht: docs/Pipeline_Strang_Matrix.xlsx)

--- Bisherige Beschreibung ---

READ LAYER — Stage 02: Pretranslator
====================================
Input:  data/work/<book_id>_stage01.json
Output: data/work/<book_id>_stage02.json  (= 210_profil + meta.pretranslation)

Aufgabe: Pro Kapitel und Zielsprache eine ZUSAMMENHAENGENDE Vooruebersetzung
erzeugen — am Stueck, ohne Tag-Zwang. Sie dient NICHT der Auslieferung,
sondern als semantischer Kontext-Anker fuer die satzgenaue Uebersetzung
in Stage 03 (verhindert, dass Saetze isoliert und kontextlos uebersetzt werden).

Wichtig: immer direkt aus der Originalsprache, nie ueber eine Zwischensprache.
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import api_layer


# ============================================================
# KAPITELTEXT EINSAMMELN (Quelltext, pro Kapitel)
# ============================================================

def _collect_chapter_texts(data: dict) -> dict:
    """
    Gruppiert die Quelltext-Saetze nach Kapitel.
    Gibt {chapter_id: "zusammenhaengender Text"} zurueck.
    Ueberspringt Nicht-Audio-Typen (p/skip/tt) und leere Felder.
    """
    src = config.SOURCE_LANGUAGE
    cd = config.CHAPTER_DIGITS
    chapters = {}

    for tag_id, entry in data["content"].items():
        if entry.get("type") in config.NO_AUDIO_TYPES:
            continue
        text = entry.get(src, "").strip()
        if not text:
            continue
        # Kapitel-ID aus dem Tag ableiten: "c001_s00003" -> "c001"
        chapter_id = tag_id.split("_")[0]
        chapters.setdefault(chapter_id, []).append(text)

    return {cid: " ".join(sents) for cid, sents in chapters.items()}


# ============================================================
# PRETRANSLATOR-PROMPT
# ============================================================

def _build_prompt(chapter_text: str, target_lang: str, profile: dict) -> str:
    src = config.SOURCE_LANGUAGE
    style = profile.get("style", {})
    tone = style.get("tone", "")
    register = style.get("register", "")

    style_hint = ""
    if tone or register:
        style_hint = f"\nKeep this style: tone = {tone}, register = {register}."

    return f"""Translate the following text from {src} into {target_lang}.
Produce a single, coherent, natural translation of the whole passage.
This is a context reference, so prioritise fluent meaning over literal word order.{style_hint}

--- TEXT START ---
{chapter_text}
--- TEXT END ---

Return ONLY the translated text, no explanation."""


# ============================================================
# PRETRANSLATOR
# ============================================================

def pretranslate_chapter(chapter_text: str, target_lang: str, profile: dict) -> str:
    if config.RUN_MODE == "mock":
        # Strukturtreuer Platzhalter
        return api_layer.call_model(
            "pretranslator", "", target_lang=target_lang
        )
    prompt = _build_prompt(chapter_text, target_lang, profile)
    # QF-7 (18.10.2026): 8192 schnitt lange Kapitel still ab.
    result = api_layer.call_model("pretranslator", prompt, max_tokens=32000)
    if len(result) < 0.6 * len(chapter_text):
        print(f"    [WARNUNG] Vorübersetzung {target_lang}: nur {len(result)} von "
              f"{len(chapter_text)} Zeichen -- vermutlich abgeschnitten.")
    return result


# ============================================================
# HAUPTPROZESS
# ============================================================

def run(book_id: str) -> dict:
    in_path = config.work_path(book_id, "210_profil")
    print(f"[stage52] Lese: {in_path}")
    with open(in_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    profile = data["meta"].get("profile", {})
    chapter_texts = _collect_chapter_texts(data)
    print(f"[stage52] Kapitel: {len(chapter_texts)} | Zielsprachen: {config.TARGET_LANGUAGES}")

    # Struktur: meta.pretranslation[chapter_id][lang] = "text"
    pretranslation = {}
    for chapter_id, text in chapter_texts.items():
        pretranslation[chapter_id] = {}
        for lang in config.TARGET_LANGUAGES:
            result = pretranslate_chapter(text, lang, profile)
            pretranslation[chapter_id][lang] = result
        print(f"    {chapter_id}: vooruebersetzt in {len(config.TARGET_LANGUAGES)} Sprachen")

    data["meta"]["pretranslation"] = pretranslation

    out_path = config.work_path(book_id, "300_voruebersetzung")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[stage52] Geschrieben: {out_path}")
    return data


if __name__ == "__main__":
    book = sys.argv[1] if len(sys.argv) > 1 else "aesop_three_fables"
    run(book)
