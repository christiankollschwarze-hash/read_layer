"""STAGE 501 — Vertonung (Thorsten-Gleis)
Funktion:     Satz-WAVs lokal mit Piper/Thorsten (DE).
Wirkungsweise: Satz fuer Satz ueber ONNX auf der CPU; Resume ueber vorhandene WAVs.
Komponenten:  pipeline/s501_vertonung_thorsten.py, piper
Zulieferer:   s400 Regie (work/400_regie.json)
Abnehmer:     s520 Wortzeiten, s710 Cloud-Export (fassungen/de/audio/<tag>.wav)
(Nomenklatur seit 18.10.2026, Uebersicht: docs/Pipeline_Strang_Matrix.xlsx)

--- Bisherige Beschreibung ---

READ LAYER — Stage 58 (Local-TTS, upps_only-Pfad via Piper/Thorsten)
====================================================================
Input:  authors/<a>/books/<b>/work/400_regie.json   (Tags, Text je Sprache)
        authors/<a>/books/<b>/book.json           (audio_voice_local -- optional)
Output: authors/<a>/books/<b>/fassungen/<lang>/audio/<tag_id>.wav   (GLEICHER Vertrag wie 58/58b)

ZWECK — der schlanke "upps_only"-Pfad (BOARD_audio-strategie.md):
  Fuer Fassungen, die KEIN dramatisiertes Hoerbuch bekommen, sondern nur den
  "Upps"-Stuetzton (Verstaendnishilfe pro Satz). Neutrale Stimmfuehrung ist hier
  didaktisch passend (Werkzeug, nicht Auffuehrung). Lokal, gratis, limit-frei.

BEWUSST NICHT (im Gegensatz zum Gemini-Pfad s500_vertonung_gemini):
  - KEINE Block-Synthese  (Satz -> WAV, einzeln)
  - KEINE Kontext-Regie   (Piper nimmt nur den reinen Satztext)
  - KEIN Forced-Alignment-Schnitt (jeder Satz ist schon sein eigenes WAV)
  - KEINE Doppler-/Mengenpruefung (kein Nachbar-Text, kann nicht ueberlaufen)
Damit ist dieser Pfad DEUTLICH einfacher als der Gemini-Weg -- absichtlich.

STIMME: Piper de_DE-thorsten-high (lokal im read_layer-Root). Ueberschreibbar
  ueber book.json "audio_voice_local" oder --voice.

RESILIENZ: Checkpoint = die WAV-Dateien selbst. Existiert <tag_id>.wav schon
  (und ist nicht leer), wird der Satz uebersprungen (ausser --force). Ein
  abgebrochener Lauf wird beim Neustart fortgesetzt, ohne alles neu zu synthetisieren.

Aufruf (ueber run.py-Weiche, wenn audio_quelle/scope == local):
  python -m pipeline.s501_vertonung_thorsten call-of-the-wild --lang de
Direkt:
  python -m pipeline.s501_vertonung_thorsten call-of-the-wild --lang de --voice de_DE-thorsten-high
  python -m pipeline.s501_vertonung_thorsten call-of-the-wild --lang de --force
"""

import os
import sys
import json
import wave
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config

STAGE = "501"
DEFAULT_VOICE = "de_DE-thorsten-high"
# Sprechtempo: >1.0 = langsamer (deutlichere Wortgrenzen). Fuer den "Upps"-
# Stuetzton bewusst gedehnt, damit einzelne Saetze gut verstaendlich sind.
DEFAULT_LENGTH_SCALE = 1.0   # 10.10.2026: natuerliches Tempo fuers Hoerbuch (vorher 1.3 fuer Upps gedehnt)

# Typen ohne eigenes Audio (reine Struktur). Robust ueber config, Fallback {"p","skip"}.
NO_AUDIO_TYPES = set(getattr(config, "NO_AUDIO_TYPES", {"p", "skip"}))


# ============================================================
# STIMME / MODELL-PFAD
# ============================================================
def _voice_name(book_id: str, override: str = None) -> str:
    """Piper-Stimmenname. Prioritaet: --voice > book.json audio_voice_local > Default."""
    if override:
        return override
    try:
        bj = json.load(open(os.path.join(config.book_dir(book_id), "book.json"), encoding="utf-8"))
        v = (bj.get("audio_voice_local") or "").strip()
        if v:
            return v
    except Exception:
        pass
    return DEFAULT_VOICE


def _find_model(voice_name: str) -> str:
    """Sucht <voice_name>.onnx. Reihenfolge: config.LOCAL_TTS_DIR (falls gesetzt),
    read_layer-Root, dann rekursiv unter dem Root. Gibt den .onnx-Pfad zurueck."""
    candidates = []
    d = getattr(config, "LOCAL_TTS_DIR", None)
    if d:
        candidates.append(os.path.join(d, f"{voice_name}.onnx"))
    root = getattr(config, "BASE_DIR", None) or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    candidates.append(os.path.join(root, f"{voice_name}.onnx"))
    for c in candidates:
        if os.path.exists(c):
            return c
    # Fallback: rekursiv suchen (aber _archiv meiden, damit nicht die Test-Voice greift)
    for dirpath, _dirs, files in os.walk(root):
        if os.sep + "_archiv" in dirpath or os.sep + "archive" in dirpath:
            continue
        if f"{voice_name}.onnx" in files:
            return os.path.join(dirpath, f"{voice_name}.onnx")
    raise FileNotFoundError(
        f"Piper-Modell '{voice_name}.onnx' nicht gefunden (weder in LOCAL_TTS_DIR "
        f"noch im read_layer-Root). Stimme ziehen: python -m piper.download_voices {voice_name}")


