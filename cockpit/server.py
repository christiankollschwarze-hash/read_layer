"""
READ LAYER — Cockpit (lokal)
============================
Kleiner Webserver um die bestehende Pipeline. Nur Standardbibliothek, keine Installation.

Start:   cockpit_start.bat   (oder: py -3.11 cockpit\\server.py)
Browser: http://127.0.0.1:8765

Was es tut:
  - Katalog: Startliste (cockpit/startliste.json) + vorhandene Buecher (authors/...),
    Status je Schritt aus der Ordnerstruktur gelesen (kein eigener Zustand ausser Freigaben).
  - Tore: Sammelansichten zur Freigabe im Stapel. Freigaben in daten/freigaben.json.
  - Hoerspiel-Pruefung (nach dem Overlay): Ampel je Figur aus casting.json pruefung[lg]
    (tools/trennung_auswerten.py); Entscheidung Freigeben / Nachrunde / Umbesetzen in casting.json.
  - Lauf: fuehrt fuer markierte Werke die naechsten Schritte aus, bis ein Tor offen ist.
    Werke laufen nacheinander; ein offenes Tor haelt nur dieses Werk an.

Die Pipeline selbst wird NICHT veraendert: das Cockpit ruft run.py / tools/s100_anlegen.py
als Unterprozess auf (gleicher Python-Interpreter wie der Server).
"""

import os
import sys
import json
import re
import time
import random
import threading
import subprocess
import datetime as dt
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
AUTHORS = os.path.join(BASE, "authors")
sys.path.insert(0, BASE)
from pipeline.klappentext_pruefung import pruefe as _kt_pruefe  # noqa: E402  (18.10.2026)
INDEX = os.path.join(BASE, "daten", "index.json")
FREIGABEN = os.path.join(BASE, "daten", "freigaben.json")
STARTLISTE = os.path.join(HERE, "startliste.json")
LOGDIR = os.path.join(HERE, "logs")
DEMO_DIR = os.path.join(os.path.dirname(BASE), "taella-app", "public", "demo")
PORT = 8765
PY = sys.executable
NO_AUDIO_TYPES = {"p", "tt", "skip"}

# Ablauf: Produktionsschritte (s) und Tore (t). Reihenfolge = Ablauf.
FLOW = [
    ("pd",                "t", "PD-Pruefung"),
    ("anlegen",           "s", "Anlegen"),
    ("titel",             "s", "Titel DE/EN (Wikidata)"),
    ("text",              "s", "Text (11-56)"),
    ("uebersetzung",      "t", "Uebersetzung"),
    ("woerter",           "s", "Wortanker (54a)"),
    ("wortzeit_en",       "s", "Wortzeit-EN (Forced Alignment 58c)"),
    ("klappentext_cover", "s", "Klappentext + Cover"),
    ("cover_final",       "s", "Cover final (mit Titel)"),
    ("cover",             "t", "Cover + Klappentext"),
    ("audio_de",          "s", "Audio DE"),
    ("audio_de_pruefung", "t", "Audio DE"),
    ("wortzeit_de",       "s", "Wortzeit-DE (Forced Alignment 58c)"),
    ("export",            "s", "Export EPUB"),
    ("export_pruefung",   "t", "Export"),
    ("demo",              "s", "Demo-Ordner"),
]
# Nicht blockierend (EN-Spur aus LibriVox): eigenes Tor, haelt den Lauf nicht an.
EXTRA_GATES = []   # 11.10.2026: LibriVox-Spur entfernt (designte Stimmen statt LibriVox)
DEEPSEEK_STEPS = {"text", "woerter"}   # Klappentext/Cover laufen auf Gemini


# ------------------------------------------------------------------ Dateien
_JSON_CACHE = {}


def _load_cached(path, default):
    """Wie _load, aber je Datei-Zeitstempel zwischengespeichert (book.json, index, freigaben)."""
    try:
        mt = os.stat(path).st_mtime
    except OSError:
        return default
    c = _JSON_CACHE.get(path)
    if c and c[0] == mt:
        return c[1]
    v = _load(path, default)
    _JSON_CACHE[path] = (mt, v)
    return v


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


_lock = threading.Lock()


def _save_freigaben(d):
    with _lock:
        tmp = FREIGABEN + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, FREIGABEN)


def _rel(p):
    return os.path.relpath(p, BASE).replace("\\", "/")


# ------------------------------------------------------------------ Status-Scanner
def _book_dir(slug, idx):
    a = idx.get("books", {}).get(slug)
    return os.path.join(AUTHORS, a, "books", slug) if a else None


def _work(bdir, name):
    return os.path.join(bdir, "work", name + ".json")


def _cover(bdir):
    for ext in ("png", "jpg", "jpeg", "webp"):
        p = os.path.join(bdir, "images", "cover." + ext)
        if os.path.exists(p):
            return p
    return None


_WAV_CACHE = {}


def _wavs(bdir, lang):
    # Ordnerinhalt nur neu lesen, wenn sich der Ordner geaendert hat (Tausende WAVs je Buch)
    d = os.path.join(bdir, "fassungen", lang, "audio")
    try:
        mt = os.stat(d).st_mtime
    except OSError:
        return []
    c = _WAV_CACHE.get(d)
    if c and c[0] == mt:
        return c[1]
    w = sorted(f for f in os.listdir(d) if f.endswith(".wav"))
    _WAV_CACHE[d] = (mt, w)
    return w


_SOLL_CACHE = {}


def _audio_soll(bdir, lang):
    # 400_regie kann mehrere MB gross sein -> Ergebnis je Datei-Zeitstempel zwischenspeichern
    p = _work(bdir, "400_regie")
    try:
        key = (p, lang, os.path.getmtime(p))
    except OSError:
        return 0
    if key in _SOLL_CACHE:
        return _SOLL_CACHE[key]
    _SOLL_CACHE[key] = n = _audio_soll_lesen(bdir, lang)
    return n


