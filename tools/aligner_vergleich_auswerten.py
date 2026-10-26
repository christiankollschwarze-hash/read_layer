"""AP 54a - Auswertung Aligner-Vergleich gegen Stage 340 (DeepSeek-Wortanker).
Aufruf: py -3.11 tools/aligner_vergleich_auswerten.py [werk]
Kennzahlen je Aligner (GPU-Lauf, ganzes Werk):
  abdeckung     = Anteil EN-Woerter mit Anker (54a-Metrik: alles ausser 'unresolved'; Nenner alle EN-Woerter)
  deckung_54a   = von 54a-Ankern (direct/gap_fallback/compound_pair) trifft der Aligner dasselbe DE-Wort
  null_einig    = wo 54a 'none' sagt, setzt der Aligner ebenfalls keinen Anker
Schreibt: work/_aligner_vergleich/auswertung.json, tabelle.md, stichprobe_<variante>.txt (Abweichungen, 40 Saetze)
"""
import json, random, sys
from pathlib import Path

werk = sys.argv[1] if len(sys.argv) > 1 else "call-of-the-wild"
basis = next(Path("authors").glob(f"*/books/{werk}"))
ordner = basis / "work" / "_aligner_vergleich"
ref = json.loads((basis / "work" / "340_wortalignment.json").read_text(encoding="utf-8"))["content"]
lauf = {f"{r.get('variante')}_{r.get('geraet')}": r for r in
        json.loads((ordner / "laufzeit.json").read_text(encoding="utf-8")) if "variante" in r}

n_ges = sum(len(v.get("align") or []) for v in ref.values())
n_unres = sum(1 for v in ref.values() for w in v.get("align") or [] if w.get("source") == "unresolved")
zeilen = [{"aligner": "DeepSeek 54a (Referenz)", "abdeckung": round(100 * (1 - n_unres / n_ges), 2),
           "deckung_54a": 100.0, "null_einig": 100.0}]


def ueberlappt(a, b):
    return a[0] < b[1] and b[0] < a[1]


for datei in sorted(ordner.glob("*_cuda.json")):
    name = datei.stem[:-5]
    al = {s["id"]: {i: sp for i, sp in s["w"]} for s in json.loads(datei.read_text(encoding="utf-8"))}
    mit = treffer = n_anker = n_null = null_ok = 0
    abw = {}
    for sid, v in ref.items():
        a = al.get(sid, {})
        for w in v.get("align") or []:
            sp = a.get(w["i"])
            mit += bool(sp)
            if w.get("source") in ("direct", "gap_fallback", "compound_pair") and w.get("de_span"):
                n_anker += 1
                if sp and any(ueberlappt(x, w["de_span"]) for x in sp):
                    treffer += 1
                else:
                    abw.setdefault(sid, []).append((w["en"], w.get("de"), [v["de"][x[0]:x[1]] for x in sp or []]))
            elif w.get("source") == "none":
                n_null += 1
                null_ok += not sp
    r = lauf.get(name.rsplit("_", 1)[0] + "_cuda", lauf.get(name + "_cuda", {}))
    cpu = lauf.get(name.rsplit("_", 1)[0] + "_cpu", lauf.get(name + "_cpu", {}))
    zeilen.append({"aligner": name, "abdeckung": round(100 * mit / n_ges, 2),
                   "deckung_54a": round(100 * treffer / max(n_anker, 1), 2),
                   "null_einig": round(100 * null_ok / max(n_null, 1), 2),
                   "gpu_s": r.get("gesamt_s"), "gpu_usd": r.get("kosten_usd"),
                   "cpu_s_hochgerechnet": round(cpu["ausrichten_s"] / cpu["saetze"] * len(ref), 0) if cpu.get("saetze") else None})
    random.seed(54)
    with open(ordner / f"stichprobe_{name}.txt", "w", encoding="utf-8") as f:
        for sid in random.sample(sorted(abw), min(40, len(abw))):
            f.write(f"## {sid}\nEN: {ref[sid]['en']}\nDE: {ref[sid]['de']}\n")
            for en, de54, deal in abw[sid]:
                f.write(f"  {en!r:20} 54a={de54!r:22} aligner={deal}\n")
            f.write("\n")

(ordner / "auswertung.json").write_text(json.dumps(zeilen, ensure_ascii=False, indent=1), encoding="utf-8")
md = ["| Aligner | Abdeckung (54a-Metrik) | Deckung mit 54a | Null-Einigkeit | GPU T4 s | Kosten/Buch $ | CPU 4 Kerne s (hochger.) |",
      "|---|---|---|---|---|---|---|"]
for z in zeilen:
    md.append(f"| {z['aligner']} | {z['abdeckung']} % | {z['deckung_54a']} % | {z['null_einig']} % | "
              f"{z.get('gpu_s', '-')} | {z.get('gpu_usd', '-')} | {z.get('cpu_s_hochgerechnet', '-')} |")
(ordner / "tabelle.md").write_text("\n".join(md) + "\n", encoding="utf-8")
print("\n".join(md))
