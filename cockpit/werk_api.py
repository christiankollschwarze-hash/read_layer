"""Phase 3, P3-1: Einzeltitel-Ansicht – Lese-API und Aktionen fuer EIN Werk (Book-ID).

Eine Wahrheit: liest/schreibt nur work/status.json ueber pipeline.status (Sperrdatei + atomar).
  - Lesen (werk) veraendert status.json nicht (kein bedarf_setzen, kein run.py --plan).
  - Entscheiden/Zuruecksetzen/Override wie CLI `python -m pipeline.status` inkl. Rechtepruefung 080.
  - Laeufe nur als Unterprozess run.py, Regler nur als Unterprozess `python -m pipeline.sNNN_*`.
Exit-Codes: 0 frei, 1 Fehler, 2 Stopp, 3 Mensch (3 ist kein Fehler).
"""
import datetime as dt
import glob
import os
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from config import config                                            # noqa: E402
from pipeline import bestellung, kette, status, s080_mandant, usage_log  # noqa: E402
import run as RUN                                                    # noqa: E402

PY = sys.executable
LOGDIR = os.path.join(HERE, "logs")
EXIT_DEUTUNG = {0: "frei", 1: "fehler", 2: "stopp", 3: "mensch"}
NAMEN = {"080": "Mandant & Rechte", "090": "Eingang", "095": "Produktwahl", "100": "Anlegen"}

# Regler je Stage = CLI-Parameter des Stage-Moduls (Whitelist). typ: schalter|text|zahl|ganz|wahl|liste
REGLER = {
    "095": {"modul": "pipeline.s095_produktwahl", "aktion": "bestellen", "felder": [
        {"flag": "--produkt", "typ": "liste",
         "hilfe": "je Zeile SPRACHE:INHALT[:STUFE]:KANAL[,KANAL][:+ZUSATZ] – ersetzt die Bestellung"},
        {"flag": "--default", "typ": "schalter", "hilfe": "Bestellung aus Wunsch (090) neu ableiten"}]},
    "410": {"modul": "pipeline.s410_casting", "aktion": "lauf", "felder": [
        {"flag": "--freigeben", "typ": "schalter", "hilfe": "Casting freigeben (nach Hoerprobe)"},
        {"flag": "--grund", "typ": "text"},
        {"flag": "--schwelle", "typ": "zahl"},
        {"flag": "--f0-abstand", "typ": "zahl"},
        {"flag": "--max-ensemble", "typ": "ganz"},
        {"flag": "--min-anteil", "typ": "zahl"},
        {"flag": "--max-text", "typ": "ganz"},
        {"flag": "--trocken", "typ": "schalter", "hilfe": "nur pruefen"}]},
    "615": {"modul": "pipeline.s615_cover_final", "aktion": "lauf", "felder": [
        {"flag": "--titel", "typ": "liste", "hilfe": "je Zeile LG=TEXT"},
        {"flag": "--umbruch", "typ": "liste", "hilfe": "je Zeile LG=A|B ('LG=' = auto)"},
        {"flag": "--schrift", "typ": "ganz", "hilfe": "Titel-Schriftgroesse pt"},
        {"flag": "--position", "typ": "wahl", "werte": ["oben", "unten"]},
        {"flag": "--transparenz", "typ": "zahl", "hilfe": "0..1"},
        {"flag": "--sprecher", "typ": "wahl", "werte": ["an", "aus"]},
        {"flag": "--neu", "typ": "schalter", "hilfe": "Varianten neu schreiben"},
        {"flag": "--freigeben", "typ": "schalter", "hilfe": "Sichtfreigabe"},
        {"flag": "--trocken", "typ": "schalter", "hilfe": "nur pruefen"}]},
    "710": {"modul": "pipeline.s710_cloud_export", "aktion": "lauf", "felder": [
        {"flag": "--bitrate", "typ": "text", "hilfe": "z. B. 96k (wird gemerkt)"},
        {"flag": "--nur-manifest", "typ": "schalter"},
        {"flag": "--freigeben", "typ": "schalter", "hilfe": "Freischalten im Katalog"},
        {"flag": "--grund", "typ": "text"},
        {"flag": "--dry", "typ": "schalter", "hilfe": "Probelauf ohne Upload und Status"}]},
}


# ------------------------------------------------------------------ Hilfen
def _modul(s):
    """Stage-Modul (Dateiname) fuer Namen; 100 liegt in tools/."""
    treffer = sorted(glob.glob(os.path.join(BASE, "pipeline", f"s{s}_*.py")))
    return os.path.splitext(os.path.basename(treffer[0]))[0] if treffer else None


def name(s):
    if s in NAMEN:
        return NAMEN[s]
    m = _modul(s)
    return m.split("_", 1)[1].replace("_", " ").capitalize() if m else s


