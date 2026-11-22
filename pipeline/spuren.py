"""READ LAYER — Parallele Spuren je Stage (AP Parallele Spuren, 22.11.2026; Muster aus 310)
=========================================================================================
Trennbare Jobs einer Stage (Kapitel x Sprache, Satz, Clip, Datei) laufen gleichzeitig. Jeder Job sichert sein
Ergebnis selbst (Checkpoint) -> Wiederaufnahme nach Abbruch; die Stage fuehrt die Ergebnisse danach in fester
Reihenfolge zusammen (feste IDs), Gate und Ausgabeformat bleiben unveraendert.
Anbietergrenzen gelten zusaetzlich zentral (pipeline/grenzen.py: DeepSeek, Gemini-TTS, Modal).

  n = spuren.anzahl(b.roh, "uebersetzung_spuren", spuren)         # Regler je Werk > config.SPUREN[stage] > 12
  erg, info = spuren.parallel(werk, "300", jobs, fn, n, einheit="Kapitel", gewicht=[...])
  spuren.metriken(g, info)                                          # spuren, laufzeit_s, http_429, erwartet_s

Fehler in einem Job brechen den Lauf ab (noch nicht gestartete Jobs entfallen, gestartete laufen zu Ende und sind
gesichert) und werden weitergereicht – wie im seriellen Lauf. Jobs, die selbst Fehler abfangen, liefern ihr
Ergebnis normal zurueck. spuren=1 laeuft ohne Threads (gleiches Verhalten wie vorher).
Zaehler je Job lokal fuehren und nach dem Lauf summieren (kein gemeinsames dict += aus Threads).
"""
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import fortschritt, grenzen

STANDARD = 12


def anzahl(roh=None, feld=None, wert=None, stage=None):
    """Spurenzahl: Argument > book.json-Feld > config.SPUREN[stage] > config.SPUREN_STANDARD (12)."""
    for v in (wert, (roh or {}).get(feld) if feld else None,
              (getattr(config, "SPUREN", {}) or {}).get(str(stage)) if stage else None,
              getattr(config, "SPUREN_STANDARD", STANDARD)):
        if v not in (None, "", 0):
            try:
                return max(1, min(64, int(v)))
            except (TypeError, ValueError):
                continue
    return STANDARD


def parallel(werk, stage, jobs, fn, n, einheit="Kapitel", gewicht=None, fortschritt_an=True, text=True):
    """-> (Ergebnisse in Reihenfolge der jobs, info). gewicht: Liste je Job (z. B. Zeichen) fuer die Schaetzung."""
    jobs = list(jobs)
    n = max(1, int(n or 1))
    gw = list(gewicht) if gewicht is not None else [0] * len(jobs)
    fs = fortschritt.Fortschritt(werk, stage, einheit, len(jobs), gewicht=sum(gw) or None, spuren=n,
                                 schreiben=bool(fortschritt_an and jobs and werk))
    if jobs and text:
        print(f"[{stage}] {fs.text_vorab()}")
    vor = sum(grenzen.zaehler().values())
    t0 = time.time()
    erg = [None] * len(jobs)
    try:
        if n == 1 or len(jobs) <= 1:
            for i, j in enumerate(jobs):
                erg[i] = fn(j)
                fs.plus(1, gw[i])
        else:
            with ThreadPoolExecutor(max_workers=min(n, len(jobs)), thread_name_prefix=f"s{stage}") as ex:
                futs = [ex.submit(fn, j) for j in jobs]
                fehler = None
                for i, f in enumerate(futs):
                    try:
                        erg[i] = f.result()
                        fs.plus(1, gw[i])
                    except BaseException as e:
                        fehler = fehler or e
                        for f2 in futs:
                            f2.cancel()
                if fehler:
                    raise fehler
    except BaseException:
        fs.ende(ok=False)
        raise
    dauer = fs.ende(ok=True) if jobs else time.time() - t0
    info = {"spuren": n, "jobs": len(jobs), "laufzeit_s": round(dauer, 1),
            "http_429": sum(grenzen.zaehler().values()) - vor,
            "erwartet_s": None if fs.erwartet is None else round(fs.erwartet)}
    return erg, info


def metriken(g, info, praefix=""):
    if not g or not info:
        return
    for k in ("spuren", "laufzeit_s", "http_429", "erwartet_s"):
        if info.get(k) is not None:
            g.metrik(praefix + k, info[k])
    if info.get("jobs") is not None:
        g.metrik(praefix + "jobs_parallel", info["jobs"])


def summe(ziel, *teile):
    """Zaehler-dicts der Jobs aufaddieren (in-place in ziel)."""
    for t in teile:
        for k, v in (t or {}).items():
            if isinstance(v, (int, float)):
                ziel[k] = ziel.get(k, 0) + v
    return ziel


def modal_map(fn, eingaben, kwargs=None):
    """Ersatz fuer fn.map(eingaben, kwargs=...) unter der Modal-Grenze (config.GRENZEN modal, ueber alle
    Stages/Werke): Wellen von hoechstens so vielen Aufrufen, wie gerade Plaetze frei sind. Reihenfolge bleibt."""
    eingaben = list(eingaben)
    i = 0
    while i < len(eingaben):
        with grenzen.plaetze("modal", len(eingaben) - i) as m:
            welle = eingaben[i:i + m]
            for r in (fn.map(welle, kwargs=kwargs) if kwargs else fn.map(welle)):
                yield r
        i += m


def modal_platz():
    """Ein Modal-Job (modal run / .remote) unter der Modal-Grenze."""
    return grenzen.platz("modal")
