"""READ LAYER — Zentraler Begrenzer je Anbieter (TODO 22.11.2026 Punkt 8, AP Parallele Spuren)
==========================================================================================
Ein gemeinsamer Zaehler ueber ALLE gleichzeitig laufenden Stages und Werke (auch mehrere Prozesse:
Cockpit-Laeufe, Bats). Dateibasiert mit Sperre in config.GRENZEN_DIR (Standard cache/grenzen/).
Werte zentral in config.GRENZEN.

  platz(anbieter)        Gleichzeitigkeit (Semaphor ueber Prozesse). Belegung mit Ablaufzeit (ttl_s):
                         ein abgestuerzter Prozess blockiert hoechstens ttl_s.
                           with grenzen.platz("deepseek"):  ... ein API-Aufruf ...
                           with grenzen.platz("modal"):     ... ein Modal-Job ...
  takt(anbieter)         Taktgeber (Ziel-RPM) + Tageszaehler (RPD) fuer Gemini-TTS; Tageswechsel um
                         Mitternacht Pazifikzeit (= 09:00 MEZ). Tagesgrenze erreicht -> TagesgrenzeError
                         (mit Reset-Zeitpunkt), damit 500/510 sauber anhalten (tts_client -> QuotaError).
  melde_429(anbieter)    429 zaehlen (Prozess-Zaehler + cache/grenzen/protokoll.jsonl).
  pause_429(versuch)     steigende Pause mit Streuung (5, 10, 20, 40 ... s, Deckel 120 s).
  zaehler()              {anbieter: 429-Anzahl in diesem Prozess} -> Gate-Metrik der Stage.
  stand()                Belegung/Tageszaehler aller Anbieter (Cockpit, Laufzeitanzeige).

Regler: config.GRENZEN[anbieter]; Umgebung READLAYER_GRENZE_<ANBIETER>=N ueberschreibt "gleichzeitig".
"""
import contextlib
import datetime as dt
import json
import os
import random
import sys
import threading
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config

_tlock = {}
_tlock_meta = threading.Lock()
_429 = {}
_429_lock = threading.Lock()


class TagesgrenzeError(RuntimeError):
    """Tageskontingent (RPD) erschoepft; .reset = datetime (UTC) des naechsten Tageswechsels."""
    def __init__(self, text, reset=None):
        super().__init__(text)
        self.reset = reset


# ------------------------------------------------------------ Werte
def wert(anbieter, feld, std=None):
    g = (getattr(config, "GRENZEN", {}) or {}).get(anbieter) or {}
    if feld == "gleichzeitig":
        env = os.environ.get(f"READLAYER_GRENZE_{anbieter.upper()}")
        if env:
            try:
                return max(1, int(env))
            except ValueError:
                pass
    return g.get(feld, std)


def _dir():
    d = getattr(config, "GRENZEN_DIR", None) or os.path.join(config.BASE_DIR, "cache", "grenzen")
    os.makedirs(d, exist_ok=True)
    return d


# ------------------------------------------------------------ Sperre (Prozesse + Threads)
def _thread_lock(name):
    with _tlock_meta:
        return _tlock.setdefault(name, threading.Lock())


