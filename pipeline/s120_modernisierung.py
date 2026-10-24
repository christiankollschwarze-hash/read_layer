"""STAGE 120 — Modernisierung
Funktion:     Sanfte Modernisierung des englischen Quelltexts.
Wirkungsweise: Kapitelweise in Chunks an DeepSeek (modernizer), Checkpoint je Kapitel; schreibt raw_modernized.txt mit ###-Marken.
Komponenten:  pipeline/s120_modernisierung.py, s620_epub_original (Kapitel-Extraktion), api_layer
Zulieferer:   s100 Anlegen (raw.txt)
Abnehmer:     s200 Tagging, s600 Klappentext, s620 ePub Original (work/modernized/chapter-N.json)
(Nomenklatur seit 18.10.2026, Uebersicht: docs/Pipeline_Strang_Matrix.xlsx)

--- Bisherige Beschreibung ---

READ LAYER — Modernisierung (Phase 1, vor EPUB + Uebersetzung)
==============================================================
Ueberfuehrt den viktorianischen EN-Originaltext in SANFT modernes Englisch:
Schachtelsaetze aufloesen, veraltete Vokabel modernisieren -- ABER Handlung,
Stimmung, Erzaehlstimme und Eigennamen wahren. Der modernisierte Text wird
zur EN-Quelle fuer BEIDE Ausgaenge (englisches EPUB + Uebersetzung).

Politik (CK): nur modernisiert (klassisch entfaellt als Ausgabe; raw.txt bleibt Archiv).
Rechtlich: modernisierter Text ist eine BEARBEITUNG (eigenes Copyright SOMNIO),
keine reine gemeinfreie Transkription -> Metadaten/Colophon spaeter anpassen.

Ausgabe: work/modernized/chapter-1..N.json  (Checkpoint pro Kapitel)
stage_11 (_load_chapters) und stage_13 ziehen diesen Text dann automatisch.

Aufruf:  python -m pipeline.stage_modernize jekyll-and-hyde
Gemini ist aus dem Container gesperrt -> echter Lauf laeuft lokal bei CK.
"""

import os, re, json
from config import config
from pipeline import s620_epub_original as epub

STAGE = "modernize"
CHUNK_CHARS = 3500
HR = "\u2014\u2014HR\u2014\u2014"

_SYS = (
    "You gently modernize a public-domain English literary text for contemporary "
    "readers and language learners. For each numbered segment: break up long, "
    "convoluted Victorian sentences into clearer, shorter ones; replace archaic or "
    "obscure vocabulary with natural modern English. PRESERVE the plot, meaning, "
    "narrative voice, tone, and ALL proper names. Do not summarize, omit, or add "
    "content; keep roughly the same length. Return each result on its own line, "
    "prefixed with the SAME number in the form [n], in the same order. "
    "Output ONLY the numbered lines."
)


def _modernize_segments(segments):
    """Liste Textsegmente -> sanft modernisiert (gleiche Anzahl/Reihenfolge).
    HR-Marker werden durchgereicht."""
    idx_map = [i for i, s in enumerate(segments) if s != HR]
    payload = [segments[i] for i in idx_map]
    out = list(segments)

    groups, cur, size = [], [], 0
    for i, s in enumerate(payload):
        if cur and size + len(s) > CHUNK_CHARS:
            groups.append(cur); cur, size = [], 0
        cur.append((i, s)); size += len(s)
    if cur:
        groups.append(cur)

    done = {}
    for grp in groups:
        numbered = "\n".join(f"[{n}] {s}" for n, s in grp)
        if config.RUN_MODE == "mock":
            for n, s in grp:
                done[n] = f"[MOD] {s}"      # Platzhalter: Mechanik testen
            continue
        raw = _call_model(_SYS + "\n\n" + numbered)
        for m in re.finditer(r"\[(\d+)\]\s*(.*?)(?=\n\[\d+\]|\Z)", raw, re.S):
            done[int(m.group(1))] = m.group(2).strip()

    for local_i, orig_i in enumerate(idx_map):
        out[orig_i] = done.get(local_i, segments[orig_i])
    return out


