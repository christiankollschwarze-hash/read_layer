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


# ---- 200 Tagging (Steckbrief GATE_MONITORE 200: Knotentext nicht editierbar, nur teilen/zusammen/Typ/Neu-Taggen)
def _m200_lesen(book_id, name):
    import json as _j
    p = os.path.join(config.work_dir(book_id), name)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return _j.load(f)


def _m200_kap(book_id):
    """Kapitel aus raw_modernized.txt wie Stage 200 -> [(titel, text)]."""
    from pipeline import s190_vertrag
    p = os.path.join(config.book_dir(book_id), "raw_modernized.txt")
    if not os.path.exists(p):
        raise FileNotFoundError("raw_modernized.txt fehlt (120 nicht gelaufen)")
    with open(p, encoding="utf-8") as f:
        _t, _a, kap = s190_vertrag.marken_lesen(f.read())
    return [(t, k.strip()) for t, k in kap]


def _m200_daten(book_id):
    from pipeline import s200_tagging as T
    b = bestellung.lesen(book_id)
    src = b.quellsprache or config.SOURCE_LANGUAGE
    pr = _m200_lesen(book_id, "200_pruefung.json") or {}
    tg = _m200_lesen(book_id, "200_tagging.json") or {}
    standard = config.MODELS.get("tagger")
    modell = ((tg.get("meta") or {}).get("tagging") or {}).get("modell") or standard
    kap = _m200_kap(book_id)
    pk = {k["kapitel"]: k for k in pr.get("kapitel") or []}
    liste = []
    for n, (t, txt) in enumerate(kap, 1):
        k = pk.get(n) or {}
        liste.append({"n": n, "titel": t, "zeichen": len(txt), "treue": k.get("treue"), "herkunft": k.get("herkunft"),
                      "knoten": k.get("knoten"), "abweichungen": k.get("abweichungen") or [],
                      "kosten": round(T.kosten_schaetzen(len(txt), modell), 4)})
    werk_abk = sorted(str(a) for a in b.roh.get("abkuerzungen") or [])
    korr = T.korrekturen_lesen(book_id)
    return {"sprache": src, "vorhanden": bool(pr), "kapitel": liste,
            "mehrsatz": pr.get("mehrsatz") or [], "ueberlang": pr.get("ueberlang") or [],
            "korrekturen": korr, "verworfen": pr.get("korrekturen_verworfen") or [],
            "abk_werk": werk_abk,
            "abk_sprache": sorted(set(T.abk_liste(book_id, b, src)) - {a.lower().rstrip(".") for a in werk_abk}),
            "modell": modell, "standard_modell": standard,
            "modelle": [m for m in getattr(config, "PREISE", {}) if m.startswith("deepseek")],
            "typen": [t for t in config.TAG_TYPES if t != "h"], "treue_min": T.TREUE_MIN, "lang_max": T.LANG_MAX,
            "kosten_alle": round(sum(k["kosten"] for k in liste), 4)}


def _m200_segmente(text, marken):
    """text + markierte Zeichenspannen -> [{t, aus}]; Spannen mit nur Leer-/Satzzeichen dazwischen zusammengefasst."""
    import re as _re
    zus = []
    for a, e in marken:
        if zus and not _re.search(r"\w", text[zus[-1][1]:a]):
            zus[-1][1] = e
        else:
            zus.append([a, e])
    out, pos = [], 0
    for a, e in zus:
        if a > pos:
            out.append({"t": text[pos:a], "aus": False})
        out.append({"t": text[a:e], "aus": True})
        pos = e
    if pos < len(text):
        out.append({"t": text[pos:], "aus": False})
    return out


def _m200_teil(book_id, q):
    """Kapitel k: Original | Knoten, Wortabweichungen (wie Treue in Stage 200) markiert."""
    import difflib
    from pipeline import s200_tagging as T
    v = q.get("k")
    k = int((v[0] if isinstance(v, list) else v) or 1)
    kap = _m200_kap(book_id)
    if not 1 <= k <= len(kap):
        raise ValueError(f"Kapitel {k} gibt es nicht")
    titel, txt = kap[k - 1]
    src = bestellung.lesen(book_id).quellsprache or config.SOURCE_LANGUAGE
    tg = _m200_lesen(book_id, "200_tagging.json") or {}
    pre = f"c{k:0{config.CHAPTER_DIGITS}d}_"
    knoten = [(tid, e) for tid, e in (tg.get("content") or {}).items() if tid.startswith(pre)]

    def tok(s):
        s2 = (s or "").replace(config.VERS_MARKE, " " * len(config.VERS_MARKE))
        for m in T._W.finditer(s2):
            w = m.group().lower().replace("’", "'").strip("'")
            if w:
                yield m.start(), m.end(), w
    ta = list(tok(txt))
    tb = [(i, a, e, w) for i, (_tid, n) in enumerate(knoten) if n.get("type") != "h" for a, e, w in tok(n.get(src))]
    sm = difflib.SequenceMatcher(None, [x[2] for x in ta], [x[3] for x in tb], autojunk=False)
    aus_a, aus_b = set(), set()
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op != "equal":
            aus_a.update(range(i1, i2))
            aus_b.update(range(j1, j2))
    mb = {}
    for j in sorted(aus_b):
        i, a, e, _w = tb[j]
        mb.setdefault(i, []).append((a, e))
    mehr = {m["id"]: m for m in ((_m200_lesen(book_id, "200_pruefung.json") or {}).get("mehrsatz") or [])}
    return {"k": k, "titel": titel,
            "original": _m200_segmente(txt, [ta[i][:2] for i in sorted(aus_a)]),
            "fehlend": len(aus_a), "zusaetzlich": len(aus_b),
            "knoten": [{"id": tid, "typ": n.get("type"), "text": n.get(src) or "",
                        "seg": _m200_segmente(n.get(src) or "", mb.get(i, [])), "aus": i in mb,
                        "mehrsatz": tid in mehr, "vorschlag": (mehr.get(tid) or {}).get("vorschlag")}
                       for i, (tid, n) in enumerate(knoten)]}


