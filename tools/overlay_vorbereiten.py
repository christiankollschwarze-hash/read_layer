"""READ LAYER — Overlay-Test vorbereiten (laeuft lokal/VM, keine API).
Schneidet aus dem Single-Speaker-Audio (fassungen/<lg>/audio) die Rede-Spannen jeder Figur heraus
und baut ein GPU-Paket fuer Chatterbox (VC + Multilingual-TTS).

Aufruf:  python tools/overlay_vorbereiten.py <book_id> [de|en]
Ergebnis: gpu_overlay/<book_id>_<lg>/  (jobs.json, src/*.wav, ref/*.wav)
"""
import json, os, re, sys, wave, glob

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ERZ = "Erzaehler"
PAD = 0.06          # s Luft vor/nach der Spanne


def _werk(book_id):
    t = glob.glob(os.path.join(HIER, "authors", "*", "books", book_id))
    if not t:
        sys.exit(f"Werk nicht gefunden: {book_id}")
    return t[0]


def _wav_lesen(p):
    with wave.open(p) as w:
        return w.getparams(), w.readframes(w.getnframes())


def _wav_schreiben(p, params, frames):
    with wave.open(p, "wb") as w:
        w.setparams(params)
        w.writeframes(frames)


def _tonhoehe(pfad, halbtoene):
    """Tonhoehe der Quellspanne verschieben, Dauer bleibt (ffmpeg asetrate+atempo)."""
    import subprocess
    if not halbtoene:
        return
    r = 2 ** (halbtoene / 12)
    tmp = pfad + ".tmp.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", pfad, "-af",
                    f"asetrate=24000*{r:.5f},aresample=24000,atempo={1 / r:.5f}", tmp], check=True)
    os.replace(tmp, pfad)


