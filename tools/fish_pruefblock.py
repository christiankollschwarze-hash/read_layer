"""READ LAYER — Pruefblock Klanggleichheit Fish-API vs. Modal (AP Fish-Modal 25.11.2026, Schritt 3).
Ein kurzer Block (Standard ~1.800 Zeichen ≈ 2 min, vorhandener Text Alice Kap. 7 aus tools/fish_test/<lg>/block_*.txt, KEINE Werk-Neuvertonung)
in der Erzaehlerstimme mit Figuren-Anweisungen ueber beide Wege:
  1. API  (fish_motor.tts_zeitmarken, Fish-Zeitmarken)          -> tools/fish_pruefblock/<lg>/api.wav
  2. Modal (gpu_fish/fish_modal.py, eigene Gewichte + MMS_FA)    -> .../modal.wav
  3. MMS_FA auf das API-Audio (im selben Modal-Lauf)              -> Zeitmarken-Abweichung FA vs. Fish auf GLEICHEM Audio
Ausgabe tools/fish_pruefblock/<lg>/bericht.md (Dauer, Woerter/s, Abdeckung, Abweichung Wortanfaenge + Schnittgrenzen, Kosten,
Modal-Bericht: GPU, Kaltstart, RTF). Hoervergleich durch CK; erst nach Freigabe config.FISH_MODAL_FREI = True.
Aufruf:  py -3.11 tools/fish_pruefblock.py [--lang de] [--stimme grossmutter_a] [--zeichen 1800] [--nur-auswerten]
"""
import argparse
import difflib
import json
import os
import shutil
import statistics
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config  # noqa: E402
from pipeline import fish_motor as F  # noqa: E402
from pipeline import manifest  # noqa: E402
from pipeline import s503_vertonung_fish as V  # noqa: E402

AUS = os.path.join(config.BASE_DIR, "tools", "fish_pruefblock")


FIGUREN = ["Erzaehler", "Alice", "Hatter", "March Hare", "Dormouse"]    # Speaker-Index im Fish-Test (fish_test.py)


def beitraege(lg, zeichen):
    """Erzaehler/Figuren-Stuecke aus tools/fish_test/<lg>/block_NN.txt (<|speaker:i|>) bis ~zeichen Zeichen;
    Figuren mit Anweisung [voicing ...] wie in Stage 430 (ohne Moment)."""
    import glob
    import re
    out, n = [], 0
    for p in sorted(glob.glob(os.path.join(config.BASE_DIR, "tools", "fish_test", lg, "block_*.txt"))):
        with open(p, encoding="utf-8") as f:
            roh = f.read()
        for i, t in re.findall(r"<\|speaker:(\d+)\|>([^<]*)", roh):
            t = t.strip()
            if not t:
                continue
            fig = FIGUREN[int(i)] if int(i) < len(FIGUREN) else "Erzaehler"
            text = t if fig == "Erzaehler" else f"[{F.grundhaltung(fig)}] {t}"
            out.append({"fig": fig, "text": text})
            n += len(text) + 1
            if n >= zeichen:
                return out
    return out


def _norm(w):
    return V._buchst(w)


def abweichung(a, b):
    """Wortlisten [{w,a,b}] zweier Zeitmarkenquellen auf GLEICHEM Audio -> Kennzahlen Wortanfang (s)."""
    na, nb = [_norm(x["w"]) for x in a], [_norm(x["w"]) for x in b]
    sm = difflib.SequenceMatcher(None, na, nb, autojunk=False)
    d = []
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            d.append(abs(float(a[blk.a + k]["a"]) - float(b[blk.b + k]["a"])))
    if not d:
        return {"paare": 0}
    d.sort()
    return {"paare": len(d), "von": len(na), "median_s": round(statistics.median(d), 3),
            "p90_s": round(d[int(0.9 * (len(d) - 1))], 3), "max_s": round(d[-1], 3)}


