"""READ LAYER - AP 60 (27.10.2026): Hoerprobe woertliche Rede - Modal-Teil. Keine Aenderung an der Produktion.
1) fa_vc (L4, je Sprache): MMS_FA richtet A-Einheiten, B-Basis (Erzaehler) und Referenz aus und schneidet die
   Rede-Segmente; B: Rede-Segmente per Chatterbox VC auf die Figurenstimme (Stimmprobe = Gemini-Cast-Muster),
   wieder eingesetzt; je Variante eine durchgehende Datei, Lautheit einheitlich (ffmpeg loudnorm -18 LUFS).
2) sprache (L4): faster-whisper large-v3 Spracherkennung je Rede-Segment (A, B nach VC, Referenz).
Ergebnis: tests/ap60/ergebnis/<lg>_A_multispeaker.wav, <lg>_B_voiceconversion.wav, <lg>_Referenz.wav,
          tabelle.md, modal_bericht.json
Aufruf: py -3.11 -m modal run gpu_tts/ap60_modal.py   (vorher tools/ap60_gemini.py)
"""
import json, os, re, time, unicodedata
from pathlib import Path
import modal

HIER = Path(__file__).resolve().parent
T = HIER.parent / "tests" / "ap60"
PAUSE_S, LUFS = 0.6, -18
USD_H = 0.80  # L4

app = modal.App("readlayer-ap60")
vol = modal.Volume.from_name("readlayer-tts", create_if_missing=True)
img_cb = (modal.Image.debian_slim(python_version="3.11").apt_install("ffmpeg", "libsndfile1")
          .pip_install("chatterbox-tts", "huggingface_hub", "safetensors", "soundfile")
          .env({"HF_HOME": "/vol/hf", "TORCH_HOME": "/vol/torch", "PYTHONUNBUFFERED": "1"})
          .add_local_dir(str(T), remote_path="/t", ignore=lambda p: "ergebnis" in p.parts))


def _modell_laden():
    from huggingface_hub import snapshot_download
    snapshot_download("Systran/faster-whisper-large-v3", local_dir="/modell")


img_wh = (modal.Image.from_registry("nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04", add_python="3.11")
          .apt_install("ffmpeg").pip_install("faster-whisper==1.1.1", "huggingface_hub", "requests").run_function(_modell_laden))


def laut(text):
    """Text -> [(wort, laut)] fuer MMS_FA (romanisiert, a-z')."""
    out = []
    for m in re.finditer(r"[\w’']+", text):
        w = m.group().lower().replace("ß", "ss").replace("’", "'")
        w = "".join(c for c in unicodedata.normalize("NFD", w) if not unicodedata.combining(c))
        w = re.sub(r"[^a-z']", "", w).strip("'")
        if w:
            out.append(w)
    return out


