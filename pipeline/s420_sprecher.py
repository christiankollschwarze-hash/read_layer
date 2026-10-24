"""STAGE 420 — Sprecherzuordnung
Funktion:     Ordnet Rede-Segmente einem Sprecher der Besetzung zu.
Wirkungsweise: Nur Absaetze mit Rede; DeepSeek in Teilen a 40 Saetze, Rekonstruktionspruefung, unsichere Faelle in sprecher_pruefen.txt.
Komponenten:  pipeline/s420_sprecher.py, api_layer
Zulieferer:   s400 Regie, s410 Casting (work/casting.json)
Abnehmer:     s510 Hoerspiel-Overlay, s540 Trennung (work/sprecher.json)
(Nomenklatur seit 18.10.2026, Uebersicht: docs/Pipeline_Strang_Matrix.xlsx)

--- Bisherige Beschreibung ---

READ LAYER — Stage 57b: Sprecher-Zuordnung je Dialogsatz (Mehrstimmigkeit)
===========================================================================
Zerlegt jeden Satz mit woertlicher Rede in Segmente (Zitat vs. Begleitsatz)
und ordnet jedem Segment einen Sprecher aus der Besetzung (work/casting.json) zu.
Getrennt fuer EN und DE (Anfuehrungszeichen und Wortstellung unterscheiden sich).

Input : work/400_regie.json, work/casting.json
Output: work/sprecher.json  {tag_id: {"en": [{"t": text, "s": sprecher}], "de": [...]}}
        sprecher = Figurenname aus der Besetzung (EN-Name) oder "Erzaehler"

Pruefung: Segmente muessen zusammengesetzt den Originalsatz ergeben (Leerraum egal),
sonst faellt der Satz auf "Erzaehler" zurueck (Hinweis im Log).

Aufruf: py -3.11 -m pipeline.s420_sprecher <book_id> [--kapitel c001,c007] [--neu]
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import api_layer

ERZ = "Erzaehler"
TYPEN = {"s", "dl", "qt"}


# 14.10.2026: Kosten-Hebel. Nur Saetze mit Rede-Spuren gehen ans LLM (+ Nachbarn als Kontext).
# Spur = Anfuehrungszeichen in EN oder DE ODER Satz liegt in einem noch offenen Zitat
# (mehrsaetzige Rede: mittlere Saetze haben keine Zeichen) ODER Tagger-Typ dl/qt.
# einfache Zeichen (‘ ’ ‚ ') bewusst NICHT: ’ ist meist Apostroph (Charles’s, don’t)
OEFFNEN, SCHLIESSEN, BEIDES = set("“„»"), set("”«"), set('"')


def _offen_nach(text, offen, lg="en"):
    for ch in text or "":
        if ch in BEIDES:
            offen = not offen
        elif ch == "“" and offen and lg != "en":   # DE: „…“ -> “ schliesst; EN: “ oeffnet immer
            offen = False
        elif ch in OEFFNEN:
            offen = True
        elif ch in SCHLIESSEN:
            offen = False
    return offen


def _kandidaten(eintraege, tgt, src="en"):
    ids, offen = set(), {src: False, tgt: False}
    zeichen = OEFFNEN | SCHLIESSEN | BEIDES
    for tid, e in eintraege:
        spur = e.get("type") in ("dl", "qt") or any(offen.values())
        for lg in (src, tgt):
            t = e.get(lg, "")
            if any(ch in zeichen for ch in t):
                spur = True
            offen[lg] = _offen_nach(t, offen[lg], lg)
        if spur:
            ids.add(tid)
    return ids


def _auswahl(eintraege, tgt, kapitel_alles=None, src="en"):
    """Ganze Absaetze mit Rede-Spur + je ein Nachbarsatz davor/danach.
    Absatzweise, weil die Segmentierung Wiederoeffnungs-Zeichen verliert
    ('“…,” said Mortimer. A glance at …' -> Folgesatz ohne Zeichen, spricht aber weiter)."""
    k = _kandidaten(eintraege, tgt, src)
    absatz, nr = {}, 0
    for tid, e in (kapitel_alles or eintraege):
        if e.get("type") in ("p", "h"):
            nr += 1
        absatz[tid] = nr
    rede_absaetze = {absatz.get(tid) for tid in k}
    idx = {tid: i for i, (tid, _) in enumerate(eintraege)}
    behalten = set()
    for tid, _ in eintraege:
        if absatz.get(tid) in rede_absaetze:
            i = idx[tid]
            behalten.update(eintraege[j][0] for j in (i - 1, i, i + 1) if 0 <= j < len(eintraege))
    return [(tid, e) for tid, e in eintraege if tid in behalten]


def _norm(t):
    return re.sub(r"\s+", "", t or "")


def _pfad(book_id):
    # READLAYER_57B_OUT: anderer Dateiname (z. B. Modellvergleich), sprecher.json bleibt unberuehrt
    return os.path.join(config.work_dir(book_id), os.environ.get("READLAYER_57B_OUT") or "sprecher.json")


def _besetzung(book_id):
    with open(os.path.join(config.work_dir(book_id), "casting.json"), encoding="utf-8") as f:
        c = json.load(f)
    namen = {}
    for f in c["steckbriefe"].get("figuren", []):
        namen[f["name"]] = f.get("name_de") or f["name"]
    return namen


def _ich_erzaehler(book_id):
    with open(os.path.join(config.work_dir(book_id), "casting.json"), encoding="utf-8") as f:
        return (json.load(f).get("plan") or {}).get("erzaehler_je_kapitel") or {}


def _prompt(eintraege, namen, tgt, src="en", ich=None):
    # 22.10.2026: Ich-Erzaehler je Kapitel (casting.json plan.erzaehler_je_kapitel) -> eigene Rede dieser Figur
    ich_regel = (f"\n- This chapter is told in the first person by {ich}. Quoted speech of the narrator ('I') -> \"{ich}\" "
                 f"(not \"{ERZ}\"); the narration itself stays \"{ERZ}\".") if ich else ""
    besetzung = "\n".join(f"- {en} (DE: {de})" for en, de in namen.items())
    zeilen = "\n".join(json.dumps({"id": tid, src: e.get(src, ""), tgt: e.get(tgt, "")}, ensure_ascii=False)
                       for tid, e in eintraege)
    return f"""You prepare a multi-voice audiobook. For every line below that contains spoken words (direct speech,
thoughts spoken aloud, songs or poems recited by a character), split the line into consecutive segments and say who
speaks each segment. Narration (e.g. "said Alice", "thought she") belongs to "{ERZ}".

