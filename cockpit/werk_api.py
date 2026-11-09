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


_HILFE_NAMEN = {}


def name(s):
    if s in NAMEN:
        return NAMEN[s]
    if not _HILFE_NAMEN:
        _HILFE_NAMEN.update({k: v.get("name") for k, v in hilfe().items() if isinstance(v, dict)} or {"_": None})
    if _HILFE_NAMEN.get(s):
        return _HILFE_NAMEN[s]
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


MONITOR_TEIL = {}        # stage -> f(book_id, query) -> dict (nachgeladene Teile, z. B. ein Kapitel)


def monitor_teil(book_id, stage, q):
    try:
        f = MONITOR_TEIL.get(status._norm(stage))
        if not f:
            raise ValueError(f"Stage {stage}: kein Teil-Abruf")
        return f(book_id, q)
    except (ValueError, OSError, RuntimeError) as e:
        return {"fehler": str(e)}


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


def _nachweis_argv(n):
    """Baustein PD-/Rechte-Nachweis (100 + 110) -> CLI-Flags des Stage-Moduls."""
    argv = []
    n = n or {}
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
    return argv


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
    argv += _nachweis_argv(e.get("nachweis"))
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
        ed = os.path.join(config.work_dir(book_id), "_editor")     # nicht work/100_* (kein Stage-Ergebnis)
        os.makedirs(ed, exist_ok=True)
        p = os.path.join(ed, "100_rohtext.txt")
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


# ---- 110 Wikidata
def _m110_daten(book_id):
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
    kp = os.path.join(config.work_dir(book_id), "110_kandidaten.json")
    kand = {}
    if os.path.exists(kp):
        with open(kp, encoding="utf-8") as f:
            kand = _j.load(f)
    tj = aj.get("todesjahr")
    nw = [n for n in S.nachweise(roh) if "autor" in (n.get("deckt") or [])]
    grenze = int(tj) + S.PD_JAHRE if tj not in (None, "") else None
    fass = {f.get("sprache"): f for f in roh.get("fassungen", []) if isinstance(f, dict)}
    titel = [{"sprache": lg, "titel": (fass.get(lg) or {}).get("titel") or "",
              "quelle": (fass.get(lg) or {}).get("titel_quelle") if (fass.get(lg) or {}).get("titel") else None,
              "ok": ((fass.get(lg) or {}).get("titel_quelle") in ("original", "wikidata", "manuell"))
                    and bool((fass.get(lg) or {}).get("titel"))} for lg in b.sprachen]
    titelei = []
    raw = os.path.join(ordner, "raw.txt")
    if os.path.exists(raw):
        with open(raw, encoding="utf-8", errors="replace") as f:
            for i, z in enumerate(f):
                if i >= 60:
                    break
                titelei.append(z.rstrip("\r\n"))
    gid = roh.get("gutenberg_id") or ""
    return {"autor": {"name": aj.get("name_display") or "", "geburtsjahr": aj.get("geburtsjahr"), "todesjahr": tj,
                      "qid": aj.get("wikidata_id") or "", "verified": bool(aj.get("verified")),
                      "todesjahr_quelle": aj.get("todesjahr_quelle"), "wikipedia": aj.get("quelle_weich") or "",
                      "geburtsort": aj.get("geburtsort") or ""},
            "autor_kandidaten": kand.get("autor") or [], "autor_kandidaten_wann": kand.get("autor_wann"),
            "werk_kandidaten": kand.get("werk") or [], "werk_kandidaten_wann": kand.get("werk_wann"),
            "pd": {"jahr": jahr, "pd_jahre": S.PD_JAHRE, "grenze": grenze, "ok": bool(nw) or (grenze is not None and grenze < jahr),
                   "per_nachweis": bool(nw) and not (grenze is not None and grenze < jahr),
                   "nachweise": [S.nachweis_text(n) for n in nw]},
            "werk": {"qid": roh.get("work_wikidata_id") or "", "titel_original": roh.get("titel_original") or "",
                     "erscheinungsjahr": roh.get("erscheinungsjahr")},
            "titel": titel, "quellsprache": b.quellsprache, "uebersetzer": roh.get("quell_uebersetzer") or "",
            "gutenberg_id": gid, "gutenberg_link": f"https://www.gutenberg.org/ebooks/{gid}" if gid else None,
            "titelei": titelei, "eigenes_werk": config.eigene_rechte(book_id)}


