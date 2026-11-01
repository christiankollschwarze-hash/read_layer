"""Phase 2, Fundament 2: gemeinsamer Gate-Baustein fuer alle Stages.

Ablauf in einer Stage:
    from pipeline import gate
    gate.vorgaenger_frei(werk, "310", ["300"])          # sonst Stopp in 310, GateHalt
    g = gate.Gate(werk, "310", scope="c001/de", reparatur_max=1, ruecksprung="310")
    g.pflicht("abdeckung", fehlende == 0, wert=fehlende, bei_fehler="reparatur_stopp", ruecksprung="310")
    g.bereich("laenge", ratio, 0.5, 2.0, bei_fehler="reparatur")
    g.min("glossar", treffer, 0.98, bei_fehler="reparatur", ruecksprung="210")
    g.hinweis("ueberlang", n_lang == 0, wert=n_lang)
    g.metrik("saetze", n)
    e = g.entscheide(mensch_immer=(mandant == "verlag"))
    if e == "reparatur":  ... einmal reparieren, neues Gate, erneut entscheiden
    gate.beenden([e, ...])                               # Exit-Code fuer CLI

bei_fehler (Katalog-Entscheidung je Metrik):
    stopp            sofort Stopp
    mensch           sofort Mensch
    reparatur        bis reparatur_max automatisch neu, dann Mensch
    reparatur_stopp  bis reparatur_max automatisch neu, dann Stopp
    hinweis          nur Anzeige, entscheidet nichts
Reparaturzaehler in status.json (versuche je Stage/Teil). Text 1x, Audio 2x (reparatur_max).
Ergebnis 'reparatur' schreibt kein Gate-Ergebnis (Stage bleibt 'laeuft'), nur den Versuch.

Umgehungsvariablen (READLAYER_WEITER, READLAYER_57B_ALLE ...) sind abgeschafft:
Freigabe eines Stopps nur per Admin-Override mit Protokoll (python -m pipeline.status ... --override).
"""
import os
import sys

from pipeline import mock, status

EXIT = {"auto": 0, "stopp": 2, "mensch": 3, "reparatur": 4}
SCHWERE = ("stopp", "mensch", "reparatur", "reparatur_stopp", "hinweis")
ALT_UMGEHUNG = ("READLAYER_WEITER", "READLAYER_57B_ALLE")


class GateHalt(Exception):
    """Stage darf nicht weiterlaufen (Stopp oder Mensch). .ergebnis, .gruende"""
    def __init__(self, stage, ergebnis, gruende):
        self.stage, self.ergebnis, self.gruende = stage, ergebnis, list(gruende)
        super().__init__(f"Stage {stage}: {ergebnis.upper()} – " + "; ".join(self.gruende))

    @property
    def exit_code(self):
        return EXIT.get(self.ergebnis, 1)


def _fmt(v):
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


