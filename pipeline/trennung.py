"""
READ LAYER — Hoerbare Trennung Figur <-> Erzaehler (Regel F0 x VTL, gemessen 16.10.2026)
=========================================================================================
Grundlage: Messung an Ruf der Wildnis (77 Rede-Spannen, Chatterbox-VC). Ergebnis in
stimmen_archiv/_trennungsregel.json (versioniert; Neueichung nur Admin ueber pipeline/s540_trennung.py --eichen).
Die Pruefung am fertigen Hoerspiel macht Stage 540 (ECAPA einzige Gate-Metrik, D nur Anzeige).

Befunde, die diese Regel begruenden
  * Gemessen wird gegen den Erzaehler DES WERKS (Endfassung audio_final/ aus 530), nicht gegen
    seine Archiv-Hoerprobe: herr_a im Archiv und herr_a im Werk sind fuer ECAPA verschiedene Sprecher.
  * D = sqrt((dF0/skala_f0)^2 + (dVTL/skala_vtl)^2) zwischen Zielstimme und Erzaehler
    sagte das Ergebnis am fertigen Overlay 5/5 richtig voraus (ECAPA + pyannote).
    Skalen = typischer Unterschied zweier Aufnahmen DERSELBEN Archivstimme; Schwelle = EER an
    105 Gleich- / 5355 Verschieden-Paaren. D >= D_ziel (25 % Reserve) = sicher.
  * Tonhoehe allein aendert die Sprecheridentitaet kaum (ECAPA unveraendert). Wirksam ist der Formantfaktor
    (pipeline/s510_hoerspiel_hybrid.korrigieren), Tonhoehe nur als Zugabe.
  * Geeicht an Chatterbox-VC; 510 erzeugt Gemini-Takes direkt -> Regel fuer Gemini neu eichen (540 --eichen).

Status je Figur: ok (D >= D_ziel) | knapp (D_schwelle..D_ziel) | zu_nah (< D_schwelle)
"""
import hashlib
import json
import os
import random

import numpy as np

from config import config

STIMMEN_DIR = getattr(config, "STIMMEN_DIR", os.path.join(config.BASE_DIR, "stimmen_archiv"))
REGEL_PFAD = os.path.join(STIMMEN_DIR, "_trennungsregel.json")
PROFIL_PFAD = os.path.join(STIMMEN_DIR, "_praat_profile.json")
SR = 24000
C_SCHALL = 35000.0
_REGEL_STANDARD = {"version": 1, "stand": "aus call-of-the-wild_de (Standard im Code)",
                   "skala_f0_ht": 1.438, "skala_vtl_ht": 0.445, "D_schwelle": 3.244, "D_ziel": 4.06,
                   "stueck": {"skala_f0_ht": 2.725, "skala_vtl_ht": 0.65, "D_schwelle": 2.566},
                   "ecapa": {"stueck": {"schwelle_cosdist": 0.609, "eer": 0.025},
                             "clip": {"schwelle_cosdist": 0.599, "eer": 0.086}}}


def _json_atomar(pfad, obj):
    tmp = pfad + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, pfad)


def regel() -> dict:
    """Trennungsregel mit Version (Datei ohne Version = Version 1); fehlende Teile aus dem Standard."""
    try:
        with open(REGEL_PFAD, encoding="utf-8") as f:
            r = json.load(f)
    except Exception:
        r = {}
    out = dict(_REGEL_STANDARD)
    out.update(r)
    out["version"] = int(r.get("version") or 1)
    return out


# ------------------------------------------------------------------ Messung (Parselmouth)

def _lade(pfad):
    import soundfile as sf
    x, sr = sf.read(pfad, dtype="float32", always_2d=False)
    if x.ndim > 1:
        x = x.mean(axis=1)
    if sr != SR:
        n = int(round(len(x) * SR / sr))
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype("float32")
    return x


