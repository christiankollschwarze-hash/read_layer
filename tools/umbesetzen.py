"""READ LAYER - Figur umbesetzen nach der Hoerspiel-Pruefung (Urteil "umbesetzen").

Aufruf:
  py -3.11 tools/umbesetzen.py <werk> <lg> "<Figur>"                  Kandidaten designen + gegen den Werk-Erzaehler messen
        [--richtung hoeher,groesser] [--versuche 2] [--notiz "..."]
  py -3.11 tools/umbesetzen.py <werk> <lg> "<Figur>" --waehlen <stimme>   Kandidat besetzen (auch per Cockpit-Knopf)
  (Windows: start_umbesetzen.bat <werk> <lg> "<Figur>")

Kandidaten: je Richtung eine neue Stimme (Gemini Voice Design, mit Abgrenzung zum Ensemble):
  hoeher    hoerbar hoeher und heller als der Erzaehler (kleinerer Vokaltrakt)
  groesser  hoerbar groesser und dunkler (tiefer, groesserer Resonanzraum)
Gemessen wird wie in pipeline/trennung.py: Zielstimme (muster_<lg> + hoerprobe) gegen den Erzaehler DES WERKS
(fassungen/<lg>/audio). Liegt ein Kandidat unter D_ziel, wird er mit deutlicherer Regie-Notiz neu designt
(bis --versuche). Ergebnis in casting.json ensemble[].umbesetzung[lg] -> Cockpit "Hoerspiel-Pruefung" (CK-Tor).
Nach der Wahl: Overlay nur fuer diese Figur (start_overlay_teil.bat) -> start_trennung_messen.bat.
"""
import json, os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from config import config  # noqa
from pipeline import voice_registry as vr, s410_casting as s57, trennung  # noqa

BESCHREIBUNG = {
    "hoeher": ("{wer} with a light, bright, warm baritone that sits clearly HIGHER than a deep bass voice; "
               "a smaller, lighter, more forward resonance. {temperament}"),
    "groesser": ("{wer} with a very deep, dark, booming bass voice and a large chest resonance; a big, heavy-set man "
                 "who sounds clearly BIGGER and LOWER than an ordinary deep voice. {temperament}"),
}
NOTIZ = {
    "hoeher": ("The narrator of this audiobook is a deep, resonant, rugged male voice (about {f0:.0f} Hz). "
               "This character must be instantly distinguishable from him: audibly higher in pitch (around {ziel:.0f} Hz) "
               "and brighter, lighter timbre. Keep it natural, warm and adult - no falsetto, no caricature."),
    "groesser": ("The narrator of this audiobook is a deep, resonant, rugged male voice (about {f0:.0f} Hz). "
                 "This character must be instantly distinguishable from him: audibly lower in pitch (around {ziel:.0f} Hz) "
                 "and a darker, bigger, fuller body. Keep it natural and adult - no growl, no caricature."),
}
STAERKER = {"hoeher": " The previous attempt was still too close to the narrator: go clearly higher and brighter.",
            "groesser": " The previous attempt was still too close to the narrator: go clearly deeper and darker."}
RICHTUNG_R = {"hoeher": +1, "groesser": -1}


def _opt(n, d=None):
    return sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d


def _laden(book):
    cp = s57.casting_pfad(book)
    return cp, json.load(open(cp, encoding="utf-8"))


def _speichern(cp, c):
    tmp = cp + ".tmp"
    json.dump(c, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, cp)


