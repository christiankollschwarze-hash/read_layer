"""Mehrstimmige Hoerprobe: vertont ausgewaehlte Kapitel mit Erzaehler + Ensemble.

Aufruf: py -3.11 tools/hoerprobe_mehrstimmig.py <book_id> c001,c007 [en,de]
Input : work/400_regie.json, work/casting.json, work/sprecher.json (Stage 57b)
Output: work/_hoerprobe/<lang>/<kapitel>.wav  (+ Segment-Cache in _hoerprobe/_seg/)
Statisten und unbekannte Sprecher -> Erzaehlerstimme.
"""
import concurrent.futures as cf
import hashlib
import re
import json
import os
import sys
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from config import config  # noqa: E402
from pipeline import tts_client  # noqa: E402

RATE = 24000
LANG = {"en": "en-GB", "de": "de-DE"}
SATZDATEIEN = "--satzdateien" in sys.argv
STILLE = {"seg": 0.25, "satz": 0.55, "absatz": 0.9, "kapitel": 1.4}


def _englische_namen(data, lg):
    """Eigennamen, die in der Zielsprache unveraendert bleiben (z. B. Alice, Rosalind)
    -> sollen englisch ausgesprochen werden (CK 11.10.2026)."""
    if lg == "en":
        return []
    ch = ((data.get("meta") or {}).get("profile") or {}).get("characters") or {}
    namen = []
    for en, info in ch.items():
        ziel = (info or {}).get(lg, "") if isinstance(info, dict) else ""
        for teil in re.split(r"[,;/]| the ", en):
            teil = re.sub(r"^(the|The)\s+", "", teil).strip()
            if teil and teil[0].isupper() and (not ziel or teil.lower() in ziel.lower()):
                namen.append(teil)
    return sorted(set(namen), key=len, reverse=True)


