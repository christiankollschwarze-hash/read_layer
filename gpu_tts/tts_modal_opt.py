"""READ LAYER — Single-Speaker-Vertonung, Chatterbox MULTILINGUAL auf Modal (L4), OPTIMIERT (17.10.2026).
Fuer private Uploads (TAELLA) und Kostenmessung je 50.000 Zeichen.

Optimierungen gegenueber tts_modal.py (alle per Schalter, fuer A/B-Messung):
  --parallel N   N Modell-Instanzen je GPU, die Saetze gleichzeitig rechnen (L4 sonst kaum ausgelastet)
  --fp16         Rechnen in halber Genauigkeit (torch.autocast); Satz faellt bei Fehler auf fp32 zurueck
  Modellgewichte liegen im Modal-Volume (kein Download je Lauf).

Aufruf:
  py -3.11 -m modal run gpu_tts/tts_modal_opt.py --paket <werk>_<lg> [--kapitel c001] [--parallel 3] [--fp16]
Messung: gpu_tts/<paket>/messung_<variante>.json  (GPU-Sekunden, Audio-Sekunden, Zeichen, RTF)
Ergebnis: WAVs -> <werk>/fassungen/<lg>/audio/<tag>.wav
"""
import json, os, sys
from pathlib import Path
import modal

HIER = Path(__file__).resolve().parent
LESER = HIER.parent
L4_USD_H = 0.80          # Modal L4 inkl. CPU/RAM-Anteil ~0.80-0.90 $/h (Messung 16.10.)


def _hf_token():
    tok = os.environ.get("HF_TOKEN", "")
    env = LESER / ".env"
    if not tok and env.exists():
        for z in env.read_text(encoding="utf-8").splitlines():
            if z.strip().startswith("HF_TOKEN="):
                tok = z.split("=", 1)[1].strip().strip('"')
    return tok


app = modal.App("readlayer-chatterbox-opt")
vol = modal.Volume.from_name("readlayer-tts", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libsndfile1")
    .pip_install("chatterbox-tts", "huggingface_hub", "safetensors")
    .env({"HF_HOME": "/vol/hf", "TORCH_HOME": "/vol/torch"})
    .add_local_dir(str(HIER), remote_path="/pakete", ignore=lambda p: p.suffix in (".zip", ".tmp") or (p.suffix == ".wav" and not p.name.startswith("ref")))
    # 17.10.: ref.wav MUSS mit hoch (vorher "**/*.wav" ignoriert -> Werkstimme fehlte, Standardstimme lief)
    .add_local_file(str(LESER / "gpu_lora" / "lora_kern.py"), remote_path="/lora_kern/lora_kern.py")
)
# LoRA-Adapter (18.10.2026, AP claude/AP_lora_librivox.md): Name -> Quelle im Volume (wird einmalig nach
# /vol/lora/adapter/<name>.safetensors kopiert). jobs.json "lora" schaltet ihn ein (tools/tts_paket.py, book.json tts_lora).
ADAPTER = {"ramona_v1": "lora/ramona_test/ckpt/step_00250.safetensors",
           "mix_v1": "lora/mix_v1/ckpt/step_01000.safetensors"}     # 18.10.: Standard DE
GEHEIM = [modal.Secret.from_dict({"HF_TOKEN": _hf_token()})]


@app.function(image=image, volumes={"/vol": vol}, timeout=1800, secrets=GEHEIM)
def vorladen(lora: str = ""):
    import shutil
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    ChatterboxMultilingualTTS.from_pretrained(device="cpu")
    info = "Multilingual-Modell im Volume"
    if lora:
        ziel = f"/vol/lora/adapter/{lora}.safetensors"
        if not os.path.exists(ziel):
            if lora not in ADAPTER or not os.path.exists(f"/vol/{ADAPTER[lora]}"):
                raise RuntimeError(f"LoRA-Adapter {lora} unbekannt bzw. Quelle fehlt im Volume")
            os.makedirs(os.path.dirname(ziel), exist_ok=True)
            shutil.copy(f"/vol/{ADAPTER[lora]}", ziel)
        info += f" | LoRA {lora}: {os.path.getsize(ziel) / 1e6:.1f} MB"
    vol.commit()
    return info