def _auszug(m, n=40):
    """Metriken kurz: Skalare direkt, kurze Skalarlisten verbunden, Rest als Groessenangabe."""
    out = {}
    for k, v in list((m or {}).items())[:n]:
        if isinstance(v, str):
            out[k] = v if len(v) <= 200 else v[:200] + "…"
        elif isinstance(v, (int, float, bool)) or v is None:
            out[k] = v
        elif isinstance(v, list) and len(v) <= 8 and all(isinstance(x, (str, int, float)) for x in v):
            out[k] = ", ".join(str(x) for x in v)
        elif isinstance(v, dict) and len(v) <= 8 and all(isinstance(x, (str, int, float, bool)) or x is None
                                                          for x in v.values()):
            out[k] = ", ".join(f"{a}={b}" for a, b in v.items())
        elif isinstance(v, (list, dict)):
            out[k] = f"[{len(v)}]" if isinstance(v, list) else "{" + ", ".join(list(v)[:6]) + ("…" if len(v) > 6 else "") + "}"
        else:
            out[k] = str(v)[:200]
    return out


def _eintrag(t):
    g = t.get("gate") or {}
    return {"zustand": t.get("zustand", "offen"), "gate": g.get("ergebnis"), "gruende": list(g.get("gruende") or []),
            "ruecksprung": g.get("ruecksprung"), "gate_wann": g.get("wann"), "hinweise": list(t.get("hinweise") or []),
            "metriken": _auszug(t.get("metriken")), "versuche": t.get("versuche", 0), "wer": t.get("wer"),
            "wann": t.get("wann"), "override": t.get("override"), "stand": t.get("stand")}


def befunde(st):
    """Offene Befunde (mensch/stopp) der Stage bzw. ihrer Teile + Ruecksprungziele [(ziel, scope)]."""
    if not st:
        return [], []
    g = st.get("gate") or {}
    gr = list(g.get("gruende") or []) if st.get("zustand") in ("mensch", "stopp") else []
    rs = [(g["ruecksprung"], None)] if g.get("ruecksprung") and st.get("zustand") in ("mensch", "stopp") else []
    for sc, t in sorted((st.get("teile") or {}).items()):
        if t.get("zustand") in ("mensch", "stopp"):
            tg = t.get("gate") or {}
            gr += [f"{sc}: {x}" for x in (tg.get("gruende") or [t["zustand"]])]
            if tg.get("ruecksprung") and tg["ruecksprung"] not in [r for r, _ in rs]:
                rs.append((tg["ruecksprung"], sc))
    return gr, rs


def _manifeste(book_id, s):
    try:
        w = config.work_dir(book_id)
    except Exception:
        return []
    out = []
    for p in sorted(glob.glob(os.path.join(w, f"{s}_*.json"))):
        out.append({"datei": os.path.relpath(p, BASE).replace("\\", "/"),
                    "wann": dt.datetime.fromtimestamp(os.path.getmtime(p)).isoformat(timespec="seconds")})
    return out


# ------------------------------------------------------------------ Lesen
def werke():
    """Book-IDs aus daten/index.json (fuer Titelwechsel)."""
    try:
        return sorted(config._load_index().get("books", {}))
    except Exception:
        return []


def nutzer_liste():
    reg = s080_mandant.register()
    return {"standard": s080_mandant.nutzer(), "sprachen": list(bestellung.sprachliste()), "nutzer": [
        {"id": k, "rolle": v.get("rolle"), "name": v.get("name", k)} for k, v in (reg.get("nutzer") or {}).items()]}


