"""STAGE 095 — Produktwahl (neu; GATE_KATALOG.md Zeile 095 + Produktmodell, 01.11.2026)
Funktion:     Legt die Bestellung `produkte` in book.json fest (Sprache x Inhalt x Stufe x Kanal) und setzt
              die Stage-Liste laeuft/entfaellt in status.json (kette.bedarf_setzen).
Eingang:      Mandant (080), Quelle + wunsch.zielsprachen (090), vorhandene produkte.
Gate:         mind. 1 Produkt; nur gueltige Kombinationen (Matrix) -> sonst Stopp.
              Abhaengigkeit Hoerspiel -> Hoerbuch-Erzaehlerspur gleicher Sprache (Stufe premium) wird ergaenzt.
              Somnio -> auto; User/Verlag -> Mensch (Kostenangebot aus Bestellung); BETA (Sound-Carpet) -> Mensch.
Hoerspiel-Eignung (13.11.2026): Empfehlung aus pipeline/hoerspiel_eignung (Rede-Anteil, Sprecher, Buehnenform,
              0 $); Metrik hoerspiel_eignung. Hoerspiel bestellt, Urteil ungeeignet -> Mensch (bewusst bestaetigen).
Default:      ohne produkte: Text TAELLA in Quellsprache + Zielsprachen (wunsch aus 090, sonst en<->de).
Kosten:       0 $ (kein LLM). Kostenangebot = Selbstkosten-Schaetzung aus config.ANGEBOT_USD_100K
              (Audio-Linie Modal/Fish Drama 3, eine Erzaehlerspur je Sprache; Hoerspiel-Zuschlag nach
              Rede-Anteil und Figurenzahl der Eignung, CK 27.11.2026).
Regler:       --produkt SPRACHE:INHALT[:STUFE]:KANAL[,KANAL][:+ZUSATZ]  (mehrfach; ersetzt die Bestellung)
              --default (Bestellung aus Wunsch neu ableiten)
Aufruf:
  python -m pipeline.s095_produktwahl <werk> [--produkt de:hoerbuch:basic:taella,epub] [--wer CK]
Exit: 0 auto, 2 Stopp, 3 Mensch.
"""
import argparse
import os
import sys

from config import config
from pipeline import bestellung, gate, hoerspiel_eignung, kette, s080_mandant, status
from pipeline.manifest import hash_obj

STAGE = "095"


def produkt_parsen(t):
    """'de:hoerbuch:basic:taella,epub:+sound_carpet' -> Produkt-Dict (Text/Hook ohne Stufe: 'de:text:taella')."""
    teile = [x.strip() for x in t.split(":") if x.strip()]
    zus = [x[1:] for x in teile if x.startswith("+")]
    teile = [x for x in teile if not x.startswith("+")]
    if len(teile) == 3 and teile[1] in bestellung.OHNE_STUFE:
        lg, inh, kan = teile
        st = None
    elif len(teile) == 4:
        lg, inh, st, kan = teile
    else:
        raise ValueError(f"--produkt {t!r}: Form SPRACHE:INHALT[:STUFE]:KANAL[,KANAL][:+ZUSATZ]")
    return bestellung.produkt_norm({"sprache": lg, "inhalt": inh, "stufe": st,
                                    "kanaele": kan.split(","), "zusatz": zus})


def abhaengigkeiten(produkte):
    """Hoerspiel braucht die Hoerbuch-Erzaehlerspur gleicher Sprache (510-Overlay). -> (neu, ergaenzt)."""
    neu = [dict(p) for p in produkte]
    erg = []
    for p in produkte:
        if p["inhalt"] != "hoerspiel":
            continue
        if not any(q["inhalt"] == "hoerbuch" and q["sprache"] == p["sprache"] and q["stufe"] == "premium"
                   for q in neu):
            h = bestellung.produkt_norm({"sprache": p["sprache"], "inhalt": "hoerbuch", "stufe": "premium",
                                         "kanaele": ["taella"]})
            neu.append(h)
            erg.append(f"{p['sprache']}:hoerbuch:premium:taella")
    return neu, erg


