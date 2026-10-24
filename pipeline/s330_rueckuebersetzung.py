"""STAGE 330 — Rueckuebersetzung
Funktion:     Qualitaets-Score je Satz per Rueckuebersetzung.
Wirkungsweise: Ziel -> EN zurueck (DeepSeek Pro), Bewertung 0-100 (Flash); unter Schwelle -> flagged. s400 stoppt bei zu vielen Flags.
Komponenten:  pipeline/s330_rueckuebersetzung.py, api_layer
Zulieferer:   s320 Integritaet (work/320_integritaet.json)
Abnehmer:     s400 Regie (work/330_rueckuebersetzung.json), Cockpit-Tor Uebersetzung
(Nomenklatur seit 18.10.2026, Uebersicht: docs/Pipeline_Strang_Matrix.xlsx)

--- Bisherige Beschreibung ---

READ LAYER — Stage 55 (Backtranslation Check)
=============================================
Input:  authors/<autor>/books/<book>/work/320_integritaet.json
Output: authors/<autor>/books/<book>/work/330_rueckuebersetzung.json + meta.quality_report

API-GESTUETZT. Beantwortet die QUALITAETS-Frage, nicht die Struktur-Frage.

Verfahren pro Kapitel und Zielsprache (ID-GEBUNDEN, robust):
  1. Zielsprache zurueck in die Quellsprache uebersetzen (back-translation)
  2. Rueckuebersetzung gegen das Original bewerten lassen -> Score 0..100
  3. Score < VALIDATION_THRESHOLD -> Tag zur Nacharbeit markieren

Robustheit: Alle Modell-Antworten ID-gebunden ({tag_id: ...}), nicht
positionsbasiert. Kaputtes/teilweises JSON reisst nicht die ganze Stage ab —
betroffene Tags werden als 'nicht bewertet' uebersprungen, der Rest zaehlt.
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import api_layer


def _safe_parse(raw):
    """parse_json, aber wirft nie — gibt {} bei kaputtem JSON."""
    try:
        parsed = api_layer.parse_json(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _chunks(seq, size):
    """Teilt eine Liste in Haeppchen von max. `size` Elementen."""
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _collect_translatable(data: dict, chapter: str = None) -> dict:
    """{chapter_id: [(tag_id, source, {lang: translation}), ...]}"""
    src = config.SOURCE_LANGUAGE
    chapters = {}
    for tag_id, entry in data["content"].items():
        if entry.get("type") in config.NO_AUDIO_TYPES:
            continue
        if chapter and not tag_id.startswith(chapter):
            continue
        source = entry.get(src, "").strip()
        if not source:
            continue
        trans = {l: entry.get(l, "") for l in config.TARGET_LANGUAGES}
        chapter_id = tag_id.split("_")[0]
        chapters.setdefault(chapter_id, []).append((tag_id, source, trans))
    return chapters


def _backtranslate(items_bt, lang):
    """
    items_bt = [(tag_id, target_text), ...]  (target_text in Sprache `lang`)
    Gibt dict {tag_id: back_translation_in_source} zurueck.
    Verarbeitet in Haeppchen (BACKTRANS_BATCH_SIZE) -> robust gegen
    unvollstaendiges JSON bei grossen Kapiteln. Pro Haeppchen ein Retry.
    """
    src = config.SOURCE_LANGUAGE
    size = getattr(config, "BACKTRANS_BATCH_SIZE", 25)
    result = {}

    if config.RUN_MODE == "mock":
        for batch in _chunks(items_bt, size):
            wanted = [tid for tid, _ in batch]
            sentences = [t for _, t in batch]
            raw = api_layer.call_model("translator", "", target_lang=src, sentences=sentences)
            parsed = _safe_parse(raw)
            lst = parsed.get("translations", []) if isinstance(parsed, dict) else []
            for i, tid in enumerate(wanted):
                if i < len(lst):
                    result[tid] = lst[i]
        return result

    def _one_batch(batch):
        wanted = [tid for tid, _ in batch]
        lines = "\n".join(
            f'  {json.dumps(tid)}: {json.dumps(t, ensure_ascii=False)}'
            for tid, t in batch
        )
        prompt = f"""Translate each sentence from {lang} into {src}.
Each sentence has a unique ID. Return the translation under the SAME ID.
Return every ID exactly once. Never merge or split sentences.
Return ONLY a JSON object mapping each ID to its translation:
{{ "<id1>": "<translation>", ... }}

There are exactly {len(batch)} IDs.

Sentences (as JSON, id -> text):
{{
{lines}
}}"""
        raw = api_layer.call_model("translator", prompt, max_tokens=16000)
        parsed = _safe_parse(raw)
        if "translations" in parsed and isinstance(parsed["translations"], dict):
            parsed = parsed["translations"]
        return {tid: parsed[tid] for tid in wanted
                if isinstance(parsed.get(tid), str) and parsed.get(tid, "").strip()}

    for batch in _chunks(items_bt, size):
        got = _one_batch(batch)
        if len(got) < len(batch):  # unvollstaendig -> ein Retry
            got2 = _one_batch(batch)
            got = {**got2, **got}  # vorhandene behalten, fehlende ergaenzen
        result.update(got)
    return result


def _score(items_sc, lang):
    """
    items_sc = [(tag_id, original_source, back_translation), ...]
    Gibt dict {tag_id: score(int)} zurueck. Gehaeppchen wie _backtranslate.
    """
    src = config.SOURCE_LANGUAGE
    size = getattr(config, "BACKTRANS_BATCH_SIZE", 25)
    result = {}

    if config.RUN_MODE == "mock":
        raw = api_layer.call_model("validator", "")
        single = _safe_parse(raw).get("score", 95)
        return {tid: single for tid, _, _ in items_sc}

    def _one_batch(batch):
        wanted = [tid for tid, _, _ in batch]
        blocks = "\n".join(
            f'  {json.dumps(tid)}: {{ "original": {json.dumps(o, ensure_ascii=False)}, '
            f'"back": {json.dumps(b, ensure_ascii=False)} }}'
            for tid, o, b in batch
        )
        prompt = f"""You are a translation quality assessor.