def werk(book_id, wer=None):
    """Alles fuer die Einzeltitel-Ansicht. Schreibt nichts."""
    d = status.laden(book_id)
    try:
        b = bestellung.lesen(book_id)
        bfehler = b.fehler()
    except Exception as e:
        b, bfehler = None, [f"Bestellung nicht lesbar: {e}"]
    if b is not None and not bfehler:
        laeuft = kette.bedarf(b)
    else:
        laeuft = {s for s, st in d["stages"].items() if st.get("zustand") != "entfaellt"}
    try:
        kosten = usage_log.summe(book_id)
    except Exception:
        kosten = {"gesamt": {}, "stages": {}}

    stages, naechster = [], None
    for s in status.STAGES:
        st = d["stages"].get(s) or {}
        bestellt = s in laeuft
        z = st.get("zustand", "offen") if st else ("offen" if bestellt else "entfaellt")
        frei = bestellt and z in status.FREI
        fehlt = alt = []
        if frei and b is not None:
            try:
                fehlt = RUN.fehlende_teile(book_id, s, b, d=d)
                alt = [(v, t.isoformat(timespec="seconds")) for v, t in RUN.veraltet(book_id, s, laeuft, d=d)]
            except Exception:
                pass
        gr, rs = befunde(st)
        try:
            sprachen = kette.sprachen(s, b) if (b is not None and bestellt) else None
        except Exception:
            sprachen = None
        e = _eintrag(st) if st else _eintrag({"zustand": z})
        e.update(stage=s, name=name(s), bestellt=bestellt, zustand=z,
                 bedarf_abweichung=bool(st) and ((z == "entfaellt") == bestellt),
                 befunde=gr, ruecksprung_ziele=[{"ziel": r, "scope": sc} for r, sc in rs],
                 teile={sc: _eintrag(t) for sc, t in sorted((st.get("teile") or {}).items())},
                 vorgaenger=kette.wirksame_vorgaenger(s, laeuft, RUN.IN_KETTE) if bestellt else [],
                 sprachen=sprachen, fehlende_teile=fehlt, veraltet=alt,
                 kosten=(kosten.get("stages") or {}).get(s), regler=REGLER.get(s),
                 manifeste=_manifeste(book_id, s))
        stages.append(e)
        if naechster is None and bestellt and (z not in status.FREI or fehlt or alt):
            naechster = {"stage": s, "zustand": z, "ruecksprung": rs[0][0] if rs else None,
                         "grund": "Teile offen" if fehlt else ("veraltet" if alt else z)}

    wer = s080_mandant.nutzer(wer)
    rechte = {}
    for a in ("lauf", "bestellen", "entscheiden", "zuruecksetzen", "override"):
        try:
            ok, grund = s080_mandant.pruefen(book_id, a, wer, b=b)
        except Exception as ex:
            ok, grund = False, str(ex)
        rechte[a] = {"ok": ok, "grund": grund}
    return {"book_id": book_id, "aktualisiert": d.get("aktualisiert"), "status_vorhanden": os.path.exists(status.pfad(book_id)),
            "bestellung": b.als_dict() if b is not None else None, "bestellung_fehler": bfehler,
            "kosten_gesamt": kosten.get("gesamt"), "stages": stages, "naechster": naechster,
            "protokoll": list(reversed(d.get("protokoll") or []))[:80],
            "ampel": _ampel_aus(d, os.path.dirname(status.pfad(book_id)), LAEUFE.state(book_id, zeilen=0)),
            "run_mode": config.RUN_MODE, "wer": wer, "rolle": s080_mandant.rolle(wer), "rechte": rechte, "lauf": LAEUFE.state(book_id)}


# ------------------------------------------------------------------ Entscheidungen (wie status-CLI)
def aktion(book_id, art, stage, wer, grund, scope=None, nach=None):
    """art: entscheiden (nach frei|stopp|offen) | zuruecksetzen | override (nach, nur admin)."""
    try:
        if not (grund or "").strip():
            raise ValueError("Grund ist Pflicht")
        wer = s080_mandant.nutzer(wer)
        if art not in ("entscheiden", "zuruecksetzen", "override"):
            raise ValueError(f"Aktion {art!r} unbekannt")
        rolle = s080_mandant.darf(book_id, art, wer)
        scope = scope or None
        if art == "entscheiden":
            status.entscheiden(book_id, stage, nach, wer, grund, scope, rolle)
        elif art == "override":
            status.override(book_id, stage, wer, rolle, grund, nach or "frei", scope)
        else:
            status.zuruecksetzen(book_id, stage, wer, grund, scope)
        return {"ok": True, "zustand": status.zustand(book_id, stage, scope)}
    except (ValueError, PermissionError, RuntimeError, TimeoutError) as e:
        return {"ok": False, "fehler": str(e)}


# ------------------------------------------------------------------ Unterprozesse
def lauf_argv(book_id, modus, wer, von=None, live=False):
    """modus fortsetzen (Kette ab Anfang, freie Stages werden uebersprungen) | ab (--from von) | nur (--only von)."""
    argv = [PY, "run.py", book_id]
    if modus in ("ab", "nur"):
        von = status._norm(von or "")
        argv += ["--from" if modus == "ab" else "--only", von]
    elif modus != "fortsetzen":
        raise ValueError(f"Modus {modus!r} unbekannt")
    if live:
        argv.append("--live")
    return argv + ["--wer", s080_mandant.nutzer(wer)]


