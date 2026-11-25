"""STAGE 430 — Fish-Regie (AP Fish-Regie, 25.11.2026; Prompt claude/PROMPT_fish_regie_cockpit.md)
Funktion:     Redebeitraege je Hoerspiel-Sprache mit Motor Fish: die Erzaehlerstimme spielt alle Figuren per Anweisung
              (Fish Drama 3), Stage 510 tapeziert danach die Figurenstimmen per Chatterbox-VC. Je Beitrag
              {id, tid, seg, fig, text, anweisung, block}; Anweisung = "[<Grundhaltung>; <Moment>]" (+ nonverbal-Tag)
              nur vor Figurensegmenten, Erzaehler (und Statisten/unbekannte Sprecher) ohne Tag.
Moment:       Interpreter-Schema mit festem Vokabular (LLM DeepSeek, kein Freitext): stimmung ∈ {ruhig, gespannt,
              heiter, duester, dramatisch}, intensitaet 1–3, nonverbal ∈ {—, lachen, seufzen, gaehnen, staunen},
              optional betonung (ein Wort) und vortrag ∈ {normal, fluestern, leise}. Feste Tabelle auf Fish-Sprache:
              Intensitaet = Verstaerker (slightly / – / very; Werk-Regler emotion verschiebt die Stufe), nonverbal =
              [laughs]/[sighs]/[yawns]/[gasps], betonung = <emphasis>Wort</emphasis> (Regler betonung >= 4),
              vortrag = <whisper>…</whisper> / <soft>…</soft>, Regler tempo >= 7 "brisk" / <= 3 "unhurried".
              Anweisungen immer Englisch (werden nicht gesprochen). LLM-Ergebnis je Kapitel × Sprache im Checkpoint
              (work/ckpt/430), Wiederholung ohne Kosten bei gleichem Eingang.
Bloecke:      ~2.000–2.500 Zeichen an Absatzgrenzen (Kapitelgrenze immer), ein Sprecher (Erzaehlerstimme) je Block.
Eingang:      work/400_regie.json (Sprechtext, Ansagen; Gate 400 frei), work/420_sprecher.json (Segmente; Gate 420 frei),
              work/casting.json freigegeben (engine fish, fish_grundhaltung; Gate 410 frei), book.json audio_regler.
Ausgabe:      work/430_fish_regie.json {schema, sprachen: {lg: {beitraege: [...], bloecke: [...]}}},
              work/430_korrekturen.json (manuelle Anweisungen je Beitrag, an Texthash gebunden).
Gate:         Hoerspiel mit Motor Fish bestellt, Gate 400/410/420 frei, Casting freigegeben, Abdeckung (jeder
              Audio-Knoten in einem Beitrag) -> sonst Stopp; Anweisung <= 200 Zeichen, jede Figur mit Grundhaltung oder
              Freigabe "ohne" -> sonst Mensch; unbekannte Sprecher -> Erzaehler + Hinweis; Segmente veraltet
              (Sprechtext nach 420 geaendert) -> ganzer Satz Erzaehler + Hinweis; Moment ungueltig -> ohne Moment + Hinweis.
              Mensch-Freigabe gilt bei gleichem ausgabe_hash. Tags zaehlen nicht in Laengenpruefungen (400).
Kosten:       usage_log Stage 430 (DeepSeek, Cent-Bereich je Werk).
Regler:       book.json fish_regler: --block-min 2000, --block-max 2500, --anweisung-max 200, --modell,
              overlay_plus 1 (Figuren mit vc_ziel: Intensitaet +1, VC in 511 glaettet; 0 = aus);
              dazu --anweisung LG/ID=TEXT (manuell, '-' = weg), --kapitel, --neu, --trocken.
Aufruf:       py -3.11 -m pipeline.s430_fish_regie <werk> [Regler] [--wer CK]
Exit: 0 auto, 2 Stopp, 3 Mensch, 1 Fehler.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import api_layer, bestellung, fish_motor, gate, manifest, mock, status, usage_log
from pipeline import s410_casting as s410
from pipeline import s420_sprecher as s420

STAGE = "430"
SCHEMA = 1
PROMPT_V = 1
ERZ = s420.ERZ
REGLER_STD = {"block_min": 2000, "block_max": 2500, "anweisung_max": 200, "modell": None, "overlay_plus": 1}
STIMMUNG = {"ruhig": "calm", "gespannt": "tense", "heiter": "cheerful", "duester": "gloomy", "dramatisch": "dramatic"}
NONVERBAL = {"—": "", "lachen": "[laughs]", "seufzen": "[sighs]", "gaehnen": "[yawns]", "staunen": "[gasps]"}
VORTRAG = {"normal": None, "fluestern": "whisper", "leise": "soft"}
VERSTAERKER = {1: "slightly ", 2: "", 3: "very ", 4: "extremely "}
LLM_TEIL = 60


def pfad(werk):
    return config.work_path(werk, "430_fish_regie")


def korr_pfad(werk):
    return os.path.join(config.work_dir(werk), "430_korrekturen.json")


def _json(p, leer=None):
    if not os.path.exists(p):
        return leer
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def laden(werk):
    return _json(pfad(werk))


def ziele(b):
    """{lg: stufe} je bestelltem Hoerspiel mit Motor Fish (nur Gemini-Stufen premium/drama)."""
    out = {}
    for lg, st in s420._ziele(b).items():
        if s410.ENGINE.get(st) == "gemini" and fish_motor.motor(b.roh, lg) == "fish":
            out[lg] = st
    return out


# ============================================================ Regler
def _regler(roh):
    r = dict(REGLER_STD)
    r.update({k: v for k, v in (roh.get("fish_regler") or {}).items() if v is not None and k in REGLER_STD})
    return r


def _regler_gueltig(rg):
    try:
        return (500 <= int(rg["block_min"]) <= int(rg["block_max"]) <= 5000 and 50 <= int(rg["anweisung_max"]) <= 400
                and 0 <= int(rg["overlay_plus"]) <= 2)
    except Exception:
        return False


def werk_regler(roh):
    """audio_regler (400) 1–10, Standard 5."""
    r = roh.get("audio_regler") or {}
    out = {}
    for k in ("betonung", "emotion", "tempo"):
        try:
            out[k] = min(10, max(1, int(r.get(k, 5))))
        except (TypeError, ValueError):
            out[k] = 5
    return out


# ============================================================ Moment -> Fish-Sprache (feste Tabelle)
def moment_norm(m):
    """LLM-Antwort -> gueltiges Moment-Dict oder None."""
    if not isinstance(m, dict):
        return None
    s = fish_motor._norm(m.get("s") or m.get("stimmung"))
    try:
        i = int(m.get("i") or m.get("intensitaet") or 2)
    except (TypeError, ValueError):
        return None
    n = fish_motor._norm(m.get("n") or m.get("nonverbal") or "—")
    n = "—" if n in ("", "-", "—", "none", "keins") else n
    v = fish_motor._norm(m.get("v") or m.get("vortrag") or "normal")
    b = (m.get("b") or m.get("betonung") or "") or ""
    if s not in STIMMUNG or i not in (1, 2, 3) or n not in NONVERBAL or v not in VORTRAG:
        return None
    b = str(b).strip()
    if b and (" " in b or len(b) > 30):
        b = ""
    return {"stimmung": s, "intensitaet": i, "nonverbal": n, "vortrag": v, "betonung": b or None}


def moment_text(m, wr, plus=0):
    """Moment -> englische Stichworte (Teil 2 der Anweisung). plus: Verstaerkung fuer Figuren mit VC-Overlay
    (510/511 glaettet die Prosodie; CK 25.11.2026: mit Overlay traegt die starke Fassung)."""
    if not m:
        return ""
    stufe = m["intensitaet"] + (-1 if wr["emotion"] <= 3 else 1 if wr["emotion"] >= 7 else 0) + plus
    teile = []
    if stufe >= 1:
        teile.append(VERSTAERKER[min(stufe, 4)] + STIMMUNG[m["stimmung"]])
    if wr["tempo"] >= 7:
        teile.append("brisk")
    elif wr["tempo"] <= 3:
        teile.append("unhurried")
    return ", ".join(teile)


def anweisung_bauen(grundhaltung, m, wr, plus=0):
    teile = [x for x in (grundhaltung or "", moment_text(m, wr, plus)) if x]
    out = f"[{'; '.join(teile)}]" if teile else ""
    nv = NONVERBAL.get((m or {}).get("nonverbal") or "—", "")
    return (out + (" " + nv if out and nv else nv)).strip()


def text_markieren(text, m, wr):
    """Wort-Betonung / Fluestern / leise als Fish-Markup im Sprechtext (nur Figurenbeitraege)."""
    if not m:
        return text
    b = m.get("betonung")
    if b and wr["betonung"] >= 4:
        t2, n = re.subn(rf"(?<!\w)({re.escape(b)})(?!\w)", r"<emphasis>\1</emphasis>", text, count=1)
        if n:
            text = t2
    tag = VORTRAG.get(m.get("vortrag") or "normal")
    if tag:
        text = f"<{tag}>{text}</{tag}>"
    return text


def fish_text(bt):
    """Beitrag -> Text fuer Fish (Anweisung + markierter Text)."""
    t = bt.get("text_fish") or bt["text"]
    return f"{bt['anweisung']} {t}".strip() if bt.get("anweisung") else t


def block_text(beitraege):
    out = []
    for bt in beitraege:
        sep = "" if not out else ("\n\n" if bt.get("absatz") else " ")
        out.append(sep + fish_text(bt))
    return "".join(out)


# ============================================================ Beitraege + Bloecke
def beitraege_bauen(data, lg, segs_fn=None, cast=None):
    """-> (beitraege, befund). Ohne segs_fn (Hoerbuch) nur Erzaehler. cast: {figur: ensemble-eintrag}."""
    content = data.get("content") or {}
    prod = data.get("production") or {}
    sp = prod.get("sprechtext") or {}
    an = (data.get("ansagen") or {}).get(lg) or []
    out, bef = [], {"unbekannt": {}, "veraltet": [], "statist": 0}
    absatz = True

    def neu(tid, k, fig, text, typ, abs_):
        out.append({"id": f"{tid}_{k:02d}", "tid": tid, "seg": k, "fig": fig, "text": text.strip(), "typ": typ,
                    "absatz": abs_, "anweisung": "", "block": None})

    for k in an:
        if k.get("position") == "anfang" and (k.get("sprechtext") or k.get("text") or "").strip():
            neu(k["id"], 0, ERZ, k.get("sprechtext") or k.get("text"), "ansage", True)
    for tid, e in content.items():
        if not isinstance(e, dict):
            continue
        typ = e.get("type", "s")
        if typ in config.NO_AUDIO_TYPES or typ == "h":
            absatz = True
        if typ in config.NO_AUDIO_TYPES:
            continue
        t = (sp.get(tid) or {}).get(lg)
        if t is None:
            t = str(e.get(lg) or "")
        if not t.strip():
            continue
        segs = segs_fn(tid) if segs_fn else None
        if segs and re.sub(r"\s+", "", "".join(g["t"] for g in segs)) != re.sub(r"\s+", "", t):
            bef["veraltet"].append(tid)
            segs = None
        if not segs:
            neu(tid, 0, ERZ, t, typ, absatz)
        else:
            for i, g in enumerate(segs):
                if not g["t"].strip():
                    continue
                fig = g.get("s") or ERZ
                if fig != ERZ and fig not in (cast or {}):
                    if fig not in (cast or {}).get("_statisten", set()):
                        bef["unbekannt"][fig] = bef["unbekannt"].get(fig, 0) + 1
                    else:
                        bef["statist"] += 1
                    fig = ERZ
                if out and out[-1]["tid"] == tid and out[-1]["fig"] == fig == ERZ:
                    out[-1]["text"] += " " + g["t"].strip()           # Erzaehler-Stuecke eines Satzes zusammen
                    continue
                neu(tid, i, fig, g["t"], typ, absatz if i == 0 else False)
        if typ == "h":
            out[-1]["absatz"] = True
            absatz = True
        else:
            absatz = False
    for k in an:
        if k.get("position") != "anfang" and (k.get("sprechtext") or k.get("text") or "").strip():
            neu(k["id"], 0, ERZ, k.get("sprechtext") or k.get("text"), "ansage", True)
    return out, bef


def bloecke_bilden(beitraege, block_min=2000, block_max=2500):
    """Bloecke an Absatzgrenzen (>= block_min), spaetestens an Satzgrenzen (> block_max); Kapitelwechsel = neuer Block.
    Ansagen am Anfang/Ende bilden eigene Bloecke. Setzt bt['block']; -> [{nr, kap, ids, zeichen}]."""
    bl, cur, n = [], [], 0

    def zu():
        nonlocal cur, n
        if cur:
            bl.append({"nr": len(bl) + 1, "kap": cur[0]["tid"][:4] if cur[0]["typ"] != "ansage" else "ansage",
                       "ids": [x["id"] for x in cur], "zeichen": n})
        cur, n = [], 0

    for bt in beitraege:
        if cur:
            k_alt = cur[-1]["tid"][:4] if cur[-1]["typ"] != "ansage" else "ansage"
            k_neu = bt["tid"][:4] if bt["typ"] != "ansage" else "ansage"
            satzgrenze = bt["tid"] != cur[-1]["tid"]
            if k_alt != k_neu or (satzgrenze and ((bt["absatz"] and n >= block_min) or n + len(bt["text"]) > block_max)):
                zu()
        cur.append(bt)
        n += len(bt["text"])
    zu()
    nach_id = {x["id"]: x for x in beitraege}
    for b_ in bl:
        for i in b_["ids"]:
            nach_id[i]["block"] = b_["nr"]
    return bl


# ============================================================ LLM (Moment-Schicht)
def _prompt(items, lg):
    zeilen = "\n".join(json.dumps(x, ensure_ascii=False) for x in items)
    return f"""You are the director of an audio drama in which ONE narrator voices all characters. For each character