@app.function(image=image, gpu="L4", volumes={"/vol": vol}, timeout=4 * 3600, secrets=GEHEIM)
def kapitel(paket: str, kap: str, parallel: int = 1, fp16: bool = False, variante: str = "", batch: int = 0,
            s3batch: bool = False) -> dict:
    import time, threading, queue
    import torch, torchaudio
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    t_start = time.time()
    daten = json.load(open(f"/pakete/{paket}/jobs.json", encoding="utf-8"))
    lang = daten["lang"]
    jobs = [j for j in daten["jobs"] if j["kap"] == kap]
    ref = f"/pakete/{paket}/ref.wav" if os.path.exists(f"/pakete/{paket}/ref.wav") else None
    if daten.get("ref") not in (None, "", "chatterbox-standard") and not ref:
        raise RuntimeError(f"Werkstimme {daten.get('ref')} angefordert, aber ref.wav fehlt im Container")
    aus = f"/vol/out/{paket}{('_' + variante) if variante else ''}"
    os.makedirs(aus, exist_ok=True)

    modelle = [ChatterboxMultilingualTTS.from_pretrained(device="cuda") for _ in range(max(1, parallel))]
    if daten.get("lora"):                     # 18.10.2026: eigenes Modellgewicht (LoRA) ins T3 einmischen
        sys.path.insert(0, "/lora_kern")
        import lora_kern
        pfad = f"/vol/lora/adapter/{daten['lora']}.safetensors"
        if not os.path.exists(pfad):
            raise RuntimeError(f"LoRA {daten['lora']} fehlt im Volume ({pfad})")
        for m in modelle:
            n = lora_kern.einmischen(m.t3, pfad, float(daten.get("lora_staerke", 1.0)))
        print(f"[{kap}] LoRA {daten['lora']}: {n} Schichten eingemischt", flush=True)
    t_geladen = time.time()
    sr = modelle[0].sr
    stille = torch.zeros(1, int(sr * 0.12))

    def teile(t, maxlen=280):
        if len(t) <= maxlen:
            return [t]
        mitte = len(t) // 2
        for zeichen in ("; ", ": ", ", ", " — ", " "):
            kand = [i for i in range(len(t)) if t.startswith(zeichen, i)]
            if kand:
                i = min(kand, key=lambda x: abs(x - mitte)) + len(zeichen.rstrip())
                return teile(t[:i].strip(), maxlen) + teile(t[i:].strip(), maxlen)
        return [t]

    q = queue.Queue()
    for j in jobs:
        q.put(j)
    sperre = threading.Lock()
    stat = {"audio_s": 0.0, "neu": 0, "fehler": [], "fp16_fallback": 0, "zeichen": 0}

    def gen(m, s):
        kw = {"language_id": lang}
        if ref:
            kw["audio_prompt_path"] = ref
        if fp16:
            try:
                with torch.autocast("cuda", dtype=torch.float16):
                    return m.generate(s, **kw)
            except Exception:
                with sperre:
                    stat["fp16_fallback"] += 1
        return m.generate(s, **kw)

    def arbeiter(m):
        while True:
            try:
                j = q.get_nowait()
            except queue.Empty:
                return
            ziel = f"{aus}/{j['id']}.wav"
            if os.path.exists(ziel):
                continue
            try:
                stuecke = []
                for s in teile(j["text"]):
                    w = gen(m, s)
                    stuecke += [w.float().cpu().reshape(1, -1), stille]
                w = torch.cat(stuecke[:-1], dim=1).clamp(-1, 1)
                torchaudio.save(ziel, w, sr, encoding="PCM_S", bits_per_sample=16)
                with sperre:
                    stat["audio_s"] += w.shape[-1] / sr
                    stat["neu"] += 1
                    stat["zeichen"] += len(j["text"])
            except Exception as ex:
                with sperre:
                    stat["fehler"].append(f"{j['id']}: {str(ex)[:100]}")

    if batch > 0:
        # Echtes Batching (cb_batch.py): B Satzstuecke je Transformer-Durchgang
        sys.path.insert(0, "/pakete")
        from cb_batch import BatchTTS
        if ref:
            modelle[0].prepare_conditionals(ref, exaggeration=0.5)   # Werkstimme aus dem Stimmen-Archiv
        # Stimmungs-Referenzen (17.10.2026): je Stil eigene Referenz derselben Stimme (tts_paket.py --stil-refs)
        stil_refs = {}
        for stil, datei in (daten.get("refs") or {}).items():
            pfad = f"/pakete/{paket}/{datei}"
            if os.path.exists(pfad):
                modelle[0].prepare_conditionals(pfad, exaggeration=0.5)
                stil_refs[stil] = modelle[0].conds
        if stil_refs:
            if ref:
                modelle[0].prepare_conditionals(ref, exaggeration=0.5)   # Standard wieder herstellen
            print(f"[{kap}] Stimmungs-Referenzen: {sorted(stil_refs)}", flush=True)
        ref_je = {j["id"]: stil_refs.get(j.get("stil")) for j in jobs}
        bt = BatchTTS(modelle[0])
        bt.zeichen_erhalten = daten.get("zeichen") != "punc_norm"  # STANDARD seit 17.10.2026 (CK): Satzzeichen erhalten (cb_batch.sprech_norm)
        offen = [j for j in jobs if not os.path.exists(f"{aus}/{j['id']}.wav")]
        regler = {j["id"]: (float(j.get("ex", 0.5)), float(j.get("cfg", 0.5))) for j in jobs}   # Prosodie je Satz
        stuecke = [(j["id"], n, s) for j in offen for n, s in enumerate(teile(j["text"]))]
        stuecke.sort(key=lambda x: len(x[2]))          # aehnliche Laengen zusammen -> wenig Leerlauf
        audio = {}

        def rechne(liste):
            for a in range(0, len(liste), batch):
                yield a, liste[a:a + batch]

        for a, gruppe in rechne(stuecke):
            try:
                wavs = bt.generate([g[2] for g in gruppe], language_id=lang, s3batch=s3batch,
                                   ex=[regler[g[0]][0] for g in gruppe], cfg=[regler[g[0]][1] for g in gruppe],
                                   refs=[ref_je.get(g[0]) for g in gruppe])
            except Exception as ex:
                stat["fehler"].append(f"batch {a}: {str(ex)[:160]}")
                wavs = []
                for g in gruppe:                        # Rueckfall: einzeln wie Original
                    try:
                        wavs.append(gen(modelle[0], g[2]))
                    except Exception as ex2:
                        wavs.append(None)
                        stat["fehler"].append(f"{g[0]}: {str(ex2)[:100]}")
            for g, w in zip(gruppe, wavs):
                if w is not None:
                    audio.setdefault(g[0], {})[g[1]] = w.float().cpu().reshape(1, -1)
            print(f"[{kap}] {min(a + batch, len(stuecke))}/{len(stuecke)} Stuecke", flush=True)

        # PRUEFUNG IM LAUF (17.10.2026, CK: Pruefungen gehoeren in den Standardprozess; cb_pruefung.py):
        # Forced Alignment je Stueck -> Nachklang/Wortfetzen, Vorlauf, verschmiert, zu kurz/lang.
        # Auffaellige Stuecke bis zu 2x neu; das beste bleibt. Bleibt nur Nachklang -> hinter letztem Wort kappen.
        import cb_pruefung
        from cb_pruefung import Pruefer, kappen
        if daten.get("ms_je_zeichen"):            # LoRA spricht schneller -> Erwartung anpassen
            cb_pruefung.MS_JE_ZEICHEN = float(daten["ms_je_zeichen"])
        pr = Pruefer("cuda")
        RANG = {None: 0, "nachklang": 1, "vorlauf": 2, "zu_lang": 3, "verschmiert": 3, "nicht_ausrichtbar": 3, "zu_kurz": 4}
        befund = {}
        for g in stuecke:
            if g[0] in audio and g[1] in audio[g[0]]:
                befund[(g[0], g[1])] = pr.pruefe(g[2], audio[g[0]][g[1]], sr)
        stat["pruefung_neu"], stat["pruefung_gekappt"], stat["pruefung_gruende"] = 0, 0, {}
        for b in befund.values():
            if b["grund"]:
                stat["pruefung_gruende"][b["grund"]] = stat["pruefung_gruende"].get(b["grund"], 0) + 1
        for runde in (1, 2):
            schlecht = [g for g in stuecke if (g[0], g[1]) in befund and befund[(g[0], g[1])]["grund"]]
            if not schlecht:
                break
            print(f"[{kap}] Pruefung Runde {runde}: {len(schlecht)} Stuecke neu", flush=True)
            for a, gruppe in rechne(schlecht):
                try:
                    wavs = bt.generate([g[2] for g in gruppe], language_id=lang, s3batch=s3batch,
                                       ex=[regler[g[0]][0] for g in gruppe], cfg=[regler[g[0]][1] for g in gruppe],
                                   refs=[ref_je.get(g[0]) for g in gruppe])
                except Exception as ex:
                    stat["fehler"].append(f"pruefung {a}: {str(ex)[:120]}")
                    continue
                for g, w in zip(gruppe, wavs):
                    w = w.float().cpu().reshape(1, -1)
                    b_neu = pr.pruefe(g[2], w, sr)
                    if RANG[b_neu["grund"]] < RANG[befund[(g[0], g[1])]["grund"]]:
                        audio[g[0]][g[1]], befund[(g[0], g[1])] = w, b_neu
                        stat["pruefung_neu"] += 1
        for (jid, n), b in befund.items():
            if b["grund"] == "nachklang" and b["letzt"]:
                audio[jid][n] = kappen(audio[jid][n], sr, b["letzt"] + 0.12)
                b["grund"] = None
                stat["pruefung_gekappt"] += 1
        stat["pruefung_rest"] = sorted({jid for (jid, n), b in befund.items() if b["grund"]})
        for j in offen:
            teile_j = audio.get(j["id"], {})
            n_soll = len(teile(j["text"]))
            if len(teile_j) != n_soll:
                stat["fehler"].append(f"{j['id']}: {len(teile_j)}/{n_soll} Stuecke")
                continue
            folge = []
            for n in range(n_soll):
                folge += [teile_j[n], stille]
            w = torch.cat(folge[:-1], dim=1).clamp(-1, 1)
            torchaudio.save(f"{aus}/{j['id']}.wav", w, sr, encoding="PCM_S", bits_per_sample=16)
            stat["audio_s"] += w.shape[-1] / sr
            stat["neu"] += 1
            stat["zeichen"] += len(j["text"])
        stat["t3_s"] = round(getattr(bt, "zeit_t3", 0), 1)
        stat["s3gen_s"] = round(getattr(bt, "zeit_s3", 0), 1)
    else:
        th = [threading.Thread(target=arbeiter, args=(m,)) for m in modelle]
        for t in th:
            t.start()
        for t in th:
            t.join()
    vol.commit()
    t_ende = time.time()
    stat.update(kap=kap, saetze=len(jobs), laden_s=round(t_geladen - t_start, 1),
                rechnen_s=round(t_ende - t_geladen, 1), gpu_s=round(t_ende - t_start, 1),
                audio_s=round(stat["audio_s"], 1), parallel=parallel, fp16=fp16, batch=batch)
    stat["rtf"] = round(stat["rechnen_s"] / max(stat["audio_s"], 1), 3)
    return stat