For each ID, compare the BACK-translation (from {lang} back to {src}) against
the ORIGINAL. Score how well the meaning was preserved, 0-100 (integer).

Return ONLY a JSON object mapping each ID to its integer score:
{{ "<id1>": <score>, "<id2>": <score>, ... }}

There are exactly {len(batch)} IDs.

Pairs (as JSON, id -> {{original, back}}):
{{
{blocks}
}}"""
        raw = api_layer.call_model("validator", prompt, max_tokens=8192)
        parsed = _safe_parse(raw)
        if "scores" in parsed and isinstance(parsed["scores"], dict):
            parsed = parsed["scores"]
        out = {}
        for tid in wanted:
            v = parsed.get(tid)
            if isinstance(v, (int, float)):
                out[tid] = int(v)
            elif isinstance(v, str) and v.strip().isdigit():
                out[tid] = int(v.strip())
        return out

    for batch in _chunks(items_sc, size):
        got = _one_batch(batch)
        if len(got) < len(batch):  # unvollstaendig -> ein Retry
            got2 = _one_batch(batch)
            got = {**got2, **got}
        result.update(got)
    return result


def run(book_id: str, chapter: str = None) -> dict:
    in_path = config.work_path(book_id, "320_integritaet")
    print(f"[stage55] Lese: {in_path}{' | NUR Kapitel '+chapter if chapter else ''}")
    with open(in_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # QF-6 (18.10.2026): Stopp, wenn Stage 54 Struktur-Fehler gemeldet hat.
    ir = data.get("meta", {}).get("integrity_report", {})
    if ir and not ir.get("clean", True) and os.environ.get("READLAYER_WEITER") != "1":
        raise RuntimeError(
            f"Stage 54 meldet Fehler (fehlend: {len(ir.get('missing_language', []))}, "
            f"leer: {len(ir.get('empty_translation', []))}, Luecken: {len(ir.get('sequence_gaps', []))}). "
            f"Erst Uebersetzung nachziehen (--from 53) oder bewusst weiter mit READLAYER_WEITER=1.")

    threshold = config.VALIDATION_THRESHOLD
    chapters = _collect_translatable(data, chapter)
    print(f"[stage55] Schwelle: {threshold} | Kapitel: {len(chapters)} "
          f"| Batch: {getattr(config,'BACKTRANS_BATCH_SIZE',25)}")

    flagged = []
    all_scores = []
    not_scored = []   # Tags, die nicht bewertet werden konnten

    for chapter_id, items in chapters.items():
        for lang in config.TARGET_LANGUAGES:
            # Nur Tags mit nichtleerer Uebersetzung in dieser Sprache
            bt_items = [(tid, tr[lang]) for tid, _, tr in items if tr.get(lang, "").strip()]
            back = _backtranslate(bt_items, lang)   # {tag_id: back}

            # Score-Paare nur fuer Tags, die zurueckuebersetzt wurden
            sc_items = []
            src_by_tag = {tid: s for tid, s, _ in items}
            for tid, _ in bt_items:
                if tid in back:
                    sc_items.append((tid, src_by_tag[tid], back[tid]))

            scores = _score(sc_items, lang)   # {tag_id: score}

            for tid, _, _ in sc_items:
                if tid in scores:
                    sc = scores[tid]
                    all_scores.append(sc)
                    if sc < threshold:
                        flagged.append((tid, lang, sc))
                else:
                    not_scored.append((tid, lang))

            # Tags ohne Rueckuebersetzung gelten ebenfalls als nicht bewertet
            for tid, _ in bt_items:
                if tid not in back:
                    not_scored.append((tid, lang))

        print(f"    {chapter_id}: geprueft")

    avg = round(sum(all_scores) / len(all_scores), 1) if all_scores else 0
    print(f"[stage55] Durchschnitts-Score: {avg} | bewertet: {len(all_scores)} "
          f"| unter Schwelle: {len(flagged)} | nicht bewertbar: {len(not_scored)}")
    if flagged:
        print(f"[stage55] Zur Nacharbeit markiert (erste 10):")
        for tag_id, lang, sc in flagged[:10]:
            print(f"    {tag_id} [{lang}] = {sc}")
    if not_scored:
        print(f"[stage55] Hinweis: {len(not_scored)} Tag/Sprache nicht bewertbar "
              f"(JSON/Antwort unvollstaendig) — Uebersetzung bleibt gueltig.")

    data["meta"]["quality_report"] = {
        "threshold": threshold,
        "average_score": avg,
        "scored_count": len(all_scores),
        "flagged": flagged,
        "not_scored": not_scored,
    }

    out_path = config.work_path(book_id, "330_rueckuebersetzung")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[stage55] Geschrieben: {out_path}")
    return data


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    book = args[0] if args else "jekyll-and-hyde"
    ch = None
    if "--chapter" in sys.argv:
        i = sys.argv.index("--chapter")
        ch = sys.argv[i+1] if i+1 < len(sys.argv) else None
    run(book, chapter=ch)