line below, choose the delivery of this moment from a FIXED vocabulary (no free text):
- "s" (mood): one of "ruhig" (calm), "gespannt" (tense), "heiter" (cheerful), "duester" (gloomy), "dramatisch" (dramatic)
- "i" (intensity): 1 (slight), 2 (normal), 3 (strong)
- "n" (nonverbal, only if the text or context clearly implies it): "—", "lachen" (laugh), "seufzen" (sigh),
  "gaehnen" (yawn), "staunen" (gasp)
- "b" (optional): ONE word of the line that carries contrastive stress, copied exactly; "" if none (use rarely)
- "v" (delivery): "normal", "fluestern" (whisper, only if the text says so), "leise" (soft)
Use the context (previous narration) and the character. Be sparing: most lines are "i": 2, "n": "—", "b": "", "v": "normal".
Language of the lines: {lg}.

Return ONLY JSON: {{"<id>": {{"s": "...", "i": 2, "n": "—", "b": "", "v": "normal"}}}}

LINES:
{zeilen}"""


def _llm(prompt, modell=None):
    p = api_layer.parse_json(api_layer.call_model("caster", prompt, temperature=0.1, max_tokens=8000,
                                                  modell=modell or None))
    if not isinstance(p, dict):
        raise ValueError("Antwort ist kein JSON-Objekt")
    return p


def momente_kapitel(beitraege, lg, modell=None):
    """Figurenbeitraege eines Kapitels -> {id: moment|None}."""
    items, vorher = [], ""
    for bt in beitraege:
        if bt["fig"] == ERZ:
            vorher = bt["text"][-200:]
            continue
        items.append({"id": bt["id"], "figur": bt["fig"], "kontext": vorher, "text": bt["text"]})
    out = {}
    if mock.aktiv() or config.RUN_MODE == "mock":
        return {x["id"]: {"stimmung": "ruhig", "intensitaet": 2, "nonverbal": "—", "vortrag": "normal",
                          "betonung": None} for x in items}
    for i in range(0, len(items), LLM_TEIL):
        teil = items[i:i + LLM_TEIL]
        try:
            a = _llm(_prompt(teil, lg), modell)
        except Exception as e:
            print(f"[430] LLM-Fehler ({type(e).__name__}: {e}) – Teil ohne Moment", flush=True)
            a = {}
        for x in teil:
            out[x["id"]] = moment_norm(a.get(x["id"]))
    return out


# ============================================================ Korrekturen
def korrekturen(werk):
    return _json(korr_pfad(werk), {}) or {}


def anweisung_setzen(werk, lg, bid, text, wer="CK"):
    """Manuelle Anweisung je Beitrag (Cockpit/CLI); text '-' = entfernen. Bindung an den Beitragstext (Hash)."""
    d = laden(werk) or {}
    bts = {x["id"]: x for x in ((d.get("sprachen") or {}).get(lg) or {}).get("beitraege") or []}
    if bid not in bts:
        raise ValueError(f"Beitrag {lg}/{bid} unbekannt (430 erst laufen lassen)")
    k = korrekturen(werk)
    lk = k.setdefault(lg, {})
    if text.strip() == "-":
        lk.pop(bid, None)
    else:
        lk[bid] = {"anweisung": text.strip(), "h": manifest.hash_text(bts[bid]["text"]), "wer": wer,
                   "wann": status.jetzt()}
    manifest.json_atomar(korr_pfad(werk), k, indent=1)
    return k


# ============================================================ Lauf
def run(werk, wer=None, regler=None, kapitel=None, neu=False, anweisungen=None, trocken=False):
    wer = wer or "pipeline"
    g = gate.Gate(werk, STAGE, ruecksprung="430", wer=wer)
    b = bestellung.lesen(werk)
    rg = _regler(dict(b.roh))
    if regler and any(v is not None for v in regler.values()):
        rg.update({k: v for k, v in regler.items() if v is not None and k in REGLER_STD})
        if not trocken:
            b = bestellung.feld_setzen(werk, fish_regler=rg)
    for x in anweisungen or []:
        lgid, t = x.split("=", 1)
        lg_, bid = lgid.split("/", 1)
        if not trocken:
            anweisung_setzen(werk, lg_, bid, t, wer)
    wr = werk_regler(b.roh)
    zl = ziele(b)
    g.metrik("ziele", zl)
    g.metrik("regler", rg)
    g.metrik("werk_regler", wr)
    ip = config.work_path(werk, "400_regie")
    ok = g.pflicht("eingang", os.path.exists(ip), ruecksprung="400", text="400_regie.json vorhanden")
    ok = g.pflicht("fish", bool(zl), ruecksprung="095", text="Hoerspiel mit Motor Fish bestellt (book.json audio_motor)") and ok
    ok = g.pflicht("regler", _regler_gueltig(rg), wert=rg, text="Regler im Bereich") and ok
    for v in ("400", "410", "420"):
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
    sp420 = s420.laden(werk) or {}
    korr = korrekturen(werk)
    ck = manifest.Checkpoint(werk, STAGE)
    kap_neu = set(kapitel or [])
    ausgabe = {"schema": SCHEMA, "werk": werk, "datum": status.jetzt(), "regler": rg, "werk_regler": wr,
               "sprachen": {}}
    je_sprache, n_llm = {}, 0
    for lg, st in sorted(zl.items()):
        bs = (((c or {}).get("rollen") or {}).get(lg) or {}).get(st) or {}
        if not g.pflicht(f"engine_{lg}", bs.get("engine") == "fish", wert=bs.get("engine"), ruecksprung="410",
                         text=f"{lg}: Casting rollen[{lg}][{st}] mit Engine fish ({bs.get('engine')})"):
            continue
        cast = {e["figur"]: e for e in bs.get("ensemble") or [] if e.get("figur") and e.get("stimme")}
        cast["_statisten"] = {s_.get("figur") for s_ in bs.get("statisten") or []}
        ohne = [f for f, e in cast.items() if f != "_statisten" and e.get("fish_grundhaltung_quelle") != "ohne"
                and not fish_motor.grundhaltung_ok(e.get("fish_grundhaltung"))]
        g.pruefe(f"grundhaltung_{lg}", not ohne, wert=ohne[:5], bei_fehler="mensch", ruecksprung="410",
                 text=f"{lg}: jede Figur mit Grundhaltung oder Freigabe 'ohne'" + (f" – fehlt: {', '.join(ohne[:4])}" if ohne else ""))
        seg_lg = {t: (v.get(lg) or {}).get("seg") for t, v in (sp420.get("saetze") or {}).items()}
        bts, bef = beitraege_bauen(data, lg, lambda t: seg_lg.get(t), cast)
        # Abdeckung: jeder Audio-Knoten mit Sprechtext in einem Beitrag
        soll = [t for t, e in (data.get("content") or {}).items() if isinstance(e, dict)
                and e.get("type", "s") not in config.NO_AUDIO_TYPES
                and str(((data.get("production") or {}).get("sprechtext") or {}).get(t, {}).get(lg) or e.get(lg) or "").strip()]
        da = {x["tid"] for x in bts}
        fehlt = [t for t in soll if t not in da]
        g.pruefe(f"abdeckung_{lg}", not fehlt, wert=len(fehlt), bei_fehler="stopp", ruecksprung="400",
                 text=f"{lg}: Audio-Knoten ohne Beitrag {len(fehlt)}" + (f" {fehlt[:4]}" if fehlt else ""))
        if bef["unbekannt"]:
            g.hinweis(f"unbekannt_{lg}", False, wert=bef["unbekannt"],
                      text=f"{lg}: unbekannte Sprecher -> Erzaehler: " + ", ".join(f"{k} ({v})" for k, v in
                                                                             sorted(bef["unbekannt"].items())[:5]))
        if bef["veraltet"]:
            g.hinweis(f"veraltet_{lg}", False, wert=len(bef["veraltet"]),
                      text=f"{lg}: {len(bef['veraltet'])} Saetze mit veralteten 420-Segmenten -> ganz Erzaehler "
                           f"({', '.join(bef['veraltet'][:3])}; 420 neu laufen lassen)")
        # Moment je Kapitel (Checkpoint)
        usage_log.set_context(werk, STAGE, sprache=lg)
        kaps = list(dict.fromkeys(x["tid"][:4] for x in bts if x["typ"] != "ansage"))
        momente, ungueltig, offen_trocken = {}, 0, 0
        llm_kaps = []                                    # (kap, hash, beitraege) -> parallel (25.11.2026)
        for kap in kaps:
            fig_bts = [x for x in bts if x["tid"].startswith(kap)]
            h = manifest.hash_obj({"v": PROMPT_V, "m": rg["modell"],
                                   "b": [(x["id"], x["fig"], x["text"]) for x in fig_bts if x["fig"] != ERZ]})
            alt = None if (neu or kap in kap_neu) else ck.lesen(kap, lg, h)
            if alt is None:
                if not any(x["fig"] != ERZ for x in fig_bts):
                    alt = {}
                elif trocken:
                    offen_trocken += 1
                    alt = {}
                else:
                    llm_kaps.append((kap, h, fig_bts))
                    continue
            momente.update(alt)
        if llm_kaps:
            import concurrent.futures as cf

            def _kap(k):
                usage_log.set_context(werk, STAGE, sprache=lg)      # Neben-Thread: Kontext je Thread
                return k, momente_kapitel(k[2], lg, rg["modell"])
            n_par = max(1, int(getattr(config, "FISH_REGIE_PARALLEL", 5)))
            print(f"[430] {lg}: Momente fuer {len(llm_kaps)} Kapitel ({n_par} parallel)", flush=True)
            with cf.ThreadPoolExecutor(n_par) as ex:
                for (kap, h, _), alt in ex.map(_kap, llm_kaps):
                    ck.schreiben(kap, lg, h, alt)               # Checkpoint je Kapitel (Abbruch -> Rest neu)
                    momente.update(alt)
                    n_llm += 1
        # Anweisungen
        man = korr.get(lg) or {}
        n_man, lang = 0, []
        for bt in bts:
            if bt["fig"] == ERZ:
                continue
            e = cast[bt["fig"]]
            gh = e.get("fish_grundhaltung") if e.get("fish_grundhaltung_quelle") != "ohne" else ""
            m = momente.get(bt["id"])
            if bt["id"] in momente and m is None:
                ungueltig += 1
            bt["moment"] = m
            bt["overlay"] = bool(e.get("vc_ziel"))      # Figur wird in 510/511 per Chatterbox-VC umgefaerbt
            bt["anweisung"] = anweisung_bauen(gh, m, wr, int(rg["overlay_plus"]) if bt["overlay"] else 0)
            bt["text_fish"] = text_markieren(bt["text"], m, wr)
            mk = man.get(bt["id"])
            if mk and mk.get("h") == manifest.hash_text(bt["text"]):
                bt["anweisung"], bt["manuell"] = mk["anweisung"], True
                n_man += 1
            if len(bt["anweisung"]) > int(rg["anweisung_max"]):
                lang.append(bt["id"])
        g.pruefe(f"anweisung_{lg}", not lang, wert=len(lang), bei_fehler="mensch", ruecksprung="430",
                 text=f"{lg}: Anweisung <= {rg['anweisung_max']} Zeichen" + (f" – zu lang: {lang[:4]}" if lang else ""))
        g.hinweis(f"moment_{lg}", not ungueltig, wert=ungueltig,
                  text=f"{lg}: Moment ungueltig/fehlt (ohne Moment) {ungueltig}")
        if offen_trocken:
            g.hinweis(f"trocken_{lg}", False, text=f"{lg}: {offen_trocken} Kapitel ohne Moment-Checkpoint (Probe ohne LLM)")
        bl = bloecke_bilden(bts, int(rg["block_min"]), int(rg["block_max"]))
        n_fig = sum(1 for x in bts if x["fig"] != ERZ)
        je_sprache[lg] = {"beitraege": len(bts), "figurenbeitraege": n_fig, "bloecke": len(bl), "manuell": n_man,
                          "zeichen": sum(x["zeichen"] for x in bl), "unbekannt": sum(bef["unbekannt"].values()),
                          "statisten": bef["statist"], "veraltet": len(bef["veraltet"]), "moment_ungueltig": ungueltig}
        ausgabe["sprachen"][lg] = {"stufe": st, "beitraege": bts, "bloecke": bl}
    g.metrik("je_sprache", je_sprache)
    g.metrik("llm_aufrufe", n_llm)
    g.mock(0)
    aus_hash = manifest.hash_obj({lg: [(x["id"], x["fig"], x["text"], x["anweisung"], x.get("text_fish"), x["block"])
                                       for x in v["beitraege"]] for lg, v in ausgabe["sprachen"].items()})
    g.metrik("ausgabe_hash", aus_hash)
    st0 = status.laden(werk)["stages"].get(STAGE) or {}
    if st0.get("zustand") == "frei" and (st0.get("gate") or {}).get("ergebnis") == "mensch" \
            and (st0.get("metriken") or {}).get("ausgabe_hash") == aus_hash:
        for p in g.pruefungen:
            if not p["ok"] and p["bei_fehler"] == "mensch":
                p["bei_fehler"] = "hinweis"
                p["text"] += " [Mensch-Freigabe gilt, Ausgabe unveraendert]"
    if not trocken and ausgabe["sprachen"]:
        manifest.json_atomar(pfad(werk), ausgabe, indent=1)
    g.entscheide(schreiben=not trocken)
    g.ausgabe = ausgabe
    return g


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 430 Fish-Regie")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--block-min", type=int)
    ap.add_argument("--block-max", type=int)
    ap.add_argument("--anweisung-max", type=int)
    ap.add_argument("--modell")
    ap.add_argument("--overlay-plus", type=int, help="Intensitaet +N fuer Figuren mit VC-Overlay (0-2, Std 1)")
    ap.add_argument("--anweisung", action="append", metavar="LG/ID=TEXT")
    ap.add_argument("--kapitel")
    ap.add_argument("--neu", action="store_true")
    ap.add_argument("--trocken", action="store_true")
    a = ap.parse_args(argv)
    regler = {"block_min": a.block_min, "block_max": a.block_max, "anweisung_max": a.anweisung_max,
              "modell": a.modell, "overlay_plus": a.overlay_plus}
    try:
        if (any(v is not None for v in regler.values()) or a.anweisung) and not a.trocken:
            from pipeline import s080_mandant
            s080_mandant.darf(a.werk, "entscheiden", a.wer or "pipeline")
        g = run(a.werk, a.wer, regler, kapitel=(a.kapitel.split(",") if a.kapitel else None), neu=a.neu,
                anweisungen=a.anweisung, trocken=a.trocken)
    except gate.GateHalt as e:
        print(e)
        return e.exit_code
    except (ValueError, PermissionError, RuntimeError) as e:
        print(f"[430] Fehler: {e}")
        return 1
    print(g.bericht())
    return gate.EXIT[g.ergebnis["ergebnis"]]


if __name__ == "__main__":
    sys.exit(main())
