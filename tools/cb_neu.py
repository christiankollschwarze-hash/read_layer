"""READ LAYER — Saetze mit Chatterbox NEU vertonen (satzweise, 17.10.2026).

  python tools/cb_neu.py <werk> <lg> liste [Quellen] [--probe N]   Auswahl + Paket gpu_tts/<werk>_<lg>_neu (kostet nichts)
  python tools/cb_neu.py <werk> <lg> einspielen [--tempo 0.91]     nach dem Modal-Lauf: Tempo, alte WAVs sichern, einsetzen
  python tools/cb_neu.py <werk> <lg> abschluss                     nach 58c: Satzpruefung der neuen Saetze + Mock-up-Export
Quellen (kombinierbar):
  --pruefung   work/satzpruefung_<lg>.json "neu" (tools/satzpruefung.py)
  --nachklang  work/nachklang_klassen_<lg>.json "neu" (Altbestand Peter Pan)
  --lexikon    alle Saetze, deren TTS-Text das Aussprache-Lexikon aendert (mit --probe auch unfreigegeben)
  --kuration   offene CK-Anmerkungen (work/kuration.jsonl, Kategorien audio/wortzeit/aussprache)
  --tags a,b   einzelne Saetze
  --ueberschriften  alle Ueberschriften (type h)
--probe N: nur N Saetze, Ergebnis nach work/_cb_probe/<lg>/ (alt + neu nebeneinander), Werk bleibt unveraendert.
Ablauf komplett: start_cb_neu.bat <werk> <lg> [liste|probe|los] [Quellen]
"""
import datetime, json, os, shutil, subprocess, sys

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HIER)
sys.path.insert(0, os.path.join(HIER, "tools"))
from config import config
import tts_paket

HEUTE = datetime.date.today().strftime("%Y%m%d")


