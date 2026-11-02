"""STAGE 210 — Profil (Umbau Phase 2, GATE_KATALOG.md Zeile 210, 02.11.2026)
Funktion:     Buchprofil: Stil (+ voice_note), Figuren (Uebersetzung je Zielsprache, Aussprache), Unuebersetztes,
              Glossar je Zielsprache, Redewendungen. Haengt unter meta.profile, Content bleibt unberuehrt.
Wirkungsweise: Ganzer Text in einem DeepSeek-Aufruf (config.MODELS profiler). Rohantwort als Checkpoint
              work/ckpt/210/profil__-.json (Eingang = Quelltext + Zielsprachen + Grenzen); Neulauf ohne Aenderung 0 $.
              Danach kostenlos: Kappung, feste Eintraege aus book.json (glossar_fest, figuren_fest, voice_note_fest),
              Reihen-Erbe (reihen/<reihe>/reihe_profil.json, ab Teil 2 fest).
Eingang:      work/200_tagging.json; book.json (zielsprachen aus Bestellung, reihe/teil, feste Eintraege);
              ab Teil 2: reihen/<reihe>/reihe_profil.json.
Ausgabe:      work/210_profil.json (Format unveraendert fuer 300 ff.), work/210_pruefung.json (Figuren-Treffer,
              Kappung, Namensvarianten), reihen/<reihe>/reihe_profil.json (nach Freigabe: Teil 1 ganz, ab Teil 2 Neuzugaenge).
Gate:         5 Bereiche vorhanden, Glossar je bestellter Zielsprache (Stopp); Antwort nur gerettet -> 1x automatisch neu,
              dann Mensch; Figur < 2x im Text, Liste voll (Kappung), Werk > Grenzwert 195 (nicht abgelehnt) -> Mensch;
              Teil >= 2: Namensvariante (Aehnlichkeit >= 0,8 zu bekannter Figur) -> Mensch; Hoerspiel bestellt -> immer Mensch;
              Figuren ohne Aussprache -> Hinweis (an 400); Mock im Live-Lauf -> Stopp.
              Mensch-Freigabe bleibt bei unveraenderter Ausgabe (ausgabe_hash) gueltig.
Kosten:       deepseek-v4-pro, ein Aufruf je Werk (nur bei geaendertem Eingang oder --neu).
Regler:       --modell, --neu, --glossar BEGRIFF:lg=WERT[,lg=WERT], --glossar-weg BEGRIFF,
              --figur NAME:feld=WERT[,feld=WERT] (feld = Zielsprache, pronunciation, tts_<lg>), --figur-weg NAME,
              --voice-note TEXT, --grenze bereich=N (characters/untranslated/glossary/idioms), --ohne-reihe / --mit-reihe,
              --uebernehmen (vorhandene 210_profil.json als Rohergebnis, ohne LLM),
              --trocken (Probe am Bestand: nutzt vorhandene 210_profil.json, schreibt nichts, kein LLM).
Aufruf:
  python -m pipeline.s210_profil <werk> [Regler] [--wer CK]
Exit: 0 auto, 2 Stopp, 3 Mensch, 1 Fehler.
"""

import argparse
import copy
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import api_layer, bestellung, gate, manifest, mock, status

STAGE = "210"
BEREICHE = ("style", "characters", "untranslated", "glossary", "idioms")
GRENZEN = {"characters": 40, "untranslated": 25, "glossary": 60, "idioms": 40}
FIGUR_MIN = 2
AEHNLICH = 0.8


# ============================================================
# QUELLTEXT EINSAMMELN
# ============================================================

def _collect_source_text(data: dict, src=None) -> str:
    """Alle Quelltext-Knoten (ohne p/skip/tt) als zusammenhaengender Text."""
    src = src or data.get("meta", {}).get("source_language") or config.SOURCE_LANGUAGE
    parts = []
    for _tid, entry in data["content"].items():
        if entry.get("type") in config.NO_AUDIO_TYPES:
            continue
        text = (entry.get(src) or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts)


# ============================================================
# PROFILER-PROMPT
# ============================================================

