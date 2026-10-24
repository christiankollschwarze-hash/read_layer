"""READ LAYER — Werk auf Modal FERTIGSTELLEN, ohne Hin- und Herladen einzelner Saetze (17.10.2026).

Die Satz-WAVs liegen nach tts_modal_opt.py (--no-herunterladen) schon im Volume (out/<paket>_<variante>).
Je Sprache ein GPU-Container:
  1. Wortzeiten Rohfassung (Stage 58c, MMS_FA)
  2. Raender schneiden (tools/raender_schneiden.py)  -> Stoergeraeusche zwischen Saetzen weg
  3. Tempo atempo 0,91 (CK 17.10.: 0,73 x 1,25) (tools/tempo_anpassen.py, ffmpeg)
  4. Wortzeiten Endfassung (Stage 58c)
  4b. Satzpruefung (tools/satzpruefung.py --schneiden): Nachklang kappen, verschmierte Saetze -> work/satzpruefung_<lg>.json
  5. Ergebnis als EIN Archiv ins Volume (audio/*.wav + 520_wortzeiten_<lg>.json)
Lokal: ein Download je Sprache, entpacken nach <werk>/fassungen/<lg>/audio + work/.

Aufruf:
  py -3.11 -m modal run gpu_tts/fertig_modal.py --werk <book_id> [--sprachen en,de] [--variante b8]
"""
import json, os, sys, time
from pathlib import Path
import modal

HIER = Path(__file__).resolve().parent
LESER = HIER.parent

app = modal.App("readlayer-fertigstellen")
vol = modal.Volume.from_name("readlayer-tts", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install("torch", "torchaudio", "numpy")
    .env({"TORCH_HOME": "/vol/torch", "READLAYER_FA_DEVICE": "cuda", "PYTHONUNBUFFERED": "1"})
    .add_local_dir(str(LESER / "config"), remote_path="/rl/config", ignore=["*.bak*", "__pycache__"])
    .add_local_file(str(LESER / "pipeline" / "__init__.py"), remote_path="/rl/pipeline/__init__.py")
    .add_local_file(str(LESER / "pipeline" / "s520_wortzeiten.py"), remote_path="/rl/pipeline/s520_wortzeiten.py")
    .add_local_file(str(LESER / "tools" / "raender_schneiden.py"), remote_path="/rl/tools/raender_schneiden.py")
    .add_local_file(str(LESER / "tools" / "tempo_anpassen.py"), remote_path="/rl/tools/tempo_anpassen.py")
    .add_local_file(str(LESER / "tools" / "satzpruefung.py"), remote_path="/rl/tools/satzpruefung.py")
    .add_local_file(str(LESER / "daten" / "index.json"), remote_path="/rl/daten/index.json")
)


