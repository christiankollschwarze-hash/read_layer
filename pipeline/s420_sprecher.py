"""STAGE 420 — Sprecher (Umbau Phase 2, GATE_KATALOG.md Zeile 420, 02.11.2026)
Funktion:     Zerlegt jeden Satz mit woertlicher Rede je Hoerspiel-Sprache in Segmente (Zitat / Begleitsatz) und
              ordnet jedem Segment einen Sprecher der freigegebenen Besetzung (casting.json) zu.
Wirkungsweise: Je Kapitel x Hoerspiel-Sprache: Vorfilter (nur Absaetze mit Rede-Spur + Nachbarn), DeepSeek (Rolle
              caster, Regler --modell) in Teilen a --teil Saetzen; Zielsprache = Sprechtext 400, Ausgangssprache als
              Referenz (Konsistenz der Sprecherfolge). Kaputte/fehlende Antworten und Rekonstruktions- oder
              Sprecherfehler -> 1x automatisch einzeln neu (mit Kontext), danach Rueckfall auf Erzaehler (gezaehlt).
              Checkpoint work/ckpt/420/<kap>__<lg>.json mit Hash je Satz (Sprechtext + Referenz): geaenderter Satz
              -> automatisch neu zugeordnet. Erster Lauf uebernimmt passende Zuordnungen aus Alt-sprecher.json (0 $).
              Drama-Modus (meta.modus drama bzw. --drama an): Sprecher steht am Knoten, kein LLM.
Eingang:      work/400_regie.json (content + production.sprechtext; Gate 400 frei), work/casting.json Schema 2
              freigegeben (rollen[lg][stufe]: ensemble + statisten; Gate 410 frei), book.json (Bestellung,
              sprecher_regler), work/420_korrekturen.json (manuell).
Ausgabe:      work/420_sprecher.json {schema, sprachen {lg: stufe, besetzung, text}, saetze {tid: {lg: {seg [{t, s, u?}],
              h, q, rf?}}}, meta}; work/420_pruefung.json (Listen je Sprache); Altsicht work/sprecher.json
              ({tid: {lg: [{t, s, u?}], pruefen?}}) fuer 510/540/tools bis zu deren Umbau (Sicherung sprecher_v1.json).
Gate:         je Hoerspiel-Sprache: Abdeckung Kandidatensaetze 100 % (nach Wiederholung), Rekonstruktion 100 %,
              unbekannte Sprecher 0, Aktualitaet, Casting freigegeben, Gate 400/410 frei -> sonst Stopp;
              Rueckfaelle <= 1 %, unsicher <= 5 %, Konsistenz Ausgangs-/Zielsprache >= 98 %, Drama-Rollenname nicht in
              Besetzung -> Mensch; Mandant verlag -> immer Mensch; besetzte Figur ohne Segmente, Rede-Spur ohne
              Segmente, veraltete Korrektur -> Hinweis. Mensch-Freigabe gilt bei gleichem ausgabe_hash.
Kosten:       usage_log Stage 420 mit Sprache (DeepSeek).
Regler:       --modell, --teil 40, --vorfilter an|aus, --drama an|aus|auto, --rueckfall-max, --unsicher-max,
              --konsistenz-min (book.json sprecher_regler); --kapitel c001,c002 / --satz ID (neu zuordnen), --neu (alles),
              --sprecher ID:IDX=NAME, --segmente ID=JSON, --korrektur-weg ID (je --lang), --trocken.
Aufruf:       py -3.11 -m pipeline.s420_sprecher <werk> [Regler] [--wer CK]
Exit: 0 auto, 2 Stopp, 3 Mensch, 1 Fehler.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import api_layer, bestellung, gate, manifest, mock, status, usage_log
from pipeline import s410_casting as s410

STAGE = "420"
SCHEMA = 1
PROMPT_V = 2
ERZ = "Erzaehler"
TYPEN = {"s", "dl", "qt", "vs"}
REGLER_STD = {"modell": None, "teil": 40, "vorfilter": True, "drama": None,
              "rueckfall_max": 0.01, "unsicher_max": 0.05, "konsistenz_min": 0.98}
LANG_NAME = {"en": "English", "de": "German", "fr": "French", "es": "Spanish", "it": "Italian"}
ERZ_NAMEN = {"erzaehler", "erzähler", "narrator", "narration", "narrateur", "narratore", "narrador"}

# Rede-Spur: einfache Zeichen (‘ ’ ‚ ') bewusst NICHT – ’ ist meist Apostroph
OEFFNEN, SCHLIESSEN, BEIDES = set("“„»"), set("”«"), set('"')
ZEICHEN = OEFFNEN | SCHLIESSEN | BEIDES
_ZITAT = re.compile(r'(“[^”]*”|„[^“]*“|"[^"]*"|»[^«]*«|«[^»]*»)')


# ============================================================ Ablage
def pfad(werk):
    return config.work_path(werk, "420_sprecher")


def alt_pfad(werk):
    return os.path.join(config.work_dir(werk), "sprecher.json")


def korr_pfad(werk):
    return os.path.join(config.work_dir(werk), "420_korrekturen.json")


def _json(p, leer=None):
    if not os.path.exists(p):
        return leer
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def laden(werk):
    return _json(pfad(werk))


def segmente(werk, tid, lg):
    """Segmente eines Satzes (nur Saetze mit Rede), sonst None (= ganz Erzaehler)."""
    a = laden(werk) or {}
    return (((a.get("saetze") or {}).get(tid) or {}).get(lg) or {}).get("seg")


# ============================================================ Vorfilter
def _offen_nach(text, offen, lg):
    for ch in text or "":
        if ch in BEIDES:
            offen = not offen
        elif ch == "“" and offen and lg == "de":     # DE „…“: “ schliesst; sonst oeffnet “
            offen = False
        elif ch in OEFFNEN:
            offen = True
        elif ch in SCHLIESSEN:
            offen = False
    return offen


def kandidaten(eintraege, sprachen):
    ids, offen = set(), {lg: False for lg in sprachen}
    for tid, e in eintraege:
        spur = e.get("type") in ("dl", "qt", "vs") or any(offen.values())
        for lg in sprachen:
            t = e.get(lg, "")
            if any(ch in ZEICHEN for ch in t):
                spur = True
            offen[lg] = _offen_nach(t, offen[lg], lg)
        if spur:
            ids.add(tid)
    return ids


def auswahl(eintraege, sprachen, kapitel_alles):
    """Ganze Absaetze mit Rede-Spur + je ein Nachbarsatz (Folgesaetze ohne Zeichen sprechen oft weiter)."""
    k = kandidaten(eintraege, sprachen)
    absatz, nr = {}, 0
    for tid, e in kapitel_alles:
        if e.get("type") in ("p", "h"):
            nr += 1
        absatz[tid] = nr
    rede = {absatz.get(tid) for tid in k}
    idx = {tid: i for i, (tid, _) in enumerate(eintraege)}
    behalten = set()
    for tid, _ in eintraege:
        if absatz.get(tid) in rede:
            i = idx[tid]
            behalten.update(eintraege[j][0] for j in (i - 1, i, i + 1) if 0 <= j < len(eintraege))
    return [(tid, e) for tid, e in eintraege if tid in behalten]


# ============================================================ Besetzung / Pruefung
def _ziele(b):
    """{lg: stufe} je bestelltem Hoerspiel."""
    z = {}
    for p in b.produkte_fuer(inhalt="hoerspiel"):
        z.setdefault(p["sprache"], p.get("stufe"))
    return z


def besetzung(c, lg, stufe):
    bs = (((c or {}).get("rollen") or {}).get(lg) or {}).get(stufe)
    if bs is None:
        return None
    out = []
    for rolle, liste in (("ensemble", bs.get("ensemble")), ("statist", bs.get("statisten"))):
        for e in liste or []:
            if e.get("figur") and e["figur"] not in [x["figur"] for x in out]:
                out.append({"figur": e["figur"], "name": e.get("name_lg") or e.get(f"name_{lg}") or e["figur"],
                            "rolle": rolle})
    return out


def _namen(cast):
    m = {}
    for x in cast:
        m[x["figur"].casefold()] = x["figur"]
        m[x["name"].casefold()] = x["figur"]
    return m


def _sprecher(s, namen):
    s = (s or "").strip()
    if s.casefold() in ERZ_NAMEN:
        return ERZ
    return namen.get(s.casefold())


def _norm(t):
    return re.sub(r"\s+", "", t or "")


def rekonstruiert(seg, original):
    return (isinstance(seg, list) and bool(seg) and all(isinstance(x, dict) and isinstance(x.get("t"), str) for x in seg)
            and _norm("".join(x["t"] for x in seg)) == _norm(original))


def _segs(seg, original, namen, ersetzen=False):
    """-> (segmente, fehler). fehler: None | 'rekonstruktion' | 'sprecher_unbekannt'."""
    if not rekonstruiert(seg, original):
        return None, "rekonstruktion"
    out, unbekannt = [], False
    for x in seg:
        s = _sprecher(x.get("s"), namen)
        if s is None:
            unbekannt = True
            s = ERZ
        if not x["t"].strip():
            continue
        y = {"t": x["t"], "s": s}
        if x.get("u"):
            y["u"] = 1
        out.append(y)
    if unbekannt and not ersetzen:
        return None, "sprecher_unbekannt"
    return out, ("sprecher_unbekannt" if unbekannt else None)


def _figuren(seg):
    return {x["s"] for x in seg or [] if x["s"] != ERZ}


# ============================================================ LLM
def _prompt(items, cast, lg, src, ich=None, kontext=None):
    """items [(tid, text_lg, ref_src|None)]."""
    sprachen = [lg] + ([src] if src != lg else [])
    namen = " / ".join(f'"{s}" ({LANG_NAME.get(s, s)})' for s in sprachen)
    besetzung_ = "\n".join(f"- {x['figur']}" + (f" ({LANG_NAME.get(lg, lg)}: {x['name']})" if x["name"] != x["figur"]
                                                 else "") for x in cast) or "- (no characters)"
    ich_regel = (f"\n- This chapter is told in the first person by {ich}. Quoted speech of the narrator ('I') -> "
                 f"\"{ich}\" (not \"{ERZ}\"); the narration itself stays \"{ERZ}\".") if ich else ""
    zeilen = "\n".join(json.dumps({"id": tid, lg: t, **({src: r} if src != lg else {})}, ensure_ascii=False)
                       for tid, t, r in items)
    ctx = ("\nCONTEXT (previous lines, for speaker identification only – do NOT output them):\n"
           + "\n".join(kontext) + "\n") if kontext else ""
    beispiel = ", ".join(f'"{s}": [{{"t": "...", "s": "<name>"}}]' for s in sprachen)
    return f"""You prepare a multi-voice audio drama. For every line below that contains spoken words (direct speech,
thoughts spoken aloud, songs or poems recited by a character), split the line into consecutive segments and say who
speaks each segment. Narration (e.g. "said Alice", "thought she") belongs to "{ERZ}".

