"""STAGE 540 — Trennung Figur <-> Erzaehler (Phase 2, 03.11.2026, GATE_KATALOG.md Zeile 540)
Funktion:     Prueft je Hoerspiel-Sprache und besetzter Figur, ob die Figurenstuecke der fertigen Hoerspielspur hoerbar
              vom Erzaehler DES WERKS getrennt sind (ECAPA-Kosinusabstand der Sprecher-Embeddings) und naeher an der
              Zielstimme (Figuren-Takes 510, sonst Archivmuster) liegen als am Erzaehler. Kontrolle: die Hoerbuchspur
              muss fuer pyannote EIN Sprecher sein. D (F0 x VTL, Praat) und pyannote-Anteil je Figur nur Anzeige.
Wirkungsweise: Figurenstuecke aus hoerspiel_final/ (530): Satz-Segmente 420 -> Lesetext-Token (400-Abbildung) ->
              Wortzeiten 520_wortzeiten_<lg>_hoerspiel; ohne Wortzeiten anteilig aus dem Schnittprotokoll 510. Erzaehler
              = Saetze ohne Figurenrede aus audio_final/. Messpaket work/_540/<lg>/paket -> ECAPA + pyannote auf Modal
              (T4, gpu_messung/messung_modal.py) oder CPU (gpu_messung/messung_gpu.py), Praat lokal. Eingangs-Hash je
              Sprache: unveraenderte Eingaenge -> keine neue Messung (0 $). Nicht getrennt und Formantgrenze nicht
              erreicht -> 1x automatisch Nachrunde: Korrektur eine Stufe weiter (casting.json mit Protokoll), 510 -> 530
              -> 520 bauen nur die betroffenen Saetze neu (Hash), dann neue Messung.
Eingang:      work/510_overlay.json (Schnittprotokoll, Figuren je Satz), work/530_pruefung_<lg>.json + hoerspiel_final/ und
              audio_final/, work/520_wortzeiten_<lg>_hoerspiel.json, work/420_sprecher.json, work/400_regie.json,
              work/casting.json (Schema 2 freigegeben: Erzaehler, Ensemble, Korrekturstufe), Takes work/_510/<lg>/takes/,
              stimmen_archiv/_trennungsregel.json (Regel mit Version).
Ausgabe:      work/540_trennung_<lg>.json (je Figur ECAPA, D, pyannote, Runde, Urteil, Hoerproben), work/_540/<lg>/
              (Paket, Messergebnis, Hoerproben), work/540_entscheidungen.json (Annahmen, Nachrunden-Zaehler).
              casting.json nur Korrekturstufe mit Protokoll (keine Pruefergebnisse).
Gate:         je Figur x Sprache: Hoerspiel bestellt, Gates 410/420/510/530/520 frei, Casting freigegeben, Endfassung
              aktuell, Korrektur 510 = casting, Werkzeuge (Praat, Modal bzw. speechbrain/pyannote, HF_TOKEN) -> sonst
              Stopp; Messfehler -> 1x automatisch neu, dann Stopp; ECAPA >= Schwelle (Regel, 0,599) und naeher an der
              Zielstimme -> auto; sonst Nachrunde (1x), danach bzw. an der Grenze -> Mensch (umbesetzen -> 410 /
              annehmen); Erzaehler-Kontrolle > 1 Sprecher -> Mensch (500); Redezeit < Mindestwert -> Hinweis.
              Mensch-Freigabe gilt bei gleichem ausgabe_hash.
Kosten:       usage_log Stage 540 (Modal-T4-Sekunden je Sprache, ~0,03 $); Praat/CPU 0 $.
Regler:       book.json trennung_regler: --messung modal|cpu, --ecapa-min, --redezeit-min, --nachrunde an|aus,
              --erzaehler-s, --spur-max-s; dazu --korrektur FIGUR:LG=F[,HT]|weg --grund (Korrekturstufe manuell, baut
              510 -> 530 -> 520 neu), --annehmen FIGUR:LG --grund (trotz Befund, Protokoll), --neu (Messung neu),
              --lang, --trocken, --eichen LG (Regel neu eichen, nur Admin, neue Regelversion).
Aufruf:       py -3.11 -m pipeline.s540_trennung <werk> [Regler] [--wer CK]
Exit: 0 auto, 2 Stopp, 3 Mensch, 1 Fehler.
"""
import argparse
import collections
import io
import itertools
import json
import os
import random
import shutil
import subprocess
import sys
import time
import zipfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from config import config
from pipeline import bestellung, gate, manifest, mock, status, trennung, usage_log
from pipeline import s410_casting as s410
from pipeline import s420_sprecher as s420
from pipeline import s510_hoerspiel_hybrid as s510
from pipeline import s520_wortzeiten as s520
from pipeline import s525_wortbruecke as s525

STAGE = "540"
VERSION = 1
SR = 24000
ERZ = s420.ERZ
REGLER_STD = {"messung": "modal", "ecapa_min": None, "redezeit_min": 3.0, "nachrunde": True,
              "erzaehler_s": 90.0, "spur_max_s": 1800.0}
STUECK_MIN_S = 0.3          # kuerzere Figurenstuecke gehen nicht in die Messung
ZIEL_MAX_S = 30.0           # Zielstimme: hoechstens so viel Take-Audio
KONTROLLE_ANTEIL = 0.05     # pyannote-Sprecher zaehlt erst ab 5 % der Kontrollspur (und >= 2 s)
USD_JE_SPRACHE = 0.03


class MessFehler(RuntimeError):
    pass


# ============================================================ Ablage
def pfad(werk, lg):
    return config.work_path(werk, f"540_trennung_{lg}")


def entsch_pfad(werk):
    return config.work_path(werk, "540_entscheidungen")


def arbeit_dir(werk, lg):
    return os.path.join(config.work_dir(werk), "_540", lg)


