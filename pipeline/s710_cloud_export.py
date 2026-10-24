"""STAGE 710 — Cloud-Export
Funktion:     Auslieferung an TAELLA ueber Google Cloud Storage.
Wirkungsweise: WAV -> MP3, Upload nach readlayer-taella-content, Manifest je Sprache, catalog.json; private Werke unter users/.
Komponenten:  pipeline/s710_cloud_export.py, pydub, google-cloud-storage
Zulieferer:   s340 Wort-Alignment, s400 Regie, s500 Vertonung, s520 Wortzeiten, s410 Casting
Abnehmer:     TAELLA-App (manifest_<lang>.json, catalog.json), work/710_cloud_export_<lang>.json
(Nomenklatur seit 18.10.2026, Uebersicht: docs/Pipeline_Strang_Matrix.xlsx)

--- Bisherige Beschreibung ---

s710_cloud_export.py — Cloud-Export fuer TAELLA

Liest 400_regie.json (content-Dict + production.pause_after_ms),
konvertiert WAVs -> MP3, laedt alles in GCS, schreibt manifest + catalog.

Audio ist OPTIONAL: fehlt der Audio-Ordner oder eine Datei, wird das
Manifest trotzdem geschrieben (audio_path = "" fuer die betroffenen Tags).
So kann z.B. manifest_de.json mit vollem DE-Text schon exportiert werden,
bevor das DE-Audio existiert; die Audio-Pfade fuellen sich beim naechsten Lauf.

Bucket-Struktur:
  <bucket>/
    catalog.json
    werke/<werk_id>/
      manifest_<lang>.json
      audio/<lang>/<tag_id>.mp3

Aufruf:
  python -m pipeline.s710_cloud_export <book-slug> --lang en
  python -m pipeline.s710_cloud_export <book-slug> --lang de          # ohne Audio ok
  python -m pipeline.s710_cloud_export <book-slug> --lang de --force
  python -m pipeline.s710_cloud_export <book-slug> --lang de --dry
"""

import argparse
import json
import os
import sys
import datetime
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
def _find_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "config").is_dir():
            return p
    raise RuntimeError("Kein config/-Ordner gefunden")

ROOT = _find_root(Path(__file__).resolve().parent)
sys.path.insert(0, str(ROOT))
from config import config  # noqa: E402

STAGE_NAME = "710_cloud_export"
MP3_BITRATE = "128k"

# Typen ohne eigenes Audio (reine Struktur-Knoten wie Absatzmarken).
# Robust ueber config, Fallback auf {"p"}.
NO_AUDIO_TYPES = set(getattr(config, "NO_AUDIO_TYPES", {"p"}))

# ---------------------------------------------------------------------------
# GCS-Hilfsfunktionen
# ---------------------------------------------------------------------------

def _gcs_client():
    try:
        from google.cloud import storage as gcs
        return gcs.Client()
    except ImportError:
        raise RuntimeError("google-cloud-storage nicht installiert.")

def _bucket(client):
    name = getattr(config, "GCS_BUCKET", None)
    if not name:
        raise RuntimeError("config.GCS_BUCKET nicht gesetzt")
    return client.bucket(name)

def _wav_to_mp3(wav_path: Path, mp3_path: Path):
    try:
        from pydub import AudioSegment
    except ImportError:
        raise RuntimeError("pydub nicht installiert.")
    AudioSegment.from_wav(str(wav_path)).export(str(mp3_path), format="mp3", bitrate=MP3_BITRATE)

_PREFIX = "werke"   # private Uploads: users/<uid>/works (17.10.2026), nie im Katalog


def _gcs_audio_path(werk_id, lang, tag_id):
    return f"{_PREFIX}/{werk_id}/audio/{lang}/{tag_id}.mp3"

def _gcs_manifest_path(werk_id, lang):
    return f"{_PREFIX}/{werk_id}/manifest_{lang}.json"

def _upload_blob(bucket, source: Path, dest: str, dry: bool) -> str:
    uri = f"gs://{bucket.name}/{dest}"
    if dry:
        print(f"  [DRY] {source.name} -> {uri}")
        return uri
    bucket.blob(dest).upload_from_filename(str(source))
    return uri