def _build_profiler_prompt(data: dict, source_text: str, src=None, ziele=None, grenzen=None) -> str:
    src = src or config.SOURCE_LANGUAGE
    ziele = list(ziele or config.TARGET_LANGUAGES)
    grenzen = grenzen or GRENZEN
    title = data["meta"].get("title", "")
    author = data["meta"].get("author", "")
    if ziele:
        z_fig = "".join(f'\n      "{l}": "<rendering in {l} or same if kept>",' for l in ziele)
        z_tts = "".join(f'\n      "tts_{l}": "<respelling so a {l} text-to-speech voice says the KEPT name as in the original '
                        f'language; empty if a {l} reader would already say it right>",' for l in ziele)
        z_glo = ", ".join(f'"{l}": "<translation>"' for l in ziele)
        z_idi = ", ".join(f'"{l}": "<idiomatic equivalent or neutral paraphrase>"' for l in ziele)
        sprachen = f"Source language: {src}. Target languages: {', '.join(ziele)}."
    else:
        z_fig = z_tts = z_glo = z_idi = ""
        sprachen = f"Source language: {src}. No translation (audiobook in the source language only)."

    return f"""You are a literary analyst preparing a translation and narration brief for a multilingual audiobook.

Analyze the following work and produce a profile as JSON.
{sprachen}

Return ONLY this JSON structure, nothing else:
{{
  "style": {{
    "tone": "<overall tone in a few words>",
    "register": "<e.g. literary, archaic, colloquial>",
    "setting": "<time period and place of the story, and the technological/social context of that era — e.g. 'London, 1880s; gas lamps, horse carriages, no telephones in daily use'>",
    "notes": "<any guidance a translator should keep in mind>",
    "voice_note": "<delivery hint for the AUDIOBOOK NARRATOR ONLY — how to read this work aloud. CONDITIONAL RULE: if the work's own style is already plain, sober or matter-of-fact, describe its natural delivery faithfully (1:1, no artificial flattening). ONLY if the style is ornate, archaic, florid, whimsical, grandiose or otherwise prone to over-acting, explicitly instruct RESTRAINT — so the narrator does NOT perform or exaggerate that style but carries it calmly and lets the words do the work. The goal is a natural modern audiobook reader, never a theatrical declaimer. A few words, e.g. plain work -> 'clear, steady narration'; florid work -> 'calm, even delivery; do not perform the ornate style, let the dry wit sit in the text'>"
  }},
  "characters": {{
    "<name exactly as written in the source>": {{{z_fig}
      "pronunciation": "<IPA>",{z_tts}
      "gender": "<m, f or n>"
    }}
  }},
  "untranslated": {{
    "<term to keep in original>": {{
      "meaning": "<short gloss>",
      "pronunciation": "<IPA or empty>"
    }}
  }},
  "glossary": {{
    "<source term>": {{ {z_glo} }}
  }},
  "idioms": {{
    "<source idiom>": {{
      "meaning": "<plain meaning>"{', ' + z_idi if z_idi else ''}
    }}
  }}
}}

Rules:
- Only include entries that genuinely occur in the text. Empty categories stay as {{}}.
- Character keys must be spelled exactly as they appear in the text (so they can be found again).
- Give an IPA pronunciation for every character.
- HARD LIMITS (the whole JSON must stay short): characters max {grenzen['characters']} (named, recurring figures only),
  untranslated max {grenzen['untranslated']}, glossary max {grenzen['glossary']} (only terms whose translation must stay
  consistent), idioms max {grenzen['idioms']}.
  Each key appears ONCE. Never repeat an entry, never list ordinary words. Stop when the limits are reached.
- For idioms, prefer an idiomatic equivalent; if none exists, give a neutral paraphrase.
- Decide per character whether the name is translated or kept; reflect that in the entry.

WORK TITLE: {title}
AUTHOR: {author}

--- TEXT START ---
{source_text}
--- TEXT END ---"""


# ============================================================
# MOCK-PROFIL (strukturtreu, leer)
# ============================================================

def _mock_profile(data: dict) -> dict:
    return {
        "style":        {"tone": "mock-tone", "register": "mock-register", "notes": "", "voice_note": "calm, even, understated narration"},
        "characters":   {},
        "untranslated": {},
        "glossary":     {},
        "idioms":       {},
    }


