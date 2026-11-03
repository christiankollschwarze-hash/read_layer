"""Phase 2, Fundament 1: Statusdatei je Werk -> books/<werk>/work/status.json.

Kommandozeile und Cockpit lesen und schreiben dieselbe Datei. Schreiben nur ueber
diese Funktionen: Sperrdatei (status.json.lock) + atomares Ersetzen (tmp -> os.replace).

Zustaende je Stage (Katalog GATE_KATALOG.md):
  offen      gebraucht, noch nicht gelaufen
  laeuft     Stage arbeitet gerade
  entfaellt  laut Bestellung (095) nicht gebraucht -> zaehlt fuer Nachfolger als frei
  frei       Gate bestanden (auto, Mensch-Freigabe oder Admin-Override)
  mensch     Gate wartet auf menschliche Entscheidung
  stopp      harter Halt
Gate-Ergebnis: auto | mensch | stopp (Rohentscheidung des Gates, vor Mensch/Override).
Teilbereiche (Kapitel x Sprache, Sprache x Variante ...) unter stages[NNN]["teile"][<scope>].

CLI:
  python -m pipeline.status <werk>                         Uebersicht
  python -m pipeline.status <werk> --stage 310             Stage-Eintrag als JSON
  python -m pipeline.status <werk> --entscheiden 310 frei --wer CK --grund "..."
  python -m pipeline.status <werk> --override 320 --wer CK --rolle admin --grund "..."
  python -m pipeline.status <werk> --zuruecksetzen 310 --wer CK --grund "..."
"""
import argparse
import contextlib
import json
import os
import sys
import time
from datetime import datetime, timezone

SCHEMA = 1

# Katalog-Reihenfolge (GATE_KATALOG.md, 01.11.2026). 345 ist Teil von 340, 502 Teil von 500,
# 525 Teil von 520; 900/910 ausserhalb der Pipeline.
STAGES = ["080", "090", "095", "100", "110", "150", "115", "120", "190", "195", "200",
          "210", "300", "310", "320", "330", "340", "400", "410", "420", "500", "510",
          "530", "520", "540", "600", "610", "615", "620", "630", "640", "650", "700", "710"]

ZUSTAENDE = ("offen", "laeuft", "entfaellt", "frei", "mensch", "stopp")
GATE_ERGEBNISSE = ("auto", "mensch", "stopp")
FREI = ("frei", "entfaellt")

LOCK_TIMEOUT_S = 30
LOCK_STALE_S = 120


def jetzt():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def pfad(book_id):
    from config import config
    return os.path.join(config.work_dir(book_id), "status.json")


def _leer(book_id):
    return {"schema": SCHEMA, "book_id": book_id, "angelegt": jetzt(), "aktualisiert": None,
            "stages": {}, "protokoll": []}


def _stage_leer():
    return {"zustand": "offen", "gate": None, "metriken": {}, "hinweise": [],
            "versuche": 0, "teile": {}, "wer": None, "wann": None}


def _norm(stage):
    s = str(stage).strip()
    if s.isdigit():
        s = s.zfill(3)
    if s not in STAGES:
        raise ValueError(f"Unbekannte Stage {stage!r} (erlaubt: {', '.join(STAGES)})")
    return s


# ---------------------------------------------------------------- Lesen/Schreiben
def laden(book_id):
    """Status lesen. Fehlt die Datei -> leeres Schema (nicht gespeichert).
    Kaputte Datei -> Fehler (nie still ueberschreiben)."""
    p = pfad(book_id)
    if not os.path.exists(p):
        return _leer(book_id)
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    if d.get("schema") != SCHEMA:
        raise RuntimeError(f"{p}: Schema {d.get('schema')} != {SCHEMA}")
    return d


def _schreiben(book_id, d):
    p = pfad(book_id)
    d["aktualisiert"] = jetzt()
    tmp = f"{p}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    for i in range(20):                       # Windows: Ziel kann kurz von Leser offen sein
        try:
            os.replace(tmp, p)
            return
        except PermissionError:
            time.sleep(0.05 * (i + 1))
    os.replace(tmp, p)


@contextlib.contextmanager
def _sperre(book_id):
    lock = pfad(book_id) + ".lock"
    t0 = time.time()
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {jetzt()}".encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lock) > LOCK_STALE_S:
                    os.remove(lock)               # verwaiste Sperre (abgestuerzter Prozess)
                    continue
            except FileNotFoundError:
                continue
            if time.time() - t0 > LOCK_TIMEOUT_S:
                raise TimeoutError(f"status.json gesperrt: {lock}")
            time.sleep(0.1)
    try:
        yield
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.remove(lock)


