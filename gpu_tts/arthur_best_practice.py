"""READ LAYER — Best-Practice-Lauf mit anderer Werkstimme (herr_a = Arthur), 23.10.2026.
Regeln aus den Tests 23.10. (PROJEKTSTAND 0e-0g):
  - Stimmung: Emoji-Vorlage stimmen_archiv/_emoji/<stimmung>_<lg>.wav als Referenz JE CHUNK -> Chatterbox -> VC auf Arthur
  - neutral: Arthur direkt als Referenz (kein VC)
  - Pausen | || |||: Split, ausser ein Nachbar-Chunk ist ein kurzer ganzer Satz (< 4 Woerter, endet auf .!?) -> dann am Stueck
    (Test: 'Wait.'/'Quiet now.' verloren, 'Leise jetzt,'/'Das ist' gewannen)
  - *Wort*: nur Kontrast kurzer Woerter (<= 3 Buchstaben) als "... Wort" am Chunk-Ende (e_split_pause), sonst ignoriert
  - Chunk-Enden per Forced Alignment (cb_pruefung, MMS_FA): Nachklang/Vorlauf/verschmiert -> bis 2x neu, dann hinter letztem Wort kappen
  - 🤫: Fluestertrick (tools/fluestern.py, Standard) als letzter Schritt nach VC
  - Tempo 0,91 (Projektstandard)
Aufruf: py -3.11 -m modal run gpu_tts/arthur_best_practice.py [--stimme herr_a]
Ergebnis: gpu_tts/stimmung_vc_test/ergebnis_<stimme>/<Stimmung|Satz>/<lg>/1_neutral.wav, 2_best_practice.wav + plan.json
"""
import json, os, re, sys
from pathlib import Path
import modal

HIER = Path(__file__).resolve().parent
LESER = HIER.parent
TEST = HIER / "stimmung_vc_test"
EMOJI = LESER / "stimmen_archiv" / "_emoji"
PAUSE_MS = {1: 250, 2: 600, 3: 1200}
NAME = {"wuetend": "wütend", "aengstlich": "ängstlich", "froehlich": "fröhlich", "fluesternd": "flüsternd",
        "muede": "müde", "ueberrascht": "überrascht"}

