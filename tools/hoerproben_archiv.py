"""AP 63: Klon-Hoerproben (Nordwind-Text) fuer alle Archivstimmen nachziehen.
Aufruf: py -3.11 tools/hoerproben_archiv.py [liste|los] [--stimmen a,b] [--sprachen de,en]
  liste = nur zaehlen + Kosten schaetzen (kostenlos) | los = fehlende klon_<lg>.wav per Gemini erzeugen
"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pipeline import hoerprobe as hp


def opt(n, d=None):
    return sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d


def main():
    modus = next((a for a in sys.argv[1:] if a in ("liste", "los")), "liste")
    nur = set((opt("--stimmen") or "").split(",")) - {""}
    spr = tuple((opt("--sprachen") or "de,en").split(","))
    offen = [(n, o, lg) for n, o in hp.stimmen() if not nur or n in nur for lg in hp.fehlend(o, spr)]
    print(f"[hoerproben] {len(hp.stimmen())} Stimmen im Archiv, {len(offen)} Klon-Proben fehlen "
          f"-> ca. {len(offen) * hp.USD_JE_CLIP:.2f} USD (2026), {len(offen) * hp.USD_JE_CLIP * 2:.2f} USD (ab 2027)")
    if modus != "los":
        return
    for i, (n, o, lg) in enumerate(offen, 1):
        try:
            hp.erzeuge(n, o, lg)
            print(f"  {i}/{len(offen)} {n} {lg}: ok", flush=True)
        except Exception as e:
            print(f"  {i}/{len(offen)} {n} {lg}: FEHLER {type(e).__name__}: {str(e)[:150]}", flush=True)


if __name__ == "__main__":
    main()