def _audio_soll_lesen(bdir, lang):
    data = _load(_work(bdir, "400_regie"), None)
    if not data:
        return 0
    n = 0
    for _t, e in data.get("content", {}).items():
        if e.get("type") in NO_AUDIO_TYPES:
            continue
        if str(e.get(lang, "")).strip():
            n += 1
    return n


def _epubs(bdir, slug):
    out = []
    for lang in ("en", "de"):
        p = os.path.join(bdir, "fassungen", lang, "output", slug + ".epub")
        if os.path.exists(p):
            out.append(p)
    return out


def _audio_de_done(bdir):
    wavs = _wavs(bdir, "de")
    if not wavs:
        return False, 0, 0
    soll = _audio_soll(bdir, "de")
    # Block-Synthese (Gemini) schreibt weniger, aber laengere WAVs: dann zaehlt das
    # fertige Hoerbuch im output-Ordner als Nachweis.
    out = os.path.join(bdir, "fassungen", "de", "output")
    has_out = os.path.isdir(out) and any(f.endswith((".mp3", ".m4b")) for f in os.listdir(out))
    return (len(wavs) >= soll > 0) or has_out, len(wavs), soll


def _kosten(bdir):
    """Summe aus work/kosten.jsonl (pipeline/usage_log.py): Token und geschaetzte USD."""
    p = os.path.join(bdir, "work", "kosten.jsonl")
    try:
        mt = os.stat(p).st_mtime
    except OSError:
        return None
    c = _JSON_CACHE.get(p)
    if c and c[0] == mt:
        return c[1]
    k = {"usd": 0.0, "in": 0, "out": 0, "aufrufe": 0, "stages": {}}
    with open(p, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            k["aufrufe"] += 1
            k["in"] += r.get("in", 0); k["out"] += r.get("out", 0)
            k["usd"] += r.get("usd") or 0
            st = str(r.get("stage") or "?")
            k["stages"][st] = round(k["stages"].get(st, 0) + (r.get("usd") or 0), 4)
    k["usd"] = round(k["usd"], 4)
    _JSON_CACHE[p] = (mt, k)
    return k


def _kt_status(bdir):
    """Klappentext-Pruefung (pipeline/klappentext_pruefung.py), je Datei-Zeitstempel gecacht.
    Liefert None (kein Klappentext) oder {"ok", "fehler", "hinweise"}."""
    p = _work(bdir, "600_klappentext")
    kt = _load_cached(p, None)
    if not kt:
        return None
    key = ("kt", p)
    try:
        mt = os.stat(p).st_mtime
    except OSError:
        return None
    c = _JSON_CACHE.get(key)
    if c and c[0] == mt:
        return c[1]
    r = _kt_pruefe(kt)
    gesp = kt.get("pruefung") or {}
    v = {"ok": r["ok"], "fehler": r["fehler"], "hinweise": gesp.get("hinweise") or r["hinweise"]}
    _JSON_CACHE[key] = (mt, v)
    return v


def _cover_final_ok(bdir):
    """Beide Fassungen (EN/DE) haben ein fertiges Cover, juenger als die Illustration."""
    c = _cover(bdir)
    if not c:
        return False
    for lang in ("en", "de"):
        p = os.path.join(bdir, "fassungen", lang, "output", f"cover_final_{lang}.jpg")
        if not os.path.exists(p) or os.path.getmtime(p) < os.path.getmtime(c):
            return False
    return True


def scan():
    """Liefert alle Werke (Startliste + vorhandene Buecher) mit Status je Schritt."""
    idx = _load_cached(INDEX, {"books": {}})
    start = _load_cached(STARTLISTE, [])
    frei = _load_cached(FREIGABEN, {})
    jahr = dt.date.today().year

    # vorhandene Buecher nach gutenberg_id
    by_gid, rows = {}, []
    for slug in idx.get("books", {}):
        bdir = _book_dir(slug, idx)
        if not bdir or not os.path.isdir(bdir):
            continue
        b = _load_cached(os.path.join(bdir, "book.json"), {})
        gid = str(b.get("gutenberg_id") or "")
        by_gid[gid or ("slug:" + slug)] = (slug, bdir, b)
        # LibriVox-Pruefung kann die Ausgabe wechseln (gutenberg_id = Quelltext der Aufnahme):
        # unter der urspruenglichen Startlisten-Nummer weiter auffindbar bleiben
        alt = str(b.get("gutenberg_id_original") or "")
        if alt:
            by_gid.setdefault(alt, (slug, bdir, b))

    def _tnorm(t):
        t = re.split(r"[:;(]", (t or "").lower())[0]
        return re.sub(r"[^a-z0-9]", "", re.sub(r"^(the|a|an)\s+", "", t.strip()))
    by_titel = {}
    for info in by_gid.values():
        by_titel.setdefault(_tnorm(info[2].get("titel_original") or info[0]), info)

    seen, slugs_gesehen = set(), set()
    for e in start:
        gid = e["gutenberg_id"]
        info = by_gid.get(gid)
        if not info:
            # gleiche Werk-Ausgabe unter anderer Nummer schon angelegt (Anlegen meldet "existiert")
            cand = by_titel.get(_tnorm(e["titel"]))
            if cand and cand[0] not in slugs_gesehen:
                info = cand
        rows.append(_row(e, info, frei, jahr))
        seen.add(gid)
        if info:
            slugs_gesehen.add(info[0])
    for gid, info in by_gid.items():
        if gid not in seen and info[0] not in slugs_gesehen:
            slugs_gesehen.add(info[0])
            b = info[2]
            e = {"prio": 999, "gutenberg_id": gid if not gid.startswith("slug:") else "",
                 "titel": b.get("titel_original") or info[0], "autor": "", "todesjahr": None,
                 "uebersetzung": bool(b.get("quell_uebersetzer")), "woerter": None,
                 "ampel": "", "flags": "nicht in Startliste"}
            rows.append(_row(e, info, frei, jahr))
    return rows


def _key(e, info):
    if e.get("gutenberg_id"):
        return "g" + e["gutenberg_id"]
    return "s:" + info[0]


def _row(e, info, frei, jahr):
    key = _key(e, info)
    r = dict(e)
    r["key"] = key
    r["slug"] = info[0] if info else None
    st = {}
    tod = e.get("todesjahr")
    r["pd_vorschlag"] = bool(tod and tod + 70 < jahr and not e.get("uebersetzung"))
    r["produktionsreif"] = r["pd_vorschlag"] and e.get("ampel") in ("gruen", "gelb")
    if info:
        slug, bdir, b = info
        st["anlegen"] = True
        st["text"] = os.path.exists(_work(bdir, "400_regie"))
        fde = next((f for f in b.get("fassungen", []) if f.get("sprache") == "de"), {}) or {}
        st["titel"] = bool((fde.get("titel") or "").strip())
        r["titel_de"], r["titel_pruefen"] = fde.get("titel") or "", bool(fde.get("titel_pruefen"))
        # 18.10.2026: LibriVox-Audio-Strang archiviert (EN-Audio kommt aus eigener Vertonung).
        # Wortzeit EN wird gebraucht, sobald EN-Audio vorliegt.
        st["woerter"] = os.path.exists(_work(bdir, "340_wortalignment"))
        st["wortzeit_en"] = (not _wavs(bdir, "en")) or os.path.exists(_work(bdir, "520_wortzeiten_en"))
        st["wortzeit_de"] = os.path.exists(_work(bdir, "520_wortzeiten_de"))
        kt = _kt_status(bdir)
        r["kt_pruefung"] = kt
        st["klappentext_cover"] = bool(kt and kt["ok"]) and bool(_cover(bdir))
        # 18.10.2026: Cover-Tor abgelehnt -> Illustration neu erzeugen (s610 --force).
        # Ist die Illustration juenger als die Ablehnung, gilt das Tor wieder als offen.
        r["cover_neu"] = False
        g_cov = (frei.get(key, {}) or {}).get("cover") or {}
        c = _cover(bdir)
        if g_cov.get("status") == "abgelehnt" and c:
            try:
                t_abl = dt.datetime.fromisoformat(g_cov.get("zeit", "")).timestamp()
            except Exception:
                t_abl = 0
            if os.path.getmtime(c) <= t_abl:
                r["cover_neu"] = True
                st["klappentext_cover"] = False
            else:
                r["cover_wieder_offen"] = True
        st["cover_final"] = _cover_final_ok(bdir)
        done, ist, soll = _audio_de_done(bdir)
        st["audio_de"] = done
        r["audio_de_fortschritt"] = [ist, soll]
        # Gemini-Blockdateien vorhanden, aber unvollstaendig -> nicht automatisch mit Thorsten mischen
        r["audio_de_gemischt"] = (not done) and any(w.startswith("_block") for w in _wavs(bdir, "de"))
        st["export"] = len(_epubs(bdir, slug)) > 0
        st["demo"] = os.path.exists(os.path.join(DEMO_DIR, slug, "manifest_en.json")) or \
            os.path.exists(os.path.join(DEMO_DIR, slug, "manifest_de.json"))
        r["en_audio"] = len(_wavs(bdir, "en")) > 0
        r["kosten"] = _kosten(bdir)
        # Translator-PD aus book.json
        if b.get("quell_uebersetzer"):
            ty = b.get("quell_uebersetzer_todesjahr")
            r["pd_vorschlag"] = bool(ty and ty + 70 < jahr and tod and tod + 70 < jahr)
    else:
        for k in ("anlegen", "titel", "text", "woerter", "wortzeit_en",
                  "klappentext_cover", "cover_final", "audio_de", "wortzeit_de", "export", "demo"):
            st[k] = False
        r["en_audio"] = False
    g = frei.get(key, {})
    for k, typ, _l in FLOW:
        if typ == "t":
            st[k] = (g.get(k) or {}).get("status", "offen")   # offen | frei | abgelehnt
    if r.get("cover_wieder_offen"):
        st["cover"] = "offen"
    # 22.10.2026: eigenes Werk (book.json rechte=eigene) -> PD-Tor entfaellt (keine Todesjahr-Pruefung)
    if info and str(info[2].get("rechte") or "").lower().startswith("eigen"):
        st["pd"] = "frei"
        r["pd_vorschlag"] = True
        r["eigene_rechte"] = True
        r["flags"] = "eigene Rechte" if not r.get("flags") or r.get("flags") == "nicht in Startliste" \
            else f'{r["flags"]}; eigene Rechte'
    r["status"] = st
    moeglich, offen, abgelehnt = _plan(st)
    r["moeglich"], r["tore_offen"], r["tore_abgelehnt"] = moeglich, offen, abgelehnt
    if moeglich:
        r["naechster"] = ["step", moeglich[0]]
    elif offen:
        r["naechster"] = ["gate", offen[0]]
    elif abgelehnt:
        r["naechster"] = ["blockiert", abgelehnt[0]]
    else:
        r["naechster"] = _next(st)
    return r


# Abhaengigkeiten: Schritt -> (vorher fertige Schritte, vorher freigegebene Tore).
# Klappentext + Cover entstehen aus dem Originaltext -> laufen parallel zum Text.
STEP_DEPS = {
    "anlegen":           ([], ["pd"]),
    "text":              (["anlegen"], ["pd"]),
    "klappentext_cover": (["anlegen"], ["pd"]),
    "cover_final":       (["klappentext_cover", "titel"], ["pd"]),
    "woerter":           (["text"], ["uebersetzung"]),
    "wortzeit_en":       (["woerter"], ["uebersetzung"]),
    "audio_de":          (["text"], ["uebersetzung"]),
    "wortzeit_de":       (["audio_de", "woerter"], ["audio_de_pruefung"]),
    "titel":             (["anlegen"], ["pd"]),
    "export":            (["audio_de", "klappentext_cover", "titel"], ["cover", "audio_de_pruefung"]),
    "demo":              (["export", "wortzeit_de", "wortzeit_en"], ["export_pruefung"]),
}
GATE_DEPS = {"pd": [], "uebersetzung": ["text"], "cover": ["klappentext_cover", "cover_final"],
             "audio_de_pruefung": ["audio_de"], "export_pruefung": ["export"]}


def _plan(st):
    """(moegliche Schritte, offene Tore, abgelehnte Tore) in Ablauf-Reihenfolge."""
    moeglich, offen, abgelehnt = [], [], []
    for k, typ, _l in FLOW:
        if typ == "s":
            if st.get(k):
                continue
            steps, gates = STEP_DEPS[k]
            if all(st.get(x) is True for x in steps) and all(st.get(g) == "frei" for g in gates):
                moeglich.append(k)
        else:
            if not all(st.get(x) is True for x in GATE_DEPS[k]):
                continue
            if st.get(k) == "abgelehnt":
                abgelehnt.append(k)
            elif st.get(k) != "frei":
                offen.append(k)
    return moeglich, offen, abgelehnt


def _next(st):
    """Naechster Eintrag im Ablauf: ('step', k) | ('gate', k) | ('blockiert', k) | ('fertig', None)."""
    for k, typ, _l in FLOW:
        if typ == "s":
            if not st.get(k):
                return ["step", k]
        else:
            s = st.get(k)
            if s == "abgelehnt":
                return ["blockiert", k]
            if s != "frei":
                return ["gate", k]
    return ["fertig", None]


# ------------------------------------------------------------------ Tor-Ansichten
def gate_items(gate):
    rows = scan()
    idx = _load(INDEX, {"books": {}})
    items = []
    for r in rows:
        if gate not in r.get("tore_offen", []):
            continue
        it = {"key": r["key"], "titel": r["titel"], "autor": r.get("autor"), "prio": r["prio"],
              "slug": r["slug"]}
        bdir = _book_dir(r["slug"], idx) if r["slug"] else None
        try:
            it.update(_gate_payload(gate, r, bdir))
        except Exception as ex:
            it["fehler"] = str(ex)
        items.append(it)
    items.sort(key=lambda x: x["prio"])
    return items


def _gate_payload(gate, r, bdir):
    if gate == "pd":
        return {"todesjahr": r.get("todesjahr"), "uebersetzung": r.get("uebersetzung"),
                "vorschlag": r.get("pd_vorschlag"), "ampel": r.get("ampel"),
                "flags": r.get("flags"), "woerter": r.get("woerter")}
    if gate == "uebersetzung":
        d = _load(_work(bdir, "330_rueckuebersetzung"), {})
        q = d.get("meta", {}).get("quality_report", {}) or {}
        flagged = sorted(q.get("flagged", []), key=lambda x: x[2])[:6]
        content = d.get("content", {})
        beispiele = [{"tag": t, "score": s, "en": content.get(t, {}).get("en", ""),
                      "de": content.get(t, {}).get(l, "")} for t, l, s in flagged]
        return {"avg": q.get("average_score"), "n": q.get("scored_count"),
                "n_flagged": len(q.get("flagged", [])), "schwelle": q.get("threshold"),
                "beispiele": beispiele}
    if gate == "cover":
        d = _load(_work(bdir, "600_klappentext"), {})
        meta, blurb = d.get("meta", {}), d.get("blurb", {})

        def _txt(k, lang):
            v = blurb.get(k)
            if isinstance(v, list) and v:
                return v[0].get(lang, "")
            return ""
        c = _cover(bdir)
        finals = {}
        for lang in ("de", "en"):
            fp = os.path.join(bdir, "fassungen", lang, "output", f"cover_final_{lang}.jpg")
            if os.path.exists(fp):
                finals[lang] = _rel(fp)
        kt = r.get("kt_pruefung") or {}
        return {"cover": _rel(c) if c else None, "cover_final": finals,
                "kt_fehler": kt.get("fehler", []), "kt_hinweise": kt.get("hinweise", []),
                "titel_de": r.get("titel_de"),
                "titel_pruefen": r.get("titel_pruefen"), "sicherheit": meta.get("sicherheit", ""),
                "inhaltshinweise": meta.get("inhaltshinweise", []),
                "einordnung_de": _txt("einordnung", "de"), "einordnung_en": _txt("einordnung", "en"),
                "koeder_de": _txt("koeder", "de")}
    if gate == "audio_de_pruefung":
        return {"proben": _proben(bdir, "de", r["slug"]), "stt": _stt(bdir),
                "fortschritt": r.get("audio_de_fortschritt")}
    if gate == "export_pruefung":
        return {"dateien": [{"pfad": _rel(p), "kb": os.path.getsize(p) // 1024}
                            for p in _epubs(bdir, r["slug"])]}
    return {}


def _proben(bdir, lang, slug, n=4):
    w = _wavs(bdir, lang)
    rnd = random.Random(slug + lang)
    pick = sorted(rnd.sample(w, min(n, len(w))))
    d = os.path.join(bdir, "fassungen", lang, "audio")
    return [_rel(os.path.join(d, f)) for f in pick]


def _stt(bdir):
    q = _load(os.path.join(bdir, "work", "quality_report.json"), {})
    de = q.get("langs", {}).get("de", {})
    return {"geprueft": de.get("checked"), "flags": len(de.get("remaining_flags", []))}


# ------------------------------------------------------------------ Lauf (Warteschlange)
def nebenzeit_jetzt():
    """DeepSeek-Spitzenzeit: Mo-Fr 01-04 und 06-10 UTC. Sonst Nebenzeit (halber Preis)."""
    u = dt.datetime.now(dt.timezone.utc)
    if u.weekday() >= 5:
        return True
    return not (1 <= u.hour < 4 or 6 <= u.hour < 10)


def _cmd(step, r):
    s = r.get("slug")
    if step == "anlegen":
        return [PY, os.path.join("tools", "s100_anlegen.py"), "--gutenberg", r["gutenberg_id"]]
    if step == "text":
        return [PY, "run.py", s, "--line", "audio", "--to", "400", "--live"]
    if step == "klappentext_cover":
        if r.get("cover_neu"):        # Cover-Tor abgelehnt -> neue Illustration
            return [PY, "-m", "pipeline.s610_cover", s, "--force"]
        kt = r.get("kt_pruefung")
        if kt and not kt.get("ok"):   # Klappentext da, aber Pruefung nicht bestanden -> nur reparieren
            return [PY, "-m", "pipeline.s600_klappentext", s, "--pruefen"]
        return [PY, "run.py", s, "--line", "epub", "--from", "600", "--to", "610", "--live"]
    if step == "cover_final":
        return [PY, "-m", "pipeline.s615_cover_final", s]
    if step == "audio_de":
        return [PY, "run.py", s, "--line", "audio", "--from", "500", "--to", "500",
                "--lang", "de", "--live"]
    if step == "titel":
        return [PY, os.path.join("tools", "titel_auto.py"), s]
    if step == "woerter":
        return [PY, "-m", "pipeline.s340_wortalignment", s]
    if step in ("wortzeit_en", "wortzeit_de"):
        return [PY, "-m", "pipeline.s520_wortzeiten", s, "--lang", step[-2:]]
    if step == "export":
        return [PY, "run.py", s, "--line", "epub", "--from", "620", "--to", "630", "--live"]
    if step == "demo":
        return [PY, os.path.join("tools", "export_demo.py"), s, DEMO_DIR]
    raise ValueError(step)


# Bahnen: je Ressource ein Arbeiter -> lange Text-Jobs blockieren keine Cover/Exporte.
LANES = {
    "anlegen": "netz",
    "titel": "netz",
    "woerter": "deepseek",
    "wortzeit_en": "align",
    "wortzeit_de": "align",
    "text": "deepseek",
    "klappentext_cover": "gemini",
    "cover_final": "export",
    "audio_de": "tts",
    "export": "export",
    "demo": "export",
}
# Mehrere Plaetze je Bahn: DeepSeek verkraftet parallele Werke (je Werk weiter nur ein Schritt)
SLOTS = {"deepseek": ["deepseek", "deepseek2", "deepseek3", "deepseek4", "deepseek5", "deepseek6"]}
# 11.10.2026: Audio DE (Thorsten) pausiert -- Vertonung kuenftig mit designten Stimmen (Stage 57/58)
# Musterwerke zuerst (CK, 11.10.2026)
PRIO_SLUGS = ["alice-s-adventures-in-wonderland", "the-hound-of-the-baskervilles", "as-you-like-it"]
SCHRITTE_PAUSIERT = {"audio_de", "wortzeit_de", "wortzeit_en"}   # titel: Wikidata 429 -> spaeter langsam nachholen
LANE_NAMEN = {"netz": "Anlegen + Titel", "deepseek": "Text (DeepSeek) 1",
              "deepseek2": "Text (DeepSeek) 2", "deepseek3": "Text (DeepSeek) 3",
              "deepseek4": "Text (DeepSeek) 4", "deepseek5": "Text (DeepSeek) 5", "deepseek6": "Text (DeepSeek) 6", "gemini": "Klappentext + Cover (Gemini)",
              "tts": "Audio DE (Thorsten)", "align": "Wortzeiten (CPU)", "export": "Export + Demo"}
AUFTRAEGE = os.path.join(BASE, "daten", "auftraege.json")


class Runner:
    """Mehrere Jobs gleichzeitig: je Bahn ein Job, je Werk immer nur ein Schritt zur Zeit.
    Innerhalb einer Bahn: kuerzeste Werke (Woerter) zuerst. Auftraege ueberstehen Neustart."""

    def __init__(self):
        self.lk = threading.Lock()
        self.aktiv = []            # keys, die laufen sollen (bis Tor/fertig)
        self.wartend = set()       # keys, die an einem Tor halten -> nach Freigabe weiter
        self.nebenzeit = True
        self.stop_flag = False
        self.running = {}          # lane -> {"key","titel","step","log","start","proc"}
        self.history = []
        self.wake = threading.Event()
        self.pruefen = set()       # (key, step) gerade erfolgreich -> muss danach erledigt sein
        self._load()
        threading.Thread(target=self._dispatch, daemon=True).start()

    # -- Persistenz --
    def _load(self):
        d = _load(AUFTRAEGE, {})
        self.aktiv = d.get("aktiv", [])
        self.wartend = set(d.get("wartend", []))
        self.nebenzeit = d.get("nebenzeit", True)

    def _save(self):
        try:
            tmp = AUFTRAEGE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"aktiv": self.aktiv, "wartend": sorted(self.wartend),
                           "nebenzeit": self.nebenzeit}, f, ensure_ascii=False, indent=1)
            os.replace(tmp, AUFTRAEGE)
        except Exception:
            pass

    # -- API --
    def state(self):
        with self.lk:
            lanes = []
            for lane, name in LANE_NAMEN.items():
                j = self.running.get(lane)
                log = ""
                if j and j.get("log") and os.path.exists(j["log"]):
                    try:
                        with open(j["log"], encoding="utf-8", errors="replace") as f:
                            log = f.read()[-3000:]
                    except Exception:
                        pass
                lanes.append({"lane": lane, "name": name,
                              "job": {k: v for k, v in j.items() if k != "proc"} if j else None,
                              "log": log})
            laufend = {j["key"] for j in self.running.values()}
            return {"lanes": lanes, "queue": [k for k in self.aktiv if k not in laufend],
                    "wartend": sorted(self.wartend), "history": self.history[-40:],
                    "nebenzeit": self.nebenzeit, "nebenzeit_jetzt": nebenzeit_jetzt(),
                    "stop": self.stop_flag, "laeuft": bool(self.running),
                    "current": next(iter(self.running.values()), None) and
                               {k: v for k, v in next(iter(self.running.values())).items() if k != "proc"},
                    "n_laufend": len(self.running)}

    def add(self, keys, nebenzeit):
        with self.lk:
            for k in keys:
                self.wartend.discard(k)
                if k not in self.aktiv:
                    self.aktiv.append(k)
            self.nebenzeit = nebenzeit
            self.stop_flag = False
            self._save()
        self.wake.set()

    def stop(self):
        """Keine neuen Jobs mehr starten; laufende Schritte duerfen zu Ende laufen."""
        with self.lk:
            self.stop_flag = True
            self.aktiv.clear()
            self._save()

    def _note(self, key, titel, msg):
        self.history.append({"zeit": time.strftime("%H:%M:%S"), "key": key, "titel": titel, "msg": msg})

    # -- Verteiler --
    def _dispatch(self):
        while True:
            self.wake.wait(timeout=30)
            self.wake.clear()
            try:
                self._tick()
            except Exception as ex:
                self._note("-", "Cockpit", f"Verteiler-Fehler: {ex}")

    def _tick(self):
        with self.lk:
            if self.stop_flag or not self.aktiv:
                return
            aktiv = list(self.aktiv)
            laufend = {(j["key"], j["step"]) for j in self.running.values()}
            keys_laufend = {j["key"] for j in self.running.values()}
            frei = [l for l in LANE_NAMEN if l not in self.running]
        rows = {r["key"]: r for r in scan() if r["key"] in aktiv}
        kandidaten = {}   # lane -> [(woerter, key, row, step)]
        for key in aktiv:
            r = rows.get(key)
            if not r:
                with self.lk:
                    if key in self.aktiv: self.aktiv.remove(key)
                continue
            # Schutz gegen Endlosschleife: Schritt meldete Erfolg, ist aber nicht erledigt
            ohne_wirkung = [x for (k2, x) in list(self.pruefen) if k2 == key and x in r.get("moeglich", [])]
            for (k2, x) in [p for p in list(self.pruefen) if p[0] == key]:
                self.pruefen.discard((k2, x))
            if ohne_wirkung:
                self._drop(key, r, f"Schritt {ohne_wirkung[0]} ohne Wirkung (Erfolg gemeldet, aber nicht erledigt) - pruefen")
                continue
            schritte = [x for x in r.get("moeglich", []) if (key, x) not in laufend]
            if not schritte and key not in keys_laufend:
                kind, what = r["naechster"]
                label = dict((k, l) for k, _t, l in FLOW).get(what, "")
                msg = {"gate": f"wartet am Tor: {label}", "blockiert": f"abgelehnt am Tor: {label}",
                       "fertig": "fertig"}.get(kind, "wartet")
                with self.lk:
                    if key in self.aktiv: self.aktiv.remove(key)
                    if r.get("tore_offen"): self.wartend.add(key)
                    self._save()
                self._note(key, r["titel"], msg)
                continue
            for what in schritte:
                if what in SCHRITTE_PAUSIERT:
                    continue
                if what != "anlegen" and not r.get("slug"):
                    continue
                if what == "audio_de" and r.get("audio_de_gemischt"):
                    self._drop(key, r, "angehalten: Gemini-Teilvertonung vorhanden - manuell entscheiden")
                    break
                lane = LANES.get(what, "export")
                if not [sl for sl in SLOTS.get(lane, [lane]) if sl in frei]:
                    continue
                if what in DEEPSEEK_STEPS and self.nebenzeit and not nebenzeit_jetzt():
                    continue
                prio = 0 if r.get("slug") in PRIO_SLUGS else 1
                kandidaten.setdefault(lane, []).append(((prio, r.get("woerter") or 10**9), key, r, what))
        for lane, liste in kandidaten.items():
            liste.sort(key=lambda x: x[0])           # kuerzeste zuerst
            plaetze = [sl for sl in SLOTS.get(lane, [lane]) if sl in frei]
            for platz, (_w, key, r, step) in zip(plaetze, liste):
                self._start(platz, key, r, step)

    def _drop(self, key, r, msg):
        with self.lk:
            if key in self.aktiv: self.aktiv.remove(key)
            self._save()
        self._note(key, r["titel"], msg)

    def _start(self, lane, key, r, step):
        os.makedirs(LOGDIR, exist_ok=True)
        name = (r.get("slug") or key).replace(":", "_")
        log = os.path.join(LOGDIR, f"{name}_{step}_{time.strftime('%Y%m%d_%H%M%S')}.log")
        job = {"key": key, "titel": r["titel"], "step": step, "log": log, "start": time.strftime("%H:%M")}
        with self.lk:
            self.running[lane] = job
        threading.Thread(target=self._exec, args=(lane, job, r), daemon=True).start()

    def _exec(self, lane, job, r):
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1",
                   READLAYER_BOOK=r.get("slug") or "")   # Kostenzaehler bei direkt gestarteten Stages
        cmd = _cmd(job["step"], r)
        ok = False
        try:
            with open(job["log"], "w", encoding="utf-8") as f:
                f.write("$ " + " ".join(cmd) + "\n"); f.flush()
                p = subprocess.Popen(cmd, cwd=BASE, stdout=f, stderr=subprocess.STDOUT, env=env)
                job["proc"] = p
                rc = p.wait()
                f.write(f"\n=== Exitcode {rc} ===\n")
            ok = rc == 0
            if ok:
                with open(job["log"], encoding="utf-8", errors="replace") as f:
                    ok = "[FEHLER]" not in f.read()
        except Exception as ex:
            self._note(job["key"], job["titel"], f"Startfehler {job['step']}: {ex}")
        with self.lk:
            self.running.pop(lane, None)
            if ok:
                self.pruefen.add((job["key"], job["step"]))
            if not ok and job["key"] in self.aktiv:
                self.aktiv.remove(job["key"])
            self._save()
        self._note(job["key"], job["titel"], f"{job['step']} fertig" if ok else f"Fehler in Schritt {job['step']} - siehe Log")
        self.wake.set()


