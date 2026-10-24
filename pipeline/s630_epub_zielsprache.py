"""STAGE 630 — ePub Zielsprache
Funktion:     EPUB3 je Zielsprache.
Wirkungsweise: Baut aus work/400_regie.json (Absatz- und Kapitelmarken) das zielsprachige EPUB; Drama-Pfad mit Rollen.
Komponenten:  pipeline/s630_epub_zielsprache.py, s620_epub_original (Bausteine)
Zulieferer:   s400 Regie (work/400_regie.json), s600 Klappentext, s610 Cover, s410 Casting (Drama)
Abnehmer:     Auslieferung (fassungen/<lang>/output/<werk>.epub)
(Nomenklatur seit 18.10.2026, Uebersicht: docs/Pipeline_Strang_Matrix.xlsx)

--- Bisherige Beschreibung ---

READ LAYER — Stage 31: Uebersetztes EPUB (Katalog) — AUS KANONISCHER QUELLE
===========================================================================
Erzeugt das fremdsprachige EPUB (z.B. DE) NICHT durch Neu-Uebersetzung,
sondern aus der bereits geprueften, satzgenauen Uebersetzung in 400_regie
(dem "doppelt gekneteten Teig"): satzgenau uebersetzt, Backtranslation-
geprueft, vom Alignment-Waechter (Stage 60) bestaetigt.

Prinzip:
  - Die `p`-Marken in den aligned Daten sind die Absatzgrenzen (dieselbe
    Struktur, aus der auch das EN-EPUB gebaut wurde -> Absatzstruktur deckt
    sich mit dem EN-EPUB, weil die Saetze aligned sind).
  - Saetze (s/dl/qt/ep) zwischen zwei `p`-Marken werden zu EINEM Absatz
    zusammengesetzt. `h`-Tags werden Kapitel-Titel.
  - Es findet KEIN LLM-Call statt. Reine Datenarbeit, gratis, deterministisch.
  - Cover 1:1; TITEL kommt jetzt aus der Fassung (Stage 08b --work):
    fassung.titel der Zielsprache, Fallback Originaltitel. dc:language = Ziel.
  - Klappentext = der zielsprachige aus 600_klappentext.json.

Aufruf: python -m pipeline.s630_epub_zielsprache the-legend-of-sleepy-hollow --lang de
"""

import os, json
from config import config
from pipeline import s620_epub_original as epub

NO_AUDIO = set(getattr(config, "NO_AUDIO_TYPES", ["p", "tt", "skip"]))


def _chapter_of(tag_id: str) -> str:
    return tag_id.split("_")[0]


_ROLLEN_DE = {"DUKE SENIOR": "HERZOG SENIOR", "DUKE FREDERICK": "HERZOG FREDERICK", "FIRST LORD": "ERSTER EDELMANN",
              "SECOND LORD": "ZWEITER EDELMANN", "FIRST PAGE": "ERSTER PAGE", "SECOND PAGE": "ZWEITER PAGE",
              "PAGES": "PAGEN", "SONG": "LIED"}


def _rollen_namen(book_id: str, target: str) -> dict:
    """Sprechername je Figur in der Zielsprache: casting.json name_de, sonst Tabelle, sonst Original."""
    if target == config.SOURCE_LANGUAGE:
        return {}
    namen = dict(_ROLLEN_DE) if target == "de" else {}
    try:
        c = json.load(open(os.path.join(config.work_dir(book_id), "casting.json"), encoding="utf-8"))
        for e in c["plan"]["ensemble"]:
            if e.get("figur") and e.get(f"name_{target}"):
                namen[e["figur"]] = e[f"name_{target}"].upper()
    except Exception:
        pass
    return namen


def _build_drama_chapters(book_id: str, content: dict, target: str, src: str):
    """Drama: je Replik ein Absatz "SPRECHER. Text ...", Regieanweisungen eigene Absaetze,
    skip-Tags (bereinigte Zeilennummern, Dubletten, Sprecherzeilen) fallen weg."""
    namen = _rollen_namen(book_id, target)
    chapters = {}
    for tag_id, e in content.items():
        ch = _chapter_of(tag_id)
        typ = e.get("type")
        text = str(e.get(target, "") or "").strip() or str(e.get(src, "") or "").strip()
        slot = chapters.setdefault(ch, {"title": "", "paras": [], "key": None})
        if typ == "h":
            if text and not slot["title"]:
                slot["title"] = text
            continue
        if typ in ("p", "tt", "skip") or not text:
            continue
        if typ == "dl":
            key = (e.get("sprecher"), e.get("replik"))
            if key != slot["key"]:
                sp = e.get("sprecher") or ""
                slot["paras"].append([f"{namen.get(sp, sp)}." if sp else ""])
                slot["key"] = key
            slot["paras"][-1].append(text)
        else:
            slot["paras"].append([text])
            slot["key"] = None
    return [(chapters[ch]["title"], [" ".join(x for x in p if x) for p in chapters[ch]["paras"] if any(p)])
            for ch in sorted(chapters)]


