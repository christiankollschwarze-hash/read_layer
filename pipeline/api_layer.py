"""
READ LAYER — API-Layer
======================
Einzige Stelle, an der mit Modellen gesprochen wird.
Alle Pipeline-Module rufen NUR diese Funktionen auf — nie direkt eine API.

Zwei Modi (gesteuert ueber config.RUN_MODE):
  "mock" = strukturtreue Platzhalter-Antworten. Kein Key, keine Kosten.
           Die Mocks sind bewusst DUMM: korrekte Form, Platzhalter-Inhalt.
           So testen wir Mechanik (Struktur, Fluss), nicht Qualitaet.
  "live" = echte API-Calls (DeepSeek / Gemini). Keys noetig.

Beim Wechsel auf "live" aendert sich KEIN Pipeline-Code — nur config.RUN_MODE.
"""

import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config


# ============================================================
# OEFFENTLICHE SCHNITTSTELLE
# ============================================================

def call_model(task: str, prompt: str, **kwargs) -> str:
    """
    Zentraler Einstiegspunkt. 'task' bestimmt via config.MODELS das Modell.
    Gibt immer einen String zurueck (oft JSON-Text, den der Aufrufer parst).
    """
    if config.RUN_MODE == "mock":
        return _mock_response(task, prompt, **kwargs)
    elif config.RUN_MODE == "live":
        return _live_response(task, prompt, **kwargs)
    else:
        raise ValueError(f"Unbekannter RUN_MODE: {config.RUN_MODE}")


# ============================================================
# MOCK-MODUS — strukturtreu, aber bewusst dumm
# ============================================================

def _mock_response(task: str, prompt: str, **kwargs) -> str:
    """
    Liefert vorhersehbare Platzhalter in der RICHTIGEN Form.
    Niemals 'kluge' Inhalte — sonst testen wir eine Pipeline unter
    unrealistisch guten Bedingungen.
    """
    if task == "translator":
        # Erwartet: Liste von Saetzen als JSON rein, uebersetzte Liste raus
        lang = kwargs.get("target_lang", "xx")
        sentences = kwargs.get("sentences", [])
        translated = [f"[{lang.upper()}] {s}" for s in sentences]
        return json.dumps({"translations": translated}, ensure_ascii=False)

    if task == "pretranslator":
        lang = kwargs.get("target_lang", "xx")
        return f"[PRETRANSLATION {lang.upper()}] (mock context translation of chapter)"

    if task == "profiler":
        # Minimal-Profil in korrekter Struktur
        return json.dumps({
            "style":        {"tone": "mock-tone", "register": "mock-register"},
            "characters":   {},
            "untranslated": {},
            "glossary":     {},
            "idioms":       {},
        }, ensure_ascii=False)

    if task == "validator":
        # Immer bestanden im Mock — Schwellen-Logik wird trotzdem durchlaufen
        return json.dumps({"score": 95, "issues": []}, ensure_ascii=False)

    if task == "ssml":
        text = kwargs.get("text", "")
        return f"<speak>{text}</speak>"

    if task == "tts":
        # Kein echtes Audio — Platzhalter-Marker
        return "MOCK_AUDIO_BYTES"

    if task == "aligner":
        # Strukturtreuer Mock fuer Stage 54a: bindet pro Satz den ganzen EN- an
        # den ganzen DE-Text (ein bid). Bewusst "dumm" — testet die Pipeline,
        # nicht die Alignmentguete.
        out = {}
        for m in re.finditer(r'"(c\d+_\d+_\w+)": \{"en": (".*?"), "de": (".*?")\}', prompt):
            tid = m.group(1)
            try:
                en = json.loads(m.group(2)); de = json.loads(m.group(3))
            except Exception:
                continue
            out[tid] = [{"bid": "01", "en": en, "de": de}]
        return json.dumps(out, ensure_ascii=False)

    # Fallback
    return f"[MOCK:{task}]"


# ============================================================
# LIVE-MODUS — echte APIs (erst bei dir lokal mit Keys aktiv)
# ============================================================