@contextlib.contextmanager
def _sperre(name):
    tl = _thread_lock(name)
    with tl:
        pfad = os.path.join(_dir(), f"{name}.lock")
        f = open(pfad, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                f.seek(0)
                while True:
                    try:
                        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        time.sleep(0.01)
                try:
                    yield
                finally:
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        finally:
            f.close()


def _lesen(name):
    p = os.path.join(_dir(), f"{name}.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _schreiben(name, d):
    p = os.path.join(_dir(), f"{name}.json")
    tmp = f"{p}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f)
    for _ in range(50):                      # Windows: Ziel kurz von Virenscanner o. ae. gehalten
        try:
            os.replace(tmp, p)
            return
        except PermissionError:
            time.sleep(0.02)
    os.replace(tmp, p)


# ------------------------------------------------------------ Gleichzeitigkeit
def _belegt(d, jetzt):
    b = {k: v for k, v in (d.get("belegt") or {}).items() if (v.get("bis") or 0) > jetzt}
    d["belegt"] = b
    return b


@contextlib.contextmanager
def platz(anbieter, warte_max=None):
    """Einen Platz belegen (blockiert, bis frei). warte_max s -> TimeoutError."""
    n = int(wert(anbieter, "gleichzeitig", 0) or 0)
    if n <= 0:                               # Anbieter ohne Grenze
        yield
        return
    ttl = float(wert(anbieter, "ttl_s", 900))
    token = uuid.uuid4().hex[:12]
    t0 = time.time()
    while True:
        with _sperre(anbieter):
            d = _lesen(anbieter)
            jetzt = time.time()
            b = _belegt(d, jetzt)
            if len(b) < n:
                b[token] = {"pid": os.getpid(), "seit": round(jetzt, 1), "bis": round(jetzt + ttl, 1)}
                d["spitze"] = max(int(d.get("spitze") or 0), len(b))
                _schreiben(anbieter, d)
                break
        if warte_max is not None and time.time() - t0 > warte_max:
            raise TimeoutError(f"grenzen: kein Platz bei {anbieter} nach {warte_max}s")
        time.sleep(0.15 + random.random() * 0.25)
    try:
        yield
    finally:
        with _sperre(anbieter):
            d = _lesen(anbieter)
            (d.get("belegt") or {}).pop(token, None)
            _belegt(d, time.time())
            _schreiben(anbieter, d)


@contextlib.contextmanager
def plaetze(anbieter, wunsch):
    """Bis zu `wunsch` Plaetze auf einmal belegen (mindestens 1, blockiert bis einer frei ist). yield -> Anzahl.
    Fuer Modal-.map(): eine Welle von hoechstens so vielen Aufrufen."""
    n = int(wert(anbieter, "gleichzeitig", 0) or 0)
    wunsch = max(1, int(wunsch or 1))
    if n <= 0:
        yield wunsch
        return
    ttl = float(wert(anbieter, "ttl_s", 900))
    tokens = []
    while True:
        with _sperre(anbieter):
            d = _lesen(anbieter)
            jetzt = time.time()
            b = _belegt(d, jetzt)
            frei = n - len(b)
            if frei >= 1:
                for _ in range(min(frei, wunsch)):
                    t = uuid.uuid4().hex[:12]
                    b[t] = {"pid": os.getpid(), "seit": round(jetzt, 1), "bis": round(jetzt + ttl, 1)}
                    tokens.append(t)
                d["spitze"] = max(int(d.get("spitze") or 0), len(b))
                _schreiben(anbieter, d)
                break
        time.sleep(0.5 + random.random() * 0.5)
    try:
        yield len(tokens)
    finally:
        with _sperre(anbieter):
            d = _lesen(anbieter)
            for t in tokens:
                (d.get("belegt") or {}).pop(t, None)
            _belegt(d, time.time())
            _schreiben(anbieter, d)


# ------------------------------------------------------------ Taktgeber + Tageszaehler
def _pazifik_offset(utc):
    """Stunden UTC-Versatz Pazifikzeit (PST -8 / PDT -7, US-Sommerzeit 2. So. Maerz – 1. So. Nov., 02:00 lokal).
    Eigene Rechnung: Windows-Python hat ohne Paket tzdata keine Zeitzonen."""
    y = utc.year
    maerz = dt.datetime(y, 3, 8 + (6 - dt.date(y, 3, 8).weekday()) % 7, 10)   # 2. So. 02:00 PST = 10:00 UTC
    nov = dt.datetime(y, 11, 1 + (6 - dt.date(y, 11, 1).weekday()) % 7, 9)    # 1. So. 02:00 PDT = 09:00 UTC
    u = utc.replace(tzinfo=None)
    return -7 if maerz <= u < nov else -8


def tag_pazifik(utc=None):
    utc = utc or dt.datetime.now(dt.timezone.utc)
    return (utc + dt.timedelta(hours=_pazifik_offset(utc))).date().isoformat()


def naechster_reset(utc=None):
    """-> datetime UTC des naechsten Tageswechsels (Mitternacht Pazifik)."""
    utc = utc or dt.datetime.now(dt.timezone.utc)
    off = _pazifik_offset(utc)
    lokal = (utc + dt.timedelta(hours=off)).replace(tzinfo=None)
    mitternacht = dt.datetime.combine(lokal.date() + dt.timedelta(days=1), dt.time())
    return (mitternacht - dt.timedelta(hours=_pazifik_offset(mitternacht - dt.timedelta(hours=off + 1)))
            ).replace(tzinfo=dt.timezone.utc)


def takt(anbieter, anzahl=1):
    """Vor jedem Aufruf: wartet auf den naechsten Takt (Ziel-RPM) und zaehlt den Tageszaehler hoch."""
    rpm = float(wert(anbieter, "rpm_ziel", 0) or 0)
    rpd = int(wert(anbieter, "rpd", 0) or 0)
    if rpm <= 0 and rpd <= 0:
        return
    while True:
        with _sperre(anbieter):
            d = _lesen(anbieter)
            jetzt = time.time()
            tag = tag_pazifik()
            if d.get("tag") != tag:
                d.update(tag=tag, heute=0)
            if rpd and int(d.get("heute") or 0) + anzahl > rpd:
                _schreiben(anbieter, d)
                r = naechster_reset()
                raise TagesgrenzeError(f"{anbieter}: Tagesgrenze {rpd} Anfragen erreicht (Tageswechsel "
                                       f"{r.astimezone().strftime('%d.%m. %H:%M')})", reset=r)
            slot = max(jetzt, float(d.get("naechster") or 0))
            if slot - jetzt <= 5:            # weiter voraus belegt (viele Spuren): kurz warten, neu anstellen
                d["naechster"] = slot + (60.0 / rpm if rpm > 0 else 0) * anzahl
                d["heute"] = int(d.get("heute") or 0) + anzahl
                _schreiben(anbieter, d)
                break
        time.sleep(min(2.0, max(0.05, slot - jetzt - 4)))
    if slot > time.time():
        time.sleep(slot - time.time())


def rest_heute(anbieter):
    rpd = int(wert(anbieter, "rpd", 0) or 0)
    if not rpd:
        return None
    d = _lesen(anbieter)
    return rpd - (int(d.get("heute") or 0) if d.get("tag") == tag_pazifik() else 0)


# ------------------------------------------------------------ 429
def melde_429(anbieter, werk=None, stage=None):
    with _429_lock:
        _429[anbieter] = _429.get(anbieter, 0) + 1
    try:
        with _sperre("protokoll"):
            with open(os.path.join(_dir(), "protokoll.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps({"zeit": dt.datetime.now().isoformat(timespec="seconds"), "anbieter": anbieter,
                                    "art": "429", "pid": os.getpid(), "werk": werk, "stage": stage}) + "\n")
    except OSError:
        pass


def pause_429(versuch, basis=5.0, deckel=120.0):
    return min(deckel, basis * (2 ** versuch)) * (0.75 + random.random() * 0.5)


def zaehler():
    with _429_lock:
        return dict(_429)


def stand():
    out = {}
    for a in (getattr(config, "GRENZEN", {}) or {}):
        d = _lesen(a)
        e = {"gleichzeitig": wert(a, "gleichzeitig")}
        if "belegt" in d or e["gleichzeitig"]:
            e["belegt"] = len(_belegt(d, time.time()))
            e["spitze"] = d.get("spitze")
        if wert(a, "rpd"):
            e["rpd"] = wert(a, "rpd")
            e["rest_heute"] = rest_heute(a)
            e["reset"] = naechster_reset().astimezone().strftime("%d.%m. %H:%M")
        out[a] = e
    return out


if __name__ == "__main__":
    print(json.dumps(stand(), indent=1, ensure_ascii=False))
