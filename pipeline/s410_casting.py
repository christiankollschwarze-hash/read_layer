"""STAGE 410 — Casting (Phase 2, 02.11.2026)
Funktion:     Besetzt je Audiosprache × Stufe den Erzaehler (jedes Hoerbuch) und bei Hoerspiel das Figuren-Ensemble.
              Einzige Ablage work/casting.json (Stimme, Gemini-ID bzw. Chatterbox-Referenz, Modell, LoRA-Adapter,
              Trennung/Korrektur je Rolle × Sprache); book.json haelt nur den Verweis "casting".
Komponenten:  pipeline/s410_casting.py, voice_registry (Archiv, Passung, Design), trennung (Abstand D, Korrektur)
Zulieferer:   s400 Regie (work/400_regie.json, Gate 400 frei), Profil 210 (meta.profile.characters, style.voice_note),
              stimmen_archiv, reihen/<reihe>/reihe_casting.json, Bestellung 095 (Sprache × Inhalt × Stufe)
Abnehmer:     s420, s500/502 (Stimme), s510, s540 (Korrekturstufe), s615 (Sprecherzeile), s640 (Teaser-Erzaehler),
              s650/s710 (Metadaten)
Kosten:       usage_log Stage 410: Steckbriefe 1 LLM-Aufruf (MODELS caster, deepseek-v4-pro), wiederverwendet bei
              gleichem Eingang; Voice Design (Stueckpreis) nur mit --design.

Engine aus Stufe: basic → Chatterbox (Referenz-Audio klon_<lg> + freigegebener LoRA-Adapter aus config.LORA_ADAPTER),
premium/drama → Gemini (Archiv-Design-ID oder Standardstimme). Teaser-Erzaehler (640) auch fuer TÆLLA-Sprachen ohne
Audio, sobald Audio bestellt ist.
Erzaehler: Vorgabe (Regler/Altfeld) > Bestand > Reihe > Genre > Archiv (Passung ≥ Schwelle) > Design (--design).
Ensemble (nur Hoerspiel): Figuren aus 210 (LLM ergaenzt nur Stimm-Merkmale, Gewicht, Dialoganteil); eigene Stimme bei
Gewicht haupt/neben und Anteil ≥ min_anteil, max. max_ensemble; Rest Statisten (Erzaehler).

Gate 410 je Rolle × Sprache: Erzaehler besetzt, Stimme fuer Stufe nutzbar, Adapter freigegeben, Ensemble-Sperre,
Reihenstimme reproduzierbar, Archiv ≤ 200, Gate 400 frei → sonst Stopp; Ensemble-Figur unbesetzt, Grundton-Abstand
Figur↔Figur < 12 %, D zu nah, neu designte Stimme, Steckbrief nur gerettet (nach 1× neu) → Mensch; Hoerspiel → immer
Mensch; Passung < Schwelle bei Vorgabe, D knapp (Korrektur vorgeschlagen), Figuren 210 ohne Steckbrief → Hinweis.
Mensch-Freigabe gilt, solange ausgabe_hash gleich bleibt. Freigegebenes Casting nur mit --neu --grund ueberschreibbar
(Protokoll); Korrekturstufe (540) per korrektur_setzen ohne --neu, mit Protokoll.

CLI: py -3.11 -m pipeline.s410_casting <werk> [--design] [--neu [--grund TEXT]] [--neu-steckbriefe]
     [--erzaehler [LG=]STIMME] [--figur NAME=STIMME] [--figur-weg NAME] [--statist NAME] [--statist-weg NAME]
     [--design-prompt NAME=TEXT] [--schwelle 70] [--f0-abstand 0.12] [--max-ensemble 15] [--min-anteil 2]
     [--modell M] [--ohne-reihe | --mit-reihe] [--korrektur FIGUR:LG=FAKTOR[,HT]] [--freigeben --grund TEXT]
     [--trocken] [--wer CK]
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import api_layer, bestellung, gate, manifest, mock, status, usage_log
from pipeline import voice_registry as vr
from pipeline import trennung

STAGE = "410"
SCHEMA = 2
PROMPT_V = 2
ENGINE = {"basic": "chatterbox", "premium": "gemini", "drama": "gemini"}
AUDIO = ("hoerbuch", "hoerspiel")
CB_STANDARD = "chatterbox-standard"
HOERBUCH_TEXT = 30_000
GENRE_ERZAEHLER = getattr(config, "CASTING_GENRE_ERZAEHLER", {
    "maerchen": "grossmutter_a", "abenteuer": "herr_a", "krimi": "herr_a", "grosses_werk": "herr_b"})
REGLER_STD = {"erzaehler": {}, "figuren": {}, "statisten": [], "design_prompt": {},
              "schwelle": getattr(config, "CASTING_SCHWELLE", 70),
              "f0_abstand": getattr(config, "CASTING_MIN_F0_ABSTAND", 0.12),
              "max_ensemble": getattr(config, "CASTING_MAX_ENSEMBLE", 15),
              "min_anteil": getattr(config, "CASTING_MIN_ANTEIL", 2.0),
              "max_text": getattr(config, "CASTING_MAX_ZEICHEN", 400_000),
              "modell": None, "reihe_erbe": True}
LANG_NAME = {"en": "English", "de": "German", "fr": "French", "es": "Spanish", "it": "Italian"}


# ============================================================ Ablage
def casting_pfad(book_id):
    return os.path.join(config.work_dir(book_id), "casting.json")


def laden(werk):
    p = casting_pfad(werk)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def reihe_pfad(reihe):
    return os.path.join(config.BASE_DIR, "reihen", reihe, "reihe_casting.json")


def _reihe_lesen(reihe):
    p = reihe_pfad(reihe) if reihe else None
    if not p or not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def kern(rollen):
    """Was eine Freigabe bindet: Stimme, Gemini-ID, Referenz, Adapter je Rolle (ohne Korrektur/Messwerte)."""
    out = {}
    for lg, je in sorted((rollen or {}).items()):
        for st, bs in sorted(je.items()):
            r = [bs.get("erzaehler") or {}] + list(bs.get("ensemble") or [])
            out[f"{lg}/{st}"] = {"adapter": bs.get("adapter"),
                                 "rollen": [[x.get("figur"), x.get("stimme"), x.get("gemini_id"), x.get("referenz")]
                                            for x in r],
                                 "statisten": sorted(s.get("figur") or "" for s in bs.get("statisten") or [])}
    return manifest.hash_obj(out)


def freigegeben(c):
    return bool(c and c.get("schema") == SCHEMA and (c.get("freigabe") or {}).get("hash") == kern(c.get("rollen")))


def aktiv(book_id) -> bool:
    try:
        return bool(bestellung.lesen(book_id).audiosprachen())
    except Exception:
        return False


def stimme(werk, lg, figur=None, stufe=None, nur_freigegeben=True):
    """Archivname der Stimme (Erzaehler bzw. Figur; Statist → Erzaehler) aus casting.json, sonst None."""
    c = laden(werk)
    if not c or c.get("schema") != SCHEMA or (nur_freigegeben and not freigegeben(c)):
        return None
    je = (c.get("rollen") or {}).get(lg) or {}
    if not je:
        return None
    bs = je.get(stufe) if stufe else je[sorted(je)[0]]
    if not bs:
        return None
    if figur:
        for e in bs.get("ensemble") or []:
            if e.get("figur") == figur:
                return e.get("stimme")
    return (bs.get("erzaehler") or {}).get("stimme")


# ============================================================ Stimmen
def _standard():
    p = os.path.join(vr.STIMMEN_DIR, "_gemini_standard", "standard.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _stimm_daten(name, reg, std):
    """(merkmale, grundton, status) einer Archiv-, Standard- oder Chatterbox-Standardstimme."""
    if name in reg:
        s = reg[name]
        return vr.normalisieren(s.get("merkmale")), s.get("grundton_hz"), s.get("status")
    if name in std:
        return vr.normalisieren({"geschlecht": std[name].get("geschlecht")}), std[name].get("grundton_hz"), "standard"
    if name == CB_STANDARD:
        return {}, None, "standard"
    return {}, None, None


def nutzbar(name, lg, engine, reg=None, std=None):
    """-> (ok, info, grund). Gemini: Design-ID bzw. Standardname; Chatterbox: Referenz-Audio der Sprache."""
    from pipeline import legacy_tor
    reg = vr.laden() if reg is None else reg
    std = _standard() if std is None else std
    _, _, st = _stimm_daten(name, reg, std)
    if st is None:
        return False, {}, f"{name} nicht im Archiv"
    if st == "abgelehnt":
        return False, {}, f"{name} im Archiv abgelehnt"
    if engine == "gemini":
        vid = (reg.get(name) or {}).get("id") or legacy_tor.gemini_voice(name)
        if not vid:
            return False, {}, f"{name} ohne Gemini-ID"
        return True, {"gemini_id": vid, "modell": config.MODELS.get("tts", "")}, ""
    if name == CB_STANDARD:
        return True, {"referenz": None, "modell": "chatterbox"}, ""
    ref = legacy_tor.ref_clip(name, lg)
    if not ref:
        return False, {}, f"{name} ohne Referenz-Audio fuer {lg}"
    return True, {"referenz": os.path.relpath(ref, config.BASE_DIR).replace(os.sep, "/"), "modell": "chatterbox"}, ""


def adapter(roh, lg):
    """LoRA-Adapter fuer Chatterbox: book.json tts_lora (str | {lg}) > config.TTS_LORA; 'aus' = keiner.
    -> (info | None, ok, grund)."""
    t = roh.get("tts_lora")
    name = (t.get(lg) if isinstance(t, dict) else t) if t else getattr(config, "TTS_LORA", {}).get(lg)
    if not name or name == "aus":
        return None, True, ""
    reg = getattr(config, "LORA_ADAPTER", {}) or {}
    a = reg.get(name)
    if not a:
        return {"name": name}, False, f"Adapter {name} nicht registriert (config.LORA_ADAPTER)"
    info = {"name": name, "version": a.get("version")}
    if not a.get("freigegeben"):
        return info, False, f"Adapter {name} v{a.get('version')} nicht freigegeben"
    if a.get("datei") and not os.path.exists(os.path.join(config.BASE_DIR, a["datei"])):
        return info, False, f"Adapter {name}: Datei {a['datei']} fehlt"
    return info, True, ""


# ============================================================ Steckbriefe
def _text(data, src, grenze, mit_ids):
    zeilen, dl = [], 0
    for tid, e in (data.get("content") or {}).items():
        if e.get("type") in config.NO_AUDIO_TYPES:
            continue
        t = (e.get(src) or "").strip()
        if not t:
            continue
        if e.get("type") == "dl" and mit_ids:
            dl += 1
            zeilen.append(f"[{tid}] {e['sprecher']}: {t}" if e.get("sprecher") else f"[{tid}] {t}")
        else:
            zeilen.append(t)
    text = "\n".join(zeilen)
    gekuerzt = len(text) > grenze
    return (text[:grenze] + "\n[... gekuerzt ...]" if gekuerzt else text), dl, gekuerzt


def _prompt(titel, autor, src, sprachen, text, n_dl, figuren, voice_note, hoerspiel):
    alle = lambda xs: " | ".join(xs)
    schema = f"""{{
  "geschlecht": "w | m | neutral",
  "alter": "kind | jung | mittel | alt | greis",
  "tonlage": "hoch | mittel | tief",
  "klangfarbe": [one or more of: {alle(vr.KLANGFARBEN)}],
  "tempo": "langsam | mittel | schnell",
  "temperament": [one or more of: {alle(vr.TEMPERAMENTE)}],
  "sicherheit": "unsicher | neutral | fest",
  "akzent": "<e.g. britisch, schottisch, amerikanisch, or empty>"
}}"""
    fig = ""
    if hoerspiel:
        fig = f""",
  "figuren": [
    {{
      "name": "<EXACTLY one name from the CHARACTER LIST>",
      "gewicht": "haupt | neben | statist",
      "dialog_anteil_prozent": <estimated share of all dialogue lines spoken by this character, number>,
      "merkmale": <schema>,
      "auffaelligkeiten": "<speech quirks, dialect ... or empty>",
      "unterscheiden_von": ["<names from the list that must sound clearly different>"],
      "beispiel_tag_ids": ["<1-3 ids of dialogue lines where this character speaks>"],
      "stimm_beschreibung_en": "<2-3 sentence voice design prompt: age, gender, pitch, timbre, pace, temperament>",
      "kurz": "<German summary in 5-8 words>"
    }}
  ]"""
    liste = ""
    if hoerspiel:
        liste = ("\nCHARACTER LIST (fixed, from the book profile; describe each one that speaks, use these names "
                 "exactly, add no others):\n" + "\n".join(f"- {n}" for n in figuren) + "\n")
    return f"""You are the casting director for an audiobook{' with a multi-voice ensemble' if hoerspiel else ''}.
