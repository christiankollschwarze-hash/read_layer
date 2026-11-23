"""AP Tausch 520/530 (23.11.2026): Bestandswerke auf die neuen Stage-Nummern umstellen.
  alt 530 Audio-Pruefung -> neu 520, alt 520 Wortzeiten -> neu 530, alt 525 Wortbruecke -> neu 535.
Je Werkordner (authors/*/books/*/work, users/**/work):
  * work/520_* <-> 530_*, 525_* -> 535_* (ueber Zwischennamen), _fortschritt/<stage>.json, ckpt/<stage>/
  * Inhalte: Manifest-Feld "stage", Felder "stage"/"ruecksprung" in 5xx-7xx-Dateien und _fortschritt,
    Wortzeiten "einheit" ..._endfassung_530 -> _520, kosten.jsonl (stage, teil 525_* -> 535_*)
  * status.json: Stage-Schluessel, Ruecksprung, Metrik-Schluessel (gate_530 ...), Gruende/Hinweise,
    Protokoll-Stage; ausgabe_hash neu 530 (Schluessel 525 -> 535) und Signaturen werden nur dann neu
    berechnet, wenn der alte Wert zum alten Stand passte -> Freigaben bleiben gueltig.
  * 700_guard.json: Artefakt-Stages + ausgabe_hash (gleiche Regel), Status 700 je Scope nachgezogen.
Idempotent: Werke mit Marker work/_migration_520_530.json werden uebersprungen.
Aufruf: py -3.11 tools/migration_520_530.py --trocken | --los [--werk PFADTEIL]"""
import argparse, glob, json, os, re, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
from pipeline import manifest, status  # noqa: E402

M = {"520": "530", "530": "520", "525": "535"}
MARKER = "_migration_520_530.json"
RX_DATEI = re.compile(r"^(520|525|530)_(.+)$")
RX_TEXT = re.compile(r"(?<![\d./])(520|525|530)(?![\d/%])(?!\s*(?:Saetze|Sätze|Woerter|Wörter|Token|Anker|ms|min|s\b))")
RX_KEY = re.compile(r"(^|_)(520|525|530)(?=$|_)")
EIN_ALT, EIN_NEU = "sekunden_clip_relativ_endfassung_530", "sekunden_clip_relativ_endfassung_520"


def sw(s):
    return M.get(s, s) if isinstance(s, str) else s


def sw_text(o):
    if isinstance(o, str):
        return RX_TEXT.sub(lambda m: M[m.group(1)], o)
    if isinstance(o, list):
        return [sw_text(x) for x in o]
    if isinstance(o, dict):
        return {k: sw_text(v) for k, v in o.items()}
    return o


def sw_felder(o):
    """Felder stage/ruecksprung rekursiv tauschen; Rueckgabe Anzahl."""
    n = 0
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("stage", "ruecksprung") and isinstance(v, str) and v in M:
                o[k] = M[v]; n += 1
            else:
                n += sw_felder(v)
    elif isinstance(o, list):
        for x in o:
            n += sw_felder(x)
    return n


def lesen(p):
    with open(p, encoding="utf-8") as f:
        roh = f.read()
    zw = roh.split("\n", 2)
    ind = None
    if len(zw) > 1 and zw[1][:1] == " ":
        ind = len(zw[1]) - len(zw[1].lstrip(" "))
    return json.loads(roh), ind


def schreiben(p, d, ind):
    manifest.json_atomar(p, d, indent=ind)


def werkordner(nur=None):
    out = []
    for muster in ("authors/*/books/*/work", "users/**/work"):
        for w in glob.glob(os.path.join(BASE, muster), recursive=True):
            if os.path.isdir(w) and (nur is None or nur in w.replace("\\", "/")):
                out.append(w)
    return sorted(set(out))


