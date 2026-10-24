"""READ LAYER — Ergebnisse des Stimmungs-Tests ordnen (23.10.2026):
gpu_tts/stimmung_vc_test/ergebnis/<stimmung>_..._.wav -> ergebnis/<Stimmung>/<lg>/<Nr>_<Art>[_<Quelle>].<ext>
  <Stimmung>/quelle_<emodb08|gemini>.wav  (Vorlage, sprachunabhaengig)
  <Stimmung>/<lg>/1_margaret.wav | 2_fremd_<quelle>.wav | 3_umgewandelt_<quelle>.wav | 4_elevenlabs.mp3
Idempotent; laeuft am Ende von start_stimmung_vc_test.bat und start_elevenlabs_vergleich.bat.
"""
import os, re, sys
HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ERG = os.path.join(HIER, "gpu_tts", "stimmung_vc_test", "ergebnis")
NAME = {"wuetend": "wütend", "aengstlich": "ängstlich", "froehlich": "fröhlich", "fluesternd": "flüsternd",
        "muede": "müde", "ueberrascht": "überrascht"}


def ziel_fuer(datei):
    stamm, ext = os.path.splitext(datei)
    t = stamm.split("_")
    st = NAME.get(t[0], t[0])
    if len(t) == 3 and t[2] == "1" or stamm.endswith("_1_margaret"):          # <st>_<lg>_1_margaret
        return os.path.join(st, t[1], "1_margaret" + ext)
    if stamm.endswith("_4_elevenlabs"):                                       # <st>_<lg>_4_elevenlabs
        return os.path.join(st, t[1], "4_elevenlabs" + ext)
    if stamm.endswith("_0_quelle"):                                           # <st>_<quelle>_0_quelle
        return os.path.join(st, f"quelle_{t[1]}" + ext)
    m = re.match(r"^[a-z]+_(.+)_(de|en)_(2_fremd|3_umgewandelt)$", stamm)    # <st>_<quelle>_<lg>_<n>
    if m:
        return os.path.join(st, m.group(2), f"{m.group(3)}_{m.group(1)}" + ext)
    return None


def main():
    n = 0
    for f in sorted(os.listdir(ERG)):
        p = os.path.join(ERG, f)
        if not os.path.isfile(p):
            continue
        z = ziel_fuer(f)
        if not z:
            print(f"[ordnen] unbekannt, bleibt liegen: {f}")
            continue
        os.makedirs(os.path.dirname(os.path.join(ERG, z)), exist_ok=True)
        os.replace(p, os.path.join(ERG, z))
        n += 1
    print(f"[ordnen] {n} Dateien einsortiert -> {ERG}")


if __name__ == "__main__":
    main()
