"""AP 54a - Vergleichslauf lokaler Wort-Aligner (SimAlign, awesome-align) gegen Stage 340 (DeepSeek).
Aufruf:  py -3.11 -m modal run gpu_align/align_vergleich_modal.py --werk call-of-the-wild
Ablauf:  EN/DE-Saetze aus work/340_wortalignment.json -> je Aligner ein T4-Container (ganzes Werk)
         + je Aligner ein CPU-Container (100 Saetze, Hochrechnung fuer NUC/CPU)
         -> work/_aligner_vergleich/<variante>_<geraet>.json
Tokenisierung: EN-Wortindex i = s340.tokenize_en (\\S+), damit Ergebnis direkt neben 54a liegt.
Modelltoken: Woerter ohne angehaengte Satzzeichen; Rueckabbildung ueber Zeichen-Spans.
Ausgabe je Satz: {"id", "w": [[i, [[de_start,de_end],...]], ...]}  (nur EN-Woerter mit Anker)
"""
import json, os, re, time
from pathlib import Path
import modal

app = modal.App("readlayer-aligner-vergleich")
image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("git")
    .pip_install("torch==2.3.1", "transformers==4.40.2", "huggingface_hub==0.23.4",
                 "simalign==0.4", "networkx", "scipy", "scikit-learn", "regex", "numpy<2")
    .pip_install("git+https://github.com/neulab/awesome-align.git")
)

# Modal-Preise (Stand Liste 2026, vor Abrechnung pruefen): T4 je s, CPU je Kern-s, RAM je GiB-s
PREIS_T4_S = 0.000164
PREIS_CPU_KERN_S = 0.0000131
PREIS_RAM_GIB_S = 0.00000222

WORT = re.compile(r"\w+(?:[’'\-]\w+)*|[^\w\s]")

VARIANTEN = {
    "simalign_mbert": ("simalign", "bert-base-multilingual-cased"),
    "awesome_mbert": ("awesome", "bert-base-multilingual-cased"),
    "awesome_co": ("awesome", "aneuraz/awesome-align-with-co"),
}


def _tok(text):
    return [(m.group(), m.start(), m.end()) for m in WORT.finditer(text)]


def _en_index(text):
    return [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]


def _ist_satzzeichen(t):
    return not any(ch.isalnum() for ch in t)


def _abbilden(paar, links):
    """links: [(src_tok, tgt_tok)] -> {en_i: [de_span,...]} ohne Satzzeichen-Links."""
    en_t, de_t, en_w = paar["_en_t"], paar["_de_t"], paar["_en_w"]
    out = {}
    for s, t in links:
        if s >= len(en_t) or t >= len(de_t):
            continue
        if _ist_satzzeichen(en_t[s][0]) or _ist_satzzeichen(de_t[t][0]):
            continue
        st = en_t[s][1]
        i = next((k for k, (a, b) in enumerate(en_w) if a <= st < b), None)
        if i is None:
            continue
        span = [de_t[t][1], de_t[t][2]]
        out.setdefault(i, [])
        if span not in out[i]:
            out[i].append(span)
    return [[i, sorted(v)] for i, v in sorted(out.items())]


@app.function(image=image, gpu="T4", timeout=3600)
def lauf_gpu(variante, paare):
    return _lauf(variante, paare, "cuda")


@app.function(image=image, cpu=4.0, memory=8192, timeout=3600)
def lauf_cpu(variante, paare):
    return _lauf(variante, paare, "cpu")


def _modell_holen(name):
    from huggingface_hub import snapshot_download
    return snapshot_download(name, allow_patterns=["config.json", "pytorch_model.bin", "vocab.txt",
                                                   "tokenizer_config.json", "special_tokens_map.json"])


