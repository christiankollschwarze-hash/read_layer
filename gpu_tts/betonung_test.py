"""READ LAYER — Wortbetonung + Textpausen mit Chatterbox (23.10.2026, v2).
Kette je Variante: Emoji-Vorlage (stimmen_archiv/_emoji/<stimmung>_<lg>.wav, neutral = Margaret) als Referenz JE CHUNK
-> Chatterbox -> Stille an | || ||| (250/600/1200 ms, 🤔 x1,5) -> Chatterbox VC auf Margaret -> bei 🤫 Fluestertrick.
Betonung (*Wort*), nur Chatterbox, keine Einzelwort-Chunks:
  a_ohne          ohne Pausen/Betonungshilfe (Vergleich)
  b_pause         Denkpause vor dem Wort ("dass ... er")
  c_strich        Gedankenstriche ("dass — er — das")
  d_split         Chunk endet auf dem betonten Wort (+ exaggeration), Vorlage je Chunk
  e_split_pause   wie d, mit "..." vor dem Wort
Pausen (|):
  a_ohne          Satz am Stueck, Pausenzeichen entfernt
  p_split         Chunk-Split an |, Vorlage je Chunk, Stille eingesetzt
  p_split_betont  wie p_split, zusaetzlich Betonung wie d_split (nur Saetze mit *Wort*)
Aufruf: py -3.11 -m modal run gpu_tts/betonung_test.py
Ergebnis: gpu_tts/stimmung_vc_test/ergebnis_betonung/<satz>/<variante>.wav + texte.json
"""
import json, os, re, sys
from pathlib import Path
import modal

HIER = Path(__file__).resolve().parent
LESER = HIER.parent
TEST = HIER / "stimmung_vc_test"
EMOJI = LESER / "stimmen_archiv" / "_emoji"
PAUSE_MS = {1: 250, 2: 600, 3: 1200}

SAETZE = [  # id, lang, stimmung (None = neutral), Markup
    ("B_DE04_gesagt", "de", "wuetend", "Ich habe dir *gesagt*, dass du die Tür nicht offen lassen sollst, und du hast es *schon wieder* vergessen!"),
    ("B_DE_er", "de", None, "Ich habe nicht gesagt, dass *er* das Geld gestohlen hat. Ich habe nur gesagt, dass es jemand getan hat."),
    ("B_DE_nicht", "de", None, "Das ist *nicht* dein Ernst. Du willst wirklich heute noch los?"),
    ("B_EN07_twice", "en", "wuetend", "I told you *twice* not to touch the lock, and now the whole door is ruined!"),
    ("B_EN12_he", "en", None, "I did not say *he* stole the money. I only said that someone did."),
    ("B_EN_your", "en", None, "It was not my idea, it was *your* idea, and you know it."),
    ("P_DE05_leise", "de", "fluesternd", "Leise jetzt, || sie schlafen noch. Wenn wir die Treppe hinunter wollen, müssen wir an der dritten Stufe vorbei."),
    ("P_DE07_vielleicht", "de", "nachdenklich", "Vielleicht | war es gar nicht der Zufall, || der uns hierher geführt hat, | sondern etwas, das wir nicht sehen konnten."),
    ("P_DE_ernst", "de", "wuetend", "Das ist ||| *nicht* dein Ernst!"),
    ("P_EN05_kingdom", "en", "feierlich", "And so, upon the last night of the old kingdom, || the bells rang out over the silent towers."),
    ("P_EN14_wait", "en", "aengstlich", "Wait. || Listen. ||| Now run, run, run, before they close the gates behind us!"),
    ("P_EN_quiet", "en", "fluesternd", "Quiet now. || They are still asleep. | If we want to get down the stairs, we have to pass the third step."),
]


def _betonung(markup, mit_pause):
    """Chunks, die jeweils auf einem betonten Wort enden."""
    teile, rest = [], markup
    while "*" in rest:
        vor, wort, rest = re.match(r"^(.*?)\*([^*]+)\*(.*)$", rest, re.S).groups()
        vor = vor.strip()
        if teile and vor[:1] in ",;:":
            teile[-1] = (teile[-1][0] + vor[0], True)
            vor = vor[1:].strip()
        if mit_pause and vor:
            vor += " ..."
        teile.append(((vor + " " + wort).strip(), True))
    rest = rest.strip()
    if teile and rest[:1] in ",;:.!?":
        teile[-1] = (teile[-1][0] + rest[0], True)
        rest = rest[1:].strip()
    if rest:
        teile.append((rest, False))
    # kein Einzelwort-Chunk: betontes Wort am Chunk-Anfang mit dem Folgetext zusammenlassen
    while len(teile) > 1 and teile[0][1] and len(teile[0][0].split()) == 1:
        teile = [(teile[0][0] + " " + teile[1][0], True)] + teile[2:]
    return teile


def varianten(markup, faktor=1.0):
    """-> {variante: [ (text, betont) | ("PAUSE", ms) ]}"""
    ohne_pause = re.sub(r"\s*\|{1,3}\s*", " ", markup).strip()
    plain = ohne_pause.replace("*", "")
    v = {"a_ohne": [(plain, False)]}
    if "|" not in markup:
        b = re.sub(r"(\S+)\s+\*([^*]+)\*", r"\1 ... \2", markup).replace("*", "")
        c = re.sub(r"\s+", " ", re.sub(r"\s*\*([^*]+)\*\s*,?", r" — \1 — ", markup).replace("*", ""))
        v.update({"b_pause": [(b, False)], "c_strich": [(c, False)],
                  "d_split": _betonung(markup, False), "e_split_pause": _betonung(markup, True)})
        return v
    for name, betont in (("p_split", False), ("p_split_betont", True)):
        if betont and "*" not in markup:
            continue
        folge = []
        for i, stueck in enumerate(re.split(r"(\|{1,3})", markup)):
            if stueck.startswith("|"):
                folge.append(("PAUSE", int(PAUSE_MS[len(stueck)] * faktor)))
            elif stueck.strip():
                folge += _betonung(stueck.strip(), False) if betont else [(stueck.strip().replace("*", ""), False)]
        v[name] = folge
    return v


