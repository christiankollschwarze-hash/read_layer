"""STAGE 503 — Fish-Engine der Stage 500 (Motor fish, AP Fish-Regie 25.11.2026), kein eigenes Gate (Katalogzeile 500).
Funktion:     Block-Vertonung mit Fish Drama 3 (bis Modal-Hosting: Fish-API /v1/tts/stream/with-timestamp, Header
              model drama-3 geprueft): je Block (430, sonst Hoerbuch-Bloecke ohne Anweisungen) EIN Aufruf in der
              Erzaehlerstimme; Figuren spielt der Erzaehler per Anweisung. Wort-Zeitmarken -> Schnittpunkte je
              Redebeitrag (Grenze in die Pause zwischen den Woertern, leisester Punkt) -> Satz-WAVs
              fassungen/<lg>/audio/<tid>.wav (Rohfassung wie Gemini/Chatterbox; Tempo/Raender/Lautheit erst 520) mit
              Spannen je Beitrag im Manifest (fuer 510-VC).
Wirkungsweise: Manifest work/500_vertonung.json: Block-Eintraege <lg>/_fish/<erste Beitrags-ID> (Hash: Fish-Text inkl.
              Lexikon, Fish-Modell-ID, Modell, Version) + Satz-Eintraege <lg>/<tid> (spannen [{id, fig, a, b}] in s).
              Nur neue/geaenderte Bloecke werden vertont (Resume); --satz ID vertont den Block des Satzes neu.
              Kosten: Listenpreis $/Byte (config.FISH_USD_JE_MIO_BYTES) -> Freigabe je Sprache wie 500 (Somnio im
              Budget, Kleinbetrag, sonst --kosten-freigeben). Concurrency <= 3, Retry 429.
Pruefung:     je Block Zeitmarken-Abdeckung (Fish-Woerter vs. Text, 0,85–1,15) und je Satz leer/Clipping/Dauer je
              Zeichen (Median der Sprache); auffaellige Bloecke bis rg['versuche'] x neu. Modell-Rueckfall -> Stopp.
Weiche:       fish_motor.weg (book.json fish_weg api|modal|auto, AP Fish-Modal 25.11.2026): je Sprache api (Fish-API,
              Kosten $/Byte) oder modal (gpu_fish/fish_modal.py, eigene Gewichte, ein Stapel-Lauf je Werk x Sprache,
              Zeitmarken per MMS_FA im Container, Kosten GPU-s -> $ + Kaltstart). Entscheidung + Grund in
              Manifest-meta fish_weg; Blockhash ohne Weg (Wegwechsel allein vertont nicht neu).
Aufrufer:     pipeline/s500_vertonung_gemini.run (alle Audiosprachen des Werks mit Motor fish).
"""
import concurrent.futures as cf
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata

import numpy as np

from config import config
from pipeline import fish_motor, manifest, mock, status, usage_log
from pipeline import s410_casting as s410
from pipeline import s430_fish_regie as s430

VERSION = 1
SR = fish_motor.SR
ABDECKUNG = (0.85, 1.15)


def block_dir(werk, lg):
    return os.path.join(config.work_dir(werk), "_500", lg, "fish")


def _lesen(p):
    from pipeline.s510_hoerspiel_hybrid import lesen
    return lesen(p)


def _schreiben(p, y):
    from pipeline.s510_hoerspiel_hybrid import schreiben
    schreiben(p, y)


# ============================================================ Zeitmarken -> Schnitt
def _klartext(s):
    """Gesprochener Text eines Blocks: Anweisungen [..] und Markup <..> entfernt, Leerraum verdichtet."""
    return " ".join(re.sub(r"<[^>]+>|\[[^\]]*\]", " ", s or "").split())


def _buchst(s):
    s = unicodedata.normalize("NFKC", re.sub(r"<[^>]+>|\[[^\]]*\]", " ", s or "")).casefold()
    return "".join(ch for ch in s if ch.isalnum())