def _json(p, leer=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return leer


def entscheidungen(werk):
    d = _json(entsch_pfad(werk), {}) or {}
    d.setdefault("annahmen", {})
    d.setdefault("nachrunden", {})
    d.setdefault("protokoll", [])
    return d


def _entsch_schreiben(werk, d):
    manifest.json_atomar(entsch_pfad(werk), d, indent=1)


def annehmen(werk, figur, lg, wer, grund):
    """Figur trotz Befund annehmen – gilt, solange Stimme und Korrekturstufe gleich bleiben."""
    if not grund:
        raise ValueError("grund ist Pflicht")
    e = _ensemble(s410.laden(werk), lg).get(figur)
    if not e:
        raise ValueError(f"Figur {figur!r} in {lg} nicht im Ensemble")
    d = entscheidungen(werk)
    d["annahmen"][f"{lg}/{figur}"] = {"stimme": e.get("stimme"), "korrektur": _korr(e), "wer": wer,
                                      "wann": status.jetzt(), "grund": grund}
    d["protokoll"].append({"wann": status.jetzt(), "wer": wer, "aktion": "annehmen", "figur": figur, "sprache": lg,
                           "grund": grund})
    _entsch_schreiben(werk, d)


def korrektur(werk, figur, lg, formant, tonhoehe, wer, grund):
    """Korrekturstufe manuell (casting.json mit Protokoll, ueber 410); Nachrunden-Zaehler der Figur zurueck."""
    s410.korrektur_setzen(werk, figur, lg, formant=formant, tonhoehe=tonhoehe, wer=wer, grund=f"540: {grund}")
    d = entscheidungen(werk)
    d["nachrunden"].pop(f"{lg}/{figur}", None)
    d["protokoll"].append({"wann": status.jetzt(), "wer": wer, "aktion": "korrektur", "figur": figur, "sprache": lg,
                           "formant": formant, "tonhoehe": tonhoehe, "grund": grund})
    _entsch_schreiben(werk, d)


# ============================================================ Regler / Werkzeuge
def _regler(roh):
    rg = dict(REGLER_STD)
    rg.update({k: v for k, v in (roh.get("trennung_regler") or {}).items() if k in REGLER_STD})
    return rg


def _regler_gueltig(rg):
    try:
        return (rg["messung"] in ("modal", "cpu") and (rg["ecapa_min"] is None or 0 < float(rg["ecapa_min"]) < 2)
                and 0 <= float(rg["redezeit_min"]) <= 60 and isinstance(rg["nachrunde"], bool)
                and 10 <= float(rg["erzaehler_s"]) <= 600 and 60 <= float(rg["spur_max_s"]) <= 7200)
    except (KeyError, TypeError, ValueError):
        return False


def hf_token():
    tok = os.environ.get("HF_TOKEN", "")
    env = os.path.join(ROOT, ".env")
    if not tok and os.path.exists(env):
        with open(env, encoding="utf-8") as f:
            for z in f:
                if z.strip().startswith("HF_TOKEN="):
                    tok = z.split("=", 1)[1].strip().strip('"')
    return tok


def _modul_da(name):
    import importlib.util as iu
    try:
        return iu.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def werkzeuge_pruefen(art):
    """-> Liste fehlender Werkzeuge (leer = alles da). Vor jeder Messung (Befund 540 (7)/(10))."""
    fe = []
    if not _modul_da("parselmouth"):
        fe.append("parselmouth fehlt (py -3.11 -m pip install praat-parselmouth)")
    if art == "modal":
        if not _modul_da("modal"):
            fe.append("modal fehlt")
    else:
        for m in ("torch", "torchaudio", "speechbrain", "pyannote.audio"):
            if not _modul_da(m):
                fe.append(f"{m} fehlt (CPU-Messung)")
    if not hf_token():
        fe.append("HF_TOKEN fehlt (.env) – pyannote braucht ihn")
    return fe


# ============================================================ Casting
def _ensemble(c, lg, stufe=None):
    je = ((c or {}).get("rollen") or {}).get(lg) or {}
    bs = je.get(stufe) if stufe else (je[sorted(je)[0]] if je else None)
    return {e["figur"]: e for e in (bs or {}).get("ensemble") or [] if e.get("figur")}


def _korr(e):
    k = (e or {}).get("korrektur") or {}
    return {"formant_faktor": float(k.get("formant_faktor", 1.0)), "tonhoehe_ht": float(k.get("tonhoehe_ht", 0.0))}


def _stufe_weiter(ff, r):
    weiter = [s for s in trennung.STUFEN[r] if (s > ff + 1e-6 if r > 0 else s < ff - 1e-6)]
    return weiter[0] if weiter else None


# ============================================================ Figurenstuecke in der Endfassung
def _seg_spans(segs, text):
    """Zeichenspannen der 420-Segmente im Text (Leerraum-unabhaengig) oder None, wenn sie den Text nicht ergeben."""
    idx = [i for i, ch in enumerate(text or "") if not ch.isspace()]
    if "".join(text[i] for i in idx) != "".join(ch for g in segs for ch in g["t"] if not ch.isspace()):
        return None
    out, j = [], 0
    for g in segs:
        n = sum(1 for ch in g["t"] if not ch.isspace())
        out.append((idx[j], idx[j + n - 1] + 1) if n else None)
        j += n
    return out


def regionen(segs, besetzt, lese, sprech, abb, tags, dauer, prot=None, pad=0.05):
    """-> ([{q, t0, t1}], quelle) Sprecherregionen (q = Figur oder Erzaehler) in Sekunden der Endfassung.
    Segmente 420 -> Lesetext-Spannen (direkt oder ueber die 400-Abbildung) -> \\S+-Token -> Wortzeiten 520;
    ohne Wortzeiten anteilig aus dem Schnittprotokoll 510 (Stuecklaengen auf die Enddauer skaliert)."""
    qs = [g["s"] if g["s"] in besetzt else ERZ for g in segs]
    lspan = _seg_spans(segs, lese)
    if lspan is None:
        sp = _seg_spans(segs, sprech)
        if sp is not None:
            karte = s520.lese_karte(sprech, abb)
            lspan = []
            for x in sp:
                ks = karte[x[0]:x[1]] if x else []
                lspan.append((min(k[0] for k in ks), max(k[1] for k in ks)) if ks else None)
    if lspan is not None and tags:
        zeit = {int(e["i"]): (float(e["t0"]), float(e["t1"])) for e in tags}
        runs = []
        for i, (c0, c1) in enumerate(s525.token_spans(lese)):
            if i not in zeit:
                continue
            best, bw = None, 0
            for k, x in enumerate(lspan):
                if x and min(c1, x[1]) - max(c0, x[0]) > bw:
                    best, bw = k, min(c1, x[1]) - max(c0, x[0])
            if best is None:
                continue
            a, b = zeit[i]
            if runs and runs[-1][0] == qs[best]:
                runs[-1][2] = max(runs[-1][2], b)
            else:
                runs.append([qs[best], a, b])
        if runs:
            ende = float(dauer) if dauer else runs[-1][2] + pad
            out = []
            for n, (q, a, b) in enumerate(runs):
                a2 = max(a - pad, (runs[n - 1][2] + a) / 2) if n else max(0.0, a - pad)
                b2 = min(b + pad, (b + runs[n + 1][1]) / 2) if n + 1 < len(runs) else min(ende, b + pad)
                out.append({"q": q, "t0": round(max(0.0, a2), 3), "t1": round(min(ende, b2), 3)})
            return out, "wortzeiten"
    if prot and dauer:
        tot = sum(max(0.0, float(p["b"]) - float(p["a"])) for p in prot)
        if tot > 0:
            f, t, out = float(dauer) / tot, 0.0, []
            for p in prot:
                ln = max(0.0, float(p["b"]) - float(p["a"])) * f
                q = ERZ if p["q"] == "erz" else p["q"]
                if out and out[-1]["q"] == q:
                    out[-1]["t1"] = round(t + ln, 3)
                else:
                    out.append({"q": q, "t0": round(t, 3), "t1": round(t + ln, 3)})
                t += ln
            return out, "schnitt"
    return [], None


# ============================================================ Planung je Sprache
def plan_sprache(werk, lg, stufe, c, data, spr, m510, rg):
    """-> Plan (Eingaenge, Stuecke, Spuren, Eingangs-Hash) oder Plan mit 'fehler' [(name, text, ruecksprung)]."""
    p = {"lg": lg, "stufe": stufe, "fehler": [], "hinweise": []}
    bs = (((c or {}).get("rollen") or {}).get(lg) or {}).get(stufe) or {}
    erz_stimme = (bs.get("erzaehler") or {}).get("stimme")
    ens = _ensemble(c, lg, stufe)
    p.update(erz_stimme=erz_stimme, ens=ens)
    m530 = manifest.Manifest(werk, f"530_pruefung_{lg}", stage="530")
    w520 = (_json(s520.pfad(werk, lg, "hoerspiel"), {}) or {}).get("tags") or {}
    texte = s520.saetze_text(data, lg)
    # Korrektur 510 = casting (sonst ist die Hoerspielspur veraltet)
    fig510 = ((m510.meta.get("je_sprache") or {}).get(lg) or {}).get("figuren") or {}
    abw = [f for f, x in fig510.items() if f in ens and _korr({"korrektur": x.get("korrektur")}) != _korr(ens[f])]
    if abw:
        p["fehler"].append((f"korrektur_{lg}", f"{lg}: Korrekturstufe in casting.json neuer als die Hoerspielspur 510 "
                                               f"({', '.join(sorted(abw))}) – 510 -> 530 -> 520 neu", "510"))
    hs, stuecke, fehlt, mocks, quellen = [], [], [], 0, collections.Counter()
    fig_saetze = collections.defaultdict(list)
    for k in sorted(m510.eintraege):
        if not k.startswith(f"{lg}/"):
            continue
        tid, e = k.split("/", 1)[1], m510.eintraege[k]
        if e.get("q") not in ("neu", "mock"):            # Erzaehlerfassung/behalten: keine Figurenstimme im Satz
            continue
        k5 = f"hoerspiel/{tid}"
        e5 = m530.get(k5) or {}
        if not e5 or not m530.datei_aktuell(k5):
            fehlt.append(tid)
            continue
        w = m530._abs(e5["datei"])
        if mock.ist_datei(w):
            mocks += 1
        segs = ((spr.get(tid) or {}).get(lg) or {}).get("seg") or []
        lese, sprech, abb = texte.get(tid, ("", "", []))
        regs, quelle = regionen(segs, ens, lese, sprech, abb, w520.get(tid), e5.get("dauer"), e.get("schnitt"))
        quellen[quelle or "keine"] += 1
        hs.append({"tid": tid, "wav": w, "h": e5.get("datei_hash"), "reg": regs})
        for r in regs:
            if r["q"] != ERZ and r["q"] in ens:
                fig_saetze[r["q"]].append(tid)
                if r["t1"] - r["t0"] >= STUECK_MIN_S:
                    stuecke.append({"id": f"fs__{len(stuecke):05d}", "figur": r["q"], "tid": tid, "wav": w,
                                    "t0": r["t0"], "t1": r["t1"]})
    if fehlt:
        p["fehler"].append((f"endfassung_{lg}", f"{lg}: Hoerspiel-Endfassung 530 fehlt/veraltet fuer {len(fehlt)} "
                                                f"Saetze ({', '.join(fehlt[:5])})", "530"))
    if quellen.get("schnitt"):
        p["hinweise"].append((f"wortzeiten_{lg}", f"{lg}: {quellen['schnitt']} Saetze ohne Hoerspiel-Wortzeiten 520 – "
                                                  f"Stuecke anteilig aus dem Schnittprotokoll 510"))
    # Erzaehler des Werks: Saetze ohne Figurenrede aus der Hoerbuchspur (audio_final/)
    kand = []
    for k in sorted(m530.eintraege):
        if not k.startswith("hoerbuch/"):
            continue
        tid = k.split("/", 1)[1]
        segs = ((spr.get(tid) or {}).get(lg) or {}).get("seg") or []
        if any(g.get("s") != ERZ for g in segs):
            continue
        kand.append(tid)
    random.Random(57).shuffle(kand)
    erz, dauer = [], 0.0
    for tid in kand:
        e5 = m530.get(f"hoerbuch/{tid}")
        if not m530.datei_aktuell(f"hoerbuch/{tid}"):
            continue
        d = float(e5.get("dauer") or 0) or s510.s500.wav_dauer(m530._abs(e5["datei"]))
        if d < 1.0:
            continue
        erz.append({"tid": tid, "wav": m530._abs(e5["datei"]), "h": e5.get("datei_hash")})
        dauer += d
        if dauer >= float(rg["erzaehler_s"]):
            break
    if len(erz) < 3:
        p["fehler"].append((f"erzaehler_{lg}", f"{lg}: zu wenig Erzaehler-Saetze in audio_final/ ({len(erz)})", "530"))
    # Zielstimme je Figur: Takes 510 (genau die besetzte Stimme), sonst Archivmuster
    ziel = {}
    tdir = s510.take_dir(werk, lg)
    takes = sorted(os.listdir(tdir)) if os.path.isdir(tdir) else []
    for f in sorted(fig_saetze):
        ws = [os.path.join(tdir, n) for n in takes if n.endswith(f"__{f}.wav")]
        if not ws:
            st = ens[f].get("stimme") or ""
            ws = [x for x in (os.path.join(trennung.STIMMEN_DIR, st, f"muster_{lg}.wav"),
                              os.path.join(trennung.STIMMEN_DIR, st, "hoerprobe.wav")) if os.path.exists(x)][:1]
        ziel[f] = ws
    regel = trennung.regel()
    p.update(hs=hs, stuecke=stuecke, erz=erz, ziel=ziel, mocks=mocks, quellen=dict(quellen),
             fig_saetze={f: sorted(set(v)) for f, v in fig_saetze.items()},
             korr={f: _korr(ens[f]) for f in fig_saetze})
    p["eingang_hash"] = manifest.hash_obj({
        "hs": [[x["tid"], x["h"], x["reg"]] for x in hs], "erz": [[x["tid"], x["h"]] for x in erz],
        "ziel": {f: [[os.path.basename(w), os.path.getsize(w)] for w in ws] for f, ws in ziel.items()},
        "stimmen": {f: ens[f].get("stimme") for f in fig_saetze}, "erz_stimme": erz_stimme,
        "korr": p["korr"], "spur_max": rg["spur_max_s"], "v": VERSION})
    p["regel_version"] = regel.get("version")
    return p


# ============================================================ Messung
def paket_bauen(p, d, rg):
    """Messpaket im Format von gpu_messung/messung_gpu.py; -> {id: meta}, Praat-Rohwerte."""
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(os.path.join(d, "segmente"))
    cache, man = {}, []

    def lade(w):
        if w not in cache:
            cache[w] = s510.lesen(w)
        return cache[w]

    def ab(sid, x, **meta):
        s510.schreiben(os.path.join(d, "segmente", sid + ".wav"), x)
        man.append(dict(id=sid, dauer=round(len(x) / SR, 3), **meta))

    fig_audio = collections.defaultdict(list)
    for s in p["stuecke"]:
        x = lade(s["wav"])[int(s["t0"] * SR):int(s["t1"] * SR)]
        ab(s["id"], x, typ="fs", figur=s["figur"], tid=s["tid"], t0=s["t0"], t1=s["t1"])
        fig_audio[s["figur"]].append(x)
    erz_audio = []
    for e in p["erz"]:
        x = lade(e["wav"])
        ab("en__" + e["tid"], x, typ="en", tid=e["tid"])
        erz_audio.append(x)
    for n, (f, ws) in enumerate(sorted(p["ziel"].items())):
        if ws:
            x = np.concatenate([lade(w) for w in ws])[:int(ZIEL_MAX_S * SR)]
            ab(f"ref__{n:02d}", x, typ="ref", figur=f)
    pause = np.zeros(int(0.4 * SR), "float32")
    ref = {"hs": [], "hb": []}
    for var, quelle in (("hs", p["hs"]), ("hb", p["erz"])):
        teile, t = [], 0.0
        for x_ in quelle:
            x = lade(x_["wav"])
            regs = x_.get("reg") if var == "hs" else [{"q": ERZ, "t0": 0.0, "t1": len(x) / SR}]
            for r in regs or []:
                if r["t1"] - r["t0"] > 0.05:
                    ref[var].append([round(t + r["t0"], 3), round(t + r["t1"], 3), r["q"], x_["tid"]])
            teile += [x, pause]
            t += (len(x) + len(pause)) / SR
            if t >= float(rg["spur_max_s"]):
                break
        if teile:
            s510.schreiben(os.path.join(d, f"spur_{var}.wav"), np.concatenate(teile))
    manifest.json_atomar(os.path.join(d, "spur_ref.json"), ref)
    manifest.json_atomar(os.path.join(d, "manifest.json"), {"werk": None, "lang": p["lg"], "sr": SR, "segmente": man},
                         indent=1)
    praat = {"erz": trennung.praat_merkmale(np.concatenate(erz_audio)) if erz_audio else {},
             "fig": {f: trennung.praat_merkmale(np.concatenate(xs)) for f, xs in fig_audio.items()}}
    return {s["id"]: s for s in man}, praat, ref


def gpu_messen(paket, art):
    """ECAPA + pyannote (gpu_messung/messung_gpu.py) auf Modal oder CPU -> (Ergebnisordner, Sekunden)."""
    erg = os.path.join(paket, "ergebnis")
    shutil.rmtree(erg, ignore_errors=True)
    os.makedirs(erg)
    t0 = time.time()
    if art == "modal":
        sys.path.insert(0, os.path.join(ROOT, "gpu_messung"))
        import messung_modal as mm
        daten = mm.messen([paket])[paket]
        zipfile.ZipFile(io.BytesIO(daten)).extractall(erg)
    else:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "gpu_messung", "messung_gpu.py"), paket, erg],
                           env=dict(os.environ, HF_TOKEN=hf_token()), capture_output=True, text=True)
        if r.returncode:
            raise MessFehler(f"messung_gpu: {(r.stderr or r.stdout)[-300:]}")
    return erg, time.time() - t0


