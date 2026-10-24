"""READ LAYER - Eigenes Chatterbox-Modellgewicht: LoRA auf T3 aus LibriVox (AP claude/AP_lora_librivox.md), 17.10.2026.
TESTLAUF: Ramona Deininger-Schnabel (LibriVox reader 6507), ~10 h: Pinocchio, Fraeulein Else, Sterben.

Aufruf (start_lora_test.bat):
  py -3.11 -m modal run gpu_lora/lora_modal.py --schritt alle [--lauf ramona_test] [--werke "Pinocchio,Fräulein Else,Sterben"]
  --schritt holen | abschrift | schnitt | training | bewertung | alle      (jeder Schritt wiederaufnehmbar)
  --werke alle  -> alle 22 Ramona-Werke (Vollausbau, eigener --lauf)
  --mix standard -> Mischlauf (MIX_PLAN): Julia Niedermaier alles DE, Bernd Ungerer + Ramona je gleich viele Stunden,
                    kleine Werke zuerst; Deckel 40 % je Sprecher im Training (start_lora_mix.bat, Lauf mix_v1)
Schritte (AP 1-6):
  1 holen      archive.org-MP3s je Werk (Original-MP3 vor 128 vor 64 kbit)                  CPU
  2 abschrift  Whisper large-v3, Deutsch, Wortzeiten                                         L4, bis 10 parallel
  3 schnitt    Saetze aus Wortzeiten -> Schnitt am Tal wie Stage 58 3rd party (LibriVox) -> cb_pruefung (MMS_FA) sortiert aus
               (Vorlauf, Nachklang, verschmiert, zu kurz/lang) -> 24-kHz-FLAC 2-15 s
               + S3-Sprachtokens, Texttokens (sprech_norm wie Produktion), Stimmprofil (VE), Prosodie-Marke
  4 marken     Testlauf: Marke nur aus dem Audio (Tonhoehen-Streuung, Lautstaerke, Tempo; je Werk 0,25..0,85)
               -> emotion_adv. DeepSeek-Stimmungsklasse + Gegenprobe folgt im Vollausbau.
  5 training   LoRA (Rang 32) auf T3/Llama, A100, Bedingung = ANDERER Satz derselben Sprecherin (6 s Prompt + VE),
               Validierung auf 3 % zurueckgehaltenen Saetzen, Checkpoint je Validierung
  6 bewertung  Peter Pan Kap. 1 DE mit grossmutter_a: basis / bester / letzter Checkpoint
               -> Pruefung im Lauf (cb_pruefung), Stimmaehnlichkeit (VE) zur Referenz und zu Ramona, Prosodie lokal
Ablage: Modal-Volume readlayer-tts /lora/<lauf>/{mp3,abschrift,clips,daten,bericht,ckpt,bewertung}
        lokal gpu_lora/<lauf>/: bericht_*.json, training.json, bewertung/<variante>/*.wav, BERICHT.md, hoerliste.txt
"""
import json
import os
import time
from pathlib import Path
import modal

HIER = Path(__file__).resolve().parent
LESER = HIER.parent
SPRECHER = "6507"
TEST_WERKE = "Pinocchio,Fräulein Else,Sterben"
# Mischlauf (CK 18.10.2026): mehrere Sprecher; "<reader_id>:<Stunden|alle>" je Sprecher, kleine Werke zuerst.
# Budget "julia" = so viele Stunden wie Julia Niedermaier auf Deutsch hat (alles von ihr).
MIX_PLAN = "5424:alle,9565:julia,6507:julia"
# mix_v2 (CK 23.10.2026): Ramona-Dominanz austreiben -> Ramona raus, Hokuspokus neu; Julia + Bernd aus mix_v1 uebernommen
MIX_PLAENE = {"standard": MIX_PLAN, "v2": "5424:alle,9565:julia,2037:julia"}
UEBERNAHME_QUELLE = "mix_v1"   # fertige Schnipsel (daten/bericht/clips) je Werk werden kopiert statt neu geholt/geschnitten
RAMONA_QUELLE = "mix_v1"       # Gegenprobe Ramona + Ramona-VE-Zentrum, wenn der Lauf selbst keine Ramona-Daten hat
MAX_ANTEIL = 0.40          # kein Sprecher > 40 % der Trainingsstunden (Schutzregel AP)
ZEICHEN_PAUSE_MIN = 0.06   # s; Komma/Semikolon/Doppelpunkt/Gedankenstrich ohne hoerbare Pause = verschliffen
# CK 18.10.: Ramona verschleift oft die Interpunktion und hat starken Singsang -> halbes Gewicht, und von ihr
# werden bevorzugt die ruhigsten Saetze genommen (geringste Tonhoehen-Streuung) statt zufaelliger Auswahl.
SPRECHER_GEWICHT = {"6507": 0.5}
SPRECHER_RUHIG = {"6507"}
NIVELLIEREN = True         # CK 18.10.: alle Sprecher mit gleichen Stunden ins Training (Ausgleich statt Stimmengewinn)
PP_PAKET = LESER / "gpu_tts" / "u-mikemustermann-peter-and-wendy_de"   # jobs.json + ref.wav (grossmutter_a)
MAX_GPU = 10


def _hf_token():
    tok = os.environ.get("HF_TOKEN", "")
    env = LESER / ".env"
    if not tok and env.exists():
        for z in env.read_text(encoding="utf-8").splitlines():
            if z.strip().startswith("HF_TOKEN="):
                tok = z.split("=", 1)[1].strip().strip('"')
    return tok


app = modal.App("readlayer-lora")
vol = modal.Volume.from_name("readlayer-tts", create_if_missing=True)
GEHEIM = [modal.Secret.from_dict({"HF_TOKEN": _hf_token()})]

cb_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libsndfile1")
    .pip_install("chatterbox-tts", "huggingface_hub", "safetensors", "soundfile")
    .env({"HF_HOME": "/vol/hf", "TORCH_HOME": "/vol/torch", "PYTHONUNBUFFERED": "1", "TQDM_DISABLE": "1"})
    .add_local_file(str(HIER / "lora_kern.py"), remote_path="/rl/lora_kern.py")
    .add_local_dir(str(LESER / "config"), remote_path="/rl/config", ignore=["*.bak*", "__pycache__"])
    .add_local_file(str(LESER / "pipeline" / "__init__.py"), remote_path="/rl/pipeline/__init__.py")
    .add_local_file(str(LESER / "pipeline" / "schnitt_lib.py"), remote_path="/rl/pipeline/schnitt_lib.py")
    .add_local_file(str(LESER / "daten" / "index.json"), remote_path="/rl/daten/index.json")
    .add_local_file(str(LESER / "gpu_tts" / "cb_pruefung.py"), remote_path="/rl/cb_pruefung.py")
    .add_local_file(str(LESER / "gpu_tts" / "cb_batch.py"), remote_path="/rl/cb_batch.py")
    .add_local_file(str(PP_PAKET / "jobs.json"), remote_path="/rl/pp_jobs.json")
    .add_local_file(str(PP_PAKET / "ref.wav"), remote_path="/rl/pp_ref.wav")
    .add_local_file(str(LESER / "stimmen_archiv" / "herr_a" / "muster_de.wav"), remote_path="/rl/stimme_herr_a.wav")
)


def _whisper_laden():
    from huggingface_hub import snapshot_download
    snapshot_download("Systran/faster-whisper-large-v3", local_dir="/modell")


whisper_image = (
    modal.Image.from_registry("nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04", add_python="3.11")
    .apt_install("ffmpeg")
    .pip_install("faster-whisper==1.1.1", "huggingface_hub", "requests")
    .run_function(_whisper_laden)
    .env({"PYTHONUNBUFFERED": "1"})
)


