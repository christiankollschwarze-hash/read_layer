"""READ LAYER — Emoji-Referenzen mit Gemini TTS (23.10.2026).
Je Emoji (Vokabelheft v0.1) ein kraeftig GESPIELTER Mustersatz, 6-10 s, DE, mit einer Gemini-Voice-Design-Stimme aus dem
Archiv (Standard grossmutter_a = Margaret). Learning 17.10. (Variante R): zurueckhaltende Regie ("nie theatralisch")
traegt nicht; Emo-DB (Schauspieler, deutlich gespielt) traegt -> hier Schauspieler-Regie.
Rechtsrahmen (Entscheidung 14.10.): nur eigene Voice-Design-Stimmen als Referenz, KEIN Training auf Gemini-Ausgaben.
Aufruf: py -3.11 tools/emoji_referenzen_gemini.py [stimme] [--nur wuetend,ironisch] [--neu]
Ergebnis: gpu_tts/stimmung_vc_test/muster/<stimmung>_gemini.wav  (danach start_stimmung_vc_test.bat --emodb -)
"""
import json, os, sys, wave
HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HIER)
from pipeline import tts_client
from pipeline.voice_registry import LANG_CODES

BASIS = ("Perform this like a professional stage and audio-drama actor, fully committed to the emotion - clearly "
         "audible in pitch, tempo, loudness and voice quality. Not narration, a character in the moment. ")
EMOJI = {  # stimmung: (emoji, Regie, Mustersatz DE)
    "wuetend": ("😠", "Furious, shouting through clenched teeth, hard attacks on the stressed words.",
                "Jetzt reicht es mir! Wie oft soll ich dir das noch sagen? Du hörst mir einfach nie zu!"),
    "traurig": ("😢", "Deeply sad, close to tears, slow, voice breaking, long heavy pauses.",
                "Er kommt nicht mehr zurück. Ich habe so lange gewartet, und jetzt ist alles vorbei."),
    "aengstlich": ("😨", "Afraid, trembling, breathy, hesitant, whispering fast as if someone might hear.",
                   "Hast du das gehört? Da ist jemand im Flur. Bitte, mach das Licht nicht an."),
    "erschrocken": ("😱", "Sudden shock and terror, a sharp gasp, high pitch, almost screaming.",
                    "Oh Gott! Was war das? Da, am Fenster, da steht doch jemand!"),
    "froehlich": ("😄", "Overjoyed and laughing, bright high voice, bubbling with excitement, fast.",
                  "Wir haben gewonnen! Ich kann es gar nicht glauben, das ist der schönste Tag überhaupt!"),
    "fluesternd": ("🤫", "A real whisper, unvoiced, very close to the microphone, secretive.",
                   "Psst, ganz leise. Wenn sie uns hören, ist alles verloren. Komm, hier entlang."),
    "ironisch": ("🙄", "Dripping with sarcasm and irony, exaggerated fake enthusiasm, drawn-out vowels, eye-rolling tone.",
                 "Na wunderbar. Genau das hat mir heute noch gefehlt. Was für eine großartige Idee."),
    "verschmitzt": ("😏", "Mischievous and sly, a smile you can hear, playful, slightly teasing, conspiratorial.",
                    "Ich? Ich weiß von gar nichts. Aber falls doch, verrate ich es dir bestimmt nicht."),
    "liebevoll": ("🥰", "Tender and loving, warm and soft, smiling, like speaking to a beloved child.",
                  "Na komm her, mein Schatz. Du hast das ganz wunderbar gemacht. Ich bin so stolz auf dich."),
    "ueberrascht": ("😮", "Genuinely astonished, rising pitch, wide-eyed disbelief, a little breathless.",
                    "Was? Du bist schon da? Damit hätte ich ja niemals gerechnet!"),
    "nachdenklich": ("🤔", "Pensive and searching, slow, with thinking pauses, trailing off, weighing every word.",
                     "Hm. Vielleicht... vielleicht haben wir es die ganze Zeit falsch verstanden. Ich weiß es nicht."),
    "muede": ("😴", "Exhausted and sleepy, low energy, slurred edges, yawning, very slow.",
              "Ich kann nicht mehr. Lass uns morgen weitermachen, mir fallen gleich die Augen zu."),
    "feierlich": ("🎭", "Solemn and ceremonial, grand, slow, resonant, like an announcement in a great hall.",
                  "Und so verkünden wir an diesem Tage: Das Reich ist frei, und die Glocken sollen läuten."),
    "freundlich": ("🙂", "Friendly and welcoming, open and warm, light smile, relaxed natural pace.",
                   "Hallo, schön, dass du da bist! Komm rein, setz dich, ich mache uns einen Tee."),
}


def dauer(p):
    with wave.open(p) as w:
        return w.getnframes() / w.getframerate()


def main(stimme="grossmutter_a", nur=None, neu=False):
    sb = json.load(open(os.path.join(HIER, "stimmen_archiv", stimme, "steckbrief.json"), encoding="utf-8"))
    ordner = os.path.join(HIER, "gpu_tts", "stimmung_vc_test", "muster")
    os.makedirs(ordner, exist_ok=True)
    for st in (nur or EMOJI):
        emo, regie, text = EMOJI[st]
        ziel = os.path.join(ordner, f"{st}_gemini.wav")
        if os.path.exists(ziel) and not neu:
            print(f"[emoji] {emo} {st}: vorhanden ({dauer(ziel):.1f} s)")
            continue
        tts_client.synthesize_wav(text, BASIS + regie, ziel, sb["id"], LANG_CODES.get("de"))
        print(f"[emoji] {emo} {st}: {dauer(ziel):.1f} s -> {ziel}", flush=True)


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    nur = sys.argv[sys.argv.index("--nur") + 1].split(",") if "--nur" in sys.argv else None
    a = [x for x in a if not nur or x != ",".join(nur)]
    main(a[0] if a else "grossmutter_a", nur, "--neu" in sys.argv)