@contextlib.contextmanager
def aendern(book_id):
    """with aendern(werk) as d: ...  -> sperren, lesen, aendern, atomar schreiben."""
    with _sperre(book_id):
        d = laden(book_id)
        yield d
        _schreiben(book_id, d)


def _st(d, stage):
    return d["stages"].setdefault(stage, _stage_leer())


def _ziel(d, stage, scope):
    st = _st(d, stage)
    if scope is None:
        return st
    t = st["teile"].setdefault(str(scope), _stage_leer())
    t.pop("teile", None)
    return t


def _protokoll(d, **eintrag):
    d["protokoll"].append({"wann": jetzt(), **eintrag})


# ---------------------------------------------------------------- Stage-API
def bedarf_setzen(book_id, laeuft, wer="095"):
    """Aus 095: laeuft = Menge der gebrauchten Stages. Alle anderen -> entfaellt.
    Gebrauchte, die auf entfaellt standen, gehen auf offen; andere bleiben."""
    laeuft = {_norm(s) for s in laeuft}
    with aendern(book_id) as d:
        for s in STAGES:
            st = _st(d, s)
            if s not in laeuft:
                st["zustand"] = "entfaellt"
            elif st["zustand"] == "entfaellt":
                st["zustand"] = "offen"
            st["wer"], st["wann"] = wer, jetzt()
        _protokoll(d, wer=wer, aktion="bedarf", stages=sorted(laeuft))


def entfaellt(book_id, stage, grund, wer="pipeline", scope=None):
    """Stage (bzw. Teil) stellt selbst fest, dass sie nicht gebraucht wird (z. B. 610 bei Cover aus 150,
    700 Produkt zurueckgehalten)."""
    stage = _norm(stage)
    with aendern(book_id) as d:
        st = _ziel(d, stage, scope)
        st.update(zustand="entfaellt", hinweise=[grund], wer=wer, wann=jetzt())
        if scope is not None:
            _gesamt_aus_teilen(_st(d, stage))
        _protokoll(d, wer=wer, aktion="entfaellt", stage=stage, scope=scope, grund=grund)


def start(book_id, stage, wer="pipeline", scope=None):
    stage = _norm(stage)
    with aendern(book_id) as d:
        z = _ziel(d, stage, scope)
        z.update(zustand="laeuft", wer=wer, wann=jetzt())
        if scope is None:                  # neuer Lauf: Befunde/Hinweise des Vorlaufs gelten nicht mehr
            _signatur_sichern(z)
            z.update(gate=None, hinweise=[])
        else:
            _st(d, stage)["zustand"] = "laeuft"


def ergebnis(book_id, stage, gate, metriken=None, gruende=None, ruecksprung=None,
             hinweise=None, wer="pipeline", scope=None):
    """Gate-Ergebnis schreiben. gate: auto -> frei, mensch -> mensch, stopp -> stopp.
    Ohne Gate (Stage ohne Pruefung) gate='auto' uebergeben."""
    stage = _norm(stage)
    if gate not in GATE_ERGEBNISSE:
        raise ValueError(f"Gate-Ergebnis {gate!r} ungueltig")
    zustand = {"auto": "frei", "mensch": "mensch", "stopp": "stopp"}[gate]
    with aendern(book_id) as d:
        z = _ziel(d, stage, scope)
        _signatur_sichern(z)
        z.update(zustand=zustand, metriken=metriken or {}, hinweise=list(hinweise or []),
                 gate={"ergebnis": gate, "gruende": list(gruende or []),
                       "ruecksprung": ruecksprung, "wann": jetzt()},
                 wer=wer, wann=jetzt())
        sig = _signatur(gate, gruende, hinweise, metriken)
        if z.get("signatur") != sig:       # Ergebnis geaendert -> Folgestages sind veraltet (Frische)
            z.update(signatur=sig, stand=jetzt())
        if scope is not None:
            _gesamt_aus_teilen(_st(d, stage))
    return zustand


# Metriken, die sich bei jedem Lauf aendern, zaehlen nicht als Ergebnisaenderung.
FLUECHTIG = ("dauer", "sek", "wann", "zeitpunkt", "laufzeit")


def _signatur(gate, gruende, hinweise, metriken):
    import hashlib
    m = metriken or {}
    if isinstance(m, dict):
        m = {k: v for k, v in m.items() if not any(f in str(k).lower() for f in FLUECHTIG)}
    roh = json.dumps([gate, list(gruende or []), list(hinweise or []), m], sort_keys=True,
                     ensure_ascii=False, default=str)
    return hashlib.sha1(roh.encode("utf-8")).hexdigest()[:16]