RUNNER = Runner()


# ------------------------------------------------------------------ Hoerspiel-Pruefung (Tor nach dem Overlay)
# Quelle: tools/trennung_auswerten.py schreibt casting.json ensemble[].pruefung[lg]; hier entscheidet CK je Figur.
GPU_MESSUNG = os.path.join(BASE, "gpu_messung")
HS_STUFEN = {1: [1.05, 1.10], -1: [0.97, 0.94]}   # wie trennung_auswerten.STUFEN (Natuerlichkeitsgrenzen)
_HS_LOCK = threading.Lock()


def _casting_pfad(slug):
    bdir = _book_dir(slug, _load_cached(INDEX, {"books": {}}))
    return os.path.join(bdir, "work", "casting.json") if bdir else None


def hoerspiel_items():
    """Je Werk und Sprache mit Pruefung: Figuren mit Messwerten, Urteil, Hoerproben, Entscheidung."""
    out = []
    if not os.path.isdir(GPU_MESSUNG):
        return out
    idx = _load_cached(INDEX, {"books": {}})
    for d in sorted(os.listdir(GPU_MESSUNG)):
        if not os.path.isfile(os.path.join(GPU_MESSUNG, d, "auswertung.json")) or "_" not in d:
            continue
        slug, _, lg = d.rpartition("_")
        bdir = _book_dir(slug, idx)
        if not bdir:
            continue
        cast = _load(os.path.join(bdir, "work", "casting.json"), {})
        figs = []
        for e in (cast.get("plan") or {}).get("ensemble", []):
            p = (e.get("pruefung") or {}).get(lg)
            if p:
                figs.append(dict(p, figur=e["figur"], stimme=e.get("stimme"),
                                 umbesetzung=(e.get("umbesetzung") or {}).get(lg)))
        if not figs:
            continue
        b = _load_cached(os.path.join(bdir, "book.json"), {})
        fde = next((f for f in b.get("fassungen", []) if f.get("sprache") == "de"), {}) or {}
        bericht = os.path.join(GPU_MESSUNG, d, "BERICHT_trennung.md")
        out.append({"slug": slug, "lg": lg, "titel": fde.get("titel") or b.get("titel_original") or slug,
                    "titel_original": b.get("titel_original") or "", "runde": figs[0].get("runde"),
                    "datum": figs[0].get("datum"), "tor": (cast.get("hoerspiel_tor") or {}).get(lg, "offen"),
                    "bericht": _rel(bericht) if os.path.exists(bericht) else None, "figuren": figs})
    return out