def _absatzgrenzen(book_id, content, src):
    """22.10.2026: Tag-IDs, nach denen ein Quell-Absatz endet (aus work/modernized/chapter-N.json).
    Der Tagger (200) setzt p-Marken nicht immer (Spiegelschwestern: Prolog ohne eine einzige) ->
    Zielsprachen-EPUB hatte zusammengeklebte Absaetze. Abgleich ueber normalisierten Quelltext;
    ein Kapitel, das nicht sauber aufgeht, bleibt unveraendert (nur p-Marken)."""
    import re as _re
    norm = lambda t: _re.sub(r"[\W_]+", "", str(t)).lower()
    mod = os.path.join(config.work_dir(book_id), "modernized")
    if not os.path.isdir(mod):
        return set()
    saetze = {}
    for tag_id, e in content.items():
        if e.get("type") in ("h", "p", "tt", "skip"):
            continue
        saetze.setdefault(_chapter_of(tag_id), []).append((tag_id, norm(e.get(src, ""))))
    grenzen = set()
    for ch, liste in saetze.items():
        f = os.path.join(mod, f"chapter-{int(ch[1:])}.json")
        if not os.path.exists(f):
            continue
        try:
            paras = [norm(p) for p in json.load(open(f, encoding="utf-8")).get("paragraphs", [])
                     if p != "\u2014\u2014HR\u2014\u2014"]
        except (OSError, ValueError):
            continue
        paras = [p for p in paras if p]
        neu, i, ok = set(), 0, True
        for pn in paras:
            acc = ""
            while i < len(liste) and len(acc) < len(pn):
                acc += liste[i][1]; i += 1
            if acc != pn:
                ok = False; break
            neu.add(liste[i - 1][0])
        if ok and i == len(liste):
            grenzen |= neu
    return grenzen


def _build_chapters_from_stage06(book_id: str, target: str):
    """Rekonstruiert [(titel, [absatz, ...]), ...] in der ZIELSPRACHE aus 400_regie.
    Absatzgrenzen = `p`-Marken; `h`-Tags = Kapiteltitel; Saetze dazwischen
    werden zu Absaetzen zusammengefuegt. Faellt eine Uebersetzung aus, bleibt
    der Originaltext stehen (sichtbar statt verschwunden)."""
    path = config.work_path(book_id, "400_regie")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"400_regie fehlt fuer {book_id} — erst Audio-Textkette (50-56) laufen lassen.")
    data = json.load(open(path, encoding="utf-8"))
    content = data["content"]
    src = config.SOURCE_LANGUAGE
    if (data.get("meta") or {}).get("modus") == "drama":
        return _build_drama_chapters(book_id, content, target, src)

    # 22.10.2026: fehlende p-Marken (Tagger) aus den Quell-Absaetzen ergaenzen
    grenzen = _absatzgrenzen(book_id, content, src)

    # nach Kapitel gruppieren, Reihenfolge der IDs beibehalten
    chapters = {}   # chap_id -> {"title": str, "paras": [[satz,...], ...]}
    for tag_id, e in content.items():
        ch = _chapter_of(tag_id)
        typ = e.get("type")
        # Zieltext bevorzugen, sonst Originaltext als sichtbarer Fallback
        text = str(e.get(target, "") or "").strip() or str(e.get(src, "") or "").strip()

        slot = chapters.setdefault(ch, {"title": "", "paras": []})

        if typ == "h":
            if text and not slot["title"]:
                slot["title"] = text
            continue
        if typ in ("p", "tt", "skip"):
            # Absatzgrenze: neuen (leeren) Absatz beginnen
            slot["paras"].append([])
            continue
        # echter Satz (s/dl/qt/ep/...)
        if not slot["paras"]:
            slot["paras"].append([])
        if text:
            slot["paras"][-1].append(text)
        if tag_id in grenzen:
            slot["paras"].append([])

    # in das von build_epub erwartete Format giessen: (title, [absatz_string, ...])
    out = []
    for ch in sorted(chapters.keys()):
        slot = chapters[ch]
        paras = [" ".join(s for s in p if s) for p in slot["paras"]]
        paras = [p for p in paras if p.strip()]    # leere Absaetze raus
        title = slot["title"] or ""
        out.append((title, paras))
    return out


def run(book_id: str, target: str = "de", lang: str = None):
    if lang: target = lang
    src = config.SOURCE_LANGUAGE
    if target == src:
        print(f"[stage31] Zielsprache == Quellsprache ({src}) -> nimm Stage 30 direkt.")
        return epub.run(book_id)

    print(f"[stage31] Baue {target}-EPUB aus kanonischer Quelle (400_regie), "
          f"KEINE Neu-Uebersetzung ...")
    chapters = _build_chapters_from_stage06(book_id, target)
    # Mobil-Absaetze wie beim EN-EPUB anwenden (gleiche Darstellung)
    chapters = [(t, epub._split_for_mobile(paras)) for t, paras in chapters]

    n_paras = sum(len(p) for _, p in chapters)
    print(f"[stage31] {len(chapters)} Kapitel, {n_paras} Absaetze aus 400_regie uebernommen.")

    # lang=target -> dc:language = Ziel UND Titel = fassung.titel (Fallback Originaltitel)
    meta = epub._gather_meta(book_id, lang=target)

    # Klappentext in der Zielsprache (aus 600_klappentext.json)
    sp = config.work_path(book_id, "600_klappentext")
    if os.path.exists(sp):
        try:
            stage09 = json.load(open(sp, encoding="utf-8"))
            meta["blurb_html"] = epub._blurb_xhtml(stage09, target, target,
                                                   epub._is_modernized(book_id))
        except Exception as e:
            print(f"[stage31] HINWEIS: Klappentext uebersprungen ({type(e).__name__}).")

    out_dir = os.path.join(config.book_dir(book_id), "fassungen", target, "output")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{book_id}.epub")
    epub.build_epub(meta, chapters, out_path)

    print(f"[stage31] EPUB ({target}) -> {out_path}")
    print(f"[stage31] Kapitel: {len(chapters)}, Absaetze: {n_paras}, "
          f"Klappentext: {'ja' if meta.get('blurb_html') else 'nein'}, "
          f"Titel: {meta['title']!r}, Sprache: {target}")
    return out_path


if __name__ == "__main__":
    import sys
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    lang = "de"
    if "--lang" in sys.argv:
        lang = sys.argv[sys.argv.index("--lang") + 1]
    run(args[0] if args else "the-legend-of-sleepy-hollow", target=lang)
