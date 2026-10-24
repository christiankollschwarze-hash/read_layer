"""READ LAYER — Test "Stimmung einfangen, Klang tauschen" (23.10.2026).
Frage: Uebersteht die Stimmung eines fremden Sprechclips die Stimmumwandlung (Chatterbox VC) auf unsere Erzaehlerin?

Eingabe: gpu_tts/stimmung_vc_test/muster/<stimmung>_<frei>.<wav/mp3/m4a/webm/ogg>  (6-10 s, eine Person, ohne Musik/Hall)
         stimmung = wuetend | fluesternd | traurig | aengstlich | froehlich | erschrocken
Je Clip und Sprache (de, en) drei Dateien in gpu_tts/stimmung_vc_test/ergebnis/:
  <clip>_<lg>_1_margaret.wav   Margaret direkt, Standardregler (Vergleich)
  <clip>_<lg>_2_fremd.wav      Testsatz mit dem Clip als Referenz (Stimmung + fremder Klang)
  <clip>_<lg>_3_umgewandelt.wav  2 per Chatterbox VC in Margarets Klang  <- darauf kommt es an
Aufruf: py -3.11 -m modal run gpu_tts/stimmung_vc_test.py
"""
import json, os, sys
from pathlib import Path
import modal

HIER = Path(__file__).resolve().parent
LESER = HIER.parent
TEST = HIER / "stimmung_vc_test"
ZIEL = "grossmutter_a"   # Margaret

SAETZE = {  # aus Testset v0.1, ohne Markup
    "wuetend": ("Ich habe dir gesagt, dass du die Tür nicht offen lassen sollst, und du hast es schon wieder vergessen!",
                "I told you twice not to touch the lock, and now the whole door is ruined!"),
    "fluesternd": ("Leise jetzt, sie schlafen noch. Wenn wir die Treppe hinunter wollen, müssen wir an der dritten Stufe vorbei.",
                   "Quiet now, they are still asleep. If we want to get down the stairs, we have to pass the third step."),
    "traurig": ("Das Haus war leer, nur der Stuhl am Fenster stand noch dort, wo sie immer gesessen hatte.",
                "The last train had gone, and she stood alone on the platform, holding a ticket for nowhere."),
    "aengstlich": ("Im Keller hat sich etwas bewegt. Ich habe es zweimal gehört, und beide Male war es näher als zuvor.",
                   "Something moved in the cellar. I heard it twice, and both times it was closer than before."),
    "froehlich": ("Endlich Ferien! Wir packen die Koffer, wir nehmen den frühen Zug, und heute Abend sitzen wir am Meer.",
                  "Finally, holidays! We pack our bags, we take the early train, and tonight we sit by the sea."),
    "ueberrascht": ("Du bist den ganzen Weg gekommen? Ich hatte keine Ahnung, ich dachte wirklich, du wärst noch im Ausland!",
                    "You came all this way? I had no idea, I really thought you were still abroad!"),
    "muede": ("Ich habe seit Tagen nicht richtig geschlafen, und die Buchstaben auf der Seite rutschen mir immer wieder weg.",
              "I haven't slept properly in days, and the letters on the page keep sliding away from me."),
    "feierlich": ("Und so, in der letzten Nacht des alten Königreichs, läuteten die Glocken über den stillen Türmen.",
                  "And so, upon the last night of the old kingdom, the bells rang out over the silent towers."),
    "freundlich": ("Guten Morgen! Komm herein, setz dich, ich stelle den Wasserkessel auf. Du musst ja ganz durchgefroren sein.",
                   "Good morning! Come in, sit down, and let me put the kettle on. You must be freezing."),
    "nachdenklich": ("Vielleicht war es gar nicht der Zufall, der uns hierher geführt hat, sondern etwas, das wir nicht sehen konnten.",
                     "Perhaps it was not chance that brought us here, but something we could not see."),
    "liebevoll": ("Komm her, mein Kleiner. Es ist alles gut, ich bin ja da, und morgen früh gehen wir zusammen zu den Enten.",
                  "Come here, my little one. Everything is fine, I am here, and tomorrow morning we will go to see the ducks."),
    "verschmitzt": ("Natürlich habe ich nichts gesehen. Ich war ja die ganze Zeit hier, genau neben dem leeren Kuchenteller.",
                    "Of course I didn't see anything. I was right here the whole time, next to the empty cake plate."),
    "ironisch": ("Oh, großartig. Noch ein Meeting, das auch eine E-Mail hätte sein können.",
                 "Oh, wonderful. Another meeting that could have been an email."),
    "erschrocken": ("Hinter ihm krachte die Tür ins Schloss, und im selben Augenblick erlosch das Licht!",
                    "Behind him the door slammed shut, and at the same moment the light went out!"),
}