def hoerspiel_entscheiden(slug, lg, figuren, aktion, notiz=""):
    """aktion: freigeben | nachrunde | umbesetzen | offen (zuruecknehmen). Nachrunde setzt korrektur[lg] eine Stufe
    weiter (hoechstens bis zur Natuerlichkeitsgrenze); danach Overlay neu + start_trennung_messen.bat."""
    if aktion == "waehlen":   # Kandidat der Umbesetzung besetzen (tools/umbesetzen.py --waehlen)
        if len(figuren) != 1 or not notiz:
            raise ValueError("waehlen: genau eine Figur + stimme")
        r = subprocess.run([PY, os.path.join("tools", "umbesetzen.py"), slug, lg, figuren[0], "--waehlen", notiz],
                           cwd=BASE, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        if r.returncode:
            raise ValueError((r.stderr or r.stdout)[-400:])
        return {"ok": True, "meldung": [r.stdout.strip()]}
    if aktion not in ("freigeben", "nachrunde", "umbesetzen", "offen"):
        raise ValueError("aktion")
    cp = _casting_pfad(slug)
    if not cp or not os.path.exists(cp):
        raise ValueError("casting.json fehlt")
    with _HS_LOCK:
        cast = _load(cp, {})
        zeit = dt.datetime.now().isoformat(timespec="seconds")
        meldung = []
        for e in cast["plan"]["ensemble"]:
            p = (e.get("pruefung") or {}).get(lg)
            if not p or e["figur"] not in figuren:
                continue
            if aktion == "nachrunde":
                neu = p.get("korrektur_neu")
                if neu is None:
                    r, ff = p.get("richtung") or 1, float(p.get("korrektur") or 1.0)
                    weiter = [x for x in HS_STUFEN[r] if (x > ff + 1e-6 if r > 0 else x < ff - 1e-6)]
                    if not weiter:
                        meldung.append(f"{e['figur']}: Grenze erreicht ({ff}) - umbesetzen")
                        continue
                    neu = weiter[0]
                k = e.get("korrektur") or {}
                if k and not any(x in k for x in ("de", "en")):
                    k = {lg: k}
                k[lg] = {"formant_faktor": neu, "tonhoehe_ht": 0, "grund": "Nachrunde (CK, Cockpit)",
                         "quelle": f"Hoerspiel-Pruefung {p.get('runde')}, {zeit[:10]}"}
                e["korrektur"] = k
                p["korrektur_neu"] = neu
            p["entscheidung"] = None if aktion == "offen" else {"aktion": aktion, "zeit": zeit, "notiz": notiz}
        alle = [(e.get("pruefung") or {}).get(lg) for e in cast["plan"]["ensemble"]]
        alle = [p for p in alle if p]
        ents = [(p.get("entscheidung") or {}).get("aktion") for p in alle]
        tor = "offen" if not all(ents) else ("frei" if all(a == "freigeben" for a in ents) else "entschieden")
        cast.setdefault("hoerspiel_tor", {})[lg] = tor
        tmp = cp + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cast, f, ensure_ascii=False, indent=1)
        os.replace(tmp, cp)
    return {"ok": True, "tor": tor, "meldung": meldung}


