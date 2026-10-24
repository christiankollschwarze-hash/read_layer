"""READ LAYER - Auswertung Hoertest (Artifact "TÆLLA Hörtest Stimmen").
Antworten holen (Claude: ArtifactData list antworten, out_dir) oder Codes "BT1.0v.1gk..." in eine Textdatei.
Aufruf: py -3.11 tools/blindtest_auswerten.py <ordner_mit_json_oder_codes.txt> [<werk> <lg> [runde]]
Schluessel: gpu_messung/<werk>_<lg>/blindtest_<runde>/trials.json (von tools/blindtest_bauen.py);
ohne Werk: gpu_messung/blindtest/trials.json (erster Hoertest Ruf der Wildnis, version cotw-de-r3).
Gezaehlt werden nur Antworten mit passender version (Codes ohne version zaehlen immer)."""
import glob, json, os, sys, collections, re

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def schluessel(werk=None, lg=None, runde=None):
    if not werk:
        T = json.load(open(os.path.join(HIER, "gpu_messung", "blindtest", "trials.json"), encoding="utf-8"))
        return {t["id"]: t for t in T}, "cotw-de-r3"
    z = os.path.join(HIER, "gpu_messung", f"{werk}_{lg}")
    if not runde:
        ds = sorted(glob.glob(os.path.join(z, "blindtest_r*")), key=lambda p: int(re.sub(r"\D", "", p.rsplit("_r", 1)[1]) or 0))
        if not ds:
            sys.exit(f"kein Hoertest in {z} (tools/blindtest_bauen.py)")
        runde = os.path.basename(ds[-1])[len("blindtest_"):]
    T = json.load(open(os.path.join(z, f"blindtest_{runde}", "trials.json"), encoding="utf-8"))
    return {t["id"]: t for t in T["trials"]}, T["version"]


def lesen(pfad, version):
    leute = []
    for f in glob.glob(os.path.join(pfad, "**", "*.json"), recursive=True):
        d = json.load(open(f, encoding="utf-8"))
        d = d.get("data", d) if isinstance(d, dict) else {}
        a = d.get("antworten")
        if a and d.get("version", version) == version:
            leute.append(dict(a))
    for f in glob.glob(os.path.join(pfad, "*.txt")):
        for z in open(f, encoding="utf-8").read().split():
            if z.startswith("BT1."):
                eintrag = {}
                for x in z.split(".")[1:]:
                    nr = x.rstrip("gvk"); kenn = x[len(nr):]
                    eintrag["t" + nr] = {"a": "gleich" if "g" in kenn else "verschieden", "k": "k" in kenn}
                leute.append(eintrag)
    return leute


def main(pfad, werk=None, lg=None, runde=None):
    T, version = schluessel(werk, lg, runde)
    leute = lesen(pfad, version)
    zelle = collections.defaultdict(lambda: [0, 0, 0])   # richtig, gesamt, kuenstlich
    for a in leute:
        for tid, x in a.items():
            t = T.get(tid)
            if not t:
                continue
            key = (t["art"], t["figur"], t["version"])
            zelle[key][0] += x["a"] == t["richtig"]; zelle[key][1] += 1; zelle[key][2] += bool(x.get("k"))
    print(f"Hoertest {version}: {len(leute)} Hoerer\n{'Art':12} {'Figur':28} {'Version':6} {'richtig':>8} {'kuenstlich':>10}")
    for k, (r, n, kk) in sorted(zelle.items()):
        print(f"{k[0]:12} {k[1]:28} {k[2]:6} {r}/{n} ({r / n:.0%})  {kk / n:.0%}")
    print("Trennung bestaetigt je Figur/Version, wenn 'verschieden' >= 75 % UND Kontrollen (erz_erz, figur_figur) >= 75 % 'gleich'.")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    main(a[0], *(a[1:4]))
