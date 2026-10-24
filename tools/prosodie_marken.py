"""READ LAYER — Prosodie-Marken je Satz (17.10.2026): DeepSeek (flash) ordnet jeden Satz einer von fuenf
festen Vortragsklassen zu. KEINE freie Regie (Learning Juni 2026: frei formulierte LLM-Regie unkontrollierbar) -
nur Klassen, die tools/tts_paket.py --prosodie auf feste Chatterbox-Regler abbildet (STILE).
Aufruf: python tools/prosodie_marken.py <book_id> [--kapitel c001,c002]
Ergebnis: work/prosodie_en.json + work/prosodie_de.json (gleiche Marken; Klassifikation am Originaltext).
"""
import json, os, sys

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HIER)
sys.path.insert(0, os.path.join(HIER, "tools"))
from config import config
from pipeline import api_layer
from tts_paket import STILE, TYPEN

PROMPT = """You prepare an audiobook narration. For each numbered sentence decide how a good narrator would deliver it.
Classes (choose exactly one):
- ruhig: calm narration, description, neutral dialogue (DEFAULT - most sentences)
- lebhaft: lively action, brisk or cheerful speech
- gespannt: suspense, foreboding, hesitation, a secret
- ausruf: exclamation, alarm, anger, great excitement
- leise: whisper, sadness, tenderness, awe
Judge from the sentence AND its neighbours. Be sparing: only mark a sentence non-ruhig when the text clearly calls for it.
Answer ONLY with JSON mapping the numbers of NON-ruhig sentences to their class, e.g. {"3": "ausruf", "7": "leise"}.
If all are ruhig answer {}.

Sentences:
"""


def main(book, nur=None):
    d = json.load(open(config.work_path(book, "400_regie"), encoding="utf-8"))["content"]
    quelle = json.load(open(os.path.join(config.book_dir(book), "book.json"), encoding="utf-8")).get("originalsprache", "en")
    saetze = [(t, (e.get(quelle) or "").strip()) for t, e in d.items()
              if e.get("type") in TYPEN and (e.get(quelle) or "").strip() and (not nur or t[:4] in nur)]
    stil = {}
    STUECK = 80
    for a in range(0, len(saetze), STUECK):
        teil = saetze[a:a + STUECK]
        text = "\n".join(f"{i}. {s}" for i, (_, s) in enumerate(teil, 1))
        try:
            roh = api_layer.call_model("validator", PROMPT + text, max_tokens=2000)
            erg = api_layer.parse_json(roh)
        except Exception as ex:
            print(f"[prosodie] Stueck {a}: {ex}")
            continue
        for k, v in (erg or {}).items():
            try:
                i = int(k) - 1
            except ValueError:
                continue
            if 0 <= i < len(teil) and v in STILE and v != "ruhig":
                stil[teil[i][0]] = v
        print(f"[prosodie] {min(a + STUECK, len(saetze))}/{len(saetze)} Saetze, markiert {len(stil)}", flush=True)
    for t, _ in saetze:
        stil.setdefault(t, "ruhig")
    zaehl = {}
    for v in stil.values():
        zaehl[v] = zaehl.get(v, 0) + 1
    for lg in ("en", "de"):
        json.dump({"quelle": quelle, "modell": config.MODELS.get("validator"), "stil": stil},
                  open(os.path.join(config.work_dir(book), f"prosodie_{lg}.json"), "w", encoding="utf-8"), indent=1)
    print(f"[prosodie] {book}: {zaehl}")


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    nur = set(sys.argv[sys.argv.index("--kapitel") + 1].split(",")) if "--kapitel" in sys.argv else None
    main(a[0], nur)