class Gate:
    def __init__(self, book_id, stage, scope=None, reparatur_max=1, ruecksprung=None, wer="pipeline"):
        self.book_id, self.stage, self.scope = book_id, status._norm(stage), scope
        self.reparatur_max, self.ruecksprung, self.wer = reparatur_max, ruecksprung, wer
        self.pruefungen = []     # dicts: name, ok, wert, schwelle, bei_fehler, ruecksprung, text
        self.metriken = {"modus": mock.modus()}
        self.ergebnis = None
        for v in ALT_UMGEHUNG:
            if os.environ.get(v):
                print(f"[gate {self.stage}] {v} ist abgeschafft und wirkungslos – Admin-Override nutzen.",
                      file=sys.stderr)

    # ---------------------------------------------------------- Pruefungen
    def pruefe(self, name, ok, wert=None, schwelle=None, bei_fehler="stopp", ruecksprung=None, text=None):
        if bei_fehler not in SCHWERE:
            raise ValueError(f"bei_fehler {bei_fehler!r} ungueltig")
        ok = bool(ok)
        if text is None:
            text = name + (f" = {_fmt(wert)}" if wert is not None else "") + \
                (f" (Soll {schwelle})" if schwelle is not None else "")
        self.pruefungen.append(dict(name=name, ok=ok, wert=wert, schwelle=schwelle,
                                    bei_fehler=bei_fehler, ruecksprung=ruecksprung, text=text))
        if wert is not None:
            self.metriken[name] = wert
        return ok

    def pflicht(self, name, ok, wert=None, bei_fehler="stopp", ruecksprung=None, text=None):
        return self.pruefe(name, ok, wert, "Pflicht", bei_fehler, ruecksprung, text)

    def min(self, name, wert, grenze, bei_fehler="mensch", ruecksprung=None):
        return self.pruefe(name, wert is not None and wert >= grenze, wert, f">= {grenze}", bei_fehler, ruecksprung)

    def max(self, name, wert, grenze, bei_fehler="mensch", ruecksprung=None):
        return self.pruefe(name, wert is not None and wert <= grenze, wert, f"<= {grenze}", bei_fehler, ruecksprung)

    def bereich(self, name, wert, lo, hi, bei_fehler="mensch", ruecksprung=None):
        return self.pruefe(name, wert is not None and lo <= wert <= hi, wert, f"{lo}–{hi}", bei_fehler, ruecksprung)

    def gleich(self, name, wert, soll, bei_fehler="stopp", ruecksprung=None):
        return self.pruefe(name, wert == soll, wert, f"= {soll}", bei_fehler, ruecksprung)

    def hinweis(self, name, ok, wert=None, text=None):
        return self.pruefe(name, ok, wert, None, "hinweis", None, text)

    def metrik(self, name, wert):
        self.metriken[name] = wert

    def mock(self, anzahl, beispiele=None, ruecksprung=None):
        """Mock-Artefakte im Eingang/Ausgang: im Live-Lauf Stopp, im Mock-Lauf nur Hinweis."""
        txt = f"mock = {anzahl}" + (f" ({', '.join(beispiele)})" if beispiele and anzahl else "")
        if mock.aktiv():
            return self.hinweis("mock", anzahl == 0, anzahl, text=txt + " [Mock-Lauf]")
        return self.pruefe("mock", anzahl == 0, anzahl, "= 0 im Live-Lauf", "stopp",
                           ruecksprung or self.ruecksprung, txt + " im Live-Lauf")

    # ---------------------------------------------------------- Entscheidung
    def fehler(self):
        return [p for p in self.pruefungen if not p["ok"] and p["bei_fehler"] != "hinweis"]

    def entscheide(self, mensch_immer=False, mensch_grund=None, schreiben=True):
        """-> 'auto' | 'mensch' | 'stopp' | 'reparatur'. Schreibt status.json (ausser bei 'reparatur')."""
        fe = self.fehler()
        versuche = self._versuche()
        rep_offen = versuche < self.reparatur_max
        stopp = [p for p in fe if p["bei_fehler"] == "stopp"
                 or (p["bei_fehler"] == "reparatur_stopp" and not rep_offen)]
        rep = [p for p in fe if p["bei_fehler"] in ("reparatur", "reparatur_stopp") and rep_offen]
        mensch = [p for p in fe if p["bei_fehler"] == "mensch"
                  or (p["bei_fehler"] == "reparatur" and not rep_offen)]
        if stopp:
            e, massgeblich = "stopp", stopp
        elif rep:
            e, massgeblich = "reparatur", rep
        elif mensch or mensch_immer:
            e, massgeblich = "mensch", mensch
        else:
            e, massgeblich = "auto", []
        gruende = [p["text"] for p in massgeblich]
        if e == "mensch" and mensch_immer and not mensch:
            gruende.append(mensch_grund or "Entscheidung immer durch Mensch (Katalog)")
        hinweise = [p["text"] for p in self.pruefungen if not p["ok"] and p["bei_fehler"] == "hinweis"]
        ruecksprung = next((p["ruecksprung"] for p in massgeblich if p["ruecksprung"]), self.ruecksprung)
        self.ergebnis = dict(ergebnis=e, gruende=gruende, hinweise=hinweise,
                             ruecksprung=None if e == "auto" else ruecksprung, versuche=versuche)
        if schreiben:
            if e == "reparatur":
                self.ergebnis["versuche"] = status.versuch(self.book_id, self.stage, self.scope)
            else:
                status.ergebnis(self.book_id, self.stage, e, metriken=self.metriken, gruende=gruende,
                                ruecksprung=self.ergebnis["ruecksprung"], hinweise=hinweise,
                                wer=self.wer, scope=self.scope)
        return e

    def _versuche(self):
        d = status.laden(self.book_id)
        st = d["stages"].get(self.stage) or {}
        if self.scope is not None:
            st = (st.get("teile") or {}).get(str(self.scope)) or {}
        return st.get("versuche", 0)

    def halt(self):
        """Nach entscheide(): GateHalt bei stopp/mensch."""
        if self.ergebnis and self.ergebnis["ergebnis"] in ("stopp", "mensch"):
            raise GateHalt(self.stage, self.ergebnis["ergebnis"], self.ergebnis["gruende"])

    def bericht(self):
        z = [f"Gate {self.stage}{' ' + str(self.scope) if self.scope else ''}: "
             f"{(self.ergebnis or {}).get('ergebnis', '?').upper()}"]
        for p in self.pruefungen:
            z.append(f"  {'ok ' if p['ok'] else 'X  '} [{p['bei_fehler']}] {p['text']}")
        if self.ergebnis and self.ergebnis.get("ruecksprung"):
            z.append(f"  Ruecksprung -> {self.ergebnis['ruecksprung']}")
        return "\n".join(z)


