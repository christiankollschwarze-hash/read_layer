"""READ LAYER - Trennung Erzaehler <-> Figur am FERTIGEN VC-Overlay messen (lokal, Parselmouth). Werkunabhaengig.

Aufruf (Normalfall ueber start_trennung_messen.bat <werk> <lg>):
  py -3.11 tools/trennung_messen.py <werk> <lg>                  Paket bauen (falls fehlt) + Praat-Messung
  py -3.11 tools/trennung_messen.py <werk> <lg> --runde auto     fertiges Overlay (spannen/vc_korr) als naechste Runde r1, r2, ...
  py -3.11 tools/trennung_messen.py <werk> <lg> --runde <name>   dasselbe mit festem Namen
  py -3.11 tools/trennung_messen.py <werk> <lg> --korrektur      Varianten fuer alle Figuren mit korrektur[lg] in casting.json
Optionen: --neu (Paket neu bauen)  --eichen (Archiv-Eichclips mitpacken; nur fuer neue Eichung der Regel)
          --nur-paket (ohne Praat)  --budget <s> (Praat-Messung nach s Sekunden unterbrechen, wiederaufnehmbar)

Ohne --eichen gelten Regel und Schwellen aus stimmen_archiv/_trennungsregel.json; das Paket enthaelt dann
keine Archivsegmente (Modal-Lauf und Auswertung brauchen sie nicht).

Paket gpu_messung/<werk>_<lg>/:
  segmente/*.wav   vc__  Figurenspanne nach VC (roh)           v1__  Figurenspanne VC vor Nachbesserung (falls _teil)
                   os__  dieselbe Spanne im Erzaehler-Original nb__  angrenzende Erzaehler-Rede (Wortzeiten)
                   ref__ VC-Zielstimme                         ref3__ VC-Zielstimme der Nachbesserung
                   en__  Erzaehler-Saetze des Werks            kx__<variante|runde>__<job>  Korrektur / fertiges Overlay
                   ar__/arf__  Archivstimmen (nur --eichen)
  manifest.json    Segment-Metadaten, "runden" (Reihenfolge der Pruefrunden)
  spur_<var>.wav + spur_ref.json   Pruefspuren fuer die Diarisierung (Referenz aus Wortzeiten)
  messung_praat.json   F0, Formanten F1-F4, VTL (Formantabstand), HNR, CPPS je Segment
"""
import os, sys, json, glob, zipfile, io, time, random, re
import numpy as np
import soundfile as sf

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR = 24000
C_SCHALL = 35000.0  # cm/s
# Natuerlichkeitsgrenzen (CK 16.10.2026, wie pipeline/trennung.py): Stufen je Richtung
STUFEN = {+1: [1.05, 1.10], -1: [0.97, 0.94]}


def werk_dir(book):
    t = glob.glob(os.path.join(HIER, "authors", "*", "books", book))
    if not t:
        sys.exit(f"Werk '{book}' nicht gefunden (authors/*/books/{book})")
    return t[0]


def paket_dir(book, lg):
    return os.path.join(HIER, "gpu_messung", f"{book}_{lg}")


def lade(quelle):
    x, sr = sf.read(quelle, dtype="float32", always_2d=False)
    if x.ndim > 1:
        x = x.mean(axis=1)
    if sr != SR:
        n = int(round(len(x) * SR / sr))
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype("float32")
    return x


def schneide(x, t0, t1):
    return x[max(0, int(t0 * SR)):max(0, int(t1 * SR))]


def regionen(woerter, luecke=0.25):
    """Wortzeiten -> zusammenhaengende Sprechregionen [(t0, t1, [wortindizes])]."""
    out = []
    for w in sorted(woerter, key=lambda w: w["t0"]):
        if out and w["t0"] - out[-1][1] <= luecke:
            out[-1][1] = max(out[-1][1], w["t1"]); out[-1][2].append(w["i"])
        else:
            out.append([w["t0"], w["t1"], [w["i"]]])
    return out