def praat_merkmale(x):
    """F0 zweistufig (Hirst: 0.75*q25..1.5*q75), Formanten fest bis 5500 Hz in kraeftigen stimmhaften
    Rahmen mit plausiblen Werten, VTL aus Formantabstand F1-F4 (Reby & McComb), HNR, CPPS."""
    import parselmouth
    from parselmouth.praat import call
    snd = parselmouth.Sound(np.asarray(x, np.float64), SR)
    r = {"dauer": round(len(x) / SR, 3)}
    p1 = snd.to_pitch_ac(time_step=0.01, pitch_floor=60, pitch_ceiling=600).selected_array["frequency"]
    if (p1 > 0).sum() < 8:
        r["stimmhaft_s"] = 0
        return r
    q25, q75 = np.percentile(p1[p1 > 0], [25, 75])
    lo, hi = max(50, 0.75 * q25), min(800, 1.5 * q75)
    pitch = snd.to_pitch_ac(time_step=0.01, pitch_floor=lo, pitch_ceiling=hi)
    f0 = pitch.selected_array["frequency"]; zeiten = pitch.xs(); v = f0 > 0
    r["stimmhaft_s"] = round(v.sum() * 0.01, 2)
    if v.sum() < 8:
        return r
    r["f0_hz"] = round(float(np.median(f0[v])), 1)
    inten = snd.to_intensity(minimum_pitch=max(lo, 60), time_step=0.01)
    tv = zeiten[v]
    iv = np.array([inten.get_value(t) for t in tv], float)
    tv = tv[np.nan_to_num(iv, nan=-1e9) >= np.nanpercentile(iv, 40)]
    decke = 5500
    fo = snd.to_formant_burg(time_step=0.01, max_number_of_formants=5, maximum_formant=decke,
                             window_length=0.025, pre_emphasis_from=50)
    F = np.array([[fo.get_value_at_time(i, t) for t in tv] for i in range(1, 5)], dtype=float)
    k = decke / 5000.0
    baender = [(200 * k, 1100 * k), (550 * k, 2900 * k), (1600 * k, 3800 * k), (2600 * k, 4900 * k)]
    gut = np.all([(F[i] >= a) & (F[i] <= b) for i, (a, b) in enumerate(baender)], axis=0)
    if gut.sum() >= 10:
        med = np.median(F[:, gut], axis=1)
        kk = np.array([0.5, 1.5, 2.5, 3.5])
        dF = float((med * kk).sum() / (kk * kk).sum())
        r.update(F=[round(float(m)) for m in med], vtl_cm=round(C_SCHALL / (2 * dF), 2))
    try:
        h = call(snd, "To Harmonicity (cc)", 0.01, max(lo, 60), 0.1, 1.0).values
        h = h[h > -100]
        r["hnr_db"] = round(float(np.mean(h)), 2) if h.size else None
    except Exception:
        pass
    return r


