"""STAGE 340 — Wort-Alignment (Umbau Phase 2, GATE_KATALOG.md Zeile 340, 02.11.2026; 345 integriert)
Funktion:     Ordnet jedem Quellwort sein Fragment im fertigen Zielsatz zu (Wort-Tippen TAELLA, Anker fuer 520/525/710),
              prueft auf verschobene Anker (Pruefaligner awesome-align, Modal T4) und repariert, Gate je Zielsprache.
Wirkungsweise: Je Kapitel x Zielsprache (TAELLA-Produkt in Zielsprache): DeepSeek (Rolle aligner, Regler --modell)
              bekommt nummerierte Quellwoerter + fertigen Zielsatz und kopiert je Wort das Fragment (Index -> Fragment,
              nie neu uebersetzen); lokale Span-Suche (direkt -> Luecke -> Kompositum, Doppelwoerter auf plausibles
              Vorkommen). Checkpoint work/ckpt/340/<kap>__<lg>.json mit Hash je Satz (Quelle + Ziel aus 330): Neulauf
              aligned nur neue/geaenderte Saetze. Ohne Antwort oder mit >= 2 unaufgeloesten Woertern (> 3 % des Satzes)
              -> 1x automatisch neu (kleine Gruppen, Hinweis), Uebernahme bei weniger unaufgeloesten Woertern ohne
              Ankerverlust > Regler. Doppelt belegte Anker (nicht benachbarte Woerter auf demselben
              Zielwort) -> erst auf freie Vorkommen verteilen, sonst wie verschoben 1x Nachlauf. Pruefaligner (aus 345): je Satz unabhaengige Anker; Kette >= --kette Treffer gleicher
              Richtung auf den Nachbaranker = verschoben -> 1x DeepSeek mit Kettenhinweis; Uebernahme nur bei weniger
              Kettentreffern und <= --ankerverlust Ankerverlust, sonst bleibt die alte Zuordnung.
Eingang:      work/330_rueckuebersetzung.json (Stand nach Reparatur, Gate 330 frei), book.json (Bestellung),
              work/340_korrekturen.json (manuelle Anker).
Ausgabe:      work/340_wortalignment.json = 330 + je Satz `align_<lg>` (i, Quellwort/-span, Zielfragment/-span, source),
              `align_h` {lg: Hash Quelle+Ziel}, `verschiebung` {lg: Ketten}; `align` = erste Zielsprache (Altschnittstelle
              fuer 520/525/710 bis zu deren Umbau); meta.wortalignment. work/340_pruefung.json (je Sprache auffaellige
              Saetze: fehlt/unresolved/verschoben/doppelt/Inhaltswoerter ohne Anker).
Gate:         je Zielsprache: Abdeckung (jeder Satz aligned, Wortzahl = Quell-Tokens), Spans gueltig, Aktualitaet -> Stopp;
              Inhaltswoerter mit Anker >= 95 %, unresolved <= 3 %, verschoben <= 1 %, doppelt belegt <= 1 % -> sonst Mensch;
              Pruefaligner nicht erreichbar -> Mensch; Gate 330 nicht frei, Mock im Live-Lauf -> Stopp.
              Mensch-Freigabe gilt bei gleichem ausgabe_hash.
Kosten:       usage_log Stage 340 mit Sprache (DeepSeek; Pruefaligner Modal-T4 Teil "pruefaligner").
Regler:       --modell, --batch, --kapitel N|alle, --satz ID (neu alignen), --anker ID:I=FRAGMENT bzw. ID:I=- (manuell
              setzen/loeschen, --lang bei mehreren Zielsprachen), --pruefaligner an|aus, --kette 3, --ankerverlust 0.10,
              --inhalt-min 0.95, --unresolved-max 0.03, --verschoben-max 0.01, --doppelt-max 0.01, --lang,
              --uebernehmen (vorhandene 340_wortalignment.json + 345_pruefaligner.json als Rohergebnis; nur Saetze mit
              unveraendertem Zielsatz und gueltigen Spans, Rest wird neu aligned), --trocken (Probe ohne LLM/Schreiben).
Aufruf:       python -m pipeline.s340_wortalignment <werk> [Regler] [--wer CK]
Exit: 0 auto, 2 Stopp, 3 Mensch, 1 Fehler.

Konvention (seit 17.07.2026, nicht ohne Ruecksprache aendern): Quellwort-Index "i" = \\S+-Token des Quellsatzes,
"<quelle>_span" = Zeichenposition im Quellsatz; 520/525 docken ueber genau diesen Index/Span an.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import api_layer, bestellung, gate, manifest, mock, status, usage_log

STAGE = "340"
PROMPT_V = 1
BATCH = 20
BATCH_NACH = 10
KETTE = 3
ANKERVERLUST = 0.10
INHALT_MIN = 0.95
UNRESOLVED_MAX = 0.03
VERSCHOBEN_MAX = 0.01
DOPPELT_MAX = 0.01
SPRACHNAME = {"en": "English", "de": "German", "es": "Spanish", "fr": "French", "it": "Italian"}

# Funktionswoerter je Ausgangssprache (Inhaltswort = Buchstabenwort, nicht in der Liste)
STOP = {
    "en": set("""a an the and or but nor if of to in on at by for with from as is are was were be been being am do does
        did done have has had having not no so than that this these those it its he she they we you i me him her them us my
        your his our their there here who whom whose which what when where why how all any each some such into onto upon
        over under about after before up down out off then too very can could will would shall should may might must just
        also only own same s t o oh ah let lets""".split()),
    "de": set("""der die das den dem des ein eine einen einem einer eines und oder aber wenn als wie zu zum zur in im an am
        auf aus bei beim mit nach von vom für fur über uber unter um durch ist sind war waren sein bin bist seid hat haben
        hatte hatten habe wird werden wurde wurden würde nicht kein keine keinen so dass daß es er sie wir ihr ich du mich
        dich sich ihn ihm ihnen uns euch mein meine dein deine seine ihre unser euer man ja nein doch noch schon auch nur
        da dann denn wo was wer ob o ach""".split()),
    "es": set("""el la los las un una unos unas y o pero si de del a al en con por para como es son era eran ser estar
        está están fue fueron ha han había no que se lo le les me te nos os mi tu su sus yo tú él ella ellos ellas nosotros
        este esta esto ese esa eso muy ya también""".split()),
    "fr": set("""le la les l un une des et ou mais si de du d à au aux en dans sur par pour avec comme est sont était
        étaient être a ont avait ne pas que qui se s me m te t nous vous il elle ils elles je j tu y on ce cet cette ces
        son sa ses mon ma mes ton ta tes leur leurs très déjà aussi""".split()),
    "it": set("""il lo la i gli le un uno una e o ma se di del della dei degli delle a al alla ai agli alle in nel nella
        con per come è sono era erano essere ha hanno aveva non che si mi ti ci vi lui lei loro io tu noi voi questo questa
        quello quella mio mia tuo tua suo sua molto già anche""".split()),
}


# ============================================================
# TOKENISIERUNG + SPAN-SUCHE (lokal, deterministisch)
# ============================================================

def tokenize_en(text):
    """\\S+-Token des Quellsatzes (Name historisch, gilt fuer jede Ausgangssprache)."""
    return [{"i": i, "word": m.group(), "start": m.start(), "end": m.end()}
            for i, m in enumerate(re.finditer(r"\S+", text))]


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
    """Fragment im Zielsatz, nur auf Wortgrenzen; bevorzugt ab cursor, sonst erster Treffer (auch case-insensitive)."""
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
    """Luecke zwischen bestaetigten Nachbarankern (Funktionswort, nicht wortgetreu kopiert)."""
    if prev_end is None or next_start is None or next_start <= prev_end:
        return None
    gap = de_text[prev_end:next_start].strip()
    if not gap or len(gap) > max_len:
        return None
    return gap


_PUNCT_STRIP = re.compile(r"^[^\wÄÖÜäöüß]+|[^\wÄÖÜäöüß]+$")
_RAND = _PUNCT_STRIP


def _clean_frag(s):
    return _PUNCT_STRIP.sub("", s) if s else s


def try_compound_pair(de_text, frag1, frag2):
    """Benachbarte unaufgeloeste Woerter, deren Fragmente zusammen ein Wort ergeben (Kompositum)."""
    f1, f2 = _clean_frag(frag1), _clean_frag(frag2)
    if not f1 or not f2:
        return None
    combined = f1 + f2
    cands = _boundary_candidates(de_text, combined)
    if not cands:
        cands = _boundary_candidates(de_text, combined, ignore_case=True)
    return cands[0] if cands else None


def _mehrdeutige_korrigieren(de_text, rows, en_len):
    """Mehrfach vorkommende Zielwoerter auf das Vorkommen setzen, das zwischen die eindeutigen Nachbaranker passt
    (Befund 8, CK 01.11.2026; gleiche Logik wie tools/satzweise.anker_reparieren)."""
    kand, eindeutig = {}, []
    for k, r in enumerate(rows):
        t, span = r[0], r[2]
        if not span:
            continue
        c = _boundary_candidates(de_text, de_text[span[0]:span[1]])
        if len(c) > 1:
            kand[k] = c
        else:
            eindeutig.append((t["start"], span[0]))
    eindeutig.sort()
    for k, c in kand.items():
        q0, sp = rows[k][0]["start"], rows[k][2]
        vor = [e for e in eindeutig if e[0] < q0]
        nach = [e for e in eindeutig if e[0] > q0]
        if vor and nach:
            (qa, za), (qb, zb) = vor[-1], nach[0]
            soll = za + (zb - za) * (q0 - qa) / max(1, qb - qa)
        elif vor:
            soll = vor[-1][1] + (q0 - vor[-1][0])
        elif nach:
            soll = nach[0][1] - (nach[0][0] - q0)
        else:
            soll = q0 / max(1, en_len) * len(de_text)
        best = min(c, key=lambda x: abs(x[0] - soll))
        if best[0] != sp[0] and abs(best[0] - soll) + 0.1 * len(de_text) < abs(sp[0] - soll):
            rows[k][2] = best


def schluessel(src=None, lg=None):
    """(Quellwort, Quell-Span, Zielfragment, Ziel-Span) je Sprachpaar."""
    src = src or config.SOURCE_LANGUAGE
    lg = lg or config.TARGET_LANGUAGES[0]
    return src, f"{src}_span", lg, f"{lg}_span"


def resolve_alignment(en_text, de_text, model_result, src=None, lg=None):
    """Drei Passes (direkt -> Luecke -> Kompositum-Paar) -> words-Liste."""
    tokens = tokenize_en(en_text)
    rows = []
    cursor = 0
    for t in tokens:
        frag = model_result.get(str(t["i"]))
        frag = frag if isinstance(frag, str) and frag.strip() else None
        span = find_de_span(de_text, frag, cursor) if frag else None
        if span:
            cursor = span[0]
        rows.append([t, frag, span, None, None])
    _mehrdeutige_korrigieren(de_text, rows, len(en_text))

    for i in range(len(rows)):
        frag, span = rows[i][1], rows[i][2]
        if frag is not None and span is None:
            prev_end = next((rows[j][2][1] for j in range(i - 1, -1, -1) if rows[j][2]), None)
            next_start = next((rows[j][2][0] for j in range(i + 1, len(rows)) if rows[j][2]), None)
            rows[i][3] = find_gap_fallback(de_text, prev_end, next_start)

    i = 0
    while i < len(rows) - 1:
        u1 = rows[i][1] is not None and rows[i][2] is None and rows[i][3] is None
        u2 = rows[i + 1][1] is not None and rows[i + 1][2] is None and rows[i + 1][3] is None
        if u1 and u2:
            cspan = try_compound_pair(de_text, rows[i][1], rows[i + 1][1])
            if cspan:
                rows[i][4] = cspan
                rows[i + 1][4] = cspan
                i += 2
                continue
        i += 1

    k_src, k_src_span, k_tgt, k_tgt_span = schluessel(src, lg)
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


# ---- Ziel-Spans je Anker (aus s525 hierher verlagert, Befund 345 (3)) ----
def _grenze(text, a, b):
    vor = a == 0 or not text[a - 1].isalpha()
    nach = b == len(text) or not text[b].isalpha()
    return vor and nach


def _finde(text, frag, von, bis):
    """Wortgrenzen-saubere Treffer (auch case-insensitive); bevorzugt im Fenster [von, bis]."""
    if not frag:
        return None
    kand = []
    for hay, nd in ((text, frag), (text.lower(), frag.lower())):
        s = 0
        while True:
            x = hay.find(nd, s)
            if x < 0:
                break
            if _grenze(text, x, x + len(nd)):
                kand.append((x, x + len(nd)))
            s = x + 1
        if kand:
            break
    if not kand:
        return None
    im = [c for c in kand if c[0] >= von and c[1] <= bis]
    if im:
        return im[0]
    return min(kand, key=lambda c: abs(c[0] - von))


def _spans_aus(w, key):
    sp = w.get(key)
    if not sp:
        return []
    if isinstance(sp[0], int):
        return [list(sp)]
    return [list(x) for x in sp]


def ziel_spans(align, ziel_text, reparatur=True, lg=None):
    """-> je Anker (spans, quelle); quelle '340' | 'repariert' | None. lg = Zielsprache (sonst erste aus config)."""
    _, _, k_tgt, k_tgt_span = schluessel(None, lg)
    roh = [_spans_aus(w, k_tgt_span) for w in align]
    out = []
    for n, w in enumerate(align):
        if roh[n]:
            out.append((roh[n], "340"))
            continue
        frag = w.get(k_tgt)
        # Lueckenfuellung nur glaubwuerdig, wenn kurz (<= 2 Woerter, kein Satzende)
        if frag and w.get("source") == "gap_fallback" and (len(frag.split()) > 2 or re.search(r"[.!?;:]\s", frag)):
            frag = None
        if not (reparatur and frag):
            out.append(([], None))
            continue
        von = next((roh[p][-1][1] for p in range(n - 1, -1, -1) if roh[p]), 0)
        bis = next((roh[p][0][0] for p in range(n + 1, len(roh)) if roh[p]), len(ziel_text))
        teile = [t for t in (_RAND.sub("", x) for x in re.split(r"\s*(?:\.\.\.|…|\s)\s*", frag)) if t]
        ganz = _finde(ziel_text, _RAND.sub("", frag), von, max(bis, von))
        spans = []
        if ganz:
            spans = [list(ganz)]
        else:
            cur = von
            for t in teile:
                s = _finde(ziel_text, t, cur, len(ziel_text))
                if s:
                    spans.append(list(s))
                    cur = s[1]
        if spans:
            roh[n] = spans
        out.append((spans, "repariert" if spans else None))
    return out


# ---- Verschiebung (aus s345) ----
def _ztok(text):
    return [(m.start(), m.end()) for m in re.finditer(r"\S+", text or "")]


def _tokset(spans, ztok):
    return {k for k, (a, b) in enumerate(ztok) for s in spans if a < s[1] and s[0] < b}


def ketten(align, ziel_text, pruef_w, lg=None, min_kette=KETTE):
    """Verschiebungsketten: Pruefanker von i trifft den Anker des Nachbarn i+d (d=-1/+1), nicht den eigenen;
    >= min_kette Treffer gleicher Richtung hintereinander. -> [{"von","bis","richtung","treffer":[i,..]}]."""
    zt = _ztok(ziel_text)
    A = {}
    for w, (sp, _) in zip(align, ziel_spans(align, ziel_text, reparatur=True, lg=lg)):
        A[w["i"]] = _tokset(sp, zt)
    B = {i: _tokset(sp, zt) for i, sp in (pruef_w or [])}
    n = max(A) + 1 if A else 0
    stat = []
    for i in range(n):
        a, b = A.get(i, set()), B.get(i, set())
        if not b:
            stat.append(0)
            continue
        if b & a:
            stat.append(None)
            continue
        d_hit = [d for d in (-1, 1) if b & A.get(i + d, set())]
        stat.append(d_hit[0] if d_hit else None)
    out = []
    for d in (-1, 1):
        lauf = []
        for i, s in enumerate(stat + [None]):
            if s == d:
                lauf.append(i)
            elif s == 0 and lauf:
                continue
            else:
                if len(lauf) >= min_kette:
                    out.append({"von": lauf[0], "bis": lauf[-1], "richtung": d, "treffer": lauf})
                lauf = []
    return sorted(out, key=lambda k: k["von"])


def _gruppen(align, k_span):
    g = {}
    for w in align:
        sp = w.get(k_span)
        if sp and w.get("source") != "compound_pair":
            g.setdefault(tuple(sp), []).append(w["i"])
    return g


def doppelt(align, lg=None):
    """Nicht benachbarte Woerter auf demselben Ziel-Span (benachbarte = Mehrwort-Einheit, z. B. "coat hooks" ->
    "Garderobenhaken", gelten nicht) -> [i, ..] (je Gruppe ohne das erste Wort)."""
    _, _, _, k_span = schluessel(None, lg)
    out = []
    for l in _gruppen(align, k_span).values():
        l = sorted(l)
        out += [b for a, b in zip(l, l[1:]) if b - a > 1]
    return sorted(out)


def normieren(align, q, z, src=None, lg=None):
    """Deterministische Nacharbeit je Satz (auch fuer Altbestand/Checkpoint): Fragment = Text am Span (Gross-/
    Kleinschreibung), doppelt belegte Anker eines mehrfach vorkommenden Zielworts auf freie Vorkommen verteilen
    (Doppelwoerter auf plausiblem Vorkommen, in Lesereihenfolge)."""
    _, k_src_span, k_tgt, k_span = schluessel(src, lg)
    for w in align:
        sp, f = w.get(k_span), w.get(k_tgt)
        if sp and isinstance(f, str) and z[sp[0]:sp[1]] != f and z[sp[0]:sp[1]].lower() == f.lower():
            w[k_tgt] = z[sp[0]:sp[1]]
    gr = _gruppen(align, k_span)
    belegt = set(gr)
    by_i = {w["i"]: w for w in align}
    for span, idx in gr.items():
        idx = sorted(idx)
        if len(idx) < 2 or all(b - a == 1 for a, b in zip(idx, idx[1:])):
            continue
        frei = [c for c in _boundary_candidates(z, z[span[0]:span[1]]) if c == span or c not in belegt]
        if len(frei) < len(idx):
            continue
        cur, wahl = 0, []
        for n, i in enumerate(idx):
            w = by_i[i]
            soll = (w.get(k_src_span) or [0])[0] / max(1, len(q)) * len(z)
            rest = len(idx) - n - 1
            moegl = frei[cur:len(frei) - rest]
            c = min(moegl, key=lambda x: abs(x[0] - soll))
            cur = frei.index(c) + 1
            wahl.append(c)
        for i, c in zip(idx, wahl):
            by_i[i][k_span] = list(c)
            by_i[i][k_tgt] = z[c[0]:c[1]]
            belegt.add(c)
    return align


def anker(align, lg=None):
    _, _, _, k_span = schluessel(None, lg)
    return sum(1 for w in align if w.get(k_span))


def ist_inhaltswort(wort, src):
    w = _RAND.sub("", wort or "").lower()
    return bool(w) and any(c.isalpha() for c in w) and w not in STOP.get(src, set())


# ============================================================
# EINGANG
# ============================================================

def saetze(data, src, lg):
    """-> {kap: [(id, quelle, ziel)]} (Knoten mit Quell- und Zieltext, ohne NO_AUDIO_TYPES)."""
    kap = {}
    for tid, e in (data.get("content") or {}).items():
        cid = tid.split("_")[0]
        kap.setdefault(cid, [])
        if not isinstance(e, dict) or e.get("type") in config.NO_AUDIO_TYPES:
            continue
        q, z = (e.get(src) or "").strip(), (e.get(lg) or "").strip()
        if q and z:
            kap[cid].append((tid, q, z))
    return kap


def satz_hash(q, z):
    return manifest.hash_text(q + "\u0001" + z)


# ============================================================
# LLM
# ============================================================

def _build_prompt(items, src=None, lg=None):
    """items = [(tag_id, quelltext, zieltext), ...]."""
    src = src or config.SOURCE_LANGUAGE
    lg = lg or config.TARGET_LANGUAGES[0]
    if src == "de" and lg == "en":
        return _build_prompt_de_en(items)
    S, Z = src.upper(), lg.upper()
    zname = SPRACHNAME.get(lg, lg)
    blocks = []
    for tag_id, en_text, de_text in items:
        numbered = " ".join(f'[{t["i"]}]{t["word"]}' for t in tokenize_en(en_text))
        blocks.append(
            f'ID {json.dumps(tag_id)}\n'
            f'{S} (numbered words): {numbered}\n'
            f'{Z} (existing, already translated - do NOT retranslate): {json.dumps(de_text, ensure_ascii=False)}\n')
    joined = "\n".join(blocks)
    if src == "en" and lg == "de":
        beispiele = """Examples of dissolution:
  EN "trouble was brewing"   DE "Unheil zusammenbraute"
      -> "was" is inside the verb form. "was" = null.
      (Answering "war" would be a dictionary guess - "war" is not there.)
  EN "in the grass"          DE "im Gras"
      -> "im" already contains the article. "the" = null.
  EN "a St. Bernard"         DE "ein Bernhardiner"
      -> "St." is absorbed into the compound. "St." = null.