def teil_pakete(ov):
    return [t for t in glob.glob(ov + "_teil*") if os.path.exists(os.path.join(t, "ergebnis.zip"))]


def veraltet(book, lg):
    """Paket aelter als das Overlay (neues VC-Ergebnis, z. B. nach Umbesetzung) -> neu bauen."""
    mp = os.path.join(paket_dir(book, lg), "manifest.json")
    if not os.path.exists(mp):
        return True
    ov = os.path.join(HIER, "gpu_overlay", f"{book}_{lg}")
    zips = [os.path.join(t, "ergebnis.zip") for t in [ov] + teil_pakete(ov) if os.path.exists(os.path.join(t, "ergebnis.zip"))]
    return any(os.path.getmtime(z) > os.path.getmtime(mp) for z in zips)


def korrekturen(book, lg):
    """casting.json ensemble[].korrektur[lg] (oder flach) -> {figur: {formant_faktor, tonhoehe_ht}}"""
    cast = json.load(open(os.path.join(werk_dir(book), "work", "casting.json"), encoding="utf-8"))
    out = {}
    for e in cast["plan"]["ensemble"]:
        k = e.get("korrektur") or {}
        k = k.get(lg, {}) if any(x in k for x in ("de", "en")) else k
        if k and (abs(float(k.get("formant_faktor", 1.0)) - 1) > 1e-3 or k.get("tonhoehe_ht")):
            out[e["figur"]] = k
    return out


