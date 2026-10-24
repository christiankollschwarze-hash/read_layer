"""READ LAYER — Hoertest mix_v1 vs. mix_v2 mit Emoji-Weg (CK 24.10.2026).
Text: Machen, "Der große Gott Pan", Kap. 1 Schluss (c001_00122-00160: Marys Experiment), DE-Uebersetzung aus 310_uebersetzung.json.
Regie: DeepSeek ordnet je Satz eine Stimmung der Emoji-Bibliothek zu (sparsam, sonst neutral) -> gpu_tts/pan_test/regie.json (gecacht).
Kette je Satz: Emoji-Vorlage (stimmen_archiv/_emoji/<stimmung>_de.wav; neutral = Werkstimme) -> Chatterbox DE + LoRA
-> VC auf Werkstimme -> bei fluesternd Fluestertrick. Gleicher Zufallsstartwert je Satz in allen Varianten.
Varianten: grandma_mix_v1, grandma_mix_v2, herr_a_mix_v1, herr_a_mix_v2.
Aufruf: start_pan_test.bat   Ergebnis: gpu_tts/pan_test/<variante>/NN_<stimmung>.wav, szene_<variante>.wav, hoerliste.txt
"""
import json, os, sys
from pathlib import Path
import modal

HIER = Path(__file__).resolve().parent
LESER = HIER.parent
ZIEL = HIER / "pan_test"
EMOJI = LESER / "stimmen_archiv" / "_emoji"
BUCH = LESER / "authors" / "machen-a" / "books" / "the-great-god-pan" / "work"
VON, BIS = 122, 160
ADAPTER = {"mix_v1": "/vol/lora/adapter/mix_v1.safetensors",
           "mix_v2": "/vol/lora/mix_v2/ckpt/step_01250.safetensors"}
STIMMEN = {"grandma": "/ref/grandma.wav", "herr_a": "/ref/herr_a.wav"}
# CK 24.10. 09:39: Prosodie kaum hoerbar -> Regler fuer Saetze MIT Stimmung aufdrehen (neutral bleibt 0.5 / 0.5 / 0.8)
EXAG_EMO, CFG_EMO, TEMP_EMO = 1.0, 0.3, 0.9     # exaggeration hoch, cfg niedrig (folgt der Vorlage staerker), etwas mehr Varianz


def _hf_token():
    tok = os.environ.get("HF_TOKEN", "")
    env = LESER / ".env"
    if not tok and env.exists():
        for z in env.read_text(encoding="utf-8").splitlines():
            if z.strip().startswith("HF_TOKEN="):
                tok = z.split("=", 1)[1].strip().strip('"')
    return tok


app = modal.App("readlayer-pan-test")
vol = modal.Volume.from_name("readlayer-tts", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libsndfile1")
    .pip_install("chatterbox-tts", "huggingface_hub", "safetensors", "pyworld", "soundfile", "scipy")
    .env({"HF_HOME": "/vol/hf", "TORCH_HOME": "/vol/torch"})
    .add_local_file(str(HIER / "cb_batch.py"), remote_path="/code/cb_batch.py")
    .add_local_file(str(LESER / "gpu_lora" / "lora_kern.py"), remote_path="/code/lora_kern.py")
    .add_local_file(str(LESER / "tools" / "fluestern.py"), remote_path="/code/fluestern.py")
    .add_local_file(str(HIER / "stimmung_vc_test" / "ref_grossmutter_a_de.wav"), remote_path="/ref/grandma.wav")
    .add_local_file(str(LESER / "stimmen_archiv" / "herr_a" / "muster_de.wav"), remote_path="/ref/herr_a.wav")
    .add_local_dir(str(EMOJI), remote_path="/emoji")
)


@app.function(image=image, gpu="L4", volumes={"/vol": vol}, timeout=3600,
              secrets=[modal.Secret.from_dict({"HF_TOKEN": _hf_token()})])
def lauf(saetze: list, tempo: float = 0.91) -> dict:
    import random, subprocess, tempfile, time
    import numpy as np, torch, torchaudio, soundfile as sf
    sys.path.insert(0, "/code")
    import chatterbox.mtl_tts as mtl
    from chatterbox.vc import ChatterboxVC
    from cb_batch import sprech_norm
    from fluestern import fluestern
    import lora_kern
    mtl.punc_norm = sprech_norm
    t0 = time.time()
    vc = ChatterboxVC.from_pretrained(device="cuda")
    aus = {}
    for aname, apfad in ADAPTER.items():
        m = mtl.ChatterboxMultilingualTTS.from_pretrained(device="cuda")
        lora_kern.einmischen(m.t3, apfad, 1.0)
        for sname, sref in STIMMEN.items():
            var = f"{sname}_{aname}"
            for nr, (sid, text, st) in enumerate(saetze, 1):
                ref = f"/emoji/{st}_de.wav" if st else sref
                torch.manual_seed(1000 + nr); random.seed(1000 + nr); np.random.seed(1000 + nr)
                kw = dict(exaggeration=EXAG_EMO, cfg_weight=CFG_EMO, temperature=TEMP_EMO) if st else \
                    dict(exaggeration=0.5, cfg_weight=0.5, temperature=0.8)
                w = m.generate(text, language_id="de", audio_prompt_path=ref, **kw).float().cpu().reshape(1, -1)
                with tempfile.TemporaryDirectory() as td:
                    torchaudio.save(f"{td}/r.wav", w.clamp(-1, 1), m.sr)
                    if st:                                  # Klangtausch auf Werkstimme
                        w2 = vc.generate(audio=f"{td}/r.wav", target_voice_path=sref)
                        torchaudio.save(f"{td}/r.wav", w2.reshape(1, -1).float().cpu().clamp(-1, 1), vc.sr)
                    if st == "fluesternd":
                        x, sr = sf.read(f"{td}/r.wav")
                        sf.write(f"{td}/r.wav", fluestern(x, sr), sr)
                    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{td}/r.wav", "-ac", "1", "-ar", "24000",
                                    "-c:a", "pcm_s16le", "-filter:a", f"atempo={tempo}", f"{td}/f.wav"], check=True)
                    aus[f"{var}/{nr:02d}_{st or 'neutral'}.wav"] = open(f"{td}/f.wav", "rb").read()
            print(f"[pan] {var} fertig ({round(time.time() - t0)} s)", flush=True)
        del m
        torch.cuda.empty_cache()
    s = round(time.time() - t0, 1)
    return {"dateien": aus, "gpu_s": s, "usd": round(s / 3600 * 0.80, 3)}


