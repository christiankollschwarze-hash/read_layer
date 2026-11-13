"""
READ LAYER — Kostenzaehler je Werk (10.10.2026; Phase 2 Fundament 5, 01.11.2026)
==============================================================================
Jeder kostenpflichtige Aufruf schreibt eine Zeile nach  <werk>/work/kosten.jsonl:
  Token-Aufrufe (DeepSeek, OpenRouter, Gemini Text/Bild/TTS)   log(modell, anbieter, usage, extra)
  Modal-GPU-Sekunden                                            log_gpu(werk, stage, gpu_s, gpu="L4"|"T4")
  Stueckpreise (Gemini Voice Design u. a.)                      log_stueck(modell, anzahl, werk=, stage=)

Stage-Nr. (Phase 2): jede Zeile traegt die NEUE dreistellige Stage-Nr. aus dem Gate-Katalog
(status.STAGES). Zusaetze wandern in eigene Felder:
  "500_de"            -> stage 500, sprache de
  "345_verschiebung"  -> stage 340, teil 345_verschiebung   (345 Teil von 340, 502 von 500, 525 von 520)
  alte Nummern 11/20/50/55 ... -> 120/600/200/330 ... , stage_alt = alte Nummer
Kontext: run.py bzw. die Stage setzt set_context(werk, stage[, sprache=..]) oder `with kontext(werk, stage):`.
Ohne Kontext: Stage-CLI (Modulname sNNN_) -> Werk aus erstem Argument, sonst READLAYER_BOOK.
Ohne Stage: Rueckfall ueber task (tagger->200, tts->500 ...), stage_quelle = "task"; sonst "?" + Warnung.

Preise: config.PREISE (USD je 1 Mio. Token), config.MODAL_<GPU>_USD_H, config.STUECKPREISE (USD je Stueck).
Fehlt ein Preis: usd = null (Menge wird trotzdem gezaehlt). Token/Sekunden sind die harte Wahrheit.

Auswertung (alte Zeilen werden beim Lesen auf neue Nummern abgebildet):
  python -m pipeline.usage_log <werk>
  python -m pipeline.usage_log --alle            Zeilen ohne zuordenbare Stage je Werk
"""
import os
import re
import sys
import json
import contextlib
import threading
import datetime as dt

_ctx = {"book": None, "stage": None, "extra": {}}
_gewarnt = set()

# Alte Stage-Nummern (bis 18.10.2026) -> Katalog-Nummern
ALT = {"01": "110", "05": "150", "11": "120", "20": "600", "21": "610", "30": "620", "31": "630",
       "40": "640", "50": "200", "51": "210", "52": "300", "53": "310", "54": "320", "54a": "340",
       "55": "330", "56": "400", "57": "410", "57b": "420", "58": "500", "58c": "520", "59": "650",
       "60": "710"}
# Teil-Stages ohne eigenen Status-Schluessel
TEIL = {"345": "340", "501": "500", "502": "500", "525": "520"}
# Werkzeug-Kontexte ohne Nummer
NAMEN = {"aussprache_lexikon": "400", "nachlauf_geschlecht": "600", "pruefaligner": "340",
         "verschiebung": "340", "casting": "410", "voice_design": "410"}
# Rueckfall ueber task, wenn gar keine Stage bekannt ist
TASK = {"modernizer": "120", "tagger": "200", "profiler": "210", "pretranslator": "300",
        "aligner": "340", "caster": "410", "tts": "500", "blurb": "600", "cover": "610"}


def _stages():
    from pipeline import status
    return status.STAGES


def _sprachen():
    try:
        return tuple(getattr(_config(), "SPRACHLISTE", ())) or ("en", "de", "es", "fr", "it")
    except Exception:
        return ("en", "de", "es", "fr", "it")


def stage_norm(stage, task=None):
    """-> (neue Stage-Nr. oder None, Zusatzfelder). Siehe Modulkopf."""
    extra = {}
    s = "" if stage is None else str(stage).strip()
    neu = None
    if s:
        m = re.fullmatch(r"(\d{2,3}[a-z]?)(?:_(.+))?", s)
        if m:
            num, rest = m.groups()
            if num in ALT:
                neu = ALT[num]
            elif num.isdigit() and len(num) == 3:
                neu = TEIL.get(num, num)
                if neu != num and not rest:
                    extra["teil"] = num
            if rest:
                if rest in _sprachen():
                    extra["sprache"] = rest
                else:
                    extra["teil"] = f"{num}_{rest}" if num in TEIL else rest
        elif s in NAMEN:
            neu = NAMEN[s]
            extra["teil"] = s
        if neu is not None and neu not in _stages():
            neu = None
        if neu is not None and neu != s.split("_")[0]:
            extra["stage_alt"] = s
        elif neu is None:
            extra["stage_alt"] = s
    if neu is None and task in TASK:
        neu = TASK[task]
        extra["stage_quelle"] = "task"
    return neu, extra