def _ergebnis_lesen(erg, man):
    pe, pd = os.path.join(erg, "embeddings.npz"), os.path.join(erg, "diar.json")
    if not (os.path.exists(pe) and os.path.exists(pd)):
        raise MessFehler("Messergebnis unvollstaendig (embeddings.npz/diar.json fehlt)")
    npz = np.load(pe)
    emb = {str(i): e / (np.linalg.norm(e) or 1.0) for i, e in zip(npz["ids"], npz["emb"]) if str(i) in man}
    diar = _json(pd, {}) or {}
    if diar.get("pyannote_fehler"):
        raise MessFehler(f"pyannote: {diar['pyannote_fehler'][:200]}")
    if not any(man[i]["typ"] == "en" for i in emb):
        raise MessFehler("keine Erzaehler-Embeddings")
    return emb, diar


def messen(werk, lg, p, rg):
    """Paket bauen, Praat lokal, ECAPA/pyannote; Ergebnis bleibt unter work/_540/<lg>/paket/."""
    d = os.path.join(arbeit_dir(werk, lg), "paket")
    man, praat, ref = paket_bauen(p, d, rg)
    manifest.json_atomar(os.path.join(d, "praat.json"), praat, indent=1)
    erg, sek = gpu_messen(d, rg["messung"])
    if rg["messung"] == "modal":
        usage_log.log_gpu(werk, STAGE, sek, gpu="T4", extra={"sprache": lg})
    emb, diar = _ergebnis_lesen(erg, man)
    manifest.json_atomar(os.path.join(d, "eingang.json"), {"eingang_hash": p["eingang_hash"], "wann": status.jetzt(),
                                                           "messung": rg["messung"], "sekunden": round(sek, 1)})
    return {"man": man, "praat": praat, "ref": ref, "emb": emb, "diar": diar, "sekunden": round(sek, 1)}


