"""READ LAYER — Satzweise Knoten (CK 01.11.2026).

Regel (CK): ".", "!" und "?" beenden einen Satz. Ausnahmen nur bei woertlicher Rede:
  - Redebegleitsatz dahinter:  "Help!" cried Alice.  /  "Komm!" Alice rief.   (bleibt beim Redesatz)
  - ankuendigender Satz davor: Then Pooh said. "Hello."                      (bleibt beim Redesatz)
Technische Ausnahmen (kein Satzende): Abkuerzungen (Mr., Dr., z.B.), Initialen (A. A. Milne),
Ordinalzahlen (am 3. Mai), Auslassungspunkte (... / …), Kleinbuchstabe nach dem Satzzeichen.

Zwei Einsatzorte:
  1. Stage 200 (neue Werke): satzgrenzen() trennt Tags nach dem LLM-Tagging deterministisch.
  2. Export (bestehende Werke): teile_ordner(<demo>/<slug>) teilt Mehrsatz-Knoten im exportierten
     Werk. Audio wird NICHT geschnitten: jeder Teil verweist mit clip_begin/clip_end auf dieselbe
     WAV (die App spielt Clip-Fenster lueckenlos weiter). Wortzeiten und Anker (t/tz/ths/tzhs, Spans)
     werden je Teil neu bezogen. EN und DE werden ueber die Wortanker gekoppelt; laesst sich eine
     Grenze nicht sicher in beide Sprachen uebertragen, bleiben die Saetze dort zusammen.
     Teil 1 behaelt die tag_id, weitere Teile heissen <tag_id>-2, -3, ...; alle tragen basis_tag.

Aufruf:
  python tools/satzweise.py <ordner> [<ordner> ...] [--trocken]     z. B. ../taella-app/public/demo/winnie-the-pooh
  python tools/satzweise.py --alle <demo-ordner> [--trocken]        alle Werke mit manifest_en/de.json
"""
import json
import re
import sys
from pathlib import Path

OEFFNER = "\"'“„«»‚‘‹›(["
SCHLIESSER = "\"'”“’‘»«›‹)]"
ABK = {
    # EN
    "mr", "mrs", "ms", "dr", "st", "mt", "jr", "sr", "vs", "etc", "e.g", "i.e", "no", "prof", "rev", "gen",
    "col", "capt", "lt", "sgt", "gov", "messrs", "esq", "ft", "vol", "ch", "fig", "cf", "viz", "co", "inc",
    # DE
    "hr", "fr", "frl", "nr", "z.b", "d.h", "u.a", "usw", "bzw", "ca", "vgl", "str", "kap", "bd", "s", "jh",
    "geb", "gest", "evtl", "ggf", "inkl", "u", "o", "z", "d", "sog", "bspw", "allg", "abs", "dt", "engl",
}
REDEVERBEN = {
    "said", "says", "say", "cried", "asked", "replied", "answered", "thought", "whispered", "shouted",
    "exclaimed", "added", "continued", "remarked", "called", "muttered", "murmured", "observed", "explained",
    "repeated", "growled", "sighed", "laughed", "screamed", "yelled", "insisted",
    "suggested", "declared", "inquired", "enquired", "protested", "agreed", "interrupted", "sobbed",
    "hummed", "sang", "retorted", "snapped", "grumbled", "pleaded", "demanded",
    "sagte", "sagt", "rief", "fragte", "antwortete", "erwiderte", "dachte", "flüsterte", "schrie",
    "meinte", "bemerkte", "murmelte", "erklärte", "fügte", "seufzte", "lachte", "brummte", "summte", "sang",
    "entgegnete", "versetzte", "wiederholte", "jammerte", "knurrte", "stöhnte",
}
TEILBARE_TYPEN = {"s", "dl", "qt", "fn", "ep"}
_KANDIDAT = re.compile(r"[.!?]+[" + re.escape(SCHLIESSER) + r"]*(?=\s)")
_WORT = re.compile(r"[\w’'-]+", re.UNICODE)


