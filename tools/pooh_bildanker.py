"""AP 58 - Bildanker Winnie-the-Pooh: 27 ausgewaehlte Bilder (Projekt-Doc POOH_bilder.md) an Ankersaetze haengen.
Quelle der Auswahl: Gutenberg #67098 (Bildbeschreibungen Distributed Proofreaders). Shepard-Bilder werden NICHT verwendet,
nur Szene als Textgrundlage fuer eigene One-Line-Bilder.
Regel: Bild steht NACH dem letzten Satz des Absatzes, der den Ankertext enthaelt; Kapitelanfang -> nach der Ueberschrift.
Ausgabe: work/bilder.json  (liest work/200_tagging.json; ohne Tagging: --probe prueft Anker gegen raw_modernized.txt)
"""
import os, re, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
BOOK = "winnie-the-pooh"

# nr, Kapitel (c001 = Einleitung), Ankertext ("KAPITELANFANG" = nach Ueberschrift), Szene (Bildbeschreibung)
BILDER = [
 (3, "c002", "KAPITELANFANG", "A hand-drawn map of the Forest: a river; Christopher Robin's house; the Hundred Acre Wood and Owl's house; big stones and rocks; Rabbit's house with friends and relations; Eeyore's gloomy boggy place; a floody place near Piglet's house; where the Woozle wasn't; Pooh's house past six pine trees; the Heffalump trap; Kanga's house and the sandy pit where Roo plays; a picnic place and a bee tree."),
 (4, "c002", "KAPITELANFANG", "Christopher Robin drags his teddy bear down the stairs by one leg, bump, bump, bump, the bear's head on the steps. The boy wears a checked shirt over shorts."),
 (7, "c002", "So he began to climb the tree", "A tall tree; the bear climbs slowly up the trunk."),
 (14, "c002", "something tells me that they're suspicious", "The bear floats in the air hanging from a balloon, surrounded by bees."),
 (22, "c003", "Oh, well, then, come in", "The bear squeezes halfway into Rabbit's burrow; he barely fits through the hole."),
 (27, "c003", "And for a long time Pooh only said", "Christopher Robin, Rabbit, Rabbit's friends and relations, Piglet, some mice and a hedgehog all pull in a long line on the bear, still stuck in the hole."),
 (28, "c004", "KAPITELANFANG", "Piglet in front of the very big old beech-tree that is his house; his small clothes dry on a washing line."),
 (30, "c004", "So off they went together", "The bear and Piglet follow tracks in the snow around a small spinney of trees."),
 (35, "c005", "KAPITELANFANG", "Eeyore, the old grey donkey, stands with his nose to the ground at the base of a tree, in a thistly corner."),
 (39, "c005", "PLEZ CNOKE IF AN RNSR IS NOT REQID", "The bear stands before Owl's front door high up in a branch of a big old tree, studying the notices by the bell-pull and the knocker."),
 (42, "c005", "Attached to it", "Christopher Robin nails Eeyore's tail back on; Eeyore bends round to look; the bear watches with a smile."),
 (45, "c006", "KAPITELANFANG", "The bear, Piglet and Christopher Robin sit around a picnic blanket with a honey pot, plates and teacups; the boy talks with one foot in the air, the bear and Piglet listen."),
 (51, "c006", "and began to lick", "An odd creature: its bottom looks like the bear, but where the head should be there is a honey jar."),
 (54, "c006", "it was at that moment that Piglet looked down", "The bear in the pit, struggling furiously to get the honey jar off his head."),
 (57, "c007", "KAPITELANFANG", "Eeyore looks at his own reflection in a stream in front of a big old tree, ears flopping down; a dragonfly."),
 (63, "c007", "And he began to eat", "The bear sits on the ground with his face deep in the honey jar."),
 (69, "c007", "as happy as could be", "Eeyore happily puts the burst balloon into the empty jar and takes it out again, tail perked up; the bear and Piglet walk away hand in hand."),
 (73, "c008", "who should come stumping up the hill but Pooh", "Kanga, a kangaroo mother, opens her arms and smiles down at tiny Roo climbing out of a mousehole, tail in the air; the bear and Rabbit approach."),
 (75, "c008", "thought of something at the same time", "Kanga bounds away in great jumps, leaving a cloud of dust; Piglet peers out of her pouch."),
 (78, "c008", "scrubbing him firmly with a large lathery flannel", "Piglet in a washtub being scrubbed by Kanga with a lathery flannel; water splashes everywhere."),
 (85, "c009", "it's simply a Confused Noise", "Christopher Robin in big boots shouts to the front of a long line: Rabbit, the bear, Piglet, Owl, Kanga and baby Roo."),
 (90, "c009", "drifted up against it, and climbed out", "The bear holds a long pole across a stream; Roo climbs out; Kanga opens her arms; Owl spreads his wings."),
 (93, "c010", "and still he hadn't done anything", "Piglet looks out of a window of his house in a huge tree; rain pours down and floodwater swirls around the trunk."),
 (102, "c010", "so I brought it to you", "The bear rides astride his empty floating honey jar out of the water; it is still raining."),
 (103, "c010", "and it wobbled no longer", "The bear climbs into an upside-down umbrella floating as a boat; Christopher Robin in big boots looks on with approval."),
 (112, "c011", "one of Rabbit's relations", "A party under the trees: Christopher Robin stands at a long table speaking to everyone; at the table Rabbit, Kanga and Roo, the bear, Piglet, Eeyore and Owl; small animals all around."),
 (114, "c011", "for a long time they were silent", "The bear and Piglet walk home together into the golden evening sunset; the bear carries his present."),
]