def _m200_argv(book_id, e, wer):
    import re as _re
    a = [PY, "-m", "pipeline.s200_tagging", book_id, "--wer", wer]
    ID = _re.compile(r"c\d+_\d+_[a-z]+")
    n_kap = len(_m200_kap(book_id))
    if e.get("modell"):
        if e["modell"] not in getattr(config, "PREISE", {}):
            raise ValueError(f"Modell {e['modell']!r} unbekannt")
        a.append(f"--modell={e['modell']}")
    kap = e.get("kapitel") or []
    if "alle" in [str(x) for x in kap]:
        a.append("--kapitel=alle")
    else:
        for k in sorted({int(x) for x in kap}):
            if not 1 <= k <= n_kap:
                raise ValueError(f"Kapitel {k} gibt es nicht")
            a.append(f"--kapitel={k}")
    ids = []
    for i, stelle in e.get("teilen") or []:
        if not ID.fullmatch(i) or not str(stelle).strip():
            raise ValueError(f"Teilen {i!r}: Knoten-ID und Stelle noetig")
        ids.append(i)
        a.append(f"--teilen={i}@{stelle}")
    for i in e.get("zusammen") or []:
        if not ID.fullmatch(i):
            raise ValueError(f"Zusammenfuehren {i!r}: Knoten-ID")
        ids.append(i)
        a.append(f"--zusammen={i}")
    for i, t in (e.get("typ") or {}).items():
        if not ID.fullmatch(i) or t not in config.TAG_TYPES or t == "h":
            raise ValueError(f"Typ {i!r}={t!r} ungueltig")
        ids.append(i)
        a.append(f"--typ={i}={t}")
    if len(ids) != len(set(ids)):
        raise ValueError("je Knoten nur eine Korrektur pro Lauf")
    for art in ("abk", "abk_weg"):
        for w in e.get(art) or []:
            w = str(w).strip().rstrip(".")
            if not w or " " in w:
                raise ValueError(f"Abkuerzung {w!r}: ein Wort ohne Punkt")
            a.append(f"--{art.replace('_', '-')}={w}")
    if e.get("lang") not in (None, ""):
        n = int(e["lang"])
        if n < 50:
            raise ValueError("Grenze ueberlang mindestens 50 Zeichen")
        a.append(f"--lang={n}")
    if e.get("trocken"):
        a.append("--trocken")
    return a


MONITOR_DATEN["200"] = _m200_daten
MONITOR_SPEICHERN["200"] = _m200_argv
MONITOR_TEIL["200"] = _m200_teil


# ---- 210 Profil (Steckbrief GATE_MONITORE 210)
def _m210_text(book_id):
    from pipeline import s210_profil as P
    tg = _m200_lesen(book_id, "200_tagging.json")
    if not tg:
        raise FileNotFoundError("200_tagging.json fehlt (200 nicht gelaufen)")
    src = bestellung.lesen(book_id).quellsprache or config.SOURCE_LANGUAGE
    return P._collect_source_text(tg, src)