@app.function(image=img_cb, gpu="L4", volumes={"/vol": vol}, timeout=3600)
def fa_vc(lg: str) -> dict:
    import io, subprocess, tempfile, wave
    import numpy as np, torch, torchaudio
    from torchaudio.pipelines import MMS_FA as B
    from chatterbox.vc import ChatterboxVC
    t0 = time.time()
    P = json.load(open("/t/passage.json", encoding="utf-8"))
    satz = {s["tid"]: s for s in P["saetze"]}
    fa_m, tok, ali = B.get_model().to("cuda"), B.get_tokenizer(), B.get_aligner()
    vc = ChatterboxVC.from_pretrained(device="cuda")
    SR = 24000

    def lesen(p):
        with wave.open(p, "rb") as w:
            sr, x = w.getframerate(), np.frombuffer(w.readframes(w.getnframes()), "<i2").astype("float32") / 32768
            if w.getnchannels() > 1:
                x = x.reshape(-1, w.getnchannels()).mean(1)
        if sr != SR:
            x = torchaudio.functional.resample(torch.from_numpy(x), sr, SR).numpy()
        return x

    def wavbytes(x, sr=SR):
        b = io.BytesIO()
        with wave.open(b, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
            w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
        return b.getvalue()

    def segmente(x, segs):
        """segs = [(tid, k, text, sprecher)] -> [(a, b)] Samplegrenzen je Segment (Schnitt in der Mitte der Luecke)."""
        woerter, zu = [], []
        for j, (_, _, t, _) in enumerate(segs):
            for w in laut(t):
                woerter.append(w); zu.append(j)
        x16 = torchaudio.functional.resample(torch.from_numpy(x), SR, 16000).unsqueeze(0).to("cuda")
        with torch.inference_mode():
            em, _ = fa_m(x16)
            sp = ali(em[0], tok(woerter))
        f = x16.shape[1] / em.shape[1] / 16000
        zeit = [(s[0].start * f, s[-1].end * f) for s in sp]
        ab = []
        for j in range(len(segs)):
            z = [zeit[i] for i in range(len(woerter)) if zu[i] == j]
            ab.append((min(a for a, _ in z), max(b for _, b in z)) if z else None)
        grenzen, n = [], len(x)
        for j, z in enumerate(ab):
            if z is None:
                grenzen.append(None); continue
            vor = next((ab[i] for i in range(j - 1, -1, -1) if ab[i]), None)
            nach = next((ab[i] for i in range(j + 1, len(ab)) if ab[i]), None)
            a = 0 if vor is None else (vor[1] + z[0]) / 2
            b = len(x) / SR if nach is None else (z[1] + nach[0]) / 2
            grenzen.append((int(a * SR), min(n, int(b * SR))))
        return grenzen

    def fade(x, ms=12):
        k = min(len(x) // 2, int(SR * ms / 1000))
        if k > 0:
            x = x.copy(); r = np.linspace(0, 1, k); x[:k] *= r; x[-k:] *= r[::-1]
        return x

    pause = np.zeros(int(SR * PAUSE_S), "float32")
    clips, laeufe, info = {}, {}, []
    # Takes je Variante: [(datei, [(tid, k, text, sprecher)])]
    takes = {
        "A": [(f"/t/{lg}/A/u{i:02d}.wav", [(tid, k, g["t"], g["s"]) for tid in e["tids"] for k, g in enumerate(satz[tid][lg])])
              for i, e in enumerate(P["einheiten"], 1)],
        "B": [(f"/t/{lg}/B_basis/{s['tid']}.wav", [(s["tid"], k, g["t"], g["s"]) for k, g in enumerate(s[lg])]) for s in P["saetze"]],
        "Referenz": [(f"/t/{lg}/ref/{s['tid']}.wav", [(s["tid"], k, g["t"], g["s"]) for k, g in enumerate(s[lg])]) for s in P["saetze"]],
    }
    vc_s = 0.0
    for v, liste in takes.items():
        teile = []
        for datei, segs in liste:
            if not os.path.exists(datei):
                info.append(f"{v}: fehlt {datei}"); continue
            x = lesen(datei)
            gr = segmente(x, segs)
            if v == "B":
                neu = []
                for (tid, k, t, s), g in zip(segs, gr):
                    if g is None:
                        continue
                    stueck = x[g[0]:g[1]]
                    if s != "Erzaehler":
                        t1 = time.time()
                        with tempfile.TemporaryDirectory() as td:
                            open(f"{td}/s.wav", "wb").write(wavbytes(stueck))
                            y = vc.generate(audio=f"{td}/s.wav", target_voice_path=f"/t/stimmproben/{s.replace(' ', '_')}_{lg}.wav")
                        y = y.reshape(-1).float().cpu().numpy()
                        if vc.sr != SR:
                            y = torchaudio.functional.resample(torch.from_numpy(y), vc.sr, SR).numpy()
                        stueck = y; vc_s += time.time() - t1
                    neu.append(fade(stueck))
                x = np.concatenate(neu) if neu else x
                gr = segmente(x, segs)   # Rede-Segmente nach VC neu schneiden (fuer Whisper)
            for (tid, k, t, s), g in zip(segs, gr):
                if s != "Erzaehler" and g is not None:
                    clips[f"{v}|{tid}|{k}"] = wavbytes(torchaudio.functional.resample(torch.from_numpy(x[g[0]:g[1]]), SR, 16000).numpy(), 16000)
            teile += [x, pause]
        roh = np.concatenate(teile[:-1]) if teile else np.zeros(1, "float32")
        with tempfile.TemporaryDirectory() as td:
            open(f"{td}/r.wav", "wb").write(wavbytes(roh))
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{td}/r.wav", "-af",
                            f"loudnorm=I={LUFS}:TP=-1.5:LRA=11", "-ar", str(SR), "-ac", "1", f"{td}/n.wav"], check=True)
            laeufe[v] = open(f"{td}/n.wav", "rb").read()
        info.append(f"{lg} {v}: {len(liste)} Takes, {len(roh) / SR:.1f} s")
    s = round(time.time() - t0, 1)
    return {"dateien": laeufe, "clips": clips, "info": info, "gpu_s": s, "vc_s": round(vc_s, 1)}