# ============================================================
# PROFILER (LLM)
# ============================================================

def _abgeschnitten_retten(raw: str) -> dict:
    """Abgeschnittenes JSON: an der letzten Stelle kappen, an der ein Objekt '}' vollstaendig endet,
    offene Klammern schliessen. Prueft von hinten bis zu 3000 Kandidaten."""
    s = raw[raw.find("{"):]
    ends = [i for i, c in enumerate(s) if c == "}"]
    for i in reversed(ends[-3000:]):
        teil = s[:i + 1]
        stapel, im_str, esc = [], False, False
        for c in teil:
            if im_str:
                if esc: esc = False
                elif c == "\\": esc = True
                elif c == '"': im_str = False
                continue
            if c == '"': im_str = True
            elif c in "{[": stapel.append(c)
            elif c in "}]" and stapel: stapel.pop()
        if im_str:
            continue
        zu = "".join("}" if c == "{" else "]" for c in reversed(stapel))
        try:
            return json.loads(teil.rstrip().rstrip(",") + zu)
        except Exception:
            continue
    raise ValueError("210: Profil nicht rettbar")


def profil_llm(data, src, ziele, grenzen, modell=None):
    """-> (profil roh, gerettet: bool, raw)."""
    if config.RUN_MODE == "mock":
        return _mock_profile(data), False, ""
    prompt = _build_profiler_prompt(data, _collect_source_text(data, src), src, ziele, grenzen)
    alt = config.MODELS.get("profiler")
    if modell:
        config.MODELS["profiler"] = modell
    try:
        raw = api_layer.call_model("profiler", prompt, max_tokens=24000)
    finally:
        config.MODELS["profiler"] = alt
    try:
        return api_layer.parse_json(raw), False, raw
    except ValueError:
        return _abgeschnitten_retten(raw), True, raw


def build_profile(data: dict) -> dict:
    """Altschnittstelle (ohne Gate)."""
    prof, _g, _r = profil_llm(data, config.SOURCE_LANGUAGE, config.TARGET_LANGUAGES, GRENZEN)
    return _kappen(prof, GRENZEN)[0]


def _kappen(prof: dict, grenzen) -> tuple:
    """Obergrenzen durchsetzen -> (profil, {bereich: anzahl vor Kappung} fuer volle Listen)."""
    voll = {}
    for k, n in grenzen.items():
        v = prof.get(k)
        if isinstance(v, dict) and len(v) >= n:
            voll[k] = len(v)
            prof[k] = dict(list(v.items())[:n])
    return prof, voll


# ============================================================
# NACHBEARBEITUNG (kostenlos)
# ============================================================

def feste_eintraege(prof, roh):
    """book.json: glossar_fest {begriff: {lg: wert} | null}, figuren_fest {name: {feld: wert} | null}, voice_note_fest."""
    for feld, bereich in (("glossar_fest", "glossary"), ("figuren_fest", "characters")):
        for k, v in (roh.get(feld) or {}).items():
            ziel = prof.setdefault(bereich, {})
            if v is None:
                ziel.pop(k, None)
            elif bereich == "characters" and k in ziel:
                ziel[k] = dict(ziel[k], **v)
            else:
                ziel[k] = v
    if roh.get("voice_note_fest"):
        prof.setdefault("style", {})["voice_note"] = roh["voice_note_fest"]
    return prof


def reihen_pfad(reihe):
    return os.path.join(config.BASE_DIR, "reihen", reihe, "reihe_profil.json")


def reihe_lesen(reihe):
    p = reihen_pfad(reihe)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def reihe_anwenden(prof, rp):
    """Reihen-Profil fest uebernehmen. -> (profil, neue Figuren, Namensvarianten [(neu, bekannt, aehnlichkeit)])."""
    bekannt = rp.get("characters") or {}
    neu = [n for n in (prof.get("characters") or {}) if n not in bekannt]
    varianten = []
    for n in neu:
        for b in bekannt:
            r = difflib.SequenceMatcher(None, n.lower(), b.lower()).ratio()
            if r >= AEHNLICH or n.lower() in b.lower().split() or b.lower() in n.lower().split():
                varianten.append((n, b, round(r, 2)))
    for bereich in ("characters", "untranslated", "glossary"):
        prof.setdefault(bereich, {}).update(copy.deepcopy(rp.get(bereich) or {}))
    if (rp.get("style") or {}).get("voice_note"):
        prof.setdefault("style", {})["voice_note"] = rp["style"]["voice_note"]
    return prof, neu, varianten