def _upload_json(bucket, data: dict, dest: str, dry: bool) -> str:
    uri = f"gs://{bucket.name}/{dest}"
    if dry:
        print(f"  [DRY] json -> {uri}")
        return uri
    blob = bucket.blob(dest)
    blob.upload_from_string(json.dumps(data, ensure_ascii=False, indent=2),
                            content_type="application/json")
    return uri

def _download_json(bucket, path: str):
    blob = bucket.blob(path)
    if not blob.exists():
        return None
    return json.loads(blob.download_as_text())

# ---------------------------------------------------------------------------
# Kern
# ---------------------------------------------------------------------------

def _load_content_source(book_slug: str):
    """Nimmt die neueste vollstaendige Content-Datei: 340_wortalignment (enthaelt align),
    sonst 400_regie als Fallback. 340_wortalignment ist per Konstruktion ein Superset von
    400_regie (gleiche Struktur + 'align'-Feld pro Knoten). So exportiert Stage 60
    das Wort-Alignment automatisch, sobald 54a gelaufen ist -- ohne dass Werke
    ohne Alignment brechen (die exportieren dann eben ohne 'align')."""
    p54 = Path(config.work_path(book_slug, "340_wortalignment"))
    p06 = Path(config.work_path(book_slug, "400_regie"))
    if p54.exists():
        with open(p54, encoding="utf-8") as f:
            return json.load(f), True   # hat_align
    if p06.exists():
        with open(p06, encoding="utf-8") as f:
            return json.load(f), False
    raise FileNotFoundError(f"Weder {p54} noch {p06} gefunden — Stage 56 zuerst ausfuehren")

def _load_audio_dir(book_slug: str, lang: str):
    """Audio-Ordner der Fassung. Fehlt er, wird None zurueckgegeben (Audio optional)."""
    d = Path(config.book_dir(book_slug)) / "fassungen" / lang / "audio"
    if not d.exists():
        return None
    return d

def _pause_for(pause_map, tag_id, lang):
    """pause_after_ms liegt pro Sprache vor ({'en':..,'de':..}); ziehe den Wert der Fassung."""
    pa = pause_map.get(tag_id, 0)
    if isinstance(pa, dict):
        return pa.get(lang, 0)
    return pa

# Felder, die pro Wort-Anker WIRKLICH ins Frontend-Manifest gehoeren.
# Die Arbeitsdatei 340_wortalignment.json traegt pro Wort {i, en, en_span, de, de_span,
# source}. Fuers Frontend gebraucht (Stand 17.07., mit CK abgestimmt):
#   i        - stabile Achse (Flyover, Karaoke, spaeter Audio-Zeitstempel)
#   en_span  - Position des EN-Worts im EN-Satztext (Bubble-Anker + Karaoke-Highlight)
#   de       - DE-Fragment fuer die Flyover-Bubble (kann null sein = kein Anker,
#              z.B. Funktionswort in Verbform aufgeloest; Eintrag bleibt aber
#              erhalten, damit die Karaoke-Achse lueckenlos jedes EN-Wort kennt)
#   de_span  - Position im DE-Satz; Grundlage fuer den spaeteren Fall
#              "DE-Vollaudio -> EN-Wort ueber DE-Zeitstempel rueckwaerts highlighten"
# BEWUSST WEGGELASSEN:
#   source   - reine Pipeline-Diagnostik (direct/gap_fallback/none/compound_pair),
#              fuers Frontend ohne Nutzen -> spart bei ~31.750 Woertern spuerbar Groesse.
#   en       - der EN-Wortlaut steckt bereits ueber en_span im Satztext ("text"),
#              muss nicht pro Anker dupliziert werden.
# Audio-Zeitstempel (en_time/de_time) werden hier NICHT als Leerfeld reserviert,
# sondern spaeter dort ergaenzt, wo sie entstehen (Stage 58b MMS_FA fuer EN,
# Piper include_alignments fuer DE) - kein Ballast, bis der Fall gebaut ist.
def _slim_align(align):
    """Reduziert die volle 54a-Wortliste auf die Frontend-Felder."""
    slim = []
    for w in align:
        k_src_span, k_tgt, k_tgt_span = config.align_keys()   # je Werk (22.10.2026)
        node = {"i": w.get("i"), k_src_span: w.get(k_src_span), k_tgt: w.get(k_tgt)}
        if w.get(k_tgt_span) is not None:
            node[k_tgt_span] = w[k_tgt_span]
        slim.append(node)
    return slim

