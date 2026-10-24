"""STAGE 200 — Tagging
Funktion:     Zerlegt den Text in Kapitel und Satz-Tags (s, dl, p, qt ...).
Wirkungsweise: Je Kapitel ein DeepSeek-Aufruf, bei Fehlern rekursive Halbierung; Tag-IDs deterministisch neu vergeben.
Komponenten:  pipeline/s200_tagging.py, api_layer
Zulieferer:   s120 Modernisierung bzw. s150 ePub-Import (raw_modernized.txt)
Abnehmer:     s210 Profil (work/200_tagging.json) und mittelbar alle Folgestufen
(Nomenklatur seit 18.10.2026, Uebersicht: docs/Pipeline_Strang_Matrix.xlsx)

--- Bisherige Beschreibung ---

READ LAYER — Stage 00: Tagger
=============================
Input:  data/raw/<book_id>_marked.txt   (manuell mit ###MARKER### versehen)
Output: data/work/<book_id>_stage00.json

Aufgabe: Marked-Text parsen, jedes Kapitel in Tags segmentieren.
Nichts ist auf einen bestimmten Titel hartcodiert — alles kommt aus
book_id und der Eingabedatei.
"""

import sys
import os
import json
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import api_layer


# ============================================================
# PARSER: ###MARKER###-Datei -> Struktur
# ============================================================

def parse_marked_file(text: str) -> dict:
    """
    Liest eine mit ###MARKER### versehene Datei.
    Gibt {title, author, chapters:[{title, text}]} zurueck.
    """
    M = config.MARKERS
    title, author = "", ""
    chapters = []
    cur_title = None
    cur_lines = []

    for line in text.splitlines():
        s = line.strip()
        if s.startswith(M["title"]):
            title = s.replace(M["title"], "").strip()
        elif s.startswith(M["author"]):
            author = s.replace(M["author"], "").strip()
        elif s.startswith(M["chapter"]):
            if cur_title is not None:
                body = "\n".join(cur_lines).strip()
                if body:
                    chapters.append({"title": cur_title, "text": body})
            cur_title = s.replace(M["chapter"], "").strip()
            cur_lines = []
        else:
            if cur_title is not None:
                cur_lines.append(line)

    if cur_title is not None:
        body = "\n".join(cur_lines).strip()
        if body:
            chapters.append({"title": cur_title, "text": body})

    return {"title": title, "author": author, "chapters": chapters}


def _new_tag_id(chapter_num: int, seq: int, typ: str) -> str:
    """Neues Schema: c<kapitel>_<global-sequenz>_<typ>  (z.B. c001_00005_dl).
    Global pro Kapitel durchnummeriert -> WAV-Dateien sortieren nach Vorlesefolge."""
    cd, sd = config.CHAPTER_DIGITS, config.SEQUENCE_DIGITS
    return f"c{chapter_num:0{cd}d}_{seq:0{sd}d}_{typ}"


def _renumber_chapter(chapter_num: int, chapter_title: str, content: dict) -> dict:
    """Nimmt die Tags des Modells (oder Mock) in IHRER REIHENFOLGE und vergibt
    die IDs NEU -- global durchnummeriert. Typ + Text bleiben, die ID wird
    deterministisch gesetzt. So kann das Modell die Sequenz nicht verpfuschen.

    SINGLE SOURCE OF TRUTH (Kapitel-Header):
    Der Kapitel-Header ist eine HARTE Tatsache aus der ###CHAPTER###-Marke
    (= chapter_title, = meta.chapters). Er wird hier DETERMINISTISCH als
    ERSTER Knoten des Kapitels gesetzt (c<N>_00001_h) -- NICHT vom LLM.
    Etwaige vom Modell gelieferte h-Knoten werden VERWORFEN (keine Doppelung,
    keine LLM-Streuung). Alle nachgelagerten Stages (53, 58, 58b, 60) ordnen
    sich dieser Wahrheit unter: 58b konstruiert KEINEN eigenen Header mehr,
    sondern schneidet den h-Knoten aus dem content."""
    src = config.SOURCE_LANGUAGE
    # LLM-Header verwerfen -- der Header kommt allein aus chapter_title.
    body = [(tid, e) for tid, e in content.items() if e.get("type") != "h"]
    out = {}
    seq = 1
    # 1) Kanonischer Header als erster Knoten.
    out[_new_tag_id(chapter_num, seq, "h")] = {"type": "h", src: chapter_title.strip()}
    seq += 1
    # 2) Restliche Knoten in Modell-Reihenfolge neu durchnummerieren.
    for _old_id, entry in body:
        typ = entry.get("type", "s")
        out[_new_tag_id(chapter_num, seq, typ)] = entry
        seq += 1
    return out