def _m110_argv(book_id, e, wer):
    import re as _re
    argv = [PY, "-m", "pipeline.s110_wikidata", book_id, "--wer", wer]
    for k, flag in (("autor_qid", "--autor-qid"), ("werk_qid", "--werk-qid")):
        v = (e.get(k) or "").strip().upper()
        if v:
            if not _re.fullmatch(r"Q\d+", v):
                raise ValueError(f"{flag}: {v!r} ist keine Q-ID")
            argv.append(f"{flag}={v}")
    for lg, t in (e.get("titel") or {}).items():
        if lg not in bestellung.sprachliste():
            raise ValueError(f"Titel: Sprache {lg!r} unbekannt")
        if (t or "").strip():
            argv.append(f"--titel={lg}={t.strip()}")
    argv += _nachweis_argv(e.get("nachweis"))
    if e.get("neu"):
        argv.append("--neu")
    return argv


MONITOR_DATEN["110"] = _m110_daten
MONITOR_SPEICHERN["110"] = _m110_argv


# ---- 115 Fassungsweiche
def _m115_daten(book_id):
    from pipeline import s115_fassung as S, s095_produktwahl as P
    b = bestellung.lesen(book_id)
    ordner = bestellung.werkordner(book_id)
    df, dh = S.default(b)
    z = P.zeichen(book_id)
    satz = getattr(config, "ANGEBOT_USD_100K", {}).get("modernisierung", 0)
    probe = []
    raw = os.path.join(ordner, "raw.txt")
    if os.path.exists(raw):
        with open(raw, encoding="utf-8", errors="replace", newline="") as f:
            t = f.read().replace("\r\r\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
        abs_ = [a.strip() for a in t.split("\n\n") if len(a.strip()) > 200]
        if abs_:
            i = len(abs_) // 3
            probe = [" ".join(a.split()) for a in abs_[i:i + 3]]
        else:   # Absatzgrenzen nicht erkennbar (Leerzeile nach jeder Zeile): 3 Bloecke zu 8 Zeilen
            zl = [x.strip() for x in t.split("\n") if x.strip()]
            i = len(zl) // 3
            probe = [" ".join(zl[i + k * 8:i + k * 8 + 8]) for k in range(3) if zl[i + k * 8:]]
    return {"fassung": b.fassung if "fassung" not in b.abgeleitet else None,
            "default": df, "default_herkunft": dh,
            "mandant": b.mandant, "mandant_art": b.mandant_art, "quelle": b.roh.get("quelle"),
            "quellsprache": b.quellsprache, "modern_sprachen": list(S.MODERN_SPRACHEN),
            "bearbeitung": b.rechte.get("bearbeitung"), "zeichen": z,
            "angebot_usd": round(satz * z / 100000, 2) if z else None,
            "vermerk": S.VERMERK, "modernisiert_vorhanden": S._modernisiert_vorhanden(book_id),
            "probe": probe}


def _m115_argv(book_id, e, wer):
    f = e.get("fassung")
    if f not in ("modernisiert", "original"):
        raise ValueError("Fassung: modernisiert oder original wählen")
    return [PY, "-m", "pipeline.s115_fassung", book_id, "--wer", wer,
            "--modernisieren", "ja" if f == "modernisiert" else "nein"]


MONITOR_DATEN["115"] = _m115_daten
MONITOR_SPEICHERN["115"] = _m115_argv


# ---- 120 Modernisierung
def _m120_kap(book_id):
    """-> (b, S, kap_orig [(titel, absaetze)], ref, herkunft, fehler). Quelle wie Stage 120 (ohne LLM)."""
    from pipeline import s120_modernisierung as S
    b = bestellung.lesen(book_id)
    try:
        kap, ref, herkunft = S.original_kapitel(book_id, b)
        return b, S, kap, ref, herkunft, None
    except (FileNotFoundError, RuntimeError) as e:
        return b, S, [], None, None, str(e)


def _m120_neu(S, book_id, k):
    p = os.path.join(S.mod_dir(book_id), f"chapter-{k}.json")
    return S._lesen(p) if os.path.exists(p) else None


def _m120_daten(book_id):
    from pipeline import s115_fassung as F
    b, S, kap, ref, herkunft, fehler = _m120_kap(book_id)
    fassung = b.fassung or "original"
    if fassung == "modernisiert" and b.quellsprache not in F.MODERN_SPRACHEN:
        fassung = "original"
    liste, param, z_ges = [], None, 0
    for k, (t, po) in enumerate(kap, 1):
        n = _m120_neu(S, book_id, k) or {}
        pn = n.get("paragraphs") or []
        zo, zn = S._zeichen(po), S._zeichen(pn) if pn else 0
        z_ges += zo
        aus = 0
        for a, c in zip(po, pn):
            if a != S.HR and len(a) >= S.AUSREISSER_MIN_ZEICHEN and not S.AUSREISSER[0] <= len(c) / len(a) <= S.AUSREISSER[1]:
                aus += 1
        param = param or n.get("param")
        liste.append({"k": k, "titel": t, "absaetze": len(po), "woerter": S._woerter(po),
                      "vorhanden": bool(pn), "aktuell": n.get("quelle_hash") == S.hash_obj({"t": t, "p": po}),
                      "fassung": n.get("fassung"), "laenge": round(zn / zo, 2) if pn and zo else None,
                      "ausreisser": aus, "fehlend": len(n.get("fehlend") or []), "manuell": len(n.get("manuell") or [])})
    standard = S._param(None, None, None, None)
    return {"fassung": fassung, "fassung_aus_115": "fassung" not in b.abgeleitet, "fehler": fehler,
            "herkunft": herkunft, "referenz": ref, "kapitel": liste,
            "bestaetigt": S.kapitel_bestaetigt(book_id, kap) if kap else False,
            "titel_treffer": round(S.titel_treffer(kap, ref), 3) if ref else None,
            "param": param if isinstance(param, dict) and "staerke" in param else None,
            "standard": standard, "staerken": list(S.SYS), "kosten_usd": round(S._kosten(z_ges), 2),
            "grenzen": {"laenge": S.LAENGE, "ausreisser": S.AUSREISSER, "min_zeichen": S.AUSREISSER_MIN_ZEICHEN},
            "kurz_woerter": S.KURZ_WOERTER}


def _m120_teil(book_id, q):
    b, S, kap, _r, _h, fehler = _m120_kap(book_id)
    if fehler:
        raise ValueError(fehler)
    k = int(q.get("k") or 1)
    if not 1 <= k <= len(kap):
        raise ValueError(f"Kapitel {k} gibt es nicht")
    t, po = kap[k - 1]
    n = _m120_neu(S, book_id, k) or {}
    pn = n.get("paragraphs") or []
    fehl, man = set(n.get("fehlend") or []), set(n.get("manuell") or [])
    paare = []
    for i, a in enumerate(po):
        c = pn[i] if i < len(pn) else None
        q_ = round(len(c) / len(a), 2) if c is not None and a and a != S.HR else None
        paare.append({"n": i + 1, "original": a, "neu": c, "q": q_, "hr": a == S.HR,
                      "ausreisser": bool(q_ is not None and len(a) >= S.AUSREISSER_MIN_ZEICHEN
                                         and not S.AUSREISSER[0] <= q_ <= S.AUSREISSER[1]),
                      "gleich": c == a, "fehlend": i in fehl, "manuell": i in man})
    return {"k": k, "titel": t, "paare": paare, "fassung": n.get("fassung")}


def _m120_argv(book_id, e, wer):
    import re as _re
    argv = [PY, "-m", "pipeline.s120_modernisierung", book_id, "--wer", wer]
    if e.get("kapitel_ok"):
        argv.append("--kapitel-ok")
    if e.get("staerke"):
        argv.append(f"--staerke={e['staerke']}")
    if e.get("temperatur") not in (None, ""):
        t = float(e["temperatur"])
        if not 0 <= t <= 1.5:
            raise ValueError("Temperatur 0-1,5")
        argv.append(f"--temperatur={t}")
    if e.get("stueck") not in (None, ""):
        argv.append(f"--stueck={int(e['stueck'])}")
    for k in e.get("kapitel") or []:
        argv.append(f"--kapitel={int(k)}")
    for s in e.get("absatz") or []:
        if not _re.fullmatch(r"\d+:\d+", s):
            raise ValueError(f"Absatz {s!r}: Form K:N")
        argv.append(f"--absatz={s}")
    for s, txt in (e.get("absatz_text") or {}).items():
        if not _re.fullmatch(r"\d+:\d+", s):
            raise ValueError(f"Absatz {s!r}: Form K:N")
        txt = " ".join((txt or "").split())
        if not txt:
            raise ValueError(f"Absatz {s}: Text leer")
        argv.append(f"--absatz-text={s}={txt}")
    if e.get("force"):
        argv.append("--force")
    return argv


MONITOR_DATEN["120"] = _m120_daten
MONITOR_SPEICHERN["120"] = _m120_argv
MONITOR_TEIL["120"] = _m120_teil


# ---- 150 ePub-Import
def _m150_epub(book_id):
    from pipeline import s150_epub_import as E
    b = bestellung.lesen(book_id)
    ordner = bestellung.werkordner(book_id)
    return b, E, ordner, E.epub_finden(ordner, b.roh)


def _rel(p):
    return os.path.relpath(p, BASE).replace(os.sep, "/") if p else None


def _m150_daten(book_id):
    import json as _j
    b, E, ordner, ep = _m150_epub(book_id)
    bp = os.path.join(ordner, "work", "ingest_bericht.json")
    ber = {}
    if os.path.exists(bp):
        with open(bp, encoding="utf-8") as f:
            ber = _j.load(f)
    opt = dict(E.OPT_STANDARD, **(b.roh.get("epub_import") or {}))
    zwang = opt.get("seiten") or {}
    seiten = []
    for art, liste in (("inhalt", ber.get("inhalt")), ("notizen", ber.get("notizseiten")), ("weg", ber.get("entfernt"))):
        for x in liste or []:
            seiten.append({"datei": x["datei"], "art": art, "grund": x.get("grund"), "zeichen": x.get("zeichen"),
                           "zwang": zwang.get(x["datei"]) or zwang.get(os.path.basename(x["datei"]))})
    if ep:                                            # Spine-Reihenfolge aus der Quelle
        try:
            z, opf_path = E.oeffnen(ep)
            opf = E.opf_lesen(z, opf_path)
            ordnung = [opf["items"][i]["href"] for i in opf["spine"] if i in opf["items"]]
            seiten.sort(key=lambda x: ordnung.index(x["datei"]) if x["datei"] in ordnung else 9999)
        except Exception:
            pass
    um = ber.get("umfang") or b.roh.get("umfang") or {}
    cov = os.path.join(ordner, b.roh.get("cover")) if b.roh.get("cover") else None
    kt = b.roh.get("klappentext") or {}
    vorschlag = None
    if not ep and ber.get("datei"):                   # Altwerke: Quelle liegt noch im Eingangsordner
        v = os.path.join(BASE, "_epub_import", ber["datei"])
        vorschlag = _rel(v) if os.path.exists(v) else None
    return {"datei": ber.get("datei"), "zeit": ber.get("zeit"), "epub": _rel(ep), "epub_vorschlag": vorschlag,
            "bericht": bool(ber),
            "titel": ber.get("titel") or b.roh.get("titel_original") or "", "titel_kandidaten": ber.get("titel_kandidaten") or [],
            "autor": ber.get("autor") or "", "sprache": b.quellsprache, "opf_sprache": ber.get("opf_sprache", ber.get("sprache")),
            "sprachliste": list(bestellung.sprachliste()), "seiten": seiten, "kapitel": ber.get("kapitel") or [],
            "umfang": um, "warnungen": ber.get("warnungen") or [], "opt": {k: opt.get(k) for k in ("bilder", "fussnoten", "cover")},
            "cover": _rel(cov) if cov and os.path.exists(cov) else None, "cover_info": ber.get("cover") or {},
            "klappentext": kt if isinstance(kt, dict) else {}, "mandant_art": b.mandant_art,
            "grenzen": {"zeichen": E.MIN_ZEICHEN, "inhaltsanteil": E.MIN_INHALTSANTEIL}}


def _m150_teil(book_id, q):
    b, E, ordner, ep = _m150_epub(book_id)
    if not ep:
        v = _m150_daten(book_id).get("epub_vorschlag")
        ep = os.path.join(BASE, v) if v else None
    if not ep:
        raise ValueError("Quell-ePub nicht im Werkordner (quelle/)")
    z, opf_path = E.oeffnen(ep)
    opf = E.opf_lesen(z, opf_path)
    d = q.get("datei") or ""
    it = next((i for i in opf["items"].values() if i.get("href") == d), None)
    if not it:
        raise ValueError(f"Seite {d!r} nicht im ePub")
    s = z.read(it["path"]).decode("utf-8", "ignore")
    body = s[s.find("<body"):] if "<body" in s else s
    import re as _re
    body = _re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body, flags=_re.S)
    body = _re.sub(r"</(p|h\d|div|li|section)>", "\n", body)
    t = "\n".join(" ".join(x.split()) for x in _re.sub(r"<[^>]+>", " ", body).split("\n") if x.strip())
    import html as _h
    t = _h.unescape(t)
    return {"datei": d, "zeichen": len(t), "text": t[:4000]}