def _profile():
    try:
        with open(PROFIL_PFAD, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def stimm_profil(name: str, lg: str = "de") -> dict:
    """Profil einer Archivstimme: muster_<lg> + hoerprobe (+ Muster der uebrigen Sprachen der Sprachliste,
    falls < 4 s stimmhaft). Einzelne Muster sind oft < 2 s -> VTL zu unsicher (Pruefrunde 2, Perrault/Malcolm)."""
    alle = _profile()
    if alle.get(name, {}).get(lg):
        return alle[name][lg]
    andere = [x for x in getattr(config, "SPRACHLISTE", ("en", "de")) if x != lg]
    reihen = [f"muster_{lg}.wav", "hoerprobe.wav"] + [f"muster_{x}.wav" for x in andere]
    try:
        teile, quellen, p = [], [], {}
        for d in reihen:
            pfad = os.path.join(STIMMEN_DIR, name, d)
            if not os.path.exists(pfad):
                continue
            teile.append(_lade(pfad)); quellen.append(d)
            p = praat_merkmale(np.concatenate(teile))
            if p.get("stimmhaft_s", 0) >= 4 and p.get("vtl_cm"):
                break
    except ImportError:
        print("  [trennung] parselmouth fehlt -> py -3.11 -m pip install praat-parselmouth soundfile")
        return {}
    if not teile:
        return {}
    p["quelle"] = "+".join(quellen)
    alle.setdefault(name, {})[lg] = p
    _json_atomar(PROFIL_PFAD, alle)
    return p


def erzaehler_profil(werk_dir: str, lg: str, stimme: str = None, sekunden: float = 90, kapitel=None) -> dict:
    """Erzaehler gemessen an der Endfassung des Werks (fassungen/<lg>/audio_final aus 530), nur Saetze ohne
    Figurenrede laut work/420_sprecher.json. Ohne Endfassung (< 10 Saetze): Archiv-Muster der Erzaehlerstimme
    (unsicher). Cache work/erzaehler_profil_<lg>.json gilt nur bei gleichem Hash (Satzauswahl, Dateien, Stimme).
    kapitel (22.10.2026): nur diese Kapitel (Ich-Erzaehler je Kapitel)."""
    adir = os.path.join(werk_dir, "fassungen", lg, "audio_final")
    sp = {}
    try:
        with open(os.path.join(werk_dir, "work", "420_sprecher.json"), encoding="utf-8") as f:
            sp = json.load(f).get("saetze") or {}
    except Exception:
        pass
    tags = sorted(f[:-4] for f in os.listdir(adir) if f.endswith(".wav")) if os.path.isdir(adir) else []
    tags = [t for t in tags if all(s.get("s") == "Erzaehler"
                                   for s in (((sp.get(t) or {}).get(lg) or {}).get("seg") or []))]
    if kapitel:
        tags = [t for t in tags if t[:4] in kapitel]
    if len(tags) < 10:
        return dict(stimm_profil(stimme, lg) if stimme else {}, quelle="archiv (keine Endfassung - unsicher)",
                    stimme=stimme)
    h = hashlib.sha256(json.dumps([[t, os.path.getsize(os.path.join(adir, t + ".wav"))] for t in tags]
                                  + [stimme, sekunden, sorted(kapitel or [])]).encode()).hexdigest()[:20]
    cache = os.path.join(werk_dir, "work", f"erzaehler_profil_{lg}.json")
    try:
        with open(cache, encoding="utf-8") as f:
            c = json.load(f)
        if c.get("hash") == h:
            return c
    except Exception:
        pass
    random.Random(57).shuffle(tags)
    teile, dauer = [], 0.0
    for t in tags:
        x = _lade(os.path.join(adir, t + ".wav"))
        teile.append(x); dauer += len(x) / SR
        if dauer >= sekunden:
            break
    try:
        p = praat_merkmale(np.concatenate(teile))
    except ImportError:
        print("  [trennung] parselmouth fehlt -> py -3.11 -m pip install praat-parselmouth soundfile")
        return {}
    p.update(quelle=f"werk fassungen/{lg}/audio_final ({len(teile)} Saetze)", stimme=stimme, hash=h)
    try:
        _json_atomar(cache, p)
    except OSError:
        pass
    return p


# ------------------------------------------------------------------ Regel

def abstand(fig: dict, erz: dict, R: dict = None) -> dict:
    R = R or regel()
    if not (fig.get("f0_hz") and erz.get("f0_hz")):
        return {"status": "unbekannt", "grund": "kein Profil"}
    dF = 12 * np.log2(fig["f0_hz"] / erz["f0_hz"])
    dV = 12 * np.log2(fig["vtl_cm"] / erz["vtl_cm"]) if fig.get("vtl_cm") and erz.get("vtl_cm") else 0.0
    D = float(np.hypot(dF / R["skala_f0_ht"], dV / R["skala_vtl_ht"]))
    status = "ok" if D >= R["D_ziel"] else ("knapp" if D >= R["D_schwelle"] else "zu_nah")
    return {"D": round(D, 2), "dF0_ht": round(float(dF), 2), "dVTL_proz": round(100 * (2 ** (dV / 12) - 1), 1),
            "status": status, "D_schwelle": R["D_schwelle"], "D_ziel": R["D_ziel"]}


def richtung(steckbrief_merkmale: dict, fig: dict = None, erz: dict = None) -> int:
    """-1 = groesser/dunkler (Formante runter, Ton tiefer), +1 = kleiner/heller.
    Vorrang hat die GEMESSENE Lage: weg vom Erzaehler auf der VTL-Achse (Pruefrunde 2, 16.10.2026:
    Francois wurde nach Steckbrief 'groesser' gemacht, lag aber gemessen kuerzer als der Erzaehler ->
    ECAPA-Abstand fiel von 0,71 auf 0,53). Steckbrief nur, wenn die VTL-Differenz < 2 % ist."""
    if fig and erz and fig.get("vtl_cm") and erz.get("vtl_cm"):
        d = fig["vtl_cm"] / erz["vtl_cm"] - 1
        if abs(d) >= 0.02:
            return -1 if d > 0 else +1
    m = steckbrief_merkmale or {}
    if m.get("alter") in ("alt", "greis") or m.get("tonlage") == "tief" or "kraeftig" in (m.get("klangfarbe") or []):
        return -1
    if m.get("alter") in ("kind", "jung") or m.get("tonlage") == "hoch" or m.get("geschlecht") == "w":
        return +1
    if fig and erz and fig.get("f0_hz") and erz.get("f0_hz"):
        return -1 if fig["f0_hz"] < erz["f0_hz"] else +1
    return +1


# Natuerlichkeitsgrenzen (CK 16.10.2026: -3 HT + Formant 0,9 klang wie ein Stimmverzerrer).
# Tonhoehe allein trennt kaum (ECAPA unveraendert) -> Standard 0 HT; Formant ist der Hebel.
FORMANT_MAX = 1.10      # kleiner/heller (gemessen Perrault: 1,10 ohne Tonhoehe -> ECAPA 0,40 -> 0,67)
FORMANT_MIN = 0.94      # groesser/dunkler: Absenken klingt schneller kuenstlich
TONHOEHE_MAX_HT = 2
# Korrekturstufen je Richtung bis zur Natuerlichkeitsgrenze (Nachrunde 540: eine Stufe weiter)
STUFEN = {+1: [1.05, FORMANT_MAX], -1: [0.97, FORMANT_MIN]}


def korrektur_vorschlag(status: str, r: int) -> dict:
    """knapp -> leichte Formantkorrektur; zu_nah -> bis an die Natuerlichkeitsgrenze, ohne Tonhoehe.
    Reicht die Grenze nach der Pruefung am Hoerspiel (540) nicht: andere Stimme waehlen statt staerker verbiegen."""
    if status == "ok":
        return {}
    if r > 0:
        ff = STUFEN[+1][0] if status == "knapp" else FORMANT_MAX
    else:
        ff = STUFEN[-1][0] if status == "knapp" else FORMANT_MIN
    k = {"formant_faktor": ff, "tonhoehe_ht": 0, "grund": f"Trennung {status}",
         "pruefen": "Stage 540 misst am fertigen Hoerspiel (ECAPA/pyannote); reicht es nicht -> umbesetzen (410)"}
    if status == "zu_nah" and r < 0:
        k["hinweis"] = "Absenkung an der Natuerlichkeitsgrenze - Umbesetzung wahrscheinlich noetig"
    return k
