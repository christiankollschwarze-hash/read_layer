"""Hoertest-Casting Alice Kap. 7 mit den Qwen-Stimmen (AP Qwen-Stimmdesign, Aufgabe 5; CK 26.11.: Casting nur per Hoertest).

  py -3.11 tools/alice_hoertest.py bauen      Paket gpu_overlay/alice_c007_hoertest_de (Figurenzeilen x Kandidaten)
  py -3.11 tools/alice_hoertest.py vc         Chatterbox-VC auf Modal (L4) -> tools/alice_hoertest/de/vc/
  py -3.11 tools/alice_hoertest.py erzaehler  Erzaehler-Proben ueber Fish API (Drama 3, Qwen-Klon als Referenz)
  py -3.11 tools/alice_hoertest.py seite      Hoertestseite tools/alice_hoertest/hoertest.html (Wahl -> casting_auswahl.json)
  py -3.11 tools/alice_hoertest.py alle       bauen + vc + erzaehler + seite
  py -3.11 tools/alice_hoertest.py kapitel AUSWAHL.json   Kap. 7 komplett mit gewaehlter Besetzung (Fish ~0,5 $ + VC)
Grundlage ist der bisherige Test (start_alice_fish_vc.bat): Fish-Erzaehler spricht ALLES (Figuren per Regie-Tag), Chatterbox-VC
wandelt die Figurenzeilen in die Zielstimme. Hier: dieselben Quellzeilen (gpu_overlay/alice_c007_fish_de/src) -> je Kandidat.
"Bisher" = bisherige Gemini-Zielstimme (ergebnis.zip des alten Laufs) bzw. Erzaehler grossmutter_a (de_erz_regie).
Kandidaten nur nach Geschlecht + Stimmlage vorausgewaehlt; ergaenzen mit --kandidaten "Hatter=m_mittel_03,m_mittel_04".
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import time
import wave
import zipfile

LESER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LESER)

ALT = os.path.join(LESER, "gpu_overlay", "alice_c007_fish_de")
PAKET = "alice_c007_hoertest_de"
PDIR = os.path.join(LESER, "gpu_overlay", PAKET)
AUS = os.path.join(LESER, "tools", "alice_hoertest")
ARCHIV = os.path.join(LESER, "stimmen_archiv")
ERZ_REGIE = os.path.join(LESER, "tools", "fish_test", "de_erz_regie")
ZEILEN_JE_FIGUR = 4
KANDIDATEN = {   # Vorauswahl nach Geschlecht + Stimmlage; Hutmacher (tiefer) und Maerzhase (hoch) bewusst auseinander
    "Alice": ["k_03", "k_04", "k_05", "w_hoch_01", "w_hoch_02", "w_hoch_03", "w_hoch_04", "w_hoch_05"],
    "Hatter": ["m_mittel_02", "m_mittel_05", "m_mittel_08", "m_mittel_11", "m_mittel_14", "m_mittel_17"],
    "March Hare": ["m_hoch_01", "m_hoch_02", "m_hoch_03", "m_hoch_04", "m_hoch_05", "m_hoch_06"],
    "Dormouse": ["m_tief_01", "m_tief_02", "m_tief_03", "m_tief_04", "m_tief_05", "m_tief_06", "m_tief_07"],
    "Erzaehler": ["w_tief_01", "w_tief_02", "w_tief_03", "w_tief_04", "w_mittel_02", "w_mittel_07",
                  "m_tief_04", "m_mittel_08"],
}
FIG_DE = {"Alice": "Alice", "Hatter": "Hutmacher", "March Hare": "Märzhase", "Dormouse": "Haselmaus",
          "Erzaehler": "Erzähler"}


def _dauer(p):
    with wave.open(p) as w:
        return w.getnframes() / w.getframerate()


def _kandidaten(zusatz):
    k = {f: list(v) for f, v in KANDIDATEN.items()}
    for teil in (zusatz or "").split(";"):
        if "=" in teil:
            f, v = teil.split("=", 1)
            k.setdefault(f.strip(), [])
            k[f.strip()] += [x.strip() for x in v.split(",") if x.strip() and x.strip() not in k[f.strip()]]
    for f, liste in k.items():
        for s in liste:
            if not os.path.exists(os.path.join(ARCHIV, s, "klon_de.wav")):
                sys.exit(f"{f}: Stimme {s} hat kein stimmen_archiv/{s}/klon_de.wav")
    return k


def zeilen():
    """je Figur die ZEILEN_JE_FIGUR laengsten Quellzeilen (3-15 s) aus dem alten Paket."""
    jobs = json.load(open(os.path.join(ALT, "jobs.json"), encoding="utf-8"))["jobs"]
    je = {}
    for j in jobs:
        p = os.path.join(ALT, "src", j["id"] + ".wav")
        d = _dauer(p)
        if 3 <= d <= 15:
            je.setdefault(j["figur"], []).append((d, j))
    return {f: [j for _, j in sorted(v, key=lambda x: -x[0])[:ZEILEN_JE_FIGUR]] for f, v in je.items()}


def bauen(kand):
    z = zeilen()
    if os.path.exists(PDIR):
        shutil.rmtree(PDIR)
    os.makedirs(os.path.join(PDIR, "src"))
    os.makedirs(os.path.join(PDIR, "ref"))
    jobs = []
    for fig, liste in z.items():
        for s in kand.get(fig, []):
            shutil.copyfile(os.path.join(ARCHIV, s, "klon_de.wav"), os.path.join(PDIR, "ref", s + ".wav"))
            for j in liste:
                jid = f"{s}__{j['id']}"
                shutil.copyfile(os.path.join(ALT, "src", j["id"] + ".wav"), os.path.join(PDIR, "src", jid + ".wav"))
                jobs.append({"id": jid, "tag": j["id"], "figur": fig, "stimme": s, "text": j["text"], "lang": "de"})
    with open(os.path.join(PDIR, "jobs.json"), "w", encoding="utf-8") as f:
        json.dump({"werk": "alice-s-adventures-in-wonderland", "lang": "de", "jobs": jobs}, f, ensure_ascii=False, indent=1)
    os.makedirs(AUS, exist_ok=True)
    with open(os.path.join(AUS, "zeilen.json"), "w", encoding="utf-8") as f:
        json.dump({fig: [{"id": j["id"], "text": j["text"]} for j in v] for fig, v in z.items()}, f, ensure_ascii=False, indent=1)
    # bisherige Zielstimme (Gemini) aus dem alten Lauf
    d = os.path.join(AUS, "de", "bisher")
    os.makedirs(d, exist_ok=True)
    zz = zipfile.ZipFile(os.path.join(ALT, "ergebnis.zip"))
    for v in z.values():
        for j in v:
            n = f"vc/{j['id']}.wav"
            if n in zz.namelist():
                open(os.path.join(d, j["id"] + ".wav"), "wb").write(zz.read(n))
            shutil.copyfile(os.path.join(ALT, "src", j["id"] + ".wav"), os.path.join(d, j["id"] + "_quelle.wav"))
    sek = sum(_dauer(os.path.join(PDIR, "src", j["id"] + ".wav")) for j in jobs)
    print(f"[bauen] {len(jobs)} VC-Jobs ({sek / 60:.1f} min Audio) -> gpu_overlay/{PAKET}; Zeilen je Figur: "
          + ", ".join(f"{f} {len(v)}" for f, v in z.items()))


def vc():
    t0 = time.time()
    r = subprocess.run(["py", "-3.11", "-m", "modal", "run", "gpu_overlay/overlay_modal.py", "--paket", PAKET], cwd=LESER)
    wall = time.time() - t0
    z = zipfile.ZipFile(os.path.join(PDIR, "ergebnis.zip"))
    d = os.path.join(AUS, "de", "vc")
    os.makedirs(d, exist_ok=True)
    n = 0
    for name in z.namelist():
        if name.startswith("vc/") and name.endswith(".wav"):
            open(os.path.join(d, os.path.basename(name)), "wb").write(z.read(name))
            n += 1
    ber = z.read("bericht.txt").decode("utf-8") if "bericht.txt" in z.namelist() else ""
    from config import config
    gpu = next((g for g in ("L40S", "A10G", "L4") if g in ber), "L4")
    usd = wall / 3600 * float(getattr(config, f"MODAL_{gpu}_USD_H", 1.10))   # Wall inkl. Kaltstart = obere Schaetzung
    _kosten({"art": "vc", "clips": n, "wall_s": round(wall, 1), "usd": round(usd, 4), "bericht": ber.splitlines()[:1]})
    print(f"[vc] {n} Clips, rc {r.returncode}, ~{usd:.3f} $\n{ber}")


def erzaehler_text():
    """zusammenhaengende Erzaehlerpassage aus Kap. 7 (~450 Zeichen) + Turn-Nummern fuer die Bisher-Probe."""
    sys.path.insert(0, os.path.join(LESER, "tools", "fish_test"))
    os.environ["ERZ_ALLE"] = "1"
    import fish_einzeln as E
    tr = E.turns_mit_absatz("de")
    best = None
    for i in range(len(tr)):
        if tr[i]["fig"] != "Erzaehler" or not (tr[i]["absatz"] and tr[i]["t"][:1].isupper()):
            continue                                   # nur ab Absatzbeginn (kein Satzfragment)
        n, text = [], ""
        for k in range(i, len(tr)):
            if tr[k]["fig"] != "Erzaehler" or len(text) > 450:
                break
            n.append(k + 1)
            text = (text + " " + tr[k]["t"]).strip()
        if len(text) >= 350 and (best is None or abs(len(text) - 450) < abs(len(best[0]) - 450)):
            best = (text, n)
    return best


def erzaehler(kand):
    from pipeline import fish_motor as F
    text, turns = erzaehler_text()
    d = os.path.join(AUS, "de", "erzaehler")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(AUS, "erzaehler_text.json"), "w", encoding="utf-8") as f:
        json.dump({"text": text, "turns": turns}, f, ensure_ascii=False, indent=1)
    # bisher: grossmutter_a aus dem alten Lauf (de_erz_regie/t<nr>.wav), Pausen wie fish_einzeln
    with wave.open(os.path.join(d, "bisher.wav"), "wb") as out:
        out.setnchannels(1), out.setsampwidth(2), out.setframerate(24000)
        for i, nr in enumerate(turns):
            if i:
                out.writeframes(b"\x00\x00" * int(24000 * 0.6))
            with wave.open(os.path.join(ERZ_REGIE, f"t{nr:04d}.wav")) as w:
                out.writeframes(w.readframes(w.getnframes()))
    usd = 0.0
    for s in kand["Erzaehler"]:
        p = os.path.join(d, s + ".wav")
        if os.path.exists(p):
            continue
        rid = F.fish_id(s, "de", anlegen=True)
        wav, info = F.tts_einfach(text, rid, sr=24000)
        open(p, "wb").write(wav)
        usd += F.kosten_usd(text)
        print(f"  + Erzaehler {s} ({_dauer(p):.1f} s)", flush=True)
    _kosten({"art": "erzaehler_fish_api", "clips": len(kand["Erzaehler"]), "zeichen": len(text), "usd": round(usd, 4)})
    print(f"[erzaehler] {len(text)} Zeichen x {len(kand['Erzaehler'])} Stimmen, ~{usd:.3f} $")


def _kosten(z):
    os.makedirs(AUS, exist_ok=True)
    z["zeit"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(os.path.join(AUS, "kosten_log.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(z, ensure_ascii=False) + "\n")


def seite(kand):
    z = json.load(open(os.path.join(AUS, "zeilen.json"), encoding="utf-8"))
    et = json.load(open(os.path.join(AUS, "erzaehler_text.json"), encoding="utf-8")) \
        if os.path.exists(os.path.join(AUS, "erzaehler_text.json")) else {"text": ""}
    steck = {}
    for liste in kand.values():
        for s in liste:
            p = os.path.join(ARCHIV, s, "steckbrief.json")
            if os.path.exists(p):
                st = json.load(open(p, encoding="utf-8"))
                steck[s] = {"f0": st.get("grundton_hz"), "lage": st.get("stimmlage")}
    figuren = []
    for fig in ["Erzaehler", "Alice", "Hatter", "March Hare", "Dormouse"]:
        if fig == "Erzaehler":
            figuren.append({"fig": fig, "de": FIG_DE[fig], "zeilen": [{"id": "erz", "text": et["text"]}],
                            "reihen": [{"s": "bisher", "info": "grossmutter_a (Gemini-Klon, alt)",
                                        "audio": {"erz": "de/erzaehler/bisher.wav"}}]
                            + [{"s": s, "info": f"F0 {steck.get(s, {}).get('f0')} Hz",
                                "audio": {"erz": f"de/erzaehler/{s}.wav"}} for s in kand[fig]]})
            continue
        zl = z.get(fig, [])
        reihen = [{"s": "quelle", "info": "Fish-Erzähler mit Regie (VC-Eingang)",
                   "audio": {j["id"]: f"de/bisher/{j['id']}_quelle.wav" for j in zl}},
                  {"s": "bisher", "info": "bisherige Gemini-Zielstimme",
                   "audio": {j["id"]: f"de/bisher/{j['id']}.wav" for j in zl}}]
        reihen += [{"s": s, "info": f"F0 {steck.get(s, {}).get('f0')} Hz",
                    "audio": {j["id"]: f"de/vc/{s}__{j['id']}.wav" for j in zl}} for s in kand.get(fig, [])]
        figuren.append({"fig": fig, "de": FIG_DE[fig], "zeilen": zl, "reihen": reihen})
    html = SEITE.replace("/*DATEN*/[]", json.dumps(figuren, ensure_ascii=False))
    with open(os.path.join(AUS, "hoertest.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[seite] {os.path.join(AUS, 'hoertest.html')}")


def kapitel(auswahl_pfad):
    """Kap. 7 komplett mit der Hoertest-Besetzung (wie start_alice_fish_vc.bat + vc_montage.py, eigener Ordner):
    1) Fish API: ALLE Beitraege in der Erzaehlerstimme (Figuren mit Regie-Tag wie fish_einzeln ERZ_ALLE)
    2) Chatterbox-VC (Modal) der Figurenbeitraege in die gewaehlten Zielstimmen
    3) Montage (Pausen wie fish_einzeln) -> tools/alice_hoertest/de/fish_erz_vc_qwen_c007_de.wav
    Vergleich: tools/fish_test/de/fish_erz_vc_c007_de.wav (grossmutter_a + Gemini-Figuren)."""
    import concurrent.futures as cf
    from pipeline import fish_motor as F
    sys.path.insert(0, os.path.join(LESER, "tools", "fish_test"))
    os.environ["ERZ_ALLE"] = "1"
    import fish_einzeln as E
    wahl = json.load(open(auswahl_pfad, encoding="utf-8"))
    for f, s in wahl.items():
        if not os.path.exists(os.path.join(ARCHIV, s, "klon_de.wav")):
            sys.exit(f"{f}: {s} ohne klon_de.wav")
    tr = E.turns_mit_absatz("de")
    kd = os.path.join(AUS, "de", "kapitel")
    erz = os.path.join(kd, "erz")
    os.makedirs(erz, exist_ok=True)
    # 1) Erzaehler-Rendering (Resume ueber vorhandene WAVs)
    rid = F.fish_id(wahl["Erzaehler"], "de", anlegen=True)
    offen = [(n, x) for n, x in enumerate(tr, 1) if not os.path.exists(os.path.join(erz, f"t{n:04d}.wav"))]
    usd = 0.0

    def eins(n, x):
        text = x["t"] if x["fig"] == "Erzaehler" else (E.REGIE.get(x["fig"], "") + " " + x["t"]).strip()
        wav, _ = F.tts_einfach(text, rid, sr=24000)
        open(os.path.join(erz, f"t{n:04d}.wav"), "wb").write(wav)
        return F.kosten_usd(text)
    print(f"[kapitel] Erzaehler {wahl['Erzaehler']}: {len(tr)} Beitraege, offen {len(offen)}", flush=True)
    fehler = []
    with cf.ThreadPoolExecutor(3) as ex:
        futs = {ex.submit(eins, n, x): n for n, x in offen}
        for i, fu in enumerate(cf.as_completed(futs), 1):
            try:
                usd += fu.result()
            except Exception as e:
                fehler.append(f"t{futs[fu]:04d}: {e}")
            if i % 25 == 0:
                print(f"  {i}/{len(offen)}", flush=True)
    _kosten({"art": "kapitel_erzaehler_fish_api", "stimme": wahl["Erzaehler"], "clips": len(offen), "usd": round(usd, 4)})
    if fehler:
        sys.exit("Fish-Fehler (erneut starten = Resume):\n" + "\n".join(fehler[:10]))
    # 2) VC-Paket der Figurenbeitraege
    paket = "alice_c007_qwen_de"
    pd = os.path.join(LESER, "gpu_overlay", paket)
    if os.path.exists(pd):
        shutil.rmtree(pd)
    os.makedirs(os.path.join(pd, "src"))
    os.makedirs(os.path.join(pd, "ref"))
    jobs = []
    for n, x in enumerate(tr, 1):
        if x["fig"] == "Erzaehler":
            continue
        s = wahl.get(x["fig"])
        if not s:
            print(f"  ! {x['fig']} ohne Besetzung -> bleibt Erzaehlerstimme (t{n:04d})")
            continue
        jid = f"t{n:04d}"
        shutil.copyfile(os.path.join(erz, jid + ".wav"), os.path.join(pd, "src", jid + ".wav"))
        shutil.copyfile(os.path.join(ARCHIV, s, "klon_de.wav"), os.path.join(pd, "ref", s + ".wav"))
        jobs.append({"id": jid, "tag": jid, "figur": x["fig"], "stimme": s, "text": x["t"], "lang": "de"})
    with open(os.path.join(pd, "jobs.json"), "w", encoding="utf-8") as f:
        json.dump({"werk": "alice-s-adventures-in-wonderland", "lang": "de", "jobs": jobs}, f, ensure_ascii=False, indent=1)
    print(f"[kapitel] VC {len(jobs)} Figurenbeitraege -> Modal", flush=True)
    t0 = time.time()
    r = subprocess.run(["py", "-3.11", "-m", "modal", "run", "gpu_overlay/overlay_modal.py", "--paket", paket], cwd=LESER)
    wall = time.time() - t0
    z = zipfile.ZipFile(os.path.join(pd, "ergebnis.zip"))
    ber = z.read("bericht.txt").decode("utf-8") if "bericht.txt" in z.namelist() else ""
    from config import config
    gpu = next((g for g in ("L40S", "A10G", "L4") if g in ber), "L4")
    _kosten({"art": "kapitel_vc", "clips": len(jobs), "wall_s": round(wall, 1), "rc": r.returncode,
             "usd": round(wall / 3600 * float(getattr(config, f"MODAL_{gpu}_USD_H", 1.10)), 4), "bericht": ber.splitlines()[:1]})
    vc = {os.path.splitext(os.path.basename(nm))[0]: z.read(nm) for nm in z.namelist()
          if nm.startswith("vc/") and nm.endswith(".wav")}

    # 3) Montage
    def pcm(b):
        import numpy as np
        with wave.open(io.BytesIO(b)) as w:
            sr, a = w.getframerate(), np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32)
        if sr != 24000:
            a = np.interp(np.arange(0, len(a), sr / 24000), np.arange(len(a)), a)
        return a.astype(np.int16).tobytes()
    ziel = os.path.join(AUS, "de", "fish_erz_vc_qwen_c007_de.wav")
    ohne_vc = 0
    with wave.open(ziel, "wb") as out:
        out.setnchannels(1), out.setsampwidth(2), out.setframerate(24000)
        for n, x in enumerate(tr, 1):
            if n > 1:
                out.writeframes(b"\x00\x00" * int(24000 * (E.PAUSE_ABSATZ if x["absatz"] else E.PAUSE_TURN)))
            jid = f"t{n:04d}"
            if x["fig"] != "Erzaehler" and jid in vc:
                out.writeframes(pcm(vc[jid]))
            else:
                ohne_vc += x["fig"] != "Erzaehler"
                out.writeframes(pcm(open(os.path.join(erz, jid + ".wav"), "rb").read()))
    with open(os.path.join(kd, "besetzung.json"), "w", encoding="utf-8") as f:
        json.dump(wahl, f, ensure_ascii=False, indent=1)
    print(f"[kapitel] {ziel} ({_dauer(ziel) / 60:.1f} min), Figurenbeitraege ohne VC: {ohne_vc}\n{ber}")


SEITE = r"""<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Alice Hörtest-Casting</title><style>
:root{--bg:#faf9f6;--fg:#1f1d1a;--mut:#6b665e;--line:#e3dfd6;--card:#fff;--acc:#2f5d50}
@media (prefers-color-scheme:dark){:root{--bg:#191816;--fg:#ece8e1;--mut:#9c968c;--line:#34312c;--card:#22201d;--acc:#7fb8a5}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}
header{position:sticky;top:0;z-index:2;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 16px;display:flex;gap:12px;flex-wrap:wrap;align-items:center}
h1{font-size:17px;margin:0;flex:1}h2{font-size:16px;margin:0 0 6px}nav a{color:var(--acc);margin-right:10px;text-decoration:none}
button{font:inherit;padding:5px 10px;border-radius:6px;border:1px solid var(--acc);background:var(--acc);color:var(--bg)}
main{padding:12px 16px;display:grid;gap:16px}section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;overflow-x:auto}
table{border-collapse:collapse;width:100%;min-width:640px}td,th{border-top:1px solid var(--line);padding:6px;vertical-align:top;text-align:left}
th{font-weight:500;color:var(--mut);font-size:12px;max-width:260px}audio{height:30px;width:200px}tr.gew{background:color-mix(in srgb,var(--acc) 12%,transparent)}
.mut{color:var(--mut);font-size:12px}.s{font-family:ui-monospace,monospace;font-weight:600}.wahl{color:var(--acc);font-weight:600}
</style></head><body><header><h1>Alice Kap. 7 – Hörtest-Casting (DE)</h1><nav id="nav"></nav><span class="mut" id="n"></span>
<button id="x">casting_auswahl.json exportieren</button></header><main id="m"></main><script>
const D=/*DATEN*/[];let W={};try{W=JSON.parse(localStorage.getItem("alice_casting")||"{}")}catch(e){}
const $=i=>document.getElementById(i);function sp(){try{localStorage.setItem("alice_casting",JSON.stringify(W))}catch(e){}}
function r(){$("nav").innerHTML=D.map(f=>`<a href="#${f.fig.replace(/ /g,'_')}">${f.de}${W[f.fig]?' ✓':''}</a>`).join("");
$("n").textContent=Object.keys(W).length+"/"+D.length+" besetzt";
$("m").innerHTML=D.map(f=>`<section id="${f.fig.replace(/ /g,'_')}"><h2>${f.de} <span class="mut">(${f.fig})</span> ${W[f.fig]?'<span class="wahl">→ '+W[f.fig]+'</span>':''}</h2>
<table><tr><th>Stimme</th>${f.zeilen.map(z=>`<th>${z.text}</th>`).join("")}</tr>
${f.reihen.map(x=>`<tr class="${W[f.fig]==x.s?'gew':''}"><td>${["quelle","bisher"].includes(x.s)?`<span class="s">${x.s}</span>`:`<label><input type="radio" name="${f.fig}" value="${x.s}" ${W[f.fig]==x.s?'checked':''}> <span class="s">${x.s}</span></label>`}<div class="mut">${x.info}</div></td>
${f.zeilen.map(z=>`<td>${x.audio[z.id]?`<audio controls preload="none" src="${x.audio[z.id]}"></audio>`:''}</td>`).join("")}</tr>`).join("")}</table></section>`).join("")}
document.addEventListener("change",e=>{if(e.target.type=="radio"){W[e.target.name]=e.target.value;sp();r()}});
$("x").onclick=()=>{const b=new Blob([JSON.stringify(W,null,1)],{type:"application/json"});const l=document.createElement("a");l.href=URL.createObjectURL(b);l.download="casting_auswahl.json";l.click()};
r();</script></body></html>"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("befehl", choices=["bauen", "vc", "erzaehler", "seite", "alle", "kapitel"])
    ap.add_argument("auswahl", nargs="?", default="", help="kapitel: casting_auswahl.json")
    ap.add_argument("--kandidaten", default="", help='zusaetzlich, z. B. "Hatter=m_mittel_03;Alice=k_01"')
    a = ap.parse_args()
    if a.befehl == "kapitel":
        sys.exit(kapitel(a.auswahl))
    k = _kandidaten(a.kandidaten)
    if a.befehl in ("bauen", "alle"):
        bauen(k)
    if a.befehl in ("vc", "alle"):
        vc()
    if a.befehl in ("erzaehler", "alle"):
        erzaehler(k)
    if a.befehl in ("seite", "alle"):
        seite(k)
