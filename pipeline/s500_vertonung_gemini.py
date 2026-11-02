"""STAGE 500 — Vertonung (Umbau Phase 2, GATE_KATALOG.md Zeile 500, 02.11.2026)
Funktion:     Satz-WAVs je bestellter Audiosprache (Hoerbuch/Hoerspiel-Erzaehlerspur) in der Engine der Stufe:
              Basic -> Chatterbox auf Modal (pipeline/s502_vertonung_chatterbox.py), Premium/Drama -> Gemini-TTS
              (hier: Bloecke mit FA-Schnitt am Energietal, Sentinel, Solo-Fallback). Ansage-Knoten aus 400 mit.
Wirkungsweise: Manifest work/500_vertonung.json je Sprache/Satz mit Eingangs-Hash (Sprechtext inkl. Aussprache-
              Lexikon, Engine, Stimme, Modell, Adapter-Version, Stil, Tempo): nur neue/geaenderte Saetze werden
              vertont (Altfassung/geaenderte Stimme -> automatisch neu). Vor jedem kostenpflichtigen Lauf
              Kostenschaetzung: Somnio im Budget (Regler --budget, Standard 0 $) -> auto, sonst Mensch
              (--kosten-freigeben USD). Satzpruefung je Satz
              (FA: Woerter/Nachklang/Vorlauf/Abbruch; Chatterbox im Modal-Lauf, Gemini lokal) + Dauer je Zeichen
              (Median der Sprache), leer, Clipping; auffaellig -> bis 2x neu (bestes bleibt, Nachklang gekappt).
              Erster Lauf uebernimmt vorhandene WAVs ohne Kosten bei eindeutigem Altbeleg mit gleicher Engine,
              Stimme und Adapter (book.json tts/stimme, gpu_tts/<werk>_<lg>/jobs.json, Alt-500 audio_voice_used).
Eingang:      work/400_regie.json (production.sprechtext/direction/pause_after_ms, ansagen; Gate 400 frei),
              work/casting.json Schema 2 freigegeben (rollen[lg][stufe].erzaehler: gemini_id bzw. referenz; adapter;
              Gate 410 frei), book.json (Bestellung, vertonung_regler), work/aussprache_<lg>.json (Lexikon, frei).
Ausgabe:      fassungen/<lg>/audio/<tag>.wav (Chatterbox-Rohfassung: audio_chatterbox_roh/), work/500_vertonung.json
              (Manifest Schema 1, Schluessel <lg>/<tag>), work/500_pruefung.json (Hoerliste), work/500_kosten.json
              (Freigaben). Altdatei 500_vertonung.json (production-Format) -> 500_vertonung_v1.json.
Gate:         Kosten (Somnio im Budget -> auto, sonst Mensch); Gate 400/410 frei, Casting freigegeben, eine Engine je
              Sprache, Stimme fuer Engine nutzbar, Adapter-Version registriert + freigegeben, Abdeckung + Aktualitaet
              nach Wiederholung, leer = 0, Mock im Live-Lauf = 0, FA-Pruefer verfuegbar -> sonst Stopp; auffaellig
              <= 1 %, Clipping = 0 -> sonst Mensch (Hoerliste); Gemini-Fallback > 10 % der Bloecke, Uebernahme,
              Altfassung ohne Sprechtext -> Hinweis. Probe N -> immer Mensch. Mensch-Freigabe gilt bei gleichem
              ausgabe_hash.
Kosten:       usage_log Stage 500 mit Sprache (Gemini-TTS je Aufruf in tts_client, Modal-GPU in tts_modal_opt).
Regler:       book.json vertonung_regler: --engine LG=gemini|chatterbox, --tempo [LG=]F, --ex, --cfg, --block-min/
              --block-ideal/--block-max, --valley-ratio, --batch, --fp16 an|aus, --budget, --auffaellig-max,
              --dauer-min/--dauer-max, --versuche; dazu --satz ID (neu), --kapitel c001,c002, --lang, --neu,
              --probe N, --kosten-freigeben USD, --trocken.
Aufruf:       py -3.11 -m pipeline.s500_vertonung_gemini <werk> [Regler] [--wer CK]
Exit: 0 auto, 2 Stopp, 3 Mensch, 1 Fehler.
"""
import argparse
import array
import datetime as dt
import json
import os
import re
import statistics
import sys
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import bestellung, gate, manifest, mock, status, usage_log
from pipeline import s410_casting as s410
from pipeline import s502_vertonung_chatterbox as cb

STAGE = "500"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = s410.ENGINE
LANG_CODE = {"en": "en-US", "de": "de-DE", "fr": "fr-FR", "es": "es-ES", "it": "it-IT"}
REGLER_STD = {"engine": {}, "tempo": {}, "ex": 0.5, "cfg": 0.5, "block_min": None, "block_ideal": None,
              "block_max": None, "valley_ratio": 0.45, "batch": cb.BATCH_STD, "fp16": False,
              "budget": getattr(config, "BUDGET_500_USD", 0.0), "auffaellig_max": 0.01,
              "dauer_min": 0.6, "dauer_max": 1.6, "versuche": 2}
MS_GEMINI = 0.065            # s je Zeichen (Erwartung FA-Pruefer; Dauer-Gate misst den Median der Sprache)
KOSTEN_PUFFER = 1.15         # Wiederholungen/Fallback
FALLBACK_HINWEIS = 0.10
RETRIES = 4
PAUSE = None                 # s zwischen Gemini-Aufrufen (None = config.TTS_DELAY_SECONDS)
RANG = {None: 0, "nachklang": 1, "vorlauf": 2, "dauer": 3, "zu_lang": 3, "verschmiert": 3,
        "nicht_ausrichtbar": 3, "clipping": 3, "zu_kurz": 4, "leer": 5}
SENTINEL = {"de": "So weit, so gut.", "en": "So far, so good.", "fr": "Jusqu'ici, tout va bien.",
            "es": "Hasta aquí, todo bien.", "it": "Fin qui, tutto bene."}
SENTINEL_ID = "__sentinel__"
BLOCK_WPS, BLOCK_MAX_DUR_FACTOR = 2.5, 2.5
_TERMINAL = ".?!…:;"


# ============================================================ Ablage
def pfad(werk):
    return config.work_path(werk, "500_vertonung")


def audio_dir(werk, lg):
    return os.path.join(config.book_dir(werk), "fassungen", lg, "audio")


