"""READ LAYER — Klappentext-Teaser mit Chatterbox: Testsequenzen (19.10.2026, claude/PROZESS_klappentext_erzaehler.md).
Ablauf je Werk/Sprache/Variante (start_teaser_test.bat):
  bauen   -> gpu_tts/<werk>_teaser_<lg>_<var>/jobs.json (Saetze aus work/600_klappentext.json, Reihenfolge Koeder, Einordnung, Autor)
  [Modal]    py -3.11 -m modal run gpu_tts/tts_modal_opt.py --paket <paket>  -> fassungen/<lg>/teaser/<var>/roh/
  overlay -> Tempo auf roh (-> roh_tempo/); bei Overlay-Varianten Paket gpu_overlay/<paket>/ (Chatterbox VC)
  [Modal]    py -3.11 -m modal run gpu_overlay/overlay_modal.py --paket <paket>   (nur Overlay-Varianten)
  fertig  -> Einzelsaetze fassungen/<lg>/teaser/<var>/*.wav + Gesamtdatei fassungen/<lg>/teaser/teaser_<lg>_<var>.wav

Aufruf:  py -3.11 tools/teaser_paket.py bauen|overlay|fertig <werk> <lg> <variante>
"""
import json, os, re, shutil, subprocess, sys, wave, zipfile

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HIER)
sys.path.insert(0, os.path.join(HIER, "tools"))
from config import config
import tts_paket

# Varianten: TTS-Gewicht (lora), Klon-Referenz (ref), Overlay-Zielstimme (vc)
# 19.10.2026 CK: DE maennlich = Klon Herr A ueber Mix-Gewicht; EN-Tempo 0,80 (0,91 war zu schnell)
VARIANTEN = {
    ("de", "w"): {"lora": "mix_v1", "ref": "grossmutter_a", "vc": None},                         # Mix-Stimme DE
    ("de", "m"): {"lora": "mix_v1", "ref": "herr_a",        "vc": None},                         # Herr A ueber Mix-Gewicht
    ("en", "w"): {"lora": "aus",    "ref": None,            "vc": "grossmutter_a", "tempo": "0.80"},  # Standard + Overlay
    ("en", "m"): {"lora": "aus",    "ref": None,            "vc": "herr_a",        "tempo": "0.80"},  # Standard + Overlay
}
BLOECKE = ("koeder", "einordnung", "autor")
PAUSE_SATZ_MS, PAUSE_BLOCK_MS = 350, 800


def paket(werk, lg, var):
    return f"{werk}_teaser_{lg}_{var}"


def ordner(werk, lg, var):
    return os.path.join(config.book_dir(werk), "fassungen", lg, "teaser", var)


def saetze(text):
    # 19.10.2026: nicht nach Ordinalzahl trennen ("19. Jahrhunderts" ist kein Satzende)
    teile = re.split(r"(?<!\d\.)(?<=[.!?…])[\"“”»«']?\s+(?=[\"„“»«']?[A-ZÄÖÜ])", text.strip())
    return [t.strip() for t in teile if t.strip()]


def jobs(werk, lg):
    d = json.load(open(os.path.join(config.book_dir(werk), "work", "600_klappentext.json"), encoding="utf-8"))
    out = []
    for bi, block in enumerate(BLOECKE, 1):
        for ai, absatz in enumerate(d.get("blurb", {}).get(block, []), 1):
            for si, s in enumerate(saetze(absatz.get(lg, "")), 1):
                out.append({"id": f"t{bi}_{ai:02d}_{si:02d}", "kap": "t000", "text": s, "block": block})
    if not out:
        sys.exit(f"[teaser] kein Klappentext {lg} in {werk}")
    # 19.10.2026: Sprechtext-Regeln + Aussprache-Lexikon (work/aussprache_<lg>.json) wie bei der Werk-Vertonung.
    # TEASER_LEXIKON_TEST=1: Lexikon auch ungeprueft anwenden (Hoerprobe = Pruefung).
    from pipeline.sprechtext import sprechtext
    ers = tts_paket.lexikon(config.book_dir(werk), lg, os.environ.get("TEASER_LEXIKON_TEST") == "1")
    for j in out:
        j["text"] = tts_paket.lex_text(sprechtext(j["text"], lg, "s"), ers)
    print(f"[teaser] Aussprache-Lexikon {lg}: {len(ers)} Eintraege angewendet")
    return out


def bauen(werk, lg, var):
    v = VARIANTEN[(lg, var)]
    j = jobs(werk, lg)
    extra = tts_paket.lora_extra(config.book_dir(werk), v["lora"], lg)
    if v.get("tempo"):
        extra["tempo"] = v["tempo"]
    extra["ziel"] = os.path.relpath(os.path.join(ordner(werk, lg, var), "roh"), config.book_dir(werk))
    extra["teaser"] = {"variante": var, **v}
    tts_paket.schreiben(werk, lg, j, ref=v["ref"], name=paket(werk, lg, var), extra=extra)


def _tempo(q, z, f):
    os.makedirs(z, exist_ok=True)
    for x in sorted(os.listdir(q)):
        if x.endswith(".wav"):
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", os.path.join(q, x), "-af", f"atempo={f}",
                            "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", os.path.join(z, x)], check=True)


