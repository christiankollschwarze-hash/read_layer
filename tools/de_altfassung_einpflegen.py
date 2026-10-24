"""READ LAYER — Deutsche Altfassung (absatzweise) satzgenau in 400_regie/500_vertonung einpflegen.
Fuer Werke, deren Uebersetzung in der alten Pipeline (fassungen/de/work/chapters/chapter-N.json) vollstaendig ist,
in 400_regie aber Saetze ohne DE stehen. DeepSeek ordnet den deutschen Text WOERTLICH den englischen Satz-IDs zu.

Aufruf:  py -3.11 tools/de_altfassung_einpflegen.py <book_id> <altordner> [c002,c009,...]
         altordner = Pfad relativ zum Werk, z. B. _alt_20261010/fassungen/de/work/chapters
Exit-Code 1, wenn ein Kapitel nicht sauber aufgeht (Batch stoppt dann vor der Vertonung).
"""
import json, os, re, shutil, sys

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HIER)
from config import config            # noqa: E402
from pipeline import api_layer       # noqa: E402

TYPEN = {"s", "dl", "qt"}
TEIL = 30


def _n(t):
    return re.sub(r"\W", "", t or "").lower()


def _prompt(en_teil, de_fenster):
    zeilen = "\n".join(json.dumps({"id": t, "en": e["en"]}, ensure_ascii=False) for t, e in en_teil)
    return f"""You align an existing German translation to English sentences. Do NOT translate, do NOT change wording.

ENGLISH SENTENCES (in order):
{zeilen}

GERMAN TEXT (starts exactly where the first English sentence starts; it may continue beyond the last one):
<<<
{de_fenster}
>>>

Task: For every English id, return the German text that translates it, copied VERBATIM from the German text,
in order, contiguous, without gaps or overlaps. Start with the very beginning of the German text.
If one German sentence covers two English sentences, give it to the first id and "" to the second.
If two German sentences belong to one English sentence, give both to that id.
Stop after the German counterpart of the LAST English sentence; ignore the rest of the German text.

Return ONLY JSON: {{"<id>": "<German verbatim>", ...}}"""


def kapitel(book_id, data, altdir, k):
    nr = int(k[1:])
    alt = json.load(open(os.path.join(altdir, f"chapter-{nr}.json"), encoding="utf-8"))
    strom = "\n".join(alt["paragraphs"])
    eintraege = [(t, e) for t, e in data["content"].items() if t.startswith(k)]
    erg = {}
    for t, e in eintraege:                      # Kapitelueberschrift direkt aus der Altfassung
        if e.get("type") == "h" and not e.get("de"):
            erg[t] = alt.get("title", "")
    saetze = [(t, e) for t, e in eintraege if e.get("type") in TYPEN and e.get("en")]
    pos = 0
    for i in range(0, len(saetze), TEIL):
        teil = saetze[i:i + TEIL]
        en_len = sum(len(e["en"]) for _, e in teil)
        fenster = strom[pos:pos + int(en_len * 1.5) + 600]
        antwort = {}
        for versuch in range(3):
            try:
                antwort = api_layer.parse_json(api_layer.call_model("aligner", _prompt(teil, fenster), temperature=0))
                break
            except Exception as ex:
                print(f"    {k} Teil {i // TEIL + 1}: Versuch {versuch + 1} fehlgeschlagen ({str(ex)[:80]})")
        letzte = None
        for t, _ in teil:
            de = (antwort.get(t) or "").strip()
            erg[t] = de
            if de:
                letzte = de
        if letzte:                              # Zeiger hinter den letzten zugeordneten Satz setzen
            j = strom.find(letzte, pos)
            if j < 0:
                j = strom.find(letzte[-40:], pos)
                pos = j + 40 if j >= 0 else pos + len("".join(erg[t] for t, _ in teil))
            else:
                pos = j + len(letzte)
        print(f"    {k}: Teil {i // TEIL + 1}/{(len(saetze) + TEIL - 1) // TEIL} | Zeiger {pos}/{len(strom)}")
    zugeordnet = _n("".join(erg.get(t, "") for t, _ in saetze))
    deckung = len(zugeordnet) / max(1, len(_n(strom)))
    leer = sum(1 for t, _ in saetze if not erg.get(t))
    print(f"  [{k}] {len(saetze)} Saetze | Deckung {deckung:.1%} | leer {leer} | Rest {len(strom) - pos} Zeichen")
    return erg, deckung, leer


def main():
    a = sys.argv[1:]
    book_id, alt_rel = a[0], a[1]
    werk = config.book_dir(book_id)
    altdir = os.path.join(werk, alt_rel)
    p6, p7 = config.work_path(book_id, "400_regie"), config.work_path(book_id, "500_vertonung")
    data = json.load(open(p6, encoding="utf-8"))
    if len(a) > 2:
        kap = a[2].split(",")
    else:
        kap = sorted({t[:4] for t, e in data["content"].items()
                      if e.get("type") in TYPEN and e.get("en") and not e.get("de")})
    print(f"[einpflegen] {book_id}: Kapitel {kap} aus {alt_rel}")
    gesamt, ok = {}, True
    for k in kap:
        erg, deckung, leer = kapitel(book_id, data, altdir, k)
        if deckung < 0.97 or deckung > 1.03:
            print(f"  [{k}] ABBRUCH-KRITERIUM: Deckung ausserhalb 97-103 % -> nicht uebernommen")
            ok = False
            continue
        gesamt.update(erg)
    if gesamt:
        for p in (p6, p7):
            if not os.path.exists(p):
                continue
            shutil.copy(p, p + ".bak_einpflegen")
            d = json.load(open(p, encoding="utf-8"))
            for t, de in gesamt.items():
                if t in d["content"] and de:
                    d["content"][t]["de"] = de
                    d["content"][t]["de_quelle"] = "altfassung"
            json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"[einpflegen] geschrieben: {p} (Backup .bak_einpflegen)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