def _json(p, leer=None):
    if not os.path.exists(p):
        return leer
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _manifest(werk, schreiben):
    """Manifest laden; Altdatei (production-Format) beim echten Lauf nach 500_vertonung_v1.json verschieben."""
    p = pfad(werk)
    alt = _json(p)
    if alt is not None and (alt.get("schema") != manifest.SCHEMA or "eintraege" not in alt):
        if not schreiben:
            m = manifest.Manifest.__new__(manifest.Manifest)
            m.book_id, m.name, m.pfad = werk, "500_vertonung", p
            m.basis = os.path.dirname(os.path.dirname(p))
            m.d = {"schema": manifest.SCHEMA, "stage": STAGE, "meta": {}, "eintraege": {}}
            return m, True
        os.replace(p, os.path.join(config.work_dir(werk), "500_vertonung_v1.json"))
        return manifest.Manifest(werk, "500_vertonung", stage=STAGE), True
    return manifest.Manifest(werk, "500_vertonung", stage=STAGE), alt is None


# ============================================================ Einheiten
def _ensure_terminal(t):
    t = (t or "").rstrip()
    tail = t.rstrip("\"”»’'）)]")
    return t if (not t or (tail and tail[-1] in _TERMINAL)) else t + "."


def einheiten(data, lg):
    """[{id, typ, text, style, pause}] in Hoerreihenfolge (Ansagen Anfang, Knoten, Ansagen Ende); alt = ohne Sprechtext."""
    content = data.get("content") or {}
    prod = data.get("production") or {}
    sp, di, pa = (prod.get(k) or {} for k in ("sprechtext", "direction", "pause_after_ms"))
    an = (data.get("ansagen") or {}).get(lg) or []
    out, alt = [], 0

    def ansage(k):
        return {"id": k["id"], "typ": "ansage", "text": (k.get("sprechtext") or k.get("text") or "").strip(),
                "style": k.get("direction") or "", "pause": k.get("pause_after_ms")}
    out += [ansage(k) for k in an if k.get("position") == "anfang"]
    for tid, e in content.items():
        if not isinstance(e, dict) or e.get("type", "s") in config.NO_AUDIO_TYPES:
            continue
        t = (sp.get(tid) or {}).get(lg)
        if t is None and str(e.get(lg) or "").strip():
            from pipeline.sprechtext import sprechtext
            t = sprechtext(str(e[lg]).strip(), lg, e.get("type"))
            alt += 1
        if not (t or "").strip():
            continue
        out.append({"id": tid, "typ": e.get("type", "s"), "text": t.strip(), "style": (di.get(tid) or {}).get(lg) or "",
                    "pause": (pa.get(tid) or {}).get(lg)})
    out += [ansage(k) for k in an if k.get("position") != "anfang"]
    return [u for u in out if u["text"]], alt


def _lexikon(werk, lg):
    try:
        from tools.tts_paket import lexikon, lex_text
        ers = lexikon(config.book_dir(werk), lg)
        return (lambda t: lex_text(t, ers)) if ers else (lambda t: t), len(ers)
    except Exception:
        return (lambda t: t), 0


# ============================================================ Engine / Stimme
def _stufen(b):
    z = {}
    for lg in b.audiosprachen():
        for p in b.produkte_fuer(sprache=lg):
            if p["inhalt"] in s410.AUDIO and p.get("stufe") and p["stufe"] not in z.setdefault(lg, []):
                z[lg].append(p["stufe"])
    return z


def engine_waehlen(stufen, vorgabe=None):
    """-> (engine, stufe, fehler)."""
    eng = sorted({ENGINE[s] for s in stufen if s in ENGINE})
    if vorgabe:
        st = next((s for s in stufen if ENGINE.get(s) == vorgabe), stufen[0] if stufen else None)
        return vorgabe, st, None
    if not eng:
        return None, None, f"keine Audio-Stufe ({', '.join(stufen) or '–'})"
    if len(eng) > 1:
        return None, None, f"zwei Engines ({'/'.join(stufen)}) – Regler --engine setzen"
    return eng[0], next(s for s in stufen if ENGINE.get(s) == eng[0]), None


def stimme(c, lg, stufe, engine):
    """-> (info, fehler). info: stimme, gemini_id, referenz, modell, adapter."""
    bs = (((c or {}).get("rollen") or {}).get(lg) or {}).get(stufe) or {}
    erz = bs.get("erzaehler") or {}
    if not erz.get("stimme"):
        return None, f"kein Erzaehler in rollen[{lg}][{stufe}]"
    info = {"stimme": erz["stimme"], "gemini_id": erz.get("gemini_id"), "referenz": erz.get("referenz"),
            "modell": erz.get("modell"), "adapter": bs.get("adapter"), "quelle": erz.get("quelle")}
    if engine == "gemini" and not info["gemini_id"]:
        return info, f"{erz['stimme']} ohne Gemini-ID"
    if engine == "chatterbox":
        if info["referenz"] is None and erz["stimme"] != s410.CB_STANDARD:
            return info, f"{erz['stimme']} ohne Chatterbox-Referenz"
        if info["referenz"] and not os.path.exists(os.path.join(config.BASE_DIR, info["referenz"])):
            return info, f"Referenz {info['referenz']} fehlt"
    return info, None


def adapter_pruefen(a):
    """Adapter aus casting.json gegen config.LORA_ADAPTER: -> fehler | None."""
    if not a:
        return None
    reg = (getattr(config, "LORA_ADAPTER", {}) or {}).get(a.get("name"))
    if not reg:
        return f"Adapter {a.get('name')} nicht registriert"
    if str(reg.get("version")) != str(a.get("version")):
        return f"Adapter {a.get('name')} v{a.get('version')} nicht verfuegbar (registriert v{reg.get('version')})"
    if not reg.get("freigegeben"):
        return f"Adapter {a.get('name')} v{a.get('version')} nicht freigegeben"
    return None


def _tempo(rg, lg, engine, adapter):
    t = (rg.get("tempo") or {}).get(lg)
    if t is None:
        t = (rg.get("tempo") or {}).get("*")
    if t is None:
        t = cb.lora_werte((adapter or {}).get("name"))[1] if engine == "chatterbox" else 1.0
    return float(t)