def _build_manifest(book_slug, lang, werk_id, stage06, audio_uris):
    # (400_regie kann in Wahrheit 340_wortalignment-Inhalt sein — dann tragen Knoten 'align'.)
    content = stage06.get("content", {})
    pause_map = stage06.get("production", {}).get("pause_after_ms", {})
    if not pause_map:
        # 17.10.2026: Quelle ist oft 340_wortalignment (ohne production) -> Pausen-Dramaturgie aus 400_regie holen
        try:
            s06 = json.loads(Path(config.work_path(book_slug, "400_regie")).read_text(encoding="utf-8"))
            pause_map = s06.get("production", {}).get("pause_after_ms", {})
        except Exception:
            pause_map = {}
    meta = stage06.get("meta", {})

    # Autor aus book.json / author.json
    book_json = Path(config.book_dir(book_slug)) / "book.json"
    book_meta = {}
    if book_json.exists():
        with open(book_json, encoding="utf-8") as f:
            book_meta = json.load(f)
    author_slug = book_meta.get("author_id", "")
    autor_name = meta.get("author", "")
    if author_slug and not autor_name:
        aj = Path(config.author_dir(author_slug)) / "author.json"
        if aj.exists():
            with open(aj, encoding="utf-8") as f:
                autor_name = json.load(f).get("name_display", "")

    kapitel_map = meta.get("chapters", {})

    saetze = []
    audio_hits = 0
    for tag_id, entry in content.items():
        typ = entry.get("type", "s")
        # Zielsprachiger Text; fuer nicht-en Fassungen KEIN en-Fallback
        # (sonst stuenden untranslated-Tags faelschlich als "uebersetzt" da).
        text = entry.get(lang, "")
        # Struktur-Knoten (p) bleiben textlos erhalten; sonstige ohne Text raus.
        if not text and typ not in NO_AUDIO_TYPES:
            continue
        kapitel_key = tag_id.split("_")[0] if "_" in tag_id else ""
        uri = audio_uris.get(tag_id, "")
        if uri:
            audio_hits += 1
        node = {
            "tag_id": tag_id,
            "typ": typ,
            "kapitel": kapitel_map.get(kapitel_key, kapitel_key),
            "text": text,
            "audio_path": uri,
            "pause_after_ms": _pause_for(pause_map, tag_id, lang),
        }
        # Drama-Modus (11.10.2026): Rollenname nur zur Anzeige (wird nicht gesprochen)
        if entry.get("sprecher"):
            node["sprecher"] = entry["sprecher"]
        if entry.get("rolle"):
            node["rolle"] = entry["rolle"]
        # Wort-/Phrasen-Alignment NUR ins EN-Manifest (EN ist Anker; der Flyover
        # wird im englischen Lesetext ausgeloest). Verschlankt auf die Frontend-
        # Felder (siehe _slim_align) - die volle Wortliste mit source/en bleibt
        # nur in der Arbeitsdatei 340_wortalignment.json.
        if lang == config.SOURCE_LANGUAGE:   # Anker = Originalsprache (22.10.2026)
            al = entry.get("align")
            if al:
                node["align"] = _slim_align(al)
        saetze.append(node)

    manifest = {
        "werk_id": werk_id,
        "originalsprache": config.SOURCE_LANGUAGE,   # Anker fuer TAELLA (22.10.2026)
        "book_slug": book_slug,
        "sprache": lang,
        "titel": meta.get("title", book_slug),
        "autor": autor_name,
        "audio_vollstaendig": audio_hits > 0 and audio_hits >= sum(
            1 for s in saetze if s["typ"] not in NO_AUDIO_TYPES),
        "audio_count": audio_hits,
        "erstellt": datetime.datetime.utcnow().isoformat() + "Z",
        "modus": meta.get("modus", ""),
        "sprecher_geschlecht": _sprecher_geschlecht(book_slug),
        "saetze": saetze,
    }
    return manifest


