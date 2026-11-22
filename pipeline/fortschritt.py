"""READ LAYER — Laufzeit + Fortschritt je Stage (TODO 22.11.2026 Punkt 7; zuerst Stage 310)
===========================================================================================
Planbarkeit der EINZELNEN Stage (keine Hochrechnung ueber die Kette).
  work/_fortschritt/<stage>.json   {stage, einheit, erledigt, gesamt, start, rate, rest_s, fertig_um,
                                    erwartet_s, erwartet_fertig, spuren, zustand laeuft|fertig|abbruch, stand}
  cache/fortschritt_raten.json     gemessene Raten frueherer Laeufe je Stage (s je 1.000 Zeichen + s je Einheit, Spuren)

Schaetzung vor dem Start: Median der Raten frueherer Laeufe mit gleicher (sonst naechster) Spurenzahl,
bezogen auf das Gewicht (Zeichen), sonst auf die Einheit. Waehrend des Laufs: aktuelle Rate, anfangs mit der
Schaetzung gemischt (bis 20 % erledigt), damit die Restzeit nicht springt.

  f = Fortschritt(werk, "310", "Saetze", gesamt=n, gewicht=zeichen, spuren=12)
  f.plus(n_saetze, gewicht=zeichen_batch) ... f.ende(ok=True)
  schaetzen("310", gewicht=zeichen, gesamt=n, spuren=12) -> Sekunden oder None
"""
import datetime as dt
import json
import os
import statistics
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import manifest

MAX_RATEN = 12
MISCH_BIS = 0.2
SPUR_EXP = 0.8       # Umrechnung zwischen Spurenzahlen (grob)
MIN_DAUER = 5.0       # kuerzere Laeufe liefern keine verlaessliche Rate


def _raten_pfad():
    return os.path.join(config.BASE_DIR, "cache", "fortschritt_raten.json")


def pfad(werk, stage):
    return os.path.join(config.work_dir(werk), "_fortschritt", f"{stage}.json")


def raten(stage):
    try:
        with open(_raten_pfad(), encoding="utf-8") as f:
            return (json.load(f) or {}).get(str(stage)) or []
    except (OSError, ValueError):
        return []


def rate_merken(stage, eintrag):
    p = _raten_pfad()
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f) or {}
    except (OSError, ValueError):
        d = {}
    l = (d.get(str(stage)) or []) + [eintrag]
    d[str(stage)] = l[-MAX_RATEN:]
    manifest.json_atomar(p, d, indent=1)


def schaetzen(stage, gewicht=None, gesamt=None, spuren=1):
    """-> erwartete Sekunden (None = keine frueheren Laeufe)."""
    l = raten(stage)
    if not l:
        return None
    sp = int(spuren or 1)
    nah = min(abs(int(x.get("spuren") or 1) - sp) for x in l)
    l = [x for x in l if abs(int(x.get("spuren") or 1) - sp) == nah]
    # andere Spurenzahl: grob umrechnen (Gewinn waechst schwaecher als linear), bis ein Lauf mit gleicher Zahl da ist
    f = statistics.median((int(x.get("spuren") or 1) / sp) ** SPUR_EXP for x in l) if nah else 1.0
    if gewicht and all(x.get("s_je_1000z") for x in l):
        return f * statistics.median(x["s_je_1000z"] for x in l) * gewicht / 1000
    xs = [x["s_je_einheit"] for x in l if x.get("s_je_einheit")]
    if gesamt and xs:
        return f * statistics.median(xs) * gesamt
    return None


def _uhr(t):
    return dt.datetime.fromtimestamp(t).strftime("%H:%M") if dt.date.fromtimestamp(t) == dt.date.today() \
        else dt.datetime.fromtimestamp(t).strftime("%d.%m. %H:%M")