def betroffen(w):
    if os.path.exists(os.path.join(w, MARKER)):
        return None
    dateien = [f for f in os.listdir(w) if RX_DATEI.match(f)]
    fort = [f for f in ("520.json", "525.json", "530.json") if os.path.exists(os.path.join(w, "_fortschritt", f))]
    ck = [f for f in ("520", "525", "530") if os.path.isdir(os.path.join(w, "ckpt", f))]
    st = []
    sp = os.path.join(w, "status.json")
    if os.path.exists(sp):
        d = json.load(open(sp, encoding="utf-8"))
        st = [s for s in M if s in d.get("stages", {})] + \
             (["protokoll"] if any(p.get("stage") in M for p in d.get("protokoll", [])) else [])
    ko = os.path.exists(os.path.join(w, "kosten.jsonl")) and \
        re.search(r'"(stage|teil)": "(520|525|530)', open(os.path.join(w, "kosten.jsonl"), encoding="utf-8").read())
    if not (dateien or fort or ck or st or ko):
        return None
    return {"dateien": dateien, "fortschritt": fort, "ckpt": ck, "status": st, "kosten": bool(ko)}


def tausch_namen(ordner, namen, neu_name, los, log):
    """namen -> neu_name(n) ueber Zwischennamen."""
    paare = [(n, neu_name(n)) for n in namen]
    ziele = {b for _, b in paare}
    quellen = {a for a, _ in paare}
    for a, b in paare:
        if os.path.exists(os.path.join(ordner, b)) and b not in quellen:
            raise RuntimeError(f"Ziel existiert schon: {os.path.join(ordner, b)}")
    for a, b in paare:
        log.append(f"  {os.path.relpath(os.path.join(ordner, a), BASE)} -> {b}")
    if not los:
        return
    for a, _ in paare:
        os.rename(os.path.join(ordner, a), os.path.join(ordner, "_tausch_" + a))
    for a, b in paare:
        os.rename(os.path.join(ordner, "_tausch_" + a), os.path.join(ordner, b))
    assert ziele


def hash530(w, metriken, br_key):
    sp = metriken.get("spuren") or {}
    aus = {}
    for lg, spuren in sp.items():
        for spur in spuren:
            n = f"530_wortzeiten_{lg}{'_hoerspiel' if spur == 'hoerspiel' else ''}.json"
            p = os.path.join(w, n)
            if not os.path.exists(p):
                return None
            aus[f"{lg}/{spur}"] = json.load(open(p, encoding="utf-8")).get("tags")
    p = os.path.join(w, "535_wortbruecke.json")
    if br_key and os.path.exists(p):
        aus[br_key] = {lg: x.get("tags") for lg, x in (json.load(open(p, encoding="utf-8")).get("je_ziel") or {}).items()}
    return manifest.hash_obj(aus)


def stage_eintrag(z, log, pre):
    """Ruecksprung, Metrik-Schluessel, Gruende/Hinweise tauschen; Signatur nachziehen wenn sie passte."""
    g = z.get("gate") or {}
    sig_ok = "signatur" in z and g and z["signatur"] == status._signatur(g.get("ergebnis"), g.get("gruende"),
                                                                       z.get("hinweise"), z.get("metriken"))
    if g:
        g["ruecksprung"] = sw(g.get("ruecksprung"))
        g["gruende"] = sw_text(g.get("gruende") or [])
    z["hinweise"] = sw_text(z.get("hinweise") or [])
    m = z.get("metriken") or {}
    z["metriken"] = {RX_KEY.sub(lambda x: x.group(1) + M[x.group(2)], k): v for k, v in m.items()}
    if sig_ok:
        z["signatur"] = status._signatur(g.get("ergebnis"), g.get("gruende"), z.get("hinweise"), z.get("metriken"))
    elif "signatur" in z:
        log.append(f"  {pre}: Signatur passte schon vorher nicht – unveraendert")
    for k, t in (z.get("teile") or {}).items():
        stage_eintrag(t, log, f"{pre}/{k}")


