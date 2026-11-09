"""STAGE 200 — Tagger (Umbau Phase 2, GATE_KATALOG.md Zeile 200, 02.11.2026)
Funktion:     Zerlegt raw_modernized.txt je Kapitel in Knoten (s, dl, p, qt, vs, h ...), ein Knoten = ein Satz.
Wirkungsweise: Je Kapitel ein DeepSeek-Aufruf (bei kaputtem JSON rekursive Halbierung); Rohergebnis als Checkpoint
              work/ckpt/200/c<N>__<lg>.json (Eingang = Kapiteltitel + Text). Danach deterministisch und kostenlos:
              satzweise nachtrennen (tools/satzweise.py, Abkuerzungen je Sprache + je Werk), Header aus der Marke,
              IDs neu, gespeicherte Korrekturen (work/200_korrekturen.json) anwenden.
Eingang:      raw_modernized.txt (###TITLE/AUTHOR/CHAPTER###), Gate 190 (Kapitelzahl), book.json (quellsprache, abkuerzungen).
Ausgabe:      work/200_tagging.json (Format unveraendert fuer 210 ff.), work/200_pruefung.json (Gegenueberstellung,
              Mehrsatz-Liste, ueberlange Knoten), Gate in status.json.
Gate:         Kapitelzahl = 190 (Stopp, -> 120); Kapitel ohne Text (Stopp, -> 120); leere Knoten / unbekannte Typen (Stopp);
              Treue je Kapitel >= 99,5 % Wortuebereinstimmung -> sonst 1x automatisch neu taggen, dann Mensch;
              Mehrsatz-Knoten = 0 (sonst Mensch, manuelle Knoten ausgenommen); Knoten > 400 Zeichen nur Hinweis;
              Mock im Live-Lauf Stopp. Mensch-Freigabe bleibt bei unveraenderter Ausgabe (ausgabe_hash) gueltig.
Kosten:       DeepSeek (config.MODELS tagger) nur fuer Kapitel ohne aktuellen Checkpoint; Korrekturen/Abkuerzungen 0 $.
Regler:       --modell, --kapitel N|alle (neu taggen), --teilen ID@STELLE, --zusammen ID, --typ ID=TYP,
              --abk WORT / --abk-weg WORT (je Werk; je Sprache: config/abk_<lg>.txt), --lang N (Grenze ueberlang),
              --uebernehmen (vorhandene 200_tagging.json als Rohergebnis, ohne LLM), --trocken (Probe, schreibt nichts).
Aufruf:
  python -m pipeline.s200_tagging <werk> [Regler] [--wer CK]
Exit: 0 auto, 2 Stopp, 3 Mensch, 1 Fehler.
"""

import argparse
import copy
import difflib
import sys
import os
import json
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import api_layer, bestellung, gate, manifest, mock, s190_vertrag, status
from tools import satzweise


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
        # AP 58: Versmarke -> Typ vs, Marke entfernen (deterministisch, unabhaengig vom LLM)
        _t = str(entry.get(config.SOURCE_LANGUAGE, "") or "").lstrip()
        if _t.startswith(config.VERS_MARKE):
            entry["type"] = "vs"
            entry[config.SOURCE_LANGUAGE] = _t[len(config.VERS_MARKE):].strip()
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

VERSE RULE (songs, poems, hums):
  A paragraph that starts with the marker {config.VERS_MARKE} is ONE verse stanza.
  Emit exactly ONE tag of type "vs" for it. Keep the marker at the start of the text
  and keep its line breaks as \\n. Never split a stanza, never merge it with prose.

