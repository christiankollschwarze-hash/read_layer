"""READ LAYER — Testlauf Prosodie-Vokabelheft v0.1 auf Modal (L4), 23.10.2026.
Paket: gpu_tts/prosodie_test_v01/jobs.json (tools/prosodie_markup.py paket).
Je Satz zwei Fassungen, gleicher Seed: a = ohne Markup (Standardregler), b = mit Markup (Chunks, Pausen, Stimmen).
DE mit LoRA mix_v1 (Standard), EN ohne. Danach Tempo 0,91 (Projektstandard) auf beide Fassungen.
Aufruf: py -3.11 -m modal run gpu_tts/prosodie_test_modal.py
Ergebnis: gpu_tts/prosodie_test_v01/audio/<ID>_a.wav, <ID>_b.wav + messung.json
"""
import json, os, sys
from pathlib import Path
import modal

HIER = Path(__file__).resolve().parent
LESER = HIER.parent
PAKET = HIER / "prosodie_test_v01"


def _hf_token():
    tok = os.environ.get("HF_TOKEN", "")
    env = LESER / ".env"
    if not tok and env.exists():
        for z in env.read_text(encoding="utf-8").splitlines():
            if z.strip().startswith("HF_TOKEN="):
                tok = z.split("=", 1)[1].strip().strip('"')
    return tok


app = modal.App("readlayer-prosodie-test")
vol = modal.Volume.from_name("readlayer-tts", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libsndfile1")
    .pip_install("chatterbox-tts", "huggingface_hub", "safetensors")
    .env({"HF_HOME": "/vol/hf", "TORCH_HOME": "/vol/torch"})
    .add_local_file(str(HIER / "cb_batch.py"), remote_path="/code/cb_batch.py")
    .add_local_file(str(LESER / "gpu_lora" / "lora_kern.py"), remote_path="/code/lora_kern.py")
    .add_local_dir(str(PAKET), remote_path="/paket", ignore=lambda p: "audio" in p.parts or p.suffix == ".html")
)
ADAPTER = {"mix_v1": "lora/mix_v1/ckpt/step_01000.safetensors"}


@app.function(image=image, gpu="L4", volumes={"/vol": vol}, timeout=3600,
              secrets=[modal.Secret.from_dict({"HF_TOKEN": _hf_token()})])
def sprache(lang: str) -> dict:
    import io, random, shutil, subprocess, tempfile, time
    import numpy as np, torch, torchaudio
    sys.path.insert(0, "/code")
    import chatterbox.mtl_tts as mtl
    from cb_batch import sprech_norm
    mtl.punc_norm = sprech_norm                      # Projektstandard: Satzzeichen erhalten
    t0 = time.time()
    d = json.load(open("/paket/jobs.json", encoding="utf-8"))
    m = mtl.ChatterboxMultilingualTTS.from_pretrained(device="cuda")
    lora = (d.get("lora") or {}).get(lang)
    if lora:
        import lora_kern
        ziel = f"/vol/lora/adapter/{lora}.safetensors"
        if not os.path.exists(ziel):
            os.makedirs(os.path.dirname(ziel), exist_ok=True)
            shutil.copy(f"/vol/{ADAPTER[lora]}", ziel)
        lora_kern.einmischen(m.t3, ziel, 1.0)
    sr = m.sr
    seed = int(d.get("seed", 1234))

    def gen(g):
        torch.manual_seed(seed); random.seed(seed); np.random.seed(seed)
        ref = "/paket/" + d["refs"][f'{g["stimme"]}|{lang}']
        w = m.generate(g["text"], language_id=lang, audio_prompt_path=ref, exaggeration=g["ex"],
                       cfg_weight=g["cfg"], temperature=g["temp"]).float().cpu().reshape(-1)
        # Stille am Rand kappen (30 ms Rest), damit Chunk-Fugen nur die geplanten Pausen haben
        laut = (w.abs() > 10 ** (-40 / 20)).nonzero()
        if len(laut):
            r = int(0.03 * sr)
            w = w[max(0, int(laut[0]) - r): int(laut[-1]) + r]
        if g.get("gain_db"):
            w = w * 10 ** (g["gain_db"] / 20)
        return w

    aus, stat = {}, {"chunks": 0, "audio_s": 0.0, "fehler": []}
    for s in [x for x in d["saetze"] if x["lang"] == lang]:
        for v in ("a", "b"):
            teile = []
            for g in s[v]:
                if g["t"] == "pause":
                    teile.append(torch.zeros(int(sr * g["ms"] / 1000)))
                    continue
                try:
                    teile.append(gen(g))
                    stat["chunks"] += 1
                except Exception as ex:
                    stat["fehler"].append(f'{s["id"]}{v}: {str(ex)[:120]}')
            if not teile:
                continue
            w = torch.cat([torch.zeros(int(sr * 0.2))] + teile + [torch.zeros(int(sr * 0.3))]).clamp(-1, 1)
            with tempfile.TemporaryDirectory() as td:
                roh, fertig = f"{td}/r.wav", f"{td}/f.wav"
                torchaudio.save(roh, w.reshape(1, -1), sr, encoding="PCM_S", bits_per_sample=16)
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", roh, "-filter:a",
                                f"atempo={d.get('tempo', 1.0)}", fertig], check=True)
                aus[f'{s["id"]}_{v}.wav'] = open(fertig, "rb").read()
            stat["audio_s"] += w.shape[-1] / sr
        print(f"[{lang}] {s['id']} fertig", flush=True)
    stat["gpu_s"] = round(time.time() - t0, 1)
    stat["usd"] = round(stat["gpu_s"] / 3600 * 0.80, 3)
    return {"dateien": aus, "stat": stat}


@app.local_entrypoint()
def main():
    ziel = PAKET / "audio"
    ziel.mkdir(exist_ok=True)
    messung = {}
    for lang, erg in zip(("de", "en"), sprache.map(["de", "en"])):
        for name, b in erg["dateien"].items():
            (ziel / name).write_bytes(b)
        messung[lang] = erg["stat"]
        print(f"[prosodie] {lang}: {len(erg['dateien'])} WAVs, {erg['stat']}")
    (PAKET / "messung.json").write_text(json.dumps(messung, indent=1), encoding="utf-8")
