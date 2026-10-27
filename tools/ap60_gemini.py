"""READ LAYER - AP 60 (27.10.2026): Gemini-Teil der Hoerprobe woertliche Rede. Keine Aenderung an der Produktion.
A) Multi-Speaker: je Einheit (Tripel) EIN Aufruf, Erzaehler + Figur, Stimmen aus dem Alice-Cast, Sprache fest.
B) Basis fuer Voice Conversion: jeder Satz komplett mit der Erzaehlerstimme (ein Aufruf je Satz), Sprache fest.
Sprache fest: Feld "language" (de-DE / en-GB) in speech_config; lehnt die API das Feld ab, wird ohne Feld
wiederholt und das im Bericht vermerkt (dann wirkt nur die Sprach-Regie im style).
Ausgabe: tests/ap60/<lg>/A/u<NN>.wav, tests/ap60/<lg>/B_basis/<tid>.wav, tests/ap60/gemini_bericht.json
Aufruf: py -3.11 tools/ap60_gemini.py   (Key GEMINI_API_KEY wie in der Pipeline)
"""
import base64, concurrent.futures as cf, json, os, sys, time, wave
from pathlib import Path

LESER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LESER))
from config import config  # noqa: E402
import requests  # noqa: E402

T = LESER / "tests/ap60"
URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
MODELL = config.MODELS.get("tts", "gemini-3.8-flash-tts")
RATE = 24000
LANG = {"en": "en-GB", "de": "de-DE"}
STIL = {"de": "German audiobook. Every speaker speaks German only, with native German pronunciation and melody; "
              "never switch to English.",
        "en": "English audiobook. Every speaker speaks British English only, with native English pronunciation."}
ROLLE = {"Erzaehler": "Narrator", "March Hare": "MarchHare"}
P = json.loads((T / "passage.json").read_text(encoding="utf-8"))
SATZ = {s["tid"]: s for s in P["saetze"]}
sprachfeld = {"ok": None}
log = []


def rufen(text, speakers, lg):
    """speakers = [(rolle, voice)] -> WAV-Bytes. 1 Eintrag ohne 'speaker' = Einzelstimme."""
    # 3.8: Multi-Speaker = ein Text-Item je Turn mit speech_metadata.speaker (keine "Name:"-Praefixe)
    turns = text if isinstance(text, list) else [[speakers[0][0], text]]
    inhalt = []
    for rolle, t in turns:
        meta = {"type": "speech_metadata", "style": STIL[lg]}
        if len(speakers) > 1:
            meta["speaker"] = rolle
        inhalt.append({"type": "text", "text": t, "annotations": [meta]})

    def payload(mit_sprache):
        sc = []
        for rolle, v in speakers:
            e = {"voice": v}
            if len(speakers) > 1:
                e["speaker"] = rolle
            if mit_sprache:
                e["language"] = LANG[lg]
            sc.append(e)
        return {"model": MODELL,
                "input": [{"type": "user_input", "content": inhalt}],
                "response_format": {"type": "audio", "mime_type": "audio/l16", "sample_rate": RATE},
                "generation_config": {"speech_config": sc}}
    for versuch in range(5):
        mit = sprachfeld["ok"] is not False
        r = requests.post(URL, headers={"x-goog-api-key": config.GEMINI_API_KEY, "Content-Type": "application/json"},
                          json=payload(mit), timeout=300)
        if r.status_code == 400 and mit and "language" in r.text:
            sprachfeld["ok"] = False
            log.append("API lehnt Feld 'language' ab -> ohne Feld, Sprache nur ueber style: " + r.text[:200])
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(10 * (versuch + 1)); continue
        if r.status_code >= 400:
            raise RuntimeError(f"{r.status_code}: {r.text[:300]}")
        if mit:
            sprachfeld["ok"] = True
        b64 = _audio(r.json())
        if not b64:
            time.sleep(2); continue
        pcm = base64.b64decode(b64)
        if pcm[:4] == b"RIFF":
            pcm = pcm[pcm.find(b"data") + 8:]
        return pcm
    raise RuntimeError("kein Audio nach 5 Versuchen")


def _audio(o):
    if isinstance(o, dict):
        if o.get("type") == "audio" and isinstance(o.get("data"), str):
            return o["data"]
        for v in o.values():
            x = _audio(v)
            if x: return x
    if isinstance(o, list):
        for v in o:
            x = _audio(v)
            if x: return x
    return None


def schreiben(pfad, pcm):
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(pfad), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(pcm)
    return len(pcm) / (2 * RATE)


def job_a(lg, i, e):
    zeilen, rollen = [], []
    for tid in e["tids"]:
        for g in SATZ[tid][lg]:
            r = ROLLE.get(g["s"], g["s"])
            if zeilen and zeilen[-1][0] == r:
                zeilen[-1][1] += " " + g["t"]
            else:
                zeilen.append([r, g["t"]])
            if (g["s"], r) not in rollen:
                rollen.append((g["s"], r))
    sp = [(r, P["stimmen"][f]) for f, r in rollen]
    text = [list(z) for z in zeilen] if len(sp) > 1 else zeilen[0][1]   # nur Figurenrede -> Einzelstimme
    return schreiben(T / lg / "A" / f"u{i:02d}.wav", rufen(text, sp, lg)), sum(len(t) for _, t in zeilen)


def job_b(lg, s):
    text = " ".join(g["t"] for g in s[lg])
    return schreiben(T / lg / "B_basis" / f"{s['tid']}.wav", rufen(text, [("Narrator", P["stimmen"]["Erzaehler"])], lg)), len(text)


def main():
    if not config.GEMINI_API_KEY:
        sys.exit("GEMINI_API_KEY fehlt")
    t0 = time.time()
    # erster Aufruf allein: klaert, ob das Sprachfeld angenommen wird
    jobs = [("A", lg, i, e) for lg in ("de", "en") for i, e in enumerate(P["einheiten"], 1)] + \
           [("B", lg, None, s) for lg in ("de", "en") for s in P["saetze"]]
    erg = {"A": {"de": [0, 0], "en": [0, 0]}, "B": {"de": [0, 0], "en": [0, 0]}}
    def lauf(j):
        v, lg, i, x = j
        return v, lg, (job_a(lg, i, x) if v == "A" else job_b(lg, x))
    erst = lauf(jobs[0]); rest = jobs[1:]
    with cf.ThreadPoolExecutor(4) as ex:
        ergebnisse = [erst] + list(ex.map(lauf, rest))
    for v, lg, (sek, z) in ergebnisse:
        erg[v][lg][0] += sek; erg[v][lg][1] += z
    sek_ges = sum(erg[v][lg][0] for v in erg for lg in erg[v])
    usd = sek_ges * 25 / 1e6 * config.PREISE[MODELL]["out"] + sum(erg[v][lg][1] for v in erg for lg in erg[v]) / 4 / 1e6 * config.PREISE[MODELL]["in"]
    bericht = {"modell": MODELL, "sprachfeld_angenommen": sprachfeld["ok"], "laufzeit_s": round(time.time() - t0, 1),
               "audio_s": {v: {lg: round(erg[v][lg][0], 1) for lg in erg[v]} for v in erg},
               "usd": round(usd, 3), "usd_je_variante": {v: round(sum(erg[v][lg][0] for lg in erg[v]) * 25 / 1e6 * config.PREISE[MODELL]["out"], 3) for v in erg},
               "log": log}
    (T / "gemini_bericht.json").write_text(json.dumps(bericht, ensure_ascii=False, indent=1), encoding="utf-8")
    print("[ap60]", json.dumps(bericht, ensure_ascii=False))


if __name__ == "__main__":
    main()
