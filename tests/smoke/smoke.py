"""Smoke-Test-Helfer (E7, 24.10.2026). Nur Pruef-/Mess-Code, aendert keine Stage.
  py -3.11 tests\\smoke\\smoke.py schritt <name> -- <befehl ...>   Befehl ausfuehren, Dauer/Status protokollieren
  py -3.11 tests\\smoke\\smoke.py setup <werk>                     book.json: eigene Rechte, Casting an, DE-Titel
  py -3.11 tests\\smoke\\smoke.py linie <werk> <run.py-Argumente>  run.py mit Exit-Code != 0 bei Fehler
  py -3.11 tests\\smoke\\smoke.py tor_test <werk>                  QF-4: offenes Tor muss 500 stoppen
  py -3.11 tests\\smoke\\smoke.py tor_frei <werk>                  Exit 0 nur bei tor == freigegeben
  py -3.11 tests\\smoke\\smoke.py bericht <werk>                   cockpit\\logs\\smoke_test_bericht.txt
"""
import glob, io, json, os, shutil, subprocess, sys, time, contextlib

LESER = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, LESER)
os.chdir(LESER)
LOGS = os.path.join(LESER, "cockpit", "logs")
ZEITEN = os.path.join(LOGS, "smoke_test_zeiten.jsonl")
BERICHT = os.path.join(LOGS, "smoke_test_bericht.txt")
EPUB_IN = os.path.join(LESER, "tests", "smoke", "spiegelschwestern.epub")
SOLL_FIGUREN = {"imogen": "Imogen", "ros": "Rosalind (Ros)", "ashworth": "Mr. Ashworth"}


def _cfg():
    from config import config
    return config