def _woerter(s):
    return [w.lower() for w in _WORT.findall(s)]


def _hat_redeverb(s):
    return any(w in REDEVERBEN for w in _woerter(s))


def _hat_rede(s):
    return any(c in s for c in "\"“”„«»")


def satzgrenzen(text, lang="en"):
    """Startpositionen (Zeichenindex > 0) der Saetze 2..n in text, nach der CK-Regel."""
    if not text:
        return []
    roh = []
    for m in _KANDIDAT.finditer(text):
        zeichen = m.group().rstrip(SCHLIESSER)
        j = m.end()
        while j < len(text) and text[j].isspace():
            j += 1
        if j >= len(text):
            continue
        k = j
        while k < len(text) and text[k] in OEFFNER:
            k += 1
        if k >= len(text):
            continue
        if not (text[k].isupper() or text[k].isdigit()):
            continue                                    # Kleinbuchstabe: Redebegleitsatz / Satz laeuft weiter
        if ".." in zeichen:
            continue                                    # Auslassungspunkte
        if zeichen == "." and m.group() == ".":
            vor = re.search(r"(\S+)$", text[:m.start()])
            w = (vor.group(1) if vor else "").lstrip(OEFFNER)
            wl = w.lower()
            if wl in ABK or re.fullmatch(r"[^\W\d_]", w) or w.isdigit() or re.fullmatch(r"[ivxlcdm]+", wl) and len(wl) <= 4 and w.isupper():
                continue                                # Abkuerzung, Initiale, Ordinalzahl, roem. Zahl
            if re.fullmatch(r"(?:[^\W\d_]\.)+[^\W\d_]", w):
                continue                                # z.B, d.h, e.g (Punkt im Wort)
        roh.append((m, j))
    # Ausnahmen woertliche Rede (Redebegleitsatz dahinter / ankuendigender Satz davor)
    grenzen = [j for _, j in roh]
    behalten = []
    for idx, (m, j) in enumerate(roh):
        start_vor = grenzen[idx - 1] if idx > 0 else 0
        ende_nach = grenzen[idx + 1] if idx + 1 < len(grenzen) else len(text)
        vorher, nachher = text[start_vor:m.end()], text[j:ende_nach]
        rede_endet = any(c in SCHLIESSER for c in m.group()) and _hat_rede(vorher)
        if rede_endet and text[j] not in OEFFNER and len(_woerter(nachher)) <= 8 \
                and not _hat_rede(nachher) and _hat_redeverb(nachher):
            continue                                    # "Help!" Alice cried.
        if text[j] in OEFFNER and not _hat_rede(vorher) and len(_woerter(vorher)) <= 8 \
                and _hat_redeverb(vorher):
            continue                                    # Then Pooh said. "Hello."
        behalten.append(j)
    return behalten


def teile_text(text, lang="en"):
    """Liste der Saetze (fuer Stage 200)."""
    gr = satzgrenzen(text, lang)
    starts = [0] + gr + [len(text)]
    return [text[a:b].strip() for a, b in zip(starts, starts[1:]) if text[a:b].strip()]


# ------------------------------------------------------------------ Export: bestehende Werke

def _token_starts(text):
    return [m.start() for m in re.finditer(r"\S+", text)]


def _zielspans(a, zs):
    if a.get("zspans"):
        return [list(s) for s in a["zspans"]]
    return [list(a[zs])] if isinstance(a.get(zs), list) else []


def _schnittzeit(wt, i):
    """Schnittzeitpunkt vor Token i (etwas Vorlauf, nie vor dem Vortoken). None = unbekannt."""
    if wt is None or i >= len(wt) or wt[i] is None:
        return None
    t = wt[i] - 0.06
    if i > 0 and wt[i - 1] is not None:
        t = max(t, wt[i - 1] + 0.05)
    return round(max(0.0, t), 3)


