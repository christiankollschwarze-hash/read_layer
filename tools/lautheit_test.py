"""READ LAYER — A/B-Test Segment-Lautheit (pipeline/lautheit.py) an einzelnen Kapiteln, OHNE Neurendern und OHNE
Eingriff in Endfassungen, Manifeste oder status.json (AP Lautheit 27.11.2026).

Ablauf je Spur und Kapitel: Roh-WAVs (500/510) + Spannen + 430-Offsets -> Segment-Normierung -> Schnitt/Tempo mit den
FA-Raendern aus dem vorhandenen 520-Manifest (kein FA-/Whisper-Lauf, 0 $) -> Kapitel-Mastering -> CSV je Sprecher.
Hoerdateien (Satzfolge wie in der App: Hoerspielsatz, sonst Hoerbuchsatz; 300 ms Luecke):
  <kap>_vorher.wav   heutige Endfassungen (audio_final / hoerspiel_final)
  <kap>_nachher.wav  neue Fassung
Ausgabe: <werk>/work/_520_lautheit_test/<lg>/ (lautheit_<spur>.csv, hoerliste.md, WAVs).

Aufruf: py -3.11 tools/lautheit_test.py <werk> --kapitel c002,c003 [--lang de] [--lufs -19] [--peak -3]
"""
import argparse
import collections
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import bestellung, manifest
from pipeline import lautheit as L
from pipeline import s510_hoerspiel_hybrid as s510
from pipeline import s520_audio_pruefung as P

SR = 24000
LUECKE = np.zeros(int(0.3 * SR), np.float32)


def kapitel_bauen(werk, lg, spur, kap, rg, m520, quellen):
    """-> ({tid: Endfassung neu}, CSV-Zeilen, Protokoll je Segment) fuer ein Kapitel einer Spur."""
    mq = quellen[spur]
    if not mq:
        return {}, [], []
    tids = [k.split("/", 1)[1] for k in mq.eintraege if k.startswith(f"{lg}/{kap}_")]
    tids = [t for t in tids if (m520.get(f"{spur}/{t}") or {}).get("datei")]
    tids.sort(key=lambda t: list(m520.eintraege).index(f"{spur}/{t}"))
    if not tids:
        return {}, [], []
    seg = P.segment_kontext(werk, lg, spur, rg, quellen)
    roh_x = {t: s510.lesen(mq._abs(mq.get(f"{lg}/{t}")["datei"])) for t in tids}
    norm, sp_info = P.segmente_kapitel(seg, roh_x, rg)
    stuecke, info = {}, {}
    for t in tids:
        e = m520.get(f"{spur}/{t}") or {}
        tempo = float(e.get("tempo") or 1.0)
        y, rand, start = P.schneiden(norm[t], tuple(e["w"]) if e.get("w") else None, float(rg["vor"]),
                                     float(rg["nach"]), tempo, mit_start=True)
        stuecke[t] = P.tempo_anwenden(y, tempo)
        info[t] = {"start": start, "tempo": tempo}
    roh = np.concatenate([stuecke[t] for t in tids])
    ges, mi = L.mastern(roh, float(rg["lufs"]), float(rg["peak_max"]), rg)
    tempo = info[tids[0]]["tempo"]
    zeilen = P.segment_report(kap, tids, sp_info, stuecke, info, ges, tempo, rg)
    for z in zeilen:
        z["spur"] = spur
    out, pos = {}, 0
    for t in tids:
        out[t] = ges[pos:pos + len(stuecke[t])]
        pos += len(stuecke[t])
    prot = [dict(p, tid=t) for t in tids for p in sp_info["saetze"][t]["prot"]]
    print(f"  {spur} {kap}: {len(tids)} Saetze, Kalibrierung {sp_info['kal'].get(None):.2f} dB, "
          f"Master LUFS {mi['lufs_vor']} -> {mi['lufs']}, TP {mi['peak_vor']} -> {mi['peak']} dBTP")
    return out, zeilen, prot


def main(argv=None):
    ap = argparse.ArgumentParser(description="A/B-Test Segment-Lautheit (ohne Neurendern)")
    ap.add_argument("werk")
    ap.add_argument("--kapitel", required=True)
    ap.add_argument("--lang", default="de")
    ap.add_argument("--lufs", type=float, default=-19.0, help="Kapitelziel nach dem Master (Standard -19)")
    ap.add_argument("--peak", type=float, default=P.SEGMENT_PEAK)
    a = ap.parse_args(argv)
    werk, lg = a.werk, a.lang
    b = bestellung.lesen(werk)
    rg = P._regler(dict(b.roh))
    rg.update(segment_lautheit=True, lufs=a.lufs, peak_max=a.peak)
    m520 = manifest.Manifest(werk, f"520_pruefung_{lg}", stage="520")
    quellen = P._quellen(werk)
    ziel = os.path.join(config.work_dir(werk), "_520_lautheit_test", lg)
    os.makedirs(ziel, exist_ok=True)
    alle_z, alle_p = collections.defaultdict(list), []
    for kap in a.kapitel.split(","):
        neu = {}
        for spur in P.SPUREN:
            out, zeilen, prot = kapitel_bauen(werk, lg, spur, kap, rg, m520, quellen)
            neu[spur] = out
            alle_z[spur] += zeilen
            alle_p += [dict(p, spur=spur, kapitel=kap) for p in prot]
        # Hoerdateien in App-Reihenfolge: Hoerspielsatz, sonst Hoerbuchsatz
        reihe = [k.split("/", 1)[1] for k in m520.eintraege if k.startswith(f"hoerbuch/{kap}_")]
        vor, nach = [], []
        for t in reihe:
            sp = "hoerspiel" if t in neu.get("hoerspiel", {}) else "hoerbuch"
            e = m520.get(f"{sp}/{t}") or {}
            if not e.get("datei") or t not in neu.get(sp, {}):
                continue
            vor += [s510.lesen(m520._abs(e["datei"])), LUECKE]
            nach += [neu[sp][t], LUECKE]
        if vor:
            s510.schreiben(os.path.join(ziel, f"{kap}_vorher.wav"), np.concatenate(vor))
            s510.schreiben(os.path.join(ziel, f"{kap}_nachher.wav"), np.concatenate(nach))
    for spur, zeilen in alle_z.items():
        if zeilen:
            p = L.csv_schreiben(os.path.join(ziel, f"lautheit_{spur}.csv"), zeilen, ersetzt_kapitel=a.kapitel.split(","))
            print(f"CSV {p}")
    # Hoerliste: staerkste Anhebungen/Absenkungen (Figurensegmente)
    fig = sorted((p for p in alle_p if p["fig"] != L.ERZ and p["vor"] is not None), key=lambda p: -abs(p["gain"]))[:25]
    with open(os.path.join(ziel, "hoerliste.md"), "w", encoding="utf-8") as f:
        f.write(f"# Hoerliste Segment-Lautheit {werk} {lg} – Kapitel {a.kapitel}\n\n"
                f"Ziel Segment {rg['segment_lufs']} LUFS, Kapitel {rg['lufs']} LUFS, True Peak {rg['peak_max']} dBTP.\n"
                f"Dateien: <kap>_vorher.wav / <kap>_nachher.wav (Hoerspielsatz, sonst Hoerbuchsatz; 300 ms Luecke).\n\n"
                "| Spur | Satz | Figur | vorher (LUFS) | Korrektur (dB) |\n|---|---|---|---|---|\n")
        for p in fig:
            f.write(f"| {p['spur']} | {p['tid']} | {p['fig']} | {p['vor']} | {p['gain']:+.1f} |\n")
    print(f"Ausgabe: {ziel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