# (ordner, lang, stimmung|None, markup) - Stimmungssaetze aus dem Testset, Markup wo das Testset eines hat
SAETZE = [
    ("wuetend", "de", "wuetend", "Ich habe dir *gesagt*, dass du die Tür nicht offen lassen sollst, und du hast es *schon wieder* vergessen!"),
    ("wuetend", "en", "wuetend", "I told you *twice* not to touch the lock, and now the whole door is ruined!"),
    ("fluesternd", "de", "fluesternd", "Leise jetzt, || sie schlafen noch. Wenn wir die Treppe hinunter wollen, müssen wir an der dritten Stufe vorbei."),
    ("fluesternd", "en", "fluesternd", "Quiet now, they are still asleep. || If we want to get down the stairs, we have to pass the third step."),
    ("traurig", "de", "traurig", "Das Haus war leer, nur der Stuhl am Fenster stand noch dort, wo sie immer gesessen hatte."),
    ("traurig", "en", "traurig", "The last train had gone, and she stood alone on the platform, holding a ticket for nowhere."),
    ("aengstlich", "de", "aengstlich", "Im Keller hat sich etwas bewegt. | Ich habe es zweimal gehört, und beide Male war es näher als zuvor."),
    ("aengstlich", "en", "aengstlich", "Something moved in the cellar. | I heard it twice, and both times it was closer than before."),
    ("froehlich", "de", "froehlich", "Endlich Ferien! Wir packen die Koffer, wir nehmen den frühen Zug, und heute Abend sitzen wir am Meer."),
    ("froehlich", "en", "froehlich", "Finally, holidays! We pack our bags, we take the early train, and tonight we sit by the sea."),
    ("erschrocken", "de", "erschrocken", "Hinter ihm krachte die Tür ins Schloss, und im selben Augenblick erlosch das Licht!"),
    ("erschrocken", "en", "erschrocken", "Behind him the door slammed shut, and at the same moment the light went out!"),
    ("ueberrascht", "de", "ueberrascht", "Du bist den ganzen Weg gekommen? Ich hatte keine Ahnung, ich dachte wirklich, du wärst noch im Ausland!"),
    ("ueberrascht", "en", "ueberrascht", "You came all this way? I had no idea, I really thought you were still abroad!"),
    ("muede", "de", "muede", "Ich habe seit Tagen nicht richtig geschlafen, und die Buchstaben auf der Seite rutschen mir immer wieder weg."),
    ("muede", "en", "muede", "I haven't slept properly in days, and the letters on the page keep sliding away from me."),
    ("feierlich", "de", "feierlich", "Und so, in der letzten Nacht des alten Königreichs, || läuteten die Glocken über den stillen Türmen."),
    ("feierlich", "en", "feierlich", "And so, upon the last night of the old kingdom, || the bells rang out over the silent towers."),
    ("freundlich", "de", "freundlich", "Guten Morgen! Komm herein, setz dich, ich stelle den Wasserkessel auf. Du musst ja ganz durchgefroren sein."),
    ("freundlich", "en", "freundlich", "Good morning! Come in, sit down, and let me put the kettle on. You must be freezing."),
    ("nachdenklich", "de", "nachdenklich", "Vielleicht | war es gar nicht der Zufall, || der uns hierher geführt hat, | sondern etwas, das wir nicht sehen konnten."),
    ("nachdenklich", "en", "nachdenklich", "Perhaps it was not chance | that brought us here, || but something we could not see."),
    ("liebevoll", "de", "liebevoll", "Komm her, mein Kleiner. Es ist alles gut, ich bin ja da, und morgen früh gehen wir zusammen zu den Enten."),
    ("liebevoll", "en", "liebevoll", "Come here, my little one. Everything is fine, I am here, and tomorrow morning we will go to see the ducks."),
    ("verschmitzt", "de", "verschmitzt", "Natürlich habe ich nichts gesehen. Ich war ja die ganze Zeit hier, genau neben dem leeren Kuchenteller."),
    ("verschmitzt", "en", "verschmitzt", "Of course I didn't see anything. I was right here the whole time, next to the empty cake plate."),
    ("ironisch", "de", "ironisch", "Oh, großartig. Noch ein Meeting, das auch eine E-Mail hätte sein können."),
    ("ironisch", "en", "ironisch", "Oh, wonderful. Another meeting that could have been an email."),
    ("_betonung_er", "de", None, "Ich habe nicht gesagt, dass *er* das Geld gestohlen hat. Ich habe nur gesagt, dass es jemand getan hat."),
    ("_betonung_er", "en", None, "I did not say *he* stole the money. I only said that someone did."),
    ("_betonung_nicht", "de", None, "Das ist *nicht* dein Ernst. Du willst wirklich heute noch los?"),
    ("_betonung_your", "en", None, "It was not my idea, it was *your* idea, and you know it."),
    ("_pause_ernst", "de", "wuetend", "Das ist ||| *nicht* dein Ernst!"),
    ("_pause_wait", "en", "aengstlich", "Wait. || Listen. ||| Now run, run, run, before they close the gates behind us!"),
]