def reihe_schreiben(reihe, prof, teil, werk):
    """Teil 1: Profil anlegen; ab Teil 2: nur Neuzugaenge ergaenzen."""
    rp = reihe_lesen(reihe) or {"reihe": reihe, "teile": [], "characters": {}, "untranslated": {}, "glossary": {},
                                 "style": {}}
    neu = 0
    for bereich in ("characters", "untranslated", "glossary"):
        for k, v in (prof.get(bereich) or {}).items():
            if k not in rp[bereich]:
                rp[bereich][k] = v
                neu += 1
    if not (rp.get("style") or {}).get("voice_note") and (prof.get("style") or {}).get("voice_note"):
        rp.setdefault("style", {})["voice_note"] = prof["style"]["voice_note"]
    if werk not in rp["teile"]:
        rp["teile"].append(werk)
    os.makedirs(os.path.dirname(reihen_pfad(reihe)), exist_ok=True)
    manifest.json_atomar(reihen_pfad(reihe), rp, indent=1)
    return neu


TITEL = {"mr", "mrs", "ms", "miss", "dr", "sir", "lady", "lord", "king", "queen", "prince", "princess", "professor",
         "mme", "mlle", "monsieur", "madame", "captain", "uncle", "aunt", "herr", "frau", "the", "der", "die", "das", "st"}


def _varianten(name):
    """'Rosalind (Ros)' -> Rosalind (Ros), Rosalind, Ros; 'The Cheshire Cat' -> Cheshire Cat;
    'Mr. Gideon Ashworth' -> Gideon Ashworth, Gideon, Ashworth (Vor-/Nachname ohne Titel)."""
    out = [name]
    m = re.match(r"^(.*?)\s*\((.*?)\)\s*$", name)
    if m:
        out += [m.group(1).strip(), m.group(2).strip()]
    for v in list(out):
        w = v.replace(",", " ").split()
        while w and w[0].lower().rstrip(".") in TITEL:
            w = w[1:]
        if w and len(w) < len(v.split()):
            out.append(" ".join(w))
        namen = [x for x in w if x[:1].isupper() and len(x) > 2 and x.lower().rstrip(".") not in TITEL]
        if len(namen) >= 2:
            out += [namen[0], namen[-1]]
    return list(dict.fromkeys(v for v in out if v))


def figur_treffer(name, text):
    """Vorkommen im Text (Varianten; Grossschreibung egal bei Rollennamen in Versalien)."""
    best = 0
    for v in _varianten(name):
        flags = re.I if v.isupper() else 0
        best = max(best, len(re.findall(r"(?<!\w)" + re.escape(v) + r"(?!\w)", text, flags)))
    return best