@app.function(image=img_wh, gpu="L4", timeout=1800)
def sprache(clips: dict) -> dict:
    import io, numpy as np, wave
    from faster_whisper import WhisperModel
    t0 = time.time()
    m = WhisperModel("/modell", device="cuda", compute_type="float16")
    out = {}
    for key, b in clips.items():
        with wave.open(io.BytesIO(b)) as w:
            a = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype("float32") / 32768
        segs, inf = m.transcribe(a, language=None, beam_size=1, without_timestamps=True, condition_on_previous_text=False)
        out[key] = {"top": inf.language, "probs": {k: round(float(p), 3) for k, p in (inf.all_language_probs or [])[:4]},
                    "text": " ".join(x.text.strip() for x in segs), "dauer": round(len(a) / 16000, 2)}
    return {"erg": out, "gpu_s": round(time.time() - t0, 1)}


@app.local_entrypoint()
def main():
    t0 = time.time()
    P = json.loads((T / "passage.json").read_text(encoding="utf-8"))
    ziel = T / "ergebnis"; ziel.mkdir(exist_ok=True)
    namen = {"A": "A_multispeaker", "B": "B_voiceconversion", "Referenz": "Referenz"}
    erg, clips, gpu, vc_s = {}, {}, 0.0, {}
    for lg, r in zip(("de", "en"), list(fa_vc.map(["de", "en"]))):
        for v, b in r["dateien"].items():
            (ziel / f"{lg}_{namen[v]}.wav").write_bytes(b)
        clips.update({f"{lg}|{k}": c for k, c in r["clips"].items()})
        gpu += r["gpu_s"]; vc_s[lg] = r["vc_s"]
        for z in r["info"]:
            print("[ap60]", z)
    print(f"[ap60] Hoerproben fertig, GPU {gpu:.0f} s, davon VC {vc_s} s -> Whisper", flush=True)
    w = sprache.remote(clips)
    gpu += w["gpu_s"]
    (ziel / "whisper.json").write_text(json.dumps(w["erg"], ensure_ascii=False, indent=1), encoding="utf-8")
    zeilen = ["| Sprache | Satz/Seg | Figur | Text | A | B | Referenz |", "|---|---|---|---|---|---|---|"]
    drift = {}
    for lg in ("de", "en"):
        for s in P["saetze"]:
            for k, g in enumerate(s[lg]):
                if g["s"] == "Erzaehler":
                    continue
                zelle = []
                for v in ("A", "B", "Referenz"):
                    e = w["erg"].get(f"{lg}|{v}|{s['tid']}|{k}")
                    if not e:
                        zelle.append("–"); continue
                    p = e["probs"].get(lg, 0.0)
                    d = e["top"] != lg or p < 0.5
                    drift.setdefault((lg, v), [0, 0]); drift[(lg, v)][0] += d; drift[(lg, v)][1] += 1
                    zelle.append(f"{'**ja**' if d else 'nein'} ({e['top']} {p:.2f})")
                zeilen.append(f"| {lg} | {s['tid'][5:]}/{k} | {g['s']} | {g['t'][:40]} | " + " | ".join(zelle) + " |")
    summe = {f"{lg}_{v}": f"{a}/{n}" for (lg, v), (a, n) in drift.items()}
    usd = round(gpu / 3600 * USD_H, 3)
    bericht = {"drift": summe, "gpu_s": round(gpu, 1), "vc_s": vc_s, "usd_modal": usd, "laufzeit_s": round(time.time() - t0, 1)}
    (ziel / "tabelle.md").write_text("Drift je Replik (Whisper large-v3; ja = Top-Sprache falsch oder p<0,5)\n\n" + "\n".join(zeilen)
                                      + f"\n\nSumme Drift: {summe}\nModal: GPU {gpu:.0f} s ~ {usd} $\n", encoding="utf-8")
    (ziel / "modal_bericht.json").write_text(json.dumps(bericht, ensure_ascii=False, indent=1), encoding="utf-8")
    print("[ap60]", json.dumps(bericht, ensure_ascii=False))