# ============================================================
# TAGGER-PROMPT
# ============================================================

def _build_tagger_prompt(chapter_num: int, chapter_title: str, chapter_text: str) -> str:
    types_desc = "\n".join(
        f"  {k:5s} = {_type_description(k)}" for k in config.TAG_TYPES
    )
    cd = config.CHAPTER_DIGITS
    sd = config.SEQUENCE_DIGITS
    src = config.SOURCE_LANGUAGE

    return f"""You are a precise text segmentation engine for a multilingual audiobook platform.

Tag ONE CHAPTER of a clean literary text as structured JSON.

OUTPUT FORMAT — return ONLY this, no explanation, no markdown:
{{
  "content": {{
    "<tag_id>": {{ "type": "<tag_type>", "{src}": "<text content>" }}
  }}
}}

TAG ID SCHEMA: c<chapter>_<sequence>_<type>
- Chapter: {cd} digits as provided (e.g. c{chapter_num:0{cd}d})
- Sequence: {sd} digits, a SINGLE running counter across ALL types, starting at {'0'*(sd-1)}1
- Type suffix: the tag type (s, dl, h, ...) at the END
- Example order: c{chapter_num:0{cd}d}_00001_h, c{chapter_num:0{cd}d}_00002_p, c{chapter_num:0{cd}d}_00003_s, c{chapter_num:0{cd}d}_00004_dl
(IDs are re-numbered programmatically afterwards; just keep them in reading order.)

TAG TYPES:
{types_desc}

DIALOG RULE — apply strictly:
  dl = the ENTIRE text starts with an opening quote and ends with a closing quote — nothing before or after
  s  = everything else, even if it contains quoted speech

PARAGRAPH BREAKS:
  Insert type "p" at every paragraph boundary. The text field must be "".

QUALITY:
  Never merge two sentences into one tag.
  Never split one sentence across two tags.
  Preserve original spelling and punctuation exactly.

CHAPTER HEADING — do NOT emit:
  Do NOT create any "h" (heading) tag. The chapter heading is added
  deterministically by the pipeline from the chapter marker. Start tagging
  with the FIRST body element after the heading. Ignore the chapter_title
  line for tagging purposes -- it is context only.

chapter_number: c{chapter_num:0{cd}d}
chapter_title: {chapter_title}

--- CHAPTER START ---
{chapter_text.strip()}
--- CHAPTER END ---"""


def _type_description(t: str) -> str:
    return {
        "s":    "narrative sentence (default)",
        "h":    "chapter heading or section title",
        "dl":   "dialog line (standalone quoted speech)",
        "qt":   "block quotation, inscription, sign",
        "p":    'paragraph break (text = "", no audio)',
        "fn":   "footnote",
        "ep":   "epigraph",
        "tt":   "title page element",
        "skip": "decorative separators, page numbers (no audio)",
    }.get(t, "")


# ============================================================
# MOCK-TAGGER (strukturtreu)
# ============================================================
# Im Mock-Modus liefert das LLM keine echte Segmentierung. Damit die
# Pipeline trotzdem realistische Tags bekommt, segmentiert dieser
# deterministische Fallback den Text lokal in Saetze.

def _mock_tag_chapter(chapter_num: int, title: str, text: str) -> dict:
    import re
    cd, sd = config.CHAPTER_DIGITS, config.SEQUENCE_DIGITS
    src = config.SOURCE_LANGUAGE
    content = {}
    seq = 1

    def tag_id(prefix):
        return f"c{chapter_num:0{cd}d}_{prefix}{seq:0{sd}d}"

    # KEIN Heading hier -- der Header wird zentral in _renumber_chapter aus
    # chapter_title gesetzt (Single Source of Truth). Mock liefert nur den Body.
    content[tag_id("p")] = {"type": "p", src: ""}
    seq += 1

    # Naive Satzsegmentierung (nur fuer Mock-Struktur, nicht fuer Qualitaet)
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        # dl-Regel: beginnt und endet mit Anfuehrungszeichen
        is_dl = (sent[0] in '"\u201c' and sent[-1] in '"\u201d')
        prefix = "dl" if is_dl else "s"
        content[tag_id(prefix)] = {"type": prefix, src: sent}
        seq += 1

    return {"content": content}


# ============================================================
# TAGGER (live ueber api_layer)
# ============================================================