def regler_argv(book_id, stage, werte, wer):
    """Whitelist-Aufbau; Werte immer als --flag=wert (kein Einschleusen weiterer Optionen)."""
    r = REGLER.get(status._norm(stage))
    if not r:
        raise ValueError(f"Stage {stage}: keine Regler")
    felder = {f["flag"]: f for f in r["felder"]}
    argv = [PY, "-m", r["modul"], book_id, "--wer", s080_mandant.nutzer(wer)]
    for flag, v in (werte or {}).items():
        f = felder.get(flag)
        if f is None:
            raise ValueError(f"Regler {flag} fuer {stage} nicht erlaubt")
        t = f["typ"]
        if t == "schalter":
            if v:
                argv.append(flag)
            continue
        if v is None or v == "" or v == []:
            continue
        if t == "liste":
            zeilen = v if isinstance(v, list) else str(v).splitlines()
            argv += [f"{flag}={z.strip()}" for z in zeilen if z.strip()]
        elif t == "zahl":
            argv.append(f"{flag}={float(str(v).replace(',', '.'))}")
        elif t == "ganz":
            argv.append(f"{flag}={int(v)}")
        elif t == "wahl":
            if v not in f["werte"]:
                raise ValueError(f"{flag}: {v!r} nicht in {f['werte']}")
            argv.append(f"{flag}={v}")
        else:
            argv.append(f"{flag}={str(v).strip()}")
    return argv, r["aktion"]


class Laeufe:
    """Ein Unterprozess je Werk (Lauf oder Regler), Log in cockpit/logs/werk_<id>_<zeit>.log."""

    def __init__(self):
        self.lock = threading.Lock()
        self.jobs = {}

    def start(self, book_id, argv, art):
        with self.lock:
            j = self.jobs.get(book_id)
            if j and j["exit"] is None:
                raise RuntimeError(f"Fuer {book_id} laeuft bereits: {j['art']}")
            os.makedirs(LOGDIR, exist_ok=True)
            log = os.path.join(LOGDIR, f"werk_{book_id}_{dt.datetime.now():%Y%m%d_%H%M%S}.log")
            env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
            fh = open(log, "w", encoding="utf-8")
            fh.write("$ " + " ".join(argv[1:]) + "\n")
            fh.flush()
            p = subprocess.Popen(argv, cwd=BASE, stdout=fh, stderr=subprocess.STDOUT, env=env)
            j = {"art": art, "cmd": " ".join(argv[1:]), "log": log, "start": dt.datetime.now().isoformat(timespec="seconds"),
                 "ende": None, "exit": None, "proc": p}
            self.jobs[book_id] = j

        def warten():
            rc = p.wait()
            fh.close()
            j.update(exit=rc, ende=dt.datetime.now().isoformat(timespec="seconds"))
        threading.Thread(target=warten, daemon=True).start()
        return self.state(book_id)

    def stop(self, book_id):
        j = self.jobs.get(book_id)
        if j and j["exit"] is None:
            j["proc"].terminate()
            return True
        return False

    def state(self, book_id, zeilen=200):
        j = self.jobs.get(book_id)
        if not j:
            return None
        tail = []
        if zeilen:
            try:
                with open(j["log"], encoding="utf-8", errors="replace") as f:
                    tail = f.read().splitlines()[-zeilen:]
            except OSError:
                pass
        rc = j["exit"]
        return {"art": j["art"], "cmd": j["cmd"], "start": j["start"], "ende": j["ende"], "laeuft": rc is None,
                "exit": rc, "deutung": None if rc is None else EXIT_DEUTUNG.get(rc, "fehler"),
                "log": "\n".join(tail), "logdatei": os.path.relpath(j["log"], BASE).replace("\\", "/")}


LAEUFE = Laeufe()


def _recht(book_id, akt, wer):
    ok, grund = s080_mandant.pruefen(book_id, akt, s080_mandant.nutzer(wer))
    if not ok:
        raise PermissionError(f"080: {grund}")


def lauf(book_id, modus, wer, von=None, live=False):
    try:
        _recht(book_id, "lauf", wer)
        argv = lauf_argv(book_id, modus, wer, von, live)
        return {"ok": True, "lauf": LAEUFE.start(book_id, argv, f"run.py {modus}{' ' + von if von else ''}")}
    except (ValueError, PermissionError, RuntimeError) as e:
        return {"ok": False, "fehler": str(e)}


def regler(book_id, stage, werte, wer, nur_vorschau=False):
    try:
        argv, akt = regler_argv(book_id, stage, werte, wer)
        if nur_vorschau:
            return {"ok": True, "cmd": " ".join(argv[1:])}
        _recht(book_id, akt, wer)
        return {"ok": True, "lauf": LAEUFE.start(book_id, argv, f"Regler {stage}")}
    except (ValueError, PermissionError, RuntimeError) as e:
        return {"ok": False, "fehler": str(e)}


# ------------------------------------------------------------------ Produktions-Ampel
# Quellen: Cockpit-Unterprozess (sicher), Stage-Zustand 'laeuft' in status.json (auch CLI/Bat-Laeufe),
# letzte Aktivitaet = juengste Aenderung im Werk-work-Ordner (status.json, kosten.jsonl, Ordner + Unterordner;
# atomares Schreiben aendert die Ordnerzeit). 'laeuft' ohne Aktivitaet > STILL_MIN -> evtl. abgebrochen.
STILL_MIN = 15
AMPEL_FARBEN = ("fehler", "angehalten", "handlung", "stockt", "produktion", "ruhe")   # Rang fuer Gesamtliste