def _aussprache(text, namen):
    treffer = [n for n in namen if re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", text)]
    return ""  # AP 62 (29.10.): "pronounced as in English" entfernt (verursachte "said Alice" in DE)


def stille(sek):
    return b"\x00\x00" * int(RATE * sek)


def _freigabe_ok(book_id, c):
    """Freigabe-Tor (CK 12.10.2026): vollstaendig vertont wird nur mit freigegebenen Stimmen.
    Vorher: tools/stimmen_probe.py -> anhoeren -> s410_casting --freigeben.
    Ausnahmen: --ohne-freigabe (z. B. Kapitel-Hoerproben) oder book.json stimmen_freigabe."""
    if "--ohne-freigabe" in sys.argv or c.get("tor") == "freigegeben":
        return True
    bp = os.path.join(config.book_dir(book_id), "book.json")
    if os.path.exists(bp) and json.load(open(bp, encoding="utf-8")).get("stimmen_freigabe"):
        return True
    from pipeline import voice_registry as vr
    reg = vr.laden()
    plan = c["plan"]
    offen = [f"{r.get('figur', 'Erzaehler')} ({r.get('stimme')})" for r in [plan["erzaehler"]] + plan["ensemble"]
             if reg.get(r.get("stimme"), {}).get("status") != "freigegeben"]
    if not offen:
        return True
    print(f"[hoerprobe] STOPP Freigabe-Tor: {len(offen)} Stimme(n) nicht freigegeben: {', '.join(offen)}")
    print(f"  1. py -3.11 tools/stimmen_probe.py {book_id}   -> work/_stimmen_probe/ anhoeren")
    print(f"  2. ok: py -3.11 -m pipeline.s410_casting {book_id} --freigeben")
    print(f"     nein: py -3.11 tools/stimme_neu_designen.py {book_id} \"<Figur>\" --notiz \"tiefere Stimme\"")
    return False


def main(book_id, kapitel, sprachen):
    wd = config.work_dir(book_id)
    if not _freigabe_ok(book_id, json.load(open(os.path.join(wd, "casting.json"), encoding="utf-8"))):
        sys.exit(2)
    data = json.load(open(config.work_path(book_id, "400_regie"), encoding="utf-8"))
    cast = json.load(open(os.path.join(wd, "casting.json"), encoding="utf-8"))["plan"]
    spr = {}
    sp = os.path.join(wd, "sprecher.json")
    if os.path.exists(sp):
        spr = json.load(open(sp, encoding="utf-8"))
    erz = cast["erzaehler"]["id"]
    stimmen = {"Erzaehler": erz}
    for e in cast["ensemble"]:
        if e.get("id"):
            stimmen[e["figur"]] = e["id"]
    out = os.path.join(wd, "_hoerprobe")
    seg_dir = os.path.join(out, "_seg")
    os.makedirs(seg_dir, exist_ok=True)

    for lg in sprachen:
        namen = _englische_namen(data, lg)
        if namen:
            print(f"[hoerprobe] {lg}: englische Aussprache fuer {', '.join(namen)}")
        for k in kapitel:
            plan = []   # (pcm_pfad | None, pause_danach)
            satz_teile = {}   # tag_id -> [pcm_pfade]  (1 WAV je Satz fuer Stage 58c/App)
            auftraege = []
            eintraege = [(tid, e) for tid, e in data["content"].items()
                         if tid.startswith(k) and e.get("type") not in ("skip", "tt")]
            for i, (tid, e) in enumerate(eintraege):
                typ = e.get("type")
                if typ == "p":
                    plan.append((None, STILLE["absatz"]))
                    continue
                text = (e.get(lg) or "").strip()
                if not text:
                    continue
                segs = (spr.get(tid) or {}).get(lg) or [{"t": text, "s": "Erzaehler"}]
                for j, s in enumerate(segs):
                    t = s["t"].strip()
                    if not t:
                        continue
                    v = stimmen.get(s["s"], erz)
                    stil = _aussprache(t, namen)
                    h = hashlib.sha1((f"{lg}|{v}|{t}" + (f"|{stil}" if stil else "")).encode("utf-8")).hexdigest()[:16]
                    pfad = os.path.join(seg_dir, f"{h}.pcm")
                    if not os.path.exists(pfad):
                        auftraege.append((t, v, lg, pfad, stil))
                    letzte = j == len(segs) - 1
                    plan.append((pfad, STILLE["kapitel"] if typ == "h" else
                                 (STILLE["satz"] if letzte else STILLE["seg"])))
                    satz_teile.setdefault(tid, []).append(pfad)
            print(f"[hoerprobe] {k} [{lg}]: {len(plan)} Teile, {len(auftraege)} neu zu vertonen ...")

            def vertone(a):
                t, v, l, pfad, stil = a
                pcm = tts_client.synthesize_bytes(t, stil, v, LANG[l], fmt="l16")
                if pcm[:4] == b"RIFF":
                    i = pcm.find(b"data")
                    pcm = pcm[i + 8:]
                with open(pfad + ".tmp", "wb") as f:
                    f.write(pcm)
                os.replace(pfad + ".tmp", pfad)

            fehler = 0
            with cf.ThreadPoolExecutor(max_workers=getattr(config, "TTS_PARALLEL", 8)) as ex:
                for fut in cf.as_completed([ex.submit(vertone, a) for a in auftraege]):
                    try:
                        fut.result()
                    except Exception as e:
                        fehler += 1
                        print(f"    Fehler: {str(e)[:160]}")
            ziel = os.path.join(out, lg)
            os.makedirs(ziel, exist_ok=True)
            wav_pfad = os.path.join(ziel, f"{k}.wav")
            with wave.open(wav_pfad, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(RATE)
                for pfad, pause in plan:
                    if pfad and os.path.exists(pfad):
                        w.writeframes(open(pfad, "rb").read())
                    w.writeframes(stille(pause))
            if SATZDATEIEN:
                adir = os.path.join(config.book_dir(book_id), "fassungen", lg, "audio")
                os.makedirs(adir, exist_ok=True)
                for tid, teile in satz_teile.items():
                    if not all(os.path.exists(x) for x in teile):
                        continue
                    with wave.open(os.path.join(adir, f"{tid}.wav"), "wb") as w2:
                        w2.setnchannels(1); w2.setsampwidth(2); w2.setframerate(RATE)
                        for n, x in enumerate(teile):
                            w2.writeframes(open(x, "rb").read())
                            if n < len(teile) - 1:
                                w2.writeframes(stille(STILLE["seg"]))
                print(f"    {len(satz_teile)} Satz-WAVs -> {adir}")
            dauer = os.path.getsize(wav_pfad) / 2 / RATE
            print(f"    -> {wav_pfad} ({dauer / 60:.1f} min, {fehler} Fehler)")


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    kap = a[1].split(",")
    if kap == ["alle"]:
        d = json.load(open(config.work_path(a[0], "400_regie"), encoding="utf-8"))
        kap = list(d["meta"]["chapters"].keys())
    main(a[0], kap, (a[2] if len(a) > 2 else "en,de").split(","))
