"""STAGE 340 — Wort-Alignment
Funktion:     Ordnet jedem EN-Wort das DE-Fragment zu (Karaoke, Mitlesen).
Wirkungsweise: DeepSeek Flash liefert Index -> DE-Fragment; lokale Span-Suche, Luecken-Fallback, Komposita.
Komponenten:  pipeline/s340_wortalignment.py, api_layer
Zulieferer:   s310 Uebersetzung (work/310_uebersetzung.json)
Abnehmer:     s520 Wortzeiten, s710 Cloud-Export (work/340_wortalignment.json)
(Nomenklatur seit 18.10.2026, Uebersicht: docs/Pipeline_Strang_Matrix.xlsx)

--- Bisherige Beschreibung ---

READ LAYER — Stage 54a: Wort-Alignment (Zuordnung, nicht Uebersetzung)
========================================================================
Input:  data/work/<book_id>_stage03.json  (Translator-Output, EN+DE pro Tag)
Output: data/work/<book_id>_stage54a.json (dieselbe Struktur + "align"-Feld
        pro Tag: Liste von Wort-Ankern, EN-indexiert)

Ersetzt die alte Phrasen-Buendelung (freies Neu-Uebersetzen kleiner Haeppchen)
durch reine ZUORDNUNG: DeepSeek bekommt den EN-Satz UND den bereits fertigen
DE-Satz (aus 310_uebersetzung) und muss fuer jedes EN-Wort nur die Entsprechung im
GEGEBENEN DE-Satz FINDEN (verbatim kopieren), nicht neu uebersetzen. Vorteile
gegenueber der alten Version: konsistent mit dem Satz-Untertitel (keine
Zweit-Uebersetzung, die vom eigentlichen 310_uebersetzung-Text abweichen kann),
deterministisch verankerbar (EN- UND DE-Offsets), granularer (kein "1 bid =
ganzer Satz" mehr bei langen Saetzen).

VALIDIERT (17.07.2026, Call of the Wild, 1637 Saetze / 31754 Woerter):
  - 89,4% direkter Wortgrenzen-Treffer (inkl. case-insensitive Fallback)
  -  2,3% Luecken-Fallback (Funktionswort zwischen bestaetigten Nachbarn)
  -  0,04% Kompositum-Paar (zwei EN-Woerter -> ein deutsches Kompositum)
  -  5,2% vom Modell akzeptiert als "keine Entsprechung" (Funktionswort in
       Verbform/Konstruktion aufgeloest, z.B. "was brewing"->"zusammenbraute")
  -  3,0% echte Fehlschlaege (ueberwiegend FUNKTIONAL AEQUIVALENT zu obigem
       Fall, nur vom Modell falsch erraten statt korrekt als null erkannt -
       "of"->"von" geraten, obwohl im Satz gar keine Praeposition steht)
  Kosten: ~0,08 USD fuer das komplette Werk (deepseek-v4-flash, Cache-Hits
  auf den identischen Prompt-Instruktionsteil ueber alle Batches).

PROMPT-SCHAERFUNG (24.07.2026) — Grund:
  Die Messung mit mess_54a_verschiebung.py zeigte ~3% VERSCHOBENE Anker
  (Wort N traegt die Entsprechung von Wort N+1). Beispiel c001_00025:
      'the' -> 'Gras'  /  'grass,' -> 'herum'
  Ursache ist NICHT ein Positionsfehler, sondern Raten: liefert das Modell
  fuer ein aufgeloestes Funktionswort eine Woerterbuch-Vokabel statt null,
  trifft diese Vokabel manchmal zufaellig ein ANDERES Wort des DE-Satzes ->
  falscher Anker. In 1301 Faellen waere null die richtige Antwort gewesen.
  Der Prompt adressiert das jetzt direkt: Aufloesung wird mit Beispielen
  erklaert, Raten ausdruecklich als schaedlicher-als-null benannt, und die
  Nachbar-Verwechslung als eigene Regel behandelt. Gegengewicht, damit nicht
  zu viel genullt wird: Inhaltswoerter haben fast immer eine Entsprechung.

  Wirkung pruefen: nach dem Lauf mess_54a_verschiebung.py erneut laufen
  lassen und Detektor C sowie die Ankerzahl vergleichen.

WICHTIG fuer spaeteres Karaoke (Stage 58b MMS_FA-Erweiterung, vorgemerkt):
  Der EN-Wort-INDEX (Feld "i") und der EN-Wort-SPAN (Feld "en_span", Zeichen-
  Position im kanonischen EN-Satztext) MUESSEN stabil bleiben. Sobald Stage
  58b Wort-Zeitstempel per Forced Alignment auf den bereits satzweise
  zugeschnittenen LibriVox-Clips liefert, docken diese ueber genau diesen
  Index/Span an - OHNE eine zweite, inkompatible Nummerierung. Bitte diese
  Konvention nicht ohne Ruecksprache aendern.

ACHTUNG: Stage 60 (Cloud-Export) liest aktuell noch das ALTE "align"-Format
(bid-Liste mit en/de/en_span). Das neue Format hier hat ein anderes Schema
(word-Liste mit i/en/en_span/de/de_span/source). Stage 60 braucht nach
Einbau dieser Stage einen kleinen Anpassungs-Schritt - bewusst NICHT hier
mitgemacht (eigener, uebersichtlicher Schritt).
"""