@app.function(image=image, volumes={"/vol": vol}, timeout=600, secrets=GEHEIM)
def zeichen_pruefen(sprache: str = "de") -> str:
    """Kennt der Multilingual-Tokenizer unsere Pausen-/Spannungszeichen? (17.10.2026)"""
    import glob
    from chatterbox.models.tokenizers.tokenizer import MTLTokenizer
    sys.path.insert(0, "/pakete")
    from cb_batch import sprech_norm
    from chatterbox.mtl_tts import punc_norm
    datei = (glob.glob("/vol/hf/**/grapheme_mtl_merged_expanded_v1.json", recursive=True) or [None])[0]
    tok = MTLTokenizer(datei)
    zeilen = [f"Vokabular: {datei}"]
    for z in ["...", "…", "—", "–", "-", ":", ";", "?!", "!!", '"', "„"]:
        ids = tok.encode(f"a{z}b", language_id=sprache)
        zeilen.append(f"  {z!r:6} -> {ids} | {tok.decode(ids)!r}")
    satz = "Dann, ganz langsam... öffnete sich das Fenster — niemand hatte es berührt: Wer war das?!"
    for name, f in (("punc_norm", punc_norm), ("sprech_norm", sprech_norm)):
        t = f(satz)
        zeilen.append(f"{name}: {t!r} -> {tok.decode(tok.encode(t, language_id=sprache))!r}")
    return "\n".join(zeilen)