def _m210_daten(book_id):
    from pipeline import s210_profil as P
    b = bestellung.lesen(book_id)
    src = b.quellsprache or config.SOURCE_LANGUAGE
    ziele = [z for z in (b.zielsprachen or []) if z != src]
    d = _m200_lesen(book_id, "210_profil.json") or {}
    prof = (d.get("meta") or {}).get("profile") or {}
    info = (d.get("meta") or {}).get("profil_info") or {}
    pr = _m200_lesen(book_id, "210_pruefung.json") or {}
    roh = b.roh
    text = _m210_text(book_id)
    reihe, teil = roh.get("reihe"), int(roh.get("teil") or 0)
    rp = (P.reihe_lesen(reihe) or {}) if reihe else {}
    grenzen = {**P.GRENZEN, **{k: int(v) for k, v in (roh.get("profil_grenzen") or {}).items()}}
    ff, gf = roh.get("figuren_fest") or {}, roh.get("glossar_fest") or {}

    def herkunft(name, fest, bereich):
        return "fest" if fest.get(name) else "reihe" if name in (rp.get(bereich) or {}) and teil >= 2 else "llm"
    figuren = [{"name": n, "werte": v if isinstance(v, dict) else {}, "treffer": P.figur_treffer(n, text),
                "herkunft": herkunft(n, ff, "characters")} for n, v in (prof.get("characters") or {}).items()]
    glossar = [{"begriff": k, "werte": v if isinstance(v, dict) else {}, "herkunft": herkunft(k, gf, "glossary"),
                "luecke": not isinstance(v, dict) or any(not (v.get(z) or "").strip() for z in ziele)}
               for k, v in (prof.get("glossary") or {}).items()]
    modell = info.get("modell") or config.MODELS.get("profiler")
    return {"sprache": src, "ziele": ziele, "vorhanden": bool(prof), "herkunft_profil": info.get("herkunft"),
            "modell": modell, "standard_modell": config.MODELS.get("profiler"),
            "modelle": [m for m in getattr(config, "PREISE", {}) if m.startswith("deepseek")],
            "zeichen": len(text), "kosten_neu": round(P.kosten_schaetzen(len(text), modell), 3),
            "style": prof.get("style") or {}, "voice_note_fest": roh.get("voice_note_fest"),
            "figuren": figuren, "figur_min": P.FIGUR_MIN, "glossar": glossar,
            "untranslated": prof.get("untranslated") or {}, "idioms": prof.get("idioms") or {},
            "grenzen": grenzen, "standard_grenzen": P.GRENZEN,
            "anzahl": {k: len(prof.get(k) or {}) for k in P.GRENZEN}, "voll": pr.get("voll") or {},
            "fest_entfernt": {"figuren": [k for k, v in ff.items() if v is None],
                              "glossar": [k for k, v in gf.items() if v is None]},
            "reihe": reihe, "teil": teil, "reihe_erbe": roh.get("reihe_erbe", True) is not False,
            "varianten": pr.get("varianten") or [], "neue_figuren": pr.get("neue_figuren") or [],
            "hoerspiel": bool(b.produkte_fuer(inhalt="hoerspiel"))}


def _m210_teil(book_id, q):
    from pipeline import s210_profil as P
    v = q.get("name")
    name = (v[0] if isinstance(v, list) else v) or ""
    if not name.strip():
        raise ValueError("Name fehlt")
    text = _m210_text(book_id)
    return {"name": name, "treffer": P.figur_treffer(name, text), "stellen": P.fundstellen(name, text, n=12)}


def _m210_argv(book_id, e, wer):
    from pipeline import s210_profil as P
    a = [PY, "-m", "pipeline.s210_profil", book_id, "--wer", wer]

    def sauber(x, was):
        x = " ".join(str(x or "").split())
        if not x:
            raise ValueError(f"{was} leer")
        return x
    if e.get("modell"):
        if e["modell"] not in getattr(config, "PREISE", {}):
            raise ValueError(f"Modell {e['modell']!r} unbekannt")
        a.append(f"--modell={e['modell']}")
    for art, opt in (("figur", "--figur"), ("glossar", "--glossar")):
        for name, felder in (e.get(art) or {}).items():
            name = sauber(name, "Name")
            if ":" in name:
                raise ValueError(f"{name!r}: Doppelpunkt im Namen nicht moeglich")
            for f, w in (felder or {}).items():
                if not __import__("re").fullmatch(r"[A-Za-z_][\w-]*", f):
                    raise ValueError(f"Feld {f!r} ungueltig")
                a.append(f"{opt}={name}:{f}={sauber(w, name + ' ' + f)}")
    for art, opt in (("figur_weg", "--figur-weg"), ("glossar_weg", "--glossar-weg")):
        for name in e.get(art) or []:
            a.append(f"{opt}={sauber(name, 'Name')}")
    if e.get("voice_note") is not None:
        a.append(f"--voice-note={' '.join(str(e['voice_note']).split())}")
    for k, n in (e.get("grenze") or {}).items():
        if k not in P.GRENZEN or not 5 <= int(n) <= 500:
            raise ValueError(f"Grenze {k}={n}: Bereich {list(P.GRENZEN)}, 5–500")
        a.append(f"--grenze={k}={int(n)}")
    if e.get("reihe") == "mit":
        a.append("--mit-reihe")
    elif e.get("reihe") == "ohne":
        a.append("--ohne-reihe")
    if e.get("neu"):
        a.append("--neu")
    if e.get("trocken"):
        a.append("--trocken")
    return a


MONITOR_DATEN["210"] = _m210_daten
MONITOR_SPEICHERN["210"] = _m210_argv
MONITOR_TEIL["210"] = _m210_teil