import sys
import os
import re
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import api_layer


# ---------------------------------------------------------------------------
# EN-Tokenisierung (lokal, deterministisch - Modell bekommt nur Indizes)
# ---------------------------------------------------------------------------
def tokenize_en(text):
    return [{"i": i, "word": m.group(), "start": m.start(), "end": m.end()}
            for i, m in enumerate(re.finditer(r"\S+", text))]


# ---------------------------------------------------------------------------
# DE-Span-Suche: Wortgrenzen-sauber, mit case-insensitive Fallback
# ---------------------------------------------------------------------------
def _on_word_boundary(de_text, span):
    start, end = span
    before_ok = (start == 0) or not de_text[start - 1].isalpha()
    after_ok = (end == len(de_text)) or not de_text[end].isalpha()
    return before_ok and after_ok


def _boundary_candidates(de_text, fragment, ignore_case=False):
    hay = de_text.lower() if ignore_case else de_text
    needle = fragment.lower() if ignore_case else fragment
    candidates = []
    search_from = 0
    while True:
        idx = hay.find(needle, search_from)
        if idx == -1:
            break
        span = (idx, idx + len(fragment))
        if _on_word_boundary(de_text, span):
            candidates.append(span)
        search_from = idx + 1
    return candidates


def find_de_span(de_text, de_fragment, cursor):
    """Sucht de_fragment im de_text, NUR auf echten Wortgrenzen. Bevorzugt
    den ersten Treffer ab cursor (Lesereihenfolge bei Wiederholungen), faellt
    sonst auf den ersten Treffer im ganzen Satz zurueck (noetig, weil DE/EN-
    Wortstellung abweichen kann). Case-insensitive Fallback faengt EN-
    Satzanfangs-Grossschreibung, die im DE-Satz an anderer Stelle steht."""
    if not de_fragment:
        return None
    candidates = _boundary_candidates(de_text, de_fragment)
    if not candidates:
        candidates = _boundary_candidates(de_text, de_fragment, ignore_case=True)
    if not candidates:
        return None
    forward = [c for c in candidates if c[0] >= cursor]
    return forward[0] if forward else candidates[0]


