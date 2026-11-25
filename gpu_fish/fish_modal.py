"""READ LAYER — Fish Drama 3 selbst gehostet auf Modal (Stage 500, Motor fish, Weg "modal"; AP Fish-Modal 25.11.2026).
Gewichte: fishaudio/drama-3 (Fish Audio Community License v1.0 – "Built with Fish Audio" sichtbar, keine Hosted-Service-
Nutzung, kein Training mit Outputs; Umsatzgrenze -> business@fish.audio vor Massenproduktion). Inferenz: fish-speech
(tools/api_server.py im Container, msgpack /v1/tts), >= 48 GB GPU (FP8-Experten), kein --compile.
Zeitmarken: der lokale Server liefert keine Wort-Zeitmarken -> MMS_FA (pipeline/fa_mms.py) im selben Container.
Schnittstelle wie API-Weg: Block-Text mit Anweisungen + Referenzstimme (Klon-Clip + Text) -> WAV 24 kHz mono 16 bit
+ Woerter [{w,a,b}] in s.

Aufrufe (aus pipeline/s503_vertonung_fish.py, cwd = Projektwurzel):
  py -3.11 -m modal run gpu_fish/fish_modal.py --paket <werk>_<lg>_500      Stapel: alle Bloecke eines Werks x Sprache
  py -3.11 -m modal run gpu_fish/fish_modal.py --gewichte-laden             nur Gewichte ins Volume (CPU, einmalig)
Paket gpu_fish/<paket>/: jobs.json {lang, ref: {datei, text}, jobs: [{key, text, woerter: [{w, l}], seed, audio?}]}, ref/<datei>.
  Job mit "audio" (Pfad im Paket): keine Vertonung, nur MMS_FA auf dieses Audio (Pruefblock: FA vs. Fish-API-Zeitmarken).
Ergebnis gpu_fish/<paket>/out/<key>.wav + <key>.json {woerter, info}, bericht.txt (GPU, WALL, KALTSTART, MODELL, COMMIT).
Resume: fertige Bloecke liegen im Volume readlayer-fish unter /out/<key>.* und werden nicht neu vertont
(key = Blockhash aus dem 500-Manifest + Versuch). GPU-Liste: Umgebung READLAYER_FISH_GPU (Standard "H100,L40S").
"""
import io
import json
import os
import time
import zipfile
from pathlib import Path

import modal

HIER = Path(__file__).resolve().parent
LESER = HIER.parent
GEWICHTE = "/vol/drama-3"
S2_CODEC = "/vol/s2-pro"
SR = 24000
# Inferenz-Engine: sglang (SGLang-Omni, buendelt viele Stroeme auf einer GPU; Standard seit 25.11.) | fish (fish-speech
# api_server, arbeitet Anfragen nacheinander ab: Pruefblock RTF 0,56 -> ~2,2 $/Audio-h auf H100)
ENGINE = os.environ.get("READLAYER_FISH_ENGINE", "sglang")
NACH = f"{ENGINE}-pegel1"        # Engine + Nachbearbeitung (aendern -> fertige Bloecke im Volume werden neu erzeugt)
TEIL_MAX = 1000                  # sglang: Block in Teile <= so viele Zeichen (max_new_tokens <= 2048 Frames ~ 95 s je Anfrage)
SPRACH_RMS_DB = -16.5            # Ziel-Pegel der Sprachanteile (wie Fish-API, Pruefblock 25.11.: API -16,4 / Modal roh -22,1 dBFS)
PEAK_MAX_DB = -1.0
PARALLEL = 16 if ENGINE == "sglang" else 4   # gleichzeitige Bloecke (SGLang-Omni: Standard 16 laufende Anfragen)
GPU = [g.strip() for g in os.environ.get("READLAYER_FISH_GPU", "H100,L40S").split(",") if g.strip()]


def _hf_token():
    tok = os.environ.get("HF_TOKEN", "")
    env = LESER / ".env"
    if not tok and env.exists():
        for z in env.read_text(encoding="utf-8").splitlines():
            if z.strip().startswith("HF_TOKEN="):
                tok = z.split("=", 1)[1].strip().strip('"')
    return tok


