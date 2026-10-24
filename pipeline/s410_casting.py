"""STAGE 410 — Casting
Funktion:     Besetzt Erzaehler und Figurenensemble mit Stimmen.
Wirkungsweise: Steckbriefe per DeepSeek, Archivsuche oder Gemini Voice Design, Abstandsregel; Freigabetor (--freigeben).
Komponenten:  pipeline/s410_casting.py, voice_registry, trennung, tts_client
Zulieferer:   s400 Regie (work/400_regie.json), stimmen_archiv
Abnehmer:     s420 Sprecher, s500 Vertonung (Tor muss freigegeben sein), s510 Overlay, s630 ePub (work/casting.json, book.json)
(Nomenklatur seit 18.10.2026, Uebersicht: docs/Pipeline_Strang_Matrix.xlsx)

--- Bisherige Beschreibung ---

READ LAYER — Stage 57: Casting (Stimmen-Ensemble je Werk)
=========================================================
Laeuft VOR der Vertonung (Stage 58). Bestimmt Erzaehler + Figuren-Ensemble und
besetzt jede Rolle mit einer Stimme aus dem Stimmen-Archiv (stimmen_archiv/) —
oder designt eine neue, wenn nichts passt.

Input : work/400_regie.json (Fallback: juengster Checkpoint mit content)
Output: work/casting.json  (Besetzungsplan + Figuren-Steckbriefe, Tor 'offen')
        stimmen_archiv/<neue_stimme>/  (nur mit --design)
Nach Freigabe (--freigeben): book.json -> audio_voice (Erzaehler) + besetzung {figur: voice}

Ablauf
  1. LLM (config.MODELS['caster'], Default = profiler) liest den Text und liefert
     Erzaehler-Steckbrief + Figuren-Steckbriefe (festes Merkmal-Schema, siehe voice_registry).
  2. Erzaehler: book.json 'erzaehler_stimme' gilt FEST (auch bei Ich-Erzaehler; 16.10.2026, Bug
     Baskerville) > Genre-Zuordnung (config.CASTING_GENRE_ERZAEHLER) > bester Archiv-Treffer >
     neu designen. Ohne Vorgabe: Ich-Erzaehler = Stimme der Figur.
  2b. Abstandsregel Figur <-> Erzaehler (pipeline/trennung.py, geeicht 16.10.2026): Erzaehler wird an
     der fertigen Einzelstimmen-Fassung des Werks gemessen (F0, VTL); Kandidaten mit hoerbarem Abstand
     (D >= D_ziel) zuerst. Je Figur und Sprache 'trennung' {D, dF0_ht, dVTL_proz, status} im Plan;
     bei knapp/zu_nah 'korrektur' {formant_faktor, tonhoehe_ht} -> wird NACH dem VC angewendet
     (tools/overlay_montage.py). Pruefung am fertigen Overlay: tools/trennung_messen.py + Modal.
  3. Ensemble: Haupt- und Nebenfiguren mit genug Dialoganteil (CASTING_MIN_ANTEIL),
     max. CASTING_MAX_ENSEMBLE. Reihenfolge: Hauptfiguren zuerst.
     Je Figur: beste Archiv-Stimme, die (a) passt (>= Schwelle), (b) im Werk noch frei ist,
     (c) sich hoerbar vom bisherigen Ensemble unterscheidet. Sonst neu designen
     (Prompt enthaelt Abgrenzung zu allen Ensemble-Stimmen gleichen Geschlechts),
     danach Grundton messen; zu nah -> ein zweiter Versuch mit verschobener Tonlage.
  4. Statisten (wenig Text) sprechen mit der Erzaehlerstimme.

Aufruf
  py -3.11 -m pipeline.s410_casting <book_id>              Plan (kein Design, nur Archiv)
  py -3.11 -m pipeline.s410_casting <book_id> --design     fehlende Stimmen designen
  py -3.11 -m pipeline.s410_casting <book_id> --neu        Steckbriefe neu erzeugen (LLM)
  py -3.11 -m pipeline.s410_casting <book_id> --freigeben  Besetzung in book.json uebernehmen
  py -3.11 -m pipeline.s410_casting <book_id> --trennung   Abstandsregel fuer bestehende Besetzung
                                                               (+ --neu: Korrekturen neu vorschlagen)
  Optional: --quelle <pfad/zu/stageXX.json>  (z. B. Altfassung)
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import api_layer
from pipeline import voice_registry as vr
from pipeline import trennung

CHECKPOINTS = ["400_regie", "330_rueckuebersetzung", "320_integritaet", "310_uebersetzung", "300_voruebersetzung", "210_profil", "200_tagging"]
MAX_ENSEMBLE = getattr(config, "CASTING_MAX_ENSEMBLE", 8)
MIN_ANTEIL = getattr(config, "CASTING_MIN_ANTEIL", 2.0)       # % der Dialogsaetze
MAX_TEXT = getattr(config, "CASTING_MAX_ZEICHEN", 900_000)
GENRE_ERZAEHLER = getattr(config, "CASTING_GENRE_ERZAEHLER", {
    "maerchen": "grossmutter_a",
    "abenteuer": "herr_a",
    "krimi": "herr_a",
    "grosses_werk": "herr_b",
})


# ============================================================
# EIN- UND AUSGABE
# ============================================================

def _quelle_laden(book_id, quelle=None):
    if quelle:
        with open(quelle, encoding="utf-8") as f:
            return json.load(f), quelle
    for cp in CHECKPOINTS:
        p = config.work_path(book_id, cp)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            if d.get("content"):
                return d, p
    raise FileNotFoundError(f"Kein Text-Checkpoint fuer {book_id} (200_tagging..06).")


def _book_json_pfad(book_id):
    return os.path.join(config.book_dir(book_id), "book.json")


def _book_json(book_id):
    try:
        with open(_book_json_pfad(book_id), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def casting_pfad(book_id):
    return os.path.join(config.work_dir(book_id), "casting.json")


def aktiv(book_id) -> bool:
    """Casting nur fuer Werke mit Ensemble-Modus (book.json besetzung_modus)
    oder global per config.CASTING_AKTIV."""
    if getattr(config, "CASTING_AKTIV", False):
        return True
    return _book_json(book_id).get("besetzung_modus") in ("erzaehler", "ensemble")


# ============================================================
# STECKBRIEFE PER LLM
# ============================================================

def _text_mit_ids(data):
    src = config.SOURCE_LANGUAGE
    zeilen, dl = [], 0
    for tid, e in data["content"].items():
        if e.get("type") in config.NO_AUDIO_TYPES:
            continue
        t = (e.get(src) or "").strip()
        if not t:
            continue
        if e.get("type") == "dl":
            dl += 1
            zeilen.append(f"[{tid}] {e['sprecher']}: {t}" if e.get("sprecher") else f"[{tid}] {t}")
        else:
            zeilen.append(t)
    text = "\n".join(zeilen)
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT] + "\n[... gekuerzt ...]"
    return text, dl


def _prompt(data, text, n_dl):
    titel = data["meta"].get("title", "")
    autor = data["meta"].get("author", "")
    alle = lambda xs: " | ".join(xs)
    return f"""You are the casting director for a multi-voice audiobook (English original, German translation).
