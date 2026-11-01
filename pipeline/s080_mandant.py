"""STAGE 080 — Mandant & Rechte (Querschicht, neu; GATE_KATALOG.md, 01.11.2026)
Funktion:     Wer darf was an welchem Werk? Mandant/Besitzer in book.json, Wer/Wann je Gate-Entscheidung
              in status.json. Gate: Rolle berechtigt fuer die Aktion -> auto, sonst Stopp.
Register:     config/rollen.json (nutzer -> rolle admin/kurator/verlag, grenzen; mandanten -> imprint)
Nutzer:       --wer, sonst Umgebung READLAYER_NUTZER, sonst config/rollen.json "standard" (CK)
Rollen:       admin   alles inkl. Override
              kurator eigene Werke (besitzer = Nutzer-ID oder mandant user:<id>), Aktionen laut grenzen
              verlag  eigener Mandant verlag:<id>, Aktionen laut grenzen (spaeter)
Aktionen:     lauf, bestellen, entscheiden, zuruecksetzen, override, mandant
Abnehmer:     run.py (Kette, Nutzer je Lauf), status-CLI (entscheiden/override/zuruecksetzen),
              615/620 (Imprint aus Mandant), 090/095 (Mandant-Defaults)

Aufruf:
  python -m pipeline.s080_mandant <werk>                                pruefen (Gate 080)
  python -m pipeline.s080_mandant <werk> --mandant verlag:xy --besitzer xy --wer CK   setzen (Aktion mandant)
  python -m pipeline.s080_mandant <werk> --darf override --wer anna     nur Rechteauskunft
Exit: 0 auto, 2 Stopp.
"""
import argparse
import json
import os
import sys

from pipeline import bestellung, gate, status

STAGE = "080"
ROLLEN = ("admin", "kurator", "verlag")
AKTIONEN = ("lauf", "bestellen", "entscheiden", "zuruecksetzen", "override", "mandant")
GRENZEN_STANDARD = {"kurator": ["lauf", "bestellen", "entscheiden", "zuruecksetzen"],
                    "verlag": ["lauf", "bestellen", "entscheiden"]}
IMPRINT_STANDARD = "SOMNIO"


def register_pfad():
    return os.environ.get("READLAYER_ROLLEN") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "rollen.json")


def register():
    p = register_pfad()
    if not os.path.exists(p):
        return {"standard": "CK", "nutzer": {"CK": {"rolle": "admin"}}, "mandanten": {}}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def nutzer(wer=None):
    return wer or os.environ.get("READLAYER_NUTZER") or register().get("standard") or "CK"


def rolle(wer, reg=None):
    e = ((reg or register()).get("nutzer") or {}).get(wer) or {}
    r = e.get("rolle")
    return r if r in ROLLEN else None


def _eigenes_werk(wer, e, r, b):
    if r == "kurator":
        uid = e.get("uid") or wer
        return b.besitzer == uid or b.mandant == f"user:{uid}" or b.mandant in e.get("mandanten", [])
    if r == "verlag":
        vid = e.get("verlag") or wer
        return b.mandant == f"verlag:{vid}"
    return False


def pruefen(werk, aktion, wer=None, b=None, reg=None):
    """(ok, grund) – darf <wer> die <aktion> an <werk>?"""
    if aktion not in AKTIONEN:
        return False, f"unbekannte Aktion {aktion!r}"
    reg = reg or register()
    wer = nutzer(wer)
    r = rolle(wer, reg)
    if not r:
        return False, f"Nutzer {wer!r} ohne Rolle (config/rollen.json)"
    if r == "admin":
        return True, f"{wer}: admin"
    if aktion in ("override", "mandant"):
        return False, f"{wer}: {aktion} nur fuer admin"
    e = reg["nutzer"][wer]
    erlaubt = e.get("grenzen") or GRENZEN_STANDARD[r]
    if aktion not in erlaubt:
        return False, f"{wer} ({r}): {aktion} nicht in Grenzen {erlaubt}"
    b = b or bestellung.lesen(werk)
    if not _eigenes_werk(wer, e, r, b):
        return False, f"{wer} ({r}): fremdes Werk (mandant {b.mandant}, besitzer {b.besitzer})"
    return True, f"{wer} ({r}): eigenes Werk"


def darf(werk, aktion, wer=None):
    """Wie pruefen, wirft PermissionError (fuer CLI/Cockpit)."""
    ok, grund = pruefen(werk, aktion, wer)
    if not ok:
        raise PermissionError(f"080: {grund}")
    return rolle(nutzer(wer))


def imprint(werk=None, b=None):
    """Imprint aus dem Mandanten (Befund 615 (10): statt book.json publisher)."""
    b = b or bestellung.lesen(werk)
    m = (register().get("mandanten") or {}).get(b.mandant) or {}
    if m.get("imprint"):
        return m["imprint"]
    return IMPRINT_STANDARD if b.mandant == "somnio" else ""


def run(werk, wer=None, mandant=None, besitzer=None, aktion="lauf"):
    """Gate 080. Setzt Mandant/Besitzer aus der Ableitung in book.json, wenn sie fehlen (bzw. auf Wunsch).
    Rueckgabe: auto | stopp."""
    wer = nutzer(wer)
    b = bestellung.lesen(werk)
    g = gate.Gate(werk, STAGE, ruecksprung=None, wer=wer)
    if mandant or besitzer:
        ok, grund = pruefen(werk, "mandant", wer, b)
    else:
        ok, grund = pruefen(werk, aktion, wer, b)
    g.pflicht("berechtigt", ok, wert=grund, text=grund)
    gueltig = b.mandant == "somnio" or b.mandant.startswith(("user:", "verlag:"))
    if mandant:
        gueltig = mandant == "somnio" or mandant.startswith(("user:", "verlag:"))
    g.pflicht("mandant_gueltig", gueltig, wert=mandant or b.mandant)
    g.metrik("nutzer", wer)
    g.metrik("rolle", rolle(wer) or "-")
    g.metrik("mandant", mandant or b.mandant)
    e = g.entscheide()
    if e == "auto":
        felder = {}
        if mandant:
            felder["mandant"] = mandant
            felder["besitzer"] = besitzer or (mandant.split(":", 1)[1] if ":" in mandant else mandant)
        elif besitzer:
            felder["besitzer"] = besitzer
        else:
            if "mandant" in b.abgeleitet:
                felder["mandant"] = b.mandant
            if not b.roh.get("besitzer"):
                felder["besitzer"] = b.besitzer
        if felder:
            bestellung.schreiben(werk, **felder)
            if mandant or besitzer:
                with status.aendern(werk) as d:
                    status._protokoll(d, wer=wer, aktion="mandant", stage=STAGE, nach=felder)
    print(g.bericht())
    return e


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 080 Mandant & Rechte")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--mandant")
    ap.add_argument("--besitzer")
    ap.add_argument("--darf", metavar="AKTION", help="nur Auskunft, schreibt nichts")
    a = ap.parse_args(argv)
    if a.darf:
        ok, grund = pruefen(a.werk, a.darf, a.wer)
        print(("ja: " if ok else "nein: ") + grund)
        return 0 if ok else 2
    e = run(a.werk, a.wer, a.mandant, a.besitzer)
    return gate.EXIT[e]


if __name__ == "__main__":
    sys.exit(main())