app = modal.App("readlayer-fish-500")
vol = modal.Volume.from_name("readlayer-fish", create_if_missing=True)
image = (
    modal.Image.from_registry("nvidia/cuda:12.9.1-devel-ubuntu22.04", add_python="3.12")
    .apt_install("git", "ffmpeg", "portaudio19-dev", "libsox-dev", "libsndfile1", "clang")   # clang: pyaudio-Build (Python von Modal ist mit clang gebaut)
    .run_commands(
        "git clone --depth 1 https://github.com/fishaudio/fish-speech.git /fish",
        "cd /fish && git rev-parse HEAD > /fish/COMMIT",
        # fish-speech in EIGENER venv: seine Abhaengigkeiten (u. a. protobuf 3.19) zerschiessen sonst Modals Laufzeit
        "python -m venv /fishenv",
        "cd /fish && /fishenv/bin/pip install --extra-index-url https://download.pytorch.org/whl/cu129 -e '.[cu129]'",
        # SGLang-Omni (empfohlen von Fish fuer Effizienz) ebenfalls in eigener venv
        "git clone --depth 1 https://github.com/sgl-project/sglang-omni.git /omni",
        "cd /omni && git rev-parse HEAD > /omni/COMMIT",
        "python -m venv /omnienv",
        "/omnienv/bin/pip install uv",
        "cd /omni && /omnienv/bin/uv pip install --python /omnienv/bin/python --prerelease=allow -e '.[fishaudio]'",
    )
    .pip_install("torch==2.8.0", "torchaudio==2.8.0", index_url="https://download.pytorch.org/whl/cu129")  # MMS_FA
    .pip_install("huggingface_hub[cli]", "ormsgpack", "requests", "soundfile", "numpy")
    .env({"PYTHONUNBUFFERED": "1", "HF_HUB_ENABLE_HF_TRANSFER": "0", "TORCH_HOME": "/vol/torch"})
    .run_commands("apt-get update && apt-get install -y ninja-build")   # SGLang baut Kernel per JIT (ninja + nvcc)
    .add_local_file(str(LESER / "pipeline" / "fa_mms.py"), remote_path="/rl/fa_mms.py")
)
geheim = [modal.Secret.from_dict({"HF_TOKEN": _hf_token()})]


# ============================================================ Gewichte
@app.function(image=image, volumes={"/vol": vol}, timeout=3 * 3600, secrets=geheim, cpu=4)
def gewichte() -> str:
    """drama-3 nach /vol/drama-3 (einmalig); fehlt codec.pth -> Codec aus s2-pro (Fallback laut Fish-Doku)."""
    import subprocess
    t0 = time.time()
    vol.reload()
    if not Path(GEWICHTE, "config.json").exists():
        subprocess.run(["hf", "download", "fishaudio/drama-3", "--local-dir", GEWICHTE], check=True)
    if not Path(GEWICHTE, "codec.pth").exists() and not Path(S2_CODEC, "codec.pth").exists():
        subprocess.run(["hf", "download", "fishaudio/s2-pro", "codec.pth", "--local-dir", S2_CODEC], check=True)
    vol.commit()
    gb = sum(p.stat().st_size for p in Path(GEWICHTE).rglob("*") if p.is_file()) / 1e9
    lizenz = next((p.name for p in Path(GEWICHTE).iterdir() if p.name.upper().startswith("LICENSE")), "-")
    return f"Gewichte {GEWICHTE}: {gb:.1f} GB, Lizenzdatei {lizenz}, {time.time() - t0:.0f} s"


def modell_pruefen():
    """Self-Hosting garantiert drama-3: Checkpoint-config.json muss Drama 3 sein (kein stiller Rueckfall wie bei der API)."""
    cfg = json.loads(Path(GEWICHTE, "config.json").read_text(encoding="utf-8"))
    roh = json.dumps(cfg).lower()
    ok = "drama" in roh or cfg.get("num_experts") or cfg.get("num_local_experts") or "moe" in roh
    return ("drama-3" if ok else "UNBEKANNT"), {k: cfg.get(k) for k in ("model_type", "architectures", "num_experts",
                                                                          "num_local_experts") if k in cfg}


# ============================================================ Server + Vertonung
def _server_starten():
    return _sglang_starten() if ENGINE == "sglang" else _fish_starten()