def raender(p, vor=0.10, nach=0.15, schwelle_anfang_db=-55.0, schwelle_ende_db=-35.0):
    """19.10.2026: Satz-WAV auf den Sprachanteil schneiden (Pegelschwelle relativ zum Spitzenpegel, 20-ms-Fenster),
    kurze Ein-/Ausblendung -- entfernt Rauschen/Nachklang zwischen den Saetzen (EN-Standard + Overlay)."""
    import numpy as np
    with wave.open(p) as w:
        par = w.getparams()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    if par.nchannels != 1 or len(x) == 0:
        return
    fen = int(par.framerate * 0.02)
    n = len(x) // fen
    if n < 3:
        return
    rms = np.sqrt((x[:n * fen].reshape(n, fen) ** 2).mean(axis=1) + 1e-9)
    # 19.10.2026 Runde 3: Anfang nur echte Stille kappen (-55 dB; -35 dB hatte das gehauchte "H" von "Hinter" geschnitten),
    # Ende wie Runde 2 (-35 dB) gegen Rauschen/Nachklang.
    db = 20 * np.log10(rms / rms.max())
    an_a, an_e = np.where(db > schwelle_anfang_db)[0], np.where(db > schwelle_ende_db)[0]
    if not len(an_a) or not len(an_e):
        return
    a = max(0, an_a[0] * fen - int(vor * par.framerate))
    e = min(len(x), (an_e[-1] + 1) * fen + int(nach * par.framerate))
    y = x[a:e].copy()
    f = min(int(0.01 * par.framerate), len(y) // 4)
    if f:
        y[:f] *= np.linspace(0, 1, f)
        y[-f:] *= np.linspace(1, 0, f)
    with wave.open(p, "wb") as w:
        w.setparams(par)
        w.writeframes(y.astype(np.int16).tobytes())


def overlay(werk, lg, var):
    v = VARIANTEN[(lg, var)]
    daten = json.load(open(os.path.join(HIER, "gpu_tts", paket(werk, lg, var), "jobs.json"), encoding="utf-8"))
    o = ordner(werk, lg, var)
    roh, rt = os.path.join(o, "roh"), os.path.join(o, "roh_tempo")
    if not os.path.isdir(roh) or not any(x.endswith(".wav") for x in os.listdir(roh)):
        sys.exit(f"[teaser] keine Roh-WAVs in {roh} -- Modal-Vertonung gelaufen?")
    _tempo(roh, rt, daten.get("tempo", tts_paket.TEMPO_STANDARD))
    for x in os.listdir(rt):
        raender(os.path.join(rt, x))
    print(f"[teaser] Tempo {daten.get('tempo')} + Raender -> {rt}")
    if not v["vc"]:
        return
    z = os.path.join(HIER, "gpu_overlay", paket(werk, lg, var))
    os.makedirs(os.path.join(z, "src"), exist_ok=True)
    os.makedirs(os.path.join(z, "ref"), exist_ok=True)
    for x in os.listdir(rt):
        shutil.copy(os.path.join(rt, x), os.path.join(z, "src", x))
    shutil.copy(os.path.join(HIER, "stimmen_archiv", v["vc"], f"muster_{lg}.wav"), os.path.join(z, "ref", v["vc"] + ".wav"))
    oj = [{"id": j["id"], "stimme": v["vc"], "figur": "Klappentext", "text": j["text"]} for j in daten["jobs"]]
    json.dump({"lang": lg, "jobs": oj}, open(os.path.join(z, "jobs.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[teaser] Overlay-Paket {z} ({len(oj)} Saetze -> {v['vc']})")


def _stille(params, ms):
    return b"\x00" * (int(params.framerate * ms / 1000) * params.sampwidth * params.nchannels)


def fertig(werk, lg, var):
    v = VARIANTEN[(lg, var)]
    o = ordner(werk, lg, var)
    daten = json.load(open(os.path.join(HIER, "gpu_tts", paket(werk, lg, var), "jobs.json"), encoding="utf-8"))
    if v["vc"]:
        zp = os.path.join(HIER, "gpu_overlay", paket(werk, lg, var), "ergebnis.zip")
        with zipfile.ZipFile(zp) as zf:
            for n in zf.namelist():
                if n.startswith("vc/") and n.endswith(".wav"):
                    tmp = os.path.join(o, "_vc_" + os.path.basename(n))
                    open(tmp, "wb").write(zf.read(n))
                    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-ar", "24000", "-ac", "1",
                                    "-c:a", "pcm_s16le", os.path.join(o, os.path.basename(n))], check=True)
                    os.remove(tmp)
    else:
        for x in os.listdir(os.path.join(o, "roh_tempo")):
            shutil.copy(os.path.join(o, "roh_tempo", x), os.path.join(o, x))
    for j in daten["jobs"]:
        if os.path.exists(os.path.join(o, j["id"] + ".wav")):
            raender(os.path.join(o, j["id"] + ".wav"))
    gesamt = os.path.join(os.path.dirname(o), f"teaser_{lg}_{var}.wav")
    params, frames, vorher, fehlt = None, [], None, []
    for j in daten["jobs"]:
        p = os.path.join(o, j["id"] + ".wav")
        if not os.path.exists(p):
            fehlt.append(j["id"]); continue
        with wave.open(p) as w:
            params = params or w.getparams()
            if vorher:
                frames.append(_stille(params, PAUSE_BLOCK_MS if vorher != j["block"] else PAUSE_SATZ_MS))
            frames.append(w.readframes(w.getnframes()))
        vorher = j["block"]
    with wave.open(gesamt, "wb") as w:
        w.setparams(params)
        w.writeframes(b"".join(frames))
    sek = sum(len(f) for f in frames) / (params.framerate * params.sampwidth)
    print(f"[teaser] {gesamt}  ({sek:.0f} s){'  FEHLT: ' + ', '.join(fehlt) if fehlt else ''}")


if __name__ == "__main__":
    if len(sys.argv) != 5 or sys.argv[1] not in ("bauen", "overlay", "fertig"):
        sys.exit(__doc__)
    {"bauen": bauen, "overlay": overlay, "fertig": fertig}[sys.argv[1]](*sys.argv[2:5])
