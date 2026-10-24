"""READ LAYER — Demo-Export fuer das Web-Mockup (Katalogtest), rein lokal.

Legt ein fertiges Werk in den Demo-Ordner der TAELLA-App und pflegt dort den Katalog.

Aufruf:
  python tools/export_demo.py <book_slug> [<demo-ordner>] [--audio] [--hoerspiel]
  --hoerspiel: Hoerspiel-Schicht (Saetze mit Figurenrede aus fassungen/<lang>/audio_overlay/vc) ZUSAETZLICH
               nach audio_hoerspiel/<lang>/; Erzaehler bleibt unveraendert in audio/<lang>/ (N-3, 24.10.2026:
               die App schaltet je Werk zwischen Erzaehler und Hoerspiel um)
  Default demo-ordner: ../taella-app/public/demo

Erzeugt:
  <demo>/katalog.json                     Liste aller Demo-Werke (wird aktualisiert, nicht ersetzt)
  <demo>/<slug>/manifest_<lang>.json      wie Stage 60, Audio-Pfade relativ: audio/<lang>/<tag>.wav
  <demo>/<slug>/blurb.json, cover_<lang>.jpg, wordtimes_<lang>.json   (ueber tools/export_app.py)
  <demo>/<slug>/cover.<ext>               Fallback, wenn kein cover_final_<lang>.jpg existiert
  <demo>/<slug>/audio/<lang>/*.wav        NUR mit --audio (gross: ~1 GB je Hoerbuch)
  <demo>/<slug>/audio_hoerspiel/<lang>/*.wav   NUR mit --audio --hoerspiel; Manifest dann zusaetzlich:
      hoerspiel: true, hoerspiel_saetze: [tag_id, ...], hoerspiel_sprecher: {tag_id: Figur}
  <demo>/<slug>/wordtimes_<lang>_hoerspiel.json  Wortzeiten der Hoerspiel-Saetze (falls 520_..._hoerspiel.json)

Ohne --audio stehen im Manifest keine Audio-Pfade; der Katalog vermerkt aber, ob Audio
im read_layer vorhanden ist.
"""
import json
import shutil
import sys
import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from config import config  # noqa: E402
from regal import regal_von  # noqa: E402
from pipeline import s710_cloud_export as s60  # noqa: E402
import export_app  # noqa: E402

LANGS = ["en", "de"]


def _titel(book, lang, fallback):
    for f in book.get("fassungen", []):
        if f.get("sprache") == lang and f.get("titel"):
            return f["titel"]
    return fallback


def _kopiere(wavs, adir):
    """WAVs nach adir; neu kopiert wird bei abweichender Groesse oder Zeitmarke (copy2 haelt die Zeitmarke)."""
    adir.mkdir(parents=True, exist_ok=True)
    for w in wavs:
        dst = adir / w.name
        if not dst.exists() or dst.stat().st_size != w.stat().st_size \
                or int(dst.stat().st_mtime) != int(w.stat().st_mtime):
            shutil.copy2(w, dst)


def _hoerspiel_sprecher(bdir, lang, tags):
    """Figur je Hoerspiel-Satz: erste Figur ausser Erzaehler aus work/sprecher.json."""
    spj = bdir / "work" / "sprecher.json"
    if not spj.exists():
        return {}
    sp = json.loads(spj.read_text(encoding="utf-8"))
    out = {}
    for t in tags:
        for seg in sp.get(t, {}).get(lang, []):
            if seg.get("s") and seg["s"].lower() not in ("erzaehler", "erzähler", "narrator"):
                out[t] = seg["s"]
                break
    return out


