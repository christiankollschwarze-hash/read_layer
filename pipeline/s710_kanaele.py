"""STAGE 710 — Kanaele EPUB und Extern (AP 710b, 03.11.2026; GATE_KATALOG.md Zeile 710, Befund 710 (8), (11))
EPUB:    Scope "<lg>:epub". Je lieferbarem 700-Scope (Kanal epub) die Variante aus 620/630 (text -> <werk>_<lg>.epub,
         Hoerbuch -> <werk>_<lg>_audio.epub; Manifest work/620_epub.json, Hash = ausgabe_hash) ins Ziel unter
         download/; Katalogfeld "downloads" {lg: {text|audio: "download/<datei>"}} am Werkeintrag.
Extern:  Scope "<lg>:extern". Paket fassungen/<lg>/extern_paket/: kapitel/ (Kapiteldateien 650 Profil extern),
         <werk>_<lg>.m4b (falls 650 gebaut), cover.jpg (615 _quadrat), metadaten.json (Titel, Autor, Sprecher
         mit KI-Hinweis, Sprache, ISBN leer, Kapitel, Dauer, Beschreibung 600, Plattformen). Gemini-Plattformregel:
         Premium/Drama nur bei "extern" in config.GEMINI_AUDIO_KANAELE, Plattformliste aus
         config.EXTERN_PLATTFORMEN (gemini True/False/None = Rueckfrage). Ergebnis Mensch "Paket bereit"; Upload auf
         die Plattform manuell durch CK, danach --extern-hochgeladen LG (gilt bei gleichem ausgabe_hash).
"""
import json
import os

from config import config
from pipeline import manifest

EPUB_CT = "application/epub+zip"
PAKET = "extern_paket"
GEMINI_STUFEN = ("premium", "drama")
PLATTFORMEN_STD = {"google_play": {"name": "Google Play Books", "gemini": True},
                   "spotify": {"name": "Spotify (Findaway)", "gemini": None},
                   "acx": {"name": "ACX / Audible", "gemini": False},
                   "apple": {"name": "Apple Books", "gemini": False},
                   "inaudio": {"name": "INaudio", "gemini": False}}
META_PFLICHT = ("titel", "autor", "sprecher", "sprache")