def plan(markup, faktor=1.0):
    """Best Practice -> [(text, betont) | ("PAUSE", ms)]"""
    roh = [s.strip() for s in re.split(r"(\|{1,3})", markup) if s.strip()]
    # Pausen nur zwischen Chunks mit >= 4 Woertern, sonst zusammenziehen
    teile = []
    for s in roh:
        if s.startswith("|"):
            teile.append(s)
            continue
        kurz = lambda c: len(c.split()) < 4 and c.rstrip("\"' ").endswith((".", "!", "?"))   # kurzer ganzer Satz
        if len(teile) >= 2 and teile[-1].startswith("|") and (kurz(teile[-2]) or (kurz(s) and teile[-2].rstrip("\"' ").endswith((".", "!", "?")))):
            teile.pop()
            teile[-1] = teile[-1] + " " + s
        else:
            teile.append(s)
    folge = []
    for s in teile:
        if s.startswith("|"):
            folge.append(("PAUSE", int(PAUSE_MS[len(s)] * faktor)))
            continue
        # Betonung nur fuer kurze Kontrastwoerter (<= 3 Buchstaben), sonst Markierung entfernen
        s = re.sub(r"\*([^*]+)\*", lambda m: f"*{m.group(1)}*" if len(m.group(1)) <= 3 else m.group(1), s)
        m = re.match(r"^(.*?)\s*\*([^*]+)\*(.*)$", s)
        if m and m.group(1).strip():
            vor, wort, rest = m.group(1).strip(), m.group(2), m.group(3).strip()
            folge.append((f"{vor} ... {wort}", True))
            if rest:
                folge.append((rest.replace("*", ""), False))
        else:
            folge.append((s.replace("*", ""), False))
    return folge


def _hf_token():
    tok = os.environ.get("HF_TOKEN", "")
    env = LESER / ".env"
    if not tok and env.exists():
        for z in env.read_text(encoding="utf-8").splitlines():
            if z.strip().startswith("HF_TOKEN="):
                tok = z.split("=", 1)[1].strip().strip('"')
    return tok


