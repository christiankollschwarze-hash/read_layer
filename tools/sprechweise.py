"""READ LAYER - Sprechweise je Figur/Kapitel (22.10.2026, AP4 Spiegelschwestern).

Zwei Figuren mit EINER Grundstimme (Zwillinge) unterscheiden sich nur ueber die Sprechweise. Umsetzung nach dem Vertonen
mit Praat "Change gender" (tools/overlay_korrektur.korrigieren): tonhoehe_ht (F0-Median) + formant_faktor; Dauer bleibt,
Wortzeiten (520) bleiben gueltig. Grenzen wie Abstandsregel: Formant 0,94-1,10, Tonhoehe +-2 HT.

casting.json plan.sprechweise:
  {"<Figur>": {"standard": {"tonhoehe_ht": -1.0, "formant_faktor": 0.98},
               "kapitel": {"c007": {"von": {...}, "bis": {...}},   # gleitend ueber das Kapitel (Satzposition)
                           "c008": {...}}}}                          # fest fuer das Kapitel
Wirkt an zwei Stellen:
  1. Erzaehl-Audio: Kapitel, deren Ich-Erzaehler (plan.erzaehler_je_kapitel) eine Sprechweise hat -> dieses Skript.
  2. Rede der Figur in anderen Kapiteln (Hoerspiel-Overlay): tools/overlay_korrektur.anwenden nutzt werte().

Aufruf:  py -3.11 tools/sprechweise.py <werk> [de] [--liste]
  Originale: fassungen/<lg>/audio_vor_sprechweise/ (Quelle bei jedem Lauf -> wiederholbar), Protokoll work/sprechweise_<lg>.json.
"""
import glob, json, os, shutil, sys

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HIER)
sys.path.insert(0, os.path.join(HIER, "tools"))


def _mix(a, b, t):
    return {k: round(a.get(k, d) + (b.get(k, d) - a.get(k, d)) * t, 3)
            for k, d in (("tonhoehe_ht", 0.0), ("formant_faktor", 1.0))}


def werte(cast, figur, kap, anteil=0.0):
    """Sprechweise einer Figur in einem Kapitel (anteil 0..1 = Position im Kapitel) oder None."""
    sw = ((cast.get("plan") or {}).get("sprechweise") or {}).get(figur)
    if not sw:
        return None
    k = (sw.get("kapitel") or {}).get(kap) or sw.get("standard")
    if not k:
        return None
    if "von" in k:
        return _mix(k["von"], k.get("bis", k["von"]), max(0.0, min(1.0, anteil)))
    return _mix(k, k, 0)


def kapitel_anteile(werk_dir):
    """tag -> Position 0..1 im Kapitel (nach 400_regie)."""
    c = json.load(open(os.path.join(werk_dir, "work", "400_regie.json"), encoding="utf-8"))["content"]
    je = {}
    for t in c:
        je.setdefault(t[:4], []).append(t)
    return {t: (i / max(1, len(ts) - 1)) for ts in je.values() for i, t in enumerate(ts)}


def main(werk, lg="de", nur_liste=False):
    from config import config
    wd = config.book_dir(werk)
    cast = json.load(open(os.path.join(wd, "work", "casting.json"), encoding="utf-8"))
    erz = (cast.get("plan") or {}).get("erzaehler_je_kapitel") or {}
    if lg not in (cast.get("hoerspiel_sprachen") or [config.werk_sprachen(werk)[0]]):
        print(f"[sprechweise] {lg}: keine Hoerspiel-Sprache -> nichts zu tun")
        return
    if not nur_liste:
        import soundfile as sf
        from overlay_korrektur import korrigieren
    anteil = kapitel_anteile(wd)
    audio = os.path.join(wd, "fassungen", lg, "audio")
    vor = os.path.join(wd, "fassungen", lg, "audio_vor_sprechweise")
    proto, n = {}, 0
    for kap, fig in sorted(erz.items()):
        if not werte(cast, fig, kap, 0):
            continue
        wavs = sorted(glob.glob(os.path.join(audio, f"{kap}_*.wav")))
        w0, w1 = werte(cast, fig, kap, 0), werte(cast, fig, kap, 1)
        print(f"[sprechweise] {kap} {fig}: {len(wavs)} Saetze, {w0}" + ("" if w0 == w1 else f" -> {w1}"))
        proto[kap] = {"figur": fig, "von": w0, "bis": w1, "saetze": len(wavs)}
        if nur_liste:
            continue
        os.makedirs(vor, exist_ok=True)
        for p in wavs:
            name = os.path.basename(p)
            q = os.path.join(vor, name)
            if not os.path.exists(q):
                shutil.copy2(p, q)                 # Original einmalig sichern, danach immer von dort rechnen
            w = werte(cast, fig, kap, anteil.get(name[:-4], 0))
            x, sr = sf.read(q, dtype="float32")
            sf.write(p, korrigieren(x, sr, w["formant_faktor"], w["tonhoehe_ht"]), sr, subtype="PCM_16")
            n += 1
    if not nur_liste:
        json.dump(proto, open(os.path.join(wd, "work", f"sprechweise_{lg}.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"[sprechweise] {n} Saetze angepasst; Originale in {vor}")


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    main(a[0], a[1] if len(a) > 1 else "de", "--liste" in sys.argv)