def _aktivitaet(work):
    """Sekunden seit der letzten Aenderung im work-Ordner (eine Ebene tief), None = kein Ordner."""
    if not os.path.isdir(work):
        return None
    t = os.path.getmtime(work)
    with os.scandir(work) as it:
        for e in it:
            try:
                if e.is_dir() or e.name in ("status.json", "kosten.jsonl"):
                    t = max(t, e.stat().st_mtime)
            except OSError:
                pass
    import time as _t
    return max(0, int(_t.time() - t))


def _fehler(st):
    """Unerwarteter Fehler: Stopp mit 'Fehler: …' (Ausnahme in einer Stage, von run.py geschrieben)."""
    for t in [st] + list((st.get("teile") or {}).values()):
        if t.get("zustand") == "stopp" and any(str(g).startswith("Fehler:") for g in (t.get("gate") or {}).get("gruende") or []):
            return True
    return False


def _ampel_aus(d, work, job, naechster=None):
    """Ampel (CK 03.11.2026): produktion gruen · stockt gruen blinkend · handlung orange blinkend ·
    angehalten rot · fehler rot blinkend · ruhe grau (nichts laeuft, nichts offen)."""
    laufend, mensch, stopp, fehler = [], [], [], []
    for s in status.STAGES:
        st = d["stages"].get(s) or {}
        z = st.get("zustand")
        teile_l = [sc for sc, t in (st.get("teile") or {}).items() if t.get("zustand") == "laeuft"]
        if z == "laeuft" or teile_l:
            laufend.append({"stage": s, "seit": st.get("wann"), "teile": teile_l})
        elif _fehler(st):
            fehler.append(s)
        elif z == "stopp":
            stopp.append(s)
        elif z == "mensch":
            mensch.append(s)
    still = _aktivitaet(work)
    job_laeuft = bool(job and job.get("laeuft"))
    if job and job.get("exit") == 1 and not job_laeuft and not laufend:
        fehler = fehler or ["Lauf"]
    out = {"laufend": laufend, "mensch": mensch, "stopp": stopp, "fehler": fehler, "still_s": still,
           "cockpit_lauf": job_laeuft, "cockpit_art": job.get("art") if job else None}
    st_txt = ", ".join(x["stage"] for x in laufend) or "Start"
    ruhig = [x for x in (still, _log_alter(job) if job_laeuft else None) if x is not None]
    if (laufend or job_laeuft) and ruhig and min(ruhig) >= STILL_MIN * 60:
        still = min(ruhig)
        out.update(farbe="stockt", blink=True, text=f"Produktion stockt: Stage {st_txt}, keine Aktivitaet seit "
                                                     f"{still // 60} min")
    elif job_laeuft or laufend:
        out.update(farbe="produktion", blink=False, text=f"Produktion laeuft: Stage {st_txt}")
    elif fehler:
        out.update(farbe="fehler", blink=True, text=f"Unerwarteter Fehler: {', '.join(fehler)}")
    elif stopp:
        out.update(farbe="angehalten", blink=False, text=f"Produktion angehalten: Stopp {', '.join(stopp)}")
    elif mensch:
        out.update(farbe="handlung", blink=True, text=f"Handlungsbedarf: Entscheidung {', '.join(mensch)}")
    else:
        out.update(farbe="ruhe", blink=False, text="Nichts laeuft, nichts offen")
    return out


def _log_alter(job):
    """Sekunden seit der letzten Zeile im Log des Cockpit-Laufs (None = unbekannt)."""
    import time as _t
    try:
        return int(_t.time() - os.path.getmtime(os.path.join(BASE, job["logdatei"])))
    except (OSError, KeyError, TypeError):
        return None


def ampel(book_id):
    d = status.laden(book_id)
    return _ampel_aus(d, os.path.dirname(status.pfad(book_id)), LAEUFE.state(book_id, zeilen=0))


def _status_dateien():
    muster = (os.path.join(BASE, "authors", "*", "books", "*", "work", "status.json"),
              os.path.join(BASE, "users", "*", "works", "*", "work", "status.json"))
    for m in muster:
        for p in glob.glob(m):
            yield os.path.basename(os.path.dirname(os.path.dirname(p))), p