def find_gap_fallback(de_text, prev_end, next_start, max_len=40):
    """Luecke zwischen dem vorherigen und dem naechsten BESTAETIGTEN Nachbar-
    Anker vorschlagen (faengt Funktionswoerter, die zwischen zwei bestaetigten
    Ankern liegen, aber vom Modell nicht wortgetreu kopiert wurden)."""
    if prev_end is None or next_start is None or next_start <= prev_end:
        return None
    gap = de_text[prev_end:next_start].strip()
    if not gap or len(gap) > max_len:
        return None
    return gap


_PUNCT_STRIP = re.compile(r"^[^\wÄÖÜäöüß]+|[^\wÄÖÜäöüß]+$")


def _clean_frag(s):
    return _PUNCT_STRIP.sub("", s) if s else s


def try_compound_pair(de_text, frag1, frag2):
    """Nur fuer direkt BENACHBARTE, sonst unaufgeloeste EN-Woerter: wenn ihre
    DE-Fragmente aneinandergehaengt ein wortgrenzen-sauberes deutsches Wort
    ergeben (z.B. 'Beeren'+'anpflanzungen'='Beerenanpflanzungen'), ist das ein
    echtes Kompositum, kein Zufallstreffer. Die Nachbarschafts-Bedingung
    schuetzt vor Kollisionen wie 'der' zufaellig in 'wieder'."""
    f1, f2 = _clean_frag(frag1), _clean_frag(frag2)
    if not f1 or not f2:
        return None
    combined = f1 + f2
    cands = _boundary_candidates(de_text, combined)
    if not cands:
        cands = _boundary_candidates(de_text, combined, ignore_case=True)
    return cands[0] if cands else None


def resolve_alignment(en_text, de_text, model_result):
    """Wendet alle drei Passes an (direkt -> Luecke -> Kompositum-Paar) und
    gibt die fertige 'words'-Liste fuers Output-Schema zurueck."""
    tokens = tokenize_en(en_text)

    rows = []
    cursor = 0
    for t in tokens:
        frag = model_result.get(str(t["i"]))
        span = find_de_span(de_text, frag, cursor) if frag else None
        if span:
            cursor = span[0]
        rows.append([t, frag, span, None, None])  # token, frag, span, gap, compound_span

    for i in range(len(rows)):
        t, frag, span = rows[i][0], rows[i][1], rows[i][2]
        if frag is not None and span is None:
            prev_end = next((rows[j][2][1] for j in range(i - 1, -1, -1) if rows[j][2]), None)
            next_start = next((rows[j][2][0] for j in range(i + 1, len(rows)) if rows[j][2]), None)
            rows[i][3] = find_gap_fallback(de_text, prev_end, next_start)

    i = 0
    while i < len(rows) - 1:
        unresolved_1 = rows[i][1] is not None and rows[i][2] is None and rows[i][3] is None
        unresolved_2 = rows[i + 1][1] is not None and rows[i + 1][2] is None and rows[i + 1][3] is None
        if unresolved_1 and unresolved_2:
            cspan = try_compound_pair(de_text, rows[i][1], rows[i + 1][1])
            if cspan:
                rows[i][4] = cspan
                rows[i + 1][4] = cspan
                i += 2
                continue
        i += 1

    # Schluessel je Sprachrichtung (22.10.2026): EN-Werk en/en_span/de/de_span wie bisher,
    # DE-Werk de/de_span/en/en_span. "en_text"/"de_text" heissen hier Quell-/Zieltext.
    k_src = config.SOURCE_LANGUAGE
    k_src_span, k_tgt, k_tgt_span = config.align_keys()
    words = []
    for t, frag, span, gap, cspan in rows:
        entry = {"i": t["i"], k_src: t["word"], k_src_span: [t["start"], t["end"]]}
        if frag is None:
            entry[k_tgt] = None
            entry["source"] = "none"
        elif span is not None:
            entry[k_tgt] = frag
            entry[k_tgt_span] = list(span)
            entry["source"] = "direct"
        elif gap is not None:
            entry[k_tgt] = gap
            entry["source"] = "gap_fallback"
        elif cspan is not None:
            entry[k_tgt] = de_text[cspan[0]:cspan[1]]
            entry[k_tgt_span] = list(cspan)
            entry["source"] = "compound_pair"
        else:
            entry[k_tgt] = frag
            entry["source"] = "unresolved"
        words.append(entry)
    return words


