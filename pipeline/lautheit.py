"""READ LAYER — Segment-Lautheit + Kapitel-Mastering (Baustein der Stage 520, AP Lautheit 27.11.2026)
Funktion:     Vor dem Zusammenfuegen eines Kapitels jedes Segment (Redebeitrag Erzaehler/Figur aus den Spannen 500/510)
              auf ein festes Ziel (Standard -19 LUFS) bringen, je Sprechanweisung (430: vortrag/nonverbal) mit Offset
              aus config.LAUTHEIT_OFFSETS (book.json lautheit_offsets ueberschreibt). Danach Kapitel-Mastering: leichte
              Kompression (ffmpeg acompressor), Lautheit auf Kapitelziel, True-Peak-Limiter (Standard -3 dBTP).
Messung:      Segmente >= segment_kurz_s (3 s): integrierte Lautheit (pyloudnorm, BS.1770). Kuerzere: aktiver RMS-Pegel
              (s510._db_aktiv) + Kalibrier-Offset (Median LUFS - RMS der langen Segmente derselben Figur im Kapitel,
              sonst des Kapitels, sonst config.LAUTHEIT_KALIB_STD) -> beide auf derselben Skala.
Wirkung:      Verstaerkung je Segment (gekappt +-segment_gain_max) als Huellkurve mit Rampen an den Segmentgrenzen
              (keine Spruenge). Segmente < MIN_S uebernehmen die Verstaerkung des Nachbarn.
Befund:       Monte Cristo DE (27.11.2026): Hoerspiel-Figuren bis 38 % der Segmente > 3 LU unter dem Erzaehler
              (s511.montage gleicht nur innerhalb des Satzes per RMS an) -> Anlass.
Abnehmer:     pipeline/s520_audio_pruefung.py (Regler segment_lautheit/master), tools/lautheit_test.py (A/B ohne Ausgabe).
Kosten:       0 $ (CPU).
"""
import collections
import csv
import json
import os
import subprocess
import tempfile

import numpy as np

from config import config

VERSION = 1
SR = 24000
MIN_S = 0.3                       # kuerzere Segmente: Verstaerkung vom Nachbarn
STILL_DB = -60.0                  # Segment leiser (Pegel) -> nicht anheben
RAMPE_MS = 20.0
LUFS_MIN = 0.4                    # pyloudnorm braucht >= 400 ms (ein Messblock)
ERZ = "Erzaehler"


def _kalib_std():
    return float(getattr(config, "LAUTHEIT_KALIB_STD", 2.5))


# ============================================================ Messen
_METER = {}


def lufs(y):
    """Integrierte Lautheit (BS.1770, pyloudnorm); zu kurz/still -> -70."""
    import pyloudnorm as pyln
    y = np.asarray(y, np.float64)
    if len(y) < int(LUFS_MIN * SR):
        return -70.0
    m = _METER.get(SR) or _METER.setdefault(SR, pyln.Meter(SR))
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        v = m.integrated_loudness(y)
    return max(-70.0, float(v)) if np.isfinite(v) else -70.0


def rms_db(y):
    from pipeline import s510_hoerspiel_hybrid as s510
    return float(s510._db_aktiv(np.asarray(y, np.float32))) if len(y) else -90.0


def kalibrierung(stuecke, kurz_s):
    """stuecke: [(fig, y)] -> {fig: LUFS-RMS, None: Kapitelwert}. Lange Segmente (>= kurz_s) zaehlen."""
    je = collections.defaultdict(list)
    for fig, y in stuecke:
        if len(y) >= kurz_s * SR:
            d = lufs(y) - rms_db(y)
            if -10 < d < 15:
                je[fig].append(d)
    alle = [d for v in je.values() for d in v]
    out = {f: float(np.median(v)) for f, v in je.items() if len(v) >= 3}
    out[None] = float(np.median(alle)) if alle else _kalib_std()
    return out


def pegel(y, fig, kal, kurz_s):
    """LUFS-Pegel eines Segments (lang: LUFS, kurz: RMS + Kalibrierung)."""
    if len(y) >= kurz_s * SR:
        return lufs(y)
    return rms_db(y) + kal.get(fig, kal.get(None, _kalib_std()))


# ============================================================ Offsets aus der Sprechanweisung (430)
def offset_tabelle(roh=None):
    t = json.loads(json.dumps(getattr(config, "LAUTHEIT_OFFSETS", {})))
    for k, v in ((roh or {}).get("lautheit_offsets") or {}).items():
        t.setdefault(k, {}).update(v or {})
    return t


