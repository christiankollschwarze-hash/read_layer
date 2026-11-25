"""Hörtest Fish Audio Drama 3 vs. Gemini – Alice Kap. 7 (Teegesellschaft).
Einmaliger Test, keine Stage. Aufruf:  python tools/fish_test/fish_test.py [de|en|alle] [--nur-stimmen]
Key: .env -> FISH_API_KEY
"""
import json, os, sys, wave, io, time, pathlib, requests

ROOT = pathlib.Path(__file__).resolve().parents[2]
BOOK = ROOT / "authors/carroll-l/books/alice-s-adventures-in-wonderland"
OUT = ROOT / "tools/fish_test"
ARCHIV = ROOT / "stimmen_archiv"
KAP = "c007"
API = "https://api.fish.audio"
BLOCK_MAX = 2000

def key():
    import re
    for line in open(ROOT / ".env", encoding="utf-8-sig", errors="ignore"):
        m = re.match(r"\s*(?:export\s+)?[A-Za-z_]*FISH[A-Za-z_]*\s*[=:]\s*(.+)", line, re.I)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    if os.environ.get("FISH_API_KEY"): return os.environ["FISH_API_KEY"]
    sys.exit("FISH_API_KEY fehlt in .env")

H = {"Authorization": f"Bearer {key()}"}
LOG = OUT / "kosten_log.jsonl"
def log(d):
    d["zeit"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG, "a", encoding="utf-8") as f: f.write(json.dumps(d, ensure_ascii=False) + "\n")

# --- Besetzung aus casting.json ---
casting = json.load(open(BOOK / "work/casting.json", encoding="utf-8"))["plan"]
STIMME = {"Erzaehler": casting["erzaehler"]["stimme"]}
for e in casting["ensemble"]:
    STIMME[e["figur"]] = e["stimme"]
FIGUREN = ["Erzaehler", "Alice", "Hatter", "March Hare", "Dormouse"]  # Speaker-Index 0..4
CHOR_ERSATZ = "Hatter" if "Crowd / Chorus" not in STIMME else None
if "Crowd / Chorus" in STIMME: FIGUREN.append("Crowd / Chorus")

nordwind = json.load(open(ARCHIV / "_texte/nordwind.json", encoding="utf-8"))