def _m150_argv(book_id, e, wer):
    b, E, ordner, ep = _m150_epub(book_id)
    argv = [PY, "-m", "pipeline.s150_epub_import", book_id, "--wer", wer]
    for k in ("titel", "autor"):
        v = " ".join((e.get(k) or "").split())
        if v:
            argv.append(f"--{k}={v}")
    if e.get("sprache"):
        if e["sprache"] not in bestellung.sprachliste():
            raise ValueError(f"Sprache {e['sprache']!r} nicht in der Sprachliste")
        argv.append(f"--sprache={e['sprache']}")
    bekannt = {x["datei"] for x in _m150_daten(book_id)["seiten"]}
    for art in ("behalten", "entfernen"):
        for d in e.get(art) or []:
            if d not in bekannt:
                raise ValueError(f"Seite {d!r} unbekannt")
            argv.append(f"--{art}={d}")
    for k in ("bilder", "fussnoten"):
        if e.get(k) in ("ja", "nein"):
            argv.append(f"--{k}={e[k]}")
    if e.get("cover") in ("epub", "neu"):
        argv.append(f"--cover={e['cover']}")
    if e.get("force"):
        argv.append("--force")
    if e.get("epub"):
        q = os.path.normpath(os.path.join(BASE, e["epub"]))
        if not q.startswith(BASE) or not q.lower().endswith(".epub") or not os.path.isfile(q):
            raise ValueError(f"ePub {e['epub']!r} nicht gefunden")
        argv.append(f"--epub={q}")
        ep = q
    if len(argv) > 6 and not ep:
        raise ValueError("Quell-ePub fehlt im Werkordner (quelle/) – Regler brauchen die Quelldatei")
    return argv