def offsets_laden(werk, lg, tabelle):
    """{beitrags_id: dB} aus work/430_fish_regie.json (moment.vortrag/nonverbal); fehlt 430 -> {}."""
    p = config.work_path(werk, "430_fish_regie")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    out = {}
    for b in ((d.get("sprachen") or {}).get(lg) or {}).get("beitraege") or []:
        mo = b.get("moment") or {}
        v = sum(float((tabelle.get(feld) or {}).get(mo.get(feld) or "", 0.0)) for feld in ("vortrag", "nonverbal"))
        if v:
            out[b["id"]] = v
    return out


# ============================================================ Spannen
def spannen_hoerbuch(e500, dauer_s):
    """Spannen der Hoerbuch-Rohfassung (500) oder ganzer Satz als ein Segment."""
    sp = [dict(id=s["id"], fig=s.get("fig") or ERZ, a=float(s["a"]), b=float(s["b"]))
          for s in (e500 or {}).get("spannen") or []]
    return sp or [{"id": None, "fig": ERZ, "a": 0.0, "b": dauer_s}]


def spannen_hoerspiel(e500, e510, dauer_s):
    """Spannen der Hoerspiel-Rohfassung (511.montage): Teile in 500-Reihenfolge, Figurenteil Laenge (b-a)*q."""
    q = {s["id"]: float(s.get("q") or 1.0) for s in (e510 or {}).get("schnitt") or []}
    sp500 = (e500 or {}).get("spannen") or []
    if not sp500 or not q:
        figs = (e510 or {}).get("figuren") or []
        return [{"id": None, "fig": figs[0] if len(figs) == 1 else ERZ, "a": 0.0, "b": dauer_s}]
    out, pos = [], 0.0
    for s in sp500:
        L = (float(s["b"]) - float(s["a"])) * q.get(s["id"], 1.0)
        out.append({"id": s["id"], "fig": s.get("fig") or ERZ, "a": pos, "b": pos + L})
        pos += L
    if out and pos > 0:                         # Rundung: auf Dateilaenge strecken
        f = dauer_s / pos
        for s in out:
            s["a"], s["b"] = s["a"] * f, s["b"] * f
    return out


# ============================================================ Segment-Normierung
def gains(stuecke, kal, offsets, rg):
    """stuecke [(spanne, y)] -> [gain_db] je Segment (gekappt, kurze vom Nachbarn)."""
    ziel, kurz, cap = float(rg["segment_lufs"]), float(rg["segment_kurz_s"]), float(rg["segment_gain_max"])
    g, gemessen = [], []
    for s, y in stuecke:
        if len(y) < MIN_S * SR:
            g.append(None)
            gemessen.append(None)
            continue
        p = pegel(y, s["fig"], kal, kurz)
        gemessen.append(p)
        if p <= STILL_DB:
            g.append(0.0)
            continue
        soll = ziel + float(offsets.get(s.get("id"), 0.0))
        g.append(max(-cap, min(cap, soll - p)))
    for i in range(len(g)):                     # kurze Segmente: Nachbar (vorher, sonst nachher, sonst 0)
        if g[i] is None:
            nb = next((g[j] for j in range(i - 1, -1, -1) if g[j] is not None), None)
            if nb is None:
                nb = next((g[j] for j in range(i + 1, len(g)) if g[j] is not None), 0.0)
            g[i] = nb
    return g, gemessen


def huellkurve(n, grenzen, g_db, rampe_ms=RAMPE_MS):
    """Stueckweise konstante Verstaerkung (dB) je [a,b) in Samples, Luecken = vorheriges Segment, geglaettet
    (gleitendes Mittel rampe_ms) -> lineare Faktoren."""
    if not n:
        return np.ones(0, np.float32)
    d = np.full(n, np.nan, np.float64)
    for (a, b), v in zip(grenzen, g_db):
        d[max(0, a):min(n, b)] = v
    ok = ~np.isnan(d)
    if not ok.any():
        return np.ones(n, np.float32)
    idx = np.where(ok, np.arange(n), 0)
    np.maximum.accumulate(idx, out=idx)
    d = np.where(ok, d, d[idx])
    erst = np.argmax(ok)
    d[:erst] = d[erst]
    w = int(rampe_ms / 1000 * SR) // 2
    if w > 0:
        c = np.concatenate([[0.0], np.cumsum(np.pad(d, (w, w), mode="edge"))])
        d = (c[2 * w + 1:] - c[:-(2 * w + 1)]) / (2 * w + 1)
    return (10 ** (d / 20)).astype(np.float32)


