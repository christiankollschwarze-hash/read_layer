"""READ LAYER — Satzpruefung Stage 500 (Gemini-Gleis) auf Modal-GPU (20.11.2026).
Gleicher Pruefer wie lokal (gpu_tts/cb_pruefung.py, MMS_FA), nur device=cuda. Vorher lief die Pruefung der
Gemini-Saetze seriell auf der CPU (Art of War DE: 2742 Saetze ~5 h). Aufruf aus pipeline/s500_vertonung_gemini.py
(pruefen_modal) ueber `with app.run():`; WAVs als 16 kHz mono ins Volume (Pruefer rechnet ohnehin auf 16 kHz).
Rueckfall: CPU lokal (je Satz, der auf Modal fehlt). GPU-Liste ["L4", "A10G", "T4"].
"""
from pathlib import Path
import modal

HIER = Path(__file__).resolve().parent

app = modal.App("readlayer-pruef500")
vol = modal.Volume.from_name("readlayer-tts", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch", "torchaudio", "numpy")
    .env({"TORCH_HOME": "/vol/torch", "PYTHONUNBUFFERED": "1"})
    .add_local_file(str(HIER / "cb_pruefung.py"), remote_path="/rl/cb_pruefung.py")
)


@app.function(image=image, gpu=["L4", "A10G", "T4"], volumes={"/vol": vol}, timeout=3600)
def pruefen(chunk: list, ms: float) -> dict:
    """chunk: [{key, wav (relativ zum Volume), text}] -> {key: {grund, letzt, dauer} | {fehler}}."""
    import sys
    import wave
    import numpy as np
    import torch
    sys.path.insert(0, "/rl")
    vol.reload()
    import cb_pruefung
    cb_pruefung.MS_JE_ZEICHEN = ms
    P = cb_pruefung.Pruefer("cuda")
    out = {}
    for j in chunk:
        try:
            with wave.open("/vol" + j["wav"], "rb") as w:
                sr = w.getframerate()
                x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype("float32") / 32768.0
            out[j["key"]] = dict(P.pruefe(j["text"], torch.from_numpy(x.copy()).unsqueeze(0), sr))
        except Exception as e:
            out[j["key"]] = {"fehler": f"{type(e).__name__}: {str(e)[:120]}"}
    return out