def main(book_id, lg="de", nur=None):
    werk = _werk(book_id)
    work = os.path.join(werk, "work")
    sp = json.load(open(os.path.join(work, "sprecher.json"), encoding="utf-8"))
    st06 = json.load(open(os.path.join(work, "400_regie.json"), encoding="utf-8"))["content"]
    wt = json.load(open(os.path.join(work, f"520_wortzeiten_{lg}.json"), encoding="utf-8"))["tags"]
    cast = json.load(open(os.path.join(work, "casting.json"), encoding="utf-8"))
    stimme = {e["figur"]: e.get("stimme") for e in cast["plan"]["ensemble"] if e.get("stimme")}
    ht = {e["figur"]: e.get("tonhoehe_ht", 0) for e in cast["plan"]["ensemble"]}
    # 22.10.2026 (AP4): Ich-Erzaehler je Kapitel -> eigene Rede im eigenen Kapitel ist schon Erzaehlstimme (kein VC).
    # Ausnahme: gleiche Grundstimme, andere Figur (Zwilling) -> Spanne laeuft mit (VC ~ neutral, Sprechweise per Korrektur).
    erz_kap = cast["plan"].get("erzaehler_je_kapitel") or {}
    # 22.10.2026 (CK): Figuren mit Gemini-Standardstimme (plan.overlay_gemini, z. B. Zwillinge = Zephyr) duerfen nicht
    # VC-Vorlage sein -> Spanne direkt mit Gemini sprechen (tools/overlay_gemini.py); spricht der Kapitel-Erzaehler mit
    # derselben Stimme, bleibt die Spanne (nur Sprechweise-Korrektur): modus "kopie".
    gem = cast["plan"].get("overlay_gemini") or {}
    gstimme = cast["plan"].get("gemini_stimmen") or {}
    jobs_gem = []
    if nur:
        stimme = {k: v for k, v in stimme.items() if k in nur}
    audio = os.path.join(werk, "fassungen", lg, "audio")

    ziel = os.path.join(HIER, "gpu_overlay", f"{book_id}_{lg}" + ("_teil" if nur else ""))
    if nur and os.path.exists(os.path.join(ziel, "ergebnis.zip")):
        # fruehere Nachbesserung behalten: overlay_montage wendet alle _teil*-Pakete in zeitlicher Reihenfolge an
        n = 1
        while os.path.exists(f"{ziel}_v{n}"):
            n += 1
        os.rename(ziel, f"{ziel}_v{n}")
        print(f"  [overlay] fruehere Teil-Fassung -> {os.path.basename(ziel)}_v{n}")
    os.makedirs(os.path.join(ziel, "src"), exist_ok=True)
    os.makedirs(os.path.join(ziel, "ref"), exist_ok=True)

    jobs, fehlt = [], {"audio": 0, "timing": 0, "stimme": 0, "spanne": 0}
    for tid in sorted(sp):
        segs = sp[tid].get(lg) or []
        if not any(s["s"] != ERZ for s in segs):
            continue
        text = st06.get(tid, {}).get(lg, "")
        wav = os.path.join(audio, f"{tid}.wav")
        if not os.path.exists(wav):
            fehlt["audio"] += 1; continue
        zeiten = {z["i"]: (z["t0"], z["t1"]) for z in (wt.get(tid) or [])}
        if not zeiten:
            fehlt["timing"] += 1; continue
        tokens = [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]
        params, frames = _wav_lesen(wav)
        sr, bpf = params.framerate, params.sampwidth * params.nchannels
        dauer = len(frames) / bpf / sr
        # Segment -> Zeichenspanne im Text (Segmente = Text ohne Whitespace-Unterschiede)
        pos = 0
        for n, s in enumerate(segs):
            kern = s["t"].strip()
            a = text.find(kern[:12], pos) if kern else -1
            if a < 0:
                fehlt["spanne"] += 1; break
            b = a + len(kern)
            pos = b
            if s["s"] == ERZ or s["s"] == erz_kap.get(tid[:4]):
                continue
            if s["s"] not in stimme and s["s"] not in gem:
                fehlt["stimme"] += 1; continue
            idx = [i for i, (x, y) in enumerate(tokens) if x < b and y > a and i in zeiten]
            if not idx:
                fehlt["timing"] += 1; continue
            t0 = max(0.0, zeiten[idx[0]][0] - PAD)
            t1 = min(dauer, zeiten[idx[-1]][1] + PAD)
            jid = f"{tid}__{n}"
            f0, f1 = int(t0 * sr) * bpf, int(t1 * sr) * bpf
            _wav_schreiben(os.path.join(ziel, "src", f"{jid}.wav"), params, frames[f0:f1])
            if s["s"] in gem:
                modus = "kopie" if gstimme.get(erz_kap.get(tid[:4])) == gem[s["s"]] else "gemini"
                jobs_gem.append({"id": jid, "tag": tid, "figur": s["s"], "stimme": gem[s["s"]], "modus": modus,
                                 "text": kern, "t0": round(t0, 3), "t1": round(t1, 3), "lang": lg})
                continue
            _tonhoehe(os.path.join(ziel, "src", f"{jid}.wav"), ht.get(s["s"], 0))
            ref = stimme[s["s"]]
            jobs.append({"id": jid, "tag": tid, "figur": s["s"], "stimme": ref, "text": kern,
                         "t0": round(t0, 3), "t1": round(t1, 3), "lang": lg})
            rq = os.path.join(HIER, "stimmen_archiv", ref, f"muster_{lg}.wav")
            rz = os.path.join(ziel, "ref", f"{ref}.wav")
            if os.path.exists(rq) and not os.path.exists(rz):
                p, fr = _wav_lesen(rq)
                _wav_schreiben(rz, p, fr)
    json.dump({"werk": book_id, "lang": lg, "jobs": jobs}, open(os.path.join(ziel, "jobs.json"), "w",
              encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({"werk": book_id, "lang": lg, "jobs": jobs_gem}, open(os.path.join(ziel, "jobs_gemini.json"), "w",
              encoding="utf-8"), ensure_ascii=False, indent=1)
    if jobs_gem:
        print(f"[overlay] Gemini-Spannen: {sum(j['modus'] == 'gemini' for j in jobs_gem)} neu sprechen, "
              f"{sum(j['modus'] == 'kopie' for j in jobs_gem)} nur Sprechweise -> tools/overlay_gemini.py")
    figuren = {}
    for j in jobs:
        figuren[j["figur"]] = figuren.get(j["figur"], 0) + 1
    print(f"[overlay] {len(jobs)} Rede-Spannen -> {ziel}")
    print("  je Figur: " + ", ".join(f"{k} {v}" for k, v in sorted(figuren.items(), key=lambda x: -x[1])))
    print(f"  uebersprungen: {fehlt}")


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    nur = next((x.split("=", 1)[1].split(",") for x in sys.argv if x.startswith("--nur=")), None)
    main(a[0], a[1] if len(a) > 1 else "de", nur)
