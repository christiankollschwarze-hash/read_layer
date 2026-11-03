"""STAGE 502 — Chatterbox-Engine der Stage 500 (Stufe Basic), kein eigenes Gate (Katalogzeile 500).
Funktion:     Baut aus den offenen Saetzen von Stage 500 ein Paket gpu_tts/<werk>_<lg>_500/ (jobs.json + ref.wav),
              startet den Modal-Lauf (gpu_tts/tts_modal_opt.py::main, Batch, Satzpruefung per FA im Lauf, bis 2x neu,
              Nachklang gekappt) und holt die WAVs ab (Rohfassung fassungen/<lg>/audio/; Tempo wendet Stage 530
              einmal an, Adapter-Tempo aus lora_werte).
Aufrufer:     pipeline/s500_vertonung_gemini.py (Stage 500) – nur nach Kostenfreigabe. Kein Start per Bat mehr
              (start_cb_neu.bat / tools/cb_neu.py bleiben fuer Altwerke ausserhalb der Kette).
Stimme:       Referenz-Audio und LoRA-Adapter (Name + Version) aus casting.json (Freigabe 410).
Kosten:       Modal-GPU-Sekunden -> usage_log Stage 500 (in tts_modal_opt.main, mit Sprache).
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config

TEMPO_STD = 0.91          # Grundmodell (tools/tts_paket.TEMPO_STANDARD)
MS_STD = 0.051            # s je Zeichen roh (gpu_tts/cb_pruefung.MS_JE_ZEICHEN)
BATCH_STD = 8
EIN_CONTAINER_BIS = 200   # bis so viele Saetze: ein GPU-Container (Modell nur einmal laden)


def lora_werte(name):
    """(ms_je_zeichen, tempo) fuer einen Adapter; ohne Adapter Grundmodell."""
    if not name:
        return MS_STD, TEMPO_STD
    try:
        from tools.tts_paket import LORA
        a = LORA.get(name) or {}
        return float(a.get("ms_je_zeichen", MS_STD)), float(a.get("tempo", TEMPO_STD))
    except Exception:
        return MS_STD, TEMPO_STD


def paket_name(werk, lg, stage="500"):
    return f"{werk}_{lg}_{stage}"


def paket_dir(werk, lg, stage="500"):
    return os.path.join(config.BASE_DIR, "gpu_tts", paket_name(werk, lg, stage))


def paket_bauen(werk, lg, jobs, stimme, referenz, adapter, ex=0.5, cfg=0.5, tag=None, stage="500"):
    """jobs [(tid, text)] -> Paketordner. referenz relativ zu BASE_DIR (casting.json) oder None (Standardstimme)."""
    d = paket_dir(werk, lg, stage)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    ref = "chatterbox-standard"
    if referenz:
        q = referenz if os.path.isabs(referenz) else os.path.join(config.BASE_DIR, referenz)
        if not os.path.exists(q):
            raise FileNotFoundError(f"Referenz-Audio {referenz} fehlt")
        from pipeline.hoerprobe import ref_schnitt
        ref_schnitt(q, os.path.join(d, "ref.wav"))
        ref = stimme or "werkstimme"
    ein = len(jobs) <= EIN_CONTAINER_BIS
    tag = tag or time.strftime("%Y%m%d%H%M%S")
    daten = {"werk": werk, "lang": lg, "ref": ref, "ziel": f"work/_{stage}/{lg}/{tag}", "tag": tag, "stage": stage,
             "jobs": [{"id": t, "kap": "neu" if ein else t[:4], "text": x, "ex": ex, "cfg": cfg} for t, x in jobs]}
    if adapter:
        ms, tempo = lora_werte(adapter)
        daten.update(lora=adapter, ms_je_zeichen=ms, tempo=str(tempo))
    with open(os.path.join(d, "jobs.json"), "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=1)
    return d, daten


def modal_lauf(werk, lg, batch=BATCH_STD, fp16=False, tag=None, stage="500"):
    """Startet Modal (Batch mit Satzpruefung) und laedt ab. -> Messung (dict) inkl. befund {tid: grund}."""
    name = paket_name(werk, lg, stage)
    cmd = [sys.executable, "-m", "modal", "run", "gpu_tts/tts_modal_opt.py::main", "--paket", name,
           "--batch", str(int(batch)), "--zusatz", tag or "z"]
    if fp16:
        cmd.append("--fp16")
    print(f"[502] Modal: {' '.join(cmd[3:])}", flush=True)
    r = subprocess.run(cmd, cwd=config.BASE_DIR)
    if r.returncode != 0:
        raise RuntimeError(f"Modal-Lauf {name} Exit {r.returncode}")
    m = sorted(glob.glob(os.path.join(paket_dir(werk, lg, stage), f"messung_*{tag or 'z'}.json")), key=os.path.getmtime)
    if not m:
        return {}
    with open(m[-1], encoding="utf-8") as f:
        return json.load(f)


def atempo(q, z, faktor):
    if abs(float(faktor) - 1.0) < 1e-6:
        shutil.copy2(q, z)
        return
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", q, "-af", f"atempo={faktor}",
                    "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", z], check=True)


def einsetzen(werk, lg, daten, audio_dir):
    """Abgeholte Roh-WAVs -> audio/ (Rohfassung, ohne Tempo). -> {tid: pfad}."""
    quelle = os.path.join(config.book_dir(werk), daten["ziel"])
    os.makedirs(audio_dir, exist_ok=True)
    out = {}
    for j in daten["jobs"]:
        q = os.path.join(quelle, f"{j['id']}.wav")
        if not os.path.exists(q) or os.path.getsize(q) == 0:
            continue
        z = os.path.join(audio_dir, f"{j['id']}.wav")
        shutil.copy2(q, z + ".tmp.wav")
        os.replace(z + ".tmp.wav", z)
        out[j["id"]] = z
    shutil.rmtree(quelle, ignore_errors=True)
    return out


def befund(messung):
    """{tid: grund} der nach den Modal-Wiederholungen noch auffaelligen Saetze."""
    out = {}
    for k in messung.get("kapitel_details") or []:
        out.update(k.get("befund") or {})
        for t in k.get("pruefung_rest") or []:
            out.setdefault(t, "auffaellig")
    return out
