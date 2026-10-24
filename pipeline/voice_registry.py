"""
READ LAYER — Stimmen-Register ("Samenbank") + Ensemble-Logik
=============================================================
Ein Register fuer ALLE Werke: stimmen_archiv/stimmen.json
Je Stimme ein Ordner stimmen_archiv/<name>/ mit hoerprobe.wav, muster_en.wav,
muster_de.wav, steckbrief.json (Herkunft belegt, modellunabhaengig replizierbar).

Grundregeln (CK, 11.10.2026):
  1. Werke bedienen sich ZUERST aus dem Archiv, wenn eine Stimme "in etwa passt".
  2. Nur wenn nichts passt, wird neu designt (Gemini Voice Design) und archiviert.
  3. Innerhalb EINES Werks hat jede Stimme genau EINE Rolle (Ensemble-Sperre).
  4. Neue oder uebernommene Stimmen muessen sich HOERBAR von den bereits besetzten
     Ensemble-Stimmen unterscheiden (Merkmale + gemessener Grundton).
  5. Max. 200 gespeicherte Stimmen je Google-Projekt; jede Nutzung setzt die
     1-Jahres-TTL zurueck. Verfallene Stimmen -> Voice Replication aus den Clips.

Merkmal-Schema (gleich fuer Figuren-Steckbrief und Stimme):
  geschlecht   : w | m | neutral
  alter        : kind | jung | mittel | alt | greis
  tonlage      : hoch | mittel | tief
  klangfarbe   : Liste aus KLANGFARBEN
  tempo        : langsam | mittel | schnell
  temperament  : Liste aus TEMPERAMENTE
  sicherheit   : fest | neutral | unsicher
  akzent       : Freitext (z. B. "britisch", "schottisch", "Cockney", "")
"""

import json
import os
import time
import wave

from config import config

STIMMEN_DIR = getattr(config, "STIMMEN_DIR", os.path.join(config.BASE_DIR, "stimmen_archiv"))
REGISTER = os.path.join(STIMMEN_DIR, "stimmen.json")
# 24.10.2026 (Smoke #6): eigenes Register per Umgebungsvariable (Smoke-Test) -> globales bleibt unberuehrt.
# Stimm-Audios liegen weiter unter STIMMEN_DIR.
REGISTER = os.environ.get("READLAYER_STIMMEN_REGISTER") or REGISTER
MAX_STIMMEN = 200

ALTER = ["kind", "jung", "mittel", "alt", "greis"]
TONLAGE = ["hoch", "mittel", "tief"]
TEMPO = ["langsam", "mittel", "schnell"]
SICHERHEIT = ["unsicher", "neutral", "fest"]
KLANGFARBEN = ["warm", "kuehl", "rau", "heiser", "bruechig", "samtig", "nasal", "kehlig",
               "hell", "dunkel", "kraeftig", "duenn", "piepsig", "verraucht", "klar"]
TEMPERAMENTE = ["ruhig", "nervoes", "cholerisch", "melancholisch", "verschmitzt", "guetig",
                "streng", "herablassend", "aengstlich", "albern", "feierlich", "neugierig",
                "schlaefrig", "hochmuetig", "verwirrt", "froehlich"]

# Mindest-Passung fuer Wiederverwendung aus dem Archiv (0-100)
SCHWELLE_PASST = getattr(config, "CASTING_SCHWELLE", 70)
# Mindestabstand Grundton zu Ensemble-Stimmen gleichen Geschlechts (relativ)
MIN_F0_ABSTAND = getattr(config, "CASTING_MIN_F0_ABSTAND", 0.12)
# Mindest-Merkmalsabstand (0-100), wenn der Grundton zu nah liegt
MIN_MERKMAL_ABSTAND = 35

LANG_CODES = {"en": "en-GB", "de": "de-DE"}


# ============================================================
# REGISTER LESEN / SCHREIBEN
# ============================================================

def laden() -> dict:
    if not os.path.exists(REGISTER):
        return {}
    with open(REGISTER, "r", encoding="utf-8") as f:
        return json.load(f)


def speichern(reg: dict) -> None:
    os.makedirs(os.path.dirname(REGISTER) or ".", exist_ok=True)
    tmp = REGISTER + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=1)
    os.replace(tmp, REGISTER)


