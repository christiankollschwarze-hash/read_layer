"""STAGE 400 — Regie (Phase 2, 02.11.2026)
Funktion:     Deterministische Audio-Regie je Knoten × bestellter Audiosprache: Sprechtext (+ Abbildung auf den
              Lesetext), Pause, bei Premium/Drama Stil-Zeile (direction) mit Aussprachehinweisen; Ansage-Knoten.
Komponenten:  pipeline/s400_regie.py, pipeline/sprechtext.py
Zulieferer:   s330 Rueckuebersetzung (work/330_rueckuebersetzung.json, Stand nach Reparatur; Gate 330 frei),
              Gate 340 frei, Profil 210 (meta.profile: characters, untranslated), book.json (Bestellung, audio_regler,
              audio_pron_skip, audio_pausen, fassungen/titel), author.json (name_display, wirkungssprache)
Abnehmer:     s410, s420, s500/502, s510, s520 (Abbildung), s530, s650 (Pausen, Ansagen), s710 (work/400_regie.json)
Kosten:       0 $ (kein LLM)

Ausgabe work/400_regie.json = 330 + production:
    sprechtext[tid][lg], abbildung[tid][lg] ([[s0, s1, l0, l1], ...] nur bei Abweichung),
    pause_after_ms[tid][lg], direction[tid][lg] (nur Premium/Drama-Sprachen)
  + ansagen[lg] = [{id, type "ansage", art titel|autor|sprecher|ende, position anfang|ende, text, sprechtext,
                    abbildung, pause_after_ms, direction?, vorlage?}]  (nur Hoerbuch-Sprachen; nicht in content,
                    damit Text-Abnehmer unberuehrt bleiben)
  + meta.regie. Dazu work/400_pruefung.json (Listen Text / Sprechtext), work/400_korrekturen.json (manuell).

Gate 400 je Audiosprache: Abdeckung (Text je Audio-Knoten) → Stopp (310); roemisch in Ueberschriften, Mehrfach-Roemisch,
Reste (Ziffern § & %), Laenge Sprechtext ≤ 1,5× Text (+20 Zeichen Puffer; Zahl-/Symbolwoerter
zaehlen nicht) → 1× erweiterte Regeln, dann Mensch;
Style ≤ 200 Zeichen → Mensch; Figuren/Unuebersetzt ohne Aussprache → Mensch bei Premium/Drama, sonst Hinweis (210);
Regler 1–10, Gate 330/340 frei, Audiosprache bestellt → sonst Stopp; Mock im Live-Lauf → Stopp.
Mensch-Freigabe gilt, solange ausgabe_hash gleich bleibt.

CLI: py -3.11 -m pipeline.s400_regie <werk> [--betonung N --emotion N --tempo N] [--pause TYP=MS]
     [--pron-skip BEGRIFF] [--aussprache BEGRIFF=HINWEIS] [--sprechtext ID=TEXT | --sprechtext ID=-] [--lang LG]
     [--laenge-max 1.5] [--style-max 200] [--trocken] [--wer CK]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import bestellung, gate, manifest, mock, status
from pipeline import sprechtext as st

STAGE = "400"
REGLER = ("betonung", "emotion", "tempo")
LAENGE_MAX = 1.5
LAENGE_PUFFER = 20
STYLE_MAX = 200
PREMIUM = ("premium", "drama")

# Tag-Typen mit eigener Regie (Rest erbt 's')
DIRECTION_TYPES = ["s", "dl", "h", "ansage"]
LANG_NAME = {"en": "English", "de": "German", "fr": "French", "es": "Spanish",
             "it": "Italian", "ru": "Russian", "nl": "Dutch", "pt": "Portuguese"}

ANSAGE = {
    "en": {"autor": "by {autor}.", "sprecher": "Read by an AI voice.",
           "vorlage": "Read by {sprecher}, an AI voice.", "ende": "The End."},
    "de": {"autor": "von {autor}.", "sprecher": "Gelesen von einer KI-Stimme.",
           "vorlage": "Gelesen von {sprecher}, einer KI-Stimme.", "ende": "Ende."},
    "es": {"autor": "de {autor}.", "sprecher": "Leído por una voz de IA.",
           "vorlage": "Leído por {sprecher}, una voz de IA.", "ende": "Fin."},
    "fr": {"autor": "de {autor}.", "sprecher": "Lu par une voix d'IA.",
           "vorlage": "Lu par {sprecher}, une voix d'IA.", "ende": "Fin."},
    "it": {"autor": "di {autor}.", "sprecher": "Letto da una voce IA.",
           "vorlage": "Letto da {sprecher}, una voce IA.", "ende": "Fine."},
}
ANSAGE_PAUSE = {"titel": 700, "autor": 1200, "sprecher": 1500, "ende": 0}


# ============================================================ Pausen
def pausen_tabellen(roh=None):
    roh = roh or {}
    typ = dict(config.PAUSE_AFTER_MS)
    typ.update({k: int(v) for k, v in (roh.get("audio_pausen") or {}).items()})
    sz = dict(config.PAUSE_BY_PUNCTUATION)
    sz.update({k: int(v) for k, v in (roh.get("audio_pausen_satzzeichen") or {}).items()})
    return typ, sz


def compute_pause_ms(entry: dict, lang: str, typ_tab=None, sz_tab=None) -> int:
    """Dramaturgische Pause NACH diesem Knoten (ms): Typ-Wert + Schluss-Satzzeichen der Sprachfassung."""
    typ_tab = typ_tab or config.PAUSE_AFTER_MS
    sz_tab = sz_tab or config.PAUSE_BY_PUNCTUATION
    typ = entry.get("type", "s")
    base = typ_tab.get(typ, typ_tab["s"])
    text = str(entry.get(lang, "")).strip()
    if text:
        last = text[-1]
        if last in '"”»“' and len(text) >= 2:
            last = text[-2]
        base += sz_tab.get(last, 0)
    return max(0, base)


# ============================================================ Regler -> Regie
def _band(v) -> str:
    try:
        v = int(v)
    except (TypeError, ValueError):
        v = 5
    return "low" if v <= 3 else "high" if v >= 8 else "mid"


_BETONUNG = {"low": "Use even, level word stress; do not emphasize nouns or individual "
                    "words -- read with natural, everyday delivery.", "mid": "",
             "high": "Give the meaningful words clear, deliberate emphasis."}
_EMOTION = {"low": "Keep the tone neutral, matter-of-fact and restrained.", "mid": "",
            "high": "Let genuine feeling and expression come through in the voice."}
_TEMPO = {"low": "Speak at a slow, unhurried, measured pace.", "mid": "", "high": "Speak at a lively, brisk pace."}
_BASE = {"s": "Read this as a calm audiobook narrator.",
         "dl": "Read this line of dialogue as spoken by a person, within the narration's mood.",
         "h": "Read this chapter heading clearly and plainly.",
         "ansage": "Read this announcement clearly and plainly."}
# Gemini 3.8: knappe Stil-Stichworte (speech_metadata.style)
_BETONUNG_38 = {"low": "even word stress, no emphasis on nouns", "mid": "", "high": "clear emphasis on key words"}
_EMOTION_38 = {"low": "neutral and restrained", "mid": "", "high": "expressive, heartfelt"}
_TEMPO_38 = {"low": "slow, measured pace", "mid": "", "high": "lively, brisk pace"}
_BASE_38 = {"s": "calm audiobook narration", "dl": "natural spoken dialogue within the narration's mood",
            "h": "clear, plain chapter heading", "ansage": "clear, plain announcement"}


def _is_38() -> bool:
    return getattr(config, "TTS_BACKEND", "gemini_api") == "gemini_api"


def _compose(base, reglers, t, e, b, sep):
    parts = [base] + [p for p in (t[_band(reglers.get("tempo", 5))], e[_band(reglers.get("emotion", 5))],
                                  b[_band(reglers.get("betonung", 5))]) if p]
    return sep.join(parts)


def directions_from_reglers(reglers: dict) -> dict:
    """{typ: regie} aus den drei Reglern (oeffentlich: s500/tts_probe nutzen dieselbe Regie)."""
    if _is_38():
        return {t: _compose(_BASE_38[t], reglers, _TEMPO_38, _EMOTION_38, _BETONUNG_38, ", ") for t in DIRECTION_TYPES}
    return {t: _compose(_BASE[t], reglers, _TEMPO, _EMOTION, _BETONUNG, " ") for t in DIRECTION_TYPES}


def _regler_roh(roh):
    r = roh.get("audio_regler") or {}
    return {k: r.get(k, 5) for k in REGLER}


def regler_gueltig(r):
    return all(isinstance(r.get(k), int) and not isinstance(r.get(k), bool) and 1 <= r[k] <= 10 for k in REGLER)


def _load_reglers(book_id: str) -> dict:
    """audio_regler aus book.json (fehlt -> 5/5/5). Oeffentlich fuer s500."""
    try:
        r = _regler_roh(bestellung.lesen(book_id).roh)
    except Exception:
        r = {}
    out = {}
    for k in REGLER:
        try:
            out[k] = int(r.get(k, 5))
        except (TypeError, ValueError):
            out[k] = 5
    return out


# ============================================================ Aussprache
def _autor(werk):
    p = os.path.join(os.path.dirname(os.path.dirname(config.book_dir(werk))), "author.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def begriffe(profil, aussprache_manuell=None):
    """[(schluessel, {lg: name|None}, {lg: hat_aussprache}|bool, quelle)] aus Figuren + Unuebersetzt."""
    man = aussprache_manuell or {}
    out = []
    for quelle in ("characters", "untranslated"):
        for k, e in (profil.get(quelle) or {}).items():
            if not k:
                continue
            e = e if isinstance(e, dict) else {}
            out.append({"key": k, "quelle": quelle, "e": e, "manuell": (man.get(k) or {}).get("hinweis")})
    return out


def _name(b, lg):
    if b["quelle"] == "characters":
        n = b["e"].get(lg)
        return n if isinstance(n, str) and n.strip() else b["key"]
    return b["key"]


def _hat_aussprache(b, lg):
    return bool(b["manuell"] or b["e"].get("pronunciation") or b["e"].get(f"tts_{lg}"))


def _treffer(text, namen):
    low = (text or "").lower()
    hits = [n for n in namen if re.search(r"(?<!\w)" + re.escape(n.lower()) + r"(?!\w)", low)]
    return [n for n in hits if not any(n != m and n.lower() in m.lower() for m in hits)]   # in laengerem Namen enthalten


def _pron_hinweis(hits, lang_name, manuell):
    if not hits:
        return ""
    if _is_38():
        teile = [f"{n} pronounced {manuell[n]}" for n in hits if manuell.get(n)]
        rest = [n for n in hits if not manuell.get(n)]
        if rest:
            teile.append(f"{', '.join(rest)} pronounced as in {lang_name}")
        return "; " + "; ".join(teile)
    s = "".join(f" Pronounce {n} as {manuell[n]}." for n in hits if manuell.get(n))
    rest = [n for n in hits if not manuell.get(n)]
    if len(rest) == 1:
        s += f" Pronounce the proper noun {rest[0]} in {lang_name}."
    elif rest:
        s += f" Pronounce the proper nouns {', '.join(rest[:-1])} and {rest[-1]} in {lang_name}."
    return s


# ============================================================ Korrekturen
def _korr_pfad(werk):
    return os.path.join(config.work_dir(werk), "400_korrekturen.json")


def korrekturen_lesen(werk):
    try:
        with open(_korr_pfad(werk), encoding="utf-8") as f:
            k = json.load(f)
    except Exception:
        k = {}
    k.setdefault("sprechtext", {})
    k.setdefault("aussprache", {})
    return k


def _korr_schreiben(werk, k):
    manifest.json_atomar(_korr_pfad(werk), k, indent=1)


def _lesehash(text):
    return manifest.hash_text(text or "")


# ============================================================ Pruefung je Knoten
_ZAHL = re.compile(r"[\d§&%]")


def zahl_zuschlag(abb, text):
    """Laengenzuwachs aus Zahl-/Symbolwoertern (zaehlt nicht ins Laengenverhaeltnis)."""
    return sum(max(0, (b - a) - (d - c)) for a, b, c, d in abb or [] if b > a and _ZAHL.search(text[c:d]))


def fehlerarten(sp, text, typ, laenge_max=LAENGE_MAX, abb=None):
    f = []
    ro = st.roemisch_offen(sp, typ == "h")
    if ro:
        f.append("roemisch_h" if typ == "h" else "roemisch")
    if st.reste(sp):
        f.append("reste")
    n = len(sp) - zahl_zuschlag(abb, text)
    if n > laenge_max * len(text) and n - len(text) > LAENGE_PUFFER:
        f.append("laenge")
    return f


def _sprech(text, lg, typ, laenge_max):
    """Standard-Regeln; bei Fehler 1× erweitert. -> (sp, abb, fehler, versucht, repariert)."""
    sp, abb = st.sprechtext_abb(text, lg, typ)
    f = fehlerarten(sp, text, typ, laenge_max, abb)
    if not f:
        return sp, abb, f, False, False
    sp2, abb2 = st.sprechtext_abb(text, lg, typ, erweitert=True)
    f2 = fehlerarten(sp2, text, typ, laenge_max, abb2)
    if len(f2) < len(f) or (len(f2) == len(f) and "reste" in f and "reste" not in f2):
        return sp2, abb2, f2, True, not f2
    return sp, abb, f, True, False


# ============================================================ Ansagen
def _titel(b, data, lg):
    for fa in b.roh.get("fassungen") or []:
        if isinstance(fa, dict) and fa.get("sprache") == lg and str(fa.get("titel") or "").strip():
            return fa["titel"].strip(), "fassungen"
    if str(b.roh.get(f"titel_{lg}") or "").strip():
        return b.roh[f"titel_{lg}"].strip(), f"titel_{lg}"
    t = b.roh.get("titel_original") or (data.get("meta") or {}).get("title") or ""
    return str(t).strip(), "original"


def ansagen(b, data, lg, autor_name, laenge_max):
    tx = ANSAGE.get(lg) or ANSAGE["en"]
    titel, quelle = _titel(b, data, lg)
    out, hinweise = [], []
    if titel:
        out.append(("titel", "anfang", titel if titel[-1] in ".!?" else titel + "."))
    if quelle == "original" and lg != b.quellsprache:
        hinweise.append(f"{lg}: Ansage-Titel ohne Titel in {lg} (Originaltitel) – 110/310/615 pruefen")
    if not titel:
        hinweise.append(f"{lg}: Ansage-Titel fehlt")
    if autor_name:
        out.append(("autor", "anfang", tx["autor"].format(autor=autor_name)))
    else:
        hinweise.append(f"{lg}: Autor unbekannt – Ansage Autor entfaellt (110/150)")
    out.append(("sprecher", "anfang", tx["sprecher"]))
    out.append(("ende", "ende", tx["ende"]))
    knoten = []
    for art, pos, text in out:
        sp, abb, f, _, _ = _sprech(text, lg, "ansage", laenge_max)
        k = {"id": f"ansage_{art}", "type": "ansage", "art": art, "position": pos, "text": text,
             "sprechtext": sp, "pause_after_ms": ANSAGE_PAUSE[art], "fehler": f}
        if abb:
            k["abbildung"] = abb
        if art == "sprecher":
            k["vorlage"] = tx["vorlage"]
        knoten.append(k)
    return knoten, hinweise


# ============================================================ Hauptlauf
def run(werk, wer=None, regler=None, pausen=None, pron_skip=None, aussprache=None, sprechtext_man=None,
        nur_lang=None, laenge_max=None, style_max=None, trocken=False):
    wer = wer or "pipeline"
    g = gate.Gate(werk, STAGE, ruecksprung="400", wer=wer)
    laenge_max = float(laenge_max or LAENGE_MAX)
    style_max = int(style_max or STYLE_MAX)
    b = bestellung.lesen(werk)
    roh = dict(b.roh)

    # --- Regler in book.json (Werkregler, wirken auch fuer 500/tts_probe)
    neu = {}
    if regler and any(v is not None for v in regler.values()):
        r = _regler_roh(roh)
        r.update({k: v for k, v in regler.items() if v is not None})
        neu["audio_regler"] = r
    if pausen:
        p = dict(roh.get("audio_pausen") or {})
        p.update(pausen)
        neu["audio_pausen"] = p
    if pron_skip:
        s = list(roh.get("audio_pron_skip") or [])
        s += [x for x in pron_skip if x not in s]
        neu["audio_pron_skip"] = s
    if neu and not trocken:
        b = bestellung.feld_setzen(werk, **neu)
        roh = dict(b.roh)
    elif neu:
        roh.update(neu)

    src = b.quellsprache or config.SOURCE_LANGUAGE
    audio = b.audiosprachen()
    hoerbuch = b.audiosprachen("hoerbuch")
    premium = [lg for lg in audio if any(p.get("stufe") in PREMIUM and p.get("inhalt") in ("hoerbuch", "hoerspiel")
                                         for p in b.produkte_fuer(sprache=lg))]
    r = _regler_roh(roh)
    for k, v in (("audiosprachen", audio), ("premium", premium), ("regler", r)):
        g.metrik(k, v)

    ip = config.work_path(werk, "330_rueckuebersetzung")
    ok = g.pflicht("eingang", os.path.exists(ip), ruecksprung="330", text="330_rueckuebersetzung.json vorhanden")
    ok = g.pflicht("audiosprachen", bool(audio), ruecksprung="095", text="Bestellung nennt mind. eine Audiosprache") and ok
    ok = g.pflicht("regler", regler_gueltig(r), wert=r, ruecksprung="400",
                   text=f"Regler Betonung/Emotion/Tempo ganzzahlig 1–10 ({r})") and ok
    for vor in ("330", "340"):
        z = status.zustand(werk, vor)
        if trocken:
            g.hinweis(f"gate_{vor}", z in status.FREI, text=f"Gate {vor}: {z}")
        else:
            ok = g.pflicht(f"gate_{vor}", z in status.FREI, wert=z, ruecksprung=vor, text=f"Gate {vor} frei ({z})") and ok
    if not ok:
        g.entscheide(schreiben=not trocken)
        return g
    with open(ip, encoding="utf-8") as f:
        data = json.load(f)
    content = data.get("content") or {}
    meta = data.setdefault("meta", {})
    profil = meta.get("profile") or {}

    # --- manuelle Korrekturen
    korr = korrekturen_lesen(werk)
    k_neu = False
    for x in aussprache or []:
        term, hin = x.split("=", 1)
        korr["aussprache"][term.strip()] = {"hinweis": hin.strip(), "wer": wer, "wann": manifest.jetzt()}
        k_neu = True
    if sprechtext_man:
        lg_m = nur_lang or (audio[0] if len(audio) == 1 else None)
        if not lg_m:
            raise ValueError("--sprechtext braucht --lang bei mehreren Audiosprachen")
        for x in sprechtext_man:
            tid, t = x.split("=", 1)
            if tid not in content:
                raise ValueError(f"unbekannte ID {tid}")
            lk = korr["sprechtext"].setdefault(lg_m, {})
            if t.strip() == "-":
                lk.pop(tid, None)
            else:
                lk[tid] = {"h": _lesehash(str(content[tid].get(lg_m) or "").strip()), "text": t.strip(),
                           "wer": wer, "wann": manifest.jetzt()}
        k_neu = True
    if k_neu and not trocken:
        _korr_schreiben(werk, korr)

    reglers = {k: int(v) for k, v in r.items()}
    regie = directions_from_reglers(reglers)
    typ_tab, sz_tab = pausen_tabellen(roh)
    au = _autor(werk)
    namensprache = (au.get("wirkungssprache") or "").strip() or src
    lang_name = LANG_NAME.get(namensprache, namensprache)
    skip = {str(s).strip().lower() for s in (roh.get("audio_pron_skip") or []) if str(s).strip()}
    alle_begriffe = [x for x in begriffe(profil, korr["aussprache"]) if x["key"].lower() not in skip]
    autor_name = (au.get("name_display") or (data.get("meta") or {}).get("author") or "").strip()
    if autor_name.lower() in ("unbekannt", "unknown", "anonym", "anonymous"):
        autor_name = ""

    prod = {"sprechtext": {}, "abbildung": {}, "pause_after_ms": {}, "direction": {}}
    pruef, je_sprache, ansage_out = {}, {}, {}
    z = {"knoten": 0, "erweitert": 0, "repariert": 0, "manuell": 0, "manuell_veraltet": 0}
    n_mock = 0
    for lg in audio:
        prem = lg in premium
        man_lg = korr["sprechtext"].get(lg) or {}
        namen = {}
        for bg in alle_begriffe:
            namen.setdefault(_name(bg, lg), bg)
        fehl = {"roemisch_h": [], "roemisch": [], "reste": [], "laenge": [], "style": []}
        leer, ohne_aus, manuell_ids, veraltet = [], {}, [], 0
        for tid, e in content.items():
            if not isinstance(e, dict):
                continue
            typ = e.get("type", "s")
            prod["pause_after_ms"].setdefault(tid, {})[lg] = compute_pause_ms(e, lg, typ_tab, sz_tab)
            if typ in config.NO_AUDIO_TYPES:
                continue
            text = str(e.get(lg) or "").strip()
            if not text:
                leer.append(tid)
                continue
            if mock.ist_text(text):
                n_mock += 1
            z["knoten"] += 1
            m = man_lg.get(tid)
            if m and m.get("h") == _lesehash(text):
                sp, abb, f = m["text"], [[0, len(m["text"]), 0, len(text)]], []
                z["manuell"] += 1
                manuell_ids.append(tid)
            else:
                if m:
                    z["manuell_veraltet"] += 1
                    veraltet += 1
                sp, abb, f, vers, rep = _sprech(text, lg, typ, laenge_max)
                z["erweitert"] += vers
                z["repariert"] += rep
            for art in f:
                fehl[art].append({"id": tid, "text": text, "sprechtext": sp})
            prod["sprechtext"].setdefault(tid, {})[lg] = sp
            if abb:
                prod["abbildung"].setdefault(tid, {})[lg] = abb
            hits = _treffer(text, list(namen)) if lg != namensprache else []
            for n in hits:
                if not _hat_aussprache(namen[n], lg):
                    ohne_aus.setdefault(namen[n]["key"], []).append(tid)
            if prem:
                man_hin = {n: namen[n]["manuell"] for n in hits if namen[n]["manuell"]}
                d = regie.get(typ, regie["s"]) + _pron_hinweis(hits, lang_name, man_hin)
                prod["direction"].setdefault(tid, {})[lg] = d
                if len(d) > style_max:
                    fehl["style"].append({"id": tid, "text": text, "sprechtext": d})
        # --- Ansagen
        hinweise_a = []
        if lg in hoerbuch:
            kn, hinweise_a = ansagen(b, data, lg, autor_name, laenge_max)
            for k in kn:
                if prem:
                    k["direction"] = regie["ansage"]
                for art in k.pop("fehler"):
                    fehl[art].append({"id": k["id"], "text": k["text"], "sprechtext": k["sprechtext"]})
            ansage_out[lg] = kn

        # --- Gate je Sprache
        n_aud = sum(1 for e in content.values() if isinstance(e, dict) and e.get("type", "s") not in config.NO_AUDIO_TYPES)
        g.pruefe(f"abdeckung_{lg}", not leer, wert=len(leer), schwelle="= 0", bei_fehler="stopp", ruecksprung="310",
                 text=f"{lg}: Audio-Knoten ohne Text {len(leer)}/{n_aud}" + (f" {leer[:6]}" if leer else ""))
        for art, txt in (("roemisch_h", "roemisch in Ueberschriften"), ("roemisch", "Mehrfach-Roemisch im Fliesstext"),
                         ("reste", "Reste (Ziffern, §, &, %)"),
                         ("laenge", f"Sprechtext > {laenge_max}× Text"), ("style", f"Style > {style_max} Zeichen")):
            if art == "style" and not prem:
                continue
            l = fehl[art]
            g.pruefe(f"{art}_{lg}", not l, wert=len(l), schwelle="= 0", bei_fehler="mensch", ruecksprung="400",
                     text=f"{lg}: {txt} {len(l)}" + (f" {[x['id'] for x in l[:5]]}" if l else ""))
        txt = f"{lg}: Figuren/Unuebersetzt ohne Aussprache {len(ohne_aus)}" + \
              (f" {sorted(ohne_aus)[:6]}" if ohne_aus else "")
        if prem:
            g.pruefe(f"aussprache_{lg}", not ohne_aus, wert=len(ohne_aus), schwelle="= 0", bei_fehler="mensch",
                     ruecksprung="210", text=txt + " (Premium/Drama)")
        else:
            g.hinweis(f"aussprache_{lg}", not ohne_aus, wert=len(ohne_aus), text=txt)
        if veraltet:
            g.hinweis(f"manuell_veraltet_{lg}", False, text=f"{lg}: manueller Sprechtext veraltet (Text geaendert) – "
                                                           f"Regeln angewandt")
        for i, h in enumerate(hinweise_a):
            g.hinweis(f"ansage_{lg}_{i}", False, text=h)
        if st._n2w is None:
            g.hinweis("num2words", False, text="num2words fehlt – Ziffern bleiben (py -3.11 -m pip install num2words)")
        je_sprache[lg] = {k: len(v) for k, v in fehl.items()} | {"ohne_aussprache": len(ohne_aus),
                                                                "manuell": len(manuell_ids), "ansagen": len(ansage_out.get(lg, []))}
        pruef[lg] = {"fehler": fehl, "ohne_aussprache": ohne_aus, "manuell": manuell_ids, "leer": leer}

    g.mock(0 if mock.aktiv() else n_mock, ruecksprung="330")
    for k, v in z.items():
        g.metrik(k, v)
    g.metrik("je_sprache", je_sprache)

    data["production"] = prod
    data["ansagen"] = ansage_out
    meta["regie"] = {"audiosprachen": audio, "premium": premium, "regler": reglers, "namensprache": namensprache,
                     "regeln_v": st.REGELN_V, "laenge_max": laenge_max, "style_max": style_max,
                     "tts_backend": getattr(config, "TTS_BACKEND", ""), "erzeugt": manifest.jetzt()}
    aus_hash = manifest.hash_obj({"p": prod, "a": ansage_out})
    g.metrik("ausgabe_hash", aus_hash)
    st0 = status.laden(werk)["stages"].get(STAGE) or {}
    if st0.get("zustand") == "frei" and (st0.get("gate") or {}).get("ergebnis") == "mensch" \
            and (st0.get("metriken") or {}).get("ausgabe_hash") == aus_hash:
        for p in g.pruefungen:
            if not p["ok"] and p["bei_fehler"] == "mensch":
                p["bei_fehler"] = "hinweis"
                p["text"] += " [Mensch-Freigabe gilt, Ausgabe unveraendert]"
    if not trocken:
        manifest.json_atomar(config.work_path(werk, "400_regie"), data, indent=2)
        manifest.json_atomar(os.path.join(config.work_dir(werk), "400_pruefung.json"), pruef, indent=1)
    g.entscheide(schreiben=not trocken)
    g.pruef = pruef
    g.data = data
    return g


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 400 Regie (deterministisch, 0 $)")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    for k in REGLER:
        ap.add_argument(f"--{k}", type=int)
    ap.add_argument("--pause", action="append", metavar="TYP=MS")
    ap.add_argument("--pron-skip", action="append", metavar="BEGRIFF")
    ap.add_argument("--aussprache", action="append", metavar="BEGRIFF=HINWEIS")
    ap.add_argument("--sprechtext", action="append", metavar="ID=TEXT", help="ID=- loescht")
    ap.add_argument("--lang", help="Audiosprache fuer --sprechtext")
    ap.add_argument("--laenge-max", type=float)
    ap.add_argument("--style-max", type=int)
    ap.add_argument("--trocken", action="store_true")
    a = ap.parse_args(argv)
    regler = {k: getattr(a, k) for k in REGLER}
    pausen = {x.split("=", 1)[0]: int(x.split("=", 1)[1]) for x in a.pause or []}
    try:
        aendert = any(v is not None for v in regler.values()) or pausen or a.pron_skip or a.aussprache or a.sprechtext
        if aendert and not a.trocken:
            from pipeline import s080_mandant
            s080_mandant.darf(a.werk, "entscheiden", a.wer or "pipeline")
        g = run(a.werk, a.wer, regler, pausen, a.pron_skip, a.aussprache, a.sprechtext, a.lang,
                a.laenge_max, a.style_max, a.trocken)
    except gate.GateHalt as e:
        print(e)
        return e.exit_code
    except (ValueError, PermissionError) as e:
        print(f"[400] Fehler: {e}")
        return 1
    print(g.bericht())
    return gate.EXIT[g.ergebnis["ergebnis"]]


if __name__ == "__main__":
    sys.exit(main())