def _zeit(t):
    try:
        return datetime.fromisoformat(t) if t else None
    except (TypeError, ValueError):
        return None


def _zeiten(st, feld):
    """Zeitpunkte von Stage + Teilen: feld 'stand' (letzte Ergebnisaenderung, Rueckfall Gate-Zeit)
    oder 'lauf' (letztes Gate-Ergebnis)."""
    out = []
    for t in [st] + list((st.get("teile") or {}).values()):
        g = (t.get("gate") or {}).get("wann")
        z = _zeit(t.get("stand") or g) if feld == "stand" else _zeit(g)
        if z:
            out.append(z)
    return out


def _signatur_sichern(z):
    """Altbestand ohne 'signatur': Signatur und Stand aus dem vorhandenen Gate nachtragen, bevor es
    ueberschrieben/geloescht wird – sonst gaelte der erste Neulauf als Ergebnisaenderung (Kaskade)."""
    g = z.get("gate")
    if "signatur" in z or not g:
        return
    z["signatur"] = _signatur(g.get("ergebnis"), g.get("gruende"), z.get("hinweise"), z.get("metriken"))
    z["stand"] = z.get("stand") or g.get("wann")


def stand(book_id, stage, d=None):
    """Zeit der letzten Ergebnisaenderung (Stage oder ein Teil) – Bezug fuer Nachfolger. None = nie."""
    st = (d or laden(book_id))["stages"].get(_norm(stage)) or {}
    z = _zeiten(st, "stand")
    return max(z) if z else None


def gelaufen(book_id, stage, d=None):
    """Zeit des letzten Gate-Ergebnisses (Stage oder ein Teil). None = nie."""
    st = (d or laden(book_id))["stages"].get(_norm(stage)) or {}
    z = _zeiten(st, "lauf")
    return max(z) if z else None


def _gesamt_aus_teilen(st):
    """Stage-Zustand aus Teilen: stopp > mensch > laeuft > offen > frei."""
    zs = [t["zustand"] for t in st["teile"].values()]
    for z in ("stopp", "mensch", "laeuft", "offen"):
        if z in zs:
            st["zustand"] = z
            return
    if zs:
        st["zustand"] = "frei"


def versuch(book_id, stage, scope=None):
    """Reparaturzaehler +1, gibt neuen Stand zurueck."""
    stage = _norm(stage)
    with aendern(book_id) as d:
        z = _ziel(d, stage, scope)
        z["versuche"] = z.get("versuche", 0) + 1
        return z["versuche"]


def entscheiden(book_id, stage, nach, wer, grund, scope=None, rolle="kurator"):
    """Mensch-Entscheidung an einem Gate im Zustand 'mensch': nach = frei | stopp | offen (neu)."""
    stage = _norm(stage)
    if nach not in ("frei", "stopp", "offen"):
        raise ValueError("nach muss frei/stopp/offen sein")
    if not wer or not grund:
        raise ValueError("wer und grund sind Pflicht")
    with aendern(book_id) as d:
        z = _ziel(d, stage, scope)
        if z["zustand"] != "mensch":
            raise RuntimeError(f"Stage {stage}{'/' + str(scope) if scope else ''} steht auf "
                               f"{z['zustand']}, nicht auf mensch (Admin: override)")
        von = z["zustand"]
        z.update(zustand=nach, wer=wer, wann=jetzt())
        if scope is not None:
            _gesamt_aus_teilen(_st(d, stage))
        _protokoll(d, wer=wer, rolle=rolle, aktion="entscheidung", stage=stage, scope=scope,
                   von=von, nach=nach, grund=grund)


def override(book_id, stage, wer, rolle, grund, nach="frei", scope=None):
    """Admin-Override mit Protokoll (ersetzt READLAYER_WEITER u. a.). Nur Rolle admin."""
    stage = _norm(stage)
    if rolle != "admin":
        raise PermissionError("Override nur fuer Rolle admin")
    if not wer or not grund:
        raise ValueError("wer und grund sind Pflicht")
    if nach not in ZUSTAENDE:
        raise ValueError(f"Zustand {nach!r} ungueltig")
    with aendern(book_id) as d:
        z = _ziel(d, stage, scope)
        von = z["zustand"]
        z.update(zustand=nach, wer=wer, wann=jetzt(),
                 override={"wer": wer, "grund": grund, "von": von, "wann": jetzt()})
        if scope is not None:
            _gesamt_aus_teilen(_st(d, stage))
        _protokoll(d, wer=wer, rolle=rolle, aktion="override", stage=stage, scope=scope,
                   von=von, nach=nach, grund=grund)