def ampel_alle():
    """Alle Werke mit status.json: wo wird produziert, wo wartet etwas? (ohne Index, ohne Anlegen)."""
    import json as _j
    werke = []
    for bid, p in _status_dateien():
        try:
            with open(p, encoding="utf-8") as f:
                d = _j.load(f)
        except (OSError, ValueError):
            continue
        a = _ampel_aus(d, os.path.dirname(p), LAEUFE.state(bid, zeilen=0))
        if a["farbe"] != "ruhe":
            werke.append({"book_id": bid, "farbe": a["farbe"], "text": a["text"]})
    for bid in LAEUFE.jobs:                      # Cockpit-Lauf fuer Werk ohne status.json
        if LAEUFE.jobs[bid]["exit"] is None and bid not in [w["book_id"] for w in werke]:
            werke.append({"book_id": bid, "farbe": "produktion", "text": f"Produktion laeuft ({LAEUFE.jobs[bid]['art']})"})
    rang = {f: i for i, f in enumerate(AMPEL_FARBEN)}
    werke.sort(key=lambda w: (rang[w["farbe"]], w["book_id"]))
    n = {f: sum(1 for w in werke if w["farbe"] == f) for f in AMPEL_FARBEN[:5]}
    return {"werke": werke, "anzahl": n}


# ------------------------------------------------------------------ Start: Werkliste + Upload (Schritt 1/2)
_LISTE = {"t": 0, "daten": None}


def werke_liste():
    """Alle Werke aus daten/index.json mit Autor + Titel (book.json/author.json) und Ampelfarbe. Cache 30 s."""
    import json as _j
    import time as _t
    if _LISTE["daten"] is not None and _t.time() - _LISTE["t"] < 30:
        return _LISTE["daten"]
    try:
        books = config._load_index().get("books", {})
    except Exception:
        books = {}
    autoren, out = {}, []
    for bid, a in sorted(books.items()):
        ordner = (os.path.join(BASE, "users", a[5:], "works", bid) if a.startswith("user:")
                  else os.path.join(BASE, "authors", a, "books", bid))
        try:
            with open(os.path.join(ordner, "book.json"), encoding="utf-8") as f:
                bj = _j.load(f)
        except (OSError, ValueError):
            bj = {}
        autor = bj.get("autor_name")
        if not autor and a and not a.startswith("user:"):
            if a not in autoren:
                try:
                    with open(os.path.join(BASE, "authors", a, "author.json"), encoding="utf-8") as f:
                        autoren[a] = _j.load(f).get("name_display") or a
                except (OSError, ValueError):
                    autoren[a] = a
            autor = autoren[a]
        farbe = None
        sp = os.path.join(ordner, "work", "status.json")
        if os.path.exists(sp):
            try:
                with open(sp, encoding="utf-8") as f:
                    farbe = _ampel_aus(_j.load(f), os.path.dirname(sp), LAEUFE.state(bid, zeilen=0))["farbe"]
            except (OSError, ValueError):
                pass
        out.append({"book_id": bid, "autor": autor or "", "titel": bj.get("titel_original") or bid,
                    "privat": a.startswith("user:"), "ampel": farbe})
    _LISTE.update(t=_t.time(), daten=out)
    return out


UPLOAD_DIR = os.path.join(BASE, "daten", "uploads")


def upload(art, dateiname, inhalt, wer, meta=None):
    """Upload speichern und Neuanlage als Unterprozess starten.
    epub -> Stage 150 (Neuanlage) · txt -> Stage 100 --txt (Eingangsart user_txt; meta: titel, autor, sprache, todesjahr)."""
    import re as _re
    meta = meta or {}
    try:
        wer = s080_mandant.nutzer(wer)
        if art not in ("epub", "txt"):
            raise ValueError(f"Art {art!r} unbekannt")
        name = _re.sub(r"[^A-Za-z0-9._-]+", "_", os.path.basename(dateiname or f"upload.{art}"))[:80]
        if not name.lower().endswith("." + art):
            raise ValueError(f"Datei ist kein .{art}")
        if art == "txt":
            if not (meta.get("titel") or "").strip():
                raise ValueError("Titel fehlt")
            if (meta.get("sprache") or "") not in bestellung.sprachliste():
                raise ValueError(f"Sprache fehlt/ungueltig (erlaubt {', '.join(bestellung.sprachliste())})")
            try:
                inhalt.decode("utf-8")
            except UnicodeDecodeError:
                raise ValueError("TXT ist nicht UTF-8")
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        pfad = os.path.join(UPLOAD_DIR, f"{dt.datetime.now():%Y%m%d_%H%M%S}_{name}")
        with open(pfad, "wb") as f:
            f.write(inhalt)
        vorher = set(werke())
        if art == "epub":
            argv = [PY, "-m", "pipeline.s150_epub_import", pfad, "--user", wer.lower(), "--wer", wer]
        else:
            argv = [PY, os.path.join("tools", "s100_anlegen.py"), "--txt", pfad, f"--titel={meta['titel'].strip()}",
                    f"--autor={(meta.get('autor') or '').strip()}", f"--sprache={meta['sprache']}", "--wer", wer]
            if str(meta.get("todesjahr") or "").strip():
                argv.append(f"--todesjahr={int(meta['todesjahr'])}")
        st = LAEUFE.start("_upload", argv, f"{art.upper()}-Upload {name}")
        LAEUFE.jobs["_upload"]["vorher"] = vorher
        return {"ok": True, "lauf": st}
    except (ValueError, RuntimeError, OSError) as e:
        return {"ok": False, "fehler": str(e)}