CAST (use exactly these names; anyone else -> the closest cast name, unknown -> "{ERZ}"):
{besetzung_}

Rules:
- Do this separately for {namen}. Segments, concatenated in order, must reproduce the original text EXACTLY
  (same characters incl. quotation marks and punctuation; only whitespace between segments may differ).
- Keep quotation marks with the quoted segment. Keep the narrator part with the narrator.
- Identify the speaker from context (previous/next lines) when there is no attribution.
- Lines without any direct speech: omit them from the output.
- Inner thoughts of a character that are written as quotes ("thought Alice") -> that character.
- Attribution words like "said Holmes", "he cried", "answered Watson" are NARRATION -> separate "{ERZ}" segment.
- The same line in both languages must have the same speakers.
- If you are NOT sure who speaks a segment (rapid exchanges without attribution, similar characters,
  ambiguous pronouns), still give your best guess but add "u": 1 to that segment. Be honest: mark real doubt.{ich_regel}

Return ONLY JSON: {{"<id>": {{{beispiel}}}}}
{ctx}
LINES (in reading order):
{zeilen}"""


def _llm(prompt, modell=None):
    alt = config.MODELS.get("caster")
    if modell:
        config.MODELS["caster"] = modell
    try:
        p = api_layer.parse_json(api_layer.call_model("caster", prompt, temperature=0.1, max_tokens=16000))
    finally:
        config.MODELS["caster"] = alt
    if not isinstance(p, dict):
        raise ValueError("Antwort ist kein JSON-Objekt")
    return p


def mock_seg(text, figur):
    teile = [t for t in _ZITAT.split(text or "") if t and t.strip()]
    if not any(_ZITAT.fullmatch(t.strip()) for t in teile):
        return None
    return [{"t": t, "s": figur if (figur and _ZITAT.fullmatch(t.strip())) else ERZ} for t in teile]


def _antwort(a, tid, text, ref, lg, src, namen, ersetzen):
    """Antwort eines Satzes -> (rec | None=keine Rede | 'offen', fehler)."""
    if not a:
        return None, None
    if not isinstance(a, dict) or not a.get(lg):
        return "offen", "rekonstruktion"
    seg, fe = _segs(a.get(lg), text, namen, ersetzen)
    if seg is None:
        return "offen", fe
    rec = {"seg": seg, "q": "llm"}
    if fe:
        rec["rf"] = fe
    if src != lg and ref:
        r, rfe = _segs(a.get(src), ref, namen)
        if r is not None and not rfe:
            rec["ref"] = r
    return rec, fe


def zuordnen(items, cast, lg, src, ich, rg, kontext_fn):
    """items [(tid, text, ref)] -> ({tid: rec|None}, llm_aufrufe). Fehlt tid -> keine Antwort (Abdeckung)."""
    namen = _namen(cast)
    out, offen, n = {}, [], 0
    teil = max(1, int(rg["teil"]))
    for i in range(0, len(items), teil):
        t = items[i:i + teil]
        n += 1
        try:
            p = _llm(_prompt(t, cast, lg, src, ich), rg.get("modell"))
        except EnvironmentError:
            raise
        except Exception as ex:
            print(f"    [{lg}] Teil {i // teil + 1}: Antwort unbrauchbar ({str(ex)[:80]}) -> einzeln neu")
            offen += t
            continue
        for tid, text, ref in t:
            rec, _ = _antwort(p.get(tid), tid, text, ref, lg, src, namen, False)
            if rec == "offen":
                offen.append((tid, text, ref))
            else:
                out[tid] = rec
    for tid, text, ref in offen:                       # 1x automatisch einzeln neu (mit Kontext)
        n += 1
        try:
            p = _llm(_prompt([(tid, text, ref)], cast, lg, src, ich, kontext_fn(tid)), rg.get("modell"))
        except EnvironmentError:
            raise
        except Exception:
            continue                                   # bleibt ohne Antwort -> Abdeckung
        rec, fe = _antwort(p.get(tid), tid, text, ref, lg, src, namen, True)
        if rec == "offen":                             # Rekonstruktion scheitert -> Rueckfall Erzaehler
            rec = {"seg": [{"t": text, "s": ERZ}], "q": "rueckfall", "rf": fe or "rekonstruktion"}
        out[tid] = rec
    return out, n


# ============================================================ Regler / Korrekturen
def _regler(roh):
    r = dict(REGLER_STD)
    r.update({k: v for k, v in (roh.get("sprecher_regler") or {}).items() if k in REGLER_STD})
    return r


def regler_anwenden(rg, aend):
    rg = dict(rg)
    for k in REGLER_STD:
        if aend.get(k) is not None:
            rg[k] = None if aend[k] == "auto" else aend[k]
    return rg


def _regler_gueltig(rg):
    try:
        return (1 <= int(rg["teil"]) <= 200 and 0 <= float(rg["rueckfall_max"]) <= 1
                and 0 <= float(rg["unsicher_max"]) <= 1 and 0 <= float(rg["konsistenz_min"]) <= 1
                and rg["drama"] in (None, True, False) and rg["vorfilter"] in (True, False))
    except Exception:
        return False


def korrektur_setzen(werk, lg, tid, seg=None, idx=None, name=None, weg=False):
    k = _json(korr_pfad(werk), {}) or {}
    je = k.setdefault(lg, {})
    if weg:
        je.pop(tid, None)
    else:
        if seg is None:
            seg = [dict(x) for x in (segmente(werk, tid, lg) or [])]
            if not seg or not (0 <= idx < len(seg)):
                raise ValueError(f"{tid} [{lg}]: kein Segment {idx}")
            seg[idx]["s"] = name
        for x in seg:
            x.pop("u", None)
        je[tid] = seg
    manifest.json_atomar(korr_pfad(werk), k, indent=1)
    return k


# ============================================================ Lauf
def run(werk, wer=None, kapitel=None, neu=False, saetze=None, regler=None, trocken=False):
    wer = wer or "pipeline"
    g = gate.Gate(werk, STAGE, ruecksprung="420", wer=wer)
    b = bestellung.lesen(werk)
    rg = _regler(dict(b.roh))
    if regler and any(v is not None for v in regler.values()):
        rg = regler_anwenden(rg, regler)
        if not trocken:
            b = bestellung.feld_setzen(werk, sprecher_regler=rg)
    src = b.quellsprache or config.SOURCE_LANGUAGE
    ziele = _ziele(b)
    g.metrik("ziele", ziele)
    g.metrik("regler", {k: rg[k] for k in REGLER_STD})
    ip = config.work_path(werk, "400_regie")
    ok = g.pflicht("eingang", os.path.exists(ip), ruecksprung="400", text="400_regie.json vorhanden")
    ok = g.pflicht("hoerspiel", bool(ziele), ruecksprung="095", text="Hoerspiel bestellt") and ok
    ok = g.pflicht("regler", _regler_gueltig(rg), wert={k: rg[k] for k in REGLER_STD}, text="Regler im Bereich") and ok
    for v in ("400", "410"):
        z = status.zustand(werk, v)
        if trocken:
            g.hinweis(f"gate_{v}", z in status.FREI, text=f"Gate {v}: {z}")
        else:
            ok = g.pflicht(f"gate_{v}", z in status.FREI, wert=z, ruecksprung=v, text=f"Gate {v} frei ({z})") and ok
    c = s410.laden(werk)
    frei = s410.freigegeben(c)
    if trocken and c and c.get("schema") == s410.SCHEMA:
        g.hinweis("casting", frei, text="Casting freigegeben" + ("" if frei else " – nein (Probe)"))
    else:
        ok = g.pflicht("casting", frei, ruecksprung="410", text="casting.json (Schema 2) freigegeben") and ok
    if not ok:
        g.entscheide(schreiben=not trocken)
        return g

    with open(ip, encoding="utf-8") as f:
        data = json.load(f)
    content = data.get("content") or {}
    sprech = (data.get("production") or {}).get("sprechtext") or {}
    v1 = c.get("v1_extra") or c.get("plan") or {}
    ich_je = v1.get("erzaehler_je_kapitel") or {}
    drama = rg["drama"] if rg["drama"] is not None else (data.get("meta") or {}).get("modus") == "drama"
    alt_v = _json(alt_pfad(werk), {}) or {}
    korr = _json(korr_pfad(werk), {}) or {}
    ck = manifest.Checkpoint(werk, STAGE)
    kap_alle = []
    for tid in content:
        if tid[:4] not in kap_alle:
            kap_alle.append(tid[:4])
    kap_neu = set(kapitel or [])
    saetze = set(saetze or [])
    ausgabe = {"schema": SCHEMA, "werk": werk, "datum": status.jetzt(), "quelle": "work/400_regie.json",
               "sprachen": {}, "saetze": {}}
    pruef, je_sprache, ck_soll, n_llm = {}, {}, [], 0

    for lg, stufe in sorted(ziele.items()):
        cast = besetzung(c, lg, stufe)
        if not g.pflicht(f"besetzung_{lg}", cast is not None, ruecksprung="410",
                         text=f"{lg}: Besetzung rollen[{lg}][{stufe}] in casting.json"):
            continue
        namen = _namen(cast)
        mit_sp = sum(1 for t in content if (sprech.get(t) or {}).get(lg) is not None)
        def text(tid, e, lg=lg):
            v = (sprech.get(tid) or {}).get(lg)
            return v if v is not None else e.get(lg, "")
        ref_lg = src if src != lg else None
        eingang_h = manifest.hash_obj({"cast": [x["figur"] for x in cast], "v": PROMPT_V, "ich": ich_je,
                                       "drama": drama, "vorfilter": rg["vorfilter"], "modell": rg["modell"]})
        usage_log.set_context(werk, STAGE, sprache=lg)
        recs_lg, texte, n_kand, offen_trocken, uebernommen, drama_fremd = {}, {}, 0, 0, 0, []
        for kap in kap_alle:
            ck_soll.append((kap, lg))
            alles = [(t, e) for t, e in content.items() if t.startswith(kap) and isinstance(e, dict)]
            eintraege = [(t, e) for t, e in alles if e.get("type") in TYPEN]
            if drama:
                kand = [(t, e) for t, e in eintraege if e.get("type") == "dl" and e.get("sprecher")]
            elif rg["vorfilter"]:
                kand = auswahl(eintraege, [lg] + ([ref_lg] if ref_lg else []), alles)
            else:
                kand = eintraege
            n_kand += len(kand)
            h = {}
            for t, e in kand:
                texte[t] = text(t, e)
                h[t] = manifest.hash_text(texte[t] + "\x1f" + ((e.get(ref_lg) or "") if ref_lg else ""))
            alt_ck = (None if (neu or kap in kap_neu) else ck.lesen(kap, lg, eingang_h)) or {}
            a_recs, a_h = alt_ck.get("recs") or {}, alt_ck.get("h") or {}
            recs = {t: a_recs[t] for t, _ in kand if t in a_recs and a_h.get(t) == h[t] and t not in saetze}
            offen = [(t, e) for t, e in kand if t not in recs]
            # Erstlauf: Uebernahme aus Alt-sprecher.json (nur rekonstruierbar, Sprecher bekannt)
            if offen and alt_v and not neu and not ck.vorhanden(kap, lg) and kap not in kap_neu:
                hat = any(t.startswith(kap) and isinstance(v, dict) and lg in v for t, v in alt_v.items())
                for t, e in offen:
                    v = (alt_v.get(t) or {}).get(lg) if isinstance(alt_v.get(t), dict) else None
                    if v:
                        seg, fe = _segs(v, texte[t], namen)
                        if seg is not None and not fe:
                            r = {"seg": seg, "q": "uebernommen"}
                            rv = (alt_v.get(t) or {}).get(ref_lg) if ref_lg else None
                            if rv:
                                rs, rfe = _segs(rv, e.get(ref_lg, ""), namen)
                                if rs is not None and not rfe:
                                    r["ref"] = rs
                            recs[t] = r
                            uebernommen += 1
                    elif hat:
                        recs[t] = None
                        uebernommen += 1
                offen = [(t, e) for t, e in kand if t not in recs]
            if offen:
                if drama:
                    for t, e in offen:
                        s = _sprecher(e.get("sprecher"), namen)
                        if s is None:
                            drama_fremd.append(f"{t}: {e.get('sprecher')}")
                            s = ERZ
                        recs[t] = {"seg": [{"t": texte[t], "s": s}], "q": "drama"}
                elif mock.aktiv():
                    fig = next((x["figur"] for x in cast if x["rolle"] == "ensemble"), None)
                    for t, e in offen:
                        seg = mock_seg(texte[t], fig)
                        recs[t] = {"seg": seg, "q": "mock"} if seg else None
                        if seg and ref_lg and mock_seg(e.get(ref_lg, ""), fig):
                            recs[t]["ref"] = mock_seg(e.get(ref_lg, ""), fig)
                elif trocken:
                    offen_trocken += len(offen)
                else:
                    ids = [t for t, _ in alles]
                    def kontext(tid, ids=ids, alles=dict(alles)):
                        i = ids.index(tid)
                        return [text(x, alles[x]) for x in ids[max(0, i - 2):i]]
                    print(f"[420] {kap} [{lg}]: {len(offen)}/{len(eintraege)} Saetze -> LLM")
                    neu_r, n = zuordnen([(t, texte[t], e.get(ref_lg) if ref_lg else None) for t, e in offen],
                                        cast, lg, src, ich_je.get(kap), rg, kontext)
                    n_llm += n
                    recs.update(neu_r)
            for t in recs:
                if recs[t] is not None:
                    recs[t]["h"] = h[t]
            if not trocken:
                ck.schreiben(kap, lg, eingang_h, {"recs": recs, "h": {t: h[t] for t in recs}}, kandidaten=len(kand))
            recs_lg.update({t: r for t, r in recs.items()})
        # manuelle Korrekturen
        veraltet = []
        for tid, seg in ((korr.get(lg) or {}).items()):
            e = content.get(tid)
            if not isinstance(e, dict):
                veraltet.append(tid)
                continue
            texte.setdefault(tid, text(tid, e))
            s, fe = _segs(seg, texte[tid], namen)
            if s is None or fe:
                veraltet.append(tid)
                continue
            if tid not in recs_lg:
                n_kand += 1
            recs_lg[tid] = {"seg": s, "q": "manuell",
                            "h": manifest.hash_text(texte[tid] + "\x1f" + ((e.get(ref_lg) or "") if ref_lg else ""))}

        # ---- Gate je Sprache
        mit = {t: r for t, r in recs_lg.items() if r is not None}
        fehlt = n_kand - len(recs_lg)
        abd = len(recs_lg) / n_kand if n_kand else 1.0
        if trocken and offen_trocken:
            g.hinweis(f"abdeckung_{lg}", False, wert=offen_trocken,
                      text=f"{lg}: {offen_trocken} Saetze wuerden neu zugeordnet (Probe, kein LLM)")
        else:
            g.pflicht(f"abdeckung_{lg}", fehlt == 0, wert=round(abd, 4), ruecksprung="420",
                      text=f"{lg}: Abdeckung Kandidatensaetze {len(recs_lg)}/{n_kand}"
                           + (f" – {fehlt} ohne Antwort nach Wiederholung" if fehlt else ""))
        rek = [t for t, r in mit.items() if not rekonstruiert(r["seg"], texte.get(t, ""))]
        g.pflicht(f"rekonstruktion_{lg}", not rek, wert=len(rek), text=f"{lg}: Rekonstruktion Segmente = Satz"
                  + (f" – verletzt: {', '.join(rek[:3])}" if rek else ""))
        erlaubt = {x["figur"] for x in cast} | {ERZ}
        unb = sorted({x["s"] for r in mit.values() for x in r["seg"] if x["s"] not in erlaubt})
        g.pflicht(f"sprecher_{lg}", not unb, wert=unb[:5], ruecksprung="410",
                  text=f"{lg}: Sprecher in Besetzung" + (f" – unbekannt: {', '.join(unb[:5])}" if unb else ""))
        alt_h = [t for t, r in mit.items() if t in texte and r.get("q") != "manuell"
                 and r.get("h") != manifest.hash_text(texte[t] + "\x1f" + ((content[t].get(ref_lg) or "") if ref_lg else ""))]
        g.pflicht(f"aktualitaet_{lg}", not alt_h, wert=len(alt_h), text=f"{lg}: Aktualitaet (Hash = 400)")
        rf = [t for t, r in mit.items() if r.get("rf")]
        q_rf = len(rf) / n_kand if n_kand else 0.0
        g.max(f"rueckfaelle_{lg}", round(q_rf, 4), float(rg["rueckfall_max"]), ruecksprung="420")
        fig_s = [t for t, r in mit.items() if _figuren(r["seg"])]
        uns = [t for t in fig_s if any(x.get("u") for x in mit[t]["seg"])]
        q_u = len(uns) / len(fig_s) if fig_s else 0.0
        g.max(f"unsicher_{lg}", round(q_u, 4), float(rg["unsicher_max"]), ruecksprung="420")
        vergl = [t for t, r in mit.items() if r.get("ref") is not None and not r.get("rf")]
        inkon = [t for t in vergl if _figuren(mit[t]["seg"]) != _figuren(mit[t]["ref"])]
        if ref_lg and vergl:
            kons = 1 - len(inkon) / len(vergl)
            g.min(f"konsistenz_{lg}", round(kons, 4), float(rg["konsistenz_min"]), ruecksprung="420")
        else:
            kons = None
            g.hinweis(f"konsistenz_{lg}", not ref_lg, text=f"{lg}: Konsistenz nicht messbar"
                      + (" (Hoerspiel in Ausgangssprache)" if not ref_lg else " (keine Referenzsegmente)"))
        if drama:
            g.pruefe(f"drama_{lg}", not drama_fremd, wert=drama_fremd[:5], bei_fehler="mensch", ruecksprung="410",
                     text=f"{lg}: Drama-Rollennamen in Besetzung"
                          + (f" – fremd: {'; '.join(drama_fremd[:3])}" if drama_fremd else ""))
        ens = [x["figur"] for x in cast if x["rolle"] == "ensemble"]
        gehoert = {x["s"] for r in mit.values() for x in r["seg"]}
        stumm = [f for f in ens if f not in gehoert]
        g.hinweis(f"figur_ohne_{lg}", not stumm, wert=stumm, text=f"{lg}: besetzte Figuren ohne Segmente: "
                  + ", ".join(stumm))
        spur = [t for t, r in recs_lg.items() if r is None and any(ch in ZEICHEN for ch in texte.get(t, ""))
                and content.get(t, {}).get("type") in ("dl", "qt")]
        g.hinweis(f"rede_ohne_{lg}", not spur, wert=len(spur),
                  text=f"{lg}: {len(spur)} Rede-Saetze (dl/qt) ohne Segmente (ganz Erzaehler)")
        g.hinweis(f"korrektur_{lg}", not veraltet, wert=veraltet[:5],
                  text=f"{lg}: Korrekturen veraltet/ungueltig: {', '.join(veraltet[:5])}")
        if uebernommen:
            g.hinweis(f"uebernommen_{lg}", False, wert=uebernommen,
                      text=f"{lg}: {uebernommen} Zuordnungen aus Alt-sprecher.json uebernommen (0 $)")
        if mit_sp == 0 and content:
            g.hinweis(f"sprechtext_{lg}", False, text=f"{lg}: 400 ohne Sprechtext (Altfassung) – Lesetext segmentiert")
        stat = {}
        for r in mit.values():
            for x in r["seg"]:
                stat[x["s"]] = stat.get(x["s"], 0) + 1
        je_sprache[lg] = {"stufe": stufe, "kandidaten": n_kand, "mit_rede": len(mit), "rueckfaelle": len(rf),
                          "unsicher": len(uns), "konsistenz": None if kons is None else round(kons, 4),
                          "segmente": dict(sorted(stat.items(), key=lambda x: -x[1]))}
        ausgabe["sprachen"][lg] = {"stufe": stufe, "besetzung": cast,
                                   "text": "sprechtext" if mit_sp else "lesetext"}
        for t, r in mit.items():
            ausgabe["saetze"].setdefault(t, {})[lg] = {k: v for k, v in r.items() if k in ("seg", "h", "q", "rf", "ref")}
        def zeile(t):
            return {"id": t, "text": texte.get(t, "")[:300],
                    "seg": [f"[{x['s']}{' ?' if x.get('u') else ''}] {x['t']}" for x in (mit.get(t) or {}).get("seg", [])]}
        pruef[lg] = {"unsicher": [zeile(t) for t in uns], "rueckfall": [dict(zeile(t), grund=mit[t]["rf"]) for t in rf],
                     "inkonsistent": [dict(zeile(t), ref=sorted(_figuren(mit[t]["ref"]))) for t in inkon],
                     "drama_fremd": drama_fremd}

    g.metrik("llm_aufrufe", n_llm)
    g.metrik("je_sprache", je_sprache)
    g.mock(0 if mock.aktiv() else sum(1 for v in ausgabe["saetze"].values() for r in v.values() if r.get("q") == "mock"),
           ruecksprung="420")
    ausgabe["saetze"] = dict(sorted(ausgabe["saetze"].items()))
    aus_hash = manifest.hash_obj({t: {lg: r["seg"] for lg, r in v.items()} for t, v in ausgabe["saetze"].items()})
    g.metrik("ausgabe_hash", aus_hash)
    ausgabe["meta"] = {"prompt_v": PROMPT_V, "modell": rg["modell"] or config.MODELS.get("caster"), "drama": drama,
                       "regler": {k: rg[k] for k in REGLER_STD}, "je_sprache": je_sprache, "ausgabe_hash": aus_hash}
    st0 = status.laden(werk)["stages"].get(STAGE) or {}
    if st0.get("zustand") == "frei" and (st0.get("gate") or {}).get("ergebnis") == "mensch" \
            and (st0.get("metriken") or {}).get("ausgabe_hash") == aus_hash:
        for p in g.pruefungen:
            if not p["ok"] and p["bei_fehler"] == "mensch":
                p["bei_fehler"] = "hinweis"
                p["text"] += " [Mensch-Freigabe gilt, Zuordnung unveraendert]"
    verlag = b.mandant_art == "verlag"
    if not trocken:
        manifest.json_atomar(pfad(werk), ausgabe, indent=1)
        manifest.json_atomar(os.path.join(config.work_dir(werk), "420_pruefung.json"), pruef, indent=1)
        _altsicht(werk, ausgabe, src, ziele)
        if not kapitel and not saetze:
            ck.aufraeumen(ck_soll)
    g.entscheide(mensch_immer=verlag, mensch_grund="Mandant verlag: Sprecherzuordnung pruefen" if verlag else None,
                 schreiben=not trocken)
    g.ausgabe, g.pruef = ausgabe, pruef
    return g


def _altsicht(werk, ausgabe, src, ziele):
    """work/sprecher.json im Altformat fuer 510/540/tools (bis zu deren Umbau)."""
    p = alt_pfad(werk)
    alt = _json(p)
    bak = os.path.join(config.work_dir(werk), "sprecher_v1.json")
    if alt and not os.path.exists(bak):              # erster Lauf: Original (Stage 57b) sichern
        manifest.json_atomar(bak, alt, indent=1)
    out = {}
    for t, v in ausgabe["saetze"].items():
        e = {}
        for lg, r in v.items():
            e[lg] = r["seg"]
            if r.get("ref") and src not in ziele and src not in e:
                e[src] = r["ref"]
            if any(x.get("u") for x in r["seg"]):
                e["pruefen"] = True
        out[t] = e
    manifest.json_atomar(p, out, indent=1)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 420 Sprecher")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--modell")
    ap.add_argument("--teil", type=int)
    ap.add_argument("--vorfilter", choices=("an", "aus"))
    ap.add_argument("--drama", choices=("an", "aus", "auto"))
    ap.add_argument("--rueckfall-max", type=float)
    ap.add_argument("--unsicher-max", type=float)
    ap.add_argument("--konsistenz-min", type=float)
    ap.add_argument("--kapitel", help="c001,c002: neu zuordnen")
    ap.add_argument("--satz", action="append", help="Satz-ID neu zuordnen")
    ap.add_argument("--neu", action="store_true", help="alles neu zuordnen (ohne Checkpoint/Uebernahme)")
    ap.add_argument("--sprecher", action="append", metavar="ID:IDX=NAME")
    ap.add_argument("--segmente", action="append", metavar="ID=JSON")
    ap.add_argument("--korrektur-weg", action="append", metavar="ID")
    ap.add_argument("--lang")
    ap.add_argument("--trocken", action="store_true")
    a = ap.parse_args(argv)
    wer = a.wer or "pipeline"
    an = {"an": True, "aus": False}
    regler = {"modell": a.modell, "teil": a.teil, "vorfilter": an.get(a.vorfilter),
              "drama": "auto" if a.drama == "auto" else an.get(a.drama),
              "rueckfall_max": a.rueckfall_max, "unsicher_max": a.unsicher_max, "konsistenz_min": a.konsistenz_min}
    try:
        korr = a.sprecher or a.segmente or a.korrektur_weg
        if (korr or any(v is not None for v in regler.values())) and not a.trocken:
            from pipeline import s080_mandant
            s080_mandant.darf(a.werk, "entscheiden", wer)
        if korr:
            lg = a.lang
            if not lg:
                z = sorted(_ziele(bestellung.lesen(a.werk)))
                if len(z) != 1:
                    raise ValueError(f"--lang noetig (Hoerspiel-Sprachen: {', '.join(z) or 'keine'})")
                lg = z[0]
            for x in a.sprecher or []:
                tid_i, name = x.split("=", 1)
                tid, i = tid_i.rsplit(":", 1)
                korrektur_setzen(a.werk, lg, tid, idx=int(i), name=name)
            for x in a.segmente or []:
                tid, js = x.split("=", 1)
                korrektur_setzen(a.werk, lg, tid, seg=json.loads(js))
            for tid in a.korrektur_weg or []:
                korrektur_setzen(a.werk, lg, tid, weg=True)
        g = run(a.werk, wer, kapitel=a.kapitel.split(",") if a.kapitel else None, neu=a.neu, saetze=a.satz,
                regler=regler, trocken=a.trocken)
    except gate.GateHalt as e:
        print(e)
        return e.exit_code
    except (ValueError, PermissionError, RuntimeError) as e:
        print(f"[420] Fehler: {e}")
        return 1
    print(g.bericht())
    return gate.EXIT[g.ergebnis["ergebnis"]]


if __name__ == "__main__":
    sys.exit(main())
