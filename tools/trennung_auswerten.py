"""READ LAYER - Auswertung Sprechertrennung Erzaehler <-> Figur (nach tools/trennung_messen.py + Modal-Lauf).

Aufruf:  py -3.11 tools/trennung_auswerten.py <werk> <lg> [--eichen] [--ohne-rueckfluss]
Liest  gpu_messung/<werk>_<lg>/{manifest.json, messung_praat.json, ergebnis_modal.zip (optional)}
       stimmen_archiv/_trennungsregel.json (Regel + Schwellen; ohne --eichen massgeblich)
Schreibt
  gpu_messung/<werk>_<lg>/auswertung.json + BERICHT_trennung.md
  authors/.../<werk>/work/casting.json: ensemble[].pruefung[lg] je Figur (ECAPA, pyannote, Runde, Urteil)
      ok         getrennt (ECAPA) und naeher an der Zielstimme als am Erzaehler
      nachrunde  nicht getrennt, Formantgrenze noch nicht erreicht -> korrektur[lg] eine Stufe weiter (Richtung: VC
                 gegen Nachbar-Erzaehler auf der VTL-Achse); hoechstens EINE Nachrunde
      umbesetzen nicht getrennt an der Grenze / nach der Nachrunde, oder entfernt sich von der Zielstimme
  nur mit --eichen (Paket mit Archivsegmenten): stimmen_archiv/_trennungsregel.json neu
"""
import os, sys, json, glob, zipfile, io, itertools, collections, math
import numpy as np

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def st(x):  # Hz/cm -> Halbtoene (log-Skala)
    return 12 * np.log2(x)


def eer(gleich, versch):
    """Schwelle mit gleicher Fehlrate. Werte: groesser = eher verschieden."""
    g, v = np.asarray(gleich, float), np.asarray(versch, float)
    best = None
    for t in np.unique(np.concatenate([g, v])):
        fa = np.mean(v < t)   # verschieden faelschlich "gleich"
        fr = np.mean(g >= t)  # gleich faelschlich "verschieden"
        if best is None or abs(fa - fr) < best[0]:
            best = (abs(fa - fr), float(t), float((fa + fr) / 2))
    return best[1], best[2]


def logit_fit(X, y, it=50, lam=1e-3):
    X = np.hstack([X, np.ones((len(X), 1))]); w = np.zeros(X.shape[1])
    for _ in range(it):
        p = 1 / (1 + np.exp(-X @ w)); W = p * (1 - p)
        H = X.T @ (X * W[:, None]) + lam * np.eye(len(w)); w += np.linalg.solve(H, X.T @ (y - p) - lam * w)
    return w


REGEL_PFAD = os.path.join(HIER, "stimmen_archiv", "_trennungsregel.json")
# Stufen je Richtung bis zur Natuerlichkeitsgrenze (CK 16.10.2026, pipeline/trennung.py)
STUFEN = {+1: [1.05, 1.10], -1: [0.97, 0.94]}