# ---------------------------------------------------------------------------
# Prompt-Bau + Batch-Call (Muster wie Stage 53 Translator)
# ---------------------------------------------------------------------------
def _build_prompt(items):
    """items = [(tag_id, quelltext, zieltext), ...]; Richtung aus config (22.10.2026)."""
    if config.SOURCE_LANGUAGE == "de":
        return _build_prompt_de_en(items)
    blocks = []
    for tag_id, en_text, de_text in items:
        tokens = tokenize_en(en_text)
        numbered = " ".join(f'[{t["i"]}]{t["word"]}' for t in tokens)
        blocks.append(
            f'ID {json.dumps(tag_id)}\n'
            f'EN (numbered words): {numbered}\n'
            f'DE (existing, already translated - do NOT retranslate): {json.dumps(de_text, ensure_ascii=False)}\n'
        )
    joined = "\n".join(blocks)

    return f"""You are NOT translating. You are locating existing text.

For each numbered EN word, find that word's counterpart inside the GIVEN
German sentence and copy it VERBATIM, character for character, exactly as it
appears there. The German sentence is fixed and already correct - never
retranslate, improve, or invent wording for it.

THE MOST IMPORTANT RULE - when to answer null:
German often dissolves an English word into another word or into the
grammar itself. When that happens there is NO fragment to point at, and
null is the CORRECT and expected answer. Examples of dissolution:
  EN "trouble was brewing"   DE "Unheil zusammenbraute"
      -> "was" is inside the verb form. "was" = null.
      (Answering "war" would be a dictionary guess - "war" is not there.)
  EN "in the grass"          DE "im Gras"
      -> "im" already contains the article. "the" = null.
  EN "a St. Bernard"         DE "ein Bernhardiner"
      -> "St." is absorbed into the compound. "St." = null.
Do NOT supply the word's usual dictionary translation when that translation
does not literally stand in the German sentence. A guessed word is far worse
than null, because it may coincidentally match a DIFFERENT word in the
sentence and anchor to the wrong place.

SECOND RULE - anchor to THAT word, never to its neighbour:
German word order differs from English, so the counterpart may sit far from
where the English word sits. That is fine. What is NOT fine is taking the
counterpart that belongs to the previous or next English word. Before you
answer, re-read your fragments in order and check that each one is the
counterpart of ITS OWN word. If word N and word N+1 would both point at the
same German word, at most one of them is right - give it to the word it
truly belongs to and answer null for the other.

Remaining rules:
- Content words (nouns, verbs, adjectives, adverbs, names) almost always DO
  have a counterpart. Look carefully before answering null for one.
- Function words (articles, prepositions, auxiliaries, particles) are the
  ones that frequently dissolve. Answer null freely for these.
- One EN word may map to several German words when they form one unit
  (e.g. "sun-kissed" -> "sonnenverwöhnt", "plunged" -> "tauchte ein").
  Keep the fragment as short as it can be while still being correct.
- Answer for every index. Do not skip any.
- Return only the index and the German fragment, never the English word.

Sentences:
{joined}

Return ONLY a JSON object, one entry per sentence ID, mapping each EN word
index (as string) to its German fragment (or null):
{{
  "<tag_id>": {{"0": "<german fragment or null>", "1": "...", ...}},
  ...
}}"""


