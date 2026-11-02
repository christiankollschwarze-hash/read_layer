"""STAGE 195 — Teilung (neu; GATE_KATALOG.md Zeile 195, 01.11.2026)
Funktion:     Teilt zu lange Werke an Kapitelgrenzen in Reihenteile `<slug>-1…n` (≈ 7–8 h Hörbuch je Teil).
Eingang:      work/modernized/chapter-N.json (Stand 190), raw_modernized.txt (Hash), book.json.
Ausgabe:      work/195_teilung.json (Vorschlag/Entscheidung). Nach Annahme neue Werke `<slug>-k` neben dem
              Werk: book.json (Kopie + reihe, teil, teile_gesamt, teil_von, kapitel_von/bis, teil_titel;
              geerbt: Rechte, Produkte 095, glossar_fest …), work/modernized (Kapitel umnummeriert, mit Original),
              raw_modernized.txt, status.json (Gates 080–120 geerbt, 190 am Teil neu geprueft, 195 frei).
              Das Werk selbst bekommt `geteilt_in` → seine Stages nach 195 entfallen (kette.bedarf).
Gate:         Zeichen gesamt ≤ Grenzwert → auto (keine Teilung). Sonst Teilezahl = aufgerundet gesamt/Grenzwert,
              Schnitt nur an Kapitelgrenzen, Teile moeglichst gleich lang (DP, kleinste Quadratabweichung);
              Original-Gliederung (VOLUME/PART/BOOK im Kapiteltitel oder ersten Absatz) bevorzugt, wenn jeder Teil
              ≤ ±15 % vom Optimum (gesamt/Teile) → Mensch (annehmen / Schnitt verschieben / ablehnen).
              Einzelkapitel > Grenzwert → Mensch (Hinweis). Abgelehnt trotz Ueberschreitung → auto mit Warnung.
              Text seit Vorschlag geaendert (Hash) → neuer Vorschlag, Entscheidung verfaellt.
Kosten:       0 $ (kein LLM).
Regler:       --grenze N, --teile N (1 = nicht teilen = ablehnen), --schnitte 12,25 (Kapitel, mit denen Teil 2, 3 …
              beginnt), --name K=TITEL (Benennung der Teile, mehrfach), --annehmen, --ablehnen.
              Grenze/Teile/Schnitte/Name brauchen 080 `bestellen`, annehmen/ablehnen 080 `entscheiden`.
              `status --entscheiden 195 frei` ohne --annehmen = ablehnen (weiter ohne Teilung, Warnung).
Aufruf:
  python -m pipeline.s195_teilung <werk> [--grenze 400000] [--schnitte 12] [--annehmen|--ablehnen] [--wer CK]
Exit: 0 auto, 2 Stopp, 3 Mensch.
"""
import argparse
import copy
import datetime
import json
import math
import os
import re
import shutil
import sys

from config import config
from pipeline import bestellung, gate, s080_mandant, status
from pipeline.manifest import hash_obj, json_atomar

STAGE = "195"
GRENZE = 400_000
GLIEDERUNG_TOL = 0.15
HR = "——HR——"
GEERBT = ("080", "090", "095", "100", "110", "150", "115", "120")
NICHT_ERBEN = ("geteilt_in", "teilung")


def _z(n):
    return f"{n:,}".replace(",", ".")