# ---- 310 Uebersetzung (Steckbrief GATE_MONITORE 310: nur Befundliste je Zielsprache)
def _m310_daten(book_id):
    from pipeline import s310_uebersetzung as P
    b = bestellung.lesen(book_id)
    roh = b.roh
    src = b.quellsprache or config.SOURCE_LANGUAGE
    ziele = [z for z in (b.zielsprachen or []) if z != src]
    vu = _m200_lesen(book_id, "300_voruebersetzung.json") or {}
    kap = P.saetze(vu, src) if vu else {}
    ids = [t for l in kap.values() for t, _q, _y in l]
    zeichen = sum(len(q) for l in kap.values() for _t, q, _y in l)
    ue = (_m200_lesen(book_id, "310_uebersetzung.json") or {})
    inh = ue.get("content") or {}
    meta = ue.get("meta") or {}
    pr = _m200_lesen(book_id, "310_pruefung.json") or {}
    korr = P.korrekturen_lesen(book_id)
    standard = config.MODELS.get("translator")
    modell = roh.get("uebersetzung_modell") or (meta.get("uebersetzung") or {}).get("modell") or standard
    laenge = list(roh.get("uebersetzung_laenge") or P.LAENGE)
    batch = int(roh.get("uebersetzung_batch") or getattr(config, "TRANSLATE_BATCH_SIZE", P.BATCH))
    n = max(1, len(ids))
    arten = ("sprache", "kopie", "verschmelzung", "schema", "laenge", "glossar")
    fass = {f.get("sprache"): f for f in roh.get("fassungen") or [] if isinstance(f, dict)}
    ohne = ((vu.get("meta") or {}).get("voruebersetzung") or {}).get("ohne_anker") or {}
    sprachen = {}
    for lg in ziele:
        bf = [dict(x, kapitel=x["id"].split("_")[0], arten=sorted({y.split(":")[0] for y in x.get("befund") or []}))
              for x in pr.get(lg) or []]
        zaehl = {a: sum(1 for x in bf if a in x["arten"]) for a in arten}
        fehlt = [t for t in ids if not ((inh.get(t) or {}).get(lg) or "").strip()]
        pruef = []
        for a in arten:
            if a == "laenge":
                pruef.append({"art": a, "wert": zaehl[a], "anteil": round(zaehl[a] / n, 4), "schwelle": f"≤ {P.AUSREISSER_MAX:.0%}",
                              "ok": zaehl[a] / n <= P.AUSREISSER_MAX})
            elif a == "glossar":
                q = 1 - zaehl[a] / n
                pruef.append({"art": a, "wert": zaehl[a], "anteil": round(q, 4), "schwelle": f"≥ {P.GLOSSAR_MIN:.0%} eingehalten",
                              "ok": q >= P.GLOSSAR_MIN, "ruecksprung": "210"})
            else:
                pruef.append({"art": a, "wert": zaehl[a], "schwelle": "0", "ok": zaehl[a] == 0})
        k = korr.get(lg) or {}
        sprachen[lg] = {"befunde": bf, "pruef": pruef, "abdeckung": round(1 - len(fehlt) / n, 4) if ids else None, "luecken": fehlt[:50],
                        "n_luecken": len(fehlt), "titel": (fass.get(lg) or {}).get("titel"),
                        "titel_pruefen": bool((fass.get(lg) or {}).get("titel_pruefen")),
                        "ohne_anker": len(ohne.get(lg) or []),
                        "manuell": sum(1 for v in k.values() if v.get("text")),
                        "angenommen": sum(1 for v in k.values() if v.get("angenommen"))}
    return {"sprache": src, "ziele": ziele, "vorhanden": bool(inh), "vu_fehlt": not vu, "saetze": len(ids), "kapitel": sorted(kap),
            "zeichen": zeichen, "titel_original": roh.get("titel_original"), "sprachen": sprachen,
            "modell": modell, "standard_modell": standard,
            "modelle": [m for m in getattr(config, "PREISE", {}) if m.startswith("deepseek")],
            "batch": batch, "standard_batch": P.BATCH, "laenge": laenge, "standard_laenge": list(P.LAENGE),
            "anker": roh.get("uebersetzung_anker", True) is not False,
            "kosten_neu": round(P.kosten_schaetzen(zeichen, modell, len(ziele)), 3),
            "kosten_satz": round(P.kosten_schaetzen(zeichen / n, modell) + 0.0005, 4)}


