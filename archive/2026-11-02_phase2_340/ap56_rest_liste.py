"""AP 56 (26.10.2026): Rest-Saetze nach zweitem 345-Nachlauf als Vorlage fuer den Kuratormodus.
Erkennt die Verschiebungsketten erneut (offline, s345.erkennen) und listet je Satz die betroffenen Woerter:
Quellwort | jetziges Gegenwort (s340) | Vorschlag Pruefaligner. AENDERT NICHTS an 340/345.
Aufruf:  python tools/ap56_rest_liste.py [werk ...]   (ohne Werk: alle mit work/345_verschiebung.json)
Ausgabe: <werk>/work/345_rest_kurator.json  +  docs/AP56_rest_saetze_345.md
"""
import glob, json, os, re, sys
HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HIER)
from config import config
from pipeline import s345_verschiebung as s345


def werk_liste(book_id):
    config.werk_sprachen(book_id)
    src, tgt = config.SOURCE_LANGUAGE, config.TARGET_LANGUAGES[0]
    data = json.load(open(config.work_path(book_id, "340_wortalignment"), encoding="utf-8"))
    pruef = {s["id"]: s["w"] for s in json.load(open(config.work_path(book_id, "345_pruefaligner"), encoding="utf-8"))}
    markiert = s345.erkennen(data["content"], pruef)
    out = []
    for tid, kett in sorted(markiert.items()):
        v = data["content"][tid]
        zt = [m.group() for m in re.finditer(r"\S+", v.get(tgt, ""))]
        pw = dict((i, sp) for i, sp in pruef[tid])
        zt_sp = [(m.start(), m.end()) for m in re.finditer(r"\S+", v.get(tgt, ""))]
        eintr = []
        for k in kett:
            for w in v["align"]:
                if k["von"] <= w["i"] <= k["bis"]:
                    vor = sorted(s345._tokset(pw.get(w["i"], []), zt_sp))
                    eintr.append({"i": w["i"], "wort": w.get(src), "jetzt": w.get(tgt),
                                  "pruef": " ".join(zt[j] for j in vor) or None, "richtung": k["richtung"]})
        out.append({"tag_id": tid, src: v.get(src, ""), tgt: v.get(tgt, ""), "woerter": eintr})
    p = os.path.join(os.path.dirname(config.work_path(book_id, "345_verschiebung")), "345_rest_kurator.json")
    json.dump({"werk": book_id, "quelle": src, "ziel": tgt, "saetze": out}, open(p, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return src, tgt, out


def main(werke):
    if not werke:
        werke = sorted(os.path.basename(os.path.dirname(os.path.dirname(f)))
                       for f in glob.glob(os.path.join(HIER, "authors", "*", "books", "*", "work", "345_verschiebung.json")))
    md = ["# AP 56 – Rest-Saetze nach 345-Nachlauf (Vorlage Kuratormodus)", "",
          "Spalten: Quellwort | jetzt (s340) | Pruefaligner-Vorschlag. Nichts automatisch geaendert.", ""]
    ges = 0
    for w in werke:
        src, tgt, out = werk_liste(w)
        ges += len(out)
        print(f"{w}: {len(out)} Saetze")
        if not out:
            continue
        md += [f"## {w} ({len(out)})", ""]
        for s in out:
            md += [f"**{s['tag_id']}**  ", f"{src.upper()}: {s[src]}  ", f"{tgt.upper()}: {s[tgt]}", ""]
            md += [f"- [{e['i']}] {e['wort']} | {e['jetzt'] or '–'} | {e['pruef'] or '–'}" for e in s["woerter"]] + [""]
    md.insert(3, f"Gesamt: {ges} Saetze.\n")
    os.makedirs(os.path.join(HIER, "docs"), exist_ok=True)
    open(os.path.join(HIER, "docs", "AP56_rest_saetze_345.md"), "w", encoding="utf-8").write("\n".join(md))
    print(f"Gesamt {ges} -> docs/AP56_rest_saetze_345.md")


if __name__ == "__main__":
    main(sys.argv[1:])
