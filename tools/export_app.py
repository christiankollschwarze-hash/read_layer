"""Keim von Stage 60: exportiert Cover + Klappentext eines Werks nach taella-app/public/.

Aufruf:  python tools/export_app.py <buch-ordner> <app-public-ordner>
Beispiel: python tools/export_app.py authors/london-j/books/call-of-the-wild ../taella-app/public

Erzeugt:
  public/cover_<lang>.jpg  aus fassungen/<lang>/output/cover_final_<lang>.jpg
  public/blurb.json        aus work/600_klappentext.json (satzparallele EN/DE-Paare)
  public/wordtimes_<lang>.json  aus work/520_wortzeiten_<lang>.json (falls gefüllt)
                           { "tags": { tag_id: [t0 je \\S+-Token, null = ohne Zeit] } }
"""
import json, shutil, sys
from pathlib import Path

def main(book: Path, public: Path):
    public.mkdir(parents=True, exist_ok=True)
    covers = []
    for f in sorted((book / "fassungen").glob("*/output/cover_final_*.jpg")):
        lang = f.stem.rsplit("_", 1)[-1]
        shutil.copy2(f, public / f"cover_{lang}.jpg")
        covers.append(lang)

    s09p = book / "work" / "600_klappentext.json"
    if s09p.exists():
        s09 = json.loads(s09p.read_text(encoding="utf-8"))
        b = s09["blurb"]
    else:
        # Privater ePub-Upload (17.10.2026): kein Stage 09 -> Klappentext aus book.json (OPF)
        bj = json.loads((book / "book.json").read_text(encoding="utf-8"))
        kt = bj.get("klappentext") or {}
        if isinstance(kt, str):
            kt = {"en": kt}
        txt = kt.get("en") or next(iter(kt.values()), "")
        s09 = {"autor": bj.get("autor_name")}
        b = {"einordnung": [{"en": kt.get("en", txt), "de": kt.get("de", txt)}]} if txt else {}
    out = {
        "autor": s09.get("autor"),
        "covers": covers,
        "koeder": b.get("koeder", []),
        "einordnung": b.get("einordnung", []),
        "autor_info": b.get("autor", []),
    }
    (public / "blurb.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    wt = []
    for f in sorted((book / "work").glob("520_wortzeiten_*.json")):
        lang = f.stem.rsplit("_", 1)[-1]
        if lang not in ("en", "de"):
            continue  # z.B. *_ALT_stt.json
        tags = json.loads(f.read_text(encoding="utf-8")).get("tags", {})
        if not tags:
            continue
        kompakt = {}
        for tid, eintraege in tags.items():
            n = max(e["i"] for e in eintraege) + 1
            starts = [None] * n
            for e in eintraege:
                starts[e["i"]] = e["t0"]
            kompakt[tid] = starts
        (public / f"wordtimes_{lang}.json").write_text(
            json.dumps({"sprache": lang, "tags": kompakt}, separators=(",", ":")), encoding="utf-8")
        wt.append(f"{lang}:{len(kompakt)}")

    print(f"Wortzeiten: {wt or 'keine (Stage 58c laufen lassen)'}")
    print(f"Cover: {covers}  |  blurb.json: {len(out['koeder'])}/{len(out['einordnung'])}/{len(out['autor_info'])} Sätze")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