def migriere_status(w, los, log, hash_neu):
    sp = os.path.join(w, "status.json")
    if not os.path.exists(sp):
        return
    d, ind = lesen(sp)
    st = d.get("stages", {})
    alt = {s: st.pop(s) for s in list(st) if s in M}
    for s, z in alt.items():
        st[M[s]] = z
        stage_eintrag(z, log, f"status {s}->{M[s]}")
    # Reihenfolge wie STAGES
    d["stages"] = {k: st[k] for k in sorted(st, key=lambda x: status.STAGES.index(x) if x in status.STAGES else 999)}
    z = d["stages"].get("530")
    if z and (z.get("metriken") or {}).get("ausgabe_hash"):
        h = z["metriken"]["ausgabe_hash"]
        if h == hash530(w, z["metriken"], "525"):
            neu = hash530(w, z["metriken"], "535")
        elif h == hash530(w, z["metriken"], None):
            neu = h
        else:
            neu = None
        if neu is None:
            log.append("  status 530: ausgabe_hash passt nicht zum Dateistand (war schon veraltet) – unveraendert")
        elif neu != h:
            g = z.get("gate") or {}
            sig_ok = z.get("signatur") == status._signatur(g.get("ergebnis"), g.get("gruende"), z.get("hinweise"), z["metriken"])
            z["metriken"]["ausgabe_hash"] = neu
            if sig_ok:
                z["signatur"] = status._signatur(g.get("ergebnis"), g.get("gruende"), z.get("hinweise"), z["metriken"])
            log.append(f"  status 530: ausgabe_hash {h} -> {neu} (Freigabe bleibt gueltig)")
    for sc, h in hash_neu.items():               # 700 je Scope
        t = ((d["stages"].get("700") or {}).get("teile") or {}).get(sc)
        if t and (t.get("metriken") or {}).get("ausgabe_hash") == h[0]:
            g = t.get("gate") or {}
            sig_ok = t.get("signatur") == status._signatur(g.get("ergebnis"), g.get("gruende"), t.get("hinweise"), t["metriken"])
            t["metriken"]["ausgabe_hash"] = h[1]
            if sig_ok:
                t["signatur"] = status._signatur(g.get("ergebnis"), g.get("gruende"), t.get("hinweise"), t["metriken"])
            log.append(f"  status 700 {sc}: ausgabe_hash nachgezogen")
    n = 0
    for p in d.get("protokoll", []):
        if p.get("stage") in M:
            p["stage"] = M[p["stage"]]; n += 1
    if n:
        log.append(f"  status protokoll: {n} Eintraege")
    if los:
        schreiben(sp, d, ind)


def migriere_700(w, los, log):
    p = os.path.join(w, "700_guard.json")
    if not os.path.exists(p):
        return {}
    d, ind = lesen(p)
    out = {}
    for sc, x in (d.get("produkte") or {}).items():
        arts = x.get("artefakte") or []
        alt = manifest.hash_obj({f"{a['stage']}/{a['name']}": a["hash"] for a in arts})
        for a in arts:
            a["stage"], a["ruecksprung"] = sw(a.get("stage")), sw(a.get("ruecksprung"))
        x["ruecksprung"] = sw(x.get("ruecksprung"))
        x["gruende"], x["hinweise"] = sw_text(x.get("gruende") or []), sw_text(x.get("hinweise") or [])
        if x.get("ausgabe_hash") == alt:
            neu = manifest.hash_obj({f"{a['stage']}/{a['name']}": a["hash"] for a in arts})
            out[sc] = (alt, neu)
            x["ausgabe_hash"] = neu
        else:
            log.append(f"  700_guard {sc}: ausgabe_hash passte schon vorher nicht – unveraendert")
    log.append(f"  700_guard.json: {len(d.get('produkte') or {})} Scopes")
    if los:
        schreiben(p, d, ind)
    return out


