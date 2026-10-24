"""READ LAYER — Prosodie-Markup v0.1 (Vokabelheft) -> Chatterbox-Segmente + Testpaket (23.10.2026).

Aufruf:
  py -3.11 tools/prosodie_markup.py paket   [--testset docs/prosodie/testset_prosodie_v0.1.md]
      -> gpu_tts/prosodie_test_v01/jobs.json + ref_*.wav (Variante a = ohne Markup, b = mit Markup)
  py -3.11 tools/prosodie_markup.py zeigen "<markup-text>" [de|en]
      -> Segmentliste zum Pruefen (kostet nichts)
  py -3.11 tools/prosodie_markup.py seite
      -> gpu_tts/prosodie_test_v01/hoertest.html (nach dem Modal-Lauf)

Umsetzung nach Vokabelheft v0.1:
  Emoji Stimmung -> exaggeration/cfg_weight/temperature je Chunk; am Absatzanfang (oder direkt nach @Name:) bis zum
  naechsten Sprecher, sonst bis Satzende. Verdopplung = exaggeration +0,2.
  🐢/🐇 (doppelt) -> cfg_weight -0,15/+0,15 (-0,25/+0,25) bis Satzende.
  | || ||| -> 250/600/1200 ms Stille; Standardpausen an Chunkgrenzen: Komma 150, Satzende 400 ms.
  *Wort* -> Fallback: eigener Chunk, exaggeration +0,15.   @Name: -> Referenzstimme.   {Wort|Laut} -> Laut.
  🤫 -> -6 dB;  🤔 -> Pausen +50 %.
"""
import json, os, re, shutil, sys

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAKET = os.path.join(HIER, "gpu_tts", "prosodie_test_v01")
ARCHIV = os.path.join(HIER, "stimmen_archiv")

NEUTRAL = (0.5, 0.5, 0.8)
STIMMUNG = {  # emoji: (exaggeration, cfg_weight, temperature, gain_db, pausenfaktor)
    "😐": (0.5, 0.5, 0.8, 0, 1.0), "🙂": (0.6, 0.5, 0.8, 0, 1.0), "😄": (0.8, 0.45, 0.85, 0, 1.0),
    "😏": (0.7, 0.4, 0.85, 0, 1.0), "🥰": (0.5, 0.35, 0.75, 0, 1.0), "😮": (0.9, 0.5, 0.9, 0, 1.0),
    "😱": (1.1, 0.5, 0.9, 0, 1.0), "😨": (0.8, 0.35, 0.85, 0, 1.0), "😠": (1.0, 0.3, 0.85, 0, 1.0),
    "😢": (0.35, 0.3, 0.75, 0, 1.0), "🤫": (0.3, 0.3, 0.7, -6, 1.0), "🤔": (0.4, 0.3, 0.75, 0, 1.5),
    "🙄": (0.7, 0.4, 0.85, 0, 1.0), "😴": (0.25, 0.25, 0.7, 0, 1.0), "🎭": (0.9, 0.3, 0.85, 0, 1.0),
}
TEMPO = {"🐢": -0.15, "🐇": 0.15}
PAUSE = {1: 250, 2: 600, 3: 1200}
BETONUNG_PLUS = 0.15

# Sprecher -> Archivstimme (Erzaehler = Margaret)
STIMMEN = {
    "de": {"_": "grossmutter_a", "Erzähler": "grossmutter_a", "Anna": "w_jung_mittel_ruhig", "Max": "m_jung_mittel_ruhig"},
    "en": {"_": "grossmutter_a", "Narrator": "grossmutter_a", "Captain": "m_alt_tief_ruhig", "Mate": "m_jung_mittel_ruhig"},
}

EMO = "|".join(re.escape(e) for e in sorted(list(STIMMUNG) + list(TEMPO), key=len, reverse=True))
TOKEN = re.compile(r"(?P<sp>@[^\s:]+:)|(?P<lex>\{[^{}|]+\|[^{}]+\})|(?P<emo>(?:" + EMO + r")+)|(?P<pa>\|{1,3})|(?P<bet>\*[^*]+\*)")
SATZENDE = re.compile(r"(?<=[.!?])[\"']?\s+")