def upload_stand():
    """Stand des Uploads; nach Ende: neu angelegte Book-ID(s)."""
    st = LAEUFE.state("_upload", zeilen=40)
    if st and not st["laeuft"]:
        st["neu"] = sorted(set(werke()) - LAEUFE.jobs["_upload"].get("vorher", set()))
        _LISTE["daten"] = None
    return st


# ------------------------------------------------------------------ Gate-Monitore (Phase 3, Bau ab 04.11.2026)
# Rahmen: je Stage eine Ansicht (/monitor#<id>/<stage>), Schema 1 Anzeigen · 2 Bearbeiten · 3 Speichern ·
# 4 Freigeben · 5 Ruecksprung (claude/GATE_MONITORE.md). Speichern nur ueber das Stage-Modul (Unterprozess),
# dessen Lauf die Stage zugleich neu prueft. Stages ohne eigenen Monitor zeigen Befunde/Metriken/Manifeste.
MONITOR_DATEN = {}       # stage -> f(book_id) -> dict
MONITOR_SPEICHERN = {}   # stage -> f(book_id, eingabe, wer) -> argv (Stage-Modul)


def monitor(book_id, stage, wer=None):
    stage = status._norm(stage)
    w = werk(book_id, wer)
    st = next((s for s in w["stages"] if s["stage"] == stage), None)
    if st is None:
        return {"fehler": f"Stage {stage} unbekannt"}
    daten = dfehler = None
    f = MONITOR_DATEN.get(stage)
    if f:
        try:
            daten = f(book_id)
        except Exception as e:
            dfehler = f"{type(e).__name__}: {e}"
    kette_kurz = [{"stage": s["stage"], "name": s["name"], "zustand": s["zustand"]} for s in w["stages"] if s["bestellt"]]
    return {"book_id": book_id, "wer": w["wer"], "rolle": w["rolle"], "rechte": w["rechte"], "ampel": w["ampel"],
            "run_mode": w["run_mode"], "lauf": w["lauf"], "naechster": w["naechster"], "kette": kette_kurz,
            "titel": _titel(book_id),
            "stage": st, "monitor": stage in MONITOR_DATEN, "daten": daten, "daten_fehler": dfehler}


def _titel(book_id):
    try:
        return bestellung.lesen(book_id).roh.get("titel_original") or book_id
    except Exception:
        return book_id


def monitor_speichern(book_id, stage, eingabe, wer):
    """'Uebernehmen und neu pruefen': Stage-Modul als Unterprozess mit den Monitor-Werten."""
    try:
        stage = status._norm(stage)
        f = MONITOR_SPEICHERN.get(stage)
        if not f:
            raise ValueError(f"Stage {stage}: kein Monitor zum Speichern")
        _recht(book_id, "bestellen", wer)
        argv = f(book_id, eingabe or {}, s080_mandant.nutzer(wer))
        if eingabe.get("nur_vorschau"):
            return {"ok": True, "cmd": " ".join(argv[1:])}
        return {"ok": True, "lauf": LAEUFE.start(book_id, argv, f"Monitor {stage}: übernehmen und neu prüfen")}
    except (ValueError, PermissionError, RuntimeError, OSError) as e:
        return {"ok": False, "fehler": str(e)}


