"""STAGE 710 — Auslieferung TAELLA (Umbau Phase 2, AP 710a, 03.11.2026; GATE_KATALOG.md Zeile 710)
Funktion:      Liefert die von Gate 700 freigegebenen TAELLA-Produkte eines Werks an ein Ziel aus: Cloud (GCS) oder
               lokal (Ordner public/ der TAELLA-App) im selben Paketformat. Kanaele EPUB/Extern folgen mit AP 710b
               (bis dahin Gate Mensch "noch nicht gebaut").
Wirkungsweise: Ein Gate je Scope "<lg>:taella", nur Sprachen mit lieferbarem 700-Scope (s700_guard.lieferbar).
               Paket je Sprache: manifest_<lg>.json (Schema 2, Obermenge des Altformats), audio/<lg>/<tid>.mp3 (Hoerbuch,
               Endfassung 530), audio_hoerspiel/<lg>/<tid>.mp3 (Hoerspiel), wordtimes_<lg>[_hoerspiel].json (520),
               cover_<lg>.jpg (615 text bzw. audio), teaser/<lg>/ (640); je Werk blurb.json (600) und Katalogeintrag.
               Anker je Zielsprache align_<lg> aus 340 mit Wortzeiten aus 520/525 (je_ziel); "align" = erste
               Zielsprache (Altschnittstelle App bis AP 710c). Pausen 400, Sprechergeschlecht 410/210, Rollen 420.
               Manifest work/710_export.json je Ziel x Scope: Datei -> {quelle_hash, md5, groesse}; nur Geaendertes wird
               hochgeladen, Verwaistes geloescht; MP3-Zwischenstand work/_710/<lg>/<spur>/ (Hash Endfassung + Bitrate).
Gate:          je Scope: Gate 700 frei + Scope lieferbar, Text/Audio/Wortzeit-Abdeckung laut Bestellung 100 %, Manifest
               besteht Schema-Pruefung, jede Datei im Ziel mit Groesse/MD5 = lokal, Upload-Fehler (1x neu) = 0,
               Katalog stimmt (privat nie im oeffentlichen Katalog) -> sonst Stopp. Erstes Freischalten im oeffentlichen
               Katalog -> Mensch (--freigeben, einmal je Werk; Update danach auto); Mandant verlag -> immer Mensch
               (Freigabe gilt bei gleichem ausgabe_hash). Katalog nur bei unveraenderter Generation (1x neu gelesen).
Ziel-Adapter:  GCS (Bucket config.GCS_BUCKET, ifGenerationMatch) | Lokal (Ordner config.APP_PUBLIC, Standard
               ../taella-app/public; demo/<slug>/ bzw. privat/<uid>/<slug>/). status.json nur beim Standardziel
               (config.AUSLIEFERUNG_ZIEL, Standard gcs); andere Ziele nur Manifest + Bericht.
Eingang:       Gate 700 + work/700_guard.json, book.json (Bestellung, Mandant 080), work/330_rueckuebersetzung.json
               (ohne Uebersetzung work/200_tagging.json), 340_wortalignment.json, 400_regie.json, 530_pruefung_<lg>.json +
               audio_final/ bzw. hoerspiel_final/, 520_wortzeiten_<lg>[_hoerspiel].json, 525_wortbruecke.json,
               600_klappentext.json, 615 Cover, fassungen/<lg>/blurb/ (640), casting.json, 420_sprecher.json.
Ausgabe:       Ziel (s. oben), work/710_export.json, Gate je Scope in status.json, Regler work/710_entscheidungen.json.
Regler:        --ziel gcs|lokal[:PFAD], --lang LG, --bitrate 96k (Kanal taella), --nur-manifest (Audio nicht neu
               umwandeln/hochladen), --freigeben (erstes Freischalten/Verlag), --zurueckziehen --grund TEXT (Werk aus
               dem Katalog nehmen, Dateien bleiben), --dry (Probelauf ohne Upload/Status).
Kosten:        0 $ LLM; GCS-Bytes je Lauf in kosten.jsonl unter Stage 710 (gcs_upload_gb).
Aufruf:        py -3.11 -m pipeline.s710_cloud_export <werk> [Regler] [--wer CK]
Exit:          0 auto, 2 Stopp, 3 Mensch, 1 Fehler.
"""
import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from pipeline import bestellung, gate, manifest, status

STAGE = "710"
VERSION = 1
APP_SCHEMA = 2                      # Manifest-Schema, das die App kennt (loader.js prueft ab AP 710c)
AUDIO = ("hoerbuch", "hoerspiel")
GEBAUT = ("taella",)                # Kanaele dieser Stage; epub/extern folgen mit AP 710b
NO_AUDIO_TYPES = set(getattr(config, "NO_AUDIO_TYPES", ["p"]))
ERZ_NAMEN = {"erzaehler", "erzähler", "narrator", "narration", "narrateur", "narratore", "narrador"}
WERK = "_werk"                      # Scope werkweiter Dateien (blurb.json)
MANIFEST_PFLICHT = ("schema", "werk_id", "book_slug", "sprache", "quellsprache", "originalsprache", "sprachen", "titel",
                    "autor", "saetze", "audio_vollstaendig", "audio_count", "spuren")
KNOTEN_PFLICHT = ("tag_id", "typ", "kapitel", "text", "audio_path", "pause_after_ms")


def bitrate_std():
    return dict(getattr(config, "AUSLIEFERUNG_BITRATE", None) or {"taella": "128k", "epub": "64k", "extern": "192k"})


# ============================================================ Ablage
def pfad(werk):
    return config.work_path(werk, "710_export")


def entscheidungen_pfad(werk):
    return config.work_path(werk, "710_entscheidungen")