Read the work and describe the NARRATOR and every CHARACTER WHO SPEAKS, so that each can get a fitting voice.
Dialogue lines are marked with their id in square brackets, e.g. [c001_00004_dl]. There are {n_dl} dialogue lines.

Return ONLY this JSON, nothing else:
{{
  "erzaehler": {{
    "erzaehlform": "allwissend | ich",
    "ich_figur": "<name of the first-person narrator if erzaehlform is ich, else empty>",
    "genre_stimme": "maerchen | abenteuer | krimi | grosses_werk | anderes",
    "merkmale": {{<schema>}},
    "stimm_beschreibung_en": "<2-3 sentence voice design prompt for the narrator>"
  }},
  "figuren": [
    {{
      "name": "<name as in source>",
      "name_de": "<German name as used in the translation>",
      "gewicht": "haupt | neben | statist",
      "dialog_anteil_prozent": <estimated share of all dialogue lines spoken by this character, number>,
      "merkmale": {{<schema>}},
      "herkunft_stand": "<origin, class, education - only if it shapes the voice>",
      "beruf": "<only if it shapes the voice>",
      "koerper": "<build/size if it shapes resonance, e.g. tiny, massive>",
      "auffaelligkeiten": "<speech quirks: stutter, lisp, yawning, sniffing, dialect ...>",
      "haltung": "<attitude towards others>",
      "humor": "<dry, silly, none ...>",
      "entwicklung": "<how the character changes in the book, if relevant for the voice>",
      "unterscheiden_von": ["<names of similar characters that must sound clearly different>"],
      "beleg": "<short quote (max 15 words) from the text supporting the description>",
      "beispiel_tag_ids": ["<1-3 ids of dialogue lines where this character speaks a lot>"],
      "stimm_beschreibung_en": "<2-3 sentence voice design prompt: age, gender, pitch, timbre, pace, temperament, accent>",
      "kurz": "<German summary in 5-8 words, e.g. 'nervoeser alter Hofbeamter, hoch, hastig'>"
    }}
  ],
  "hinweise": "<anything a casting director should know, in German>"
}}