def verfuegbar(reg: dict, rolle_typ: str = None) -> list:
    """Freigegebene + Kandidaten-Stimmen (abgelehnte nie)."""
    out = []
    for name, s in reg.items():
        if s.get("status") == "abgelehnt":
            continue
        if rolle_typ and s.get("rolle_typ") not in (rolle_typ, "beides"):
            continue
        out.append((name, s))
    return out


def belegte_plaetze(reg: dict) -> int:
    return sum(1 for s in reg.values() if s.get("status") != "geloescht")


# ============================================================
# MERKMALE NORMALISIEREN + VERGLEICHEN
# ============================================================

def _norm_wert(wert, erlaubt, default):
    w = (wert or "").strip().lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    return w if w in erlaubt else default


def _norm_liste(werte, erlaubt):
    out = []
    for w in werte or []:
        w = str(w).strip().lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
        if w in erlaubt and w not in out:
            out.append(w)
    return out


def normalisieren(m: dict) -> dict:
    m = m or {}
    g = (m.get("geschlecht") or "").strip().lower()[:1]
    return {
        "geschlecht": {"w": "w", "f": "w", "m": "m"}.get(g, "neutral"),
        "alter": _norm_wert(m.get("alter"), ALTER, "mittel"),
        "tonlage": _norm_wert(m.get("tonlage"), TONLAGE, "mittel"),
        "klangfarbe": _norm_liste(m.get("klangfarbe"), KLANGFARBEN),
        "tempo": _norm_wert(m.get("tempo"), TEMPO, "mittel"),
        "temperament": _norm_liste(m.get("temperament"), TEMPERAMENTE),
        "sicherheit": _norm_wert(m.get("sicherheit"), SICHERHEIT, "neutral"),
        "akzent": (m.get("akzent") or "").strip().lower(),
    }


def _ordinal(a, b, skala):
    """1.0 = gleich, 0.0 = maximal entfernt."""
    return 1.0 - abs(skala.index(a) - skala.index(b)) / (len(skala) - 1)


def _jaccard(a, b):
    a, b = set(a), set(b)
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def passung(figur: dict, stimme: dict) -> int:
    """Wie gut passt eine Archiv-Stimme zu einem Figuren-Steckbrief? 0-100.
    Geschlecht ist hart (Abweichung -> 0), ausser eine Seite ist 'neutral'."""
    f, s = normalisieren(figur), normalisieren(stimme)
    if f["geschlecht"] != s["geschlecht"] and "neutral" not in (f["geschlecht"], s["geschlecht"]):
        return 0
    teile = [
        (25, _ordinal(f["alter"], s["alter"], ALTER)),
        (20, _ordinal(f["tonlage"], s["tonlage"], TONLAGE)),
        (20, _jaccard(f["klangfarbe"], s["klangfarbe"])),
        (15, _jaccard(f["temperament"], s["temperament"])),
        (8, _ordinal(f["tempo"], s["tempo"], TEMPO)),
        (7, _ordinal(f["sicherheit"], s["sicherheit"], SICHERHEIT)),
        (5, 1.0 if f["akzent"] == s["akzent"] else 0.0),
    ]
    return round(sum(g * w for g, w in teile))


def merkmal_abstand(a: dict, b: dict) -> int:
    """0 = identisch, 100 = voellig verschieden (ohne Geschlecht)."""
    a, b = normalisieren(a), normalisieren(b)
    teile = [
        (30, 1 - _ordinal(a["alter"], b["alter"], ALTER)),
        (30, 1 - _ordinal(a["tonlage"], b["tonlage"], TONLAGE)),
        (25, 1 - _jaccard(a["klangfarbe"], b["klangfarbe"])),
        (15, 1 - _jaccard(a["temperament"], b["temperament"])),
    ]
    return round(sum(g * w for g, w in teile))


