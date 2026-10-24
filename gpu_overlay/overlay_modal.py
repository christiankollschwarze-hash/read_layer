"""READ LAYER — Overlay-Test (Chatterbox VC + Multilingual) ueber Modal, L4-GPU.
Aufruf (start_overlay_test.bat):  py -3.11 -m modal run gpu_overlay/overlay_modal.py --paket call-of-the-wild_de
Ergebnis: gpu_overlay/<paket>/ergebnis.zip  -> danach tools/overlay_montage.py
"""
import os
from pathlib import Path
import modal

HIER = Path(__file__).resolve().parent


def _hf_token():
    tok = os.environ.get("HF_TOKEN", "")
    env = HIER.parent / ".env"
    if not tok and env.exists():
        for z in env.read_text(encoding="utf-8").splitlines():
            if z.strip().startswith("HF_TOKEN="):
                tok = z.split("=", 1)[1].strip().strip('"')
    return tok


app = modal.App("readlayer-overlay-test")
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libsndfile1")
    .pip_install("chatterbox-tts", "huggingface_hub", "safetensors")
    .add_local_dir(str(HIER), remote_path="/pakete", ignore=["**/ergebnis.zip", "**/*.zip"])
)


@app.function(image=image, gpu="L4", timeout=2 * 3600,
              secrets=[modal.Secret.from_dict({"HF_TOKEN": _hf_token()})])
def lauf(paket: str) -> bytes:
    import shutil, subprocess
    os.makedirs("/out", exist_ok=True)
    subprocess.run(["python", "/pakete/overlay_gpu.py", f"/pakete/{paket}"], check=False)
    shutil.make_archive("/tmp/ergebnis", "zip", "/out")
    return open("/tmp/ergebnis.zip", "rb").read()


@app.local_entrypoint()
def main(paket: str = "call-of-the-wild_de"):
    daten = lauf.remote(paket)
    ziel = HIER / paket / "ergebnis.zip"
    ziel.write_bytes(daten)
    print(f"Ergebnis gespeichert: {ziel} ({len(daten) // 1024} KB)")
