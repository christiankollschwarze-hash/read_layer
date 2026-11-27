"""READ LAYER — Stimmdesign mit Qwen3-TTS auf Modal (AP Qwen-Stimmdesign 26.11.2026, Prompt PROMPT_qwen_stimmdesign.md).
Modelle (Apache-2.0): Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign (Stimme aus Beschreibung), Qwen/Qwen3-TTS-12Hz-1.7B-Base
(Klon aus Referenz, auch sprachuebergreifend). Ersetzt Gemini Voice Design als Quelle fuer Klon-Referenzen (Gemini-
Bedingungen: keine Nutzung zur Entwicklung konkurrierender Modelle).

Aufrufe (aus tools/qwen_stimmen.py, cwd = Projektwurzel):
  py -3.11 -m modal run gpu_qwen/qwen_modal.py --paket <name>
Paket gpu_qwen/<name>/jobs.json:
  {"design": [{"key", "instruct", "text", "language", "seed"}],            VoiceDesign -> /vol/out/<paket>/<key>.wav
   "klon":   [{"key", "ref" (key eines fertigen Clips oder Paketdatei), "ref_text", "text", "language", "seed"}],
                                                                          Base-Klon -> /vol/out/<paket>/<key>.wav
   "ableiten": [{"key", "ref", "halbtoene"}],                             Tonhoehe/Formanten verschieben (Kinder aus Frauen)
   "embed": true}                                                         ECAPA je Clip -> /vol/out/<paket>/<key>.emb.json
Ergebnis gpu_qwen/<name>/out/<key>.wav (+ .emb.json), bericht.txt (GPU, WALL, KALTSTART, Clips, Audio, RTF).
Resume: fertige Clips liegen im Volume readlayer-qwen unter /out/<paket> und werden nicht neu erzeugt.
Cockpit (spaeter): `modal deploy gpu_qwen/qwen_modal.py`, dann modal.Function.from_name("readlayer-qwen-stimmen",
"erzeugen").remote(jobs_dict) – dieselbe Funktion wie im Stapel (Aufgabe 6).
"""
import io
import json
import os
import time
import zipfile
from pathlib import Path

import modal

HIER = Path(__file__).resolve().parent
SR = 24000
SPRACH_RMS_DB = -16.5          # wie Fish-Modal (gleicher Pegel fuer Referenzen)
PEAK_MAX_DB = -1.0
BATCH = int(os.environ.get("READLAYER_QWEN_BATCH", "8"))
GPU = [g.strip() for g in os.environ.get("READLAYER_QWEN_GPU", "L40S,A10G").split(",") if g.strip()]
M_DESIGN = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
M_BASE = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"

app = modal.App("readlayer-qwen-stimmen")
vol = modal.Volume.from_name("readlayer-qwen", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "ffmpeg", "sox", "libsndfile1")
    .pip_install("setuptools", "wheel")                    # qwen-tts zieht ein sdist (Build braucht setuptools)
    .run_commands("pip install --no-build-isolation qwen-tts soundfile numpy 'huggingface_hub[cli]'")
    .env({"PYTHONUNBUFFERED": "1", "HF_HOME": "/vol/hf"})
)
ecapa_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch==2.4.1", "torchaudio==2.4.1", "numpy<2", "soundfile", "speechbrain==1.0.3",
                 "huggingface_hub<0.26")
    .env({"HF_HOME": "/vol/hf"})
)


# ============================================================ Audio-Helfer
def _mono24(x, sr):
    import numpy as np
    import torch
    import torchaudio.functional as F
    x = np.asarray(x, dtype="float32")
    if x.ndim > 1:
        x = x.mean(axis=-1 if x.shape[-1] < x.shape[0] else 0)
    if sr != SR:
        x = F.resample(torch.from_numpy(x), sr, SR).numpy()
    return np.clip(x, -1, 1)