def unterscheidbar(kandidat: dict, ensemble: list) -> tuple:
    """Prueft eine Stimme (Register-Eintrag) gegen alle bereits besetzten
    Ensemble-Stimmen. Konflikt nur bei gleichem Geschlecht.
    Rueckgabe: (ok, grund, konflikt_eintrag)."""
    km = normalisieren(kandidat.get("merkmale"))
    kf0 = kandidat.get("grundton_hz")
    for e in ensemble:
        em = normalisieren(e.get("merkmale"))
        if km["geschlecht"] != em["geschlecht"] and "neutral" not in (km["geschlecht"], em["geschlecht"]):
            continue
        ef0 = e.get("grundton_hz")
        f0_nah = bool(kf0 and ef0 and abs(kf0 - ef0) / max(kf0, ef0) < MIN_F0_ABSTAND)
        abst = merkmal_abstand(km, em)
        if f0_nah and abst < MIN_MERKMAL_ABSTAND:
            return False, (f"zu nah an {e.get('name')}: Grundton {kf0:.0f}/{ef0:.0f} Hz, "
                           f"Merkmalsabstand {abst}"), e
        if not (kf0 and ef0) and abst < MIN_MERKMAL_ABSTAND / 2:
            return False, f"Merkmale fast gleich wie {e.get('name')} (Abstand {abst})", e
    return True, "", None


# ============================================================
# ARCHIV-SUCHE
# ============================================================

def beste_stimme(figur_merkmale: dict, reg: dict, gesperrt: set, ensemble: list,
                 rolle_typ: str = "figur", erz_profil: dict = None, lg: str = "de") -> tuple:
    """Beste passende, nicht gesperrte, unterscheidbare Archiv-Stimme.
    Mit erz_profil (Erzaehler des Werks, pipeline.trennung) gilt zusaetzlich die Abstandsregel
    F0 x VTL: zuerst Stimmen mit Status ok, dann knapp, zuletzt zu_nah (-> Korrektur nach VC).
    Rueckgabe: (name, eintrag, score) oder (None, None, bester_score)."""
    kandidaten = []
    for name, s in verfuegbar(reg, rolle_typ):
        if name in gesperrt:
            continue
        kandidaten.append((passung(figur_merkmale, s.get("merkmale")), name, s))
    kandidaten.sort(key=lambda x: -x[0])
    bester = kandidaten[0][0] if kandidaten else 0
    passend = []
    for score, name, s in kandidaten:
        if score < SCHWELLE_PASST:
            break
        ok, _, _ = unterscheidbar(dict(s, name=name), ensemble)
        if ok:
            passend.append((score, name, s))
    if not passend:
        return None, None, bester
    if not erz_profil:
        return passend[0][1], passend[0][2], passend[0][0]
    from pipeline import trennung
    rang = {"ok": 0, "knapp": 1, "unbekannt": 2, "zu_nah": 3}
    bewertet = []
    for score, name, s in passend:
        t = trennung.abstand(trennung.stimm_profil(name, lg), erz_profil)
        bewertet.append((rang.get(t["status"], 2), -score, name, s, t))
    bewertet.sort(key=lambda x: (x[0], x[1]))
    _, mscore, name, s, t = bewertet[0]
    return name, dict(s, _trennung=t), -mscore


# ============================================================
# DESIGN-PROMPT MIT ABGRENZUNG
# ============================================================

# Kinderstimmen blockt Gemini Voice Design ("blocked by safety policies", 11.10.2026).
# Wie im Hoerspiel: erwachsene Sprecher*in spielt die junge Figur.
_EN_ALTER = {"kind": "an adult voice performer with a naturally light, youthful voice, playing a young character",
             "jung": "a young adult (early twenties)",
             "mittel": "a middle-aged person (forties)", "alt": "an older person (around seventy)",
             "greis": "a very old person (over eighty)"}
_EN_TON = {"hoch": "high-pitched", "mittel": "medium-pitched", "tief": "deep, low-pitched"}
_EN_TEMPO = {"langsam": "slow, unhurried", "mittel": "natural-paced", "schnell": "quick, hurried"}
_EN_KLANG = {"warm": "warm", "kuehl": "cool", "rau": "rough", "heiser": "hoarse", "bruechig": "brittle",
             "samtig": "velvety", "nasal": "nasal", "kehlig": "throaty", "hell": "bright", "dunkel": "dark",
             "kraeftig": "strong", "duenn": "thin", "piepsig": "squeaky", "verraucht": "smoky", "klar": "clear"}
_EN_TEMP = {"ruhig": "calm", "nervoes": "nervous", "cholerisch": "irascible", "melancholisch": "melancholic",
            "verschmitzt": "mischievous", "guetig": "kindly", "streng": "stern", "herablassend": "condescending",
            "aengstlich": "timid", "albern": "silly", "feierlich": "solemn", "neugierig": "curious",
            "schlaefrig": "sleepy", "hochmuetig": "haughty", "verwirrt": "bewildered", "froehlich": "cheerful"}
