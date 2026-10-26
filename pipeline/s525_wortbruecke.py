"""STAGE 525 — Wortbruecke (Tokenisierungsbruecke 340 <-> MMS_FA)
Funktion:      Gibt jedem Quellwort (Index i aus s340) eindeutig seine Wortzeit im Quell-Audio
               und jedem Ziel-Anker (de_span, auch mehrere je Wort) seine Wortzeit im Ziel-Audio.
Wirkungsweise: Gemeinsame Wahrheit ist die ZEICHENPOSITION im Satztext, nie ein Wortindex.
               1) lautwoerter(): Satztext -> MMS_FA-Lautwoerter mit Offset (Apostroph ’ -> ',
                  Bindestrich trennt, Ziffern/Satzzeichen sind keine Lautwoerter).
               2) bind_to_tokens(): Lautwort-Zeiten -> \\S+-Token (Mitte des Lautworts im Token-Span;
                  mehrere Lautwoerter je Token = ein Fenster). Diese Funktion nutzt s520 fuer BEIDE Sprachen.
               3) tokenzeiten(): Token ohne Zeit (Zahl, nicht darstellbares Zeichen) werden zwischen
                  zeitlich bekannten Nachbarn interpoliert (tq="interp"); reine Satzzeichen-Token bleiben leer.
               4) ziel_spans(): de_span aus s340; fehlt er (gap_fallback/unresolved), wird das Fragment
                  im Zielsatz neu verortet, Teile ("tauchte ... ein") einzeln -> mehrere Spans (sq="repariert").
               5) zeit_fuer_span(): Span -> Ziel-Tokens; Teil eines Tokens (Kompositum, "Santa-Clara-Tal")
                  bekommt den Zeitanteil nach Buchstabenposition, mehrere Tokens die Vereinigung.
Komponenten:   pipeline/s525_wortbruecke.py (einzige Stelle fuer Lautwort-Zerlegung + Token-Bindung)
Zulieferer:    s340/s345 (work/340_wortalignment.json), s520 (work/520_wortzeiten_<lg>.json)
Abnehmer:      s520 (lautwoerter, bind_to_tokens), s710 Cloud-Export (Felder t / tz / Ziel-Span je Anker),
               TAELLA-App. Ausgabe: work/525_wortbruecke.json
               { "tags": { tid: [ {"i", "t":[t0,t1]|null, "tq", "zspans":[[a,b],..], "tz":[[t0,t1],..]|null, "sq"} ] },
                 "messung": {"vorher": {...}, "nachher": {...}} }
Aufruf:        python -m pipeline.s525_wortbruecke <werk>
(AP 54b, 26.10.2026)
AP 55 (26.10.2026): richtungsneutral (Quelle aus book.json, auch DE-Original); Hoerspiel-Zeiten je Anker
               ths (Quell-Hoerspiel-Clip) / tzhs (Ziel-Hoerspiel-Clip) aus 520_wortzeiten_<lg>_hoerspiel.json.
"""
import os
import re
import sys
import json
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config

STAGE = "525"
_APO = str.maketrans({"\u2019": "'", "\u2018": "'", "\u02bc": "'"})   # gleiche Laenge -> Offsets bleiben
_LAUT = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)*")
_TOK = re.compile(r"\S+")
_WORT = re.compile(r"[^\W_]")


# ---------------------------------------------------------------------------
# 1) Lautwoerter fuer MMS_FA
# ---------------------------------------------------------------------------
def romanisieren(w):
    """Umlaute/Akzente auf a-z von MMS_FA: ae/oe/ue -> a/o/u, sz -> ss, Akzente weg."""
    w = w.replace("\u00df", "ss")
    w = unicodedata.normalize("NFKD", w)
    return "".join(c for c in w if not unicodedata.combining(c))


def lautwoerter(text):
    """[{"c0","c1","w"}] mit Offsets im ORIGINALTEXT."""
    t = (text or "").translate(_APO)
    out = []
    for m in _LAUT.finditer(t):
        w = romanisieren(m.group().lower()).strip("'")
        if w:
            out.append({"c0": m.start(), "c1": m.end(), "w": w})
    return out


def token_spans(text):
    return [(m.start(), m.end()) for m in _TOK.finditer(text or "")]


# ---------------------------------------------------------------------------
# 2) Lautwort-Zeiten -> \S+-Token (von s520 genutzt)
# ---------------------------------------------------------------------------
def bind_to_tokens(zeiten, text):
    """zeiten = [{c0,c1,t0,t1}] -> [{"i","t0","t1"}], i = \\S+-Index (= s340-Index in der Quellsprache)."""
    spans = token_spans(text)
    treffer = {}
    for z in zeiten:
        mitte = (z["c0"] + z["c1"]) / 2.0
        for i, (a, b) in enumerate(spans):
            if a <= mitte <= b:
                if i in treffer:
                    treffer[i][0] = min(treffer[i][0], z["t0"])
                    treffer[i][1] = max(treffer[i][1], z["t1"])
                else:
                    treffer[i] = [z["t0"], z["t1"]]
                break
    return [{"i": i, "t0": round(v[0], 3), "t1": round(v[1], 3)} for i, v in sorted(treffer.items())]


