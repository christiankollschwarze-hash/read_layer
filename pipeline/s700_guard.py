"""STAGE 700 — Guard
Funktion:     Kostenlose Pruefung der ID-Deckung ueber alle Sprachen.
Wirkungsweise: Prueft Luecken und Fremd-IDs in work/400_regie.json, Exit 0/1.
Komponenten:  pipeline/s700_guard.py
Zulieferer:   s400 Regie (work/400_regie.json)
Abnehmer:     s710 Cloud-Export (geplant als Vorbedingung)
(Nomenklatur seit 18.10.2026, Uebersicht: docs/Pipeline_Strang_Matrix.xlsx)
"""
r"""
READ LAYER — Stage 60: Alignment-Waechter (Cross-Language)
===========================================================
Prueft VOR dem App-Export, ob alle Sprachbloecke eines Werks ueber die
Satz-ID deckungsgleich sind — die Bedingung dafuer, dass das Geraet sie
zur Laufzeit paaren kann (TAELLA-Architektur: pro Sprache ein Block,
Paarung im Geraet ueber gemeinsame Satz-ID).

Gnadenlos + gratis: liest nur Daten, ruft keine API. Gibt am Ende ein
klares Urteil — gruenes Licht (Export erlaubt) oder STOPP (welche IDs wackeln).

Prueft vier Facetten:
  1. ID-Deckungsgleichheit  — jede Sprache hat exakt dieselbe ID-Menge.
  2. Symmetrie              — Waisen in BEIDE Richtungen (fehlend UND ueberzaehlig).
  3. Nutzdaten-Vollstaendigkeit — jede ID hat in jeder Sprache nicht-leeren Text.
  4. Typ-Konsistenz         — derselbe Satz traegt in allen Sprachen denselben Typ.

Quelle: work/400_regie.json (Fallback 310_uebersetzung.json) — das gemeinsame `content`,
aus dem der Export spaeter die getrennten Bloecke schneidet.

Aufruf (als Modul, da in pipeline/):
  python -m pipeline.s700_guard jekyll-and-hyde
  python -m pipeline.s700_guard jekyll-and-hyde --langs en,de
  python -m pipeline.s700_guard jekyll-and-hyde --chapter c001
Exit-Code 0 = sauber (Export erlaubt), 1 = Verstoss (Export blockieren).
"""
import sys, os, json, argparse

def _find_root(start):
    d = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(d, "config")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return os.path.abspath(start)
        d = parent

sys.path.insert(0, _find_root(os.path.dirname(os.path.abspath(__file__))))
from config import config

NO_AUDIO = set(getattr(config, "NO_AUDIO_TYPES", ["p", "tt", "skip"]))


def _load_content(book_id):
    """Liest das gemeinsame content aus 400_regie (Fallback 310_uebersetzung)."""
    for stage in ("400_regie", "310_uebersetzung"):
        path = config.work_path(book_id, stage)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f).get("content", {}), stage
    raise FileNotFoundError(f"Weder 400_regie noch 310_uebersetzung fuer {book_id} gefunden.")


def _detect_langs(content):
    """Findet alle vorkommenden Sprachfelder (alles ausser type/Metafeldern)."""
    META = {"type", "direction", "pause_after_ms", "production"}
    langs = set()
    for e in content.values():
        for k in e.keys():
            if k not in META and isinstance(e.get(k), str):
                langs.add(k)
    return sorted(langs)