MONITOR_DATEN["150"] = _m150_daten
MONITOR_SPEICHERN["150"] = _m150_argv
MONITOR_TEIL["150"] = _m150_teil


# ---- 190 Eingangsvertrag (keine Regler: Vertragsliste als Trockenlauf)
def _m190_daten(book_id):
    import contextlib as _c, io as _io
    from pipeline import s190_vertrag as V
    with _c.redirect_stdout(_io.StringIO()):
        g = V.run(book_id, trocken=True)
    return {"ergebnis": (g.ergebnis or {}).get("ergebnis"), "ruecksprung": (g.ergebnis or {}).get("ruecksprung"),
            "pruefungen": [{"name": p["name"], "ok": bool(p["ok"]), "text": p["text"], "art": p["bei_fehler"],
                            "wert": p["wert"] if isinstance(p["wert"], (int, float, str, bool, type(None))) else str(p["wert"]),
                            "ruecksprung": p["ruecksprung"]} for p in g.pruefungen],
            "metriken": {k: g.metriken.get(k) for k in ("quelle", "fassung", "zielsprachen", "mandant", "kapitel",
                                                         "woerter", "zeichen") if k in g.metriken},
            "max": V.TEXT_MAX}


MONITOR_DATEN["190"] = _m190_daten


# ---- 195 Teilung
HOER_ZPH = 55_000   # Zeichen je Hoerstunde (Schaetzung)


