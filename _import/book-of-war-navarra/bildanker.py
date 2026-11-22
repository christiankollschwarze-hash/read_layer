"""Bildanker (allgemein, 22.11.2026): haengt die Bilder aus work/bilder_vorlage.json an Knoten aus work/200_tagging.json.
Vorbild: tools/pooh_bildanker.py (AP 58). Regel wie dort: Bild steht NACH dem letzten Knoten des Absatzes, der den
Ankertext enthaelt; "KAPITELANFANG" -> nach der Ueberschrift.
Eingang:  work/bilder_vorlage.json {werk, quellsprache, bilder: [{nr, kapitel, ankertext, szene, datei, status, ...}]}
          work/200_tagging.json (content: {knoten_id: {type, <sprache>: text}})
Ausgabe:  work/bilder.json {werk, stand, bilder: [... + anker, position]}  (Format wie Pooh)
Aufruf:   python tools/bildanker.py <werk> [--probe]
          --probe prueft die Ankertexte gegen raw_modernized.txt (ohne Tagging).
Exit:     0 alle verankert, 1 Probleme (Liste wird ausgegeben).
"""
import os, re, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config

norm = lambda t: re.sub(r"[^a-z0-9äöüß]+", "", str(t).lower())


def vorlage(werk):
    p = os.path.join(config.work_dir(werk), "bilder_vorlage.json")
    return json.load(open(p, encoding="utf-8"))


def anker_finden(content, bilder, src):
    ids = list(content)
    out = []
    for b in bilder:
        kap, txt = b["kapitel"], b["ankertext"]
        kids = [i for i in ids if i.startswith(kap + "_")]
        anker, fehler = None, None
        if txt == "KAPITELANFANG":
            anker = next((i for i in kids if content[i].get("type") == "h"), None)
        else:
            t = norm(txt)
            treffer = [i for i in kids if t in norm(content[i].get(src, ""))]
            if not treffer:   # Ankertext ueber Satzgrenze: Kapiteltext zusammensetzen, Knoten am Ende suchen
                acc, pos = "", []
                for i in kids:
                    acc += norm(content[i].get(src, "")); pos.append((len(acc), i))
                k = acc.find(t)
                if k != -1 and acc.find(t, k + 1) == -1:
                    ende = k + len(t)
                    treffer = [next(i for l, i in pos if l >= ende)]
            if len(treffer) != 1:
                fehler = f"{len(treffer)} Treffer"
            if treffer:
                j = ids.index(treffer[0])
                while j + 1 < len(ids) and ids[j + 1].startswith(kap + "_") and content[ids[j + 1]].get("type") not in ("p", "h"):
                    j += 1
                anker = ids[j]
        e = dict(b)
        e.update({"anker": anker, "position": "nach"})
        if fehler or not anker:
            e["fehler"] = fehler or "kein Anker"
        out.append(e)
    return out


def probe(werk):
    v = vorlage(werk)
    raw = open(os.path.join(config.book_dir(werk), "raw_modernized.txt"), encoding="utf-8").read()
    kap = re.split(r"###CHAPTER###", raw)[1:]
    f = 0
    for b in v["bilder"]:
        if b["ankertext"] == "KAPITELANFANG":
            continue
        n = norm(kap[int(b["kapitel"][1:]) - 1]).count(norm(b["ankertext"]))
        f += n != 1
        print(f"  {b['nr']:3d} {b['kapitel']} {'ok' if n == 1 else f'!! {n} Treffer'}  {b['ankertext'][:60]}")
    return 1 if f else 0


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__); return 2
    werk = args[0]
    if "--probe" in sys.argv:
        return probe(werk)
    v = vorlage(werk)
    src = v.get("quellsprache", "en")
    d = json.load(open(config.work_path(werk, "200_tagging"), encoding="utf-8"))
    res = anker_finden(d["content"], v["bilder"], src)
    for b in res:
        if not os.path.exists(os.path.join(config.book_dir(werk), b["datei"])):
            b["fehler"] = (b.get("fehler", "") + " Datei fehlt").strip()
    p = os.path.join(config.work_dir(werk), "bilder.json")
    json.dump({"werk": werk, "stand": v.get("stand", ""), "bilder": res}, open(p, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    f = [b for b in res if b.get("fehler")]
    print(f"[bildanker] {len(res)} Bilder -> {p}; Probleme: {len(f)}")
    for b in f:
        print("   ", b["nr"], b["kapitel"], b["fehler"], b["ankertext"][:60])
    return 1 if f else 0


if __name__ == "__main__":
    sys.exit(main() or 0)
