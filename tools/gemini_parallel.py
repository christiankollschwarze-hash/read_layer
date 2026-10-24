"""READ LAYER — Stage 58 (Gemini-TTS) kapitelweise parallel.
Aufruf:  py -3.11 tools/gemini_parallel.py <book_id> <lang> [--jobs 5] [--kapitel c001,c002] [--mit-fa]
- Startet je Kapitel einen eigenen s500_vertonung_gemini-Prozess, hoechstens --jobs gleichzeitig.
- Ohne --mit-fa: READLAYER_58_OHNE_FA=1 (Wortzeiten macht Stage 58c).
- Logs je Kapitel: work/_58_logs/<lang>_<kapitel>.log ; Zusammenfassung mit Laufzeiten am Ende.
- Bereits vorhandene WAVs werden uebersprungen (Wiederaufnahme wie gewohnt).
- 22.10.2026: Ich-Erzaehler je Kapitel -> --voice je Kapitel aus casting.json plan.erzaehler_je_kapitel + plan.gemini_stimmen
  (Figur -> Gemini-Stimme: Standardname wie "Zephyr" oder designte voice_...-ID), nur fuer Hoerspiel-Sprachen.
"""
import json, os, subprocess, sys, time

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HIER)
from config import config  # noqa: E402


def main():
    a = sys.argv[1:]
    book, lg = a[0], a[1]
    opt = lambda n, d=None: a[a.index(n) + 1] if n in a and a.index(n) + 1 < len(a) else d
    jobs = int(opt("--jobs", 5))
    data = json.load(open(config.work_path(book, "400_regie"), encoding="utf-8"))["content"]
    kap = opt("--kapitel")
    kapitel = kap.split(",") if kap else sorted({t[:4] for t, e in data.items() if (e.get(lg) or "").strip()})
    logdir = os.path.join(config.work_dir(book), "_58_logs")
    os.makedirs(logdir, exist_ok=True)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    if "--mit-fa" not in a:
        env["READLAYER_58_OHNE_FA"] = "1"
    stimme_kap = {}
    cp = os.path.join(config.work_dir(book), "casting.json")
    if os.path.exists(cp):
        cast = json.load(open(cp, encoding="utf-8"))
        plan = cast.get("plan") or {}
        if lg in (cast.get("hoerspiel_sprachen") or [config.werk_sprachen(book)[0]]):
            gs = plan.get("gemini_stimmen") or {}
            stimme_kap = {k: gs[f] for k, f in (plan.get("erzaehler_je_kapitel") or {}).items() if f in gs}
            if stimme_kap:
                print("[parallel] Stimme je Kapitel: " + ", ".join(f"{k}={v}" for k, v in sorted(stimme_kap.items())), flush=True)
    offen, laufend, fertig = list(kapitel), {}, []
    t0 = time.time()
    print(f"[parallel] {book} [{lg}]: {len(kapitel)} Kapitel, {jobs} gleichzeitig", flush=True)
    while offen or laufend:
        while offen and len(laufend) < jobs:
            k = offen.pop(0)
            log = open(os.path.join(logdir, f"{lg}_{k}.log"), "w", encoding="utf-8")
            p = subprocess.Popen([sys.executable, "-m", "pipeline.s500_vertonung_gemini", book, "--lang", lg,
                                  "--chapter", k] + (["--voice", stimme_kap[k]] if k in stimme_kap else []), cwd=HIER, env=env, stdout=log, stderr=subprocess.STDOUT)
            laufend[k] = (p, log, time.time())
            print(f"  start {k}", flush=True)
        time.sleep(5)
        for k in list(laufend):
            p, log, ts = laufend[k]
            if p.poll() is not None:
                log.close()
                fertig.append((k, p.returncode, time.time() - ts))
                del laufend[k]
                print(f"  fertig {k} (rc {p.returncode}, {(time.time() - ts) / 60:.1f} min) | "
                      f"{len(fertig)}/{len(kapitel)} | gesamt {(time.time() - t0) / 60:.1f} min", flush=True)
    fehler = [k for k, rc, _ in fertig if rc != 0]
    print(f"[parallel] {book} [{lg}] fertig in {(time.time() - t0) / 60:.1f} min | Fehler: {fehler or 'keine'}", flush=True)
    sys.exit(1 if fehler else 0)


if __name__ == "__main__":
    main()