def set_context(book_id, stage, **extra):
    """Werk + Stage fuer alle folgenden Zeilen. extra z. B. sprache="de", teil="345_verschiebung"."""
    _ctx["book"], _ctx["stage"], _ctx["extra"] = book_id, stage, dict(extra)


@contextlib.contextmanager
def kontext(book_id, stage, **extra):
    """Voruebergehend anderer Kontext (z. B. Voice Design in 410 mit Muster-TTS)."""
    alt = (_ctx["book"], _ctx["stage"], _ctx["extra"])
    set_context(book_id, stage, **extra)
    try:
        yield
    finally:
        _ctx["book"], _ctx["stage"], _ctx["extra"] = alt


def _config():
    from config import config
    return config


def _cli_kontext():
    """Stage direkt per CLI (py -m pipeline.s340_... <werk>) -> Werk aus dem ersten Argument,
    Stage aus dem Modulnamen. Sonst (None, None)."""
    try:
        main = sys.modules.get("__main__")
        name = getattr(getattr(main, "__spec__", None), "name", None) or os.path.basename(sys.argv[0])
        m = re.search(r"\bs(\d{3})_", name)
        stage = m.group(1) if m else None
        cfg = _config()
        for a in sys.argv[1:]:
            if a.startswith("-"):
                continue
            try:
                cfg.author_of(a)
                return a, stage
            except Exception:
                continue
        return None, stage
    except Exception:
        return None, None


def _kontext(book=None, stage=None, task=None):
    """-> (werk, stage_neu, zusatz) aus Argument > gesetztem Kontext > CLI > Umgebung."""
    extra = {}
    if book is None:
        book = _ctx["book"]
    if stage is None:
        stage = _ctx["stage"]
        extra.update(_ctx["extra"])
    if not book or not stage:
        cli_book, cli_stage = _cli_kontext()
        book = book or os.environ.get("READLAYER_BOOK") or cli_book
        stage = stage or cli_stage
    neu, zus = stage_norm(stage, task)
    zus.update(extra)
    if neu is None:
        neu = "?"
        key = (str(stage), task)
        if key not in _gewarnt:
            _gewarnt.add(key)
            print(f"[usage_log] Kosten ohne Stage-Nr. (stage={stage!r}, task={task!r}) -> '?'. "
                  f"set_context(werk, 'NNN') setzen.", file=sys.stderr)
    return book, neu, zus


_lock = threading.Lock()          # parallele Aufrufe (z. B. 340) schreiben nicht ineinander


def _schreiben(book, row):
    path = os.path.join(_config().work_dir(book), "kosten.jsonl")
    with _lock, open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _jetzt():
    return dt.datetime.now(dt.timezone.utc)


def _deepseek_peak(now_utc):
    # Spitzenzeit laut DeepSeek: Mo-Fr 01-04 und 06-10 UTC; sonst halber Preis
    return now_utc.weekday() < 5 and (1 <= now_utc.hour < 4 or 6 <= now_utc.hour < 10)


def _usd(model, t_in, t_cache, t_out, now_utc):
    p = getattr(_config(), "PREISE", {}).get(model)
    if not p:
        return None
    for datum, neu in sorted((p.get("ab") or {}).items()):
        if now_utc.date().isoformat() >= datum:
            p = {**p, **neu}
    g = p.get("gross")
    if g and t_in > g.get("schwelle", 200000):
        p = {**p, **g}
    faktor = 1.0
    if model.startswith("deepseek") and not _deepseek_peak(now_utc):
        faktor = 0.5
    miss = max(0, t_in - t_cache)
    usd = (miss * p.get("in", 0) + t_cache * p.get("cache", p.get("in", 0)) + t_out * p.get("out", 0)) / 1e6
    return round(usd * faktor, 6)


def log(model, provider, usage, extra=None):
    """usage: Antwort-Usage des Anbieters (DeepSeek/OpenRouter 'usage' oder Gemini 'usageMetadata')."""
    try:
        if not usage:
            return
        book, stage, zus = _kontext(task=(extra or {}).get("task"))
        if not book:
            return
        if provider in ("deepseek", "openrouter"):
            t_in = usage.get("prompt_tokens", 0) or 0
            t_cache = usage.get("prompt_cache_hit_tokens", 0) or 0
            t_out = usage.get("completion_tokens", 0) or 0
        else:  # gemini
            t_in = usage.get("promptTokenCount", 0) or 0
            t_cache = usage.get("cachedContentTokenCount", 0) or 0
            t_out = (usage.get("candidatesTokenCount", 0) or 0) + (usage.get("thoughtsTokenCount", 0) or 0)
        now = _jetzt()
        row = {"zeit": now.isoformat(timespec="seconds"), "stage": stage, **zus, "modell": model,
               "in": t_in, "cache": t_cache, "out": t_out, "usd": _usd(model, t_in, t_cache, t_out, now)}
        if extra:
            row.update({k: v for k, v in extra.items() if k != "usd" or v is not None})
        _schreiben(book, row)
    except Exception:
        pass   # Zaehlen darf nie einen Lauf abbrechen