def _lauf(variante, paare, device):
    import subprocess, tempfile
    import torch
    t0 = time.time()
    art, modell = VARIANTEN[variante]
    for p in paare:
        p["_en_t"], p["_de_t"], p["_en_w"] = _tok(p["en"]), _tok(p["de"]), _en_index(p["en"])
    ergebnis = {}
    if art == "simalign":
        from simalign import SentenceAligner
        al = SentenceAligner(model="bert", token_type="bpe", matching_methods="mai", device=device)
        t1 = time.time()
        for p in paare:
            src = [t[0] for t in p["_en_t"]]
            tgt = [t[0] for t in p["_de_t"]]
            if not src or not tgt:
                continue
            res = al.get_word_aligns(src, tgt)
            for meth, key in (("mwmf", "m"), ("inter", "a"), ("itermax", "i")):
                ergebnis.setdefault(f"{variante}_{key}", []).append(
                    {"id": p["id"], "w": _abbilden(p, res.get(meth, []))})
    else:
        pfad = _modell_holen(modell)
        t1 = time.time()
        with tempfile.TemporaryDirectory() as d:
            ein, aus = Path(d) / "ein.txt", Path(d) / "aus.txt"
            gueltig = [p for p in paare if p["_en_t"] and p["_de_t"]]
            ein.write_text("\n".join(" ".join(t[0] for t in p["_en_t"]) + " ||| " +
                                     " ".join(t[0] for t in p["_de_t"]) for p in gueltig), encoding="utf-8")
            env = dict(os.environ, CUDA_VISIBLE_DEVICES="0" if device == "cuda" else "")
            subprocess.run(["awesome-align", "--output_file", str(aus), "--model_name_or_path", pfad,
                            "--data_file", str(ein), "--extraction", "softmax", "--batch_size", "32"],
                           check=True, env=env)
            zeilen = aus.read_text(encoding="utf-8").splitlines()
        for p, z in zip(gueltig, zeilen):
            links = [tuple(int(x) for x in l.split("-")) for l in z.split()]
            ergebnis.setdefault(variante, []).append({"id": p["id"], "w": _abbilden(p, links)})
    t2 = time.time()
    return {"variante": variante, "geraet": device, "saetze": len(paare),
            "gpu": torch.cuda.get_device_name(0) if device == "cuda" and torch.cuda.is_available() else "",
            "laden_s": round(t1 - t0, 1), "ausrichten_s": round(t2 - t1, 1), "gesamt_s": round(t2 - t0, 1),
            "ergebnis": ergebnis}


@app.local_entrypoint()
def main(werk: str = "call-of-the-wild", cpu_saetze: int = 100):
    basis = next(Path("authors").glob(f"*/books/{werk}"))
    d = json.loads((basis / "work" / "340_wortalignment.json").read_text(encoding="utf-8"))
    paare = [{"id": k, "en": v["en"], "de": v["de"]} for k, v in d["content"].items()
             if v.get("align") and v.get("en") and v.get("de")]
    ziel = basis / "work" / "_aligner_vergleich"
    ziel.mkdir(exist_ok=True)
    print(f"{werk}: {len(paare)} Saetze")
    auftraege = [lauf_gpu.spawn(v, paare) for v in VARIANTEN]
    auftraege += [lauf_cpu.spawn(v, paare[:cpu_saetze]) for v in VARIANTEN]
    laufzeit = []
    for a in auftraege:
        try:
            r = a.get()
        except Exception as e:
            print("FEHLER:", e)
            laufzeit.append({"fehler": str(e)[:500]})
            continue
        for name, liste in r.pop("ergebnis").items():
            (ziel / f"{name}_{r['geraet']}.json").write_text(json.dumps(liste, ensure_ascii=False), encoding="utf-8")
        if r["geraet"] == "cuda":
            r["kosten_usd"] = round(r["gesamt_s"] * PREIS_T4_S, 4)
        else:
            r["kosten_usd"] = round(r["gesamt_s"] * (4 * PREIS_CPU_KERN_S + 8 * PREIS_RAM_GIB_S), 4)
        laufzeit.append(r)
        print(r)
    (ziel / "laufzeit.json").write_text(json.dumps(laufzeit, ensure_ascii=False, indent=1), encoding="utf-8")
    print("FERTIG ->", ziel)
