"""Fuegt Satz-WAVs eines Probe-Ordners in Tag-Reihenfolge zu EINER Hoerdatei zusammen (0,4 s Pause).
Aufruf: python tools/probe_hoerdatei.py <ordner> [ziel.wav]"""
import os, sys, wave

def main(ordner, ziel=None):
    dateien = sorted(f for f in os.listdir(ordner) if f.endswith(".wav"))
    ziel = ziel or os.path.join(os.path.dirname(ordner.rstrip("/\\")), os.path.basename(ordner.rstrip("/\\")) + "_komplett.wav")
    with wave.open(os.path.join(ordner, dateien[0])) as w0:
        params = w0.getparams()
    pause = b"\x00" * int(params.framerate * 0.4) * params.sampwidth * params.nchannels
    with wave.open(ziel, "wb") as out:
        out.setparams(params)
        for f in dateien:
            with wave.open(os.path.join(ordner, f)) as w:
                out.writeframes(w.readframes(w.getnframes()))
            out.writeframes(pause)
    print(f"{len(dateien)} Saetze -> {ziel}")

if __name__ == "__main__":
    main(*sys.argv[1:])
