"""READ LAYER - Formant- plus Tonhoehen-Korrektur NACH dem Voice-Conversion-Schritt (Praat "Change gender").

Warum nach VC: eine Verschiebung am Quellaudio (tonhoehe_ht in overlay_vorbereiten) holt das VC grossteils
zurueck (gemessen Ruf der Wildnis: von +-3 HT kommen ~0,7 HT an). Hier wird das fertige VC-Ergebnis veraendert.

  formant_faktor < 1  -> laengerer Vokaltrakt (groesser/aelter/dunkler),  > 1 -> kuerzer (kleiner/juenger)
  tonhoehe_ht         -> Verschiebung des F0-Medians in Halbtoenen (Tonhoehenverlauf bleibt)

Aufruf als Modul:  korrigieren(x, sr, formant_faktor, tonhoehe_ht) -> np.ndarray
CLI:  py -3.11 tools/overlay_korrektur.py <book_id> [lang]   wendet casting.json ensemble[].korrektur[lang]
      {"formant_faktor":..,"tonhoehe_ht":..} auf audio_overlay/spannen/vc an -> spannen/vc_korr
      (tools/overlay_montage.py ruft das automatisch auf und montiert vc/ aus vc_korr)
"""
import os, sys, json, glob
import numpy as np
import soundfile as sf

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def korrigieren(x, sr, formant_faktor=1.0, tonhoehe_ht=0.0):
    import parselmouth
    from parselmouth.praat import call
    # Natuerlichkeitsgrenzen (CK 16.10.2026), siehe pipeline/trennung.py
    formant_faktor = min(1.10, max(0.94, float(formant_faktor)))
    tonhoehe_ht = min(2.0, max(-2.0, float(tonhoehe_ht)))
    if abs(formant_faktor - 1) < 1e-3 and abs(tonhoehe_ht) < 1e-3:
        return x
    snd = parselmouth.Sound(np.asarray(x, np.float64), sr)
    f0 = snd.to_pitch_ac(time_step=0.01, pitch_floor=60, pitch_ceiling=600).selected_array["frequency"]
    med = float(np.median(f0[f0 > 0])) if (f0 > 0).sum() >= 3 else 0.0
    neu_med = med * 2 ** (tonhoehe_ht / 12) if med else 0.0
    out = call(snd, "Change gender", 60, 600, float(formant_faktor), neu_med, 1.0, 1.0)
    y = out.values[0].astype(np.float32)
    n = len(x)
    y = y[:n] if len(y) >= n else np.pad(y, (0, n - len(y)))
    r1, r2 = np.sqrt(np.mean(y ** 2)), np.sqrt(np.mean(np.asarray(x) ** 2))
    return (y * (r2 / r1) if r1 > 0 else y).astype(np.float32)


def anwenden(book, lg="de"):
    """casting.json ensemble[].korrektur[lg] (oder flach) auf spannen/vc anwenden -> spannen/vc_korr.
    Figuren ohne Korrektur werden unveraendert kopiert. Rueckgabe: Anzahl korrigierter Spannen."""
    werk = glob.glob(os.path.join(HIER, "authors", "*", "books", book))[0]
    cast = json.load(open(os.path.join(werk, "work", "casting.json"), encoding="utf-8"))
    korr = {}
    for e in cast["plan"]["ensemble"]:
        k = e.get("korrektur") or {}
        k = k.get(lg, {}) if any(x in k for x in ("de", "en")) else k
        if k.get("formant_faktor") or k.get("tonhoehe_ht"):
            korr[e["figur"]] = k
    jobs = json.load(open(os.path.join(HIER, "gpu_overlay", f"{book}_{lg}", "jobs.json"), encoding="utf-8"))["jobs"]
    jg = os.path.join(HIER, "gpu_overlay", f"{book}_{lg}", "jobs_gemini.json")      # 22.10.2026 (AP4)
    if os.path.exists(jg):
        jobs = jobs + json.load(open(jg, encoding="utf-8"))["jobs"]
    # 22.10.2026 (AP4): Sprechweise je Kapitel (plan.sprechweise, tools/sprechweise.py) hat Vorrang vor korrektur
    sys.path.insert(0, os.path.join(HIER, "tools"))
    from sprechweise import werte as sw_werte, kapitel_anteile
    anteil = kapitel_anteile(werk) if (cast["plan"].get("sprechweise")) else {}
    ov = os.path.join(werk, "fassungen", lg, "audio_overlay")
    src, ziel = os.path.join(ov, "spannen", "vc"), os.path.join(ov, "spannen", "vc_korr")
    os.makedirs(ziel, exist_ok=True)
    n = 0
    for j in jobs:
        q = os.path.join(src, j["id"] + ".wav")
        if not os.path.exists(q):
            continue
        x, sr = sf.read(q, dtype="float32")
        k = sw_werte(cast, j["figur"], j["tag"][:4], anteil.get(j["tag"], 0)) or korr.get(j["figur"])
        if k:
            x = korrigieren(x, sr, k.get("formant_faktor", 1.0), k.get("tonhoehe_ht", 0.0)); n += 1
        sf.write(os.path.join(ziel, j["id"] + ".wav"), x, sr, subtype="PCM_16")
    liste = ", ".join(f"{f}: {k.get('formant_faktor', 1)}/{k.get('tonhoehe_ht', 0)} HT" for f, k in korr.items()) or "-"
    print(f"[korrektur] {n} Spannen korrigiert ({liste}) -> {ziel}")
    return n


if __name__ == "__main__":
    anwenden(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "de")
