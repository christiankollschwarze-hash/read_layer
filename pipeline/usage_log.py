"""
READ LAYER — Token-/Kostenzaehler je Werk (10.10.2026)
======================================================
Jeder API-Aufruf (DeepSeek, Gemini Text/Bild/TTS) schreibt eine Zeile nach
  authors/<a>/books/<b>/work/kosten.jsonl
mit Stage, Modell, Token (Eingabe / davon Cache / Ausgabe) und geschaetzten USD.

Kontext (Werk + Stage) setzt run.py vor jeder Stage: usage_log.set_context(book_id, stage).
Ohne Kontext (Stage direkt aufgerufen) faellt das Werk auf die Umgebungsvariable
READLAYER_BOOK zurueck; sonst wird nichts geschrieben.

Preise: config.PREISE (USD je 1 Mio. Token). Fehlt ein Modell dort, werden nur Token
gezaehlt (usd = null). Die Token sind die harte Wahrheit, die USD eine Schaetzung.

Auswertung:  python -m pipeline.usage_log <book_id>
"""
import os
import re
import sys
import json
import datetime as dt

_ctx = {"book": None, "stage": None}


def set_context(book_id, stage):
    _ctx["book"], _ctx["stage"] = book_id, stage


def _config():
    from config import config
    return config


def _cli_kontext():
    """24.10.2026 (Smoke #7): Stage direkt per CLI (py -m pipeline.s340_... <werk>) ->
    Werk aus dem ersten Argument, Stage aus dem Modulnamen. Sonst (None, None)."""
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


def _deepseek_peak(now_utc):
    # Spitzenzeit laut DeepSeek: Mo-Fr 01-04 und 06-10 UTC; sonst halber Preis
    return now_utc.weekday() < 5 and (1 <= now_utc.hour < 4 or 6 <= now_utc.hour < 10)


def _usd(model, t_in, t_cache, t_out, now_utc):
    p = getattr(_config(), "PREISE", {}).get(model)
    if not p:
        return None
    # Preiswechsel zu einem Datum ("ab": {"2027-01-01": {...}}) - spaetester gueltiger gewinnt
    for datum, neu in sorted((p.get("ab") or {}).items()):
        if now_utc.date().isoformat() >= datum:
            p = {**p, **neu}
    # Grosse Eingaben teurer (z. B. Gemini 2.5 Pro ueber 200k Token je Aufruf)
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
    """usage: Antwort-Usage des Anbieters (DeepSeek 'usage' oder Gemini 'usageMetadata')."""
    try:
        if not usage:
            return
        book, stage = _ctx["book"], _ctx["stage"]
        if not book or not stage:
            cli_book, cli_stage = _cli_kontext()
            book = book or os.environ.get("READLAYER_BOOK") or cli_book
            stage = stage or cli_stage
        if not book:
            return
        if provider == "deepseek":
            t_in = usage.get("prompt_tokens", 0) or 0
            t_cache = usage.get("prompt_cache_hit_tokens", 0) or 0
            t_out = usage.get("completion_tokens", 0) or 0
        else:  # gemini
            t_in = usage.get("promptTokenCount", 0) or 0
            t_cache = usage.get("cachedContentTokenCount", 0) or 0
            t_out = (usage.get("candidatesTokenCount", 0) or 0) + (usage.get("thoughtsTokenCount", 0) or 0)
        now = dt.datetime.now(dt.timezone.utc)
        row = {
            "zeit": now.isoformat(timespec="seconds"), "stage": stage, "modell": model,
            "in": t_in, "cache": t_cache, "out": t_out, "usd": _usd(model, t_in, t_cache, t_out, now),
        }
        if extra:
            row.update(extra)
        path = os.path.join(_config().work_dir(book), "kosten.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass   # Zaehlen darf nie einen Lauf abbrechen


def log_gpu(book_id, stage, gpu_s, gpu="L4", extra=None):
    """Modal-Lauf in kosten.jsonl: GPU-Sekunden x Preis (config.MODAL_L4_USD_H). Smoke #7 / N-4."""
    try:
        preis = getattr(_config(), f"MODAL_{gpu.upper()}_USD_H", None)
        usd = round(gpu_s / 3600 * preis, 6) if preis else None
        row = {"zeit": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "stage": stage,
               "modell": f"modal-{gpu.lower()}", "quelle": "modal", "in": 0, "cache": 0, "out": 0,
               "gpu_s": round(gpu_s, 1), "usd": usd}
        if extra:
            row.update(extra)
        with open(os.path.join(_config().work_dir(book_id), "kosten.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return usd
    except Exception as e:
        print(f"[usage_log] Modal-Kosten nicht geschrieben ({type(e).__name__}: {e})")
        return None


def summe(book_id):
    """{'gesamt': {...}, 'stages': {stage: {...}}, 'modelle': {modell: {...}}}"""
    path = os.path.join(_config().work_dir(book_id), "kosten.jsonl")
    leer = lambda: {"aufrufe": 0, "in": 0, "cache": 0, "out": 0, "usd": 0.0, "ohne_preis": 0}
    out = {"gesamt": leer(), "stages": {}, "modelle": {}}
    if not os.path.exists(path):
        return out
    for line in open(path, encoding="utf-8"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        for d in (out["gesamt"], out["stages"].setdefault(r.get("stage") or "?", leer()),
                  out["modelle"].setdefault(r.get("modell") or "?", leer())):
            d["aufrufe"] += 1
            d["in"] += r.get("in", 0); d["cache"] += r.get("cache", 0); d["out"] += r.get("out", 0)
            if r.get("usd") is None:
                d["ohne_preis"] += 1
            else:
                d["usd"] += r["usd"]
    for d in [out["gesamt"], *out["stages"].values(), *out["modelle"].values()]:
        d["usd"] = round(d["usd"], 4)
    return out


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    s = summe(sys.argv[1])
    print(json.dumps(s, ensure_ascii=False, indent=1))