def _sglang_starten():
    """sgl-omni serve (Standard-FP8, Attention triton, 16 laufende Anfragen, 0,70 GPU-Speicher); bereit = /health 200."""
    import subprocess
    import requests
    cmd = ["/omnienv/bin/sgl-omni", "serve", "--model-path", GEWICHTE, "--port", "8000"]
    log = open("/tmp/server.log", "w")
    env = dict(os.environ, PATH="/omnienv/bin:/usr/local/cuda/bin:" + os.environ.get("PATH", ""))   # ninja/nvcc fuer JIT-Kernel
    proc = subprocess.Popen(cmd, cwd="/omni", stdout=log, stderr=subprocess.STDOUT, env=env)
    t0 = time.time()
    while time.time() - t0 < 1800:
        if proc.poll() is not None:
            raise RuntimeError("SGLang-Omni beendet:\n" + open("/tmp/server.log").read()[-3000:])
        try:
            if requests.get("http://127.0.0.1:8000/health", timeout=5).status_code == 200:
                return proc, time.time() - t0
        except Exception:
            pass
        time.sleep(5)
    raise RuntimeError("SGLang-Omni nicht bereit nach 30 min:\n" + open("/tmp/server.log").read()[-3000:])


def teile(text, maxz=TEIL_MAX):
    """Block -> Teile <= maxz Zeichen; bevorzugt vor einer Anweisung '[' (Figurenwechsel), sonst am Satzende."""
    import re
    out = []
    while len(text) > maxz:
        stueck = text[:maxz]
        vor_anw = [m.start() for m in re.finditer(r"(?<!\])\s\[", stueck) if m.start() > maxz * 0.4]  # vor Tag-Folge
        satz = [m.end() for m in re.finditer(r"[.!?…][»“\"«]?\s", stueck) if m.end() > maxz * 0.4]
        k = (vor_anw or satz or [stueck.rfind(" ")])[-1]
        if k <= 0:
            k = maxz
        out.append(text[:k].strip())
        text = text[k:].strip()
    if text:
        out.append(text)
    return out


def _tts_sglang(text, ref_pfad, ref_text, extra=None):
    """POST /v1/audio/speech (OpenAI-kompatibel) -> WAV-Bytes (44,1 kHz). seed wird von SGLang-Omni abgelehnt."""
    import requests
    daten = {"input": text, "references": [{"audio_path": ref_pfad, "text": ref_text}], "response_format": "wav"}
    daten.update(extra or {})
    for versuch in range(3):
        r = requests.post("http://127.0.0.1:8000/v1/audio/speech", json=daten, timeout=1800)
        if r.status_code == 200 and r.content:
            return r.content
        time.sleep(3 * (versuch + 1))
    raise RuntimeError(f"/v1/audio/speech {r.status_code}: {r.text[:300]}")


def _fish_starten():
    import subprocess
    import requests
    codec = Path(GEWICHTE, "codec.pth") if Path(GEWICHTE, "codec.pth").exists() else Path(S2_CODEC, "codec.pth")
    cmd = ["/fishenv/bin/python", "tools/api_server.py", "--listen", "127.0.0.1:8080", "--llama-checkpoint-path", GEWICHTE,
           "--decoder-checkpoint-path", str(codec), "--device", "cuda"]
    log = open("/tmp/server.log", "w")
    proc = subprocess.Popen(cmd, cwd="/fish", stdout=log, stderr=subprocess.STDOUT)
    t0 = time.time()
    while time.time() - t0 < 1800:
        if proc.poll() is not None:
            raise RuntimeError("Fish-Server beendet:\n" + open("/tmp/server.log").read()[-3000:])
        try:
            r = requests.get("http://127.0.0.1:8080/v1/health", timeout=5)
            if r.status_code < 500:
                return proc, time.time() - t0
        except Exception:
            pass
        time.sleep(5)
    raise RuntimeError("Fish-Server nicht bereit nach 30 min:\n" + open("/tmp/server.log").read()[-3000:])


def _tts(text, ref_audio, ref_text, seed, extra=None):
    import ormsgpack
    import requests
    # Felder wie fish_speech.utils.schema.ServeTTSRequest (als dict, fish-speech liegt in eigener venv)
    daten = {"text": text, "references": [{"audio": ref_audio, "text": ref_text}], "reference_id": None,
             "format": "wav", "streaming": False, "use_memory_cache": "on", "seed": seed, "normalize": True}
    daten.update(extra or {})                      # z. B. temperature/top_p (Pruefzwecke)
    for versuch in range(3):
        r = requests.post("http://127.0.0.1:8080/v1/tts", params={"format": "msgpack"},
                          data=ormsgpack.packb(daten),
                          headers={"content-type": "application/msgpack"}, timeout=1800)
        if r.status_code == 200 and r.content:
            return r.content
        time.sleep(3 * (versuch + 1))
    raise RuntimeError(f"/v1/tts {r.status_code}: {r.text[:300]}")


