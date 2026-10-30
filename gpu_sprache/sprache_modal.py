"""READ LAYER - Sprachpruefung auf Modal: Whisper large-v3 (faster-whisper) je Satz-Audio.
Aufruf (start_sprachpruefung.bat):  py -3.11 -m modal run gpu_sprache/sprache_modal.py --paket <werk>_<lg>
Je Satz: Sprachwahrscheinlichkeiten (de/en/fr ...), freie Abschrift, bei anderer Sprache zusaetzlich Abschrift in der
Zielsprache (AP 57: immer, mit Wort-Konfidenz 'woerter'). Pakete zu je 400 Saetzen, hoechstens 10 GPUs gleichzeitig. Wiederaufnehmbar (fertige Saetze werden
uebersprungen). Ergebnis: gpu_sprache/<paket>/ergebnis_<n>.json -> tools/sprachpruefung.py --auswerten
"""
import json
from pathlib import Path
import modal

HIER = Path(__file__).resolve().parent
MAX_GPU, JE_PAKET = 10, 400


def _modell_laden():
    from huggingface_hub import snapshot_download
    snapshot_download("Systran/faster-whisper-large-v3", local_dir="/modell")


app = modal.App("readlayer-sprachpruefung")
image = (
    modal.Image.from_registry("nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04", add_python="3.11")
    .apt_install("ffmpeg")
    .pip_install("faster-whisper==1.1.1", "huggingface_hub", "requests")
    .run_function(_modell_laden)
    .add_local_dir(str(HIER), remote_path="/pakete", ignore=["**/ergebnis_*.json", "**/__pycache__", "**/*.py", "**/*.txt"])
)


@app.function(image=image, gpu=["L4", "A10G", "T4"], timeout=3600)
def lauf(paket: str, tags: list, lg: str) -> dict:
    from faster_whisper import WhisperModel
    from faster_whisper.audio import decode_audio
    m = WhisperModel("/modell", device="cuda", compute_type="float16")
    out = {}
    for t in tags:
        try:
            a = decode_audio(f"/pakete/{paket}/audio/{t}.flac", sampling_rate=16000)
            segs, info = m.transcribe(a, language=None, beam_size=1, without_timestamps=True,
                                      condition_on_previous_text=False, vad_filter=False)
            frei = " ".join(s.text.strip() for s in segs)
            probs = {k: round(float(v), 4) for k, v in (info.all_language_probs or [])[:8]}
            r = {"dauer": round(len(a) / 16000, 2), "top": info.language, "probs": probs, "text_frei": frei}
            # AP 57: immer zusaetzlich in der Zielsprache erzwungen, mit Wort-Konfidenz (englisch gesprochene
            # Woerter bekommen in der deutschen Dekodierung niedrige Wahrscheinlichkeiten)
            segs, _ = m.transcribe(a, language=lg, beam_size=1, word_timestamps=True,
                                   condition_on_previous_text=False, vad_filter=False)
            segs = list(segs)
            r["text_ziel"] = " ".join(s.text.strip() for s in segs)
            r["woerter"] = [[w.word.strip(), round(float(w.probability), 3)] for s in segs for w in (s.words or [])]
            out[t] = r
        except Exception as e:
            out[t] = {"fehler": f"{type(e).__name__}: {e}"[:200]}
    return out


@app.local_entrypoint()
def main(paket: str):
    z = HIER / paket
    T = json.loads((z / "texte.json").read_text(encoding="utf-8"))
    lg = T["lang"]
    fertig = set()
    for f in z.glob("ergebnis_*.json"):
        fertig |= set(json.loads(f.read_text(encoding="utf-8")))
    offen = [t for t in sorted(T["texte"]) if t not in fertig]
    pakete = [offen[i:i + JE_PAKET] for i in range(0, len(offen), JE_PAKET)]
    print(f"{paket}: {len(offen)} Saetze offen ({len(fertig)} fertig) -> {len(pakete)} Pakete")
    n0 = len(list(z.glob("ergebnis_*.json")))
    for w in range(0, len(pakete), MAX_GPU):
        welle = pakete[w:w + MAX_GPU]
        for i, erg in enumerate(lauf.starmap([(paket, p, lg) for p in welle])):
            (z / f"ergebnis_{n0 + w + i:03d}.json").write_text(json.dumps(erg, ensure_ascii=False), encoding="utf-8")
            print(f"  Paket {w + i + 1}/{len(pakete)}: {len(erg)} Saetze")