def _m310_argv(book_id, e, wer):
    import re as _re
    from pipeline import s310_uebersetzung as P
    a = [PY, "-m", "pipeline.s310_uebersetzung", book_id, "--wer", wer]
    b = bestellung.lesen(book_id)
    src = b.quellsprache or config.SOURCE_LANGUAGE
    ziele = [z for z in (b.zielsprachen or []) if z != src]
    ID = _re.compile(r"c\d+_\d+_[a-z]+")
    lg = e.get("lang")
    satz = {k: str(v).strip() for k, v in (e.get("satz_text") or {}).items()}
    neu, ann = list(e.get("satz") or []), list(e.get("annehmen") or [])
    if satz or neu or ann:
        if lg not in ziele:
            raise ValueError(f"Zielsprache {lg!r} nicht bestellt {ziele}")
        alle = satz.keys() | set(neu) | set(ann)
        if len(alle) != len(satz) + len(neu) + len(ann):
            raise ValueError("je Satz nur eine Aktion pro Lauf")
        for i in alle:
            if not ID.fullmatch(i):
                raise ValueError(f"Satz-ID {i!r} ungueltig")
        a.append(f"--lang={lg}")
        for i, t in satz.items():
            if not t:
                raise ValueError(f"{i}: Text leer")
            a.append(f"--satz-text={i}={t}")
        a += [f"--satz={i}" for i in neu] + [f"--annehmen={i}" for i in ann]
    if e.get("modell"):
        if e["modell"] not in getattr(config, "PREISE", {}):
            raise ValueError(f"Modell {e['modell']!r} unbekannt")
        a.append(f"--modell={e['modell']}")
    if e.get("batch") not in (None, ""):
        n = int(e["batch"])
        if not 1 <= n <= 100:
            raise ValueError("Batch 1–100 Saetze")
        a.append(f"--batch={n}")
    if e.get("laenge"):
        lo, hi = (float(x) for x in e["laenge"])
        if not 0.1 <= lo < 1 < hi <= 5:
            raise ValueError("Laengengrenze: unten 0,1–1, oben 1–5")
        a.append(f"--laenge={lo}-{hi}")
    if e.get("anker") in ("an", "aus"):
        a.append(f"--anker={e['anker']}")
    if e.get("alle"):
        a.append("--kapitel=alle")
    if e.get("trocken"):
        a.append("--trocken")
    return a


MONITOR_DATEN["310"] = _m310_daten
MONITOR_SPEICHERN["310"] = _m310_argv


# ---- 330 Rueckuebersetzung (Steckbrief GATE_MONITORE 330: nur Befundliste; Regler Schwelle/Flag-Quote/Umfang)
def _m330_daten(book_id):
    from pipeline import s330_rueckuebersetzung as P
    b = bestellung.lesen(book_id)
    roh = b.roh
    src = b.quellsprache or config.SOURCE_LANGUAGE
    ziele = [z for z in (b.zielsprachen or []) if z != src]
    ein = _m200_lesen(book_id, "320_integritaet.json") or {}
    aus = _m200_lesen(book_id, "330_rueckuebersetzung.json") or {}
    meta = aus.get("meta") or {}
    qr = meta.get("quality_report") or {}
    rm = meta.get("rueckuebersetzung") or {}
    pr = _m200_lesen(book_id, "330_pruefung.json") or {}
    korr = P.korrekturen_lesen(book_id)
    schwelle = int(roh.get("rueck_schwelle") or getattr(config, "VALIDATION_THRESHOLD", P.SCHWELLE))
    flag_max = float(roh.get("rueck_flag_max") or getattr(config, "FLAG_MAX_ANTEIL", P.FLAG_MAX))
    flag_ab = int(getattr(config, "FLAG_ANTEIL_AB_SAETZEN", P.FLAG_AB))
    flag_klein = int(getattr(config, "FLAG_MAX_KLEIN", P.FLAG_KLEIN))
    m_rueck = rm.get("modell_rueck") or config.MODELS.get("backtranslator") or config.MODELS.get("translator")
    m_bew = rm.get("modell_bewertung") or config.MODELS.get("validator")
    kap, zeichen, n_saetze = set(), {}, {}
    for lg in ziele:
        k = P.saetze(ein, src, lg) if ein else {}
        kap |= {c for c, l in k.items() if l}
        zeichen[lg] = sum(len(zt) for l in k.values() for _t, _q, zt in l)
        n_saetze[lg] = sum(len(l) for l in k.values())
    sprachen = {}
    for lg in ziele:
        js = (qr.get("je_sprache") or {}).get(lg) or {}
        bf = [dict(x, kapitel=x["id"].split("_")[0]) for x in pr.get(lg) or [] if isinstance(x, dict) and x.get("id")]
        bew = js.get("bewertet") or 0
        nfl = sum(1 for x in bf if x["befund"] == "flag")
        nns = sum(1 for x in bf if x["befund"] == "nicht_bewertbar")
        nb = max(1, bew - nns)
        if bew - nns >= flag_ab:
            fq = {"wert": nfl, "anteil": round(nfl / nb, 4), "schwelle": f"≤ {flag_max:.0%}", "ok": nfl / nb <= flag_max}
        else:
            fq = {"wert": nfl, "anteil": round(nfl / nb, 4), "schwelle": f"≤ {flag_klein} (unter {flag_ab} Sätzen)",
                  "ok": nfl <= flag_klein}
        ans = nns / max(1, bew)
        k = korr.get(lg) or {}
        sprachen[lg] = {"befunde": bf, "flag": fq,
                        "nicht_bewertbar": {"wert": nns, "anteil": round(ans, 4), "schwelle": f"≤ {P.NICHT_BEWERTBAR_MAX:.0%}",
                                            "ok": ans <= P.NICHT_BEWERTBAR_MAX},
                        "schnitt": js.get("durchschnitt"),
                        "schnitt_ok": js.get("durchschnitt") is None or js["durchschnitt"] >= P.SCHNITT_HINWEIS,
                        "bewertet": bew, "ungeprueft": js.get("ungeprueft") or 0,
                        "repariert": sum(1 for x in bf if x["befund"] == "repariert"),
                        "saetze": n_saetze[lg], "zeichen": zeichen[lg],
                        "manuell": sum(1 for v in k.values() if v.get("text")),
                        "angenommen": sum(1 for v in k.values() if v.get("angenommen")),
                        "erledigt": [{"id": t, "text": v.get("text"), "angenommen": bool(v.get("angenommen")),
                                      "wer": v.get("wer"), "wann": v.get("wann")} for t, v in sorted(k.items())]}
    z_alle = sum(zeichen.values())
    je = z_alle / max(1, sum(n_saetze.values()))
    return {"sprache": src, "ziele": ziele, "vorhanden": bool(aus), "ein_fehlt": not ein, "kapitel": sorted(kap),
            "sprachen": sprachen, "schwelle": schwelle, "flag_max": flag_max, "flag_ab": flag_ab, "flag_klein": flag_klein,
            "umfang": roh.get("rueck_umfang") or "alle", "stichprobe": float(roh.get("rueck_stichprobe") or 10),
            "schnitt_soll": P.SCHNITT_HINWEIS,
            "standard": {"schwelle": getattr(config, "VALIDATION_THRESHOLD", P.SCHWELLE),
                         "flag_max": getattr(config, "FLAG_MAX_ANTEIL", P.FLAG_MAX)},
            "modell_rueck": m_rueck, "modell_bewertung": m_bew, "geprueft": qr.get("geprueft"),
            "kosten_neu": round(P.kosten_schaetzen(z_alle, m_rueck, m_bew), 3),
            "kosten_satz": round(P.kosten_schaetzen(je, m_rueck, m_bew, reparatur=0) + P.s310.kosten_schaetzen(je)
                                 + 0.0005, 4)}