def _tag_robust(chapter_num: int, title: str, text: str, tiefe: int = 0) -> dict:
    """11.10.2026: Lange Kapitel (z. B. Akt eines Dramas) liefern teils kaputtes JSON.
    Ein Wiederholungsversuch, danach Kapiteltext an Absatzgrenze halbieren und
    Teile einzeln taggen (Reihenfolge bleibt; IDs vergibt _renumber_chapter neu)."""
    fehler = None
    for _ in range(2):
        try:
            raw = api_layer.call_model("tagger", _build_tagger_prompt(chapter_num, title, text), max_tokens=65000)
            res = api_layer.parse_json(raw)
            if isinstance(res, dict) and res.get("content"):
                return res
            fehler = "leere Antwort"
        except Exception as e:
            fehler = e
    absaetze = [a for a in re.split(r"\n\s*\n", text) if a.strip()]
    if tiefe >= 4 or len(absaetze) < 2:
        raise ValueError(f"Tagger-Antwort nicht parsebar ({str(fehler)[:120]})")
    mitte = len(absaetze) // 2
    print(f"    [stage50] Kapitel {chapter_num}: JSON fehlerhaft -> in 2 Teile geteilt (Ebene {tiefe + 1})")
    inhalt = {}
    for teil in ("\n\n".join(absaetze[:mitte]), "\n\n".join(absaetze[mitte:])):
        r = _tag_robust(chapter_num, title, teil, tiefe + 1)
        for k, v in r.get("content", {}).items():
            inhalt[f"t{len(inhalt):06d}_{k}"] = v   # eindeutige Schluessel, Reihenfolge wahren
    return {"content": inhalt}


def tag_chapter(chapter_num: int, title: str, text: str) -> dict:
    if config.RUN_MODE == "mock":
        result = _mock_tag_chapter(chapter_num, title, text)
    else:
        result = _tag_robust(chapter_num, title, text)
    # IDs ZENTRAL neu vergeben (global, Typ-Suffix) -- unabhaengig davon, welche
    # IDs das Modell geliefert hat. Reihenfolge des Modells bleibt erhalten.
    # Der Kapitel-Header wird hier deterministisch aus 'title' gesetzt (SSoT).
    result["content"] = _renumber_chapter(chapter_num, title, result.get("content", {}))
    return result


# ============================================================
# HAUPTPROZESS
# ============================================================

def _source_path(book_id: str) -> str:
    """Kanonische Quelle bevorzugen: raw_modernized.txt (von Stage 11 erzeugt,
    bereits mit ###TITLE###/###AUTHOR###/###CHAPTER###-Marken). Faellt auf das
    klassische raw.txt zurueck, falls noch nicht modernisiert wurde."""
    mod = os.path.join(config.book_dir(book_id), "raw_modernized.txt")
    if os.path.exists(mod):
        return mod
    return config.raw_path(book_id, "marked.txt")


def run(book_id: str) -> dict:
    in_path = _source_path(book_id)
    print(f"[stage50] Lese: {in_path}")
    with open(in_path, "r", encoding="utf-8") as f:
        marked = f.read()

    parsed = parse_marked_file(marked)
    print(f"[stage50] Titel:   {parsed['title']}")
    print(f"[stage50] Autor:   {parsed['author']}")
    print(f"[stage50] Kapitel: {len(parsed['chapters'])}")

    if not parsed["chapters"]:
        raise ValueError("Keine Kapitel gefunden — ###CHAPTER###-Marker pruefen.")

    all_content = {}
    chapters_meta = {}
    for i, ch in enumerate(parsed["chapters"], 1):
        print(f"  Kapitel {i}/{len(parsed['chapters'])}: {ch['title']}")
        result = tag_chapter(i, ch["title"], ch["text"])
        content = result.get("content", {})
        all_content.update(content)
        chapters_meta[f"c{i:0{config.CHAPTER_DIGITS}d}"] = ch["title"]
        print(f"    -> {len(content)} Tags")

    final = {
        "book_id": book_id,
        "meta": {
            "title": parsed["title"],
            "author": parsed["author"],
            "source_language": config.SOURCE_LANGUAGE,
            "target_languages": config.TARGET_LANGUAGES,
            "chapters": chapters_meta,
        },
        "content": all_content,
    }

    out_path = config.work_path(book_id, "200_tagging")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)

    print(f"[stage50] Geschrieben: {out_path}")
    print(f"[stage50] Kapitel: {len(chapters_meta)} | Tags gesamt: {len(all_content)}")
    return final


if __name__ == "__main__":
    book = sys.argv[1] if len(sys.argv) > 1 else "aesop_three_fables"
    run(book)
