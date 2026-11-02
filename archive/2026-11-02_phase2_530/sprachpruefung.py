"""READ LAYER - Sprachpruefung der Satz-Audios: kippt die Aussprache ins Englische/Franzoesische?

Ablauf (start_sprachpruefung.bat <werk> [lg]):
  1) py -3.11 tools/sprachpruefung.py <werk> <lg> --paket      Satz-WAVs -> 16 kHz FLAC + Solltexte (gpu_sprache/<werk>_<lg>/)
  2) py -3.11 -m modal run gpu_sprache/sprache_modal.py --paket <werk>_<lg>   Whisper large-v3 je Satz (Sprache + Abschrift)
  3) py -3.11 tools/sprachpruefung.py <werk> <lg> --auswerten  Rangliste + Namen-Statistik

Je Satz (Whisper, frei und - falls nicht Deutsch erkannt - zusaetzlich deutsch erzwungen):
  p_de / p_en / p_fr   Sprachwahrscheinlichkeit des Audios
  top                  erkannte Sprache
  cer                  Zeichenfehlerrate der deutschen Abschrift gegen den Solltext (0 = deckungsgleich)
  verdacht             0..1  = max(1 - p_de, cer/0.6), kurze Saetze (< 1,2 s oder < 3 Woerter) halb gewichtet
  wort_unsicher        (AP 57) Woerter der erzwungenen Abschrift mit Konfidenz < P_WORT (fremd gesprochen?)
  wort_en              (AP 57) Woerter der freien Abschrift, die im EN-Satz stehen, aber nicht im Solltext
  stufe                gekippt (top != Zielsprache) | verdacht (verdacht >= 0,35 oder wort_en) | ok
Namen: Grossgeschriebene Woerter, die im DE- und EN-Text desselben Satzes stehen, plus Anreden (Mr., Sir, Le ...).
Ergebnis: authors/.../work/sprachpruefung_<lg>.json (+ BERICHT) -> Cockpit "Sprachpruefung" (CK: kippt / ok -> Schwelle).
"""
import os, sys, json, glob, re, difflib, collections, datetime
import numpy as np
import soundfile as sf

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR = 16000
ANREDEN = {"Mr.", "Mrs.", "Dr.", "Sir", "Lady", "Lord", "Miss", "Monsieur", "Madame", "Le", "La", "De"}
AUDIO_TYPEN = ("h", "s", "dl", "qt", "vs")


def werk_dir(book):
    t = glob.glob(os.path.join(HIER, "authors", "*", "books", book))
    if not t:
        sys.exit(f"Werk '{book}' nicht gefunden")
    return t[0]


def paket_dir(book, lg):
    return os.path.join(HIER, "gpu_sprache", f"{book}_{lg}")


def _lade16(p):
    x, sr = sf.read(p, dtype="float32", always_2d=False)
    if x.ndim > 1:
        x = x.mean(axis=1)
    if sr != SR:
        n = int(round(len(x) * SR / sr))
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype("float32")
    return x


