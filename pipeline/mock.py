"""Phase 2, Fundament 5: Mock-Erkennung (01.11.2026).

RUN_MODE "mock" (config.RUN_MODE) liefert strukturtreue Platzhalter ohne Kosten. Sie duerfen nie in
einen Live-Lauf rutschen. Leitlinie Katalog: Mock erkennen, im Live-Lauf Stopp.

  mock.aktiv()                    True im Mock-Lauf
  mock.modus()                    "mock" | "live"  (Gate schreibt es als Metrik "modus" je Stage/Teil)
  mock.ist_text(s) / ist_obj(o)   Platzhaltertexte der Mocks ([MOCK:..], mock-tone, ...)
  mock.ist_bytes(b) / ist_datei(p)  Mock-Audio (MOCK..., MOCK_AUDIO, WAV mit Marker READLAYER-MOCK,
                                  Alt-Mock aus s500: 0,1 s Stille 24 kHz)
  mock.wav(pfad)                  Mock-WAV mit Marker schreiben (statt stiller Datei ohne Kennung)
  mock.zaehlen(pfade)             -> (anzahl, beispiele)
  g.mock(anzahl, beispiele)       Gate-Pruefung: live -> Stopp bei anzahl > 0, mock -> Hinweis
Kette: gate.vorgaenger_frei stoppt im Live-Lauf, wenn ein Vorgaenger (oder ein Teil davon) im
Mock-Lauf erzeugt wurde (Metrik modus = mock).
"""
import os
import re
import struct
import wave

MARKER = b"READLAYER-MOCK"
_TEXT = re.compile(r"\[MOCK[:\]]|\[PRETRANSLATION [A-Z]{2}\] \(mock|\bmock-(?:tone|register)\b|"
                   r"MOCK_AUDIO|\(mock\b|Mock-Essenz|Mock-Zitat")
_ALT_STILLE = 2400 * 2          # s500 _write_mock_wav bis 01.11.2026: 2400 Frames Null, 24 kHz mono 16 bit


def _config():
    from config import config
    return config


def modus():
    return "mock" if getattr(_config(), "RUN_MODE", "live") == "mock" else "live"


def aktiv():
    return modus() == "mock"


def ist_text(s):
    return isinstance(s, str) and bool(_TEXT.search(s))


def ist_obj(o, _tiefe=0):
    """Rekursiv: irgendein String im Objekt ist ein Mock-Platzhalter."""
    if _tiefe > 50:
        return False
    if isinstance(o, str):
        return ist_text(o)
    if isinstance(o, dict):
        return any(ist_obj(v, _tiefe + 1) for v in o.values())
    if isinstance(o, (list, tuple)):
        return any(ist_obj(v, _tiefe + 1) for v in o)
    return False


def ist_bytes(b):
    if not b:
        return False
    kopf = bytes(b[:512])
    if kopf.startswith(b"MOCK") or MARKER in kopf or MARKER in bytes(b[-512:]):
        return True
    if kopf.startswith(b"RIFF") and len(b) <= 44 + _ALT_STILLE + 64:
        try:
            import io
            with wave.open(io.BytesIO(bytes(b))) as w:
                daten = w.readframes(w.getnframes())
                return (w.getframerate() == 24000 and w.getnchannels() == 1
                        and len(daten) == _ALT_STILLE and not any(daten))
        except Exception:
            return False
    return False


def ist_datei(pfad):
    try:
        groesse = os.path.getsize(pfad)
        with open(pfad, "rb") as f:
            kopf = f.read(512)
            if groesse > 1024:
                f.seek(-512, os.SEEK_END)
                kopf_ende = f.read(512)
            else:
                kopf_ende = b""
        if groesse <= 44 + _ALT_STILLE + 64:
            with open(pfad, "rb") as f:
                return ist_bytes(f.read())
        return kopf.startswith(b"MOCK") or MARKER in kopf or MARKER in kopf_ende
    except OSError:
        return False


def wav(pfad, frames=2400, rate=24000):
    """Mock-WAV (Stille) mit LIST/INFO-Chunk ISFT=READLAYER-MOCK – gueltig fuer wave/ffmpeg, erkennbar."""
    daten = b"\x00\x00" * frames
    isft = MARKER + b"\x00"
    if len(isft) % 2:
        isft += b"\x00"
    info = b"INFO" + b"ISFT" + struct.pack("<I", len(isft)) + isft
    fmt = struct.pack("<HHIIHH", 1, 1, rate, rate * 2, 2, 16)
    chunks = (b"fmt " + struct.pack("<I", len(fmt)) + fmt
              + b"LIST" + struct.pack("<I", len(info)) + info
              + b"data" + struct.pack("<I", len(daten)) + daten)
    with open(pfad, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WAVE" + chunks)


def zaehlen(pfade, max_beispiele=5):
    n, bsp = 0, []
    for p in pfade:
        if ist_datei(p):
            n += 1
            if len(bsp) < max_beispiele:
                bsp.append(os.path.basename(p))
    return n, bsp
