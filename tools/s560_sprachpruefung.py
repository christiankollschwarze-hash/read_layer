"""READ LAYER - Stage 560 Sprachpruefung mit Neuvertonung (AP 57, 26.10.2026)
Ablauf (start_s560.bat <werk> [lg]), hoechstens MAX_RUNDEN Neuvertonungen je Satz:
  Pruefen   tools/sprachpruefung.py --paket -> Modal Whisper (frei + erzwungen mit Wort-Konfidenz) -> --auswerten
  Auswahl   py -3.11 tools/s560_sprachpruefung.py <werk> <lg> --auswahl    -> work/560_auswahl_<lg>.json
            (Exit 3 = nichts mehr neu zu vertonen)
  Vertonen  tools/neu_vertonen.py <werk> <lg> --los --stage560  (Gemini, gleiche Stimme je Figur, Lexikon nur wenn
            freigegeben, deutsche Regie), dann Wortzeiten 58c/520 der neuen Saetze, dann erneut Pruefen
  Bericht   ... --bericht  -> work/560_bericht_<lg>.json + BERICHT_560_<lg>.md (Rest fuer Kuratormodus,
            Lexikon-Vorschlag work/aussprache_<lg>_vorschlag.json - wird NICHT automatisch angewendet)
Auswahl je Satz (CK-Urteil "ok" nie, "kippt" immer):
  gekippt (erkannte Sprache != Ziel) | p(Ziel) < P_ZIEL | wort_en (englische Form gehoert) |
  wort_unsicher: mind. 2 Woerter < P_WORT oder eines < P_WORT_HART. Kurze Saetze nur bei "gekippt"/CK.
"""
import collections, json, os, sys
HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HIER)
from config import config  # noqa: E402

MAX_RUNDEN = 2
P_ZIEL = 0.5
P_WORT_HART = 0.10
GRENZE = 0.20      # mehr als 20 % der Saetze ausgewaehlt -> Halt vor dem Vertonen (Schwellen pruefen), Exit 4


def _lade(book, lg):
    wd = config.work_dir(book)
    sp = json.load(open(os.path.join(wd, f"sprachpruefung_{lg}.json"), encoding="utf-8"))
    pn = os.path.join(wd, f"neuvertonung_{lg}.json")
    nv = json.load(open(pn, encoding="utf-8")) if os.path.exists(pn) else {"laeufe": []}
    runden = collections.Counter(t for l in nv["laeufe"] if l.get("quelle") == "s560" for t in l["saetze"])
    # CK-Urteil "kippt" galt dem alten Audio: nach einer Neuvertonung zaehlt nur noch Whisper
    neu = {t for l in nv["laeufe"] for t in l["saetze"]}
    sp["urteile"] = {t: u for t, u in sp.get("urteile", {}).items() if not (u == "kippt" and t in neu)}
    return wd, sp, runden


def gruende(s, urteil):
    if urteil == "ok":
        return []
    g = []
    if urteil == "kippt":
        g.append("ck")
    if s.get("stufe") == "gekippt":
        g.append("gekippt")
    if s.get("kurz"):
        return g
    if s.get("p_ziel", 1) < P_ZIEL and "gekippt" not in g:
        g.append("p_ziel")
    if s.get("wort_en"):
        g.append("wort_en")
    wu = s.get("wort_unsicher") or []
    if len(wu) >= 2 or any(p < P_WORT_HART for _, p in wu):
        g.append("wort_unsicher")
    return g


def auswahl(book, lg):
    wd, sp, runden = _lade(book, lg)
    U = sp.get("urteile", {})
    tags, rest, gr = [], [], collections.Counter()
    for t, s in sp["saetze"].items():
        g = gruende(s, U.get(t))
        if not g:
            continue
        if runden[t] >= MAX_RUNDEN:
            rest.append(t)
            continue
        tags.append(t)
        gr.update(g)
    runde = max(runden.values(), default=0) + 1
    json.dump({"runde": runde, "tags": sorted(tags), "rest": sorted(rest), "gruende": dict(gr)},
              open(os.path.join(wd, f"560_auswahl_{lg}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[560] {book} [{lg}] Runde {runde}: {len(tags)} Saetze neu vertonen ({dict(gr)}); "
          f"{len(rest)} nach {MAX_RUNDEN} Runden weiter auffaellig")
    if tags and len(tags) > GRENZE * len(sp["saetze"]) and "--ohne-grenze" not in sys.argv:
        print(f"[560] HALT: {len(tags)} von {len(sp['saetze'])} Saetzen (> {GRENZE:.0%}) - Schwellen pruefen "
              f"(BERICHT_sprachpruefung, Cockpit), dann start_s560.bat erneut mit S560_OHNE_GRENZE=1")
        return 4
    return 0 if tags else 3


def bericht(book, lg):
    wd, sp, runden = _lade(book, lg)
    U = sp.get("urteile", {})
    S = sp["saetze"]
    rest = {t: gruende(s, U.get(t)) for t, s in S.items()}
    rest = {t: g for t, g in rest.items() if g}
    # Lexikon-Vorschlag: haeufig unsicher/englisch gehoerte Woerter (nur Vorschlag, CK prueft)
    zaehl = collections.Counter()
    for t in rest:
        zaehl.update(w for w, _ in S[t].get("wort_unsicher") or [])
        zaehl.update(S[t].get("wort_en") or [])
    vorschlag = {w: n for w, n in zaehl.most_common(60) if n >= 2}
    json.dump({"hinweis": "Vorschlag AP 57 - Woerter, die in auffaelligen Saetzen wiederholt fremd klingen. "
                          "Lautschreibung in aussprache_<lg>.json eintragen, dann freigegeben=true.",
               "woerter": vorschlag},
              open(os.path.join(wd, f"aussprache_{lg}_vorschlag.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    out = {"werk": book, "lang": lg, "saetze": len(S), "neu_vertont_s560": len(runden),
           "runden": dict(collections.Counter(runden.values())), "rest": rest}
    json.dump(out, open(os.path.join(wd, f"560_bericht_{lg}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    L = [f"# Stage 560 Sprachpruefung {book} [{lg}]", "",
         f"{len(S)} Saetze | neu vertont (s560): {len(runden)} | noch auffaellig: {len(rest)}", "",
         "## Rest fuer Kuratormodus", "| Satz | Gruende | p(Ziel) | unsicher/englisch | Soll |", "|---|---|---|---|---|"]
    for t, g in sorted(rest.items()):
        s = S[t]
        w = ", ".join([f"{x}({p})" for x, p in s.get("wort_unsicher") or []] + (s.get("wort_en") or []))
        L.append(f"| {t} | {'+'.join(g)} | {s.get('p_ziel')} | {w} | {s.get('soll', '')[:80]} |")
    L += ["", "## Lexikon-Vorschlag (haeufig fremd)", ", ".join(f"{w} ({n})" for w, n in vorschlag.items()) or "-"]
    open(os.path.join(wd, f"BERICHT_560_{lg}.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L[:4]))
    print(f"-> {os.path.join(wd, f'BERICHT_560_{lg}.md')}")


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    if not a:
        sys.exit(__doc__)
    book, lg = a[0], (a[1] if len(a) > 1 else "de")
    if "--auswahl" in sys.argv:
        sys.exit(auswahl(book, lg))
    if "--bericht" in sys.argv:
        bericht(book, lg)