# ---------------------------------------------------------------------------
# 3) Zeiten je Token, Luecken interpolieren
# ---------------------------------------------------------------------------
def tokenzeiten(text, eintraege, reparatur=True):
    """-> (spans, zeiten[[t0,t1]|None], quelle["fa"|"interp"|None]) je \\S+-Token."""
    spans = token_spans(text)
    z = [None] * len(spans)
    q = [None] * len(spans)
    for e in eintraege or []:
        i = e.get("i")
        if isinstance(i, int) and 0 <= i < len(z):
            z[i] = [e["t0"], e["t1"]]
            q[i] = "fa"
    if not reparatur:
        return spans, z, q
    k = 0
    while k < len(z):
        if z[k] is None and _WORT.search(text[spans[k][0]:spans[k][1]]):
            lauf = [k]
            j = k + 1
            while j < len(z) and z[j] is None:
                if _WORT.search(text[spans[j][0]:spans[j][1]]):
                    lauf.append(j)
                j += 1
            prev = next((z[p] for p in range(k - 1, -1, -1) if z[p]), None)
            nach = z[j] if j < len(z) else None
            if prev and nach:
                t0, t1 = prev[1], max(prev[1], nach[0])
                d = (t1 - t0) / len(lauf)
                for n, m in enumerate(lauf):
                    z[m] = [round(t0 + n * d, 3), round(t0 + (n + 1) * d, 3)]
                    q[m] = "interp"
            k = j
        else:
            k += 1
    return spans, z, q


# ---------------------------------------------------------------------------
# 4) Ziel-Spans je Anker (inkl. Reparatur fehlender Spans)
# ---------------------------------------------------------------------------
_RAND = re.compile(r"^[^\wÄÖÜäöüß]+|[^\wÄÖÜäöüß]+$")


def _grenze(text, a, b):
    vor = a == 0 or not text[a - 1].isalpha()
    nach = b == len(text) or not text[b].isalpha()
    return vor and nach


def _finde(text, frag, von, bis):
    """Alle wortgrenzen-sauberen Treffer (auch case-insensitive); bevorzugt im Fenster [von, bis]."""
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


def ziel_spans(align, ziel_text, reparatur=True):
    """-> je Anker (spans, quelle) ; quelle '340' | 'repariert' | None."""
    _, k_tgt, k_tgt_span = config.align_keys()
    roh = [_spans_aus(w, k_tgt_span) for w in align]
    out = []
    for n, w in enumerate(align):
        if roh[n]:
            out.append((roh[n], "340"))
            continue
        frag = w.get(k_tgt)
        # Schutz: s340-Lueckenfuellung ist nur glaubwuerdig, wenn sie kurz ist (<= 2 Woerter, kein Satzende)
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


# ---------------------------------------------------------------------------
# 5) Span -> Zeitfenster
# ---------------------------------------------------------------------------
def zeit_fuer_span(span, spans, z, text, reparatur=True):
    hits = [k for k, (a, b) in enumerate(spans) if a < span[1] and span[0] < b and z[k]]
    if not hits:
        return None
    if len(hits) == 1 and reparatur:
        k = hits[0]
        a, b = spans[k]
        tok = text[a:b]
        m = [i for i, c in enumerate(tok) if c.isalnum()]
        if m:
            ca, cb = a + m[0], a + m[-1] + 1
            s0, s1 = max(span[0], ca), min(span[1], cb)
            if (s0 > ca or s1 < cb) and s1 > s0:
                t0, t1 = z[k]
                d = (t1 - t0) / (cb - ca)
                return [round(t0 + (s0 - ca) * d, 3), round(t0 + (s1 - ca) * d, 3)]
    return [min(z[k][0] for k in hits), max(z[k][1] for k in hits)]