Source language: {LANG_NAME.get(src, src)}. Audio languages: {', '.join(LANG_NAME.get(x, x) for x in sprachen)}.
Describe the NARRATOR{' and every CHARACTER of the list who speaks' if hoerspiel else ''} so that each can get a fitting voice.
{f'Dialogue lines are marked with their id in square brackets. There are {n_dl} dialogue lines.' if hoerspiel else ''}
Narrator delivery note from the book profile: {voice_note or '-'}
{liste}
Return ONLY this JSON, nothing else:
{{
  "erzaehler": {{
    "erzaehlform": "allwissend | ich",
    "ich_figur": "<{'name from the CHARACTER LIST' if hoerspiel else 'name of the narrating character'} if first-person narrator, else empty>",
    "genre_stimme": "maerchen | abenteuer | krimi | grosses_werk | anderes",
    "merkmale": <schema>,
    "stimm_beschreibung_en": "<2-3 sentence voice design prompt for the narrator>"
  }}{fig},
  "hinweise": "<anything a casting director should know, in German>"
}}

<schema> = {schema}

Rules:
- Use ONLY the listed values for the schema fields (German words without umlauts as given).
- Base everything on the text; where it says nothing about the voice, infer from age, role and behaviour.
- NEVER reference real actors, film or dubbing voices, or famous adaptations.
- Narrator genre: fairy tales / children's classics -> 'maerchen'; adventure -> 'abenteuer'; crime -> 'krimi';
  monumental literary novels -> 'grosses_werk'.

WORK: {titel} — {autor}