def _json(p, leer=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return leer


def entscheidungen(werk):
    return _json(entscheidungen_pfad(werk), {}) or {}


def _entscheidung(werk, wer, aktion, **kw):
    e = entscheidungen(werk)
    e.update(kw)
    e.setdefault("protokoll", []).append({"wer": wer, "aktion": aktion, "wann": manifest.jetzt(),
                                         **{k: v for k, v in kw.items() if k != "freigabe"}})
    manifest.json_atomar(entscheidungen_pfad(werk), e, indent=1)
    return e


def _jbytes(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def md5_bytes(b):
    return hashlib.md5(b).hexdigest()


def md5_datei(p, block=1 << 20):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(block), b""):
            h.update(c)
    return h.hexdigest()


# ============================================================ Ziel-Adapter
class UploadFehler(RuntimeError):
    pass


class KatalogKonflikt(RuntimeError):
    pass


class Ziel:
    """Schnittstelle: inventar(prefix), hochladen, schreiben, loeschen, katalog_lesen/-schreiben (mit Generation).
    Pfade relativ zur Zielwurzel mit "/"."""
    art = None

    def __init__(self):
        self.bytes, self.hochgeladen, self.geloescht = 0, 0, 0

    def kennung(self):
        raise NotImplementedError

    def werk_prefix(self, werk_id, slug, uid=None):
        raise NotImplementedError

    def katalog_rel(self, uid=None):
        raise NotImplementedError


class GCS(Ziel):
    art = "gcs"

    def __init__(self, bucket=None, client=None):
        super().__init__()
        if client is None:
            try:
                from google.cloud import storage
            except ImportError:
                raise RuntimeError("google-cloud-storage nicht installiert (pip install google-cloud-storage)")
            client = storage.Client()
        self.client = client
        self.name = bucket or getattr(config, "GCS_BUCKET", "")
        if not self.name:
            raise RuntimeError("config.GCS_BUCKET nicht gesetzt")
        self.b = client.bucket(self.name)

    def kennung(self):
        return f"gcs:{self.name}"

    def werk_prefix(self, werk_id, slug, uid=None):
        return f"users/{uid}/works/{slug}" if uid else f"werke/{werk_id}"

    def katalog_rel(self, uid=None):
        return f"users/{uid}/catalog.json" if uid else "catalog.json"

    @staticmethod
    def _hex(b64):
        return base64.b64decode(b64).hex() if b64 else None

    def inventar(self, prefix):
        return {bl.name: (self._hex(bl.md5_hash), bl.size)
                for bl in self.client.list_blobs(self.b, prefix=prefix.rstrip("/") + "/")}

    def hochladen(self, quelle, rel, ctype=None):
        self.b.blob(rel).upload_from_filename(quelle, content_type=ctype)

    def schreiben(self, data, rel, ctype=None):
        self.b.blob(rel).upload_from_string(data, content_type=ctype)

    def loeschen(self, rel):
        try:
            self.b.blob(rel).delete()
        except Exception as e:                      # NotFound = schon weg
            if type(e).__name__ != "NotFound":
                raise

    def katalog_lesen(self, rel):
        bl = self.b.get_blob(rel)
        if bl is None:
            return None, 0
        return json.loads(bl.download_as_text()), bl.generation

    def katalog_schreiben(self, rel, obj, generation):
        try:
            self.b.blob(rel).upload_from_string(json.dumps(obj, ensure_ascii=False, indent=1),
                                                content_type="application/json", if_generation_match=generation)
        except Exception as e:
            if type(e).__name__ == "PreconditionFailed":
                raise KatalogKonflikt(rel)
            raise


class Lokal(Ziel):
    """Ordner public/ der TAELLA-App: demo/<slug>/ (Katalog demo/katalog.json), privat/<uid>/<slug>/."""
    art = "lokal"

    def __init__(self, wurzel=None):
        super().__init__()
        self.wurzel = os.path.abspath(wurzel or getattr(config, "APP_PUBLIC", None) or
                                      os.path.join(os.path.dirname(config.BASE_DIR), "taella-app", "public"))

    def kennung(self):
        return f"lokal:{self.wurzel}"

    def werk_prefix(self, werk_id, slug, uid=None):
        return f"privat/{uid}/{slug}" if uid else f"demo/{slug}"

    def katalog_rel(self, uid=None):
        return f"privat/{uid}/katalog.json" if uid else "demo/katalog.json"

    def _p(self, rel):
        return os.path.join(self.wurzel, *rel.split("/"))

    def inventar(self, prefix):
        out, basis = {}, self._p(prefix)
        for dp, _, fs in os.walk(basis):
            for f in fs:
                p = os.path.join(dp, f)
                rel = os.path.relpath(p, self.wurzel).replace(os.sep, "/")
                out[rel] = (md5_datei(p), os.path.getsize(p))
        return out

    def _ersetzen(self, rel, schreib):
        p = self._p(rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp710"
        schreib(tmp)
        os.replace(tmp, p)

    def hochladen(self, quelle, rel, ctype=None):
        self._ersetzen(rel, lambda t: shutil.copyfile(quelle, t))

    def schreiben(self, data, rel, ctype=None):
        def w(t):
            with open(t, "wb") as f:
                f.write(data)
        self._ersetzen(rel, w)

    def loeschen(self, rel):
        p = self._p(rel)
        if os.path.exists(p):
            os.remove(p)

    def katalog_lesen(self, rel):
        p = self._p(rel)
        if not os.path.exists(p):
            return None, 0
        return _json(p, {}) or {}, os.stat(p).st_mtime_ns

    def katalog_schreiben(self, rel, obj, generation):
        p = self._p(rel)
        ist = os.stat(p).st_mtime_ns if os.path.exists(p) else 0
        if ist != generation:
            raise KatalogKonflikt(rel)
        self.schreiben(json.dumps(obj, ensure_ascii=False, indent=1).encode("utf-8"), rel)


def ziel_aus(name=None):
    name = name or getattr(config, "AUSLIEFERUNG_ZIEL", "gcs")
    if name == "gcs":
        return GCS()
    if name == "lokal" or name.startswith("lokal:"):
        return Lokal(name.split(":", 1)[1] if ":" in name else None)
    raise ValueError(f"Ziel {name!r} unbekannt (gcs | lokal[:PFAD])")


def standardziel():
    return getattr(config, "AUSLIEFERUNG_ZIEL", "gcs").split(":", 1)[0]


def _zweimal(fn, *a):
    """Upload-Fehler -> 1x automatisch neu, dann UploadFehler."""
    try:
        return fn(*a)
    except Exception:
        try:
            return fn(*a)
        except Exception as e:
            raise UploadFehler(f"{type(e).__name__}: {e}")


# ============================================================ MP3
def mp3_ffmpeg(quelle, ziel, bitrate):
    os.makedirs(os.path.dirname(ziel), exist_ok=True)
    tmp = ziel + ".tmp.mp3"
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", quelle, "-codec:a", "libmp3lame", "-b:a", bitrate,
                        "-map_metadata", "-1", tmp], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(tmp):
        raise RuntimeError(f"ffmpeg {os.path.basename(quelle)}: {r.stderr.strip()[:200]}")
    os.replace(tmp, ziel)


_mp3 = mp3_ffmpeg                   # Tests ersetzen den Wandler


# ============================================================ Eingaenge
class Daten:
    """Alle Eingaenge eines Werks, einmal geladen."""

    def __init__(self, werk, b):
        self.werk, self.b, self.src = werk, b, b.quellsprache
        w = lambda n: _json(config.work_path(werk, n))
        self.d330 = w("330_rueckuebersetzung")
        self.text_quelle = "330" if self.d330 else "200"
        self.text = self.d330 or w("200_tagging") or {}
        self.d340 = w("340_wortalignment") or {}
        self.d400 = w("400_regie") or {}
        self.d525 = w("525_wortbruecke") or {}
        self.d600 = w("600_klappentext") or {}
        self.d420 = w("420_sprecher") or {}
        self.casting = _json(os.path.join(config.work_dir(werk), "casting.json")) or {}
        self.d520 = {}
        for lg in b.sprachen:
            for spur in AUDIO:
                n = f"520_wortzeiten_{lg}{'_hoerspiel' if spur == 'hoerspiel' else ''}"     # = s520.pfad
                self.d520[(lg, spur)] = ((_json(config.work_path(werk, n)) or {}).get("tags")) or {}
        self.m530 = {}

    @property
    def content(self):
        return self.text.get("content") or {}

    @property
    def meta(self):
        return self.text.get("meta") or {}

    def manifest530(self, lg):
        if lg not in self.m530:
            p = config.work_path(self.werk, f"530_pruefung_{lg}")
            self.m530[lg] = manifest.Manifest(self.werk, f"530_pruefung_{lg}", stage="530") if os.path.exists(p) \
                else None
        return self.m530[lg]

    def pause(self, tid, lg):
        pa = ((self.d400.get("production") or {}).get("pause_after_ms") or {}).get(tid)
        if isinstance(pa, dict):
            return pa.get(lg) or 0
        return pa or 0

    def audio_ids(self, lg):
        """Audio-Knoten (ohne Ansagen) in Hoerreihenfolge laut 400."""
        if not self.d400:
            return []
        from pipeline import s500_vertonung_gemini as s500
        return [u["id"] for u in s500.einheiten(self.d400, lg)[0] if u["typ"] != "ansage"]

    def geschlecht(self):
        """{Figur: m|w|n} aus casting.json (Steckbriefe 410), Rueckfall Profil 210 (gender)."""
        out = {}
        for f in ((self.casting.get("steckbriefe") or {}).get("figuren") or []):
            g = str(((f.get("merkmale") or {}).get("geschlecht")) or "").lower()[:1]
            if f.get("name") and g in ("m", "w", "n"):
                out[f["name"]] = g
        prof = ((self.d400.get("meta") or self.meta or {}).get("profile") or {}).get("characters") or {}
        if not prof:
            prof = ((_json(config.work_path(self.werk, "210_profil")) or {}).get("profile") or {}).get("characters") or {}
        for n, x in (prof.items() if isinstance(prof, dict) else []):
            g = str((x or {}).get("gender") or "").lower()[:1] if isinstance(x, dict) else ""
            g = {"f": "w"}.get(g, g)
            if g in ("m", "w", "n"):
                out.setdefault(n, g)
        return out

    def hoerspiel_sprecher(self, lg, tids):
        out = {}
        saetze = self.d420.get("saetze") or {}
        for t in tids:
            for seg in ((saetze.get(t) or {}).get(lg) or {}).get("seg") or []:
                s = seg.get("s")
                if s and s.lower() not in ERZ_NAMEN:
                    out[t] = s
                    break
        return out


def _slim(al, br, src, lg):
    """Anker auf die App-Felder: i, <src>_span, <lg>, <lg>_span (+ zspans, t, tz, ths, tzhs aus 525)."""
    k_src, k_tgt, k_tgt_span = f"{src}_span", lg, f"{lg}_span"          # = s340.schluessel(src, lg)
    bm = {x["i"]: x for x in (br or []) if isinstance(x, dict)}
    out = []
    for w in al:
        n = {"i": w.get("i"), k_src: w.get(k_src), k_tgt: w.get(k_tgt)}
        if w.get(k_tgt_span) is not None:
            n[k_tgt_span] = w[k_tgt_span]
        x = bm.get(w.get("i"))
        if x:
            if x.get("zspans") and n.get(k_tgt_span) is None:
                n[k_tgt_span] = x["zspans"][0]
            if len(x.get("zspans") or []) > 1:
                n["zspans"] = x["zspans"]
            for k in ("t", "tz", "ths", "tzhs"):
                if x.get(k):
                    n[k] = x[k]
        out.append(n)
    return out


def kompakt(tags):
    """520-Tags {tid: [{i, t0, t1}]} -> {tid: [t0 je Token, None = ohne Zeit]} (Format export_app)."""
    out = {}
    for tid, ws in (tags or {}).items():
        ws = [x for x in ws or [] if isinstance(x, dict) and x.get("i") is not None]
        if not ws:
            continue
        st = [None] * (max(x["i"] for x in ws) + 1)
        for x in ws:
            st[x["i"]] = x.get("t0")
        out[tid] = st
    return out


# ============================================================ Paket je Sprache
class Plan:
    """Dateien eines Scopes: rel (zum Werkordner) -> {art: mp3|kopie|json, quelle|daten, quelle_hash, ctype, cache}."""

    def __init__(self):
        self.dateien = {}
        self.befunde = []           # (name, text, ruecksprung)
        self.metriken = {}

    def json(self, rel, obj):
        data = _jbytes(obj)
        self.dateien[rel] = {"art": "json", "daten": data, "quelle_hash": md5_bytes(data),
                             "ctype": "application/json"}

    def kopie(self, rel, quelle, ctype=None):
        self.dateien[rel] = {"art": "kopie", "quelle": quelle, "quelle_hash": manifest.hash_datei(quelle),
                             "ctype": ctype}

    def mp3(self, rel, quelle, quelle_hash, cache, bitrate):
        self.dateien[rel] = {"art": "mp3", "quelle": quelle, "quelle_hash": manifest.hash_obj([quelle_hash, bitrate]),
                             "ctype": "audio/mpeg", "cache": cache, "bitrate": bitrate}


def inhalte_lieferbar(werk, lg):
    """{inhalt: [scopes]} der lieferbaren 700-Scopes (Kanal taella) einer Sprache."""
    from pipeline import s700_guard
    d = _json(s700_guard.pfad(werk), {}) or {}
    out = {}
    for sc in s700_guard.lieferbar(werk, lg=lg, kanal="taella"):
        x = (d.get("produkte") or {}).get(sc) or {}
        out.setdefault(x.get("inhalt") or "text", []).append(sc)
    return out


def taella_sprachen(b):
    return [lg for lg in b.sprachen if b.hat(sprache=lg, kanal="taella")]


def paket(D, lg, inhalte, werk_id, bitrate, titel, autor):
    """-> (Plan, manifest_obj). Pruefbefunde im Plan (Abdeckung Text/Audio/Wortzeiten)."""
    from pipeline import s615_cover_final as s615
    werk, b, src = D.werk, D.b, D.src
    P = Plan()
    hb = "hoerbuch" in inhalte or "hoerspiel" in inhalte     # Hoerspiel setzt die Erzaehlerspur voraus
    hs = "hoerspiel" in inhalte
    ziele = [z for z in taella_sprachen(b) if z != src]
    content, kap = D.content, D.meta.get("chapters") or {}
    m530 = D.manifest530(lg) if hb else None

    # ---- Audio Hoerbuch
    audio_rel, fehlt_audio = {}, []
    soll_audio = D.audio_ids(lg) if hb else []
    if hb and not D.d400:
        P.befunde.append(("regie", "400_regie.json fehlt (Audio bestellt)", "400"))
    if hb and m530 is None:
        P.befunde.append(("endfassung", f"530_pruefung_{lg}.json fehlt", "530"))
    for tid in soll_audio:
        k = f"hoerbuch/{tid}"
        e = m530.get(k) if m530 else None
        if not e or not m530.datei_aktuell(k):
            fehlt_audio.append(tid)
            continue
        rel = f"audio/{lg}/{tid}.mp3"
        P.mp3(rel, m530._abs(e["datei"]), e.get("datei_hash"),
              os.path.join(config.work_dir(werk), "_710", lg, "hoerbuch", f"{tid}.mp3"), bitrate)
        audio_rel[tid] = rel
    # ---- Audio Hoerspiel
    hs_rel, fehlt_hs = {}, []
    if hs and m530 is not None:
        for k in sorted(x for x in m530.eintraege if x.startswith("hoerspiel/")):
            tid = k.split("/", 1)[1]
            e = m530.get(k)
            if not e or not m530.datei_aktuell(k):
                fehlt_hs.append(tid)
                continue
            rel = f"audio_hoerspiel/{lg}/{tid}.mp3"
            P.mp3(rel, m530._abs(e["datei"]), e.get("datei_hash"),
                  os.path.join(config.work_dir(werk), "_710", lg, "hoerspiel", f"{tid}.mp3"), bitrate)
            hs_rel[tid] = rel
        if not hs_rel and not fehlt_hs:
            P.befunde.append(("hoerspiel", f"keine Hoerspiel-Endfassung {lg} in 530", "510"))
    # ---- Wortzeiten
    wt, wt_hs, fehlt_wt, fehlt_wths = {}, {}, [], []
    if hb:
        wt = kompakt(D.d520.get((lg, "hoerbuch")))
        fehlt_wt = [t for t in audio_rel if not wt.get(t)]
        P.json(f"wordtimes_{lg}.json", {"sprache": lg, "spur": "hoerbuch", "tags": wt})
    if hs:
        wt_hs = kompakt(D.d520.get((lg, "hoerspiel")))
        fehlt_wths = [t for t in hs_rel if not wt_hs.get(t)]
        P.json(f"wordtimes_{lg}_hoerspiel.json", {"sprache": lg, "spur": "hoerspiel", "tags": wt_hs})

    # ---- Saetze
    saetze, ohne_text = [], 0
    c340 = D.d340.get("content") or {}
    je_ziel = D.d525.get("je_ziel") or {}
    for tid, e in content.items():
        if not isinstance(e, dict):
            continue
        typ = e.get("type", "s")
        text = e.get(lg) or ""
        if not text and typ not in NO_AUDIO_TYPES:
            if lg != src and str(e.get(src) or "").strip():      # leerer Quellknoten (z. B. Kapitel ohne Titel) ok
                ohne_text += 1
            continue
        kk = tid.split("_")[0] if "_" in tid else ""
        n = {"tag_id": tid, "typ": typ, "kapitel": kap.get(kk) or kk, "text": text,
             "audio_path": audio_rel.get(tid, ""), "pause_after_ms": D.pause(tid, lg)}
        if tid in hs_rel:
            n["audio_hs_path"] = hs_rel[tid]
        for f in ("sprecher", "rolle"):
            if e.get(f):
                n[f] = e[f]
        if lg == src:
            erst = None
            for z in ziele:
                al = (c340.get(tid) or {}).get(f"align_{z}")
                if not al and z == (ziele[0] if ziele else None):
                    al = (c340.get(tid) or {}).get("align")
                if al:
                    s = _slim(al, ((je_ziel.get(z) or {}).get("tags") or {}).get(tid), src, z)
                    n[f"align_{z}"] = s
                    erst = erst or s
            if erst:
                n["align"] = erst
        saetze.append(n)
    if ohne_text:
        P.befunde.append(("text", f"{ohne_text} Knoten ohne Text {lg} (Quelle {D.text_quelle})",
                          "310" if lg != src else "200"))
    if fehlt_audio:
        P.befunde.append(("audio", f"Hoerbuch {lg}: {len(fehlt_audio)}/{len(soll_audio)} ohne aktuelle Endfassung "
                                   f"(z. B. {', '.join(fehlt_audio[:3])})", "530"))
    if fehlt_hs:
        P.befunde.append(("audio_hoerspiel", f"Hoerspiel {lg}: {len(fehlt_hs)} ohne aktuelle Endfassung "
                                             f"(z. B. {', '.join(fehlt_hs[:3])})", "530"))
    if fehlt_wt:
        P.befunde.append(("wortzeiten", f"Wortzeiten {lg}: {len(fehlt_wt)}/{len(audio_rel)} Saetze ohne Zeiten "
                                        f"(z. B. {', '.join(fehlt_wt[:3])})", "520"))
    if fehlt_wths:
        P.befunde.append(("wortzeiten_hoerspiel", f"Wortzeiten Hoerspiel {lg}: {len(fehlt_wths)} ohne Zeiten "
                                                  f"(z. B. {', '.join(fehlt_wths[:3])})", "520"))
    if lg == src and ziele and not any(f"align_{z}" in n for n in saetze for z in ziele):
        P.befunde.append(("anker", f"keine Anker align_{'/'.join(ziele)} im Manifest {lg}", "340"))

    # ---- Cover, Teaser
    var = "audio" if hb else "text"
    cp = s615.ausgabe_pfad(werk, lg, var)
    if os.path.exists(cp):
        P.kopie(f"cover_{lg}.jpg", cp, "image/jpeg")
    else:
        P.befunde.append(("cover", f"Cover {lg}:{var} fehlt ({os.path.relpath(cp, config.book_dir(werk))})", "615"))
    tdir = os.path.join(config.book_dir(werk), "fassungen", lg, "blurb")
    teaser = []
    for dp, _, fs in os.walk(tdir):
        for f in sorted(fs):
            if f.endswith((".tmp", ".part")):
                continue
            p = os.path.join(dp, f)
            rel = "teaser/" + lg + "/" + os.path.relpath(p, tdir).replace(os.sep, "/")
            P.kopie(rel, p, "audio/mpeg" if f.endswith(".mp3") else
                    "application/json" if f.endswith(".json") else None)
            teaser.append(rel)
    if not teaser:
        P.befunde.append(("teaser", f"Teaser {lg} fehlt (fassungen/{lg}/blurb/)", "640"))

    n_audio = sum(1 for s in saetze if s["audio_path"])
    m = {"schema": APP_SCHEMA, "werk_id": werk_id, "book_slug": werk, "sprache": lg,
         "quellsprache": src, "originalsprache": src, "sprachen": taella_sprachen(b),
         "titel": titel or D.meta.get("title") or werk, "autor": autor or "",
         "modus": D.meta.get("modus") or (b.roh.get("modus") or ""),
         "inhalte": sorted(inhalte), "spuren": {"hoerbuch": bool(hb), "hoerspiel": bool(hs)},
         "audio_format": {"typ": "mp3", "bitrate": bitrate},
         "audio_vollstaendig": bool(hb) and bool(soll_audio) and not fehlt_audio,
         "audio_count": n_audio,
         "hoerspiel": bool(hs_rel), "hoerspiel_saetze": sorted(hs_rel),
         "hoerspiel_sprecher": D.hoerspiel_sprecher(lg, sorted(hs_rel)) if hs_rel else {},
         "sprecher_geschlecht": D.geschlecht(),
         "dateien": {"cover": f"cover_{lg}.jpg" if f"cover_{lg}.jpg" in P.dateien else None,
                     "blurb": "blurb.json",
                     "wordtimes": f"wordtimes_{lg}.json" if hb else None,
                     "wordtimes_hoerspiel": f"wordtimes_{lg}_hoerspiel.json" if hs else None,
                     "teaser": f"teaser/{lg}/" if teaser else None},
         "text_quelle": D.text_quelle,
         "saetze": saetze}
    P.json(f"manifest_{lg}.json", m)
    P.metriken.update({"saetze": len(saetze), "audio": n_audio, "audio_soll": len(soll_audio),
                       "hoerspiel": len(hs_rel), "teaser": len(teaser)})
    return P, m


def schema_pruefen(m):
    """Fehlerliste: Manifest im Schema, das die App kennt."""
    f = []
    if m.get("schema") != APP_SCHEMA:
        f.append(f"schema {m.get('schema')!r} != {APP_SCHEMA}")
    f += [f"Feld {k} fehlt" for k in MANIFEST_PFLICHT if k not in m]
    if not isinstance(m.get("saetze"), list) or not m.get("saetze"):
        f.append("saetze leer")
    else:
        for n in m["saetze"]:
            fe = [k for k in KNOTEN_PFLICHT if k not in n]
            if fe:
                f.append(f"Knoten {n.get('tag_id')}: {', '.join(fe)} fehlt")
                break
        ids = [n.get("tag_id") for n in m["saetze"]]
        if len(ids) != len(set(ids)):
            f.append("doppelte tag_id")
    if m.get("sprache") not in (m.get("sprachen") or []):
        f.append("sprache nicht in sprachen")
    return f


def blurb(D, sprachen):
    k = D.d600.get("blurb") or {}
    return {"autor": (D.d600.get("meta") or {}).get("autor") or D.d600.get("autor"), "covers": sprachen,
            "sprachen": sprachen, "koeder": k.get("koeder") or [], "einordnung": k.get("einordnung") or [],
            "autor_info": k.get("autor") or [], "vermerke": D.d600.get("vermerke") or {}}


# ============================================================ Ausfuehren je Ziel
def ausfuehren(ziel, prefix, plan, alt, inventar, nur_manifest=False):
    """Plan ins Ziel. -> (eintraege {rel: {quelle_hash, md5, groesse}}, fehler [text])."""
    neu, fehler = {}, []
    for rel, d in plan.items():
        voll = f"{prefix}/{rel}"
        a = alt.get(rel) or {}
        try:
            if d["art"] == "mp3":
                if nur_manifest and a:
                    neu[rel] = a
                    continue
                c = d["cache"]
                if a.get("quelle_hash") == d["quelle_hash"] and os.path.exists(c) and os.path.getsize(c) == a.get("groesse"):
                    md5, gr = a["md5"], a["groesse"]
                else:
                    _mp3(d["quelle"], c, d["bitrate"])
                    md5, gr = md5_datei(c), os.path.getsize(c)
                quelle = c
            elif d["art"] == "kopie":
                quelle = d["quelle"]
                md5, gr = md5_datei(quelle), os.path.getsize(quelle)
            else:
                quelle, md5, gr = None, md5_bytes(d["daten"]), len(d["daten"])
            if inventar.get(voll) != (md5, gr):
                if quelle:
                    _zweimal(ziel.hochladen, quelle, voll, d.get("ctype"))
                else:
                    _zweimal(ziel.schreiben, d["daten"], voll, d.get("ctype"))
                ziel.bytes += gr
                ziel.hochgeladen += 1
            neu[rel] = {"quelle_hash": d["quelle_hash"], "md5": md5, "groesse": gr}
        except (UploadFehler, RuntimeError, OSError) as e:
            fehler.append(f"{rel}: {e}")
    for rel in sorted(set(alt) - set(plan)):
        try:
            _zweimal(ziel.loeschen, f"{prefix}/{rel}")
            ziel.geloescht += 1
        except UploadFehler as e:
            fehler.append(f"loeschen {rel}: {e}")
            neu[rel] = alt[rel]
    return neu, fehler


def pruefen_im_ziel(eintraege, prefix, inventar):
    return sorted(rel for rel, x in eintraege.items() if inventar.get(f"{prefix}/{rel}") != (x["md5"], x["groesse"]))


# ============================================================ Katalog
def katalog_eintrag(D, werk_id, prefix, sprachen, pakete, titel, autor):
    b = D.b
    q = (pakete.get(D.src) or next(iter(pakete.values())))[1]
    try:
        sys.path.insert(0, os.path.join(config.BASE_DIR, "tools"))
        from regal import regal_von
        regal = regal_von(D.werk)
    except Exception:
        regal = {}
    audio = {lg: bool(pakete[lg][1]["audio_count"]) for lg in sprachen}
    return {"schema": APP_SCHEMA, "werk_id": werk_id, "slug": D.werk, "book_slug": D.werk,
            "titel": {lg: titel.get(lg) or q["titel"] for lg in sprachen}, "autor": autor.get(D.src) or q["autor"],
            "erscheinungsjahr": b.roh.get("erscheinungsjahr"), "quellsprache": D.src, "sprachen": sprachen,
            "cover": [f"cover_{lg}.jpg" for lg in sprachen if pakete[lg][1]["dateien"]["cover"]],
            "cover_path": f"{prefix}/cover_{D.src if D.src in sprachen else sprachen[0]}.jpg",
            "kapitel": sum(1 for s in q["saetze"] if s["typ"] == "h"),
            "woerter": sum(len(s["text"].split()) for s in q["saetze"]),
            "audio_vorhanden": audio, "audio": audio, "audio_im_demo": any(audio.values()),
            "hoerspiel": {lg: True for lg in sprachen if pakete[lg][1]["hoerspiel"]},
            "teaser": {lg: bool(pakete[lg][1]["dateien"]["teaser"]) for lg in sprachen},
            "bilder": 0, "pfad": prefix + "/", "status": "sichtbar", "aktualisiert": manifest.jetzt(), **regal}


def katalog_setzen(ziel, rel, werk_id, eintrag):
    """Eintrag setzen (eintrag None = entfernen); Schreiben nur bei unveraenderter Generation, 1x neu gelesen."""
    for versuch in (1, 2):
        kat, gen = ziel.katalog_lesen(rel)
        kat = kat or {"werke": []}
        werke = [w for w in kat.get("werke") or [] if w.get("werk_id") != werk_id]
        if eintrag:
            werke.append(eintrag)
        werke.sort(key=lambda w: (w.get("autor") or "", w.get("slug") or w.get("werk_id") or ""))
        kat["werke"], kat["aktualisiert"], kat["schema"] = werke, manifest.jetzt(), APP_SCHEMA
        try:
            ziel.katalog_schreiben(rel, kat, gen)
            return True
        except KatalogKonflikt:
            if versuch == 2:
                raise


def katalog_hat(ziel, rel, werk_id):
    kat, _ = ziel.katalog_lesen(rel)
    return next((w for w in (kat or {}).get("werke") or [] if w.get("werk_id") == werk_id), None)


# ============================================================ Lauf
def run(werk, wer=None, ziel=None, nur=None, bitrate=None, nur_manifest=False, freigeben=False,
        zurueckziehen=False, grund=None, dry=False):
    """-> Liste der Gates (je Scope). ziel: Name ('gcs', 'lokal[:PFAD]') oder Ziel-Objekt."""
    from pipeline import s615_cover_final as s615
    wer = wer or "pipeline"
    b = bestellung.lesen(werk)
    Z = ziel if isinstance(ziel, Ziel) else ziel_aus(ziel)
    schreibt = not dry and Z.art == standardziel()
    if bitrate:
        _entscheidung(werk, wer, "bitrate", bitrate={**(entscheidungen(werk).get("bitrate") or {}), "taella": bitrate})
    if zurueckziehen:
        if not grund:
            raise ValueError("--grund ist Pflicht beim Zurueckziehen")
        _entscheidung(werk, wer, "zurueckziehen", zurueckgezogen={"wer": wer, "grund": grund, "wann": manifest.jetzt()})
    ents = entscheidungen(werk)
    br = (ents.get("bitrate") or {}).get("taella") or bitrate_std()["taella"]
    verlag = b.mandant_art == "verlag"
    uid = b.mandant.split(":", 1)[1] if b.mandant_art == "user" else None
    autor_slug = ""
    try:
        autor_slug = config.author_of(werk) or ""
    except Exception:
        pass
    werk_id = werk if uid else (f"{autor_slug}_{werk}" if autor_slug and not autor_slug.startswith("user:") else werk)
    prefix = Z.werk_prefix(werk_id, werk, uid)
    st_alt = ((status.laden(werk)["stages"].get(STAGE) or {}).get("teile") or {})
    z700 = status.zustand(werk, "700")
    gates = []

    # ---- Kanaele, die erst mit AP 710b kommen
    for lg in b.sprachen:
        for k in b.kanaele(lg):
            if k in GEBAUT or (nur and lg not in nur):
                continue
            g = gate.Gate(werk, STAGE, scope=f"{lg}:{k}", ruecksprung="710", wer=wer)
            g.pflicht("kanal_gebaut", False, bei_fehler="mensch",
                      text=f"Kanal {k} wird mit AP 710b gebaut – noch keine Auslieferung")
            g.entscheide(schreiben=schreibt)
            gates.append(g)

    # ---- TAELLA: Scopes und Plaene
    D = Daten(werk, b)
    alle = taella_sprachen(b)
    lieferbar = {lg: inhalte_lieferbar(werk, lg) for lg in alle}
    sprachen = [lg for lg in alle if lieferbar[lg]] if z700 in status.FREI else []
    titel, autor = {}, {}
    for lg in alle:
        titel[lg] = s615.titel(b.roh, lg, b.quellsprache)[0]
        try:
            autor[lg] = s615.autor(werk, b.roh, lg)
        except Exception:
            autor[lg] = D.meta.get("author") or ""
    pakete, ggs = {}, {}
    for lg in alle:
        if nur and lg not in nur:
            continue
        sc = f"{lg}:taella"
        g = gate.Gate(werk, STAGE, scope=sc, ruecksprung="710", wer=wer)
        ggs[lg] = g
        g.pflicht("gate_700", z700 in status.FREI, z700, ruecksprung="700", text=f"Gate 700 frei ({z700})")
        if z700 in status.FREI:
            bestellt = [p["inhalt"] for p in b.produkte_fuer(sprache=lg, kanal="taella")]
            inh = lieferbar[lg]
            g.pflicht("lieferbar", bool(inh), ruecksprung="700",
                      text=f"lieferbare 700-Scopes {lg}: {', '.join(s for v in inh.values() for s in v) or '–'}"
                           f" (bestellt: {', '.join(bestellt)})")
            fehlt = [i for i in bestellt if i not in inh]
            if inh and fehlt:
                g.hinweis("zurueckgehalten", False, text=f"nicht lieferbar (700): {', '.join(fehlt)} – Rest wird geliefert")
        if not g.fehler():
            P, m = paket(D, lg, set(lieferbar[lg]), werk_id, br, titel[lg], autor[lg])
            pakete[lg] = (P, m)
            for name, text, rs in P.befunde:
                g.pflicht(name, False, ruecksprung=rs, text=text)
            sf = schema_pruefen(m)
            g.pflicht("schema", not sf, text=f"Manifest Schema {APP_SCHEMA}" + (f": {'; '.join(sf[:3])}" if sf else " ok"))
            for k, v in P.metriken.items():
                g.metrik(k, v)
    werk_plan = Plan()
    if pakete:
        werk_plan.json("blurb.json", blurb(D, [lg for lg in sprachen]))

    # ---- Ausfuehren
    exp = _json(pfad(werk), {}) or {}
    ze = (exp.get("ziele") or {}).get(Z.kennung()) or {}
    alt_sc = ze.get("scopes") or {}
    ok_lg = [lg for lg in pakete if not ggs[lg].fehler()]
    eintraege, upload_fehler = {}, {}
    if dry:
        for lg in pakete:
            print(f"[710] DRY {lg}:taella -> {Z.kennung()}/{prefix}: {len(pakete[lg][0].dateien)} Dateien")
    elif ok_lg:
        try:
            inv = _zweimal(Z.inventar, prefix)
        except UploadFehler as e:
            for lg in ok_lg:
                ggs[lg].pflicht("upload", False, text=f"Ziel nicht erreichbar (1x neu): {e}")
            ok_lg = []
    if ok_lg and not dry:
        for lg in ok_lg:
            sc = f"{lg}:taella"
            if schreibt:
                status.start(werk, STAGE, wer=wer, scope=sc)
            eintraege[sc], upload_fehler[sc] = ausfuehren(Z, prefix, pakete[lg][0].dateien,
                                                          (alt_sc.get(sc) or {}).get("dateien") or {}, inv, nur_manifest)
        eintraege[WERK], upload_fehler[WERK] = ausfuehren(Z, prefix, werk_plan.dateien,
                                                          (alt_sc.get(WERK) or {}).get("dateien") or {}, inv)
        try:
            inv2 = _zweimal(Z.inventar, prefix)
        except UploadFehler:
            inv2 = {}
        for lg in ok_lg:
            sc = f"{lg}:taella"
            g = ggs[lg]
            fe = upload_fehler[sc] + upload_fehler[WERK]
            g.pflicht("upload", not fe, len(fe), text="Upload ohne Fehler (1x neu)" + (f": {'; '.join(fe[:3])}" if fe else ""))
            abw = pruefen_im_ziel({**eintraege[sc], **eintraege[WERK]}, prefix, inv2)
            g.pflicht("ziel_md5", not abw, len(abw),
                      text=f"{len(eintraege[sc]) + len(eintraege[WERK])} Dateien im Ziel, Groesse/MD5 = lokal"
                           + (f" – abweichend: {', '.join(abw[:3])}" if abw else ""))
            g.metrik("dateien", len(eintraege[sc]))

    # ---- Katalog + Entscheidung
    fg = ents.get("freigabe") or {}
    zurueck = ents.get("zurueckgezogen")
    kat_rel = Z.katalog_rel(uid)
    ausgabe_hash = {lg: manifest.hash_obj({r: x["md5"] for r, x in {**eintraege.get(f"{lg}:taella", {}),
                                                                         **eintraege.get(WERK, {})}.items()})
                    for lg in ok_lg}
    gruen = [lg for lg in ok_lg if not ggs[lg].fehler()]
    if freigeben and not dry:
        fg = {"wer": wer, "wann": manifest.jetzt(), "hash": {f"{lg}:taella": ausgabe_hash[lg] for lg in gruen}}
        _entscheidung(werk, wer, "freigeben", freigabe=fg, zurueckgezogen=None)
        zurueck = None
    def mensch_offen(lg):
        if uid:
            return None
        if verlag and (fg.get("hash") or {}).get(f"{lg}:taella") != ausgabe_hash.get(lg):
            return "Mandant verlag: Abnahme vor Katalog (python -m pipeline.s710_cloud_export " \
                   f"{werk} --freigeben)"
        if not fg and not zurueck:
            return f"erstes Freischalten im oeffentlichen Katalog: python -m pipeline.s710_cloud_export {werk} --freigeben"
        return None
    offen = {lg: mensch_offen(lg) for lg in gruen}
    sichtbar = [lg for lg in gruen if not offen[lg]]
    kat_fehler = None
    if not dry and gruen:
        try:
            if uid:
                katalog_setzen(Z, kat_rel, werk_id, katalog_eintrag(D, werk_id, prefix, gruen, pakete, titel, autor))
            elif zurueck:
                katalog_setzen(Z, kat_rel, werk_id, None)
            elif sichtbar:
                katalog_setzen(Z, kat_rel, werk_id, katalog_eintrag(D, werk_id, prefix, sichtbar, pakete, titel, autor))
        except (KatalogKonflikt, UploadFehler, OSError) as e:
            kat_fehler = f"{type(e).__name__}: {e}"
    kat_ist = katalog_hat(Z, kat_rel, werk_id) if (not dry and gruen) else None
    oeff_ist = katalog_hat(Z, Z.katalog_rel(None), werk_id) if (not dry and gruen and uid) else None
    for lg in ok_lg:
        sc, g = f"{lg}:taella", ggs[lg]
        if dry:
            continue
        if kat_fehler:
            g.pflicht("katalog", False, text=f"Katalog nicht geschrieben (Generation/Upload): {kat_fehler}")
        elif uid:
            g.pflicht("katalog", bool(kat_ist) and lg in (kat_ist.get("sprachen") or []) and not oeff_ist,
                      text=f"privat: Eintrag in {kat_rel}, nicht im oeffentlichen Katalog")
        elif zurueck:
            g.pflicht("katalog", not kat_ist, text=f"zurueckgezogen: Werk nicht im Katalog ({zurueck.get('grund')})")
            g.hinweis("zurueckgezogen", False, text=f"Werk zurueckgezogen von {zurueck.get('wer')} – unsichtbar")
        elif lg in sichtbar:
            g.pflicht("katalog", bool(kat_ist) and lg in (kat_ist.get("sprachen") or []),
                      text=f"Katalog {kat_rel}: Eintrag mit Sprache {lg}")
        g.metrik("ausgabe_hash", ausgabe_hash.get(lg))
        g.metrik("ziel", Z.kennung())
    for lg, g in ggs.items():
        immer = bool(offen.get(lg))
        g.entscheide(mensch_immer=immer, mensch_grund=offen.get(lg), schreiben=schreibt)
        gates.append(g)

    # ---- Ablage, Kosten, Altcheckpoint
    if not dry:
        sc_neu = dict(alt_sc)
        for sc, e in eintraege.items():
            lg = sc.split(":")[0]
            sc_neu[sc] = {"dateien": e, "zeit": manifest.jetzt(),
                          **({"inhalte": sorted(lieferbar[lg]), "ausgabe_hash": ausgabe_hash.get(lg),
                              "ergebnis": ggs[lg].ergebnis["ergebnis"], "gruende": ggs[lg].ergebnis["gruende"]}
                             if sc != WERK else {})}
        (exp.setdefault("ziele", {}))[Z.kennung()] = {
            "art": Z.art, "prefix": prefix, "werk_id": werk_id, "katalog": kat_rel, "bitrate": br,
            "sichtbar": bool(kat_ist), "zeit": manifest.jetzt(), "scopes": sc_neu}
        exp.update({"schema": 1, "stage": STAGE, "version": VERSION, "werk": werk, "mandant": b.mandant})
        manifest.json_atomar(pfad(werk), exp, indent=1)
        if Z.art == "gcs" and (Z.bytes or Z.geloescht):
            try:
                from pipeline import usage_log
                usage_log.log_stueck("gcs_upload_gb", round(Z.bytes / 1e9, 6), book_id=werk, stage=STAGE,
                                     extra={"bytes": Z.bytes, "dateien": Z.hochgeladen, "geloescht": Z.geloescht})
            except Exception:
                pass
        for lg in b.sprachen:
            a = config.work_path(werk, f"710_cloud_export_{lg}")
            if os.path.exists(a):
                os.replace(a, config.work_path(werk, f"710_cloud_export_{lg}_alt"))
        print(f"[710] {Z.kennung()}/{prefix}: {Z.hochgeladen} hochgeladen ({Z.bytes / 1e6:.1f} MB), "
              f"{Z.geloescht} geloescht, Katalog {'sichtbar' if kat_ist else 'nicht sichtbar'}")
    return gates


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 710 Auslieferung (TAELLA)")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--ziel", help="gcs | lokal[:PFAD] (Standard config.AUSLIEFERUNG_ZIEL)")
    ap.add_argument("--lang", action="append", help="nur diese Sprache(n)")
    ap.add_argument("--bitrate", help="MP3-Bitrate Kanal taella, z. B. 96k (wird gemerkt)")
    ap.add_argument("--nur-manifest", action="store_true", help="Audio nicht neu umwandeln/hochladen")
    ap.add_argument("--freigeben", action="store_true", help="erstes Freischalten im Katalog / Abnahme Verlag")
    ap.add_argument("--zurueckziehen", action="store_true", help="Werk aus dem Katalog nehmen (Dateien bleiben)")
    ap.add_argument("--grund")
    ap.add_argument("--dry", action="store_true", help="Probelauf ohne Upload und Status")
    a = ap.parse_args(argv)
    try:
        gates = run(a.werk, a.wer, ziel=a.ziel, nur=a.lang, bitrate=a.bitrate, nur_manifest=a.nur_manifest,
                    freigeben=a.freigeben, zurueckziehen=a.zurueckziehen, grund=a.grund, dry=a.dry)
    except (ValueError, RuntimeError) as e:
        print(f"[710] {e}")
        return 1
    for g in gates:
        print(g.bericht())
    return gate.EXIT[gate.gesamt([g.ergebnis["ergebnis"] for g in gates] or ["auto"])]