def messung_laden(werk, lg, p):
    """Vorhandene Messung bei gleichem Eingangs-Hash (0 $), sonst None."""
    d = os.path.join(arbeit_dir(werk, lg), "paket")
    if (_json(os.path.join(d, "eingang.json"), {}) or {}).get("eingang_hash") != p["eingang_hash"]:
        return None
    try:
        man = {s["id"]: s for s in (_json(os.path.join(d, "manifest.json"), {}) or {}).get("segmente") or []}
        emb, diar = _ergebnis_lesen(os.path.join(d, "ergebnis"), man)
        return {"man": man, "praat": _json(os.path.join(d, "praat.json"), {}) or {},
                "ref": _json(os.path.join(d, "spur_ref.json"), {}) or {}, "emb": emb, "diar": diar, "sekunden": 0,
                "wiederverwendet": True}
    except MessFehler:
        return None


# ============================================================ Auswertung
def _mittel(vs):
    m = np.mean(vs, axis=0)
    return m / (np.linalg.norm(m) or 1.0)


def wechsel_treffer(ref, hyp, tol=0.5):
    """Sprecherwechsel Erzaehler <-> Figur laut Referenz: findet pyannote dort einen Wechsel (+-tol)? (nur Hinweis)"""
    rw = [ref[i][0] for i in range(1, len(ref)) if ref[i][2] != ref[i - 1][2] and ref[i][0] - ref[i - 1][1] < 1.5]
    hw, letzter = [], None
    for a, b, lab in sorted(hyp):
        if letzter is not None and lab != letzter and b - a > 0.2:
            hw.append(a)
        if b - a > 0.2:
            letzter = lab
    if not rw:
        return {"ref_wechsel": 0, "hyp_wechsel": len(hw), "recall": None}
    rec = float(np.mean([any(abs(h - r) <= tol for h in hw) for r in rw]))
    return {"ref_wechsel": len(rw), "hyp_wechsel": len(hw), "recall": round(rec, 3)}


def figur_trennung(ref, hyp, schritt=0.05):
    """Anteil der Redezeit je Figur, die pyannote NICHT dem Erzaehler-Sprecher zuordnet (nur Anzeige)."""
    hyp = sorted(hyp)

    def lab(t):
        for a, b, lb in hyp:
            if a <= t <= b:
                return lb
        return None
    T = collections.defaultdict(collections.Counter)
    for a, b, lb, _ in ref:
        for t in np.arange(a, b, schritt):
            T[lb][lab(t)] += schritt
    if ERZ not in T:
        return {}
    erz = T[ERZ].most_common(1)[0][0]
    return {lb: round(1 - c[erz] / sum(c.values()), 2) for lb, c in T.items() if lb != ERZ and sum(c.values())}


def sprecher_zahl(hyp):
    """Sprecher der Kontrollspur mit nennenswertem Anteil (>= 5 % und >= 2 s)."""
    t = collections.Counter()
    for a, b, lb in hyp or []:
        t[lb] += b - a
    ges = sum(t.values()) or 1.0
    return sum(1 for v in t.values() if v >= max(2.0, KONTROLLE_ANTEIL * ges))