def _teilung_abgelehnt(werk):
    p = os.path.join(config.work_dir(werk), "195_teilung.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f).get("entscheidung") == "abgelehnt"
    except (OSError, ValueError):
        return False


# ============================================================
# LAUF
# ============================================================

def _parse_kv(s):
    """'de=Peter,pronunciation=x' -> dict"""
    out = {}
    for teil in s.split(","):
        if "=" not in teil:
            raise ValueError(f"Feld ohne '=': {teil!r}")
        k, v = teil.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def regler_schreiben(werk, b, glossar=None, glossar_weg=None, figur=None, figur_weg=None, voice_note=None,
                     reihe_erbe=None):
    felder = {}
    if glossar or glossar_weg:
        g = dict(b.roh.get("glossar_fest") or {})
        for x in glossar or []:
            k, v = x.split(":", 1)
            g[k.strip()] = dict(g.get(k.strip()) or {}, **_parse_kv(v))
        for k in glossar_weg or []:
            g[k] = None
        felder["glossar_fest"] = g
    if figur or figur_weg:
        f = dict(b.roh.get("figuren_fest") or {})
        for x in figur or []:
            k, v = x.split(":", 1)
            f[k.strip()] = dict(f.get(k.strip()) or {}, **_parse_kv(v))
        for k in figur_weg or []:
            f[k] = None
        felder["figuren_fest"] = f
    if voice_note is not None:
        felder["voice_note_fest"] = voice_note or None
    if reihe_erbe is not None:
        felder["reihe_erbe"] = reihe_erbe
    if felder:
        bestellung.feld_setzen(werk, **felder)
    return bool(felder)


def run(werk, wer=None, modell=None, neu=False, glossar=None, glossar_weg=None, figur=None, figur_weg=None,
        voice_note=None, grenze=None, reihe_erbe=None, trocken=False, uebernehmen=False):
    wer = wer or "pipeline"
    g = gate.Gate(werk, STAGE, ruecksprung="210", wer=wer)
    d = status.laden(werk)
    if not trocken:
        regler_schreiben(werk, bestellung.lesen(werk), glossar, glossar_weg, figur, figur_weg, voice_note, reihe_erbe)
    b = bestellung.lesen(werk)
    src = b.quellsprache or config.SOURCE_LANGUAGE
    ziele = [z for z in (b.zielsprachen or []) if z != src]
    grenzen = dict(GRENZEN, **{k: int(v) for k, v in (grenze or {}).items()})
    g.metrik("zielsprachen", ziele)

    ip = config.work_path(werk, "200_tagging")
    if not g.pflicht("tagging", os.path.exists(ip), ruecksprung="200", text="200_tagging.json vorhanden"):
        g.entscheide(schreiben=not trocken)
        return g
    with open(ip, encoding="utf-8") as f:
        data = json.load(f)
    data.get("meta", {}).pop("profile", None)
    text = _collect_source_text(data, src)
    g.metrik("zeichen", len(text))

    # LLM (Checkpoint) bzw. Bestand
    ck = manifest.Checkpoint(werk, STAGE)
    h = manifest.hash_obj([text, ziele, grenzen])
    modell_eff = modell or config.MODELS.get("profiler")
    gerettet, n_llm = False, 0
    if trocken:
        op = config.work_path(werk, "210_profil")
        if not os.path.exists(op):
            g.pflicht("profil_vorhanden", False, text="210_profil.json fehlt (Probe ohne LLM)")
            g.entscheide(schreiben=False)
            return g
        with open(op, encoding="utf-8") as f:
            roh = (json.load(f).get("meta") or {}).get("profile") or {}
        herkunft = "bestand"
    else:
        daten = None if neu else ck.lesen("profil", None, h)
        herkunft = "checkpoint"
        op = config.work_path(werk, "210_profil")
        if daten is None and uebernehmen and not neu and os.path.exists(op):
            with open(op, encoding="utf-8") as f:
                alt_prof = (json.load(f).get("meta") or {}).get("profile")
            if alt_prof:
                daten = {"profil": alt_prof, "gerettet": False, "modell": "bestand"}
                ck.schreiben("profil", None, h, daten)
                herkunft = "bestand"
        if daten is None:
            roh, gerettet, _raw = profil_llm(data, src, ziele, grenzen, modell)
            n_llm += 1
            if gerettet:            # 1x automatisch neu
                roh2, ger2, _raw2 = profil_llm(data, src, ziele, grenzen, modell)
                n_llm += 1
                if not ger2 or len(json.dumps(roh2)) > len(json.dumps(roh)):
                    roh, gerettet = roh2, ger2
            daten = {"profil": roh, "gerettet": gerettet, "modell": modell_eff}
            ck.schreiben("profil", None, h, daten)
            herkunft = "neu"
        roh, gerettet = daten["profil"], daten.get("gerettet", False)
    g.metrik("llm_aufrufe", n_llm)
    g.metrik("herkunft", herkunft)
    g.metrik("modell", modell_eff)

    prof = copy.deepcopy(roh) if isinstance(roh, dict) else {}
    prof, voll = _kappen(prof, grenzen)
    prof = feste_eintraege(prof, b.roh)

    # Reihen-Erbe
    reihe, teil = b.roh.get("reihe"), int(b.roh.get("teil") or 0)
    erbe = bool(reihe) and b.roh.get("reihe_erbe", True) is not False
    neue_fig, varianten = [], []
    if erbe and teil >= 2:
        rp = reihe_lesen(reihe)
        g.pflicht("reihe_profil", rp is not None, ruecksprung="210",
                  text=f"Reihen-Profil {reihe} vorhanden (aus Teil 1)" if rp else f"Reihen-Profil {reihe} fehlt -> Teil 1 zuerst")
        if rp:
            prof, neue_fig, varianten = reihe_anwenden(prof, rp)
            g.metrik("neue_figuren", len(neue_fig))

    # Pruefungen
    fehlt = [k for k in BEREICHE if not isinstance(prof.get(k), dict)]
    g.pflicht("bereiche", not fehlt, wert=fehlt or None, text="5 Bereiche vorhanden" + (f", fehlt: {fehlt}" if fehlt else ""))
    glo_luecke = [k for k, v in (prof.get("glossary") or {}).items()
                  if not isinstance(v, dict) or any(not (v.get(z) or "").strip() for z in ziele)]
    g.pflicht("glossar_sprachen", not glo_luecke, wert=len(glo_luecke),
              text=f"Glossar je Zielsprache {ziele}: Luecken {len(glo_luecke)}" + (f" {glo_luecke[:5]}" if glo_luecke else ""))
    g.pruefe("vollstaendig", not gerettet, wert=gerettet, schwelle="nicht gerettet", bei_fehler="mensch",
             text="Antwort vollstaendig" if not gerettet else "Antwort abgeschnitten, nur gerettet (auch nach Wiederholung)")
    figuren = prof.get("characters") or {}
    treffer = {n: figur_treffer(n, text) for n in figuren}
    selten = {n: t for n, t in treffer.items() if t < FIGUR_MIN}
    g.pruefe("figuren_im_text", not selten, wert=len(selten), schwelle=f">= {FIGUR_MIN}x", bei_fehler="mensch",
             text=f"Figuren im Text >= {FIGUR_MIN}x" + (f"; seltener: {list(selten.items())[:8]}" if selten else ""))
    g.pruefe("kappung", not voll, wert=voll or None, schwelle="keine Liste voll", bei_fehler="mensch",
             text="Listen unter Grenze" if not voll else f"Liste voll (gekappt): {voll} -> --grenze")
    ohne_ausspr = [n for n, v in figuren.items() if not (isinstance(v, dict) and (v.get("pronunciation") or "").strip())]
    g.hinweis("aussprache", not ohne_ausspr, wert=len(ohne_ausspr),
              text=f"Figuren ohne Aussprache: {len(ohne_ausspr)}" + (f" {ohne_ausspr[:5]}" if ohne_ausspr else "") + " (an 400)")
    from pipeline import s195_teilung
    zu_lang = len(text) > s195_teilung.GRENZE and not b.roh.get("geteilt_in")
    if zu_lang and _teilung_abgelehnt(werk):
        g.hinweis("werk_laenge", False, wert=len(text), text=f"Werk {len(text):,} Zeichen > Grenzwert, Teilung abgelehnt")
    else:
        g.pruefe("werk_laenge", not zu_lang, wert=len(text), schwelle=f"<= {s195_teilung.GRENZE}", bei_fehler="mensch",
                 ruecksprung="195", text=f"Werk {len(text):,} Zeichen" + (" > Grenzwert 195" if zu_lang else ""))
    if erbe and teil >= 2:
        g.pruefe("namensvarianten", not varianten, wert=len(varianten), schwelle=f"Aehnlichkeit < {AEHNLICH}",
                 bei_fehler="mensch", text="Namensvarianten zur Reihe: " +
                 (", ".join(f"{a} ~ {c} ({r})" for a, c, r in varianten[:6]) + " -> gleiche oder neue Figur? (--figur / --figur-weg)"
                  if varianten else "keine"))
        g.hinweis("neue_figuren", True, wert=len(neue_fig), text=f"neue Figuren ggue. Reihe: {neue_fig[:8]}")
    g.mock(1 if mock.ist_obj(roh) else 0, ruecksprung="210")
    hoerspiel = bool(b.produkte_fuer(inhalt="hoerspiel"))
    g.metrik("figuren", len(figuren))
    for k in BEREICHE[1:]:
        g.metrik(k, len(prof.get(k) or {}))

    data["meta"]["profile"] = prof
    data["meta"]["profil_info"] = {"modell": modell_eff, "eingang": h, "herkunft": herkunft}
    aus_hash = manifest.hash_obj(prof)
    g.metrik("ausgabe_hash", aus_hash)
    st = d["stages"].get(STAGE) or {}
    freigegeben = st.get("zustand") == "frei" and (st.get("gate") or {}).get("ergebnis") == "mensch" \
        and (st.get("metriken") or {}).get("ausgabe_hash") == aus_hash
    if freigegeben:
        for p in g.pruefungen:
            if not p["ok"] and p["bei_fehler"] == "mensch":
                p["bei_fehler"] = "hinweis"
                p["text"] += " [Mensch-Freigabe gilt, Ausgabe unveraendert]"
    pruef = {"treffer": treffer, "voll": voll, "ohne_aussprache": ohne_ausspr,
             "neue_figuren": neue_fig, "varianten": varianten}
    if not trocken:
        manifest.json_atomar(config.work_path(werk, "210_profil"), data, indent=2)
        manifest.json_atomar(os.path.join(config.work_dir(werk), "210_pruefung.json"), pruef, indent=1)
    e = g.entscheide(mensch_immer=hoerspiel and not freigegeben,
                     mensch_grund="Hoerspiel bestellt: Figurenliste pruefen (steuert Casting 410)",
                     schreiben=not trocken)
    if e == "auto" and erbe and not trocken and teil >= 1:
        g.metrik("reihe_neu", reihe_schreiben(reihe, prof, teil, werk))
    g.pruef = pruef
    return g


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 210 Profil")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--modell")
    ap.add_argument("--neu", action="store_true", help="Profil neu erzeugen (LLM), auch wenn Eingang unveraendert")
    ap.add_argument("--glossar", action="append", metavar="BEGRIFF:lg=WERT", help="fester Glossar-Eintrag (book.json glossar_fest)")
    ap.add_argument("--glossar-weg", action="append", metavar="BEGRIFF")
    ap.add_argument("--figur", action="append", metavar="NAME:feld=WERT", help="Figur fest setzen/korrigieren (figuren_fest)")
    ap.add_argument("--figur-weg", action="append", metavar="NAME")
    ap.add_argument("--voice-note", help="voice_note fest ('' = wieder aus dem Profil)")
    ap.add_argument("--grenze", action="append", metavar="BEREICH=N", help="Listengrenze (characters/untranslated/glossary/idioms)")
    ap.add_argument("--ohne-reihe", action="store_true", help="Reihen-Erbe fuer diesen Teil abschalten")
    ap.add_argument("--mit-reihe", action="store_true", help="Reihen-Erbe wieder einschalten")
    ap.add_argument("--uebernehmen", action="store_true", help="vorhandene 210_profil.json als Rohergebnis nutzen (ohne LLM)")
    ap.add_argument("--trocken", action="store_true", help="Probe: vorhandenes Profil pruefen, nichts schreiben, kein LLM")
    a = ap.parse_args(argv)
    grenze = dict(x.split("=", 1) for x in a.grenze or [])
    erbe = False if a.ohne_reihe else (True if a.mit_reihe else None)
    try:
        g = run(a.werk, a.wer, a.modell, a.neu, a.glossar, a.glossar_weg, a.figur, a.figur_weg, a.voice_note,
                grenze, erbe, a.trocken, a.uebernehmen)
    except gate.GateHalt as e:
        print(e)
        return e.exit_code
    except ValueError as e:
        print(f"[210] Fehler: {e}")
        return 1
    print(g.bericht())
    return gate.EXIT[g.ergebnis["ergebnis"]]


if __name__ == "__main__":
    sys.exit(main())