# ---- 100 Anlegen
def _m100_daten(book_id):
    import datetime as _d
    import json as _j
    from tools import s100_anlegen as S
    b = bestellung.lesen(book_id)
    roh = b.roh
    ordner = bestellung.werkordner(book_id)
    jahr = _d.date.today().year
    ap = S._author_pfad(roh, ordner)
    aj = {}
    if os.path.exists(ap):
        with open(ap, encoding="utf-8") as f:
            aj = _j.load(f)

    def pd(person, name_, tj, quelle=None):
        nw = [n for n in S.nachweise(roh) if person in (n.get("deckt") or [])]
        grenze = int(tj) + S.PD_JAHRE if tj not in (None, "") else None
        ok = bool(nw) or (grenze is not None and grenze < jahr)
        return {"person": person, "name": name_, "todesjahr": tj, "todesjahr_quelle": quelle, "grenze": grenze,
                "ok": ok, "per_nachweis": bool(nw) and not (grenze is not None and grenze < jahr),
                "nachweise": [S.nachweis_text(n) for n in nw]}
    personen = [pd("autor", aj.get("name_display") or "", aj.get("todesjahr"),
                   (aj.get("todesjahr_quelle") or {}).get("art") if isinstance(aj.get("todesjahr_quelle"), dict) else None)]
    if (roh.get("quell_uebersetzer") or "").strip():
        personen.append(pd("uebersetzer", roh["quell_uebersetzer"], roh.get("quell_uebersetzer_todesjahr")))
    raw = os.path.join(ordner, "raw.txt")
    rt = {"vorhanden": os.path.exists(raw)}
    if rt["vorhanden"]:
        with open(raw, encoding="utf-8", errors="replace") as f:
            text = f.read()
        s, e, kern = S.text_rahmen(text)
        ms, me = S.START.search(text), S.ENDE.search(text)
        rt.update(zeichen=len(text), zeilen=text.count("\n") + 1, kern=len(kern.strip()), min=S.MIN_ZEICHEN,
                  start=text.count("\n", 0, ms.start()) + 1 if ms else None,
                  ende=text.count("\n", 0, me.start()) + 1 if me else None)
    tq = roh.get("textquelle") or {}
    gid = roh.get("gutenberg_id") or ""
    return {"titel": roh.get("titel_original") or book_id, "quelle": roh.get("quelle") or ("gutenberg" if gid else ""),
            "gutenberg_id": gid, "gutenberg_link": f"https://www.gutenberg.org/ebooks/{gid}" if gid else None,
            "textquelle": tq, "personen": personen, "jahr": jahr, "pd_jahre": S.PD_JAHRE,
            "nachweise": [dict(n, text=S.nachweis_text(n)) for n in S.nachweise(roh)],
            "rechte_art": b.rechte.get("art"), "quellsprache": b.quellsprache,
            "sprachliste": list(bestellung.sprachliste()), "sprache_ok": b.quellsprache in bestellung.sprachliste(),
            "rohtext": rt, "rohtext_url": f"/api/werk/{book_id}/rohtext"}


def _m100_argv(book_id, e, wer):
    import re as _re
    argv = [PY, os.path.join("tools", "s100_anlegen.py"), book_id, "--wer", wer]
    grund = (e.get("grund") or "").strip()
    for k, flag in (("todesjahr", "--todesjahr"), ("uebersetzer_todesjahr", "--uebersetzer-todesjahr")):
        if str(e.get(k) or "").strip():
            argv.append(f"{flag}={int(e[k])}")
    if e.get("quellsprache"):
        if e["quellsprache"] not in bestellung.sprachliste():
            raise ValueError("Quellsprache nicht in Sprachliste")
        argv.append(f"--quellsprache={e['quellsprache']}")
    n = e.get("nachweis") or {}
    if n.get("art"):
        deckt = [p for p in (n.get("deckt") or []) if p in ("autor", "uebersetzer")]
        if not deckt:
            raise ValueError("Nachweis: deckt Autor und/oder Übersetzer wählen")
        if n["art"] == "url":
            argv.append(f"--pd-url={(n.get('url') or '').strip()}")
        elif n["art"] == "rechteinhaber":
            ra = n.get("rechte_art") or "eigene"
            if ra not in ("eigene", "lizenz"):
                raise ValueError("Rechteinhaber: eigene|lizenz")
            argv.append(f"--rechteinhaber={ra}")
        elif n["art"] == "andere_quelle":
            argv.append(f"--pd-quelle={(n.get('quelle') or '').strip()}")
            if (n.get("url") or "").strip():
                argv.append(f"--pd-url={n['url'].strip()}")
        else:
            raise ValueError(f"Nachweis-Art {n['art']!r} unbekannt")
        argv.append(f"--deckt={','.join(deckt)}")
    url = (e.get("textquelle_url") or "").strip()
    if url:
        if not _re.match(r"^https?://", url):
            raise ValueError("andere Quelle: nur http(s)-URL (Datei über 'Datei laden' in den Editor)")
        argv.append(f"--textquelle={url}")
    if e.get("rohtext") is not None:
        if url:
            raise ValueError("Editor-Text und andere Quelle schließen sich aus")
        if not grund:
            raise ValueError("Grund ist Pflicht (Rohtext geändert)")
        p = os.path.join(config.work_dir(book_id), "100_editor.txt")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(e["rohtext"])
        argv += [f"--rohtext-aus={p}", f"--grund={grund}"]
    if e.get("neu_laden"):
        argv.append("--force")
    return argv


def rohtext(book_id):
    p = os.path.join(bestellung.werkordner(book_id), "raw.txt")
    with open(p, "rb") as f:
        return f.read()


MONITOR_DATEN["100"] = _m100_daten
MONITOR_SPEICHERN["100"] = _m100_argv