def _ziel_schnitte(ts, tz, schnitte_q, anker, qs, zs, ziel):
    """Uebertraegt Quell-Satzgrenzen ueber die Anker in den Zieltext. Liefert [(q, z), ...].
    Je Grenze gewinnt die Ziel-Satzgrenze mit den wenigsten widersprechenden Ankern
    (hoechstens 1 bzw. 10 %); widersprechende Anker verlieren beim Teilen ihr Gegenstueck."""
    kand = satzgrenzen(tz, ziel)
    mit_ziel = [a for a in anker if isinstance(a.get(qs), list) and _zielspans(a, zs)]
    paare, letzt = [], 0
    if not mit_ziel:
        if len(kand) == len(schnitte_q):
            return list(zip(schnitte_q, kand))
        return []
    toleranz = max(1, int(0.1 * len(mit_ziel)))
    for b in schnitte_q:
        vor = [s for a in mit_ziel if a[qs][1] <= b for s in _zielspans(a, zs)]
        nach = [s for a in mit_ziel if a[qs][0] >= b for s in _zielspans(a, zs)]
        c = [z for z in kand if z > letzt]
        if not c:
            continue
        soll = b / max(1, len(ts)) * len(tz)
        def fehler(z):
            return sum(1 for s in vor if s[1] > z) + sum(1 for s in nach if s[0] < z)
        z = min(c, key=lambda x: (fehler(x), abs(x - soll)))
        if fehler(z) > toleranz:
            continue
        paare.append((b, z))
        letzt = z
    return paare


def _vorkommen(text, frag):
    """Fundstellen von frag in text auf Wortgrenzen."""
    out, i = [], text.find(frag)
    while i >= 0:
        vor_ok = i == 0 or not text[i - 1].isalnum()
        j = i + len(frag)
        nach_ok = j >= len(text) or not text[j].isalnum()
        if vor_ok and nach_ok:
            out.append(i)
        i = text.find(frag, i + 1)
    return out


def anker_reparieren(nq, nz, quelle, ziel, wt_z, wths_z):
    """Doppelte Woerter (Befund 8, 01.11.2026): Stage 340 nahm bei Wiederholungen oft das falsche
    Vorkommen im Zielsatz. Fuer mehrdeutige Anker wird das Vorkommen gewaehlt, das am besten zwischen
    die eindeutigen Nachbaranker passt; tz/tzhs werden aus den Ziel-Wortzeiten neu bestimmt."""
    anker = nq.get("align") or []
    tz = nz.get("text") or ""
    ts = nq.get("text") or ""
    qs, zs = f"{quelle}_span", f"{ziel}_span"
    if not anker or not tz:
        return 0
    kandidaten, eindeutig = {}, []
    for k, a in enumerate(anker):
        sp, q = a.get(zs), a.get(qs)
        if a.get("zspans") or not isinstance(sp, list) or not isinstance(q, list):
            continue
        v = _vorkommen(tz, tz[sp[0]:sp[1]])
        if len(v) > 1:
            kandidaten[k] = v
        elif len(v) == 1:
            eindeutig.append((q[0], sp[0]))
    if not kandidaten:
        return 0
    eindeutig.sort()
    tok = _token_starts(tz)
    geaendert = 0
    for k, v in kandidaten.items():
        a = anker[k]
        q0, sp = a[qs][0], a[zs]
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
            soll = q0 / max(1, len(ts)) * len(tz)
        best = min(v, key=lambda x: abs(x - soll))
        if best == sp[0] or abs(best - soll) + 0.1 * len(tz) >= abs(sp[0] - soll):
            continue                                    # nur deutliche Ausreisser umhaengen
        laenge = sp[1] - sp[0]
        a[zs] = [best, best + laenge]
        ti = sum(1 for p in tok if p <= best) - 1
        for key, w in (("tz", wt_z), ("tzhs", wths_z)):
            if key not in a:
                continue
            if w is None or ti < 0 or ti >= len(w) or w[ti] is None or not a[key] or not isinstance(a[key][0], list):
                a.pop(key, None)
                continue
            alt = a[key][0]
            dauer = max(0.05, alt[1] - alt[0])
            t0 = w[ti]
            t1 = t0 + dauer
            if ti + 1 < len(w) and w[ti + 1] is not None:
                t1 = min(t1, w[ti + 1])
            a[key] = [[round(t0, 3), round(max(t0 + 0.02, t1), 3)]]
        geaendert += 1
    return geaendert


