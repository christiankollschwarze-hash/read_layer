"""READ LAYER — Stage 58c (Wortzeiten, MMS_FA) auf Modal-GPU (L4).
Gleicher Code wie lokal (pipeline/s520_wortzeiten.py), nur READLAYER_FA_DEVICE=cuda.
Aufruf:  py -3.11 -m modal run gpu_fa/fa_modal.py --werk jekyll-and-hyde [--sprachen de,en] [--force]
Ablauf:  Audio + 340_wortalignment.json ins Volume laden -> je Sprache ein GPU-Container -> Ergebnis-JSON zurueck nach work/.
"""
import json, os, time
from pathlib import Path
import modal

HIER = Path(__file__).resolve().parent
LESER = HIER.parent

app = modal.App("readlayer-wortzeiten")
vol = modal.Volume.from_name("readlayer-tts", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch", "torchaudio", "numpy")
    .env({"TORCH_HOME": "/vol/torch", "READLAYER_FA_DEVICE": "cuda", "PYTHONUNBUFFERED": "1"})
    .add_local_dir(str(LESER / "config"), remote_path="/rl/config", ignore=["*.bak*", "__pycache__"])
    .add_local_file(str(LESER / "pipeline" / "__init__.py"), remote_path="/rl/pipeline/__init__.py")
    .add_local_file(str(LESER / "pipeline" / "s520_wortzeiten.py"), remote_path="/rl/pipeline/s520_wortzeiten.py")
    .add_local_file(str(LESER / "pipeline" / "s525_wortbruecke.py"), remote_path="/rl/pipeline/s525_wortbruecke.py")
    .add_local_file(str(LESER / "daten" / "index.json"), remote_path="/rl/daten/index.json")
)


@app.function(image=image, gpu="L4", volumes={"/vol": vol}, timeout=3 * 3600)
def ausrichten(rel_werk: str, werk: str, lang: str, force: bool) -> str:
    import shutil, subprocess, sys
    vol.reload()
    # Werkordner aus dem Volume an die erwartete Stelle legen (authors/<a>/books/<b>)
    ziel = Path("/rl") / rel_werk
    ziel.parent.mkdir(parents=True, exist_ok=True)
    if not ziel.exists():
        os.symlink(f"/vol/fa/{rel_werk}", ziel)
    t0 = time.time()
    cmd = [sys.executable, "-m", "pipeline.s520_wortzeiten", werk, "--lang", lang] + (["--force"] if force else [])
    r = subprocess.run(cmd, cwd="/rl", capture_output=True, text=True)
    vol.commit()
    log = (r.stdout + r.stderr)[-1500:]
    return f"[{lang}] rc={r.returncode} | {(time.time() - t0) / 60:.1f} min\n{log}"


@app.local_entrypoint()
def main(werk: str, sprachen: str = "de,en", force: bool = False):
    import sys
    sys.path.insert(0, str(LESER))
    from config import config
    pfad = Path(config.book_dir(werk))     # auch private Uploads (users/<uid>/works/...)
    rel = pfad.relative_to(LESER).as_posix()
    langs = [s for s in sprachen.split(",") if (pfad / "fassungen" / s / "audio").is_dir()]
    t0 = time.time()
    print(f"Lade hoch: {rel} ({', '.join(langs)}) ...", flush=True)
    with vol.batch_upload(force=True) as b:
        b.put_file(str(pfad / "work" / "340_wortalignment.json"), f"/fa/{rel}/work/340_wortalignment.json")
        for s in langs:
            ziel_json = pfad / "work" / f"520_wortzeiten_{s}.json"
            fertig = set()
            if ziel_json.exists() and not force:
                b.put_file(str(ziel_json), f"/fa/{rel}/work/520_wortzeiten_{s}.json")
                fertig = set(json.loads(ziel_json.read_text(encoding="utf-8")).get("tags", {}))
            # 16.10.2026: nur Saetze ohne Wortzeiten hochladen (nach Neuvertonung wenige hundert statt ganzer Ordner).
            # Bereits vermessene Tags ueberspringt 58c ohnehin; ihre WAVs muessen nicht im Volume liegen.
            wavs = [w for w in (pfad / "fassungen" / s / "audio").glob("*.wav") if w.stem not in fertig]
            for w in wavs:
                b.put_file(str(w), f"/fa/{rel}/fassungen/{s}/audio/{w.name}")
            print(f"  {s}: {len(wavs)} Satz-WAVs ohne Wortzeiten ({len(fertig)} schon vermessen)", flush=True)
    print(f"Hochgeladen in {(time.time() - t0) / 60:.1f} min. Starte {len(langs)} GPU-Container ...", flush=True)
    for zeile in ausrichten.starmap([(rel, werk, s, force) for s in langs]):
        print(zeile, flush=True)
    for s in langs:
        name = f"520_wortzeiten_{s}.json"
        daten = b"".join(vol.read_file(f"/fa/{rel}/work/{name}"))
        (pfad / "work" / name).write_bytes(daten)
        print(f"Zurueck: work/{name} ({len(json.loads(daten).get('tags', {}))} Saetze)", flush=True)
    print(f"Gesamt {(time.time() - t0) / 60:.1f} min", flush=True)
