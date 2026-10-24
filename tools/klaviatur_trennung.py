"""READ LAYER - Daten fuer die Stimmen-Klaviatur: Abstand Figur <-> Erzaehler je Werk (pipeline/trennung.py).
Aufruf: py -3.11 tools/klaviatur_trennung.py  -> stimmen_archiv/_klaviatur_trennung.json
Liest casting.json aller Werke (plan.ensemble[].trennung/korrektur, plan.erzaehler.profil),
stimmen_archiv/_praat_profile.json, _trennungsregel.json und vorhandene Pruefungen
(gpu_messung/<werk>_de/auswertung.json: ECAPA + pyannote am fertigen Overlay)."""
import glob, json, os

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SA = os.path.join(HIER, "stimmen_archiv")


def main():
    regel = json.load(open(os.path.join(SA, "_trennungsregel.json"), encoding="utf-8"))
    prof = json.load(open(os.path.join(SA, "_praat_profile.json"), encoding="utf-8"))
    out = {"regel": {k: regel[k] for k in ("skala_f0_ht", "skala_vtl_ht", "D_schwelle", "D_ziel")},
           "stimmen": {n: {lg: {k: v.get(k) for k in ("f0_hz", "vtl_cm")} for lg, v in p.items()} for n, p in prof.items()},
           "werke": {}}
    for cp in glob.glob(os.path.join(HIER, "authors", "*", "books", "*", "work", "casting.json")):
        werk = cp.split(os.sep)[-3]
        c = json.load(open(cp, encoding="utf-8"))
        plan = c.get("plan") or {}
        if not any(e.get("trennung") for e in plan.get("ensemble", [])):
            continue
        pruef = {}
        ap = os.path.join(HIER, "gpu_messung", f"{werk}_de", "auswertung.json")
        if os.path.exists(ap):
            A = json.load(open(ap, encoding="utf-8"))
            d = A.get("diarisierung", {})
            letzte = max((v for v in ("r1", "r2", "r3") if any(kv for e in A["figuren"].values()
                          for kv in [(e.get("korrektur_varianten") or {}).get(v)])), default=None)
            for f, e in A["figuren"].items():
                vor = e.get("ecapa_vc") or {}
                nach = ((e.get("korrektur_varianten") or {}).get(letzte) or {}).get("ecapa") if letzte else None
                pruef[f] = {"ecapa_vor": vor.get("cosdist_erzaehler"), "ecapa_nach": (nach or {}).get("cosdist_erzaehler"),
                            "naeher_ref_nach": (nach or {}).get("naeher_an_ref", vor.get("naeher_an_ref")),
                            "pyannote_vor": (d.get("figuren_vc") or {}).get(f, {}).get("getrennt"),
                            "pyannote_nach": (d.get(f"figuren_{letzte}") or {}).get(f, {}).get("getrennt") if letzte else None,
                            "pyannote_nach_n": (d.get(f"figuren_{letzte}_n") or {}).get(f, {}).get("getrennt") if letzte else None,
                            "runde": letzte}
            out.setdefault("ecapa_schwelle", (A.get("ecapa_eichung") or {}).get("clip", {}).get("schwelle_cosdist"))
        out["werke"][werk] = {
            "erzaehler": {"stimme": (plan.get("erzaehler") or {}).get("stimme"), "profil": (plan.get("erzaehler") or {}).get("profil")},
            "figuren": [{"figur": e.get("figur"), "stimme": e.get("stimme"), "trennung": e.get("trennung"),
                         "korrektur": {lg: {k: v.get(k) for k in ("formant_faktor", "tonhoehe_ht")} for lg, v in (e.get("korrektur") or {}).items()},
                         "pruefung": pruef.get(e.get("figur"))}
                        for e in plan.get("ensemble", []) if e.get("stimme")]}
    json.dump(out, open(os.path.join(SA, "_klaviatur_trennung.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[klaviatur] {len(out['werke'])} Werke -> stimmen_archiv/_klaviatur_trennung.json")


if __name__ == "__main__":
    main()