QUALITY:
  ONE SENTENCE PER TAG. ".", "!" and "?" end a sentence. Only exception: direct speech may keep
  its speech tag ("Help!" cried Alice.) or a short announcing clause (Then Pooh said: "Hello.").
  A paragraph with five sentences becomes five tags.
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
        "vs":   "verse/song stanza (lines kept, separated by \\n)",
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
    print(f"    [200] Kapitel {chapter_num}: JSON fehlerhaft -> in 2 Teile geteilt (Ebene {tiefe + 1})")
    inhalt = {}
    for teil in ("\n\n".join(absaetze[:mitte]), "\n\n".join(absaetze[mitte:])):
        r = _tag_robust(chapter_num, title, teil, tiefe + 1)
        for k, v in r.get("content", {}).items():
            inhalt[f"t{len(inhalt):06d}_{k}"] = v   # eindeutige Schluessel, Reihenfolge wahren
    return {"content": inhalt}


def _satzweise(content: dict, abk=None, src=None) -> dict:
    """CK 01.11.2026: Ein Tag = ein Satz. Das LLM fasst gelegentlich ganze Absaetze zusammen
    (Befund Winnie-the-Pooh c007_00133_dl, 5 Saetze). Hier deterministisch nachtrennen nach der
    Regel in tools/satzweise.py (.!? beenden; Ausnahme Redebegleitsatz / ankuendigender Satz).
    src: Werksprache (09.11.2026: vorher immer config.SOURCE_LANGUAGE -> DE-Originale nicht nachgetrennt)."""
    src = src or config.SOURCE_LANGUAGE
    out = {}
    for tid, e in content.items():
        typ = e.get("type", "s")
        text = e.get(src) or ""
        teile = satzweise.teile_text(text, src, abk) if typ in satzweise.TEILBARE_TYPEN else [text]
        if len(teile) <= 1:
            out[tid] = e
            continue
        for k, t in enumerate(teile):
            neu = dict(e)
            neu[src] = t
            if typ in ("s", "dl"):
                rede = t[:1] in satzweise.OEFFNER and t[-1:] in satzweise.SCHLIESSER
                neu["type"] = "dl" if rede else "s"
            out[tid if k == 0 else f"{tid}__{k + 1}"] = neu
    return out


def tag_chapter(chapter_num: int, title: str, text: str) -> dict:
    if config.RUN_MODE == "mock":
        result = _mock_tag_chapter(chapter_num, title, text)
    else:
        result = _tag_robust(chapter_num, title, text)
    vorher = len(result.get("content", {}))
    result["content"] = _satzweise(result.get("content", {}))
    if len(result["content"]) != vorher:
        print(f"    [satzweise] {len(result['content']) - vorher} Tags nachgetrennt")
    # IDs ZENTRAL neu vergeben (global, Typ-Suffix) -- unabhaengig davon, welche
    # IDs das Modell geliefert hat. Reihenfolge des Modells bleibt erhalten.
    # Der Kapitel-Header wird hier deterministisch aus 'title' gesetzt (SSoT).
    result["content"] = _renumber_chapter(chapter_num, title, result.get("content", {}))
    return result


# ============================================================
# PHASE 2 (02.11.2026): Gate, Checkpoints je Kapitel, Regler
# ============================================================

STAGE = "200"
TREUE_MIN = 0.995
LANG_MAX = 400
OHNE_TEXT = {"p", "skip"}
_W = re.compile(r"[\w’']+", re.UNICODE)
PROMPT_ZEICHEN = 4000   # Tagger-Prompt ohne Kapiteltext (Schaetzung)
AUS_FAKTOR = 1.6        # JSON-Ausgabe je Eingabe-Token (Schaetzung)


def kosten_schaetzen(zeichen, modell=None):
    """Schaetzung Neu-Taggen in $ (Peak-Preis, ohne Cache; Token ~ Zeichen/4)."""
    p = getattr(config, "PREISE", {}).get(modell or config.MODELS.get("tagger")) or {}
    return ((PROMPT_ZEICHEN + zeichen) / 4 * p.get("in", 0) + zeichen / 4 * AUS_FAKTOR * p.get("out", 0)) / 1e6