# ---------------------------------------------------------- Kette
def vorgaenger_frei(book_id, stage, vorgaenger, wer="pipeline"):
    """Stage startet nur bei freiem Vorgaenger-Gate (frei oder entfaellt). Sonst Stopp in dieser
    Stage mit Ruecksprung auf den ersten nicht freien Vorgaenger und GateHalt."""
    d = status.laden(book_id)
    offen = [(status._norm(v), status.zustand(book_id, v, d=d)) for v in vorgaenger]
    offen = [(v, z) for v, z in offen if z not in status.FREI]
    gruende = [f"Gate {v} nicht frei ({z})" for v, z in offen]
    if not mock.aktiv():     # Fundament 5: Mock-Ergebnis eines Vorgaengers darf nicht in den Live-Lauf
        for v in vorgaenger:
            v = status._norm(v)
            st = d["stages"].get(v) or {}
            teile = [st] + list((st.get("teile") or {}).values())
            if any((t.get("metriken") or {}).get("modus") == "mock" for t in teile):
                offen.append((v, "mock"))
                gruende.append(f"Gate {v} im Mock-Lauf erzeugt – im Live-Lauf neu ausfuehren")
    if not offen:
        status.start(book_id, stage, wer=wer)
        return True
    status.ergebnis(book_id, stage, "stopp", gruende=gruende, ruecksprung=offen[0][0], wer=wer)
    raise GateHalt(status._norm(stage), "stopp", gruende)


def gesamt(ergebnisse):
    """Schlechtestes Ergebnis mehrerer Gates (z. B. je Kapitel x Sprache)."""
    for e in ("stopp", "mensch", "reparatur"):
        if e in ergebnisse:
            return e
    return "auto"


def beenden(ergebnisse):
    """Exit-Code fuer CLI: 0 auto, 2 stopp, 3 mensch, 4 reparatur offen."""
    if isinstance(ergebnisse, str):
        ergebnisse = [ergebnisse]
    sys.exit(EXIT[gesamt(list(ergebnisse))])
