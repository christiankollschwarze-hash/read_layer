"""Hoerkopie eines Probeordners im Werk-Tempo: python tools/tempo_ordner.py <ordner> [0.91] -> <ordner>_tempo/ (ffmpeg atempo)."""
import os, subprocess, sys
q, f = sys.argv[1].rstrip("\\/"), (sys.argv[2] if len(sys.argv) > 2 else "0.91")
z = q + "_tempo"
os.makedirs(z, exist_ok=True)
for x in sorted(os.listdir(q)):
    if x.endswith(".wav"):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", os.path.join(q, x), "-af", f"atempo={f}",
                        "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", os.path.join(z, x)], check=True)
print(f"[tempo_ordner] {z}")
