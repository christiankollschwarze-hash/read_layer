"""READ LAYER — Plausibilitaetspruefung Satz-Audio (lokal, keine API).
Findet Nachhall-Schwaenze und abgeschnittene/verschluckte Saetze ueber das Verhaeltnis Dauer : Textlaenge.
Aufruf:  python tools/audio_plausi.py <book_id> <lang>
Ergebnis: work/audio_plausi_<lang>.txt (verdaechtige Saetze, Grund) -> Kandidaten fuer Neuerzeugung
"""
import glob, json, os, statistics, sys, wave

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(book_id, lg):
    werk = glob.glob(os.path.join(HIER, "authors", "*", "books", book_id))[0]
    d = json.load(open(os.path.join(werk, "work", "400_regie.json"), encoding="utf-8"))["content"]
    audio = os.path.join(werk, "fassungen", lg, "audio")
    werte, fehlt = {}, []
    for t, e in d.items():
        txt = (e.get(lg) or "").strip()
        if e.get("type") not in ("h", "s", "dl", "qt", "vs") or not txt:
            continue
        p = os.path.join(audio, f"{t}.wav")
        if not os.path.exists(p):
            fehlt.append(t)
            continue
        with wave.open(p) as w:
            werte[t] = (w.getnframes() / w.getframerate(), len(txt))
    tempo = statistics.median(s / max(c, 1) for s, c in werte.values() if c >= 20)
    auff = []
    for t, (s, c) in werte.items():
        erwartet = c * tempo
        if c < 12:                                   # sehr kurze Zeilen: nur grobe Grenzen
            if s > erwartet * 3 + 1.5:
                auff.append((t, "zu lang (Nachhall?)", s, erwartet))
        elif s > erwartet * 1.7 + 0.8:
            auff.append((t, "zu lang (Nachhall?)", s, erwartet))
        elif s < erwartet * 0.55:
            auff.append((t, "zu kurz (abgeschnitten?)", s, erwartet))
    pfad = os.path.join(werk, "work", f"audio_plausi_{lg}.txt")
    with open(pfad, "w", encoding="utf-8") as f:
        f.write(f"{book_id} [{lg}] | {len(werte)} Saetze | Tempo {1 / tempo:.1f} Zeichen/s | "
                f"auffaellig {len(auff)} | fehlend {len(fehlt)}\n\n")
        for t, g, s, e in sorted(auff):
            f.write(f"{t}\t{g}\t{s:.1f}s statt ~{e:.1f}s\t{d[t].get(lg, '')[:90]}\n")
        for t in fehlt:
            f.write(f"{t}\tFEHLT\n")
    print(f"[plausi] {book_id} [{lg}]: {len(werte)} Saetze, {len(auff)} auffaellig, {len(fehlt)} fehlend -> {pfad}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