def auswerten(p, roh, regel, rg, nachrunden, annahmen):
    """-> {erzaehler, kontrolle, diarisierung, figuren {f: {...urteil}}}"""
    man, emb, praat = roh["man"], roh["emb"], roh.get("praat") or {}
    schwelle = float(rg["ecapa_min"]) if rg["ecapa_min"] is not None else float(regel["ecapa"]["clip"]["schwelle_cosdist"])
    st_schwelle = float(regel["ecapa"]["stueck"]["schwelle_cosdist"])
    erz_m = _mittel([emb[i] for i in emb if man[i]["typ"] == "en"])
    pe = praat.get("erz") or {}
    diar = roh.get("diar") or {}
    hyp_hs, hyp_hb = (diar.get("pyannote") or {}).get("hs"), (diar.get("pyannote") or {}).get("hb")
    ref = roh.get("ref") or {}
    py_fig = figur_trennung(ref.get("hs") or [], hyp_hs) if hyp_hs else {}
    out = {"erzaehler": {"stimme": p["erz_stimme"], "saetze": len(p["erz"]), "praat": pe},
           "kontrolle": {"sprecher": sprecher_zahl(hyp_hb) if hyp_hb is not None else None,
                         "sekunden": round(sum(b - a for a, b, _ in hyp_hb or []), 1)},
           "diarisierung": {"wechsel": wechsel_treffer(ref.get("hs") or [], hyp_hs) if hyp_hs else None,
                            "figuren": py_fig},
           "schwelle": schwelle, "stueck_schwelle": st_schwelle, "figuren": {}}
    for f in sorted(p["fig_saetze"]):
        ens = p["ens"][f]
        ids = [i for i in emb if man[i]["typ"] == "fs" and man[i].get("figur") == f]
        rid = next((i for i in emb if man[i]["typ"] == "ref" and man[i].get("figur") == f), None)
        pf = (praat.get("fig") or {}).get(f) or {}
        redezeit = float(pf.get("stimmhaft_s") or 0.0)
        e = {"stimme": ens.get("stimme"), "korrektur": p["korr"][f], "saetze": len(p["fig_saetze"][f]),
             "stuecke": len(ids), "redezeit_s": round(redezeit, 2), "praat": pf,
             "D": trennung.abstand(pf, pe, regel) if pf and pe else {"status": "unbekannt"},
             "pyannote_getrennt": py_fig.get(f)}
        ff = p["korr"][f]["formant_faktor"]
        r = (+1 if ff > 1 else -1) if abs(ff - 1) > 1e-3 else trennung.richtung({}, pf, pe)
        e["richtung"] = r
        n_nr = (nachrunden.get(f"{p['lg']}/{f}") or {})
        n_nr = int(n_nr.get("n", 0)) if n_nr.get("stimme") == ens.get("stimme") else 0
        e["nachrunden"] = n_nr
        if ids:
            fm = _mittel([emb[i] for i in ids])
            d_erz = 1 - float(np.dot(fm, erz_m))
            d_ref = 1 - float(np.dot(fm, emb[rid])) if rid else None
            je = [1 - float(np.dot(emb[i], erz_m)) >= st_schwelle for i in ids]
            lang = max(ids, key=lambda i: man[i]["dauer"])
            e["ecapa"] = {"cosdist_erzaehler": round(d_erz, 3), "cosdist_ziel": None if d_ref is None else round(d_ref, 3),
                          "schwelle": schwelle, "getrennt": d_erz >= schwelle,
                          "naeher_an_ziel": None if d_ref is None else d_ref < d_erz,
                          "stuecke_verschieden": round(float(np.mean(je)), 2)}
            e["hoerprobe_id"] = lang
        else:
            e["ecapa"] = None
        # Urteil
        ec = e["ecapa"] or {}
        neu = None
        if not ids:
            u, grund = "zu_kurz", "keine messbaren Figurenstuecke"
        elif redezeit < float(rg["redezeit_min"]):
            u, grund = "zu_kurz", f"nur {redezeit:.1f} s stimmhafte Rede (< {float(rg['redezeit_min']):.0f} s)"
        elif ec["getrennt"] and ec["naeher_an_ziel"] is not False:
            u, grund = "ok", f"getrennt (ECAPA {ec['cosdist_erzaehler']} >= {schwelle})"
        elif ec["naeher_an_ziel"] is False:
            u, grund = "umbesetzen", (f"naeher am Erzaehler als an der Zielstimme (ECAPA Erz {ec['cosdist_erzaehler']}, "
                                      f"Ziel {ec['cosdist_ziel']})")
        elif n_nr >= 1:
            u, grund = "umbesetzen", f"nach der Nachrunde nicht getrennt (ECAPA {ec['cosdist_erzaehler']} < {schwelle})"
        elif _stufe_weiter(ff, r) is None:
            u, grund = "grenze", f"nicht getrennt an der Natuerlichkeitsgrenze (Formant {ff})"
        elif not rg["nachrunde"]:
            u, grund = "nachrunde_aus", f"nicht getrennt (ECAPA {ec['cosdist_erzaehler']} < {schwelle}), Nachrunde aus"
        else:
            neu = _stufe_weiter(ff, r)
            u, grund = "nachrunde", (f"nicht getrennt (ECAPA {ec['cosdist_erzaehler']} < {schwelle}) -> Formant "
                                     f"{ff} -> {neu} ({'kleiner/heller' if r > 0 else 'groesser/dunkler'})")
        a = annahmen.get(f"{p['lg']}/{f}")
        if u not in ("ok", "zu_kurz") and a and a.get("stimme") == ens.get("stimme") and a.get("korrektur") == e["korrektur"]:
            u, grund = "angenommen", f"{grund} – angenommen von {a.get('wer')} ({a.get('grund')})"
            neu = None
        e.update(urteil=u, grund=grund, korrektur_neu=neu)
        out["figuren"][f] = e
    return out


def mock_auswertung(p):
    return {"erzaehler": {"stimme": p["erz_stimme"], "saetze": len(p["erz"]), "praat": {}},
            "kontrolle": {"sprecher": 1, "sekunden": 0}, "diarisierung": {}, "schwelle": None, "modus": "mock",
            "figuren": {f: {"stimme": p["ens"][f].get("stimme"), "korrektur": p["korr"][f],
                            "saetze": len(p["fig_saetze"][f]), "stuecke": 0, "redezeit_s": None, "ecapa": None,
                            "nachrunden": 0, "urteil": "ok", "grund": "Mock-Lauf (keine Messung)", "korrektur_neu": None}
                        for f in sorted(p["fig_saetze"])}}


def hoerproben(werk, lg, p, roh, aus):
    """Laengstes Figurenstueck je Figur + ein Erzaehlersatz als Hoerprobe (work/_540/<lg>/hoerproben/)."""
    d = os.path.join(arbeit_dir(werk, lg), "hoerproben")
    os.makedirs(d, exist_ok=True)
    seg = os.path.join(arbeit_dir(werk, lg), "paket", "segmente")
    rel = lambda x: os.path.relpath(x, config.book_dir(werk)).replace(os.sep, "/")
    en = sorted(i for i in roh["man"] if roh["man"][i]["typ"] == "en")
    if en:
        shutil.copy2(os.path.join(seg, en[0] + ".wav"), os.path.join(d, "erzaehler.wav"))
        aus["erzaehler"]["hoerprobe"] = rel(os.path.join(d, "erzaehler.wav"))
    for n, (f, e) in enumerate(sorted(aus["figuren"].items())):
        i = e.pop("hoerprobe_id", None)
        if i and os.path.exists(os.path.join(seg, i + ".wav")):
            z = os.path.join(d, f"figur_{n:02d}.wav")
            shutil.copy2(os.path.join(seg, i + ".wav"), z)
            m = roh["man"][i]
            e["hoerprobe"] = {"datei": rel(z), "satz": m.get("tid"), "t0": m.get("t0"), "t1": m.get("t1"),
                              "erzaehler": aus["erzaehler"].get("hoerprobe")}