def schnittpunkte(beitraege, woerter, x=None, sr=SR):
    """Beitraege [{text}] eines Blocks + Fish-Woerter [{w,a,b}] -> (grenzen_s [k-1 Werte], abdeckung).
    Abgleich ueber Buchstabenstroeme (robust gegen andere Tokenisierung); Grenze = leisester Punkt in der Pause
    zwischen letztem Wort von k und erstem Wort von k+1 (sonst Mitte)."""
    soll = [len(_buchst(b["text"])) for b in beitraege]
    ww = [(len(_buchst(w["w"])), float(w["a"]), float(w["b"])) for w in woerter]
    ww = [w for w in ww if w[0] > 0]
    ges_soll, ges_ist = sum(soll), sum(w[0] for w in ww)
    abd = ges_ist / ges_soll if ges_soll else 0.0
    if not ww or not ges_soll:
        return None, abd
    f = ges_ist / ges_soll                                    # Streckung bei kleinen Abweichungen
    kum, c = [], 0
    for w in ww:
        c += w[0]
        kum.append(c)
    grenzen, c_soll = [], 0
    for k in range(len(beitraege) - 1):
        c_soll += soll[k] * f
        i = min(range(len(kum)), key=lambda j: abs(kum[j] - c_soll))     # letztes Wort von k
        i = min(i, len(ww) - 2) if len(ww) > 1 else 0
        ende, anfang = ww[i][2], ww[min(i + 1, len(ww) - 1)][1]
        if anfang < ende:
            anfang = ende
        g = (ende + anfang) / 2
        if x is not None and anfang - ende >= 0.04:
            a0, a1 = int(ende * sr), int(anfang * sr)
            fr = max(1, int(0.01 * sr))
            seg = x[a0:a1]
            if len(seg) >= 2 * fr:
                e = [float(np.mean(seg[j:j + fr] ** 2)) for j in range(0, len(seg) - fr + 1, fr // 2 or 1)]
                g = (a0 + int(np.argmin(e)) * (fr // 2 or 1) + fr // 2) / sr
        grenzen.append(round(g, 3))
    for j in range(1, len(grenzen)):                          # monoton
        grenzen[j] = max(grenzen[j], grenzen[j - 1])
    return grenzen, abd


def zerlegen(beitraege, x, grenzen):
    """-> {beitrags_id: (a_sample, b_sample)} im Block."""
    n = len(x)
    pk = [0] + [int(g * SR) for g in grenzen] + [n]
    return {b["id"]: (min(pk[i], n), min(max(pk[i + 1], pk[i]), n)) for i, b in enumerate(beitraege)}


# ============================================================ Planung
def stimme_fish(c, lg):
    """-> (stufe, erzaehler-info, fehler). Erzaehler der Fish-Besetzung."""
    for st, bs in sorted((((c or {}).get("rollen") or {}).get(lg) or {}).items()):
        if bs.get("engine") == "fish":
            erz = bs.get("erzaehler") or {}
            if not erz.get("stimme"):
                return st, None, f"kein Erzaehler in rollen[{lg}][{st}]"
            return st, {"stimme": erz["stimme"], "fish_id": erz.get("fish_id"), "referenz": erz.get("referenz"),
                        "modell": f"fish-{fish_motor.MODELL}", "gemini_id": None, "adapter": None}, None
    return None, None, f"keine Fish-Besetzung in rollen[{lg}] (410 mit audio_motor fish neu laufen lassen)"


def beitraege_fuer(werk, data, lg, regie):
    """430 (Hoerspiel) oder Hoerbuch-Bloecke ohne Anweisungen. -> (beitraege, bloecke, quelle)."""
    v = ((regie or {}).get("sprachen") or {}).get(lg)
    if v:
        return v["beitraege"], v["bloecke"], "430"
    bts, _ = s430.beitraege_bauen(data, lg)
    rg = s430._regler({})
    bl = s430.bloecke_bilden(bts, rg["block_min"], rg["block_max"])
    return bts, bl, "hoerbuch"


def planen(werk, lg, data, regie, info, lex, m, saetze=(), kapitel=(), neu=False, probe=None):
    bts, bl, quelle = beitraege_fuer(werk, data, lg, regie)
    nach_id = {b["id"]: b for b in bts}
    for b_ in bl:
        b_["beitraege"] = [nach_id[i] for i in b_["ids"]]
        b_["key"] = f"{lg}/_fish/{b_['ids'][0]}"
        b_["text"] = lex(s430.block_text(b_["beitraege"]))
        b_["soll"] = manifest.hash_obj({"t": b_["text"], "id": info.get("fish_id") or info["stimme"],
                                        "m": fish_motor.MODELL, "v": VERSION})
        b_["tids"] = list(dict.fromkeys(x["tid"] for x in b_["beitraege"]))
    offen = []
    for b_ in bl:
        e = m.get(b_["key"]) or {}
        mock_alt = e.get("q") == "mock" and not mock.aktiv()
        wav = os.path.join(block_dir(werk, lg), f"{b_['ids'][0]}.wav")
        if neu or mock_alt or m.braucht_neu(b_["key"], b_["soll"]) or not os.path.exists(wav) \
                or set(b_["tids"]) & set(saetze):
            if kapitel and b_["kap"] not in kapitel and not set(b_["tids"]) & set(saetze):
                continue
            offen.append(b_)
    if probe:
        offen = offen[:int(probe)]
    zeichen = sum(len(b_["text"]) for b_ in offen)
    gesprochen = sum(len(_klartext(b_["text"])) for b_ in offen)     # ohne Anweisungen/Markup (Modal-Schaetzung)
    usd = round(sum(fish_motor.kosten_usd(b_["text"]) for b_ in offen) * 1.15, 4)   # Puffer Wiederholungen
    return {"bloecke": bl, "beitraege": bts, "quelle": quelle, "offen": offen, "zeichen": zeichen,
            "gesprochen": gesprochen, "usd": usd}


# ============================================================ Vertonen
def _vertonen_block(werk, lg, b_, fish_id):
    """Ein Block -> (wav_pfad, woerter, info). Mock: Stille + gleichmaessige Wortzeiten."""
    d = block_dir(werk, lg)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{b_['ids'][0]}.wav")
    if mock.aktiv():
        woerter, t = [], 0.0
        for bt in b_["beitraege"]:
            for w in re.sub(r"<[^>]+>", " ", bt["text"]).split():
                woerter.append({"w": w, "a": round(t, 3), "b": round(t + 0.3, 3)})
                t += 0.4
        mock.wav(p, frames=int((t + 0.3) * SR))
        info = {"bytes": len(b_["text"].encode("utf-8")), "mock": True}
    else:
        wav, woerter, info = fish_motor.tts_zeitmarken(b_["text"], fish_id)
        with open(p + ".tmp", "wb") as f:
            f.write(wav)
        os.replace(p + ".tmp", p)
        usage_log.log_stueck(f"fish-{fish_motor.MODELL}", anzahl=info["bytes"], book_id=werk, stage="500",
                             extra={"sprache": lg, "block": b_["ids"][0]})
    with open(p[:-4] + ".json", "w", encoding="utf-8") as f:
        json.dump({"woerter": woerter, "info": info, "text": b_["text"]}, f, ensure_ascii=False)
    return p, woerter, info


def paket_name(werk, lg):
    return f"{werk}_{lg}_500"


def paket_dir(werk, lg):
    return os.path.join(config.BASE_DIR, "gpu_fish", paket_name(werk, lg))


def modal_key(b_, runde):
    return f"{b_['soll']}_v{runde}"


def _modal_jobs(b_, runde):
    from pipeline import s535_wortbruecke as wb
    klar = re.sub(r"<[^>]+>|\[[^\]]*\]", " ", b_["text"])
    woerter = [{"w": klar[x["c0"]:x["c1"]], "l": x["w"]} for x in wb.lautwoerter(klar)]
    return {"key": modal_key(b_, runde), "text": b_["text"], "woerter": woerter, "seed": runde + 1, "id": b_["ids"][0]}


def bericht_lesen(text):
    """bericht.txt aus gpu_fish -> {gpu, wall_s, kalt_s, modell, ...}."""
    def zahl(muster):
        mm = re.search(muster, text or "")
        return float(mm.group(1)) if mm else None
    mg = re.search(r"GPU ([^\n]+)", text or "")
    gname = mg.group(1) if mg else ""
    gpu = next((g for g in ("H200", "H100", "L40S", "A100", "A10G", "L4") if g in gname), "H100")
    mm = re.search(r"MODELL (\S+)", text or "")
    return {"gpu": gpu, "gpu_name": gname.strip(), "wall_s": zahl(r"WALL ([\d.]+) s") or 0.0,
            "kalt_s": zahl(r"KALTSTART ([\d.]+) s"), "modell": mm.group(1) if mm else None,
            "rtf": zahl(r"RTF ([\d.]+)"), "audio_s": zahl(r"AUDIO ([\d.]+) s")}


def modal_stapel(werk, lg, bloecke, info, runde=0, paket=None, bdir=None, stage="500"):
    """Alle Bloecke einer Sprache in EINEM Modal-Lauf -> ({key: (wav, woerter, info)}, bericht{}).
    Modell-Pruefung: bericht MODELL != drama-3 -> ModellRueckfall. paket/bdir/stage fuer Proben (fish_probe)."""
    paket = paket or paket_name(werk, lg)
    d = os.path.join(config.BASE_DIR, "gpu_fish", paket)
    shutil.rmtree(os.path.join(d, "ref"), ignore_errors=True)
    os.makedirs(os.path.join(d, "ref"), exist_ok=True)
    clip = fish_motor.klon_clip(info["stimme"], lg)
    if not clip:
        raise RuntimeError(f"{info['stimme']}: kein klon_{lg}.wav im Archiv")
    shutil.copy2(clip, os.path.join(d, "ref", "ref.wav"))
    jobs = [_modal_jobs(b_, runde) for b_ in bloecke]
    manifest.json_atomar(os.path.join(d, "jobs.json"), {"werk": werk, "lang": lg, "stimme": info["stimme"],
                                                        "ref": {"datei": "ref.wav", "text": fish_motor.klon_text(lg)},
                                                        "jobs": jobs}, indent=1)
    cmd = [sys.executable, "-m", "modal", "run", "gpu_fish/fish_modal.py", "--paket", paket]
    print(f"[503] Modal Fish {lg}: {len(jobs)} Bloecke (Stapel, Resume im Volume)", flush=True)
    bp = os.path.join(d, "bericht.txt")
    if os.path.exists(bp):
        os.remove(bp)
    from pipeline import spuren as SP
    with SP.modal_platz():
        r = subprocess.run(cmd, cwd=config.BASE_DIR)
    roh = ""
    if os.path.exists(bp):
        with open(bp, encoding="utf-8") as f:
            roh = f.read()
    ber = bericht_lesen(roh)
    if ber["modell"] and ber["modell"] != "drama-3":
        raise fish_motor.ModellRueckfall(f"Modal-Checkpoint {ber['modell']} statt drama-3")
    if r.returncode != 0 and not os.path.isdir(os.path.join(d, "out")):
        raise RuntimeError(f"Modal-Fish {paket} Exit {r.returncode}")
    erg = {}
    bdir = bdir or block_dir(werk, lg)
    os.makedirs(bdir, exist_ok=True)
    for b_, j in zip(bloecke, jobs):
        w = os.path.join(d, "out", j["key"] + ".wav")
        js = os.path.join(d, "out", j["key"] + ".json")
        if not (os.path.exists(w) and os.path.exists(js)):
            continue
        p = os.path.join(bdir, f"{b_['ids'][0]}.wav")
        shutil.move(w, p + ".tmp")                 # verschieben: Block-WAV nur einmal auf der Platte
        os.replace(p + ".tmp", p)
        with open(js, encoding="utf-8") as f:
            o = json.load(f)
        inf = dict(o.get("info") or {}, weg="modal", gpu=ber["gpu"])
        with open(p[:-4] + ".json", "w", encoding="utf-8") as f:
            json.dump({"woerter": o["woerter"], "info": inf, "text": b_["text"]}, f, ensure_ascii=False)
        erg[b_["key"]] = (p, o["woerter"], inf)
    if not mock.aktiv() and ber["wall_s"]:
        usage_log.log_gpu(werk, stage, ber["wall_s"], gpu=ber["gpu"],
                          extra={"sprache": lg, "art": "fish-tts", "bloecke": len(erg), "kaltstart_s": ber["kalt_s"],
                                 "rtf": ber["rtf"], "audio_s": ber["audio_s"]})
    return erg, ber


def _schneiden(werk, lg, b_, wav, woerter, adir):
    """Block -> Satz-WAVs + Spannen. -> ({tid: {pfad, spannen}}, abdeckung)."""
    x = _lesen(wav)
    grenzen, abd = schnittpunkte(b_["beitraege"], woerter, x)
    if grenzen is None:
        return {}, abd
    st = zerlegen(b_["beitraege"], x, grenzen)
    out = {}
    for tid in b_["tids"]:
        teil = [bt for bt in b_["beitraege"] if bt["tid"] == tid]
        a0, a1 = st[teil[0]["id"]][0], st[teil[-1]["id"]][1]
        pf = os.path.join(adir, f"{tid}.wav")
        _schreiben(pf, x[a0:a1])
        out[tid] = {"pfad": pf, "dauer": round((a1 - a0) / SR, 3), "spannen": [{"id": bt["id"], "fig": bt["fig"], "a": round((st[bt["id"]][0] - a0) / SR, 3),
                                             "b": round((st[bt["id"]][1] - a0) / SR, 3)} for bt in teil]}
    return out, abd


def vertonen(werk, lg, plan, info, m, rg, adir, units, versuche=2):
    """Offene Bloecke vertonen (api: <= 3 parallel; modal: ein Stapel-Lauf je Runde), schneiden, verbuchen.
    -> (befund {tid: grund}, n_bloecke, rueckfall)."""
    weg = (plan.get("weg") or {}).get("weg", "api")
    fid = info.get("fish_id")
    if weg == "modal":
        fid = fid or None
    elif not fid and not mock.aktiv():
        fid = fish_motor.fish_id(info["stimme"], lg, anlegen=True)
        info["fish_id"] = fid
    pause = {u["id"]: u.get("pause") for u in units}
    befund, rueckfall, n = {}, None, 0
    offen = list(plan["offen"])
    for runde in range(int(versuche) + 1):
        if not offen:
            break
        erg = {}
        if weg == "modal" and not mock.aktiv():
            try:
                erg, ber = modal_stapel(werk, lg, offen, info, runde)
                plan.setdefault("modal_berichte", []).append(ber)
            except fish_motor.ModellRueckfall as e:
                rueckfall = str(e)
        else:
            with cf.ThreadPoolExecutor(fish_motor.PARALLEL) as ex:
                futs = {ex.submit(_vertonen_block, werk, lg, b_, fid): b_ for b_ in offen}
                for fu in cf.as_completed(futs):
                    b_ = futs[fu]
                    try:
                        erg[b_["key"]] = fu.result()
                    except fish_motor.ModellRueckfall as e:
                        rueckfall = str(e)
                    except Exception as e:
                        print(f"[503] {lg} Block {b_['ids'][0]}: {type(e).__name__}: {str(e)[:160]}", flush=True)
        if rueckfall:
            break
        schlecht = []
        for b_ in offen:
            if b_["key"] not in erg:
                for t in b_["tids"]:
                    befund[t] = "fehlt"
                continue
            p, woerter, inf = erg[b_["key"]]
            n += 1
            saetze, abd = _schneiden(werk, lg, b_, p, woerter, adir)
            ok = ABDECKUNG[0] <= abd <= ABDECKUNG[1] or mock.aktiv()
            m.setzen(b_["key"], b_["soll"], datei=p, engine="fish", stimme=info["stimme"], fish_id=fid, weg=weg,
                     modell=f"fish-{fish_motor.MODELL}", q="mock" if mock.aktiv() else "neu", abdeckung=round(abd, 3),
                     bytes=inf.get("bytes"), saetze=b_["tids"], versuche=runde)
            for tid, s_ in saetze.items():
                h = manifest.hash_obj({"b": b_["soll"], "tid": tid})
                m.setzen(f"{lg}/{tid}", h, datei=s_["pfad"], engine="fish", stimme=info["stimme"],
                         modell=f"fish-{fish_motor.MODELL}", q="mock" if mock.aktiv() else "neu",
                         pruefung=None if ok else "zeitmarken", versuche=runde, block=b_["ids"][0],
                         spannen=s_["spannen"], pause_ms=pause.get(tid), dauer=s_["dauer"])
                befund[tid] = None if ok else "zeitmarken"
            if not ok:
                schlecht.append(b_)
        m.speichern()
        offen = schlecht
    return befund, n, rueckfall


def gate_sprache(g, m, lg, plan, units, befund, rg, trocken, probe, werk=None):
    """Pruefungen je Sprache (Muster 500). Hoerliste im Format des 500-Monitors (auffaellig/angenommen) + Bloecke."""
    from pipeline import s500_vertonung_gemini as s500
    ids = [u["id"] for u in units]
    fehlt = [t for t in ids if not m.datei_aktuell(f"{lg}/{t}")]
    ent = (s500._json(s500.entscheidungen_pfad(werk), {}) or {}) if werk else {}
    texte = {u["id"]: u["text"] for u in units}
    dauern = {t: float((m.get(f"{lg}/{t}") or {}).get("dauer") or 0) for t in ids if m.get(f"{lg}/{t}")}
    q = sorted(d / max(1, len(texte[t])) for t, d in dauern.items() if d and len(texte.get(t, "")) >= 15)
    med = q[len(q) // 2] if len(q) >= 20 else None
    auff, angen = [], []
    for t in ids:
        k = f"{lg}/{t}"
        e = m.get(k) or {}
        if not e or not m.datei_aktuell(k):
            continue
        inf = s500.wav_info(m._abs(e["datei"]))
        grund = befund.get(t) or e.get("pruefung") or s500._grund_lokal(inf, texte[t], med, rg)
        if not trocken:
            e["dauer"], e["pruefung"] = inf["dauer"], grund
        if not grund or grund == "nachklang":
            continue
        z = {"id": t, "grund": grund, "block": e.get("block"), "datei": e["datei"], "dauer": inf["dauer"],
             "versuche": e.get("versuche"), "text": texte[t]}
        a = ent.get(k)
        if a and a.get("datei_hash") == e.get("datei_hash"):
            angen.append(dict(z, wer=a.get("wer"), wann=a.get("wann"), grund_annahme=a.get("grund")))
        else:
            auff.append(z)
    bloecke = []
    for b_ in plan["bloecke"]:
        e = m.get(b_.get("key") or f"{lg}/_fish/{b_['ids'][0]}") or {}
        bloecke.append({"nr": b_["nr"], "kap": b_["kap"], "erste": b_["ids"][0], "saetze": len(b_.get("tids") or []),
                        "erster_satz": (b_.get("tids") or [None])[0], "zeichen": b_["zeichen"],
                        "datei": e.get("datei"), "abdeckung": e.get("abdeckung"), "versuche": e.get("versuche"),
                        "offen": any(o is b_ for o in plan["offen"])})
    out = {"auffaellig": auff, "angenommen": angen, "fehlt": fehlt, "bloecke": bloecke, "quelle": plan["quelle"],
           "engine": "fish", "stimme": (plan.get("info") or {}).get("stimme")}
    if trocken:
        g.hinweis(f"abdeckung_{lg}", not fehlt, wert=len(fehlt),
                  text=f"{lg}: {len(ids) - len(fehlt)}/{len(ids)} Saetze vorhanden; offen {len(plan['offen'])} Bloecke "
                       f"({plan['zeichen']} Z., ~{plan['usd']:.2f} $, Quelle {plan['quelle']})")
        return out
    m.speichern()
    if not probe and not plan.get("gesperrt"):
        g.pruefe(f"abdeckung_{lg}", not fehlt, wert=len(fehlt), bei_fehler="stopp", ruecksprung="500",
                 text=f"{lg}: Saetze mit aktueller Fish-WAV {len(ids) - len(fehlt)}/{len(ids)}"
                      + (f" – fehlt {fehlt[:4]}" if fehlt else ""))
    anteil = len(auff) / max(1, len(ids))
    g.pruefe(f"auffaellig_{lg}", anteil <= float(rg["auffaellig_max"]), wert=round(anteil, 4),
             bei_fehler="mensch", ruecksprung="500",
             text=f"{lg}: auffaellige Saetze {len(auff)} ({anteil:.1%}) <= {float(rg['auffaellig_max']):.0%} "
                  f"(Hoerliste work/500_pruefung.json)")
    if angen:
        g.hinweis(f"angenommen_{lg}", False, wert=len(angen),
                  text=f"{lg}: {len(angen)} auffaellige Saetze angenommen (Vermerk 500_entscheidungen.json)")
    return out


def run(werk, g, b, rg, c, data, m, wer, saetze=None, kapitel=None, nur_lang=None, neu=False, probe=None,
        kosten_freigeben=None, trocken=False, sprachen=None):
    """Stage 500 fuer Sprachen mit Motor fish (aus s500.run aufgerufen, Gate g dort angelegt und vorgeprueft)."""
    from pipeline import s500_vertonung_gemini as s500
    regie = s430.laden(werk) or {}
    hs = set(s430.ziele(b))
    plan, je_sprache, pruef = {}, {}, {}
    for lg in sprachen:
        if nur_lang and lg != nur_lang:
            continue
        if lg in hs:
            z = status.zustand(werk, "430")
            if trocken:
                g.hinweis(f"gate_430_{lg}", z in status.FREI, text=f"{lg}: Gate 430: {z}")
            elif not g.pflicht(f"gate_430_{lg}", z in status.FREI and lg in (regie.get("sprachen") or {}), wert=z,
                               ruecksprung="430", text=f"{lg}: Fish-Regie 430 frei + Sprache vorhanden ({z})"):
                continue
        st, info, fe = stimme_fish(c, lg)
        if not g.pflicht(f"stimme_{lg}", fe is None, ruecksprung="410",
                         text=f"{lg}: Fish-Erzaehler" + (f" – {fe}" if fe else f" ({info['stimme']}, "
                                                          f"{'Modell ' + info['fish_id'] if info.get('fish_id') else 'Fish-Modell wird angelegt'})")):
            continue
        units, _ = s500.einheiten(data, lg)
        lex, n_lex = s500._lexikon(werk, lg)
        p = planen(werk, lg, data, regie, info, lex, m, saetze or (), set(kapitel or ()), neu, probe)
        p.update(info=info, stufe=st, units=units, n_lex=n_lex, engine="fish")
        w = fish_motor.weg(b, lg, sum(len(b_["text"]) for b_ in p["bloecke"]), einzel=bool(saetze) and not neu)
        if not g.pflicht(f"weg_{lg}", w["stopp"] is None, wert=w, ruecksprung="500",
                         text=f"{lg}: Fish-Weg {w['weg']} ({w['grund']})" + (f" – {w['stopp']}" if w["stopp"] else "")):
            continue
        p["weg"] = w
        if w["weg"] == "modal":
            sch = fish_motor.modal_schaetzung(p.get("gesprochen", p["zeichen"]))
            p["modal"] = sch
            p["usd"] = round((sch["usd"] + sch["kaltstart_usd"]) * float(getattr(config, "FISH_MODAL_AUFSCHLAG", 1.2))
                             if p["offen"] else 0.0, 4)
        plan[lg] = p
    usd = round(sum(p["usd"] for p in plan.values()), 4)
    g.metrik("kosten_usd", usd)
    g.metrik("kosten_je_sprache", {lg: {"engine": "fish", "weg": p["weg"]["weg"], "grund": p["weg"]["grund"],
                                        "modal": p.get("modal"), "bloecke": len(p["offen"]), "zeichen": p["zeichen"],
                                        "saetze": sum(len(b_["tids"]) for b_ in p["offen"]),
                                        "bytes": sum(len(b_["text"].encode("utf-8")) for b_ in p["offen"]),
                                        "usd": p["usd"]} for lg, p in plan.items()})
    g.metrik("offen", {lg: len(p["offen"]) for lg, p in plan.items()})
    if g.fehler():
        g.entscheide(schreiben=not trocken)
        return g
    if not trocken and not mock.aktiv() and any(p["offen"] for p in plan.values()):
        kf = kosten_freigeben if isinstance(kosten_freigeben, dict) else (
            {"*": kosten_freigeben} if kosten_freigeben is not None else {})
        im_budget = b.mandant_art == "somnio" and usd <= float(rg["budget"])
        frei = set(plan) if im_budget else s500._freigabe_je_sprache(kf, plan)
        frei |= {lg for lg, p in plan.items() if p["usd"] < float(getattr(config, "KOSTEN_KLEINBETRAG_USD", 0.01))}
        mit = {lg for lg, p in plan.items() if p["offen"]}
        gesperrt = mit - frei
        for lg in sorted(gesperrt):
            p = plan[lg]
            g.pruefe(f"kosten_{lg}", False, wert=p["usd"], bei_fehler="mensch", ruecksprung="500",
                     text=f"{lg}: Kosten ~{p['usd']:.2f} $ fuer {len(p['offen'])} Bloecke (Fish {fish_motor.MODELL} "
                          f"{p['weg']['weg']}, "
                          f"{p['zeichen']} Z.) nicht freigegeben – Freigabe im Cockpit (Monitor 500) bzw. "
                          f"--kosten-freigeben {lg}={p['usd']:.2f}")
            p["offen"], p["gesperrt"] = [], True
        if mit and gesperrt == mit:
            g.entscheide(schreiben=True)
            return g
        if not im_budget:
            for lg in sorted(mit - gesperrt):
                s500._kosten_protokoll(werk, {"wann": status.jetzt(), "wer": wer, "sprache": lg, "engine": "fish",
                                              "usd": plan[lg]["usd"], "bloecke": len(plan[lg]["offen"]),
                                              "grenze": float(kf.get(lg, kf.get("*", 0)))})
    ausfall = None
    for lg, p in plan.items():
        befund, n_bl = {}, 0
        if p["offen"] and not trocken:
            usage_log.set_context(werk, "500", sprache=lg)
            adir = s500.audio_dir(werk, lg)
            print(f"[503] {lg} (Fish {fish_motor.MODELL} {p['weg']['weg']}, {p['info']['stimme']}): {len(p['offen'])} Bloecke, "
                  f"{p['zeichen']} Zeichen, ~{p['usd']:.2f} $ (Quelle {p['quelle']})", flush=True)
            try:
                befund, n_bl, rf = vertonen(werk, lg, p, p["info"], m, rg, adir, p["units"], rg["versuche"])
            except Exception as e:
                rf, ausfall = None, f"{lg}: {type(e).__name__}: {str(e)[:160]}"
            if rf:
                g.pflicht(f"modell_{lg}", False, ruecksprung="500",
                          text=f"{lg}: Fish-Modell-Rueckfall – {rf} (Header model: {fish_motor.MODELL} pruefen)")
        pruef[lg] = gate_sprache(g, m, lg, p, p["units"], befund, rg, trocken, probe, werk)
        ber = (p.get("modal_berichte") or [None])[-1]
        je_sprache[lg] = {"engine": "fish", "weg": p["weg"]["weg"], "weg_grund": p["weg"]["grund"],
                          "modal_bericht": ber, "stufe": p["stufe"], "stimme": p["info"]["stimme"],
                          "fish_id": p["info"].get("fish_id"), "modell": fish_motor.MODELL,
                          "einheiten": len(p["units"]), "bloecke": len(p["bloecke"]), "vertont_bloecke": n_bl,
                          "quelle": p["quelle"], "lexikon": p["n_lex"]}
    if ausfall:
        g.pflicht("lauf", False, ruecksprung="500", text=f"Vertonung abgebrochen – {ausfall}")
    alle = [f"{lg}/{u['id']}" for lg, p in plan.items() for u in p["units"]]
    g.mock(sum(1 for k in alle if (m.get(k) or {}).get("q") == "mock"), ruecksprung="500")
    aus_hash = manifest.hash_obj({k: (m.get(k) or {}).get("datei_hash") for k in alle})
    g.metrik("ausgabe_hash", aus_hash)
    g.metrik("je_sprache", je_sprache)
    st0 = status.laden(werk)["stages"].get("500") or {}
    if st0.get("zustand") == "frei" and (st0.get("gate") or {}).get("ergebnis") == "mensch" \
            and (st0.get("metriken") or {}).get("ausgabe_hash") == aus_hash and not probe:
        for x in g.pruefungen:
            if not x["ok"] and x["bei_fehler"] == "mensch" and not x["name"].startswith("kosten"):
                x["bei_fehler"] = "hinweis"
                x["text"] += " [Mensch-Freigabe gilt, Audio unveraendert]"
    if not trocken:
        m.meta.update({"je_sprache": je_sprache, "ausgabe_hash": aus_hash, "regler": rg, "motor": "fish",
                       "fish_weg": {lg: p["weg"] for lg, p in plan.items()}})
        if plan:
            m.speichern()
        manifest.json_atomar(os.path.join(config.work_dir(werk), "500_pruefung.json"), pruef, indent=1)
    g.entscheide(mensch_immer=bool(probe), mensch_grund=f"Probe {probe} Bloecke je Sprache – anhoeren, dann Volllauf"
                 if probe else None, schreiben=not trocken)
    g.pruef = pruef
    return g