def _post_robust(url, **kw):
    """requests.post mit Wiederholung bei Netz-/SSL-Abbruechen und 429/5xx (11.10.2026:
    SSLEOFError bei vielen parallelen Cockpit-Jobs)."""
    import time
    import requests
    kw.setdefault("timeout", 600)
    letzte = None
    for versuch in range(6):
        try:
            r = requests.post(url, **kw)
            if r.status_code in (429, 500, 502, 503, 504) and versuch < 5:
                letzte = f"HTTP {r.status_code}"
            else:
                return r
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            letzte = e
            if versuch == 5:
                raise
        pause = 10 * (versuch + 1)
        print(f"    [api] {str(letzte)[:120]} -> neuer Versuch in {pause}s ({versuch + 1}/6)")
        time.sleep(pause)
    return r


def _live_response(task: str, prompt: str, **kwargs) -> str:
    """
    Echte API-Calls. Wird hier in der Mock-Umgebung nicht ausgefuehrt,
    ist aber vollstaendig verdrahtet fuer den lokalen Lauf.
    """
    import requests

    model = config.MODELS[task]

    # --- DeepSeek ---
    if model.startswith("deepseek"):
        if not config.DEEPSEEK_API_KEY:
            raise EnvironmentError("DEEPSEEK_API_KEY fehlt (live-Modus).")
        resp = _post_robust(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {config.DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": kwargs.get("temperature", 0.1),
                "max_tokens": min(kwargs.get("max_tokens", 8192), getattr(config, "DEEPSEEK_MAX_OUT", 16000)),
                # v4-Modelle (deepseek-v4-flash/-pro) denken PER DEFAULT nach
                # (thinking=enabled, reasoning_effort=high) - Reasoning laeuft
                # ins reasoning_content-Feld und kann bei laengeren/komplexeren
                # Prompts das gesamte max_tokens-Budget aufbrauchen, sodass
                # "content" leer bleibt (17.07. an Stage 54a gefunden: trivialer
                # Test-Prompt lief durch, echter 20-Satz-Batch kam leer zurueck).
                # Alle bisherigen Aufgaben (Uebersetzen, Alignment, Profiling)
                # sind strukturierte Extraktion, kein Reasoning noetig -> global
                # abschalten. Nebeneffekt: temperature greift dann auch wieder
                # (wird in Thinking-Mode laut Doku ignoriert). Ueberschreibbar
                # via thinking=... kwarg, falls eine kuenftige Aufgabe doch
                # Reasoning brauchen sollte.
                "thinking": kwargs.get("thinking", {"type": "disabled"}),
            },
        )
        resp.raise_for_status()
        js = resp.json()
        from pipeline import usage_log
        usage_log.log(model, "deepseek", js.get("usage"), {"task": task})
        content = js["choices"][0]["message"]["content"]
        return (content or "").strip()

    # --- OpenRouter (12.10.2026: Modellvergleiche ohne Vorab-Kauf; Modellname "or/<anbieter>/<modell>") ---
    if model.startswith("or/"):
        if not getattr(config, "OPENROUTER_API_KEY", ""):
            raise EnvironmentError("OPENROUTER_API_KEY fehlt (.env).")
        resp = _post_robust(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
                     "Content-Type": "application/json",
                     "X-Title": "READ LAYER"},
            json={
                "model": model[3:],
                "messages": [{"role": "user", "content": prompt}],
                "temperature": kwargs.get("temperature", 0.1),
                "max_tokens": min(kwargs.get("max_tokens", 8192), getattr(config, "OPENROUTER_MAX_OUT", 32000)),
                "reasoning": kwargs.get("reasoning", {"enabled": False}),   # Denk-Token aus (Kostenfalle)
                "usage": {"include": True},                                 # echte Kosten in USD zurueck
            },
        )
        resp.raise_for_status()
        js = resp.json()
        from pipeline import usage_log
        u = js.get("usage") or {}
        usage_log.log(model, "deepseek", u, {"task": task, "usd": u.get("cost"),
                                             "anbieter": js.get("provider")})
        content = js["choices"][0]["message"]["content"]
        return (content or "").strip()

    # --- Gemini ---
    if model.startswith("gemini"):
        if not config.GEMINI_API_KEY:
            raise EnvironmentError("GEMINI_API_KEY fehlt (live-Modus).")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        resp = _post_robust(
            url,
            headers={
                "X-goog-api-key": config.GEMINI_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": kwargs.get("temperature", 0.1),
                    "maxOutputTokens": kwargs.get("max_tokens", 65000),
                },
            },
        )
        resp.raise_for_status()
        js = resp.json()
        from pipeline import usage_log
        usage_log.log(model, "gemini", js.get("usageMetadata"), {"task": task})
        return js["candidates"][0]["content"]["parts"][0]["text"].strip()

    raise ValueError(f"Unbekanntes Modell: {model}")


