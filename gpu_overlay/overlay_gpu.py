"""READ LAYER — Overlay-Test auf der GPU (laeuft in Modal, aufgerufen von overlay_modal.py).
Je Rede-Spanne zwei Varianten:
  vc/<id>.wav   Chatterbox Voice Conversion: Gemini-Spanne -> Zielstimme (Betonung/Tempo/Melodie bleiben)
  tts/<id>.wav  Chatterbox Multilingual DE: Text neu gesprochen mit Zielstimme
Lautheit wird an die Originalspanne angeglichen.
"""
import json, os, re, sys, time
import torch, torchaudio

PAKET = sys.argv[1]
DEV = "cuda" if torch.cuda.is_available() else "cpu"
jobs = json.load(open(os.path.join(PAKET, "jobs.json"), encoding="utf-8"))
lang = jobs["lang"]
jobs = jobs["jobs"]
os.makedirs("/out/vc", exist_ok=True)
os.makedirs("/out/tts", exist_ok=True)
bericht = []


def rms_angleichen(wav, ref):
    r1, r2 = wav.pow(2).mean().sqrt(), ref.pow(2).mean().sqrt()
    return wav * (r2 / r1) if r1 > 0 else wav


def speichern(p, wav, sr):
    torchaudio.save(p, wav.detach().cpu().reshape(1, -1).clamp(-1, 1), sr, encoding="PCM_S", bits_per_sample=16)


from chatterbox.vc import ChatterboxVC
from chatterbox.mtl_tts import ChatterboxMultilingualTTS
vc = ChatterboxVC.from_pretrained(device=DEV)
MIT_TTS = os.environ.get("OVERLAY_TTS") == "1"   # 14.10.2026: Variante B verworfen, nur noch auf Wunsch
mtl = ChatterboxMultilingualTTS.from_pretrained(device=DEV) if MIT_TTS else None

t_vc = t_tts = dauer = 0.0
for n, j in enumerate(jobs):
    src = os.path.join(PAKET, "src", j["id"] + ".wav")
    ref = os.path.join(PAKET, "ref", j["stimme"] + ".wav")
    orig, sr0 = torchaudio.load(src)
    dauer += orig.shape[-1] / sr0
    try:
        t = time.time()
        w = vc.generate(audio=src, target_voice_path=ref)
        w = rms_angleichen(w, torchaudio.functional.resample(orig, sr0, vc.sr))
        speichern(f"/out/vc/{j['id']}.wav", w, vc.sr)
        t_vc += time.time() - t
    except Exception as ex:
        bericht.append(f"VC  {j['id']}: {ex}")
    if MIT_TTS:
      try:
        t = time.time()
        text = re.sub(r"[„“”\"»«]", "", j["text"]).strip()
        w = mtl.generate(text, language_id=lang, audio_prompt_path=ref)
        w = rms_angleichen(w, torchaudio.functional.resample(orig, sr0, mtl.sr))
        speichern(f"/out/tts/{j['id']}.wav", w, mtl.sr)
        t_tts += time.time() - t
      except Exception as ex:
        bericht.append(f"TTS {j['id']}: {ex}")
    print(f"[{n + 1}/{len(jobs)}] {j['id']} {j['figur']}", flush=True)

kopf = (f"Jobs: {len(jobs)} | Audio gesamt {dauer:.0f} s | VC {t_vc:.0f} s (RTF {t_vc / max(dauer, 1):.2f}) | "
        f"TTS {t_tts:.0f} s (RTF {t_tts / max(dauer, 1):.2f}) | GPU {torch.cuda.get_device_name(0) if DEV == 'cuda' else 'CPU'}")
print(kopf)
open("/out/bericht.txt", "w", encoding="utf-8").write(kopf + "\n" + "\n".join(bericht) + "\n")