def _m195_grenze(book_id, roh=None):
    import json as _j
    from pipeline import s195_teilung as T
    p = os.path.join(config.work_dir(book_id), "195_teilung.json")
    alt = {}
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            alt = _j.load(f)
    return alt, alt.get("grenze") or T.GRENZE


def _m195_daten(book_id):
    from pipeline import s195_teilung as T
    roh = bestellung.lesen(book_id).roh
    alt, grenze = _m195_grenze(book_id)
    kap = T.kapitel(book_id)
    aktuell = bool(alt) and alt.get("quelle_hash") == T._quelle_hash(book_id)
    if aktuell:
        teile, herkunft = alt.get("teile") or [], alt.get("herkunft")
    elif kap:
        starts, herkunft = T.vorschlag(kap, grenze, alt.get("teile_soll") if aktuell else None)
        teile = T._teile_liste(book_id, kap, starts or [0], {int(k): v for k, v in (alt.get("namen") or {}).items()})
    else:
        teile, herkunft = [], None
    geteilt = []
    for sl in roh.get("geteilt_in") or []:
        try:
            z = status.zustand(sl, "190")
        except Exception:
            z = "fehlt"
        geteilt.append({"slug": sl, "zustand_190": z})
    return {"grenze": grenze, "standard": T.GRENZE, "zph": HOER_ZPH,
            "zeichen": sum(z for _n, _t, z, _s in kap),
            "kapitel": [{"n": n, "titel": t, "zeichen": z, "gliederung": s} for n, t, z, s in kap],
            "teile": teile, "herkunft": herkunft, "aktuell": aktuell,
            "vorhanden": bool(alt), "entscheidung": alt.get("entscheidung") if aktuell else None,
            "wer": alt.get("wer") if aktuell else None, "wann": alt.get("wann") if aktuell else None,
            "teile_soll": alt.get("teile_soll") if aktuell else None, "geteilt_in": geteilt}


