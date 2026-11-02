"""READ LAYER - Sprachpruefung auf Modal (Stage 530): Whisper large-v3 (faster-whisper) je Satz-Audio.
Wird aus pipeline/s530_audio_pruefung.py (sprache_modal) ueber `with app.run():` aufgerufen; Rueckfall CPU (lokal).
Je Satz: erkannte Sprache + Wahrscheinlichkeit der Zielsprache (frei) und Abschrift in der Zielsprache (CER).
Eingang je Job: {key, wav (16 kHz mono WAV-Bytes), lg}. GPU-Liste wie fa_modal.py.
"""
import modal


def _modell_laden():
    from huggingface_hub import snapshot_download
    snapshot_download("Systran/faster-whisper-large-v3", local_dir="/modell")


app = modal.App("readlayer-sprache530")
image = (
    modal.Image.from_registry("nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04", add_python="3.11")
    .apt_install("ffmpeg")
    .pip_install("faster-whisper==1.1.1", "huggingface_hub")
    .run_function(_modell_laden)
)


@app.function(image=image, gpu=["L4", "A10G", "T4"], timeout=3600)
def pruefen(chunk: list) -> dict:
    import io
    from faster_whisper import WhisperModel
    from faster_whisper.audio import decode_audio
    m = WhisperModel("/modell", device="cuda", compute_type="float16")
    out = {}
    for j in chunk:
        try:
            a = decode_audio(io.BytesIO(j["wav"]), sampling_rate=16000)
            segs, info = m.transcribe(a, language=None, beam_size=1, without_timestamps=True,
                                      condition_on_previous_text=False, vad_filter=False)
            list(segs)
            probs = dict(info.all_language_probs or [])
            segs, _ = m.transcribe(a, language=j["lg"], beam_size=1, without_timestamps=True,
                                   condition_on_previous_text=False, vad_filter=False)
            out[j["key"]] = {"top": info.language, "p": round(float(probs.get(j["lg"], 0.0)), 4),
                             "text": " ".join(s.text.strip() for s in segs), "dauer": round(len(a) / 16000, 2)}
        except Exception as e:
            out[j["key"]] = {"fehler": f"{type(e).__name__}: {e}"[:200]}
    return out