def _m330_argv(book_id, e, wer):
    import re as _re
    a = [PY, "-m", "pipeline.s330_rueckuebersetzung", book_id, "--wer", wer]
    b = bestellung.lesen(book_id)
    src = b.quellsprache or config.SOURCE_LANGUAGE
    ziele = [z for z in (b.zielsprachen or []) if z != src]
    ID = _re.compile(r"c\d+_\d+_[a-z]+")
    lg = e.get("lang")
    satz = {k: str(v).strip() for k, v in (e.get("satz_text") or {}).items()}
    neu, ann, kap = list(e.get("satz") or []), list(e.get("annehmen") or []), list(e.get("kapitel") or [])
    if satz or neu or ann or kap:
        if lg not in ziele:
            raise ValueError(f"Zielsprache {lg!r} nicht bestellt {ziele}")
        alle = satz.keys() | set(neu) | set(ann)
        if len(alle) != len(satz) + len(neu) + len(ann):
            raise ValueError("je Satz nur eine Aktion pro Lauf")
        for i in alle:
            if not ID.fullmatch(i):
                raise ValueError(f"Satz-ID {i!r} ungueltig")
        a.append(f"--lang={lg}")
        for i, t in satz.items():
            if not t:
                raise ValueError(f"{i}: Text leer")
            a.append(f"--satz-text={i}={t}")
        a += [f"--satz={i}" for i in neu] + [f"--annehmen={i}" for i in ann]
        for k in kap:
            m = _re.fullmatch(r"c?0*(\d+)", str(k).strip())
            if not m or int(m.group(1)) < 1:
                raise ValueError(f"Kapitel {k!r} ungueltig")
            a.append(f"--kapitel={int(m.group(1))}")
    if e.get("schwelle") not in (None, ""):
        n = int(e["schwelle"])
        if not 50 <= n <= 100:
            raise ValueError("Score-Schwelle 50–100")
        a.append(f"--schwelle={n}")
    if e.get("flag_max") not in (None, ""):
        x = float(e["flag_max"])
        if not 0 < x <= 0.5:
            raise ValueError("Flag-Quote 0–50 %")
        a.append(f"--flag-max={x:g}")
    if e.get("umfang"):
        if e["umfang"] not in ("alle", "ausreisser"):
            raise ValueError("Umfang alle|ausreisser")
        a.append(f"--umfang={e['umfang']}")
    if e.get("stichprobe") not in (None, ""):
        x = float(e["stichprobe"])
        if not 0 <= x <= 100:
            raise ValueError("Stichprobe 0–100 %")
        a.append(f"--stichprobe={x:g}")
    if e.get("alle"):
        a.append("--kapitel=alle")
    if e.get("trocken"):
        a.append("--trocken")
    return a


MONITOR_DATEN["330"] = _m330_daten
MONITOR_SPEICHERN["330"] = _m330_argv


