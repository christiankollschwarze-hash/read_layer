"""READ LAYER - Betroffene Saetze neu vertonen (Sprachkipper), mit Aussprache-Lexikon und deutscher Regie.

Aufruf:
  py -3.11 tools/neu_vertonen.py <werk> <lg> --liste           nur zeigen, welche Saetze neu kaemen (kostet nichts)
  py -3.11 tools/neu_vertonen.py <werk> <lg> --probe [12]      Hoerprobe: N Saetze neu -> work/_neuvertonung/probe/ (alt + neu)
  py -3.11 tools/neu_vertonen.py <werk> <lg> --los             alle ausgewaehlten Saetze neu (fassungen/<lg>/audio)
  ... --los --tags a,b,c       nur diese Saetze (z. B. nach Sprecher-Korrektur in sprecher.json)
  ... --los --stage560        Stage 560 (AP 57): Auswahl aus work/560_auswahl_<lg>.json, Lexikon nur wenn freigegeben
  ... --los --nur-whisper     Nachrunde: nur Saetze, die Whisper nach der Neuvertonung noch als gekippt hoert (p < 0,5)
  (Windows: start_neu_vertonen.bat <werk> [lg] [probe|los])

Auswahl (work/sprachpruefung_<lg>.json): Saetze, deren Text durch das Lexikon veraendert wird, + Whisper p(Ziel) < 0,5
+ CK-Urteil "kippt"; CK-Urteil "ok" bleibt immer unangetastet.
Vertonung je Segment wie tools/hoerprobe_mehrstimmig.py (sprecher.json + casting.json: Figur -> Stimme), aber:
  - Text: Namen per Lexikon (work/aussprache_<lg>.json) in Lautschreibung - nur fuer die Vertonung
  - Regie: "This is a German sentence ..." (zusaetzlich zu config.TTS_SPRACH_STIL), KEIN "pronounced as in English" mehr
--los sichert jedes alte WAV nach fassungen/<lg>/audio_alt_<datum>/, nimmt die Saetze aus den Wortzeiten (58c misst sie neu)
und schreibt work/neuvertonung_<lg>.json. Danach: Stage 58c (Wortzeiten) + start_sprachpruefung.bat (prueft nur die neuen).
"""
import concurrent.futures as cf
import datetime
import json
import os
import re
import shutil
import sys
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from config import config  # noqa: E402

RATE = 24000
LANG = {"en": "en-GB", "de": "de-DE"}
PAUSE_SEG = 0.25
NUR_WHISPER = "--nur-whisper" in sys.argv
STAGE560 = "--stage560" in sys.argv   # AP 57: Auswahl aus work/560_auswahl_<lg>.json, Lexikon nur wenn freigegeben
def _tags_lesen():
    """--tags a,b,c oder --tags a b c (Windows-Batch trennt Kommas in Argumente auf)."""
    if "--tags" not in sys.argv:
        return []
    out = []
    for x in sys.argv[sys.argv.index("--tags") + 1:]:
        if x.startswith("--"):
            break
        out += [t for t in x.replace(";", ",").split(",") if t.strip()]
    return out


TAGS = _tags_lesen()   # --tags c001_00002_s,...   # Nachrunde: nur Saetze, die Whisper (noch) als gekippt hoert
STIL = {"de": "This is a German sentence. Read every word with natural German pronunciation and German sentence melody, "
              "names included; never switch to English or French.",
        "en": "This is an English sentence. Read every word with natural English pronunciation."}


def lexikon(book_id, lg):
    p = os.path.join(config.work_dir(book_id), f"aussprache_{lg}.json")
    if not os.path.exists(p):
        return {}, False
    d = json.load(open(p, encoding="utf-8"))
    return d.get("ersatz", {}), bool(d.get("freigegeben"))


def anwenden(text, lex):
    """Ganze Woerter/Wortfolgen ersetzen, laengste zuerst. Gross/klein exakt (Namen)."""
    for k in sorted(lex, key=len, reverse=True):
        if not lex[k] or lex[k] == k:
            continue
        text = re.sub(r"(?<![\w])" + re.escape(k) + r"(?![\w])", lex[k], text)
    return text