def zuruecksetzen(book_id, stage, wer, grund, scope=None):
    """Stage (bzw. Teil) auf offen, Versuche 0 (z. B. Ruecksprung, Neu-Lauf)."""
    stage = _norm(stage)
    with aendern(book_id) as d:
        z = _ziel(d, stage, scope)
        von = z["zustand"]
        _signatur_sichern(z)
        z.update(zustand="offen", versuche=0, gate=None, wer=wer, wann=jetzt())
        if scope is not None:
            _gesamt_aus_teilen(_st(d, stage))
        _protokoll(d, wer=wer, aktion="zuruecksetzen", stage=stage, scope=scope,
                   von=von, nach="offen", grund=grund)


# ---------------------------------------------------------------- Abfragen
def zustand(book_id, stage, scope=None, d=None):
    d = d or laden(book_id)
    st = d["stages"].get(_norm(stage))
    if not st:
        return "offen"
    if scope is not None:
        return st["teile"].get(str(scope), {}).get("zustand", "offen")
    return st["zustand"]


def ist_frei(book_id, stage, scope=None, d=None):
    return zustand(book_id, stage, scope, d) in FREI


def _befund_zeile(st):
    """Befunde nur fuer offene Entscheidungen/Halts (mensch, stopp) – bei frei/entfaellt keine alten
    Fehlertexte. Stage-Gate leer -> Befunde der nicht freien Teile als '<scope>: <grund>'."""
    if st.get("zustand") not in ("mensch", "stopp"):
        return ""
    g = st.get("gate") or {}
    gr, rs = list(g.get("gruende") or []), [g["ruecksprung"]] if g.get("ruecksprung") else []
    if not gr:
        for sc, t in sorted((st.get("teile") or {}).items()):
            if t.get("zustand") in ("mensch", "stopp"):
                tg = t.get("gate") or {}
                gr += [f"{sc}: {x}" for x in (tg.get("gruende") or [t["zustand"]])]
                if tg.get("ruecksprung") and tg["ruecksprung"] not in rs:
                    rs.append(tg["ruecksprung"])
    info = (" | " + "; ".join(gr)[:100]) if gr else ""
    return info + (f" -> {','.join(rs)}" if rs else "")


def uebersicht(book_id):
    d = laden(book_id)
    zeilen = [f"Werk {book_id}  (aktualisiert {d.get('aktualisiert')})"]
    for s in STAGES:
        st = d["stages"].get(s)
        if not st:
            continue
        info = _befund_zeile(st)
        teile = f" [{len(st['teile'])} Teile]" if st.get("teile") else ""
        zeilen.append(f"  {s}  {st['zustand']:<9} v{st.get('versuche', 0)}{teile}{info}")
    return "\n".join(zeilen)


def main(argv=None):
    ap = argparse.ArgumentParser(description="status.json je Werk lesen/aendern")
    ap.add_argument("werk")
    ap.add_argument("--stage")
    ap.add_argument("--scope")
    ap.add_argument("--entscheiden", nargs=2, metavar=("STAGE", "NACH"))
    ap.add_argument("--override", metavar="STAGE")
    ap.add_argument("--nach", default="frei")
    ap.add_argument("--zuruecksetzen", metavar="STAGE")
    ap.add_argument("--wer")
    ap.add_argument("--rolle", help="veraltet: Rolle kommt aus config/rollen.json (Stage 080)")
    ap.add_argument("--grund")
    a = ap.parse_args(argv)
    try:
        if a.entscheiden or a.override or a.zuruecksetzen:     # Stage 080: Rolle aus config/rollen.json
            from pipeline import s080_mandant as m
            a.wer = m.nutzer(a.wer)
            aktion = "entscheiden" if a.entscheiden else ("override" if a.override else "zuruecksetzen")
            a.rolle = m.darf(a.werk, aktion, a.wer)
        if a.entscheiden:
            entscheiden(a.werk, a.entscheiden[0], a.entscheiden[1], a.wer, a.grund, a.scope, a.rolle)
        elif a.override:
            override(a.werk, a.override, a.wer, a.rolle, a.grund, a.nach, a.scope)
        elif a.zuruecksetzen:
            zuruecksetzen(a.werk, a.zuruecksetzen, a.wer, a.grund, a.scope)
        elif a.stage:
            st = laden(a.werk)["stages"].get(_norm(a.stage))
            print(json.dumps(st, ensure_ascii=False, indent=1))
            return 0
        print(uebersicht(a.werk))
        return 0
    except (ValueError, PermissionError, RuntimeError, TimeoutError) as e:
        print(f"FEHLER: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
