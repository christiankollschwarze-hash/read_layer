"""STAGE 640 — Teaser (Klappentext vertont, je Sprache der TAELLA-Produkte)
Funktion:     Vertont den Klappentext aus 600 satzweise (Koeder -> Einordnung -> Autor) fuer das Katalog-
              Schaufenster. Stimme = Erzaehler des Werks aus casting.json (Engine aus der Stufe: Basic ->
              Chatterbox/Modal, Premium/Drama -> Gemini), ohne Audio-Bestellung der Sprache Zuordnung Genre-
              Gruppe/hauptfigur_geschlecht/Autor-Geschlecht (claude/PROZESS_klappentext_erzaehler.md) -> Gemini.
Komponenten:  pipeline/s640_teaser.py; Pruefbausteine aus s530 (Raender, Tempo, Lautheit, Whisper-CER),
              s500 (Gemini synth, Stimme/Engine, Kosten), s502 (Chatterbox-Paket, Stage 640), s510 (FA)
Eingang:      work/600_klappentext.json (blurb je Sprache, meta: ton, genre_gruppe, hauptfigur_geschlecht, autor,
              wirkungssprache) + Gate 600 frei; casting.json freigegeben + Gate 410 frei (Sprache mit Audio);
              author.json (autor_geschlecht, wirkungssprache); book.json (Bestellung, Mandant)
Ausgabe:      fassungen/<lg>/blurb/text/blurb.json; fassungen/<lg>/blurb/audio/<id>.mp3 + manifest.json;
              work/640_teaser.json Manifest je Satz x Sprache (Schluessel "<lg>/<id>": Eingangs-Hash, Roh-Hash,
              Engine, Stimme, Stil, Versuche, Pruefung); Rohfassung work/_640/<lg>/roh/<id>.wav;
              Regler work/640_entscheidungen.json
Gate:         je Sprache (status teile "<lg>"): Abdeckung 100 %; Whisper Sprache/CER; Dauer 0,6–1,6 x Erwartung;
              Rand <= 0,15 s; LUFS -18 +-1, Spitze <= -1 dBTP (Raender/Lautheit automatisch korrigiert); Mock = 0.
              Auffaelliger Satz -> bis 2x automatisch neu, dann Mensch (Hoerliste, --annehmen / --satz).
              Stopp: Gate 600 bzw. 410 nicht frei, kein Klappentext, Stimme nicht nutzbar, Werkzeuge fehlen,
              Satz ohne Audio, Mock im Live-Lauf. Mandant verlag -> immer Mensch; Mensch-Freigabe gilt bei
              gleichem ausgabe_hash.
Kosten:       Gemini-TTS (tts_client loggt unter Stage 640), Modal Chatterbox/FA/Whisper (log_gpu Stage 640);
              vor dem Lauf Kostenschaetzung (--kosten nur Schaetzung).
Abnehmer:     710 (Teaser in Cloud/Katalog), Cockpit (abspielen), 700 (Vertrag).

Aufruf:  py -3.11 -m pipeline.s640_teaser <werk> [--stimme LG=NAME|weg] [--stil LG|*=TEXT|weg] [--engine LG=gemini|chatterbox]
         [--tempo LG|*=F] [--aussprache an|aus] [--fa modal|cpu] [--sprachpruefung modal|cpu|aus]
         [--satz LG:ID] [--annehmen LG:ID --grund ...] [--sprache LG] [--neu] [--kosten] [--trocken]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import bestellung, gate, manifest, mock, status, usage_log

STAGE = "640"
VERSION = 1
BLOECKE = ("koeder", "einordnung", "autor")
LANG_NAME = {"de": "German", "en": "English", "fr": "French", "es": "Spanish", "it": "Italian", "ru": "Russian"}
REGLER_STD = {"stimme": {}, "stil": {}, "engine": {}, "tempo": {}, "aussprache": "an", "fa": "modal",
              "sprache": "modal", "vor": 0.05, "nach": 0.12, "rand_max": 0.15, "lufs": -18.0, "lufs_tol": 1.0,
              "peak_max": -1.0, "dauer_min": 0.6, "dauer_max": 1.6, "cer_verdacht": 0.35, "p_min": 0.5,
              "kurz_s": 1.0, "versuche": 2}
# Genre-Gruppe (600) -> Erzaehler (PROZESS_klappentext_erzaehler.md, Abschnitt 2); "autor" = Geschlecht des Autors
GRUPPE_ERZ = {"Märchen & Fabel": ("weiblich", None), "Liebe": ("weiblich", None), "Bühne": ("weiblich", None),
              "Krimi": ("maennlich", None), "Abenteuer": ("maennlich", None), "Science-Fiction": ("maennlich", None),
              "Horror": ("maennlich", None), "Roman allgemein": ("maennlich", "weiblich"),
              "Historisch": ("maennlich", "weiblich"), "Fantastik": ("maennlich", "weiblich"),
              "Mythos & Epos": ("maennlich", "weiblich"), "Kinder & Jugend": ("weiblich", "maennlich"),
              "Kurzprosa": ("autor", None), "Sachtext": ("autor", None), "Lyrik": ("autor", None),
              "Sonstiges": ("autor", None)}
TEASER_STIMMEN = getattr(config, "TEASER_STIMMEN", {"weiblich": "grossmutter_a", "maennlich": "herr_a"})
MODAL_LAUF_USD = 0.02            # Schaetzung Chatterbox-Container (L4, Start + ~10 Saetze)


# ------------------------------------------------------------------ Ablage
def blurb_dirs(werk, lg):
    base = os.path.join(config.book_dir(werk), "fassungen", lg, "blurb")
    return os.path.join(base, "text"), os.path.join(base, "audio")


def roh_dir(werk, lg):
    return os.path.join(config.work_dir(werk), "_640", lg, "roh")


def _json(p, leer=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return leer


def entscheidungen(werk):
    return _json(config.work_path(werk, "640_entscheidungen"), {}) or {}


def entscheidung_setzen(werk, wer, **kw):
    d = entscheidungen(werk)
    d.setdefault("protokoll", [])
    for k, v in kw.items():
        if v is None:
            d.pop(k, None)
        else:
            d[k] = v
    d["protokoll"].append({"wer": wer, "wann": manifest.jetzt(), **{k: v for k, v in kw.items() if k != "annahmen"}})
    manifest.json_atomar(config.work_path(werk, "640_entscheidungen"), d, indent=2)
    return d


def regler(werk):
    rg = {k: (dict(v) if isinstance(v, dict) else v) for k, v in REGLER_STD.items()}
    for k, v in (entscheidungen(werk).get("regler") or {}).items():
        if isinstance(rg.get(k), dict) and isinstance(v, dict):
            rg[k].update(v)
        else:
            rg[k] = v
    return rg


def _manifest(werk, nur_lesen=False):
    """Manifest work/640_teaser.json; Altdatei (Zaehlerstand ohne Schema) -> 640_teaser_alt.json."""
    p = config.work_path(werk, "640_teaser")
    alt = _json(p)
    if alt is not None and alt.get("schema") != manifest.SCHEMA:
        if nur_lesen:
            m = manifest.Manifest.__new__(manifest.Manifest)
            m.book_id, m.name, m.pfad = werk, "640_teaser", p
            m.basis = os.path.dirname(os.path.dirname(p))
            m.d = {"schema": manifest.SCHEMA, "stage": STAGE, "meta": {}, "eintraege": {}}
            return m
        os.replace(p, config.work_path(werk, "640_teaser_alt"))
        print("[640] Altdatei 640_teaser.json -> 640_teaser_alt.json")
    return manifest.Manifest(werk, "640_teaser", stage=STAGE)


# ------------------------------------------------------------------ Text
_EMPH_US = re.compile(r"_([^_\n]+)_")
_EMPH_AST = re.compile(r"\*([^*\n]+)\*")


def _clean_text(t):
    """Sicherheitsnetz (Markup prueft Gate 600): _kursiv_, *kursiv*, -- -> Gedankenstrich."""
    t = _EMPH_US.sub(r"\1", t)
    t = _EMPH_AST.sub(r"\1", t)
    t = t.replace("_", " ")
    t = re.sub(r"(?<!\w)\*|\*(?!\w)", "", t)
    t = t.replace("--", "—")
    return re.sub(r"\s{2,}", " ", t).strip()


def saetze(blurb, lg):
    """[{id, block, index, text, roh}] einer Sprache, Reihenfolge Koeder -> Einordnung -> Autor."""
    out = []
    for blk in BLOECKE:
        for i, s in enumerate(blurb.get(blk) or [], 1):
            roh = str((s or {}).get(lg) or "").strip()
            if roh:
                out.append({"id": f"{blk}_{i:02d}", "block": blk, "index": i, "text": _clean_text(roh), "roh": roh})
    return out


def stil(rg, lg, meta, engine):
    """Gemini-Stil aus meta.ton / Genre-Gruppe, Regler je Sprache bzw. '*'. Chatterbox: kein Stil."""
    if engine != "gemini":
        return ""
    s = (rg.get("stil") or {}).get(lg) or (rg.get("stil") or {}).get("*")
    if s:
        return s.strip()
    ton = " ".join(str(meta.get("ton") or "").split())[:80]
    return "warm, inviting narration" + (f", {ton}" if ton and not mock.ist_text(ton) else "")


def stil_satz(basis, text, autor, lg, wirkung, aussprache):
    if not basis or not autor or not wirkung or wirkung == lg or aussprache == "aus" or autor not in text:
        return basis
    return f"{basis}; {autor} pronounced as in {LANG_NAME.get(wirkung, wirkung)}, unstressed"


# ------------------------------------------------------------------ Stimme
def _geschlecht(v):
    v = str(v or "").strip().lower()
    return "weiblich" if v[:1] in ("w", "f") else "maennlich" if v[:1] == "m" else None


def genre_geschlecht(meta, autor_json):
    """-> (weiblich|maennlich, begruendung) nach Abschnitt 2 PROZESS_klappentext_erzaehler.md."""
    from pipeline.s600_klappentext import genre_gruppe
    gr = meta.get("genre_gruppe") or genre_gruppe(meta.get("genre"))[0]
    std, ausnahme = GRUPPE_ERZ.get(gr, ("autor", None))
    hf = _geschlecht(meta.get("hauptfigur_geschlecht"))
    if std == "autor":
        ag = _geschlecht((autor_json or {}).get("autor_geschlecht"))
        return (ag or "weiblich"), f"{gr}: Geschlecht des Autors ({ag or 'unbekannt -> weiblich'})"
    if ausnahme and hf == ausnahme:
        return ausnahme, f"{gr}: Hauptfigur {hf}"
    return std, f"{gr}"


def stimme_waehlen(werk, b, lg, meta, autor_json, rg):
    """-> (info | None, fehler, ruecksprung). info: stimme, engine, gemini_id, referenz, adapter, quelle, grund."""
    from pipeline import s410_casting as s410
    from pipeline import s500_vertonung_gemini as s500
    stufen = s500._stufen(b).get(lg) or []
    manuell = (rg.get("stimme") or {}).get(lg)
    if stufen:
        engine, stufe, fe = s500.engine_waehlen(stufen, (rg.get("engine") or {}).get(lg))
        if fe:
            return None, fe + " (Regler --engine LG=...)", "640"
        c = s410.laden(werk)
        if not s410.freigegeben(c):
            return None, "casting.json nicht freigegeben", "410"
        info, fe = s500.stimme(c, lg, stufe, engine)
        if fe:
            return None, fe, "410"
        info.update(engine=engine, stufe=stufe, quelle="casting", grund=f"Erzaehler des Werks ({stufe})")
        if engine == "chatterbox":
            fa = s500.adapter_pruefen(info.get("adapter"))
            if fa:
                return None, fa, "410"
    else:
        g, grund = genre_geschlecht(meta, autor_json)
        info = {"stimme": TEASER_STIMMEN.get(g), "engine": (rg.get("engine") or {}).get(lg) or "gemini",
                "adapter": None, "quelle": "genre", "grund": grund, "geschlecht": g}
    if manuell:
        info.update(stimme=manuell, quelle="manuell", grund="Regler --stimme")
    if info["quelle"] != "casting":
        ok, d, fe = s410.nutzbar(info["stimme"], lg, info["engine"])
        if not ok:
            return None, f"Stimme {info['stimme']} ({info['engine']}): {fe}", "640"
        info.update(gemini_id=d.get("gemini_id"), referenz=d.get("referenz"), modell=d.get("modell"))
        if info["engine"] == "chatterbox":
            a, ok_a, fe = s410.adapter(b.roh, lg)
            if not ok_a:
                return None, fe, "410"
            info["adapter"] = a
    return info, None, None


# ------------------------------------------------------------------ Vertonung
def _tempo(rg, lg, info):
    from pipeline import s502_vertonung_chatterbox as cb
    t = (rg.get("tempo") or {}).get(lg)
    if t is None:
        t = (rg.get("tempo") or {}).get("*")
    if t is None:
        t = cb.lora_werte((info.get("adapter") or {}).get("name"))[1] if info["engine"] == "chatterbox" else 1.0
    return float(t)


def ms_erwartung(info):
    from pipeline import s500_vertonung_gemini as s500
    from pipeline import s502_vertonung_chatterbox as cb
    if info["engine"] == "chatterbox":
        return cb.lora_werte((info.get("adapter") or {}).get("name"))[0]
    return s500.MS_GEMINI


def kosten(info, zeichen):
    from pipeline import s500_vertonung_gemini as s500
    if not zeichen:
        return 0.0
    if info["engine"] == "chatterbox":
        return MODAL_LAUF_USD
    return s500.kosten("gemini", zeichen)


def synth_gemini(werk, lg, jobs, info):
    """jobs [(id, text, stil, ziel)] -> {id: pfad}."""
    from pipeline import s500_vertonung_gemini as s500
    out = {}
    with usage_log.kontext(werk, STAGE, sprache=lg):
        for tid, text, st, ziel in jobs:
            os.makedirs(os.path.dirname(ziel), exist_ok=True)
            if s500._synth_retry(text, st, ziel, info["gemini_id"], lg, f"{lg} {tid}"):
                out[tid] = ziel
    return out


def synth_chatterbox(werk, lg, jobs, info, rd):
    """Ein Modal-Lauf (Paket <werk>_<lg>_640) -> {id: pfad}, befund {id: grund}."""
    from pipeline import s502_vertonung_chatterbox as cb
    tag = time.strftime("%Y%m%d%H%M%S")
    _, daten = cb.paket_bauen(werk, lg, [(t, x) for t, x, _, _ in jobs], info["stimme"], info.get("referenz"),
                              (info.get("adapter") or {}).get("name"), tag=tag, stage=STAGE)
    mess = cb.modal_lauf(werk, lg, tag=tag, stage=STAGE)
    return cb.einsetzen(werk, lg, daten, rd), cb.befund(mess)


def fa_zeiten(jobs, werk, lg, art):
    from pipeline import s510_hoerspiel_hybrid as s510
    t0 = time.time()
    out = s510.zeiten(jobs, werk, lg, art)
    if art == "modal":
        usage_log.log_gpu(werk, STAGE, time.time() - t0, extra={"sprache": lg, "teil": "fa"})
    return out


def sprache_pruefen(jobs, werk, lg, art):
    """jobs [(key, wav)] -> {key: {top, p, text, dauer}}; Modal mit CPU-Rueckfall (Bausteine 530)."""
    from pipeline import s530_audio_pruefung as P5
    if not jobs or art == "aus":
        return {}
    if art == "modal":
        try:
            from gpu_sprache.sprache_modal import app, pruefen
            t0, out = time.time(), {}
            with app.run():
                for res in pruefen.map([[{"key": k, "wav": P5._wav16(p), "lg": lg} for k, p in jobs]]):
                    out.update(res)
            usage_log.log_gpu(werk, STAGE, time.time() - t0, extra={"sprache": lg, "teil": "whisper"})
            return out
        except Exception as e:
            print(f"[640] Modal-Whisper nicht nutzbar -> CPU: {type(e).__name__}: {str(e)[:120]}")
    return P5.sprache_cpu(jobs, lg)


def werkzeuge(rg):
    from pipeline import s530_audio_pruefung as P5
    return P5.werkzeuge_pruefen(rg["fa"], rg["sprache"], True, rg["sprache"] != "aus")


def mp3(wav, ziel):
    tmp = ziel + ".tmp.mp3"
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-codec:a", "libmp3lame", "-q:a", "2", tmp],
                       capture_output=True)
    if r.returncode != 0 or not os.path.exists(tmp) or not os.path.getsize(tmp):
        raise RuntimeError(f"ffmpeg mp3 {os.path.basename(ziel)}: {r.stderr[-200:]!r}")
    os.replace(tmp, ziel)


def nachbearbeiten(roh, ziel, w, rg, tempo):
    """Raender (FA) schneiden, Tempo, Lautheit je Satz, Spitze begrenzen -> MP3. -> Pruefwerte."""
    from pipeline import s510_hoerspiel_hybrid as s510
    from pipeline import s530_audio_pruefung as P5
    x = s510.lesen(roh)
    y, rand = P5.schneiden(x, w, float(rg["vor"]), float(rg["nach"]), tempo)
    y = P5.tempo_anwenden(y, tempo)
    lu, pk = P5.lautheit(y)
    gain = max(-P5.GAIN_MAX, min(P5.GAIN_MAX, float(rg["lufs"]) - lu)) if lu > -70 else 0.0
    y = y * 10 ** (gain / 20)
    if pk + gain > float(rg["peak_max"]):
        y = P5.begrenzen(y, float(rg["peak_max"]) - 1.0)
    lu2, pk2 = P5.lautheit(y)
    with tempfile.TemporaryDirectory() as d:
        q = os.path.join(d, "s.wav")
        s510.schreiben(q, y)
        mp3(q, ziel)
    return {"rand": list(rand) if rand else None, "lufs": round(lu2, 2), "peak": round(pk2, 2),
            "dauer": round(len(y) / P5.SR, 3), "gain_db": round(gain, 2)}


def urteil(e, text, rg, lg):
    """Pruefwerte eines Satzes -> Grund oder None."""
    if e.get("befund"):
        return e["befund"]
    if e.get("leer"):
        return "leer"
    if e.get("dauer_q") is not None and not (rg["dauer_min"] <= e["dauer_q"] <= rg["dauer_max"]):
        return "dauer"
    if not e.get("rand"):
        return "ohne_fa"
    if max(e["rand"]) > float(rg["rand_max"]):
        return "rand"
    if e.get("sprache") in ("gekippt", "verdacht"):
        return e["sprache"]
    if (e.get("dauer") or 0) >= 1.0 and abs(e["lufs"] - float(rg["lufs"])) > float(rg["lufs_tol"]):
        return "lufs"
    if e.get("peak") is not None and e["peak"] > float(rg["peak_max"]):
        return "spitze"
    return None


# ------------------------------------------------------------------ Lauf
def sprachen(b):
    return [lg for lg in b.sprachen if b.hat(sprache=lg, kanal="taella")]


def run(werk, wer=None, nur=None, neu=False, satz=None, nur_kosten=False, trocken=False):
    """satz: {"<lg>/<id>"} neu vertonen. -> Liste der Gates (je Sprache)."""
    from pipeline import s530_audio_pruefung as P5
    from pipeline.s600_klappentext import autor_laden
    wer = wer or "pipeline"
    b = bestellung.lesen(werk)
    rg = regler(werk)
    ents = entscheidungen(werk)
    annahmen = ents.get("annahmen") or {}
    k600 = _json(config.work_path(werk, "600_klappentext")) or {}
    meta, blurb = k600.get("meta") or {}, k600.get("blurb") or {}
    aj = autor_laden(werk)
    autor = (k600.get("autor") or meta.get("autor") or aj.get("name_display") or "").strip()
    wirkung = (k600.get("wirkungssprache") or aj.get("wirkungssprache") or "").strip()
    z600, z410 = status.zustand(werk, "600"), status.zustand(werk, "410")
    audio = set(b.audiosprachen())
    verlag = b.mandant_art == "verlag"
    satz = set(satz or ())
    m = _manifest(werk, nur_lesen=trocken or nur_kosten)
    st = status.laden(werk)["stages"].get(STAGE) or {}
    gates, schaetzung = [], {}
    if not (trocken or nur_kosten):
        usage_log.set_context(werk, STAGE)

    for lg in sprachen(b):
        if nur and lg not in nur:
            continue
        g = gate.Gate(werk, STAGE, scope=lg, ruecksprung="640", wer=wer)
        pf = g.hinweis if (trocken or nur_kosten) else g.pflicht
        pf("gate_600", z600 in status.FREI, z600, **({} if trocken or nur_kosten else {"ruecksprung": "600"}),
           text=f"Gate 600 frei ({z600})")
        if lg in audio:
            pf("gate_410", z410 in status.FREI, z410, **({} if trocken or nur_kosten else {"ruecksprung": "410"}),
               text=f"Gate 410 frei ({z410}, Audio bestellt)")
        ss = saetze(blurb, lg)
        g.pflicht("klappentext", bool(ss), len(ss), ruecksprung="600", text=f"Klappentext {lg} aus 600 ({len(ss)} Saetze)")
        info, fe, rs = stimme_waehlen(werk, b, lg, meta, aj, rg) if ss else (None, None, None)
        if ss:
            g.pflicht("stimme", info is not None, info and info["stimme"], ruecksprung=rs,
                      text=f"Stimme {lg}: " + (f"{info['stimme']} ({info['engine']}, {info['grund']})" if info else fe))
        if g.fehler() and not (trocken or nur_kosten):
            g.entscheide()
            gates.append(g)
            continue
        if not info:
            g.entscheide(schreiben=False)
            gates.append(g)
            continue
        for k_ in ("stimme", "engine", "quelle"):
            g.metrik(k_, info[k_])
        markup = sum(1 for s in ss if s["text"] != " ".join(s["roh"].split()))
        g.hinweis("markup", markup == 0, markup, text=f"Markup-Reste im Klappentext bereinigt: {markup} (Gate 600)")
        if autor and lg != (wirkung or b.quellsprache):
            g.hinweis("wirkungssprache", bool(wirkung), wirkung or None,
                      text="Wirkungssprache des Autors fehlt (110) – kein Aussprachehinweis" if not wirkung
                      else f"Autor-Aussprache {wirkung}")
        basis = stil(rg, lg, meta, info["engine"])
        tempo = _tempo(rg, lg, info)
        stimm_kern = {k_: info.get(k_) for k_ in ("stimme", "engine", "gemini_id", "referenz")}
        stimm_kern["adapter"] = (info.get("adapter") or {}).get("name"), (info.get("adapter") or {}).get("version")
        text_dir, audio_dir = blurb_dirs(werk, lg)
        rd = roh_dir(werk, lg)

        # Soll je Satz
        soll = {}
        for s in ss:
            sst = stil_satz(basis, s["text"], autor, lg, wirkung, rg.get("aussprache"))
            roh_h = manifest.hash_obj({"v": VERSION, "t": s["text"], "s": stimm_kern, "stil": sst})
            ein = manifest.hash_obj({"r": roh_h, "tempo": tempo, "p": [rg[k_] for k_ in ("vor", "nach", "lufs", "peak_max")]})
            soll[s["id"]] = dict(s, stil=sst, roh_h=roh_h, ein=ein, key=f"{lg}/{s['id']}",
                                 roh=os.path.join(rd, f"{s['id']}.wav"), ziel=os.path.join(audio_dir, f"{s['id']}.mp3"))

        def offen_roh(x):
            e = m.get(x["key"]) or {}
            return neu or x["key"] in satz or e.get("roh_h") != x["roh_h"] or not os.path.exists(x["roh"]) \
                or (not mock.aktiv() and mock.ist_datei(x["roh"]))

        def offen_ziel(x):
            e = m.get(x["key"]) or {}
            return offen_roh(x) or e.get("eingang") != x["ein"] or not m.datei_aktuell(x["key"]) \
                or (not mock.aktiv() and mock.ist_datei(x["ziel"]))

        z_roh = [x for x in soll.values() if offen_roh(x)]
        usd = kosten(info, sum(len(x["text"]) for x in z_roh))
        schaetzung[lg] = {"saetze": len(z_roh), "zeichen": sum(len(x["text"]) for x in z_roh), "usd": usd,
                          "engine": info["engine"], "stimme": info["stimme"]}
        g.metrik("kosten_schaetzung_usd", usd)
        if nur_kosten or trocken:
            g.entscheide(schreiben=False)
            gates.append(g)
            continue
        if not mock.aktiv():
            fe_w = werkzeuge(rg)
            g.pflicht("werkzeuge", not fe_w, fe_w or None, text="Werkzeuge (ffmpeg, FA, Whisper): "
                      + ("; ".join(fe_w) or "ok"))
            if g.fehler():
                g.entscheide()
                gates.append(g)
                continue
        print(f"[640] {lg}: {len(ss)} Saetze | {info['stimme']} ({info['engine']}, {info['grund']}) | "
              f"neu zu vertonen {len(z_roh)} | Schaetzung {usd:.4f} $")

        # Runden: vertonen -> nachbearbeiten -> pruefen; auffaellig bis rg["versuche"]x neu
        ms = ms_erwartung(info)
        runde, zu_vertonen = 0, z_roh
        nach = [x for x in soll.values() if offen_ziel(x)]
        while True:
            befund = {}
            if zu_vertonen:
                jobs = [(x["id"], x["text"], x["stil"], x["roh"]) for x in zu_vertonen]
                if mock.aktiv():
                    os.makedirs(rd, exist_ok=True)
                    for x in zu_vertonen:
                        mock.wav(x["roh"])
                    fertig = {x["id"]: x["roh"] for x in zu_vertonen}
                elif info["engine"] == "chatterbox":
                    fertig, befund = synth_chatterbox(werk, lg, jobs, info, rd)
                else:
                    fertig = synth_gemini(werk, lg, jobs, info)
                for x in zu_vertonen:
                    alt = m.get(x["key"]) or {}
                    frisch = runde == 0 and (neu or x["key"] in satz or alt.get("roh_h") != x["roh_h"])
                    v = (0 if frisch else alt.get("versuche", 0)) + 1
                    m.setzen(x["key"], None, roh_h=x["roh_h"] if x["id"] in fertig else None, versuche=v,
                             vertont=x["id"] in fertig)
                m.speichern()
            # Nachbearbeitung
            fa = {}
            if nach and not mock.aktiv():
                from pipeline import s510_hoerspiel_hybrid as s510
                jobs = [(x["id"], x["roh"], s510.woerter(x["text"])) for x in nach if os.path.exists(x["roh"])]
                fa = {k_: P5.raender(z) for k_, z in fa_zeiten(jobs, werk, lg, rg["fa"]).items()}
            os.makedirs(audio_dir, exist_ok=True)
            for x in nach:
                alt = m.get(x["key"]) or {}
                if not os.path.exists(x["roh"]):
                    m.setzen(x["key"], None, roh_h=None, versuche=alt.get("versuche", 0), vertont=False)
                    continue
                if mock.aktiv():
                    with open(x["ziel"], "wb") as f:
                        f.write(b"MOCK" + mock.MARKER)
                    w = {"rand": None, "lufs": None, "peak": None, "dauer": 0.0}
                    roh_dauer = 0.0
                else:
                    from pipeline import s500_vertonung_gemini as s5
                    wi = s5.wav_info(x["roh"])
                    roh_dauer = wi["dauer"]
                    w = nachbearbeiten(x["roh"], x["ziel"], fa.get(x["id"]), rg, tempo)
                    w["leer"] = wi["leer"] or wi["clip"] > 0.001
                q = round(roh_dauer / (len(x["text"]) * ms), 3) if len(x["text"]) >= 15 and roh_dauer else None
                m.setzen(x["key"], x["ein"], datei=x["ziel"], roh_h=x["roh_h"], versuche=alt.get("versuche", 0),
                         engine=info["engine"], stimme=info["stimme"], stil=x["stil"], text=x["text"],
                         block=x["block"], index=x["index"], dauer_q=q, befund=befund.get(x["id"]), **w)
            m.speichern()
            # Sprachpruefung (Whisper) nur fuer neu nachbearbeitete Saetze
            if nach and not mock.aktiv() and rg["sprache"] != "aus":
                with tempfile.TemporaryDirectory() as d:
                    jobs = []
                    for x in nach:
                        if os.path.exists(x["ziel"]) and (m.get(x["key"]) or {}).get("eingang") == x["ein"]:
                            p = os.path.join(d, f"{x['id']}.wav")
                            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", x["ziel"], "-ar", "24000",
                                            "-ac", "1", p], check=True)
                            jobs.append((x["id"], p))
                    res = sprache_pruefen(jobs, werk, lg, rg["sprache"])
                for x in nach:
                    if x["id"] in res:
                        u, c = P5.urteil(res[x["id"]], x["text"], lg, rg)
                        e = m.get(x["key"])
                        e.update(sprache=u, cer=c, abschrift=(res[x["id"]] or {}).get("text"))
                m.speichern()
            # Urteil, Wiederholung
            auff = []
            for x in soll.values():
                e = m.get(x["key"]) or {}
                if e.get("eingang") != x["ein"]:
                    continue
                gr = None if mock.aktiv() else urteil(e, x["text"], rg, lg)
                if gr and annahmen.get(x["key"]) == e.get("datei_hash"):
                    gr = None
                    e["angenommen"] = True
                e["grund"] = gr
                if gr and e.get("versuche", 0) <= int(rg["versuche"]):
                    auff.append(x)
            m.speichern()
            if not auff or runde >= int(rg["versuche"]):
                break
            runde += 1
            print(f"[640] {lg}: Runde {runde}: {len(auff)} auffaellig -> neu ({', '.join(x['id'] for x in auff)})")
            zu_vertonen, nach = auff, auff

        # Verwaiste Saetze
        for key in [k_ for k_ in list(m.eintraege) if k_.startswith(f"{lg}/") and k_.split("/", 1)[1] not in soll]:
            p = m._abs((m.get(key) or {}).get("datei") or "")
            for q_ in (p, os.path.join(rd, key.split("/", 1)[1] + ".wav")):
                if q_ and os.path.exists(q_):
                    os.remove(q_)
            m.entfernen(key)
        for alt_f in os.listdir(audio_dir) if os.path.isdir(audio_dir) else []:
            stem, ext = os.path.splitext(alt_f)
            if ext in (".mp3", ".wav") and stem not in soll:
                os.remove(os.path.join(audio_dir, alt_f))

        # Ausgabe Text + Audio-Manifest
        ein = [m.get(f"{lg}/{i}") or {} for i in soll]
        os.makedirs(text_dir, exist_ok=True)
        manifest.json_atomar(os.path.join(text_dir, "blurb.json"), {"lang": lg, "snippets": [
            {"id": x["id"], "block": x["block"], "index": x["index"], "text": x["text"]} for x in soll.values()]},
            indent=2)
        manifest.json_atomar(os.path.join(audio_dir, "manifest.json"), {
            "lang": lg, "schema": 2, "stage": STAGE, "engine": info["engine"], "voice": info["stimme"],
            "voice_quelle": info["quelle"], "stil": basis, "autor": autor, "source_language": wirkung,
            "snippets": [{"id": x["id"], "file": os.path.basename(x["ziel"]), "block": x["block"],
                          "index": x["index"], "text": x["text"], "dauer": (m.get(x["key"]) or {}).get("dauer")}
                         for x in soll.values() if (m.get(x["key"]) or {}).get("eingang") == x["ein"]]}, indent=2)

        # Gate
        n = len(soll)
        da = sum(1 for x in soll.values() if (m.get(x["key"]) or {}).get("eingang") == x["ein"]
                 and m.datei_aktuell(x["key"]))
        g.pflicht("abdeckung", da == n, round(da / n, 4), ruecksprung="640", text=f"Abdeckung {da}/{n} Saetze mit Audio")
        gruende = {x["id"]: (m.get(x["key"]) or {}).get("grund") for x in soll.values()}
        auff = {i: gr for i, gr in gruende.items() if gr}
        art_von = {"dauer": "dauer", "leer": "dauer", "rand": "rand", "ohne_fa": "rand", "lufs": "lufs", "spitze": "lufs"}
        for art in ("sprache", "dauer", "rand", "lufs"):
            g.metrik(f"auffaellig_{art}", sum(1 for gr in auff.values() if art_von.get(gr, "sprache") == art))
        rs_a = "410" if any(gr in ("gekippt",) for gr in auff.values()) and info["quelle"] == "casting" else "640"
        g.pruefe("auffaellig", not auff, len(auff), 0, "mensch", rs_a,
                 text=f"Auffaellige Saetze nach {rg['versuche']}x neu: {len(auff)}"
                      + (" – Hoerliste: " + ", ".join(f"{i} ({gr})" for i, gr in auff.items()) if auff else ""))
        werte = [m.get(x["key"]) or {} for x in soll.values()]
        lufs = [e["lufs"] for e in werte if e.get("lufs") is not None and (e.get("dauer") or 0) >= 1.0]
        g.metrik("lufs_min", min(lufs) if lufs else None)
        g.metrik("lufs_max", max(lufs) if lufs else None)
        pk = [e["peak"] for e in werte if e.get("peak") is not None]
        g.metrik("peak_max", max(pk) if pk else None)
        rd_ = [max(e["rand"]) for e in werte if e.get("rand")]
        g.metrik("rand_max", max(rd_) if rd_ else None)
        g.metrik("dauer_s", round(sum(e.get("dauer") or 0 for e in werte), 2))
        g.metrik("versuche_max", max((e.get("versuche") or 0) for e in werte) if werte else 0)
        n_mock = sum(1 for x in soll.values() if os.path.exists(x["ziel"]) and mock.ist_datei(x["ziel"]))
        g.mock(n_mock, [x["id"] for x in soll.values() if os.path.exists(x["ziel"]) and mock.ist_datei(x["ziel"])][:3],
               ruecksprung="640")
        ausgabe_hash = manifest.hash_obj(sorted((x["id"], (m.get(x["key"]) or {}).get("datei_hash")) for x in soll.values()))
        g.metrik("ausgabe_hash", ausgabe_hash)
        alt = (st.get("teile") or {}).get(lg) or {}
        mensch_gilt = alt.get("zustand") == "frei" and (alt.get("gate") or {}).get("ergebnis") == "mensch" \
            and (alt.get("metriken") or {}).get("ausgabe_hash") == ausgabe_hash
        if mensch_gilt:
            for p in g.pruefungen:
                if not p["ok"] and p["bei_fehler"] == "mensch":
                    p["bei_fehler"] = "hinweis"
                    p["text"] += " [Mensch-Freigabe gilt, Teaser unveraendert]"
            immer, grund = False, None
        else:
            immer, grund = verlag, "Mandant verlag: Teaser anhoeren und freigeben" if verlag else None
        e = g.entscheide(mensch_immer=immer, mensch_grund=grund)
        m.meta[lg] = {"stimme": info["stimme"], "engine": info["engine"], "quelle": info["quelle"],
                      "grund": info["grund"], "stil": basis, "tempo": tempo, "ausgabe_hash": ausgabe_hash,
                      "pruefung": {"ergebnis": e, "gruende": g.ergebnis["gruende"], "zeit": manifest.jetzt()}}
        m.speichern()
        gates.append(g)

    if schaetzung:
        ges = round(sum(v["usd"] for v in schaetzung.values()), 4)
        print(f"[640] Kostenschaetzung: {ges:.4f} $ – " + "; ".join(
            f"{lg} {v['saetze']} Saetze/{v['zeichen']} Z. {v['engine']} {v['usd']:.4f} $" for lg, v in schaetzung.items()))
    return gates


def annehmen(werk, wer, ziele, grund):
    """Auffaellige Saetze trotz Befund annehmen (gilt fuer die aktuelle Datei)."""
    m = _manifest(werk)
    an = dict(entscheidungen(werk).get("annahmen") or {})
    for z in ziele:
        e = m.get(z)
        if not e or not e.get("datei_hash"):
            raise ValueError(f"--annehmen {z}: kein Teaser-Satz mit Audio")
        an[z] = e["datei_hash"]
    entscheidung_setzen(werk, wer, annahmen=an, angenommen=sorted(ziele), grund=grund)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 640 Teaser")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--stimme", action="append", metavar="LG=NAME|weg", help="Stimme je Sprache manuell")
    ap.add_argument("--stil", action="append", metavar="LG|*=TEXT|weg", help="Gemini-Stil (Standard aus meta.ton)")
    ap.add_argument("--engine", action="append", metavar="LG=gemini|chatterbox")
    ap.add_argument("--tempo", action="append", metavar="LG|*=F")
    ap.add_argument("--aussprache", choices=["an", "aus"], help="Aussprachehinweis Autor")
    ap.add_argument("--fa", choices=["modal", "cpu"])
    ap.add_argument("--sprachpruefung", choices=["modal", "cpu", "aus"])
    ap.add_argument("--satz", action="append", metavar="LG:ID", help="Satz neu vertonen")
    ap.add_argument("--annehmen", action="append", metavar="LG:ID", help="Satz trotz Befund annehmen")
    ap.add_argument("--grund", default="")
    ap.add_argument("--sprache", action="append", metavar="LG")
    ap.add_argument("--neu", action="store_true", help="alle Saetze neu vertonen")
    ap.add_argument("--kosten", action="store_true", help="nur Kostenschaetzung")
    ap.add_argument("--trocken", action="store_true")
    ap.add_argument("--force", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--lang", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    wer = a.wer or "pipeline"

    def paare(xs, name, zahl=False):
        out = {}
        for x in xs or []:
            if "=" not in x:
                raise ValueError(f"--{name} {x!r}: Format LG=WERT")
            k, v = x.split("=", 1)
            v = v.strip()
            out[k.strip().lower() if k.strip() != "*" else "*"] = None if v in ("", "weg") else (float(v) if zahl else v)
        return out

    def ids(xs):
        return {x.replace(":", "/", 1) for x in xs or []}

    try:
        aend = {}
        for name, xs, zahl in (("stimme", a.stimme, False), ("stil", a.stil, False), ("engine", a.engine, False),
                               ("tempo", a.tempo, True)):
            p = paare(xs, name, zahl)
            if p:
                if name == "engine" and any(v not in (None, "gemini", "chatterbox") for v in p.values()):
                    raise ValueError("--engine gemini|chatterbox")
                aend[name] = p
        for name, v in (("aussprache", a.aussprache), ("fa", a.fa), ("sprache", a.sprachpruefung)):
            if v:
                aend[name] = v
        if (aend or a.annehmen) and not a.trocken:
            from pipeline import s080_mandant
            s080_mandant.darf(a.werk, "entscheiden", wer)
        if aend and not a.trocken:
            rg = dict(entscheidungen(a.werk).get("regler") or {})
            for k, v in aend.items():
                if isinstance(v, dict):
                    d = dict(rg.get(k) or {})
                    for lg, w in v.items():
                        if w is None:
                            d.pop(lg, None)
                        else:
                            d[lg] = w
                    rg[k] = d
                else:
                    rg[k] = v
            entscheidung_setzen(a.werk, wer, regler=rg)
        if a.annehmen and not a.trocken:
            if not a.grund:
                raise ValueError("--annehmen braucht --grund")
            annehmen(a.werk, wer, ids(a.annehmen), a.grund)
        nur = a.sprache or (a.lang.split(",") if a.lang else None)
        gates = run(a.werk, wer, nur, a.neu or a.force, ids(a.satz), a.kosten, a.trocken)
    except gate.GateHalt as e:
        print(e)
        return e.exit_code
    except (ValueError, PermissionError, RuntimeError) as e:
        print(f"[640] Fehler: {e}")
        return 1
    for g in gates:
        print(f"--- {g.scope}")
        print(g.bericht())
    if a.kosten or a.trocken:
        return 0
    return gate.EXIT[gate.gesamt([g.ergebnis["ergebnis"] for g in gates])] if gates else 0


if __name__ == "__main__":
    raise SystemExit(main())
