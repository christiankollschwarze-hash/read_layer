"""STAGE 650 — Hoerbuch (DEFEKT, aus der Linie)
Funktion:     Kapitel-Audio zusammenfuegen.
Wirkungsweise: Signatur und Pfade passen nicht zur Pipeline; Neudefinition offen (AP S-3).
Komponenten:  pipeline/s650_hoerbuch.py
Zulieferer:   s500 Vertonung (WAVs)
Abnehmer:     keine (aus run.py genommen)
(Nomenklatur seit 18.10.2026, Uebersicht: docs/Pipeline_Strang_Matrix.xlsx)

--- Bisherige Beschreibung ---

READ LAYER — Stage 08: Assembler
================================
Input:  data/work/<book_id>_stage07.json  (+ Audio-Schnipsel + manifest.json)
Output: data/output/<book_id>/stories/
          <chapter>_<lang>.wav   - zusammengefuegtes Audio je Kapitel & Sprache
          <chapter>_<lang>.txt   - zusammengefuegter Text je Kapitel & Sprache

Fuegt die Einzelschnipsel in Manifest-Reihenfolge zu einer Geschichte zusammen.
Zwischen den Tags wird die dramaturgische Stille (pause_after_ms) eingefuegt —
genau dort wird hoerbar, was die Pausen-Regie taugt.

Rein mechanisch, keine API.
"""

import sys
import os
import json
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config


def _silence_frames(ms: int, rate: int = 24000, width: int = 2, channels: int = 1) -> bytes:
    """Erzeugt Stille als PCM-Frames fuer die angegebene Dauer in ms."""
    n_frames = int(rate * ms / 1000)
    return b"\x00" * (n_frames * width * channels)


def _read_wav_frames(path: str):
    """Liest PCM-Frames + Parameter aus einer WAV-Datei."""
    with wave.open(path, "rb") as w:
        params = w.getparams()
        frames = w.readframes(w.getnframes())
    return frames, params


def _assemble_audio(data, chapter_id, lang, audio_dir, out_path):
    """
    Fuegt alle Audio-Schnipsel eines Kapitels/Sprache + Pausen zusammen.
    Nutzt die echte Tag-Reihenfolge + Pausen direkt aus 400_regie (data),
    NICHT aus dem Manifest (das kann aus einem Mock-Lauf stammen).
    Die WAV-Datei wird nach dem Schema <tag_id>_<lang>.wav im Ordner gesucht.
    """
    rate, width, channels = 24000, 2, 1
    combined = bytearray()
    found_any = False

    pause_layer = data.get("production", {}).get("pause_after_ms", {})

    for tag_id, entry in data["content"].items():
        if not tag_id.startswith(chapter_id):
            continue

        # Audio-Schnipsel anhaengen — Dateiname direkt aus Tag-ID + Sprache
        if entry.get("type") not in config.NO_AUDIO_TYPES:
            fname = f"{tag_id}_{lang}.wav"
            fpath = os.path.join(audio_dir, fname)
            if os.path.exists(fpath):
                try:
                    frames, params = _read_wav_frames(fpath)
                    rate, width, channels = params.framerate, params.sampwidth, params.nchannels
                    combined.extend(frames)
                    found_any = True
                except Exception as e:
                    print(f"      ! uebersprungen (defekt): {fname} ({e})")
            else:
                print(f"      ! fehlt (noch nicht vertont): {fname}")

        # Dramaturgische Pause danach
        pause_ms = pause_layer.get(tag_id, {}).get(lang, 0)
        if pause_ms:
            combined.extend(_silence_frames(pause_ms, rate, width, channels))

    if not found_any:
        return False

    with wave.open(out_path, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(bytes(combined))
    return True


def _assemble_text(data, chapter_id, lang) -> str:
    """Fuegt den Text eines Kapitels/Sprache zu einer Geschichte zusammen."""
    parts = []
    for tag_id, entry in data["content"].items():
        if not tag_id.startswith(chapter_id):
            continue
        typ = entry.get("type")
        text = str(entry.get(lang, "")).strip()
        if typ == "h":
            # Ueberschrift mit Leerzeile abheben
            parts.append(text + "\n")
        elif typ == "p":
            parts.append("")  # Absatzumbruch
        elif text:
            parts.append(text)
    # Saetze mit Leerzeichen, Absaetze mit Zeilenumbruch
    story = ""
    for p in parts:
        if p == "":
            story = story.rstrip() + "\n\n"
        else:
            story += p + " "
    return story.strip() + "\n"


def run(book_id: str) -> dict:
    # Alles aus 400_regie — dem letzten verlaesslichen Live-Stand vor TTS.
    # Enthaelt echte Tag-IDs, echten Text UND die Pausen-Dramaturgie.
    # Das Mock-anfaellige manifest.json wird NICHT mehr gebraucht; die WAVs
    # werden direkt im audio/-Ordner nach <tag_id>_<lang>.wav gesucht.
    in_path = config.work_path(book_id, "400_regie")
    print(f"[stage08] Lese aus: {in_path}")
    with open(in_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    audio_dir = os.path.join(config.OUTPUT_DIR, book_id, "audio")
    stories_dir = os.path.join(config.OUTPUT_DIR, book_id, "stories")
    os.makedirs(stories_dir, exist_ok=True)

    chapters = list(data["meta"]["chapters"].keys())
    langs = config.ALL_LANGUAGES
    is_mock = (config.RUN_MODE == "mock")

    audio_count = 0
    text_count = 0

    for chapter_id in chapters:
        for lang in langs:
            # --- Text immer ---
            story_text = _assemble_text(data, chapter_id, lang)
            txt_path = os.path.join(stories_dir, f"{chapter_id}_{lang}.txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(story_text)
            text_count += 1

            # --- Audio nur im Live-Modus (Mock hat keine echten WAVs) ---
            if not is_mock:
                wav_path = os.path.join(stories_dir, f"{chapter_id}_{lang}.wav")
                ok = _assemble_audio(data, chapter_id, lang, audio_dir, wav_path)
                if ok:
                    audio_count += 1

        print(f"    {chapter_id}: Text {'+ Audio' if not is_mock else '(nur Text, Mock)'} "
              f"in {len(langs)} Sprachen")

    print(f"[stage08] Text-Geschichten: {text_count}")
    if is_mock:
        print(f"[stage08] (Mock-Modus: kein echtes Audio zusammengefuegt)")
    else:
        print(f"[stage08] Audio-Geschichten: {audio_count}")
    print(f"[stage08] Ausgabe: {stories_dir}")
    return data


if __name__ == "__main__":
    book = sys.argv[1] if len(sys.argv) > 1 else "aesop_three_fables"
    run(book)
