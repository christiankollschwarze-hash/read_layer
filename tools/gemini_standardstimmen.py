"""Hoerproben der 30 Gemini-Standardstimmen (Systemnamen) fuer das Stimmen-Archiv / die "Klaviatur".
Aufruf: py -3.11 tools/gemini_standardstimmen.py   (60 kurze TTS-Anfragen, Cent-Betrag)
Ausgabe: stimmen_archiv/_gemini_standard/<Name>/muster_en.wav, muster_de.wav + standard.json (Grundton gemessen)
"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from config import config  # noqa
from pipeline import tts_client, voice_registry as vr  # noqa

# Systemname: (Geschlecht laut Google-Beschreibung, Charakter laut Google)
STIMMEN = {
 "Zephyr": ("w", "Bright"), "Puck": ("m", "Upbeat"), "Charon": ("m", "Informative"), "Kore": ("w", "Firm"),
 "Fenrir": ("m", "Excitable"), "Leda": ("w", "Youthful"), "Orus": ("m", "Firm"), "Aoede": ("w", "Breezy"),
 "Callirrhoe": ("w", "Easy-going"), "Autonoe": ("w", "Bright"), "Enceladus": ("m", "Breathy"), "Iapetus": ("m", "Clear"),
 "Umbriel": ("m", "Easy-going"), "Algieba": ("m", "Smooth"), "Despina": ("w", "Smooth"), "Erinome": ("w", "Clear"),
 "Algenib": ("m", "Gravelly"), "Rasalgethi": ("m", "Informative"), "Laomedeia": ("w", "Upbeat"), "Achernar": ("w", "Soft"),
 "Alnilam": ("m", "Firm"), "Schedar": ("m", "Even"), "Gacrux": ("w", "Mature"), "Pulcherrima": ("w", "Forward"),
 "Achird": ("m", "Friendly"), "Zubenelgenubi": ("m", "Casual"), "Vindemiatrix": ("w", "Gentle"), "Sadachbia": ("m", "Lively"),
 "Sadaltager": ("m", "Knowledgeable"), "Sulafat": ("w", "Warm"),
}
MUSTER = {
 "en": "It was a dark and stormy night, and the old house at the end of the lane stood silent, waiting for a visitor who would never come.",
 "de": "Es war eine dunkle und stürmische Nacht, und das alte Haus am Ende der Gasse stand still da und wartete auf einen Besucher, der niemals kommen würde.",
}
LANG = {"en": "en-GB", "de": "de-DE"}
ziel = os.path.join(vr.STIMMEN_DIR, "_gemini_standard")
os.makedirs(ziel, exist_ok=True)
info = {}
for name, (g, char) in STIMMEN.items():
    d = os.path.join(ziel, name); os.makedirs(d, exist_ok=True)
    ok = {}
    for lg, text in MUSTER.items():
        p = os.path.join(d, f"muster_{lg}.wav")
        if not os.path.exists(p):
            try:
                tts_client.synthesize_wav(text, "", p, name, LANG[lg])
            except Exception as e:
                print(f"{name} {lg}: FEHLER {str(e)[:120]}"); continue
        ok[lg] = p
    f0 = vr.grundton(ok["en"]) if "en" in ok else 0
    info[name] = {"geschlecht": g, "charakter": char, "grundton_hz": round(f0 or 0, 1), "muster": sorted(ok)}
    print(f"{name:14s} {g} {char:14s} {info[name]['grundton_hz']:6.1f} Hz  {sorted(ok)}")
json.dump(info, open(os.path.join(ziel, "standard.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("fertig:", len(info), "Stimmen ->", ziel)
