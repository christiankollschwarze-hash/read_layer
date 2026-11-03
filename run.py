"""
READ LAYER — Orchestrator (Phase 2, Fundament 6, 01.11.2026)
============================================================
Eine Kette fuer jedes Werk, Reihenfolge laut Gate-Katalog (pipeline.status.STAGES):
  080 090 095 100 110 150 115 120 190 195 200 210 300 310 320 330 340 400 410 420
  500 510 530 520 540 600 610 615 620 630 640 650 700 710
- Welche Stages laufen bzw. entfallen, kommt aus der Bestellung in book.json (095, pipeline.kette.bedarf
  -> status.bedarf_setzen). Linien (--line epub/audio) gibt es nicht mehr.
- Jede Stage startet nur bei freiem Vorgaenger-Gate (gate.vorgaenger_frei, Katalog-Eingaenge aus
  pipeline.kette.VORGAENGER). Gate-Zustaende stehen in work/status.json.
- Exit-Code wie gate.beenden: 0 alles frei, 2 Stopp, 3 Mensch, 1 Fehler (Ausnahme in einer Stage).
  Freigabe: python -m pipeline.status <werk> --entscheiden <stage> frei --wer CK --grund "..."
            (Stopp nur per Admin-Override: --override <stage> --wer CK --rolle admin --grund "...").

Uebergang bis zum Umbau der Stages (Phase 2, je Stage):
- Stages ohne Modul laufen nicht in der Kette (seit 650 keine mehr); ihre Vorgaenger
  treten an ihre Stelle (kette.wirksame_vorgaenger).
- Altstages schreiben noch kein eigenes Gate. run.py bewertet sie mit ihrer bisherigen Ausgabepruefung
  (Altpruefung): Ausgabe vorhanden -> auto, 410 Casting-Tor nicht freigegeben -> mensch, Ausgabe fehlt
  nach Lauf -> stopp. Laeuft eine Altstage ausserhalb von run.py (Bat, Cockpit), gleicht run.py ihren
  Zustand vor der Vorgaengerpruefung ab. Umgebaute Stages (UMGEBAUT) schreiben ihr Gate selbst.

Aufruf:
  python run.py <werk>                    ganze Kette laut Bestellung
  python run.py <werk> --from 600         ab Stage 600
  python run.py <werk> --to 400           bis einschliesslich 400
  python run.py <werk> --only 630         nur eine Stage
  python run.py <werk> --lang de          sprachweise Stages (500 510 520 630 710) nur fuer de
  python run.py <werk> --force            frei/Ausgabe vorhanden ignorieren, neu ausfuehren
  python run.py <werk> --live             RUN_MODE=live fuer diesen Lauf
  python run.py <werk> --plan             nur zeigen: Stage, laeuft/entfaellt, Zustand, Vorgaenger
  python run.py <werk> --wer anna         Nutzer des Laufs (sonst READLAYER_NUTZER bzw. config/rollen.json)

080 Mandant & Rechte ist Querschicht: laeuft bei jedem Aufruf zuerst (auch mit --from/--only);
ohne Berechtigung fuer "lauf" -> Stopp, Exit 2.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import config

# Stages, die ihr Gate selbst ueber gate.py/status.py schreiben (waechst mit jedem Stage-Umbau).
UMGEBAUT = {"080", "090", "095", "100", "110", "115", "120", "150", "190", "195", "200", "210", "300", "310", "320", "330", "340", "400", "410", "420", "500", "510", "530", "520", "540", "600", "610", "615", "620", "630", "640", "650", "700"}


def _neu(modul, **kw):
    """Kettenaufruf einer umgebauten Stage: run(book_id, wer=...) -> auto/mensch/stopp."""
    def f(book_id, b, force, wer):
        import importlib
        return importlib.import_module(modul).run(book_id, wer=wer, **kw)
    return f


# Umgebaute Stages mit eigenem Gate (080 laeuft als Querschicht vorab)
NEU = {"090": _neu("pipeline.s090_eingang"),
       "095": _neu("pipeline.s095_produktwahl"),
       "100": _neu("tools.s100_anlegen"),
       "110": _neu("pipeline.s110_wikidata"),
       "115": _neu("pipeline.s115_fassung"),
       "120": _neu("pipeline.s120_modernisierung"),
       "190": _neu("pipeline.s190_vertrag"),
       "195": _neu("pipeline.s195_teilung"),
       "200": _neu("pipeline.s200_tagging"),
       "210": _neu("pipeline.s210_profil"),
       "300": _neu("pipeline.s300_voruebersetzung"),
       "310": _neu("pipeline.s310_uebersetzung"),
       "320": _neu("pipeline.s320_integritaet"),
       "330": _neu("pipeline.s330_rueckuebersetzung"),
       "340": _neu("pipeline.s340_wortalignment"),
       "400": _neu("pipeline.s400_regie"),
       "410": _neu("pipeline.s410_casting"),
       "420": _neu("pipeline.s420_sprecher"),
       "500": _neu("pipeline.s500_vertonung_gemini"),
       "510": _neu("pipeline.s510_hoerspiel_hybrid"),
       "530": _neu("pipeline.s530_audio_pruefung"),
       "520": _neu("pipeline.s520_wortzeiten"),
       "540": _neu("pipeline.s540_trennung"),
       "600": _neu("pipeline.s600_klappentext"),
       "610": _neu("pipeline.s610_cover"),
       "615": _neu("pipeline.s615_cover_final"),
       "620": _neu("pipeline.s620_epub_original"),
       "630": _neu("pipeline.s630_epub_zielsprache"),
       "640": _neu("pipeline.s640_teaser"),
       "650": _neu("pipeline.s650_hoerbuch"),
       "700": _neu("pipeline.s700_guard"),
       "150": _neu("pipeline.s150_epub_import")}        # --force der Kette laedt raw.txt nicht neu (nur Stage-CLI)


# ---- Altpruefung (Ausgabe vorhanden) ------------------------------------
def _modernized(book_id, lang=None):
    d = os.path.join(config.work_dir(book_id), "modernized")
    mod = os.path.join(config.book_dir(book_id), "raw_modernized.txt")
    return (os.path.exists(mod) and os.path.isdir(d)
            and any(f.startswith("chapter-") for f in os.listdir(d)))


def _work_json(suffix):
    return lambda book_id, lang=None: os.path.exists(config.work_path(book_id, suffix))


def _casting_done(book_id, lang=None):
    from pipeline import s410_casting
    if not s410_casting.aktiv(book_id):
        return True
    return os.path.exists(s410_casting.casting_pfad(book_id))


def _casting_tor(book_id):
    """None = frei (Casting inaktiv oder freigegeben), sonst Tor-Zustand."""
    from pipeline import s410_casting
    if not s410_casting.aktiv(book_id):
        return None
    pfad = s410_casting.casting_pfad(book_id)
    tor = json.load(open(pfad, encoding="utf-8")).get("tor") if os.path.exists(pfad) else "fehlt"
    return None if tor == "freigegeben" else str(tor)


def _cloud_export_done(book_id, lang=None):
    return bool(lang) and os.path.exists(config.work_path(book_id, f"710_cloud_export_{lang}"))


# ---- Altstage-Aufrufe ---------------------------------------------------
def _mod(name):
    import importlib
    return importlib.import_module(name)


# key -> (aufruf(book_id, lang, b, force), fertig(book_id, lang) | None)
ALT = {
    "710": (lambda w, lg, b, f: _mod("pipeline.s710_cloud_export").run(w, lg, force=f), _cloud_export_done),
}
IMMER = {"700"}             # Vertrag vor jeder Auslieferung: laeuft auch bei freiem Gate
MANUELL = set()             # Vorbedingungen ausserhalb der Kette (seit 150 keine mehr)
IN_KETTE = set(ALT) | UMGEBAUT


def _fertig(stage, book_id, lang, b):
    fn = ALT[stage][1]
    if fn is None:
        return False
    try:
        return bool(fn(book_id, lang))
    except Exception:
        return False


# ---- Status der Altstages -----------------------------------------------
def _alt_bewerten(book_id, stage, b, scope=None, wer="run.py"):
    """Altpruefung -> status.json. Rueckgabe Zustand (frei/mensch) oder None (Ausgabe fehlt)."""
    from pipeline import mock, status
    if not _fertig(stage, book_id, scope, b):
        return None
    met = {"modus": mock.modus(), "altpruefung": True}
    if stage == "410":
        tor = _casting_tor(book_id)
        if tor:
            return status.ergebnis(book_id, stage, "mensch", metriken=met, ruecksprung="410", wer=wer,
                                   gruende=[f"Casting-Tor {tor} – Hoerprobe, dann "
                                            f"python -m pipeline.s410_casting {book_id} --freigeben"])
    return status.ergebnis(book_id, stage, "auto", metriken=met, scope=scope, wer=wer,
                           hinweise=["Altpruefung: Ausgabe vorhanden (Stage noch ohne eigenes Gate)"])


def _alt_abgleichen(book_id, stages, b):
    """Altstages, die ausserhalb von run.py gelaufen sind (Bat/Cockpit/CLI), in status.json nachziehen."""
    from pipeline import kette, status
    d = status.laden(book_id)
    for s in stages:
        if s not in ALT or s in UMGEBAUT:
            continue
        st = d["stages"].get(s) or {}
        z = st.get("zustand", "offen")
        if z in ("frei", "entfaellt"):
            continue
        if z == "mensch" and not (s == "410" and (st.get("metriken") or {}).get("altpruefung")):
            continue                                   # echte Mensch-Entscheidung bleibt offen
        langs = kette.sprachen(s, b)
        if langs is None:
            _alt_bewerten(book_id, s, b)
        else:
            for lg in langs:
                if status.zustand(book_id, s, scope=lg) not in status.FREI:
                    _alt_bewerten(book_id, s, b, scope=lg)


# ---- Kette --------------------------------------------------------------
def _stage_ausfuehren(book_id, stage, b, force, only_lang, wer=None):
    """Eine Stage. Rueckgabe Zustand nach dem Lauf: frei | mensch | stopp."""
    from pipeline import kette, mock, status, usage_log
    if stage in NEU:
        usage_log.set_context(book_id, stage)
        NEU[stage](book_id, b, force, wer)
        return status.zustand(book_id, stage)
    if stage in UMGEBAUT:
        raise NotImplementedError(f"Stage {stage}: Kettenaufruf fehlt in NEU")
    aufruf = ALT[stage][0]
    langs = kette.sprachen(stage, b)
    met = {"modus": mock.modus(), "altpruefung": True}
    if langs is None:
        if force or not _fertig(stage, book_id, None, b):
            usage_log.set_context(book_id, stage)
            aufruf(book_id, None, b, force)
        z = _alt_bewerten(book_id, stage, b)
        if z is None and ALT[stage][1] is None:          # Altpruefung ohne Datei
            z = status.ergebnis(book_id, stage, "auto", metriken=met, wer="run.py")
        if z is None:
            z = status.ergebnis(book_id, stage, "stopp", metriken=met, ruecksprung=stage, wer="run.py",
                                gruende=["Altpruefung: Ausgabe fehlt nach Lauf"])
        return z
    for lg in langs:
        if only_lang and lg != only_lang:
            if not _fertig(stage, book_id, lg, b) and status.zustand(book_id, stage, scope=lg) != "offen":
                status.zuruecksetzen(book_id, stage, wer="run.py", grund="Sprache nicht in --lang, Ausgabe fehlt",
                                     scope=lg)
            elif _fertig(stage, book_id, lg, b):
                _alt_bewerten(book_id, stage, b, scope=lg)
            continue
        if force or not _fertig(stage, book_id, lg, b):
            print(f"  -> Stage {stage} [{lg}]")
            usage_log.set_context(book_id, stage, sprache=lg)
            aufruf(book_id, lg, b, force)
        else:
            print(f"[skip] Stage {stage} [{lg}] — Ausgabe vorhanden")
        if _alt_bewerten(book_id, stage, b, scope=lg) is None:
            status.ergebnis(book_id, stage, "stopp", metriken=met, ruecksprung=stage, scope=lg, wer="run.py",
                            gruende=[f"Altpruefung: Ausgabe {lg} fehlt nach Lauf"])
    if not langs:
        return status.ergebnis(book_id, stage, "auto", metriken=met, wer="run.py",
                               hinweise=["keine Sprache laut Bestellung"])
    return status.zustand(book_id, stage)


def plan(book_id):
    from pipeline import kette, status
    b, laeuft, fehler = kette.bedarf_setzen(book_id)
    if fehler:
        print("[STOPP] Bestellung ungueltig: " + "; ".join(fehler))
        return 2
    d = status.laden(book_id)
    print(f"Werk {book_id}  Quelle {b.quellsprache}  Ziele {b.zielsprachen}  Audio {b.audiosprachen()}")
    for s in status.STAGES:
        art = ("laeuft" if s in laeuft else "entfaellt")
        weg = "Kette" if s in IN_KETTE else ("manuell" if s in MANUELL else "nicht gebaut")
        v = kette.wirksame_vorgaenger(s, laeuft, IN_KETTE) if s in laeuft else []
        langs = kette.sprachen(s, b) if s in laeuft else None
        print(f"  {s}  {art:<9} {weg:<12} {status.zustand(book_id, s, d=d):<9}"
              f"{' ' + ','.join(langs) if langs else ''}{'  <- ' + ' '.join(v) if v else ''}")
    return 0


def run_pipeline(book_id, start_from=None, stop_to=None, only=None, force=False, only_lang=None, line=None,
                 wer=None):
    """Kette ausfuehren. Rueckgabe Exit-Code (0 frei, 2 Stopp, 3 Mensch, 1 Fehler)."""
    from pipeline import gate, kette, status, s080_mandant
    config.werk_sprachen(book_id)          # Altschnittstelle config-Globals fuer Altstages
    b, laeuft, fehler = kette.bedarf_setzen(book_id)
    print("=" * 60)
    print(f"READ LAYER — Kette  {book_id}  (Modus {config.RUN_MODE})")
    if fehler:
        print("[STOPP] Bestellung (095) ungueltig: " + "; ".join(fehler))
        status.ergebnis(book_id, "095", "stopp", gruende=fehler, ruecksprung="095", wer="run.py")
        print(f"[STOPP] Bestellung korrigieren: python -m pipeline.s095_produktwahl {book_id} --produkt ...")
        return gate.EXIT["stopp"]
    print(f"  Quelle {b.quellsprache} -> Ziele {b.zielsprachen}  Audio {b.audiosprachen()}"
          f"{'  (--lang ' + only_lang + ')' if only_lang else ''}")
    if b.abgeleitet:
        print(f"  Bestellung abgeleitet (book.json ohne {', '.join(b.abgeleitet)})")
    if line:
        print(f"  Hinweis: --line {line} ist abgeschafft; Stages kommen aus der Bestellung (095).")
    print("=" * 60)

    # 080 Querschicht: jeder Lauf prueft den Nutzer (Gate schreibt Wer/Wann in status.json)
    wer = s080_mandant.nutzer(wer)
    if "080" in laeuft:
        print(f"--- Stage 080 (Nutzer {wer}) ---")
        if s080_mandant.run(book_id, wer=wer) != "auto":
            print(f"\n[STOPP] Stage 080: {wer} darf {book_id} nicht bearbeiten")
            return gate.EXIT["stopp"]

    for n, s in (("--from", start_from), ("--to", stop_to), ("--only", only)):
        if s is not None and status._norm(s) not in status.STAGES:
            print(f"[FEHLER] {n} {s}: unbekannte Stage")
            return 1
    start_from, stop_to, only = [status._norm(x) if x else None for x in (start_from, stop_to, only)]
    idx = status.STAGES.index
    t_start = time.time()
    ergebnis = "auto"

    for s in status.STAGES:
        if only and s != only:
            continue
        if start_from and idx(s) < idx(start_from):
            continue
        if stop_to and idx(s) > idx(stop_to):
            break
        if s == "080":
            continue                                   # oben geprueft
        if s not in laeuft:
            print(f"[entfaellt] Stage {s}")
            continue
        if s not in IN_KETTE:
            print(f"[--] Stage {s}: {'manuelle Vorbedingung' if s in MANUELL else 'noch nicht gebaut'} – uebergangen")
            continue
        if s == "095" and status.ist_frei(book_id, s):
            from pipeline import s095_produktwahl
            if s095_produktwahl.veraltet(book_id):
                status.zuruecksetzen(book_id, s, wer=wer, grund="Bestellung seit Freigabe geaendert")
        if not force and s not in IMMER and status.ist_frei(book_id, s):
            print(f"[skip] Stage {s} — frei")
            continue

        # 700 prueft die Gates je Produkt selbst (Zurueckhalten einzelner Produkte statt Kettenstopp)
        vorg = [] if s == "700" else kette.wirksame_vorgaenger(s, laeuft, IN_KETTE)
        _alt_abgleichen(book_id, vorg, b)
        try:
            gate.vorgaenger_frei(book_id, s, vorg, wer=wer)
        except gate.GateHalt as e:
            print(f"\n[STOPP] Stage {s}: " + "; ".join(e.gruende))
            print(f"[STOPP] Status: python -m pipeline.status {book_id}")
            return e.exit_code

        print(f"\n--- Stage {s} ---")
        t0 = time.time()
        try:
            z = _stage_ausfuehren(book_id, s, b, force, only_lang, wer=wer)
        except gate.GateHalt as e:
            print(f"\n[{e.ergebnis.upper()}] Stage {s}: " + "; ".join(e.gruende))
            return e.exit_code
        except Exception as e:
            status.ergebnis(book_id, s, "stopp", gruende=[f"Fehler: {e}"], ruecksprung=s, wer="run.py")
            print(f"\n[FEHLER] Stage {s} abgebrochen: {e}")
            print(f"[FEHLER] Nach Fix mit --from {s} fortsetzen.")
            return 1
        print(f"--- Stage {s}: {z} ({time.time()-t0:.1f}s) ---")
        if s == "095":
            b, laeuft, _ = kette.bedarf_setzen(book_id, wer=wer)    # neue Bestellung -> Stage-Liste
        if z == "mensch":
            st = (status.laden(book_id)["stages"].get(s) or {}).get("gate") or {}
            print(f"\n[MENSCH] Stage {s}: " + "; ".join(st.get("gruende") or ["Entscheidung offen"]))
            print(f"[MENSCH] python -m pipeline.status {book_id} --entscheiden {s} frei --wer CK --grund \"...\"")
            ergebnis = "mensch"
            break
        if z == "stopp":
            st = (status.laden(book_id)["stages"].get(s) or {}).get("gate") or {}
            print(f"\n[STOPP] Stage {s}: " + "; ".join(st.get("gruende") or []))
            ergebnis = "stopp"
            break

    print("\n" + "=" * 60)
    print(f"Kette beendet: {ergebnis} ({time.time()-t_start:.1f}s)")
    print("=" * 60)
    return gate.EXIT[ergebnis]


def main(argv=None):
    ap = argparse.ArgumentParser(description="READ LAYER – Kette laut Bestellung (095) und Gate-Katalog")
    ap.add_argument("book_id")
    ap.add_argument("--from", dest="start_from")
    ap.add_argument("--to", dest="stop_to")
    ap.add_argument("--only")
    ap.add_argument("--lang")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--wer")
    ap.add_argument("--line", help=argparse.SUPPRESS)        # abgeschafft, nur Hinweis
    a = ap.parse_args(argv)
    if a.live:
        config.RUN_MODE = "live"
    if a.plan:
        sys.exit(plan(a.book_id))
    sys.exit(run_pipeline(a.book_id, start_from=a.start_from, stop_to=a.stop_to, only=a.only,
                          force=a.force, only_lang=a.lang, line=a.line, wer=a.wer))


if __name__ == "__main__":
    main()