@app.local_entrypoint()
def zeichen(sprache: str = "de"):
    print(zeichen_pruefen.remote(sprache))


@app.local_entrypoint()
def leeren(paket: str):
    """24.10.2026 (Smoke #12): alle Ausgabeordner out/<paket>_* auf dem Volume loeschen,
    damit 500 wirklich neu vertont (Smoke-Test vor 500)."""
    if not paket.startswith("u-smoketest"):
        raise SystemExit(f"leeren nur fuer Smoke-Pakete (u-smoketest-*), nicht {paket}")
    weg = [e.path for e in vol.listdir("out") if e.path.split("/")[-1].startswith(paket + "_")]
    for p in weg:
        vol.remove_file(p, recursive=True)
    print(f"Volume geleert: {len(weg)} Ordner" + (f" ({', '.join(x.split('/')[-1] for x in weg)})" if weg else ""))


@app.local_entrypoint()
def main(paket: str, kapitel_nur: str = "", parallel: int = 1, fp16: bool = False, herunterladen: bool = True,
         batch: int = 0, zusatz: str = "", s3batch: bool = False):
    import time
    sys.path.insert(0, str(LESER))
    from config import config
    daten = json.load(open(HIER / paket / "jobs.json", encoding="utf-8"))
    kaps = sorted({j["kap"] for j in daten["jobs"]})
    if kapitel_nur:
        kaps = [k for k in kaps if k in kapitel_nur.split(",")]
    variante = (f"b{batch}" if batch else f"p{parallel}") + ("_s3b" if s3batch else "") + ("_fp16" if fp16 else "") \
        + ("_probe" if kapitel_nur else "") + (f"_{daten['lora']}" if daten.get("lora") else "")
    if zusatz:
        variante += f"_{zusatz}"     # eigener Volume-Ordner, z.B. Neuvertonung mit anderer Stimme
    print(vorladen.remote(daten.get("lora", "")))
    print(f"Variante {variante}: {len(kaps)} Kapitel parallel, Sprache {daten['lang']}, Stimme {daten.get('ref')}"
          + (f", LoRA {daten['lora']}" if daten.get("lora") else ""))
    t0 = time.time()
    ergebnisse = []
    for st in kapitel.starmap([(paket, k, parallel, fp16, variante, batch, s3batch) for k in kaps]):
        ergebnisse.append(st)
        print(f"  {st['kap']}: {st['neu']}/{st['saetze']} | Audio {st['audio_s']/60:.1f} min | "
              f"GPU {st['gpu_s']/60:.1f} min (Laden {st['laden_s']:.0f}s) | RTF {st['rtf']}"
              + (f" | FEHLER {len(st['fehler'])}" if st['fehler'] else "")
              + (f" | fp16->fp32 {st['fp16_fallback']}" if st['fp16_fallback'] else "")
              + (f" | T3 {st.get('t3_s')}s S3Gen {st.get('s3gen_s')}s" if st.get('batch') else "")
              + (f" | Pruefung {st.get('pruefung_gruende', {})}: {st.get('pruefung_neu', 0)} neu, "
                 f"{st.get('pruefung_gekappt', 0)} gekappt, Rest {len(st.get('pruefung_rest', []))}" if st.get('batch') else "")
              + (f" | {st['fehler'][:2]}" if st['fehler'] else ""), flush=True)
    gpu_s = sum(e["gpu_s"] for e in ergebnisse)
    audio_s = sum(e["audio_s"] for e in ergebnisse)
    zeichen = sum(e["zeichen"] for e in ergebnisse)
    usd = gpu_s / 3600 * getattr(config, "MODAL_L4_USD_H", L4_USD_H)
    messung = {
        "variante": variante, "paket": paket, "kapitel": len(kaps), "wandzeit_s": round(time.time() - t0),
        "gpu_s": round(gpu_s), "audio_s": round(audio_s), "zeichen": zeichen,
        "gpu_h_je_audio_h": round(gpu_s / max(audio_s, 1), 3),
        "usd_geschaetzt": round(usd, 3),
        "usd_je_50k_zeichen": round(usd / max(zeichen, 1) * 50000, 3),
        "fehler": sum(len(e["fehler"]) for e in ergebnisse),
        "pruefung_neu": sum(e.get("pruefung_neu", 0) for e in ergebnisse),
        "pruefung_rest": [t for e in ergebnisse for t in e.get("pruefung_rest", [])],
        "kapitel_details": ergebnisse,
    }
    json.dump(messung, open(HIER / paket / f"messung_{variante}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"MESSUNG {variante}: GPU {gpu_s/60:.1f} min fuer {audio_s/60:.1f} min Audio "
          f"(x{messung['gpu_h_je_audio_h']}) | ~{usd:.2f} $ | {messung['usd_je_50k_zeichen']:.3f} $ je 50.000 Zeichen")
    if daten.get("werk"):   # 24.10.2026 (Smoke #7): Modal-Kosten ins Werk (kosten.jsonl)
        from pipeline import usage_log
        usage_log.log_gpu(daten["werk"], "500", gpu_s, extra={"paket": paket, "variante": variante,
                                                              "sprache": daten.get("lang")})
    if not herunterladen:
        return
    _holen(paket, variante, kapitel_nur, daten)


def _holen(paket, variante, kapitel_nur, daten):
    sys.path.insert(0, str(LESER))
    from config import config
    werk = Path(config.book_dir(daten["werk"]))
    ziel = (werk / "work" / "_tts_probe" / f"{daten['lang']}_{variante}") if kapitel_nur else (werk / "fassungen" / daten["lang"] / "audio")
    if daten.get("ziel") and not kapitel_nur:
        ziel = werk / daten["ziel"]          # Neuvertonung (tools/cb_neu.py): eigener Ordner, nichts ueberschreiben
    ziel.mkdir(parents=True, exist_ok=True)
    # 17.10.: parallel herunterladen (einzeln ~1 Datei/s -> 3.000 Saetze = 50 min)
    from concurrent.futures import ThreadPoolExecutor
    offen = [e.path for e in vol.listdir(f"out/{paket}_{variante}")
             if e.path.endswith(".wav") and not (ziel / e.path.split("/")[-1]).exists()]

    def eins(pfad):
        name = pfad.split("/")[-1]
        tmp = ziel / (name + ".part")
        with open(tmp, "wb") as f:
            for chunk in vol.read_file(pfad):
                f.write(chunk)
        os.replace(tmp, ziel / name)
        return 1

    n = 0
    with ThreadPoolExecutor(max_workers=16) as pool:
        for k, _ in enumerate(pool.map(eins, offen), 1):
            n += 1
            if k % 250 == 0:
                print(f"  heruntergeladen {k}/{len(offen)}", flush=True)
    print(f"Heruntergeladen: {n} WAVs -> {ziel}")
    # Tempo (0.91) und Randschnitt laufen danach als eigene Schritte (start_epub_fertig.bat)


@app.local_entrypoint()
def adapter_sichern(lora: str = ""):
    """Adapter im Volume anlegen (/lora/adapter/<lora>.safetensors) + lokale Sicherung gpu_lora/adapter/ (18.10.2026).
    py -3.11 -m modal run gpu_tts/tts_modal_opt.py::adapter_sichern --lora ramona_v1"""
    for name in ([lora] if lora else list(ADAPTER)):      # ohne --lora: alle Adapter
        ziel = LESER / "gpu_lora" / "adapter" / f"{name}.safetensors"
        if ziel.exists():
            print(f"Lokal schon vorhanden: {ziel}")
            continue
        print(vorladen.remote(name))
        ziel.parent.mkdir(parents=True, exist_ok=True)
        with open(str(ziel) + ".part", "wb") as f:
            for chunk in vol.read_file(f"lora/adapter/{name}.safetensors"):
                f.write(chunk)
        os.replace(str(ziel) + ".part", ziel)
        print(f"Lokal gesichert: {ziel} ({ziel.stat().st_size / 1e6:.1f} MB)")


@app.local_entrypoint()
def nur_holen(paket: str, variante: str, kapitel_nur: str = "c001"):
    """Nur herunterladen (z.B. Probe DE nachholen): modal run gpu_tts/tts_modal_opt.py::nur_holen --paket .. --variante p1_probe"""
    daten = json.load(open(HIER / paket / "jobs.json", encoding="utf-8"))
    _holen(paket, variante, kapitel_nur, daten)