def stimmen(lg):
    """Je Figur ein privates Fish-Stimmmodell aus klon_<lg>.wav (Nordwind-Text). Wird gecacht."""
    cache_f = OUT / "stimmen_fish.json"
    cache = json.load(open(cache_f, encoding="utf-8")) if cache_f.exists() else {}
    ids = []
    for fig in FIGUREN:
        st = STIMME[fig]; k = f"{st}_{lg}"
        if k not in cache:
            wav = ARCHIV / st / f"klon_{lg}.wav"
            text = " ".join(nordwind[lg]) if isinstance(nordwind[lg], list) else nordwind[lg]
            r = requests.post(f"{API}/model", headers=H, timeout=300,
                data={"type": "tts", "train_mode": "fast", "visibility": "private",
                      "title": f"RL {st} {lg}", "texts": text, "enhance_audio_quality": "false"},
                files={"voices": (wav.name, open(wav, "rb"), "audio/wav")})
            if r.status_code >= 300: sys.exit(f"Stimme {k}: {r.status_code} {r.text[:400]}")
            cache[k] = {"figur": fig, "fish_id": r.json()["_id"], "clip": str(wav.relative_to(ROOT))}
            json.dump(cache, open(cache_f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            log({"art": "stimme", "key": k, "id": cache[k]["fish_id"]})
            print("Stimme angelegt:", k)
        ids.append(cache[k]["fish_id"])
    return ids

def turns(lg):
    u = json.load(open(BOOK / "work/310_uebersetzung.json", encoding="utf-8"))["content"]
    sp = json.load(open(BOOK / "work/sprecher.json", encoding="utf-8"))
    out = []  # (unit_id, fig, text)
    for uid, v in u.items():
        if not uid.startswith(KAP) or v["type"] in ("p", "h"): continue
        segs = sp[uid][lg] if uid in sp else [{"t": v.get(lg, ""), "s": "Erzaehler"}]
        for s in segs:
            fig = s["s"]
            if fig not in FIGUREN: fig = CHOR_ERSATZ if fig == "Crowd / Chorus" and CHOR_ERSATZ else "Erzaehler"
            t = s["t"].strip()
            if t: out.append((uid, fig, t))
    return out

def bloecke(tr):
    bl, cur, n = [], [], 0
    for uid, fig, t in tr:
        if n > BLOCK_MAX and (not cur or cur[-1][0] != uid):
            bl.append(cur); cur, n = [], 0
        cur.append((uid, fig, t)); n += len(t)
    if cur: bl.append(cur)
    return bl

def fish_text(block):
    parts, last = [], None
    for _, fig, t in block:
        i = FIGUREN.index(fig)
        parts.append((f"<|speaker:{i}|>" if i != last else " ") + t); last = i
    return "".join(parts)

def tts(text, ids):
    body = {"text": text, "reference_id": ids, "format": "wav", "sample_rate": 24000,
            "latency": "normal", "normalize": True}
    r = requests.post(f"{API}/v1/tts", headers={**H, "model": "drama-3", "Content-Type": "application/json"},
                      data=json.dumps(body), timeout=600)
    if r.status_code >= 300: raise RuntimeError(f"{r.status_code} {r.text[:400]}")
    return r.content, dict(r.headers)

def fix_wav(path):
    """Fish-Stream-WAV hat Platzhalter-Längen (0xFFFFFF..) -> korrekte Header schreiben."""
    import struct
    d = bytearray(path.read_bytes()); i = d.find(b"data")
    n = len(d) - (i + 8)
    d[4:8] = struct.pack("<I", len(d) - 8); d[i+4:i+8] = struct.pack("<I", n)
    path.write_bytes(bytes(d))

def lauf(lg, nur_stimmen=False):
    ids = stimmen(lg)
    if nur_stimmen: return
    d = OUT / lg; d.mkdir(parents=True, exist_ok=True)
    bl = bloecke(turns(lg)); frames = []
    for n, b in enumerate(bl, 1):
        f = d / f"block_{n:02d}.wav"; txt = fish_text(b)
        (d / f"block_{n:02d}.txt").write_text(txt, encoding="utf-8")
        if not f.exists():
            audio, hd = tts(txt, ids); f.write_bytes(audio)
            byt = len(txt.encode("utf-8"))
            log({"art": "tts", "lg": lg, "block": n, "bytes": byt, "usd_listenpreis_15": round(byt / 1e6 * 15, 4),
                 "header_modell": {k: v for k, v in hd.items() if "model" in k.lower()}})
            print(f"{lg} Block {n}/{len(bl)} ok ({byt} Bytes)")
        fix_wav(f)
        with wave.open(str(f)) as w: frames.append((w.getparams(), w.readframes(w.getnframes())))
    with wave.open(str(d / f"fish_{KAP}_{lg}.wav"), "wb") as w:
        w.setparams(frames[0][0])
        for _, fr in frames: w.writeframes(fr)
    # Gemini-Vergleich aus fassungen/<lg>/audio zusammenfügen
    src = sorted((BOOK / f"fassungen/{lg}/audio").glob(f"{KAP}_*.wav"))
    if src:
        with wave.open(str(d / f"gemini_{KAP}_{lg}.wav"), "wb") as out:
            for i, s in enumerate(src):
                with wave.open(str(s)) as w:
                    if i == 0: out.setparams(w.getparams())
                    out.writeframes(w.readframes(w.getnframes()))
    print(lg, "fertig:", d)

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "alle"
    for lg in (["de", "en"] if arg == "alle" else [arg]):
        lauf(lg, "--nur-stimmen" in sys.argv)
