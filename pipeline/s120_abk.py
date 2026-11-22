"""STAGE 120 — Schritt "Abkuerzungen" (Teil A2, 22.11.2026; Entscheidung CK 22.11.2026 15:35)
Funktion:     Abkuerzungen im Lesetext der MODERNISIERTEN Fassung ausschreiben ("ch. 65" -> "chapter 65",
              "pp. 12–14" -> "pages 12–14", "S. 12 ff." -> "Seite 12 und folgende"); Ziffern bleiben.
              Fassung original: nichts (Lesetext bleibt, 400 spricht aus).
Quelle:       EINE Tabelle wie 400: config/abk_sprech_<lg>.json + book.json abk_sprech (sprechtext.abk_tabelle),
              gleiche Bedingungen (zahl | nach_zahl | name). Feld lesetext/lesetext_plural je Eintrag, falls abweichend.
Ablauf:       deterministisch, 0 $, nach Modernisierung und Fremdsprache-Schritt. Basis bleibt in chapter-N.json
              paragraphs_vor_fremd (Basis vor allen Nachschritten); Ruecknahme: book.json abk_lesetext false.
Befunde:      Abkuerzung der Tabelle, bei der keine Bedingung passt (z. B. "f. 1" = Folio) -> Monitor 120:
              ausschreiben (Wort waehlen) | bleibt stehen | in die Werktabelle (book.json abk_sprech, wie 400).
              Behaltene Fremdzitate (120_fremd.json) werden nicht angefasst.
Datei:        work/120_abk.json {version, aktiv, sprache, stellen [{id, kapitel, absatz, abk, wort, herkunft
              sprache|werk|hand, kontext}], befunde [{id, kapitel, absatz, abk, vorschlaege, kontext}],
              entscheidungen {id: {wort, wer, wann}}}  (wort "" = bleibt stehen)
Stellen-ID:   "K:A:ABK#n" (Kapitel, Absatz 1-basiert, Abkuerzung ohne Leerzeichen, n-tes Vorkommen im Absatz).
"""
import datetime
import json
import os

from config import config
from pipeline import manifest
from pipeline import sprechtext as st

VERSION = 1
KONTEXT = 40


def pfad(werk):
    return os.path.join(config.work_dir(werk), "120_abk.json")


def lesen(werk):
    p = pfad(werk)
    if not os.path.exists(p):
        return {"version": VERSION, "aktiv": False, "stellen": [], "befunde": [], "entscheidungen": {}}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def schreiben(werk, d):
    manifest.json_atomar(pfad(werk), d, indent=1)


def aktiv(roh, fassung):
    return fassung == "modernisiert" and (roh or {}).get("abk_lesetext", True) is not False


def sid(k, a, key, n):
    return f"{k}:{a}:{key}#{n}"


def _sid_teile(i):
    stelle, n = i.rsplit("#", 1)
    k, a, key = stelle.split(":", 2)
    return int(k), int(a), key, int(n)


def _kontext(p, a, e):
    return ("…" if a > KONTEXT else "") + p[max(0, a - KONTEXT):a] + "[" + p[a:e] + "]" + p[e:e + KONTEXT] + (
        "…" if e + KONTEXT < len(p) else "")


def _fremd_bereiche(p, saetze):
    out = []
    for t in saetze:
        i = p.find(t)
        while i >= 0:
            out.append((i, i + len(t)))
            i = p.find(t, i + 1)
    return out


def entscheiden(d, aenderungen, wer):
    """aenderungen ["ID=WORT", ...]; WORT "" = bleibt stehen, "offen" = Entscheidung loeschen."""
    ent = d.setdefault("entscheidungen", {})
    for x in aenderungen or []:
        if "=" not in x:
            raise ValueError(f"--abk {x!r}: Form ID=WORT (leer = bleibt stehen, offen = zuruecksetzen)")
        i, w = x.split("=", 1)
        i, w = i.strip(), " ".join(w.split())
        _sid_teile(i)
        if w == "offen":
            ent.pop(i, None)
        else:
            ent[i] = {"wort": w, "wer": wer, "wann": datetime.datetime.now().isoformat(timespec="seconds")}
    return d


def anwenden(kapitel, lg, abk_werk, d, fremd_saetze=()):
    """Kapitel [(titel, absaetze)] -> neue Kapitel; d bekommt stellen/befunde (Entscheidungen bleiben)."""
    tab = st.abk_tabelle(lg, abk_werk)
    hand = {}
    for i, e in (d.get("entscheidungen") or {}).items():
        k, a, key, n = _sid_teile(i)
        hand.setdefault((k, a), {})[(key, n)] = e.get("wort") or ""
    stellen, befunde, neu = [], [], []
    for k, (titel, paras) in enumerate(kapitel, 1):
        aus = []
        for a, p in enumerate(paras, 1):
            if not isinstance(p, str) or not p:
                aus.append(p)
                continue
            t, st_, of = st.abk_lesetext(p, lg, tab, _fremd_bereiche(p, fremd_saetze), hand.get((k, a)))
            for x in st_:
                stellen.append({"id": sid(k, a, x["key"], x["n"]), "kapitel": k, "absatz": a, "abk": x["abk"],
                                "wort": x["wort"], "herkunft": x["herkunft"], "kontext": _kontext(p, x["a"], x["e"])})
            for x in of:
                befunde.append({"id": sid(k, a, x["key"], x["n"]), "kapitel": k, "absatz": a, "abk": x["abk"],
                                "vorschlaege": x["vorschlaege"], "kontext": _kontext(p, x["a"], x["e"])})
            aus.append(t)
        neu.append((titel, aus))
    gueltig = {s["id"] for s in stellen} | {b["id"] for b in befunde}
    bleibt = {i for i, e in (d.get("entscheidungen") or {}).items() if not e.get("wort")}
    d.update({"version": VERSION, "aktiv": True, "sprache": lg, "stellen": stellen, "befunde": befunde,
              "verwaist": sorted(i for i in (d.get("entscheidungen") or {}) if i not in gueltig and i not in bleibt)})
    return neu


def zusammenfassung(d):
    z = {}
    for s in d.get("stellen") or []:
        z[s["herkunft"]] = z.get(s["herkunft"], 0) + 1
    return z