# ---------------------------------------------------------------- 1 holen
@app.function(image=cb_image, volumes={"/vol": vol}, timeout=3 * 3600, cpu=2)
def holen(lauf: str, aid: str) -> dict:
    import re, urllib.request
    ziel = Path(f"/vol/lora/{lauf}/mp3/{aid}")
    ziel.mkdir(parents=True, exist_ok=True)
    meta = json.loads(urllib.request.urlopen(f"https://archive.org/metadata/{aid}", timeout=120).read())
    mp3 = [f["name"] for f in meta.get("files", []) if f.get("name", "").lower().endswith(".mp3")
           and "/" not in f["name"] and "sample" not in f["name"].lower()]
    wahl = [f for f in mp3 if not re.search(r"_\d+kb\.mp3$", f, re.I)]           # Original (meist 128 kbit)
    for suf in ("_128kb.mp3", "_64kb.mp3"):
        if not wahl:
            wahl = [f for f in mp3 if f.lower().endswith(suf)]
    n = 0
    for name in sorted(wahl):
        d = ziel / name
        if d.exists() and d.stat().st_size > 0:
            continue
        tmp = d.with_suffix(".tmp")
        for versuch in range(3):
            try:
                with urllib.request.urlopen(f"https://archive.org/download/{aid}/{name}", timeout=300) as r, open(tmp, "wb") as f:
                    while True:
                        b = r.read(1 << 20)
                        if not b:
                            break
                        f.write(b)
                tmp.rename(d)
                n += 1
                break
            except Exception as ex:
                print(f"[holen] {aid}/{name} Versuch {versuch + 1}: {ex}", flush=True)
                time.sleep(5)
    (ziel / "_fertig.json").write_text(json.dumps({"dateien": sorted(wahl), "titel": meta.get("metadata", {}).get("title")},
                                                   ensure_ascii=False), encoding="utf-8")
    vol.commit()
    return {"werk": aid, "dateien": len(wahl), "neu": n}


# ---------------------------------------------------------------- 1b Referenztext (LibriVox "Online text")
@app.function(image=cb_image, volumes={"/vol": vol}, timeout=1800, cpu=1)
def referenz(lauf: str, aid: str, lv_url: str) -> dict:
    """Online-Text der LibriVox-Seite -> /lora/<lauf>/text/<aid>.json {quelle, absaetze}.
    gutenberg.org: Plaintext (.txt.utf-8). projekt-gutenberg.org (neu): alle /chapter/N-Seiten.
    Sonst: die verlinkte Seite. Absaetze aus <p>, doppelte (Lesemodus) entfernt."""
    import re, html as H, urllib.request, urllib.parse

    def get(u):
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (READ LAYER)"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read().decode("utf-8", "replace"), r.geturl()

    ziel = Path(f"/vol/lora/{lauf}/text")
    ziel.mkdir(parents=True, exist_ok=True)
    lv, _ = get(lv_url)
    m = re.search(r'<a[^>]+href="([^"]+)"[^>]*>\s*(?:Online[ -]text|Source text|Text source)', lv, re.I)
    url = H.unescape(m.group(1)) if m else ""
    absaetze, seiten = [], []
    g = re.search(r"gutenberg\.org/(?:ebooks|files|cache/epub)/(\d+)", url)
    if g and "projekt-gutenberg" not in url:
        txt, _ = get(f"https://www.gutenberg.org/ebooks/{g.group(1)}.txt.utf-8")
        a = re.search(r"\*\*\* ?START OF.*?\*\*\*", txt)
        e = re.search(r"\*\*\* ?END OF", txt)
        txt = txt[a.end() if a else 0:e.start() if e else len(txt)]
        absaetze = [" ".join(p.split()) for p in re.split(r"\n\s*\n", txt) if p.strip()]
        seiten = [url]
    elif url:
        h0, final = get(url)
        kap = {}
        for href, n in re.findall(r'href="([^"]*?/chapter/(\d+))[^"]*"', h0):
            kap[int(n)] = urllib.parse.urljoin(final, H.unescape(href))
        seiten = [kap[k] for k in sorted(kap)] or [final]
        gesehen = set()
        for u in seiten:
            h = h0 if u == final else get(u)[0]
            for roh in re.findall(r"<p[^>]*>(.*?)</p>", h, re.S | re.I):
                t = " ".join(H.unescape(re.sub(r"<[^>]+>", " ", roh)).split())
                if len(t) >= 20 and t not in gesehen:
                    gesehen.add(t)
                    absaetze.append(t)
    erg = {"quelle": url, "seiten": len(seiten), "absaetze": absaetze}
    (ziel / f"{aid}.json").write_text(json.dumps(erg, ensure_ascii=False), encoding="utf-8")
    vol.commit()
    return {"werk": aid, "quelle": url, "seiten": len(seiten), "absaetze": len(absaetze),
            "woerter": sum(len(a.split()) for a in absaetze)}


# ---------------------------------------------------------------- 2 abschrift
@app.function(image=whisper_image, gpu="L4", volumes={"/vol": vol}, timeout=3 * 3600)
def abschrift(lauf: str, aid: str, namen: list) -> list:
    from faster_whisper import WhisperModel, BatchedInferencePipeline
    vol.reload()
    # 17.10. Testlauf 1: ohne Prompt fehlten ueber lange Strecken die Satzzeichen -> kaum Saetze erkannt.
    # Batch-Pipeline gibt den Prompt JEDEM VAD-Abschnitt mit -> Satzzeichen durchgehend.
    m = BatchedInferencePipeline(WhisperModel("/modell", device="cuda", compute_type="float16"))
    PROMPT = ("Es war einmal ein alter Mann, der lebte allein. Eines Tages sagte er: \u201eKomm her, mein Kind!\u201c "
              "Sie lachte; dann ging sie langsam nach Hause \u2013 m\u00fcde, aber froh. Warum nur?")
    aus = Path(f"/vol/lora/{lauf}/abschrift/{aid}")
    aus.mkdir(parents=True, exist_ok=True)
    fertig = []
    for name in namen:
        t0 = time.time()
        segs, info = m.transcribe(f"/vol/lora/{lauf}/mp3/{aid}/{name}", language="de", beam_size=5,
                                  word_timestamps=True, initial_prompt=PROMPT, batch_size=16)
        woerter = [[w.word.strip(), round(w.start, 3), round(w.end, 3), round(w.probability, 3)]
                   for s in segs for w in (s.words or []) if w.word.strip()]
        (aus / (Path(name).stem + ".json")).write_text(json.dumps({"dauer": info.duration, "woerter": woerter},
                                                                  ensure_ascii=False), encoding="utf-8")
        fertig.append(f"{name}: {info.duration / 60:.1f} min Audio in {(time.time() - t0) / 60:.1f} min")
        vol.commit()
    return fertig


# ---------------------------------------------------------------- 3+4 schnitt, pruefung, tokens, marken
MIN_S, MAX_S = 2.0, 15.0


def _f0_streuung(a, sr=16000):
    import numpy as np
    n, h, lo, hi = int(sr * 0.04), int(sr * 0.01), int(sr / 400), int(sr / 70)
    f0 = []
    for i in range(0, len(a) - n, h):
        x = a[i:i + n] - a[i:i + n].mean()
        if (x ** 2).mean() < 1e-4:
            continue
        r = np.correlate(x, x, "full")[n - 1:]
        r = r / (r[0] + 1e-9)
        k = lo + int(np.argmax(r[lo:hi]))
        if r[k] > 0.45:
            f0.append(sr / k)
    if len(f0) < 10:
        return None
    f0 = np.array(f0)
    return float((12 * np.log2(f0 / np.median(f0))).std())


