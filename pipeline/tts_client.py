"""
READ LAYER — TTS-Client (eine Quelle fuer ALLE Sprachsynthese-Calls)
====================================================================
Seit 08.10.2026: Gemini 3.8 TTS (gemini-3.8-flash-tts / -flash-lite-tts).

Zwei Backends (config.TTS_BACKEND):
  "gemini_api" = NEU. Gemini-API, Interactions-Endpoint, Key = GEMINI_API_KEY.
                 Die 3.8-Modelle gibt es NUR hier (nicht in Cloud Text-to-Speech).
  "cloud_tts"  = ALT. Google Cloud Text-to-Speech (SynthesisInput.prompt),
                 Service-Account via GOOGLE_APPLICATION_CREDENTIALS.
                 Nur noch fuer gemini-2.5-*-tts / gemini-3.1-flash-tts-preview.

Was sich bei 3.8 in der STEUERUNG aendert (Google-Doku, Migration):
  - 'text' ist ein WORTGETREUES Transkript. Keine Regie in den Text.
  - Regie gehoert in speech_metadata.style -- KURZ ("calm narration, slow pace").
    Lange Regie-/Persona-Bloecke und Meta-Anweisungen ("do not repeat",
    "keep the voice steady") ERHOEHEN laut Doku das Abdriften der Stimme.
  - Keine festen Merkmale (Alter, Geschlecht, Akzent) in style -> Stimme waehlen.
  - Inline-Tags in SPITZEN Klammern, englisch: <short pause>, <long pause>, <sigh> ...
    (Cloud-TTS/2.5 nutzte eckige Klammern [short pause]).
  - Keine Sprachangabe mehr: Sprache wird automatisch erkannt.
  - Unary-Antwort ist bereits WAV (RIFF, 24 kHz, mono, 16 bit) -- kein eigener
    WAV-Header mehr noetig.

Oeffentlich:
  synthesize_wav(text, style, out_path, voice, lang_code)  -> schreibt WAV 24 kHz
  synthesize_bytes(text, style, voice, lang_code, fmt)     -> bytes (wav | l16 | mp3*)
  is_gemini_api()                                          -> bool
  (*mp3 nur im Cloud-Backend; im Gemini-Backend -> WAV, Umwandlung beim Aufrufer)
"""

import os
import sys
import time
import base64

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config

INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
SAMPLE_RATE = 24000
RETRIES = 4


class QuotaError(RuntimeError):
    """429 auch nach allen Wiederholungen: Tages-/Minutenkontingent erschoepft.
    Stage 58 bricht dann ab, statt in den Einzelsatz-Fallback zu laufen
    (der wuerde nur weitere Abrufe gegen das leere Kontingent verbrennen)."""


def backend() -> str:
    return getattr(config, "TTS_BACKEND", "gemini_api")


def is_gemini_api() -> bool:
    return backend() == "gemini_api"


def model() -> str:
    return config.MODELS.get("tts", "gemini-3.8-flash-tts")


# ============================================================
# GEMINI-API (3.8) -- Interactions-Endpoint
# ============================================================
def _find_audio_b64(obj):
    """Sucht das (letzte) Audio-Element in der Interactions-Antwort.
    Robust gegen beide Formen: output_audio.data  ODER  steps[].content[] type=audio."""
    if isinstance(obj, dict):
        oa = obj.get("output_audio")
        if isinstance(oa, dict) and oa.get("data"):
            return oa["data"]
        found = None
        steps = obj.get("steps")
        if isinstance(steps, list):
            for st in steps:
                for c in (st.get("content") or []) if isinstance(st, dict) else []:
                    if isinstance(c, dict) and c.get("type") == "audio" and c.get("data"):
                        found = c["data"]
            if found:
                return found
        for v in obj.values():
            r = _find_audio_b64(v)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find_audio_b64(v)
            if r:
                return r
    return None


def _gemini_payload(text: str, style: str, voice: str, mime: str) -> dict:
    meta = {"type": "speech_metadata"}
    if style and style.strip():
        meta["style"] = style.strip()
    item = {"type": "text", "text": text}
    if len(meta) > 1:
        item["annotations"] = [meta]
    rf = {"type": "audio", "mime_type": mime, "sample_rate": SAMPLE_RATE}
    return {
        "model": model(),
        "input": [{"type": "user_input", "content": [item]}],
        "response_format": rf,
        "generation_config": {"speech_config": [{"voice": voice or config.TTS_VOICE}]},
    }


