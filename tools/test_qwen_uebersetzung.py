"""Testlauf: Qwen 3.5 397B (OpenRouter) übersetzt Kapitel neu, Vergleich mit Pipeline-DE (310).
Aufruf: python tools/test_qwen_uebersetzung.py [buch_pfad] [kapitel ...]   (Standard: Baskerville c002)
"""
import json, os, sys, re, time, requests
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELL = os.environ.get("MODELL", "qwen/qwen3.5-397b-a17b")
KURZ = MODELL.split("/")[-1].replace(":", "_")

def key(name="OPENROUTERAPIKEY"):
    for z in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if z.split("=",1)[0].strip().upper().replace("_","") == name:
            return z.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit(f"{name} fehlt in .env")

buch = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "authors/doyle-ac/books/the-hound-of-the-baskervilles"
kapitel = sys.argv[2:] or ["c002"]
d = json.loads((buch / "work/310_uebersetzung.json").read_text(encoding="utf-8"))
c, prof = d["content"], d["meta"].get("profile", {}).get("style", {})

SYSTEM = ("You are a literary translator (English to German) for a published audiobook edition. "
          f"Tone: {prof.get('tone','')}. Register: {prof.get('register','')}. Setting: {prof.get('setting','')}. "
          f"Notes: {prof.get('notes','')} "
          "Translate faithfully and idiomatically into modern, elegant German; keep names; use 'Sie' between Holmes and Watson. "
          "Use German quotation marks „…“. "
          "Input lines look like [n] English sentence. Translate each line separately so the numbers stay aligned 1:1, "
          "and keep everything belonging to that line (including speech tags like 'said Holmes'). "
          "Reply ONLY with the lines in the form [n] German sentence, nothing else.")

def absaetze(kap):
    block = []
    for k, v in c.items():
        if not k.startswith(kap): continue
        if v["type"] == "p":
            if block: yield block; block = []
        elif v.get("en", "").strip():
            block.append(k)
    if block: yield block

from concurrent.futures import ThreadPoolExecutor
MISTRAL = MODELL.startswith("mistral-")
URL = "https://api.mistral.ai/v1/chat/completions" if MISTRAL else "https://openrouter.ai/api/v1/chat/completions"
PREIS = {"mistral-large-2512": (0.5, 1.5), "mistral-small-latest": (0.15, 0.6)}.get(MODELL)
s = requests.Session(); s.headers["Authorization"] = f"Bearer {key('MISTRALAPIKEY' if MISTRAL else 'OPENROUTERAPIKEY')}"
bloecke = [b for kap in kapitel for b in absaetze(kap)]

def uebersetze(nr):
    block = bloecke[nr]
    ctx = " ".join(c[i]["en"] for i in bloecke[nr-1]) if nr else "(start of chapter)"
    user = f"Previous paragraph (English, context only, do not translate):\n{ctx}\n\nTranslate:\n" + \
           "\n".join(f"[{n}] {c[i]['en']}" for n, i in enumerate(block, 1))
    for versuch in range(5):
        try:
            body = {"model": MODELL, "temperature": 0.3, "max_tokens": 250 * len(block) + 200,
                    "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]}
            if not MISTRAL:
                body.update({"usage": {"include": True},
                             "reasoning": {"effort": os.environ["EFFORT"]} if os.environ.get("EFFORT") else {"enabled": False}})
            r = s.post(URL, timeout=90, json=body)
            if r.status_code == 429:
                time.sleep(5 + 5 * versuch); continue
            txt = ""; j = r.json(); txt = j["choices"][0]["message"]["content"] or ""
            out = {}
            for m in re.finditer(r"^\s*\[(\d+)\]\s*(.+?)\s*$", txt, re.M):
                n = int(m.group(1))
                if 1 <= n <= len(block): out[block[n-1]] = m.group(2)
            if len(out) != len(block): raise ValueError(f"{len(out)}/{len(block)} Zeilen")
            print("ok", block[0], flush=True)
            return {i: out.get(i, "[FEHLT]") for i in block}, (j.get("usage", {}).get("cost") or (PREIS and (j["usage"]["prompt_tokens"] * PREIS[0] + j["usage"]["completion_tokens"] * PREIS[1]) / 1e6) or 0)
        except Exception as e:
            print("Fehler, neuer Versuch:", block[0], e, repr(txt[:300]) if "txt" in locals() else ""); time.sleep(3)
    return {i: "[FEHLER]" for i in block}, 0

cache = ROOT / "Claude outputs/qwen_test" / f"_cache_{KURZ}_{buch.name}_{'_'.join(kapitel)}.jsonl"
cache.parent.mkdir(parents=True, exist_ok=True)
erg, kosten = {}, 0.0
if cache.exists():
    for z in cache.read_text(encoding="utf-8").splitlines():
        e = json.loads(z); erg.update(e["t"]); kosten += e["k"]
offen = [n for n in range(len(bloecke)) if bloecke[n][0] not in erg]
print("offen:", len(offen), "von", len(bloecke), flush=True)
def job(n):
    teil, k = uebersetze(n)
    if "[FEHLER]" not in teil.values():
        with open(cache, "a", encoding="utf-8") as f: f.write(json.dumps({"t": teil, "k": k}, ensure_ascii=False) + "\n")
    return teil, k
with ThreadPoolExecutor(int(os.environ.get("THREADS", "16"))) as ex:
    for (teil, k) in ex.map(job, offen):
        erg.update(teil); kosten += k
erg = {i: erg[i] for b in bloecke for i in b if i in erg}
print(len(bloecke), "Absätze,", len(erg), "Sätze")

ziel = ROOT / "Claude outputs/qwen_test"; ziel.mkdir(parents=True, exist_ok=True)
name = f"{KURZ}_{buch.name}_{'_'.join(kapitel)}"
(ziel / f"{name}.json").write_text(json.dumps(erg, ensure_ascii=False, indent=1), encoding="utf-8")
md = [f"# {MODELL} vs. Pipeline (310) – {name}\n", f"Kosten: {kosten:.4f} $\n", "| ID | EN | Pipeline-DE | Test-DE |", "|---|---|---|---|"]
esc = lambda t: (t or "").replace("|", "\\|")
for i, de in erg.items():
    md.append(f"| {i} | {esc(c[i]['en'])} | {esc(c[i].get('de'))} | {esc(de)} |")
try:
    import sacrebleu
    ref = [c[i].get("de", "") for i in erg]; hyp = list(erg.values())
    md.insert(2, f"chrF (Qwen gegen Pipeline): {sacrebleu.corpus_chrf(hyp, [ref]).score:.1f}\n")
except ImportError:
    pass
(ziel / f"{name}.md").write_text("\n".join(md), encoding="utf-8")
print("Fertig:", ziel / f"{name}.md", f"Kosten {kosten:.4f} $")