def main(slug: str, demo: Path, mit_audio: bool, hoerspiel: bool = False):
    bdir = Path(config.book_dir(slug))
    ziel = demo / slug
    ziel.mkdir(parents=True, exist_ok=True)
    book = json.loads((bdir / "book.json").read_text(encoding="utf-8"))
    content, _ = s60._load_content_source(slug)
    werk_id = f"{config.author_of(slug)}_{slug}"

    # Cover, Klappentext, Wortzeiten
    export_app.main(bdir, ziel)
    covers = sorted(p.name for p in ziel.glob("cover_*.jpg"))
    if not covers:
        for ext in ("png", "jpg", "jpeg", "webp"):
            src = bdir / "images" / f"cover.{ext}"
            if src.exists():
                shutil.copy2(src, ziel / f"cover.{ext}")
                covers = [f"cover.{ext}"]
                break

    audio_info, manifeste = {}, {}
    for lang in LANGS:
        wavs = sorted((bdir / "fassungen" / lang / "audio").glob("*.wav")) \
            if (bdir / "fassungen" / lang / "audio").is_dir() else []
        audio_info[lang] = len(wavs)
        uris = {}
        hs_wavs, hs_sprecher = [], {}
        ov = bdir / "fassungen" / lang / "audio_overlay" / "vc"
        if hoerspiel and ov.is_dir():
            basis = {w.name for w in wavs}
            hs_wavs = sorted(w for w in ov.glob("*.wav") if w.name in basis)
            hs_sprecher = _hoerspiel_sprecher(bdir, lang, [w.stem for w in hs_wavs])
            print(f"  {lang}: Hoerspiel-Schicht {len(hs_wavs)} Saetze, {len(hs_sprecher)} mit Figur")
            # Wortzeiten der Hoerspiel-Saetze (overlay_montage) getrennt; Erzaehler-Wortzeiten bleiben unberuehrt
            hw = bdir / "work" / f"520_wortzeiten_{lang}_hoerspiel.json"
            if hw.exists():
                tags = {}
                for tid, ws in json.loads(hw.read_text(encoding="utf-8")).get("tags", {}).items():
                    starts = [None] * (max(x["i"] for x in ws) + 1)
                    for x in ws:
                        starts[x["i"]] = x["t0"]
                    tags[tid] = starts
                (ziel / f"wordtimes_{lang}_hoerspiel.json").write_text(
                    json.dumps({"tags": tags}, separators=(",", ":")), encoding="utf-8")
                print(f"  {lang}: wordtimes_{lang}_hoerspiel.json ({len(tags)} Saetze)")
        if mit_audio and wavs:
            _kopiere(wavs, ziel / "audio" / lang)
            uris = {w.stem: f"audio/{lang}/{w.name}" for w in wavs}
            if hs_wavs:
                _kopiere(hs_wavs, ziel / "audio_hoerspiel" / lang)
        m = s60._build_manifest(slug, lang, werk_id, content, uris)
        if not m["saetze"]:
            continue
        if mit_audio and hs_wavs:
            m["hoerspiel"] = True
            m["hoerspiel_saetze"] = [w.stem for w in hs_wavs]
            if hs_sprecher:
                m["hoerspiel_sprecher"] = hs_sprecher
        (ziel / f"manifest_{lang}.json").write_text(
            json.dumps(m, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        manifeste[lang] = m
        print(f"  manifest_{lang}.json: {len(m['saetze'])} Knoten, {m['audio_count']} mit Audio")

    # Katalog
    en = manifeste.get("en") or next(iter(manifeste.values()))
    kapitel = sorted({s["kapitel"] for s in en["saetze"] if s.get("kapitel")})
    woerter = sum(len(s["text"].split()) for s in en["saetze"])
    eintrag = {
        "slug": slug,
        "werk_id": werk_id,
        "titel": {l: _titel(book, l, en["titel"]) for l in manifeste},
        "autor": en.get("autor") or "",
        "erscheinungsjahr": book.get("erscheinungsjahr"),
        "sprachen": sorted(manifeste),
        "cover": covers,
        "kapitel": len(kapitel),
        "woerter": woerter,
        "audio_vorhanden": {l: n > 0 for l, n in audio_info.items()},
        "audio_im_demo": mit_audio,
        "hoerspiel": {l: True for l, m in manifeste.items() if m.get("hoerspiel")},
        "pfad": f"demo/{slug}/",
        "aktualisiert": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    eintrag.update(regal_von(slug))   # Genre-Regal fuer den Book-Shop
    kp = demo / "katalog.json"
    kat = json.loads(kp.read_text(encoding="utf-8")) if kp.exists() else {"werke": []}
    kat["werke"] = [w for w in kat["werke"] if w.get("slug") != slug] + [eintrag]
    kat["werke"].sort(key=lambda w: (w.get("autor") or "", w["slug"]))
    kat["aktualisiert"] = eintrag["aktualisiert"]
    kp.write_text(json.dumps(kat, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[demo] {slug} -> {ziel}  (Katalog: {len(kat['werke'])} Werke)")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    demo = Path(args[1]) if len(args) > 1 else ROOT.parent / "taella-app" / "public" / "demo"
    main(args[0], demo.resolve(), "--audio" in sys.argv, "--hoerspiel" in sys.argv)
