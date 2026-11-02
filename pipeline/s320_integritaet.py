"""STAGE 320 — Integritaet (Umbau Phase 2, GATE_KATALOG.md Zeile 320, 02.11.2026)
Funktion:      Mechanischer Strukturvertrag vor 330 ff. Keine API, keine Kosten.
Wirkungsweise: Gleicht 310 gegen 200 ab (ID-Menge, Quelltext je Knoten), prueft ID-Form,
               lueckenlose Sequenz je Kapitel, jede bestellte Zielsprache vorhanden und nicht leer,
               keine unbestellte Sprache, Gates 300/310 frei. Alles gruen -> auto, sonst Stopp in 320
               selbst (Ruecksprung 310 bei Uebersetzungsluecken, 200 bei Struktur/Quelltext).
               Keine Regler; Abweichung nur per Admin-Override (pipeline.status --override).
               READLAYER_WEITER ist abgeschafft.
Komponenten:   pipeline/s320_integritaet.py
Zulieferer:    s310 Uebersetzung (work/310_uebersetzung.json), s200 Tagging (work/200_tagging.json, Referenz),
               book.json (bestellte Zielsprachen)
Abnehmer:      s330 Rueckuebersetzung (work/320_integritaet.json = Durchreichung + meta.integrity_report)
Aufruf:        python -m pipeline.s320_integritaet <werk> [--trocken]
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import bestellung, gate, manifest, status

STAGE = "320"
SPRACH_SCHLUESSEL = re.compile(r"^[a-z]{2}(-[a-z]{2})?$")


def id_muster():
    cd, sd = config.CHAPTER_DIGITS, config.SEQUENCE_DIGITS
    return re.compile(rf"^c\d{{{cd}}}_\d{{{sd}}}_[a-z]{{1,4}}$")


def _kurz(liste, n=6):
    return f"{liste[:n]}" + (f" (+{len(liste) - n})" if len(liste) > n else "")


def pruefen(data, ref, src, ziele):
    """-> Bericht (dict mit Listen). data = 310, ref = 200."""
    c = data.get("content") or {}
    r = ref.get("content") or {}
    muster = id_muster()
    rep = {"ids_fehlen": sorted(set(r) - set(c)), "ids_zusaetzlich": sorted(set(c) - set(r)),
           "quelltext_geaendert": [], "id_form": [], "sequenz_luecken": [],
           "fehlt": {lg: [] for lg in ziele}, "leer": {lg: [] for lg in ziele}, "unbestellt": {}}
    seq = {}
    erlaubt = set(ziele) | {src}
    for tid, e in c.items():
        if not muster.match(tid):
            rep["id_form"].append(tid)
        teile = tid.split("_")
        if len(teile) >= 3 and teile[1].isdigit():
            seq.setdefault(teile[0], []).append(int(teile[1]))
        if not isinstance(e, dict):
            rep["id_form"].append(tid)
            continue
        q = e.get(src) or ""
        re_ = r.get(tid)
        if isinstance(re_, dict) and ((re_.get(src) or "") != q or re_.get("type") != e.get("type")):
            rep["quelltext_geaendert"].append(tid)
        for k in e:
            if SPRACH_SCHLUESSEL.match(k) and k not in erlaubt:
                rep["unbestellt"].setdefault(k, []).append(tid)
        if e.get("type") in config.NO_AUDIO_TYPES or not q.strip():
            continue
        for lg in ziele:
            if lg not in e:
                rep["fehlt"][lg].append(tid)
            elif not str(e[lg]).strip():
                rep["leer"][lg].append(tid)
    for cid, s in sorted(seq.items()):
        s = sorted(s)
        if s != list(range(1, len(s) + 1)):
            soll = set(range(1, max(s) + 1))
            rep["sequenz_luecken"].append({"kapitel": cid, "fehlend": sorted(soll - set(s))[:20],
                                           "doppelt": sorted({x for x in s if s.count(x) > 1})[:20]})
    return rep


def sauber(rep):
    return not (rep["ids_fehlen"] or rep["ids_zusaetzlich"] or rep["quelltext_geaendert"] or rep["id_form"]
                or rep["sequenz_luecken"] or rep["unbestellt"]
                or any(rep["fehlt"].values()) or any(rep["leer"].values()))


def run(werk, wer=None, trocken=False):
    wer = wer or "pipeline"
    g = gate.Gate(werk, STAGE, ruecksprung="310", wer=wer)
    b = bestellung.lesen(werk)
    src = b.quellsprache or config.SOURCE_LANGUAGE
    ziele = [z for z in (b.zielsprachen or []) if z != src]
    g.metrik("zielsprachen", ziele)

    ip, rp = config.work_path(werk, "310_uebersetzung"), config.work_path(werk, "200_tagging")
    ok_i = g.pflicht("uebersetzung", os.path.exists(ip), ruecksprung="310", text="310_uebersetzung.json vorhanden")
    ok_r = g.pflicht("referenz", os.path.exists(rp), ruecksprung="200", text="200_tagging.json vorhanden")
    g.pflicht("zielsprachen", bool(ziele), ruecksprung="310", text="Bestellung nennt mindestens eine Zielsprache")
    if not (ok_i and ok_r):
        g.entscheide(schreiben=not trocken)
        return g
    with open(ip, encoding="utf-8") as f:
        data = json.load(f)
    with open(rp, encoding="utf-8") as f:
        ref = json.load(f)

    rep = pruefen(data, ref, src, ziele)
    g.metrik("knoten", len(data.get("content") or {}))
    g.metrik("knoten_200", len(ref.get("content") or {}))

    # Struktur gegen 200 -> Ruecksprung 200
    g.pflicht("id_menge", not (rep["ids_fehlen"] or rep["ids_zusaetzlich"]),
              wert=len(rep["ids_fehlen"]) + len(rep["ids_zusaetzlich"]), ruecksprung="200",
              text="ID-Menge = 200" + (f": fehlen {_kurz(rep['ids_fehlen'])}" if rep["ids_fehlen"] else "")
              + (f"; zusaetzlich {_kurz(rep['ids_zusaetzlich'])}" if rep["ids_zusaetzlich"] else ""))
    g.pflicht("quelltext", not rep["quelltext_geaendert"], wert=len(rep["quelltext_geaendert"]), ruecksprung="200",
              text="Quelltext je Knoten = 200" + (f": geaendert {_kurz(rep['quelltext_geaendert'])}"
                                                    if rep["quelltext_geaendert"] else ""))
    g.pflicht("id_form", not rep["id_form"], wert=len(rep["id_form"]), ruecksprung="200",
              text="ID-Form gueltig" + (f": {_kurz(rep['id_form'])}" if rep["id_form"] else ""))
    g.pflicht("sequenz", not rep["sequenz_luecken"], wert=len(rep["sequenz_luecken"]), ruecksprung="200",
              text="Sequenz lueckenlos je Kapitel" + (f": {rep['sequenz_luecken'][:3]}" if rep["sequenz_luecken"] else ""))
    # Sprachen -> Ruecksprung 310
    for lg in ziele:
        f_, l_ = rep["fehlt"][lg], rep["leer"][lg]
        g.pflicht(f"sprache_{lg}", not (f_ or l_), wert=len(f_) + len(l_), ruecksprung="310",
                  text=f"{lg}: vorhanden und nicht leer" + (f"; fehlt {len(f_)} {_kurz(f_)}" if f_ else "")
                  + (f"; leer {len(l_)} {_kurz(l_)}" if l_ else ""))
    g.pflicht("unbestellt", not rep["unbestellt"], wert=sorted(rep["unbestellt"]) or None, ruecksprung="310",
              text="keine unbestellte Sprache" + (f": { {k: len(v) for k, v in rep['unbestellt'].items()} }"
                                                    if rep["unbestellt"] else ""))
    # Vorgaenger-Gates
    d = status.laden(werk)
    for v in ("300", "310"):
        z = status.zustand(werk, v, d=d)
        if trocken:
            g.hinweis(f"gate_{v}", z in status.FREI, text=f"Gate {v}: {z}")
        else:
            g.pflicht(f"gate_{v}", z in status.FREI, wert=z, ruecksprung=v, text=f"Gate {v} frei ({z})")

    meta = data.setdefault("meta", {})
    meta["integrity_report"] = dict(rep, clean=sauber(rep), zielsprachen=ziele, geprueft=manifest.jetzt())
    meta["target_languages"] = ziele
    if not trocken:
        manifest.json_atomar(config.work_path(werk, "320_integritaet"), data, indent=2)
    g.entscheide(schreiben=not trocken)
    g.bericht_daten = rep
    return g


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 320 Integritaet")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--trocken", action="store_true", help="nur pruefen, nichts schreiben")
    a = ap.parse_args(argv)
    try:
        g = run(a.werk, a.wer, a.trocken)
    except gate.GateHalt as e:
        print(e)
        return e.exit_code
    print(g.bericht())
    return gate.EXIT[g.ergebnis["ergebnis"]]


if __name__ == "__main__":
    sys.exit(main())