def _gemini_call(text: str, style: str, voice: str, mime: str) -> bytes:
    import requests
    if not config.GEMINI_API_KEY:
        raise EnvironmentError("GEMINI_API_KEY fehlt (live-Modus).")
    payload = _gemini_payload(text, style, voice, mime)
    last = None
    for attempt in range(RETRIES):
        resp = requests.post(
            INTERACTIONS_URL,
            headers={"x-goog-api-key": config.GEMINI_API_KEY,
                     "Content-Type": "application/json"},
            json=payload, timeout=300,
        )
        if resp.status_code == 429:
            last = f"429 Rate-Limit (Versuch {attempt+1}/{RETRIES}): {resp.text[:300]}"
            time.sleep(30 * (attempt + 1))
            continue
        if resp.status_code in (500, 502, 503, 504):
            last = f"{resp.status_code} (Versuch {attempt+1}/{RETRIES})"
            time.sleep(3 * (attempt + 1))
            continue
        if resp.status_code >= 400:
            raise RuntimeError(f"TTS {resp.status_code}: {resp.text[:400]}")
        js = resp.json()
        b64 = _find_audio_b64(js)
        if not b64:
            # "nur Text statt Audio" -> wie bisher als Fehler -> Retry beim Aufrufer
            raise RuntimeError("TTS-Antwort ohne Audio")
        audio = base64.b64decode(b64)
        try:
            # Interactions-API liefert keine usageMetadata -> Token aus Audiolaenge rechnen
            # (25 Audio-Token je Sekunde, 24 kHz 16 bit mono = 48.000 Byte/s; Text ~4 Zeichen je Token)
            from pipeline import usage_log
            u = js.get("usageMetadata") or js.get("usage") or {}
            if not (u.get("candidatesTokenCount") or u.get("output_tokens")):
                u = {"promptTokenCount": (len(text) + len(style or "")) // 4 + 1,
                     "candidatesTokenCount": round(len(audio) / 48000 * 25)}
            usage_log.log(model(), "gemini", u, {"task": "tts", "zeichen": len(text),
                                                 "sek": round(len(audio) / 48000, 1)})
        except Exception:
            pass
        return audio
    if last and last.startswith("429"):
        raise QuotaError(f"TTS-Kontingent erschoepft: {last}")
    raise RuntimeError(f"TTS nach {RETRIES} Versuchen fehlgeschlagen: {last}")


# ============================================================
# FAL.AI (Ueberlauf) -- gleiches Modell google/gemini-3.8-flash-tts
# ============================================================
FAL_URL = "https://fal.run/google/gemini-3.8-flash-tts"
_overflow_active = False


def _normalize_wav(data: bytes) -> bytes:
    """Sichert den Pipeline-Vertrag: WAV, 16 bit, mono, 24 kHz."""
    import io, wave, audioop
    with wave.open(io.BytesIO(data), "rb") as w:
        ch, sw, sr, frames = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.readframes(w.getnframes())
    if sw != 2:
        frames = audioop.lin2lin(frames, sw, 2); sw = 2
    if ch == 2:
        frames = audioop.tomono(frames, 2, 0.5, 0.5); ch = 1
    if sr != SAMPLE_RATE:
        frames, _ = audioop.ratecv(frames, 2, 1, sr, SAMPLE_RATE, None)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SAMPLE_RATE); w.writeframes(frames)
    return out.getvalue()


