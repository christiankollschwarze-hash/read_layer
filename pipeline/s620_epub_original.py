"""STAGE 620/630 — ePub (Ausgangssprache 620, Zielsprache 630 ueber s630_epub_zielsprache)
Funktion:     EPUB3 je Sprache x Variante laut Bestellung (Kanal EPUB): Text (<werk>_<lg>.epub) und
              Audio (Hoerbuch Basic, EPUB3 mit Media Overlay, <werk>_<lg>_audio.epub).
Wirkungsweise: Eingaenge -> Kapitel aus Satzteilen -> epub_bau.bauen -> Gate am fertigen EPUB (epubcheck,
              Textabgleich, Kapitel, Fallback, Vermerke, Sprache, Bilder/Fussnoten, SMIL). Rein deterministisch,
              Neu-Bauen aendert nichts -> rot = Stopp (geklebte Absaetze und Mandant verlag -> Mensch).
Eingang:      Text Ausgangssprache: work/modernized/chapter-N.json (190); Zielsprache: 330_rueckuebersetzung.json;
              Audio: Knoten 200 bzw. 330 + work/650_hoerbuch_<lg>.json (Kapiteldateien, Satz-Zeitmarken);
              Klappentext 600 (Gate frei); Cover 615 (cover_final_<lg>[_audio].jpg, Gate frei); anhang.json (150);
              book.json (Bestellung, fassung, teil/teile_gesamt, Rechte, Mandant 080); Profil 210 (Rollennamen).
Ausgabe:      fassungen/<lg>/output/<werk>_<lg>[_audio].epub; work/620_epub.json (je Scope <lg>:<variante>:
              Eingangs-/Ausgabe-Hash, Pruefmetriken); Gate je Scope in status.json (Stage 620 bzw. 630).
Regler:       --variante text|audio, --mobil an|aus, --mobil-laenge N, --bilder an|aus, --fussnoten an|aus,
              --kolophon LG=TEXT (nur Admin), --sprache LG, --neu, --freigeben, --trocken
Kosten:       0 $ (CPU, Java epubcheck).
Aufruf:       python -m pipeline.s620_epub_original <werk> [Regler] [--wer CK]
"""

import argparse
import datetime
import difflib
import json
import os
import re
import shutil
import tempfile
import uuid

from config import config
from pipeline import bestellung, epub_bau, gate, manifest, mock, status

STAGE_Q, STAGE_Z = "620", "630"
BAU_V = 1
TEXT_AUS = ("p", "tt", "skip", "ansage")         # keine Lesetext-Knoten
AUDIO_MEDIA = {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".mp4": "audio/mp4"}
BILD_MEDIA = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif",
              ".svg": "image/svg+xml", ".webp": "image/webp"}
REGLER = {"mobil": "an", "mobil_laenge": 320, "bilder": "an", "fussnoten": "an", "kolophon": {}}
SCHWELLEN = {"textabgleich_min": 1.0, "fallback_max": 0, "epubcheck_fehler_max": 0, "smil_min": 1.0}


# ------------------------------------------------------------ Pfade / Ablage
def ausgabe_pfad(werk, lg, variante):
    zus = "_audio" if variante == "audio" else ""
    return os.path.join(config.book_dir(werk), "fassungen", lg, "output", f"{werk}_{lg}{zus}.epub")


def manifest_pfad(werk):
    return config.work_path(werk, "620_epub")


def entscheidungen_pfad(werk):
    return config.work_path(werk, "620_entscheidungen")


def hoerbuch_pfad(werk, lg):
    return config.work_path(werk, f"650_hoerbuch_{lg}")