def _pegel(x):
    """Sprach-RMS (50-ms-Fenster > -45 dBFS) auf SPRACH_RMS_DB, Spitze hart <= PEAK_MAX_DB (Stille an den Raendern weg)."""
    import numpy as np
    w = int(0.05 * SR)
    if len(x) < w:
        return x
    fr = np.sqrt((x[:len(x) // w * w].reshape(-1, w) ** 2).mean(1))
    an = np.where(fr > 10 ** (-45 / 20))[0]
    if not len(an):
        return x
    x = x[max(0, (an[0] - 4) * w): min(len(x), (an[-1] + 6) * w)]       # 0,2 s vor / 0,3 s nach Sprache
    akt = fr[an]
    y = x * (10 ** (SPRACH_RMS_DB / 20) / np.sqrt((akt ** 2).mean()))
    t = 10 ** (PEAK_MAX_DB / 20)
    if np.abs(y).max() > t:
        y = y * (t / np.abs(y).max()) if np.abs(y).max() < t * 1.6 else np.tanh(y / t) * t
    return y


def _schreiben(pfad, x):
    import numpy as np
    import soundfile as sf
    Path(pfad).parent.mkdir(parents=True, exist_ok=True)
    sf.write(pfad, (np.clip(x, -1, 1) * 32767).astype(np.int16), SR, subtype="PCM_16")


def _lesen(pfad):
    import soundfile as sf
    x, sr = sf.read(pfad, dtype="float32", always_2d=True)
    return _mono24(x.mean(axis=1), sr)


def _modell(name):
    import torch
    from qwen_tts import Qwen3TTSModel
    return Qwen3TTSModel.from_pretrained(name, device_map="cuda:0", dtype=torch.bfloat16, attn_implementation="sdpa")


# ============================================================ Erzeugung
@app.function(image=image, gpu=GPU, volumes={"/vol": vol}, timeout=6 * 3600)
def erzeugen(jobs: dict, paket_zip: bytes = b"") -> str:
    import subprocess
    import torch
    t_start = time.time()
    vol.reload()
    d = Path("/tmp/paket")
    if paket_zip:
        zipfile.ZipFile(io.BytesIO(paket_zip)).extractall(d)
    out = Path("/vol/out", jobs.get("paket") or "_ohne")       # je Paket getrennt (Resume nur im selben Paket)
    out.mkdir(parents=True, exist_ok=True)
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                         capture_output=True, text=True).stdout.strip()
    bericht = [f"GPU {gpu}"]
    fertig = lambda k: (out / f"{k}.wav").exists()
    design = [j for j in jobs.get("design", []) if not fertig(j["key"])]
    klon = [j for j in jobs.get("klon", []) if not fertig(j["key"])]
    ableiten = [j for j in jobs.get("ableiten", []) if not fertig(j["key"])]
    bericht.append(f"OFFEN design {len(design)} klon {len(klon)} ableiten {len(ableiten)}")
    audio_s, gen_s, fehler, n = 0.0, 0.0, [], 0

    def ref_pfad(r):
        p = d / r
        return str(p if p.exists() else out / f"{r}.wav")

    if design:
        t0 = time.time()
        m = _modell(M_DESIGN)
        bericht.append(f"KALTSTART design {time.time() - t_start:.1f} s (Laden {time.time() - t0:.1f} s)")
        # Gruppen gleicher Seed+Sprache stapeln: Seed gilt je Stapel (Clip ist massgeblich, nicht bitgenau reproduzierbar)
        gruppen = {}
        for j in design:
            gruppen.setdefault((j.get("seed", 0), j["language"]), []).append(j)
        for (seed, lang), js in gruppen.items():
            for i in range(0, len(js), BATCH):
                teil = js[i:i + BATCH]
                t1 = time.time()
                try:
                    torch.manual_seed(int(seed))
                    wavs, sr = m.generate_voice_design(text=[j["text"] for j in teil], language=[lang] * len(teil),
                                                       instruct=[j["instruct"] for j in teil])
                except Exception as e:
                    fehler.append(f"design {seed}/{lang}: {type(e).__name__}: {str(e)[:200]}")
                    continue
                gen_s += time.time() - t1
                for j, w in zip(teil, wavs):
                    x = _pegel(_mono24(w, sr))
                    _schreiben(out / f"{j['key']}.wav", x)
                    audio_s += len(x) / SR
                    n += 1
                vol.commit()
                print(f"[qwen] design {n}/{len(design)}, {audio_s / 60:.1f} min Audio", flush=True)
        del m
        torch.cuda.empty_cache()

    if klon:
        t0 = time.time()
        m = _modell(M_BASE)
        bericht.append(f"LADEN base {time.time() - t0:.1f} s")
        def ein_klon(teil):
            torch.manual_seed(int(teil[0].get("seed", 0)))
            if len(teil) == 1:
                j = teil[0]
                prompt = m.create_voice_clone_prompt(ref_audio=ref_pfad(j["ref"]), ref_text=j["ref_text"],
                                                     x_vector_only_mode=False)
                return m.generate_voice_clone(text=j["text"], language=j["language"], voice_clone_prompt=prompt)
            return m.generate_voice_clone(text=[j["text"] for j in teil], language=[j["language"] for j in teil],
                                          ref_audio=[ref_pfad(j["ref"]) for j in teil],
                                          ref_text=[j["ref_text"] for j in teil])

        stapel = BATCH
        i = 0
        while i < len(klon):
            teil = klon[i:i + stapel]
            t1 = time.time()
            try:
                wavs, sr = ein_klon(teil)
            except Exception as e:
                if stapel > 1:             # Stapel-Klon nicht unterstuetzt -> einzeln weiter
                    bericht.append(f"KLON-STAPEL aus ({type(e).__name__}: {str(e)[:120]}) -> einzeln")
                    stapel = 1
                    continue
                fehler.append(f"klon {teil[0]['key']}: {type(e).__name__}: {str(e)[:200]}")
                i += 1
                continue
            gen_s += time.time() - t1
            for j, w in zip(teil, wavs):
                x = _pegel(_mono24(w, sr))
                _schreiben(out / f"{j['key']}.wav", x)
                audio_s += len(x) / SR
                n += 1
            i += len(teil)
            vol.commit()
            print(f"[qwen] klon {i}/{len(klon)}", flush=True)
        bericht.append(f"KLON-STAPEL {stapel}")

    for j in ableiten:                      # Kinderstimme aus heller Frauenstimme: Tonhoehe + Formanten gemeinsam
        try:
            import torchaudio.functional as F
            x = _lesen(ref_pfad(j["ref"]))
            y = F.pitch_shift(torch.from_numpy(x).unsqueeze(0), SR, n_steps=float(j["halbtoene"])).squeeze(0).numpy()
            _schreiben(out / f"{j['key']}.wav", _pegel(y))
            n += 1
        except Exception as e:
            fehler.append(f"ableiten {j['key']}: {type(e).__name__}: {str(e)[:200]}")
    vol.commit()
    bericht += [f"CLIPS {n} fehler {len(fehler)}", f"AUDIO {audio_s:.1f} s",
                f"GEN {gen_s:.1f} s RTF {gen_s / audio_s if audio_s else 0:.3f} (Stapel {BATCH})",
                f"WALL {time.time() - t_start:.1f} s"] + fehler[:30]
    return "\n".join(bericht)


@app.function(image=ecapa_image, volumes={"/vol": vol}, timeout=3600, cpu=4)
def embeddings(keys: list, paket: str = "_ohne") -> str:
    """ECAPA-TDNN (speechbrain/spkrec-ecapa-voxceleb, wie Stage 540) je Clip -> /vol/out/<paket>/<key>.emb.json (192 Werte)."""
    import soundfile as sf
    import torch
    import torchaudio.functional as F
    from speechbrain.inference.speaker import EncoderClassifier
    t0 = time.time()
    vol.reload()
    enc = EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb", savedir="/vol/hf/ecapa",
                                         run_opts={"device": "cpu"})
    n = 0
    for k in keys:
        p, z = Path(f"/vol/out/{paket}/{k}.wav"), Path(f"/vol/out/{paket}/{k}.emb.json")
        if not p.exists() or z.exists():
            continue
        x, sr = sf.read(str(p), dtype="float32")
        w = F.resample(torch.from_numpy(x), sr, 16000).unsqueeze(0)
        e = enc.encode_batch(w).squeeze().cpu().numpy()
        z.write_text(json.dumps([round(float(v), 5) for v in e]), encoding="utf-8")
        n += 1
    vol.commit()
    return f"ECAPA {n} neu, {time.time() - t0:.1f} s (CPU)"


# ============================================================ lokal
@app.local_entrypoint()
def main(paket: str):
    q = HIER / paket
    jobs = json.loads((q / "jobs.json").read_text(encoding="utf-8"))
    jobs["paket"] = paket
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        for j in jobs.get("klon", []) + jobs.get("ableiten", []):
            if (q / j["ref"]).is_file():
                z.write(q / j["ref"], j["ref"])
    n = sum(len(jobs.get(k, [])) for k in ("design", "klon", "ableiten"))
    print(f"[qwen] {paket}: {n} Clips -> Modal ({', '.join(GPU)})", flush=True)
    t0 = time.time()
    bericht = erzeugen.remote(jobs, bio.getvalue()) if n else "nichts zu erzeugen"
    wall_gpu = time.time() - t0
    keys = [j["key"] for k in ("design", "klon", "ableiten") for j in jobs.get(k, [])]
    if jobs.get("embed"):
        bericht += "\n" + embeddings.remote(keys, paket)
    out = q / "out"
    out.mkdir(exist_ok=True)
    geholt = 0
    for k in keys:
        for end in (".wav", ".emb.json"):
            if (out / f"{k}{end}").exists():
                continue
            try:
                (out / f"{k}{end}").write_bytes(b"".join(vol.read_file(f"/out/{paket}/{k}{end}")))
            except Exception:
                continue
        geholt += (out / f"{k}.wav").exists()
    bericht += f"\nLOKAL_WALL {wall_gpu:.1f} s\nGEHOLT {geholt}/{len(keys)}\n"
    (q / "bericht.txt").write_text(bericht, encoding="utf-8")
    print(bericht, flush=True)