# ============================================================ Altschnittstelle (tools/export_demo.py bis AP 710c)
def _load_content_source(book_slug):
    p340, p400 = config.work_path(book_slug, "340_wortalignment"), config.work_path(book_slug, "400_regie")
    for p, al in ((p340, True), (p400, False)):
        d = _json(p)
        if d:
            return d, al
    raise FileNotFoundError(f"Weder {p340} noch {p400} gefunden")


def _build_manifest(book_slug, lang, werk_id, stage06, audio_uris):
    """Altformat fuer tools/export_demo.py (entfaellt mit AP 710c)."""
    b = bestellung.lesen(book_slug)
    D = Daten(book_slug, b)
    D.text = stage06
    content, kap = D.content, D.meta.get("chapters") or {}
    ziele = [z for z in b.zielsprachen]
    saetze = []
    for tid, e in content.items():
        if not isinstance(e, dict):
            continue
        typ, text = e.get("type", "s"), e.get(lang, "")
        if not text and typ not in NO_AUDIO_TYPES:
            continue
        kk = tid.split("_")[0] if "_" in tid else ""
        n = {"tag_id": tid, "typ": typ, "kapitel": kap.get(kk, kk), "text": text, "audio_path": audio_uris.get(tid, ""),
             "pause_after_ms": D.pause(tid, lang)}
        for f in ("sprecher", "rolle"):
            if e.get(f):
                n[f] = e[f]
        if lang == b.quellsprache and ziele:
            z = ziele[0]
            al = e.get(f"align_{z}") or e.get("align")
            if al:
                n["align"] = _slim(al, ((D.d525.get("je_ziel") or {}).get(z) or {}).get("tags", {}).get(tid)
                                   or (D.d525.get("tags") or {}).get(tid), b.quellsprache, z)
        saetze.append(n)
    hits = sum(1 for s in saetze if s["audio_path"])
    return {"werk_id": werk_id, "originalsprache": b.quellsprache, "book_slug": book_slug, "sprache": lang,
            "titel": D.meta.get("title", book_slug), "autor": D.meta.get("author", ""),
            "audio_vollstaendig": hits > 0 and hits >= sum(1 for s in saetze if s["typ"] not in NO_AUDIO_TYPES),
            "audio_count": hits, "erstellt": manifest.jetzt(), "modus": D.meta.get("modus", ""),
            "sprecher_geschlecht": D.geschlecht(), "saetze": saetze}


if __name__ == "__main__":
    sys.exit(main())