def _hf_token():
    tok = os.environ.get("HF_TOKEN", "")
    env = LESER / ".env"
    if not tok and env.exists():
        for z in env.read_text(encoding="utf-8").splitlines():
            if z.strip().startswith("HF_TOKEN="):
                tok = z.split("=", 1)[1].strip().strip('"')
    return tok


app = modal.App("readlayer-betonung-test")
vol = modal.Volume.from_name("readlayer-tts", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libsndfile1")
    .pip_install("chatterbox-tts", "huggingface_hub", "safetensors", "pyworld", "soundfile", "scipy")
    .env({"HF_HOME": "/vol/hf", "TORCH_HOME": "/vol/torch"})
    .add_local_file(str(HIER / "cb_batch.py"), remote_path="/code/cb_batch.py")
    .add_local_file(str(LESER / "gpu_lora" / "lora_kern.py"), remote_path="/code/lora_kern.py")
    .add_local_file(str(LESER / "tools" / "fluestern.py"), remote_path="/code/fluestern.py")
    .add_local_file(str(TEST / "ref_grossmutter_a_de.wav"), remote_path="/ref/margaret_de.wav")
    .add_local_file(str(TEST / "ref_grossmutter_a_en.wav"), remote_path="/ref/margaret_en.wav")
    .add_local_dir(str(EMOJI), remote_path="/emoji")
)


@app.function(image=image, gpu="L4", volumes={"/vol": vol}, timeout=3600,
              secrets=[modal.Secret.from_dict({"HF_TOKEN": _hf_token()})])
def lauf(tempo: float = 0.91) -> dict:
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
    tts = {"en": mtl.ChatterboxMultilingualTTS.from_pretrained(device="cuda"),
           "de": mtl.ChatterboxMultilingualTTS.from_pretrained(device="cuda")}
    lora_kern.einmischen(tts["de"].t3, "/vol/lora/adapter/mix_v1.safetensors", 1.0)
    vc = ChatterboxVC.from_pretrained(device="cuda")
    aus, plan = {}, {}
    for sid, lg, st, markup in SAETZE:
        ref = f"/emoji/{st}_{lg}.wav" if st else f"/ref/margaret_{lg}.wav"
        m = tts[lg]
        for v, folge in varianten(markup, 1.5 if st == "nachdenklich" else 1.0).items():
            stuecke = []
            for text, wert in folge:
                if text == "PAUSE":
                    stuecke.append(torch.zeros(int(m.sr * wert / 1000)))
                    continue
                torch.manual_seed(1234); random.seed(1234); np.random.seed(1234)
                w = m.generate(text, language_id=lg, audio_prompt_path=ref,      # Vorlage JE CHUNK
                               exaggeration=0.7 if wert else 0.5).float().cpu().reshape(-1)
                laut = (w.abs() > 10 ** (-40 / 20)).nonzero()
                if len(laut) and len(folge) > 1:
                    w = w[max(0, int(laut[0]) - 720): int(laut[-1]) + 720]
                stuecke.append(w)
                stuecke.append(torch.zeros(int(m.sr * 0.06)))
            w = torch.cat(stuecke[:-1]).clamp(-1, 1)
            with tempfile.TemporaryDirectory() as td:
                torchaudio.save(f"{td}/r.wav", w.reshape(1, -1), m.sr)
                if st:                                     # Klangtausch auf Margaret (neutral: ist schon Margaret)
                    w2 = vc.generate(audio=f"{td}/r.wav", target_voice_path=f"/ref/margaret_{lg}.wav")
                    torchaudio.save(f"{td}/r.wav", w2.reshape(1, -1).float().cpu().clamp(-1, 1), vc.sr)
                if st == "fluesternd":                     # Fluestertrick als letzter Schritt
                    x, sr = sf.read(f"{td}/r.wav")
                    sf.write(f"{td}/r.wav", fluestern(x, sr), sr)
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{td}/r.wav", "-ac", "1", "-c:a", "pcm_s16le",
                                "-filter:a", f"atempo={tempo}", f"{td}/f.wav"], check=True)
                aus[f"{sid}/{v}.wav"] = open(f"{td}/f.wav", "rb").read()
            plan[f"{sid}/{v}"] = [f"<{x} ms>" if t == "PAUSE" else (t + (" [betont]" if x else "")) for t, x in folge]
        print(f"[betonung] {sid} fertig", flush=True)
    s = round(time.time() - t0, 1)
    return {"dateien": aus, "plan": plan, "gpu_s": s, "usd": round(s / 3600 * 0.80, 3)}


@app.local_entrypoint()
def main():
    erg = lauf.remote()
    ziel = TEST / "ergebnis_betonung"
    for n, b in erg["dateien"].items():
        (ziel / n).parent.mkdir(parents=True, exist_ok=True)
        (ziel / n).write_bytes(b)
    (ziel / "texte.json").write_text(json.dumps(erg["plan"], ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[betonung] {len(erg['dateien'])} WAVs -> {ziel} | GPU {erg['gpu_s']} s, ca. {erg['usd']} $")
