"""READ LAYER - Hoertest-Generator (Artifact "TÆLLA Hörtest Stimmen") fuer ein beliebiges Werk.

Aufruf:  py -3.11 tools/blindtest_bauen.py <werk> <lg> [--runde rN] [--je-figur 5] [--kontrollen 4]
Braucht: gpu_messung/<werk>_<lg>/ (tools/trennung_messen.py, mit Runde) und ffmpeg im PATH (oder pip imageio-ffmpeg).

Paare (Hoerer entscheidet "dieselbe Person?"):
  erz_figur  vor   Erzaehler daneben (nb__) gegen Figur VC roh (vc__)            richtig: verschieden
  erz_figur  nach  Erzaehler daneben gegen Figur im fertigen Overlay (kx__<runde>) richtig: verschieden
  figur_figur nach zwei verschiedene Spannen derselben Figur (Overlay)            richtig: gleich   (Kontrolle)
  erz_erz    -     zwei verschiedene Erzaehler-Saetze des Werks (en__)            richtig: gleich   (Kontrolle)
Figuren ohne Korrektur: vor == nach -> nur "nach".

Schreibt gpu_messung/<werk>_<lg>/blindtest_<runde>/: hoertest.html (aus tools/vorlagen/hoertest_stimmen.html),
trials.json (Schluessel fuer tools/blindtest_auswerten.py), clips/*.mp3.
Danach (Claude-Sitzung): Artifact "TÆLLA Hörtest Stimmen" mit hoertest.html neu veroeffentlichen (gleiche URL).
Antworten landen in dessen Datenbank, Sammlung "antworten", mit version = <werk>-<lg>-<runde>.
"""
import os, sys, json, glob, random, base64, shutil, subprocess, tempfile, re
import numpy as np
import soundfile as sf

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VORLAGE = os.path.join(HIER, "tools", "vorlagen", "hoertest_stimmen.html")
SR = 24000
MAX_S, MIN_S = 4.0, 1.2


def ffmpeg():
    f = shutil.which("ffmpeg")
    if f:
        return f
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("ffmpeg fehlt: in den PATH legen oder  py -3.11 -m pip install imageio-ffmpeg")


def clip(pfad, start_mitte=False):
    x, sr = sf.read(pfad, dtype="float32", always_2d=False)
    if x.ndim > 1:
        x = x.mean(axis=1)
    n = int(MAX_S * sr)
    if len(x) > n:
        a = (len(x) - n) // 2 if start_mitte else 0
        x = x[a:a + n]
    rms = float(np.sqrt(np.mean(x ** 2))) or 1e-9
    x = x * (10 ** (-20 / 20) / rms)                       # alle Ausschnitte auf -20 dBFS RMS: keine Lautstaerke-Hinweise
    f = int(0.015 * sr)
    if len(x) > 2 * f:
        x[:f] *= np.linspace(0, 1, f); x[-f:] *= np.linspace(1, 0, f)
    return np.clip(x, -1, 1), sr


def mp3(x, sr, ziel, exe):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as t:
        sf.write(t.name, x, sr, subtype="PCM_16")
    subprocess.run([exe, "-y", "-loglevel", "error", "-i", t.name, "-ac", "1", "-b:a", "64k", ziel], check=True)
    os.unlink(t.name)


def runden_liste(M):
    if M.get("runden"):
        return list(M["runden"])
    rs = {s.get("variante") for s in M["segmente"] if s["typ"] == "kx" and re.fullmatch(r"r\d+", s.get("variante") or "")}
    return sorted(rs, key=lambda r: int(r[1:]))


