"""Laeuft in Modal (aufgerufen von messung_modal.py).
1) ECAPA-TDNN (speechbrain/spkrec-ecapa-voxceleb): Embedding je Segment -> /out/embeddings.npz
2) pyannote/speaker-diarization-3.1 auf spur_vc / spur_v1 / spur_orig -> /out/diar.json (+ DER gegen spur_ref.json)
3) Zweitmeinung ohne pyannote: ECAPA-Fenster (1,5 s) in den Referenz-Sprechregionen + agglomeratives Clustering
"""
import json, os, sys, traceback
import numpy as np, torch, torchaudio

P = sys.argv[1]
DEV = "cuda" if torch.cuda.is_available() else "cpu"
TOK = os.environ.get("HF_TOKEN") or None
bericht = []
man = json.load(open(os.path.join(P, "manifest.json"), encoding="utf-8"))["segmente"]


def lade16(p):
    w, sr = torchaudio.load(p)
    w = w.mean(0, keepdim=True)
    return torchaudio.functional.resample(w, sr, 16000) if sr != 16000 else w


# 1) ECAPA
from speechbrain.inference.speaker import EncoderClassifier
enc = EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb", savedir="/tmp/ecapa",
                                     run_opts={"device": DEV})
ids, embs = [], []
with torch.no_grad():
    for s in man:
        w = lade16(os.path.join(P, "segmente", s["id"] + ".wav"))
        if w.shape[-1] < 1600:
            continue
        e = enc.encode_batch(w.to(DEV)).squeeze().cpu().numpy()
        ids.append(s["id"]); embs.append(e)
np.savez("/out/embeddings.npz", ids=np.array(ids), emb=np.stack(embs))
bericht.append(f"ECAPA: {len(ids)} Embeddings")

ref = json.load(open(os.path.join(P, "spur_ref.json"), encoding="utf-8"))
diar = {"pyannote": {}, "ecapa_cluster": {}, "der": {}}

# 3) Zweitmeinung: ECAPA-Fenster in Referenz-Sprechregionen (Oracle-VAD), AHC
from scipy.cluster.hierarchy import linkage, fcluster
import glob
VARS = [v for v in sorted(os.path.basename(f)[5:-4] for f in glob.glob(os.path.join(P, "spur_*.wav"))) if v in ref]   # vc, orig, v1, s1/s2, r1..
for var in VARS:
    w = lade16(os.path.join(P, f"spur_{var}.wav"))[0]
    fen = []
    for a, b, lab, tag in ref[var]:
        t = a
        while t < b - 0.3:
            e = min(b, t + 1.5)
            fen.append((t, e)); t += 0.75
    E = []
    with torch.no_grad():
        for a, b in fen:
            x = w[int(a * 16000):int(b * 16000)].unsqueeze(0).to(DEV)
            E.append(enc.encode_batch(x).squeeze().cpu().numpy())
    E = np.stack(E); E /= np.linalg.norm(E, axis=1, keepdims=True)
    np.save(f"/out/fenster_{var}.npy", E)
    diar["ecapa_cluster"][var] = {"fenster": fen}

# 2) pyannote
try:
    from pyannote.audio import Pipeline
    from pyannote.core import Annotation, Segment
    from pyannote.metrics.diarization import DiarizationErrorRate
    pipe = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=TOK)
    pipe.to(torch.device(DEV))
    for var in VARS:
        w = lade16(os.path.join(P, f"spur_{var}.wav"))
        hyp = pipe({"waveform": w, "sample_rate": 16000})
        diar["pyannote"][var] = [[round(s.start, 3), round(s.end, 3), l] for s, _, l in hyp.itertracks(yield_label=True)]
        r = Annotation()
        for a, b, lab, _ in ref[var]:
            r[Segment(a, b)] = lab
        for collar in (0.0, 0.25):
            m = DiarizationErrorRate(collar=collar, skip_overlap=True)
            d = m(r, hyp, detailed=True)
            diar["der"][f"{var}_collar{collar}"] = {k: float(v) for k, v in d.items()}
        k = len({x[2] for x in ref[var]})
        hn = pipe({"waveform": w, "sample_rate": 16000}, num_speakers=k)
        diar.setdefault("pyannote_n", {})[var] = [[round(s.start, 3), round(s.end, 3), l] for s, _, l in hn.itertracks(yield_label=True)]
        m = DiarizationErrorRate(collar=0.25, skip_overlap=True)
        diar["der"][f"{var}_n{k}_collar0.25"] = {kk: float(vv) for kk, vv in m(r, hn, detailed=True).items()}
        bericht.append(f"pyannote {var}: {len(set(x[2] for x in diar['pyannote'][var]))} Sprecher, "
                       f"DER {diar['der'][f'{var}_collar0.25']['diarization error rate']:.3f} (collar 0.25)")
except Exception as ex:
    diar["pyannote_fehler"] = f"{type(ex).__name__}: {ex}"
    bericht.append("pyannote FEHLER: " + diar["pyannote_fehler"][:300])
    traceback.print_exc()

json.dump(diar, open("/out/diar.json", "w", encoding="utf-8"), ensure_ascii=False)
open("/out/bericht.txt", "w", encoding="utf-8").write("\n".join(bericht) + "\n")
print("\n".join(bericht))