def auswahl(book_id, lg, lex):
    wd = config.work_dir(book_id)
    sp = json.load(open(os.path.join(wd, f"sprachpruefung_{lg}.json"), encoding="utf-8"))
    S, U = sp["saetze"], sp.get("urteile", {})
    data = json.load(open(config.work_path(book_id, "400_regie"), encoding="utf-8"))["content"]
    out = {}
    if STAGE560:
        aw = json.load(open(os.path.join(wd, f"560_auswahl_{lg}.json"), encoding="utf-8"))
        return {t: {"gruende": ["s560"], "verdacht": S.get(t, {}).get("verdacht", 0),
                    "text": (data.get(t, {}).get(lg) or "").strip()}
                for t in aw["tags"] if (data.get(t, {}).get(lg) or "").strip()}
    if TAGS:   # feste Auswahl (z. B. nach Sprecher-Korrektur), unabhaengig von Pruefung und CK-Urteil
        return {t: {"gruende": ["manuell"], "verdacht": 1.0, "text": (data.get(t, {}).get(lg) or "").strip()}
                for t in TAGS if (data.get(t, {}).get(lg) or "").strip()}
    for t, s in S.items():
        if U.get(t) == "ok":
            continue
        txt = (data.get(t, {}).get(lg) or "").strip()
        gruende = []
        if txt and anwenden(txt, lex) != txt:
            gruende.append("lexikon")
        if s.get("p_ziel", 1) < 0.5:
            gruende.append("whisper")
        if U.get(t) == "kippt":
            gruende.append("ck")
        if NUR_WHISPER and "whisper" not in gruende:
            continue
        if gruende:
            out[t] = {"gruende": gruende, "verdacht": s.get("verdacht", 0), "text": txt}
    return out


def stimmen(book_id):
    wd = config.work_dir(book_id)
    cast = json.load(open(os.path.join(wd, "casting.json"), encoding="utf-8"))["plan"]
    v = {"Erzaehler": cast["erzaehler"]["id"]}
    for e in cast["ensemble"]:
        if e.get("id"):
            v[e["figur"]] = e["id"]
    spr = {}
    p = os.path.join(wd, "sprecher.json")
    if os.path.exists(p):
        spr = json.load(open(p, encoding="utf-8"))
    return v, spr