def trennstelle(text, teil2):
    """Kuerzester Anfang von teil2 (ganze Woerter, ab 8 Zeichen), dessen erstes Vorkommen in text
    die Trennstelle ist -> Wert fuer --teilen ID@STELLE; None, wenn nicht eindeutig findbar."""
    pos = text.find(teil2, 1)
    if pos <= 0:
        return None
    for n in range(min(8, len(teil2)), len(teil2) + 1):
        if n < len(teil2) and not teil2[n].isspace():
            continue
        if text.find(teil2[:n]) == pos:
            return teil2[:n]
    return None


def _hash(o):
    return manifest.hash_obj(o)


def abk_liste(werk, b, lg):
    """Zusaetzliche Abkuerzungen: config/abk_<lg>.txt (je Ausgangssprache) + book.json abkuerzungen (je Werk)."""
    out = set()
    p = os.path.join(os.path.dirname(os.path.abspath(config.__file__)), f"abk_{lg}.txt")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            out |= {z.strip().lower().rstrip(".") for z in f if z.strip() and not z.startswith("#")}
    out |= {str(a).strip().lower().rstrip(".") for a in (b.roh.get("abkuerzungen") or []) if str(a).strip()}
    return sorted(out)


def _woerter(s):
    out = (w.lower().replace("’", "'").strip("'") for w in _W.findall((s or "").replace(config.VERS_MARKE, " ")))
    return [w for w in out if w]


def treue(kaptext, knoten, src):
    """Wortuebereinstimmung Kapiteltext <-> zusammengesetzte Knotentexte (ohne h) -> (quote, beispiele)."""
    a = _woerter(kaptext)
    bb = _woerter(" ".join(e.get(src) or "" for e in knoten.values() if e.get("type") != "h"))
    if not a and not bb:
        return 1.0, []
    sm = difflib.SequenceMatcher(None, a, bb, autojunk=False)
    m = sum(x.size for x in sm.get_matching_blocks())
    bsp = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op != "equal" and len(bsp) < 5:
            bsp.append({"op": op, "text": " ".join(a[max(0, i1 - 3):i2 + 3]),
                        "knoten": " ".join(bb[max(0, j1 - 3):j2 + 3])})
    return m / max(len(a), len(bb)), bsp


def nachbearbeiten(n, titel, roh, src, abk):
    """LLM-Rohergebnis -> satzweise nachtrennen, Header setzen, IDs vergeben (deterministisch, kostenlos)."""
    content = _satzweise(copy.deepcopy(roh), abk, src)
    return _renumber_chapter(n, titel, content)


def _tag_llm(n, titel, text, modell):
    alt = config.MODELS.get("tagger")
    if modell:
        config.MODELS["tagger"] = modell
    try:
        res = _mock_tag_chapter(n, titel, text) if config.RUN_MODE == "mock" else _tag_robust(n, titel, text)
    finally:
        config.MODELS["tagger"] = alt
    return res.get("content", {})


# ------------------------------------------------------------ Korrekturen (Regler)
def _korr_pfad(werk):
    return os.path.join(config.work_dir(werk), "200_korrekturen.json")


def korrekturen_lesen(werk):
    p = _korr_pfad(werk)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def korrektur_anwenden(n, titel, knoten, k, src):
    """Eine Korrektur auf ein Kapitel (Knoten in Reihenfolge). -> neue Knoten; ValueError bei Fehler.
    Manuell entstandene Knoten tragen _m (zaehlen nicht als Mehrsatz)."""
    ids = list(knoten)
    if k["id"] not in knoten:
        raise ValueError(f"Knoten {k['id']} nicht gefunden")
    i = ids.index(k["id"])
    e = dict(knoten[k["id"]])
    liste = [dict(knoten[x]) for x in ids]
    if k["op"] == "typ":
        if k["arg"] not in config.TAG_TYPES:
            raise ValueError(f"Typ {k['arg']!r} unbekannt")
        liste[i]["type"] = k["arg"]
    elif k["op"] == "teilen":
        t = e.get(src) or ""
        pos = t.find(k["arg"])
        if pos <= 0:
            raise ValueError(f"Stelle {k['arg']!r} nicht im Knoten (oder am Anfang)")
        a, b = dict(e, **{src: t[:pos].strip(), "_m": 1}), dict(e, **{src: t[pos:].strip(), "_m": 1})
        liste[i:i + 1] = [a, b]
    elif k["op"] == "zusammen":
        j = next((x for x in range(i + 1, len(liste)) if liste[x].get("type") not in OHNE_TEXT), None)
        if j is None or e.get("type") in OHNE_TEXT | {"h"}:
            raise ValueError(f"{k['id']}: kein Folgeknoten zum Zusammenfuehren")
        liste[i] = dict(e, **{src: f"{e.get(src, '').strip()} {liste[j].get(src, '').strip()}", "_m": 1})
        del liste[j]
    else:
        raise ValueError(f"Operation {k['op']!r} unbekannt")
    body = {f"x{z:06d}": v for z, v in enumerate(liste) if v.get("type") != "h"}
    return _renumber_chapter(n, titel, body)