def _sprecher_geschlecht(book_slug):
    """{Figurenname: 'm'|'w'|'n'} aus work/casting.json (Steckbriefe) - fuer Farben der Sprechernamen in der App."""
    try:
        p = os.path.join(config.work_dir(book_slug), "casting.json")
        c = json.load(open(p, encoding="utf-8"))
        out = {}
        for f in (c.get("steckbriefe") or {}).get("figuren", []):
            g = ((f.get("merkmale") or {}).get("geschlecht") or "").lower()[:1]
            if f.get("name") and g in ("m", "w", "n"):
                out[f["name"]] = g
        for e in (c.get("plan") or {}).get("ensemble", []):
            g = (((e.get("steckbrief") or {}).get("merkmale") or {}).get("geschlecht") or "").lower()[:1]
            if e.get("figur") and g in ("m", "w", "n"):
                out.setdefault(e["figur"], g)
        return out
    except Exception:
        return {}

def _update_catalog(bucket, werk_id, book_slug, lang, manifest, has_audio, dry):
    if dry:
        catalog = {"werke": []}
    else:
        catalog = _download_json(bucket, "catalog.json") or {"werke": []}

    existing = next((w for w in catalog["werke"] if w["werk_id"] == werk_id), None)
    if existing is None:
        existing = {
            "werk_id": werk_id,
            "book_slug": book_slug,
            "titel": manifest["titel"],
            "autor": manifest["autor"],
            "sprachen": [],
            "cover_path": f"werke/{werk_id}/cover.png",
            "status": "fertig",
        }
        catalog["werke"].append(existing)
    if lang not in existing.get("sprachen", []):
        existing.setdefault("sprachen", []).append(lang)
    # Audio-Verfuegbarkeit pro Sprache transparent halten
    existing.setdefault("audio", {})[lang] = bool(has_audio)
    existing["aktualisiert"] = datetime.datetime.utcnow().isoformat() + "Z"
    catalog["aktualisiert"] = datetime.datetime.utcnow().isoformat() + "Z"

    _upload_json(bucket, catalog, "catalog.json", dry)
    print(f"  catalog.json aktualisiert ({len(catalog['werke'])} Werk(e))")

# ---------------------------------------------------------------------------
# Hauptfunktion
# ---------------------------------------------------------------------------