"""
        einheit = '(e.g. "sun-kissed" -> "sonnenverwöhnt", "plunged" -> "tauchte ein")'
    else:
        beispiele = ""
        einheit = "(e.g. a verb with its particle, or a compound)"
    return f"""You are NOT translating. You are locating existing text.

For each numbered {S} word, find that word's counterpart inside the GIVEN
{zname} sentence and copy it VERBATIM, character for character, exactly as it
appears there. The {zname} sentence is fixed and already correct - never
retranslate, improve, or invent wording for it.

THE MOST IMPORTANT RULE - when to answer null:
{zname} often dissolves a {SPRACHNAME.get(src, src)} word into another word or into the
grammar itself. When that happens there is NO fragment to point at, and
null is the CORRECT and expected answer. {beispiele}Do NOT supply the word's usual dictionary translation when that translation
does not literally stand in the {zname} sentence. A guessed word is far worse
than null, because it may coincidentally match a DIFFERENT word in the
sentence and anchor to the wrong place.

SECOND RULE - anchor to THAT word, never to its neighbour:
Word order differs between the languages, so the counterpart may sit far from
where the {S} word sits. That is fine. What is NOT fine is taking the
counterpart that belongs to the previous or next {S} word. Before you
answer, re-read your fragments in order and check that each one is the
counterpart of ITS OWN word. If word N and word N+1 would both point at the
same {zname} word, at most one of them is right - give it to the word it
truly belongs to and answer null for the other.