def _nach_24k(wav_bytes):
    """beliebiges WAV -> float32 mono 24 kHz."""
    import numpy as np
    import soundfile as sf
    import torch
    import torchaudio.functional as F
    x, sr = sf.read(io.BytesIO(wav_bytes), dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    if sr != SR:
        x = F.resample(torch.from_numpy(x), sr, SR).numpy()
    return np.clip(x, -1, 1)


def pegel(x):
    """Sprach-RMS (50-ms-Fenster ueber -45 dBFS) auf SPRACH_RMS_DB, Spitze <= PEAK_MAX_DB (Fish-API liefert ~-16,5 dBFS)."""
    import numpy as np
    w = int(0.05 * SR)
    if len(x) < w:
        return x
    fr = np.sqrt((x[:len(x) // w * w].reshape(-1, w) ** 2).mean(1))
    akt = fr[fr > 10 ** (-45 / 20)]
    if not len(akt):
        return x
    y = x * (10 ** (SPRACH_RMS_DB / 20) / np.sqrt((akt ** 2).mean()))
    return limiter(y)


def limiter(y, ms=3):
    """Spitzenbegrenzer auf PEAK_MAX_DB: Verstaerkung je Sample, Minimum ueber +-ms, geglaettet (kein hartes Clipping)."""
    import numpy as np
    from numpy.lib.stride_tricks import sliding_window_view as fenster
    t = 10 ** (PEAK_MAX_DB / 20)
    if np.abs(y).max() <= t:
        return y
    g = np.minimum(1.0, t / np.maximum(np.abs(y), 1e-9))
    k = max(1, int(ms / 1000 * SR))
    g = fenster(np.pad(g, k, mode="edge"), 2 * k + 1).min(axis=1)
    g = np.convolve(np.pad(g, k, mode="edge"), np.ones(2 * k + 1) / (2 * k + 1), mode="valid")
    return np.clip(y * g, -t, t)


def _schreiben(pfad, x):
    import numpy as np
    import soundfile as sf
    sf.write(pfad, (x * 32767).astype(np.int16), SR, subtype="PCM_16")


@app.function(image=image, gpu=GPU, volumes={"/vol": vol}, timeout=12 * 3600, secrets=geheim)
def vertonen(paket_zip: bytes) -> str:
    import concurrent.futures as cf
    import subprocess
    import sys
    import torch
    t_start = time.time()
    vol.reload()
    d = "/tmp/paket"
    zipfile.ZipFile(io.BytesIO(paket_zip)).extractall(d)
    jobs = json.loads(Path(d, "jobs.json").read_text(encoding="utf-8"))
    ref = jobs["ref"]
    ref_audio = Path(d, "ref", ref["datei"]).read_bytes()
    ref_pfad = str(Path(d, "ref", ref["datei"]))
    os.makedirs("/vol/out", exist_ok=True)
    def fertig(j):
        p = Path("/vol/out", j["key"] + ".json")
        if not p.exists():
            return False
        try:
            return j.get("audio") or json.loads(p.read_text(encoding="utf-8"))["info"].get("nach") == NACH
        except Exception:
            return False
    offen = [j for j in jobs["jobs"] if not fertig(j)]
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                         capture_output=True, text=True).stdout.strip()
    modell, cfg = modell_pruefen()
    commit = Path("/omni/COMMIT" if ENGINE == "sglang" else "/fish/COMMIT").read_text().strip()
    bericht = [f"GPU {gpu}", f"MODELL {modell} {json.dumps(cfg)}", f"ENGINE {ENGINE} {commit}",
               f"JOBS {len(jobs['jobs'])} offen {len(offen)}"]
    if modell != "drama-3" or not offen:
        bericht.append(f"WALL {time.time() - t_start:.1f} s")
        return "\n".join(bericht)
    proc, kalt = _server_starten()
    bericht.append(f"KALTSTART {time.time() - t_start:.1f} s (Server {kalt:.1f} s)")
    sys.path.insert(0, "/rl")
    os.environ["READLAYER_FA_DEVICE"] = "cuda"
    from fa_mms import Aligner
    al = Aligner()
    t_tts = time.time()

    def ein_block(j):
        t0 = time.time()
        if j.get("audio"):                         # nur Zeitmarken (Pruefblock: MMS_FA auf fremdes Audio)
            return j, _nach_24k(Path(d, j["audio"]).read_bytes()), 0.0
        extra = {k: j[k] for k in ("temperature", "top_p") if j.get(k) is not None}
        if ENGINE == "sglang":
            import numpy as np
            x = np.concatenate([_nach_24k(_tts_sglang(t, ref_pfad, ref.get("text") or "", extra))
                                for t in teile(j["text"])])
            return j, pegel(x), time.time() - t0
        wav = _tts(j["text"], ref_audio, ref.get("text") or "", int(j.get("seed") or 0) or None, extra)
        return j, pegel(_nach_24k(wav)), time.time() - t0

    fehler, n, audio_s, tts_s = [], 0, 0.0, 0.0
    with cf.ThreadPoolExecutor(PARALLEL) as ex:
        futs = [ex.submit(ein_block, j) for j in offen]
        for fu in cf.as_completed(futs):
            try:
                j, x, dt = fu.result()
            except Exception as e:
                fehler.append(f"{type(e).__name__}: {str(e)[:200]}")
                continue
            p = f"/vol/out/{j['key']}.wav"
            _schreiben(p, x)
            lw = [w["l"] for w in j["woerter"]]
            zeiten = al.ausrichten(p, lw) if lw else []
            woerter = [{"w": w["w"], "a": round(z[0], 3), "b": round(z[1], 3)}
                       for w, z in zip(j["woerter"], zeiten) if z]
            info = {"bytes": len(j["text"].encode("utf-8")), "sek": round(len(x) / SR, 2), "tts_s": round(dt, 1),
                    "fa_woerter": f"{len(woerter)}/{len(lw)}", "modell": modell, "zeitmarken": "mms_fa",
                    "nach": None if j.get("audio") else NACH}
            Path(f"/vol/out/{j['key']}.json").write_text(json.dumps({"woerter": woerter, "info": info},
                                                                     ensure_ascii=False), encoding="utf-8")
            n += 1
            if not j.get("audio"):                 # RTF nur ueber vertonte Bloecke (nicht reine FA-Jobs)
                audio_s += len(x) / SR
                tts_s += dt
            if n % 10 == 0:
                vol.commit()
                print(f"[fish] {n}/{len(offen)} Bloecke, {audio_s / 60:.1f} min Audio", flush=True)
    vol.commit()
    proc.terminate()
    rt = time.time() - t_tts
    bericht += [f"BLOECKE {n} fehler {len(fehler)}", f"AUDIO {audio_s:.1f} s", f"TTS {rt:.1f} s RTF "
                f"{rt / audio_s if audio_s else 0:.3f} (je Block {tts_s / audio_s if audio_s else 0:.3f}, {PARALLEL} parallel)",
                f"PEGEL {NACH} Sprache {SPRACH_RMS_DB} dBFS", f"WALL {time.time() - t_start:.1f} s"] + fehler[:20]
    if torch.cuda.is_available():
        bericht.append(f"VRAM_MAX {torch.cuda.max_memory_allocated() / 1e9:.1f} GB (nur FA-Prozess)")
    return "\n".join(bericht)


# ============================================================ lokal
@app.local_entrypoint()
def main(paket: str = "", gewichte_laden: bool = False):
    if gewichte_laden or not paket:
        print(gewichte.remote(), flush=True)
        if not paket:
            return
    q = HIER / paket
    jobs = json.loads((q / "jobs.json").read_text(encoding="utf-8"))
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(q / "jobs.json", "jobs.json")
        z.write(q / "ref" / jobs["ref"]["datei"], f"ref/{jobs['ref']['datei']}")
        for j in jobs["jobs"]:
            if j.get("audio"):
                z.write(q / j["audio"], j["audio"])
    print(f"[fish] {paket}: {len(jobs['jobs'])} Bloecke -> Modal ({', '.join(GPU)})", flush=True)
    if not vol_hat("/drama-3", "config.json"):
        print(gewichte.remote(), flush=True)
    bericht = vertonen.remote(bio.getvalue())
    out = q / "out"
    out.mkdir(exist_ok=True)
    geholt = 0
    for j in jobs["jobs"]:
        for end in (".json", ".wav"):
            try:
                daten = b"".join(vol.read_file(f"/out/{j['key']}{end}"))
            except Exception:
                break
            (out / f"{j['key']}{end}").write_bytes(daten)
        else:
            geholt += 1
    (q / "bericht.txt").write_text(bericht + f"\nGEHOLT {geholt}\n", encoding="utf-8")
    print(bericht, f"\nGEHOLT {geholt}/{len(jobs['jobs'])}", flush=True)


def vol_hat(ordner, name):
    try:
        return any(e.path.rstrip("/").endswith(name) for e in vol.listdir(ordner))
    except Exception:
        return False
