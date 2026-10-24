"""READ LAYER — Satz-Audio im Tempo anpassen (ffmpeg atempo, Tonhoehe bleibt).
Aufruf: python tools/tempo_anpassen.py <book_id> <lang> <faktor>
Originale -> fassungen/<lang>/audio_roh_<faktor>/ (einmalig), dann audio/ ueberschrieben.
"""
import glob, os, shutil, subprocess, sys
HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
book, lg, f = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, HIER)
from config import config
werk = config.book_dir(book)   # auch private Uploads
audio = os.path.join(werk, "fassungen", lg, "audio")
roh = os.path.join(werk, "fassungen", lg, "audio_chatterbox_roh")
os.makedirs(roh, exist_ok=True)
dateien = sorted(x for x in os.listdir(audio) if x.endswith(".wav"))
for n, name in enumerate(dateien):
    q = os.path.join(roh, name)
    if not os.path.exists(q):
        shutil.copy2(os.path.join(audio, name), q)
    tmp = os.path.join(audio, name + ".tmp.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", q, "-af", f"atempo={f}",
                    "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", tmp], check=True)
    os.replace(tmp, os.path.join(audio, name))
    if n % 200 == 0:
        print(f"[tempo] {book} {lg}: {n}/{len(dateien)}", flush=True)
open(os.path.join(roh, "TEMPO.txt"), "w").write(f"audio/ = audio_chatterbox_roh/ x atempo {f}\n")
print(f"[tempo] {book} {lg}: fertig, {len(dateien)} Dateien, Faktor {f}", flush=True)