def _fal_call(text: str, style: str, voice: str) -> bytes:
    import requests
    key = getattr(config, "FAL_KEY", "")
    if not key:
        raise EnvironmentError("FAL_KEY fehlt (.env).")
    payload = {"prompt": text, "voice": voice or config.TTS_VOICE}
    if style and style.strip():
        payload["style_instructions"] = style.strip()
    last = None
    for attempt in range(RETRIES):
        resp = requests.post(FAL_URL, headers={"Authorization": f"Key {key}",
                                               "Content-Type": "application/json"},
                             json=payload, timeout=600)
        if resp.status_code in (429, 500, 502, 503, 504):
            last = f"{resp.status_code}: {resp.text[:300]}"
            time.sleep(10 * (attempt + 1))
            continue
        if resp.status_code >= 400:
            raise RuntimeError(f"fal {resp.status_code}: {resp.text[:400]}")
        url = ((resp.json() or {}).get("audio") or {}).get("url")
        if not url:
            raise RuntimeError(f"fal-Antwort ohne Audio: {resp.text[:300]}")
        audio = requests.get(url, timeout=300)
        audio.raise_for_status()
        return _normalize_wav(audio.content)
    raise RuntimeError(f"fal nach {RETRIES} Versuchen fehlgeschlagen: {last}")


# ============================================================
# CLOUD TEXT-TO-SPEECH (alt, 2.5 / 3.1-preview)
# ============================================================
_cloud_client = None


def _cloud_call(text: str, style: str, voice: str, lang_code: str, fmt: str) -> bytes:
    global _cloud_client
    from google.cloud import texttospeech
    if _cloud_client is None:
        if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            print("WARN: GOOGLE_APPLICATION_CREDENTIALS nicht gesetzt (live-Modus).")
        _cloud_client = texttospeech.TextToSpeechClient()
    si = texttospeech.SynthesisInput(text=text, prompt=style or None)
    vp = texttospeech.VoiceSelectionParams(
        language_code=lang_code or "en-US",
        name=voice or config.TTS_VOICE,
        model_name=model(),
    )
    enc = texttospeech.AudioEncoding.MP3 if fmt == "mp3" else texttospeech.AudioEncoding.LINEAR16
    resp = _cloud_client.synthesize_speech(
        input=si, voice=vp, audio_config=texttospeech.AudioConfig(audio_encoding=enc))
    return resp.audio_content


# ============================================================
# OEFFENTLICH
# ============================================================
def synthesize_bytes(text: str, style: str = "", voice: str = None,
                     lang_code: str = None, fmt: str = "wav") -> bytes:
    """fmt: 'wav' (24 kHz mono 16 bit mit Header) | 'l16' (roh-PCM) | 'mp3' (nur cloud_tts)."""
    global _overflow_active
    if backend() == "fal" or (is_gemini_api() and _overflow_active):
        data = _fal_call(text, style, voice)
        return _strip_wav(data) if fmt == "l16" else data
    if is_gemini_api():
        mime = "audio/l16" if fmt == "l16" else "audio/wav"
        try:
            # 12.10.2026: Sprache festigen. Der Sprachcode ging bisher nicht an Gemini -> designte
            # (englisch entworfene) Stimmen kippten im DE gelegentlich ins Englische/Franzoesische.
            fest = getattr(config, "TTS_SPRACH_STIL", {}).get((lang_code or "")[:2], "")
            if fest:
                style = f"{fest} {style}".strip() if style else fest
            return _gemini_call(text, style, voice, mime)
        except QuotaError as e:
            # Designte Stimmen (voice_...) gibt es nur bei Google -> kein fal-Ueberlauf (12.10.2026)
            if str(voice or "").startswith("voice_"):
                raise
            if getattr(config, "TTS_OVERFLOW", "") == "fal" and getattr(config, "FAL_KEY", ""):
                print(f"[tts] Google-Kontingent erschoepft -> Ueberlauf auf fal.ai fuer den Rest des Laufs ({e})")
                _overflow_active = True
                data = _fal_call(text, style, voice)
                return _strip_wav(data) if fmt == "l16" else data
            raise
    return _cloud_call(text, style, voice, lang_code, fmt)


def _strip_wav(data: bytes) -> bytes:
    i = data.find(b"data")
    return data[i + 8:] if data[:4] == b"RIFF" and i >= 0 else data


def synthesize_wav(text: str, style: str, out_path: str, voice: str = None,
                   lang_code: str = None) -> None:
    """Schreibt eine WAV-Datei (LINEAR16, 24 kHz). Wirft bei Fehler."""
    data = synthesize_bytes(text, style, voice, lang_code, fmt="wav")
    with open(out_path, "wb") as f:
        f.write(data)