def altbeleg(werk, lg, roh, alt500):
    """Womit wurde der Altbestand einer Sprache vertont? -> [(engine, stimme, adapter)] aus book.json tts/stimme,
    gpu_tts/<werk>_<lg>/jobs.json (Chatterbox) und Alt-500_vertonung.json (Gemini, audio_voice_used)."""
    out = []
    t = roh.get("tts") if isinstance(roh.get("tts"), dict) else {}
    st = roh.get("stimme")
    st = st.get(lg) if isinstance(st, dict) else st
    if t.get(lg) in ("gemini", "chatterbox") and st:
        out.append((t[lg], st, roh.get("tts_lora") if t[lg] == "chatterbox" else None))
    j = _json(os.path.join(config.BASE_DIR, "gpu_tts", f"{werk}_{lg}", "jobs.json"))
    if j:
        out.append(("chatterbox", j.get("ref") or "chatterbox-standard", j.get("lora")))
    pr = (alt500 or {}).get("production") or {}
    if lg in (pr.get("audio_manifest") or {}) and pr.get("audio_voice_used"):
        out.append(("gemini", pr["audio_voice_used"], None))
    return out


def uebernahme_ok(belege, engine, info):
    """Nur bei eindeutigem Beleg: gleiche Engine, gleiche Stimme (Name bzw. Gemini-ID), gleicher Adapter."""
    if not belege or len({(e, s, a) for e, s, a in belege}) != 1:
        return False
    e, s_, a = belege[0]
    ad = (info.get("adapter") or {}).get("name") if engine == "chatterbox" else None
    return e == engine and s_ in (info["stimme"], info["gemini_id"]) and (a or None) == (ad or None)


def eingang_hash(u, tts_text, engine, info, rg, tempo):
    return manifest.hash_obj({"t": tts_text, "e": engine, "s": info["stimme"],
                              "id": info["gemini_id"] if engine == "gemini" else info["referenz"],
                              "m": info.get("modell"), "a": (info.get("adapter") or {}) if engine == "chatterbox" else None,
                              "d": u["style"] if engine == "gemini" else None,
                              "x": [rg["ex"], rg["cfg"]] if engine == "chatterbox" else None, "tempo": tempo})


