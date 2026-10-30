"""READ LAYER — AP 62 Punkt 4: Schnitt-Zeitpunkte (MMS_FA) fuer die Hoerspiel-Stufe 510 auf Modal-GPU.
Gleicher Aligner wie lokal (pipeline/s520_wortzeiten.py, _Aligner), nur READLAYER_FA_DEVICE=cuda.
Wird aus pipeline/s510_hoerspiel_hybrid.py ueber `with app.run():` aufgerufen. Rueckfall: CPU (lokal).
GPU-Liste wie fa_modal.py: ["L4", "A10G", "T4"].
"""
from pathlib import Path
import modal

HIER = Path(__file__).resolve().parent
LESER = HIER.parent

app = modal.App("readlayer-schnitt510")
vol = modal.Volume.from_name("readlayer-tts", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch", "torchaudio", "numpy")
    .env({"TORCH_HOME": "/vol/torch", "READLAYER_FA_DEVICE": "cuda", "PYTHONUNBUFFERED": "1"})
    .add_local_dir(str(LESER / "config"), remote_path="/rl/config", ignore=["*.bak*", "__pycache__"])
    .add_local_file(str(LESER / "pipeline" / "__init__.py"), remote_path="/rl/pipeline/__init__.py")
    .add_local_file(str(LESER / "pipeline" / "s520_wortzeiten.py"), remote_path="/rl/pipeline/s520_wortzeiten.py")
    .add_local_file(str(LESER / "daten" / "index.json"), remote_path="/rl/daten/index.json")
)


@app.function(image=image, gpu=["L4", "A10G", "T4"], volumes={"/vol": vol}, timeout=3 * 3600)
def zeiten(chunk: list) -> dict:
    """chunk: [{key, erz, alt, woerter}] (Pfade relativ zum Volume). Gibt {key: (zeit_erz, zeit_alt)}."""
    import sys
    sys.path.insert(0, "/rl")
    vol.reload()
    from pipeline.s520_wortzeiten import _Aligner
    AL = _Aligner()
    out = {}
    for j in chunk:
        out[j["key"]] = (AL.ausrichten("/vol" + j["erz"], j["woerter"]),
                         AL.ausrichten("/vol" + j["alt"], j["woerter"]))
    return out