def _json(p, leer=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return leer


def plattformen():
    return dict(getattr(config, "EXTERN_PLATTFORMEN", None) or PLATTFORMEN_STD)


def produkte_700(werk, lg, kanal):
    """[(scope, {inhalt, stufe, ...})] der lieferbaren 700-Scopes einer Sprache x Kanal."""
    from pipeline import s700_guard
    d = _json(s700_guard.pfad(werk), {}) or {}
    return [(sc, (d.get("produkte") or {}).get(sc) or {}) for sc in s700_guard.lieferbar(werk, lg=lg, kanal=kanal)]


# ============================================================ EPUB
def epub_plan(werk, lg, src, prod, plan):
    """Variante je lieferbarem Produkt -> plan.kopie(download/<datei>). -> {variante: rel}."""
    m620 = (_json(config.work_path(werk, "620_epub"), {}) or {}).get("varianten") or {}
    out = {}
    for sc, x in prod:
        var = "text" if (x.get("inhalt") or "text") == "text" else "audio"
        rs = "620" if lg == src else "630"
        e = m620.get(f"{lg}:{var}")
        if not e:
            plan.befunde.append((f"epub_{var}", f"ePub {lg}:{var} nicht im Manifest 620 ({sc})", "620"))
            continue
        p = os.path.join(config.book_dir(werk), *str(e.get("datei") or "").replace("\\", "/").split("/"))
        if not os.path.exists(p):
            plan.befunde.append((f"epub_{var}", f"ePub-Datei fehlt: {e.get('datei')}", rs))
            continue
        if manifest.hash_datei(p) != e.get("ausgabe_hash"):
            plan.befunde.append((f"epub_{var}", f"ePub {lg}:{var} veraendert seit 620/630 (Hash)", "700"))
            continue
        rel = f"download/{os.path.basename(p)}"
        plan.kopie(rel, p, EPUB_CT)
        out[var] = rel
    plan.metriken["varianten"] = sorted(out)
    return out


# ============================================================ Extern
def paket_dir(werk, lg):
    return os.path.join(config.book_dir(werk), "fassungen", lg, PAKET)


def beschreibung(d600, lg):
    k = (d600 or {}).get("blurb") or {}
    teile = []
    for block in ("koeder", "einordnung", "autor"):
        for s in k.get(block) or []:
            t = s.get(lg) if isinstance(s, dict) else None
            if t:
                teile.append(str(t).strip())
    return " ".join(teile)


def extern_plan(werk, b, lg, prod, plan):
    """Paket-Plan fuer fassungen/<lg>/extern_paket/ (rel zum Paketordner). -> metadaten (dict)."""
    from pipeline import s080_mandant, s410_casting, s615_cover_final as s615, s700_guard, status
    stt = status.laden(werk)
    stufen = sorted({x.get("stufe") or "basic" for _, x in prod})
    gem = [s for s in stufen if s in GEMINI_STUFEN]
    pl = plattformen()
    if gem and "extern" not in s700_guard.gemini_kanaele():
        plan.befunde.append(("gemini_regel", f"Stufe {', '.join(gem)} (Gemini-Audio) nicht an Kanal extern "
                             f"(config.GEMINI_AUDIO_KANAELE {list(s700_guard.gemini_kanaele())})", "700"))
    erlaubt = [k for k, v in pl.items() if not gem or v.get("gemini") is True]
    rueckfrage = [k for k, v in pl.items() if gem and v.get("gemini") is None]
    if gem and not erlaubt:
        plan.befunde.append(("plattformen", "keine Plattform in config.EXTERN_PLATTFORMEN nimmt Gemini-Audio an", "700"))

    # Kapiteldateien 650 (Profil extern)
    z650 = status.zustand(werk, "650", scope=lg, d=stt)
    if z650 not in status.FREI:
        plan.befunde.append(("gate_650", f"Gate 650 {lg} nicht frei ({z650})", "650"))
    d650 = _json(config.work_path(werk, f"650_hoerbuch_{lg}"), {}) or {}
    ext = (d650.get("profile") or {}).get("extern") or {}
    kap = ext.get("kapitel") or []
    if not kap:
        plan.befunde.append(("kapitel", f"650 ohne Profil extern fuer {lg} (Hoerbuch-Assembler baut Extern nur fuer "
                             "Hoerbuch Basic)", "650"))
    bd = config.book_dir(werk)
    kap_meta, fehlt = [], []
    for e in kap:
        p = os.path.join(bd, *str(e.get("datei") or "").replace("\\", "/").split("/"))
        if not os.path.exists(p) or manifest.hash_datei(p) != e.get("datei_hash"):
            fehlt.append(e.get("kapitel"))
            continue
        rel = f"kapitel/{os.path.basename(p)}"
        plan.kopie(rel, p, "audio/mpeg")
        kap_meta.append({"nr": e.get("nr"), "kapitel": e.get("kapitel"), "titel": e.get("titel") or "",
                         "datei": rel, "dauer": e.get("dauer")})
    if fehlt:
        plan.befunde.append(("kapitel_aktuell", f"Kapiteldateien fehlen/veraendert seit 650: "
                             f"{', '.join(map(str, fehlt[:4]))}", "650"))
    m4b = None
    if ext.get("m4b"):
        p = os.path.join(bd, *str(ext["m4b"].get("datei") or "").replace("\\", "/").split("/"))
        if os.path.exists(p):
            m4b = os.path.basename(p)
            plan.kopie(m4b, p, "audio/mp4")
        else:
            plan.befunde.append(("m4b", f"M4B fehlt: {ext['m4b'].get('datei')}", "650"))

    # Cover _quadrat
    z615 = status.zustand(werk, "615", scope=f"{lg}:quadrat", d=stt)
    cover = s615.ausgabe_pfad(werk, lg, "quadrat")
    if z615 not in status.FREI:
        plan.befunde.append(("gate_615", f"Gate 615 {lg}:quadrat nicht frei ({z615})", "615"))
    elif not os.path.exists(cover):
        plan.befunde.append(("cover", f"Cover _quadrat fehlt: {os.path.basename(cover)}", "615"))
    else:
        plan.kopie("cover.jpg", cover, "image/jpeg")

    # Metadaten
    roh = b.roh
    titel = s615.titel(roh, lg, b.quellsprache)[0]
    try:
        autor = s615.autor(werk, roh, lg)
    except Exception:
        autor = ""
    stimme = s410_casting.stimme(werk, lg)
    d600 = _json(config.work_path(werk, "600_klappentext"), {}) or {}
    meta = {"schema": 1, "titel": titel or "", "autor": autor or "",
            "sprecher": f"{stimme} ({s615.KI.get(lg, 'AI voice')})" if stimme else "",
            "sprecher_stimme": stimme or "", "ki_stimme": True, "ki_hinweis": s615.KI.get(lg, "AI voice"),
            "sprache": lg, "isbn": "", "stufe": stufen, "gemini_audio": bool(gem),
            "verlag": s080_mandant.imprint(werk, b) or "", "erscheinungsjahr": roh.get("erscheinungsjahr") or "",
            "fassung": b.fassung, "rechte": (b.rechte or {}).get("art"),
            "beschreibung": beschreibung(d600, lg),
            "kapitel": kap_meta, "dauer_s": round(sum(float(k.get("dauer") or 0) for k in kap_meta), 1),
            "m4b": m4b, "cover": "cover.jpg" if "cover.jpg" in plan.dateien else None,
            "plattformen": {k: {"name": v.get("name", k), "zulaessig": k in erlaubt,
                                **({"rueckfrage": True} if k in rueckfrage else {})} for k, v in pl.items()},
            "audio_profil": ext.get("werte") or {}}
    leer = [k for k in META_PFLICHT if not meta.get(k)]
    if leer:
        rs = {"titel": "110", "autor": "110", "sprecher": "410"}
        plan.befunde.append(("metadaten", f"Metadaten leer: {', '.join(leer)}", rs.get(leer[0], "710")))
    plan.json("metadaten.json", meta)
    plan.metriken.update({"kapitel": len(kap_meta), "dauer_min": round(meta["dauer_s"] / 60, 1),
                          "m4b": bool(m4b), "plattformen": [k for k in erlaubt]})
    return meta