def _hf_token():
    tok = os.environ.get("HF_TOKEN", "")
    env = LESER / ".env"
    if not tok and env.exists():
        for z in env.read_text(encoding="utf-8").splitlines():
            if z.strip().startswith("HF_TOKEN="):
                tok = z.split("=", 1)[1].strip().strip('"')
    return tok


app = modal.App("readlayer-stimmung-vc-test")
vol = modal.Volume.from_name("readlayer-tts", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libsndfile1")
    .pip_install("chatterbox-tts", "huggingface_hub", "safetensors")
    .env({"HF_HOME": "/vol/hf", "TORCH_HOME": "/vol/torch"})
    .add_local_file(str(HIER / "cb_batch.py"), remote_path="/code/cb_batch.py")
    .add_local_file(str(LESER / "gpu_lora" / "lora_kern.py"), remote_path="/code/lora_kern.py")
    .add_local_dir(str(TEST), remote_path="/test", ignore=lambda p: "ergebnis" in p.parts)
)


def emodb_clips(sprecher: str, info: list) -> list:
    """Emo-DB (TU Berlin, Schauspieler, DE): Download einmalig ins Volume; je Sprecher und Stimmung
    mehrere Aeusserungen (gleicher Sprecher, gleiche Emotion) zu einem Clip bis 10 s verketten."""
    import glob, subprocess, urllib.request, zipfile
    basis = "/vol/emodb"
    if not glob.glob(f"{basis}/wav/*.wav"):
        os.makedirs(basis, exist_ok=True)
        lokal = glob.glob("/test/*.zip")      # manuell geladen: gpu_tts/stimmung_vc_test/download.zip
        if lokal:
            zipfile.ZipFile(lokal[0]).extractall(basis)
        else:
            urllib.request.urlretrieve("http://emodb.bilderbar.info/download/download.zip", f"{basis}/emodb.zip")
            zipfile.ZipFile(f"{basis}/emodb.zip").extractall(basis)
        if not glob.glob(f"{basis}/wav/*.wav"):           # Zip mit anderem Ordneraufbau
            for w in glob.glob(f"{basis}/**/*.wav", recursive=True):
                os.makedirs(f"{basis}/wav", exist_ok=True)
                os.replace(w, f"{basis}/wav/{os.path.basename(w)}")
        vol.commit()
    info.append(f"emodb: {len(glob.glob(basis + '/wav/*.wav'))} Dateien im Volume")
    code = {"W": "wuetend", "T": "traurig", "A": "aengstlich", "F": "froehlich"}
    clips = []
    for sp in sprecher.split(","):
        for c, stimmung in code.items():
            teile = sorted(glob.glob(f"{basis}/wav/{sp.strip()}*{c}?.wav"))
            if not teile:
                info.append(f"emodb {sp}{c}: keine Dateien")
                continue
            ziel = f"/tmp/clips/{stimmung}_emodb{sp.strip()}.wav"
            liste = f"/tmp/clips/{stimmung}_{sp}.txt"
            stille = "/tmp/clips/stille.wav"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                            "-t", "0.25", stille], check=True)
            with open(liste, "w") as f:
                for t in teile[:6]:
                    norm = t.replace(".wav", "_24k.wav").replace(basis + "/wav", "/tmp/clips")
                    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", t, "-ac", "1", "-ar", "24000", norm], check=True)
                    f.write(f"file '{norm}'\nfile '{stille}'\n")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", liste, "-t", "10", ziel],
                           check=True)
            clips.append(ziel)
    return clips


@app.function(image=image, gpu="L4", volumes={"/vol": vol}, timeout=3600,
              secrets=[modal.Secret.from_dict({"HF_TOKEN": _hf_token()})])
