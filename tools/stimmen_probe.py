"""READ LAYER — Stimmen-Probe vor der Freigabe (CK 12.10.2026)

Ablauf (Freigabe-Tor fuer neue Stimmen):
  1. Stage 57 Casting (--design)   -> Stimmen aus dem Archiv oder neu designt (Status "kandidat")
  2. Stage 57b Sprecher           -> wer spricht welchen Satzteil
  3. tools/stimmen_probe.py <book> -> je Figur EIN typischer Satzteil aus dem Skript, EN + DE vertont
  4. CK hoert work/_stimmen_probe/ an
       ok    -> py -3.11 -m pipeline.s410_casting <book> --freigeben
       nein  -> py -3.11 tools/stimme_neu_designen.py <book> "<Figur>"  (danach Schritt 3 erneut)
  5. tools/hoerprobe_mehrstimmig.py   -> laeuft erst nach Freigabe; die Probe-Saetze liegen schon
     im Segment-Cache (gleicher Schluessel) und werden recycelt, nicht neu bezahlt.

Aufruf: py -3.11 tools/stimmen_probe.py <book_id> [--alle]   (--alle: auch freigegebene Stimmen)
"""
import json
import os
import shutil
import sys
import hashlib
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from config import config  # noqa: E402
from pipeline import tts_client, voice_registry as vr  # noqa: E402
import hoerprobe_mehrstimmig as hm  # noqa: E402

ZIEL_LAENGE = 140   # Zeichen: lang genug zum Beurteilen, kurz genug fuer schnelles Hoeren


def _segment(spr, figur, lg):
    kand = [x["t"].strip() for e in spr.values() for x in (e.get(lg) or [])
            if x.get("s") == figur and len(x.get("t", "").strip()) >= 25]
    if not kand:
        return None
    return min(kand, key=lambda t: abs(len(t) - ZIEL_LAENGE))


def main(book_id, alle=False):
    wd = config.work_dir(book_id)
    data = json.load(open(config.work_path(book_id, "400_regie"), encoding="utf-8"))
    c = json.load(open(os.path.join(wd, "casting.json"), encoding="utf-8"))
    sp = os.path.join(wd, "sprecher.json")
    if not os.path.exists(sp):
        print("[probe] Erst Stage 57b (Sprecher-Zuordnung) laufen lassen.")
        return 2
    spr = json.load(open(sp, encoding="utf-8"))
    reg = vr.laden()
    seg_dir = os.path.join(wd, "_hoerprobe", "_seg")
    out = os.path.join(wd, "_stimmen_probe")
    os.makedirs(seg_dir, exist_ok=True)
    os.makedirs(out, exist_ok=True)
    rollen = [dict(c["plan"]["erzaehler"], figur="Erzaehler")] + c["plan"]["ensemble"]
    zeilen, n_neu, n_cache = [], 0, 0
    for nr, r in enumerate(rollen):
        if not r.get("id"):
            zeilen.append(f"{r['figur']}: OHNE STIMME (erst Stage 57 --design)")
            continue
        status = reg.get(r["stimme"], {}).get("status", "?")
        if status == "freigegeben" and not alle:
            continue
        for lg in ("en", "de"):
            t = _segment(spr, r["figur"], lg)
            if not t:
                continue
            stil = hm._aussprache(t, hm._englische_namen(data, lg))
            h = hashlib.sha1((f"{lg}|{r['id']}|{t}" + (f"|{stil}" if stil else "")).encode("utf-8")).hexdigest()[:16]
            pcm_pfad = os.path.join(seg_dir, f"{h}.pcm")
            if os.path.exists(pcm_pfad):
                n_cache += 1
            else:
                pcm = tts_client.synthesize_bytes(t, stil, r["id"], hm.LANG[lg], fmt="l16")
                if pcm[:4] == b"RIFF":
                    pcm = pcm[pcm.find(b"data") + 8:]
                with open(pcm_pfad + ".tmp", "wb") as f:
                    f.write(pcm)
                os.replace(pcm_pfad + ".tmp", pcm_pfad)
                n_neu += 1
            name = f"{nr:02d}_{r['figur'].replace(' ', '_').replace('.', '')}_{lg}.wav"
            with wave.open(os.path.join(out, name), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(hm.RATE)
                w.writeframes(open(pcm_pfad, "rb").read())
            arch = os.path.join(vr.STIMMEN_DIR, r["stimme"])
            if os.path.isdir(arch):
                shutil.copy2(os.path.join(out, name), os.path.join(arch, f"probe_{book_id}_{lg}.wav"))
            zeilen.append(f"{name}  [{r['stimme']} · {status}]  {t}")
    with open(os.path.join(out, "liste.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(zeilen) + "\n")
    print("\n".join(zeilen))
    print(f"[probe] {n_neu} neu vertont, {n_cache} aus dem Cache -> {out}")
    print(f"[probe] Freigabe: py -3.11 -m pipeline.s410_casting {book_id} --freigeben")
    return 0


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    sys.exit(main(a[0], alle="--alle" in sys.argv))