# ============================================================ Nachrunde (510 -> 530 -> 520)
def nachrunde_kette(werk, wer):
    """Korrektur ist gesetzt: 510/530/520 bauen per Hash nur die betroffenen Saetze neu. -> [(stage, ergebnis)]"""
    from pipeline import s530_audio_pruefung as s530
    out = []
    for st, f in (("510", lambda: s510.run(werk, wer=wer, nachrunde=True)),
                  ("530", lambda: s530.run(werk, wer=wer)), ("520", lambda: s520.run(werk, wer=wer))):
        try:
            g = f()
            e = (g.ergebnis or {}).get("ergebnis")
        except gate.GateHalt as ex:
            e = ex.ergebnis if hasattr(ex, "ergebnis") else "stopp"
        out.append((st, e))
        if e != "auto":
            break
    return out


# ============================================================ Lauf
def run(werk, wer=None, regler=None, nur_lang=None, neu=False, trocken=False):
    wer = wer or "pipeline"
    g = gate.Gate(werk, STAGE, ruecksprung="540", wer=wer)
    b = bestellung.lesen(werk)
    rg = _regler(dict(b.roh))
    if regler and any(v is not None for v in regler.values()):
        rg.update({k: v for k, v in regler.items() if v is not None})
        if not trocken:
            b = bestellung.feld_setzen(werk, trennung_regler=rg)
    ziele = s420._ziele(b)
    if nur_lang:
        ziele = {k: v for k, v in ziele.items() if k == nur_lang}
    regel = trennung.regel()
    g.metrik("hoerspielsprachen", ziele)
    g.metrik("regler", rg)
    g.metrik("regel", {"version": regel.get("version"), "stand": regel.get("stand"),
                       "ecapa_schwelle": regel["ecapa"]["clip"]["schwelle_cosdist"]})
    ip, sp, op = config.work_path(werk, "400_regie"), s420.pfad(werk), config.work_path(werk, "510_overlay")
    ok = g.pflicht("hoerspiel", bool(ziele), ruecksprung="095", text="Hoerspiel bestellt")
    ok = g.pflicht("eingang", all(os.path.exists(x) for x in (ip, sp, op)), ruecksprung="510",
                   text="400_regie.json, 420_sprecher.json, 510_overlay.json vorhanden") and ok
    ok = g.pflicht("regler", _regler_gueltig(rg), wert=rg, text="Regler im Bereich") and ok
    for v in ("410", "420", "510", "530", "520"):
        z = status.zustand(werk, v)
        if trocken:
            g.hinweis(f"gate_{v}", z in status.FREI, text=f"Gate {v}: {z}")
        else:
            ok = g.pflicht(f"gate_{v}", z in status.FREI, wert=z, ruecksprung=v, text=f"Gate {v} frei ({z})") and ok
    c = s410.laden(werk)
    ok = g.pflicht("casting", s410.freigegeben(c), ruecksprung="410", text="casting.json (Schema 2) freigegeben") and ok
    if not ok:
        g.entscheide(schreiben=not trocken)
        return g
    if not mock.aktiv() and not trocken:
        fe = werkzeuge_pruefen(rg["messung"])
        if fe:
            g.pflicht("werkzeug", False, wert=fe, ruecksprung="540", text="Messwerkzeuge – " + "; ".join(fe))
            g.entscheide(schreiben=True)
            return g
    ent = entscheidungen(werk)
    ergebnisse, plaene, haengt = {}, {}, None
    for durchgang in (0, 1):
        data = _json(ip, {}) or {}
        spr = (_json(sp, {}) or {}).get("saetze") or {}
        c = s410.laden(werk)
        m510 = manifest.Manifest(werk, "510_overlay", stage="510")
        for lg, stufe in sorted(ziele.items()):
            if durchgang and lg not in nachrunde_lg:
                continue
            p = plan_sprache(werk, lg, stufe, c, data, spr, m510, rg)
            plaene[lg] = p
            if p["fehler"]:
                ergebnisse[lg] = None
                continue
            if mock.aktiv() or trocken:
                ergebnisse[lg] = mock_auswertung(p) if mock.aktiv() else None
                continue
            roh = None if neu and not durchgang else messung_laden(werk, lg, p)
            fehler = None
            for versuch in (1, 2):
                if roh is not None:
                    break
                try:
                    print(f"[540] {lg}: Messung {rg['messung']} ({len(p['stuecke'])} Figurenstuecke, "
                          f"{len(p['erz'])} Erzaehlersaetze, Versuch {versuch})")
                    roh = messen(werk, lg, p, rg)
                except Exception as ex:                       # Modal/pyannote/Praat
                    fehler = f"{type(ex).__name__}: {str(ex)[:200]}"
                    print(f"[540] {lg}: Messfehler {fehler}")
            if roh is None:
                p["fehler"].append((f"messung_{lg}", f"{lg}: Messfehler nach 2 Versuchen – {fehler}", "540"))
                ergebnisse[lg] = None
                continue
            aus = auswerten(p, roh, regel, rg, ent["nachrunden"], ent["annahmen"])
            aus["messung"] = {"art": rg["messung"], "sekunden": roh.get("sekunden"),
                              "wiederverwendet": bool(roh.get("wiederverwendet"))}
            hoerproben(werk, lg, p, roh, aus)
            ergebnisse[lg] = aus
        nr = [(lg, f, e) for lg, a in ergebnisse.items() if a for f, e in a["figuren"].items()
              if e["urteil"] == "nachrunde"]
        if durchgang or not nr or trocken or mock.aktiv():
            break
        nachrunde_lg = {lg for lg, _, _ in nr}
        for lg, f, e in nr:
            print(f"[540] Nachrunde {lg}/{f}: {e['grund']}")
            s410.korrektur_setzen(werk, f, lg, formant=e["korrektur_neu"], tonhoehe=0, wer=wer,
                                  grund=f"540 Nachrunde: {e['grund']}")
            ent["nachrunden"][f"{lg}/{f}"] = {"stimme": e["stimme"], "n": e["nachrunden"] + 1, "wann": status.jetzt(),
                                              "von": e["korrektur"]["formant_faktor"], "nach": e["korrektur_neu"]}
            ent["protokoll"].append({"wann": status.jetzt(), "wer": wer, "aktion": "nachrunde", "figur": f,
                                     "sprache": lg, "grund": e["grund"]})
        _entsch_schreiben(werk, ent)
        kette = nachrunde_kette(werk, wer)
        g.metrik("nachrunde_kette", kette)
        schlecht = [(s, e) for s, e in kette if e != "auto"]
        if schlecht:
            haengt = f"Stage {schlecht[0][0]}: {schlecht[0][1]}"
            for lg, f, e in nr:
                e["grund"] += f" – Korrektur gesetzt, Nachrunde haengt ({haengt})"
            break

    # ---- Gate je Sprache x Figur
    je, aus_hash = {}, {}
    for lg, p in sorted(plaene.items()):
        for name, text, rs in p["fehler"]:
            g.pflicht(name, False, ruecksprung=rs, text=text)
        for name, text in p["hinweise"]:
            g.hinweis(name, False, text=text)
        a = ergebnisse.get(lg)
        je[lg] = {"figuren": len(p["fig_saetze"]), "saetze": len(p["hs"]), "stuecke": len(p["stuecke"]),
                  "erzaehler_saetze": len(p["erz"]), "eingang_hash": p["eingang_hash"]}
        if trocken and not p["fehler"]:
            vorh = messung_laden(werk, lg, p) is not None
            g.hinweis(f"messung_{lg}", vorh, text=f"{lg}: {len(p['fig_saetze'])} Figuren, {len(p['stuecke'])} Stuecke"
                      + (" – Messung aktuell (0 $)" if vorh else f" – Messung noetig (~{USD_JE_SPRACHE:.2f} $)"))
            continue
        if not a:
            continue
        if a.get("modus") != "mock":
            k = a["kontrolle"]["sprecher"]
            g.pruefe(f"kontrolle_{lg}", k == 1, wert=k, bei_fehler="mensch", ruecksprung="500",
                     text=f"{lg}: Erzaehler-Kontrolle Hoerbuchspur (pyannote {k} Sprecher)")
            w = (a.get("diarisierung") or {}).get("wechsel") or {}
            if w.get("recall") is not None:
                g.hinweis(f"wechsel_{lg}", True, wert=w["recall"],
                          text=f"{lg}: pyannote erkennt {w['recall']:.0%} der Wechsel Erzaehler/Figur (nur Hinweis)")
        for f, e in a["figuren"].items():
            n = f"figur_{lg}_{f}"
            ec = e.get("ecapa") or {}
            t = (f"{lg}/{f}: {e['urteil']} – {e['grund']}" +
                 (f" (D {e['D'].get('D')}, pyannote {e.get('pyannote_getrennt')})" if e.get("D") else ""))
            u = e["urteil"]
            if u == "ok":
                g.hinweis(n, True, wert=ec.get("cosdist_erzaehler"), text=t)
            elif u in ("zu_kurz", "angenommen"):
                g.hinweis(n, False, wert=ec.get("cosdist_erzaehler"), text=t)
            else:
                rs = "410" if u in ("umbesetzen", "grenze") else "510"
                g.pruefe(n, False, wert=ec.get("cosdist_erzaehler"), bei_fehler="mensch", ruecksprung=rs,
                         text=t + (" – umbesetzen (410) oder annehmen: --annehmen "
                                   f"\"{f}:{lg}\" --grund ..." if rs == "410" else ""))
        aus_hash[lg] = {f: [e["urteil"], (e.get("ecapa") or {}).get("cosdist_erzaehler"), e["stimme"], e["korrektur"]]
                        for f, e in a["figuren"].items()}
        if not trocken:
            doc = {"schema": 1, "stage": STAGE, "sprache": lg, "stufe": p["stufe"], "version": VERSION,
                   "datum": status.jetzt(), "eingang_hash": p["eingang_hash"],
                   "regel": {"version": regel.get("version"), "stand": regel.get("stand")},
                   "quellen_regionen": p["quellen"], **a}
            manifest.json_atomar(pfad(werk, lg), doc, indent=1)
    n_mock = sum(p.get("mocks", 0) for p in plaene.values())
    g.mock(n_mock, ruecksprung="510")
    ah = manifest.hash_obj(aus_hash)
    g.metrik("ausgabe_hash", ah)
    g.metrik("je_sprache", je)
    st0 = status.laden(werk)["stages"].get(STAGE) or {}
    if st0.get("zustand") == "frei" and (st0.get("gate") or {}).get("ergebnis") == "mensch" \
            and (st0.get("metriken") or {}).get("ausgabe_hash") == ah:
        for x in g.pruefungen:
            if not x["ok"] and x["bei_fehler"] == "mensch":
                x["bei_fehler"] = "hinweis"
                x["text"] = (x.get("text") or x["name"]) + " [Mensch-Freigabe gilt, Ergebnis unveraendert]"
    g.entscheide(schreiben=not trocken)
    g.ergebnisse = ergebnisse
    return g