--- TEXT START ---
{text}
--- TEXT END ---"""


def _llm(prompt, modell=None):
    """-> (steckbriefe, gerettet)."""
    alt = config.MODELS.get("caster")
    if modell:
        config.MODELS["caster"] = modell
    try:
        roh = api_layer.call_model("caster", prompt, temperature=0.2, max_tokens=16000)
    finally:
        config.MODELS["caster"] = alt
    try:
        return api_layer.parse_json(roh), False
    except Exception:
        from pipeline.s210_profil import _abgeschnitten_retten
        try:
            return _abgeschnitten_retten(roh), True
        except Exception:
            return {}, True


def steckbriefe_mock(data, figuren, profil, src):
    """Mock-Lauf: deterministisch aus 210 (kein LLM). Anteil = Namensnennungen in Dialogzeilen."""
    dl = [(e.get(src) or "") for e in (data.get("content") or {}).values() if e.get("type") == "dl"]
    n = max(len(dl), 1)
    figs = []
    for name in figuren:
        k = sum(1 for t in dl if name.split()[0] in t)
        anteil = round(100 * k / n, 1)
        g = ((profil.get("characters") or {}).get(name) or {}).get("gender")
        figs.append({"name": name, "gewicht": "haupt" if anteil >= 10 else ("neben" if anteil >= 2 else "statist"),
                     "dialog_anteil_prozent": anteil, "merkmale": {"geschlecht": g or "neutral"},
                     "kurz": "[MOCK] Figur", "stimm_beschreibung_en": "[MOCK] voice"})
    return {"erzaehler": {"erzaehlform": "allwissend", "genre_stimme": "anderes",
                          "merkmale": {"geschlecht": "m", "alter": "alt", "tonlage": "tief", "klangfarbe": ["warm"],
                                       "temperament": ["ruhig"], "sicherheit": "fest"}},
            "figuren": figs, "hinweise": "[MOCK]", "_mock": True}


def _sb_norm(sb):
    for f in sb.get("figuren") or []:
        f["merkmale"] = vr.normalisieren(f.get("merkmale"))
    if sb.get("erzaehler"):
        sb["erzaehler"]["merkmale"] = vr.normalisieren(sb["erzaehler"].get("merkmale"))
    return sb


def _abgleich(sb, figuren):
    """LLM-Figuren auf 210-Namen abbilden. -> (je_name {210-name: steckbrief}, fremd [namen], fehlend [namen])."""
    if not figuren:
        return {f.get("name"): f for f in sb.get("figuren") or [] if f.get("name")}, [], []
    norm = {n.casefold(): n for n in figuren}
    je, fremd = {}, []
    for f in sb.get("figuren") or []:
        n = (f.get("name") or "").strip()
        z = norm.get(n.casefold()) or next((m for m in figuren if n and (n.casefold() in m.casefold()
                                                                         or m.casefold() in n.casefold())), None)
        if z and z not in je:
            je[z] = dict(f, name=z)
        elif n:
            fremd.append(n)
    return je, fremd, [n for n in figuren if n not in je]


# ============================================================ Besetzen
class _Ctx:
    def __init__(self, werk, data, roh, rg, sb, figuren_sb, ich, fest, reihe, design, src, std):
        self.werk, self.data, self.roh, self.rg, self.sb = werk, data, roh, rg, sb
        self.figuren_sb, self.ich, self.fest, self.reihe, self.design = figuren_sb, ich, fest, reihe, design
        self.src, self.std = src, std
        self.reg = vr.laden()
        self.neu, self.design_fehler = [], []
        self.werk_dir = config.book_dir(werk)
        self._erz = {}


def _profil_erz(ctx, lg, name):
    k = (lg, name)
    if k not in ctx._erz:
        try:
            ctx._erz[k] = trennung.erzaehler_profil(ctx.werk_dir, lg, name) or {}
        except Exception:
            ctx._erz[k] = {}
    return ctx._erz[k]


def _abstand(ctx, name, lg, erz_name, merk):
    try:
        ep = _profil_erz(ctx, lg, erz_name)
        fp = trennung.stimm_profil(name, lg) or {}
        t = trennung.abstand(fp, ep)
        k = trennung.korrektur_vorschlag(t["status"], trennung.richtung(merk, fp, ep)) \
            if t.get("status") in ("knapp", "zu_nah") else {}
        return t, k
    except Exception as e:
        return {"status": "unbekannt", "grund": type(e).__name__}, {}


def _rolle(ctx, rolle, figur, stimme_, quelle, lg, engine, merk, **extra):
    vm, f0, st = _stimm_daten(stimme_, ctx.reg, ctx.std)
    ok, info, grund = nutzbar(stimme_, lg, engine, ctx.reg, ctx.std)
    e = {"rolle": rolle, "figur": figur, "stimme": stimme_, "quelle": quelle,
         "passung": vr.passung(merk, vm) if vm and merk else None, "grundton_hz": f0, "archiv_status": st,
         "gemini_id": info.get("gemini_id"), "referenz": info.get("referenz"), "modell": info.get("modell"),
         "nutzbar": ok}
    if grund:
        e["grund"] = grund
    e.update({k: v for k, v in extra.items() if v is not None})
    return e


def _usable_reg(ctx, lg, engine):
    return {n: s for n, s in ctx.reg.items() if s.get("status") != "abgelehnt"
            and nutzbar(n, lg, engine, ctx.reg, ctx.std)[0]}


def _muster(ctx, profil):
    out = {}
    for lg in ctx.sprachen:
        for tid in profil.get("beispiel_tag_ids") or []:
            t = ((ctx.data.get("content") or {}).get(tid) or {}).get(lg)
            if t:
                out[lg] = t
                break
        if lg not in out:
            out[lg] = next((e.get(lg) for e in (ctx.data.get("content") or {}).values()
                            if e.get("type") == "s" and e.get(lg)), "")
    return out


def _designen(ctx, profil, rolle_typ, ensemble):
    """Gemini Voice Design (kostet). -> (name, eintrag) oder (None, None)."""
    if vr.belegte_plaetze(vr.laden()) >= vr.MAX_STIMMEN - 5:
        ctx.design_fehler.append(f"{profil.get('name')}: Archiv voll")
        return None, None
    figur = dict(profil, rolle_typ=rolle_typ)
    dp = (ctx.rg.get("design_prompt") or {}).get(profil.get("name"))
    if dp:
        figur["stimm_beschreibung_en"] = dp
    merk = dict(figur.get("merkmale") or {})
    for versuch in (1, 2):
        m = merk
        teile = [m.get("geschlecht", "n"), m.get("alter", "mittel"), m.get("tonlage", "mittel")] + (m.get("temperament") or [])[:1]
        name = vr.eindeutiger_name("_".join(teile), vr.laden())
        try:
            e = vr.neu_designen(name, dict(figur, merkmale=m), ensemble, _muster(ctx, profil), ctx.werk)
        except Exception as ex:
            ctx.design_fehler.append(f"{profil.get('name')}: {str(ex)[:160]}")
            figur["stimm_beschreibung_en"] = ""
            continue
        ok, grund, konflikt = vr.unterscheidbar(dict(e, name=name), ensemble)
        ctx.reg = vr.laden()
        if ok or versuch == 2:
            ctx.neu.append(name)
            return name, e
        reg = vr.laden()
        reg[name]["status"] = "abgelehnt"
        reg[name]["einsatz"] = f"automatisch verworfen: {grund}"
        vr.speichern(reg)
        eigen, fremd = e.get("grundton_hz") or 0, (konflikt or {}).get("grundton_hz") or 0
        merk = dict(merk, tonlage="hoch" if eigen >= fremd else "tief")
        figur["stimm_beschreibung_en"] = ""
    return None, None


def _fest(ctx, lg, st, figur=None):
    bs = ((ctx.fest or {}).get(lg) or {}).get(st) or {}
    if figur is None:
        return bs.get("erzaehler")
    return next((e for e in bs.get("ensemble") or [] if e.get("figur") == figur), None)


def _reihe(ctx, lg, st, figur=None):
    if not ctx.reihe or not ctx.rg.get("reihe_erbe", True):
        return None
    bs = ((ctx.reihe.get("rollen") or {}).get(lg) or {}).get(st) or {}
    if figur is None:
        return bs.get("erzaehler")
    return next((e for e in bs.get("ensemble") or [] if e.get("figur") == figur), None)


def _vorgabe_erz(ctx, lg):
    v = ctx.rg.get("erzaehler") or {}
    if v.get(lg) or v.get("*"):
        return v.get(lg) or v.get("*"), "vorgabe"
    alt = ctx.roh.get("stimme")
    alt = alt.get(lg) if isinstance(alt, dict) else alt
    alt = alt or ctx.roh.get("erzaehler_stimme")
    return (alt, "vorgabe_altfeld") if alt else (None, None)


def _erzaehler(ctx, lg, st, engine, gesperrt, ensemble):
    erz = ctx.sb.get("erzaehler") or {}
    ich = ctx.ich
    profil = dict(ctx.figuren_sb.get(ich) or erz, name=ich or "Erzaehler")
    merk = vr.normalisieren(profil.get("merkmale")) if profil.get("merkmale") else None
    figur = ich or "Erzaehler"
    name, quelle = _vorgabe_erz(ctx, lg)
    extra = {}
    if not name:
        f = _fest(ctx, lg, st)
        if f and f.get("stimme"):
            name, quelle = f["stimme"], f.get("quelle") or "bestand"
    if not name:
        r = _reihe(ctx, lg, st)
        if r and r.get("stimme"):
            name, quelle, extra = r["stimme"], "reihe", {"reihe_ref": {k: r.get(k) for k in ("gemini_id", "referenz")}}
    if not name and not ich:
        gn = GENRE_ERZAEHLER.get(erz.get("genre_stimme", ""))
        if gn and nutzbar(gn, lg, engine, ctx.reg, ctx.std)[0] and gn not in gesperrt:
            name, quelle = gn, "genre"
    if not name:
        pool = _usable_reg(ctx, lg, engine)
        for rt in ("erzaehler", None):
            n, _s, _sc = vr.beste_stimme(merk or vr.normalisieren({}), pool, gesperrt, ensemble, rt)
            if n:
                name, quelle = n, "archiv"
                break
    if not name and ctx.design:
        n, _e = _designen(ctx, profil, "erzaehler", ensemble)
        if n:
            name, quelle = n, "neu"
    if not name:
        return {"rolle": "erzaehler", "figur": figur, "stimme": None, "quelle": "unbesetzt", "nutzbar": False,
                "design_prompt": vr.design_prompt(dict(profil, rolle_typ="erzaehler"), ensemble)}
    return _rolle(ctx, "erzaehler", figur, name, quelle, lg, engine, merk, **extra)


def _ensemble(ctx, lg, st, engine, erz, gesperrt, ensemble):
    rg = ctx.rg
    rang = {"haupt": 0, "neben": 1, "statist": 2}
    figs = sorted(ctx.figuren_sb.values(),
                  key=lambda f: (rang.get(f.get("gewicht"), 2), -float(f.get("dialog_anteil_prozent") or 0)))
    out, statisten = [], []
    for f in figs:
        name_f = f.get("name")
        if ctx.ich and name_f == ctx.ich:
            continue
        anteil = float(f.get("dialog_anteil_prozent") or 0)
        vorgabe = (rg.get("figuren") or {}).get(name_f)
        bestand = (_fest(ctx, lg, st, name_f) or _reihe(ctx, lg, st, name_f) or {}).get("stimme")
        eigene = vorgabe or (bestand and name_f not in (rg.get("statisten") or [])) or (f.get("gewicht") in ("haupt", "neben") and anteil >= float(rg["min_anteil"])
                             and name_f not in (rg.get("statisten") or []) and len(out) < int(rg["max_ensemble"]))
        if not eigene:
            statisten.append({"figur": name_f, "gewicht": f.get("gewicht"), "anteil": anteil, "stimme": "erzaehler"})
            continue
        merk = vr.normalisieren(f.get("merkmale"))
        prof = ((ctx.data.get("meta") or {}).get("profile") or {}).get("characters") or {}
        name_lg = (prof.get(name_f) or {}).get(lg) or name_f
        meta = {"gewicht": f.get("gewicht"), "anteil": anteil, "kurz": f.get("kurz"), "name_lg": name_lg}
        stimme_, quelle, extra = None, None, {}
        fest = _fest(ctx, lg, st, name_f)
        if vorgabe:
            stimme_, quelle = vorgabe, "vorgabe"
        elif fest and fest.get("stimme"):
            stimme_, quelle = fest["stimme"], fest.get("quelle") or "bestand"
        else:
            r = _reihe(ctx, lg, st, name_f)
            if r and r.get("stimme"):
                stimme_, quelle = r["stimme"], "reihe"
                extra = {"reihe_ref": {k: r.get(k) for k in ("gemini_id", "referenz")}}
        if not stimme_:
            ep = _profil_erz(ctx, lg, erz.get("stimme")) if erz.get("stimme") else None
            pool = _usable_reg(ctx, lg, engine)
            try:
                n, _s, _sc = vr.beste_stimme(merk, pool, gesperrt, ensemble, "figur",
                                             erz_profil=ep if (ep or {}).get("f0_hz") else None, lg=lg)
            except Exception:
                n, _s, _sc = vr.beste_stimme(merk, pool, gesperrt, ensemble, "figur")
            if n:
                stimme_, quelle = n, "archiv"
        if not stimme_ and ctx.design:
            n, _e = _designen(ctx, f, "figur", ensemble)
            if n:
                stimme_, quelle = n, "neu"
        if not stimme_:
            out.append(dict({"rolle": "figur", "figur": name_f, "stimme": None, "quelle": "unbesetzt",
                             "nutzbar": False, "design_prompt": vr.design_prompt(f, ensemble)}, **meta))
            continue
        e = _rolle(ctx, "figur", name_f, stimme_, quelle, lg, engine, merk, **extra, **meta)
        ok_g, grund_g, _k = vr.unterscheidbar({"merkmale": _stimm_daten(stimme_, ctx.reg, ctx.std)[0],
                                               "grundton_hz": e.get("grundton_hz"), "name": stimme_}, ensemble)
        e["grundton_ok"] = ok_g
        if grund_g:
            e["grundton_grund"] = grund_g
        if erz.get("stimme"):
            t, k = _abstand(ctx, stimme_, lg, erz["stimme"], merk)
            e["trennung"] = t
            if fest and fest.get("korrektur"):
                e["korrektur"] = fest["korrektur"]
                e["korrektur_protokoll"] = fest.get("korrektur_protokoll")
            elif k:
                e["korrektur"] = k
        gesperrt.add(stimme_)
        ensemble.append({"name": stimme_, "merkmale": _stimm_daten(stimme_, ctx.reg, ctx.std)[0],
                         "grundton_hz": e.get("grundton_hz")})
        out.append(e)
    return out, statisten


def plan_bauen(ctx, ziele):
    """ziele: {lg: {stufe: [inhalte]}} -> rollen."""
    rollen = {}
    ctx.sprachen = sorted(ziele)
    for lg in sorted(ziele):
        for st, inhalte in sorted(ziele[lg].items()):
            engine = ENGINE[st]
            bs = {"stufe": st, "engine": engine, "inhalte": inhalte}
            if engine == "chatterbox":
                a, ok, grund = adapter(ctx.roh, lg)
                bs["adapter"] = a
                bs["adapter_ok"] = ok
                if grund:
                    bs["adapter_grund"] = grund
            gesperrt, ensemble = set(), []
            erz = _erzaehler(ctx, lg, st, engine, gesperrt, ensemble)
            if erz.get("stimme"):
                gesperrt.add(erz["stimme"])
                ensemble.append({"name": erz["stimme"], "merkmale": _stimm_daten(erz["stimme"], ctx.reg, ctx.std)[0],
                                 "grundton_hz": erz.get("grundton_hz")})
            bs["erzaehler"] = erz
            bs["ensemble"], bs["statisten"] = ([], [])
            if "hoerspiel" in inhalte:
                bs["ensemble"], bs["statisten"] = _ensemble(ctx, lg, st, engine, erz, gesperrt, ensemble)
            rollen.setdefault(lg, {})[st] = bs
    return rollen


# ============================================================ Altfassung (Schema 1)
def _fest_aus_v1(alt, ziele):
    plan = alt.get("plan") or {}
    erz = (plan.get("erzaehler") or {}).get("stimme")
    ens = {e.get("figur"): e for e in plan.get("ensemble") or [] if e.get("stimme")}
    fest = {}
    for lg, je in ziele.items():
        for st in je:
            fest.setdefault(lg, {})[st] = {
                "erzaehler": {"stimme": erz, "quelle": "uebernommen"} if erz else None,
                "ensemble": [{"figur": f, "stimme": e["stimme"], "quelle": "uebernommen",
                              "korrektur": (e.get("korrektur") or {}).get(lg)} for f, e in ens.items()]}
    return fest


def _plan_v1(rollen):
    """Kompatible Sicht fuer Altabnehmer (420/510/630/710, tools): plan.erzaehler/ensemble/statisten."""
    wahl = None
    for lg, je in sorted(rollen.items()):
        for st, bs in sorted(je.items()):
            if wahl is None or ("hoerspiel" in bs.get("inhalte", []) and "hoerspiel" not in wahl[2].get("inhalte", [])):
                wahl = (lg, st, bs)
    if not wahl:
        return None
    lg, st, bs = wahl
    e = bs.get("erzaehler") or {}
    ens = []
    for x in bs.get("ensemble") or []:
        korr, name_de = {}, None
        for lg2, je2 in rollen.items():
            for b2 in je2.values():
                for y in b2.get("ensemble") or []:
                    if y.get("figur") == x.get("figur"):
                        if y.get("korrektur"):
                            korr[lg2] = y["korrektur"]
                        if lg2 == "de":
                            name_de = y.get("name_lg")
        ens.append({"figur": x.get("figur"), "stimme": x.get("stimme"), "id": x.get("gemini_id"),
                    "name_de": name_de, "gewicht": x.get("gewicht"), "anteil": x.get("anteil"),
                    "kurz": x.get("kurz"), "korrektur": korr, "trennung": {lg: x.get("trennung")}})
    return {"sprache": lg, "stufe": st,
            "erzaehler": {"stimme": e.get("stimme"), "id": e.get("gemini_id"), "figur": e.get("figur"),
                          "quelle": e.get("quelle")},
            "ensemble": ens, "statisten": bs.get("statisten") or []}


# ============================================================ Regler
def _regler(roh):
    r = dict(REGLER_STD)
    r.update({k: v for k, v in (roh.get("casting_regler") or {}).items() if v is not None})
    for k in ("erzaehler", "figuren", "design_prompt"):
        r[k] = dict(r.get(k) or {})
    r["statisten"] = list(r.get("statisten") or [])
    return r


def regler_anwenden(rg, aend):
    """aend: erzaehler [..], figur [..], figur_weg, statist, statist_weg, design_prompt, Zahlen, modell, reihe_erbe."""
    rg = json.loads(json.dumps(rg))
    for x in aend.get("erzaehler") or []:
        lg, n = x.split("=", 1) if "=" in x else ("*", x)
        if n in ("", "-"):
            rg["erzaehler"].pop(lg, None)
        else:
            rg["erzaehler"][lg] = n
    for x in aend.get("figur") or []:
        f, n = x.split("=", 1)
        rg["figuren"][f] = n
    for f in aend.get("figur_weg") or []:
        rg["figuren"].pop(f, None)
    for f in aend.get("statist") or []:
        if f not in rg["statisten"]:
            rg["statisten"].append(f)
    for f in aend.get("statist_weg") or []:
        rg["statisten"] = [x for x in rg["statisten"] if x != f]
    for x in aend.get("design_prompt") or []:
        f, t = x.split("=", 1)
        rg["design_prompt"][f] = t
    for k in ("schwelle", "f0_abstand", "max_ensemble", "min_anteil", "max_text", "modell", "reihe_erbe"):
        if aend.get(k) is not None:
            rg[k] = aend[k]
    return rg


def _regler_gueltig(rg):
    try:
        return (0 <= float(rg["schwelle"]) <= 100 and 0 < float(rg["f0_abstand"]) < 1
                and 0 <= int(rg["max_ensemble"]) <= 40 and 0 <= float(rg["min_anteil"]) <= 100
                and int(rg["max_text"]) >= 10_000)
    except Exception:
        return False


# ============================================================ Korrektur (540, ohne --neu)
def korrektur_setzen(werk, figur, lg, formant=None, tonhoehe=None, wer="pipeline", grund=""):
    c = laden(werk)
    if not c or c.get("schema") != SCHEMA:
        raise ValueError("casting.json (Schema 2) fehlt – erst Stage 410 laufen lassen")
    if not grund:
        raise ValueError("grund ist Pflicht")
    treffer = 0
    for st, bs in ((c.get("rollen") or {}).get(lg) or {}).items():
        for e in bs.get("ensemble") or []:
            if e.get("figur") == figur:
                alt = e.get("korrektur")
                if formant is None:
                    e.pop("korrektur", None)
                else:
                    e["korrektur"] = {"formant_faktor": float(formant), "tonhoehe_ht": float(tonhoehe or 0),
                                      "grund": grund}
                e["korrektur_protokoll"] = (e.get("korrektur_protokoll") or []) + [
                    {"wann": status.jetzt(), "wer": wer, "von": alt, "nach": e.get("korrektur"), "grund": grund}]
                treffer += 1
    if not treffer:
        raise ValueError(f"Figur {figur!r} in {lg} nicht im Ensemble")
    c.setdefault("protokoll", []).append({"wann": status.jetzt(), "wer": wer, "aktion": "korrektur",
                                          "figur": figur, "sprache": lg, "grund": grund})
    manifest.json_atomar(casting_pfad(werk), c, indent=1)
    return c


# ============================================================ Freigabe
def _freigabe_anwenden(werk, c, wer, b):
    h = kern(c["rollen"])
    if (c.get("freigabe") or {}).get("hash") == h:
        return False
    c["freigabe"] = {"wer": wer, "wann": status.jetzt(), "hash": h}
    c["tor"] = "freigegeben"
    c.setdefault("protokoll", []).append({"wann": status.jetzt(), "wer": wer, "aktion": "freigabe", "hash": h})
    reg = vr.laden()
    for je in c["rollen"].values():
        for bs in je.values():
            for e in [bs.get("erzaehler") or {}] + list(bs.get("ensemble") or []):
                n = e.get("stimme")
                if n in reg and reg[n].get("status") == "kandidat":
                    reg[n]["status"] = "freigegeben"
    vr.speichern(reg)
    for je in c["rollen"].values():
        for bs in je.values():
            for e in [bs.get("erzaehler") or {}] + list(bs.get("ensemble") or []):
                if e.get("stimme") in reg:
                    vr.nutzung_vermerken(e["stimme"], werk, e.get("figur"))
    if b.roh.get("casting") != "work/casting.json":
        bestellung.feld_setzen(werk, casting="work/casting.json")
    reihe = b.roh.get("reihe")
    if reihe:
        rp = _reihe_lesen(reihe) or {"reihe": reihe, "teile": [], "rollen": {}}
        teil = b.roh.get("teil") or 1
        for lg, je in c["rollen"].items():
            for st, bs in je.items():
                ziel = rp["rollen"].setdefault(lg, {}).setdefault(st, {"erzaehler": None, "ensemble": []})
                if not ziel.get("erzaehler") or int(teil) == 1:
                    ziel["erzaehler"] = {k: bs["erzaehler"].get(k) for k in ("figur", "stimme", "gemini_id", "referenz", "modell")}
                bekannt = {e.get("figur") for e in ziel["ensemble"]}
                for e in bs.get("ensemble") or []:
                    if e.get("stimme") and (e["figur"] not in bekannt):
                        ziel["ensemble"].append({k: e.get(k) for k in ("figur", "stimme", "gemini_id", "referenz", "modell")})
                if bs.get("adapter") and (not ziel.get("adapter") or int(teil) == 1):
                    ziel["adapter"] = bs["adapter"]
        if werk not in [t.get("werk") for t in rp["teile"]]:
            rp["teile"].append({"werk": werk, "teil": teil, "wann": status.jetzt()})
        os.makedirs(os.path.dirname(reihe_pfad(reihe)), exist_ok=True)
        manifest.json_atomar(reihe_pfad(reihe), rp, indent=1)
    return True


# ============================================================ Lauf
def _ziele(b):
    """{lg: {stufe: [inhalte]}} aus der Bestellung; Teaser-Erzaehler fuer TÆLLA-Sprachen ohne Audio."""
    z, unbekannt = {}, []
    for lg in b.audiosprachen():
        for p in b.produkte_fuer(sprache=lg):
            if p["inhalt"] not in AUDIO:
                continue
            st = p.get("stufe")
            if st not in ENGINE:
                unbekannt.append(f"{lg}/{p['inhalt']}/{st}")
                continue
            inh = z.setdefault(lg, {}).setdefault(st, [])
            if p["inhalt"] not in inh:
                inh.append(p["inhalt"])
    if z:
        st0 = sorted({st for je in z.values() for st in je})[0]
        for lg in b.sprachen:
            if lg not in z and b.hat(sprache=lg, kanal="taella"):
                z[lg] = {st0: ["teaser"]}
    return z, unbekannt


def run(werk, wer=None, design=False, neu=False, neu_steckbriefe=False, grund=None, regler=None, trocken=False):
    wer = wer or "pipeline"
    g = gate.Gate(werk, STAGE, ruecksprung="410", wer=wer)
    b = bestellung.lesen(werk)
    roh = dict(b.roh)
    rg = _regler(roh)
    alt = laden(werk)
    alt_frei = freigegeben(alt)
    aendert = bool(regler and any(v not in (None, [], {}) for v in regler.values()))
    if alt_frei and (aendert or neu) and not (neu and grund):
        raise ValueError("Casting ist freigegeben – Aenderung/Neubesetzung nur mit --neu --grund (Protokoll)")
    if aendert:
        rg = regler_anwenden(rg, regler)
        if not trocken:
            b = bestellung.feld_setzen(werk, casting_regler=rg)
            roh = dict(b.roh)

    src = b.quellsprache or config.SOURCE_LANGUAGE
    ziele, unbekannt = _ziele(b)
    hoerspiel = any("hoerspiel" in inh for je in ziele.values() for inh in je.values())
    g.metrik("ziele", ziele)
    g.metrik("regler", {k: rg[k] for k in ("schwelle", "f0_abstand", "max_ensemble", "min_anteil")})
    ip = config.work_path(werk, "400_regie")
    ok = g.pflicht("eingang", os.path.exists(ip), ruecksprung="400", text="400_regie.json vorhanden")
    ok = g.pflicht("audiosprachen", bool(b.audiosprachen()), ruecksprung="095",
                   text="Bestellung nennt mind. eine Audiosprache") and ok
    ok = g.pflicht("regler", _regler_gueltig(rg), wert={k: rg[k] for k in ("schwelle", "f0_abstand", "max_ensemble",
                                                                          "min_anteil", "max_text")},
                   text="Regler im Bereich") and ok
    for u in unbekannt:
        g.hinweis(f"stufe_{u}", False, text=f"Audioprodukt {u}: Stufe ohne Casting (BETA/unbekannt)")
    z = status.zustand(werk, "400")
    if trocken:
        g.hinweis("gate_400", z in status.FREI, text=f"Gate 400: {z}")
    else:
        ok = g.pflicht("gate_400", z in status.FREI, wert=z, ruecksprung="400", text=f"Gate 400 frei ({z})") and ok
    if not ok or not ziele:
        if ok and not ziele:
            g.pflicht("ziele", False, ruecksprung="095", text="keine besetzbare Audiostufe bestellt")
        g.entscheide(schreiben=not trocken)
        return g

    with open(ip, encoding="utf-8") as f:
        data = json.load(f)
    profil = (data.get("meta") or {}).get("profile") or {}
    if not profil.get("characters"):
        pp = config.work_path(werk, "210_profil")
        if os.path.exists(pp):
            with open(pp, encoding="utf-8") as f:
                profil = (json.load(f).get("meta") or {}).get("profile") or profil
            data.setdefault("meta", {})["profile"] = profil
    figuren = list((profil.get("characters") or {}).keys()) if hoerspiel else []
    voice_note = (profil.get("style") or {}).get("voice_note") or ""

    # --- Steckbriefe (LLM ergaenzt nur Stimm-Merkmale; wiederverwendet bei gleichem Eingang)
    grenze = int(rg["max_text"]) if hoerspiel else HOERBUCH_TEXT
    text, n_dl, gekuerzt = _text(data, src, grenze, hoerspiel)
    sb_hash = manifest.hash_obj({"f": figuren, "h": hoerspiel, "t": manifest.hash_text(text), "v": PROMPT_V,
                                 "vn": voice_note})
    alt_sb = (alt or {}).get("steckbriefe") or {}
    gerettet, n_llm, sb = False, 0, None
    if alt_sb and not neu_steckbriefe:
        if alt_sb.get("_hash") == sb_hash:
            sb = alt_sb
        elif (alt or {}).get("schema") != SCHEMA and alt_sb.get("erzaehler"):
            sb = dict(alt_sb, _hash=sb_hash, _herkunft="altfassung")
            g.hinweis("steckbriefe_alt", False, text="Steckbriefe aus Altfassung casting.json uebernommen (0 $)")
    if sb is None:
        if mock.aktiv():
            sb = steckbriefe_mock(data, figuren, profil, src)
        else:
            usage_log.set_context(werk, STAGE)
            prompt = _prompt((data.get("meta") or {}).get("title", ""), (data.get("meta") or {}).get("author", ""),
                             src, sorted(ziele), text, n_dl, figuren, voice_note, hoerspiel)
            sb, gerettet = _llm(prompt, rg.get("modell"))
            n_llm = 1
            if gerettet:                                   # 1x automatisch neu
                sb2, ger2 = _llm(prompt, rg.get("modell"))
                n_llm = 2
                if not ger2 or len(sb2.get("figuren") or []) > len(sb.get("figuren") or []):
                    sb, gerettet = sb2, ger2
        sb = _sb_norm(sb)
        sb["_hash"], sb["_gerettet"], sb["_dialogzeilen"] = sb_hash, gerettet, n_dl
    g.metrik("llm_aufrufe", n_llm)
    if gekuerzt:
        g.hinweis("text_gekuerzt", False, text=f"Text fuer Steckbriefe auf {grenze:,} Zeichen gekuerzt" + ("" if hoerspiel else " (Hoerbuch: Anfang reicht)"))
    g.pruefe("steckbrief_vollstaendig", not sb.get("_gerettet"), bei_fehler="mensch", ruecksprung="410",
             text="Steckbrief-JSON vollstaendig (nicht nur gerettet, nach 1x neu)")
    figuren_sb, fremd, fehlend = _abgleich(sb, figuren) if hoerspiel else ({}, [], [])
    if hoerspiel:
        g.hinweis("figuren_fremd", not fremd, wert=fremd[:10],
                  text=f"Steckbrief-Figuren nicht in 210: {len(fremd)} ({', '.join(fremd[:5])}) – ignoriert")
        g.hinweis("figuren_ohne_steckbrief", not fehlend, wert=fehlend[:10],
                  text=f"Figuren 210 ohne Steckbrief: {len(fehlend)} ({', '.join(fehlend[:5])}) – Statisten")
    erz_sb = sb.get("erzaehler") or {}
    ich = ""
    if erz_sb.get("erzaehlform") == "ich" and erz_sb.get("ich_figur"):
        ich = next((n for n in figuren_sb if n.casefold() == erz_sb["ich_figur"].strip().casefold()), "")

    # --- Bestand / Altfassung
    fest = None
    if alt and not neu:
        if alt.get("schema") == SCHEMA:
            fest = alt.get("rollen")
        else:
            fest = _fest_aus_v1(alt, ziele)
            g.hinweis("altfassung", False, text="casting.json Schema 1 ueberfuehrt (Stimmen uebernommen, "
                                                "Sicherung casting_v1.json)")
    reihe_name = roh.get("reihe")
    reihe = _reihe_lesen(reihe_name) if rg.get("reihe_erbe", True) else None

    alt_g = (vr.SCHWELLE_PASST, vr.MIN_F0_ABSTAND)
    vr.SCHWELLE_PASST, vr.MIN_F0_ABSTAND = float(rg["schwelle"]), float(rg["f0_abstand"])
    try:
        ctx = _Ctx(werk, data, roh, rg, sb, figuren_sb, ich, fest, reihe, design and not mock.aktiv(), src, _standard())
        rollen = plan_bauen(ctx, ziele)
    finally:
        vr.SCHWELLE_PASST, vr.MIN_F0_ABSTAND = alt_g

    # --- Gate je Rolle x Sprache
    schwelle = float(rg["schwelle"])
    belegt = vr.belegte_plaetze(vr.laden())
    g.metrik("archiv", f"{belegt}/{vr.MAX_STIMMEN}")
    g.pflicht("archiv", belegt <= vr.MAX_STIMMEN, wert=belegt, text=f"Archivplaetze {belegt} ≤ {vr.MAX_STIMMEN}")
    gesucht = [f"{lg}/{st}" for lg, je in rollen.items() for st, bs in je.items()
               if (bs["erzaehler"] or {}).get("quelle") in ("genre", "archiv", "neu", "unbesetzt")]
    g.pruefe("steckbrief_erzaehler", bool((sb.get("erzaehler") or {}).get("merkmale")) or not gesucht,
             bei_fehler="mensch" if gesucht else "hinweis", ruecksprung="410",
             text="Erzaehler-Steckbrief mit Merkmalen vorhanden" + ("" if gesucht else " (Erzaehler fest besetzt)"))
    for f in ctx.design_fehler:
        g.hinweis(f"design_{len(g.pruefungen)}", False, text=f"Voice Design: {f}")
    je_sprache = {}
    for lg, je in sorted(rollen.items()):
        for st, bs in sorted(je.items()):
            k = f"{lg}_{st}"
            erz = bs["erzaehler"]
            alle = [erz] + bs["ensemble"]
            g.pflicht(f"erzaehler_{k}", bool(erz.get("stimme")), wert=erz.get("stimme"),
                      text=f"{lg}/{st}: Erzaehler besetzt ({erz.get('stimme') or 'unbesetzt – --erzaehler oder --design'})")
            nicht = [f"{e.get('figur')}: {e.get('grund')}" for e in alle if e.get("stimme") and not e.get("nutzbar")]
            g.pflicht(f"nutzbar_{k}", not nicht, wert=nicht[:5],
                      text=f"{lg}/{st}: Stimmen fuer {bs['engine']} nutzbar" + (f" – {'; '.join(nicht[:3])}" if nicht else ""))
            if bs["engine"] == "chatterbox":
                g.pflicht(f"adapter_{k}", bs.get("adapter_ok", True), wert=bs.get("adapter"),
                          text=f"{lg}/{st}: LoRA-Adapter {((bs.get('adapter') or {}).get('name')) or 'keiner'} "
                               f"freigegeben" + (f" – {bs.get('adapter_grund')}" if bs.get("adapter_grund") else ""))
            stimmen = [e.get("stimme") for e in alle if e.get("stimme")]
            doppelt = sorted({s for s in stimmen if stimmen.count(s) > 1})
            g.pruefe(f"sperre_{k}", not doppelt, wert=doppelt, bei_fehler="mensch",
                     text=f"{lg}/{st}: eine Stimme = eine Rolle"
                      + (f" – doppelt: {', '.join(doppelt)}" if doppelt else ""))
            nrep = []
            for e in alle:
                rr = e.get("reihe_ref")
                if e.get("quelle") == "reihe" and rr and (rr.get("gemini_id") != e.get("gemini_id")
                                                           or rr.get("referenz") != e.get("referenz")
                                                           or not e.get("nutzbar")):
                    nrep.append(e.get("figur"))
            if any(e.get("quelle") == "reihe" for e in alle):
                g.pflicht(f"reihe_{k}", not nrep, wert=nrep, ruecksprung="410",
                          text=f"{lg}/{st}: Reihenstimmen reproduzierbar" + (f" – nicht: {', '.join(nrep)}" if nrep else ""))
            if "hoerspiel" in bs["inhalte"]:
                unb = [e["figur"] for e in bs["ensemble"] if not e.get("stimme")]
                g.pruefe(f"ensemble_{k}", not unb, wert=unb, bei_fehler="mensch", ruecksprung="410",
                         text=f"{lg}/{st}: Ensemble-Figuren besetzt ({len(bs['ensemble']) - len(unb)}/{len(bs['ensemble'])})"
                              + (f" – offen: {', '.join(unb[:5])}" if unb else ""))
                nah = [f"{e['figur']} ({e.get('grundton_grund')})" for e in bs["ensemble"]
                       if e.get("stimme") and e.get("grundton_ok") is False]
                g.pruefe(f"grundton_{k}", not nah, wert=nah[:5], bei_fehler="mensch", ruecksprung="410",
                         text=f"{lg}/{st}: Grundton-Abstand Figur↔Figur ≥ {int(100 * float(rg['f0_abstand']))} %"
                              + (f" – {'; '.join(nah[:3])}" if nah else ""))
                zu = [e["figur"] for e in bs["ensemble"] if (e.get("trennung") or {}).get("status") == "zu_nah"]
                kn = [e["figur"] for e in bs["ensemble"] if (e.get("trennung") or {}).get("status") == "knapp"]
                unk = [e["figur"] for e in bs["ensemble"] if e.get("stimme")
                       and (e.get("trennung") or {}).get("status") in (None, "unbekannt")]
                g.pruefe(f"abstand_{k}", not zu, wert=zu, bei_fehler="mensch", ruecksprung="410",
                         text=f"{lg}/{st}: Abstand Figur↔Erzaehler D ≥ D_schwelle" + (f" – zu nah: {', '.join(zu)}" if zu else ""))
                g.hinweis(f"knapp_{k}", not kn, wert=kn,
                          text=f"{lg}/{st}: D knapp, Korrektur vorgeschlagen: {', '.join(kn)}")
                g.hinweis(f"abstand_unbekannt_{k}", not unk, wert=unk[:5],
                          text=f"{lg}/{st}: Abstand nicht messbar (kein Profil): {len(unk)}")
            schwach = [f"{e.get('figur')} {e.get('passung')}" for e in alle
                       if e.get("stimme") and e.get("passung") is not None and e["passung"] < schwelle]
            g.hinweis(f"passung_{k}", not schwach, wert=schwach[:5],
                      text=f"{lg}/{st}: Passung < {schwelle:.0f} (Vorgabe/Bestand): {', '.join(schwach[:3])}")
            neu_d = [e.get("figur") for e in alle if e.get("quelle") == "neu"]
            g.pruefe(f"neu_{k}", not neu_d, wert=neu_d, bei_fehler="mensch", ruecksprung="410",
                     text=f"{lg}/{st}: neu designte Stimmen – Hoerprobe ({', '.join(neu_d)})" if neu_d
                     else f"{lg}/{st}: keine neu designte Stimme")
            je_sprache[f"{lg}/{st}"] = {"erzaehler": erz.get("stimme"), "quelle": erz.get("quelle"),
                                        "ensemble": len([e for e in bs["ensemble"] if e.get("stimme")]),
                                        "statisten": len(bs["statisten"])}
    g.mock(1 if (sb.get("_mock") and not mock.aktiv()) else 0, ruecksprung="410")
    g.metrik("je_sprache", je_sprache)
    aus_hash = kern(rollen)
    g.metrik("ausgabe_hash", aus_hash)

    st0 = status.laden(werk)["stages"].get(STAGE) or {}
    freigabe_gilt = (st0.get("zustand") == "frei" and (st0.get("gate") or {}).get("ergebnis") == "mensch"
                     and (st0.get("metriken") or {}).get("ausgabe_hash") == aus_hash) \
        or ((alt or {}).get("freigabe") or {}).get("hash") == aus_hash
    if freigabe_gilt:
        for p in g.pruefungen:
            if not p["ok"] and p["bei_fehler"] == "mensch":
                p["bei_fehler"] = "hinweis"
                p["text"] += " [Mensch-Freigabe gilt, Besetzung unveraendert]"

    c = {"schema": SCHEMA, "werk": werk, "datum": status.jetzt(), "quelle": "work/400_regie.json",
         "steckbriefe": sb, "rollen": rollen, "regler": {k: rg[k] for k in rg if k != "design_prompt"},
         "freigabe": (alt or {}).get("freigabe") if (alt or {}).get("schema") == SCHEMA else None,
         "protokoll": list((alt or {}).get("protokoll") or [])}
    if neu and alt:
        c["protokoll"].append({"wann": status.jetzt(), "wer": wer, "aktion": "neu", "grund": grund or "",
                               "alt_hash": kern(alt.get("rollen")) if alt.get("schema") == SCHEMA else None})
    c["tor"] = "freigegeben" if (c["freigabe"] or {}).get("hash") == aus_hash else "offen"
    c["plan"] = _plan_v1(rollen)
    v1 = (alt or {}).get("v1_extra") if (alt or {}).get("schema") == SCHEMA else \
        {k: v for k, v in ((alt or {}).get("plan") or {}).items()
         if k in ("erzaehler_je_kapitel", "sprechweise", "gemini_stimmen", "overlay_gemini", "vertonung")}
    if v1:
        c["v1_extra"] = v1                 # Altabnehmer (420 Ich-Erzaehler je Kapitel, tools) bis zu deren Umbau
        if c["plan"]:
            c["plan"].update(v1)
    e = g.entscheide(mensch_immer=hoerspiel and not freigabe_gilt,
                     mensch_grund="Hoerspiel: Ensemble-Hoerprobe (Katalog: immer Mensch)", schreiben=not trocken)
    if not trocken:
        if alt and alt.get("schema") != SCHEMA:
            bak = os.path.join(config.work_dir(werk), "casting_v1.json")
            if not os.path.exists(bak):
                manifest.json_atomar(bak, alt, indent=1)
        if e == "auto":
            _freigabe_anwenden(werk, c, wer, b)
        manifest.json_atomar(casting_pfad(werk), c, indent=1)
    g.casting = c
    return g


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 410 Casting")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--design", action="store_true", help="fehlende Stimmen per Gemini Voice Design (kostet)")
    ap.add_argument("--neu", action="store_true")
    ap.add_argument("--grund")
    ap.add_argument("--neu-steckbriefe", action="store_true")
    for k in ("erzaehler", "figur", "figur-weg", "statist", "statist-weg", "design-prompt"):
        ap.add_argument(f"--{k}", action="append")
    ap.add_argument("--schwelle", type=float)
    ap.add_argument("--f0-abstand", type=float)
    ap.add_argument("--max-ensemble", type=int)
    ap.add_argument("--min-anteil", type=float)
    ap.add_argument("--max-text", type=int)
    ap.add_argument("--modell")
    ap.add_argument("--ohne-reihe", action="store_true")
    ap.add_argument("--mit-reihe", action="store_true")
    ap.add_argument("--korrektur", action="append", metavar="FIGUR:LG=FAKTOR[,HT]")
    ap.add_argument("--freigeben", action="store_true")
    ap.add_argument("--trocken", action="store_true")
    a = ap.parse_args(argv)
    wer = a.wer or "pipeline"
    regler = {"erzaehler": a.erzaehler, "figur": a.figur, "figur_weg": a.figur_weg, "statist": a.statist,
              "statist_weg": a.statist_weg, "design_prompt": a.design_prompt, "schwelle": a.schwelle,
              "f0_abstand": a.f0_abstand, "max_ensemble": a.max_ensemble, "min_anteil": a.min_anteil,
              "max_text": a.max_text, "modell": a.modell,
              "reihe_erbe": False if a.ohne_reihe else (True if a.mit_reihe else None)}
    try:
        aendert = any(v not in (None, []) for v in regler.values()) or a.korrektur or a.freigeben or a.neu
        if aendert and not a.trocken:
            from pipeline import s080_mandant
            s080_mandant.darf(a.werk, "entscheiden", wer)
        for x in a.korrektur or []:
            fl, wert = x.split("=", 1)
            fig, lg = fl.rsplit(":", 1)
            teile = [t for t in wert.split(",") if t.strip()]
            korrektur_setzen(a.werk, fig, lg, None if teile[0] == "-" else float(teile[0]),
                             float(teile[1]) if len(teile) > 1 else 0, wer, a.grund or "manuell (CLI)")
            print(f"[410] Korrektur {fig} [{lg}] gesetzt")
        if a.freigeben:
            if not a.grund:
                raise ValueError("--freigeben braucht --grund")
            status.entscheiden(a.werk, STAGE, "frei", wer, a.grund)
        g = run(a.werk, wer, a.design, a.neu, a.neu_steckbriefe, a.grund, regler, a.trocken)
    except gate.GateHalt as e:
        print(e)
        return e.exit_code
    except (ValueError, PermissionError, RuntimeError) as e:
        print(f"[410] Fehler: {e}")
        return 1
    print(g.bericht())
    return gate.EXIT[g.ergebnis["ergebnis"]]


if __name__ == "__main__":
    sys.exit(main())