_EN_AKZENT = {"britisch": "British", "schottisch": "Scottish", "irisch": "Irish", "amerikanisch": "American",
              "cockney": "Cockney", "franzoesisch": "French", "deutsch": "German"}
_EN_SICHER = {"fest": "firm and self-assured", "neutral": "", "unsicher": "hesitant and unsure"}


def design_prompt(figur: dict, ensemble: list) -> str:
    """Englische Voice-Design-Beschreibung aus dem Steckbrief + Abgrenzung
    zu allen Ensemble-Stimmen gleichen Geschlechts."""
    import re
    m = normalisieren(figur.get("merkmale"))
    basis = (figur.get("stimm_beschreibung_en") or "").strip()
    # Kinder-/Altersangaben aus LLM-Text fuehren zur Sperre -> dann aus Merkmalen bauen
    if m["alter"] == "kind" or re.search(r"\b(child|kid|girl|boy|\d+[- ]year[- ]old|teen|young lad|little)\b", basis, re.I):
        basis = ""
    teile = []
    if not basis:
        wer = _EN_ALTER[m["alter"]]
        teile.append(f"{wer}, {'female' if m['geschlecht'] == 'w' else 'male' if m['geschlecht'] == 'm' else 'androgynous'}.")
        if m["alter"] == "kind":
            teile.append("Adult performer; do not imitate a real child.")
        teile.append(f"{_EN_TON[m['tonlage']].capitalize()} voice"
                     + (f", {', '.join(_EN_KLANG.get(k, k) for k in m['klangfarbe'])} timbre" if m["klangfarbe"] else "") + ".")
        if m["temperament"]:
            teile.append(f"Temperament: {', '.join(_EN_TEMP.get(t, t) for t in m['temperament'])}.")
        teile.append(f"{_EN_TEMPO[m['tempo']].capitalize()} delivery"
                     + (f", {_EN_SICHER[m['sicherheit']]}" if _EN_SICHER[m['sicherheit']] else "") + ".")
        if m["akzent"]:
            teile.append(f"Accent: {_EN_AKZENT.get(m['akzent'], m['akzent'])}.")
        basis = " ".join(teile)
    abgrenzung = []
    for e in ensemble:
        em = normalisieren(e.get("merkmale"))
        if em["geschlecht"] != m["geschlecht"] and "neutral" not in (em["geschlecht"], m["geschlecht"]):
            continue
        richtung = ""
        if em["tonlage"] == m["tonlage"]:
            richtung = " (choose a clearly different pitch and timbre)"
        bes = re.sub(r"\b(child|kid|girl|boy|\d+[- ]year[- ]old|teen|little)\b", "youthful", (e.get('beschreibung') or e.get('kurz') or ''), flags=re.I)
        abgrenzung.append(f"'{e.get('figur') or e.get('name')}': {bes[:160]}{richtung}")
    text = basis + " Natural audiobook character voice, believable, never cartoonish or over-acted."
    if figur.get("ck_notiz"):   # Regie-Notiz von CK nach abgelehnter Probe (hat Vorrang)
        text += f" DIRECTOR'S NOTE (highest priority, previous attempt was rejected): {figur['ck_notiz']}."
    if abgrenzung:
        text += (" It must sound CLEARLY DISTINGUISHABLE from these other voices in the same cast: "
                 + "; ".join(abgrenzung) + ".")
    return text[:1500]


# ============================================================
# AUDIO-HELFER
# ============================================================

def grundton(wav_pfad: str) -> float:
    """Median-Grundton (Hz) per Autokorrelation. 0.0 wenn nicht messbar."""
    try:
        import numpy as np
        with wave.open(wav_pfad) as w:
            sr = w.getframerate()
            x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(float)
        fr, hop = int(0.04 * sr), int(0.02 * sr)
        lo, hi = int(sr / 400), int(sr / 60)
        res = []
        for i in range(0, len(x) - fr, hop):
            s = x[i:i + fr]
            s = s - s.mean()
            if np.sqrt((s ** 2).mean()) < 500:
                continue
            c = np.correlate(s, s, "full")[fr - 1:]
            k = lo + int(np.argmax(c[lo:hi]))
            if c[k] > 0.3 * c[0]:
                res.append(sr / k)
        return float(np.median(res)) if res else 0.0
    except Exception:
        return 0.0