def kandidaten(book, lg, figur_name, richtungen, versuche=2, notiz=""):
    cp, c = _laden(book)
    data, _ = s57._quelle_laden(book)
    eintrag = next(e for e in c["plan"]["ensemble"] if e["figur"] == figur_name)
    erz = c["plan"]["erzaehler"]["stimme"]
    werk = os.path.dirname(os.path.dirname(cp))
    # 22.10.2026: Ich-Erzaehler je Kapitel -> gemessen gegen den Erzaehler, in dessen Kapiteln die Figur am meisten spricht
    ekap = c["plan"].get("erzaehler_je_kapitel") or {}
    kapitel = None
    if ekap:
        sp = json.load(open(os.path.join(werk, "work", "sprecher.json"), encoding="utf-8"))
        zaehl = {}
        for tid, e in sp.items():
            if any(x.get("s") == figur_name for x in e.get(lg) or []) and ekap.get(tid[:4]):
                zaehl[ekap[tid[:4]]] = zaehl.get(ekap[tid[:4]], 0) + 1
        if zaehl:
            haupt = max(zaehl, key=zaehl.get)
            kapitel = [k for k, f in ekap.items() if f == haupt]
            print(f"  Erzaehler fuer die Messung: {haupt} (Kapitel {', '.join(kapitel)}; Rede je Erzaehler {zaehl})")
    ep = trennung.erzaehler_profil(werk, lg, erz, kapitel=kapitel)
    if not ep.get("f0_hz"):
        sys.exit("Erzaehler-Profil nicht messbar (parselmouth installiert? py -3.11 -m pip install praat-parselmouth soundfile)")
    R = trennung.regel()
    reg = vr.laden()
    ensemble = []
    for e in [c["plan"]["erzaehler"]] + c["plan"]["ensemble"]:
        if e.get("stimme") and e["figur"] != figur_name and e["stimme"] in reg:
            s = reg[e["stimme"]]
            ensemble.append({"figur": e["figur"], "name": e["stimme"], "merkmale": s.get("merkmale"),
                             "grundton_hz": s.get("grundton_hz"),
                             "beschreibung": (e.get("steckbrief") or {}).get("stimm_beschreibung_en") or s.get("beschreibung", "")})
    sb = eintrag["steckbrief"]
    m = vr.normalisieren(sb.get("merkmale"))
    wer = {"w": "A woman", "m": "A man"}.get(m["geschlecht"], "A person") + {
        "jung": " in his early twenties", "mittel": " in his forties", "alt": " around seventy"}.get(m["alter"], "")
    if m["geschlecht"] == "w":
        wer = wer.replace(" his ", " her ")
    temp = ", ".join(vr._EN_TEMP.get(t, t) for t in m["temperament"])
    temperament = (f"Temperament: {temp}. " if temp else "") + (sb.get("haltung") and f"Attitude: {sb['haltung']}. " or "")
    muster = s57._muster(data, sb)
    erg = []
    for richtung in richtungen:
        r = RICHTUNG_R[richtung]
        ziel_f0 = ep["f0_hz"] * 2 ** (r * 6 / 12)          # ~6 HT Abstand: D(F0) ~4,2 allein
        bester = None
        for v in range(versuche):
            figur = dict(sb, merkmale=dict(m, tonlage="mittel" if r > 0 else "tief"))
            figur["stimm_beschreibung_en"] = BESCHREIBUNG[richtung].format(wer=wer, temperament=temperament)
            figur["ck_notiz"] = NOTIZ[richtung].format(f0=ep["f0_hz"], ziel=ziel_f0) + (STAERKER[richtung] if v else "") \
                + (f" {notiz}" if notiz else "")
            figur["ck_notiz"] = figur["ck_notiz"].strip().rstrip(".")
            name = vr.eindeutiger_name(f"{m['geschlecht']}_{m['alter']}_{richtung}_{figur_name.split()[-1]}", vr.laden())
            print(f"[umbesetzen] {figur_name}: design {name} ({richtung}, Versuch {v + 1}) ...")
            neu = vr.neu_designen(name, figur, ensemble, muster, book)
            p = trennung.stimm_profil(name, lg)
            t = trennung.abstand(p, ep, R)
            k = {"stimme": name, "id": neu["id"], "richtung": richtung, "versuch": v + 1, "D": t.get("D"),
                 "dF0_ht": t.get("dF0_ht"), "dVTL_proz": t.get("dVTL_proz"), "status": t.get("status"),
                 "f0_hz": p.get("f0_hz"), "vtl_cm": p.get("vtl_cm"),
                 "hoerprobe": f"stimmen_archiv/{name}/muster_{lg}.wav", "beschreibung": neu.get("beschreibung")}
            print(f"  F0 {p.get('f0_hz')} Hz, VTL {p.get('vtl_cm')} cm -> D {t.get('D')} ({t.get('status')})")
            if bester and (bester.get("D") or 0) >= (k.get("D") or 0):
                rg = vr.laden(); rg[name]["status"] = "abgelehnt"; rg[name]["einsatz"] = "Umbesetzung: schwaecher als Vorversuch"; vr.speichern(rg)
            else:
                if bester:
                    rg = vr.laden(); rg[bester["stimme"]]["status"] = "abgelehnt"; rg[bester["stimme"]]["einsatz"] = "Umbesetzung: Nachfolgeversuch besser"; vr.speichern(rg)
                bester = k
            if t.get("status") == "ok":
                break
        erg.append(bester)
    cp, c = _laden(book)     # frisch lesen (neu_designen schreibt nur das Register)
    eintrag = next(e for e in c["plan"]["ensemble"] if e["figur"] == figur_name)
    u = eintrag.setdefault("umbesetzung", {})
    alt = (u.get(lg) or {}).get("kandidaten", [])
    u[lg] = {"datum": time.strftime("%Y-%m-%d"), "alt": eintrag.get("stimme"),
             "erzaehler": {"stimme": erz, "f0_hz": ep.get("f0_hz"), "vtl_cm": ep.get("vtl_cm")},
             "D_ziel": R["D_ziel"], "kandidaten": alt + erg, "gewaehlt": None}
    _speichern(cp, c)
    print(f"[umbesetzen] {len(erg)} Kandidat(en) in casting.json -> Cockpit 'Hoerspiel-Pruefung' (CK waehlt)")
    for k in erg:
        print(f"  {k['stimme']:34} {k['richtung']:8} D {k['D']} ({k['status']})  Probe: {k['hoerprobe']}")


