"""STAGE 345 Zulieferer — Pruefaligner awesome-align-with-co auf Modal-T4 (Hugging Face nur dort erreichbar).
Aufruf:  py -3.11 -m modal run gpu_align/pruefaligner_modal.py --werk <werk>
Ausgabe: work/345_pruefaligner.json  [{"id","w":[[i,[[a,b],..]],..]}]  (i = s340-Index, Spans im Zielsatz)
Kosten:  ~0,006 $/Buch (Call of the Wild: 39 s T4, AP 54a 26.10.2026). Logik identisch mit align_vergleich_modal.py.
(AP 54b, 26.10.2026)
"""
import json, os, re, time
from pathlib import Path
import modal

app = modal.App("readlayer-pruefaligner")
image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("git")
    .pip_install("torch==2.3.1", "transformers==4.40.2", "huggingface_hub==0.23.4", "regex", "numpy<2")
    .pip_install("git+https://github.com/neulab/awesome-align.git")
)
MODELL = "aneuraz/awesome-align-with-co"
PREIS_T4_S = 0.000164
WORT = re.compile(r"\w+(?:[’'\-]\w+)*|[^\w\s]")


def _tok(t):
    return [(m.group(), m.start(), m.end()) for m in WORT.finditer(t)]


def _satzz(t):
    return not any(c.isalnum() for c in t)


@app.function(image=image, gpu="T4", timeout=3600)
def lauf(paare):
    import subprocess, tempfile
    from huggingface_hub import snapshot_download
    t0 = time.time()
    pfad = snapshot_download(MODELL, allow_patterns=["config.json", "pytorch_model.bin", "vocab.txt",
                                                    "tokenizer_config.json", "special_tokens_map.json"])
    for p in paare:
        p["et"], p["dt"] = _tok(p["q"]), _tok(p["z"])
        p["ew"] = [(m.start(), m.end()) for m in re.finditer(r"\S+", p["q"])]
    ok = [p for p in paare if p["et"] and p["dt"]]
    with tempfile.TemporaryDirectory() as d:
        ein, aus = Path(d) / "ein.txt", Path(d) / "aus.txt"
        ein.write_text("\n".join(" ".join(t[0] for t in p["et"]) + " ||| " + " ".join(t[0] for t in p["dt"])
                                 for p in ok), encoding="utf-8")
        subprocess.run(["awesome-align", "--output_file", str(aus), "--model_name_or_path", pfad,
                        "--data_file", str(ein), "--extraction", "softmax", "--batch_size", "32"],
                       check=True, env=dict(os.environ, CUDA_VISIBLE_DEVICES="0"))
        zeilen = aus.read_text(encoding="utf-8").splitlines()
    out = []
    for p, z in zip(ok, zeilen):
        m = {}
        for l in z.split():
            s, t = (int(x) for x in l.split("-"))
            if s >= len(p["et"]) or t >= len(p["dt"]) or _satzz(p["et"][s][0]) or _satzz(p["dt"][t][0]):
                continue
            i = next((k for k, (a, b) in enumerate(p["ew"]) if a <= p["et"][s][1] < b), None)
            if i is None:
                continue
            sp = [p["dt"][t][1], p["dt"][t][2]]
            if sp not in m.setdefault(i, []):
                m[i].append(sp)
        out.append({"id": p["id"], "w": [[i, sorted(v)] for i, v in sorted(m.items())]})
    return out, round(time.time() - t0, 1)


@app.local_entrypoint()
def main(werk: str):
    import sys
    sys.path.insert(0, ".")
    from config import config
    src, tgt = config.werk_sprachen(werk)[0], config.TARGET_LANGUAGES[0]   # AP 55: Richtung aus book.json
    wp = Path(config.work_path(werk, "340_wortalignment"))
    d = json.loads(wp.read_text(encoding="utf-8"))
    paare = [{"id": k, "q": v[src], "z": v[tgt]} for k, v in d["content"].items()
             if v.get("align") and v.get(src) and v.get(tgt)]
    print(f"{werk}: {len(paare)} Saetze -> Modal T4", flush=True)
    out, sek = lauf.remote(paare)
    ziel = Path(config.work_path(werk, "345_pruefaligner"))
    ziel.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    usd = round(sek * PREIS_T4_S, 4)
    with open(ziel.parent / "kosten.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"zeit": time.strftime("%Y-%m-%dT%H:%M:%S"), "stage": "345_pruefaligner",
                            "modell": "modal-T4 awesome_co", "sekunden": sek, "usd": usd}) + "\n")
    print(f"Geschrieben: {ziel} ({len(out)} Saetze, {sek} s, ~{usd} $)")