CAST (use exactly these English names; anyone else -> the closest cast name, unknown -> "{ERZ}"):
{besetzung}

Rules:
- Do this separately for "{src}" and "{tgt}". Segments, concatenated in order, must reproduce the original text EXACTLY
  (same characters incl. quotation marks and punctuation; only whitespace between segments may differ).
- Keep quotation marks with the quoted segment. Keep the narrator part with the narrator.
- Identify the speaker from context (previous/next lines) when there is no attribution.
- Lines without any direct speech: omit them from the output.
- Inner thoughts of a character that are written as quotes ("thought Alice") -> that character.
- Attribution words like "said Holmes", "he cried", "answered Watson" are NARRATION -> separate "{ERZ}" segment.
- If you are NOT sure who speaks a segment (rapid exchanges without attribution, similar characters,
  ambiguous pronouns), still give your best guess but add "u": 1 to that segment. Be honest: mark real doubt.{ich_regel}

Return ONLY JSON: {{"<id>": {{"{src}": [{{"t": "...", "s": "<name>", "u": 1?}}], "{tgt}": [{{"t": "...", "s": "<name>"}}]}}}}

LINES (in reading order):
{zeilen}"""


def _pruefen(seg, original):
    return isinstance(seg, list) and seg and _norm("".join(x.get("t", "") for x in seg)) == _norm(original)


def run(book_id: str, kapitel=None, neu: bool = False, lang: str = None) -> dict:
    with open(config.work_path(book_id, "400_regie"), encoding="utf-8") as f:
        data = json.load(f)
    namen = _besetzung(book_id)
    ich_je_kap = _ich_erzaehler(book_id)
    erlaubt = set(namen) | {ERZ}
    # 22.10.2026 (AP4 Spiegelschwestern): Sprachen je Werk (DE-Original: src=de, tgt=en)
    src, ziele = config.werk_sprachen(book_id)
    tgt = ziele[0]
    p = _pfad(book_id)
    erg = {}
    if os.path.exists(p) and not neu:
        with open(p, encoding="utf-8") as f:
            erg = json.load(f)
    kap_alle = sorted({tid[:4] for tid in data["content"]})
    kap = kapitel or kap_alle
    task = "caster" if "caster" in config.MODELS else "profiler"
    drama = (data.get("meta") or {}).get("modus") == "drama"
    if drama:
        # Drama-Tor: Sprecher steht am Tag -> keine KI noetig. Rollenname wird NICHT gesprochen.
        norm = lambda x: re.sub(r"[^a-z]", "", (x or "").lower())
        cast = {norm(n): n for n in namen}
        stat = {}
        for tid, e in data["content"].items():
            if kapitel and tid[:4] not in kapitel:
                continue
            if e.get("type") == "dl" and e.get("sprecher"):
                s_name = cast.get(norm(e["sprecher"]), ERZ)
                erg[tid] = {lg: [{"t": e.get(lg, ""), "s": s_name}] for lg in (src, tgt) if e.get(lg)}
                stat[s_name] = stat.get(s_name, 0) + 1
        print("[stage57b] Drama-Modus: Sprecher aus dem Text | Saetze je Stimme: "
              + ", ".join(f"{n} {z}" for n, z in sorted(stat.items(), key=lambda x: -x[1])))
        with open(p, "w", encoding="utf-8") as f:
            json.dump(erg, f, ensure_ascii=False, indent=1)
        return erg
    for k in kap:
        eintraege = [(tid, e) for tid, e in data["content"].items()
                     if tid.startswith(k) and e.get("type") in TYPEN]
        if not neu and any(tid in erg for tid, _ in eintraege):
            print(f"[stage57b] {k}: schon zugeordnet (--neu fuer neu)")
            continue
        alle = len(eintraege)
        if os.environ.get("READLAYER_57B_ALLE") != "1":
            eintraege = _auswahl(eintraege, tgt, [(t, e) for t, e in data["content"].items() if t.startswith(k)], src)
        print(f"[stage57b] {k}: {len(eintraege)}/{alle} Saetze (mit Rede-Spur) -> {config.MODELS[task]} ...")
        antwort = {}
        # 12.10.2026: grosse Kapitel liefern teils kaputtes JSON -> in Teilen (je 60 Saetze) wiederholen
        teile = [eintraege[i:i + 40] for i in range(0, len(eintraege), 40)]  # 40 Saetze: passt in DEEPSEEK_MAX_OUT
        for versuch in range(3):
            offen = []
            for teil in teile:
                try:
                    roh = api_layer.call_model(task, _prompt(teil, namen, tgt, src, ich_je_kap.get(k)), temperature=0.1,
                                              max_tokens=16000)   # QF-8
                    antwort.update(api_layer.parse_json(roh))
                except Exception as ex:
                    print(f"    {k}: Antwort unbrauchbar ({str(ex)[:80]}) -> kleinere Teile")
                    offen.append(teil)
            if not offen:
                break
            groesse = max(15, 60 // (versuch + 1))
            teile = [t[i:i + groesse] for t in offen for i in range(0, len(t), groesse)]
        ok = fallback = 0
        stat = {}
        for tid, e in eintraege:
            a = antwort.get(tid)
            if not a:
                continue
            eintrag = {}
            for lg in (src, tgt):
                seg = a.get(lg)
                for x in seg or []:
                    if x.get("s") not in erlaubt:
                        x["s"] = ERZ
                if _pruefen(seg, e.get(lg, "")):
                    eintrag[lg] = [dict({"t": x["t"], "s": x["s"]}, **({"u": 1} if x.get("u") else {})) for x in seg]
                    if any(x.get("u") for x in seg):
                        eintrag["pruefen"] = True
                    for x in seg:
                        stat[x["s"]] = stat.get(x["s"], 0) + 1
                else:
                    fallback += 1
                    print(f"    {tid} [{lg}]: Segmente passen nicht zum Text -> Erzaehler")
            if eintrag:
                erg[tid] = eintrag
                ok += 1
        print(f"    {ok} Saetze mehrstimmig, {fallback} Rueckfaelle | Segmente je Sprecher: "
              + ", ".join(f"{n} {z}" for n, z in sorted(stat.items(), key=lambda x: -x[1])))
        with open(p, "w", encoding="utf-8") as f:
            json.dump(erg, f, ensure_ascii=False, indent=1)
    _pruefliste(book_id, data, erg, tgt, src)
    print(f"[stage57b] Geschrieben: {p}")
    return erg


def _pruefliste(book_id, data, erg, tgt, src="en"):
    """Unsichere Zuordnungen -> work/sprecher_pruefen.txt fuer die Sichtpruefung durch CK.
    Korrektur: Sprecher in sprecher.json am Tag aendern und "pruefen" entfernen
    (spaeter: Pruefansicht im Cockpit)."""
    ids = list(data["content"])
    zeilen = []
    for tid, e in erg.items():
        if not e.get("pruefen"):
            continue
        i = ids.index(tid) if tid in ids else -1
        vor = data["content"][ids[i - 1]].get(src, "") if i > 0 else ""
        zeilen.append(f"## {tid}\n   davor: {vor[:160]}\n   " + " | ".join(
            f"[{x['s']}{' ?' if x.get('u') else ''}] {x['t']}" for x in e.get(src, [])))
    pf = os.path.join(config.work_dir(book_id), "sprecher_pruefen.txt")
    with open(pf, "w", encoding="utf-8") as f:
        f.write(f"Unsichere Sprecherzuordnungen: {len(zeilen)}\n\n" + "\n\n".join(zeilen) + "\n")
    print(f"[stage57b] Sichtpruefung: {len(zeilen)} unsichere Saetze -> {pf}")


if __name__ == "__main__":
    a = sys.argv[1:]
    kap = a[a.index("--kapitel") + 1].split(",") if "--kapitel" in a else None
    run(a[0], kapitel=kap, neu="--neu" in a)