def _m195_teil(book_id, q):
    """Vorschlag fuer Grenze/Teilezahl berechnen, ohne zu schreiben -> Schnitte (Kapitelnummern)."""
    from pipeline import s195_teilung as T
    def z(k):
        v = (q.get(k) or [""])[0] if isinstance(q.get(k), list) else q.get(k)
        return int(v) if str(v or "").strip().isdigit() else None
    _alt, g0 = _m195_grenze(book_id)
    grenze, teile = z("grenze") or g0, z("teile")
    if grenze < 10_000:
        raise ValueError("Grenze mindestens 10.000 Zeichen")
    kap = T.kapitel(book_id)
    if not kap:
        raise ValueError("keine Kapitel (190/120 fehlt)")
    starts, herkunft = T.vorschlag(kap, grenze, teile)
    if not starts:
        raise ValueError(f"{teile} Teile bei {len(kap)} Kapiteln nicht moeglich")
    return {"schnitte": [kap[s][0] for s in starts if s > 0], "herkunft": herkunft}


def _m195_argv(book_id, e, wer):
    from pipeline import s195_teilung as T
    a = [PY, "-m", "pipeline.s195_teilung", book_id, "--wer", wer]
    n = len(T.kapitel(book_id))
    if e.get("grenze") not in (None, ""):
        g = int(e["grenze"])
        if g < 10_000:
            raise ValueError("Grenze mindestens 10.000 Zeichen")
        a.append(f"--grenze={g}")
    if e.get("schnitte") is not None:
        s = sorted({int(x) for x in e["schnitte"]})
        if any(x < 2 or x > n for x in s):
            raise ValueError(f"Schnitte nur an Kapitel 2…{n}")
        if not s and e.get("entscheidung") == "annehmen":
            raise ValueError("Annehmen ohne Schnitt: 1 Teil = keine Teilung (Ablehnen)")
        a.append(f"--schnitte={','.join(map(str, s))}" if s else "--teile=1")
    elif e.get("teile") not in (None, ""):
        a.append(f"--teile={int(e['teile'])}")
    for k, v in (e.get("namen") or {}).items():
        v = " ".join(str(v).split())
        if v:
            a.append(f"--name={int(k)}={v}")
    ent = e.get("entscheidung")
    if ent == "annehmen":
        a.append("--annehmen")
    elif ent == "ablehnen":
        a.append("--ablehnen")
    elif ent:
        raise ValueError(f"Entscheidung {ent!r}")
    return a


