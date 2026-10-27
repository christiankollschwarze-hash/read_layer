"""READ LAYER - AP 60 (27.10.2026): Hoerprobe woertliche Rede - Vorbereitung (kostenlos, keine API).
Alice Kap. VII "A Mad Tea-Party", Saetze c007_00033 .. c007_00049 (Hutmacher, Maerzhase, Haselmaus, Alice).
Schreibt tests/ap60/passage.json (Saetze, Segmente je Sprache, Einheiten = Tripel, Stimmen, Stimmproben)
und kopiert die bestehende Fassung (Referenz) + Stimmproben nach tests/ap60/. Produktionsdaten werden nur gelesen.
Aufruf: py -3.11 tools/ap60_vorbereiten.py
"""
import json, os, shutil
from pathlib import Path

LESER = Path(__file__).resolve().parent.parent
WERK = LESER / "authors/carroll-l/books/alice-s-adventures-in-wonderland"
ZIEL = LESER / "tests/ap60"
VON, BIS = "c007_00033", "c007_00049"
FIGUREN = ("Alice", "Hatter", "March Hare", "Dormouse")

wd = WERK / "work"
tag = json.loads((wd / "200_tagging.json").read_text(encoding="utf-8"))["content"]
spr = json.loads((wd / "sprecher.json").read_text(encoding="utf-8"))
cast = json.loads((wd / "casting.json").read_text(encoding="utf-8"))["plan"]
stimmen = {"Erzaehler": cast["erzaehler"]["id"]}
muster = {"Erzaehler": cast["erzaehler"]["stimme"]}
for e in cast["ensemble"]:
    if e["figur"] in FIGUREN:
        stimmen[e["figur"]], muster[e["figur"]] = e["id"], e["stimme"]

saetze = []
for t in sorted(tag):
    if not (VON <= t[:10] <= BIS) or tag[t]["type"] == "p":
        continue
    s = {"tid": t}
    for lg in ("en", "de"):
        segs = (spr.get(t) or {}).get(lg)
        if not segs:   # reine Erzaehlung: Satztext aus der Fassung
            txt = tag[t]["en"] if lg == "en" else json.loads((wd / "310_uebersetzung.json").read_text(encoding="utf-8"))["content"][t]["de"]
            segs = [{"t": txt, "s": "Erzaehler"}]
        s[lg] = [{"t": g["t"].strip(), "s": g["s"]} for g in segs if g["t"].strip()]
    saetze.append(s)

# Einheiten = Tripel (Einleitung / Rede / Folgesatz): Satz mit Figurenrede + angrenzende reine Erzaehlsaetze,
# hoechstens 2 Stimmen je Einheit (Erzaehler + eine Figur) -> ein Gemini-Multi-Speaker-Aufruf.
def figuren(s):
    return {g["s"] for g in s["en"] if g["s"] != "Erzaehler"}

einheiten, vorlauf = [], []
for s in saetze:
    f = figuren(s)
    if not f:
        if einheiten and not einheiten[-1].get("folge") and not vorlauf:
            einheiten[-1]["tids"].append(s["tid"]); einheiten[-1]["folge"] = True
        else:
            vorlauf.append(s["tid"])
        continue
    einheiten.append({"tids": vorlauf + [s["tid"]], "figur": sorted(f)[0], "folge": False})
    vorlauf = []
if vorlauf:
    einheiten.append({"tids": vorlauf, "figur": "", "folge": False})

ZIEL.mkdir(parents=True, exist_ok=True)
for lg in ("en", "de"):
    (ZIEL / lg / "ref").mkdir(parents=True, exist_ok=True)
    for s in saetze:
        q = WERK / "fassungen" / lg / "audio" / f"{s['tid']}.wav"
        if q.exists():
            shutil.copy2(q, ZIEL / lg / "ref" / q.name)
        else:
            print("fehlt Referenz:", lg, q.name)
(ZIEL / "stimmproben").mkdir(exist_ok=True)
for f, st in muster.items():
    for lg in ("de", "en"):
        q = LESER / "stimmen_archiv" / st / f"muster_{lg}.wav"
        if q.exists():
            shutil.copy2(q, ZIEL / "stimmproben" / f"{f.replace(' ', '_')}_{lg}.wav")
n_rede = sum(1 for s in saetze for g in s["en"] if g["s"] != "Erzaehler")
(ZIEL / "passage.json").write_text(json.dumps({"werk": WERK.name, "von": VON, "bis": BIS, "stimmen": stimmen,
    "muster": muster, "saetze": saetze, "einheiten": einheiten}, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"AP60: {len(saetze)} Saetze, {n_rede} Rede-Segmente, {len(einheiten)} Einheiten -> {ZIEL / 'passage.json'}")