# ---- 340 Wort-Alignment (Steckbrief GATE_MONITORE 340: Befundliste + Wortpaare, Anker per Klick)
def _m340_regler(roh, P):
    w = lambda k, std: roh.get(f"align_{k}") if roh.get(f"align_{k}") is not None else std
    return {"pruefaligner": w("pruefaligner", "an"), "kette": int(w("kette", P.KETTE)),
            "ankerverlust": float(w("ankerverlust", P.ANKERVERLUST)), "inhalt_min": float(w("inhalt_min", P.INHALT_MIN)),
            "unresolved_max": float(w("unresolved_max", P.UNRESOLVED_MAX)),
            "verschoben_max": float(w("verschoben_max", P.VERSCHOBEN_MAX)),
            "doppelt_max": float(w("doppelt_max", P.DOPPELT_MAX))}


def _m340_daten(book_id):
    from pipeline import s340_wortalignment as P
    b = bestellung.lesen(book_id)
    roh = b.roh or {}
    src = b.quellsprache or config.SOURCE_LANGUAGE
    ziele = [lg for lg in (b.zielsprachen or []) if lg != src and b.hat(sprache=lg, kanal="taella")]
    ein = _m200_lesen(book_id, "330_rueckuebersetzung.json") or {}
    aus = _m200_lesen(book_id, "340_wortalignment.json") or {}
    wa = (aus.get("meta") or {}).get("wortalignment") or {}
    pr = _m200_lesen(book_id, "340_pruefung.json") or {}
    korr = P.korrekturen_lesen(book_id)
    r = _m340_regler(roh, P)
    modell = wa.get("modell") or config.MODELS.get("aligner")
    kap, zeichen, woerter, n = set(), 0, 0, 0
    sprachen = {}
    for lg in ziele:
        k = P.saetze(ein, src, lg) if ein else {}
        kap |= {c for c, l in k.items() if l}
        for l in k.values():
            for _t, q, zt in l:
                zeichen, woerter, n = zeichen + len(q) + len(zt), woerter + len(P.tokenize_en(q)), n + 1
        js = (wa.get("je_sprache") or {}).get(lg) or {}
        bf = [{"id": x["id"], "kapitel": x["id"].split("_")[0], "befund": x.get("befund") or [],
               "n": {a: len(x.get(a) or []) for a in ("unresolved", "verschoben", "doppelt", "ohne_anker")},
               "nachlauf": (x.get("nachlauf") or {}).get("ergebnis") if isinstance(x.get("nachlauf"), dict)
               else x.get("nachlauf")} for x in pr.get(lg) or [] if isinstance(x, dict) and x.get("id")]
        pruef = []
        for art, soll, ist_ok in (("inhalt_mit_anker", r["inhalt_min"], lambda v, s: v >= s),
                                  ("unresolved", r["unresolved_max"], lambda v, s: v <= s),
                                  ("verschoben", r["verschoben_max"], lambda v, s: v <= s),
                                  ("doppelt", r["doppelt_max"], lambda v, s: v <= s)):
            v = js.get(art)
            pruef.append({"art": art, "wert": v, "schwelle": ("≥ " if art == "inhalt_mit_anker" else "≤ ") + f"{soll:.0%}",
                          "ok": v is None or ist_ok(v, soll)})
        kk = korr.get(lg) or {}
        sprachen[lg] = {"befunde": bf, "pruef": pruef, "saetze": js.get("saetze"), "woerter": js.get("woerter"),
                        "fehlt": js.get("fehlt") or 0, "ohne_pruefung": js.get("ohne_pruefung") or 0,
                        "manuell": [{"id": t, "n": len(v.get("anker") or {}), "wer": v.get("wer"), "wann": v.get("wann")}
                                    for t, v in sorted(kk.items())]}
    n = max(1, n)
    return {"sprache": src, "ziele": ziele, "vorhanden": bool(aus), "ein_fehlt": not ein, "kapitel": sorted(kap),
            "sprachen": sprachen, "regler": r, "modell": modell, "geprueft": wa.get("geprueft"),
            "standard": {"pruefaligner": "an", "kette": P.KETTE, "ankerverlust": P.ANKERVERLUST,
                         "inhalt_min": P.INHALT_MIN, "unresolved_max": P.UNRESOLVED_MAX,
                         "verschoben_max": P.VERSCHOBEN_MAX, "doppelt_max": P.DOPPELT_MAX},
            "kosten_neu": round(P.kosten_schaetzen(zeichen, woerter, n, modell, r["pruefaligner"] == "an"), 3),
            "kosten_satz": round(P.kosten_schaetzen(zeichen / n, woerter / n, 1, modell, r["pruefaligner"] == "an")
                                 + 0.0003, 4)}