MONITOR_DATEN["195"] = _m195_daten
MONITOR_SPEICHERN["195"] = _m195_argv
MONITOR_TEIL["195"] = _m195_teil


# ---- Stage-Ergebnis (Monitor-Abschnitt "Ergebnis", CK 04.11.2026: Ergebnis je Stage ansehen)
ERGEBNIS_EXTRA = {"100": ["book.json", "raw.txt", "@author.json"], "110": ["book.json", "@author.json"], "115": ["book.json"], "120": ["raw_modernized.txt"],
                  "150": ["book.json", "work/ingest_bericht.json", "raw_modernized.txt"], "195": ["book.json"]}


def ergebnis(book_id, stage):
    """Dateien, die eine Stage hinterlaesst: Manifeste work/<stage>_* (auch Unterordner work/<stage>_*/),
    dazu je Stage feste Werkdateien (ERGEBNIS_EXTRA; '@' = Autorordner)."""
    stage = status._norm(stage)
    try:
        ordner = bestellung.werkordner(book_id)
        w = config.work_dir(book_id)
    except Exception as e:
        return {"fehler": str(e), "dateien": []}
    pfade = sorted(glob.glob(os.path.join(w, f"{stage}_*")))
    for x in ERGEBNIS_EXTRA.get(stage, []):
        if x.startswith("@"):
            try:
                a = bestellung.lesen(book_id).roh.get("author_slug")
                pfade.append(os.path.join(config.author_dir(a), x[1:]) if a
                             else os.path.join(os.path.dirname(os.path.dirname(ordner)), x[1:]))
            except Exception:
                pass
        else:
            pfade.append(os.path.join(ordner, x))
    out = []
    for p in pfade:
        for q in ([p] if os.path.isfile(p) else sorted(glob.glob(os.path.join(p, "**", "*"), recursive=True))
                  if os.path.isdir(p) else []):
            if not os.path.isfile(q):
                continue
            ext = os.path.splitext(q)[1].lower()
            art = ("json" if ext in (".json", ".jsonl") else "text" if ext in (".txt", ".md", ".log", ".csv", ".srt", ".vtt")
                   else "audio" if ext in (".wav", ".mp3", ".m4a", ".m4b", ".ogg") else "bild"
                   if ext in (".png", ".jpg", ".jpeg", ".webp") else "datei")
            out.append({"datei": os.path.relpath(q, BASE).replace("\\", "/"), "name": (os.path.relpath(q, w) if q.startswith(w) else os.path.relpath(q, ordner)
                                 if q.startswith(ordner) else os.path.basename(q)).replace("\\", "/"),
                        "art": art, "groesse": os.path.getsize(q),
                        "wann": dt.datetime.fromtimestamp(os.path.getmtime(q)).isoformat(timespec="seconds")})
            if len(out) >= 300:
                return {"dateien": out, "gekappt": True}
    return {"dateien": out}


# ---- Hilfe je Stage (config/stage_hilfe.json; Popup im Cockpit, Texte auch fuer docs/STAGE_SKRIPT.md)
def hilfe():
    import json as _j
    p = os.path.join(BASE, "config", "stage_hilfe.json")
    try:
        with open(p, encoding="utf-8") as f:
            return {k: v for k, v in _j.load(f).items() if not k.startswith("_")}
    except (OSError, ValueError):
        return {}