# ============================================================ Regel neu eichen (nur Admin)
def eer(gleich, versch):
    """Schwelle mit gleicher Fehlrate (groesser = eher verschieden) -> (schwelle, eer)."""
    g, v = np.asarray(gleich, float), np.asarray(versch, float)
    best = None
    for t in np.unique(np.concatenate([g, v])):
        fa, fr = np.mean(v < t), np.mean(g >= t)
        if best is None or abs(fa - fr) < best[0]:
            best = (abs(fa - fr), float(t), float((fa + fr) / 2))
    return best[1], best[2]


def eichen(werk, lg, wer, art="modal"):
    """Regel F0 x VTL + ECAPA an den Archivstimmen (je Clip und 3-s-Stuecke) + Erzaehler des Werks neu eichen.
    Neue Regelversion; alte bleibt als _trennungsregel_v<n>.json; Protokoll in der Regel."""
    from pipeline import s080_mandant
    s080_mandant.darf(werk, "override", wer)
    fe = werkzeuge_pruefen(art)
    if fe:
        raise RuntimeError("; ".join(fe))
    reg = _json(os.path.join(trennung.STIMMEN_DIR, "stimmen.json"), {}) or {}
    d = os.path.join(arbeit_dir(werk, lg), "eichung")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(os.path.join(d, "segmente"))
    man, praat = [], {}
    st = lambda x: 12 * np.log2(x)
    for name, v in sorted(reg.items()):
        if v.get("status") == "abgelehnt":
            continue
        for clip in ("hoerprobe", f"muster_{lg}"):
            q = os.path.join(trennung.STIMMEN_DIR, name, clip + ".wav")
            if not os.path.exists(q):
                continue
            x = s510.lesen(q)
            sid = f"arf__{len(man):05d}"
            s510.schreiben(os.path.join(d, "segmente", sid + ".wav"), x)
            man.append({"id": sid, "typ": "arf", "stimme": name, "clip": clip})
            praat[sid] = trennung.praat_merkmale(x)
            n = 0
            for k in range(0, max(0, len(x) - 3 * SR) + 1, 3 * SR):
                y = x[k:k + 3 * SR]
                if n >= 3 or np.sqrt(np.mean(y ** 2)) < 0.01:
                    continue
                sid = f"ar__{len(man):05d}"
                s510.schreiben(os.path.join(d, "segmente", sid + ".wav"), y)
                man.append({"id": sid, "typ": "ar", "stimme": name, "clip": clip})
                praat[sid] = trennung.praat_merkmale(y)
                n += 1
    m530 = manifest.Manifest(werk, f"530_pruefung_{lg}", stage="530")
    for k in sorted(m530.eintraege)[:40]:
        if k.startswith("hoerbuch/") and m530.datei_aktuell(k):
            sid = f"en__{len(man):05d}"
            shutil.copy2(m530._abs(m530.eintraege[k]["datei"]), os.path.join(d, "segmente", sid + ".wav"))
            man.append({"id": sid, "typ": "en"})
    if sum(1 for s in man if s["typ"] == "arf") < 4:
        raise RuntimeError("zu wenige Archivstimmen fuer eine Eichung")
    manifest.json_atomar(os.path.join(d, "manifest.json"), {"segmente": man})
    manifest.json_atomar(os.path.join(d, "spur_ref.json"), {})
    erg, sek = gpu_messen(d, art)
    if art == "modal":
        usage_log.log_gpu(werk, STAGE, sek, gpu="T4", extra={"sprache": lg, "teil": "eichung"})
    M = {s["id"]: s for s in man}
    npz = np.load(os.path.join(erg, "embeddings.npz"))
    emb = {str(i): e / np.linalg.norm(e) for i, e in zip(npz["ids"], npz["emb"])}
    ok = {k: v for k, v in praat.items() if v.get("vtl_cm") and v.get("f0_hz")}

    def f0vtl(typ):
        el = [k for k in ok if M[k]["typ"] == typ]
        gl, vs = [], []
        for a, b2 in itertools.combinations(el, 2):
            dd = (abs(st(ok[a]["f0_hz"]) - st(ok[b2]["f0_hz"])), abs(st(ok[a]["vtl_cm"]) - st(ok[b2]["vtl_cm"])))
            (gl if M[a]["stimme"] == M[b2]["stimme"] else vs).append(dd)
        gl, vs = np.array(gl), np.array(vs)
        sF, sV = float(np.median(gl[:, 0])), float(np.median(gl[:, 1]))
        D = lambda x: np.sqrt((x[:, 0] / sF) ** 2 + (x[:, 1] / sV) ** 2)
        thr, e = eer(D(gl), D(vs))
        return {"skala_f0_ht": round(sF, 3), "skala_vtl_ht": round(sV, 3), "D_schwelle": round(thr, 3),
                "eer": round(e, 3), "n_gleich": len(gl), "n_versch": len(vs)}

    def ecapa(typ, mit_werk=False):
        el = [k for k in emb if M[k]["typ"] == typ]
        gl = [1 - float(np.dot(emb[a], emb[b2])) for a, b2 in itertools.combinations(el, 2)
              if M[a]["stimme"] == M[b2]["stimme"]]
        vs = [1 - float(np.dot(emb[a], emb[b2])) for a, b2 in itertools.combinations(el, 2)
              if M[a]["stimme"] != M[b2]["stimme"]]
        if mit_werk:
            en = [k for k in emb if M[k]["typ"] == "en"]
            gl += [1 - float(np.dot(emb[a], emb[b2])) for a, b2 in itertools.combinations(en, 2)]
        thr, e = eer(gl, vs)
        return {"schwelle_cosdist": round(thr, 3), "eer": round(e, 3), "n_gleich": len(gl), "n_versch": len(vs)}

    clip, stueck = f0vtl("arf"), f0vtl("ar")
    alt = trennung.regel()
    v_alt = int(alt.get("version") or 1)
    neu_r = dict(alt, version=v_alt + 1, stand=f"eichung {werk}_{lg} {status.jetzt()[:10]}",
                 skala_f0_ht=clip["skala_f0_ht"], skala_vtl_ht=clip["skala_vtl_ht"], D_schwelle=clip["D_schwelle"],
                 D_ziel=round(clip["D_schwelle"] * 1.25, 2), eer_f0_vtl=clip["eer"],
                 stueck={k: stueck[k] for k in ("skala_f0_ht", "skala_vtl_ht", "D_schwelle")},
                 ecapa={"stueck": ecapa("ar", True), "clip": ecapa("arf")})
    neu_r["protokoll"] = list(alt.get("protokoll") or []) + [
        {"wann": status.jetzt(), "wer": wer, "werk": werk, "sprache": lg, "von_version": v_alt,
         "stimmen": len({s["stimme"] for s in man if s.get("stimme")})}]
    if os.path.exists(trennung.REGEL_PFAD):
        shutil.copy2(trennung.REGEL_PFAD, trennung.REGEL_PFAD.replace(".json", f"_v{v_alt}.json"))
    manifest.json_atomar(trennung.REGEL_PFAD, neu_r, indent=1)
    return neu_r