def lesen(werk, stage):
    try:
        with open(pfad(werk, stage), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


class Fortschritt:
    def __init__(self, werk, stage, einheit, gesamt, gewicht=None, spuren=1, schreiben=True, art=None):
        self.werk, self.stage, self.einheit = werk, str(stage), einheit
        self.raten_key = f"{stage}_{art}" if art else str(stage)    # getrennte Raten je Art (500: gemini/chatterbox)
        self.gesamt, self.gewicht_gesamt = int(gesamt), float(gewicht or 0)
        self.spuren, self.aktiv = int(spuren or 1), schreiben
        self.erledigt, self.gewicht = 0, 0.0
        self.t0 = time.time()
        self.erwartet = schaetzen(self.raten_key, self.gewicht_gesamt or None, self.gesamt, self.spuren)
        self._lock = threading.Lock()
        self._zuletzt = 0.0
        self._schreiben("laeuft", True)

    def text_vorab(self):
        if self.erwartet is None:
            return f"{self.gesamt} {self.einheit} offen, keine Schaetzung (kein frueherer Lauf)"
        return (f"{self.gesamt} {self.einheit} offen, erwartet ~{self.erwartet / 60:.1f} min, "
                f"fertig ~{_uhr(self.t0 + self.erwartet)} ({self.spuren} Spuren)")

    def _rest(self, jetzt):
        lauf = jetzt - self.t0
        if self.gewicht_gesamt and self.gewicht:
            anteil = self.gewicht / self.gewicht_gesamt
        elif self.gesamt:
            anteil = self.erledigt / self.gesamt
        else:
            anteil = 1.0
        if anteil <= 0:
            return self.erwartet, None
        ist = lauf / anteil - lauf
        if self.erwartet is not None and anteil < MISCH_BIS:
            w = anteil / MISCH_BIS
            ist = w * ist + (1 - w) * max(0.0, self.erwartet - lauf)
        rate = lauf / self.erledigt if self.erledigt else None
        return max(0.0, ist), rate

    def _schreiben(self, zustand, sofort=False):
        if not self.aktiv:
            return
        jetzt = time.time()
        if not sofort and jetzt - self._zuletzt < 1.0:
            return
        self._zuletzt = jetzt
        rest, rate = self._rest(jetzt) if zustand == "laeuft" else (0.0, None)
        d = {"stage": self.stage, "einheit": self.einheit, "erledigt": self.erledigt, "gesamt": self.gesamt,
             "start": dt.datetime.fromtimestamp(self.t0).isoformat(timespec="seconds"),
             "rate": round(rate, 3) if rate else None, "rest_s": None if rest is None else round(rest),
             "fertig_um": None if rest is None else _uhr(jetzt + rest),
             "erwartet_s": None if self.erwartet is None else round(self.erwartet),
             "erwartet_fertig": None if self.erwartet is None else _uhr(self.t0 + self.erwartet),
             "spuren": self.spuren, "zustand": zustand, "lauf_s": round(jetzt - self.t0),
             "stand": dt.datetime.fromtimestamp(jetzt).isoformat(timespec="seconds"), "pid": os.getpid()}
        manifest.json_atomar(pfad(self.werk, self.stage), d, indent=None)

    def plus(self, n=1, gewicht=0):
        with self._lock:
            self.erledigt += n
            self.gewicht += gewicht
            self._schreiben("laeuft")

    def ende(self, ok=True, merken=True):
        with self._lock:
            dauer = time.time() - self.t0
            self._schreiben("fertig" if ok else "abbruch", True)
            if ok and merken and dauer >= MIN_DAUER and (self.gewicht or self.erledigt >= 10):
                e = {"wann": dt.datetime.now().isoformat(timespec="seconds"), "werk": self.werk,
                     "spuren": self.spuren, "einheiten": self.erledigt, "s_je_einheit": round(dauer / self.erledigt, 4),
                     "dauer_s": round(dauer, 1)}
                if self.gewicht:
                    e.update(zeichen=int(self.gewicht), s_je_1000z=round(dauer * 1000 / self.gewicht, 4))
                rate_merken(self.raten_key, e)
            return dauer