def lauf(tempo: float = 0.91, emodb: str = "") -> dict:
    import glob, io, random, subprocess, tempfile, time
    import numpy as np, torch, torchaudio
    sys.path.insert(0, "/code")
    import chatterbox.mtl_tts as mtl
    from chatterbox.vc import ChatterboxVC
    from cb_batch import sprech_norm
    import lora_kern
    mtl.punc_norm = sprech_norm
    t0 = time.time()
    tts = {"en": mtl.ChatterboxMultilingualTTS.from_pretrained(device="cuda")}
    tts["de"] = mtl.ChatterboxMultilingualTTS.from_pretrained(device="cuda")
    lora_kern.einmischen(tts["de"].t3, "/vol/lora/adapter/mix_v1.safetensors", 1.0)   # Standard DE
    vc = ChatterboxVC.from_pretrained(device="cuda")
    ziel = {lg: f"/test/ref_{ZIEL}_{lg}.wav" for lg in ("de", "en")}

    def wav_bytes(w, sr):
        with tempfile.TemporaryDirectory() as td:
            torchaudio.save(f"{td}/r.wav", w.reshape(1, -1).float().cpu().clamp(-1, 1), sr, encoding="PCM_S", bits_per_sample=16)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{td}/r.wav", "-filter:a", f"atempo={tempo}",
                            f"{td}/f.wav"], check=True)
            return open(f"{td}/f.wav", "rb").read()

    def gen(lg, text, ref):
        torch.manual_seed(1234); random.seed(1234); np.random.seed(1234)
        return tts[lg].generate(text, language_id=lg, audio_prompt_path=ref)

    aus, info = {}, []
    os.makedirs("/tmp/clips", exist_ok=True)
    quellen = [p for p in sorted(glob.glob("/test/muster/*")) if Path(p).suffix.lower() in
               (".wav", ".mp3", ".m4a", ".ogg", ".opus", ".webm", ".flac", ".aac", ".mp4")]
    print(f"[stimmung] emodb={emodb!r}, eigene Clips={len(quellen)}", flush=True)
    if emodb:
        quellen += emodb_clips(emodb, info)
    if not quellen:
        info.append("keine Clips gefunden (muster leer, Emo-DB aus)")
    margaret = {}
    for quelle in quellen:          # jedes Format -> WAV mono 24 kHz, hoechstens 10 s
        name = Path(quelle).stem
        clip = f"/tmp/clips/{name}.wav"
        if quelle != clip:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", quelle, "-t", "10", "-ac", "1", "-ar", "24000", clip],
                           check=True)
        stimmung = name.split("_")[0]
        if stimmung not in SAETZE:
            info.append(f"{name}: Stimmung unbekannt, uebersprungen")
            continue
        aus[f"{name}_0_quelle.wav"] = open(clip, "rb").read()
        for i, lg in enumerate(("de", "en")):
            text = SAETZE[stimmung][i]
            sr = tts[lg].sr
            if (stimmung, lg) not in margaret:
                margaret[(stimmung, lg)] = wav_bytes(gen(lg, text, ziel[lg]), sr)
                aus[f"{stimmung}_{lg}_1_margaret.wav"] = margaret[(stimmung, lg)]
            w2 = gen(lg, text, clip)
            with tempfile.TemporaryDirectory() as td:
                torchaudio.save(f"{td}/f.wav", w2.reshape(1, -1).float().cpu(), sr)
                w3 = vc.generate(audio=f"{td}/f.wav", target_voice_path=ziel[lg])
            aus[f"{name}_{lg}_2_fremd.wav"] = wav_bytes(w2, sr)
            aus[f"{name}_{lg}_3_umgewandelt.wav"] = wav_bytes(w3, vc.sr)
            info.append(f"{name} {lg} fertig")
            print(info[-1], flush=True)
    s = round(time.time() - t0, 1)
    return {"dateien": aus, "info": info, "gpu_s": s, "usd": round(s / 3600 * 0.80, 3)}


@app.local_entrypoint()
def main(emodb: str = "08,03"):
    emodb = "" if emodb.strip() in ("-", "") else emodb.strip()
    print(f"[stimmung] Emo-DB-Sprecher: {emodb or 'keine'} | eigene Clips: {len(list((TEST / 'muster').glob('*')))}")
    erg = lauf.remote(emodb=emodb)
    ziel = TEST / "ergebnis"
    ziel.mkdir(exist_ok=True)
    for n, b in erg["dateien"].items():
        (ziel / n).write_bytes(b)
    print(f"[stimmung] {len(erg['dateien'])} WAVs -> {ziel} | GPU {erg['gpu_s']} s, ca. {erg['usd']} $")
    for z in erg["info"]:
        print("[stimmung]", z)