def _saetze():
    d = json.loads((BUCH / "310_uebersetzung.json").read_text(encoding="utf-8"))["content"]
    out = []
    for k, v in d.items():
        if k.startswith("c001_") and VON <= int(k.split("_")[1]) <= BIS and isinstance(v, dict) and v.get("de"):
            out.append((k, v["de"]))
    return out


def _regie(saetze):
    pf = ZIEL / "regie.json"
    if pf.exists():
        return json.loads(pf.read_text(encoding="utf-8"))
    sys.path.insert(0, str(LESER))
    from config import config
    from pipeline import api_layer
    bib = json.loads((EMOJI / "emoji_bibliothek.json").read_text(encoding="utf-8"))
    st = sorted({(e["emoji"], e["stimmung"]) for e in bib["eintraege"] if e["sprache"] == "de"}, key=lambda x: x[1])
    liste = "\n".join(f"- {s} {e}" for e, s in st)
    text = "\n".join(f"{k}: {t}" for k, t in saetze)
    prompt = f"""Du bist Hoerbuch-Regisseur. Ordne jedem Satz dieser Szene (Arthur Machen, "Der große Gott Pan", Gothic-Horror,
ruhiger Erzaehler) eine Sprechstimmung zu. Erlaubt sind NUR diese Stimmungen:
{liste}
- neutral 😐 (Standard, ruhiger Erzaehlton)
Regeln: sparsam! Neutral ist der Normalfall fuer Erzaehltext. Eine Stimmung nur, wenn der Satz sie klar traegt
(woertliche Rede einer Figur, Hoehepunkt, Schrecken). Kein Horror-Overacting beim Erzaehler.
Antworte NUR mit JSON: {{"<satz-id>": "<stimmung>", ...}} fuer alle Saetze.

{text}"""
    raw = api_layer.call_model("aligner", prompt, max_tokens=4000)
    r = api_layer.parse_json(raw) or {}
    erlaubt = {s for _, s in st}
    r = {k: (r.get(k) if r.get(k) in erlaubt else None) for k, _ in saetze}
    ZIEL.mkdir(parents=True, exist_ok=True)
    pf.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    return r


@app.local_entrypoint()
def main():
    saetze = _saetze()
    regie = _regie(saetze)
    sys.path.insert(0, str(LESER))
    from tools.tts_paket import lexikon, lex_text       # Aussprache-Lexikon wie Pipeline (auch ungeprueft, da Test)
    lex = lexikon(str(BUCH.parent), "de", erzwingen=True)
    if not lex:
        sys.exit("[pan] FEHLER: kein Aussprache-Lexikon -> erst py -3.11 tools/aussprache_lexikon.py the-great-god-pan de")
    print(f"[pan] Aussprache-Lexikon: {len(lex)} Eintraege", flush=True)
    plan = [(k, lex_text(t, lex), regie.get(k)) for k, t in saetze]
    print(f"[pan] {len(plan)} Saetze, mit Stimmung: {sum(1 for p in plan if p[2])}", flush=True)
    erg = lauf.remote(plan)
    for n, b in erg["dateien"].items():
        (ZIEL / n).parent.mkdir(parents=True, exist_ok=True)
        (ZIEL / n).write_bytes(b)
    import wave
    for var in sorted({n.split("/")[0] for n in erg["dateien"]}):   # ganze Szene am Stueck, 400 ms Luft
        teile = sorted((ZIEL / var).glob("*.wav"))
        with wave.open(str(ZIEL / f"szene_{var}.wav"), "wb") as o:
            o.setnchannels(1); o.setsampwidth(2); o.setframerate(24000)
            for t in teile:
                with wave.open(str(t)) as i:
                    o.writeframes(i.readframes(i.getnframes()))
                o.writeframes(b"\x00\x00" * 9600)
    zeilen = ["Hoerliste Pan-Test (je Satz: grandma v1 / v2, herr_a v1 / v2)", ""]
    for nr, (k, t, st) in enumerate(plan, 1):
        zeilen.append(f"{nr:02d} [{st or 'neutral'}] {t}")
    (ZIEL / "hoerliste.txt").write_text("\n".join(zeilen), encoding="utf-8")
    print(f"[pan] {len(erg['dateien'])} WAVs -> {ZIEL} | GPU {erg['gpu_s']} s, ca. {erg['usd']} $")