def klartext(markup):
    """Baseline: Markup entfernen, Lexikon-Original behalten, Sprechernamen weg."""
    t = re.sub(r"@[^\s:]+:", " ", markup)
    t = re.sub(r"\{([^{}|]+)\|[^{}]+\}", r"\1", t)
    t = re.sub(r"(?:" + EMO + r")+", " ", t)
    t = t.replace("|", " ").replace("*", "")
    return " ".join(t.split())


def _tempo_delta(e, k):
    return {("🐢", 1): -0.15, ("🐢", 2): -0.25, ("🐇", 1): 0.15, ("🐇", 2): 0.25}[(e, min(k, 2))]


def parse(markup, lang):
    """-> Liste von Segmenten {"t":"tts",text,ex,cfg,temp,stimme,gain_db} | {"t":"pause",ms}."""
    stimmen = STIMMEN[lang]
    zustand = {"stimme": stimmen["_"], "st": None, "n": 0, "st_bis": "satz", "tempo": 0.0}
    segs, puffer = [], []
    absatzanfang = True

    def werte(betont=False):
        st = zustand["st"]
        ex, cfg, temp, gain, pf = STIMMUNG[st] if st else (*NEUTRAL, 0, 1.0)
        if zustand["n"] >= 2:
            ex += 0.2 * (zustand["n"] - 1)
        cfg += zustand["tempo"]
        if betont:
            ex += BETONUNG_PLUS
        return dict(ex=round(min(max(ex, 0.25), 2.0), 3), cfg=round(min(max(cfg, 0.05), 1.0), 3),
                    temp=temp, gain_db=gain, pf=pf, stimme=zustand["stimme"], stimmung=st or "😐")

    def ausgeben(betont=False):
        """Puffer als Chunk(s) ausgeben; Satzende beendet satzweite Stimmung/Tempo."""
        text = "".join(puffer).strip()
        puffer.clear()
        while text:
            teile = SATZENDE.split(text, maxsplit=1)
            stueck = teile[0].strip()
            rest = teile[1] if len(teile) > 1 else ""
            # nur splitten, wenn ein satzweiter Zustand endet
            if rest and not (zustand["st_bis"] == "satz" and zustand["st"]) and not zustand["tempo"]:
                stueck, rest = text, ""
            if stueck:
                segs.append({"t": "tts", "text": stueck, **werte(betont)})
            if rest:
                if zustand["st_bis"] == "satz":
                    zustand["st"], zustand["n"] = None, 0
                zustand["tempo"] = 0.0
                segs.append({"t": "auto"})
            text = rest.strip()

    pos = 0
    for m in TOKEN.finditer(markup):
        puffer.append(markup[pos:m.start()])
        pos = m.end()
        if m.group("sp"):
            ausgeben()
            name = m.group("sp")[1:-1]
            if name not in stimmen:
                raise ValueError(f"Sprecher {name} ohne Stimme ({lang})")
            zustand.update(stimme=stimmen[name], st=None, n=0, tempo=0.0)
            segs.append({"t": "auto"})
            absatzanfang = True
            continue
        if m.group("lex"):
            puffer.append(m.group("lex")[1:-1].split("|", 1)[1])
            continue
        if m.group("emo"):
            ausgeben()
            run = m.group("emo")
            for e in TEMPO:
                if e in run:
                    zustand["tempo"] = _tempo_delta(e, run.count(e))
            for e in STIMMUNG:
                if e in run:
                    zustand.update(st=None if e == "😐" else e, n=run.count(e),
                                   st_bis="absatz" if absatzanfang else "satz")
            continue
        if m.group("pa"):
            ausgeben()
            segs.append({"t": "pause", "ms": PAUSE[len(m.group("pa"))]})
            absatzanfang = False
            continue
        if m.group("bet"):
            ausgeben()
            puffer.append(m.group("bet")[1:-1])
            ausgeben(betont=True)
            continue
        absatzanfang = False
    puffer.append(markup[pos:])
    ausgeben()

    # Standardpausen, Pausenfaktor (🤔), Aufraeumen
    aus = []
    for i, s in enumerate(segs):
        if s["t"] == "auto":
            continue
        if s["t"] == "tts" and aus and aus[-1]["t"] == "tts":
            m = re.match(r"^([,;:.!?—]+)\s*", s["text"])      # Satzzeichen nach Betonung -> an den Vorgaenger
            if m:
                aus[-1]["text"] += m.group(1)
                s = {**s, "text": s["text"][m.end():]}
                if not s["text"]:
                    continue
            vorher = aus[-1]["text"].rstrip("\"' ")
            ms = 400 if vorher.endswith((".", "!", "?")) else 150 if vorher.endswith((",", ";", ":", "—")) else 0
            aus.append({"t": "pause", "ms": int(ms * aus[-1]["pf"])})
        if s["t"] == "pause":
            pf = aus[-1]["pf"] if aus and aus[-1]["t"] == "tts" else 1.0
            s = {"t": "pause", "ms": int(s["ms"] * pf)}
            if aus and aus[-1]["t"] == "pause":
                aus[-1]["ms"] = max(aus[-1]["ms"], s["ms"])
                continue
        aus.append(s)
    while aus and aus[0]["t"] == "pause":
        aus.pop(0)
    while aus and aus[-1]["t"] == "pause":
        aus.pop()
    return aus