# ------------------------------------------------------------ Bestand uebernehmen
def bestand_roh(werk, src):
    """Vorhandene 200_tagging.json -> {kapitel_n: content ohne h} (fuer --uebernehmen, ohne LLM)."""
    p = config.work_path(werk, "200_tagging")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    out = {}
    for tid, e in (d.get("content") or {}).items():
        m = re.match(r"c(\d+)_", tid)
        if not m or e.get("type") == "h":
            continue
        out.setdefault(int(m.group(1)), {})[tid] = {k: v for k, v in e.items() if k in ("type", src)}
    return out


# ------------------------------------------------------------ Lauf
def _kap_190(werk, d, n_marken):
    m = ((d["stages"].get("190") or {}).get("metriken") or {}).get("kapitel")
    if m is not None:
        return m, "Gate 190"
    cps, _ = s190_vertrag.checkpoints(werk)
    return (len(cps) if cps else n_marken), "chapter-N.json"


def run(werk, wer=None, modell=None, kapitel=None, abk=None, abk_weg=None, lang_max=LANG_MAX,
        teilen=None, zusammen=None, typ=None, uebernehmen=False, trocken=False):
    """kapitel: Liste von Nummern (neu taggen) oder ['alle']. teilen: ['ID@STELLE'], zusammen: ['ID'],
    typ: ['ID=TYP']. trocken: nichts schreiben, kein LLM (Probe am Bestand)."""
    wer = wer or "pipeline"
    g = gate.Gate(werk, STAGE, ruecksprung="200", wer=wer)
    d = status.laden(werk)
    b = bestellung.lesen(werk)
    src = b.quellsprache or config.SOURCE_LANGUAGE
    g.metrik("sprache", src)

    if b.roh.get("geteilt_in"):
        g.pflicht("nicht_geteilt", False, ruecksprung="195",
                  text=f"Werk ist geteilt in {b.roh['geteilt_in']} -> Teile taggen")
        g.entscheide(schreiben=not trocken)
        return g

    # Abkuerzungen je Werk pflegen
    if (abk or abk_weg) and not trocken:
        alt = [a for a in (b.roh.get("abkuerzungen") or [])]
        neu = sorted((set(alt) | {a.lower().rstrip(".") for a in abk or []}) - {a.lower().rstrip(".") for a in abk_weg or []})
        bestellung.feld_setzen(werk, abkuerzungen=neu)
        b = bestellung.lesen(werk)
    abkl = abk_liste(werk, b, src)
    g.metrik("abkuerzungen", len(abkl))

    rp = os.path.join(config.book_dir(werk), "raw_modernized.txt")
    if not g.pflicht("raw_modernized", os.path.exists(rp), ruecksprung="120", text="raw_modernized.txt vorhanden"):
        g.entscheide(schreiben=not trocken)
        return g
    with open(rp, encoding="utf-8") as f:
        text = f.read()
    titel, autor, kap = s190_vertrag.marken_lesen(text)
    kap = [(t, k.strip()) for t, k in kap]
    g.metrik("quelle_hash", manifest.hash_obj(text))
    n190, n190_q = _kap_190(werk, d, len(kap))
    g.pflicht("kapitelzahl", len(kap) == n190 and len(kap) > 0, wert=f"{len(kap)}/{n190}", ruecksprung="120",
              text=f"Kapitel raw_modernized {len(kap)} = {n190_q} {n190}")
    leer_kap = [i for i, (_t, k) in enumerate(kap, 1) if not k]
    g.pflicht("kapitel_text", not leer_kap, wert=leer_kap[:20], ruecksprung="120",
              text="Kapitel ohne Text: " + (str(leer_kap[:20]) if leer_kap else "keine"))
    if g.fehler():
        g.entscheide(schreiben=not trocken)
        return g

    ck = manifest.Checkpoint(werk, STAGE)
    alle_neu = kapitel and "alle" in [str(x) for x in kapitel]
    neu = set(range(1, len(kap) + 1)) if alle_neu else {int(x) for x in kapitel or []}
    bestand = bestand_roh(werk, src) if uebernehmen else {}
    korr = korrekturen_lesen(werk)
    neue_korr = [dict(op="teilen", id=x.split("@", 1)[0], arg=x.split("@", 1)[1]) for x in teilen or []] + \
                [dict(op="zusammen", id=x, arg=None) for x in zusammen or []] + \
                [dict(op="typ", id=x.split("=", 1)[0], arg=x.split("=", 1)[1]) for x in typ or []]
    modell_eff = modell or config.MODELS.get("tagger")
    g.metrik("modell", modell_eff)
    ids = [x["id"] for x in neue_korr]
    if len(ids) != len(set(ids)):
        raise ValueError("je Knoten nur eine Korrektur pro Lauf")

    alle, chapters_meta, pruef = {}, {}, {"kapitel": [], "mehrsatz": [], "ueberlang": [], "korrekturen_verworfen": []}
    n_llm = n_wdh = n_ck = n_bestand = 0
    fehlt = []
    treue_aus, korr_gueltig = [], []
    for n, (ktitel, ktext) in enumerate(kap, 1):
        key = f"c{n:0{config.CHAPTER_DIGITS}d}"
        h = _hash([ktitel, ktext])
        daten = None if n in neu else ck.lesen(key, src, h)
        herkunft = "checkpoint"
        if daten is None and n not in neu and n in bestand:
            daten, herkunft = {"content": bestand[n], "versuche": 1, "modell": "bestand"}, "bestand"
            n_bestand += 1
        if daten is None:
            if trocken:
                fehlt.append(n)
                continue
            daten, herkunft = {"content": _tag_llm(n, ktitel, ktext, modell), "versuche": 1, "modell": modell_eff}, "neu"
            n_llm += 1
        knoten = nachbearbeiten(n, ktitel, daten["content"], src, abkl)
        q, bsp = treue(ktext, knoten, src)
        # Treue verfehlt -> einmal automatisch neu taggen (je Kapitelfassung), danach Mensch
        if q < TREUE_MIN and daten.get("versuche", 1) < 2 and not trocken:
            roh2 = _tag_llm(n, ktitel, ktext, modell)
            kn2 = nachbearbeiten(n, ktitel, roh2, src, abkl)
            q2, bsp2 = treue(ktext, kn2, src)
            n_llm += 1
            n_wdh += 1
            if q2 >= q:
                daten, knoten, q, bsp = {"content": roh2, "modell": modell_eff}, kn2, q2, bsp2
            daten["versuche"] = 2
            herkunft = "wiederholt"
        if herkunft != "checkpoint" and not trocken:
            ck.schreiben(key, src, h, daten, herkunft=herkunft)
        elif herkunft == "checkpoint":
            n_ck += 1
        # Korrekturen (gespeicherte + neue) dieses Kapitels in Reihenfolge
        # neue Korrekturen von hinten nach vorn: IDs davor bleiben gueltig (Monitor sammelt mehrere je Kapitel)
        neu_kap = sorted((dict(x, kapitel=key, eingang=h, neu=1) for x in neue_korr if x["id"].startswith(key + "_")),
                         key=lambda x: -int(x["id"].split("_")[1]))
        for k in korr + neu_kap:
            if k.get("kapitel") != key:
                continue
            if k.get("eingang") != h:
                pruef["korrekturen_verworfen"].append(k)
                continue
            try:
                knoten = korrektur_anwenden(n, ktitel, knoten, k, src)
                korr_gueltig.append({x: v for x, v in k.items() if x != "neu"})
            except ValueError as e:
                if k.get("neu"):
                    raise
                pruef["korrekturen_verworfen"].append(dict(k, fehler=str(e)))
        if neue_korr:
            q, bsp = treue(ktext, knoten, src)
        pruef["kapitel"].append({"kapitel": n, "titel": ktitel, "treue": round(q, 5), "herkunft": herkunft,
                                 "knoten": len(knoten), "zeichen": len(ktext),
                                 "abweichungen": bsp if q < TREUE_MIN else []})
        if q < TREUE_MIN:
            treue_aus.append(f"{n} ({q:.2%})")
        for tid, e in knoten.items():
            t = e.get(src) or ""
            if e.get("type") in satzweise.TEILBARE_TYPEN and not e.get("_m") \
                    and len(tt := satzweise.teile_text(t, src, abkl)) > 1:
                pruef["mehrsatz"].append({"id": tid, "text": t, "saetze": len(tt), "vorschlag": trennstelle(t, tt[1])})
            if len(t) > lang_max:
                pruef["ueberlang"].append({"id": tid, "zeichen": len(t)})
            e.pop("_m", None)
        alle.update(knoten)
        chapters_meta[key] = ktitel

    unbekannt = [t for t, e in alle.items() if e.get("type") not in config.TAG_TYPES]
    leer = [t for t, e in alle.items() if e.get("type") not in OHNE_TEXT | {"h"} and not (e.get(src) or "").strip()]
    n_mock = sum(1 for e in alle.values() if mock.ist_text(e.get(src) or ""))

    g.metrik("knoten", len(alle))
    g.metrik("llm_aufrufe", n_llm)
    g.metrik("aus_checkpoint", n_ck)
    g.metrik("aus_bestand", n_bestand)
    g.metrik("treue_min", min((k["treue"] for k in pruef["kapitel"]), default=None))
    if trocken and fehlt:
        g.pflicht("tagging_vorhanden", False, wert=fehlt[:20], text=f"kein Tagging fuer Kapitel {fehlt[:20]} (Probe ohne LLM)")
    g.pflicht("unbekannte_typen", not unbekannt, wert=len(unbekannt),
              text=f"unbekannte Typen {len(unbekannt)}" + (f": {unbekannt[:5]}" if unbekannt else ""))
    g.pflicht("leere_knoten", not leer, wert=len(leer),
              text=f"leere Knoten {len(leer)}" + (f": {leer[:5]}" if leer else ""))
    g.pruefe("treue", not treue_aus, wert=len(treue_aus), schwelle=f">= {TREUE_MIN:.1%}", bei_fehler="mensch",
             text=f"Treue >= {TREUE_MIN:.1%} je Kapitel" + (f"; verfehlt: {', '.join(treue_aus[:10])} "
                  f"(Gegenueberstellung work/200_pruefung.json; Ausgangstextfehler -> 120)" if treue_aus else ""))
    g.pruefe("mehrsatz", not pruef["mehrsatz"], wert=len(pruef["mehrsatz"]), schwelle="= 0", bei_fehler="mensch",
             text=f"Mehrsatz-Knoten {len(pruef['mehrsatz'])}" +
                  (f" (Liste work/200_pruefung.json; --teilen / --abk)" if pruef["mehrsatz"] else ""))
    g.hinweis("ueberlang", not pruef["ueberlang"], wert=len(pruef["ueberlang"]),
              text=f"Knoten > {lang_max} Zeichen: {len(pruef['ueberlang'])}")
    if korr or neue_korr:
        g.metrik("korrekturen", len(korr_gueltig))
        g.hinweis("korrekturen_verworfen", not pruef["korrekturen_verworfen"], wert=len(pruef["korrekturen_verworfen"]),
                  text=f"Korrekturen verworfen (Kapitel geaendert/nicht anwendbar): {len(pruef['korrekturen_verworfen'])}")
    g.mock(n_mock, ruecksprung="120")

    final = {
        "book_id": werk,
        "meta": {"title": titel, "author": autor, "source_language": src,
                 "target_languages": b.zielsprachen or config.TARGET_LANGUAGES, "chapters": chapters_meta,
                 "tagging": {"modell": modell_eff, "quelle_hash": g.metriken["quelle_hash"]}},
        "content": alle,
    }
    aus_hash = _hash(alle)
    g.metrik("ausgabe_hash", aus_hash)
    # Mensch-Freigabe bleibt gueltig, solange die Ausgabe unveraendert ist
    st = d["stages"].get(STAGE) or {}
    if st.get("zustand") == "frei" and (st.get("gate") or {}).get("ergebnis") == "mensch" \
            and (st.get("metriken") or {}).get("ausgabe_hash") == aus_hash:
        for p in g.pruefungen:
            if not p["ok"] and p["bei_fehler"] == "mensch":
                p["bei_fehler"] = "hinweis"
                p["text"] += " [Mensch-Freigabe gilt, Ausgabe unveraendert]"

    if not trocken:
        os.makedirs(config.work_dir(werk), exist_ok=True)
        manifest.json_atomar(config.work_path(werk, "200_tagging"), final, indent=2)
        manifest.json_atomar(os.path.join(config.work_dir(werk), "200_pruefung.json"), pruef, indent=1)
        if neue_korr or korr:
            manifest.json_atomar(_korr_pfad(werk), korr_gueltig, indent=1)
        ck.aufraeumen([(f"c{n:0{config.CHAPTER_DIGITS}d}", src) for n in range(1, len(kap) + 1)])
    g.entscheide(schreiben=not trocken)
    g.pruef = pruef
    return g


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 200 Tagger")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--modell", help="Tagger-Modell (Standard config.MODELS tagger)")
    ap.add_argument("--kapitel", action="append", help="Kapitel N neu taggen (mehrfach) oder 'alle'")
    ap.add_argument("--teilen", action="append", metavar="ID@STELLE", help="Knoten vor STELLE teilen")
    ap.add_argument("--zusammen", action="append", metavar="ID", help="Knoten mit dem folgenden zusammenfuehren")
    ap.add_argument("--typ", action="append", metavar="ID=TYP", help="Typ eines Knotens aendern")
    ap.add_argument("--abk", action="append", help="Abkuerzung je Werk hinzufuegen (ohne Punkt)")
    ap.add_argument("--abk-weg", action="append", help="Abkuerzung je Werk entfernen")
    ap.add_argument("--lang", type=int, default=LANG_MAX, help="Grenze ueberlange Knoten (Hinweis)")
    ap.add_argument("--uebernehmen", action="store_true", help="vorhandene 200_tagging.json als Rohergebnis nutzen (ohne LLM)")
    ap.add_argument("--trocken", action="store_true", help="nichts schreiben, kein LLM (Probe)")
    a = ap.parse_args(argv)
    try:
        g = run(a.werk, a.wer, a.modell, a.kapitel, a.abk, a.abk_weg, a.lang, a.teilen, a.zusammen, a.typ,
                a.uebernehmen, a.trocken)
    except gate.GateHalt as e:
        print(e)
        return e.exit_code
    except ValueError as e:
        print(f"[200] Fehler: {e}")
        return 1
    print(g.bericht())
    return gate.EXIT[g.ergebnis["ergebnis"]]


if __name__ == "__main__":
    sys.exit(main())