# ============================================================ Kosten
def kosten(engine, zeichen, heute=None):
    if not zeichen:
        return 0.0
    if engine == "chatterbox":
        usd = zeichen / 100_000 * (getattr(config, "ANGEBOT_USD_100K", {}) or {}).get("hoerbuch_basic", 0.5)
    else:
        m = config.MODELS.get("tts", "gemini-3.8-flash-tts")
        sek = zeichen * MS_GEMINI
        usd = usage_log._usd(m, zeichen // 4 + 1, 0, round(sek * 25), heute or dt.datetime.now(dt.timezone.utc))
        if usd is None:
            usd = zeichen / 100_000 * (getattr(config, "ANGEBOT_USD_100K", {}) or {}).get("hoerbuch_premium", 1.5)
    return round(usd * KOSTEN_PUFFER, 4)


def _kosten_protokoll(werk, eintrag):
    p = os.path.join(config.work_dir(werk), "500_kosten.json")
    d = _json(p, {"freigaben": []}) or {"freigaben": []}
    d["freigaben"].append(eintrag)
    manifest.json_atomar(p, d, indent=1)


# ============================================================ WAV-Pruefung (lokal, ohne torch)
def wav_info(p):
    """-> {dauer, leer, clip} (clip = Anteil Vollaussteuerung)."""
    try:
        with wave.open(p, "rb") as w:
            n, sr, sw = w.getnframes(), w.getframerate(), w.getsampwidth()
            raw = w.readframes(n)
    except Exception:
        return {"dauer": 0.0, "leer": True, "clip": 0.0}
    dauer = n / float(sr or 1)
    if sw != 2 or not raw:
        return {"dauer": round(dauer, 3), "leer": dauer < 0.1, "clip": 0.0}
    a = array.array("h", raw)
    if sys.byteorder == "big":
        a.byteswap()
    spitze = max(max(a), -min(a))
    clip = sum(1 for x in a if x >= 32700 or x <= -32700) / len(a) if spitze >= 32700 else 0.0
    return {"dauer": round(dauer, 3), "leer": dauer < 0.1 or spitze < 100, "clip": round(clip, 5)}


def wav_dauer(p):
    try:
        with wave.open(p, "rb") as w:
            return round(w.getnframes() / float(w.getframerate() or 1), 3)
    except Exception:
        return 0.0


class FaPruefer:
    """Satzpruefung per Forced Alignment (gpu_tts/cb_pruefung.py, MMS_FA) lokal auf der CPU (Gemini-Gleis)."""
    def __init__(self, ms):
        sys.path.insert(0, os.path.join(REPO, "gpu_tts"))
        import cb_pruefung
        import torchaudio
        cb_pruefung.MS_JE_ZEICHEN = ms
        self.cbp, self.ta = cb_pruefung, torchaudio
        self.p = cb_pruefung.Pruefer("cpu")

    def pruefe(self, text, p):
        w, sr = self.ta.load(p)
        return self.p.pruefe(text, w, sr)

    def kappen(self, p, ende):
        w, sr = self.ta.load(p)
        self.ta.save(p, self.cbp.kappen(w, sr, ende), sr, encoding="PCM_S", bits_per_sample=16)


def pruefer_fabrik(ms):
    return FaPruefer(ms)


def _grund_lokal(info, text, median, rg):
    if info["leer"]:
        return "leer"
    if info["clip"] > 0.001:
        return "clipping"
    if median and len(text) >= 15:
        q = info["dauer"] / (len(text) * median)
        if not (rg["dauer_min"] <= q <= rg["dauer_max"]):
            return "dauer"
    return None


# ============================================================ Gemini-Engine
def _pause():
    return getattr(config, "TTS_DELAY_SECONDS", 4) if PAUSE is None else PAUSE


def synth(text, style, out, voice, lg):
    """Ein Gemini-TTS-Aufruf -> WAV (tts_client; Kosten loggt tts_client unter usage_log-Kontext)."""
    from pipeline import tts_client
    tts_client.synthesize_wav(text, style, out, voice, LANG_CODE.get(lg, lg))


def _synth_retry(text, style, out, voice, lg, label):
    from pipeline import tts_client
    for i in range(1, RETRIES + 1):
        try:
            synth(text, style, out, voice, lg)
            time.sleep(_pause())
            return True
        except tts_client.QuotaError:
            raise
        except Exception as e:
            if i < RETRIES:
                print(f"    {label}: Fehler ({type(e).__name__}), Versuch {i + 1}")
                time.sleep(i * 3 if _pause() else 0)
            else:
                print(f"    {label}: endgueltig fehlgeschlagen: {str(e)[:120]}")
    return False


def block_style(stile):
    """Stil des ersten Satzes + Aussprachehinweise aller Saetze (3.8: '; '-getrennt), ohne Dopplung."""
    teile = [s.split("; ") for s in stile if s]
    if not teile:
        return ""
    out = [teile[0][0]]
    for t in teile:
        for h in t[1:]:
            if h and h not in out:
                out.append(h)
    return "; ".join(out)


def _bloecke(content_reihe, offen, rg):
    """Plan ueber die ganze Kapitelfolge; Ausfuehrung nur fuer offene Saetze (zusammenhaengende Laeufe >= 2)."""
    from pipeline import block_planner as bp
    bp.BLOCKABLE, bp.PARA_BREAK = {"s", "dl"}, {"p"}
    bp.NO_AUDIO = set(config.NO_AUDIO_TYPES) | {"p"}
    for k, std in (("block_min", "TTS_BLOCK_MIN"), ("block_ideal", "TTS_BLOCK_IDEAL"), ("block_max", "TTS_BLOCK_MAX")):
        setattr(bp, k.upper(), int(rg[k] or getattr(config, std, getattr(bp, k.upper()))))
    out = []
    for seg in bp.plan_tag_blocks(content_reihe):
        ids = seg["tag_ids"]
        if seg["kind"] == "solo":
            out += [("solo", [t]) for t in ids if t in offen]
            continue
        lauf = []
        for t in ids + [None]:
            if t is not None and t in offen:
                lauf.append(t)
                continue
            if len(lauf) >= 2:
                out.append(("block", lauf))
            else:
                out += [("solo", [x]) for x in lauf]
            lauf = []
    return out


def gemini_vertonen(werk, lg, units, offen, voice, rg, adir, text_tts, out, fallback):
    """Fuellt out {tid: {pfad, block, fallback}} und fallback (Liste) laufend (Abbruch behaelt Fertiges). -> Bloecke."""
    from pipeline import audio_fa
    os.makedirs(adir, exist_ok=True)
    u_by = {u["id"]: u for u in units}
    reihe = [(u["id"], u["typ"]) for u in units if u["typ"] != "ansage"]
    plan = [("solo", [u["id"]]) for u in units if u["typ"] == "ansage" and u["id"] in offen]
    plan += _bloecke(reihe, offen, rg)
    n_block = 0

    def solo(t, block=False, fb=None):
        p = os.path.join(adir, f"{t}.wav")
        if mock.aktiv():
            mock.wav(p)
        elif not _synth_retry(_ensure_terminal(text_tts[t]), u_by[t]["style"], p, voice, lg, t):
            return
        out[t] = {"pfad": p, "block": block, "fallback": fb}

    for kind, ids in plan:
        if kind == "solo" or mock.aktiv():
            for t in ids:
                solo(t)
            n_block += kind == "block"
            continue
        n_block += 1
        saetze = [{"id": t, "text": _ensure_terminal(text_tts[t])} for t in ids]
        label = f"Block {ids[0]}..{ids[-1]} ({len(ids)})"
        bwav = os.path.join(adir, f"_blockS_{ids[0]}.wav")
        sent = _ensure_terminal(SENTINEL.get(lg, SENTINEL["en"]))
        grund = None
        if not _synth_retry(" ".join(s["text"] for s in saetze) + " " + sent,
                            block_style([u_by[t]["style"] for t in ids]), bwav, voice, lg, label):
            grund = "Block-TTS gescheitert"
        else:
            nw = sum(len(re.findall(r"\w+", s["text"])) for s in saetze)
            ist = wav_info(bwav)["dauer"]
            if ist > max(1.0, nw / BLOCK_WPS) * BLOCK_MAX_DUR_FACTOR:
                grund = f"Block zu lang ({ist:.0f}s)"
        if grund is None:
            try:
                rep = audio_fa.fa_cut(bwav, saetze + [{"id": SENTINEL_ID, "text": sent}],
                                      valley_ratio=float(rg["valley_ratio"]))
                bnds, cuts = rep.get("boundaries", []), rep.get("cuts", [])
                if not (rep["net"]["ok"] and len(bnds) == len(ids) == len(cuts)
                        and all(b["status"] == "OK" for b in bnds)):
                    grund = "FLAG " + (",".join(f"{b['after_id']}:{b['reason']}" for b in bnds if b["status"] != "OK")
                                       or "Mengen/Schnitt")
                else:
                    pfade = [os.path.join(adir, f"{t}.wav") for t in ids]
                    st = os.path.join(adir, f"_sentinel_{ids[0]}.wav")
                    w = audio_fa.slice_block(bwav, cuts, pfade + [st])
                    _weg(st)
                    if all(ok for _, ok in w[:len(ids)]):
                        for t, p in zip(ids, pfade):
                            out[t] = {"pfad": p, "block": True, "fallback": None}
                    else:
                        grund = "leeres Segment nach Schnitt"
            except Exception as e:
                grund = f"FA-Fehler {type(e).__name__}"
        _weg(bwav)
        if grund:
            print(f"  {label}: Fallback ({grund})")
            fallback.append({"von": ids[0], "bis": ids[-1], "n": len(ids), "grund": grund})
            for t in ids:
                solo(t, fb=grund)
        else:
            print(f"  {label}: ok")
    return n_block


def _weg(p):
    try:
        if p and os.path.exists(p):
            os.remove(p)
    except OSError:
        pass


def gemini_reparieren(lg, ids, units, voice, adir, text_tts, pruefer, befund):
    """Auffaellige Saetze einzeln neu (Solo); besseres Ergebnis ersetzt. -> Anzahl ersetzt."""
    u_by = {u["id"]: u for u in units}
    n = 0
    for t in ids:
        p = os.path.join(adir, f"{t}.wav")
        tmp = p + ".neu.wav"
        if not _synth_retry(_ensure_terminal(text_tts[t]), u_by[t]["style"], tmp, voice, lg, t + " (neu)"):
            continue
        b = dict(pruefer.pruefe(text_tts[t], tmp)) if pruefer else {"grund": None}
        b["grund"] = b.get("grund") or _grund_lokal(wav_info(tmp), text_tts[t], None, {})
        if RANG.get(b["grund"], 3) < RANG.get(befund[t].get("grund"), 3):
            os.replace(tmp, p)
            befund[t] = b
            n += 1
        else:
            _weg(tmp)
    return n


# ============================================================ Regler
def _regler(roh):
    r = json.loads(json.dumps(REGLER_STD))
    for k, v in (roh.get("vertonung_regler") or {}).items():
        if k in REGLER_STD:
            r[k] = dict(r[k], **v) if isinstance(REGLER_STD[k], dict) and isinstance(v, dict) else v
    return r


def regler_anwenden(rg, aend):
    rg = json.loads(json.dumps(rg))
    for k in REGLER_STD:
        v = aend.get(k)
        if v is None:
            continue
        if isinstance(REGLER_STD[k], dict):
            for kk, vv in v.items():
                if vv in (None, "auto"):
                    rg[k].pop(kk, None)
                else:
                    rg[k][kk] = vv
        else:
            rg[k] = None if v == "auto" else v
    return rg


def _regler_gueltig(rg):
    try:
        bl = [int(rg[k]) for k in ("block_min", "block_ideal", "block_max") if rg[k] is not None]
        return (all(v in ("gemini", "chatterbox") for v in rg["engine"].values())
                and all(0.5 <= float(v) <= 2.0 for v in rg["tempo"].values())
                and 0 <= float(rg["ex"]) <= 1 and 0 <= float(rg["cfg"]) <= 1
                and all(2 <= v <= 40 for v in bl) and bl == sorted(bl)
                and 0 < float(rg["valley_ratio"]) < 1 and 1 <= int(rg["batch"]) <= 32
                and rg["fp16"] in (True, False) and float(rg["budget"]) >= 0
                and 0 <= float(rg["auffaellig_max"]) <= 1
                and 0 < float(rg["dauer_min"]) < float(rg["dauer_max"])
                and 0 <= int(rg["versuche"]) <= 3)
    except Exception:
        return False


# ============================================================ Lauf
def run(werk, wer=None, regler=None, saetze=None, kapitel=None, nur_lang=None, neu=False, probe=None,
        kosten_freigeben=None, trocken=False):
    wer = wer or "pipeline"
    g = gate.Gate(werk, STAGE, ruecksprung="500", wer=wer)
    b = bestellung.lesen(werk)
    rg = _regler(dict(b.roh))
    if regler and any(v is not None for v in regler.values()):
        rg = regler_anwenden(rg, regler)
        if not trocken:
            b = bestellung.feld_setzen(werk, vertonung_regler=rg)
    stufen = _stufen(b)
    g.metrik("audiosprachen", stufen)
    g.metrik("regler", rg)
    ip = config.work_path(werk, "400_regie")
    ok = g.pflicht("eingang", os.path.exists(ip), ruecksprung="400", text="400_regie.json vorhanden")
    ok = g.pflicht("audio", bool(stufen), ruecksprung="095", text="Audio (Hoerbuch/Hoerspiel) bestellt") and ok
    ok = g.pflicht("regler", _regler_gueltig(rg), wert=rg, text="Regler im Bereich") and ok
    for v in ("400", "410"):
        z = status.zustand(werk, v)
        if trocken:
            g.hinweis(f"gate_{v}", z in status.FREI, text=f"Gate {v}: {z}")
        else:
            ok = g.pflicht(f"gate_{v}", z in status.FREI, wert=z, ruecksprung=v, text=f"Gate {v} frei ({z})") and ok
    c = s410.laden(werk)
    frei = s410.freigegeben(c)
    if trocken and c and c.get("schema") == s410.SCHEMA:
        g.hinweis("casting", frei, text="Casting freigegeben" + ("" if frei else " – nein (Probe)"))
    else:
        ok = g.pflicht("casting", frei, ruecksprung="410", text="casting.json (Schema 2) freigegeben") and ok
    if not ok:
        g.entscheide(schreiben=not trocken)
        return g
    with open(ip, encoding="utf-8") as f:
        data = json.load(f)
    alt500 = _json(pfad(werk)) or {}
    if alt500.get("schema") == manifest.SCHEMA:
        alt500 = _json(os.path.join(config.work_dir(werk), "500_vertonung_v1.json")) or {}
    m, erstlauf = _manifest(werk, not trocken)
    saetze, kap = set(saetze or []), set(kapitel or [])

    # ---- Planung je Sprache
    plan, je_sprache = {}, {}
    for lg in sorted(stufen):
        engine, stufe, fe = engine_waehlen(stufen[lg], (rg["engine"] or {}).get(lg))
        if not g.pflicht(f"engine_{lg}", fe is None, ruecksprung="095", text=f"{lg}: Engine eindeutig"
                         + (f" – {fe}" if fe else f" ({engine}, Stufe {stufe})")):
            continue
        info, fe = stimme(c, lg, stufe, engine)
        if not g.pflicht(f"stimme_{lg}", fe is None, ruecksprung="410",
                         text=f"{lg}: Stimme fuer {engine} nutzbar" + (f" – {fe}" if fe else f" ({info['stimme']})")):
            continue
        if engine == "chatterbox":
            fe = adapter_pruefen(info["adapter"])
            if not g.pflicht(f"adapter_{lg}", fe is None, wert=info["adapter"], ruecksprung="410",
                             text=f"{lg}: LoRA-Adapter " + (fe or f"{(info['adapter'] or {}).get('name') or 'keiner'} "
                                                                 f"verfuegbar + freigegeben")):
                continue
        units, alt = einheiten(data, lg)
        lex, n_lex = _lexikon(werk, lg)
        tempo = _tempo(rg, lg, engine, info["adapter"])
        tts = {u["id"]: lex(u["text"]) for u in units}
        soll = {u["id"]: eingang_hash(u, tts[u["id"]], engine, info, rg, tempo) for u in units}
        adir = audio_dir(werk, lg)
        # Erstlauf: vorhandene WAVs uebernehmen (Stimme alt = casting, kein Mock)
        uebern, nicht_uebern = 0, None
        if erstlauf and not neu and not any(k.startswith(f"{lg}/") for k in m.eintraege):
            belege = altbeleg(werk, lg, b.roh, alt500)
            vorh = [u for u in units if os.path.exists(os.path.join(adir, f"{u['id']}.wav"))]
            if vorh and uebernahme_ok(belege, engine, info):
                for u in vorh:
                    p = os.path.join(adir, f"{u['id']}.wav")
                    if os.path.getsize(p) > 0 and not mock.ist_datei(p) and not trocken:
                        m.setzen(f"{lg}/{u['id']}", soll[u["id"]], datei=p, engine=engine, stimme=info["stimme"],
                                 q="uebernommen", pruefung=None, versuche=0, pause_ms=u["pause"], dauer=wav_dauer(p))
                        uebern += 1
                    elif trocken and not mock.ist_datei(p):
                        uebern += 1
            elif vorh:
                nicht_uebern = (len(vorh), "; ".join(f"{e} {s_}" + (f" + {a}" if a else "") for e, s_, a in belege)
                                or "unbekannt")
        offen = []
        for u in units:
            k = f"{lg}/{u['id']}"
            if trocken and uebern and erstlauf and os.path.exists(os.path.join(adir, f"{u['id']}.wav")):
                continue
            mock_alt = (m.get(k) or {}).get("q") == "mock" and not mock.aktiv()
            if neu or u["id"] in saetze or mock_alt or m.braucht_neu(k, soll[u["id"]]) or not m.datei_aktuell(k):
                if kap and u["id"][:4] not in kap and u["id"] not in saetze:
                    continue
                offen.append(u["id"])
        if nur_lang and lg != nur_lang:
            offen = []
        if probe:
            offen = offen[:int(probe)]
        zeichen = sum(len(tts[t]) for t in offen)
        plan[lg] = dict(engine=engine, stufe=stufe, info=info, units=units, tts=tts, soll=soll, adir=adir,
                        offen=offen, tempo=tempo, zeichen=zeichen, usd=kosten(engine, zeichen), alt=alt,
                        uebern=uebern, nicht_uebern=nicht_uebern, n_lex=n_lex)
    usd = round(sum(p["usd"] for p in plan.values()), 4)
    n_offen = sum(len(p["offen"]) for p in plan.values())
    g.metrik("kosten_usd", usd)
    g.metrik("offen", {lg: len(p["offen"]) for lg, p in plan.items()})
    if g.fehler():
        g.entscheide(schreiben=not trocken)
        return g

    # ---- Kostenfreigabe / FA-Pruefer vor dem Lauf
    if n_offen and not mock.aktiv() and not trocken:
        frei_k = kosten_freigeben is not None and usd <= float(kosten_freigeben)
        im_budget = b.mandant_art == "somnio" and usd <= float(rg["budget"])
        txt = (f"Kostenschaetzung {usd:.2f} $ fuer {n_offen} Saetze ("
               + ", ".join(f"{lg} {p['engine']} {len(p['offen'])} S./{p['zeichen']} Z. ~{p['usd']:.2f} $"
                           for lg, p in plan.items() if p["offen"]) + ")")
        if not (frei_k or im_budget):
            g.pruefe("kosten", False, wert=usd, bei_fehler="mensch", ruecksprung="500",
                     text=txt + (f" ueber Budget {float(rg['budget']):.2f} $" if b.mandant_art == "somnio"
                                 else f" – Mandant {b.mandant_art}")
                     + f" – Freigabe: py -3.11 -m pipeline.s500_vertonung_gemini {werk} --kosten-freigeben "
                       f"{usd:.2f} --wer CK" + (f" (Freigabe {float(kosten_freigeben):.2f} $ reicht nicht)"
                                                 if kosten_freigeben is not None else ""))
            g.entscheide(schreiben=True)
            return g
        g.hinweis("kosten", True, wert=usd, text=txt + (" – freigegeben" if frei_k else " – im Budget"))
        if frei_k:
            _kosten_protokoll(werk, {"wann": status.jetzt(), "wer": wer, "usd": usd, "grenze": float(kosten_freigeben),
                                     "saetze": n_offen})
        if any(p["engine"] == "gemini" and p["offen"] for p in plan.values()):
            try:
                pruefer_g = pruefer_fabrik(MS_GEMINI)
            except Exception as e:
                g.pflicht("fa_pruefer", False, ruecksprung="500",
                          text=f"FA-Satzpruefung nicht verfuegbar ({type(e).__name__}: {str(e)[:80]}) – torch/torchaudio")
                g.entscheide(schreiben=True)
                return g
        else:
            pruefer_g = None
    else:
        pruefer_g = None
        if trocken and n_offen:
            g.hinweis("kosten", False, wert=usd, text=f"Probe: {n_offen} Saetze wuerden vertont, ~{usd:.2f} $")

    # ---- Vertonung + Pruefung je Sprache
    pruef, ausfall = {}, None
    for lg, p in plan.items():
        engine, info, units, tts, adir = p["engine"], p["info"], p["units"], p["tts"], p["adir"]
        befund, neu_ids, fb, n_bl = {}, {}, [], 0
        if p["offen"] and not trocken and ausfall is None:
            usage_log.set_context(werk, STAGE, sprache=lg)
            print(f"[500] {lg} ({engine}, {info['stimme']}): {len(p['offen'])} Saetze")
            try:
                if engine == "gemini":
                    n_bl = gemini_vertonen(werk, lg, units, set(p["offen"]), info["gemini_id"], rg, adir, tts,
                                           neu_ids, fb)
                else:
                    neu_ids.update(_cb_runde(werk, lg, p["offen"], tts, info, rg, p["tempo"], adir, befund))
            except Exception as e:
                ausfall = f"{lg}: {type(e).__name__}: {str(e)[:160]}"
                print(f"[500] Abbruch {ausfall}")
            for t, x in neu_ids.items():
                befund.setdefault(t, {"grund": None})
            # Satzpruefung: FA (Gemini lokal; Chatterbox aus Modal) + lokal Dauer/leer/Clipping, bis N x neu
            if engine == "gemini" and pruefer_g and not mock.aktiv():
                for t in neu_ids:
                    befund[t] = dict(pruefer_g.pruefe(tts[t], neu_ids[t]["pfad"]))
            med = _median(units, tts, m, lg, {t: wav_dauer(x["pfad"]) for t, x in neu_ids.items()})
            for t, x in neu_ids.items():
                befund[t]["grund"] = befund[t].get("grund") or _grund_lokal(wav_info(x["pfad"]), tts[t], med, rg)
            versuche = {t: 0 for t in neu_ids}
            for _ in range(int(rg["versuche"])):
                schlecht = [t for t in neu_ids if befund[t].get("grund") and befund[t]["grund"] != "nachklang"]
                if not schlecht or mock.aktiv() or ausfall:
                    break
                for t in schlecht:
                    versuche[t] += 1
                try:
                    if engine == "gemini":
                        gemini_reparieren(lg, schlecht, units, info["gemini_id"], adir, tts, pruefer_g, befund)
                    else:
                        _cb_runde(werk, lg, schlecht, tts, info, rg, p["tempo"], adir, befund, ersetzen_wenn_besser=True)
                except Exception as e:
                    print(f"[500] Wiederholung {lg} abgebrochen: {type(e).__name__}")
                    break
                for t in schlecht:
                    befund[t]["grund"] = befund[t].get("grund") if befund[t].get("grund") not in (
                        "leer", "clipping", "dauer") else None
                    befund[t]["grund"] = befund[t]["grund"] or _grund_lokal(
                        wav_info(neu_ids[t]["pfad"]), tts[t], med, rg)
            for t, x in neu_ids.items():
                b_ = befund[t]
                if engine == "gemini" and pruefer_g and b_.get("grund") == "nachklang" and b_.get("letzt"):
                    pruefer_g.kappen(x["pfad"], b_["letzt"] + 0.12)
                    b_["grund"] = None
                k = f"{lg}/{t}"
                inf = wav_info(x["pfad"])
                m.setzen(k, p["soll"][t], datei=x["pfad"], engine=engine, stimme=info["stimme"],
                         modell=info.get("modell"), adapter=info.get("adapter") if engine == "chatterbox" else None,
                         dauer=inf["dauer"], pruefung=b_.get("grund"), versuche=versuche.get(t, 0),
                         q="mock" if mock.aktiv() else ("fallback" if x.get("fallback") else "neu"),
                         block=x.get("block", False), pause_ms=next((u["pause"] for u in units if u["id"] == t), None))
            m.speichern()
        pruef[lg] = _gate_sprache(g, m, lg, p, fb, n_bl, rg, trocken, probe, kap, nur_lang)
        je_sprache[lg] = {"engine": engine, "stufe": p["stufe"], "stimme": info["stimme"],
                          "gemini_id": info["gemini_id"] if engine == "gemini" else None,
                          "referenz": info["referenz"] if engine == "chatterbox" else None,
                          "adapter": info["adapter"] if engine == "chatterbox" else None, "tempo": p["tempo"],
                          "einheiten": len(units), "vertont": len(neu_ids), "uebernommen": p["uebern"],
                          "fallback_bloecke": len(fb), "bloecke": n_bl, "lexikon": p["n_lex"]}
    if ausfall:
        g.pflicht("lauf", False, ruecksprung="500", text=f"Vertonung abgebrochen – {ausfall}")
    alle = [f"{lg}/{u['id']}" for lg, p in plan.items() for u in p["units"]]
    n_mock = sum(1 for k in alle if (m.get(k) or {}).get("q") == "mock")
    g.mock(n_mock, ruecksprung="500")
    aus_hash = manifest.hash_obj({k: (m.get(k) or {}).get("datei_hash") for k in alle})
    g.metrik("ausgabe_hash", aus_hash)
    g.metrik("je_sprache", je_sprache)
    st0 = status.laden(werk)["stages"].get(STAGE) or {}
    if st0.get("zustand") == "frei" and (st0.get("gate") or {}).get("ergebnis") == "mensch" \
            and (st0.get("metriken") or {}).get("ausgabe_hash") == aus_hash and not probe:
        for x in g.pruefungen:
            if not x["ok"] and x["bei_fehler"] == "mensch" and x["name"] != "kosten":
                x["bei_fehler"] = "hinweis"
                x["text"] += " [Mensch-Freigabe gilt, Audio unveraendert]"
    if not trocken:
        m.meta.update({"je_sprache": je_sprache, "ausgabe_hash": aus_hash, "regler": rg})
        if plan:
            m.speichern()
        manifest.json_atomar(os.path.join(config.work_dir(werk), "500_pruefung.json"), pruef, indent=1)
    g.entscheide(mensch_immer=bool(probe), mensch_grund=f"Probe {probe} Saetze je Sprache – anhoeren "
                 f"(work/500_pruefung.json), dann Volllauf" if probe else None, schreiben=not trocken)
    g.pruef = pruef
    return g


def _median(units, tts, m, lg, neu):
    """Median s/Zeichen der Sprache (Manifest-Dauern + neue WAVs); None bei < 20 Werten."""
    q = []
    for u in units:
        t = tts[u["id"]]
        d = neu.get(u["id"]) if u["id"] in neu else (m.get(f"{lg}/{u['id']}") or {}).get("dauer")
        if len(t) >= 15 and d:
            q.append(d / len(t))
    return statistics.median(q) if len(q) >= 20 else None


def _cb_runde(werk, lg, ids, tts, info, rg, tempo, adir, befund, ersetzen_wenn_besser=False):
    """Ein Modal-Lauf fuer ids -> {tid: {pfad}}; befund aus der Modal-Satzpruefung."""
    tag = time.strftime("%Y%m%d%H%M%S")
    _, daten = cb.paket_bauen(werk, lg, [(t, tts[t]) for t in ids], info["stimme"], info["referenz"],
                              (info["adapter"] or {}).get("name"), ex=float(rg["ex"]), cfg=float(rg["cfg"]), tag=tag)
    if mock.aktiv():
        out = {}
        for t in ids:
            p = os.path.join(adir, f"{t}.wav")
            os.makedirs(adir, exist_ok=True)
            mock.wav(p)
            out[t] = {"pfad": p}
        return out
    mess = cb.modal_lauf(werk, lg, batch=int(rg["batch"]), fp16=bool(rg["fp16"]), tag=tag)
    bef = cb.befund(mess)
    if ersetzen_wenn_besser:
        tmp_dir = os.path.join(config.work_dir(werk), "_500", lg, tag + "_ein")
        neu = cb.einsetzen(werk, lg, daten, tempo, tmp_dir)
        for t, p in neu.items():
            alt = (befund.get(t) or {}).get("grund")
            g_neu = bef.get(t) or _grund_lokal(wav_info(p), tts[t], None, rg)
            if RANG.get(g_neu, 3) < RANG.get(alt, 3):
                os.replace(p, os.path.join(adir, f"{t}.wav"))
                befund[t] = {"grund": g_neu}
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return {t: {"pfad": os.path.join(adir, f"{t}.wav")} for t in ids}
    neu = cb.einsetzen(werk, lg, daten, tempo, adir)
    for t in neu:
        befund[t] = {"grund": bef.get(t)}
    return {t: {"pfad": p} for t, p in neu.items()}


def _gate_sprache(g, m, lg, p, fb, n_bl, rg, trocken, probe, kap, nur_lang):
    units = p["units"]
    fehlt, veraltet, leer, ausf = [], [], [], []
    for u in units:
        k = f"{lg}/{u['id']}"
        e = m.get(k)
        if not e or not m.datei_aktuell(k):
            fehlt.append(u["id"])
        elif e.get("eingang") != p["soll"][u["id"]]:
            veraltet.append(u["id"])
        elif e.get("pruefung") == "leer":
            leer.append(u["id"])
        elif e.get("pruefung"):
            ausf.append(u["id"])
    n = len(units) or 1
    teil = bool(probe or kap or (nur_lang and nur_lang != lg) or trocken)
    if teil:
        g.hinweis(f"abdeckung_{lg}", not fehlt and not veraltet, wert=len(fehlt) + len(veraltet),
                  text=f"{lg}: {len(fehlt) + len(veraltet)} von {len(units)} Saetzen ohne aktuelles Audio "
                       f"({'Probe' if probe else 'Teillauf' if not trocken else 'Probe trocken'})")
    else:
        g.pflicht(f"abdeckung_{lg}", not fehlt, wert=round(1 - len(fehlt) / n, 4), ruecksprung="500",
                  text=f"{lg}: Abdeckung WAV je Audio-Satz {len(units) - len(fehlt)}/{len(units)}"
                       + (f" – fehlt: {', '.join(fehlt[:3])}" if fehlt else ""))
        g.pflicht(f"aktualitaet_{lg}", not veraltet, wert=len(veraltet), ruecksprung="500",
                  text=f"{lg}: Aktualitaet (Sprechtext 400, Stimme casting, Engine/Adapter)"
                       + (f" – veraltet: {', '.join(veraltet[:3])}" if veraltet else ""))
    g.pflicht(f"leer_{lg}", not leer, wert=len(leer), ruecksprung="500",
              text=f"{lg}: leere WAVs = 0" + (f" – {', '.join(leer[:3])}" if leer else ""))
    clip = [t for t in ausf if (m.get(f"{lg}/{t}") or {}).get("pruefung") == "clipping"]
    g.max(f"clipping_{lg}", len(clip), 0, ruecksprung="500")
    g.max(f"auffaellig_{lg}", round(len(ausf) / n, 4), float(rg["auffaellig_max"]), ruecksprung="500")
    if p["engine"] == "gemini" and n_bl:
        g.hinweis(f"fallback_{lg}", len(fb) / n_bl <= FALLBACK_HINWEIS, wert=len(fb),
                  text=f"{lg}: {len(fb)}/{n_bl} Bloecke im Solo-Fallback")
    if p["uebern"]:
        g.hinweis(f"uebernommen_{lg}", False, wert=p["uebern"],
                  text=f"{lg}: {p['uebern']} WAVs aus Altbestand uebernommen (Stimme gleich, Text ungeprueft, 0 $)")
    if p["nicht_uebern"]:
        g.hinweis(f"altbestand_{lg}", False, wert=p["nicht_uebern"][0],
                  text=f"{lg}: {p['nicht_uebern'][0]} Alt-WAVs nicht uebernommen (Altbestand: {p['nicht_uebern'][1]} "
                       f"≠ {p['engine']} {p['info']['stimme']}" + (f" + {(p['info']['adapter'] or {}).get('name')}"
                       if p["engine"] == "chatterbox" and p["info"]["adapter"] else "") + ")")
    if p["alt"]:
        g.hinweis(f"sprechtext_{lg}", False, wert=p["alt"], text=f"{lg}: {p['alt']} Knoten ohne Sprechtext 400 "
                  f"(Altfassung) – Sprechtext-Regeln hier angewandt")
    u_by = {u["id"]: u for u in units}

    def zeile(t):
        e = m.get(f"{lg}/{t}") or {}
        return {"id": t, "text": u_by[t]["text"][:300], "grund": e.get("pruefung"), "datei": e.get("datei"),
                "dauer": e.get("dauer"), "versuche": e.get("versuche")}
    return {"engine": p["engine"], "stimme": p["info"]["stimme"], "auffaellig": [zeile(t) for t in ausf],
            "leer": [zeile(t) for t in leer], "fehlt": fehlt[:200], "veraltet": veraltet[:200],
            "probe": [zeile(t) for t in p["offen"]] if probe else [], "fallback_bloecke": fb}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 500 Vertonung")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--engine", action="append", metavar="LG=gemini|chatterbox|auto")
    ap.add_argument("--tempo", action="append", metavar="[LG=]F")
    for k in ("ex", "cfg", "valley-ratio", "budget", "auffaellig-max", "dauer-min", "dauer-max"):
        ap.add_argument(f"--{k}", type=float)
    for k in ("block-min", "block-ideal", "block-max", "batch", "versuche", "probe"):
        ap.add_argument(f"--{k}", type=int)
    ap.add_argument("--fp16", choices=("an", "aus"))
    ap.add_argument("--satz", action="append")
    ap.add_argument("--kapitel")
    ap.add_argument("--lang")
    ap.add_argument("--neu", action="store_true")
    ap.add_argument("--kosten-freigeben", type=float, metavar="USD")
    ap.add_argument("--trocken", action="store_true")
    a = ap.parse_args(argv)
    wer = a.wer or "pipeline"

    def paare(liste, zahl=False):
        if not liste:
            return None
        out = {}
        for x in liste:
            k, v = x.split("=", 1) if "=" in x else ("*", x)
            out[k] = v if v == "auto" or not zahl else float(v)
        return out
    regler = {"engine": paare(a.engine), "tempo": paare(a.tempo, True), "ex": a.ex, "cfg": a.cfg,
              "block_min": a.block_min, "block_ideal": a.block_ideal, "block_max": a.block_max,
              "valley_ratio": a.valley_ratio, "batch": a.batch, "fp16": {"an": True, "aus": False}.get(a.fp16),
              "budget": a.budget, "auffaellig_max": a.auffaellig_max, "dauer_min": a.dauer_min,
              "dauer_max": a.dauer_max, "versuche": a.versuche}
    try:
        if (a.kosten_freigeben is not None or any(v is not None for v in regler.values())) and not a.trocken:
            from pipeline import s080_mandant
            s080_mandant.darf(a.werk, "entscheiden", wer)
        g = run(a.werk, wer, regler=regler, saetze=a.satz, kapitel=a.kapitel.split(",") if a.kapitel else None,
                nur_lang=a.lang, neu=a.neu, probe=a.probe, kosten_freigeben=a.kosten_freigeben, trocken=a.trocken)
    except gate.GateHalt as e:
        print(e)
        return e.exit_code
    except (ValueError, PermissionError, RuntimeError) as e:
        print(f"[500] Fehler: {e}")
        return 1
    print(g.bericht())
    return gate.EXIT[g.ergebnis["ergebnis"]]


if __name__ == "__main__":
    sys.exit(main())
