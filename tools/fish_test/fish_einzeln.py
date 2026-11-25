"""Variante 2: jeder Redebeitrag einzeln (Single-Speaker), dann Montage. Resume über vorhandene WAVs.
Aufruf: python tools/fish_test/fish_einzeln.py de|en  [max_sekunden]"""
import sys, json, time, struct, pathlib, wave, concurrent.futures as cf
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fish_test as F
import requests

PAUSE_TURN, PAUSE_ABSATZ = 0.25, 0.6
MAX_MERGE = 700
import os, shutil
REGIE_AN = os.environ.get("REGIE") == "1"
ERZ_ALLE = os.environ.get("ERZ_ALLE") == "1"   # alles in Erzählerstimme, Figuren nur per Regie (Quelle für Chatterbox-VC)
if ERZ_ALLE: REGIE_AN = True
REGIE = {"Dormouse": "[very sleepy, drowsy, slow, mumbling, half asleep, occasional yawn]",
         "March Hare": "[excited, giddy, fast, high-strung, restless]",
         "Hatter": "[eccentric, flighty, theatrical]",
         "Alice": "[curious, bright, polite, a little indignant]"}
if ERZ_ALLE:
    REGIE = {"Dormouse": "[voicing a very sleepy old dormouse: drowsy, slow, mumbling, half asleep, yawning]",
             "March Hare": "[voicing the March Hare: excited, giddy, fast, high-strung, restless]",
             "Hatter": "[voicing the Hatter: eccentric, flighty, theatrical]",
             "Alice": "[voicing a curious, bright little girl: polite, a little indignant]"}

def turns_mit_absatz(lg):
    u = json.load(open(F.BOOK / "work/310_uebersetzung.json", encoding="utf-8"))["content"]
    sp = json.load(open(F.BOOK / "work/sprecher.json", encoding="utf-8"))
    out = []; absatz = False
    for uid, v in u.items():
        if not uid.startswith(F.KAP): continue
        if v["type"] == "p": absatz = True; continue
        if v["type"] == "h": continue
        segs = sp[uid][lg] if uid in sp else [{"t": v.get(lg, ""), "s": "Erzaehler"}]
        for s in segs:
            fig = s["s"]
            if fig not in F.FIGUREN: fig = F.CHOR_ERSATZ if fig == "Crowd / Chorus" and F.CHOR_ERSATZ else "Erzaehler"
            t = s["t"].strip()
            if not t: continue
            if out and out[-1]["fig"] == fig and not absatz and len(out[-1]["t"]) + len(t) < MAX_MERGE:
                out[-1]["t"] += " " + t
            else:
                out.append({"fig": fig, "t": t, "absatz": absatz})
            absatz = False
    return out

def tts1(text, rid, f):
  for versuch in range(6):
    r = requests.post(f"{F.API}/v1/tts", headers={**F.H, "model": "drama-3", "Content-Type": "application/json"},
                      data=json.dumps({"text": text, "reference_id": rid, "format": "wav", "sample_rate": 24000,
                                       "latency": "normal", "normalize": True}), timeout=300)
    if r.status_code == 429: time.sleep(3 + 3 * versuch); continue
    if r.status_code >= 300: raise RuntimeError(f"{r.status_code} {r.text[:300]}")
    break
  else: raise RuntimeError("429 dauerhaft")
  if True:
    b = bytearray(r.content); i = b.find(b"data")
    b[4:8] = struct.pack("<I", len(b) - 8); b[i+4:i+8] = struct.pack("<I", len(b) - i - 8)
    f.write_bytes(bytes(b))
    F.log({"art": "tts_einzeln", "datei": f.name, "bytes": len(text.encode()), "usd_listenpreis_15": round(len(text.encode())/1e6*15, 5)})

def main(lg, budget):
    t0 = time.time(); ids = F.stimmen(lg)
    tr = turns_mit_absatz(lg)
    d = F.OUT / (f"{lg}_erz_regie" if ERZ_ALLE else f"{lg}_einzeln_regie" if REGIE_AN else f"{lg}_einzeln"); d.mkdir(exist_ok=True)
    if REGIE_AN:  # Erzähler unverändert aus Variante ohne Regie übernehmen
        for n, x in enumerate(tr, 1):
            src = F.OUT / f"{lg}_einzeln" / f"t{n:04d}.wav"
            if x["fig"] == "Erzaehler" and src.exists() and not (d / src.name).exists(): shutil.copy(src, d / src.name)
    jobs = [(n, x) for n, x in enumerate(tr, 1) if not (d / f"t{n:04d}.wav").exists()]
    print(f"{lg}: {len(tr)} Beiträge, offen {len(jobs)}")
    with cf.ThreadPoolExecutor(3) as ex:
        futs = {}
        for n, x in jobs:
            if time.time() - t0 > budget: break
            futs[ex.submit(tts1, (REGIE.get(x["fig"], "") + " " + x["t"]).strip() if REGIE_AN else x["t"], F.FIGUREN and ids[0 if ERZ_ALLE else F.FIGUREN.index(x["fig"])], d / f"t{n:04d}.wav")] = n
        for fu in cf.as_completed(futs):
            try: fu.result()
            except Exception as e: print("Fehler", futs[fu], e)
    offen = [n for n in range(1, len(tr)+1) if not (d / f"t{n:04d}.wav").exists()]
    if offen: print("noch offen:", len(offen)); return
    sr = 24000; still = lambda s: b"\x00\x00" * int(sr * s)
    with wave.open(str(F.OUT / lg / f"fish_{'erz_regie' if ERZ_ALLE else 'einzeln_regie' if REGIE_AN else 'einzeln'}_{F.KAP}_{lg}.wav"), "wb") as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(sr)
        marks = []; pos = 0.0
        for n, x in enumerate(tr, 1):
            if n > 1:
                p = PAUSE_ABSATZ if x["absatz"] else PAUSE_TURN
                out.writeframes(still(p)); pos += p
            with wave.open(str(d / f"t{n:04d}.wav")) as w:
                fr = w.readframes(w.getnframes()); out.writeframes(fr)
                marks.append({"n": n, "start": round(pos, 2), "fig": x["fig"], "t": x["t"][:80]}); pos += w.getnframes() / sr
    json.dump(marks, open(F.OUT / lg / f"{'erz_regie' if ERZ_ALLE else 'einzeln_regie' if REGIE_AN else 'einzeln'}_marken.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(lg, "fertig", round(pos / 60, 2), "min")

if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 150)