def _call_model(prompt: str) -> str:
    """Modernisierung ueber den gemeinsamen api_layer. Modell = config.MODELS['modernizer'];
    fehlt der Eintrag, wird das translator-Modell genutzt (gleicher v4-pro-Wunsch)."""
    from pipeline import api_layer
    if "modernizer" not in config.MODELS:
        config.MODELS["modernizer"] = config.MODELS.get("translator", "deepseek-v4-pro")
    return api_layer.call_model("modernizer", prompt, temperature=0.3)


def run(book_id: str):
    chapters = epub._extract_chapters_from_raw(book_id)   # Rohkapitel (vor Mobil-Split)
    out_dir = os.path.join(config.work_dir(book_id), "modernized")
    os.makedirs(out_dir, exist_ok=True)

    # 18.10.2026: LibriVox-Modus (Original 1:1 fuer fremde Aufnahme) archiviert.
    print(f"[modernize] {len(chapters)} Kapitel, modernisiere (sanft) ...")

    for i, (title, paras) in enumerate(chapters, 1):
        cp = os.path.join(out_dir, f"chapter-{i}.json")
        if os.path.exists(cp):
            print(f"  [{i}/{len(chapters)}] aus Checkpoint")
            continue
        mod = _modernize_segments(list(paras))   # Titel bleibt unveraendert (sanft)
        json.dump({"title": title, "paragraphs": mod},
                  open(cp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"  [{i}/{len(chapters)}] modernisiert ({len(mod)} Absaetze)")

    print(f"[modernize] fertig -> {out_dir}")
    src = _write_marked_source(book_id, out_dir)
    print(f"[modernize] kanonische Quelle -> {src}")
    print("[modernize] HINWEIS: EPUB/Uebersetzung nutzen den modernisierten Text automatisch.")
    return out_dir


def _book_title(book_id: str) -> str:
    bp = os.path.join(config.book_dir(book_id), "book.json")
    if os.path.exists(bp):
        try:
            b = json.load(open(bp, encoding="utf-8"))
            return b.get("titel_original") or b.get("title") or book_id
        except Exception:
            pass
    return book_id


def _author_name(book_id: str) -> str:
    try:
        slug = config.author_of(book_id)
        ap = os.path.join(config.author_dir(slug), "author.json")
        return json.load(open(ap, encoding="utf-8")).get("name_display", "")
    except Exception:
        return ""


def _write_marked_source(book_id: str, mod_dir: str) -> str:
    """Schreibt aus den Kapitel-Checkpoints EINE kanonische Volltextdatei
    raw_modernized.txt mit ###TITLE###/###AUTHOR###/###CHAPTER###-Marken.
    Diese Datei ist die EINE englische Wahrheit -- EPUB UND Tagger (Audio)
    lesen perspektivisch daraus. Robust auch bei Resume (liest von Platte)."""
    M = config.MARKERS
    files = [f for f in os.listdir(mod_dir) if re.fullmatch(r"chapter-\d+\.json", f)]
    files.sort(key=lambda f: int(re.search(r"\d+", f).group()))

    book_title  = _book_title(book_id)
    author_name = _author_name(book_id)
    lines = [f'{M["title"]} {book_title}',
             f'{M["author"]} {author_name}', ""]
    for idx, f in enumerate(files):
        d = json.load(open(os.path.join(mod_dir, f), encoding="utf-8"))
        paras = [p for p in d.get("paragraphs", []) if p and p != "\u2014\u2014HR\u2014\u2014"]
        if idx == 0:
            before = len(paras)
            paras = epub.strip_leading_front_matter(paras, book_title, author_name)
            if len(paras) < before:
                print(f"[modernize] Front-Matter entfernt: {before - len(paras)} "
                      f"Vorspann-Absaetze (Titelblock) aus Kapitel 1.")
        if idx == len(files) - 1:
            paras = epub.strip_trailing_end_marker(paras)
        lines.append(f'{M["chapter"]} {d.get("title", "").strip()}')
        lines.append("")
        for p in paras:
            lines.append(p)
            lines.append("")
    out_path = os.path.join(config.book_dir(book_id), "raw_modernized.txt")
    open(out_path, "w", encoding="utf-8").write("\n".join(lines).strip() + "\n")
    return out_path


if __name__ == "__main__":
    import sys
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    run(args[0] if args else "jekyll-and-hyde")