# ---------------------------------------------------------------------------
# Bruecke je Satz + Messung
# ---------------------------------------------------------------------------
def bruecke_satz(quell_text, ziel_text, align, quell_520, ziel_520, reparatur=True, quell_hs=None, ziel_hs=None):
    q_sp, q_z, q_q = tokenzeiten(quell_text, quell_520, reparatur)
    z_sp, z_z, _ = tokenzeiten(ziel_text, ziel_520, reparatur)
    zsp = ziel_spans(align, ziel_text, reparatur)
    out = []
    for w, (spans, sq) in zip(align, zsp):
        i = w.get("i")
        t = q_z[i] if isinstance(i, int) and i < len(q_z) else None
        tz = None
        if spans and ziel_520 is not None:
            fen = [zeit_fuer_span(s, z_sp, z_z, ziel_text, reparatur) for s in spans]
            fen = [f for f in fen if f]
            tz = fen or None
        out.append({"i": i, "t": t, "tq": q_q[i] if t else None,
                    "zspans": spans, "tz": tz, "sq": sq})
    # AP 55: Hoerspiel-Clips haben eigene Zeiten -> ths/tzhs aus 520_wortzeiten_<lg>_hoerspiel (nur wo vorhanden)
    if quell_hs:
        _, h_z, _ = tokenzeiten(quell_text, quell_hs, reparatur)
        for w in out:
            i = w["i"]
            if isinstance(i, int) and i < len(h_z) and h_z[i]:
                w["ths"] = h_z[i]
    if ziel_hs:
        h_sp, h_z, _ = tokenzeiten(ziel_text, ziel_hs, reparatur)
        for w in out:
            if w["zspans"]:
                fen = [f for f in (zeit_fuer_span(s, h_sp, h_z, ziel_text, reparatur) for s in w["zspans"]) if f]
                if fen:
                    w["tzhs"] = fen
    return out


def _leer():
    return {"woerter": 0, "anker": 0, "zeit_quelle": 0, "zeit_ziel": 0, "anker_und_zeit_quelle": 0,
            "anker_und_beide_zeiten": 0, "spans_repariert": 0, "zeit_interpoliert": 0, "mehrere_spans": 0}


def messen(tags, content):
    src = config.SOURCE_LANGUAGE
    m = _leer()
    for tid, ws in tags.items():
        text = content[tid].get(src, "")
        sp = token_spans(text)
        for w in ws:
            i = w["i"]
            if not (isinstance(i, int) and i < len(sp) and _WORT.search(text[sp[i][0]:sp[i][1]])):
                continue   # reine Satzzeichen-Token zaehlen nicht als Wort
            m["woerter"] += 1
            a, tq, tz = bool(w["zspans"]), bool(w["t"]), bool(w["tz"])
            m["anker"] += a
            m["zeit_quelle"] += tq
            m["zeit_ziel"] += tz
            m["anker_und_zeit_quelle"] += a and tq
            m["anker_und_beide_zeiten"] += a and tq and tz
            m["spans_repariert"] += w["sq"] == "repariert"
            m["zeit_interpoliert"] += w["tq"] == "interp"
            m["mehrere_spans"] += len(w["zspans"]) > 1
    n = max(1, m["woerter"])
    m["prozent"] = {k: round(100.0 * v / n, 2) for k, v in m.items() if k != "woerter"}
    return m


def run(book_id, reparatur=True):
    config.werk_sprachen(book_id)   # AP 55: Richtung aus book.json (DE-Original -> Quelle de) VOR dem ersten Zugriff
    src = config.SOURCE_LANGUAGE
    tgt = config.TARGET_LANGUAGES[0]
    content = json.load(open(config.work_path(book_id, "340_wortalignment"), encoding="utf-8"))["content"]

    def lade(lg, zusatz=""):
        p = config.work_path(book_id, f"520_wortzeiten_{lg}{zusatz}")
        return json.load(open(p, encoding="utf-8")).get("tags", {}) if os.path.exists(p) else {}

    zq, zz = lade(src), lade(tgt)
    hq, hz = lade(src, "_hoerspiel"), lade(tgt, "_hoerspiel")   # AP 55
    erg = {}
    for modus in (False, True):
        tags = {}
        for tid, v in content.items():
            al = v.get("align")
            if not al:
                continue
            tags[tid] = bruecke_satz(v.get(src, ""), v.get(tgt, ""), al,
                                     zq.get(tid), zz.get(tid) if tid in zz else None, modus,
                                     hq.get(tid) if modus else None, hz.get(tid) if modus else None)
        erg["nachher" if modus else "vorher"] = (tags, messen(tags, content))
    hs = {"saetze_quelle": sum(1 for t in hq if t in erg["nachher"][0]), "saetze_ziel": sum(1 for t in hz if t in erg["nachher"][0]),
          "anker_ths": sum(1 for ws in erg["nachher"][0].values() for w in ws if w.get("ths")),
          "anker_tzhs": sum(1 for ws in erg["nachher"][0].values() for w in ws if w.get("tzhs"))}
    if hq or hz:
        print(f"[{STAGE}] Hoerspiel: {hs}")
    out = config.work_path(book_id, f"{STAGE}_wortbruecke")
    json.dump({"quelle": src, "ziel": tgt, "tags": erg["nachher"][0],
               "messung": {"vorher": erg["vorher"][1], "nachher": erg["nachher"][1]}, "hoerspiel": hs},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    for k in ("vorher", "nachher"):
        m = erg[k][1]
        print(f"[{STAGE}] {k:7s} Woerter {m['woerter']} | " +
              " | ".join(f"{a} {b}%" for a, b in m["prozent"].items()))
    print(f"[{STAGE}] Geschrieben: {out}")
    return erg["nachher"][1]


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    run(args[0] if args else "call-of-the-wild")