# ============================================================
# TTS — eigener Pfad (anderes Antwortformat: base64-Audio)
# ============================================================

def call_tts(text: str, lang: str, style: str = "", voice: str = None) -> bytes:
    """
    Sprachsynthese. Gibt rohe PCM-Audio-Bytes zurueck (16-bit, 24kHz, mono)
    -- Vertrag unveraendert. Mock: Platzhalter-Bytes.
    Live (seit 08.10.2026): ueber pipeline/tts_client (Gemini 3.8, Interactions,
    mime audio/l16 = headerloses PCM). Beim alten Backend 'cloud_tts' kommt
    LINEAR16 mit WAV-Header -> Header wird hier abgeschnitten.
    """
    if config.RUN_MODE == "mock":
        return f"MOCK_AUDIO | lang={lang} | {text}".encode("utf-8")
    from pipeline import tts_client
    data = tts_client.synthesize_bytes(text, style, voice, lang, fmt="l16")
    if data[:4] == b"RIFF":
        i = data.find(b"data")
        if i >= 0:
            data = data[i + 8:]
    return data


# ============================================================
# JSON-HELFER (von mehreren Modulen genutzt)
# ============================================================

def _strip_fences(s: str) -> str:
    """Entfernt ```json ... ``` Code-Fences."""
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
    if s.endswith("```"):
        s = s.rsplit("```", 1)[0]
    return s.strip()


def _extract_json_block(s: str) -> str:
    """Schneidet alles vor dem ersten { bzw. [ und nach der passenden
    schliessenden Klammer weg (Modell-Geschwaetz drumherum entfernen)."""
    starts = [i for i in (s.find("{"), s.find("[")) if i != -1]
    if not starts:
        return s
    start = min(starts)
    open_ch = s[start]
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == open_ch:
                depth += 1
            elif c == close_ch:
                depth -= 1
                if depth == 0:
                    return s[start:i+1]
    return s[start:]  # unausgewogen -> Rest (wird ggf. repariert)


def _repair_common(s: str) -> str:
    """Haeufige JSON-Macken weichmachen:
    - // und /* */ Kommentare raus
    - trailing commas vor } oder ]
    - echte Zeilenumbrueche INNERHALB von Strings -> Leerzeichen
    """
    # Kommentare
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.DOTALL)
    s = re.sub(r"(?m)//.*$", "", s)
    # Newlines in Strings glaetten (Zeichen-fuer-Zeichen, str-bewusst)
    out = []
    in_str = False
    esc = False
    for c in s:
        if in_str:
            if esc:
                out.append(c); esc = False; continue
            if c == "\\":
                out.append(c); esc = True; continue
            if c == '"':
                in_str = False; out.append(c); continue
            if c in "\n\r":
                out.append(" "); continue
            out.append(c)
        else:
            if c == '"':
                in_str = True
            out.append(c)
    s = "".join(out)
    # trailing commas
    s = re.sub(r",\s*([}\]])", r"\1", s)
    return s


def parse_json(raw: str) -> dict:
    """Robustes JSON-Parsing fuer Modell-Antworten. Mehrstufig: erst schnell,
    dann zunehmend reparierend. Faengt Code-Fences, Geschwaetz drumherum,
    Kommentare, trailing commas und Zeilenumbrueche in Strings ab.
    Wirft nur, wenn wirklich nichts mehr geht."""
    if raw is None:
        raise ValueError("parse_json: leere Antwort")
    s = _strip_fences(raw)
    # Versuch 1: direkt
    try:
        return json.loads(s)
    except Exception:
        pass
    # Versuch 2: nur den {...}/[...]-Block
    block = _extract_json_block(s)
    try:
        return json.loads(block)
    except Exception:
        pass
    # Versuch 3: gaengige Macken reparieren
    try:
        return json.loads(_repair_common(block))
    except Exception as e:
        snippet = s[:200].replace("\n", " ")
        raise ValueError(f"parse_json: nicht parsebar ({e}); Anfang: {snippet}")
