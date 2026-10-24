"""READ LAYER — Stimmungs-Referenzen einer Archivstimme mit Gemini erzeugen (17.10.2026).
Dieselbe Gemini-Voice-Design-Stimme spricht fuenf Stimmungen (ruhig, lebhaft, gespannt, ausruf, leise), je EN + DE,
~12 s. Chatterbox klont je Satz die passende Referenz (tts_paket.py --stil-refs). Referenzlaenge ~10-15 s.
Aufruf: py -3.11 tools/stimmungs_referenzen.py <stimme> [--nur ruhig,leise] [--sprachen de,en]
Ergebnis: stimmen_archiv/<stimme>/stil_<stimmung>_<lg>.wav  (vorhandene werden nicht ueberschrieben, ausser --neu)
Danach: CK hoert an und gibt frei -> steckbrief.json "stil_referenzen": {"freigegeben": true}.
"""
import json, os, sys, wave
HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HIER)
from config import config
from pipeline import tts_client
from pipeline.voice_registry import LANG_CODES

# Regie: dieselbe Person, nur die Stimmung aendert sich - deutlich, aber nie theatralisch
REGIE = {
    "ruhig": "Read calmly and evenly, like steady bedtime narration. Warm, unhurried, relaxed.",
    "lebhaft": "Read with lively, bright energy, a little quicker, with a smile in the voice, as if the story has become exciting and fun.",
    "gespannt": "Read with suspense: slower, lower, holding back, with small pauses, as if something mysterious is about to happen.",
    "ausruf": "Read with strong excitement and alarm, louder and more animated, rising emphasis, but stay natural and believable.",
    "leise": "Read softly and tenderly, close to a whisper, gentle and a little sad, very intimate.",
}
TEXTE = {
    "ruhig": {
        "en": "The house stood at the end of a quiet lane, and every evening the lamps were lit one by one. The children washed, said goodnight to the old dog, and listened to the clock on the stairs.",
        "de": "Das Haus stand am Ende einer stillen Gasse, und jeden Abend wurden die Lampen eine nach der anderen angezündet. Die Kinder wuschen sich, sagten dem alten Hund gute Nacht und lauschten der Uhr auf der Treppe.",
    },
    "lebhaft": {
        "en": "Off they went across the garden, laughing and tumbling over each other! The boy found the gate, the girl found the key, and in no time at all they were racing down to the river.",
        "de": "Los ging es quer durch den Garten, lachend und übereinander purzelnd! Der Junge fand das Tor, das Mädchen fand den Schlüssel, und im Handumdrehen rannten sie hinunter zum Fluss.",
    },
    "gespannt": {
        "en": "Then, very slowly, the window began to open. Nobody had touched it. A cold breath of air crept into the room, and somewhere in the darkness outside, something was waiting.",
        "de": "Dann, ganz langsam, begann sich das Fenster zu öffnen. Niemand hatte es berührt. Ein kalter Hauch kroch ins Zimmer, und irgendwo draußen in der Dunkelheit wartete etwas.",
    },
    "ausruf": {
        "en": "Look out! The ship is turning, the sails are tearing, and they are coming straight for us! Run, all of you, run to the boats before it is too late!",
        "de": "Pass auf! Das Schiff dreht bei, die Segel reißen, und sie kommen direkt auf uns zu! Lauft, ihr alle, lauft zu den Booten, bevor es zu spät ist!",
    },
    "leise": {
        "en": "She sat beside the little bed and held his hand. Hush now, she whispered, it is all right. I am here, and I will stay with you until you fall asleep.",
        "de": "Sie setzte sich an das kleine Bett und hielt seine Hand. Still jetzt, flüsterte sie, es ist alles gut. Ich bin da, und ich bleibe bei dir, bis du eingeschlafen bist.",
    },
}


def dauer(p):
    with wave.open(p) as w:
        return w.getnframes() / w.getframerate()


def main(stimme, nur=None, sprachen=("de", "en"), neu=False):
    ordner = os.path.join(HIER, "stimmen_archiv", stimme)
    sb = json.load(open(os.path.join(ordner, "steckbrief.json"), encoding="utf-8"))
    vid = sb["id"]
    for stil in (nur or REGIE):
        for lg in sprachen:
            ziel = os.path.join(ordner, f"stil_{stil}_{lg}.wav")
            if os.path.exists(ziel) and not neu:
                print(f"[stimmung] {stil} {lg}: vorhanden ({dauer(ziel):.1f} s)")
                continue
            tts_client.synthesize_wav(TEXTE[stil][lg], REGIE[stil], ziel, vid, LANG_CODES.get(lg))
            print(f"[stimmung] {stil} {lg}: {dauer(ziel):.1f} s -> {ziel}", flush=True)
    sb.setdefault("stil_referenzen", {"freigegeben": False, "stile": list(REGIE)})
    json.dump(sb, open(os.path.join(ordner, "steckbrief.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    o = lambda k: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else None
    nur = o("--nur").split(",") if o("--nur") else None
    sp = o("--sprachen").split(",") if o("--sprachen") else ("de", "en")
    a = [x for x in a if x not in (o("--nur"), o("--sprachen"))]
    main(a[0], nur, sp, "--neu" in sys.argv)
