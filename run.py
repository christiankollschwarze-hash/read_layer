"""
READ LAYER — Orchestrator
=========================
Fuehrt eine Produktlinie fuer einen Titel aus, Stage fuer Stage.
Nomenklatur seit 18.10.2026: pipeline/sNNN_<aufgabe>.py, Checkpoint work/NNN_<aufgabe>.json.
Hunderter = Phase (1 Eingang, 2 Text, 3 Uebersetzung, 4 Regie & Besetzung, 5 Audio,
6 Ausgabeformate, 7 Auslieferung). Uebersicht: docs/Pipeline_Strang_Matrix.xlsx

VORBEDINGUNG (manuell, NICHT Teil dieses Laufs):
  1. tools/s100_anlegen.py --gutenberg <id>  ODER  <eingabe.json>  -> Autor + Buch + raw.txt
     (User-ePub: python -m pipeline.s150_epub_import ...)
  2. python -m pipeline.s110_wikidata --author <slug> --propose
     python -m pipeline.s110_wikidata --author <slug> --confirm <Q-ID>

Linien:
  epub : 120 Modernisierung -> 600 Klappentext -> 610 Cover -> 615 Cover final -> 620 ePub Original -> 630 ePub Zielsprache -> 640 Teaser
  audio: 120 -> 200 Tagging -> 210 Profil -> 300 Vorübersetzung -> 310 Uebersetzung -> 320 Integritaet
         -> 330 Rueckuebersetzung -> 400 Regie -> 410 Casting -> 500 Vertonung -> 710 Cloud-Export
  ausserhalb: 340 Wort-Alignment, 420 Sprecher, 520 Wortzeiten, 700 Guard (Cockpit, Bats, Modal)

Aufruf:
  python run.py <book_id>                     # EPUB-Linie (Default)
  python run.py <book_id> --line audio        # Audio-Linie
  python run.py <book_id> --from 620          # ab Stage 620
  python run.py <book_id> --to 400            # BIS EINSCHLIESSLICH Stage 400, dann Stopp
  python run.py <book_id> --from 120 --to 400 # Bereich (Textkette OHNE Vertonung)
  python run.py <book_id> --only 630          # nur eine Stage
  python run.py <book_id> --lang de           # NUR diese Zielsprache (statt aller)
  python run.py <book_id> --force             # Checkpoints ignorieren, alles neu
  python run.py <book_id> --live              # RUN_MODE=live fuer diesen Lauf

TIPP (Audio-Linie ohne TTS vorbereiten):
  python run.py <book_id> --line audio --to 400 --live
  -> laeuft 120..400 (Text-/Datenkette, erzeugt work/400_regie.json), STOPPT VOR 500 (Vertonung).

SPRACHBEWUSSTSEIN:
  500, 630 und 710 sind PER-LANG: sie laufen pro Zielsprache aus config.TARGET_LANGUAGES
  (oder --lang). Ihr Checkpoint prueft die sprachspezifische Ausgabe, daher gilt Deutsch
  nie als fertig, nur weil Englisch fertig ist. Text-/Datenstages sind sprachUNabhaengig.

Checkpoint: ist die Ausgabe einer Stage (fuer die jeweilige Sprache) schon da,
wird sie uebersprungen (ausser --force).
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import config


# ---- Checkpoint-Proben --------------------------------------------------
# Sprachunabhaengige Stages: lang wird ignoriert.
def _modernized(book_id, lang=None):
    # Fertig erst, wenn raw_modernized.txt geschrieben ist (entsteht am ENDE von Stage 11).
    # Nur Kapitel-Checkpoints = abgebrochener Lauf -> Stage 11 setzt fort (10.10.2026).
    d = os.path.join(config.work_dir(book_id), "modernized")
    mod = os.path.join(config.book_dir(book_id), "raw_modernized.txt")
    return (os.path.exists(mod) and os.path.isdir(d)
            and any(f.startswith("chapter-") for f in os.listdir(d)))

def _work_json(suffix):
    return lambda book_id, lang=None: os.path.exists(config.work_path(book_id, suffix))

def _cover_png(book_id, lang=None):
    # QF-2 (18.10.2026): Stage 21 speichert bei JPEG-Antwort cover.jpg -- beide gelten.
    img = os.path.join(config.book_dir(book_id), "images")
    return any(os.path.exists(os.path.join(img, n)) for n in ("cover.png", "cover.jpg"))
    
def _cover_final(book_id, lang=None):
    # 615 (18.10.2026): beide fertigen Cover vorhanden und juenger als die Illustration
    img = os.path.join(config.book_dir(book_id), "images")
    ill = [os.path.join(img, n) for n in ("cover.png", "cover.jpg") if os.path.exists(os.path.join(img, n))]
    if not ill:
        return False
    t = os.path.getmtime(ill[0])
    for L in ("en", "de"):
        p = os.path.join(config.book_dir(book_id), "fassungen", L, "output", f"cover_final_{L}.jpg")
        if not os.path.exists(p) or os.path.getmtime(p) < t:
            return False
    return True

# Sprachbewusste Stages: pruefen die Ausgabe FUER DIESE Sprache.
def _epub(lang_fixed):
    def check(book_id, lang=None):
        L = lang_fixed or lang or config.SOURCE_LANGUAGE   # 22.10.: Quelle je Werk
        p = os.path.join(config.book_dir(book_id), "fassungen", L, "output", f"{book_id}.epub")
        return os.path.exists(p)
    return check

def _audio_done(book_id, lang=None):
    """Audio gilt fuer EINE Sprache als fertig, wenn fassungen/<lang>/audio existiert
    UND mindestens so viele WAVs enthaelt wie es Audio-Tags in 400_regie gibt.
    So kann Deutsch nie 'fertig' sein, nur weil Englisch vertont wurde, und ein
    unvollstaendiger (abgebrochener) Lauf wird beim Neustart fortgesetzt."""
    if not lang:
        return False
    audio_dir = os.path.join(config.book_dir(book_id), "fassungen", lang, "audio")
    if not os.path.isdir(audio_dir):
        return False
    n_wav = len([f for f in os.listdir(audio_dir) if f.endswith(".wav")])
    # Soll-Zahl aus 400_regie (Audio-Tags, ohne NO_AUDIO_TYPES und ohne leere Felder)
    try:
        import json
        data = json.load(open(config.work_path(book_id, "400_regie"), encoding="utf-8"))
        soll = 0
        for _tid, entry in data["content"].items():
            if entry.get("type") in config.NO_AUDIO_TYPES:
                continue
            if str(entry.get(lang, "")).strip():
                soll += 1
        if soll == 0:
            return False
        return n_wav >= soll
    except Exception:
        # 400_regie nicht lesbar -> konservativ: nur als fertig werten, wenn ueberhaupt WAVs da
        return n_wav > 0

def _casting_done(book_id, lang=None):
    """Stage 57 (Casting): fertig, wenn work/casting.json existiert -- oder das Werk
    gar kein Casting braucht (book.json besetzung_modus fehlt und CASTING_AKTIV aus)."""
    try:
        from pipeline import s410_casting
        if not s410_casting.aktiv(book_id):
            return True
        return os.path.exists(s410_casting.casting_pfad(book_id))
    except Exception:
        return True

def _casting_tor_offen(book_id):
    """QF-4 (18.10.2026): Liefert den Tor-Status, wenn Casting aktiv und NICHT freigegeben
    ist (sonst None). Stage 58 startet nur bei freigegebenem Tor."""
    try:
        from pipeline import s410_casting
        if not s410_casting.aktiv(book_id):
            return None
        import json
        pfad = s410_casting.casting_pfad(book_id)
        tor = json.load(open(pfad, encoding="utf-8")).get("tor") if os.path.exists(pfad) else "fehlt"
    except Exception:
        return None
    return None if tor == "freigegeben" else str(tor)

def _assembler_done(book_id, lang=None):
    """Assembler-Ausgabe pro Sprache: fassungen/<lang>/output/<book>.m4b o.ae.
    Fallback: work/stage08.json (sprachuebergreifend) -- aber per-lang bevorzugt."""
    if lang:
        out = os.path.join(config.book_dir(book_id), "fassungen", lang, "output")
        if os.path.isdir(out) and any(f.endswith((".m4b", ".mp3", ".wav")) for f in os.listdir(out)):
            return True
    return False

def _cloud_export_done(book_id, lang=None):
    """Stage 60 gilt als fertig, wenn der lokale Checkpoint 710_cloud_export_<lang>.json existiert."""
    if not lang:
        return False
    return os.path.exists(config.work_path(book_id, f"710_cloud_export_{lang}"))

# ---- Stage-Definitionen -------------------------------------------------
# per_lang=True  -> ueber Zielsprachen iterieren, run(book_id, lang=lang)
# per_lang=False -> einmal run(book_id)
EPUB_LINE = [
    {"key": "120", "module": "pipeline.s120_modernisierung",       "done": _modernized,                  "per_lang": False},
    {"key": "600", "module": "pipeline.s600_klappentext",           "done": _work_json("600_klappentext"),        "per_lang": False},
    {"key": "610", "module": "pipeline.s610_cover",           "done": _cover_png,                    "per_lang": False},
    {"key": "615", "module": "pipeline.s615_cover_final",     "done": _cover_final,                  "per_lang": False},
    {"key": "620", "module": "pipeline.s620_epub_original",            "done": _epub(None), "per_lang": False},
    {"key": "630", "module": "pipeline.s630_epub_zielsprache", "done": _epub(None),                   "per_lang": True},
    {"key": "640", "module": "pipeline.s640_teaser",          "done": _work_json("640_teaser"),         "per_lang": False},
]

AUDIO_LINE = [
    {"key": "120", "module": "pipeline.s120_modernisierung",        "done": _modernized,            "per_lang": False},
    {"key": "200", "module": "pipeline.s200_tagging",           "done": _work_json("200_tagging"),  "per_lang": False},
    {"key": "210", "module": "pipeline.s210_profil",         "done": _work_json("210_profil"),  "per_lang": False},
    {"key": "300", "module": "pipeline.s300_voruebersetzung",    "done": _work_json("300_voruebersetzung"),  "per_lang": False},
    {"key": "310", "module": "pipeline.s310_uebersetzung",       "done": _work_json("310_uebersetzung"),  "per_lang": False},
    {"key": "320", "module": "pipeline.s320_integritaet",        "done": _work_json("320_integritaet"), "per_lang": False},
    {"key": "330", "module": "pipeline.s330_rueckuebersetzung",  "done": _work_json("330_rueckuebersetzung"), "per_lang": False},
    {"key": "400", "module": "pipeline.s400_regie",        "done": _work_json("400_regie"),  "per_lang": False},
    {"key": "410", "module": "pipeline.s410_casting",          "done": _casting_done,          "per_lang": False},
    {"key": "500", "module": "pipeline.s500_vertonung_gemini",        "done": _audio_done,            "per_lang": True},
    # QF-5 (18.10.2026): Stage 59 defekt (Signatur/Pfade), bis Neudefinition (S-3) aus der Linie.
    # {"key": "650", "module": "pipeline.s650_hoerbuch",        "done": _assembler_done,        "per_lang": True},
    {"key": "710", "module": "pipeline.s710_cloud_export",     "done": _cloud_export_done,     "per_lang": True},
]

LINES = {"epub": EPUB_LINE, "audio": AUDIO_LINE}


def _import_stage(module_path):
    import importlib
    return importlib.import_module(module_path)


def _target_languages(only_lang=None):
    """Welche Zielsprachen dieser Lauf bedient. --lang schraenkt auf eine ein."""
    if only_lang:
        return [only_lang]
    return list(config.TARGET_LANGUAGES)


def _stage58_module(book_id, lang):
    """Weiche pro Fassung: Thorsten (DE lokal) oder Cloud-TTS.
    18.10.2026: LibriVox-Audio-Gleis (schnitt_lib) archiviert."""
    if lang == "de" and getattr(config, "TTS_ENGINE_DE", "gemini") == "thorsten":
        return "pipeline.s501_vertonung_thorsten"
    return "pipeline.s500_vertonung_gemini"


def _ctx(book_id, key, lang=None):
    """Token-/Kostenzaehler: Werk + Stage fuer alle API-Aufrufe dieser Stage."""
    try:
        from pipeline import usage_log
        usage_log.set_context(book_id, f"{key}_{lang}" if lang else key)
    except Exception:
        pass


def _run_one(stage, book_id, force, only_lang=None):
    """Fuehrt eine Stage aus. per_lang -> pro Zielsprache, mit sprachbewusstem Skip.
    Stage 58: Weiche PRO FASSUNG (Engine je Sprache)."""
    if stage["per_lang"]:
        for lang in _target_languages(only_lang):
            if not force and stage["done"](book_id, lang):
                print(f"[skip] Stage {stage['key']} [{lang}] — Ausgabe vorhanden")
                continue
            module = stage["module"]
            if stage["key"] == "500":
                module = _stage58_module(book_id, lang)   # Gleis pro Fassung stellen
                if module.endswith("s501_vertonung_thorsten"):
                    print(f"  -> Stage 58 [{lang}] (Thorsten lokal)")
                else:
                    print(f"  -> Stage 58 [{lang}] (Cloud-TTS)")
            else:
                print(f"  -> Stage {stage['key']} [{lang}]")
            _ctx(book_id, stage["key"], lang)
            _import_stage(module).run(book_id, lang=lang)
    else:
        _ctx(book_id, stage["key"])
        if stage["key"] == "610" and force:   # QF-2: --force erreicht Stage 21
            _import_stage(stage["module"]).run(book_id, force=True)
        else:
            _import_stage(stage["module"]).run(book_id)
    return True


def run_pipeline(book_id, line="epub", start_from=None, stop_to=None,
                 only=None, force=False, only_lang=None):
    stages = LINES[line]
    config.werk_sprachen(book_id)   # Sprachweiche je Werk (22.10.2026)
    print("=" * 60)
    print(f"READ LAYER — Pipeline ({line}-Linie)")
    print(f"  Titel: {book_id}")
    print(f"  Modus: {config.RUN_MODE}")
    tgt = _target_languages(only_lang)
    print(f"  Sprachen: {config.SOURCE_LANGUAGE} -> {tgt}"
          f"{'  (--lang: nur '+only_lang+')' if only_lang else ''}")
    if start_from or stop_to:
        print(f"  Bereich: {'ab '+start_from if start_from else 'Anfang'} "
              f"{'bis '+stop_to if stop_to else 'Ende'}")
    print("=" * 60)

    order = [s["key"] for s in stages]
    if stop_to is not None and stop_to not in order:
        print(f"[FEHLER] --to {stop_to}: Stage gibt es in der {line}-Linie nicht "
              f"(erlaubt: {', '.join(order)}).")
        return False
    if start_from is not None and start_from not in order:
        print(f"[FEHLER] --from {start_from}: Stage gibt es in der {line}-Linie nicht "
              f"(erlaubt: {', '.join(order)}).")
        return False

    started = False if start_from else True
    t_start = time.time()

    for stage in stages:
        key = stage["key"]
        if only is not None and key != only:
            continue
        if not started:
            if key == start_from:
                started = True
            else:
                print(f"[skip] Stage {key} (vor --from {start_from})")
                continue

        # Sprachunabhaengige Stages: hier (einmal) auf Checkpoint pruefen.
        # Sprachbewusste Stages (per_lang): NICHT hier ueberspringen -- der Skip
        # passiert PRO SPRACHE in _run_one, sonst wuerde eine fehlende Sprache
        # mit einer fertigen verwechselt.
        if (not force and only is None and not stage["per_lang"]
                and stage["done"](book_id)):
            print(f"[skip] Stage {key} — Ausgabe vorhanden")
            if stop_to is not None and key == stop_to:
                print(f"\n[stop] Stage {stop_to} erreicht (--to) — Halt.")
                break
            continue

        if key == "500":
            tor = _casting_tor_offen(book_id)
            if tor:
                print(f"\n[STOPP] Stage 58: Casting-Tor ist '{tor}'. Erst Hoerprobe und "
                      f"'py -3.11 -m pipeline.s410_casting {book_id} --freigeben', "
                      f"dann weiter mit --from 500.")
                return False

        print(f"\n--- Stage {key} ({stage['module'].split('.')[-1]}) ---")
        t0 = time.time()
        try:
            _run_one(stage, book_id, force, only_lang=only_lang)
        except Exception as e:
            print(f"\n[FEHLER] Stage {key} abgebrochen: {e}")
            print(f"[FEHLER] Nach Fix mit --from {key} fortsetzen.")
            return False
        print(f"--- Stage {key} fertig ({time.time()-t0:.1f}s) ---")

        if stop_to is not None and key == stop_to:
            print(f"\n[stop] Stage {stop_to} erreicht (--to) — Halt.")
            break

    print("\n" + "=" * 60)
    print(f"Pipeline abgeschlossen in {time.time()-t_start:.1f}s")
    print("=" * 60)
    return True


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith("--"):
        print("Aufruf: python run.py <book_id> [--line epub|audio] [--from XX] "
              "[--to XX] [--only XX] [--lang de] [--force] [--live]")
        sys.exit(1)

    book_id = args[0]
    line = "epub"
    start_from = stop_to = only = only_lang = None
    force = False

    if "--live" in args:
        config.RUN_MODE = "live"
    if "--force" in args:
        force = True
    if "--line" in args:
        line = args[args.index("--line") + 1]
    if "--from" in args:
        start_from = args[args.index("--from") + 1]
    if "--to" in args:
        stop_to = args[args.index("--to") + 1]
    if "--only" in args:
        only = args[args.index("--only") + 1]
    if "--lang" in args:
        only_lang = args[args.index("--lang") + 1]

    if line not in LINES:
        print(f"Unbekannte Linie '{line}'. Erlaubt: {', '.join(LINES)}")
        sys.exit(1)

    run_pipeline(book_id, line=line, start_from=start_from, stop_to=stop_to,
                 only=only, force=force, only_lang=only_lang)


if __name__ == "__main__":
    main()