def testset_lesen(pfad):
    saetze, lang = [], None
    zeilen = open(pfad, encoding="utf-8").read().splitlines()
    for i, z in enumerate(zeilen):
        if z.startswith("## Deutsch"):
            lang = "de"
        elif z.startswith("## Englisch"):
            lang = "en"
        m = re.match(r"- \*\*(\w+)\*\* (.+)", z)
        if m and lang:
            text = zeilen[i + 1].strip().strip("`")
            saetze.append({"id": m.group(1), "lang": lang, "label": m.group(2), "markup": text})
    return saetze


def paket(testset):
    os.makedirs(PAKET, exist_ok=True)
    saetze = testset_lesen(testset)
    refs = {}
    for s in saetze:
        s["a"] = [{"t": "tts", "text": klartext(s["markup"]), "ex": 0.5, "cfg": 0.5, "temp": 0.8, "gain_db": 0,
                   "stimme": STIMMEN[s["lang"]]["_"], "stimmung": "😐"}]
        s["b"] = parse(s["markup"], s["lang"])
        for v in ("a", "b"):
            for g in s[v]:
                g.pop("pf", None)
                if g["t"] == "tts":
                    refs.setdefault((g["stimme"], s["lang"]), None)
    ref_dateien = {}
    for (stimme, lg) in refs:
        quelle = next((p for p in (os.path.join(ARCHIV, stimme, f"muster_{lg}.wav"), os.path.join(ARCHIV, stimme, "hoerprobe.wav"))
                       if os.path.exists(p)), None)
        if not quelle:
            raise SystemExit(f"Referenz fehlt: {stimme} ({lg})")
        name = f"ref_{stimme}_{lg}.wav"
        shutil.copy(quelle, os.path.join(PAKET, name))
        ref_dateien[f"{stimme}|{lg}"] = name
    shutil.copy(testset, os.path.join(PAKET, "testset.md"))
    json.dump({"version": "prosody-markup 0.1", "seed": 1234, "lora": {"de": "mix_v1"}, "tempo": 0.91,
               "refs": ref_dateien, "saetze": saetze}, open(os.path.join(PAKET, "jobs.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    n = sum(1 for s in saetze for g in s["b"] if g["t"] == "tts")
    print(f"[prosodie] {len(saetze)} Saetze, {n} Markup-Chunks, {len(ref_dateien)} Referenzen -> {PAKET}")


def seite():
    d = json.load(open(os.path.join(PAKET, "jobs.json"), encoding="utf-8"))
    vorlage = open(os.path.join(HIER, "tools", "vorlagen", "hoertest_prosodie.html"), encoding="utf-8").read()
    daten = [{"id": s["id"], "lang": s["lang"], "label": s["label"], "markup": s["markup"],
              "chunks": [f'{g["stimmung"]} ex {g["ex"]} cfg {g["cfg"]} | {g["text"]}' if g["t"] == "tts" else f'⏸ {g["ms"]} ms'
                         for g in s["b"]]} for s in d["saetze"]]
    html = vorlage.replace("/*DATEN*/[]", json.dumps(daten, ensure_ascii=False))
    ziel = os.path.join(PAKET, "hoertest.html")
    open(ziel, "w", encoding="utf-8").write(html)
    print(f"[prosodie] Hoertest: {ziel}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "paket":
        ts = a[a.index("--testset") + 1] if "--testset" in a else os.path.join(HIER, "docs", "prosodie", "testset_prosodie_v0.1.md")
        paket(ts)
    elif a[0] == "zeigen":
        for g in parse(a[1], a[2] if len(a) > 2 else "de"):
            print(g)
    elif a[0] == "seite":
        seite()