<schema> = {{
  "geschlecht": "w | m | neutral",
  "alter": "kind | jung | mittel | alt | greis",
  "tonlage": "hoch | mittel | tief",
  "klangfarbe": [one or more of: {alle(vr.KLANGFARBEN)}],
  "tempo": "langsam | mittel | schnell",
  "temperament": [one or more of: {alle(vr.TEMPERAMENTE)}],
  "sicherheit": "unsicher | neutral | fest",
  "akzent": "<e.g. britisch, schottisch, Cockney, amerikanisch, or empty>"
}}

Rules:
- Use ONLY the listed values for the schema fields (German words without umlauts as given).
- Base everything on the text. Where the text says nothing about the voice, infer from age, role and behaviour.
- Animals and fantasy creatures: describe them as a human voice actor would play them (age, gender, temperament).
- Include every character who speaks at least once; mark minor ones as 'statist'.
- If lines carry a speaker prefix ("NAME: text", a stage play), use exactly that NAME as "name"
  (keep the capitalisation as given) and derive dialog_anteil_prozent from the prefixed lines.
- NEVER reference real actors, film or dubbing voices, or famous adaptations (e.g. Disney). Original text only.
- For the narrator: fairy tales / children's classics -> 'maerchen'; adventure -> 'abenteuer'; crime -> 'krimi';
  monumental literary novels -> 'grosses_werk'.

WORK: {titel} — {autor}