def waehlen(book, lg, figur_name, name):
    cp, c = _laden(book)
    eintrag = next(e for e in c["plan"]["ensemble"] if e["figur"] == figur_name)
    u = (eintrag.get("umbesetzung") or {}).get(lg) or {}
    k = next((x for x in u.get("kandidaten", []) if x["stimme"] == name), None)
    if not k:
        sys.exit(f"{name} ist kein Kandidat fuer {figur_name} [{lg}]")
    reg = vr.laden()
    alt = eintrag.get("stimme")
    eintrag.update({"stimme": name, "id": k["id"], "quelle": "neu", "grundton_hz": reg.get(name, {}).get("grundton_hz"),
                    "design_prompt": k.get("beschreibung")})
    t = {x: k.get(x) for x in ("D", "dF0_ht", "dVTL_proz", "status")}
    eintrag.setdefault("trennung", {})[lg] = dict(t, D_schwelle=trennung.regel()["D_schwelle"], D_ziel=trennung.regel()["D_ziel"])
    korr = eintrag.get("korrektur") or {}
    if korr and not any(x in korr for x in ("de", "en")):
        korr = {lg: korr}
    vorschlag = trennung.korrektur_vorschlag(k["status"], RICHTUNG_R[k["richtung"]])
    if vorschlag:
        korr[lg] = dict(vorschlag, quelle=f"Umbesetzung {time.strftime('%Y-%m-%d')}")
    else:
        korr.pop(lg, None)
    eintrag["korrektur"] = korr or None
    u["gewaehlt"] = name
    u["gewaehlt_am"] = time.strftime("%Y-%m-%d %H:%M")
    p = (eintrag.get("pruefung") or {}).get(lg)
    if p:
        p["entscheidung"] = {"aktion": "umbesetzen", "zeit": time.strftime("%Y-%m-%dT%H:%M:%S"), "notiz": f"neu: {name}"}
    _speichern(cp, c)
    for x in u.get("kandidaten", []):
        if x["stimme"] in reg:
            if x["stimme"] == name:
                reg[name]["status"] = "kandidat"
                reg[name]["einsatz"] = f"{book}: {figur_name} (ersetzt {alt})"
            elif reg[x["stimme"]].get("status") == "kandidat":
                reg[x["stimme"]]["status"] = "abgelehnt"
                reg[x["stimme"]]["einsatz"] = f"Umbesetzung {figur_name}: nicht gewaehlt"
    vr.speichern(reg)
    bp = os.path.join(os.path.dirname(os.path.dirname(cp)), "book.json")
    if os.path.exists(bp):
        bj = json.load(open(bp, encoding="utf-8"))
        if figur_name in (bj.get("besetzung") or {}):
            bj["besetzung"][figur_name].update({"stimme": name, "id": k["id"]})
            json.dump(bj, open(bp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[umbesetzen] {figur_name} [{lg}]: {alt} -> {name} (D {k['D']}, {k['status']}"
          f"{', Korrektur ' + str(vorschlag['formant_faktor']) if vorschlag else ''})")
    print(f"  Weiter: start_overlay_teil.bat {book} {lg} \"{figur_name}\"  ->  start_trennung_messen.bat {book} {lg}")


if __name__ == "__main__":
    a = [x for i, x in enumerate(sys.argv[1:], 1) if not x.startswith("--") and not sys.argv[i - 1].startswith("--")]
    if len(a) < 3:
        sys.exit(__doc__)
    book, lg, figur_name = a[0], a[1], a[2]
    if "--waehlen" in sys.argv:
        waehlen(book, lg, figur_name, _opt("--waehlen"))
    else:
        kandidaten(book, lg, figur_name, [r.strip() for r in _opt("--richtung", "hoeher,groesser").split(",")],
                   int(_opt("--versuche", 2)), _opt("--notiz", ""))