def opt(name, d=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else d


def paket_dir(werk, lg):
    return os.path.join(HIER, "gpu_tts", f"{werk}_{lg}_neu")


def auswahl(werk, lg):
    wd = config.work_dir(werk)
    tags, gruende = [], {}

    def add(t, g):
        if t not in gruende:
            tags.append(t)
        gruende.setdefault(t, []).append(g)

    if "--pruefung" in sys.argv:
        p = os.path.join(wd, f"satzpruefung_{lg}.json")
        for t in (json.load(open(p)) if os.path.exists(p) else {}).get("neu", []):
            add(t, "pruefung")
    if "--nachklang" in sys.argv:
        p = os.path.join(wd, f"nachklang_klassen_{lg}.json")
        for t in (json.load(open(p)) if os.path.exists(p) else {}).get("neu", []):
            add(t, "nachklang")
    if "--kuration" in sys.argv:
        p = os.path.join(wd, "kuration.jsonl")
        if os.path.exists(p):
            for z in open(p, encoding="utf-8"):
                try:
                    e = json.loads(z)
                except Exception:
                    continue
                if e.get("status", "offen") == "offen" and e.get("kategorie") in ("audio", "wortzeit", "aussprache") \
                        and (e.get("lang") or e.get("sprache") or lg) == lg and e.get("tag_id"):
                    add(e["tag_id"], "kuration")
    if "--tags" in sys.argv:
        for t in opt("--tags").split(","):
            add(t.strip(), "tags")
    if "--ueberschriften" in sys.argv:     # 18.10.2026: alle Ueberschriften (z. B. nach neuer Sprechtext-Regel)
        d = json.load(open(config.work_path(werk, "400_regie"), encoding="utf-8"))["content"]
        for t, e in d.items():
            if e.get("type") == "h" and (e.get(lg) or "").strip():
                add(t, "ueberschrift")
    if "--lexikon" in sys.argv:
        ers = tts_paket.lexikon(config.book_dir(werk), lg, erzwingen=True)
        d = json.load(open(config.work_path(werk, "400_regie"), encoding="utf-8"))["content"]
        for t, e in d.items():
            txt = (e.get(lg) or "").strip()
            if e.get("type") in tts_paket.TYPEN and txt and tts_paket.lex_text(txt, ers) != txt:
                add(t, "lexikon")
    return tags, gruende


def namensprobe(werk, lg, kandidaten, n):
    ers = tts_paket.lexikon(config.book_dir(werk), lg, erzwingen=True)
    d = json.load(open(config.work_path(werk, "400_regie"), encoding="utf-8"))["content"]
    import re
    def namen(t):
        txt, gef = d[t][lg], set()
        for k in sorted(ers, key=len, reverse=True):
            if re.search(r"(?<![\w])" + re.escape(k) + r"(?![\w])", txt):
                gef.add(k)
                txt = txt.replace(k, " ")
        return gef
    nm = {t: namen(t) for t in kandidaten}
    offen, wahl = set().union(*nm.values()) if nm else set(), []
    while offen and len(wahl) < n:
        t = max(nm, key=lambda x: (len(nm[x] & offen), -len(d[x][lg])))
        if not nm[t] & offen:
            break
        wahl.append(t)
        offen -= nm[t]
    print(f"[cb_neu] Namensprobe: {len(ers) - len(offen)}/{len(ers)} Eintraege in {len(wahl)} Saetzen"
          + (f", nicht im Text: {sorted(offen)}" if offen else ""))
    return wahl


def liste(werk, lg):
    probe = int(opt("--probe", 0) or 0)
    if "--lexikon" in sys.argv and not probe and not tts_paket.lexikon(config.book_dir(werk), lg):
        sys.exit("[cb_neu] Aussprache-Lexikon nicht freigegeben - erst Probe anhoeren, dann \"freigegeben\": true setzen")
    tags, gruende = auswahl(werk, lg)
    if probe:
        # Probe: gemischt aus allen Gruenden
        nach = {}
        for t in tags:
            nach.setdefault(gruende[t][0], []).append(t)
        gemischt = []
        while len(gemischt) < probe and any(nach.values()):
            for g in list(nach):
                if nach[g] and len(gemischt) < probe:
                    gemischt.append(nach[g].pop(0))
        tags = gemischt
        if "--lexikon" in sys.argv:           # Namensprobe (18.10.2026): jeder Lexikon-Eintrag mind. einmal, kurze Saetze zuerst
            tags = namensprobe(werk, lg, [t for t in auswahl(werk, lg)[0] if "lexikon" in gruende[t]], probe) or tags
    if not tags:
        sys.exit("[cb_neu] keine Saetze ausgewaehlt (Quelle angeben: --pruefung --nachklang --lexikon --kuration --tags)")
    _, jobs = tts_paket.jobs_bauen(werk, lg, tags=set(tags), mit_prosodie="--prosodie" in sys.argv,
                                   lex_erzwingen=bool(probe))
    for j in jobs:
        j["kap"] = "neu"          # ein GPU-Container fuer alle (Modell nur einmal laden)
    haupt = os.path.join(HIER, "gpu_tts", f"{werk}_{lg}")
    alt = json.load(open(os.path.join(haupt, "jobs.json"), encoding="utf-8"))
    ziel = f"work/_cb_probe/{lg}/neu" if probe else f"fassungen/{lg}/audio_neu_{HEUTE}"
    shutil.rmtree(paket_dir(werk, lg), ignore_errors=True)
    tts_paket.schreiben(werk, lg, jobs, ref=alt.get("ref"), ref_wav=os.path.join(haupt, "ref.wav")
                        if os.path.exists(os.path.join(haupt, "ref.wav")) else None,
                        name=f"{werk}_{lg}_neu", extra={"ziel": ziel, "gruende": gruende, "probe": bool(probe),
                                                        **tts_paket.lora_extra(config.book_dir(werk), opt("--lora"), lg)})
    werkdir = config.book_dir(werk)
    if probe:
        a = os.path.join(werkdir, "work", "_cb_probe", lg, "alt")
        shutil.rmtree(os.path.join(werkdir, "work", "_cb_probe", lg), ignore_errors=True)
        os.makedirs(a, exist_ok=True)
        for t in tags:
            q = os.path.join(werkdir, "fassungen", lg, "audio", f"{t}.wav")
            if os.path.exists(q):
                shutil.copy2(q, a)
    zaehl = {}
    for t in tags:
        for g in gruende[t]:
            zaehl[g] = zaehl.get(g, 0) + 1
    print(f"[cb_neu] {werk} {lg}: {len(tags)} Saetze {zaehl}" + (" (PROBE)" if probe else ""))


def atempo(q, z, f):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", q, "-af", f"atempo={f}",
                    "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", z], check=True)