def _json(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def entscheidungen(werk):
    return {**REGLER, **(_json(entscheidungen_pfad(werk)) or {})}


def entscheidung_setzen(werk, wer, **k):
    d = _json(entscheidungen_pfad(werk)) or {}
    d.update(k)
    d.setdefault("protokoll", []).append({"wer": wer, "wann": manifest.jetzt(), "was": sorted(k)})
    manifest.json_atomar(entscheidungen_pfad(werk), d, indent=2)


def _frei(werk, stage, scope=None, d=None):
    z = status.zustand(werk, stage, scope=scope, d=d)
    if z == "offen" and scope is not None:
        st = (d or status.laden(werk))["stages"].get(stage) or {}
        if not st.get("teile"):
            z = st.get("zustand", "offen")
    return z


# ------------------------------------------------------------ Bestellung
def varianten(b, stage):
    """[(lg, variante)] laut Bestellung: Text bei Text/EPUB, Audio bei Hoerbuch Basic/EPUB."""
    lgs = [b.quellsprache] if stage == STAGE_Q else list(b.zielsprachen)
    out = []
    for lg in lgs:
        if b.hat(sprache=lg, inhalt="text", kanal="epub"):
            out.append((lg, "text"))
        if b.hat(sprache=lg, inhalt="hoerbuch", stufe="basic", kanal="epub"):
            out.append((lg, "audio"))
    return out


# ------------------------------------------------------------ Eingaenge
def kapitel_190(werk):
    """[(titel, absaetze)] aus work/modernized/chapter-N.json (ohne .original), Reihenfolge N."""
    d = os.path.join(config.work_dir(werk), "modernized")
    if not os.path.isdir(d):
        return []
    nr = sorted(int(m.group(1)) for f in os.listdir(d) if (m := re.fullmatch(r"chapter-(\d+)\.json", f)))
    out = []
    for n in nr:
        k = _json(os.path.join(d, f"chapter-{n}.json")) or {}
        out.append(((k.get("title") or "").strip(), [str(p) for p in k.get("paragraphs") or []]))
    return out


def knoten(werk, quelle):
    """Knoten in Reihenfolge: quelle 'q' -> 200_tagging, 'z' -> 330_rueckuebersetzung. -> (liste, meta)."""
    d = _json(config.work_path(werk, "200_tagging" if quelle == "q" else "330_rueckuebersetzung")) or {}
    return list((d.get("content") or {}).items()), d.get("meta") or {}


def _kap_id(tid):
    return tid.split("_")[0]


def _norm(s):
    return re.sub(r"[\W_]+", "", str(s)).lower()


def _woerter(s):
    return re.findall(r"\w+", str(s).lower())


def teile_text(text, lg):
    try:
        from tools import satzweise
        return [{"text": t, "id": None} for t in satzweise.teile_text(text, lg)] or [{"text": text, "id": None}]
    except Exception:                       # satzweise fehlt -> ganzer Absatz (Teilung nur Darstellung)
        return [{"text": text, "id": None}]


def kapitel_aus_190(k190, lg):
    """Text Ausgangssprache: Absaetze aus 190, Satzteile ueber satzweise (Mobil-Teilung)."""
    out = []
    for titel, paras in k190:
        abs_ = [{"hr": True} if p == epub_bau.HR else {"teile": teile_text(p, lg), "refs": []}
                for p in paras if p == epub_bau.HR or p.strip()]
        out.append({"titel": titel, "titel_id": None, "absaetze": abs_, "quelle_idx": None})
    return out


def rollen(profil, lg, q):
    """Rollennamen je Sprache aus Profil 210 (characters[name][lg]); Ausgangssprache = Original."""
    if lg == q:
        return {}
    ch = (profil or {}).get("characters") or {}
    return {n: (v.get(lg) or n) for n, v in ch.items() if isinstance(v, dict)}


def kapitel_aus_knoten(liste, lg, q, k190, mit_ids, rollen_namen=None):
    """Knoten -> Kapitel. Absatzgrenzen ueber Abgleich mit 190 (Quelltext); geht ein Kapitel nicht auf ->
    p-Marken (Kapitel als 'geklebt' gemeldet, wenn die Absatzzahl von 190 abweicht).
    -> (kapitel, fallback_ids, geklebt [kapitelnr])."""
    gruppen = {}
    for tid, e in liste:
        gruppen.setdefault(_kap_id(tid), []).append((tid, e))
    drama = any(e.get("type") == "dl" and e.get("sprecher") for _, e in liste)
    kapitel, fallback, geklebt = [], [], []
    for n, kid in enumerate(sorted(gruppen), 1):
        titel, titel_id, saetze, pmarken = "", None, [], set()
        for tid, e in gruppen[kid]:
            typ = e.get("type")
            src = str(e.get(q) or "").strip()
            ziel = str(e.get(lg) or "").strip()
            if typ in TEXT_AUS:
                if typ == "p" and saetze:
                    pmarken.add(saetze[-1][0])
                continue
            if src and not ziel:
                fallback.append(tid)
                continue
            if typ == "h":
                if not titel:
                    titel, titel_id = ziel, (tid if mit_ids else None)
                continue
            if ziel:
                saetze.append((tid, e, ziel, src))
        paras190 = k190[n - 1][1] if n - 1 < len(k190) else []
        absaetze = None
        if drama:
            absaetze, key = [], None
            for tid, e, ziel, _ in saetze:
                k = (e.get("sprecher"), e.get("replik")) if e.get("type") == "dl" else None
                if k is None or k != key:
                    sp = e.get("sprecher") if k else None
                    absaetze.append({"teile": [], "refs": [], "rolle": (rollen_namen or {}).get(sp, sp) if sp else None})
                key = k
                absaetze[-1]["teile"].append({"text": ziel, "id": tid if mit_ids else None})
        else:
            absaetze = _ausrichten(saetze, paras190, mit_ids)
            if absaetze is None:
                absaetze, cur = [], []
                for tid, e, ziel, _ in saetze:
                    cur.append({"text": ziel, "id": tid if mit_ids else None})
                    if tid in pmarken:
                        absaetze.append({"teile": cur, "refs": []})
                        cur = []
                if cur:
                    absaetze.append({"teile": cur, "refs": []})
                if len(absaetze) != len([p for p in paras190 if p != epub_bau.HR and p.strip()]):
                    geklebt.append(n)
        kapitel.append({"titel": titel or (k190[n - 1][0] if n - 1 < len(k190) else ""), "titel_id": titel_id,
                        "absaetze": absaetze, "quelle_idx": None})
    return kapitel, fallback, geklebt


def _ausrichten(saetze, paras190, mit_ids):
    """Saetze (Quelltext) auf die Absaetze aus 190 legen. -> Absatzliste (inkl. HR, gleiche Indizes wie 190)
    oder None, wenn das Kapitel nicht aufgeht."""
    if not paras190:
        return None
    out, i = [], 0
    for p in paras190:
        if p == epub_bau.HR:
            out.append({"hr": True})
            continue
        pn = _norm(p)
        if not pn:
            out.append(None)
            continue
        acc, teile = "", []
        while i < len(saetze) and len(acc) < len(pn):
            tid, _, ziel, src = saetze[i]
            acc += _norm(src)
            teile.append({"text": ziel, "id": tid if mit_ids else None})
            i += 1
        if acc != pn:
            return None
        out.append({"teile": teile, "refs": []})
    if i != len(saetze):
        return None
    return [a for a in out if a is not None]


def anhang_einhaengen(werk, kapitel, k190, lg, q, bilder_an, fussnoten_an):
    """anhang.json (150) -> refs an den Absaetzen, Bilder/Noten fuer den Anhang. -> (bilder, noten, hinweise)."""
    a = _json(os.path.join(config.work_dir(werk), "anhang.json")) or {}
    bilder, noten, hinw = [], [], []
    bdir = config.book_dir(werk)

    def absatz(k_nr, idx):
        if not (1 <= k_nr <= len(kapitel)):
            return None
        abs_ = kapitel[k_nr - 1]["absaetze"]
        nhr = [x for x in abs_ if not x.get("hr")]
        if not nhr:
            return None
        # gleiche Indizes wie 190 nur, wenn die Absatzzahl uebereinstimmt; sonst ans Kapitelende
        paras = k190[k_nr - 1][1] if k_nr - 1 < len(k190) else []
        echt = [p for p in paras if p == epub_bau.HR or p.strip()]
        if len(abs_) == len(echt) and 0 <= idx < len(abs_) and not abs_[idx].get("hr"):
            return abs_[idx]
        hinw.append(f"Anker Kapitel {k_nr} Absatz {idx} ans Kapitelende")
        return nhr[-1]

    if bilder_an:
        for b in a.get("bilder") or []:
            p = os.path.join(bdir, b.get("datei") or "")
            if not os.path.isfile(p):
                hinw.append(f"Bild fehlt: {b.get('datei')}")
                continue
            ziel = absatz(int(b.get("kapitel") or 0), int(b.get("nach_absatz") or 0))
            if ziel is not None:
                ziel.setdefault("refs", []).append(("bild", b["nr"]))
            ext = os.path.splitext(p)[1].lower()
            with open(p, "rb") as f:
                bilder.append({"nr": b["nr"], "name": os.path.basename(p), "data": f.read(),
                               "media": BILD_MEDIA.get(ext, "image/jpeg"), "alt": b.get("alt") or "",
                               "unterschrift": b.get("bildunterschrift") or "", "datei": b.get("datei")})
    if fussnoten_an:
        unuebersetzt = 0
        for fn in a.get("fussnoten") or []:
            ziel = absatz(int(fn.get("kapitel") or 0), int(fn.get("absatz") or 0))
            if ziel is not None:
                ziel.setdefault("refs", []).append(("fn", fn["nr"]))
            t = fn.get(f"text_{lg}") or (fn.get("text") if lg == q else None)
            if not t:
                t, unuebersetzt = fn.get("text") or "", unuebersetzt + 1
            noten.append({"nr": fn["nr"], "text": t})
        if unuebersetzt:
            hinw.append(f"{unuebersetzt} Fussnote(n) ohne Uebersetzung ({lg}) – Ausgangstext gesetzt")
    return bilder, noten, hinw, (len(a.get("bilder") or []) if bilder_an else 0,
                                 len(a.get("fussnoten") or []) if fussnoten_an else 0)


def klappentext(werk, lg):
    """Bloecke aus 600 genau in Sprache lg (kein Rueckfall). -> dict oder None."""
    d = _json(config.work_path(werk, "600_klappentext")) or {}
    bl = d.get("blurb") or {}
    out = {k: [str(s.get(lg)).strip() for s in bl.get(k) or [] if isinstance(s, dict) and s.get(lg)]
           for k in ("koeder", "einordnung", "autor")}
    return out if (out["koeder"] or out["einordnung"]) else None


def audio_kapitel(werk, lg, kapitel):
    """650-Manifest -> ({idx: {name, data, media, dauer, clips}}, fehler, metriken).
    Format work/650_hoerbuch_<lg>.json: {"kapitel": [{"kapitel": "c001", "datei": <rel. book_dir>,
    "dauer": s, "saetze": {tid: [start, ende]}}]}."""
    d = _json(hoerbuch_pfad(werk, lg))
    if not d:
        return None, ["650-Manifest fehlt"], {}
    eintr = {e.get("kapitel"): e for e in d.get("kapitel") or []}
    out, fehl, ohne, zu_lang, n_ges = {}, [], [], [], 0
    for i, k in enumerate(kapitel, 1):
        ids = ([k["titel_id"]] if k.get("titel_id") else []) + \
              [t["id"] for a in k["absaetze"] if not a.get("hr") for t in a["teile"] if t.get("id")]
        if not ids:
            continue
        kid = _kap_id(ids[0])
        e = eintr.get(kid)
        if not e:
            fehl.append(f"Kapitel {kid} ohne Audio")
            ohne += ids
            continue
        p = os.path.join(config.book_dir(werk), e.get("datei") or "")
        if not os.path.isfile(p):
            fehl.append(f"Audiodatei fehlt: {e.get('datei')}")
            ohne += ids
            continue
        dauer = float(e.get("dauer") or 0)
        z = e.get("saetze") or {}
        clips = []
        for tid in ids:
            n_ges += 1
            if tid not in z:
                ohne.append(tid)
                continue
            a_, e_ = float(z[tid][0]), float(z[tid][1])
            if e_ > dauer + 0.05 or a_ < 0 or e_ <= a_:
                zu_lang.append(tid)
            clips.append((tid, a_, min(e_, dauer)))
        ext = os.path.splitext(p)[1].lower()
        with open(p, "rb") as f:
            out[i] = {"name": f"chapter-{i}{ext}", "data": f.read(), "media": AUDIO_MEDIA.get(ext, "audio/mpeg"),
                      "dauer": dauer, "clips": clips, "datei": e.get("datei")}
    met = {"smil_abdeckung": round(1 - len(ohne) / n_ges, 4) if n_ges else 0.0, "smil_ohne": ohne[:20],
           "smil_ausserhalb": zu_lang[:20], "audio_saetze": n_ges}
    return out, fehl, met


# ------------------------------------------------------------ Metadaten / Kolophon
def metadaten(werk, b, lg, var):
    from pipeline import s080_mandant, s615_cover_final as s615
    roh = b.roh
    t, tq, _, _ = s615.titel(roh, lg, b.quellsprache)
    au = s615.autor(werk, roh, lg)
    imprint = s080_mandant.imprint(werk, b)
    art = (b.rechte or {}).get("art")
    quelle_url = ""
    gid = str(roh.get("gutenberg_id") or "").strip()
    if gid and art != "eigene":
        quelle_url = f"https://www.gutenberg.org/ebooks/{gid}"
    zeilen = []
    from pipeline import kette
    if kette.eingangsart(roh) in ("user_epub", "verlag_epub"):
        zeilen.append(epub_bau.text(lg, "original"))
    jahr = roh.get("erscheinungsjahr") or datetime.date.today().year
    if art == "eigene":
        inhaber = au or roh.get("owner_name") or roh.get("label") or ""
        rechte = epub_bau.text(lg, "eigene", jahr=jahr, inhaber=inhaber).replace("  ", " ")
    elif art == "gemeinfrei":
        rechte = epub_bau.text(lg, "pd")
        if b.fassung == "modernisiert" and imprint:
            zeilen.append(epub_bau.text(lg, "mod", imprint=imprint))
    else:
        rechte = epub_bau.text(lg, "fremd")
    zeilen.append(rechte)
    sp = s615.sprecher(werk, lg) if var == "audio" else ""
    return {"titel": t, "titel_quelle": tq, "autor": au, "autor_sort": _sortname(au), "lang": lg,
            "uuid": str(uuid.uuid5(epub_bau.NS, f"{werk}:{lg}:{var}")), "publisher": imprint or roh.get("label") or "",
            "imprint": imprint, "rechte": rechte, "quelle_url": quelle_url, "kolophon": zeilen, "sprecher": sp}


def _sortname(n):
    p = (n or "").split()
    return f"{p[-1]}, {' '.join(p[:-1])}" if len(p) > 1 else (n or "")


# ------------------------------------------------------------ Pruefung des fertigen EPUB
def textabgleich(ist, soll):
    a, b_ = _woerter(" ".join(ist)), _woerter(" ".join(soll))
    if a == b_:
        return 1.0
    return round(difflib.SequenceMatcher(None, a, b_, autojunk=False).ratio(), 4)


def pruefen(pfad, kapitel, lg, vermerke, n_bilder, n_noten, audio):
    """Fertiges EPUB lesen + epubcheck -> Metriken (im Manifest gespeichert, beim Resume wiederverwendet)."""
    r = epub_bau.lesen(pfad)
    soll = [" ".join(t["text"] for a in k["absaetze"] if not a.get("hr") for t in a["teile"]) for k in kapitel]
    ec = epub_bau.epubcheck(pfad)
    kol = _norm(r["kolophon"])
    m = {"epubcheck": ec, "textabgleich": textabgleich(r["kapitel"], soll), "kapitel_epub": len(r["kapitel"]),
         "sprache": r["sprache"], "vermerke_ist": sum(1 for v in vermerke if _norm(v) and _norm(v) in kol),
         "bilder_epub": r["bilder"], "bildrefs": r["bildrefs"], "noten_epub": r["noten"],
         "noterefs": r["noterefs"], "bilder_soll": n_bilder, "noten_soll": n_noten}
    if audio is not None:
        smil = r["smil"]
        n = sum(len(v) for v in smil.values())
        m["smil_eintraege"] = n
        m["smil_kapitel"] = len(smil)
    return m


# ------------------------------------------------------------ Lauf
def lauf(werk, stage=STAGE_Q, wer=None, nur=None, nur_var=None, neu=False, trocken=False, freigeben=False,
         regler=None):
    """-> Liste der Gates (je Scope <lg>:<variante>)."""
    wer = wer or "pipeline"
    b = bestellung.lesen(werk)
    q = b.quellsprache
    if regler and not trocken:
        r = dict(regler)
        if "kolophon" in r:
            r["kolophon"] = {**(entscheidungen(werk).get("kolophon") or {}), **r["kolophon"]}
        entscheidung_setzen(werk, wer, **r)
    ents = entscheidungen(werk)
    if freigeben and not trocken:
        return _freigeben(werk, stage, wer)

    mobil = int(ents.get("mobil_laenge") or 0) if ents.get("mobil", "an") != "aus" else 0
    bilder_an, fussnoten_an = ents.get("bilder", "an") != "aus", ents.get("fussnoten", "an") != "aus"
    d = status.laden(werk)
    st = d["stages"].get(stage) or {}
    man = _json(manifest_pfad(werk)) or {}
    eintraege = dict(man.get("varianten") or {})
    k190 = kapitel_190(werk)
    profil = _json(config.work_path(werk, "210_profil")) or {}
    from pipeline import s615_cover_final as s615
    verlag = b.mandant_art == "verlag"
    gates = []

    for lg, var in varianten(b, stage):
        if (nur and lg not in nur) or (nur_var and var != nur_var):
            continue
        scope = f"{lg}:{var}"
        if var == "audio" and _frei(werk, "650", lg, d) not in status.FREI and not trocken:
            print(f"[{stage}] {scope}: wartet auf Gate 650 ({lg}) – uebersprungen")
            continue
        g = gate.Gate(werk, stage, scope=scope, ruecksprung=stage, wer=wer)
        g.metrik("variante", var)

        def pf(name, ok, wert=None, ruecksprung=None, text=None, g=g):
            if trocken:
                g.hinweis(name, ok, wert, text=text)
            else:
                g.pflicht(name, ok, wert, ruecksprung=ruecksprung, text=text)

        # Vorgaenger
        vor = [("600", None, "600"), ("615", scope, "615")]
        vor.append(("190", None, "190") if lg == q else ("330", None, "330"))
        if var == "audio":
            vor.append(("650", lg, "650"))
        for s, sc, rs in vor:
            z = _frei(werk, s, sc, d)
            pf(f"gate_{s}", z in status.FREI, z, ruecksprung=rs, text=f"Gate {s}{' ' + sc if sc else ''} frei ({z})")
        cover = s615.ausgabe_pfad(werk, lg, var)
        g.pflicht("cover", os.path.isfile(cover), ruecksprung="615", text=f"Cover 615 ({os.path.basename(cover)})")
        g.pflicht("kapitel_190", bool(k190), ruecksprung="190", text="Kapitel aus 190 (work/modernized)")
        bl = klappentext(werk, lg)
        g.pflicht("klappentext", bool(bl), ruecksprung="600", text=f"Klappentext {lg} aus 600")
        meta = metadaten(werk, b, lg, var)
        g.pflicht("titel", bool(meta["titel"]), ruecksprung="615", text=f"Titel {lg}")
        if var == "audio":
            g.pflicht("sprecher", bool(meta["sprecher"]), ruecksprung="410", text="Sprecher aus casting.json")

        # Kapitel
        fallback, geklebt = [], []
        if lg == q and var == "text":
            kapitel = kapitel_aus_190(k190, lg)
        else:
            liste, kmeta = knoten(werk, "q" if lg == q else "z")
            g.pflicht("knoten", bool(liste), ruecksprung="200" if lg == q else "330",
                      text=f"Knoten {'200' if lg == q else '330'} vorhanden")
            kapitel, fallback, geklebt = kapitel_aus_knoten(
                liste, lg, q, k190, var == "audio",
                rollen(profil.get("profile") or profil or kmeta.get("profile"), lg, q))
        if g.fehler():
            g.entscheide(schreiben=not trocken)
            gates.append(g)
            continue

        g.gleich("kapitel", len(kapitel), len(k190), ruecksprung="190" if lg == q else "200")
        if lg != q:
            g.max("fallback", len(fallback), SCHWELLEN["fallback_max"], bei_fehler="stopp", ruecksprung="310")
            g.metrik("fallback_ids", fallback[:20])
        vm, vsoll, vq = s615.vermerke(werk, b, lg, True)
        if vq == "bestellung":
            g.hinweis("vermerke_600", False, text="Vermerke aus 600 fehlen (altes Format) – aus Bestellung gesetzt")
        meta["vermerke"] = vm
        meta["kolophon"] = meta["kolophon"] + ([ents["kolophon"][lg]] if (ents.get("kolophon") or {}).get(lg) else [])
        bilder, noten, a_hinw, (n_b, n_n) = anhang_einhaengen(werk, kapitel, k190, lg, q, bilder_an, fussnoten_an)
        for h in a_hinw[:5]:
            g.hinweis("anhang", False, text=h)
        audio = None
        if var == "audio":
            audio, a_fehl, a_met = audio_kapitel(werk, lg, kapitel)
            for f in a_fehl[:5]:
                g.pflicht("audio", False, f, ruecksprung="650", text=f)
            for k_, v in a_met.items():
                g.metrik(k_, v)
            if not a_fehl:
                g.min("smil_abdeckung", a_met["smil_abdeckung"], SCHWELLEN["smil_min"], bei_fehler="stopp", ruecksprung="650")
                g.max("smil_ausserhalb", len(a_met["smil_ausserhalb"]), 0, bei_fehler="stopp", ruecksprung="650")
        if g.fehler():
            g.entscheide(schreiben=not trocken)
            gates.append(g)
            continue

        with open(cover, "rb") as f:
            cdata = f.read()
        eingang = manifest.hash_obj({
            "v": BAU_V, "kapitel": kapitel, "meta": meta, "blurb": bl, "cover": manifest.hash_datei(cover),"mobil": mobil, "anhang": [(x["nr"], x["datei"]) for x in bilder] + noten,
            "audio": {i: [a["datei"], a["dauer"], a["clips"], manifest.hash_datei(
                os.path.join(config.book_dir(werk), a["datei"]))] for i, a in (audio or {}).items()}})
        pfad = ausgabe_pfad(werk, lg, var)
        alt = eintraege.get(scope) or {}
        unveraendert = (not neu and alt.get("eingang_hash") == eingang and os.path.isfile(pfad)
                        and manifest.hash_datei(pfad) == alt.get("ausgabe_hash") and alt.get("metriken"))
        tmpdir = None
        if unveraendert:
            met = alt["metriken"]
            ziel = pfad
            g.metrik("unveraendert", True)
        else:
            tmpdir = tempfile.mkdtemp(prefix="epub620_")
            ziel = os.path.join(tmpdir, os.path.basename(pfad))
            meta["geaendert"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            epub_bau.bauen(meta, kapitel, ziel, (cdata, "image/jpeg", "jpg"), mobil=mobil, blurb=bl,
                           bilder=bilder, noten=noten, audio=audio)
            met = pruefen(ziel, kapitel, lg, vm, n_b, n_n, audio)

        # Gate am fertigen EPUB
        ec = met["epubcheck"]
        g.pflicht("epubcheck_werkzeug", ec.get("werkzeug"), ruecksprung=stage,
                  text="epubcheck (tools/epubcheck-5.4.0, Java) lauffaehig")
        if ec.get("werkzeug"):
            g.max("epubcheck_fehler", ec["fehler"], SCHWELLEN["epubcheck_fehler_max"], bei_fehler="stopp", ruecksprung=stage)
            g.metrik("epubcheck_warnungen", ec["warnungen"])
            if ec["fehler"]:
                g.metrik("epubcheck_meldungen", ec["meldungen"])
        g.min("textabgleich", met["textabgleich"], SCHWELLEN["textabgleich_min"], bei_fehler="stopp", ruecksprung=stage)
        g.gleich("kapitel_epub", met["kapitel_epub"], len(k190), ruecksprung=stage)
        g.gleich("sprache", met["sprache"], epub_bau.BCP47.get(lg, lg), ruecksprung=stage)
        g.gleich("vermerke", met["vermerke_ist"], len(vm), ruecksprung="115")
        g.gleich("bilder", met["bilder_epub"], met["bilder_soll"], ruecksprung="150")
        g.gleich("fussnoten", met["noten_epub"], met["noten_soll"], ruecksprung="150")
        if audio is not None:
            g.gleich("smil_eintraege", met.get("smil_eintraege"), sum(len(a["clips"]) for a in audio.values()),
                     ruecksprung=stage)
        g.metrik("geklebt_kapitel", geklebt)
        g.pruefe("geklebt", not geklebt, len(geklebt), 0, "mensch", "200",
                 text=f"Absaetze geklebt: Kapitel {', '.join(map(str, geklebt)) or 'keine'} (Absatzgrenzen 200/190)")
        mocks = [os.path.basename(p) for p in [cover] + [os.path.join(config.book_dir(werk), a["datei"])
                 for a in (audio or {}).values()] if mock.ist_datei(p)]
        g.mock(len(mocks), mocks, ruecksprung="615" if mocks and mocks[0] == os.path.basename(cover) else "650")
        g.metrik("eingang_hash", eingang)

        # Mensch-Freigabe gilt bei gleichem Eingang
        alt_st = (st.get("teile") or {}).get(scope) or {}
        mensch_gilt = alt_st.get("zustand") == "frei" and (alt_st.get("gate") or {}).get("ergebnis") == "mensch" \
            and (alt_st.get("metriken") or {}).get("eingang_hash") == eingang
        if mensch_gilt:
            for p in g.pruefungen:
                if not p["ok"] and p["bei_fehler"] == "mensch":
                    p["bei_fehler"] = "hinweis"
                    p["text"] += " [Mensch-Freigabe gilt, Eingaenge unveraendert]"
        immer = verlag and not mensch_gilt
        e = g.entscheide(mensch_immer=immer, mensch_grund="Vorschau ePub (Mandant verlag): --freigeben" if immer else None,
                         schreiben=not trocken)

        if not trocken and e != "stopp" and not unveraendert:
            os.makedirs(os.path.dirname(pfad), exist_ok=True)
            shutil.move(ziel, pfad + ".tmp")
            os.replace(pfad + ".tmp", pfad)
        if not trocken and e != "stopp":
            eintraege[scope] = {"datei": os.path.relpath(pfad, config.book_dir(werk)), "stage": stage, "sprache": lg,
                                "variante": var, "eingang_hash": eingang,
                                "ausgabe_hash": manifest.hash_datei(pfad), "titel": meta["titel"],
                                "kapitel": len(kapitel), "metriken": met,
                                "gebaut": alt.get("gebaut") if unveraendert else manifest.jetzt(),
                                "pruefung": {"ergebnis": e, "gruende": g.ergebnis["gruende"],
                                             "hinweise": g.ergebnis["hinweise"], "zeit": manifest.jetzt()}}
        if tmpdir:
            g.aus = {"datei": ziel if trocken else pfad}
            if not trocken:
                shutil.rmtree(tmpdir, ignore_errors=True)
        else:
            g.aus = {"datei": pfad}
        gates.append(g)

    if not trocken:
        neu_man = _json(manifest_pfad(werk)) or {}           # 620 und 630 teilen die Datei
        v = dict(neu_man.get("varianten") or {})
        v.update({s: e for s, e in eintraege.items() if e.get("stage") == stage})
        manifest.json_atomar(manifest_pfad(werk), {"schema": 1, "bau_v": BAU_V, "varianten": v,
                                                   "zeit": manifest.jetzt()}, indent=2)
    return gates


def run(werk, wer=None, **kw):
    """Kettenaufruf 620 (Ausgangssprache)."""
    return lauf(werk, STAGE_Q, wer=wer, **kw)


def _freigeben(werk, stage, wer):
    d = status.laden(werk)
    teile = ((d["stages"].get(stage) or {}).get("teile") or {})
    offen = [s for s, t in teile.items() if t.get("zustand") == "mensch"]
    for s in offen:
        status.entscheiden(werk, stage, "frei", wer=wer, grund=f"Freigabe ePub {stage}", scope=s)
    print(f"[{stage}] Freigabe: {', '.join(offen) or 'nichts offen'}")
    return []


def main(argv=None, stage=STAGE_Q):
    ap = argparse.ArgumentParser(description=f"Stage {stage} ePub")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--variante", choices=["text", "audio"])
    ap.add_argument("--mobil", choices=["an", "aus"], help="Mobil-Absaetze (Teilung an Satzgrenzen)")
    ap.add_argument("--mobil-laenge", type=int, metavar="N")
    ap.add_argument("--bilder", choices=["an", "aus"])
    ap.add_argument("--fussnoten", choices=["an", "aus"])
    ap.add_argument("--kolophon", action="append", metavar="LG=TEXT", help="Kolophon-Zusatz (nur Admin)")
    ap.add_argument("--sprache", action="append", metavar="LG")
    ap.add_argument("--neu", action="store_true", help="neu bauen")
    ap.add_argument("--force", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--freigeben", action="store_true", help="Mensch-Faelle freigeben")
    ap.add_argument("--trocken", action="store_true", help="nur pruefen, nichts schreiben")
    ap.add_argument("--lang", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    try:
        regler = {}
        for n in ("mobil", "bilder", "fussnoten"):
            if getattr(a, n):
                regler[n] = getattr(a, n)
        if a.mobil_laenge is not None:
            if a.mobil_laenge < 0:
                raise ValueError("--mobil-laenge >= 0")
            regler["mobil_laenge"] = a.mobil_laenge
        kol = {}
        for x in a.kolophon or []:
            if "=" not in x:
                raise ValueError(f"--kolophon {x!r}: Format LG=TEXT")
            lg, t = x.split("=", 1)
            kol[lg.strip().lower()] = t.strip()
        if kol:
            regler["kolophon"] = kol
        if not a.trocken and (regler or a.freigeben):
            from pipeline import s080_mandant
            s080_mandant.darf(a.werk, "override" if kol else "entscheiden", a.wer or "pipeline")
        nur = a.sprache or (a.lang.split(",") if a.lang else None)
        gates = lauf(a.werk, stage, a.wer, nur, a.variante, a.neu or a.force, a.trocken, a.freigeben, regler or None)
    except gate.GateHalt as e:
        print(e)
        return e.exit_code
    except (ValueError, PermissionError, RuntimeError) as e:
        print(f"[{stage}] Fehler: {e}")
        return 1
    if a.freigeben:
        return 0
    for g in gates:
        print(f"--- {g.scope}")
        print(g.bericht())
        if getattr(g, "aus", None):
            print(f"    -> {g.aus['datei']}")
    if not gates:
        print(f"[{stage}] nichts zu tun (keine EPUB-Bestellung bzw. Vorstufe offen)")
    return gate.EXIT[gate.gesamt([g.ergebnis["ergebnis"] for g in gates])] if gates else 0


if __name__ == "__main__":
    raise SystemExit(main())
