"""AP 63: Archiv-Regel je Stimme (Stimmen-Samenbank).
Jede Stimme im stimmen_archiv hat je Sprache:
  muster_<lg>.wav  ca. 5 s Kurzprobe (Auswahl, Grundton)
  klon_<lg>.wav    Referenztext "Nordwind und Sonne" (stimmen_archiv/_texte/nordwind_<lg>.txt, ca. 60 s),
                   Vorlage fuer Chatterbox-Klon; ref_schnitt() kuerzt auf 12-20 s an einer Sprechpause.
Erzeugung per Gemini TTS (Standardname oder Design-ID). Kosten ca. 0,0135 USD je Clip (2026), ab 2027 doppelt.
"""
import os
import wave

import numpy as np

from config import config
from pipeline import tts_client

ARCHIV = os.path.join(config.BASE_DIR, "stimmen_archiv")
TEXTE = os.path.join(ARCHIV, "_texte")
SPRACHEN = ("de", "en")
LANG_CODES = {"en": "en-GB", "de": "de-DE"}
STIL = {
    "de": "Calm German audiobook narration. Speak German only, native pronunciation, natural pace, clear articulation.",
    "en": "Calm English audiobook narration. Speak British English only, natural pace, clear articulation.",
}
USD_JE_CLIP = 0.0135


def text(lg):
    return open(os.path.join(TEXTE, f"nordwind_{lg}.txt"), encoding="utf-8").read().strip()


def stimmen():
    """Alle Archivstimmen: (name, ordner). Standardstimmen + Designs (Ordner mit steckbrief.json)."""
    out = []
    std = os.path.join(ARCHIV, "_gemini_standard")
    for n in sorted(os.listdir(std)):
        if os.path.isdir(os.path.join(std, n)):
            out.append((n, os.path.join(std, n)))
    for n in sorted(os.listdir(ARCHIV)):
        o = os.path.join(ARCHIV, n)
        if not n.startswith("_") and os.path.isdir(o) and os.path.exists(os.path.join(o, "steckbrief.json")):
            out.append((n, o))
    return out


def fehlend(ordner, sprachen=SPRACHEN):
    return [lg for lg in sprachen if not os.path.exists(os.path.join(ordner, f"klon_{lg}.wav"))]


def erzeuge(name, ordner, lg):
    from pipeline.gate import gemini_voice
    vid = gemini_voice(name)
    if not vid:
        raise RuntimeError(f"{name}: keine Gemini-Stimme/Design-ID")
    tts_client.synthesize_wav(text(lg), STIL[lg], os.path.join(ordner, f"klon_{lg}.wav"), vid, LANG_CODES[lg])


def fuer_neue_stimme(name, ordner):
    """Regel fuer jede neue Stimme: Klon-Text in allen Sprachen vertonen (muster_<lg> legt der Design-Schritt an)."""
    for lg in fehlend(ordner):
        try:
            erzeuge(name, ordner, lg)
            print(f"[hoerprobe] {name}: klon_{lg}.wav angelegt", flush=True)
        except Exception as e:
            print(f"[hoerprobe] {name}: klon_{lg}.wav FEHLT ({type(e).__name__}: {str(e)[:120]})", flush=True)


def ref_schnitt(quelle, ziel, min_s=12.0, max_s=20.0):
    """Kuerzt auf min_s..max_s Sekunden und schneidet in der leisesten 50-ms-Stelle (Sprechpause)."""
    with wave.open(quelle, "rb") as w:
        p = w.getparams()
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    sr = p.framerate * p.nchannels
    if len(a) / sr > max_s:
        f = int(0.05 * sr)
        lo, hi = int(min_s * sr) // f, int(max_s * sr) // f
        e = [float(np.sqrt(np.mean(a[i * f:(i + 1) * f].astype(np.float32) ** 2))) for i in range(lo, hi)]
        a = a[:(lo + int(np.argmin(e))) * f + f // 2]
    with wave.open(ziel, "wb") as o:
        o.setparams(p)
        o.writeframes(a.astype(np.int16).tobytes())
    return len(a) / sr