def _wav_aus_b64(b64: str, pfad: str, rate: int = 24000) -> None:
    import base64
    pcm = base64.b64decode(b64)
    if pcm[:4] == b"RIFF":
        with open(pfad, "wb") as f:
            f.write(pcm)
        return
    with wave.open(pfad, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)


# ============================================================
# DESIGN + ARCHIVIEREN (kostet API, belegt einen Platz)
# ============================================================

def neu_designen(name: str, figur: dict, ensemble: list, muster: dict, werk: str) -> dict:
    """Legt eine Stimme per Gemini Voice Design an, erzeugt Muster (EN+DE),
    misst den Grundton und traegt sie als 'kandidat' ins Register ein.
    muster = {"en": text, "de": text}"""
    import requests
    from pipeline import tts_client

    reg = laden()
    if belegte_plaetze(reg) >= MAX_STIMMEN - 5:
        raise RuntimeError(f"Stimmen-Limit fast erreicht ({belegte_plaetze(reg)}/{MAX_STIMMEN}).")
    m = normalisieren(figur.get("merkmale"))
    beschreibung = design_prompt(figur, ensemble)
    voice = {
        "model": config.MODELS.get("tts", "gemini-3.8-flash-tts"),
        "type": "prompted",
        "display_name": name[:60],
        "gender": {"w": "female", "m": "male"}.get(m["geschlecht"], "neutral"),
        "language_code": "en-GB",
        "prompted": {"input": beschreibung},
    }
    r = requests.post("https://generativelanguage.googleapis.com/v1beta/voices",
                      headers={"x-goog-api-key": config.GEMINI_API_KEY, "Content-Type": "application/json"},
                      json={"store": True, "voice": voice}, timeout=180)
    if r.status_code >= 400:
        raise RuntimeError(f"Voice Design {r.status_code}: {r.text[:300]}")
    d = r.json()
    vid = d.get("id") or d.get("name", "").split("/")[-1]
    ordner = os.path.join(STIMMEN_DIR, name)
    os.makedirs(ordner, exist_ok=True)
    probe = (d.get("sample_audio") or d.get("sampleAudio") or {}).get("data")
    if probe:
        _wav_aus_b64(probe, os.path.join(ordner, "hoerprobe.wav"))
    for lg, text in (muster or {}).items():
        if text:
            tts_client.synthesize_wav(text, "", os.path.join(ordner, f"muster_{lg}.wav"), vid, LANG_CODES.get(lg))
    f0 = grundton(os.path.join(ordner, "muster_en.wav")) or grundton(os.path.join(ordner, "hoerprobe.wav"))
    eintrag = {
        "id": vid,
        "status": "kandidat",
        "rolle_typ": figur.get("rolle_typ", "figur"),
        "merkmale": m,
        "beschreibung": beschreibung,
        "kurz": figur.get("kurz", ""),
        "grundton_hz": round(f0, 1),
        "einsatz": figur.get("einsatz", ""),
        "werke": [{"werk": werk, "figur": figur.get("name")}],
        "werkzeug": f"Gemini Voice Design {voice['model']}",
        "language_code": "en-GB",
        "datum": time.strftime("%Y-%m-%d"),
        "letzte_nutzung": time.strftime("%Y-%m-%d"),
        "ttl": "1 Jahr ab letzter Nutzung",
    }
    with open(os.path.join(ordner, "steckbrief.json"), "w", encoding="utf-8") as f:
        json.dump(dict(eintrag, name=name, figur_steckbrief=figur), f, ensure_ascii=False, indent=1)
    reg = laden()
    reg[name] = eintrag
    speichern(reg)
    return eintrag


def nutzung_vermerken(name: str, werk: str, figur: str) -> None:
    reg = laden()
    s = reg.get(name)
    if not s:
        return
    s["letzte_nutzung"] = time.strftime("%Y-%m-%d")
    werke = s.setdefault("werke", [])
    if not any(w.get("werk") == werk and w.get("figur") == figur for w in werke):
        werke.append({"werk": werk, "figur": figur})
    speichern(reg)


def eindeutiger_name(basis: str, reg: dict) -> str:
    import re
    b = re.sub(r"[^a-z0-9]+", "_", basis.lower()).strip("_")[:40] or "stimme"
    name, i = b, 2
    while name in reg or os.path.exists(os.path.join(STIMMEN_DIR, name)):
        name, i = f"{b}_{i}", i + 1
    return name
