"""READ LAYER — Chatterbox-VC fuer Stage 510 (Motor Fish, AP Fish-Regie 25.11.2026) auf Modal.
Kern: gpu_overlay/overlay_gpu.py (ChatterboxVC, Lautheit an die Quelle). Anders als overlay_modal.py wird nur das
eine Paket hochgeladen (als Zip), nicht der ganze Ordner gpu_overlay/.
Aufruf (aus pipeline/s511_vc_fish.py):  py -3.11 -m modal run gpu_overlay/vc_modal.py --paket <werk>_<lg>_510
Paket: gpu_overlay/<paket>/{jobs.json, src/<id>.wav, ref/<stimme>.wav} -> gpu_overlay/<paket>/ergebnis.zip
(vc/<id>.wav, bericht.txt). GPU-Fallback L4 -> A10G -> L40S.
"""
import io
import os
import zipfile
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


app = modal.App("readlayer-vc-510")
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libsndfile1")
    .pip_install("chatterbox-tts", "huggingface_hub", "safetensors")
    .add_local_file(str(HIER / "overlay_gpu.py"), remote_path="/code/overlay_gpu.py")
)


@app.function(image=image, gpu=["L4", "A10G", "L40S"], timeout=2 * 3600,
              secrets=[modal.Secret.from_dict({"HF_TOKEN": _hf_token()})])
def vc(paket_zip: bytes) -> bytes:
    import shutil, subprocess, time
    d = "/tmp/paket"
    shutil.rmtree(d, ignore_errors=True)
    zipfile.ZipFile(io.BytesIO(paket_zip)).extractall(d)
    os.makedirs("/out", exist_ok=True)
    t0 = time.time()
    subprocess.run(["python", "/code/overlay_gpu.py", d], check=False)
    with open("/out/bericht.txt", "a", encoding="utf-8") as f:
        f.write(f"WALL {time.time() - t0:.1f} s\n")
    shutil.make_archive("/tmp/ergebnis", "zip", "/out")
    return open("/tmp/ergebnis.zip", "rb").read()


@app.local_entrypoint()
def main(paket: str):
    q = HIER / paket
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        for p in q.rglob("*"):
            if p.is_file() and p.name != "ergebnis.zip":
                z.write(p, p.relative_to(q).as_posix())
    daten = vc.remote(bio.getvalue())
    ziel = q / "ergebnis.zip"
    ziel.write_bytes(daten)
    print(f"Heruntergeladen: {ziel} ({len(daten) // 1024} KB)")
