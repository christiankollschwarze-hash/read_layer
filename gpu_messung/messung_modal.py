"""READ LAYER - Sprechertrennung messen auf Modal (ECAPA-Embeddings + pyannote-Diarisierung). Werkunabhaengig.
Aufruf (start_trennung_messen.bat <werk> <lg>):
    py -3.11 -m modal run gpu_messung/messung_modal.py --pakete call-of-the-wild_de[,call-of-the-wild_en,...]
Je Paket ein T4-Container; hoechstens 10 gleichzeitig (Modal-Limit), weitere Pakete laufen in der naechsten Welle.
Ergebnis: gpu_messung/<paket>/ergebnis_modal.zip (embeddings.npz, fenster_*.npy, diar.json, bericht.txt)
Danach: py -3.11 tools/trennung_auswerten.py <werk> <lg>
"""
import os
from pathlib import Path
import modal

HIER = Path(__file__).resolve().parent
MAX_GPU = 10


def _hf_token():
    tok = os.environ.get("HF_TOKEN", "")
    env = HIER.parent / ".env"
    if not tok and env.exists():
        for z in env.read_text(encoding="utf-8").splitlines():
            if z.strip().startswith("HF_TOKEN="):
                tok = z.split("=", 1)[1].strip().strip('"')
    return tok


app = modal.App("readlayer-trennung-messen")
# Modal laedt nur geaenderte Dateien hoch (Inhalts-Hash); Hoertest, Zips und Praat-Ergebnisse bleiben lokal.
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libsndfile1")
    .pip_install("torch==2.4.1", "torchaudio==2.4.1", "numpy<2", "soundfile", "scipy",
                 "speechbrain==1.0.3", "pyannote.audio==3.3.2", "pyannote.metrics", "huggingface_hub<0.26")
    .add_local_dir(str(HIER), remote_path="/pakete",
                   ignore=["**/*.zip", "**/__pycache__", "**/blindtest", "**/blindtest/**", "**/*.mp3",
                           "**/*.html", "**/messung_praat*.json", "**/auswertung.json", "**/*.md",
                           "**/*.txt", "**/*.log", "**/*.alt", "_log*"])
)


@app.function(image=image, gpu="T4", timeout=3600,
              secrets=[modal.Secret.from_dict({"HF_TOKEN": _hf_token()})])
def lauf(paket: str) -> bytes:
    import shutil, subprocess
    shutil.rmtree("/out", ignore_errors=True)
    os.makedirs("/out", exist_ok=True)
    subprocess.run(["python", "/pakete/messung_gpu.py", f"/pakete/{paket}"], check=False)
    shutil.make_archive("/tmp/ergebnis", "zip", "/out")
    return open("/tmp/ergebnis.zip", "rb").read()


@app.local_entrypoint()
def main(pakete: str = "", paket: str = ""):
    liste = [p.strip() for p in (pakete or paket).split(",") if p.strip()]
    if not liste:
        raise SystemExit("--pakete <werk>_<lg>[,...] fehlt")
    for p in liste:
        if not (HIER / p / "manifest.json").exists():
            raise SystemExit(f"Paket fehlt: {HIER / p} (erst tools/trennung_messen.py)")
    for i in range(0, len(liste), MAX_GPU):
        welle = liste[i:i + MAX_GPU]
        for p, daten in zip(welle, lauf.map(welle)):
            ziel = HIER / p / "ergebnis_modal.zip"
            ziel.write_bytes(daten)
            print(f"Ergebnis gespeichert: {ziel} ({len(daten) // 1024} KB)")