def run(book_slug: str, lang: str, force: bool = False, dry: bool = False,
        manifest_only: bool = False):
    print(f"[stage60] {book_slug} / {lang} — Cloud-Export startet"
          + (" (NUR Manifest)" if manifest_only else ""))

    global _PREFIX
    author_slug = config.author_of(book_slug)
    privat = author_slug.startswith("user:")
    if privat:
        _PREFIX = f"users/{author_slug[5:]}/works"
        werk_id = book_slug
        print(f"  PRIVAT: Ablage {_PREFIX}/{werk_id}/ - kein Katalogeintrag")
    else:
        _PREFIX = "werke"
        werk_id = f"{author_slug}_{book_slug}"

    stage06, hat_align = _load_content_source(book_slug)
    if hat_align and lang == config.SOURCE_LANGUAGE:
        print("  Quelle: 340_wortalignment.json (mit Wort-Alignment)")

    # Audio ist optional -------------------------------------------------
    audio_dir = _load_audio_dir(book_slug, lang)
    wav_files = sorted(audio_dir.glob("*.wav")) if audio_dir else []
    if not wav_files:
        print(f"  KEIN Audio fuer '{lang}' gefunden — Manifest wird ohne Audio-Pfade "
              f"geschrieben (Text-only).")
    else:
        print(f"  {len(wav_files)} WAV-Dateien gefunden")

    # GCS ----------------------------------------------------------------
    if dry:
        bkt = type("FakeBucket", (), {"name": getattr(config, "GCS_BUCKET", "dry-bucket")})()
    else:
        bkt = _bucket(_gcs_client())

    # WAV -> MP3 + Upload (nur wenn Audio da) ----------------------------
    audio_uris = {}
    if wav_files and manifest_only:
        # Nur Manifest neu bauen: keine Konvertierung/Upload, aber die bereits
        # in GCS liegenden Audio-Pfade wiederverwenden, damit das Manifest sie
        # weiterhin referenziert. Umgeht pydub/ffmpeg komplett - genau der
        # haeufige Fall beim Iterieren am Manifest-/align-Format.
        for wav in wav_files:
            tag_id = wav.stem
            dest = _gcs_audio_path(werk_id, lang, tag_id)
            if dry:
                audio_uris[tag_id] = f"gs://{bkt.name}/{dest}"
            elif bkt.blob(dest).exists():
                audio_uris[tag_id] = f"gs://{bkt.name}/{dest}"
        print(f"  [manifest-only] {len(audio_uris)} vorhandene Audio-Pfade "
              f"aus GCS uebernommen (keine Neu-Konvertierung)")
    elif wav_files:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for wav in wav_files:
                tag_id = wav.stem
                dest = _gcs_audio_path(werk_id, lang, tag_id)

                if not dry and not force:
                    if bkt.blob(dest).exists():
                        audio_uris[tag_id] = f"gs://{bkt.name}/{dest}"
                        continue

                print(f"  -> {tag_id}", end=" ", flush=True)
                if dry:
                    audio_uris[tag_id] = f"gs://{bkt.name}/{dest}"
                    print("[DRY]")
                else:
                    mp3 = tmp_path / f"{tag_id}.mp3"
                    _wav_to_mp3(wav, mp3)
                    uri = _upload_blob(bkt, mp3, dest, dry=False)
                    audio_uris[tag_id] = uri
                    print("ok")
        print(f"  {len(audio_uris)} Audio-Dateien verarbeitet")

    # Manifest -----------------------------------------------------------
    manifest = _build_manifest(book_slug, lang, werk_id, stage06, audio_uris)
    manifest_blob = _gcs_manifest_path(werk_id, lang)
    _upload_json(bkt, manifest, manifest_blob, dry)
    print(f"  manifest_{lang}.json ({len(manifest['saetze'])} Knoten, "
          f"{manifest['audio_count']} mit Audio)")

    if not privat:
        _update_catalog(bkt, werk_id, book_slug, lang, manifest,
                        has_audio=bool(audio_uris), dry=dry)

    # Checkpoint ---------------------------------------------------------
    checkpoint = {
        "werk_id": werk_id, "sprache": lang,
        "bucket": getattr(config, "GCS_BUCKET", ""),
        "manifest_path": manifest_blob,
        "audio_count": len(audio_uris),
        "audio_vollstaendig": manifest["audio_vollstaendig"],
        "exportiert": datetime.datetime.utcnow().isoformat() + "Z",
    }
    out = Path(config.work_dir(book_slug)) / f"{STAGE_NAME}_{lang}.json"
    if not dry:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(checkpoint, f, ensure_ascii=False, indent=2)
        print(f"  Checkpoint: {out}")

    print(f"[stage60] fertig — gs://{bkt.name}/{_PREFIX}/{werk_id}/")

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="Stage 60 — Cloud-Export")
    p.add_argument("book_slug")
    p.add_argument("--lang", required=True)
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry", action="store_true")
    p.add_argument("--manifest-only", action="store_true",
                   help="Nur Manifest neu bauen; Audio nicht konvertieren/hochladen "
                        "(vorhandene GCS-Pfade wiederverwenden). Umgeht pydub/ffmpeg.")
    a = p.parse_args()
    run(a.book_slug, a.lang, force=a.force, dry=a.dry, manifest_only=a.manifest_only)

if __name__ == "__main__":
    main()