def _teile_knoten(nq, nz, quelle, ziel, wt, wths, hs_saetze):
    """Teilt ein Knotenpaar. Rueckgabe (teile_q, teile_z, wt_neu, wths_neu) oder (None, grund)."""
    if nq.get("typ") not in TEILBARE_TYPEN or nz is None:
        return None, "typ"
    if "clip_begin" in nq or "clip_begin" in nz or "basis_tag" in nq:
        return None, "schon_geteilt"
    ts, tz = nq.get("text") or "", nz.get("text") or ""
    sq = satzgrenzen(ts, quelle)
    if not sq:
        return None, "ein_satz"
    qs, zs = f"{quelle}_span", f"{ziel}_span"
    anker = nq.get("align") or []
    paare = _ziel_schnitte(ts, tz, sq, anker, qs, zs, ziel)
    if not paare:
        return None, "nicht_koppelbar"
    tag = nq["tag_id"]
    texte = {quelle: ts, ziel: tz}
    knoten = {quelle: nq, ziel: nz}
    starts = {quelle: [0] + [p[0] for p in paare], ziel: [0] + [p[1] for p in paare]}
    n = len(starts[quelle])

    # Token-Indizes je Teil und Schnittzeiten (Erzaehler / Hoerspiel)
    tok_ix, zeiten, zeiten_hs = {}, {}, {}
    for lg in (quelle, ziel):
        ts_l = _token_starts(texte[lg])
        tok_ix[lg] = [sum(1 for p in ts_l if p < s) for s in starts[lg]] + [len(ts_l)]
        hat_audio = bool(knoten[lg].get("audio_path"))
        w = wt.get(lg, {}).get(tag)
        if hat_audio:
            if w is None or len(w) != len(ts_l):
                return None, f"wortzeiten_{lg}"
            z = [0.0] + [_schnittzeit(w, i) for i in tok_ix[lg][1:-1]]
            if any(x is None for x in z):
                return None, f"wortzeiten_luecke_{lg}"
            zeiten[lg] = z
        if tag in hs_saetze.get(lg, set()):
            wh = wths.get(lg, {}).get(tag)
            if wh is None or len(wh) != len(ts_l):
                return None, f"hoerspiel_wortzeiten_{lg}"
            zh = [0.0] + [_schnittzeit(wh, i) for i in tok_ix[lg][1:-1]]
            if any(x is None for x in zh):
                return None, f"hoerspiel_luecke_{lg}"
            zeiten_hs[lg] = zh

    def tid(k):
        return tag if k == 0 else f"{tag}-{k + 1}"

    teile = {quelle: [], ziel: []}
    wt_neu = {quelle: {}, ziel: {}}
    wths_neu = {quelle: {}, ziel: {}}
    for lg in (quelle, ziel):
        text = texte[lg]
        st = starts[lg] + [len(text)]
        for k in range(n):
            roh = text[st[k]:st[k + 1]]
            off = st[k] + (len(roh) - len(roh.lstrip()))
            t = roh.strip()
            neu = {kk: vv for kk, vv in knoten[lg].items() if kk != "align"}
            neu.update(tag_id=tid(k), text=t, basis_tag=tag)
            if lg in zeiten:
                if k > 0:
                    neu["clip_begin"] = zeiten[lg][k]
                if k < n - 1:
                    neu["clip_end"] = zeiten[lg][k + 1]
                w = wt[lg][tag][tok_ix[lg][k]:tok_ix[lg][k + 1]]
                wt_neu[lg][tid(k)] = [None if x is None else round(x - zeiten[lg][k], 3) for x in w]
            if lg in zeiten_hs:
                if k > 0:
                    neu["hs_begin"] = zeiten_hs[lg][k]
                if k < n - 1:
                    neu["hs_end"] = zeiten_hs[lg][k + 1]
                w = wths[lg][tag][tok_ix[lg][k]:tok_ix[lg][k + 1]]
                wths_neu[lg][tid(k)] = [None if x is None else round(x - zeiten_hs[lg][k], 3) for x in w]
            neu["_off"] = off
            neu["_ende"] = st[k + 1]
            teile[lg].append(neu)

    # Anker auf die Teile verteilen (liegen im Manifest der Originalsprache)
    if anker:
        for k, tq in enumerate(teile[quelle]):
            tz_ = teile[ziel][k]
            oq, eq, oz, ez = tq["_off"], tq["_ende"], tz_["_off"], tz_["_ende"]
            bq, bz = (zeiten.get(quelle) or [0.0] * n)[k], (zeiten.get(ziel) or [0.0] * n)[k]
            bqh, bzh = (zeiten_hs.get(quelle) or [0.0] * n)[k], (zeiten_hs.get(ziel) or [0.0] * n)[k]
            neu_anker = []
            for a in anker:
                sp = a.get(qs)
                if not isinstance(sp, list) or not (oq <= sp[0] < eq):
                    continue
                b = dict(a)
                b[qs] = [sp[0] - oq, sp[1] - oq]
                for key, basis in (("t", bq), ("ths", bqh)):
                    if isinstance(b.get(key), list):
                        b[key] = [round(x - basis, 3) for x in b[key]]
                zsp = _zielspans(a, zs)
                behalte = [i for i, s in enumerate(zsp) if oz <= s[0] < ez]
                if zsp and len(behalte) == len(zsp):
                    if a.get("zspans"):
                        b["zspans"] = [[s[0] - oz, s[1] - oz] for s in zsp]
                    if isinstance(a.get(zs), list):
                        b[zs] = [a[zs][0] - oz, a[zs][1] - oz]
                    for key, basis in (("tz", bz), ("tzhs", bzh)):
                        if isinstance(b.get(key), list):
                            b[key] = [[round(w[0] - basis, 3), round(w[1] - basis, 3)] if isinstance(w, list) else w
                                      for w in b[key]]
                else:
                    for key in (zs, "zspans", "tz", "tzhs"):
                        b.pop(key, None)        # Gegenstueck liegt in einem anderen Satz: nur Flyover-Wort
                neu_anker.append(b)
            tq["align"] = neu_anker
    for lg in (quelle, ziel):
        for t in teile[lg]:
            t.pop("_off", None)
            t.pop("_ende", None)
    return (teile[quelle], teile[ziel], wt_neu, wths_neu), None