# ============================================================ CLI
def _figur_lg(x):
    f, lg = x.rsplit(":", 1)
    return f, lg


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 540 Trennung Figur <-> Erzaehler")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--messung", choices=("modal", "cpu"))
    ap.add_argument("--ecapa-min", type=float)
    ap.add_argument("--redezeit-min", type=float)
    ap.add_argument("--nachrunde", choices=("an", "aus"))
    ap.add_argument("--erzaehler-s", type=float)
    ap.add_argument("--spur-max-s", type=float)
    ap.add_argument("--korrektur", metavar="FIGUR:LG=F[,HT]|weg")
    ap.add_argument("--annehmen", metavar="FIGUR:LG")
    ap.add_argument("--grund")
    ap.add_argument("--eichen", metavar="LG")
    ap.add_argument("--neu", action="store_true")
    ap.add_argument("--lang")
    ap.add_argument("--trocken", action="store_true")
    a = ap.parse_args(argv)
    regler = {"messung": a.messung, "ecapa_min": a.ecapa_min, "redezeit_min": a.redezeit_min,
              "nachrunde": None if a.nachrunde is None else a.nachrunde == "an", "erzaehler_s": a.erzaehler_s,
              "spur_max_s": a.spur_max_s}
    wer = a.wer or "pipeline"
    try:
        if a.eichen:
            r = eichen(a.werk, a.eichen, wer, a.messung or "modal")
            print(f"[540] Regel v{r['version']}: ECAPA clip {r['ecapa']['clip']['schwelle_cosdist']}, "
                  f"stueck {r['ecapa']['stueck']['schwelle_cosdist']}, D_schwelle {r['D_schwelle']}")
            return 0
        if (any(v is not None for v in regler.values()) or a.korrektur or a.annehmen) and not a.trocken:
            from pipeline import s080_mandant
            s080_mandant.darf(a.werk, "entscheiden", wer)
        if a.annehmen:
            f, lg = _figur_lg(a.annehmen)
            annehmen(a.werk, f, lg, wer, a.grund)
        if a.korrektur:
            fig, rest = a.korrektur.rsplit(":", 1)
            lg, wert = rest.split("=", 1)
            if not a.grund:
                raise ValueError("--korrektur braucht --grund")
            if wert == "weg":
                korrektur(a.werk, fig, lg, None, None, wer, a.grund)
            else:
                ff, ht = (wert.split(",") + ["0"])[:2]
                korrektur(a.werk, fig, lg, float(ff), float(ht), wer, a.grund)
            erg = nachrunde_kette(a.werk, wer)
            print("[540] Korrektur gesetzt; " + ", ".join(f"{s} {e}" for s, e in erg))
            if any(e != "auto" for _, e in erg):
                return 3
        g = run(a.werk, wer, regler=regler, nur_lang=a.lang, neu=a.neu, trocken=a.trocken)
    except gate.GateHalt as e:
        print(e)
        return e.exit_code
    except (ValueError, PermissionError, RuntimeError) as e:
        print(f"[540] Fehler: {e}")
        return 1
    print(g.bericht())
    return gate.EXIT[g.ergebnis["ergebnis"]]


if __name__ == "__main__":
    sys.exit(main())