def zeichen(werk):
    o = bestellung.werkordner(werk)
    for f in ("raw_modernized.txt", "raw.txt"):
        p = os.path.join(o, f)
        if os.path.exists(p):
            with open(p, encoding="utf-8", errors="ignore") as fh:
                return len(fh.read())
    u = (bestellung.lesen(werk).roh.get("umfang") or {}).get("zeichen")
    return int(u) if u else None


AUDIO = ("hoerbuch", "hoerspiel")


def hoerspiel_basis(eig):
    """(Rede-Anteil, Figurenzahl) aus der Hoerspiel-Eignung; fehlende Werte -> Referenz aus config."""
    w = (eig or {}).get("werte") or {}
    rede = w.get("rede_anteil")
    fig = max(w.get("n_sprecher") or 0, w.get("buehne_rollen") or 0, w.get("figuren_210") or 0)
    return (rede if rede is not None else getattr(config, "ANGEBOT_VC_REDE_REF", 0.26),
            fig or getattr(config, "ANGEBOT_FIGUREN_STANDARD", 8))


def angebot(b, z, eig=None):
    """Selbstkosten-Schaetzung USD je Posten aus Bestellung und Zeichenzahl (None, wenn Zeichen fehlen).
    Audio-Linie Modal (CK 27.11.2026): je Audiosprache EINE Erzaehlerspur (500 Fish + 410 + 520), egal ob
    Hoerbuch, Hoerspiel oder beides; Hoerspiel = Zuschlag 510 VC (nach Rede-Anteil) + 540 + 420/430 + QWEN je Figur."""
    if not z:
        return None
    s = getattr(config, "ANGEBOT_USD_100K", {})
    e = z / 100000
    pos = {"grund": s.get("grund", 0) * e}
    if b.fassung == "modernisiert":
        pos["modernisierung"] = s.get("modernisierung", 0) * e
    for lg in b.zielsprachen:
        pos[f"uebersetzung_{lg}"] = s.get("uebersetzung", 0) * e
        if b.hat(sprache=lg, kanal="taella"):
            pos[f"anker_{lg}"] = s.get("anker", 0) * e
    if eig is None and any(p["inhalt"] == "hoerspiel" for p in b.produkte):
        eig = hoerspiel_eignung.fuer_werk(b.ordner)
    rede, fig = hoerspiel_basis(eig)
    for p in b.produkte:
        lg = p["sprache"]
        if p["inhalt"] not in AUDIO:
            continue
        pos[f"vertonung_{lg}"] = (s.get("vertonung", 0) + s.get("caster", 0) + s.get("pruefung", 0)) * e
        if "taella" in p["kanaele"]:
            pos[f"wortzeiten_{lg}"] = s.get("wortzeiten", 0) * e
        if p["inhalt"] == "hoerspiel":
            vc = s.get("vc", 0) * rede / getattr(config, "ANGEBOT_VC_REDE_REF", 0.26)
            pos[f"hoerspiel_{lg}"] = ((vc + s.get("trennung", 0) + s.get("regie", 0)) * e
                                      + getattr(config, "ANGEBOT_QWEN_USD_FIGUR", 0.02) * fig)
    pos = {k: round(v, 2) for k, v in pos.items()}
    pos["summe"] = round(sum(pos.values()), 2)
    return pos


def bestell_hash(b):
    return hash_obj({"p": b.produkte, "q": b.quellsprache})


def veraltet(werk):
    """Bestellung seit der Freigabe geaendert? (run.py setzt 095 dann zurueck)"""
    st = status.laden(werk)["stages"].get(STAGE) or {}
    h = (st.get("metriken") or {}).get("bestellung_hash")
    return bool(h) and h != bestell_hash(bestellung.lesen(werk))