def main(book, lg="de", eichen=False, rueckfluss_an=True):
    z = os.path.join(HIER, "gpu_messung", f"{book}_{lg}")
    man = {s["id"]: s for s in json.load(open(os.path.join(z, "manifest.json"), encoding="utf-8"))["segmente"]}
    pr = json.load(open(os.path.join(z, "messung_praat.json"), encoding="utf-8"))
    reg = json.load(open(os.path.join(HIER, "stimmen_archiv", "stimmen.json"), encoding="utf-8"))
    ok = {k: v for k, v in pr.items() if "vtl_cm" in v and v.get("stimmhaft_s", 0) >= 0.3}
    A = {"werk": book, "lang": lg}
    M = json.load(open(os.path.join(z, "manifest.json"), encoding="utf-8"))
    eichen = eichen and any(s["typ"] == "ar" for s in man.values())
    R = json.load(open(REGEL_PFAD, encoding="utf-8"))

    # ---------- 1) Eichung F0 x VTL an Archivpaaren ----------
    # Ebene "clip": je Archiv-Clip Median ueber seine 3-s-Stuecke (Stimme gegen Stimme, fuer das Casting)
    # Ebene "stueck": einzelne 3-s-Stuecke (kurze Spannen, fuer die Pruefung am Overlay)
    stuecke = [(k, man[k]) for k in ok if man[k]["typ"] == "ar"]
    clips = collections.defaultdict(list)
    for k, s in stuecke:
        clips[(s["stimme"], s["clip"])].append(ok[k])
    clipwert = {(man[k]["stimme"], man[k]["clip"]): (st(ok[k]["f0_hz"]), st(ok[k]["vtl_cm"]))
                for k in ok if man[k]["typ"] == "arf"}
    def paare(elemente, wert, schluessel):
        g, v = [], []
        for (a, b) in itertools.combinations(elemente, 2):
            d = (abs(wert[a][0] - wert[b][0]), abs(wert[a][1] - wert[b][1]))
            (g if schluessel(a) == schluessel(b) else v).append(d)
        return np.array(g), np.array(v)
    stwert = {k: (st(ok[k]["f0_hz"]), st(ok[k]["vtl_cm"])) for k, _ in stuecke}
    if eichen:
        eich = {}
        for ebene, elem, wert, key in (("clip", list(clipwert), clipwert, lambda c: c[0]),
                                       ("stueck", list(stwert), stwert, lambda k: man[k]["stimme"])):
            g, v = paare(elem, wert, key)
            # Streuung innerhalb derselben Stimme = Massstab je Achse
            # robust: typischer Unterschied zweier Aufnahmen DERSELBEN Stimme (Median) = 1 Einheit
            sF, sV = float(np.median(g[:, 0])), float(np.median(g[:, 1]))
            D = lambda d: np.sqrt((d[:, 0] / sF) ** 2 + (d[:, 1] / sV) ** 2)
            thr, e = eer(D(g), D(v))
            X = np.vstack([g, v]); y = np.r_[np.zeros(len(g)), np.ones(len(v))]
            w = logit_fit(X, y)
            nur_f0 = eer(g[:, 0], v[:, 0]); nur_vtl = eer(g[:, 1], v[:, 1])
            eich[ebene] = dict(n_gleich=len(g), n_versch=len(v), skala_f0_ht=round(float(sF), 3),
                               skala_vtl_ht=round(float(sV), 3), D_schwelle=round(thr, 3), D_eer=round(e, 3),
                               nur_f0=dict(schwelle_ht=round(nur_f0[0], 2), eer=round(nur_f0[1], 3)),
                               nur_vtl=dict(schwelle_ht=round(nur_vtl[0], 2), eer=round(nur_vtl[1], 3)),
                               logit=[round(float(x), 3) for x in w],
                               gleich_median_ht=[round(float(x), 2) for x in np.median(g, axis=0)],
                               gleich_p95_ht=[round(float(x), 2) for x in np.percentile(g, 95, axis=0)])
    else:   # Regel aus Datei (geeicht an Ruf der Wildnis, 16.10.2026)
        eich = {"clip": dict(skala_f0_ht=R["skala_f0_ht"], skala_vtl_ht=R["skala_vtl_ht"], D_schwelle=R["D_schwelle"],
                             D_eer=R.get("eer_f0_vtl"), quelle="_trennungsregel.json"),
                "stueck": dict(R["stueck"], quelle="_trennungsregel.json")}
    A["eichung_f0_vtl"] = eich
    E = eich["clip"]
    def D_clip(dF, dV):
        return math.hypot(dF / E["skala_f0_ht"], dV / E["skala_vtl_ht"])

    # ---------- 2) Messung am fertigen Overlay ----------
    def agg(ids):
        ids = [i for i in ids if i in ok]
        if not ids:
            return None
        w = np.array([ok[i]["stimmhaft_s"] for i in ids])
        f = np.array([st(ok[i]["f0_hz"]) for i in ids]); v = np.array([st(ok[i]["vtl_cm"]) for i in ids])
        return dict(f0_hz=round(float(2 ** (np.average(f, weights=w) / 12)), 1),
                    vtl_cm=round(float(2 ** (np.average(v, weights=w) / 12)), 2),
                    hnr_db=round(float(np.nanmean([ok[i].get("hnr_db") or np.nan for i in ids])), 1),
                    cpps_db=round(float(np.nanmean([ok[i].get("cpps_db") or np.nan for i in ids])), 1),
                    n=len(ids), stimmhaft_s=round(float(w.sum()), 1))
    def abstand(a, b):
        dF = st(a["f0_hz"]) - st(b["f0_hz"]); dV = st(a["vtl_cm"]) - st(b["vtl_cm"])
        return dict(dF0_ht=round(float(dF), 2), dVTL_ht=round(float(dV), 2), dVTL_proz=round(100 * (2 ** (dV / 12) - 1), 1),
                    D=round(D_clip(dF, dV), 2), getrennt=bool(D_clip(dF, dV) >= E["D_schwelle"]))
    erz = agg([k for k in ok if man[k]["typ"] in ("nb", "en")])
    A["erzaehler"] = erz
    figs = sorted({s["figur"] for s in man.values() if s["typ"] == "vc"})
    A["figuren"] = {}
    for f in figs:
        e = {}
        for typ in ("vc", "v1", "os", "nb"):
            a = agg([k for k, s in man.items() if s["typ"] == typ and s.get("figur") == f])
            if a:
                e[typ] = a
        stimme = next(s["stimme"] for s in man.values() if s.get("figur") == f and s["typ"] == "vc")
        r = ok.get("ref__" + stimme)
        if r:
            e["ref"] = dict(f0_hz=r["f0_hz"], vtl_cm=r["vtl_cm"])
        e["stimme"] = stimme
        e["rufname"] = reg.get(stimme, {}).get("rufname")
        for typ in ("vc", "v1"):
            if typ in e:
                e[f"abstand_{typ}_zu_nachbar"] = abstand(e[typ], e["nb"])
                e[f"abstand_{typ}_zu_erzaehler"] = abstand(e[typ], erz)
        if "ref" in e:
            e["abstand_ref_zu_erzaehler"] = abstand(e["ref"], erz)
        # je Spanne (Stueck-Ebene)
        sp = []
        S = eich["stueck"]
        for k, s in man.items():
            if s["typ"] == "vc" and s["figur"] == f and k in ok and ("nb__" + s["job"]) in ok:
                a, b = ok[k], ok["nb__" + s["job"]]
                dF = st(a["f0_hz"]) - st(b["f0_hz"]); dV = st(a["vtl_cm"]) - st(b["vtl_cm"])
                Dd = math.hypot(dF / S["skala_f0_ht"], dV / S["skala_vtl_ht"])
                sp.append(dict(job=s["job"], dF0_ht=round(dF, 2), dVTL_ht=round(dV, 2), D=round(Dd, 2),
                               getrennt=bool(Dd >= S["D_schwelle"])))
        e["spannen"] = sp
        e["anteil_spannen_getrennt"] = round(np.mean([x["getrennt"] for x in sp]), 2) if sp else None
        A["figuren"][f] = e
    # Korrekturvarianten nach VC (kx__<var>__<job>)
    for f, e in A["figuren"].items():
        kv = {}
        for var in sorted({s.get("variante") for s in man.values() if s["typ"] == "kx" and s.get("figur") == f}):
            ids = [k for k, s in man.items() if s["typ"] == "kx" and s.get("figur") == f and s.get("variante") == var]
            a = agg(ids)
            s0 = man[ids[0]]
            kv[var] = dict(formant_faktor=s0["formant_faktor"], tonhoehe_ht=s0["tonhoehe_ht"], praat=a,
                           abstand_zu_nachbar=abstand(a, e["nb"]) if a else None)
        if kv:
            e["korrektur_varianten"] = kv
    # Uebertragung Referenz -> VC-Ergebnis (wie viel der Zielstimme kommt an?)
    xs = [(st(A["figuren"][f]["ref"]["f0_hz"]) - st(A["figuren"][f]["os"]["f0_hz"]),
           st(A["figuren"][f]["vc"]["f0_hz"]) - st(A["figuren"][f]["os"]["f0_hz"]),
           st(A["figuren"][f]["ref"]["vtl_cm"]) - st(A["figuren"][f]["os"]["vtl_cm"]),
           st(A["figuren"][f]["vc"]["vtl_cm"]) - st(A["figuren"][f]["os"]["vtl_cm"])) for f in figs if "ref" in A["figuren"][f]]
    xs = np.array(xs)
    if len(xs) == 0:
        xs = np.ones((1, 4))
    A["vc_uebertragung"] = dict(f0=round(float((xs[:, 0] * xs[:, 1]).sum() / (xs[:, 0] ** 2).sum()), 2),
                                vtl=round(float((xs[:, 2] * xs[:, 3]).sum() / (xs[:, 2] ** 2).sum()), 2),
                                hinweis="Anteil der Differenz Referenz-Erzaehlerzitat, der im VC-Ergebnis ankommt (Regression durch 0)")

    # ---------- 3) ECAPA + Diarisierung (falls Modal-Ergebnis da) ----------
    zp = os.path.join(z, "ergebnis_modal.zip")
    ecapa = None
    if os.path.exists(zp):
        zf = zipfile.ZipFile(zp)
        npz = np.load(io.BytesIO(zf.read("embeddings.npz")))
        emb = {i: e / np.linalg.norm(e) for i, e in zip(npz["ids"], npz["emb"])}
        cos = lambda a, b: float(np.dot(a, b))
        mittel = lambda ids: (lambda m: m / np.linalg.norm(m))(np.mean([emb[i] for i in ids], axis=0))
        # Eichung: 3-s-Stuecke (Archiv) + Erzaehler-Saetze des Werks
        ar = [k for k in emb if man[k]["typ"] == "ar"]
        g = [1 - cos(emb[a], emb[b]) for a, b in itertools.combinations(ar, 2) if man[a]["stimme"] == man[b]["stimme"]]
        v = [1 - cos(emb[a], emb[b]) for a, b in itertools.combinations(ar, 2) if man[a]["stimme"] != man[b]["stimme"]]
        en = [k for k in emb if man[k]["typ"] in ("en", "nb")]
        g_werk = [1 - cos(emb[a], emb[b]) for a, b in itertools.combinations(en, 2)]
        if eichen and g and v:
            thr, e_rate = eer(g + g_werk, v)
        else:
            thr, e_rate = R["ecapa"]["stueck"]["schwelle_cosdist"], R["ecapa"]["stueck"]["eer"]
        # Clip-Ebene (Mittel je Clip)
        ck = collections.defaultdict(list)
        for k in ar:
            ck[(man[k]["stimme"], man[k]["clip"])].append(k)
        cm = {(man[k]["stimme"], man[k]["clip"]): emb[k] for k in emb if man[k]["typ"] == "arf"}
        gc = [1 - cos(cm[a], cm[b]) for a, b in itertools.combinations(cm, 2) if a[0] == b[0]]
        vc_ = [1 - cos(cm[a], cm[b]) for a, b in itertools.combinations(cm, 2) if a[0] != b[0]]
        if eichen and gc and vc_:
            thr_c, e_c = eer(gc, vc_)
            ecapa = dict(stueck=dict(schwelle_cosdist=round(thr, 3), eer=round(e_rate, 3), n_gleich=len(g) + len(g_werk), n_versch=len(v)),
                         clip=dict(schwelle_cosdist=round(thr_c, 3), eer=round(e_c, 3)))
        else:
            thr_c = R["ecapa"]["clip"]["schwelle_cosdist"]
            ecapa = dict(R["ecapa"], quelle="_trennungsregel.json")
        erz_m = mittel([k for k in emb if man[k]["typ"] == "en"])
        for f, e in A["figuren"].items():
            for typ in ("vc", "v1", "os"):
                ids = [k for k in emb if man[k]["typ"] == typ and man[k].get("figur") == f]
                if not ids:
                    continue
                fm = mittel(ids)
                ref_id = "ref__" + e["stimme"]
                d_erz = 1 - cos(fm, erz_m)
                d_ref = 1 - cos(fm, emb[ref_id]) if ref_id in emb else None
                je = []
                for k in ids:
                    nb = emb.get("nb__" + man[k]["job"])
                    if nb is None:
                        continue
                    dn = 1 - cos(emb[k], nb); dr = 1 - cos(emb[k], emb[ref_id]) if ref_id in emb else None
                    je.append(dict(job=man[k]["job"], cosdist_nachbar=round(dn, 3), cosdist_ref=None if dr is None else round(dr, 3),
                                   verschieden=bool(dn >= thr), naeher_an_ref=None if dr is None else bool(dr < dn)))
                e[f"ecapa_{typ}"] = dict(cosdist_erzaehler=round(d_erz, 3), cosdist_ref=None if d_ref is None else round(d_ref, 3),
                                         verschieden=bool(d_erz >= thr_c), naeher_an_ref=None if d_ref is None else bool(d_ref < d_erz),
                                         spannen_verschieden=round(np.mean([x["verschieden"] for x in je]), 2) if je else None,
                                         spannen_naeher_an_ref=round(np.mean([x["naeher_an_ref"] for x in je if x["naeher_an_ref"] is not None]), 2) if je else None,
                                         spannen=je)
        for f, e in A["figuren"].items():
            for var, kv in (e.get("korrektur_varianten") or {}).items():
                ids = [k for k in emb if man[k]["typ"] == "kx" and man[k].get("figur") == f and man[k].get("variante") == var]
                if not ids:
                    continue
                fm = mittel(ids); ref_id = "ref__" + e["stimme"]
                je = [1 - cos(emb[k], emb["nb__" + man[k]["job"]]) for k in ids if ("nb__" + man[k]["job"]) in emb]
                d_erz = 1 - cos(fm, erz_m); d_ref = 1 - cos(fm, emb[ref_id]) if ref_id in emb else None
                kv["ecapa"] = dict(cosdist_erzaehler=round(d_erz, 3), cosdist_ref=None if d_ref is None else round(d_ref, 3),
                                   verschieden=bool(d_erz >= thr_c), naeher_an_ref=None if d_ref is None else bool(d_ref < d_erz),
                                   spannen_verschieden=round(float(np.mean([x >= thr for x in je])), 2) if je else None)
        # Vorhersage fuer das Casting: Referenz der Figur gegen den Erzaehler DIESES Werks
        for f, e in A["figuren"].items():
            r = emb.get("ref__" + e["stimme"])
            if r is not None:
                e["ecapa_ref_zu_erzaehler"] = round(1 - cos(r, erz_m), 3)
        # Diarisierung
        diar = json.loads(zf.read("diar.json"))
        ref = json.load(open(os.path.join(z, "spur_ref.json"), encoding="utf-8"))
        A["diarisierung"] = {"der": diar.get("der"), "pyannote_fehler": diar.get("pyannote_fehler")}
        for var, hyp in diar.get("pyannote", {}).items():
            A["diarisierung"][f"wechsel_{var}"] = wechsel_treffer(ref[var], hyp)
            A["diarisierung"][f"sprecher_{var}"] = len({h[2] for h in hyp})
            A["diarisierung"][f"figuren_{var}"] = figur_trennung(ref[var], hyp)
        for var, hyp in diar.get("pyannote_n", {}).items():
            A["diarisierung"][f"figuren_{var}_n"] = figur_trennung(ref[var], hyp)
        # Zweitmeinung ECAPA-Clustering
        from_ = {}
        for var in ("vc", "v1", "orig"):
            n = f"fenster_{var}.npy"
            if n in zf.namelist():
                W = np.load(io.BytesIO(zf.read(n)))
                fen = diar["ecapa_cluster"][var]["fenster"]
                try:   # Zweitmeinung, nicht gewertet - braucht scipy
                    from_[var] = cluster_bewertung(W, fen, ref[var], thr_c)
                except ImportError:
                    from_[var] = {"hinweis": "scipy fehlt - uebersprungen"}
        A["diarisierung"]["ecapa_cluster"] = from_
    A["ecapa_eichung"] = ecapa

    # ---------- 4) Regel ----------
    regel = dict(stand="aus " + book + "_" + lg, achsen="F0 (Halbtoene) x VTL (Halbtoene, aus Formantabstand F1-F4)",
                 skala_f0_ht=E["skala_f0_ht"], skala_vtl_ht=E["skala_vtl_ht"], D_schwelle=E["D_schwelle"],
                 D_ziel=round(E["D_schwelle"] * 1.25, 2), eer_f0_vtl=E["D_eer"],
                 stueck=dict(skala_f0_ht=eich["stueck"]["skala_f0_ht"], skala_vtl_ht=eich["stueck"]["skala_vtl_ht"],
                             D_schwelle=eich["stueck"]["D_schwelle"]),
                 vc_uebertragung=A["vc_uebertragung"], ecapa=ecapa,
                 erklaerung="D = sqrt((dF0/skala_f0)^2 + (dVTL/skala_vtl)^2), gemessen Figur(VC-Ergebnis) gegen Erzaehler. "
                            "getrennt, wenn D >= D_schwelle (EER an Archivpaaren); Casting zielt auf D_ziel (25 % Reserve).")
    if eichen:
        A["regel"] = regel
        json.dump(regel, open(REGEL_PFAD, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    else:
        A["regel"] = R
    # ---------- 5) Rueckfluss nach casting.json ----------
    A["runden"] = runden_liste(M)
    if ecapa:
        A["pruefung"] = pruefung(A, book, lg, man, z, schreiben=rueckfluss_an)
    json.dump(A, open(os.path.join(z, "auswertung.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    bericht(A, os.path.join(z, "BERICHT_trennung.md"))
    print(open(os.path.join(z, "BERICHT_trennung.md"), encoding="utf-8").read())


def wechsel_treffer(ref, hyp, tol=0.5):
    """Sprecherwechsel Erzaehler<->Figur laut Referenz: findet die Hypothese dort einen Wechsel (+-tol)?"""
    rw = [ref[i][0] for i in range(1, len(ref)) if ref[i][2] != ref[i - 1][2] and ref[i][0] - ref[i - 1][1] < 1.5]
    hs = sorted(hyp)
    hw, letzter = [], None
    for a, b, l in hs:
        if letzter is not None and l != letzter[2] and b - a > 0.2:
            hw.append(a)
        if b - a > 0.2:
            letzter = (a, b, l)
    if not rw:
        return dict(ref_wechsel=0, hyp_wechsel=len(hw))
    rec = np.mean([any(abs(h - r) <= tol for h in hw) for r in rw])
    prec = np.mean([any(abs(h - r) <= tol for r in rw) for h in hw]) if hw else 0.0
    return dict(ref_wechsel=len(rw), hyp_wechsel=len(hw), recall=round(float(rec), 3), precision=round(float(prec), 3))


def figur_trennung(ref, hyp, schritt=0.05):
    """Anteil der Redezeit je Figur, die pyannote NICHT dem Erzaehler-Sprecher zuordnet."""
    hyp = sorted(hyp)
    def lab(t):
        for a, b, l in hyp:
            if a <= t <= b:
                return l
        return None
    T = collections.defaultdict(collections.Counter)
    for a, b, l, _ in ref:
        for t in np.arange(a, b, schritt):
            T[l][lab(t)] += schritt
    erz = T["Erzaehler"].most_common(1)[0][0]
    return {l: dict(sekunden=round(sum(c.values()), 1), getrennt=round(1 - c[erz] / sum(c.values()), 2))
            for l, c in T.items()}


def cluster_bewertung(W, fen, ref, thr):
    from scipy.cluster.hierarchy import linkage, fcluster
    Z = linkage(W, method="average", metric="cosine")
    lab = fcluster(Z, t=thr, criterion="distance")
    # Fenster -> Referenzlabel
    rl = []
    for a, b in fen:
        m = (a + b) / 2
        rl.append(next((r[2] for r in ref if r[0] <= m <= r[1]), "?"))
    rl = np.array(rl)
    erz_cl = collections.Counter(lab[rl == "Erzaehler"]).most_common(1)[0][0]
    out = dict(cluster=int(lab.max()))
    for f in sorted(set(rl) - {"Erzaehler", "?"}):
        m = rl == f
        out[f] = dict(fenster=int(m.sum()), anteil_nicht_im_erzaehlercluster=round(float(np.mean(lab[m] != erz_cl)), 2))
    out["erzaehler_im_erzaehlercluster"] = round(float(np.mean(lab[rl == "Erzaehler"] == erz_cl)), 2)
    return out


def bericht(A, pfad):
    E = A["eichung_f0_vtl"]; L = []
    L.append(f"# Sprechertrennung Erzaehler <-> Figur - {A['werk']} [{A['lang']}]\n")
    L.append("## Eichung F0 x VTL (Archivpaare)")
    for eb, e in E.items():
        if "n_gleich" not in e:
            L.append(f"- {eb}: aus {e.get('quelle')} | Massstab F0 {e['skala_f0_ht']} HT, VTL {e['skala_vtl_ht']} HT | D-Schwelle {e['D_schwelle']}")
            continue
        L.append(f"- {eb}: {e['n_gleich']} gleich / {e['n_versch']} verschieden | Massstab F0 {e['skala_f0_ht']} HT, VTL {e['skala_vtl_ht']} HT "
                 f"| D-Schwelle {e['D_schwelle']} (EER {e['D_eer']:.1%}) | nur F0: {e['nur_f0']['schwelle_ht']} HT (EER {e['nur_f0']['eer']:.1%}) "
                 f"| nur VTL: {e['nur_vtl']['schwelle_ht']} HT (EER {e['nur_vtl']['eer']:.1%})")
    if A.get("ecapa_eichung"):
        ec = A["ecapa_eichung"]
        L.append(f"- ECAPA: Stueck-Schwelle Kosinus-Abstand {ec['stueck']['schwelle_cosdist']} (EER {ec['stueck']['eer']:.1%}), "
                 f"Clip-Schwelle {ec['clip']['schwelle_cosdist']} (EER {ec['clip']['eer']:.1%})")
    er = A["erzaehler"]
    L.append(f"\n## Erzaehler: {er['f0_hz']} Hz, VTL {er['vtl_cm']} cm, HNR {er['hnr_db']} dB, CPPS {er['cpps_db']} dB\n")
    L.append("## Figuren am fertigen Overlay (VC-Ergebnis gegen angrenzende Erzaehler-Rede)")
    L.append("| Figur (Stimme) | F0 VC | VTL VC | dF0 HT | dVTL | D | F0xVTL getrennt | Spannen getrennt | ECAPA verschieden | naeher an Ref | Spannen verschieden (ECAPA) |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for f, e in A["figuren"].items():
        a = e.get("abstand_vc_zu_nachbar", {}); v = e.get("vc", {}); ec = e.get("ecapa_vc", {})
        L.append(f"| {f} ({e.get('rufname')}) | {v.get('f0_hz')} Hz | {v.get('vtl_cm')} cm | {a.get('dF0_ht')} | {a.get('dVTL_proz')} % | {a.get('D')} | "
                 f"{'ja' if a.get('getrennt') else 'NEIN'} | {e.get('anteil_spannen_getrennt')} | "
                 f"{ec.get('verschieden', '-') if ec else '-'} | {ec.get('naeher_an_ref', '-') if ec else '-'} | {ec.get('spannen_verschieden', '-') if ec else '-'} |")
    vtr = A["vc_uebertragung"]
    L.append(f"\nVC-Uebertragung: von der Differenz Zielstimme - Erzaehlerzitat kommen F0 {vtr['f0']:.0%}, VTL {vtr['vtl']:.0%} im Ergebnis an.")
    for f, e in A["figuren"].items():
        if "abstand_v1_zu_nachbar" in e:
            a1, a2 = e["abstand_v1_zu_nachbar"], e["abstand_vc_zu_nachbar"]
            L.append(f"- {f}: vor Nachbesserung D {a1['D']} (dF0 {a1['dF0_ht']}, dVTL {a1['dVTL_proz']} %) -> nach D {a2['D']} (dF0 {a2['dF0_ht']}, dVTL {a2['dVTL_proz']} %)")
    if A.get("diarisierung"):
        d = A["diarisierung"]
        L.append("\n## Diarisierung")
        if d.get("pyannote_fehler"):
            L.append(f"- pyannote: {d['pyannote_fehler'][:200]}")
        for k, v in (d.get("der") or {}).items():
            L.append(f"- DER {k}: {v.get('diarization error rate', 0):.3f} (Verwechslung {v.get('confusion', 0):.1f} s von {v.get('total', 0):.1f} s)")
        vs = [k[8:] for k in d if k.startswith("wechsel_")]
        for var in vs:
            L.append(f"- {var}: {d[f'sprecher_{var}']} Sprecher erkannt, Wechsel {d[f'wechsel_{var}']}")
        figs = sorted({f for v in vs for f in d[f"figuren_{v}"] if f != "Erzaehler"})
        sp = [(v, f"figuren_{v}") for v in vs] + [(v + " (Sprecherzahl vorgegeben)", f"figuren_{v}_n") for v in vs if f"figuren_{v}_n" in d]
        L.append("\nAnteil Redezeit, die pyannote NICHT dem Erzaehler zuordnet:\n")
        L.append("| Figur | " + " | ".join(n for n, _ in sp) + " |")
        L.append("|---|" + "---|" * len(sp))
        for f in ["Erzaehler"] + figs:
            L.append(f"| {f} | " + " | ".join(str(d[k].get(f, {}).get("getrennt", "-")) for _, k in sp) + " |")
        L.append("- (ECAPA-Fenster-Clustering: Schwelle fuer 1,5-s-Fenster nicht geeicht -> nicht gewertet)")
    L.append("\n## Vorhersage beim Casting: Zielstimme (Referenz) gegen Erzaehler des Werks")
    L.append("| Figur | D F0xVTL | getrennt laut Regel | ECAPA Ref-Erz | Ergebnis VC: ECAPA verschieden |")
    L.append("|---|---|---|---|---|")
    for f, e in A["figuren"].items():
        a = e.get("abstand_ref_zu_erzaehler", {})
        L.append(f"| {f} | {a.get('D')} | {'ja' if a.get('getrennt') else 'NEIN'} | {e.get('ecapa_ref_zu_erzaehler', '-')} | {(e.get('ecapa_vc') or {}).get('verschieden', '-')} |")
    if any(e.get("korrektur_varianten") for e in A["figuren"].values()):
        L.append("\n## Korrektur nach VC (Formantfaktor, Tonhoehe)")
        L.append("| Figur | Variante | Formant | HT | dF0 | dVTL | D | ECAPA Abstand Erz | verschieden | naeher an Ref | Spannen verschieden |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for f, e in A["figuren"].items():
            ec0 = e.get("ecapa_vc") or {}
            a0 = e.get("abstand_vc_zu_nachbar", {})
            if e.get("korrektur_varianten"):
                L.append(f"| {f} | ohne | 1.0 | 0 | {a0.get('dF0_ht')} | {a0.get('dVTL_proz')} % | {a0.get('D')} | {ec0.get('cosdist_erzaehler','-')} | {ec0.get('verschieden','-')} | {ec0.get('naeher_an_ref','-')} | {ec0.get('spannen_verschieden','-')} |")
            for var, kv in (e.get("korrektur_varianten") or {}).items():
                a = kv.get("abstand_zu_nachbar") or {}; ec = kv.get("ecapa") or {}
                L.append(f"| {f} | {var} | {kv['formant_faktor']} | {kv['tonhoehe_ht']} | {a.get('dF0_ht')} | {a.get('dVTL_proz')} % | {a.get('D')} | "
                         f"{ec.get('cosdist_erzaehler','-')} | {ec.get('verschieden','-')} | {ec.get('naeher_an_ref','-')} | {ec.get('spannen_verschieden','-')} |")
    if A.get("pruefung"):
        P = A["pruefung"]
        L.append(f"\n## Hoerspiel-Pruefung (Runde {P['runde'] or 'vc'}) -> casting.json")
        L.append("| Figur | Formant | ECAPA vorher -> jetzt (Schwelle) | naeher an Ziel | pyannote getrennt | Urteil | Grund |")
        L.append("|---|---|---|---|---|---|---|")
        for f, p in P["figuren"].items():
            ec = p["ecapa"]; py = p["pyannote"]
            L.append(f"| {f} | {p['korrektur']} | {ec['vorher']} -> {ec['jetzt']} ({ec['schwelle']}) | {ec['naeher_an_ziel']} | "
                     f"{py['vorher']} -> {py['jetzt']} | **{p['urteil']}** | {p['grund']} |")
    L.append(f"\n## Regel\n{A['regel']['erklaerung']}\nD_schwelle {A['regel']['D_schwelle']}, D_ziel {A['regel']['D_ziel']}")
    open(pfad, "w", encoding="utf-8").write("\n".join(L) + "\n")


def runden_liste(M):
    import re
    if M.get("runden"):
        return list(M["runden"])
    rs = {s.get("variante") for s in M["segmente"] if s["typ"] == "kx" and re.fullmatch(r"r\d+", s.get("variante") or "")}
    return sorted(rs, key=lambda r: int(r[1:]))


def _richtung(F, e):
    """+1 = kleiner/heller (Formant > 1), -1 = groesser/dunkler. Gemessen: VC gegen angrenzenden Erzaehler auf der
    VTL-Achse; unter 2 % Unterschied entscheidet der Steckbrief (pipeline/trennung.richtung)."""
    a = F.get("abstand_vc_zu_nachbar") or {}
    d = a.get("dVTL_proz")
    if d is not None and abs(d) >= 2:
        return -1 if d > 0 else +1
    m = (e.get("steckbrief") or {}).get("merkmale") or {}
    if m.get("alter") in ("alt", "greis") or m.get("tonlage") == "tief" or "kraeftig" in (m.get("klangfarbe") or []):
        return -1
    if m.get("alter") in ("kind", "jung") or m.get("tonlage") == "hoch" or m.get("geschlecht") == "w":
        return +1
    return -1 if (a.get("dF0_ht") or 0) < 0 else +1


def pruefung(A, book, lg, man, z, schreiben=True):
    """Urteil je Figur aus der juengsten Runde; schreibt ensemble[].pruefung[lg] (+ ggf. korrektur[lg]) nach casting.json."""
    import datetime as dt, shutil
    werk = glob.glob(os.path.join(HIER, "authors", "*", "books", book))[0]
    cp = os.path.join(werk, "work", "casting.json")
    cast = json.load(open(cp, encoding="utf-8"))
    runde = A["runden"][-1] if A.get("runden") else None
    D = A.get("diarisierung") or {}
    schwelle = (A.get("ecapa_eichung") or {}).get("clip", {}).get("schwelle_cosdist")
    heute = dt.date.today().isoformat()
    out = {"runde": runde, "datum": heute, "figuren": {}}
    for e in cast["plan"]["ensemble"]:
        f = e["figur"]; F = A["figuren"].get(f)
        if not F or not F.get("ecapa_vc"):
            continue
        kv = (F.get("korrektur_varianten") or {}).get(runde) if runde else None
        if kv and kv.get("ecapa"):
            jetzt, ff = kv["ecapa"], float(kv.get("formant_faktor") or 1.0)
            D_jetzt = (kv.get("abstand_zu_nachbar") or {}).get("D")
        else:
            jetzt, ff, D_jetzt = F["ecapa_vc"], 1.0, (F.get("abstand_vc_zu_nachbar") or {}).get("D")
        alt = (e.get("pruefung") or {}).get(lg) or {}
        basis = alt.get("nachrunden", 0) - (1 if alt.get("runde") == runde and alt.get("urteil") == "nachrunde" else 0)
        r = _richtung(F, e)
        weiter = [s for s in STUFEN[r] if (s > ff + 1e-6 if r > 0 else s < ff - 1e-6)]
        getrennt, naeher = jetzt.get("verschieden"), jetzt.get("naeher_an_ref")
        neu = None
        if getrennt and naeher is not False:
            urteil, grund = "ok", "getrennt und naeher an der Zielstimme"
        elif naeher is False:
            urteil, grund = "umbesetzen", "entfernt sich von der Zielstimme"
        elif basis >= 1:
            urteil, grund = "umbesetzen", "nach der Nachrunde nicht getrennt"
        elif not weiter:
            urteil, grund = "umbesetzen", f"nicht getrennt an der Natuerlichkeitsgrenze ({ff})"
        else:
            neu = weiter[0]
            urteil, grund = "nachrunde", f"nicht getrennt -> Formant {ff} -> {neu} ({'kleiner/heller' if r > 0 else 'groesser/dunkler'})"
        # Hoerprobe: laengste Spanne der Figur
        sp = sorted([s for s in man.values() if s["typ"] == "vc" and s.get("figur") == f], key=lambda s: -s["dauer"])
        hp = {}
        if sp:
            j = sp[0]["job"]; rel = os.path.relpath(z, HIER).replace("\\", "/") + "/segmente/"
            hp = {"vorher": rel + f"vc__{j}.wav", "erzaehler": rel + f"nb__{j}.wav"}
            if runde and os.path.exists(os.path.join(z, "segmente", f"kx__{runde}__{j}.wav")):
                hp["nachher"] = rel + f"kx__{runde}__{j}.wav"
        p = {"datum": heute, "runde": runde, "korrektur": ff, "richtung": r,
             "D": {"casting": ((e.get("trennung") or {}).get(lg) or {}).get("D"),
                   "vorher": (F.get("abstand_vc_zu_nachbar") or {}).get("D"), "jetzt": D_jetzt},
             "ecapa": {"vorher": F["ecapa_vc"]["cosdist_erzaehler"], "jetzt": jetzt.get("cosdist_erzaehler"),
                       "ziel_jetzt": jetzt.get("cosdist_ref"), "schwelle": schwelle,
                       "getrennt": bool(getrennt), "naeher_an_ziel": naeher},
             "pyannote": {"vorher": (D.get("figuren_vc") or {}).get(f, {}).get("getrennt"),
                          "jetzt": (D.get(f"figuren_{runde}") or {}).get(f, {}).get("getrennt") if runde else None},
             "urteil": urteil, "grund": grund, "nachrunden": basis + (1 if urteil == "nachrunde" else 0),
             "korrektur_neu": neu, "hoerprobe": hp,
             "entscheidung": alt.get("entscheidung") if alt.get("runde") == runde else None}
        out["figuren"][f] = p
        if schreiben:
            e.setdefault("pruefung", None)
            e["pruefung"] = dict(e.get("pruefung") or {}, **{lg: p})
            if neu is not None:
                k = e.get("korrektur") or {}
                if k and not any(x in k for x in ("de", "en")):
                    k = {lg: k}
                k[lg] = {"formant_faktor": neu, "tonhoehe_ht": 0, "grund": grund,
                         "quelle": f"Hoerspiel-Pruefung {runde or 'vc'}, {heute}"}
                e["korrektur"] = k
    if schreiben and out["figuren"]:
        bak = cp + ".bak_pruefung_" + heute.replace("-", "")
        if not os.path.exists(bak):
            shutil.copy2(cp, bak)
        cast.setdefault("hoerspiel_tor", {})[lg] = "offen"
        tmp = cp + ".tmp"
        json.dump(cast, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.replace(tmp, cp)
        print(f"[rueckfluss] casting.json: " + ", ".join(f"{f}: {p['urteil']}" for f, p in out["figuren"].items()))
    return out


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    main(a[0], a[1] if len(a) > 1 else "de", eichen="--eichen" in sys.argv,
         rueckfluss_an="--ohne-rueckfluss" not in sys.argv)