def main(book, lg, runde=None, je_figur=5, kontrollen=4):
    z = os.path.join(HIER, "gpu_messung", f"{book}_{lg}")
    M = json.load(open(os.path.join(z, "manifest.json"), encoding="utf-8"))
    runde = runde or (runden_liste(M) or [None])[-1]
    if not runde:
        sys.exit("Keine Runde im Paket - erst tools/trennung_messen.py <werk> <lg> --runde auto")
    seg = {s["id"]: s for s in M["segmente"]}
    da = lambda sid: sid in seg and os.path.exists(os.path.join(z, "segmente", sid + ".wav"))
    werk = glob.glob(os.path.join(HIER, "authors", "*", "books", book))[0]
    b = json.load(open(os.path.join(werk, "book.json"), encoding="utf-8"))
    fl = next((f for f in b.get("fassungen", []) if f.get("sprache") == lg), {}) or {}
    titel = fl.get("titel") or b.get("titel_original") or book
    rnd = random.Random(f"{book}{lg}{runde}")
    trials, quellen = [], []          # quellen: (schluessel, segment-id)

    def neu(sid):
        quellen.append((f"q{len(quellen)}", sid)); return quellen[-1][0]

    figuren = {}
    for s in M["segmente"]:
        if s["typ"] == "vc" and s["dauer"] >= MIN_S and da("nb__" + s["job"]) and da(f"kx__{runde}__" + s["job"]):
            figuren.setdefault(s["figur"], []).append(s)
    for f, sp in sorted(figuren.items(), key=lambda kv: -len(kv[1])):
        rnd.shuffle(sp)
        korr = abs(float(seg[f"kx__{runde}__" + sp[0]["job"]].get("formant_faktor", 1.0)) - 1) > 1e-3
        plan = (["vor", "vor", "nach", "nach"] if korr else ["nach", "nach", "nach"])[:max(1, je_figur - 1)]
        i = 0
        for v in plan:
            if i >= len(sp):
                break
            j = sp[i]["job"]; i += 1
            fig = ("vc__" if v == "vor" else f"kx__{runde}__") + j
            trials.append(dict(art="erz_figur", figur=f, version=v, a=neu("nb__" + j), b=neu(fig), richtig="verschieden",
                               segmente=["nb__" + j, fig]))
        if len(sp) - i >= 2:
            j1, j2 = sp[i]["job"], sp[i + 1]["job"]
            trials.append(dict(art="figur_figur", figur=f, version="nach", a=neu(f"kx__{runde}__{j1}"), b=neu(f"kx__{runde}__{j2}"),
                               richtig="gleich", segmente=[f"kx__{runde}__{j1}", f"kx__{runde}__{j2}"]))
    en = [s["id"] for s in M["segmente"] if s["typ"] == "en" and s["dauer"] >= MIN_S and da(s["id"])]
    rnd.shuffle(en)
    for k in range(min(kontrollen, len(en) // 2)):
        a, c = en[2 * k], en[2 * k + 1]
        trials.append(dict(art="erz_erz", figur="Erzaehler", version="-", a=neu(a), b=neu(c), richtig="gleich", segmente=[a, c]))
    for i, t in enumerate(trials):
        t["id"] = f"t{i}"
    # Ausschnitte: anonyme Schluessel k0..kN in zufaelliger Reihenfolge
    ziel = os.path.join(z, f"blindtest_{runde}")
    cd = os.path.join(ziel, "clips")
    os.makedirs(cd, exist_ok=True)
    exe = ffmpeg()
    ks = list(range(len(quellen))); rnd.shuffle(ks)
    q2k = {q: f"k{ks[i]}" for i, (q, _) in enumerate(quellen)}
    audio = {}
    for q, sid in quellen:
        x, sr = clip(os.path.join(z, "segmente", sid + ".wav"), start_mitte=sid.startswith(("nb__", "en__")))
        p = os.path.join(cd, q2k[q] + ".mp3")
        mp3(x, sr, p, exe)
        audio[q2k[q]] = base64.b64encode(open(p, "rb").read()).decode("ascii")
    for t in trials:
        t["a"], t["b"] = q2k[t["a"]], q2k[t["b"]]
    version = f"{book}-{lg}-{runde}"
    P = {"trials": [{"id": t["id"], "a": t["a"], "b": t["b"]} for t in trials], "audio": audio}
    html = open(VORLAGE, encoding="utf-8").read()
    for k, v in (("__PAKET__", json.dumps(P, separators=(",", ":"))), ("__WERK__", titel), ("__N__", str(len(trials))),
                 ("__MIN__", str(max(2, round(len(trials) * 14 / 60)))), ("__VERSION__", version)):
        html = html.replace(k, v)
    open(os.path.join(ziel, "hoertest.html"), "w", encoding="utf-8").write(html)
    json.dump({"version": version, "werk": book, "lang": lg, "runde": runde, "trials": trials},
              open(os.path.join(ziel, "trials.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    from collections import Counter
    print(f"[hoertest] {len(trials)} Paare ({dict(Counter((t['art'], t['version']) for t in trials))}), "
          f"{len(html) // 1024} KB -> {os.path.join(ziel, 'hoertest.html')}  (version {version})")
    return ziel


def opt(n, d=None):
    return sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d


if __name__ == "__main__":
    a = [x for i, x in enumerate(sys.argv[1:], 1) if not x.startswith("--") and not sys.argv[i - 1].startswith("--")]
    if len(a) < 2:
        sys.exit(__doc__)
    main(a[0], a[1], opt("--runde"), int(opt("--je-figur", 5)), int(opt("--kontrollen", 4)))