--- TEXT START ---
{text}
--- TEXT END ---"""


def steckbriefe_erzeugen(data):
    text, n_dl = _text_mit_ids(data)
    task = "caster" if "caster" in config.MODELS else "profiler"
    print(f"[stage57] Steckbriefe per {config.MODELS[task]} ({len(text):,} Zeichen, {n_dl} Dialogzeilen) ...")
    # QF-8 (18.10.2026): max_tokens explizit (Default 8192 schnitt grosse Ensembles ab),
    # abgeschnittenes JSON wie in Stage 51 retten.
    roh = api_layer.call_model(task, _prompt(data, text, n_dl), temperature=0.2, max_tokens=16000)
    try:
        sb = api_layer.parse_json(roh)
    except Exception:
        from pipeline.s210_profil import _abgeschnitten_retten
        print("[stage57] WARNUNG: Steckbrief-JSON unvollstaendig -- gerettet, letzte Figur ggf. gekappt.")
        sb = _abgeschnitten_retten(roh)
    for f in sb.get("figuren", []):
        f["merkmale"] = vr.normalisieren(f.get("merkmale"))
    if sb.get("erzaehler"):
        sb["erzaehler"]["merkmale"] = vr.normalisieren(sb["erzaehler"].get("merkmale"))
    sb["_dialogzeilen"] = n_dl
    return sb


# ============================================================
# MUSTER-TEXTE FUER NEUE STIMMEN
# ============================================================

def _muster(data, figur):
    """EN/DE-Mustertext: Dialogzeile(n) der Figur (beispiel_tag_ids)."""
    tgt = config.TARGET_LANGUAGES[0] if config.TARGET_LANGUAGES else "de"
    for tid in figur.get("beispiel_tag_ids") or []:
        e = data["content"].get(tid)
        if e and e.get(config.SOURCE_LANGUAGE):
            return {config.SOURCE_LANGUAGE: e[config.SOURCE_LANGUAGE], tgt: e.get(tgt, "")}
    return {"en": "The North Wind and the Sun were disputing which was the stronger, when a traveler came along.",
            "de": "Einst stritten sich Nordwind und Sonne, wer von ihnen beiden wohl der Stärkere wäre."}


def _stimmen_name(figur, reg):
    m = figur["merkmale"]
    teile = [m["geschlecht"], m["alter"], m["tonlage"]] + (m["temperament"][:1] or [])
    return vr.eindeutiger_name("_".join(teile), reg)


# ============================================================
# BESETZEN
# ============================================================

def _ensemble_eintrag(rolle, figur, name, s):
    return {"rolle": rolle, "figur": figur.get("name"), "name": name, "id": s.get("id"),
            "merkmale": s.get("merkmale"), "grundton_hz": s.get("grundton_hz"),
            "kurz": s.get("kurz") or figur.get("kurz", ""),
            "beschreibung": figur.get("stimm_beschreibung_en") or s.get("beschreibung", "")}


def _besetze(figur, rolle, data, werk, ensemble, gesperrt, design, rolle_typ="figur", erz_profil=None, lg="de"):
    """Gibt (plan_eintrag) zurueck und erweitert ensemble/gesperrt."""
    reg = vr.laden()
    name, s, score = vr.beste_stimme(figur["merkmale"], reg, gesperrt, ensemble, rolle_typ,
                                     erz_profil=erz_profil, lg=lg)
    if name:
        gesperrt.add(name)
        ensemble.append(_ensemble_eintrag(rolle, figur, name, s))
        return {"quelle": "archiv", "stimme": name, "id": s["id"], "passung": score}
    vorschau = vr.design_prompt(figur, ensemble)
    if not design:
        return {"quelle": "neu_zu_designen", "stimme": None, "id": None, "passung_bestes_archiv": score,
                "design_prompt": vorschau}
    figur = dict(figur, rolle_typ=rolle_typ)
    versuch_merkmale = dict(figur["merkmale"])
    hinweis = ""
    for versuch in (1, 2):
        neu_name = _stimmen_name(dict(figur, merkmale=versuch_merkmale), vr.laden())
        print(f"    design {neu_name} (Versuch {versuch}) ...")
        try:
            e = vr.neu_designen(neu_name, dict(figur, merkmale=versuch_merkmale), ensemble, _muster(data, figur), werk)
        except Exception as ex:
            if versuch == 1:
                print(f"      Design-Fehler: {str(ex)[:160]} -> 2. Versuch mit Prompt aus Merkmalen")
                figur = dict(figur, stimm_beschreibung_en="")
                continue
            return {"quelle": "design_fehler", "stimme": None, "id": None, "fehler": str(ex)[:300],
                    "design_prompt": vr.design_prompt(figur, ensemble)}
        ok, grund, konflikt = vr.unterscheidbar(dict(e, name=neu_name), ensemble)
        if ok:
            break
        hinweis = grund
        reg = vr.laden()
        reg[neu_name]["status"] = "abgelehnt"
        reg[neu_name]["einsatz"] = f"automatisch verworfen: {grund}"
        vr.speichern(reg)
        # Tonlage vom Konflikt wegschieben: eigene Stimme lag hoeher -> hoch, sonst tief
        eigen, fremd = e.get("grundton_hz") or 0, (konflikt or {}).get("grundton_hz") or 0
        versuch_merkmale["tonlage"] = "hoch" if eigen >= fremd else "tief"
        figur = dict(figur, stimm_beschreibung_en="")   # Prompt aus Merkmalen neu bauen
    gesperrt.add(neu_name)
    ensemble.append(_ensemble_eintrag(rolle, figur, neu_name, e))
    plan = {"quelle": "neu", "stimme": neu_name, "id": e["id"], "grundton_hz": e.get("grundton_hz"),
            "design_prompt": e.get("beschreibung")}
    if not ok:
        plan["pruefen"] = f"auch nach 2 Versuchen nicht klar unterscheidbar ({hinweis})"
    elif hinweis:
        plan["hinweis"] = f"1. Versuch verworfen: {hinweis}"
    return plan


def besetzen(book_id, data, sb, design=False):
    werk = book_id
    bj = _book_json(book_id)
    ensemble, gesperrt, plan = [], set(), {"erzaehler": None, "ensemble": [], "statisten": []}
    figuren = sb.get("figuren", [])
    erz = sb.get("erzaehler") or {}
    ich = (erz.get("ich_figur") or "").strip() if erz.get("erzaehlform") == "ich" else ""

    # --- Erzaehler ---
    reg = vr.laden()
    fest = bj.get("erzaehler_stimme") or GENRE_ERZAEHLER.get(erz.get("genre_stimme", ""))
    erz_figur = next((f for f in figuren if f.get("name") == ich), None) if ich else None
    erz_profil = dict(erz_figur or erz, name=ich or "Erzaehler")
    vorgabe = bj.get("erzaehler_stimme")
    if vorgabe and vorgabe in reg:      # Vorgabe gilt fest, auch fuer Ich-Erzaehler
        fest, erz_figur = vorgabe, None
    if fest and fest in reg and reg[fest].get("status") != "abgelehnt" and not erz_figur:
        s = reg[fest]
        gesperrt.add(fest)
        ensemble.append(_ensemble_eintrag("erzaehler", erz_profil, fest, s))
        p = {"quelle": "vorgabe" if bj.get("erzaehler_stimme") else "genre", "stimme": fest, "id": s["id"],
             "genre": erz.get("genre_stimme")}
    else:
        p = _besetze(erz_profil, "erzaehler", data, werk, ensemble, gesperrt, design, rolle_typ="erzaehler")
    plan["erzaehler"] = dict(p, figur=erz_profil["name"], steckbrief=erz)

    # --- Erzaehler messen (fertige Fassung des Werks, sonst Archiv) -> Abstandsregel ---
    werk_dir = os.path.dirname(_book_json_pfad(book_id))
    erz_prof = {}
    for lg in ("de", "en"):
        try:
            erz_prof[lg] = trennung.erzaehler_profil(werk_dir, lg, plan["erzaehler"].get("stimme"))
        except Exception as ex:
            print(f"  [trennung] Erzaehler {lg} nicht messbar: {str(ex)[:120]}")
            erz_prof[lg] = {}
    plan["erzaehler"]["profil"] = {lg: {k: v for k, v in p_.items() if k in ("f0_hz", "vtl_cm", "quelle")}
                                   for lg, p_ in erz_prof.items()}
    haupt_lg = "de" if erz_prof.get("de", {}).get("f0_hz") else "en"

    # --- Ensemble ---
    rang = {"haupt": 0, "neben": 1, "statist": 2}
    figuren = sorted(figuren, key=lambda f: (rang.get(f.get("gewicht"), 2), -float(f.get("dialog_anteil_prozent") or 0)))
    for f in figuren:
        if ich and f.get("name") == ich:
            continue
        anteil = float(f.get("dialog_anteil_prozent") or 0)
        eigene = (f.get("gewicht") in ("haupt", "neben") and anteil >= MIN_ANTEIL
                  and len(plan["ensemble"]) < MAX_ENSEMBLE)
        if not eigene:
            plan["statisten"].append({"figur": f.get("name"), "gewicht": f.get("gewicht"),
                                      "anteil": anteil, "stimme": "erzaehler"})
            continue
        print(f"  [{f.get('gewicht')}] {f.get('name')} ({anteil:.0f} %) — {f.get('kurz', '')}")
        p = _besetze(f, "figur", data, werk, ensemble, gesperrt, design,
                     erz_profil=erz_prof.get(haupt_lg) or None, lg=haupt_lg)
        if p.get("stimme"):
            p["trennung"], p["korrektur"] = {}, {}
            for lg, ep in erz_prof.items():
                if not ep.get("f0_hz"):
                    continue
                t = trennung.abstand(trennung.stimm_profil(p["stimme"], lg), ep)
                p["trennung"][lg] = t
                k = trennung.korrektur_vorschlag(t["status"], trennung.richtung(f.get("merkmale"),
                                                 trennung.stimm_profil(p["stimme"], lg), ep))
                if k:
                    p["korrektur"][lg] = k
            if not p["korrektur"]:
                p.pop("korrektur")
        plan["ensemble"].append(dict(p, figur=f.get("name"), name_de=f.get("name_de"),
                                     gewicht=f.get("gewicht"), anteil=anteil, kurz=f.get("kurz"),
                                     steckbrief=f))
    return plan


# ============================================================
# ABSTANDSREGEL FUER EINEN BESTEHENDEN PLAN (Besetzung bleibt, z. B. von CK gesetzt)
# ============================================================

def trennung_pruefen(book_id, ueberschreiben=False):
    """Traegt fuer jede besetzte Figur 'trennung' (je Sprache) ein und schlaegt 'korrektur' vor,
    wo noch keine steht. Erzaehler = book.json erzaehler_stimme bzw. Plan."""
    cp = casting_pfad(book_id)
    with open(cp, encoding="utf-8") as f:
        c = json.load(f)
    werk_dir = os.path.dirname(_book_json_pfad(book_id))
    erz_name = _book_json(book_id).get("erzaehler_stimme") or c["plan"]["erzaehler"].get("stimme")
    erz = {lg: trennung.erzaehler_profil(werk_dir, lg, erz_name) for lg in ("de", "en")}
    c["plan"]["erzaehler"]["profil"] = {lg: {k: v for k, v in p_.items() if k in ("f0_hz", "vtl_cm", "quelle")}
                                        for lg, p_ in erz.items()}
    for e in c["plan"]["ensemble"]:
        if not e.get("stimme"):
            continue
        e["trennung"] = {}
        vorschlag = {}
        for lg, ep in erz.items():
            if not ep.get("f0_hz"):
                continue
            fp = trennung.stimm_profil(e["stimme"], lg)
            t = trennung.abstand(fp, ep)
            e["trennung"][lg] = t
            k = trennung.korrektur_vorschlag(t["status"], trennung.richtung((e.get("steckbrief") or {}).get("merkmale"), fp, ep))
            if k:
                vorschlag[lg] = k
        if vorschlag and (ueberschreiben or not e.get("korrektur")):
            e["korrektur"] = vorschlag
    with open(cp + ".bak_trennung", "w", encoding="utf-8") as f:
        json.dump(json.load(open(cp, encoding="utf-8")), f, ensure_ascii=False, indent=1)
    with open(cp, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=1)
    _zusammenfassung(c["plan"])
    return c


# ============================================================
# FREIGABE
# ============================================================

def freigeben(book_id):
    with open(casting_pfad(book_id), encoding="utf-8") as f:
        c = json.load(f)
    offen = [e["figur"] for e in c["plan"]["ensemble"] if not e.get("id")]
    if not c["plan"]["erzaehler"].get("id"):
        offen.insert(0, "Erzaehler")
    if offen:
        print(f"[stage57] Nicht freigegeben — ohne Stimme: {', '.join(offen)} (erst --design).")
        return False
    bp = _book_json_pfad(book_id)
    bj = _book_json(book_id)
    if os.path.exists(bp):
        bak = bp + ".bak_casting_" + time.strftime("%Y%m%d")
        if not os.path.exists(bak):
            with open(bak, "w", encoding="utf-8") as f:
                json.dump(bj, f, ensure_ascii=False, indent=2)
    bj["audio_voice"] = c["plan"]["erzaehler"]["id"]
    bj["erzaehler_stimme"] = c["plan"]["erzaehler"]["stimme"]
    bj["besetzung"] = {e["figur"]: {"stimme": e["stimme"], "id": e["id"], "name_de": e.get("name_de")}
                       for e in c["plan"]["ensemble"]}
    bj["besetzung_statisten"] = "erzaehler"
    with open(bp, "w", encoding="utf-8") as f:
        json.dump(bj, f, ensure_ascii=False, indent=2)
    reg = vr.laden()
    for rolle in [c["plan"]["erzaehler"]] + c["plan"]["ensemble"]:
        n = rolle["stimme"]
        if n in reg and reg[n].get("status") == "kandidat":
            reg[n]["status"] = "freigegeben"
        vr.speichern(reg)
        vr.nutzung_vermerken(n, book_id, rolle.get("figur"))
    c["tor"] = "freigegeben"
    c["freigegeben_am"] = time.strftime("%Y-%m-%d %H:%M")
    with open(casting_pfad(book_id), "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=1)
    print(f"[stage57] Freigegeben: Erzaehler {bj['erzaehler_stimme']}, {len(bj['besetzung'])} Figurenstimmen -> book.json")
    return True


# ============================================================
# HAUPTLAUF
# ============================================================

def run(book_id: str, lang: str = None, design: bool = None, neu: bool = False, quelle: str = None) -> dict:
    if design is None:
        design = getattr(config, "CASTING_AUTO_DESIGN", False)
    data, pfad = _quelle_laden(book_id, quelle)
    print(f"[stage57] Lese: {pfad}")
    cp = casting_pfad(book_id)
    alt = None
    if os.path.exists(cp):
        with open(cp, encoding="utf-8") as f:
            alt = json.load(f)
    if alt and alt.get("steckbriefe") and not neu:
        sb = alt["steckbriefe"]
        print("[stage57] Steckbriefe aus casting.json wiederverwendet (--neu fuer neue).")
    else:
        sb = steckbriefe_erzeugen(data)
        with open(cp, "w", encoding="utf-8") as f:   # sofort sichern (LLM-Kosten)
            json.dump({"werk": book_id, "datum": time.strftime("%Y-%m-%d %H:%M"), "quelle": pfad,
                       "tor": "offen", "steckbriefe": sb, "plan": None}, f, ensure_ascii=False, indent=1)
    reg = vr.laden()
    print(f"[stage57] Archiv: {len(vr.verfuegbar(reg))} nutzbare Stimmen, {vr.belegte_plaetze(reg)}/{vr.MAX_STIMMEN} Plaetze")
    print(f"[stage57] {len(sb.get('figuren', []))} sprechende Figuren erkannt. Besetze ({'mit' if design else 'ohne'} Design) ...")
    plan = besetzen(book_id, data, sb, design=design)
    out = {"werk": book_id, "datum": time.strftime("%Y-%m-%d %H:%M"), "quelle": pfad,
           "tor": "offen", "steckbriefe": sb, "plan": plan}
    with open(cp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    _zusammenfassung(plan)
    print(f"[stage57] Geschrieben: {cp}")
    return out


def _zusammenfassung(plan):
    e = plan["erzaehler"]
    print("\n  ROLLE                      STIMME                      QUELLE        PASSUNG")
    print(f"  {'Erzaehler':26} {str(e.get('stimme')):27} {e.get('quelle'):13} {e.get('passung', '')}")
    for r in plan["ensemble"]:
        pas = r.get("passung", r.get("passung_bestes_archiv", ""))
        tr = " ".join(f"{lg}:{t['status']}(D {t['D']})" for lg, t in (r.get("trennung") or {}).items())
        print(f"  {str(r['figur'])[:26]:26} {str(r.get('stimme')):27} {r.get('quelle'):13} {pas}  {tr}"
              + (f"  !! {r['pruefen']}" if r.get("pruefen") else "")
              + (f"  -> Korrektur {r['korrektur']}" if r.get("korrektur") else ""))
    print(f"  Statisten mit Erzaehlerstimme: {', '.join(s['figur'] for s in plan['statisten']) or '-'}\n")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    bid = args[0]
    opt = lambda k: args[args.index(k) + 1] if k in args and args.index(k) + 1 < len(args) else None
    if "--freigeben" in args:
        freigeben(bid)
    elif "--trennung" in args:
        trennung_pruefen(bid, ueberschreiben="--neu" in args)
    else:
        run(bid, design="--design" in args, neu="--neu" in args, quelle=opt("--quelle"))