def paket_bauen(book, lg, eichen=False):
    alt = os.path.join(paket_dir(book, lg), "manifest.json")
    frueher = []
    if os.path.exists(alt):   # Rundennummern fortfuehren
        Malt = json.load(open(alt, encoding="utf-8"))
        frueher = Malt.get("runden_frueher", []) + runden_liste(Malt)
        for f in ("messung_praat.json", "ergebnis_modal.zip"):
            p = os.path.join(paket_dir(book, lg), f)
            if os.path.exists(p):
                os.replace(p, p + ".alt")
        for f in glob.glob(os.path.join(paket_dir(book, lg), "segmente", "*.wav")) + \
                glob.glob(os.path.join(paket_dir(book, lg), "spur_*.wav")):
            os.remove(f)
    werk = werk_dir(book)
    ov = os.path.join(HIER, "gpu_overlay", f"{book}_{lg}")
    if not os.path.exists(os.path.join(ov, "jobs.json")):
        sys.exit(f"Kein Overlay-Paket {ov} - erst tools/overlay_vorbereiten.py + Modal + overlay_montage.py")
    teil = ov + "_teil"
    ziel = paket_dir(book, lg)
    segd = os.path.join(ziel, "segmente")
    os.makedirs(segd, exist_ok=True)
    jobs = json.load(open(os.path.join(ov, "jobs.json"), encoding="utf-8"))["jobs"]
    # Nachbesserungen/Umbesetzungen (_teil, _teil_v1, ...): Stimme je Spanne aus dem juengsten Teilpaket
    neuere = {}
    for t in sorted(teil_pakete(ov), key=lambda t: os.path.getmtime(os.path.join(t, "ergebnis.zip"))):
        for j in json.load(open(os.path.join(t, "jobs.json"), encoding="utf-8"))["jobs"]:
            neuere[j["id"]] = j["stimme"]
    for j in jobs:
        j["stimme"] = neuere.get(j["id"], j["stimme"])
    teil_ids = set()
    if os.path.exists(os.path.join(teil, "jobs.json")):
        teil_ids = {j["id"] for j in json.load(open(os.path.join(teil, "jobs.json"), encoding="utf-8"))["jobs"]}
    wt = json.load(open(os.path.join(werk, "work", f"520_wortzeiten_{lg}.json"), encoding="utf-8"))["tags"]
    adir = os.path.join(werk, "fassungen", lg, "audio")
    ovd = os.path.join(werk, "fassungen", lg, "audio_overlay")
    alle = sorted(f[:-4] for f in os.listdir(adir) if f.endswith(".wav"))
    pos = {t: i for i, t in enumerate(alle)}
    je_tag = {}
    for j in jobs:
        je_tag.setdefault(j["tag"], []).append(j)
    man = []

    def ablegen(sid, x, **meta):
        sf.write(os.path.join(segd, sid + ".wav"), x, SR, subtype="PCM_16")
        man.append(dict(id=sid, dauer=round(len(x) / SR, 3), **meta))

    def erz_rede(tag):
        """nur Erzaehler-Rede eines Satzes (ohne VC-Spannen), per Wortzeiten."""
        x = lade(os.path.join(adir, tag + ".wav"))
        spannen = [(j["t0"], j["t1"]) for j in je_tag.get(tag, [])]
        teile = []
        for a, b, _ in regionen(wt.get(tag, [])):
            m = (a + b) / 2
            if any(s0 <= m <= s1 for s0, s1 in spannen):
                continue
            for s0, s1 in spannen:
                if a < s1 and b > s0:
                    a, b = (s1, b) if m > s1 else (a, s0)
            if b - a > 0.2:
                teile.append(schneide(x, a, b))
        return np.concatenate(teile) if teile else np.zeros(0, "float32")

    def nachbar(tag, richtung):
        i = pos[tag] + richtung
        while 0 <= i < len(alle):
            if alle[i] not in je_tag and alle[i] in wt:
                return alle[i]
            i += richtung
        return None

    z1 = zipfile.ZipFile(os.path.join(ov, "ergebnis.zip")) if teil_ids else None
    for j in jobs:
        jid, tag = j["id"], j["tag"]
        q = os.path.join(ovd, "spannen", "vc", jid + ".wav")
        if not os.path.exists(q):
            print(f"  [paket] Spanne fehlt: {q}")
            continue
        meta = dict(figur=j["figur"], stimme=j["stimme"], tag=tag, job=jid)
        ablegen("vc__" + jid, lade(q), typ="vc", **meta)
        if jid in teil_ids:
            ablegen("v1__" + jid, lade(io.BytesIO(z1.read(f"vc/{jid}.wav"))), typ="v1", **meta)
        orig = lade(os.path.join(adir, tag + ".wav"))
        ablegen("os__" + jid, schneide(orig, j["t0"], j["t1"]), typ="os", **meta)
        teile, quellen = [], []
        innen = erz_rede(tag)
        if len(innen) >= 0.6 * SR:
            teile.append(innen); quellen.append(tag)
        for r in (-1, 1):
            if sum(len(t) for t in teile) >= 2.0 * SR:
                break
            nt = nachbar(tag, r)
            if nt:
                teile.append(erz_rede(nt)); quellen.append(nt)
        if teile:
            ablegen("nb__" + jid, np.concatenate(teile), typ="nb", nb_quellen=quellen, **meta)
    gesehen = set()
    for d, pre in [(ov, "ref__"), (teil, "ref3__")] + [(t, "ref__") for t in teil_pakete(ov)]:
        for f in sorted(glob.glob(os.path.join(d, "ref", "*.wav"))):
            st = os.path.basename(f)[:-4]
            if (pre, st) in gesehen:
                continue
            gesehen.add((pre, st))
            ablegen(pre + st, lade(f), typ=pre[:-2], stimme=st)
    if eichen:   # Archivstimmen in 3-s-Stuecken (je Clip bis 3) - nur fuer eine neue Eichung der Regel
        reg = json.load(open(os.path.join(HIER, "stimmen_archiv", "stimmen.json"), encoding="utf-8"))
        for name, v in sorted(reg.items()):
            for clip in ("hoerprobe", "muster_de", "muster_en"):
                f = os.path.join(HIER, "stimmen_archiv", name, clip + ".wav")
                if not os.path.exists(f):
                    continue
                x = lade(f)
                g = v.get("merkmale", {}).get("geschlecht")
                ablegen(f"arf__{name}__{clip}", x, typ="arf", stimme=name, clip=clip, geschlecht=g, status=v.get("status"))
                n = 0
                for k in range(0, max(0, len(x) - 3 * SR) + 1, 3 * SR):
                    st = x[k:k + 3 * SR]
                    if np.sqrt(np.mean(st ** 2)) < 0.01 or n >= 3:
                        continue
                    ablegen(f"ar__{name}__{clip}__{n}", st, typ="ar", stimme=name, clip=clip, geschlecht=g, status=v.get("status"))
                    n += 1
    # Erzaehler des Werks: 40 reine Erzaehler-Saetze (ECAPA-Mittel des Werk-Erzaehlers)
    random.seed(57)
    frei = [t for t in alle if t not in je_tag and t in wt]
    for t in sorted(random.sample(frei, min(40, len(frei)))):
        x = erz_rede(t)
        if len(x) >= 1.5 * SR:
            ablegen("en__" + t, x, typ="en", tag=t, figur="Erzaehler")
    # Pruefspuren fuer Diarisierung
    menge = set(je_tag)
    for t in je_tag:
        for r in (-1, 1):
            nt = nachbar(t, r)
            if nt:
                menge.add(nt)
    folge = sorted(menge, key=lambda t: pos[t])
    pause = np.zeros(int(0.4 * SR), "float32")
    varianten = [("vc", "vc"), ("orig", None)]
    if teil_ids and os.path.isdir(os.path.join(ovd, "vc_v1")):
        varianten.insert(1, ("v1", "vc_v1"))
    ref = {v: [] for v, _ in varianten}
    for var, sub in varianten:
        stuecke, t_off = [], 0.0
        for t in folge:
            p = os.path.join(ovd, sub, t + ".wav") if (sub and t in je_tag) else os.path.join(adir, t + ".wav")
            if not os.path.exists(p):
                p = os.path.join(adir, t + ".wav")
            x = lade(p)
            for a, b, idx in regionen(wt.get(t, [])):
                grenzen = sorted({a, b} | {g for j in je_tag.get(t, []) for g in (j["t0"], j["t1"]) if a < g < b}) if var != "orig" else [a, b]
                for g0, g1 in zip(grenzen, grenzen[1:]):
                    l2 = "Erzaehler"
                    if var != "orig":
                        for j in je_tag.get(t, []):
                            if j["t0"] - 0.05 <= (g0 + g1) / 2 <= j["t1"] + 0.05:
                                l2 = j["figur"]
                    if g1 - g0 > 0.05:
                        ref[var].append([round(t_off + g0, 3), round(t_off + g1, 3), l2, t])
            stuecke += [x, pause]
            t_off += (len(x) + len(pause)) / SR
        sf.write(os.path.join(ziel, f"spur_{var}.wav"), np.concatenate(stuecke), SR, subtype="PCM_16")
    json.dump(ref, open(os.path.join(ziel, "spur_ref.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump({"werk": book, "lang": lg, "sr": SR, "eichung": bool(eichen), "runden": [], "runden_frueher": frueher,
               "segmente": man},
              open(os.path.join(ziel, "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[paket] {len(man)} Segmente, Spur {t_off/60:.1f} min, {len(folge)} Saetze, Eichung {'ja' if eichen else 'nein'} -> {ziel}")
    return ziel


def praat_merkmale(x):
    """F0 zweistufig (Hirst 2011: 0.75*q25 .. 1.5*q75 gegen Oktavfehler); Formanten nur in kraeftigen,
    stimmhaften Rahmen mit plausiblen Werten; VTL aus Formantabstand F1-F4 (Reby & McComb 2003)."""
    import parselmouth
    from parselmouth.praat import call
    snd = parselmouth.Sound(x.astype(np.float64), SR)
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
    st = 12 * np.log2(f0[v] / 100.0)
    r.update(f0_hz=round(float(np.median(f0[v])), 1), f0_st=round(float(np.median(st)), 2),
             f0_p5_st=round(float(np.percentile(st, 5)), 2), f0_p95_st=round(float(np.percentile(st, 95)), 2),
             f0_bereich=[round(lo), round(hi)])
    inten = snd.to_intensity(minimum_pitch=max(lo, 60), time_step=0.01)
    tv = zeiten[v]
    iv = np.array([inten.get_value(t) for t in tv], float)
    tv = tv[np.nan_to_num(iv, nan=-1e9) >= np.nanpercentile(iv, 40)]
    decke = 5500  # fest fuer alle: vergleichbar, Formantanhebung wird nicht an der Decke gekappt
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
        r.update(formant_decke=decke, F=[round(float(m)) for m in med], dF=round(dF, 1),
                 vtl_cm=round(C_SCHALL / (2 * dF), 2), formant_rahmen=int(gut.sum()))
    try:
        h = call(snd, "To Harmonicity (cc)", 0.01, max(lo, 60), 0.1, 1.0).values
        h = h[h > -100]
        r["hnr_db"] = round(float(np.mean(h)), 2) if h.size else None
    except Exception:
        pass
    try:
        cep = call(snd.resample(16000), "To PowerCepstrogram", 60, 0.002, 5000, 50)
        r["cpps_db"] = round(call(cep, "Get CPPS", "no", 0.02, 0.0005, 60, 330, 0.05, "parabolic",
                                  0.001, 0.05, "Exponential decay", "Least squares"), 2)
    except Exception as e:
        r["cpps_fehler"] = str(e)[:80]
    return r


def messen(ziel, budget=None):
    """Praat-Merkmale aller noch nicht gemessenen Segmente. Rueckgabe: Anzahl offener Segmente."""
    man = json.load(open(os.path.join(ziel, "manifest.json"), encoding="utf-8"))["segmente"]
    pfad = os.path.join(ziel, "messung_praat.json")
    erg = json.load(open(pfad, encoding="utf-8")) if os.path.exists(pfad) else {}
    t_start = time.time()
    offen = [s for s in man if s["id"] not in erg]
    for i, s in enumerate(offen):
        if budget and time.time() - t_start > budget:
            break
        try:
            erg[s["id"]] = praat_merkmale(lade(os.path.join(ziel, "segmente", s["id"] + ".wav")))
        except Exception as e:
            erg[s["id"]] = {"fehler": str(e)[:120]}
        if i % 100 == 99:
            json.dump(erg, open(pfad, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(erg, open(pfad, "w", encoding="utf-8"), ensure_ascii=False)
    rest = len([s for s in man if s["id"] not in erg])
    print(f"[praat] {len(erg)} gemessen, REST {rest}")
    return rest


def _spur_ersetzen(book, lg, ziel, name, neu):
    """spur_vc mit ersetzten Spannen {job: audio} -> spur_<name>.wav (gleiche Referenz wie spur_vc)."""
    werk = werk_dir(book)
    jobs = {j["id"]: j for j in json.load(open(os.path.join(HIER, "gpu_overlay", f"{book}_{lg}", "jobs.json"), encoding="utf-8"))["jobs"]}
    ref = json.load(open(os.path.join(ziel, "spur_ref.json"), encoding="utf-8"))
    spur = lade(os.path.join(ziel, "spur_vc.wav"))
    wt = json.load(open(os.path.join(werk, "work", f"520_wortzeiten_{lg}.json"), encoding="utf-8"))["tags"]
    start = {}
    for a, b, lab, tag in ref["vc"]:
        if tag not in start:
            start[tag] = a - min(w["t0"] for w in wt[tag])
    for jid, y in neu.items():
        j = jobs[jid]; i0 = int(round((start[j["tag"]] + j["t0"]) * SR))
        spur[i0:i0 + len(y)] = y[:len(spur) - i0]
    sf.write(os.path.join(ziel, f"spur_{name}.wav"), spur, SR, subtype="PCM_16")
    ref[name] = ref["vc"]
    json.dump(ref, open(os.path.join(ziel, "spur_ref.json"), "w", encoding="utf-8"), ensure_ascii=False)


def _alte_messwerte_weg(ziel, praefix):
    pp = os.path.join(ziel, "messung_praat.json")
    if os.path.exists(pp):
        r = json.load(open(pp, encoding="utf-8"))
        json.dump({k: v for k, v in r.items() if not k.startswith(praefix)}, open(pp, "w", encoding="utf-8"))


def korrektur_varianten(book, lg):
    """Fuer jede Figur mit korrektur[lg] in casting.json: beide Stufen in ihrer Richtung (knapp, Grenze), ohne Tonhoehe
    -> Segmente kx__s1__<job>, kx__s2__<job> + spur_s1.wav, spur_s2.wav. Richtung = Vorzeichen des Formantfaktors."""
    sys.path.insert(0, os.path.join(HIER, "tools"))
    from overlay_korrektur import korrigieren
    figuren = {f: (-1 if float(k.get("formant_faktor", 1.0)) < 1 else +1) for f, k in korrekturen(book, lg).items()}
    if not figuren:
        print("[korrektur] keine Figur mit korrektur[%s] in casting.json" % lg)
        return
    ziel = paket_dir(book, lg)
    mp = os.path.join(ziel, "manifest.json")
    M = json.load(open(mp, encoding="utf-8"))
    man = [s for s in M["segmente"] if not (s["typ"] == "kx" and s.get("variante") in ("s1", "s2"))]
    neu = {"s1": {}, "s2": {}}
    for s in [s for s in man if s["typ"] == "vc" and s["figur"] in figuren]:
        r = figuren[s["figur"]]
        x = lade(os.path.join(ziel, "segmente", "vc__" + s["job"] + ".wav"))
        for var, ff in zip(("s1", "s2"), STUFEN[r]):
            y = korrigieren(x, SR, ff, 0)
            sid = f"kx__{var}__{s['job']}"
            sf.write(os.path.join(ziel, "segmente", sid + ".wav"), y, SR, subtype="PCM_16")
            man.append(dict(id=sid, typ="kx", variante=var, formant_faktor=ff, tonhoehe_ht=0, figur=s["figur"],
                            stimme=s["stimme"], tag=s["tag"], job=s["job"], dauer=round(len(y) / SR, 3)))
            neu[var][s["job"]] = y
    M["segmente"] = man
    json.dump(M, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for var in ("s1", "s2"):
        _alte_messwerte_weg(ziel, f"kx__{var}__")
        _spur_ersetzen(book, lg, ziel, var, neu[var])
    print(f"[korrektur] {', '.join(f'{f} ({STUFEN[r]})' for f, r in figuren.items())} -> kx__s1/s2 + spur_s1/s2.wav")


def runden_liste(M):
    """Pruefrunden in Reihenfolge: manifest['runden'], sonst aus kx-Varianten r<n> abgeleitet."""
    if M.get("runden"):
        return list(M["runden"])
    rs = {s.get("variante") for s in M["segmente"] if s["typ"] == "kx" and re.fullmatch(r"r\d+", s.get("variante") or "")}
    return sorted(rs, key=lambda r: int(r[1:]))


def runde(book, lg, name="auto"):
    """Fertiges Overlay NACH Korrektur (spannen/vc_korr, Montage vc/) als Runde <name> ins Paket:
    Segmente kx__<name>__<job> + spur_<name>.wav (gleiche Referenz wie spur_vc). name=auto -> naechstes r<n>."""
    werk = werk_dir(book)
    ziel = paket_dir(book, lg)
    ovd = os.path.join(werk, "fassungen", lg, "audio_overlay")
    adir = os.path.join(werk, "fassungen", lg, "audio")
    mp = os.path.join(ziel, "manifest.json")
    M = json.load(open(mp, encoding="utf-8"))
    rl = runden_liste(M)
    if name == "auto":
        n = max([int(r[1:]) for r in rl + M.get("runden_frueher", []) if re.fullmatch(r"r\d+", r)] or [0]) + 1
        name = f"r{n}"
    man = [x for x in M["segmente"] if not (x["typ"] == "kx" and x.get("variante") == name)]
    korr = korrekturen(book, lg)
    quelle = os.path.join(ovd, "spannen", "vc_korr")
    if not os.path.isdir(quelle):
        print("  [runde] spannen/vc_korr fehlt -> spannen/vc (ohne Korrektur)")
        quelle = os.path.join(ovd, "spannen", "vc")
    for x in [x for x in man if x["typ"] == "vc"]:
        y = lade(os.path.join(quelle, x["job"] + ".wav"))
        sid = f"kx__{name}__{x['job']}"
        sf.write(os.path.join(ziel, "segmente", sid + ".wav"), y, SR, subtype="PCM_16")
        k = korr.get(x["figur"], {})
        man.append(dict(id=sid, typ="kx", variante=name, formant_faktor=float(k.get("formant_faktor", 1.0)),
                        tonhoehe_ht=k.get("tonhoehe_ht", 0), figur=x["figur"], stimme=x["stimme"], tag=x["tag"],
                        job=x["job"], dauer=round(len(y) / SR, 3)))
    M["segmente"] = man
    M["runden"] = [r for r in rl if r != name] + [name]
    json.dump(M, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    _alte_messwerte_weg(ziel, f"kx__{name}__")
    ref = json.load(open(os.path.join(ziel, "spur_ref.json"), encoding="utf-8"))
    tags = []
    for a, b, lab, tag in ref["vc"]:
        if not tags or tags[-1] != tag:
            tags.append(tag)
    pause = np.zeros(int(0.4 * SR), "float32")
    jt = {x["tag"] for x in man if x["typ"] == "vc"}
    stuecke = []
    for t in tags:
        p = os.path.join(ovd, "vc", t + ".wav")
        stuecke += [lade(p if (t in jt and os.path.exists(p)) else os.path.join(adir, t + ".wav")), pause]
    sf.write(os.path.join(ziel, f"spur_{name}.wav"), np.concatenate(stuecke), SR, subtype="PCM_16")
    ref[name] = ref["vc"]
    json.dump(ref, open(os.path.join(ziel, "spur_ref.json"), "w", encoding="utf-8"), ensure_ascii=False)
    kl = ", ".join(f"{f} {k.get('formant_faktor', 1)}" for f, k in korr.items()) or "-"
    print(f"[runde {name}] {sum(1 for x in man if x.get('variante') == name)} Spannen + spur_{name}.wav (Korrektur: {kl})")
    return name


def opt(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv and sys.argv.index(name) + 1 < len(sys.argv) else default


if __name__ == "__main__":
    pos_args = [x for i, x in enumerate(sys.argv[1:], 1)
                if not x.startswith("--") and sys.argv[i - 1] not in ("--runde", "--budget")]
    if len(pos_args) < 2:
        sys.exit(__doc__)
    book, lg = pos_args[0], pos_args[1]
    ziel = paket_dir(book, lg)
    if "--neu" in sys.argv or veraltet(book, lg):
        paket_bauen(book, lg, eichen="--eichen" in sys.argv)
    if "--korrektur" in sys.argv:
        korrektur_varianten(book, lg)
    if "--runde" in sys.argv:
        runde(book, lg, opt("--runde", "auto"))
    if "--nur-paket" not in sys.argv:
        b = opt("--budget")
        messen(ziel, budget=float(b) if b else None)