# ------------------------------------------------------------------ Sprachpruefung (tools/sprachpruefung.py)
def sprach_items(n=80, ab=0):
    """Je Werk/Sprache mit work/sprachpruefung_<lg>.json: Zusammenfassung, Namen-Tabelle, Rangliste (verdaechtigste zuerst)."""
    out = []
    idx = _load_cached(INDEX, {"books": {}})
    for slug in idx.get("books", {}):
        bdir = _book_dir(slug, idx)
        if not bdir or not os.path.isdir(os.path.join(bdir, "work")):
            continue
        for f in sorted(os.listdir(os.path.join(bdir, "work"))):
            m = re.fullmatch(r"sprachpruefung_(\w+)\.json", f)
            if not m:
                continue
            d = _load_cached(os.path.join(bdir, "work", f), {})
            S, U = d.get("saetze", {}), d.get("urteile", {})
            rang = sorted(S.items(), key=lambda kv: -kv[1].get("verdacht", 0))
            b = _load_cached(os.path.join(bdir, "book.json"), {})
            out.append({"slug": slug, "lg": m.group(1), "titel": b.get("titel_original") or slug, "datum": d.get("datum"),
                        "n": d.get("n"), "stufen": d.get("stufen"), "quote_mit_namen": d.get("quote_mit_namen"),
                        "quote_ohne_namen": d.get("quote_ohne_namen"), "namen": d.get("namen", [])[:25],
                        "urteile": {"kippt": sum(1 for v in U.values() if v == "kippt"),
                                    "ok": sum(1 for v in U.values() if v == "ok")},
                        "liste": [dict(s, tag=t, urteil=U.get(t)) for t, s in rang[ab:ab + n]]})
    return out


