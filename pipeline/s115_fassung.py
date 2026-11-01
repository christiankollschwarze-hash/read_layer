"""STAGE 115 — Modernisierungs-Weiche (neu; GATE_KATALOG.md Zeile 115, 01.11.2026)
Funktion:     Legt `fassung: modernisiert | original` in book.json fest (beide Wege: Gutenberg und ePub).
              120 modernisiert nur bei `modernisiert`; 615 setzt daraus den Vermerk "Sanft modernisierte Fassung".
Eingang:      book.json (Mandant 080, Quelle/Rechte 090, Quellsprache).
Default:      Gutenberg/Somnio -> modernisiert; User-ePub -> original; Verlag -> laut Auftrag (sonst original).
Gate:         modernisiert ohne Bearbeitungsrecht (rechte.bearbeitung) -> Stopp, Ruecksprung 090.
              Kein Modernisierungs-Prompt fuer die Quellsprache -> original erzwungen (Hinweis).
              Somnio/Gutenberg -> auto; User + modernisiert (Opt-in) -> Mensch mit Kostenangebot;
              Verlag -> immer Mensch.
Kosten:       0 $ (kein LLM).
Regler:       --modernisieren ja|nein   (Opt-in/-out; braucht 080 `bestellen`)
Aufruf:
  python -m pipeline.s115_fassung <werk> [--modernisieren ja|nein] [--wer CK]
Exit: 0 auto, 2 Stopp, 3 Mensch.
"""
import argparse
import os
import sys

from config import config
from pipeline import bestellung, gate, s080_mandant, s095_produktwahl

STAGE = "115"
MODERN_SPRACHEN = ("en",)          # Sprachen mit Modernisierungs-Prompt in 120
VERMERK = {"modernisiert": "Sanft modernisierte Fassung", "original": None}


def default(b):
    """Default-Fassung aus Quelle/Mandant -> (fassung, herkunft)."""
    if b.mandant_art == "verlag":
        return "original", "default_verlag"
    if (b.roh.get("quelle") or "") == "user_epub" or b.mandant_art == "user":
        return "original", "default_user"
    return "modernisiert", "default_somnio"


def _modernisiert_vorhanden(werk):
    o = bestellung.werkordner(werk)
    return os.path.exists(os.path.join(o, "raw_modernized.txt"))


def run(werk, wer=None, modernisieren=None):
    """Gate 115. modernisieren: True/False (Regler) oder None. Rueckgabe auto | mensch | stopp."""
    wer = s080_mandant.nutzer(wer)
    b = bestellung.lesen(werk)
    g = gate.Gate(werk, STAGE, ruecksprung="115", wer=wer)
    if modernisieren is not None:
        s080_mandant.darf(werk, "bestellen", wer)
        fassung, herkunft = ("modernisiert" if modernisieren else "original"), "regler"
    elif b.fassung and "fassung" not in b.abgeleitet:
        fassung, herkunft = b.fassung, "book.json"
    else:
        fassung, herkunft = default(b)
    g.metrik("herkunft", herkunft)
    g.metrik("mandant", b.mandant)
    g.metrik("quelle", b.roh.get("quelle"))

    erzwungen = fassung == "modernisiert" and b.quellsprache not in MODERN_SPRACHEN
    if erzwungen:
        fassung = "original"
    g.hinweis("prompt_quellsprache", not erzwungen, wert=b.quellsprache,
              text=(f"kein Modernisierungs-Prompt fuer {b.quellsprache} -> fassung original erzwungen" if erzwungen
                    else f"Quellsprache {b.quellsprache}"))
    g.metrik("fassung", fassung)
    g.metrik("vermerk", VERMERK[fassung])

    if fassung == "modernisiert":
        g.pflicht("bearbeitungsrecht", b.rechte.get("bearbeitung") is True, wert=b.rechte.get("bearbeitung"),
                  ruecksprung="090",
                  text=("Bearbeitungsrecht vorhanden" if b.rechte.get("bearbeitung") is True else
                        "modernisiert braucht Bearbeitungsrecht (090 --bearbeitung ja) oder --modernisieren nein"))
    if b.fassung and b.fassung != fassung and "fassung" not in b.abgeleitet:
        g.hinweis("wechsel", False, wert=f"{b.fassung}->{fassung}",
                  text=f"Fassung gewechselt {b.fassung} -> {fassung}"
                       + (": 120 neu laufen lassen (--force)" if _modernisiert_vorhanden(werk) else ""))

    ang = None
    if fassung == "modernisiert":
        z = s095_produktwahl.zeichen(werk)
        if z:
            ang = round(getattr(config, "ANGEBOT_USD_100K", {}).get("modernisierung", 0) * z / 100000, 2)
        g.metrik("zeichen", z)
        g.metrik("angebot_usd", ang)

    mensch, grund = False, None
    if b.mandant_art == "verlag":
        mensch, grund = True, f"Verlag {b.mandant}: Fassung {fassung} laut Auftrag bestaetigen"
    elif b.mandant_art == "user" and fassung == "modernisiert":
        mensch = True
        grund = (f"User-Opt-in Modernisierung: Kostenangebot ~{ang:.2f} $ freigeben" if ang is not None
                 else "User-Opt-in Modernisierung freigeben (Zeichenzahl unbekannt)")

    if not g.fehler() and (b.fassung != fassung or "fassung" in b.abgeleitet):
        bestellung.schreiben(werk, fassung=fassung)
    e = g.entscheide(mensch_immer=mensch, mensch_grund=grund)
    print(g.bericht())
    return e


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 115 Modernisierungs-Weiche")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--modernisieren", choices=("ja", "nein"))
    a = ap.parse_args(argv)
    m = None if a.modernisieren is None else a.modernisieren == "ja"
    return gate.EXIT[run(a.werk, a.wer, m)]


if __name__ == "__main__":
    sys.exit(main())
