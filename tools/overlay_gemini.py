"""READ LAYER - Hoerspiel-Spannen direkt mit Gemini sprechen (22.10.2026, AP4 Spiegelschwestern).

Fuer Figuren mit Gemini-Standardstimme (casting.json plan.overlay_gemini, z. B. Zwillinge = Zephyr). Diese Stimmen duerfen
nicht VC-Vorlage sein (Regel 14.10.2026) -> die Rede-Spanne wird mit Gemini 3.8 Flash TTS in dieser Stimme neu gesprochen.
  modus "gemini": Text der Spanne (Sprechtext + freigegebenes Lexikon, ohne Anfuehrungszeichen) -> Gemini -> Raender
                  geschnitten (-45 dB, 40 ms Luft) -> fassungen/<lg>/audio_overlay/spannen/vc/<id>.wav
  modus "kopie":  Kapitel-Erzaehler hat dieselbe Stimme -> Originalspanne aus fassungen/<lg>/audio (nur Sprechweise-Korrektur
                  in overlay_montage/overlay_korrektur).
Danach: tools/overlay_montage.py <werk> <lg> (setzt Spannen ein; Gemini-Spannen duerfen laenger/kuerzer sein).
Aufruf:  py -3.11 tools/overlay_gemini.py <werk> [de] [--force]
Kosten: wenige Cent (kurze Spannen).
"""
import json, os, re, sys, wave
import numpy as np

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HIER)
sys.path.insert(0, os.path.join(HIER, "tools"))
LANG_CODE = {"de": "de-DE", "en": "en-GB"}
STIL = {"de": "Sprich natürlich, wie im Gespräch. Deutsch, ohne Akzent.",
        "en": "Speak naturally, as in conversation."}


def _lesen(p):
    with wave.open(p) as w:
        return w.getparams(), w.readframes(w.getnframes())


def _schreiben(p, sr, x):
    with wave.open(p, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(np.clip(x, -32768, 32767).astype(np.int16).tobytes())


def _raender(x, sr, db=-45, luft=0.04):
    a = np.abs(x.astype(np.float32)) / 32768
    win = max(1, int(sr * 0.01))
    env = np.convolve(a, np.ones(win) / win, mode="same")
    idx = np.where(env > 10 ** (db / 20))[0]
    if not len(idx):
        return x
    i0, i1 = max(0, idx[0] - int(luft * sr)), min(len(x), idx[-1] + int(luft * sr))
    return x[i0:i1]


def main(werk, lg="de", force=False):
    from config import config
    from pipeline import tts_client
    from pipeline.sprechtext import sprechtext
    import tts_paket
    wd = config.book_dir(werk)
    paket = os.path.join(HIER, "gpu_overlay", f"{werk}_{lg}")
    jobs = json.load(open(os.path.join(paket, "jobs_gemini.json"), encoding="utf-8"))["jobs"]
    ers = tts_paket.lexikon(wd, lg)
    ziel = os.path.join(wd, "fassungen", lg, "audio_overlay", "spannen", "vc")
    os.makedirs(ziel, exist_ok=True)
    audio = os.path.join(wd, "fassungen", lg, "audio")
    n = {"gemini": 0, "kopie": 0, "vorhanden": 0, "fehler": 0}
    for j in jobs:
        out = os.path.join(ziel, j["id"] + ".wav")
        if os.path.exists(out) and not force:
            n["vorhanden"] += 1; continue
        try:
            if j["modus"] == "kopie":
                params, fr = _lesen(os.path.join(audio, j["tag"] + ".wav"))
                bpf, sr = params.sampwidth * params.nchannels, params.framerate
                with wave.open(out, "wb") as w:
                    w.setparams(params)
                    w.writeframes(fr[int(j["t0"] * sr) * bpf:int(j["t1"] * sr) * bpf])
            else:
                text = re.sub(r"[„“”\"»«‚‘’]", "", j["text"]).strip()
                text = tts_paket.lex_text(sprechtext(text, lg, "dl"), ers)
                tmp = out + ".roh.wav"
                tts_client.synthesize_wav(text, STIL.get(lg, ""), tmp, j["stimme"], LANG_CODE.get(lg, lg))
                params, fr = _lesen(tmp)
                x = np.frombuffer(fr, np.int16)
                _schreiben(out, params.framerate, _raender(x, params.framerate))
                os.remove(tmp)
            n[j["modus"]] += 1
        except Exception as ex:
            n["fehler"] += 1
            print(f"  {j['id']}: {str(ex)[:120]}")
    print(f"[overlay_gemini] {werk} [{lg}]: {n} -> {ziel}")


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    main(a[0], a[1] if len(a) > 1 else "de", "--force" in sys.argv)