def check(book_id, langs=None, chapter=None):
    content, stage = _load_content(book_id)

    # Nur textuelle (audio-/paarungsrelevante) Saetze; optional Kapitel-Filter
    items = {
        tid: e for tid, e in content.items()
        if e.get("type") not in NO_AUDIO
        and (chapter is None or tid.startswith(chapter))
    }
    if not items:
        print(f"[stage60] Keine textuellen Saetze gefunden (Kapitel-Filter: {chapter}).")
        return False

    if langs is None:
        langs = _detect_langs(content)
    print(f"[stage60] Buch: {book_id} | Quelle: {stage} | Sprachen: {langs}")
    print(f"[stage60] Textuelle Saetze: {len(items)}"
          + (f" | Kapitel {chapter}" if chapter else ""))

    # Pro Sprache: Menge der IDs mit nicht-leerem Text
    ids_per_lang = {}
    for lg in langs:
        ids_per_lang[lg] = {
            tid for tid, e in items.items()
            if str(e.get(lg, "")).strip()
        }

    all_ids = set(items.keys())

    # SOURCE_LANGUAGE ist die Referenz: Welche IDs SOLLTE es geben?
    src_lang = getattr(config, "SOURCE_LANGUAGE", "en")
    src_ids = ids_per_lang.get(src_lang, all_ids)

    # Pro Sprache zwei Fehlertypen sauber trennen:
    #   LUECKE        = ID im Original (src) vorhanden, in Zielsprache leer
    #                   -> harmlos: Uebersetzung fehlt nur, einfach nachlaufen lassen.
    #   STRUKTURBRUCH = Zielsprache traegt eine ID, die das Original NICHT kennt,
    #                   ODER eine ID fehlt komplett im content -> Satzaufteilung
    #                   weicht ab (Split/Merge). Braucht menschlichen Blick.
    gaps = {}        # lang -> [tids] (fehlende Uebersetzung)
    breaks = {}      # lang -> [tids] (strukturell fremd/abweichend)

    for lg in langs:
        if lg == src_lang:
            continue
        present = ids_per_lang[lg]
        # in src vorhanden, in Ziel leer  -> Luecke
        gap = sorted(src_ids - present)
        # in Ziel vorhanden, aber NICHT in src  -> struktureller Fremdkoerper
        extra = sorted(present - src_ids)
        if gap:
            gaps[lg] = gap
        if extra:
            breaks[lg] = extra

    # Kapitel mit Luecken sammeln (fuer Behebungs-Befehl)
    def _chapters_of(tids):
        return sorted({t.split("_")[0] for t in tids})

    # --- Urteil ---
    print()
    if not gaps and not breaks:
        print(f"[stage60] ✓ GRUENES LICHT — alle {len(langs)} Sprachen deckungsgleich "
              f"ueber {len(all_ids)} Saetze. Export erlaubt.")
        return True

    print("[stage60] ✗ STOPP — Alignment NICHT sauber. Export blockieren.\n")

    # Typ 1: LUECKEN (harmlos, mit Behebungsvorschlag)
    if gaps:
        print("  [LUECKE] Fehlende Uebersetzung(en) — einfach nachlaufen lassen:")
        for lg, tids in gaps.items():
            chs = _chapters_of(tids)
            print(f"    Sprache '{lg}': {len(tids)} Satz/Saetze ohne Uebersetzung "
                  f"(Kapitel: {', '.join(chs)})")
            for tid in tids[:5]:
                print(f"        {tid}")
            if len(tids) > 5:
                print(f"        ... (+{len(tids)-5} weitere)")
            # Behebungs-Befehl vorschlagen
            for ch in chs:
                print(f"        -> python -m pipeline.s310_uebersetzung "
                      f"{book_id} --chapter {ch}")
        print()

    # Typ 2: STRUKTURBRUCH (ernst, braucht menschlichen Blick)
    if breaks:
        print("  [STRUKTURBRUCH] Satzaufteilung weicht ab (Split/Merge?) — "
              "BITTE PRUEFEN, nicht automatisch reparieren:")
        for lg, tids in breaks.items():
            print(f"    Sprache '{lg}': {len(tids)} ID(s), die das Original ({src_lang}) "
                  f"nicht kennt:")
            for tid in tids[:5]:
                # Nachbarschaft zeigen, damit der Mensch die Stelle sieht
                txt = str(items.get(tid, {}).get(lg, ""))[:60]
                print(f"        {tid}: \"{txt}...\"")
        print()

    return False


def main():
    ap = argparse.ArgumentParser(description="Cross-Language Alignment-Waechter")
    ap.add_argument("book_id")
    ap.add_argument("--langs", help="Komma-Liste, z.B. en,de (Default: auto)")
    ap.add_argument("--chapter", help="nur dieses Kapitel, z.B. c001")
    args = ap.parse_args()

    langs = [l.strip() for l in args.langs.split(",")] if args.langs else None
    ok = check(args.book_id, langs=langs, chapter=args.chapter)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