def _build_prompt_de_en(items):
    """Spiegel des EN->DE-Prompts fuer deutsche Originale (Quelle DE, Ziel EN)."""
    blocks = []
    for tag_id, src_text, tgt_text in items:
        tokens = tokenize_en(src_text)
        numbered = " ".join(f'[{t["i"]}]{t["word"]}' for t in tokens)
        blocks.append(
            f'ID {json.dumps(tag_id)}\n'
            f'DE (numbered words): {numbered}\n'
            f'EN (existing, already translated - do NOT retranslate): {json.dumps(tgt_text, ensure_ascii=False)}\n'
        )
    joined = "\n".join(blocks)

    return f"""You are NOT translating. You are locating existing text.

For each numbered DE word, find that word's counterpart inside the GIVEN
English sentence and copy it VERBATIM, character for character, exactly as it
appears there. The English sentence is fixed and already correct - never
retranslate, improve, or invent wording for it.

THE MOST IMPORTANT RULE - when to answer null:
English often dissolves a German word into another word or into the
grammar itself. When that happens there is NO fragment to point at, and
null is the CORRECT and expected answer. Examples of dissolution:
  DE "Er zog sich an"        EN "He got dressed"
      -> the reflexive "sich" has no English word. "sich" = null.
  DE "Das ist doch klar"     EN "That's obvious"
      -> the particle "doch" is only tone. "doch" = null.
  DE "Sie hat gelacht"       EN "She laughed"
      -> "hat" is inside the past tense of "laughed". "hat" = null.
Do NOT supply the word's usual dictionary translation when that translation
does not literally stand in the English sentence. A guessed word is far worse
than null, because it may coincidentally match a DIFFERENT word in the
sentence and anchor to the wrong place.

SECOND RULE - anchor to THAT word, never to its neighbour:
English word order differs from German (verb-final clauses, separable
verbs), so the counterpart may sit far from where the German word sits.
That is fine. What is NOT fine is taking the counterpart that belongs to the
previous or next German word. Before you answer, re-read your fragments in
order and check that each one is the counterpart of ITS OWN word. If word N
and word N+1 would both point at the same English word, at most one of them
is right - give it to the word it truly belongs to and answer null for the other.

Remaining rules:
- Content words (nouns, verbs, adjectives, adverbs, names) almost always DO
  have a counterpart. Look carefully before answering null for one.
- Function words (articles, prepositions, auxiliaries, particles, reflexive
  pronouns) are the ones that frequently dissolve. Answer null freely for these.
- One DE word may map to several English words when they form one unit
  (e.g. "im" -> "in the", "Bernhardiner" -> "St. Bernard",
  "zusammenbraute" -> "was brewing"). Keep the fragment as short as it can be
  while still being correct.
- A separable verb prefix (e.g. "an" in "zog ... an") belongs to the same
  English fragment as its verb if it is part of that meaning; otherwise null.
- Answer for every index. Do not skip any.
- Return only the index and the English fragment, never the German word.

Sentences:
{joined}

Return ONLY a JSON object, one entry per sentence ID, mapping each DE word
index (as string) to its English fragment (or null):
{{
  "<tag_id>": {{"0": "<english fragment or null>", "1": "...", ...}},
  ...
}}"""