def paket(book, lg):
    werk = werk_dir(book)
    content = json.load(open(os.path.join(werk, "work", "400_regie.json"), encoding="utf-8"))["content"]
    adir = os.path.join(werk, "fassungen", lg, "audio")
    ziel = paket_dir(book, lg)
    os.makedirs(os.path.join(ziel, "audio"), exist_ok=True)
    texte, n_neu, neu = {}, 0, set()
    for t, e in content.items():
        txt = (e.get(lg) or "").strip()
        q = os.path.join(adir, t + ".wav")
        if e.get("type") not in AUDIO_TYPEN or not txt or not os.path.exists(q):
            continue
        z = os.path.join(ziel, "audio", t + ".flac")
        if not os.path.exists(z) or os.path.getmtime(z) < os.path.getmtime(q):
            if os.path.exists(z):
                neu.add(t)   # Satz-Audio wurde neu erzeugt (z. B. tools/neu_vertonen.py) -> erneut pruefen
            sf.write(z, _lade16(q), SR, format="FLAC")
            n_neu += 1
        texte[t] = {"soll": txt, "typ": e.get("type"), "en": (e.get("en") or "").strip() if lg != "en" else ""}
    json.dump({"werk": book, "lang": lg, "texte": texte}, open(os.path.join(ziel, "texte.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    if neu:   # alte Whisper-Ergebnisse dieser Saetze verwerfen -> Modal prueft nur sie neu
        for f in glob.glob(os.path.join(ziel, "ergebnis_*.json")):
            e = json.load(open(f, encoding="utf-8"))
            if neu & set(e):
                json.dump({k: v for k, v in e.items() if k not in neu}, open(f, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"[paket] {len(texte)} Saetze ({n_neu} neu kodiert, davon {len(neu)} geaendert) -> {ziel}")


def _norm(s):
    s = s.lower().replace("ß", "ss")
    s = re.sub(r"[^\wäöü ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def cer(soll, ist):
    a, b = _norm(soll), _norm(ist)
    if not a:
        return 0.0
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return round(1 - sm.ratio(), 3)


def namen(de, en, figuren):
    """Eigennamen im Satz: grossgeschriebene Woerter, die auch im EN-Text grossgeschrieben (nicht am EN-Satzanfang)
    stehen, Figurennamen aus casting.json, Anreden. Aufeinanderfolgende werden zusammengefasst (Sir Henry, Le Beau)."""
    en_gross = set()
    for m in re.finditer(r"[A-Z][\w'-]*\.?", en):
        davor = en[:m.start()].rstrip()
        if davor and (davor[-1] not in ".!?\"“”‘’(" or davor.endswith(("Mr.", "Mrs.", "Dr.", "St."))):
            en_gross |= {m.group(0), m.group(0).rstrip(".")}
    gruppen, akt, ende = [], [], -2
    for m in re.finditer(r"[A-ZÄÖÜ][\wäöüÄÖÜß'-]*\.?", de):
        w = m.group(0)
        w_ = w if w in ANREDEN else w.rstrip(".")
        if w_ in ANREDEN or w_ in figuren or (len(w_) > 1 and w_ in en_gross):
            if akt and m.start() - ende <= 1:
                akt.append(w_)
            else:
                if akt:
                    gruppen.append(" ".join(akt))
                akt = [w_]
            ende = m.end()
    if akt:
        gruppen.append(" ".join(akt))
    return sorted(set(gruppen))


def wort_en(soll, en, abschrift):
    """AP 57: Woerter, die Whisper in der freien Abschrift in englischer Form hoert: stehen im EN-Satz,
    nicht im deutschen Solltext (z. B. "the", "said", "Queen" statt "Koenigin"). Namen (in beiden Texten) zaehlen nicht."""
    if not en or not abschrift:
        return []
    s_ = set(_norm(soll).split())
    e_ = set(_norm(en).split())
    return sorted({w for w in _norm(abschrift).split() if w in e_ and w not in s_ and len(w) > 1})


P_WORT = 0.25   # AP 57: Wort-Konfidenz der erzwungenen Zielsprach-Abschrift darunter = unsicher (Kalibrierung mit CK-Urteilen)


def wort_unsicher(woerter):
    """AP 57: Woerter mit niedriger Konfidenz in der erzwungenen Abschrift (fremd gesprochen?).
    Zahlen und Woerter bis 2 Buchstaben zaehlen nicht."""
    out = []
    for w, p in woerter or []:
        n = _norm(w)
        if p < P_WORT and len(n) > 2 and not n.isdigit():
            out.append([n, p])
    return out


def auswerten(book, lg):
    werk = werk_dir(book)
    z = paket_dir(book, lg)
    T = json.load(open(os.path.join(z, "texte.json"), encoding="utf-8"))["texte"]
    erg = {}
    for f in sorted(glob.glob(os.path.join(z, "ergebnis_*.json"))):
        erg.update(json.load(open(f, encoding="utf-8")))
    if not erg:
        sys.exit("keine Modal-Ergebnisse (gpu_sprache/<werk>_<lg>/ergebnis_*.json)")
    figuren = set()
    try:
        c = json.load(open(os.path.join(werk, "work", "casting.json"), encoding="utf-8"))
        for e in c["plan"]["ensemble"]:
            n = e.get("figur") or ""      # Originalname (EN); name_de enthaelt deutsche Woerter (Herzog ...)
            if n.isupper():               # Drama: ROSALIND -> Rosalind
                n = n.title()
            figuren |= {w for w in n.split() if w[:1].isupper() and len(w) > 2 and w.lower() not in ("the", "first", "second")}
    except Exception:
        pass
    alt = {}
    pp = os.path.join(werk, "work", f"sprachpruefung_{lg}.json")
    if os.path.exists(pp):
        alt = json.load(open(pp, encoding="utf-8")).get("urteile", {})
    S = {}
    for t, r in erg.items():
        if t not in T or "fehler" in r:
            continue
        soll = T[t]["soll"]
        p_ziel = float(r.get("probs", {}).get(lg, 0.0))
        ab = (r.get("text_ziel") if r.get("top") != lg else r.get("text_frei")) or r.get("text_ziel") or ""
        c_ = cer(soll, ab)
        kurz = r.get("dauer", 0) < 1.2 or len(soll.split()) < 3
        v = max(1 - p_ziel, min(1.0, c_ / 0.6))
        if kurz:
            v *= 0.5
        we = wort_en(soll, T[t]["en"], r.get("text_frei", "")) if lg != "en" else []
        wu = wort_unsicher(r.get("woerter"))
        stufe = "gekippt" if r.get("top") != lg and not kurz else ("verdacht" if v >= 0.35 or ((we or wu) and not kurz) else "ok")
        S[t] = {"p_ziel": round(p_ziel, 3), "p_en": round(float(r.get("probs", {}).get("en", 0)), 3),
                "p_fr": round(float(r.get("probs", {}).get("fr", 0)), 3), "top": r.get("top"),
                "cer": c_, "wort_en": we, "wort_unsicher": wu, "dauer": r.get("dauer"), "kurz": kurz, "verdacht": round(v, 3), "stufe": stufe,
                "text_frei": r.get("text_frei", ""), "text_ziel": r.get("text_ziel", ""), "soll": soll,
                "typ": T[t]["typ"], "namen": namen(soll, T[t]["en"], figuren) if lg != "en" else [],
                "audio": os.path.relpath(os.path.join(werk, "fassungen", lg, "audio", t + ".wav"), HIER).replace("\\", "/")}
    # Namen-Statistik: Kipp-Quote je Name gegen Saetze ohne Namen
    proName = collections.defaultdict(list)
    ohne = []
    for t, s in S.items():
        if s["kurz"]:
            continue
        auff = s["stufe"] != "ok"
        if s["namen"]:
            for n in s["namen"]:
                proName[n].append(auff)
        else:
            ohne.append(auff)
    basis = float(np.mean(ohne)) if ohne else 0.0
    namen_tab = sorted(({"name": n, "saetze": len(v), "auffaellig": int(sum(v)), "quote": round(float(np.mean(v)), 3)}
                        for n, v in proName.items() if len(v) >= 2), key=lambda x: (-x["quote"], -x["saetze"]))
    zaehl = collections.Counter(s["stufe"] for s in S.values())
    mit = [s["stufe"] != "ok" for s in S.values() if s["namen"] and not s["kurz"]]
    out = {"werk": book, "lang": lg, "datum": datetime.date.today().isoformat(), "n": len(S), "stufen": dict(zaehl),
           "quote_ohne_namen": round(basis, 3), "quote_mit_namen": round(float(np.mean(mit)), 3) if mit else None,
           "namen": namen_tab, "saetze": S, "urteile": alt}
    json.dump(out, open(pp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    rang = sorted(S.items(), key=lambda kv: -kv[1]["verdacht"])
    L = [f"# Sprachpruefung {book} [{lg}] - {out['datum']}\n",
         f"{len(S)} Saetze: gekippt {zaehl.get('gekippt', 0)}, verdacht {zaehl.get('verdacht', 0)}, ok {zaehl.get('ok', 0)}",
         f"Auffaellig mit Eigenname {out['quote_mit_namen']:.1%} | ohne Eigenname {basis:.1%}\n" if mit else "",
         "## Namen nach Kipp-Quote (>= 2 Saetze)", "| Name | Saetze | auffaellig | Quote |", "|---|---|---|---|"]
    L += [f"| {x['name']} | {x['saetze']} | {x['auffaellig']} | {x['quote']:.0%} |" for x in namen_tab[:40]]
    L += ["\n## Top 40 Verdacht", "| Tag | Stufe | p(Ziel) | p(en) | p(fr) | CER | Namen | Soll | Whisper |", "|---|---|---|---|---|---|---|---|---|"]
    for t, s in rang[:40]:
        L.append(f"| {t} | {s['stufe']} | {s['p_ziel']} | {s['p_en']} | {s['p_fr']} | {s['cer']} | {', '.join(s['namen'])} | "
                 f"{s['soll'][:70]} | {(s['text_frei'] or '')[:70]} |")
    open(os.path.join(werk, "work", f"BERICHT_sprachpruefung_{lg}.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L[:12 + min(15, len(namen_tab))]))
    print(f"-> {pp}")


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    if len(a) < 1:
        sys.exit(__doc__)
    book, lg = a[0], (a[1] if len(a) > 1 else "de")
    if "--paket" in sys.argv:
        paket(book, lg)
    if "--auswerten" in sys.argv:
        auswerten(book, lg)