norm = lambda t: re.sub(r"[^a-z0-9]+", "", str(t).lower())


def anker_finden(content, src="en"):
    ids = list(content)
    out = []
    for nr, kap, txt, szene in BILDER:
        kids = [i for i in ids if i.startswith(kap + "_")]
        anker, fehler = None, None
        if txt == "KAPITELANFANG":
            anker = next((i for i in kids if content[i].get("type") == "h"), None)
        else:
            t = norm(txt)
            treffer = [i for i in kids if t in norm(content[i].get(src, ""))]
            if len(treffer) != 1:
                fehler = f"{len(treffer)} Treffer"
            if treffer:
                j = ids.index(treffer[0])   # bis Absatzende (naechstes p oder anderer Typ h) vorlaufen
                while j + 1 < len(ids) and ids[j + 1].startswith(kap + "_") and content[ids[j + 1]].get("type") not in ("p", "h"):
                    j += 1
                anker = ids[j]
        out.append({"nr": nr, "kapitel": kap, "anker": anker, "position": "nach", "ankertext": txt,
                    "szene": szene, "datei": f"images/bilder/pooh_{nr:03d}.jpg", "status": "offen",
                    **({"fehler": fehler} if fehler or not anker else {})})
    return out


def probe():
    raw = open(os.path.join(config.book_dir(BOOK), "raw_modernized.txt"), encoding="utf-8").read()
    kap = re.split(r"###CHAPTER###", raw)[1:]
    for nr, k, txt, _ in BILDER:
        if txt == "KAPITELANFANG":
            continue
        n = sum(norm(p).count(norm(txt)) for p in kap[int(k[1:]) - 1].split("\n\n"))
        print(f"  {nr:3d} {k} {'ok' if n == 1 else f'!! {n} Treffer'}  {txt[:50]}")


def main():
    if "--probe" in sys.argv:
        return probe()
    d = json.load(open(config.work_path(BOOK, "200_tagging"), encoding="utf-8"))
    res = anker_finden(d["content"])
    p = os.path.join(config.work_dir(BOOK), "bilder.json")
    alt = {}
    if os.path.exists(p):   # Status/Dateien frueherer Laeufe behalten
        alt = {b["nr"]: b for b in json.load(open(p, encoding="utf-8")).get("bilder", [])}
    for b in res:
        for k in ("status", "datei", "prompt", "modell", "kosten_usd", "freigabe"):
            if k in alt.get(b["nr"], {}):
                b[k] = alt[b["nr"]][k]
    for b in res:   # erzeugte Bilder (start_ap58_bilder.bat) als fertig markieren
        if os.path.exists(os.path.join(config.book_dir(BOOK), b["datei"])):
            b.update({"status": "fertig", "modell": "gemini-3.1-flash-image", "freigabe": "CK 26.10.2026"})
    json.dump({"werk": BOOK, "stand": "AP 58", "bilder": res}, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    f = [b for b in res if not b.get("anker") or b.get("fehler")]
    print(f"[bildanker] {len(res)} Bilder -> {p}; Probleme: {len(f)}")
    for b in f:
        print("   ", b["nr"], b["kapitel"], b.get("fehler"), b["ankertext"])
    return 1 if f else 0


if __name__ == "__main__":
    sys.exit(main() or 0)
