"""Fish-Hoerproben fuer das Cockpit (AP Fish-Regie, 25.11.2026). Bis Modal-Hosting ueber die Fish-API.

  figur:   Erzaehlerstimme spielt die Figur mit ihrer Grundhaltung (410) -> optional Chatterbox-VC auf die
           VC-Zielstimme + Korrektur (wie 510). Text: --text, sonst erster Beitrag der Figur aus 430, sonst Beleg
           aus dem Steckbrief.  -> work/_probe/fish/<lg>/figur_<slug>.wav (+ _vc.wav)
  beitrag: ein Redebeitrag aus 430 mit seiner Anweisung (oder --anweisung TEXT zum Ausprobieren)
           -> work/_probe/fish/<lg>/<id>.wav
Kosten: Fish $/Byte (usage_log Stage 410 bzw. 430), VC Modal-GPU (usage_log 510-Probe unter Stage 410).

CLI: py -3.11 -m pipeline.fish_probe <werk> figur <lg> <FIGUR> [--text T] [--grundhaltung T] [--vc] [--wer CK]
     py -3.11 -m pipeline.fish_probe <werk> beitrag <lg> <ID> [--anweisung T] [--wer CK]
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import fish_motor, manifest, mock, usage_log
from pipeline import s410_casting as s410
from pipeline import s430_fish_regie as s430


def probe_dir(werk, lg):
    d = os.path.join(config.work_dir(werk), "_probe", "fish", lg)
    os.makedirs(d, exist_ok=True)
    return d


def slug(t):
    return re.sub(r"[^a-z0-9]+", "_", t.casefold()).strip("_")[:40] or "x"


def _besetzung(werk, lg):
    c = s410.laden(werk) or {}
    for st, bs in sorted(((c.get("rollen") or {}).get(lg) or {}).items()):
        if bs.get("engine") == "fish":
            return c, bs
    raise ValueError(f"keine Fish-Besetzung fuer {lg} (book.json audio_motor fish, 410 neu laufen lassen)")


def _erzaehler_id(bs, lg):
    erz = bs.get("erzaehler") or {}
    if not erz.get("stimme"):
        raise ValueError("kein Erzaehler besetzt")
    return erz.get("fish_id") or fish_motor.fish_id(erz["stimme"], lg, anlegen=True)


def _tts(werk, stage, lg, text, ref, ziel):
    if mock.aktiv():
        mock.wav(ziel)
        return 0
    wav, info = fish_motor.tts_einfach(text, ref)
    with open(ziel, "wb") as f:
        f.write(wav)
    usage_log.log_stueck(f"fish-{fish_motor.MODELL}", anzahl=info["bytes"], book_id=werk, stage=stage,
                         extra={"sprache": lg, "art": "probe"})
    return info["bytes"]


def _vc(werk, lg, quelle, e, ziel):
    """Chatterbox-VC (Modal, gpu_overlay/vc_modal.py) + Korrektur fuer eine Probe."""
    from pipeline import s510_hoerspiel_hybrid as s510
    if mock.aktiv():
        shutil.copy2(quelle, ziel)
        return
    name = f"{werk}_{lg}_probe"
    d = os.path.join(config.BASE_DIR, "gpu_overlay", name)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(os.path.join(d, "src"))
    os.makedirs(os.path.join(d, "ref"))
    shutil.copy2(quelle, os.path.join(d, "src", "probe.wav"))
    shutil.copy2(os.path.join(config.BASE_DIR, e["vc_ziel"]), os.path.join(d, "ref", f"{e['stimme']}.wav"))
    with open(os.path.join(d, "jobs.json"), "w", encoding="utf-8") as f:
        json.dump({"werk": werk, "lang": lg, "jobs": [{"id": "probe", "figur": e["figur"], "stimme": e["stimme"],
                                                       "text": "", "lang": lg}]}, f, ensure_ascii=False)
    r = subprocess.run([sys.executable, "-m", "modal", "run", "gpu_overlay/vc_modal.py", "--paket", name],
                       cwd=config.BASE_DIR)
    if r.returncode != 0:
        raise RuntimeError(f"Modal-VC Exit {r.returncode}")
    import zipfile
    z = zipfile.ZipFile(os.path.join(d, "ergebnis.zip"))
    with open(ziel + ".roh.wav", "wb") as f:
        f.write(z.read("vc/probe.wav"))
    bericht = z.read("bericht.txt").decode("utf-8", "replace") if "bericht.txt" in z.namelist() else ""
    m = re.search(r"WALL ([\d.]+) s", bericht)
    usage_log.log_gpu(werk, "410", float(m.group(1)) if m else 120.0, gpu="A10G",
                      extra={"sprache": lg, "art": "fish-vc-probe"})
    y = s510.lesen(ziel + ".roh.wav")
    k = e.get("korrektur") or {}
    if s510._korr_aktiv(k):
        y = s510.korrigieren(y, s510.SR, k.get("formant_faktor", 1.0), k.get("tonhoehe_ht", 0.0))
    s510.schreiben(ziel, y)
    os.remove(ziel + ".roh.wav")


def figur(werk, lg, fig, text=None, grundhaltung=None, vc=False):
    c, bs = _besetzung(werk, lg)
    e = next((x for x in bs.get("ensemble") or [] if x.get("figur") == fig), None)
    if not e:
        raise ValueError(f"Figur {fig!r} nicht im Ensemble {lg}")
    if not text:
        r = s430.laden(werk) or {}
        bt = next((x for x in ((r.get("sprachen") or {}).get(lg) or {}).get("beitraege") or [] if x["fig"] == fig), None)
        if bt:
            text = bt["text"]
        else:
            sb = next((f for f in (c.get("steckbriefe") or {}).get("figuren") or [] if f.get("name") == fig), {})
            text = (sb.get("beleg") or "").strip() or "Well, I never! What a curious thing to say."
    gh = grundhaltung if grundhaltung is not None else (e.get("fish_grundhaltung") or "")
    voll = (f"[{gh}] " if gh else "") + text
    d = probe_dir(werk, lg)
    p = os.path.join(d, f"figur_{slug(fig)}.wav")
    n = _tts(werk, "410", lg, voll, _erzaehler_id(bs, lg), p)
    out = {"fish": p, "text": voll, "bytes": n}
    if vc:
        if not e.get("vc_ziel"):
            raise ValueError(f"{fig}: kein VC-Ziel (410)")
        pv = os.path.join(d, f"figur_{slug(fig)}_vc.wav")
        _vc(werk, lg, p, e, pv)
        out["vc"] = pv
    _merken(werk, lg, f"figur:{fig}", out)
    return out


def beitrag(werk, lg, bid, anweisung=None):
    _c, bs = _besetzung(werk, lg)
    r = s430.laden(werk) or {}
    bt = next((x for x in ((r.get("sprachen") or {}).get(lg) or {}).get("beitraege") or [] if x["id"] == bid), None)
    if not bt:
        raise ValueError(f"Beitrag {lg}/{bid} nicht in 430")
    x = dict(bt)
    if anweisung is not None:
        x["anweisung"] = anweisung.strip()
    voll = s430.fish_text(x)
    p = os.path.join(probe_dir(werk, lg), f"{bid}.wav")
    n = _tts(werk, "430", lg, voll, _erzaehler_id(bs, lg), p)
    out = {"fish": p, "text": voll, "bytes": n}
    _merken(werk, lg, f"beitrag:{bid}", out)
    return out


def _merken(werk, lg, key, out):
    p = os.path.join(probe_dir(werk, lg), "proben.json")
    d = {}
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
    d[key] = dict(out, wann=manifest.jetzt())
    manifest.json_atomar(p, d, indent=1)


def proben(werk, lg):
    p = os.path.join(config.work_dir(werk), "_probe", "fish", lg, "proben.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fish-Hoerprobe (Figur 410 / Beitrag 430)")
    ap.add_argument("werk")
    ap.add_argument("art", choices=("figur", "beitrag"))
    ap.add_argument("lg")
    ap.add_argument("name")
    ap.add_argument("--text")
    ap.add_argument("--grundhaltung")
    ap.add_argument("--anweisung")
    ap.add_argument("--vc", action="store_true")
    ap.add_argument("--wer")
    a = ap.parse_args(argv)
    try:
        if a.art == "figur":
            out = figur(a.werk, a.lg, a.name, a.text, a.grundhaltung, a.vc)
        else:
            out = beitrag(a.werk, a.lg, a.name, a.anweisung)
    except (ValueError, RuntimeError) as e:
        print(f"[probe] Fehler: {e}")
        return 1
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