def vertone_satz(tid, text, lg, v, spr, lex, ziel):
    """Ein Satz = Segmente (Figurenwechsel) -> eine WAV; Pausen wie hoerprobe_mehrstimmig."""
    from pipeline import tts_client
    segs = (spr.get(tid) or {}).get(lg) or [{"t": text, "s": "Erzaehler"}]
    teile = []
    for s in segs:
        t = s["t"].strip()
        if not t:
            continue
        stimme = v.get(s["s"], v["Erzaehler"])
        pcm = tts_client.synthesize_bytes(anwenden(t, lex), STIL.get(lg, ""), stimme, LANG[lg], fmt="l16")
        if pcm[:4] == b"RIFF":
            pcm = pcm[pcm.find(b"data") + 8:]
        teile.append(pcm)
    if not teile:
        raise RuntimeError("leer")
    tmp = ziel + ".tmp"
    with wave.open(tmp, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        for i, pcm in enumerate(teile):
            w.writeframes(pcm)
            if i < len(teile) - 1:
                w.writeframes(b"\x00\x00" * int(RATE * PAUSE_SEG))
    os.replace(tmp, ziel)


def main(book_id, lg, modus, n_probe=12):
    lex, frei = lexikon(book_id, lg)
    A = auswahl(book_id, lg, lex)
    gr = {}
    for a in A.values():
        for g in a["gruende"]:
            gr[g] = gr.get(g, 0) + 1
    print(f"[neu] {book_id} [{lg}]: {len(A)} Saetze ausgewaehlt ({', '.join(f'{k} {v}' for k, v in gr.items())}); "
          f"Lexikon {len(lex)} Eintraege{'' if frei else ' (NICHT freigegeben)'}")
    if modus == "liste":
        for t, a in sorted(A.items(), key=lambda kv: -kv[1]["verdacht"])[:40]:
            print(f"  {t:16} {'+'.join(a['gruende']):22} {anwenden(a['text'], lex)[:90]}")
        return
    if STAGE560 and not frei:
        lex = {}   # AP 57: unfreigegebenes Lexikon nicht anwenden, Stage laeuft trotzdem (deutsche Regie)
    elif modus == "los" and not frei:
        sys.exit("Lexikon nicht freigegeben (work/aussprache_%s.json: \"freigegeben\": true) - erst Hoerprobe anhoeren." % lg)
    v, spr = stimmen(book_id)
    adir = os.path.join(config.book_dir(book_id), "fassungen", lg, "audio")
    if modus == "probe":
        pd = os.path.join(config.work_dir(book_id), "_neuvertonung", "probe")
        os.makedirs(pd, exist_ok=True)
        # Probe: verdaechtigste Saetze mit Lexikon-Namen, gemischt mit reinen Whisper-/CK-Faellen
        rang = sorted(A.items(), key=lambda kv: -kv[1]["verdacht"])
        mit = [x for x in rang if "lexikon" in x[1]["gruende"]][:n_probe * 2 // 3]
        ohne = [x for x in rang if "lexikon" not in x[1]["gruende"]][:n_probe - len(mit)]
        jobs = [(t, a, os.path.join(pd, f"{t}.wav")) for t, a in mit + ohne]
        for t, a, z in jobs:
            q = os.path.join(adir, f"{t}.wav")
            if os.path.exists(q):
                shutil.copy2(q, os.path.join(pd, f"{t}_alt.wav"))
    else:
        heute = datetime.date.today().strftime("%Y%m%d")
        sich = os.path.join(config.book_dir(book_id), "fassungen", lg, f"audio_alt_{heute}")
        os.makedirs(sich, exist_ok=True)
        jobs = []
        for t, a in A.items():
            q = os.path.join(adir, f"{t}.wav")
            if os.path.exists(q) and not os.path.exists(os.path.join(sich, f"{t}.wav")):
                shutil.copy2(q, os.path.join(sich, f"{t}.wav"))
            jobs.append((t, a, q))
    fehler, fertig = [], []
    with cf.ThreadPoolExecutor(max_workers=getattr(config, "TTS_PARALLEL", 8)) as ex:
        futs = {ex.submit(vertone_satz, t, a["text"], lg, v, spr, lex, z): t for t, a, z in jobs}
        for i, f in enumerate(cf.as_completed(futs), 1):
            t = futs[f]
            try:
                f.result(); fertig.append(t)
            except Exception as e:
                fehler.append(t); print(f"  Fehler {t}: {str(e)[:150]}")
            if i % 50 == 0:
                print(f"  {i}/{len(jobs)}")
    print(f"[neu] {len(fertig)} neu vertont, {len(fehler)} Fehler")
    if modus == "probe":
        L = ["# Hoerprobe Neuvertonung " + book_id, "", "| Satz | Grund | Text (TTS) |", "|---|---|---|"]
        L += [f"| {t} | {'+'.join(a['gruende'])} | {anwenden(a['text'], lex)} |" for t, a, _ in jobs]
        open(os.path.join(pd, "liste.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
        print(f"  -> {pd} (je Satz <tag>_alt.wav und <tag>.wav, liste.md)")
        return
    # Wortzeiten der neuen Saetze verwerfen -> Stage 58c misst sie beim naechsten Lauf neu
    wp = config.work_path(book_id, f"520_wortzeiten_{lg}")
    if os.path.exists(wp) and fertig:
        shutil.copy2(wp, wp + f".bak_neuvertonung_{heute}")
        w = json.load(open(wp, encoding="utf-8"))
        for t in fertig:
            w.get("tags", {}).pop(t, None)
        json.dump(w, open(wp, "w", encoding="utf-8"), ensure_ascii=False)
    pp = os.path.join(config.work_dir(book_id), f"neuvertonung_{lg}.json")
    alt = json.load(open(pp, encoding="utf-8")) if os.path.exists(pp) else {"laeufe": []}
    alt["laeufe"].append({"datum": heute, "saetze": {t: A[t]["gruende"] for t in fertig}, "fehler": fehler,
                          "quelle": "s560" if STAGE560 else "manuell", "modell": config.MODELS.get("tts"),
                          "sicherung": os.path.relpath(sich, config.book_dir(book_id))})
    json.dump(alt, open(pp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"  Sicherung alt: {sich}\n  Weiter: py -3.11 -m pipeline.s520_wortzeiten {book_id} --lang {lg}"
          f"  und  start_sprachpruefung.bat {book_id} {lg}")


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--") and x not in TAGS and "," not in x]
    if len(a) < 2:
        sys.exit(__doc__)
    modus = "los" if "--los" in sys.argv else ("probe" if "--probe" in sys.argv else "liste")
    n = int(a[2]) if modus == "probe" and len(a) > 2 else 12
    main(a[0], a[1], modus, n)