def schritt(name, befehl):
    os.makedirs(LOGS, exist_ok=True)
    t0 = time.time()
    print(f"=== SCHRITT {name}: {' '.join(befehl)}", flush=True)
    rc = subprocess.call(befehl, shell=False)
    dauer = round(time.time() - t0, 1)
    with open(ZEITEN, "a", encoding="utf-8") as f:
        f.write(json.dumps({"schritt": name, "rc": rc, "sek": dauer,
                            "ende": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
    print(f"=== SCHRITT {name}: {'ok' if rc == 0 else 'FEHLER rc=' + str(rc)} ({dauer}s)", flush=True)
    return rc


def setup(werk):
    cfg = _cfg()
    p = os.path.join(cfg.book_dir(werk), "book.json")
    b = json.load(open(p, encoding="utf-8"))
    b["rechte"] = "eigene"
    b["besetzung_modus"] = "ensemble"
    b["smoke_test"] = True
    fs = [f for f in b.get("fassungen", []) if f.get("sprache") != "de"]
    fs.append({"sprache": "de", "titel": "Die Spiegelschwestern", "titel_quelle": "smoke_test", "titel_pruefen": False})
    b["fassungen"] = fs
    tmp = p + ".tmp"
    json.dump(b, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    os.replace(tmp, p)
    print(f"[smoke] setup {werk}: rechte=eigene, besetzung_modus=ensemble, DE-Titel gesetzt")
    return 0


def linie(werk, args):
    import run
    def opt(n):
        return args[args.index(n) + 1] if n in args else None
    if "--live" in args:
        _cfg().RUN_MODE = "live"
    ok = run.run_pipeline(werk, line=opt("--line") or "epub", start_from=opt("--from"), stop_to=opt("--to"),
                          only=opt("--only"), force="--force" in args, only_lang=opt("--lang"))
    return 0 if ok else 1


def _tor(werk):
    from pipeline import s410_casting
    p = s410_casting.casting_pfad(werk)
    return json.load(open(p, encoding="utf-8")).get("tor") if os.path.exists(p) else "fehlt"


def _wavs(werk, lg):
    return glob.glob(os.path.join(_cfg().book_dir(werk), "fassungen", lg, "audio", "*.wav"))


def tor_test(werk):
    tor = _tor(werk)
    if tor == "freigegeben":
        print("[smoke] QF-4 nicht pruefbar: Tor ist schon freigegeben"); return 1
    vorher = len(_wavs(werk, "de")) + len(_wavs(werk, "en"))
    import run
    puffer = io.StringIO()
    with contextlib.redirect_stdout(puffer):
        ok = run.run_pipeline(werk, line="audio", start_from="500", only="500")
    aus = puffer.getvalue()
    print(aus)
    nachher = len(_wavs(werk, "de")) + len(_wavs(werk, "en"))
    gestoppt = (not ok) and "[STOPP]" in aus and nachher == vorher
    print(f"[smoke] QF-4 Casting-Tor '{tor}': 500 {'GESTOPPT (ok)' if gestoppt else 'NICHT gestoppt (FEHLER)'}")
    return 0 if gestoppt else 1


def tor_frei(werk):
    t = _tor(werk)
    print(f"[smoke] Casting-Tor: {t}")
    return 0 if t == "freigegeben" else 1


# ---------------- Bericht ----------------
def _epubcheck(pfad):
    if not pfad or not os.path.exists(pfad):
        return False, "Datei fehlt"
    kandidaten = []
    if shutil.which("epubcheck"):
        kandidaten.append(["epubcheck", pfad])
    for jar in glob.glob(os.path.join(LESER, "tools", "epubcheck*", "epubcheck.jar")):
        if shutil.which("java"):
            kandidaten.append(["java", "-jar", jar, pfad])
    if not kandidaten:
        return False, "epubcheck nicht installiert (weder PATH noch tools\\epubcheck*\\epubcheck.jar + java)"
    r = subprocess.run(kandidaten[0], capture_output=True, text=True, encoding="utf-8", errors="replace")
    zeilen = [z for z in (r.stdout + r.stderr).splitlines() if z.startswith(("ERROR", "FATAL"))]
    return r.returncode == 0, ("keine Fehler" if r.returncode == 0 else f"{len(zeilen)} Fehler: " + " | ".join(zeilen[:3]))


def _laden(p, default=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default


def bericht(werk):
    cfg = _cfg()
    bd = cfg.book_dir(werk)
    wd = os.path.join(bd, "work")
    L, fehler = [], []
    L.append(f"READ LAYER - Smoke-Test-Bericht  {time.strftime('%Y-%m-%d %H:%M')}")
    L.append(f"Werk: {werk}  (The Mirror Sisters / Die Spiegelschwestern)")
    L.append("")
    # 1 Stages
    L.append("1. STAGES (ok/Fehler, Dauer)")
    schritte = [json.loads(z) for z in open(ZEITEN, encoding="utf-8")] if os.path.exists(ZEITEN) else []
    gesamt = 0.0
    for s in schritte:
        gesamt += s["sek"]
        L.append(f"   {s['schritt']:<28} {'ok    ' if s['rc'] == 0 else 'FEHLER'}  {s['sek']:>8.1f} s")
        if s["rc"] != 0:
            fehler.append(f"Schritt {s['schritt']} rc={s['rc']}")
    L.append(f"   {'GESAMT':<28}         {gesamt:>8.1f} s ({gesamt/60:.1f} min)")
    L.append("")
    # 2 Kosten
    L.append("2. KOSTEN (work\\kosten.jsonl)")
    text_usd, modal_usd, je = 0.0, 0.0, {}
    kp = os.path.join(wd, "kosten.jsonl")
    if os.path.exists(kp):
        for z in open(kp, encoding="utf-8"):
            try:
                k = json.loads(z)
            except ValueError:
                continue
            usd = float(k.get("usd") or 0)
            ist_modal = "modal" in str(k.get("modell", "")).lower() or str(k.get("quelle", "")).lower() == "modal"
            if ist_modal:
                modal_usd += usd
            else:
                text_usd += usd
                je[str(k.get("stage"))] = je.get(str(k.get("stage")), 0) + usd
    for st in sorted(je):
        L.append(f"   Stage {st:<10} {je[st]:.4f} $")
    L.append(f"   Text/API gesamt: {text_usd:.4f} $  (Ziel < 0,10 $) -> {'ok' if text_usd < 0.10 else 'UEBER ZIEL'}")
    L.append(f"   Modal (GPU):     {('%.4f $' % modal_usd) if modal_usd else 'nicht in kosten.jsonl erfasst'}")
    if text_usd >= 0.10:
        fehler.append(f"Textkosten {text_usd:.4f} $ >= 0,10 $")
    if not modal_usd:
        fehler.append("Modal-Kosten nicht in kosten.jsonl (Stufe 4 Nr. 9 offen)")
    L.append("")
    # 3 Saetze / WAV / Wortzeiten
    L.append("3. SAETZE, WAV, WORTZEITEN")
    regie = _laden(os.path.join(wd, "400_regie.json"), {}) or {}
    inhalt = regie.get("content", {}) if isinstance(regie, dict) else {}
    ids = {lg: {t for t, e in inhalt.items() if isinstance(e, dict) and str(e.get(lg, "")).strip()} for lg in ("en", "de")}
    L.append(f"   Saetze EN {len(ids['en'])} / DE {len(ids['de'])} -> {'gleich' if ids['en'] == ids['de'] and ids['en'] else 'UNGLEICH'}")
    if not ids["en"] or ids["en"] != ids["de"]:
        fehler.append(f"Satzanzahl EN {len(ids['en'])} != DE {len(ids['de'])} (oder leer)")
    for lg in ("en", "de"):
        wav = {os.path.splitext(os.path.basename(w))[0] for w in _wavs(werk, lg)}
        wz = (_laden(os.path.join(wd, f"520_wortzeiten_{lg}.json"), {}) or {}).get("tags", {})
        sprechbar = {t for t in ids[lg] if inhalt[t].get("type") not in ("hr", "img")}
        ohne_wav = sorted(sprechbar - wav)
        ohne_wz = sorted(sprechbar - set(wz))
        L.append(f"   {lg.upper()}: {len(wav)} WAV, {len(wz)} mit Wortzeiten | ohne WAV {len(ohne_wav)}, ohne Wortzeiten {len(ohne_wz)}"
                 + (f"  z.B. {ohne_wav[:3] or ohne_wz[:3]}" if ohne_wav or ohne_wz else ""))
        if ohne_wav or ohne_wz:
            fehler.append(f"{lg.upper()}: {len(ohne_wav)} Saetze ohne WAV, {len(ohne_wz)} ohne Wortzeiten")
    L.append("")
    # 4 epubcheck
    L.append("4. EPUBCHECK")
    ok_in, txt_in = _epubcheck(EPUB_IN)
    L.append(f"   Eingang spiegelschwestern.epub: {txt_in}")
    for lg in ("en", "de"):
        kand = glob.glob(os.path.join(bd, "fassungen", lg, "output", "*.epub"))
        ok, txt = _epubcheck(kand[0] if kand else None)
        L.append(f"   Ausgabe {lg.upper()}: {os.path.basename(kand[0]) if kand else '-'}: {txt}")
        if not ok:
            fehler.append(f"epubcheck {lg.upper()}: {txt}")
    L.append("")
    # 5 Sprecher
    L.append("5. SPRECHERZUORDNUNG")
    cast = _laden(os.path.join(wd, "casting.json"), {}) or {}
    namen = [f.get("name", "") for f in (cast.get("steckbriefe") or {}).get("figuren", [])]
    sp = _laden(os.path.join(wd, "sprecher.json"), {}) or {}
    sprecher = {x.get("s", "") for e in sp.values() if isinstance(e, dict) for x in e.get("en", [])}
    alle = " | ".join(namen + sorted(sprecher)).lower()
    L.append(f"   Casting-Figuren: {', '.join(namen) or '-'}")
    L.append(f"   Sprecher in sprecher.json: {', '.join(sorted(sprecher)) or '-'}")
    for key, label in SOLL_FIGUREN.items():
        da = key in alle or (key == "ros" and "rosalind" in alle)
        L.append(f"   {label:<16} {'erkannt' if da else 'FEHLT'}")
        if not da:
            fehler.append(f"Figur {label} nicht erkannt")
    L.append(f"   Casting-Tor: {cast.get('tor', '-')}")
    L.append("")
    if os.environ.get("READLAYER_WEITER") == "1":
        L.append("HINWEIS: Pruefstopp-Override READLAYER_WEITER=1 war aktiv (tests\\smoke\\override_weiter.txt)")
        fehler.append("Lauf nur mit Override der Pruefstopps 320/330 durchgekommen")
    L.append(f"ERGEBNIS: {'BESTANDEN' if not fehler else str(len(fehler)) + ' FEHLER'}")
    for f in fehler:
        L.append(f"   - {f}")
    os.makedirs(LOGS, exist_ok=True)
    open(BERICHT, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))
    return 0 if not fehler else 1


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(2)
    if a[0] == "schritt":
        sys.exit(schritt(a[1], a[a.index("--") + 1:]))
    fn = {"setup": setup, "tor_test": tor_test, "tor_frei": tor_frei, "bericht": bericht}.get(a[0])
    if a[0] == "linie":
        sys.exit(linie(a[1], a[2:]))
    if not fn:
        print(__doc__); sys.exit(2)
    sys.exit(fn(a[1]))