def _m340_teil(book_id, q):
    """?lang=LG&ids=a,b,c -> je Satz Quellwoerter, Zieltokens, Anker (Ziel-Spans), Pruefanker, Ketten, Befunde."""
    from pipeline import s340_wortalignment as P
    b = bestellung.lesen(book_id)
    src = b.quellsprache or config.SOURCE_LANGUAGE
    lg = q.get("lang") or ""
    ids = [x for x in (q.get("ids") or "").split(",") if x][:60]
    aus = _m200_lesen(book_id, "340_wortalignment.json") or {}
    inh = aus.get("content") or {}
    pr = {x["id"]: x for x in (_m200_lesen(book_id, "340_pruefung.json") or {}).get(lg) or []
          if isinstance(x, dict) and x.get("id")}
    out = []
    for t in ids:
        e = inh.get(t) or {}
        qt, zt = (e.get(src) or "").strip(), (e.get(lg) or "").strip()
        al = e.get(f"align_{lg}") or []
        x = pr.get(t) or {}
        sp = P.ziel_spans(al, zt, reparatur=True, lg=lg) if al else []
        ztok = P._ztok(zt)
        woerter = []
        for k, tok in enumerate(P.tokenize_en(qt)):
            w = al[k] if k < len(al) else {}
            spans = [list(s) for s in (sp[k][0] if k < len(sp) else [])]
            woerter.append({"i": tok["i"], "w": tok["word"], "z": sorted(P._tokset(spans, ztok)),
                            "frag": w.get(lg), "source": w.get("source"),
                            "inhalt": P.ist_inhaltswort(tok["word"], src)})
        pa = {i: sorted(P._tokset(s, ztok)) for i, s in (x.get("p") or [])}
        out.append({"id": t, "quelle": qt, "ziel": zt, "ztok": [zt[a:b_] for a, b_ in ztok],
                    "zsp": [[a, b_] for a, b_ in ztok], "woerter": woerter,
                    "p": pa, "ketten": x.get("ketten") or [], "befund": x.get("befund") or [],
                    "unresolved": x.get("unresolved") or [], "verschoben": x.get("verschoben") or [],
                    "doppelt": x.get("doppelt") or [], "ohne_anker": x.get("ohne_anker") or [],
                    "manuell": x.get("manuell") or [], "nachlauf": x.get("nachlauf")})
    return {"saetze": out}


def _m340_argv(book_id, e, wer):
    import re as _re
    a = [PY, "-m", "pipeline.s340_wortalignment", book_id, "--wer", wer]
    b = bestellung.lesen(book_id)
    src = b.quellsprache or config.SOURCE_LANGUAGE
    ziele = [lg for lg in (b.zielsprachen or []) if lg != src and b.hat(sprache=lg, kanal="taella")]
    ID = _re.compile(r"c\d+_\d+_[a-z]+")
    lg = e.get("lang")
    anker = e.get("anker") or {}
    neu, kap = list(e.get("satz") or []), list(e.get("kapitel") or [])
    if anker or neu or kap:
        if lg not in ziele:
            raise ValueError(f"Zielsprache {lg!r} nicht bestellt {ziele}")
        if set(anker) & set(neu):
            raise ValueError("je Satz nur eine Aktion pro Lauf (Anker oder neu alignen)")
        a.append(f"--lang={lg}")
        for t, m in anker.items():
            if not ID.fullmatch(t):
                raise ValueError(f"Satz-ID {t!r} ungueltig")
            for i, f in (m or {}).items():
                if not str(i).isdigit():
                    raise ValueError(f"{t}: Wortindex {i!r} ungueltig")
                f = "-" if f is None else str(f).strip()
                if not f:
                    raise ValueError(f"{t}:{i}: Fragment leer")
                a.append(f"--anker={t}:{int(i)}={f}")
        for t in neu:
            if not ID.fullmatch(t):
                raise ValueError(f"Satz-ID {t!r} ungueltig")
            a.append(f"--satz={t}")
        for k in kap:
            m = _re.fullmatch(r"c?0*(\d+)", str(k).strip())
            if not m or int(m.group(1)) < 1:
                raise ValueError(f"Kapitel {k!r} ungueltig")
            a.append(f"--kapitel={int(m.group(1))}")
    for k, flag, lo, hi in (("inhalt_min", "--inhalt-min", 0.5, 1), ("unresolved_max", "--unresolved-max", 0, 0.5),
                            ("verschoben_max", "--verschoben-max", 0, 0.5), ("doppelt_max", "--doppelt-max", 0, 0.5),
                            ("ankerverlust", "--ankerverlust", 0, 1)):
        if e.get(k) not in (None, ""):
            x = float(e[k])
            if not lo <= x <= hi:
                raise ValueError(f"{k} {lo}–{hi}")
            a.append(f"{flag}={x:g}")
    if e.get("kette") not in (None, ""):
        n = int(e["kette"])
        if not 2 <= n <= 10:
            raise ValueError("Kette 2–10")
        a.append(f"--kette={n}")
    if e.get("pruefaligner") in ("an", "aus"):
        a.append(f"--pruefaligner={e['pruefaligner']}")
    elif e.get("pruefaligner"):
        raise ValueError("Pruefaligner an|aus")
    if e.get("alle"):
        a.append("--kapitel=alle")
    if e.get("trocken"):
        a.append("--trocken")
    return a


MONITOR_DATEN["340"] = _m340_daten
MONITOR_SPEICHERN["340"] = _m340_argv
MONITOR_TEIL["340"] = _m340_teil


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
