"""READ LAYER — Overlay-Montage (lokal/VM, keine API).
Setzt die Chatterbox-Spannen in die Single-Speaker-Saetze ein.
Aufruf:  python tools/overlay_montage.py <book_id> [de|en]
Ablage:  authors/.../<werk>/fassungen/<lg>/audio_overlay/
           vc/<tag>.wav      Satz mit VC-Rede   (Variante A)
           tts/<tag>.wav     Satz mit TTS-Rede  (Variante B)
           spannen/vc|tts/   die einzelnen Rede-Spannen
           hoerliste.txt     Satz | Figur | Text  (zum Durchhoeren)
Die Single-Speaker-Ablage fassungen/<lg>/audio bleibt unberuehrt.
"""
import glob, json, os, shutil, sys, wave, zipfile

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lesen(p):
    with wave.open(p) as w:
        return w.getparams(), w.readframes(w.getnframes())


def _wortzeiten_hoerspiel(werk, lg, je_tag, neu_len):
    """22.10.2026: Gemini-Spannen sind laenger/kuerzer als die ersetzte Stelle -> Wortzeiten der Hoerspiel-Saetze
    verschieben (in der Spanne linear gestreckt, danach um die Differenz versetzt).
    -> work/520_wortzeiten_<lg>_hoerspiel.json (nur betroffene Saetze; export_demo --hoerspiel nutzt sie)."""
    q = os.path.join(werk, "work", f"520_wortzeiten_{lg}.json")
    if not os.path.exists(q):
        return
    tags = json.load(open(q, encoding="utf-8")).get("tags", {})
    erg = {}
    for tag, js in je_tag.items():
        if tag not in tags:
            continue
        sp = sorted((j["t0"], j["t1"], neu_len[j["id"]]) for j in js if j["id"] in neu_len)
        if not sp:
            continue

        def neu_t(t):
            d = 0.0
            for t0, t1, ln in sp:
                if t < t0:
                    break
                if t < t1:
                    return t0 + d + (t - t0) * ln / max(1e-3, t1 - t0)
                d += ln - (t1 - t0)
            return t + d
        erg[tag] = [dict(w, t0=round(neu_t(w["t0"]), 3), t1=round(neu_t(w["t1"]), 3)) for w in tags[tag]]
    json.dump({"sprache": lg, "einheit": "s", "tags": erg},
              open(os.path.join(werk, "work", f"520_wortzeiten_{lg}_hoerspiel.json"), "w", encoding="utf-8"))
    print(f"[montage] Wortzeiten Hoerspiel: {len(erg)} Saetze angepasst")


def main(book_id, lg="de"):
    werk = glob.glob(os.path.join(HIER, "authors", "*", "books", book_id))[0]
    paket = os.path.join(HIER, "gpu_overlay", f"{book_id}_{lg}")
    jobs = json.load(open(os.path.join(paket, "jobs.json"), encoding="utf-8"))["jobs"]
    if os.path.exists(os.path.join(paket, "jobs_gemini.json")):     # 22.10.2026: Gemini-Spannen (tools/overlay_gemini.py)
        jobs = jobs + json.load(open(os.path.join(paket, "jobs_gemini.json"), encoding="utf-8"))["jobs"]
    ziel = os.path.join(werk, "fassungen", lg, "audio_overlay")
    sp = os.path.join(ziel, "spannen")
    os.makedirs(sp, exist_ok=True)
    gem_ids = set()
    if os.path.exists(os.path.join(paket, "jobs_gemini.json")):
        gem_ids = {j["id"] for j in json.load(open(os.path.join(paket, "jobs_gemini.json"), encoding="utf-8"))["jobs"]}
    if os.path.exists(os.path.join(paket, "ergebnis.zip")):
        with zipfile.ZipFile(os.path.join(paket, "ergebnis.zip")) as z:
            # Gemini-Spannen (overlay_gemini) nicht mit alten VC-Ergebnissen ueberschreiben
            z.extractall(sp, [m for m in z.namelist() if os.path.basename(m)[:-4] not in gem_ids])
    # Nachbesserungen einzelner Figuren (_teil, _teil_v1, ...) ueberschreiben deren Spannen, aelteste zuerst
    teile = [t for t in glob.glob(paket + "_teil*") if os.path.exists(os.path.join(t, "ergebnis.zip"))]
    for teil in sorted(teile, key=lambda t: os.path.getmtime(os.path.join(t, "ergebnis.zip"))):
        with zipfile.ZipFile(os.path.join(teil, "ergebnis.zip")) as z:
            z.extractall(sp, [m for m in z.namelist() if os.path.basename(m)[:-4] not in gem_ids])
    # Korrektur NACH dem VC (Formant + Tonhoehe aus casting.json, Regel pipeline/trennung.py)
    sys.path.insert(0, os.path.join(HIER, "tools"))
    from overlay_korrektur import anwenden
    anwenden(book_id, lg)
    je_tag = {}
    for j in jobs:
        je_tag.setdefault(j["tag"], []).append(j)
    zeilen, fehl = [], 0
    neu_len = {}    # 22.10.2026: Laenge je eingesetzter Spanne (s) -> Wortzeiten der Hoerspiel-Saetze verschieben
    for var in ("vc", "tts"):
        os.makedirs(os.path.join(ziel, var), exist_ok=True)
        for tag, js in je_tag.items():
            params, base = lesen(os.path.join(werk, "fassungen", lg, "audio", f"{tag}.wav"))
            bpf, sr = params.sampwidth * params.nchannels, params.framerate
            out, pos = b"", 0
            for j in sorted(js, key=lambda x: x["t0"]):
                f = os.path.join(sp, "vc_korr" if var == "vc" else var, j["id"] + ".wav")
                if not os.path.exists(f):
                    fehl += 1
                    continue
                p2, neu = lesen(f)
                if p2.framerate != sr or p2.sampwidth != params.sampwidth:
                    fehl += 1
                    continue
                a, b = int(j["t0"] * sr) * bpf, int(j["t1"] * sr) * bpf
                out += base[pos:a] + neu
                if var == "vc":
                    neu_len[j["id"]] = len(neu) / bpf / sr
                pos = b
            out += base[pos:]
            with wave.open(os.path.join(ziel, var, f"{tag}.wav"), "wb") as w:
                w.setparams(params)
                w.writeframes(out)
    _wortzeiten_hoerspiel(werk, lg, je_tag, neu_len)
    for tag, js in sorted(je_tag.items()):
        zeilen.append(f"{tag} | " + "; ".join(f"{j['figur']}: {j['text']}" for j in js))
    open(os.path.join(ziel, "hoerliste.txt"), "w", encoding="utf-8").write(
        f"Overlay-Test {book_id} [{lg}] — Ordner vc/ (Variante A) und tts/ (Variante B), Original in ../audio/\n\n"
        + "\n".join(zeilen) + "\n")
    print(f"[montage] {len(je_tag)} Saetze x 2 Varianten -> {ziel}  (Probleme: {fehl})")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "de")