def _align_batch(items):
    approx_words = sum(len(tokenize_en(en)) for _, en, _ in items)
    max_tok = min(16000, max(2000, approx_words * 12))

    if config.RUN_MODE == "mock":
        raw = api_layer.call_model("aligner", "", items=items)
        try:
            return api_layer.parse_json(raw) or {}
        except Exception as e:
            print(f"      ! JSON-Fehler (mock): {e}")
            return {}

    prompt = _build_prompt(items)
    raw = api_layer.call_model("aligner", prompt, max_tokens=max_tok)
    try:
        parsed = api_layer.parse_json(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception as e:
        print(f"      ! JSON-Fehler: {e}")
        return {}


def align_chapter(items):
    """items = [(tag_id, en_text, de_text), ...] fuer EIN Kapitel.
    Gibt dict{tag_id: {index_str: de_fragment_or_None}} zurueck (roh, VOR
    der lokalen Nachbearbeitung durch resolve_alignment)."""
    wanted = [tid for tid, _, _ in items]
    batch_size = getattr(config, "ALIGN_BATCH_SIZE", 20)

    raw_results = {}
    n_batches = (len(items) + batch_size - 1) // batch_size
    for bi in range(n_batches):
        batch = items[bi * batch_size:(bi + 1) * batch_size]
        wanted_ids = {tid for tid, _, _ in batch}
        got = {}
        for attempt in range(1, 4):
            got = _align_batch(batch)
            covered = len([1 for tid in wanted_ids if got.get(tid)])
            if covered >= max(1, int(len(batch) * 0.7)):
                break
            if attempt < 3:
                print(f"      Batch {bi + 1}/{n_batches} duenn ({covered}/{len(batch)}), Versuch {attempt + 1} ...")
        raw_results.update(got)
        if n_batches > 1:
            done = len([t for t in wanted if t in raw_results])
            print(f"      Batch {bi + 1}/{n_batches}: {done}/{len(items)} gesamt")

    return raw_results


# ---------------------------------------------------------------------------
# Sammeln der noch zu alignenden Tags (nur solche mit fertigem EN+DE-Text,
# die NICHT schon in einem vorhandenen 340_wortalignment-Checkpoint aufgeloest sind)
# ---------------------------------------------------------------------------
def _collect_alignable(data, already_done, lang, chapter=None):
    src = config.SOURCE_LANGUAGE
    chapters = {}
    for tag_id, entry in data["content"].items():
        if entry.get("type") in config.NO_AUDIO_TYPES:
            continue
        if chapter and not tag_id.startswith(chapter):
            continue
        if tag_id in already_done:
            continue
        en_text = entry.get(src, "").strip()
        de_text = entry.get(lang, "").strip()
        if not en_text or not de_text:
            continue
        chapter_id = tag_id.split("_")[0]
        chapters.setdefault(chapter_id, []).append((tag_id, en_text, de_text))
    return chapters


def run(book_id: str, chapter: str = None) -> dict:
    src_path = config.work_path(book_id, "310_uebersetzung")
    print(f"[340_wortalignment] Lese Quelle: {src_path}")
    with open(src_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    out_path = config.work_path(book_id, "340_wortalignment")
    already_done = set()
    if os.path.exists(out_path):
        print(f"[340_wortalignment] Vorhandener Checkpoint gefunden: {out_path} - baue darauf auf.")
        with open(out_path, "r", encoding="utf-8") as f:
            prev = json.load(f)
        for tag_id, entry in prev.get("content", {}).items():
            if entry.get("align"):
                already_done.add(tag_id)
                if tag_id in data["content"]:
                    data["content"][tag_id]["align"] = entry["align"]

    total_new = 0
    for lang in config.TARGET_LANGUAGES:
        chapters = _collect_alignable(data, already_done, lang, chapter)
        if not chapters:
            print(f"[340_wortalignment] Sprache {lang}: nichts Neues zu alignen (alles schon im Checkpoint oder keine Uebersetzung vorhanden).")
            continue
        print(f"[340_wortalignment] Sprache {lang}: {len(chapters)} Kapitel, "
              f"{sum(len(v) for v in chapters.values())} Saetze neu.")

        for chapter_id, items in chapters.items():
            print(f"    {chapter_id}: {len(items)} Saetze")
            raw = align_chapter(items)
            for tag_id, en_text, de_text in items:
                model_result = raw.get(tag_id, {})
                words = resolve_alignment(en_text, de_text, model_result)
                data["content"][tag_id]["align"] = words
                total_new += 1

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[340_wortalignment] Geschrieben: {out_path} ({total_new} neu aligned)")
    return data


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    book = args[0] if args else "call-of-the-wild"
    ch = None
    if "--chapter" in sys.argv:
        i = sys.argv.index("--chapter")
        ch = sys.argv[i + 1] if i + 1 < len(sys.argv) else None
    run(book, chapter=ch)