def einspielen(werk, lg):
    d = json.load(open(os.path.join(paket_dir(werk, lg), "jobs.json"), encoding="utf-8"))
    werkdir = config.book_dir(werk)
    quelle = os.path.join(werkdir, d["ziel"])
    f = opt("--tempo", d.get("tempo", "0.91"))       # LoRA: eigenes Tempo (tts_paket.LORA)
    neu = sorted(x for x in os.listdir(quelle) if x.endswith(".wav")) if os.path.isdir(quelle) else []
    if not neu:
        sys.exit(f"[cb_neu] keine neuen WAVs in {quelle}")
    if d.get("probe"):
        for x in neu:
            p = os.path.join(quelle, x)
            atempo(p, p + ".tmp.wav", f)
            os.replace(p + ".tmp.wav", p)
        print(f"[cb_neu] Probe fertig: {len(neu)} Saetze, Tempo {f} -> {quelle} (alt: {os.path.dirname(quelle)}\\alt)")
        return
    audio = os.path.join(werkdir, "fassungen", lg, "audio")
    roh = os.path.join(werkdir, "fassungen", lg, "audio_chatterbox_roh")
    bak = os.path.join(werkdir, "fassungen", lg, f"audio_alt_{HEUTE}")
    os.makedirs(bak, exist_ok=True)
    os.makedirs(roh, exist_ok=True)
    for x in neu:
        if os.path.exists(os.path.join(audio, x)) and not os.path.exists(os.path.join(bak, x)):
            shutil.copy2(os.path.join(audio, x), bak)
        shutil.copy2(os.path.join(quelle, x), os.path.join(roh, x))          # Rohfassung fuer spaeteres Neu-Tempo
        atempo(os.path.join(quelle, x), os.path.join(audio, x + ".tmp.wav"), f)
        os.replace(os.path.join(audio, x + ".tmp.wav"), os.path.join(audio, x))
    # Wortzeiten der neuen Saetze verwerfen -> fa_modal misst nur diese neu
    wp = os.path.join(config.work_dir(werk), f"520_wortzeiten_{lg}.json")
    wt = json.load(open(wp, encoding="utf-8"))
    shutil.copy2(wp, wp + f".bak_{HEUTE}_cbneu")
    for x in neu:
        wt["tags"].pop(x[:-4], None)
    json.dump(wt, open(wp, "w", encoding="utf-8"), ensure_ascii=False)
    prot = {"datum": HEUTE, "tempo": f, "tags": [x[:-4] for x in neu], "gruende": d.get("gruende", {})}
    json.dump(prot, open(os.path.join(config.work_dir(werk), f"neuvertonung_cb_{lg}.json"), "w", encoding="utf-8"), indent=1)
    print(f"[cb_neu] {len(neu)} Saetze eingespielt (alt -> {bak}), Wortzeiten verworfen -> jetzt fa_modal")


def abschluss(werk, lg):
    import satzpruefung
    prot = json.load(open(os.path.join(config.work_dir(werk), f"neuvertonung_cb_{lg}.json"), encoding="utf-8"))
    erg = satzpruefung.main(werk, lg, schneiden=True, nur=set(prot["tags"]))
    # CK-Anmerkungen als erledigt markieren
    kp = os.path.join(config.work_dir(werk), "kuration.jsonl")
    if os.path.exists(kp):
        zeilen = []
        for z in open(kp, encoding="utf-8"):
            try:
                e = json.loads(z)
                if e.get("tag_id") in prot["tags"] and e.get("status", "offen") == "offen":
                    e["status"] = f"neu vertont {prot['datum']}"
                zeilen.append(json.dumps(e, ensure_ascii=False))
            except Exception:
                zeilen.append(z.rstrip("\n"))
        open(kp, "w", encoding="utf-8").write("\n".join(zeilen) + "\n")
    book = json.load(open(os.path.join(config.book_dir(werk), "book.json"), encoding="utf-8"))
    app = os.path.join(os.path.dirname(HIER), "taella-app", "public")
    demo = os.path.join(app, "privat", book["owner_uid"]) if book.get("owner_uid") else os.path.join(app, "demo")
    if os.path.isdir(os.path.join(demo, werk)):
        subprocess.run([sys.executable, os.path.join(HIER, "tools", "export_demo.py"), werk, demo, "--audio"], check=False)
    print(f"[cb_neu] Abschluss {lg}: {len(prot['tags'])} neu, danach noch auffaellig: {len(erg['neu'])} {erg['neu'][:10]}")


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--") and x != opt("--tags") and x != opt("--probe") and x != opt("--tempo") and x != opt("--lora")]
    werk, lg, modus = a[0], a[1], a[2]
    {"liste": liste, "einspielen": einspielen, "abschluss": abschluss}[modus](werk, lg)
