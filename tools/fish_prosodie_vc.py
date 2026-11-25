"""READ LAYER — Chatterbox-Overlay auf den Prosodie-Stresstest (25.11.2026, Wunsch CK).
Nimmt die Fish-Takes aus tools/fish_prosodie_test/<lg>/ (Erzaehlerstimme spielt alle Figuren), schneidet jede
Figurenpassage per Wort-Zeitmarken (MMS_FA aus dem Modal-Lauf) aus, wandelt sie per Chatterbox-VC
(gpu_overlay/vc_modal.py, wie Stage 511) in die Figurenstimme und setzt sie wieder ein (Lautheit an Erzaehler,
10 ms Blende). Prosodie (Fluestern, Stottern, Wut ...) bleibt von Fish, nur das Timbre wechselt.
Ausgabe tools/fish_prosodie_test/<lg>/<variante>_vc.wav. Kosten ~0,05 $ (L4/A10G).
Aufruf:  py -3.11 tools/fish_prosodie_vc.py [--varianten 2_anweisung,3_stark]
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import wave
import zipfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config  # noqa: E402
from pipeline import s503_vertonung_fish as V503  # noqa: E402
from tools import fish_prosodie_test as P  # noqa: E402

SR = 24000
# Figur -> Stimme aus stimmen_archiv (klon_<lg>.wav als VC-Ziel); Erzaehlerin bleibt die Fish-Stimme
BESETZUNG = {"Mira": "w_kind_hoch_neugierig", "Holm": "m_alt_mittel_ruhig", "Alba": "grossmutter_b",
             "Brand": "m_alt_tief_cholerisch", "Oda": "w_jung_mittel_ruhig"}
BLENDE_S = 0.010


def lesen(p):
    with wave.open(p, "rb") as w:
        sr, n = w.getframerate(), w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype("float32") / 32768
    if n > 1:
        x = x.reshape(-1, n).mean(1)
    if sr != SR:
        x = np.interp(np.arange(0, len(x), sr / SR), np.arange(len(x)), x).astype("float32")
    return x


def schreiben(p, x):
    with wave.open(p, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def rms_db(x):
    w = int(0.05 * SR)
    if len(x) < w:
        return None
    fr = np.sqrt((x[:len(x) // w * w].reshape(-1, w) ** 2).mean(1))
    akt = fr[fr > 10 ** (-45 / 20)]
    return float(20 * np.log10(np.sqrt((akt ** 2).mean()))) if len(akt) else None


def spannen(woerter, x):
    """SZENE -> [(figur, a_s, b_s)] mit der Schnitt-Mechanik aus Stage 503 (s503.schnittpunkte: Grenze im leisesten
    Punkt der Pause zwischen den Woertern, Buchstabenstrom-Abgleich) -> Auslaut-Konsonanten bleiben am Wort."""
    grenzen, abd = V503.schnittpunkte([{"text": t} for _, t, _, _ in P.SZENE], woerter, x, SR)
    if grenzen is None or not 0.97 <= abd <= 1.03:
        raise SystemExit(f"Zeitmarken decken die Szene nicht ab (Abdeckung {abd:.2f})")
    pk = [0.0] + grenzen + [len(x) / SR]
    return [(fig, pk[k], pk[k + 1]) for k, (fig, *_) in enumerate(P.SZENE)]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="de")
    ap.add_argument("--varianten", default="2_anweisung,3_stark")
    a = ap.parse_args(argv)
    lg = a.lang
    d = os.path.join(P.AUS, lg)
    pf = os.path.join(config.BASE_DIR, "gpu_fish", f"prosodie_test_{lg}")
    jobs = {j["variante"]: j for j in json.load(open(os.path.join(pf, "jobs.json"), encoding="utf-8"))["jobs"]}
    paket = f"prosodie_vc_{lg}"
    pd = os.path.join(config.BASE_DIR, "gpu_overlay", paket)
    shutil.rmtree(pd, ignore_errors=True)
    os.makedirs(os.path.join(pd, "src"))
    os.makedirs(os.path.join(pd, "ref"))
    plan, vjobs = {}, []
    for v in a.varianten.split(","):
        j = jobs[v]
        x = lesen(os.path.join(pf, "out", j["key"] + ".wav"))
        woerter = json.load(open(os.path.join(pf, "out", j["key"] + ".json"), encoding="utf-8"))["woerter"]
        sp = spannen(woerter, x)
        plan[v] = (x, sp)
        for k, (fig, s0, s1) in enumerate(sp):
            if fig not in BESETZUNG:
                continue
            st = BESETZUNG[fig]
            ref = os.path.join(pd, "ref", f"{st}.wav")
            if not os.path.exists(ref):
                shutil.copy2(os.path.join(config.STIMMEN_DIR, st, f"klon_{lg}.wav"), ref)
            bid = f"{v}_{k:02d}"
            schreiben(os.path.join(pd, "src", f"{bid}.wav"), x[int(s0 * SR):int(s1 * SR)])
            vjobs.append({"id": bid, "figur": fig, "stimme": st, "text": "", "lang": lg})
    with open(os.path.join(pd, "jobs.json"), "w", encoding="utf-8") as f:
        json.dump({"werk": "prosodie_test", "lang": lg, "jobs": vjobs}, f, ensure_ascii=False, indent=1)
    print(f"[vc] {len(vjobs)} Figurenpassagen -> Modal (Chatterbox-VC)", flush=True)
    r = subprocess.run([sys.executable, "-m", "modal", "run", "gpu_overlay/vc_modal.py", "--paket", paket],
                       cwd=config.BASE_DIR)
    if r.returncode != 0:
        return r.returncode
    z = zipfile.ZipFile(os.path.join(pd, "ergebnis.zip"))
    vc = {os.path.basename(n)[:-4]: z.read(n) for n in z.namelist() if n.startswith("vc/") and n.endswith(".wav")}
    k2 = int(BLENDE_S * SR)
    rampe = np.linspace(0, 1, k2, dtype="float32")
    for v, (x, sp) in plan.items():
        teile = []
        for k, (fig, s0, s1) in enumerate(sp):
            y = x[int(s0 * SR):int(s1 * SR)].copy()
            bid = f"{v}_{k:02d}"
            if bid in vc:
                tmp = os.path.join(pd, "_t.wav")
                open(tmp, "wb").write(vc[bid])
                y = lesen(tmp)
            teile.append((fig in BESETZUNG and bid in vc, y))
        erz = rms_db(np.concatenate([y for f_, y in teile if not f_]))
        out = []
        for f_, y in teile:
            if f_ and erz is not None and rms_db(y) is not None:
                y = y * float(10 ** ((erz - rms_db(y)) / 20))
            if len(y) > 2 * k2:
                y[:k2] *= rampe
                y[-k2:] *= rampe[::-1]
            out.append(y)
        y = np.concatenate(out)
        y = y * min(1.0, 0.89 / max(1e-9, float(np.abs(y).max())))   # Spitze <= -1 dBFS
        schreiben(os.path.join(d, f"{v}_vc.wav"), y)
        print(f"[vc] {v}_vc.wav {len(y) / SR:.1f} s ({sum(1 for f_, _ in teile if f_)} Passagen gewandelt)", flush=True)
    fehlt = [j["id"] for j in vjobs if j["id"] not in vc]
    if fehlt:
        print("[vc] ohne VC:", ", ".join(fehlt), flush=True)
    print("Besetzung:", ", ".join(f"{k}={s}" for k, s in BESETZUNG.items()), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
