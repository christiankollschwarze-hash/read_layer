"""STAGE 511 — Fish-Gleis der Stage 510 (Overlay -> VC, AP Fish-Regie 25.11.2026), kein eigenes Gate (Katalogzeile 510).
Funktion:     Hoerspielspur je Hoerspiel-Sprache mit Motor Fish: Quelle = Fish-Erzaehleraufnahme der Figurenbeitraege
              (Spannen aus dem 500-Schnitt, work/500_vertonung.json), Ziel = VC-Zielstimme der Figur aus 410 (vc_ziel =
              Archiv-Klon). Chatterbox-VC (gpu_overlay/overlay_gpu.py) auf Modal aus der Pipeline
              (gpu_overlay/vc_modal.py, GPU-Fallback L4/A10G/L40S, kein .bat). Danach je Figur korrektur[lg]
              (Formant/Tonhoehe, Praat), Lautheit an die Erzaehlerstuecke des Satzes, Einbau an der Zeitmarke mit
              Ueberblendung -> fassungen/<lg>/hoerspiel/<tid>.wav (nur Saetze mit Figurenanteil).
Wirkungsweise: VC-Cache je Beitrag work/_510/<lg>/vc/<id>.wav (Hash: 500-Satz-WAV, Spanne, Zielstimme, Version) – Korrektur
              oder Schnitt neu kosten 0 $. Manifest work/510_overlay.json <lg>/<tid> wie Gemini-Gleis (fuer 520).
              Hoerliste work/510_pruefung.json je Figurenbeitrag: vorher (Fish, work/_510/<lg>/src) / nachher (VC).
Pruefung:     je Beitrag Laenge VC/Quelle in [dauer_min, dauer_max], Nahtsprung <= naht_db (Fix 8 Gate-Katalog);
              auffaellig > auffaellig_max -> Mensch; Hoerspiel-Freigabe immer Mensch (gilt bei gleichem ausgabe_hash).
Kosten:       GPU-Minuten (Dialoganteil x RTF ~0,25 + Ladezeit) x config.MODAL_A10G_USD_H -> Freigabe wie 510.
Aufrufer:     pipeline/s510_hoerspiel_hybrid.run (Hoerspiel-Sprachen mit Motor fish).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

import numpy as np

from config import config
from pipeline import manifest, mock, status, usage_log
from pipeline import s410_casting as s410

VERSION = 1
SR = 24000
ERZ = "Erzaehler"
RTF = 0.25
LADEZEIT_S = 90


def vc_dir(werk, lg):
    return os.path.join(config.work_dir(werk), "_510", lg, "vc")


def src_dir(werk, lg):
    return os.path.join(config.work_dir(werk), "_510", lg, "src")


def paket_name(werk, lg):
    return f"{werk}_{lg}_510"


def paket_dir(werk, lg):
    return os.path.join(config.BASE_DIR, "gpu_overlay", paket_name(werk, lg))


def _s510():
    from pipeline import s510_hoerspiel_hybrid as s510
    return s510


# ============================================================ Planung
def planen(werk, lg, stufe, c, m500, m, rg, ent, saetze, kap, neu, probe):
    s510 = _s510()
    bs = (((c or {}).get("rollen") or {}).get(lg) or {}).get(stufe) or {}
    ens = {e["figur"]: e for e in bs.get("ensemble") or [] if e.get("figur") and e.get("vc_ziel")}
    sel = {}
    for k, e5 in m500.eintraege.items():
        if not k.startswith(f"{lg}/") or "/_fish/" in k or not e5.get("spannen"):
            continue
        tid = k.split("/", 1)[1]
        figs = [s_ for s_ in e5["spannen"] if s_["fig"] != ERZ and s_["fig"] in ens]
        if figs:
            sel[tid] = e5
    korr = {f: (e.get("korrektur") or {}) for f, e in ens.items()}
    soll, vc_soll, ohne500 = {}, {}, []
    for tid, e5 in sel.items():
        k5 = f"{lg}/{tid}"
        if not m500.datei_aktuell(k5) or (e5.get("q") == "mock" and not mock.aktiv()):
            ohne500.append(tid)
            continue
        figs = sorted({s_["fig"] for s_ in e5["spannen"] if s_["fig"] in ens})
        for s_ in e5["spannen"]:
            if s_["fig"] in ens:
                vc_soll[s_["id"]] = manifest.hash_obj({"d": e5.get("datei_hash"), "a": s_["a"], "b": s_["b"],
                                                       "z": ens[s_["fig"]]["vc_ziel"], "v": VERSION})
        soll[tid] = manifest.hash_obj({"d": e5.get("datei_hash"), "sp": e5["spannen"],
                                       "vc": {s_["id"]: vc_soll[s_["id"]] for s_ in e5["spannen"] if s_["fig"] in ens},
                                       "korr": {f: korr[f] for f in figs if s510._korr_aktiv(korr[f])},
                                       "n": [rg["ueberblend_ms"], rg["lautheit"]],
                                       "beh": f"{lg}/{tid}" in ent["behalten"], "v": VERSION})
    offen = []
    for tid in soll:
        k = f"{lg}/{tid}"
        mock_alt = (m.get(k) or {}).get("q") == "mock" and not mock.aktiv()
        if neu or tid in saetze or mock_alt or m.braucht_neu(k, soll[tid]) or not m.datei_aktuell(k):
            if kap and tid[:4] not in kap and tid not in saetze:
                continue
            offen.append(tid)
    if probe:
        offen = offen[:int(probe)]
    vdir = vc_dir(werk, lg)
    idx = _json(os.path.join(vdir, "index.json"), {}) or {}
    vc_neu = []
    for tid in offen:
        if f"{lg}/{tid}" in ent["behalten"]:
            continue
        for s_ in sel[tid]["spannen"]:
            if s_["fig"] in ens and (neu or tid in saetze or idx.get(s_["id"]) != vc_soll[s_["id"]]
                                     or not os.path.exists(os.path.join(vdir, f"{s_['id']}.wav"))):
                vc_neu.append((tid, s_))
    dial = sum(s_["b"] - s_["a"] for _, s_ in vc_neu)
    gpu_s = dial * RTF + (LADEZEIT_S if vc_neu else 0)
    usd = round(gpu_s / 3600 * float(getattr(config, "MODAL_A10G_USD_H", 1.10)), 4)
    return {"ens": ens, "korr": korr, "sel": sel, "soll": soll, "vc_soll": vc_soll, "offen": offen, "vc_neu": vc_neu,
            "ohne500": ohne500, "dial_s": round(dial, 1), "gpu_s": round(gpu_s), "usd": usd, "idx": idx}


def _json(p, leer=None):
    if not os.path.exists(p):
        return leer
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ============================================================ VC (Modal)
def quelle_schneiden(werk, lg, m500, tid, s_):
    s510 = _s510()
    e5 = m500.get(f"{lg}/{tid}")
    x = s510.lesen(m500._abs(e5["datei"]))
    y = x[int(s_["a"] * SR):int(s_["b"] * SR)]
    p = os.path.join(src_dir(werk, lg), f"{s_['id']}.wav")
    s510.schreiben(p, y)
    return p


def vc_lauf(werk, lg, p, m500):
    """VC fuer p['vc_neu'] -> Cache. -> (n_ok, fehler[list], gpu_s)."""
    s510 = _s510()
    vdir = vc_dir(werk, lg)
    os.makedirs(vdir, exist_ok=True)
    quellen = {s_["id"]: quelle_schneiden(werk, lg, m500, tid, s_) for tid, s_ in p["vc_neu"]}
    erg, gpu_s, bericht = {}, 0.0, ""
    if mock.aktiv():
        for bid, q in quellen.items():
            erg[bid] = s510.lesen(q)
    else:
        d = paket_dir(werk, lg)
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(os.path.join(d, "src"))
        os.makedirs(os.path.join(d, "ref"))
        jobs = []
        for tid, s_ in p["vc_neu"]:
            e = p["ens"][s_["fig"]]
            st = e["stimme"]
            ref = os.path.join(d, "ref", f"{st}.wav")
            if not os.path.exists(ref):
                shutil.copy2(os.path.join(config.BASE_DIR, e["vc_ziel"]), ref)
            shutil.copy2(quellen[s_["id"]], os.path.join(d, "src", f"{s_['id']}.wav"))
            jobs.append({"id": s_["id"], "figur": s_["fig"], "stimme": st, "text": "", "lang": lg})
        with open(os.path.join(d, "jobs.json"), "w", encoding="utf-8") as f:
            json.dump({"werk": werk, "lang": lg, "jobs": jobs}, f, ensure_ascii=False, indent=1)
        cmd = [sys.executable, "-m", "modal", "run", "gpu_overlay/vc_modal.py", "--paket", paket_name(werk, lg)]
        print(f"[511] Modal-VC: {len(jobs)} Figurenbeitraege ({p['dial_s']} s Dialog)", flush=True)
        from pipeline import spuren as SP
        with SP.modal_platz():
            r = subprocess.run(cmd, cwd=config.BASE_DIR)
        if r.returncode != 0:
            raise RuntimeError(f"Modal-VC {paket_name(werk, lg)} Exit {r.returncode}")
        z = zipfile.ZipFile(os.path.join(d, "ergebnis.zip"))
        for n in z.namelist():
            if n.startswith("vc/") and n.endswith(".wav"):
                tmp = os.path.join(d, "_vc.wav")
                with open(tmp, "wb") as f:
                    f.write(z.read(n))
                erg[os.path.basename(n)[:-4]] = s510.lesen(tmp)
        if "bericht.txt" in z.namelist():
            bericht = z.read("bericht.txt").decode("utf-8", "replace")
        mw = re.search(r"WALL ([\d.]+) s", bericht)
        gpu_s = float(mw.group(1)) if mw else p["gpu_s"]
        mg = re.search(r"GPU ([^\n|]+)", bericht)
        gpu = "A10G" if not mg else next((g for g in ("L40S", "A10G", "L4") if g in mg.group(1)), "A10G")
        usage_log.log_gpu(werk, "510", gpu_s, gpu=gpu, extra={"sprache": lg, "art": "fish-vc", "jobs": len(jobs)})
    idx = p["idx"]
    for bid, y in erg.items():
        s510.schreiben(os.path.join(vdir, f"{bid}.wav"), y)
        idx[bid] = p["vc_soll"][bid]
    manifest.json_atomar(os.path.join(vdir, "index.json"), idx, indent=1)
    fehler = [s_["id"] for _, s_ in p["vc_neu"] if s_["id"] not in erg]
    return len(erg), fehler, gpu_s


# ============================================================ Montage
def montage(x, spannen, vc, korr, rg):
    """Satz x (Fish) + {beitrags_id: vc_audio} -> (y, grund, werte, protokoll)."""
    s510 = _s510()
    teile, prot, grund = [], [], None
    dmin, dmax = float(rg["dauer_min"]), float(rg["dauer_max"])
    for s_ in spannen:
        a, b = int(s_["a"] * SR), int(s_["b"] * SR)
        src = x[a:b]
        if s_["id"] in vc:
            y = vc[s_["id"]].astype("float32").copy()
            q = len(y) / max(1, len(src))
            if not (dmin <= q <= dmax):
                grund = grund or "dauer"
            k = korr.get(s_["fig"]) or {}
            if s510._korr_aktiv(k):
                y = s510.korrigieren(y, SR, k.get("formant_faktor", 1.0), k.get("tonhoehe_ht", 0.0))
            teile.append(("fig", y))
            prot.append({"id": s_["id"], "fig": s_["fig"], "a": s_["a"], "b": s_["b"], "q": round(q, 3)})
        else:
            teile.append(("erz", src.copy()))
    erz = [y for q, y in teile if q == "erz" and len(y)]
    ref = s510._db_aktiv(np.concatenate(erz)) if erz else s510._db_aktiv(x)
    out, pegel, naht = [], [], 0.0
    kk = int(SR * float(rg["ueberblend_ms"]) / 1000)
    for i, (q, y) in enumerate(teile):
        if not len(y):
            continue
        if rg["lautheit"] and ref is not None and q == "fig":
            y = y * float(10 ** ((ref - s510._db_aktiv(y)) / 20))
        pegel.append((q, s510._db_aktiv(y)))
        k2 = min(len(y) // 2, kk)
        if k2:
            r = np.linspace(0, 1, k2, dtype="float32")
            y[:k2] *= r
            y[-k2:] *= r[::-1]
        if len(pegel) > 1 and pegel[-2][0] != q:
            naht = max(naht, abs(pegel[-1][1] - pegel[-2][1]))
        out.append(y)
    y = np.concatenate(out) if out else x
    if naht > float(rg["naht_db"]):
        grund = grund or "naht"
    return y, grund, {"naht_db": round(naht, 2), "dauer": round(len(y) / SR, 3)}, prot


def werkzeug(vc, korr):
    """-> Fehlertext oder None (modal fuer VC, parselmouth fuer Korrektur)."""
    try:
        if vc:
            import modal  # noqa: F401
        if korr:
            import parselmouth  # noqa: F401
        return None
    except Exception as e:
        return f"{type(e).__name__}: {str(e)[:80]}"


# ============================================================ Lauf
def run(werk, g, b, rg, c, m500, m, ent, wer, ziele, saetze=None, kapitel=None, nur_lang=None, neu=False,
        probe=None, kosten_freigeben=None, trocken=False, nachrunde=False):
    s510 = _s510()
    saetze, kap = set(saetze or []), set(kapitel or [])
    plan, je_sprache, pruef = {}, {}, {}
    for lg in sorted(ziele):
        if nur_lang and lg != nur_lang:
            continue
        stufe = ziele[lg]
        m5 = (m500.meta.get("je_sprache") or {}).get(lg) or {}
        bs = (((c or {}).get("rollen") or {}).get(lg) or {}).get(stufe) or {}
        erz = (bs.get("erzaehler") or {}).get("stimme")
        s510._pf(g, trocken, f"erzaehler_{lg}", m5.get("engine") == "fish" and m5.get("stimme") == erz,
                 ruecksprung="500", text=f"{lg}: Fish-Aufnahme 500 mit Erzaehler aus casting "
                                         f"({m5.get('engine')} {m5.get('stimme')} / casting {erz})")
        if not g.pflicht(f"engine_{lg}", bs.get("engine") == "fish", ruecksprung="410",
                         text=f"{lg}: Casting mit Engine fish ({bs.get('engine')})"):
            continue
        ohne_ziel = [e.get("figur") for e in bs.get("ensemble") or [] if e.get("stimme") and not e.get("vc_ziel")]
        if not g.pflicht(f"vc_ziel_{lg}", not ohne_ziel, ruecksprung="410",
                         text=f"{lg}: VC-Zielstimme je Figur" + (f" – fehlt: {', '.join(ohne_ziel[:4])}" if ohne_ziel else "")):
            continue
        for e in bs.get("ensemble") or []:
            if e.get("vc_ziel") and not os.path.exists(os.path.join(config.BASE_DIR, e["vc_ziel"])):
                g.pflicht(f"vc_datei_{lg}_{e['figur']}", False, ruecksprung="410",
                          text=f"{lg}: VC-Ziel {e['vc_ziel']} ({e['figur']}) fehlt")
        p = planen(werk, lg, stufe, c, m500, m, rg, ent, saetze, kap, neu, probe)
        _txt = f"{lg}: Figurensaetze mit aktueller Fish-Aufnahme {len(p['soll'])}/{len(p['sel'])}"
        if p["ohne500"]:
            s510._pf(g, trocken, f"quelle_{lg}", False, ruecksprung="500", text=_txt + f" – fehlt {p['ohne500'][:4]}")
        plan[lg] = p
    usd = round(sum(p["usd"] for p in plan.values()), 4)
    g.metrik("kosten_usd", usd)
    g.metrik("kosten_je_sprache", {lg: {"engine": "fish-vc", "beitraege": len(p["vc_neu"]), "dialog_s": p["dial_s"],
                                        "gpu_s": p["gpu_s"], "gpu_min": round(p["gpu_s"] / 60, 1), "usd": p["usd"],
                                        "saetze": len(p["offen"]), "takes": len(p["vc_neu"]), "zeichen": 0}
                                   for lg, p in plan.items()})
    g.metrik("offen", {lg: len(p["offen"]) for lg, p in plan.items()})
    if g.fehler():
        g.entscheide(schreiben=not trocken)
        return g
    # Werkzeuge: Modal fuer VC, parselmouth fuer aktive Korrektur
    braucht_vc = any(p["vc_neu"] for p in plan.values()) and not mock.aktiv()
    braucht_korr = any(p["offen"] and any(s510._korr_aktiv(k) for k in p["korr"].values()) for p in plan.values())
    fe = werkzeug(braucht_vc, braucht_korr)
    if fe:
        (g.hinweis if trocken else g.pflicht)("werkzeug", False, text=f"Werkzeug fehlt (Modal/parselmouth): {fe}")
        if not trocken:
            g.entscheide(schreiben=True)
            return g
    if not trocken and not mock.aktiv() and any(p["vc_neu"] for p in plan.values()):
        kf = kosten_freigeben if isinstance(kosten_freigeben, dict) else (
            {"*": kosten_freigeben} if kosten_freigeben is not None else {})
        im_budget = b.mandant_art == "somnio" and usd <= float(rg["budget"])
        from pipeline import s500_vertonung_gemini as s500
        frei = set(plan) if im_budget else s500._freigabe_je_sprache(kf, plan)
        frei |= {lg for lg, p in plan.items() if p["usd"] < float(getattr(config, "KOSTEN_KLEINBETRAG_USD", 0.01))}
        mit = {lg for lg, p in plan.items() if p["vc_neu"]}
        gesperrt = mit - frei
        for lg in sorted(gesperrt):
            p = plan[lg]
            g.pruefe(f"kosten_{lg}", False, wert=p["usd"], bei_fehler="mensch", ruecksprung="510",
                     text=f"{lg}: VC-Kosten ~{p['usd']:.2f} $ ({p['gpu_s'] / 60:.1f} GPU-min, {len(p['vc_neu'])} "
                          f"Beitraege) nicht freigegeben – Monitor 510 bzw. --kosten-freigeben {lg}={p['usd']:.2f}")
            p["offen"], p["vc_neu"], p["gesperrt"] = [], [], True
        if mit and gesperrt == mit:
            g.entscheide(schreiben=True)
            return g
    ausfall = None
    for lg, p in plan.items():
        n_vc, fehler = 0, []
        if p["offen"] and not trocken:
            usage_log.set_context(werk, "510", sprache=lg)
            try:
                if p["vc_neu"]:
                    n_vc, fehler, _gs = vc_lauf(werk, lg, p, m500)
            except Exception as e:
                ausfall = f"{lg}: {type(e).__name__}: {str(e)[:160]}"
                print(f"[511] Abbruch {ausfall}", flush=True)
            if ausfall is None:
                hdir = s510.hoerspiel_dir(werk, lg)
                vdir = vc_dir(werk, lg)
                for tid in p["offen"]:
                    e5 = p["sel"][tid]
                    pf = os.path.join(hdir, f"{tid}.wav")
                    x = s510.lesen(m500._abs(e5["datei"]))
                    if f"{lg}/{tid}" in ent["behalten"]:
                        y, grund, werte, prot = x, None, {"behalten": True}, []
                    else:
                        vc = {}
                        for s_ in e5["spannen"]:
                            q = os.path.join(vdir, f"{s_['id']}.wav")
                            if s_["fig"] in p["ens"] and os.path.exists(q):
                                vc[s_["id"]] = s510.lesen(q)
                        y, grund, werte, prot = montage(x, e5["spannen"], vc, p["korr"], rg)
                        if any(s_["fig"] in p["ens"] and s_["id"] not in vc for s_ in e5["spannen"]):
                            grund = grund or "vc_fehlt"
                    s510.schreiben(pf, y)
                    m.setzen(f"{lg}/{tid}", p["soll"][tid], datei=pf, engine="fish-vc",
                             q="mock" if mock.aktiv() else "neu", pruefung=grund, werte=werte, schnitt=prot,
                             figuren=sorted({s_["fig"] for s_ in e5["spannen"] if s_["fig"] in p["ens"]}),
                             dauer=round(len(y) / SR, 3))
                m.speichern()
        # Gate je Sprache
        ids = list(p["soll"])
        fehlt = [t for t in ids if not m.datei_aktuell(f"{lg}/{t}")]
        hoer = []
        for t in ids:
            e = m.get(f"{lg}/{t}") or {}
            if e.get("pruefung"):
                hoer.append({"id": t, "grund": e["pruefung"], "werte": e.get("werte"), "datei": e.get("datei")})
        beitraege = [{"tid": t, "id": s_["id"], "fig": s_["fig"],
                      "vorher": os.path.relpath(os.path.join(src_dir(werk, lg), f"{s_['id']}.wav"),
                                                config.book_dir(werk)).replace(os.sep, "/"),
                      "nachher": os.path.relpath(os.path.join(vc_dir(werk, lg), f"{s_['id']}.wav"),
                                                 config.book_dir(werk)).replace(os.sep, "/")}
                     for t in ids for s_ in p["sel"][t]["spannen"] if s_["fig"] in p["ens"]]
        if trocken:
            g.hinweis(f"abdeckung_{lg}", not fehlt, wert=len(fehlt),
                      text=f"{lg}: {len(ids) - len(fehlt)}/{len(ids)} Hoerspielsaetze; offen {len(p['offen'])}, "
                           f"VC neu {len(p['vc_neu'])} ({p['dial_s']} s, ~{p['usd']:.2f} $)")
        elif not probe and not p.get("gesperrt"):
            g.pruefe(f"abdeckung_{lg}", not fehlt, wert=len(fehlt), bei_fehler="stopp", ruecksprung="510",
                     text=f"{lg}: Hoerspielsaetze aktuell {len(ids) - len(fehlt)}/{len(ids)}"
                          + (f" – fehlt {fehlt[:4]}" if fehlt else ""))
        anteil = len(hoer) / max(1, len(ids))
        if not trocken:
            g.pruefe(f"auffaellig_{lg}", anteil <= float(rg["auffaellig_max"]), wert=round(anteil, 4),
                     bei_fehler="mensch", ruecksprung="510",
                     text=f"{lg}: auffaellige Hoerspielsaetze {len(hoer)} ({anteil:.1%}; Laenge VC/Quelle, Naht, VC fehlt)")
        if fehler:
            g.hinweis(f"vc_fehler_{lg}", False, wert=len(fehler), text=f"{lg}: VC ohne Ergebnis {len(fehler)} ({fehler[:3]})")
        pruef[lg] = {"auffaellig": hoer, "beitraege": beitraege, "korrektur": p["korr"], "motor": "fish"}
        je_sprache[lg] = {"engine": "fish-vc", "saetze": len(ids), "offen": len(p["offen"]), "vc_neu": n_vc,
                          "dialog_s": p["dial_s"], "figuren": sorted(p["ens"])}
    if ausfall:
        g.pflicht("lauf", False, ruecksprung="510", text=f"VC abgebrochen – {ausfall}")
    alle = [f"{lg}/{t}" for lg, p in plan.items() for t in p["soll"]]
    g.mock(sum(1 for k in alle if (m.get(k) or {}).get("q") == "mock"), ruecksprung="510")
    aus_hash = manifest.hash_obj({k: (m.get(k) or {}).get("datei_hash") for k in alle})
    g.metrik("ausgabe_hash", aus_hash)
    g.metrik("je_sprache", je_sprache)
    st0 = status.laden(werk)["stages"].get("510") or {}
    frei_alt = st0.get("zustand") == "frei" and (st0.get("metriken") or {}).get("ausgabe_hash") == aus_hash
    mensch_immer = not (frei_alt or (nachrunde and st0.get("zustand") == "frei")) and not trocken
    if frei_alt:
        for x in g.pruefungen:
            if not x["ok"] and x["bei_fehler"] == "mensch" and not x["name"].startswith("kosten"):
                x["bei_fehler"] = "hinweis"
                x["text"] += " [Mensch-Freigabe gilt, Hoerspiel unveraendert]"
    if not trocken:
        m.meta.update({"je_sprache": je_sprache, "ausgabe_hash": aus_hash, "regler": rg, "motor": "fish"})
        if plan:
            m.speichern()
        manifest.json_atomar(os.path.join(config.work_dir(werk), "510_pruefung.json"), pruef, indent=1)
    g.entscheide(mensch_immer=mensch_immer, mensch_grund="Hoerspiel-Freigabe: Figurenbeitraege anhoeren "
                 "(Monitor 510, vorher Fish / nachher VC)", schreiben=not trocken)
    g.pruef = pruef
    return g
