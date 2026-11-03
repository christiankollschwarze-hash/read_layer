"""READ LAYER - Stage 540 Trennung: ECAPA-Embeddings + pyannote-Diarisierung auf Modal (T4). Werkunabhaengig.
Aufruf aus der Stage: pipeline/s540_trennung.py -> messen([paket_dir, ...]) -> {paket_dir: ergebnis.zip (bytes)}
Paket = Ordner mit manifest.json, segmente/*.wav, spur_*.wav, spur_ref.json (Format von gpu_messung/messung_gpu.py);
es wird als Zip uebergeben (nur dieses Paket, nicht der ganze Ordner gpu_messung/).
Je Paket ein T4-Container; hoechstens 10 gleichzeitig (Modal-Limit), weitere Pakete in der naechsten Welle.
Ergebnis: embeddings.npz, fenster_*.npy, diar.json, bericht.txt. Kosten: ~0,03 $ je Paket (usage_log Stage 540).
Probe ohne Stage: py -3.11 -m modal run gpu_messung/messung_modal.py --pakete <paket_dir>[,<paket_dir>]
"""
import io
import os
import zipfile
from pathlib import Path

import modal

HIER = Path(__file__).resolve().parent
MAX_GPU = 10


def hf_token():
    tok = os.environ.get("HF_TOKEN", "")
    env = HIER.parent / ".env"
    if not tok and env.exists():
        for z in env.read_text(encoding="utf-8").splitlines():
            if z.strip().startswith("HF_TOKEN="):
                tok = z.split("=", 1)[1].strip().strip('"')
    return tok


app = modal.App("readlayer-s540-trennung")
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libsndfile1")
    .pip_install("torch==2.4.1", "torchaudio==2.4.1", "numpy<2", "soundfile", "scipy",
                 "speechbrain==1.0.3", "pyannote.audio==3.3.2", "pyannote.metrics", "huggingface_hub<0.26")
    .add_local_file(str(HIER / "messung_gpu.py"), remote_path="/root/messung_gpu.py")
)


@app.function(image=image, gpu="T4", timeout=3600,
              secrets=[modal.Secret.from_dict({"HF_TOKEN": hf_token()})])
def lauf(paket_zip: bytes) -> bytes:
    import shutil
    import subprocess
    for d in ("/paket", "/out"):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
    zipfile.ZipFile(io.BytesIO(paket_zip)).extractall("/paket")
    subprocess.run(["python", "/root/messung_gpu.py", "/paket", "/out"], check=False)
    shutil.make_archive("/tmp/ergebnis", "zip", "/out")
    return open("/tmp/ergebnis.zip", "rb").read()


def packen(paket) -> bytes:
    p = Path(paket)
    puf = io.BytesIO()
    with zipfile.ZipFile(puf, "w", zipfile.ZIP_STORED) as z:
        for f in ["manifest.json", "spur_ref.json"] + sorted(x.name for x in p.glob("spur_*.wav")):
            if (p / f).exists():
                z.write(p / f, f)
        for f in sorted((p / "segmente").glob("*.wav")):
            z.write(f, f"segmente/{f.name}")
    return puf.getvalue()


def messen(pakete):
    """[paket_dir] -> {paket_dir: ergebnis.zip bytes}; ein T4 je Paket, Wellen zu MAX_GPU."""
    liste = [str(p) for p in pakete]
    for p in liste:
        if not (Path(p) / "manifest.json").exists():
            raise FileNotFoundError(f"Paket ohne manifest.json: {p}")
    out = {}
    with app.run():
        for i in range(0, len(liste), MAX_GPU):
            welle = liste[i:i + MAX_GPU]
            for p, daten in zip(welle, lauf.map([packen(x) for x in welle])):
                out[p] = daten
    return out


@app.local_entrypoint()
def main(pakete: str = "", paket: str = ""):
    liste = [p.strip() for p in (pakete or paket).split(",") if p.strip()]
    if not liste:
        raise SystemExit("--pakete <paket_dir>[,...] fehlt")
    for i in range(0, len(liste), MAX_GPU):
        welle = liste[i:i + MAX_GPU]
        for p, daten in zip(welle, lauf.map([packen(x) for x in welle])):
            ziel = Path(p) / "ergebnis_modal.zip"
            ziel.write_bytes(daten)
            print(f"Ergebnis gespeichert: {ziel} ({len(daten) // 1024} KB)")