STIMME = os.environ.get("READLAYER_STIMME", "herr_a")
app = modal.App("readlayer-best-practice")
vol = modal.Volume.from_name("readlayer-tts", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libsndfile1")
    .pip_install("chatterbox-tts", "huggingface_hub", "safetensors", "pyworld", "soundfile", "scipy")
    .env({"HF_HOME": "/vol/hf", "TORCH_HOME": "/vol/torch"})
    .add_local_file(str(HIER / "cb_batch.py"), remote_path="/code/cb_batch.py")
    .add_local_file(str(HIER / "cb_pruefung.py"), remote_path="/code/cb_pruefung.py")
    .add_local_file(str(LESER / "gpu_lora" / "lora_kern.py"), remote_path="/code/lora_kern.py")
    .add_local_file(str(LESER / "tools" / "fluestern.py"), remote_path="/code/fluestern.py")
    .add_local_file(str(LESER / "stimmen_archiv" / STIMME / "muster_de.wav"), remote_path="/ref/ziel_de.wav")
    .add_local_file(str(LESER / "stimmen_archiv" / STIMME / "muster_en.wav"), remote_path="/ref/ziel_en.wav")
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
    from cb_pruefung import Pruefer, kappen
    from fluestern import fluestern
    import lora_kern
    mtl.punc_norm = sprech_norm
    t0 = time.time()
    tts = {"en": mtl.ChatterboxMultilingualTTS.from_pretrained(device="cuda"),
           "de": mtl.ChatterboxMultilingualTTS.from_pretrained(device="cuda")}
    lora_kern.einmischen(tts["de"].t3, "/vol/lora/adapter/mix_v1.safetensors", 1.0)
    vc = ChatterboxVC.from_pretrained(device="cuda")
    pr = Pruefer("cuda")
    stat = {"chunks": 0, "neu": 0, "gekappt": 0, "rest": []}

    def chunk(m, lg, text, ref, betont):
        """Chunk erzeugen, per Forced Alignment pruefen, bis 2x neu, dann hinter dem letzten Wort kappen."""
        bestes = None
        for versuch in range(3):
            s = 1234 + versuch
            torch.manual_seed(s); random.seed(s); np.random.seed(s)
            w = m.generate(text, language_id=lg, audio_prompt_path=ref,
                           exaggeration=0.7 if betont else 0.5).float().cpu().reshape(1, -1)
            b = pr.pruefe(text, w, m.sr)
            if bestes is None or (bestes[1]["grund"] and not b["grund"]):
                bestes = (w, b)
            if not b["grund"]:
                break
            stat["neu"] += 1
        w, b = bestes
        if b.get("letzt"):
            w = kappen(w, m.sr, b["letzt"] + 0.12)
            stat["gekappt"] += 1
        if b["grund"]:
            stat["rest"].append(f"{text[:40]}: {b['grund']}")
        stat["chunks"] += 1
        return w.reshape(-1)

    def fertig(w, sr, td, st, lg, vc_an):
        torchaudio.save(f"{td}/r.wav", w.reshape(1, -1).clamp(-1, 1), sr)
        if vc_an:
            w2 = vc.generate(audio=f"{td}/r.wav", target_voice_path=f"/ref/ziel_{lg}.wav")
            torchaudio.save(f"{td}/r.wav", w2.reshape(1, -1).float().cpu().clamp(-1, 1), vc.sr)
        if st == "fluesternd":
            x, s2 = sf.read(f"{td}/r.wav")
            sf.write(f"{td}/r.wav", fluestern(x, s2), s2)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{td}/r.wav", "-ac", "1", "-c:a", "pcm_s16le",
                        "-filter:a", f"atempo={tempo}", f"{td}/f.wav"], check=True)
        return open(f"{td}/f.wav", "rb").read()

    aus, plaene = {}, {}
    for ordner, lg, st, markup in SAETZE:
        m = tts[lg]
        d = NAME.get(ordner, ordner)
        folge = plan(markup, 1.5 if st == "nachdenklich" else 1.0)
        plaene[f"{d}/{lg}"] = [f"<{x} ms>" if t == "PAUSE" else t + (" [betont]" if x else "") for t, x in folge]
        with tempfile.TemporaryDirectory() as td:
            # 1) Vergleich: Werkstimme neutral, Satz am Stueck
            neutral = chunk(m, lg, re.sub(r"\s*\|{1,3}\s*", " ", markup).replace("*", ""), f"/ref/ziel_{lg}.wav", False)
            aus[f"{d}/{lg}/1_neutral.wav"] = fertig(neutral, m.sr, td, None, lg, False)
            # 2) Best Practice
            ref = f"/emoji/{st}_{lg}.wav" if st else f"/ref/ziel_{lg}.wav"
            stuecke = []
            for text, x in folge:
                if text == "PAUSE":
                    if stuecke:
                        stuecke[-1] = torch.zeros(int(m.sr * x / 1000))      # Pause ersetzt die kurze Fuge
                    continue
                stuecke += [chunk(m, lg, text, ref, x), torch.zeros(int(m.sr * 0.08))]
            aus[f"{d}/{lg}/2_best_practice.wav"] = fertig(torch.cat(stuecke[:-1]), m.sr, td, st, lg, bool(st))
        print(f"[best] {d} {lg} fertig", flush=True)
    s = round(time.time() - t0, 1)
    return {"dateien": aus, "plan": plaene, "stat": stat, "gpu_s": s, "usd": round(s / 3600 * 0.80, 3)}


@app.local_entrypoint()
def main():
    erg = lauf.remote()
    ziel = TEST / f"ergebnis_{STIMME}"
    for n, b in erg["dateien"].items():
        (ziel / n).parent.mkdir(parents=True, exist_ok=True)
        (ziel / n).write_bytes(b)
    (ziel / "plan.json").write_text(json.dumps({"plan": erg["plan"], "pruefung": erg["stat"]}, ensure_ascii=False, indent=1),
                                    encoding="utf-8")
    st = erg["stat"]
    print(f"[best] {len(erg['dateien'])} WAVs -> {ziel} | Chunks {st['chunks']}, neu erzeugt {st['neu']}, "
          f"Rest-Befunde {len(st['rest'])} | GPU {erg['gpu_s']} s, ca. {erg['usd']} $")