@app.function(image=image, gpu="L4", volumes={"/vol": vol}, timeout=3 * 3600)
def fertig(rel_werk: str, werk: str, lang: str, quelle: str, tempo: str) -> dict:
    import shutil, subprocess, tarfile
    vol.reload()
    t0 = time.time()
    w = Path("/rl") / rel_werk
    (w / "work").mkdir(parents=True, exist_ok=True)
    shutil.copy(f"/vol/fertig/{rel_werk}/work/340_wortalignment.json", w / "work" / "340_wortalignment.json")
    if os.path.exists(f"/vol/fertig/{rel_werk}/work/400_regie.json"):
        shutil.copy(f"/vol/fertig/{rel_werk}/work/400_regie.json", w / "work" / "400_regie.json")
    audio = w / "fassungen" / lang / "audio"
    audio.mkdir(parents=True, exist_ok=True)
    for e in os.listdir(f"/vol/{quelle}"):
        if e.endswith(".wav"):
            shutil.copy(f"/vol/{quelle}/{e}", audio / e)
    n = len(list(audio.glob("*.wav")))
    log = []

    def lauf(*cmd):
        r = subprocess.run([sys.executable, *cmd], cwd="/rl", capture_output=True, text=True)
        log.append(f"$ {' '.join(cmd)} rc={r.returncode}\n" + (r.stdout + r.stderr)[-800:])
        if r.returncode:
            raise RuntimeError(log[-1])

    lauf("-m", "pipeline.s520_wortzeiten", werk, "--lang", lang, "--force")
    lauf("tools/raender_schneiden.py", werk, lang)
    lauf("tools/tempo_anpassen.py", werk, lang, tempo)
    lauf("-m", "pipeline.s520_wortzeiten", werk, "--lang", lang, "--force")
    if (w / "work" / "400_regie.json").exists():          # 17.10.2026: Satzpruefung im Standardprozess
        lauf("tools/satzpruefung.py", werk, lang, "--schneiden")
    ziel = f"/vol/fertig/{rel_werk}/paket_{lang}.tar"
    os.makedirs(os.path.dirname(ziel), exist_ok=True)
    with tarfile.open(ziel, "w") as tar:
        tar.add(audio, arcname=f"fassungen/{lang}/audio")
        wt = w / "work" / f"520_wortzeiten_{lang}.json"
        tar.add(wt, arcname=f"work/{wt.name}")
        sp = w / "work" / f"satzpruefung_{lang}.json"
        if sp.exists():
            tar.add(sp, arcname=f"work/{sp.name}")
    vol.commit()
    return {"lang": lang, "saetze": n, "minuten": round((time.time() - t0) / 60, 1),
            "log": "\n".join(x.splitlines()[0] + " | " + x.splitlines()[-1] for x in log)}


@app.local_entrypoint()
def main(werk: str, sprachen: str = "en,de", variante: str = "b8", tempo: str = ""):
    """tempo leer = aus gpu_tts/<werk>_<lg>/jobs.json (LoRA: eigenes Tempo, sonst 0,91)."""
    import tarfile, io
    sys.path.insert(0, str(LESER))
    from config import config
    pfad = Path(config.book_dir(werk))
    rel = pfad.relative_to(LESER).as_posix()
    langs = sprachen.split(",")
    with vol.batch_upload(force=True) as b:
        b.put_file(str(pfad / "work" / "340_wortalignment.json"), f"/fertig/{rel}/work/340_wortalignment.json")
        b.put_file(str(pfad / "work" / "400_regie.json"), f"/fertig/{rel}/work/400_regie.json")
    t0 = time.time()
    def tempo_fuer(l):
        if tempo:
            return tempo
        jp = HIER / f"{werk}_{l}" / "jobs.json"
        return json.load(open(jp, encoding="utf-8")).get("tempo", "0.91") if jp.exists() else "0.91"
    def variante_fuer(l):                 # "auto" (18.10.2026): b8 + Adapter aus jobs.json
        if variante != "auto":
            return variante
        jp = HIER / f"{werk}_{l}" / "jobs.json"
        lo = json.load(open(jp, encoding="utf-8")).get("lora") if jp.exists() else None
        return "b8" + (f"_{lo}" if lo else "")
    auftraege = [(rel, werk, l, f"out/{werk}_{l}_{variante_fuer(l)}", tempo_fuer(l)) for l in langs]
    print("Tempo: " + ", ".join(f"{a[2]} {a[4]}" for a in auftraege), flush=True)
    for erg in fertig.starmap(auftraege):
        print(f"[{erg['lang']}] {erg['saetze']} Saetze fertiggestellt in {erg['minuten']} min\n{erg['log']}", flush=True)
    for l in langs:
        print(f"[{l}] lade Paket ...", flush=True)
        daten = b"".join(vol.read_file(f"/fertig/{rel}/paket_{l}.tar"))
        audio = pfad / "fassungen" / l / "audio"
        if audio.exists():   # Rohfassung lokal beiseite legen (kein Loeschen)
            audio.rename(pfad / "fassungen" / l / f"audio_roh_{int(time.time())}")
        with tarfile.open(fileobj=io.BytesIO(daten)) as tar:
            tar.extractall(pfad)
        print(f"[{l}] {len(daten)/1e6:.0f} MB entpackt -> {audio}", flush=True)
    print(f"FERTIG in {(time.time() - t0) / 60:.1f} min")