def migriere(w, info, los):
    log = [os.path.relpath(w, BASE)]
    # 1) Dateien
    tausch_namen(w, info["dateien"], lambda n: M[n[:3]] + n[3:], los, log)
    if info["fortschritt"]:
        tausch_namen(os.path.join(w, "_fortschritt"), info["fortschritt"], lambda n: M[n[:3]] + n[3:], los, log)
    if info["ckpt"]:
        tausch_namen(os.path.join(w, "ckpt"), info["ckpt"], lambda n: M[n], los, log)
    # 2) Inhalte (nach dem Umbenennen: neue Namen; im Trockenlauf alte Namen lesen)
    def name(n):
        return n if los else next((a for a in info["dateien"] if M[a[:3]] + a[3:] == n), n)
    neue = [M[a[:3]] + a[3:] for a in info["dateien"]]
    for n in neue + [f for f in os.listdir(w) if re.match(r"^(5[4-9]\d|6\d\d|710)_.*\.json$", f)]:
        p = os.path.join(w, name(n))
        if not n.endswith(".json") or not os.path.exists(p):
            continue
        try:
            d, ind = lesen(p)
        except (ValueError, UnicodeDecodeError):
            continue
        k = sw_felder(d)
        if isinstance(d, dict) and d.get("einheit") == EIN_ALT:
            d["einheit"] = EIN_NEU; k += 1
        if k:
            log.append(f"  {n}: {k} Felder")
            if los:
                schreiben(p, d, ind)
    for f in ("520.json", "530.json", "535.json"):
        p = os.path.join(w, "_fortschritt", f if los else ({"520.json": "530.json", "530.json": "520.json",
                                                              "535.json": "525.json"}[f]))
        if os.path.exists(p):
            d, ind = lesen(p)
            if sw_felder(d) and los:
                schreiben(p, d, ind)
    # 3) kosten.jsonl
    kp = os.path.join(w, "kosten.jsonl")
    if info["kosten"]:
        zeilen, n = [], 0
        for z in open(kp, encoding="utf-8").read().splitlines():
            try:
                e = json.loads(z)
            except ValueError:
                zeilen.append(z); continue
            a = dict(e)
            e["stage"] = sw(e.get("stage"))
            if isinstance(e.get("teil"), str) and e["teil"][:3] in M:
                e["teil"] = M[e["teil"][:3]] + e["teil"][3:]
            n += e != a
            zeilen.append(json.dumps(e, ensure_ascii=False) if e != a else z)
        log.append(f"  kosten.jsonl: {n} Zeilen")
        if los:
            with open(kp + ".tmp", "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(zeilen) + "\n")
            os.replace(kp + ".tmp", kp)
    # 4) 700 + status
    if los:
        h7 = migriere_700(w, los, log)
        migriere_status(w, los, log, h7)
        manifest.json_atomar(os.path.join(w, MARKER), {"stand": manifest.jetzt(), "tausch": M}, indent=1)
    else:
        log.append("  status.json/700_guard.json: Schluessel, Ruecksprung, Hash/Signatur (Pruefung im --los-Lauf)"
                   if info["status"] or os.path.exists(os.path.join(w, "700_guard.json")) else "  (ohne status.json)")
    return log


def main(argv=None):
    ap = argparse.ArgumentParser(description="Migration Tausch 520/530")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--trocken", action="store_true")
    g.add_argument("--los", action="store_true")
    ap.add_argument("--werk", help="nur Werkordner, deren Pfad diesen Text enthaelt")
    a = ap.parse_args(argv)
    liste = [(w, i) for w in werkordner(a.werk) for i in [betroffen(w)] if i]
    print(f"Betroffene Werke: {len(liste)}")
    for w, i in liste:
        print(f"  {os.path.relpath(w, BASE)}: {len(i['dateien'])} Dateien, status {i['status'] or '-'}, "
              f"fortschritt {i['fortschritt'] or '-'}, ckpt {i['ckpt'] or '-'}, kosten {'ja' if i['kosten'] else '-'}")
    for w, i in liste:
        print("\n".join(migriere(w, i, a.los)))
    print("TROCKENLAUF – nichts geschrieben." if a.trocken else "Migration fertig.")


if __name__ == "__main__":
    main()