def _wav_s(p):
    import wave
    with wave.open(p) as w:
        return w.getnframes() / w.getframerate()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="de")
    ap.add_argument("--stimme", default="grossmutter_a")
    ap.add_argument("--zeichen", type=int, default=1800)
    ap.add_argument("--nur-auswerten", action="store_true", help="vorhandene Ergebnisse neu auswerten (keine Kosten)")
    a = ap.parse_args(argv)
    lg = a.lang
    d = os.path.join(AUS, lg)
    os.makedirs(d, exist_ok=True)
    bt = beitraege(lg, a.zeichen)
    text = " ".join(x["text"] for x in bt)
    h = manifest.hash_obj({"t": text, "st": a.stimme, "lg": lg})
    with open(os.path.join(d, "text.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    api_wav, api_js = os.path.join(d, "api.wav"), os.path.join(d, "api_woerter.json")
    kosten = {}
    if not a.nur_auswerten:
        # ---- 1. API
        fid = F.fish_id(a.stimme, lg, anlegen=True)
        t0 = time.time()
        wav, ww, info = F.tts_zeitmarken(text, fid)
        with open(api_wav, "wb") as f:
            f.write(wav)
        with open(api_js, "w", encoding="utf-8") as f:
            json.dump({"woerter": ww, "info": info}, f, ensure_ascii=False)
        kosten["api_usd"] = round(F.kosten_usd(text), 4)
        kosten["api_s"] = round(time.time() - t0, 1)
        print(f"[pruefblock] API: {len(ww)} Woerter, {_wav_s(api_wav):.1f} s Audio, ~{kosten['api_usd']} $", flush=True)
        # ---- 2.+3. Modal: Vertonung + FA auf API-Audio
        paket = f"pruefblock_{lg}"
        pd = os.path.join(config.BASE_DIR, "gpu_fish", paket)
        shutil.rmtree(pd, ignore_errors=True)
        os.makedirs(os.path.join(pd, "ref"))
        os.makedirs(os.path.join(pd, "audio"))
        shutil.copy2(F.klon_clip(a.stimme, lg), os.path.join(pd, "ref", "ref.wav"))
        shutil.copy2(api_wav, os.path.join(pd, "audio", "api.wav"))
        job = V._modal_jobs({"text": text, "soll": f"pb_{h}", "ids": ["pruefblock"]}, 0)
        fa = dict(job, key=f"pb_{h}_fa_api", audio="audio/api.wav")
        manifest.json_atomar(os.path.join(pd, "jobs.json"), {"werk": "pruefblock", "lang": lg, "stimme": a.stimme,
                             "ref": {"datei": "ref.wav", "text": F.klon_text(lg)}, "jobs": [job, fa]}, indent=1)
        r = subprocess.run([sys.executable, "-m", "modal", "run", "gpu_fish/fish_modal.py", "--paket", paket],
                           cwd=config.BASE_DIR)
        if r.returncode != 0:
            print(f"[pruefblock] Modal Exit {r.returncode} – Bericht/Log pruefen", flush=True)
        for key, ziel in ((job["key"], "modal"), (fa["key"], "fa_api")):
            for end in (".wav", ".json"):
                q = os.path.join(pd, "out", key + end)
                if os.path.exists(q) and not (ziel == "fa_api" and end == ".wav"):
                    shutil.copy2(q, os.path.join(d, ziel + (".wav" if end == ".wav" else "_woerter.json")))
        if os.path.exists(os.path.join(pd, "bericht.txt")):
            shutil.copy2(os.path.join(pd, "bericht.txt"), os.path.join(d, "modal_bericht.txt"))
    # ---- Auswertung
    def lade(n):
        p = os.path.join(d, n)
        if not os.path.exists(p):
            return None
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    api, mod, faa = lade("api_woerter.json"), lade("modal_woerter.json"), lade("fa_api_woerter.json")
    ber = {}
    if os.path.exists(os.path.join(d, "modal_bericht.txt")):
        with open(os.path.join(d, "modal_bericht.txt"), encoding="utf-8") as f:
            ber = V.bericht_lesen(f.read())
    zeilen = [f"# Pruefblock Fish API vs. Modal – {lg} ({time.strftime('%Y-%m-%d %H:%M')})", "",
              f"Text: {len(text)} Zeichen, {len(bt)} Beitraege (Erzaehler {a.stimme}, Figuren per Anweisung) – text.txt", ""]
    zeilen += ["| Weg | Datei | Dauer s | Woerter/s | Abdeckung | Zeitmarken |", "|---|---|---|---|---|---|"]
    grenzen = {}
    for name, w, wav, quelle in (("API", api, "api.wav", "Fish"), ("Modal", mod, "modal.wav", "MMS_FA")):
        p = os.path.join(d, wav)
        if not w or not os.path.exists(p):
            zeilen.append(f"| {name} | – | – | – | – | fehlt |")
            continue
        dauer = _wav_s(p)
        g, abd = V.schnittpunkte(bt, w["woerter"])
        grenzen[name] = g
        zeilen.append(f"| {name} | {wav} | {dauer:.1f} | {len(w['woerter']) / dauer:.2f} | {abd:.3f} | {quelle} |")
    zeilen.append("")
    if api and faa:
        ab = abweichung(api["woerter"], faa["woerter"])
        g_fa, _ = V.schnittpunkte(bt, faa["woerter"])
        gd = sorted(abs(x - y) for x, y in zip(grenzen.get("API") or [], g_fa or []))
        zeilen += ["## Zeitmarken MMS_FA vs. Fish-API (gleiches API-Audio)",
                   f"- Wortanfaenge: {ab.get('paare')}/{ab.get('von')} Paare, Median {ab.get('median_s')} s, "
                   f"p90 {ab.get('p90_s')} s, max {ab.get('max_s')} s",
                   f"- Schnittgrenzen Erzaehler/Figur: {len(gd)} Grenzen, Median "
                   f"{round(statistics.median(gd), 3) if gd else '–'} s, max {round(gd[-1], 3) if gd else '–'} s", ""]
    if ber:
        usd = round(ber["wall_s"] / 3600 * F.modal_preis_h(ber["gpu"]), 4)
        zeilen += ["## Modal", f"- GPU {ber['gpu_name']} | Kaltstart {ber['kalt_s']} s | WALL {ber['wall_s']} s | "
                   f"RTF {ber['rtf']} | ~{usd} $ | Modell {ber['modell']}", ""]
        kosten["modal_usd"] = usd
    if kosten:
        zeilen += [f"Kosten: {json.dumps(kosten)}", ""]
        with open(os.path.join(AUS, "kosten.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"zeit": time.strftime("%Y-%m-%d %H:%M:%S"), "lang": lg, **kosten}) + "\n")
    zeilen += ["## Hoervergleich (CK)", "- api.wav vs. modal.wav: Klang, Prosodie, Figuren-Anweisungen, Aussprache",
               "- Urteil hier eintragen; bei Freigabe config.FISH_MODAL_FREI = True setzen und PROJEKTSTAND vermerken."]
    with open(os.path.join(d, "bericht.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(zeilen) + "\n")
    print("\n".join(zeilen), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
