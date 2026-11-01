"""STAGE 502 - Vertonung Chatterbox (AP 63).
Engine je Werk/Sprache: book.json "tts": {"<lg>": "chatterbox"}.
Die Pipeline erzeugt nur das Paket (kostenlos, tools/cb_neu.py <werk> <lg> liste --alle).
Der Modal-Lauf und das Einspielen passieren per .bat (start_cb_neu.bat <werk> <lg> los --alle),
damit kein GPU-Lauf unbemerkt aus der Pipeline startet."""
import glob
import json
import os
import subprocess
import sys

from config import config
from pipeline.gate import tts_engine


def _soll(book_id, lang):
    d = json.load(open(config.work_path(book_id, "400_regie"), encoding="utf-8"))["content"]
    return sum(1 for e in d.values()
               if e.get("type") not in ("p", "tt", "skip") and str(e.get(lang, "")).strip())


def _ist(book_id, lang):
    a = os.path.join(config.book_dir(book_id), "fassungen", lang, "audio")
    return len(glob.glob(os.path.join(a, "*.wav"))) if os.path.isdir(a) else 0


def _referenz(book_id, lang):
    """AP 63: gewaehlte Stimme -> gpu_tts/<werk>_<lg>/ref.wav (max. 15 s) + jobs.json["ref"]."""
    from pipeline.gate import stimme, ref_clip
    name = stimme(book_id, lang)
    q = ref_clip(name, lang)
    if not q:
        return
    d = os.path.join(config.BASE_DIR, "gpu_tts", f"{book_id}_{lang}")
    os.makedirs(d, exist_ok=True)
    from pipeline.hoerprobe import ref_schnitt
    sek = ref_schnitt(q, os.path.join(d, "ref.wav"))
    jp = os.path.join(d, "jobs.json")
    j = json.load(open(jp, encoding="utf-8")) if os.path.exists(jp) else {"jobs": []}
    j["ref"] = name
    json.dump(j, open(jp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[502] Referenz: {name} ({os.path.basename(q)}, {sek:.1f} s, Schnitt an Sprechpause)", flush=True)


def run(book_id, chapter=None, lang=None, force=False, **_):
    if tts_engine(book_id, lang) != "chatterbox":
        return
    soll = _soll(book_id, lang)
    if not force and soll and _ist(book_id, lang) >= soll:
        print(f"[502] {book_id} [{lang}] fertig: {_ist(book_id, lang)}/{soll}", flush=True)
        return
    _referenz(book_id, lang)
    print(f"[502] {book_id} [{lang}]: Paket wird erzeugt (kostenlos)", flush=True)
    subprocess.run([sys.executable, os.path.join(config.BASE_DIR, "tools", "cb_neu.py"),
                    book_id, lang, "liste", "--alle"], cwd=config.BASE_DIR, check=True)
    raise RuntimeError(f"[502] Paket {book_id}_{lang}_neu bereit. Vertonung per "
                       f"start_cb_neu.bat {book_id} {lang} los --alle (Modal, Freigabe noetig).")