def _lade(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def teile_ordner(ordner, trocken=False, sichern=None):
    """Teilt alle Mehrsatz-Knoten eines exportierten Werkordners. Rueckgabe: Bericht (dict)."""
    ordner = Path(ordner)
    m = {lg: _lade(ordner / f"manifest_{lg}.json") for lg in ("en", "de")}
    if not m["en"] or not m["de"]:
        return {"ordner": str(ordner), "fehler": "manifest fehlt"}
    quelle = m["en"].get("originalsprache") or m["de"].get("originalsprache") or "en"
    ziel = "de" if quelle == "en" else "en"
    wt_d = {lg: _lade(ordner / f"wordtimes_{lg}.json") for lg in ("en", "de")}
    wh_d = {lg: _lade(ordner / f"wordtimes_{lg}_hoerspiel.json") for lg in ("en", "de")}
    wt = {lg: (wt_d[lg] or {}).get("tags", {}) for lg in ("en", "de")}
    wths = {lg: (wh_d[lg] or {}).get("tags", {}) for lg in ("en", "de")}
    hs_saetze = {lg: set(m[lg].get("hoerspiel_saetze") or []) for lg in ("en", "de")}

    zielknoten = {s["tag_id"]: s for s in m[ziel]["saetze"]}
    ersatz = {quelle: {}, ziel: {}}
    bericht = {"ordner": str(ordner), "knoten": 0, "geteilt": 0, "teile": 0, "uebersprungen": {}}
    bericht["anker_repariert"] = 0
    for nq in m[quelle]["saetze"]:
        bericht["knoten"] += 1
        nz0 = zielknoten.get(nq["tag_id"])
        if nz0 is not None and not nq.get("basis_tag"):
            bericht["anker_repariert"] += anker_reparieren(
                nq, nz0, quelle, ziel, wt[ziel].get(nq["tag_id"]), wths[ziel].get(nq["tag_id"]))
        res, grund = _teile_knoten(nq, zielknoten.get(nq["tag_id"]), quelle, ziel, wt, wths, hs_saetze)
        if res is None:
            if grund not in ("typ", "ein_satz"):
                bericht["uebersprungen"][grund] = bericht["uebersprungen"].get(grund, 0) + 1
            continue
        tq, tz, wt_neu, wths_neu = res
        tag = nq["tag_id"]
        ersatz[quelle][tag], ersatz[ziel][tag] = tq, tz
        bericht["geteilt"] += 1
        bericht["teile"] += len(tq)
        for lg in (quelle, ziel):
            if wt_neu[lg]:
                wt[lg].pop(tag, None)
                wt[lg].update(wt_neu[lg])
            if wths_neu[lg]:
                wths[lg].pop(tag, None)
                wths[lg].update(wths_neu[lg])
            if tag in hs_saetze[lg]:
                neu_ids = [t["tag_id"] for t in (tq if lg == quelle else tz)]
                hl = m[lg]["hoerspiel_saetze"]
                pos = hl.index(tag)
                m[lg]["hoerspiel_saetze"] = hl[:pos] + neu_ids + hl[pos + 1:]
                sp = (m[lg].get("hoerspiel_sprecher") or {})
                if tag in sp:
                    for i in neu_ids:
                        sp[i] = sp[tag]
    if trocken or not (bericht["geteilt"] or bericht["anker_repariert"]):
        return bericht
    if sichern:
        sichern = Path(sichern)
        sichern.mkdir(parents=True, exist_ok=True)
        for p in ordner.glob("*.json"):
            if p.name.startswith(("manifest_", "wordtimes_")):
                (sichern / p.name).write_bytes(p.read_bytes())
    for lg in ("en", "de"):
        neu = []
        for s in m[lg]["saetze"]:
            neu.extend(ersatz[lg].get(s["tag_id"], [s]))
        m[lg]["saetze"] = neu
        m[lg]["satzweise"] = True
        (ordner / f"manifest_{lg}.json").write_text(
            json.dumps(m[lg], ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        if wt_d[lg]:
            wt_d[lg]["tags"] = wt[lg]
            (ordner / f"wordtimes_{lg}.json").write_text(json.dumps(wt_d[lg], separators=(",", ":")), encoding="utf-8")
        if wh_d[lg]:
            wh_d[lg]["tags"] = wths[lg]
            (ordner / f"wordtimes_{lg}_hoerspiel.json").write_text(
                json.dumps(wh_d[lg], separators=(",", ":")), encoding="utf-8")
    return bericht


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    trocken = "--trocken" in sys.argv
    if "--alle" in sys.argv:
        demo = Path(args[0])
        ordner = sorted(p.parent for p in demo.glob("*/manifest_en.json")
                        if not p.parent.name.startswith("_"))
    else:
        ordner = [Path(a) for a in args]
    if not ordner:
        sys.exit(__doc__)
    import datetime
    stempel = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    for o in ordner:
        sich = Path(__file__).resolve().parents[1] / "archive" / f"{stempel}_satzweise" / o.name
        b = teile_ordner(o, trocken=trocken, sichern=sich)
        print(json.dumps(b, ensure_ascii=False))