def run(werk, wer=None, produkte=None, default=False):
    """Gate 095. Rueckgabe auto | mensch | stopp."""
    wer = s080_mandant.nutzer(wer)
    b = bestellung.lesen(werk)
    g = gate.Gate(werk, STAGE, ruecksprung="095", wer=wer)
    if produkte is not None or default:
        s080_mandant.darf(werk, "bestellen", wer)
    if produkte is None:
        if default or "produkte" in b.abgeleitet:
            roh = {k: v for k, v in b.roh.items() if k != "produkte"}
            produkte = bestellung.Bestellung(roh, b.ordner).produkte
            g.metrik("herkunft", "default")
        else:
            produkte = b.produkte
            g.metrik("herkunft", "book.json")
    else:
        g.metrik("herkunft", "regler")
    produkte, erg = abhaengigkeiten(produkte)
    g.hinweis("abhaengigkeiten", not erg, wert=erg,
              text="ergaenzt (Hoerspiel braucht Erzaehlerspur): " + ", ".join(erg))

    probe = bestellung.Bestellung(dict(b.roh, produkte=produkte), b.ordner)
    fehler = probe.fehler()
    g.pflicht("mind_1_produkt", bool(produkte), wert=len(produkte))
    g.pflicht("gueltig", not fehler, wert=len(fehler), text="; ".join(fehler) or "Bestellung gueltig")
    beta = probe.beta()
    g.metrik("produkte", len(produkte))
    g.metrik("beta", len(beta))
    g.metrik("mandant", probe.mandant)
    z = zeichen(werk)
    eig = hoerspiel_eignung.fuer_werk(b.ordner)
    ang = angebot(probe, z, eig)
    g.metrik("zeichen", z)
    g.metrik("angebot_usd", ang)
    if not fehler:
        g.metrik("bestellung_hash", bestell_hash(probe))
    g.metrik("hoerspiel_eignung", {"urteil": eig["urteil"], "stufe": eig["stufe"], "gruende": eig["gruende"]})
    hs = [p for p in probe.produkte if p["inhalt"] == "hoerspiel"]
    gr = []
    if hs and eig["urteil"] == "ungeeignet":
        g.hinweis("hoerspiel_ungeeignet", False, wert=eig["urteil"],
                  text="Hoerspiel bestellt, Empfehlung: ungeeignet (" + "; ".join(eig["gruende"]) +
                       ") – bewusst bestaetigen oder Hoerbuch waehlen")
        gr.append("Hoerspiel trotz Empfehlung 'ungeeignet'")
    if beta:
        gr.append(f"BETA in Bestellung ({len(beta)}× Sound-Carpet, keine Stage)")
    if probe.mandant_art != "somnio":
        gr.append(f"Mandant {probe.mandant}: Bestellung + Kostenangebot freigeben"
                  f" (~{ang['summe']:.2f} $ Selbstkosten)" if ang else
                  f"Mandant {probe.mandant}: Bestellung freigeben (Zeichenzahl unbekannt, kein Angebot)")
    mensch, grund = bool(gr), (" · ".join(gr) + " – Mensch") if gr else None
    if not fehler and (probe.produkte != b.produkte or "produkte" in b.abgeleitet):
        bestellung.schreiben(werk, produkte=probe.produkte)
    e = g.entscheide(mensch_immer=mensch, mensch_grund=grund)
    if e != "stopp":
        kette.bedarf_setzen(werk, wer=wer)
    print(g.bericht())
    if ang:
        print("[095] Kostenangebot (Selbstkosten): " + ", ".join(f"{k} {v:.2f} $" for k, v in ang.items()))
    return e


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 095 Produktwahl")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--produkt", action="append",
                    help="SPRACHE:INHALT[:STUFE]:KANAL[,KANAL][:+ZUSATZ], mehrfach; ersetzt die Bestellung")
    ap.add_argument("--default", action="store_true", help="Bestellung aus Wunsch (090) neu ableiten")
    a = ap.parse_args(argv)
    prod = [produkt_parsen(t) for t in a.produkt] if a.produkt else None
    return gate.EXIT[run(a.werk, a.wer, prod, a.default)]


if __name__ == "__main__":
    sys.exit(main())