def log_gpu(book_id, stage, gpu_s, gpu="L4", extra=None):
    """Modal-Lauf: GPU-Sekunden x Preis (config.MODAL_<GPU>_USD_H). Gibt USD zurueck (oder None)."""
    try:
        book, st, zus = _kontext(book_id, stage)
        preis = getattr(_config(), f"MODAL_{gpu.upper()}_USD_H", None)
        usd = round(gpu_s / 3600 * preis, 6) if preis else None
        row = {"zeit": _jetzt().isoformat(timespec="seconds"), "stage": st, **zus,
               "modell": f"modal-{gpu.lower()}", "quelle": "modal", "in": 0, "cache": 0, "out": 0,
               "gpu_s": round(gpu_s, 1), "usd": usd}
        if extra:
            row.update(extra)
        _schreiben(book, row)
        return usd
    except Exception as e:
        print(f"[usage_log] Modal-Kosten nicht geschrieben ({type(e).__name__}: {e})", file=sys.stderr)
        return None


def log_stueck(model, anzahl=1, book_id=None, stage=None, extra=None):
    """Stueckpreis-Aufruf (Voice Design u. a.): anzahl x config.STUECKPREISE[model]."""
    try:
        book, st, zus = _kontext(book_id, stage)
        if not book:
            return None
        preis = getattr(_config(), "STUECKPREISE", {}).get(model)
        usd = round(anzahl * preis, 6) if preis is not None else None
        row = {"zeit": _jetzt().isoformat(timespec="seconds"), "stage": st, **zus, "modell": model,
               "in": 0, "cache": 0, "out": 0, "stueck": anzahl, "usd": usd}
        if extra:
            row.update(extra)
        _schreiben(book, row)
        return usd
    except Exception as e:
        print(f"[usage_log] Stueck-Kosten nicht geschrieben ({type(e).__name__}: {e})", file=sys.stderr)
        return None


def zeilen(book_id):
    """Alle Zeilen, Stage auf neue Nummer abgebildet (stage_alt bleibt erhalten)."""
    path = os.path.join(_config().work_dir(book_id), "kosten.jsonl")
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        text = f.read().splitlines()
    for line in text:
        try:
            r = json.loads(line)
        except Exception:
            continue
        neu, zus = stage_norm(r.get("stage"), r.get("task"))
        if r.get("stage") == "?":
            neu = None
        neu = neu or "?"
        if neu != r.get("stage"):
            r = {**zus, **r, "stage": neu}
        if "gpu_s" not in r and "sekunden" in r and str(r.get("modell", "")).startswith("modal"):
            r["gpu_s"] = r["sekunden"]
        out.append(r)
    return out


def summe(book_id, stage=None):
    """{'gesamt': {...}, 'stages': {stage: {...}}, 'modelle': {modell: {...}}}; stage filtert."""
    leer = lambda: {"aufrufe": 0, "in": 0, "cache": 0, "out": 0, "gpu_s": 0.0, "stueck": 0,
                    "usd": 0.0, "ohne_preis": 0}
    out = {"gesamt": leer(), "stages": {}, "modelle": {}}
    for r in zeilen(book_id):
        if stage is not None and r["stage"] != str(stage).zfill(3):
            continue
        for d in (out["gesamt"], out["stages"].setdefault(r["stage"], leer()),
                  out["modelle"].setdefault(r.get("modell") or "?", leer())):
            d["aufrufe"] += 1
            for k in ("in", "cache", "out", "stueck"):
                d[k] += r.get(k, 0) or 0
            d["gpu_s"] += r.get("gpu_s", 0) or 0
            if r.get("usd") is None:
                d["ohne_preis"] += 1
            else:
                d["usd"] += r["usd"]
    for d in [out["gesamt"], *out["stages"].values(), *out["modelle"].values()]:
        d["usd"] = round(d["usd"], 4)
        d["gpu_s"] = round(d["gpu_s"], 1)
    return out


def _alle_werke():
    import glob
    cfg = _config()
    pfade = glob.glob(os.path.join(cfg.AUTHORS_DIR, "*", "books", "*", "work", "kosten.jsonl"))
    pfade += glob.glob(os.path.join(cfg.USERS_DIR, "*", "works", "*", "work", "kosten.jsonl"))
    return [os.path.basename(os.path.dirname(os.path.dirname(p))) for p in pfade]


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if sys.argv[1:2] == ["--alle"]:
        for w in sorted(_alle_werke()):
            s = summe(w)
            ohne = s["stages"].get("?")
            print(f"{w}: {s['gesamt']['usd']:.2f} $" + (f"  | ohne Stage: {ohne['aufrufe']} Zeilen, "
                                                       f"{ohne['usd']:.2f} $" if ohne else ""))
    else:
        print(json.dumps(summe(sys.argv[1]), ensure_ascii=False, indent=1))