def sprach_urteil(slug, lg, tag, urteil):
    bdir = _book_dir(slug, _load_cached(INDEX, {"books": {}}))
    p = os.path.join(bdir, "work", f"sprachpruefung_{lg}.json")
    with _HS_LOCK:
        d = _load(p, {})
        u = d.setdefault("urteile", {})
        if urteil in ("kippt", "ok"):
            u[tag] = urteil
        else:
            u.pop(tag, None)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    return {"ok": True}


# ------------------------------------------------------------------ HTTP
MIME = {".html": "text/html; charset=utf-8", ".png": "image/png", ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg", ".webp": "image/webp", ".wav": "audio/wav", ".mp3": "audio/mpeg",
        ".json": "application/json", ".epub": "application/epub+zip", ".log": "text/plain; charset=utf-8"}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        try:
            if u.path in ("/", "/index.html"):
                with open(os.path.join(HERE, "index.html"), "rb") as f:
                    return self._send(200, f.read(), MIME[".html"])
            if u.path == "/api/katalog":
                hs = hoerspiel_items()
                return self._send(200, {"werke": scan(), "flow": FLOW, "extra": EXTRA_GATES,
                                        "hoerspiel_offen": sum(1 for w in hs if w["tor"] == "offen")})
            if u.path == "/api/hoerspiel":
                return self._send(200, hoerspiel_items())
            if u.path == "/api/sprache":
                return self._send(200, sprach_items(int(q.get("n", ["80"])[0]), int(q.get("ab", ["0"])[0])))
            if u.path == "/api/tor":
                return self._send(200, gate_items(q.get("g", [""])[0]))
            if u.path == "/api/lauf":
                return self._send(200, RUNNER.state())
            if u.path == "/datei":
                p = os.path.normpath(os.path.join(BASE, q.get("p", [""])[0]))
                if not p.startswith(BASE) or not os.path.isfile(p):
                    return self._send(404, {"fehler": "nicht gefunden"})
                with open(p, "rb") as f:
                    return self._send(200, f.read(),
                                      MIME.get(os.path.splitext(p)[1].lower(), "application/octet-stream"))
            return self._send(404, {"fehler": "unbekannt"})
        except Exception as ex:
            return self._send(500, {"fehler": str(ex)})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            data = {}
        try:
            if self.path == "/api/freigabe":
                gate, status = data["gate"], data["status"]
                if status not in ("frei", "abgelehnt", "offen"):
                    return self._send(400, {"fehler": "status"})
                d = _load(FREIGABEN, {})
                for k in data.get("keys", []):
                    d.setdefault(k, {})[gate] = {"status": status, "notiz": data.get("notiz", ""),
                                                 "zeit": dt.datetime.now().isoformat(timespec="seconds")}
                _save_freigaben(d)
                # Werke, die im Lauf an diesem Tor angehalten haben, laufen nach Freigabe weiter
                if status == "frei":
                    weiter = [k for k in data.get("keys", []) if k in RUNNER.wartend]
                    if weiter:
                        RUNNER.add(weiter, RUNNER.nebenzeit)
                RUNNER.wake.set()
                return self._send(200, {"ok": True, "n": len(data.get("keys", []))})
            if self.path == "/api/sprache":
                return self._send(200, sprach_urteil(data["slug"], data["lg"], data["tag"], data.get("urteil")))
            if self.path == "/api/hoerspiel":
                try:
                    return self._send(200, hoerspiel_entscheiden(data["slug"], data["lg"], data.get("figuren", []),
                                                                 data["aktion"], data.get("stimme") or data.get("notiz", "")))
                except ValueError as ex:
                    return self._send(200, {"fehler": str(ex)})
            if self.path == "/api/lauf":
                RUNNER.add(data.get("keys", []), bool(data.get("nebenzeit", True)))
                return self._send(200, {"ok": True})
            if self.path == "/api/stop":
                RUNNER.stop()
                return self._send(200, {"ok": True})
            return self._send(404, {"fehler": "unbekannt"})
        except Exception as ex:
            return self._send(500, {"fehler": str(ex)})


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"READ LAYER Cockpit: http://127.0.0.1:{PORT}   (Strg+C beendet)")
    print(f"Python fuer Pipeline-Laeufe: {PY}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
