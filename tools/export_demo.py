"""READ LAYER — Demo-Export fuer die TAELLA-App = Stage 710 mit Ziel Lokal (AP 710c, 03.11.2026).

Duenner Aufrufer: liefert das Werk ueber pipeline/s710_cloud_export.run() in den public/-Ordner der App
(gleiches Paketformat wie die Cloud: manifest_<lg>.json Schema 2, audio/<lg>/*.mp3, audio_hoerspiel/<lg>/*.mp3,
wordtimes_<lg>[_hoerspiel].json, cover_<lg>.jpg, teaser/<lg>/, blurb.json, download/*.epub, katalog.json).
Voraussetzung wie bei 710: Gate 700 frei. Altversion (eigenes Manifestformat, WAV, export_app.py) liegt in
archive/2026-11-03_710c/tools/.

Aufruf:
  python tools/export_demo.py <werk> [<ordner>] [--freigeben] [--lang LG] [--kanal taella|epub] [--dry]
  <ordner>: public/ der App, public/demo oder public/privat/<uid> (Standard config.APP_PUBLIC); Werke liegen
            immer unter demo/<slug> bzw. privat/<uid>/<slug> (Mandant aus book.json).
  --audio/--hoerspiel: ohne Wirkung (Audio laut Bestellung), bleiben fuer alte Aufrufer (cb_neu, Cockpit).
Exit wie Stage 710: 0 auto, 2 Stopp, 3 Mensch, 1 Fehler.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pipeline import gate  # noqa: E402
from pipeline import s710_cloud_export as s710  # noqa: E402


def wurzel_von(ordner):
    """public/, public/demo oder public/privat/<uid> -> public/."""
    if not ordner:
        return None
    p = os.path.abspath(ordner)
    if os.path.basename(p) == "demo":
        return os.path.dirname(p)
    if os.path.basename(os.path.dirname(p)) == "privat":
        return os.path.dirname(os.path.dirname(p))
    return p


def main(argv=None):
    ap = argparse.ArgumentParser(description="Demo-Export = Stage 710 mit Ziel Lokal")
    ap.add_argument("werk")
    ap.add_argument("ordner", nargs="?")
    ap.add_argument("--freigeben", action="store_true", help="erstes Freischalten im Demo-Katalog")
    ap.add_argument("--lang", action="append")
    ap.add_argument("--kanal", action="append", choices=["taella", "epub"])
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--wer", default="export_demo")
    ap.add_argument("--audio", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--hoerspiel", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.audio or a.hoerspiel:
        print("[export_demo] --audio/--hoerspiel ohne Wirkung: Audio laut Bestellung (Stage 710)")
    try:
        gates = s710.run(a.werk, a.wer, ziel=s710.Lokal(wurzel_von(a.ordner)), nur=a.lang, freigeben=a.freigeben,
                         dry=a.dry, kanaele=a.kanal or ["taella", "epub"])
    except (ValueError, RuntimeError, KeyError) as e:
        print(f"[export_demo] {e}")
        return 1
    for g in gates:
        print(g.bericht())
    return gate.EXIT[gate.gesamt([g.ergebnis["ergebnis"] for g in gates] or ["auto"])]


if __name__ == "__main__":
    sys.exit(main())