def _jetzt():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _lesen(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _mod_dir(werk):
    return os.path.join(config.work_dir(werk), "modernized")


def kapitel(werk):
    """-> [(n, titel, zeichen, struktur)] aus chapter-N.json."""
    from pipeline.s120_modernisierung import STRUKTUR
    d = _mod_dir(werk)
    if not os.path.isdir(d):
        return []
    nr = sorted(int(m.group(1)) for f in os.listdir(d) if (m := re.fullmatch(r"chapter-(\d+)\.json", f)))
    out = []
    for n in nr:
        c = _lesen(os.path.join(d, f"chapter-{n}.json"))
        paras = [p for p in (c.get("paragraphs") or []) if p and p != HR]
        t = (c.get("title") or "").strip()
        struktur = bool(STRUKTUR.match(t)) or bool(paras and STRUKTUR.fullmatch(paras[0].strip().rstrip(".")))
        out.append((n, t, len(t) + sum(len(p) for p in paras), struktur))
    return out


def summen(L, starts):
    grenzen = list(starts) + [len(L)]
    return [sum(L[grenzen[i]:grenzen[i + 1]]) for i in range(len(starts))]


def optimum(L, n, erlaubt=None):
    """Exakte Aufteilung von L in n zusammenhaengende Teile mit kleinster Quadratabweichung vom Mittel.
    erlaubt = zulaessige Startindizes (ausser 0); None = alle. -> starts oder None."""
    k = len(L)
    if n <= 1 or k < n:
        return [0] if n <= 1 else None
    ziel = sum(L) / n
    pre = [0]
    for x in L:
        pre.append(pre[-1] + x)
    ok = (lambda i: True) if erlaubt is None else (lambda i: i in erlaubt)
    INF = float("inf")
    # best[j][i]: Kosten fuer die ersten i Kapitel in j Teilen
    best = [[INF] * (k + 1) for _ in range(n + 1)]
    von = [[-1] * (k + 1) for _ in range(n + 1)]
    best[0][0] = 0.0
    for j in range(1, n + 1):
        for i in range(j, k + 1):
            if i < k and not ok(i):
                continue                     # Teil j endet vor Kapitel i -> i muss Startpunkt sein
            for s in range(j - 1, i):
                if best[j - 1][s] == INF or (s > 0 and not ok(s)):
                    continue
                c = best[j - 1][s] + (pre[i] - pre[s] - ziel) ** 2
                if c < best[j][i]:
                    best[j][i], von[j][i] = c, s
    if best[n][k] == INF:
        return None
    starts, i = [], k
    for j in range(n, 0, -1):
        i = von[j][i]
        starts.append(i)
    return sorted(starts)


def vorschlag(kap, grenze, teile=None, schnitte=None):
    """-> (starts 0-basiert, herkunft)."""
    L = [z for _n, _t, z, _s in kap]
    if schnitte:
        starts = sorted({0} | {s - 1 for s in schnitte})
        return starts, "manuell"
    n = teile or max(1, math.ceil(sum(L) / grenze))
    n = min(n, len(L))
    opt = optimum(L, n)
    if n > 1:
        erlaubt = {i for i, (_n, _t, _z, s) in enumerate(kap) if s and i > 0}
        if len(erlaubt) >= n - 1:
            gl = optimum(L, n, erlaubt)
            ideal = sum(L) / n
            if gl and all(abs(x - ideal) <= GLIEDERUNG_TOL * ideal for x in summen(L, gl)):
                return gl, "gliederung"
    return opt, "optimum" if n > 1 else "keine"


def _teile_liste(werk, kap, starts, namen):
    L = [z for _n, _t, z, _s in kap]
    S = summen(L, starts)
    grenzen = list(starts) + [len(kap)]
    out = []
    for i, s in enumerate(starts):
        k = i + 1
        out.append({"teil": k, "slug": f"{werk}-{k}", "kapitel_von": kap[s][0],
                    "kapitel_bis": kap[grenzen[i + 1] - 1][0], "zeichen": S[i],
                    "titel": (namen or {}).get(k)})
    return out


def _quelle_hash(werk):
    p = os.path.join(config.book_dir(werk), "raw_modernized.txt")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return hash_obj(f.read())


# ------------------------------------------------------------------ Teile anlegen
def teile_anlegen(werk, rec, wer):
    """Legt die Teilwerke an (Index, book.json, Kapitel, raw_modernized.txt, status.json) und prueft
    jeden Teil mit 190. -> {slug: ergebnis 190}."""
    from pipeline import s120_modernisierung as M, s190_vertrag
    idx = config._load_index()
    autor = idx["books"].get(werk)
    if not autor:
        raise RuntimeError(f"{werk} nicht im Index")
    basis = config.book_dir(werk)
    eltern = os.path.dirname(basis)
    roh = _lesen(os.path.join(basis, "book.json"))
    st_werk = status.laden(werk)
    n = len(rec["teile"])
    for t in rec["teile"]:
        alt = idx["books"].get(t["slug"])
        if alt and alt != autor:
            raise RuntimeError(f"{t['slug']} gehoert im Index zu {alt}")
        ziel = os.path.join(eltern, t["slug"])
        if os.path.exists(os.path.join(ziel, "book.json")) and \
                _lesen(os.path.join(ziel, "book.json")).get("teil_von") != werk:
            raise RuntimeError(f"{ziel} existiert und ist kein Teil von {werk}")
    for t in rec["teile"]:
        idx["books"][t["slug"]] = autor
    config._save_index(idx)

    ergebnisse = {}
    for t in rec["teile"]:
        slug, ziel = t["slug"], os.path.join(eltern, t["slug"])
        md = os.path.join(ziel, "work", "modernized")
        if os.path.isdir(md):
            shutil.rmtree(md)
        os.makedirs(md)
        b = {k: copy.deepcopy(v) for k, v in roh.items() if k not in NICHT_ERBEN}
        b.update(book_slug=slug, reihe=werk, teil=t["teil"], teile_gesamt=n, teil_von=werk,
                 kapitel_von=t["kapitel_von"], kapitel_bis=t["kapitel_bis"], teil_titel=t.get("titel"))
        json_atomar(os.path.join(ziel, "book.json"), b, indent=2)
        for neu, alt_n in enumerate(range(t["kapitel_von"], t["kapitel_bis"] + 1), 1):
            for suf in ("", ".original"):
                q = os.path.join(_mod_dir(werk), f"chapter-{alt_n}{suf}.json")
                if os.path.exists(q):
                    shutil.copyfile(q, os.path.join(md, f"chapter-{neu}{suf}.json"))
        for datei in ("author.json",):          # ePub-Werke ohne Autorordner: nichts zu tun
            q = os.path.join(basis, datei)
            if os.path.exists(q):
                shutil.copyfile(q, os.path.join(ziel, datei))
        M._write_marked_source(slug, md)
        anzahl = t["kapitel_bis"] - t["kapitel_von"] + 1
        with status.aendern(slug) as d:
            for s in GEERBT:
                e = copy.deepcopy(st_werk["stages"].get(s) or status._stage_leer())
                if s == "120":
                    e.setdefault("metriken", {})["kapitel"] = anzahl
                d["stages"][s] = e
            d["protokoll"].append({"wann": status.jetzt(), "wer": wer, "aktion": "teilung",
                                   "grund": f"Teil {t['teil']}/{n} aus {werk} (195), Gates 080–120 geerbt"})
        g190 = s190_vertrag.run(slug, wer)
        ergebnisse[slug] = g190.ergebnis["ergebnis"]
        status.ergebnis(slug, STAGE, "auto", wer=wer, metriken={"teil": t["teil"], "teile_gesamt": n,
                                                                "teil_von": werk, "zeichen": t["zeichen"]})
    bestellung.feld_setzen(werk, geteilt_in=[t["slug"] for t in rec["teile"]])
    return ergebnisse


# ------------------------------------------------------------------ Gate
def run(werk, wer=None, grenze=None, teile=None, schnitte=None, namen=None, annehmen=False, ablehnen=False):
    wer = s080_mandant.nutzer(wer)
    if any(x is not None for x in (grenze, teile, schnitte, namen)):
        s080_mandant.darf(werk, "bestellen", wer)
    if annehmen or ablehnen:
        s080_mandant.darf(werk, "entscheiden", wer)
    if annehmen and ablehnen:
        raise ValueError("--annehmen und --ablehnen schliessen sich aus")
    if teile == 1:
        ablehnen, teile = True, None

    g = gate.Gate(werk, STAGE, ruecksprung="195", wer=wer)
    pfad = os.path.join(config.work_dir(werk), "195_teilung.json")
    alt = _lesen(pfad) if os.path.exists(pfad) else {}
    roh = bestellung.lesen(werk).roh
    kap = kapitel(werk)
    if not g.pflicht("kapitel", bool(kap), wert=len(kap), ruecksprung="190", text=f"Kapitel {len(kap)}"):
        g.entscheide()
        return g
    qh = _quelle_hash(werk)
    regler = any(x is not None for x in (teile, schnitte, namen)) or \
        (grenze is not None and grenze != alt.get("grenze"))
    grenze = grenze or alt.get("grenze") or GRENZE
    gesamt = sum(z for _n, _t, z, _s in kap)
    gleich = bool(alt) and alt.get("quelle_hash") == qh and not regler
    if gleich:
        rec = alt
    else:
        if alt and alt.get("quelle_hash") != qh and alt.get("entscheidung"):
            g.hinweis("text_geaendert", False, text="Text seit Vorschlag geaendert → neuer Vorschlag, "
                                                    "Entscheidung verfaellt")
        nm = dict(alt.get("namen") or {}) if alt else {}
        nm = {int(k): v for k, v in nm.items()}
        nm.update(namen or {})
        if teile is None and not schnitte and alt.get("quelle_hash") == qh:
            teile = alt.get("teile_soll")
        starts, herkunft = vorschlag(kap, grenze, teile, schnitte)
        rec = {"schema": 1, "quelle_hash": qh, "grenze": grenze, "zeichen": gesamt, "herkunft": herkunft,
               "teile_soll": teile, "namen": {str(k): v for k, v in nm.items()},
               "kapitel": [{"n": n, "titel": t, "zeichen": z, "gliederung": s} for n, t, z, s in kap],
               "teile": _teile_liste(werk, kap, starts, nm), "entscheidung": None, "wer": None, "wann": None}
    if schnitte:
        ungueltig = [s for s in schnitte if s < 2 or s > len(kap)]
        g.pflicht("schnitte", not ungueltig, wert=ungueltig or None, ruecksprung="195",
                  text="Schnitte an Kapitel 2…" + str(len(kap)) + (f" – ungueltig {ungueltig}" if ungueltig else ""))

    ueber = gesamt > grenze
    teilen = len(rec["teile"]) > 1
    zz = [t["zeichen"] for t in rec["teile"]]
    g.metrik("zeichen", gesamt)
    g.metrik("grenze", grenze)
    g.metrik("teile", len(rec["teile"]))
    g.metrik("teil_zeichen", zz)
    g.metrik("spanne", max(zz) - min(zz))
    g.metrik("herkunft", rec["herkunft"])
    g.metrik("vorschlag", [f"Teil {t['teil']}: Kap. {t['kapitel_von']}–{t['kapitel_bis']} "
                           f"({_z(t['zeichen'])} Z.)" for t in rec["teile"]])
    gross = [f"{n}. {t} ({_z(z)} Z.)" for n, t, z, _s in kap if z > grenze]
    g.pruefe("kapitel_ueber_grenze", not gross, len(gross), f"<= {grenze}", "mensch", "120",
             text="Einzelkapitel > Grenzwert: " + "; ".join(gross[:5]) if gross else "kein Kapitel > Grenzwert")
    ueber_teile = [t["teil"] for t in rec["teile"] if t["zeichen"] > grenze]
    if teilen:
        g.hinweis("teil_ueber_grenze", not ueber_teile, wert=len(ueber_teile),
                  text=f"Teile > Grenzwert: {ueber_teile}" if ueber_teile else "alle Teile ≤ Grenzwert")
    g.metrik("geteilt_in", roh.get("geteilt_in"))

    if annehmen or ablehnen:
        rec.update(entscheidung="angenommen" if annehmen else "abgelehnt", wer=wer, wann=_jetzt())
    if annehmen and not teilen:
        g.hinweis("annehmen_ohne_teilung", False, text="--annehmen ohne Teilung (1 Teil) wirkungslos")
        rec["entscheidung"] = None
    json_atomar(pfad, rec, indent=2)

    entsch = rec.get("entscheidung")
    if g.fehler():
        g.entscheide()
    elif not ueber and not teilen:
        g.entscheide()
    elif entsch == "abgelehnt" or not teilen:
        g.hinweis("ueber_grenze", not ueber, wert=gesamt,
                  text=f"Werk {_z(gesamt)} Z. > Grenzwert {_z(grenze)} – Teilung abgelehnt, weiter ohne Teilung")
        g.entscheide()
    elif entsch == "angenommen":
        slugs = [t["slug"] for t in rec["teile"]]
        if roh.get("geteilt_in") == slugs:
            g.metrik("geteilt_in", slugs)
            g.hinweis("bereits_geteilt", True, text=f"Teile bestehen bereits: {', '.join(slugs)}")
        elif roh.get("geteilt_in"):
            g.pruefe("bereits_geteilt", False, bei_fehler="mensch", ruecksprung="195",
                     text=f"Werk bereits geteilt in {roh['geteilt_in']} – neue Teilung nur nach Aufraeumen")
        else:
            try:
                erg = teile_anlegen(werk, rec, wer)
                g.metrik("geteilt_in", list(erg))
                g.pflicht("teile_190", all(e == "auto" for e in erg.values()), ruecksprung="195",
                          text="Gate 190 je Teil: " + ", ".join(f"{k} {v}" for k, v in erg.items()))
            except Exception as e:
                g.pflicht("teile_anlegen", False, ruecksprung="195", text=f"Teile anlegen: {e}")
        g.entscheide()
    else:
        grund = (f"Werk {_z(gesamt)} Z. > Grenzwert {_z(grenze)}: Vorschlag {len(rec['teile'])} Teile "
                 f"({rec['herkunft']}) – " + "; ".join(g.metriken["vorschlag"]) +
                 " → --annehmen | --schnitte K,… | --ablehnen")
        g.entscheide(mensch_immer=True, mensch_grund=grund)
    return g


def _namen(liste):
    out = {}
    for x in liste or []:
        k, _, v = x.partition("=")
        if not k.strip().isdigit() or not v.strip():
            raise SystemExit(f"--name {x!r}: Format K=TITEL")
        out[int(k)] = v.strip()
    return out or None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 195 Teilung")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--grenze", type=int, help=f"Zeichen je Teil (Standard {GRENZE})")
    ap.add_argument("--teile", type=int, help="Teilezahl manuell (1 = nicht teilen)")
    ap.add_argument("--schnitte", help="Kapitel, mit denen Teil 2, 3 … beginnt, z. B. 12,25")
    ap.add_argument("--name", action="append", help="K=TITEL Benennung von Teil K (mehrfach)")
    ap.add_argument("--annehmen", action="store_true")
    ap.add_argument("--ablehnen", action="store_true")
    a = ap.parse_args(argv)
    schnitte = [int(x) for x in a.schnitte.split(",") if x.strip()] if a.schnitte else None
    try:
        g = run(a.werk, a.wer, a.grenze, a.teile, schnitte, _namen(a.name), a.annehmen, a.ablehnen)
    except (PermissionError, ValueError) as e:
        print(f"FEHLER: {e}")
        return 1
    print(g.bericht())
    return gate.EXIT[g.ergebnis["ergebnis"]]


if __name__ == "__main__":
    sys.exit(main())