Remaining rules:
- Content words (nouns, verbs, adjectives, adverbs, names) almost always DO
  have a counterpart. Look carefully before answering null for one.
- Function words (articles, prepositions, auxiliaries, particles) are the
  ones that frequently dissolve. Answer null freely for these.
- One {S} word may map to several {zname} words when they form one unit
  {einheit}.
  Keep the fragment as short as it can be while still being correct.
- Answer for every index. Do not skip any.
- Return only the index and the {zname} fragment, never the {S} word.

Sentences:
{joined}

Return ONLY a JSON object, one entry per sentence ID, mapping each {S} word
index (as string) to its {zname} fragment (or null):
{{
  "<tag_id>": {{"0": "<{zname} fragment or null>", "1": "...", ...}},
  ...
}}"""


def _build_prompt_de_en(items):
    """Spiegel fuer deutsche Originale (Quelle DE, Ziel EN)."""
    blocks = []
    for tag_id, src_text, tgt_text in items:
        numbered = " ".join(f'[{t["i"]}]{t["word"]}' for t in tokenize_en(src_text))
        blocks.append(
            f'ID {json.dumps(tag_id)}\n'
            f'DE (numbered words): {numbered}\n'
            f'EN (existing, already translated - do NOT retranslate): {json.dumps(tgt_text, ensure_ascii=False)}\n')
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


def _mock_antwort(items):
    """Mock: gleiches Wort im Zielsatz -> Fragment, sonst null (testet die Kette, nicht die Guete)."""
    out = {}
    for tid, q, z in items:
        zl = {_RAND.sub("", w).lower(): _RAND.sub("", w) for w in z.split()}
        out[tid] = {str(t["i"]): zl.get(_RAND.sub("", t["word"]).lower()) for t in tokenize_en(q)}
    return out


def _rolle(modell, fn):
    alt = config.MODELS.get("aligner")
    if modell:
        config.MODELS["aligner"] = modell
    try:
        return fn()
    finally:
        config.MODELS["aligner"] = alt


def llm(werk, items, src, lg, modell=None, hinweise=None):
    """items [(id, quelle, ziel)] -> {id: {index: fragment|None}} (nur Saetze mit Antwort)."""
    if not items:
        return {}
    usage_log.set_context(werk, STAGE, sprache=lg)
    if config.RUN_MODE == "mock":
        return _mock_antwort(items)
    prompt = _build_prompt(items, src, lg)
    if hinweise:
        prompt = prompt.replace("Return ONLY a JSON object", "\n".join(hinweise) + "\n\nReturn ONLY a JSON object", 1)
    n_w = sum(len(tokenize_en(q)) for _, q, _ in items)
    try:
        raw = _rolle(modell, lambda: api_layer.call_model("aligner", prompt,
                                                          max_tokens=min(16000, max(2000, n_w * 12))))
        p = api_layer.parse_json(raw)
    except EnvironmentError:
        raise
    except Exception as e:
        print(f"      ! Alignment gescheitert ({lg}): {str(e)[:120]}")
        return {}
    if not isinstance(p, dict):
        return {}
    return {tid: p[tid] for tid, _q, _z in items if isinstance(p.get(tid), dict) and p[tid]}


# ============================================================
# PRUEFALIGNER (awesome-align auf Modal T4)
# ============================================================

def _pruefaligner_modal(werk, lg, paare):
    """paare [{"id","q","z"}] -> {id: [[i, [[a,b],..]],..]}. Kosten unter Stage 340, Teil pruefaligner."""
    import modal
    from gpu_align import pruefaligner_modal as pm
    with modal.enable_output():
        with pm.app.run():
            out, sek = pm.lauf.remote(paare)
    usage_log.log_gpu(werk, STAGE, sek, gpu="T4", extra={"teil": "pruefaligner", "sprache": lg})
    return {x["id"]: x["w"] for x in out}


PRUEFALIGNER = _pruefaligner_modal       # in Tests ersetzbar


# ============================================================
# KORREKTUREN (manuelle Anker)
# ============================================================

def _korr_pfad(werk):
    return os.path.join(config.work_dir(werk), "340_korrekturen.json")


def korrekturen_lesen(werk):
    try:
        with open(_korr_pfad(werk), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def anker_setzen(werk, lg, tid, h, i, frag, z, wer=None):
    """frag None = Anker loeschen; sonst muss das Fragment wortgrenzen-sauber im Zielsatz stehen."""
    if frag is not None and not _boundary_candidates(z, frag, ignore_case=True):
        raise ValueError(f"'{frag}' steht nicht im Zielsatz {tid}: {z}")
    k = korrekturen_lesen(werk)
    e = k.setdefault(lg, {}).setdefault(tid, {"anker": {}})
    if e.get("h") != h:
        e["anker"] = {}
    e.update({"h": h, "wer": wer, "wann": manifest.jetzt()})
    e["anker"][str(i)] = frag
    manifest.json_atomar(_korr_pfad(werk), k, indent=1)


def _manuell_anwenden(align, z, anker_map, src, lg):
    _, _, k_tgt, k_span = schluessel(src, lg)
    for w in align:
        if str(w["i"]) not in anker_map:
            continue
        frag = anker_map[str(w["i"])]
        w.pop(k_span, None)
        if frag is None:
            w[k_tgt], w["source"] = None, "manuell"
            continue
        sp = find_de_span(z, frag, 0)
        if sp:
            w[k_tgt], w[k_span], w["source"] = z[sp[0]:sp[1]], list(sp), "manuell"


# ============================================================
# LAUF
# ============================================================

def _unaufgeloest(align):
    return sum(1 for w in align if w.get("source") == "unresolved")


def _satz_unresolved(align):
    u = _unaufgeloest(align)
    return u >= 2 and u > 0.03 * max(1, len(align))


def _alt340(werk, src, lg):
    """Altbestand: vorhandene 340_wortalignment.json (+ 345_pruefaligner.json) -> {id: (ziel, align, pruef)}."""
    p = config.work_path(werk, "340_wortalignment")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    pr = {}
    pp = config.work_path(werk, "345_pruefaligner")
    if os.path.exists(pp):
        try:
            with open(pp, encoding="utf-8") as f:
                pr = {x["id"]: x["w"] for x in json.load(f)}
        except (OSError, ValueError, KeyError, TypeError):
            pr = {}
    _, _, k_tgt, k_span = schluessel(src, lg)
    out = {}
    for tid, e in (d.get("content") or {}).items():
        if not isinstance(e, dict):
            continue
        al = e.get(f"align_{lg}") or e.get("align")
        if not al or not isinstance(al, list) or not any(k_tgt in w for w in al):
            continue
        out[tid] = ((e.get(lg) or "").strip(), al, pr.get(tid))
    return out


def _ausgabe_pruefen(align, q, z, src, lg):
    """-> (abdeckung_ok, span_fehler)."""
    k_src, k_src_span, k_tgt, k_span = schluessel(src, lg)
    tok = tokenize_en(q)
    ok = isinstance(align, list) and len(align) == len(tok) and \
        all(w.get("i") == t["i"] and w.get(k_src) == t["word"] for w, t in zip(align, tok))
    fehler = 0
    for w in align or []:
        a, b = (w.get(k_src_span) or [0, 0])
        if q[a:b] != w.get(k_src):
            fehler += 1
            continue
        sp = w.get(k_span)
        if sp and (z[sp[0]:sp[1]] != w.get(k_tgt)):
            fehler += 1
    return ok, fehler


def run(werk, wer=None, modell=None, batch=None, kapitel=None, saetze_neu=None, anker_regler=None, pruefaligner=None,
        kette=None, ankerverlust=None, inhalt_min=None, unresolved_max=None, verschoben_max=None, doppelt_max=None,
        nur_lang=None, uebernehmen=False, trocken=False):
    wer = wer or "pipeline"
    g = gate.Gate(werk, STAGE, ruecksprung="340", wer=wer)
    b = bestellung.lesen(werk)
    src = b.quellsprache or config.SOURCE_LANGUAGE
    ziele = [lg for lg in (b.zielsprachen or []) if lg != src and b.hat(sprache=lg, kanal="taella")]
    if nur_lang:
        ziele = [lg for lg in ziele if lg == nur_lang]
    roh = b.roh or {}
    modell_eff = modell or config.MODELS.get("aligner")
    batch = int(batch or getattr(config, "ALIGN_BATCH_SIZE", BATCH))
    pa = pruefaligner or roh.get("align_pruefaligner") or "an"
    kette = int(kette or KETTE)
    ankerverlust = float(ankerverlust if ankerverlust is not None else ANKERVERLUST)
    inhalt_min = float(inhalt_min if inhalt_min is not None else INHALT_MIN)
    unresolved_max = float(unresolved_max if unresolved_max is not None else UNRESOLVED_MAX)
    verschoben_max = float(verschoben_max if verschoben_max is not None else VERSCHOBEN_MAX)
    doppelt_max = float(doppelt_max if doppelt_max is not None else DOPPELT_MAX)
    for k, v in (("zielsprachen", ziele), ("modell", modell_eff), ("batch", batch), ("pruefaligner", pa),
                 ("kette", kette), ("ankerverlust", ankerverlust)):
        g.metrik(k, v)

    ip = config.work_path(werk, "330_rueckuebersetzung")
    if not g.pflicht("rueckuebersetzung", os.path.exists(ip), ruecksprung="330",
                     text="330_rueckuebersetzung.json vorhanden"):
        g.entscheide(schreiben=not trocken)
        return g
    z330 = status.zustand(werk, "330")
    if trocken:
        g.hinweis("gate_330", z330 in status.FREI, text=f"Gate 330: {z330}")
    else:
        g.pflicht("gate_330", z330 in status.FREI, wert=z330, ruecksprung="330", text=f"Gate 330 frei ({z330})")
    ok_z = g.pflicht("zielsprachen", bool(ziele), ruecksprung="095",
                     text="Bestellung nennt mindestens ein TAELLA-Produkt in einer Zielsprache")
    if not ok_z or (not trocken and z330 not in status.FREI):
        g.entscheide(schreiben=not trocken)
        return g
    with open(ip, encoding="utf-8") as f:
        data = json.load(f)
    meta = data.setdefault("meta", {})

    # Manuelle Anker
    lg_regler = nur_lang or (ziele[0] if len(ziele) == 1 else None)
    if anker_regler and not trocken:
        if not lg_regler:
            raise ValueError("--anker braucht --lang bei mehreren Zielsprachen")
        idx = {t: (q, zt) for l in saetze(data, src, lg_regler).values() for t, q, zt in l}
        for x in anker_regler:
            m = re.match(r"^(c\d+_\d+_\w+):(\d+)=(.*)$", x, re.S)
            if not m or m.group(1) not in idx:
                raise ValueError(f"--anker {x!r}: Form ID:I=FRAGMENT (bzw. =-) mit bekannter ID")
            tid, i, frag = m.group(1), int(m.group(2)), m.group(3).strip()
            q, zt = idx[tid]
            if i >= len(tokenize_en(q)):
                raise ValueError(f"--anker {x!r}: Index {i} ausserhalb des Satzes")
            anker_setzen(werk, lg_regler, tid, satz_hash(q, zt), i, None if frag in ("-", "") else frag, zt, wer)
    korr = korrekturen_lesen(werk)

    neu_k = None if kapitel == ["alle"] else {f"c{int(k):0{config.CHAPTER_DIGITS}d}" for k in (kapitel or [])}
    neu_ids = set(saetze_neu or [])
    ck = manifest.Checkpoint(werk, STAGE)
    zz = {"llm": 0, "neu_aligned": 0, "nachgefordert": 0, "unresolved_repariert": 0, "verschoben_versucht": 0,
          "verschoben_uebernommen": 0, "pruefaligner_saetze": 0, "manuell": 0, "altbestand": 0}
    pruef, je_sprache, ck_soll = {}, {}, []
    n_mock = 0
    erste = ziele[0]

    for lg in ziele:
        kap = saetze(data, src, lg)
        alt = _alt340(werk, src, lg) if (uebernehmen or trocken) else None
        if trocken and alt is None:
            g.pflicht(f"bestand_{lg}", False, text=f"{lg}: 340_wortalignment.json fehlt (Probe ohne LLM)")
            continue
        kontext = manifest.hash_obj([PROMPT_V, src, lg, modell_eff])
        res_lg = {}                      # cid -> {tid: eintrag}
        for cid, liste in kap.items():
            if not liste:
                continue
            ck_soll.append((cid, lg))
            frisch = neu_k is None or cid in neu_k
            altck = {} if (trocken or frisch) else ((ck.lesen(cid, lg, kontext) or {}).get("saetze") or {})
            res, offen = {}, []
            for t, q, zt in liste:
                if mock.ist_text(zt) or mock.ist_text(q):
                    n_mock += 1
                h = satz_hash(q, zt)
                e = altck.get(t)
                if e and e.get("h") == h and t not in neu_ids:
                    res[t] = e
                    continue
                a = (alt or {}).get(t)
                if a and a[0] == zt and t not in neu_ids and \
                        _ausgabe_pruefen(normieren(json.loads(json.dumps(a[1])), q, zt, src, lg), q, zt, src, lg) == (True, 0):
                    res[t] = {"h": h, "a": a[1], "p": a[2], "alt": True, "v": 1, "vv": 1}
                    zz["altbestand"] += 1
                    continue
                offen.append((t, q, zt))
            if offen and not trocken:
                got = {}
                for i in range(0, len(offen), batch):
                    got.update(llm(werk, offen[i:i + batch], src, lg, modell_eff))
                    zz["llm"] += 1
                zz["neu_aligned"] += len(offen)
                for t, q, zt in offen:
                    res[t] = {"h": satz_hash(q, zt), "v": 0, "vv": 0,
                              "a": resolve_alignment(q, zt, got[t], src, lg) if t in got else None}
                # fehlt / unresolved -> 1x neu (kleine Gruppen)
                nach = [(t, q, zt) for t, q, zt in offen if res[t]["a"] is None or _satz_unresolved(res[t]["a"])]
                for i in range(0, len(nach), BATCH_NACH):
                    teil = nach[i:i + BATCH_NACH]
                    hw = [f"CHECK for ID {json.dumps(t)}: a previous attempt left words unmatched or gave no answer. "
                          f"Copy each counterpart verbatim from the given sentence, or answer null." for t, _, _ in teil]
                    got2 = llm(werk, teil, src, lg, modell_eff, hinweise=hw)
                    zz["llm"] += 1
                    zz["nachgefordert"] += len(teil)
                    for t, q, zt in teil:
                        e = res[t]
                        e["v"] = 1
                        if t not in got2:
                            continue
                        neu = resolve_alignment(q, zt, got2[t], src, lg)
                        if e["a"] is None:
                            e["a"] = neu
                            zz["unresolved_repariert"] += 1
                        elif _unaufgeloest(neu) < _unaufgeloest(e["a"]) and \
                                anker(neu, lg) >= anker(e["a"], lg) - max(1, int(ankerverlust * anker(e["a"], lg))):
                            e["a"] = neu
                            zz["unresolved_repariert"] += 1
            res_lg[cid] = res

        # Pruefaligner fuer Saetze ohne Pruefergebnis (je Sprache ein Modal-Lauf)
        pa_fehler = None
        if pa == "an" and not trocken:
            paare = [{"id": t, "q": q, "z": zt} for cid, liste in kap.items() for t, q, zt in liste
                     if (res_lg.get(cid, {}).get(t) or {}).get("a") and res_lg[cid][t].get("p") is None]
            if paare:
                try:
                    pw = PRUEFALIGNER(werk, lg, paare)
                    zz["pruefaligner_saetze"] += len(paare)
                    gesendet = {p["id"] for p in paare}
                    for cid, liste in kap.items():
                        for t, _q, _zt in liste:
                            e = res_lg.get(cid, {}).get(t)
                            if e and t in pw:
                                e["p"] = pw[t]
                            elif e and t in gesendet:
                                e["p"] = []          # Pruefaligner ohne Anker fuer diesen Satz
                except Exception as ex:
                    pa_fehler = f"{type(ex).__name__}: {str(ex)[:160]}"

        # Verschiebung / doppelt belegte Anker -> 1x Nachlauf mit Hinweis
        if not trocken:
            def _last(e_a, zt, p, q):
                al = normieren(json.loads(json.dumps(e_a)), q, zt, src, lg)
                k = ketten(al, zt, p, lg, kette) if p is not None else []
                return k, doppelt(al, lg), sum(len(x["treffer"]) for x in k) + len(doppelt(al, lg))
            kand = []
            for cid, liste in kap.items():
                for t, q, zt in liste:
                    e = res_lg.get(cid, {}).get(t) or {}
                    if e.get("a") and not e.get("vv") and (e.get("p") is not None or pa != "an"):
                        k, dp, _s = _last(e["a"], zt, e.get("p"), q)
                        if k or dp:
                            kand.append((cid, t, q, zt, k, dp))
            for i in range(0, len(kand), BATCH_NACH):
                teil = kand[i:i + BATCH_NACH]
                hw = []
                for cid, t, q, zt, k, dp in teil:
                    al = res_lg[cid][t]["a"]
                    if k:
                        woerter = " | ".join(" ".join(f'[{w["i"]}]{w[src]}' for w in al if x["von"] <= w["i"] <= x["bis"])
                                             for x in k)
                        hw.append(f"CHECK for ID {json.dumps(t)}: a previous attempt shifted the anchors of these words "
                                  f"by one position (each word got the counterpart of its neighbour): {woerter}. "
                                  f"Map each of them to ITS OWN counterpart, or null.")
                    if dp:
                        woerter = " ".join(f'[{w["i"]}]{w[src]}' for w in al if w["i"] in dp)
                        hw.append(f"CHECK for ID {json.dumps(t)}: a previous attempt anchored these words to the same "
                                  f"{SPRACHNAME.get(lg, lg)} word as an earlier, non-adjacent word: {woerter}. If the "
                                  f"word occurs again in the sentence use that occurrence, otherwise answer null.")
                got = llm(werk, [(t, q, zt) for _c, t, q, zt, _k, _d in teil], src, lg, modell_eff, hinweise=hw)
                zz["llm"] += 1
                for cid, t, q, zt, k, dp in teil:
                    e = res_lg[cid][t]
                    e["vv"] = 1
                    zz["verschoben_versucht"] += 1
                    if t not in got:
                        e["nl"] = "keine_antwort"
                        continue
                    neu = resolve_alignment(q, zt, got[t], src, lg)
                    s_alt = _last(e["a"], zt, e.get("p"), q)[2]
                    s_neu = _last(neu, zt, e.get("p"), q)[2]
                    a_alt, a_neu = anker(e["a"], lg), anker(neu, lg)
                    ok = s_neu < s_alt and a_neu >= a_alt - max(1, int(ankerverlust * a_alt))
                    e["nl"] = {"ergebnis": "uebernommen" if ok else "verworfen", "treffer": [s_alt, s_neu],
                               "anker": [a_alt, a_neu]}
                    if ok:
                        e["a"] = neu
                        zz["verschoben_uebernommen"] += 1
            for cid, res in res_lg.items():
                ck.schreiben(cid, lg, kontext, {"saetze": res})

        # Ergebnis + Metriken je Sprache
        kk = korr.get(lg) or {}
        n_s = n_w = n_inh = n_inh_a = n_unres = n_versch = n_dopp = n_fehlt = n_spanf = n_abd = n_ohne_p = 0
        pruef[lg] = []
        for cid, liste in kap.items():
            for t, q, zt in liste:
                e = res_lg.get(cid, {}).get(t) or {}
                n_s += 1
                h = satz_hash(q, zt)
                al = json.loads(json.dumps(e.get("a"))) if e.get("a") else None
                if al is None:
                    n_fehlt += 1
                    pruef[lg].append({"id": t, "quelle": q, "ziel": zt, "befund": ["fehlt"]})
                    continue
                kx = kk.get(t)
                if kx and kx.get("h") == h and kx.get("anker"):
                    _manuell_anwenden(al, zt, kx["anker"], src, lg)
                    zz["manuell"] += 1
                normieren(al, q, zt, src, lg)
                abd, spf = _ausgabe_pruefen(al, q, zt, src, lg)
                n_abd += 0 if abd else 1
                n_spanf += spf
                sp = ziel_spans(al, zt, reparatur=True, lg=lg)
                inh = [(w, s) for w, (s, _q) in zip(al, sp) if ist_inhaltswort(w.get(src), src)]
                ohne = [w["i"] for w, s in inh if not s]
                k = ketten(al, zt, e.get("p"), lg, kette) if e.get("p") is not None else []
                vs = sorted({i for x in k for i in x["treffer"]})
                dp = doppelt(al, lg)
                ur = [w["i"] for w in al if w.get("source") == "unresolved"]
                n_w += len(al)
                n_inh += len(inh)
                n_inh_a += len(inh) - len(ohne)
                n_unres += len(ur)
                n_versch += len(vs)
                n_dopp += len(dp)
                n_ohne_p += 1 if e.get("p") is None else 0
                ent = data["content"][t]
                ent[f"align_{lg}"] = al
                ent.setdefault("align_h", {})[lg] = h
                if k:
                    ent.setdefault("verschiebung", {})[lg] = k
                elif isinstance(ent.get("verschiebung"), dict):
                    ent["verschiebung"].pop(lg, None)
                if lg == erste:
                    ent["align"] = al
                bef = []
                if not abd or spf:
                    bef.append("abdeckung_span")
                if ur:
                    bef.append("unresolved")
                if vs:
                    bef.append("verschoben")
                if dp:
                    bef.append("doppelt")
                if bef:
                    pruef[lg].append({"id": t, "quelle": q, "ziel": zt, "befund": bef, "unresolved": ur,
                                      "verschoben": vs, "doppelt": dp, "ohne_anker": ohne,
                                      "nachlauf": e.get("nl")})
        a_inh = round(n_inh_a / n_inh, 4) if n_inh else 1.0
        a_ur = round(n_unres / n_w, 4) if n_w else 0.0
        a_vs = round(n_versch / n_w, 4) if n_w else 0.0
        a_dp = round(n_dopp / n_w, 4) if n_w else 0.0
        je_sprache[lg] = {"saetze": n_s, "woerter": n_w, "inhalt_mit_anker": a_inh, "unresolved": a_ur,
                          "verschoben": a_vs, "doppelt": a_dp, "fehlt": n_fehlt, "ohne_pruefung": n_ohne_p}
        bsp = lambda b_: [x["id"] for x in pruef[lg] if b_ in x["befund"]][:6]
        g.pruefe(f"abdeckung_{lg}", n_fehlt == 0 and n_abd == 0, wert=n_fehlt + n_abd, schwelle="= 0",
                 bei_fehler="stopp", text=f"{lg}: Abdeckung – {n_fehlt} Saetze ohne Alignment, {n_abd} mit falscher Wortzahl"
                 + (f" {bsp('fehlt') or bsp('abdeckung_span')}" if n_fehlt or n_abd else ""))
        g.pruefe(f"spans_{lg}", n_spanf == 0, wert=n_spanf, schwelle="= 0", bei_fehler="stopp",
                 text=f"{lg}: Spans ungueltig {n_spanf}" + (f" {bsp('abdeckung_span')}" if n_spanf else ""))
        g.pruefe(f"inhalt_{lg}", a_inh >= inhalt_min, wert=a_inh, schwelle=f">= {inhalt_min:.0%}", bei_fehler="mensch",
                 text=f"{lg}: Inhaltswoerter mit Anker {a_inh:.1%} (Soll >= {inhalt_min:.0%})")
        g.pruefe(f"unresolved_{lg}", a_ur <= unresolved_max, wert=a_ur, schwelle=f"<= {unresolved_max:.0%}",
                 bei_fehler="mensch", text=f"{lg}: unresolved {a_ur:.2%} (Soll <= {unresolved_max:.0%}) "
                 f"{bsp('unresolved') if a_ur > unresolved_max else ''}".rstrip())
        g.pruefe(f"verschoben_{lg}", a_vs <= verschoben_max, wert=a_vs, schwelle=f"<= {verschoben_max:.0%}",
                 bei_fehler="mensch", text=f"{lg}: verschoben {a_vs:.2%} (Soll <= {verschoben_max:.0%}) "
                 f"{bsp('verschoben') if a_vs > verschoben_max else ''}".rstrip())
        g.pruefe(f"doppelt_{lg}", a_dp <= doppelt_max, wert=a_dp, schwelle=f"<= {doppelt_max:.0%}",
                 bei_fehler="mensch", text=f"{lg}: doppelt belegte Anker {a_dp:.2%} (Soll <= {doppelt_max:.0%}) "
                 f"{bsp('doppelt') if a_dp > doppelt_max else ''}".rstrip())
        if pa == "an" and not trocken:
            g.pruefe(f"pruefaligner_{lg}", pa_fehler is None, wert=pa_fehler, bei_fehler="mensch",
                     text=f"{lg}: Pruefaligner nicht erreichbar ({pa_fehler}) – erneut laufen lassen oder "
                          f"--pruefaligner aus" if pa_fehler else f"{lg}: Pruefaligner gelaufen")
        if n_ohne_p and pa == "an":
            g.hinweis(f"ohne_pruefung_{lg}", False, wert=n_ohne_p,
                      text=f"{lg}: {n_ohne_p} Saetze ohne Pruefaligner-Ergebnis (verschoben dort nicht gemessen)")
        if pa != "an":
            g.hinweis(f"pruefaligner_{lg}", False, text=f"{lg}: Pruefaligner aus – verschoben nicht gemessen")

    g.mock(0 if mock.aktiv() else n_mock, ruecksprung="330")
    for k_, v in zz.items():
        g.metrik(k_, v)
    g.metrik("je_sprache", je_sprache)
    meta["wortalignment"] = {"modell": modell_eff, "prompt_v": PROMPT_V, "batch": batch, "pruefaligner": pa,
                             "kette": kette, "zielsprachen": ziele, "je_sprache": je_sprache,
                             "geprueft": manifest.jetzt()}
    ids = [t for t, e in (data.get("content") or {}).items() if isinstance(e, dict)]
    aus_hash = manifest.hash_obj({lg: {t: (data["content"][t] or {}).get(f"align_{lg}") for t in ids} for lg in ziele})
    g.metrik("ausgabe_hash", aus_hash)
    st = status.laden(werk)["stages"].get(STAGE) or {}
    if st.get("zustand") == "frei" and (st.get("gate") or {}).get("ergebnis") == "mensch" \
            and (st.get("metriken") or {}).get("ausgabe_hash") == aus_hash:
        for p in g.pruefungen:
            if not p["ok"] and p["bei_fehler"] == "mensch":
                p["bei_fehler"] = "hinweis"
                p["text"] += " [Mensch-Freigabe gilt, Ausgabe unveraendert]"
    if not trocken:
        manifest.json_atomar(config.work_path(werk, "340_wortalignment"), data, indent=2)
        manifest.json_atomar(os.path.join(config.work_dir(werk), "340_pruefung.json"), pruef, indent=1)
        if not nur_lang:
            ck.aufraeumen(ck_soll)
    g.entscheide(schreiben=not trocken)
    g.pruef = pruef
    return g


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 340 Wort-Alignment (inkl. Verschiebungspruefung 345)")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--modell")
    ap.add_argument("--batch", type=int)
    ap.add_argument("--kapitel", action="append", metavar="N|alle")
    ap.add_argument("--satz", action="append", metavar="ID", help="Satz neu alignen")
    ap.add_argument("--anker", action="append", metavar="ID:I=FRAGMENT", help="Anker manuell setzen (=- loeschen)")
    ap.add_argument("--pruefaligner", choices=["an", "aus"])
    ap.add_argument("--kette", type=int)
    ap.add_argument("--ankerverlust", type=float)
    ap.add_argument("--inhalt-min", type=float)
    ap.add_argument("--unresolved-max", type=float)
    ap.add_argument("--verschoben-max", type=float)
    ap.add_argument("--doppelt-max", type=float)
    ap.add_argument("--lang", help="nur diese Zielsprache")
    ap.add_argument("--uebernehmen", action="store_true")
    ap.add_argument("--trocken", action="store_true")
    a = ap.parse_args(argv)
    kap = ["alle"] if a.kapitel and "alle" in a.kapitel else a.kapitel
    try:
        if a.anker and not a.trocken:
            from pipeline import s080_mandant
            s080_mandant.darf(a.werk, "entscheiden", a.wer or "pipeline")
        g = run(a.werk, a.wer, a.modell, a.batch, kap, a.satz, a.anker, a.pruefaligner, a.kette, a.ankerverlust,
                a.inhalt_min, a.unresolved_max, a.verschoben_max, a.doppelt_max, a.lang, a.uebernehmen, a.trocken)
    except gate.GateHalt as e:
        print(e)
        return e.exit_code
    except (ValueError, PermissionError) as e:
        print(f"[340] Fehler: {e}")
        return 1
    print(g.bericht())
    return gate.EXIT[g.ergebnis["ergebnis"]]


if __name__ == "__main__":
    sys.exit(main())