@app.function(image=cb_image, gpu="L4", volumes={"/vol": vol}, timeout=4 * 3600, secrets=GEHEIM)
def schnitt(lauf: str, aid: str) -> dict:
    import re, subprocess, sys
    import numpy as np, torch, soundfile as sf, librosa
    sys.path.insert(0, "/rl")
    import cb_pruefung
    from cb_pruefung import Pruefer, lautwoerter
    from cb_batch import sprech_norm
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    vol.reload()
    basis = Path(f"/vol/lora/{lauf}")
    clips = basis / "clips" / aid
    clips.mkdir(parents=True, exist_ok=True)
    (basis / "daten").mkdir(parents=True, exist_ok=True)
    (basis / "bericht").mkdir(parents=True, exist_ok=True)

    ENDE = re.compile(r"[.!?…][\"'»«“”„)\]]*$")
    SPERRE = re.compile(r"librivox|gemeinfrei|public domain|aufnahme|gelesen von|www|\.org|punkt org|"
                        r"ende (von|des|der)|kapitel\s+\w+\s+(von|aus)", re.I)
    zaehl = {}

    def weg(grund):
        zaehl[grund] = zaehl.get(grund, 0) + 1

    # --- Saetze aus Wortzeiten ---------------------------------------------------------------
    # Referenztext (LibriVox "Online text"): Woerter + Satzzeichen aus dem Buch, Zeiten aus Whisper (Abgleich wie
    # Stage 58 3rd party: difflib, hier fortlaufend ueber alle Dateien mit Zeiger = STROM-MODUS)
    import difflib

    def nrm(w):
        return re.sub(r"[^a-z0-9äöü]", "", w.lower().replace("ß", "ss"))

    ref_toks = []
    rp = basis / "text" / f"{aid}.json"
    if rp.exists():
        ref_toks = " ".join(json.loads(rp.read_text(encoding="utf-8"))["absaetze"]).split()
    ref_norm = [nrm(t) for t in ref_toks]
    zeiger = 0
    zaehl["_referenz_woerter"] = len(ref_toks)

    kandidaten = []           # (datei, s0, e0, vor, nach, text, p_mittel, p_min) - je Datei in Lesefolge
    for js in sorted((basis / "abschrift" / aid).glob("*.json")):
        d = json.loads(js.read_text(encoding="utf-8"))
        W, dauer = d["woerter"], d["dauer"]
        if ref_toks:
            sn = [nrm(w[0]) for w in W]
            lo, hi = zeiger, min(len(ref_toks), zeiger + int(len(sn) * 1.5) + 800)
            sm = difflib.SequenceMatcher(a=ref_norm[lo:hi], b=sn, autojunk=False)
            paar = {lo + ai + k: bj + k for ai, bj, n in sm.get_matching_blocks() for k in range(n)}
            if len(paar) >= 0.6 * len(sn):
                r0, r1 = min(paar), max(paar)
                neu_w = [[ref_toks[r], W[paar[r]][1], W[paar[r]][2], 1.0, True] if r in paar
                         else [ref_toks[r], None, None, 0.2, False] for r in range(r0, r1 + 1)]
                i = 0                                   # Zeiten ungetroffener Woerter verteilen
                while i < len(neu_w):
                    if neu_w[i][1] is None:
                        j = i
                        while neu_w[j][1] is None:
                            j += 1
                        t0, t1 = neu_w[i - 1][2], neu_w[j][1]
                        for k in range(i, j):
                            f = (k - i + 1) / (j - i + 1)
                            neu_w[k][1] = neu_w[k][2] = round(t0 + (t1 - t0) * f, 3)
                        i = j
                    i += 1
                W = neu_w
                zeiger = r1 + 1
                zaehl["_ref_treffer"] = zaehl.get("_ref_treffer", 0) + len(paar)
            else:
                zaehl["_ref_datei_whisper"] = zaehl.get("_ref_datei_whisper", 0) + 1
        satz, saetze = [], []
        for i, w in enumerate(W):
            satz.append(i)
            if ENDE.search(w[0]):
                saetze.append(satz)
                satz = []
        # Diagnose Satzzeichen (Testlauf 1)
        zaehl["_woerter"] = zaehl.get("_woerter", 0) + len(W)
        zaehl["_audio_min"] = round(zaehl.get("_audio_min", 0) + dauer / 60, 1)
        # kurze Saetze mit dem folgenden zusammenfassen (Pause < 1 s, zusammen <= MAX_S)
        zus = []
        for satz in saetze:
            if zus and W[zus[-1][-1]][2] - W[zus[-1][0]][1] < MIN_S and \
                    W[satz[0]][1] - W[zus[-1][-1]][2] < 1.0 and W[satz[-1]][2] - W[zus[-1][0]][1] <= MAX_S:
                zus[-1] = zus[-1] + satz
            else:
                zus.append(satz)
        saetze = zus

        def teilen(idx):
            s, e = W[idx[0]][1], W[idx[-1]][2]
            if e - s <= MAX_S:
                return [idx]
            kand = [k for k in range(len(idx) - 1)
                    if W[idx[k]][0][-1:] in ",;:—–-" and W[idx[k + 1]][1] - W[idx[k]][2] >= 0.3]
            if not kand:      # sonst an der laengsten echten Pause (>= 0,35 s)
                luecken = [(W[idx[k + 1]][1] - W[idx[k]][2], k) for k in range(len(idx) - 1)]
                kand = [k for g, k in luecken if g >= 0.35]
            if not kand:
                return [idx]          # bleibt als Nachbar fuer die Schnitte, faellt spaeter als zu lang raus
            mitte = (s + e) / 2
            k = min(kand, key=lambda k: abs(W[idx[k]][2] - mitte))
            return teilen(idx[:k + 1]) + teilen(idx[k + 1:])

        for satz in saetze:
            for idx in teilen(satz):
                a, b = idx[0], idx[-1]
                s0, e0 = W[a][1], W[b][2]
                vor = W[a - 1][2] if a > 0 else 0.0
                nach = W[b + 1][1] if b + 1 < len(W) else dauer
                text = " ".join(W[i][0] for i in idx)
                ps = [W[i][3] for i in idx]
                pm = sum(ps) / len(ps)
                if len(W[a]) > 4 and not (W[a][4] and W[b][4]):
                    pm = 0.0                     # erstes/letztes Wort nicht im Audio gefunden -> Grenze unsicher
                # Interpunktion verschliffen? (CK 18.10.): Satzzeichen im Satz, aber praktisch keine Pause danach
                zn = [k for k in idx[:-1] if W[k][0][-1:] in ",;:—–" and W[k + 1][1] > W[k][2] - 0.01]
                zv = sum(1 for k in zn if W[k + 1][1] - W[k][2] < ZEICHEN_PAUSE_MIN)
                kandidaten.append((js.stem, s0, e0, vor, nach, text, pm, min(ps), (zv, len(zn))))
    print(f"[{aid}] {len(kandidaten)} Satz-Kandidaten", flush=True)

    # Sprechtempo der Sprecherin -> Pruefer-Erwartung (cb_pruefung ist auf Chatterbox geeicht)
    tempi = [(k[2] - k[1]) / max(1, len(k[5])) for k in kandidaten if MIN_S <= k[2] - k[1] <= MAX_S]
    ms = float(np.median(tempi)) if tempi else 0.07
    cb_pruefung.MS_JE_ZEICHEN = ms
    pr = Pruefer("cuda")

    # --- Schnitt wie Stage 58 (3rd party) LibriVox: Tal zwischen zwei Saetzen + Konsonanten-Nachlauf ------
    # (pipeline/schnitt_lib.py: _find_valley, _end_consonant_ms, TAIL/SEARCH_PAD/NEXT_GUARD; CK am Ohr bestaetigt)
    from pipeline import schnitt_lib as s58

    def grenzen(einheiten):
        """einheiten: [(s0, e0, text)] einer Datei in Lesefolge -> [(a_s, b_s)] (Logik aus s58._cut_and_write)."""
        tail_s = s58.TAIL_MS / 1000.0
        cuts = []
        for i in range(len(einheiten) - 1):
            end_n, start_n1 = einheiten[i][1], einheiten[i + 1][0]
            end_corr = end_n + s58._end_consonant_ms(einheiten[i][2]) / 1000.0
            if start_n1 - end_n < 0.05:
                lo, hi = end_corr - s58.SEARCH_PAD_S, end_corr + 0.8
                clamp = hi
            else:
                lo, hi = end_corr - s58.SEARCH_PAD_S, start_n1 + s58.SEARCH_PAD_S
                clamp = start_n1 - s58.NEXT_GUARD_S
            cut = max(min(s58._find_valley(x16, SR, lo, hi) + tail_s, clamp), end_corr)
            cuts.append(cut)
        bounds = [max(0.0, einheiten[0][0] - 0.1)] + cuts + [einheiten[-1][1] + tail_s]
        return list(zip(bounds[:-1], bounds[1:]))

    # --- schneiden + pruefen -----------------------------------------------------------------
    SR = 24000
    behalten = []
    dateien = []
    for k in kandidaten:
        if not dateien or dateien[-1][0] != k[0]:
            dateien.append((k[0], []))
        dateien[-1][1].append(k)
    for stem, liste in dateien:
        mp3 = next((basis / "mp3" / aid).glob(stem + ".mp3"))
        roh = subprocess.run(["ffmpeg", "-v", "quiet", "-i", str(mp3), "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                             capture_output=True, check=True).stdout
        x16 = np.frombuffer(roh, dtype="<i2")
        gr = grenzen([(k[1], k[2], k[5]) for k in liste])
        for ix, ((st_, s0, e0, vor, nach, text, pm, pmin, (zv, zn)), (a_s, b_s)) in enumerate(zip(liste, gr)):
            if SPERRE.search(text) or s0 < 12.0:
                weg("ansage_librivox"); continue
            if re.search(r"\d", text):
                weg("ziffern"); continue
            if b_s - a_s > MAX_S + 0.5:
                weg("zu_lang_ungeteilt"); continue
            if b_s - a_s < MIN_S:
                weg("zu_kurz"); continue
            if pm < 0.7 or pmin < 0.15:
                weg("abschrift_unsicher"); continue
            if zn and zv * 2 > zn:               # mehr als die Haelfte der Satzzeichen ohne Pause -> verschliffen
                weg("zeichen_verschliffen"); continue
            x = x16[int(a_s * SR):int(b_s * SR)].astype(np.float32) / 32768.0
            erg = pr.pruefe(text, torch.from_numpy(x).reshape(1, -1), SR)
            if erg["grund"]:
                weg("pruefung_" + erg["grund"]); continue
            # Testlauf 2 (CK 20:51): LoRA schnitt Satzenden ~400 ms zu frueh ab -> Trainingsclips endeten direkt hinter dem
            # letzten Laut (Tal + 80 ms). Jetzt: Ende = letztes Wort (MMS_FA) + 0,40 s natuerliche Pause, hoechstens bis
            # kurz vor den naechsten Satz. So lernt das Modell Ausklang + Pause vor dem Stopp-Token.
            if erg.get("letzt") is None:
                weg("ende_unbekannt"); continue
            naechst = gr[ix + 1][0] if ix + 1 < len(gr) else len(x16) / SR
            if ix + 1 < len(liste):
                naechst = min(naechst, liste[ix + 1][1] - 0.05)
            ende = min(a_s + erg["letzt"] + 0.40, naechst)
            if ende - (a_s + erg["letzt"]) < 0.15:
                weg("keine_pause_nach_satz"); continue
            x = x16[int(a_s * SR):int(max(ende, a_s + erg["letzt"] + 0.15) * SR)].astype(np.float32) / 32768.0
            if len(x) / SR > MAX_S + 0.6:
                weg("zu_lang_ungeteilt"); continue
            cid = f"{aid}__{stem}__{int(s0 * 100):07d}"
            sf.write(str(clips / f"{cid}.flac"), x, SR)
            behalten.append({"id": cid, "werk": aid, "text": text, "dauer": round(len(x) / SR, 2), "x": x})
        print(f"[{aid}] {stem}: {len(behalten)} behalten bisher", flush=True)
    del pr
    torch.cuda.empty_cache()

    # --- Tokens, Stimmprofil, Prosodie-Marke ---------------------------------------------------
    model = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
    tok = model.s3gen.tokenizer
    for i in range(0, len(behalten), 16):
        gruppe = behalten[i:i + 16]
        w16 = [librosa.resample(r["x"], orig_sr=SR, target_sr=16000).astype(np.float32) for r in gruppe]
        with torch.inference_mode():
            st, sl = tok.forward(w16)
            ve = model.ve.embeds_from_wavs(w16, sample_rate=16000)
        for j, r in enumerate(gruppe):
            r["speech"] = st[j, :sl[j]].cpu().tolist()
            r["ve"] = [round(float(v), 5) for v in ve[j]]
            r["text_ids"] = model.tokenizer.text_to_tokens(sprech_norm(r["text"]), language_id="de")[0].tolist()
            a16 = w16[j]
            r["f0"] = _f0_streuung(a16)
            fr = a16[: len(a16) // 320 * 320].reshape(-1, 320)
            r["laut"] = float(np.percentile(20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9), 95))
            r["tempo"] = len(r["text"]) / r["dauer"]
            del r["x"]
    # Marke je Werk: z-Werte -> Rang -> 0,25 .. 0,85
    ok = [r for r in behalten if r["f0"] is not None]
    if ok:
        def z(k):
            v = np.array([r[k] for r in ok]); return (v - v.mean()) / (v.std() + 1e-9)
        s = 0.5 * z("f0") + 0.3 * z("laut") + 0.2 * z("tempo")
        rang = s.argsort().argsort() / max(1, len(s) - 1)
        for r, p in zip(ok, rang):
            r["marke"] = round(0.25 + 0.6 * float(p), 3)
    for r in behalten:
        r.setdefault("marke", 0.5)
    torch.save(behalten, str(basis / "daten" / f"{aid}.pt"))
    std = sum(r["dauer"] for r in behalten) / 3600
    bericht = {"werk": aid, "kandidaten": len(kandidaten), "behalten": len(behalten), "stunden": round(std, 2),
               "ms_je_zeichen": round(ms, 4), "verworfen": dict(sorted(zaehl.items(), key=lambda x: -x[1])),
               "speech_tokens_median": int(np.median([len(r["speech"]) for r in behalten])) if behalten else 0,
               "beispiele": [r["text"] for r in behalten[:5]]}
    (basis / "bericht" / f"{aid}.json").write_text(json.dumps(bericht, ensure_ascii=False, indent=1), encoding="utf-8")
    vol.commit()
    return bericht


# ---------------------------------------------------------------- 5 training
@app.function(image=cb_image, volumes={"/vol": vol}, timeout=1800, cpu=1)
def uebernehmen(quelle: str, lauf: str, aids: list) -> list:
    """Fertige Schnipsel eines frueheren Laufs uebernehmen (CK 23.10.): daten/<aid>.pt, bericht/<aid>.json.
    Clips NICHT (zehntausende Einzeldateien -> Timeout 23.10.; Training braucht nur die .pt).
    Ausserdem das Ramona-VE-Zentrum der Quelle (Messgroesse 'Aehnlich Ramona')."""
    import shutil
    vol.reload()
    q, z = Path(f"/vol/lora/{quelle}"), Path(f"/vol/lora/{lauf}")
    for d in ("daten", "bericht", "ckpt"):
        (z / d).mkdir(parents=True, exist_ok=True)
    fertig = []
    for aid in aids:
        if not (q / "daten" / f"{aid}.pt").exists():
            continue
        shutil.copy2(q / "daten" / f"{aid}.pt", z / "daten" / f"{aid}.pt")
        if (q / "bericht" / f"{aid}.json").exists():
            shutil.copy2(q / "bericht" / f"{aid}.json", z / "bericht" / f"{aid}.json")
        fertig.append(aid)
    rq = Path(f"/vol/lora/{RAMONA_QUELLE}/ckpt/ve_zentrum_6507.pt")
    if rq.exists():
        shutil.copy2(rq, z / "ckpt" / "ramona_ve_zentrum.pt")
    vol.commit()
    return fertig


@app.function(image=cb_image, gpu="A100", volumes={"/vol": vol}, timeout=8 * 3600, secrets=GEHEIM)
def training(lauf: str, epochen: int = 3, lr: float = 2e-4, rang: int = 32, bs: int = 16, eval_alle: int = 250) -> dict:
    import random, math, sys, zlib
    import torch, torch.nn.functional as F
    sys.path.insert(0, "/rl")
    import lora_kern
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    from chatterbox.models.t3.modules.cond_enc import T3Cond
    vol.reload()
    basis = Path(f"/vol/lora/{lauf}")
    (basis / "ckpt").mkdir(parents=True, exist_ok=True)
    daten = []
    for p in sorted((basis / "daten").glob("*.pt")):
        daten += torch.load(str(p), weights_only=False)
    daten = [r for r in daten if 10 <= len(r["speech"]) <= 400 and len(r["text_ids"]) <= 300]
    # Sprecher je Werk (Mischlauf, werke.json von main); Altlaeufe: alle = SPRECHER
    try:
        zuord = json.loads((basis / "werke.json").read_text(encoding="utf-8"))
    except Exception:
        zuord = {}
    for r in daten:
        r["sprecher"] = zuord.get(r["werk"], {}).get("sprecher", SPRECHER)
    # Deckel: kein Sprecher > MAX_ANTEIL der Stunden (deterministisch ausduennen)
    std = {}
    for r in daten:
        std[r["sprecher"]] = std.get(r["sprecher"], 0) + r["dauer"]
    if len(std) > 1:
        for _ in range(10):
            ges = sum(std.values())
            gross = max(std, key=std.get)
            if std[gross] <= MAX_ANTEIL * ges + 1:
                break
            rest = ges - std[gross]
            ziel = MAX_ANTEIL / (1 - MAX_ANTEIL) * rest
            anteil = ziel / std[gross]
            daten = [r for r in daten if r["sprecher"] != gross or zlib.crc32(r["id"].encode()) % 1000 < anteil * 1000]
            std[gross] = sum(r["dauer"] for r in daten if r["sprecher"] == gross)
    # NIVELLIERUNG (CK 18.10.2026): Ziel ist ein ausgeglichener Adapter, nicht die Stimmen -> jeder Sprecher
    # traegt gleich viele Stunden bei (alle auf den kleinsten Anteil gekuerzt, deterministisch).
    if NIVELLIEREN and len(std) > 1:
        basis_h = min(v / SPRECHER_GEWICHT.get(k, 1.0) for k, v in std.items())
        for sid in list(std):
            ziel = basis_h * SPRECHER_GEWICHT.get(sid, 1.0)
            if std[sid] <= ziel * 1.02:
                continue
            eigene = [r for r in daten if r["sprecher"] == sid]
            if sid in SPRECHER_RUHIG:            # ruhigste zuerst (Tonhoehen-Streuung), bis Ziel erreicht
                eigene.sort(key=lambda r: (r.get("f0") is None, r.get("f0") or 0))
            else:                                # sonst deterministisch gemischt
                eigene.sort(key=lambda r: zlib.crc32(r["id"].encode()))
            behalten_ids, summe = set(), 0.0
            for r in eigene:
                if summe >= ziel:
                    break
                behalten_ids.add(r["id"])
                summe += r["dauer"]
            daten = [r for r in daten if r["sprecher"] != sid or r["id"] in behalten_ids]
            std[sid] = summe
    anteile = {k: round(v / 3600, 2) for k, v in std.items()}
    print(f"Sprecher-Stunden nach Deckel: {anteile}", flush=True)
    val = [r for r in daten if zlib.crc32(r["id"].encode()) % 100 < 3]
    train = [r for r in daten if zlib.crc32(r["id"].encode()) % 100 >= 3]
    pool = {}
    for r in train:
        if len(r["speech"]) >= 150:
            pool.setdefault(r["werk"], []).append(r)
    zentrum = torch.tensor([r["ve"] for r in daten]).mean(0)
    if len(std) == 1:                         # Altname (Einzelsprecher-Laeufe); Mischlauf ohne Ramona: Zentrum aus Uebernahme bleibt
        torch.save(zentrum, str(basis / "ckpt" / "ramona_ve_zentrum.pt"))
    for sid in std:
        z = torch.tensor([r["ve"] for r in daten if r["sprecher"] == sid]).mean(0)
        torch.save(z, str(basis / "ckpt" / f"ve_zentrum_{sid}.pt"))
        if sid == "6507":
            torch.save(z, str(basis / "ckpt" / "ramona_ve_zentrum.pt"))
    print(f"Daten: {len(train)} Training, {len(val)} Validierung, "
          f"{sum(r['dauer'] for r in train) / 3600:.1f} h", flush=True)

    model = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
    t3 = model.t3
    del model.s3gen
    hp = t3.hp
    n_lora = lora_kern.einbauen(t3, rang=rang, alpha=2 * rang)
    params = lora_kern.lora_parameter(t3)
    print(f"LoRA: {n_lora} Schichten, {sum(p.numel() for p in params) / 1e6:.1f} Mio. Parameter", flush=True)
    opt = torch.optim.AdamW(params, lr=lr, weight_decay=0.0)

    def batches(liste, rng, mischen):
        s = sorted(liste, key=lambda r: (len(r["text_ids"]), len(r["speech"])))   # wenig Text-Polster
        b = [s[i:i + bs] for i in range(0, len(s), bs)]
        if mischen:
            rng.shuffle(b)
        return b

    def tensoren(rs, rng):
        B = len(rs)
        tt = [[hp.start_text_token] + r["text_ids"] + [hp.stop_text_token] for r in rs]
        ss = [[hp.start_speech_token] + r["speech"] + [hp.stop_speech_token] for r in rs]
        text = torch.full((B, max(map(len, tt))), hp.stop_text_token, dtype=torch.long)
        sp = torch.full((B, max(map(len, ss))), hp.stop_speech_token, dtype=torch.long)
        for i, (a, b) in enumerate(zip(tt, ss)):
            text[i, :len(a)] = torch.tensor(a)
            sp[i, :len(b)] = torch.tensor(b)
        conds = []
        for r in rs:
            kand = pool.get(r["werk"]) or [c for v in pool.values() for c in v]
            c = rng.choice(kand)
            while c["id"] == r["id"] and len(kand) > 1:
                c = rng.choice(kand)
            conds.append(c)
        cond = T3Cond(speaker_emb=torch.tensor([c["ve"] for c in conds], dtype=torch.float32),
                      cond_prompt_speech_tokens=torch.tensor([c["speech"][:hp.speech_cond_prompt_len] for c in conds]),
                      emotion_adv=torch.tensor([float(r["marke"]) for r in rs]).view(B, 1, 1)).to(device="cuda")
        return (cond, text.cuda(), torch.tensor(list(map(len, tt))).cuda(), sp.cuda(), torch.tensor(list(map(len, ss))).cuda())

    def verlust(rs, rng):
        cond, text, tl, sp, sl = tensoren(rs, rng)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            out = t3.forward(t3_cond=cond, text_tokens=text, text_token_lens=tl, speech_tokens=sp,
                             speech_token_lens=sl, training=True)
        logits = out.speech_logits[:, :-1].float()          # Position i sagt Token i+1 voraus
        ziel = sp[:, 1:].clone()
        ziel[torch.arange(ziel.size(1), device="cuda")[None] >= (sl - 1)[:, None]] = -100
        return F.cross_entropy(logits.reshape(-1, logits.size(-1)), ziel.reshape(-1), ignore_index=-100)

    @torch.no_grad()
    def validieren():
        t3.eval()
        rng = random.Random(7)
        summe, n = 0.0, 0
        for b in batches(val, rng, False):
            summe += float(verlust(b, rng)) * len(b)
            n += len(b)
        t3.train()
        return summe / max(1, n)

    rng = random.Random(1234)
    gesamt = epochen * math.ceil(len(train) / bs)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(1.0, (s + 1) / 100) * 0.5 * (1 + math.cos(math.pi * min(1.0, s / gesamt))))
    verlauf = {"lauf": lauf, "rang": rang, "lr": lr, "bs": bs, "epochen": epochen, "schritte_gesamt": gesamt,
               "train_saetze": len(train), "val_saetze": len(val), "val": [], "train": [], "sprecher_stunden": anteile}
    v0 = validieren()
    verlauf["val"].append([0, round(v0, 4)])
    print(f"Schritt 0: Validierung {v0:.4f} (Grundmodell)", flush=True)
    bester, schritt, t0, lauf_summe = (v0, None), 0, time.time(), []
    meta = {"rang": rang, "alpha": 2 * rang, "basis": "chatterbox-multilingual t3_mtl23ls_v2",
            "sprecher": "LibriVox " + "+".join(sorted(std)), "lauf": lauf}
    t3.train()
    for ep in range(epochen):
        for b in batches(train, rng, True):
            loss = verlust(b, rng)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            opt.step()
            sched.step()
            schritt += 1
            lauf_summe.append(float(loss))
            if schritt % 50 == 0:
                verlauf["train"].append([schritt, round(sum(lauf_summe) / len(lauf_summe), 4)])
                print(f"Ep {ep + 1} Schritt {schritt}/{gesamt}: {verlauf['train'][-1][1]:.4f} "
                      f"({(time.time() - t0) / 60:.1f} min)", flush=True)
                lauf_summe = []
            if schritt % eval_alle == 0 or schritt == gesamt:
                v = validieren()
                verlauf["val"].append([schritt, round(v, 4)])
                name = f"step_{schritt:05d}.safetensors"
                lora_kern.speichern(t3, str(basis / "ckpt" / name), {**meta, "schritt": schritt, "val": round(v, 4)})
                if v < bester[0]:
                    bester = (v, name)
                print(f"  Validierung {v:.4f} -> {name}{'  (bester)' if bester[1] == name else ''}", flush=True)
                verlauf["bester"], verlauf["letzter"] = bester[1], name
                (basis / "ckpt" / "verlauf.json").write_text(json.dumps(verlauf, indent=1), encoding="utf-8")
                vol.commit()
    verlauf["gpu_min"] = round((time.time() - t0) / 60, 1)
    (basis / "ckpt" / "verlauf.json").write_text(json.dumps(verlauf, indent=1), encoding="utf-8")
    vol.commit()
    return verlauf


# ---------------------------------------------------------------- 6 bewertung
@app.function(image=cb_image, gpu="L4", volumes={"/vol": vol}, timeout=3 * 3600, secrets=GEHEIM)
def bewertung(lauf: str, variante: str, ckpt: str, stimme: str = "grossmutter_a", kapitel: str = "c001") -> dict:
    """stimme: grossmutter_a (fremde Stimme = Adaptionsleistung) | ramona (Trainingsstimme, Gegenprobe).
    Ramona-Referenz: zurueckgehaltene Validierungs-Saetze (nicht trainiert), zusammen ~10 s."""
    import sys
    import numpy as np, torch, torchaudio, librosa
    sys.path.insert(0, "/rl")
    import lora_kern
    from cb_pruefung import Pruefer
    from cb_batch import sprech_norm
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    vol.reload()
    basis = Path(f"/vol/lora/{lauf}")
    aus = basis / "bewertung" / variante
    aus.mkdir(parents=True, exist_ok=True)
    ref_pfad = "/rl/pp_ref.wav"
    if stimme not in ("grossmutter_a", "ramona"):     # weitere Archivstimmen (CK 23.10.: herr_a)
        ref_pfad = f"/rl/stimme_{stimme}.wav"
    if stimme == "ramona":
        import zlib, soundfile as sf
        daten = []
        try:
            zuord = json.loads((basis / "werke.json").read_text(encoding="utf-8"))
        except Exception:
            zuord = {}
        rbasis = basis
        if not any(v.get("sprecher") == SPRECHER for v in zuord.values()) and zuord:
            rbasis = Path(f"/vol/lora/{RAMONA_QUELLE}")       # mix_v2: Ramona nicht im Training -> Referenz aus mix_v1
            zuord = json.loads((rbasis / "werke.json").read_text(encoding="utf-8"))
        for p in sorted((rbasis / "daten").glob("*.pt")):
            if zuord.get(p.stem, {}).get("sprecher", SPRECHER) == SPRECHER:
                daten += torch.load(str(p), weights_only=False)
        val = sorted([r for r in daten if zlib.crc32(r["id"].encode()) % 100 < 3 and 4 <= r["dauer"] <= 9],
                     key=lambda r: -r["dauer"])
        teile, summe = [], 0.0
        for r in val:
            a, sr = sf.read(str(rbasis / "clips" / r["werk"] / f"{r['id']}.flac"), dtype="float32")
            teile += [a, np.zeros(int(0.3 * sr), dtype=np.float32)]
            summe += r["dauer"]
            if summe >= 10:
                break
        ref_pfad = str(basis / "bewertung" / f"_ref_ramona_{variante}.wav")   # nicht im Variantenordner (Prosodie)
        sf.write(ref_pfad, np.concatenate(teile), sr)
    model = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
    if ckpt:
        n = lora_kern.einmischen(model.t3, str(basis / "ckpt" / ckpt))
        print(f"[{variante}] LoRA {ckpt}: {n} Schichten eingemischt", flush=True)
    model.prepare_conditionals(ref_pfad, exaggeration=0.5)
    pr = Pruefer("cuda")
    jobs = [j for j in json.load(open("/rl/pp_jobs.json", encoding="utf-8"))["jobs"] if j["kap"] == kapitel]
    stat = {"variante": variante, "ckpt": ckpt, "stimme": stimme, "saetze": len(jobs), "audio_s": 0.0, "pruefung": {}}
    ves = []
    t0 = time.time()
    for j in jobs:
        torch.manual_seed(1234)
        w = model.generate(sprech_norm(j["text"]), language_id="de", exaggeration=0.5, cfg_weight=0.5)
        w = w.float().cpu().reshape(1, -1).clamp(-1, 1)
        erg = pr.pruefe(j["text"], w, model.sr)
        g = erg["grund"] or "ok"
        stat["pruefung"][g] = stat["pruefung"].get(g, 0) + 1
        stat["audio_s"] += w.shape[-1] / model.sr
        torchaudio.save(str(aus / f"{j['id']}.wav"), w, model.sr, encoding="PCM_S", bits_per_sample=16)
        ves.append(librosa.resample(w.numpy()[0], orig_sr=model.sr, target_sr=16000))
    emb = torch.from_numpy(np.asarray(model.ve.embeds_from_wavs(ves, sample_rate=16000))).float()
    ref16 = librosa.load(ref_pfad, sr=16000)[0]
    ref = torch.from_numpy(np.asarray(model.ve.embeds_from_wavs([ref16], sample_rate=16000))).float()[0]
    cos = torch.nn.functional.cosine_similarity
    stat["ve_aehnlich_referenz"] = round(float(cos(emb, ref[None]).mean()), 4)
    zp = basis / "ckpt" / "ramona_ve_zentrum.pt"
    if zp.exists():
        stat["ve_aehnlich_ramona"] = round(float(cos(emb, torch.load(str(zp))[None].float()).mean()), 4)
    stat["ve_aehnlich_sprecher"] = {p.stem.split("_")[-1]: round(float(cos(emb, torch.load(str(p))[None].float()).mean()), 4)
                                    for p in (basis / "ckpt").glob("ve_zentrum_*.pt")}
    stat["audio_s"] = round(stat["audio_s"], 1)
    stat["gpu_min"] = round((time.time() - t0) / 60, 1)
    (aus / "_stat.json").write_text(json.dumps(stat, indent=1), encoding="utf-8")
    vol.commit()
    return stat


# ---------------------------------------------------------------- Steuerung (lokal)
def _mix_werke(plan: str):
    """Mischlauf: je Sprecher deutsche Solo-Werke, kleinste zuerst, bis das Stundenbudget erreicht ist.
    Rueckgabe wie _werke + Sprecher-Zuordnung {aid: {sprecher, name, titel, h}}."""
    sp = {str(x["reader_id"]): x for x in json.loads((LESER / "daten" / "speakers.json").read_text(encoding="utf-8"))}
    de = lambda r: sorted([w for w in r["works"] if w.get("lang", "German") == "German"], key=lambda w: w["secs"])
    eintraege = [e.split(":") for e in plan.split(",") if e.strip()]
    julia_h = sum(w["secs"] for w in de(sp["5424"])) / 3600
    out, zuord = [], {}
    for sid, budget in eintraege:
        r = sp[sid.strip()]
        b = None if budget == "alle" else (julia_h if budget == "julia" else float(budget))
        summe = 0.0
        for w in de(r):
            if b is not None and summe >= b:
                break
            aid = w["archive"].rstrip("/").split("/")[-1]
            out.append((aid, w["title"], w["secs"], w.get("librivox", "")))
            zuord[aid] = {"sprecher": sid.strip(), "name": r["name"], "titel": w["title"], "h": round(w["secs"] / 3600, 2)}
            summe += w["secs"] / 3600
    return out, zuord


def _werke(auswahl: str):
    sp = json.loads((LESER / "daten" / "speakers.json").read_text(encoding="utf-8"))
    r = next(x for x in sp if str(x["reader_id"]) == SPRECHER)
    werke = r["works"]
    if auswahl.strip().lower() != "alle":
        teile = [t.strip().lower() for t in auswahl.split(",") if t.strip()]
        werke = [w for w in werke if any(t in w["title"].lower() for t in teile)]
    out = []
    for w in werke:
        aid = w["archive"].rstrip("/").split("/")[-1]
        out.append((aid, w["title"], w["secs"], w.get("librivox", "")))
    return out


def _ausklang(ordner):
    """Median der Stille am Satzende (s, Rahmen < -40 dB) und Anzahl Saetze mit < 50 ms (abgeschnitten)."""
    import wave, numpy as np
    werte = []
    for f in sorted(os.listdir(ordner)):
        if not f.endswith(".wav"):
            continue
        with wave.open(os.path.join(ordner, f)) as w:
            sr = w.getframerate()
            a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        n = int(sr * 0.02)
        r = np.sqrt((a[: len(a) // n * n].reshape(-1, n) ** 2).mean(1)) + 1e-9
        laut = np.nonzero(20 * np.log10(r) >= -40)[0]
        werte.append((len(r) - 1 - laut[-1]) * 0.02 if len(laut) else 0.0)
    return (round(float(np.median(werte)), 2), int(sum(v < 0.05 for v in werte))) if werte else (None, 0)


def _ls(pfad):
    try:
        return [Path(e.path).name for e in vol.listdir(pfad)]
    except Exception:
        return []


def _lesen(pfad):
    return b"".join(vol.read_file(pfad))


@app.local_entrypoint()
def main(schritt: str = "alle", lauf: str = "ramona_test", werke: str = TEST_WERKE, epochen: int = 3,
         lr: float = 2e-4, rang: int = 32, bs: int = 16, neu: bool = False, mix: str = "", vergleich: str = "", stimmen: str = ""):
    lokal = HIER / lauf
    lokal.mkdir(parents=True, exist_ok=True)
    if mix:                                  # Mischlauf (CK 18.10.): --mix plan, z. B. MIX_PLAN
        liste, zuord = _mix_werke(MIX_PLAENE.get(mix, mix))
        with vol.batch_upload(force=True) as up:
            import io
            up.put_file(io.BytesIO(json.dumps(zuord, ensure_ascii=False, indent=1).encode("utf-8")), f"/lora/{lauf}/werke.json")
        (lokal / "werke.json").write_text(json.dumps(zuord, ensure_ascii=False, indent=1), encoding="utf-8")
        je = {}
        for z in zuord.values():
            je[z["name"]] = je.get(z["name"], 0) + z["h"]
        print("Sprecher-Rohstunden: " + ", ".join(f"{k} {v:.1f} h" for k, v in je.items()), flush=True)
    else:
        liste = _werke(werke)
    voll_liste = liste
    if mix and lauf != UEBERNAHME_QUELLE:   # fertige Werke aus frueherem Mischlauf kopieren statt neu verarbeiten
        uebernommen = set(uebernehmen.remote(UEBERNAHME_QUELLE, lauf, [w[0] for w in liste]))
        if uebernommen:
            print(f"[uebernahme] {len(uebernommen)} Werke aus {UEBERNAHME_QUELLE} kopiert", flush=True)
            liste = [w for w in liste if w[0] not in uebernommen]
    alle = schritt == "alle"
    if schritt == "ab_schnitt":            # Schnitt, Training, Bewertung neu; MP3, Referenz, Abschrift bleiben
        neu = True
    print(f"Lauf {lauf}: {len(liste)} Werke, {sum(w[2] for w in liste) / 3600:.1f} h Rohaudio", flush=True)
    for aid, titel, secs, _ in liste:
        print(f"  {titel} ({secs / 3600:.2f} h) -> {aid}", flush=True)

    if alle or schritt == "holen":
        print("[holen] pruefe Volume ...", flush=True)
        offen = [aid for aid, _, _, _ in liste if "_fertig.json" not in _ls(f"/lora/{lauf}/mp3/{aid}")]
        for e in (holen.starmap([(lauf, a) for a in offen]) if offen else []):   # leere starmap haengt (17.10.)
            print(f"[holen] {e}", flush=True)
        da = set(_ls(f"/lora/{lauf}/text"))
        offen = [(lauf, aid, lv) for aid, _, _, lv in liste if lv and (neu or f"{aid}.json" not in da)]
        print(f"[referenz] {len(offen)} Werke ohne Buchtext -> laden", flush=True)
        for e in (referenz.starmap(offen, return_exceptions=True) if offen else []):
            print(f"[referenz] {e}", flush=True)

    if alle or schritt == "abschrift":
        auftraege = []
        for aid, _, _, _ in liste:
            mp3 = sorted(n for n in _ls(f"/lora/{lauf}/mp3/{aid}") if n.lower().endswith(".mp3"))
            da = set(_ls(f"/lora/{lauf}/abschrift/{aid}"))
            offen = [n for n in mp3 if neu or Path(n).stem + ".json" not in da]
            auftraege += [(lauf, aid, offen[i:i + 3]) for i in range(0, len(offen), 3)]
        print(f"[abschrift] {len(auftraege)} Pakete", flush=True)
        for w in range(0, len(auftraege), MAX_GPU):
            for zeilen in (abschrift.starmap(auftraege[w:w + MAX_GPU]) if auftraege[w:w + MAX_GPU] else []):
                for z in zeilen:
                    print(f"[abschrift] {z}", flush=True)

    if alle or schritt in ("schnitt", "ab_schnitt"):
        da = set(_ls(f"/lora/{lauf}/daten"))
        offen = [aid for aid, _, _, _ in liste if neu or f"{aid}.pt" not in da]
        for b in (schnitt.starmap([(lauf, a) for a in offen]) if offen else []):
            print(f"[schnitt] {b['werk']}: {b['behalten']}/{b['kandidaten']} Saetze, {b['stunden']} h; "
                  f"verworfen {b['verworfen']}", flush=True)
        berichte = []
        for aid, _, _, _ in voll_liste:
            try:
                berichte.append(json.loads(_lesen(f"/lora/{lauf}/bericht/{aid}.json")))
            except Exception:
                pass
        (lokal / "bericht_daten.json").write_text(json.dumps(berichte, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[schnitt] gesamt {sum(b['stunden'] for b in berichte):.1f} h Schnipsel", flush=True)

    if alle or schritt in ("training", "ab_schnitt"):
        v = training.remote(lauf, epochen, lr, rang, bs)
        (lokal / "training.json").write_text(json.dumps(v, indent=1), encoding="utf-8")
        print(f"[training] Validierung {v['val'][0][1]} -> bester {v['bester']}, {v['gpu_min']} min", flush=True)

    if alle or schritt in ("bewertung", "ab_schnitt"):
        v = json.loads(_lesen(f"/lora/{lauf}/ckpt/verlauf.json"))
        varianten = [("basis", "", "grossmutter_a"), ("lora_bester", v["bester"] or "", "grossmutter_a")]
        if vergleich:                       # z. B. mix_v1:step_01000.safetensors -> Adapter eines anderen Laufs zum Vergleich
            vl, vc = vergleich.split(":")
            varianten.append((vl, f"../../{vl}/ckpt/{vc}", "grossmutter_a"))
        if v.get("letzter") and v["letzter"] != v["bester"]:
            varianten.append(("lora_letzter", v["letzter"], "grossmutter_a"))
        # Gegenprobe (CK 17.10.): Trainingsstimme Ramona -> wirkt der Adapter nur auf ihr oder auch auf fremden Stimmen?
        varianten += [("ramona_basis", "", "ramona"), ("ramona_lora", v["bester"] or "", "ramona")]
        if vergleich:
            varianten.append((f"ramona_{vl}", f"../../{vl}/ckpt/{vc}", "ramona"))
        for st in [x for x in stimmen.split(",") if x.strip()]:   # weitere Testsstimmen (CK 23.10.)
            varianten += [(f"{st}_basis", "", st), (f"{st}_lora", v["bester"] or "", st)]
            if vergleich:
                varianten.append((f"{st}_{vl}", f"../../{vl}/ckpt/{vc}", st))
        stats, offen = [], []
        for n, c, st in varianten:
            try:
                alt = json.loads(_lesen(f"/lora/{lauf}/bewertung/{n}/_stat.json"))
            except Exception:
                alt = None
            if alt and alt.get("ckpt") == c and not neu:
                stats.append(alt)
            else:
                offen.append((lauf, n, c, st))
        stats += list(bewertung.starmap(offen)) if offen else []
        stats.sort(key=lambda x: [v[0] for v in varianten].index(x["variante"]))
        sys_pfad = str(LESER / "tools")
        import sys
        sys.path.insert(0, sys_pfad)
        from prosodie_messen import ordner as prosodie
        zeilen = ["| Variante | Stimme | Checkpoint | Pruefung ok | Auffaellig | Aehnlich Referenz | Aehnlich Ramona | "
                  "Streuung HT | Spanne HT | s/Satz | Ausklang s | abgeschnitten |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for s in stats:
            ziel = lokal / "bewertung" / s["variante"]
            ziel.mkdir(parents=True, exist_ok=True)
            for n in _ls(f"/lora/{lauf}/bewertung/{s['variante']}"):
                (ziel / n).write_bytes(_lesen(f"/lora/{lauf}/bewertung/{s['variante']}/{n}"))
            p = prosodie(str(ziel))
            s["prosodie"] = p
            s["ausklang_s"], s["abgeschnitten"] = _ausklang(str(ziel))
            ok = s["pruefung"].get("ok", 0)
            auff = ", ".join(f"{k} {n}" for k, n in s["pruefung"].items() if k != "ok") or "-"
            zeilen.append(f"| {s['variante']} | {s.get('stimme', 'grossmutter_a')} | {s['ckpt'] or '-'} | {ok}/{s['saetze']} | {auff} | "
                          f"{s['ve_aehnlich_referenz']} | {s.get('ve_aehnlich_ramona', '-')} | {p['streuung_ht']} | "
                          f"{p['spanne_ht']} | {p['dauer_s_mittel']} | {s['ausklang_s']} | {s['abgeschnitten']}/{s['saetze']} |")
        (lokal / "bewertung.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")
        try:
            berichte = json.loads((lokal / "bericht_daten.json").read_text(encoding="utf-8"))
        except Exception:
            berichte = []
        md = [f"# LoRA-Testlauf {lauf} ({time.strftime('%d.%m.%Y %H:%M')})", "",
              "## Daten", ""] + [f"- {b['werk']}: {b['behalten']}/{b['kandidaten']} Saetze, {b['stunden']} h; "
                                 f"verworfen {b['verworfen']}" for b in berichte] + [
              "", "## Training", "",
              f"- {v['train_saetze']} Saetze Training / {v['val_saetze']} Validierung, Rang {v['rang']}, lr {v['lr']}, "
              f"{v['epochen']} Epochen, {v['schritte_gesamt']} Schritte, {v.get('gpu_min', '?')} GPU-min (A100)",
              f"- Validierung (Sprachtoken-Verlust): {' -> '.join(f'{s}: {x}' for s, x in v['val'])}",
              f"- bester Checkpoint: {v['bester']}",
              f"- Sprecher-Stunden (nivelliert): {v.get('sprecher_stunden', '-')}",
              "- Aehnlichkeit je Sprecher-Zentrum: " + "; ".join(f"{s['variante']} {s.get('ve_aehnlich_sprecher', {})}" for s in stats), "",
              "## Bewertung Peter Pan Kap. 1 DE (grossmutter_a = fremde Stimme, ramona = Trainingsstimme)", ""] + zeilen + [
              "", "Hoeren: gpu_lora/" + lauf + "/bewertung/<variante>/ (gleiche Saetze, gleicher Zufallsstartwert).",
              "Aehnlich Referenz soll gleich bleiben (Klangfarbe grossmutter_a); steigt 'Aehnlich Ramona' deutlich, "
              "faerbt der Adapter die Stimme."]
        (lokal / "BERICHT.md").write_text("\n".join(md), encoding="utf-8")
        ids = sorted(n for n in os.listdir(lokal / "bewertung" / "basis") if n.endswith(".wav"))
        (lokal / "hoerliste.txt").write_text("\n".join(
            f"{i}: " + " | ".join(f"bewertung/{s['variante']}/{i}" for s in stats) for i in ids), encoding="utf-8")
        print("\n".join(zeilen), flush=True)
        print(f"Bericht: gpu_lora/{lauf}/BERICHT.md", flush=True)