# ============================================================
# TAG-AUSWAHL
# ============================================================
def _audio_tags(data: dict, lang: str, chapter: str = None):
    """Sprechbare Tags in Reihenfolge: (tag_id, text) fuer die Zielsprache.
    Ueberspringt NO_AUDIO_TYPES (p/skip) und Tags ohne Text in <lang>."""
    out = []
    for tag_id, entry in data["content"].items():
        if chapter and not tag_id.startswith(chapter):
            continue
        if entry.get("type") in NO_AUDIO_TYPES:
            continue
        txt = str(entry.get(lang, "")).strip()
        if not txt:
            continue
        out.append((tag_id, txt))
    return out


def _ensure_terminal(text: str) -> str:
    """Fehlt ein Satzende, wird fuer die Vertonung ein Punkt ergaenzt (klares
    Pausen-/Prosodie-Signal). 400_regie bleibt unangetastet -- nur der vertonte
    Text bekommt den Punkt."""
    t = text.rstrip()
    if t and t[-1] not in ".!?\u2026\u201c\u201d\"'\u2019":
        return t + "."
    return t


# ============================================================
# HAUPTPROZESS
# ============================================================
def run(book_id: str, lang: str = None, chapter: str = None,
        force: bool = False, voice: str = None, length_scale: float = None):
    lang = lang or (list(config.TARGET_LANGUAGES)[0] if config.TARGET_LANGUAGES else "de")
    if length_scale is None:
        length_scale = DEFAULT_LENGTH_SCALE

    in_path = config.work_path(book_id, "400_regie")
    if not os.path.exists(in_path):
        raise FileNotFoundError(f"{in_path} nicht gefunden — Stage 56 zuerst ausfuehren.")
    data = json.load(open(in_path, encoding="utf-8"))

    voice_name = _voice_name(book_id, voice)
    model_path = _find_model(voice_name)
    print(f"[stage58_local] {book_id} / {lang} | Stimme: {voice_name}")
    print(f"[stage58_local] Modell: {model_path}")

    # Piper laden (einmal -- bleibt im Speicher ueber alle Saetze).
    from piper import PiperVoice
    from piper.config import SynthesisConfig
    piper_voice = PiperVoice.load(model_path)
    syn_config = SynthesisConfig(length_scale=length_scale)
    print(f"[stage58_local] Tempo (length_scale): {length_scale}  (>1.0 = langsamer)")

    audio_dir = os.path.join(config.book_dir(book_id), "fassungen", lang, "audio")
    os.makedirs(audio_dir, exist_ok=True)

    tags = _audio_tags(data, lang, chapter)
    print(f"[stage58_local] {len(tags)} sprechbare Saetze [{lang}]"
          f"{' (Kapitel '+chapter+')' if chapter else ''}")

    n_done, n_skip, n_fail = 0, 0, 0
    for i, (tag_id, text) in enumerate(tags, 1):
        out_path = os.path.join(audio_dir, f"{tag_id}.wav")

        # Checkpoint: nicht-leeres WAV schon da -> ueberspringen.
        if not force and os.path.exists(out_path) and os.path.getsize(out_path) > 44:
            n_skip += 1
            continue

        spoken = _ensure_terminal(text)
        try:
            with wave.open(out_path, "wb") as wf:
                piper_voice.synthesize_wav(spoken, wf, syn_config=syn_config)
            n_done += 1
        except Exception as e:
            n_fail += 1
            print(f"  [FEHLER] {tag_id}: {type(e).__name__}: {e}")
            # Kaputtes/leeres File wegraeumen, damit Resume es erneut versucht.
            try:
                if os.path.exists(out_path) and os.path.getsize(out_path) <= 44:
                    os.remove(out_path)
            except OSError:
                pass
            continue

        if i % 100 == 0 or i == len(tags):
            print(f"  ... {i}/{len(tags)} (neu {n_done}, skip {n_skip}, Fehler {n_fail})")

    print(f"[stage58_local] fertig [{lang}]: {n_done} neu, {n_skip} uebersprungen, "
          f"{n_fail} Fehler -> {audio_dir}")
    return audio_dir


# ============================================================
# CLI
# ============================================================
def main():
    p = argparse.ArgumentParser(description="Stage 58 Local-TTS (Piper, upps_only)")
    p.add_argument("book_id")
    p.add_argument("--lang", default=None)
    p.add_argument("--chapter", default=None)
    p.add_argument("--voice", default=None)
    p.add_argument("--length-scale", type=float, default=None,
                   help=f"Sprechtempo: >1.0 langsamer, <1.0 schneller (Default {DEFAULT_LENGTH_SCALE})")
    p.add_argument("--force", action="store_true")
    a = p.parse_args()
    run(a.book_id, lang=a.lang, chapter=a.chapter, force=a.force,
        voice=a.voice, length_scale=a.length_scale)


if __name__ == "__main__":
    main()