def segmente_normieren(x, spannen, kal, offsets, rg):
    """Satz x + Spannen (s) -> (y, protokoll [{id, fig, a, b, vor, gain}])."""
    x = np.asarray(x, np.float32)
    gr = [(int(round(s["a"] * SR)), int(round(s["b"] * SR))) for s in spannen]
    stuecke = [(s, x[a:b]) for s, (a, b) in zip(spannen, gr)]
    g, gemessen = gains(stuecke, kal, offsets, rg)
    y = x * huellkurve(len(x), gr, g)
    prot = [{"id": s.get("id"), "fig": s["fig"], "a": s["a"], "b": s["b"], "vor": None if p is None else round(p, 2),
             "gain": round(v, 2)} for s, p, v in zip(spannen, gemessen, g)]
    return y, prot


# ============================================================ Mastering
def _ffmpeg_filter(y, filt):
    import soundfile as sf
    with tempfile.TemporaryDirectory() as d:
        q, z = os.path.join(d, "q.wav"), os.path.join(d, "z.wav")
        sf.write(q, np.asarray(y, np.float32), SR, subtype="FLOAT")
        r = subprocess.run(["ffmpeg", "-y", "-nostats", "-hide_banner", "-loglevel", "error", "-i", q, "-af", filt,
                            "-c:a", "pcm_f32le", z], capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(f"ffmpeg {filt}: {r.stderr[-300:]}")
        out, _ = sf.read(z, dtype="float32")
    out = out[:len(y)] if len(out) >= len(y) else np.pad(out, (0, len(y) - len(out)))
    return out.astype(np.float32)


def komprimieren(y, k=None):
    """Leichte Kompression bei festem Arbeitspunkt: Vorverstaerkung auf k['vor_lufs'], acompressor (RMS), zurueck."""
    k = {**getattr(config, "LAUTHEIT_KOMPRESSOR", {}), **(k or {})}
    if not k.get("an", True) or not len(y):
        return y
    lu = lufs(y)
    if lu <= -69:
        return y
    vg = float(k.get("vor_lufs", -23.0)) - lu
    z = y * 10 ** (vg / 20)
    filt = (f"acompressor=threshold={10 ** (float(k.get('schwelle_db', -20.0)) / 20):.6f}:ratio={float(k.get('ratio', 2.0))}"
            f":attack={float(k.get('attack_ms', 10.0))}:release={float(k.get('release_ms', 200.0))}:makeup=1")
    z = _ffmpeg_filter(z, filt)
    return z * 10 ** (-vg / 20)


def true_peaks(y, faktor=4):
    """|Spitze| je Sample aus 4-fach ueberabgetastetem Signal (True Peak nach BS.1770)."""
    from scipy.signal import resample_poly
    y = np.asarray(y, np.float32)
    n, block, rand = len(y), 10 * SR, 256           # blockweise (Kapitel ~1 h: sonst mehrere GB float64)
    out = np.abs(y).copy()
    for a in range(0, n, block):
        b = min(n, a + block)
        a0, b0 = max(0, a - rand), min(n, b + rand)
        y4 = np.abs(resample_poly(y[a0:b0], faktor, 1))
        m = b0 - a0
        y4 = y4[:m * faktor] if len(y4) >= m * faktor else np.pad(y4, (0, m * faktor - len(y4)))
        tp = y4.reshape(m, faktor).max(1)[a - a0:a - a0 + (b - a)]
        np.maximum(out[a:b], tp, out=out[a:b])
    return out


def tp_begrenzen(y, grenze_db, versuche=3):
    """True-Peak-Limiter: s520.begrenzen mit Spitzen aus dem ueberabgetasteten Signal, bis Spitze <= Grenze."""
    from pipeline import s520_audio_pruefung as s520
    z, rand = np.asarray(y, np.float32), 0.1
    for _ in range(versuche):
        tp = true_peaks(z) if len(z) else None
        if tp is None or float(tp.max()) <= 10 ** (grenze_db / 20):
            break
        z = s520.begrenzen(z, grenze_db - rand, spitzen=tp)
        rand += 0.2
    return z


def mastern(y, ziel_lufs, peak_db, rg=None):
    """Kapitel: Kompression -> Lautheit auf ziel_lufs -> True-Peak-Limiter. -> (z, info)."""
    from pipeline import s520_audio_pruefung as s520
    lu0, pk0 = s520.lautheit(y)
    z = komprimieren(y) if (rg or {}).get("master", True) else np.asarray(y, np.float32)
    lu1 = lufs(z)
    gain = float(ziel_lufs) - lu1 if lu1 > -69 else 0.0
    z = (z * 10 ** (gain / 20)).astype(np.float32)
    begrenzt = bool(len(z)) and float(true_peaks(z).max()) > 10 ** (float(peak_db) / 20)
    z = tp_begrenzen(z, float(peak_db))
    lu2, pk2 = s520.lautheit(z)
    grenze = float(peak_db)
    for _ in range(3):                  # Nachregeln gegen die Gate-Messung (ffmpeg ebur128 True Peak)
        if pk2 <= float(peak_db):
            break
        grenze -= (pk2 - float(peak_db)) + 0.1
        z = tp_begrenzen(z, grenze)
        lu2, pk2 = s520.lautheit(z)
    return z, {"lufs_vor": round(lu0, 2), "peak_vor": round(pk0, 2), "gain_db": round(gain, 2), "begrenzt": begrenzt,
               "lufs": round(lu2, 2), "peak": round(pk2, 2), "kompression": bool((rg or {}).get("master", True))}


# ============================================================ Report
FELDER = ["kapitel", "sprecher", "segmente", "dauer_s", "lufs_vor", "lufs_segment", "lufs_master",
          "delta_lu", "unter_3lu_vor_pct", "unter_3lu_nach_pct"]


def _lufs_menge(teile, kal, kurz):
    """Lautheit aneinandergehaengter Segmente einer Figur (kurz insgesamt -> RMS + Kalibrierung)."""
    teile = [t for t in teile if len(t)]
    if not teile:
        return None
    y = np.concatenate(teile)
    return round(lufs(y) if len(y) >= kurz * SR else rms_db(y) + kal.get(None, _kalib_std()), 2)


def report_zeilen(kap, segs, kal, rg):
    """segs: [{fig, vor: y, seg: y, master: y}] eines Kapitels -> CSV-Zeilen je Sprecher (+ Zeile '*' gesamt).
    'unter_3lu': Anteil der Segmente (>= MIN_S) mehr als 3 LU unter dem Erzaehlerpegel des Kapitels."""
    kurz = float(rg["segment_kurz_s"])
    je = collections.defaultdict(list)
    for s in segs:
        je[s["fig"]].append(s)
    ref = {}
    for stufe in ("vor", "master"):
        e = [s[stufe] for s in je.get(ERZ, [])]
        ref[stufe] = _lufs_menge(e, kal, kurz) if e else None
    zeilen = []
    for fig in sorted(je, key=lambda f: (f != ERZ, f)):
        ss = je[fig]
        lv, ls, lm = (_lufs_menge([s[k] for s in ss], kal, kurz) for k in ("vor", "seg", "master"))

        def anteil(stufe):
            if ref[stufe] is None or fig == ERZ:
                return ""
            n = [s for s in ss if len(s[stufe]) >= MIN_S * SR]
            if not n:
                return ""
            u = sum(1 for s in n if pegel(s[stufe], fig, kal, kurz) < ref[stufe] - 3.0)
            return round(100.0 * u / len(n), 1)
        zeilen.append({"kapitel": kap, "sprecher": fig, "segmente": len(ss),
                       "dauer_s": round(sum(len(s["vor"]) for s in ss) / SR, 1), "lufs_vor": lv, "lufs_segment": ls,
                       "lufs_master": lm, "delta_lu": "" if lv is None or lm is None else round(lm - lv, 2),
                       "unter_3lu_vor_pct": anteil("vor"), "unter_3lu_nach_pct": anteil("master")})
    return zeilen


def csv_schreiben(pfad, zeilen, ersetzt_kapitel=()):
    """CSV schreiben; bestehende Zeilen anderer Kapitel bleiben (Teillaeufe)."""
    alt = []
    if os.path.exists(pfad):
        with open(pfad, encoding="utf-8", newline="") as f:
            alt = [r for r in csv.DictReader(f, delimiter=";") if r.get("kapitel") not in set(ersetzt_kapitel)]
    alle = sorted(alt + list(zeilen), key=lambda r: (str(r["kapitel"]), r["sprecher"] != ERZ, str(r["sprecher"])))
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    tmp = pfad + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FELDER, delimiter=";")
        w.writeheader()
        for r in alle:
            w.writerow({k: r.get(k, "") for k in FELDER})
    os.replace(tmp, pfad)
    return pfad
