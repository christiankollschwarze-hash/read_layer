"""READ LAYER — Vergleich ElevenLabs Eleven v4 (fal.ai) gegen Emoji-Weg (Clip -> Chatterbox -> VC), 23.10.2026.
Gleiche Testsaetze wie gpu_tts/stimmung_vc_test.py (SAETZE), Stimmung als Audio-Tag im Text.
Aufruf: py -3.11 tools/elevenlabs_vergleich.py [--voice Rachel] [--nur wuetend,ironisch] [--stability 0.3]
Ergebnis: gpu_tts/stimmung_vc_test/ergebnis/<stimmung>_<lg>_4_elevenlabs.mp3 (+ kosten in Log)
Preis fal: 0,08 $ je 1.000 Zeichen.
"""
import os, sys, time
import requests
HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HIER)
sys.path.insert(0, os.path.join(HIER, "gpu_tts"))
sys.path.insert(0, os.path.join(HIER, "tools"))
from config import config
from stimmung_vc_test import SAETZE

URL = "https://fal.run/elevenlabs/tts/eleven-v4"
TAG = {"wuetend": "angry", "traurig": "sad", "aengstlich": "scared", "erschrocken": "terrified", "froehlich": "excited",
       "fluesternd": "whispering", "ironisch": "sarcastic", "verschmitzt": "mischievously", "liebevoll": "tenderly",
       "ueberrascht": "surprised", "nachdenklich": "thoughtful", "muede": "tired", "feierlich": "solemnly",
       "freundlich": "warmly"}


def main(voice="Rachel", nur=None, stability=0.3):
    key = getattr(config, "FAL_KEY", "")
    if not key:
        raise SystemExit("FAL_KEY fehlt")
    ziel = os.path.join(HIER, "gpu_tts", "stimmung_vc_test", "ergebnis")
    os.makedirs(ziel, exist_ok=True)
    zeichen = 0
    for st in (nur or TAG):
        for i, lg in enumerate(("de", "en")):
            datei = os.path.join(ziel, f"{st}_{lg}_4_elevenlabs.mp3")
            from ergebnis_ordnen import ziel_fuer
            if os.path.exists(datei) or os.path.exists(os.path.join(ziel, ziel_fuer(os.path.basename(datei)))):
                print(f"[eleven] {st} {lg}: vorhanden")
                continue
            text = f"[{TAG[st]}] {SAETZE[st][i]}"
            body = {"text": text, "voice": voice, "stability": stability, "seed": 1234, "language_code": lg,
                    "output_format": "mp3_44100_128"}
            for versuch in range(3):
                r = requests.post(URL, headers={"Authorization": f"Key {key}", "Content-Type": "application/json"},
                                  json=body, timeout=300)
                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(10 * (versuch + 1))
                    continue
                break
            if r.status_code >= 400:
                print(f"[eleven] {st} {lg}: Fehler {r.status_code} {r.text[:300]}")
                continue
            a = requests.get(r.json()["audio"]["url"], timeout=300)
            a.raise_for_status()
            open(datei, "wb").write(a.content)
            zeichen += len(text)
            print(f"[eleven] {st} {lg}: ok ({len(text)} Zeichen)", flush=True)
    print(f"[eleven] fertig: {zeichen} Zeichen, ca. {zeichen / 1000 * 0.08:.2f} $ -> {ziel}")


if __name__ == "__main__":
    o = lambda k, d=None: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
    nur = o("--nur").split(",") if o("--nur") else None
    main(o("--voice", "Rachel"), nur, float(o("--stability", 0.3)))
