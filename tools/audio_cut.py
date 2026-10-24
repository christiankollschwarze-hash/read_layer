r"""
READ LAYER — audio_cut.py  (WAV-Schnittwerkzeug + Kette mit 58b)
===============================================================
Zweck: Kurzsatz-Doppler reparieren. Gemini-TTS verdoppelt sehr kurze Saetze
(z.B. "Er erhielt keine Antwort." -> zweimal gesprochen). Dieses Werkzeug
schneidet die WAV an der Naht zwischen den zwei Durchlaeufen und verwirft den
hinteren Teil (= die Wiederholung).

KEINE neue Abhaengigkeit: nur Standard-Modul `wave` (+ optional die 58b-Reports).

SCHNITTPUNKT (so treffsicher wie moeglich):
  --silence  sucht die LEISESTE Stelle (RMS-Minimum) nahe der Mitte = Pause
             zwischen den zwei Doppler-Durchlaeufen. Trifft auch unsaubere Faelle.
  --at SEK   manueller Schnittpunkt.

SICHERHEITSNETZ:
  - Schnitt schreibt zuerst nach <tag>_cut.wav. Original bleibt unangetastet.
  - --commit ersetzt Original (vorher Backup nach <tag>_orig.wav). --revert zurueck.
  - Arbeitsdateien (_cut/_orig) werden NIE automatisch geloescht -- nur per
    --cleanup oder am Ende der Kette NACH ausdruecklicher Bestaetigung.

================================================================
KETTE (--chain): alles in einem Durchlauf
================================================================
  python audio_cut.py <book> --lang de --chain

Ablauf:
  1. 58b Vollscan  -> flaggt too_many (Doppler-Verdacht)
  2. Schnitt pro Flag:
       - GLATTE Verdopplung (ist ~= 2*soll, Toleranz) -> Stille-Naht AUTOMATISCH
       - UNSAUBER (z.B. 1.5x, 3x) -> interaktiv [c]ut/[l]eave/[m SEK]/[s]kip
     (--auto schaltet auch die unsauberen auf automatisch; NICHT empfohlen)
  3. 58b-RECHECK nur ueber die geschnittenen Tags
  4. Bilanz + ABNAHMEFRAGE: "Aufraeumen? [j/n]" -- DU hoerst vorher rein.
  5. Nach 'j': _cut.wav + _orig.wav NUR der vom Recheck als sauber bestaetigten
     Tags loeschen -> Struktur wieder sauber 1:1. Noch geflaggte BEHALTEN ihre
     Arbeitsdateien (Backup bleibt, bis du sie von Hand abschliesst).

  -> 58b sagt WAS (nur invalide), Stille-Naht schlaegt WO vor, Recheck prueft
     den Schnitt nach, DU nimmst ab, dann erst raeumt es auf.

EINZEL-/STAPEL-MODI (wie bisher):
  --info | --silence | --at SEK | --commit | --revert        (mit --tag)
  --from-report [--auto]                                      (Stapel mit Abfrage)
  --cleanup [--tag <id>]                                      (Arbeitsdateien weg)

CLI:
  python audio_cut.py <book> --lang de --chain [--auto] [--tol 0.4] [--model tiny]
  python audio_cut.py <book> --lang de --tag <id> [--info|--silence|--at SEK|--commit|--revert]
  python audio_cut.py <book> --lang de --from-report [--auto]
  python audio_cut.py <book> --lang de --cleanup [--tag <id>]
  optional: --start SEK | --path datei.wav
"""

import sys, os, wave, shutil, json, struct


# ---- Pfad-Aufloesung -----------------------------------------------------

def _audio_dir(book_id, lang):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import config
    return os.path.join(config.book_dir(book_id), "fassungen", lang, "audio")


def _audio_path(book_id, lang, tag_id, direct_path=None):
    if direct_path:
        return direct_path
    return os.path.join(_audio_dir(book_id, lang), f"{tag_id}.wav")


# ---- WAV-Helfer ----------------------------------------------------------

def _wav_info(path):
    with wave.open(path, "rb") as w:
        return {"channels": w.getnchannels(), "sampwidth": w.getsampwidth(),
                "framerate": w.getframerate(), "nframes": w.getnframes(),
                "duration": w.getnframes() / float(w.getframerate() or 1)}


def _read_samples(path):
    with wave.open(path, "rb") as w:
        fr = w.getframerate(); sw = w.getsampwidth(); ch = w.getnchannels()
        raw = w.readframes(w.getnframes())
    if sw != 2:
        return None, fr
    vals = struct.unpack("<" + "h" * (len(raw) // 2), raw)
    if ch == 2:
        vals = vals[0::2]
    return vals, fr


def _find_silence_seam(path):
    """Leiseste Stelle (RMS-Min) im Band [40%,60%], leicht zur Mitte gewichtet.
    = Pause zwischen den zwei Doppler-Durchlaeufen. Sekunde zurueck."""
    vals, fr = _read_samples(path)
    if not vals:
        return None
    n = len(vals)
    win = max(1, int(0.020 * fr))
    lo_i, hi_i = int(0.40 * n), int(0.60 * n)
    mid = n / 2.0
    best_i, best_score = None, None
    step = max(1, win // 4)
    i = lo_i
    while i < hi_i:
        seg = vals[i:i + win]
        if not seg:
            break
        rms = (sum(s * s for s in seg) / len(seg)) ** 0.5
        dist_pen = abs((i + win / 2.0) - mid) / mid
        score = rms + dist_pen * 50.0
        if best_score is None or score < best_score:
            best_score, best_i = score, i + win // 2
        i += step
    return (best_i / float(fr)) if best_i is not None else None


def _cut(src, dst, start_sec, end_sec):
    with wave.open(src, "rb") as w:
        ch = w.getnchannels(); sw = w.getsampwidth()
        fr = w.getframerate(); nf = w.getnframes()
        start_f = max(0, int(round(start_sec * fr)))
        end_f = min(nf, int(round(end_sec * fr)))
        if end_f <= start_f:
            raise ValueError(f"Leerer Schnittbereich: {start_sec}s..{end_sec}s "
                             f"(WAV {nf/float(fr):.2f}s).")
        w.setpos(start_f)
        frames = w.readframes(end_f - start_f)
    with wave.open(dst, "wb") as o:
        o.setnchannels(ch); o.setsampwidth(sw); o.setframerate(fr)
        o.writeframes(frames)
    return (end_f - start_f) / float(fr)


# ---- Aktionen (Einzel) ---------------------------------------------------

def do_info(wav):
    if not os.path.exists(wav):
        print(f"[cut] Nicht gefunden: {wav}"); return
    i = _wav_info(wav); seam = _find_silence_seam(wav)
    print(f"[cut] {os.path.basename(wav)}")
    print(f"      Dauer: {i['duration']:.3f}s | {i['framerate']} Hz | "
          f"{i['sampwidth']*8} bit | {i['nframes']} Frames")
    print(f"      Mitte: {i['duration']/2:.2f}s | Stille-Naht: "
          + (f"{seam:.2f}s" if seam else "nicht ermittelbar"))


def _make_preview(wav, end_sec, note, start_sec=0.0):
    base, _ = os.path.splitext(wav)
    dst = base + "_cut.wav"
    total = _wav_info(wav)["duration"]
    kept = _cut(wav, dst, start_sec, end_sec)
    print(f"[cut] {os.path.basename(dst)}  ({note}) — "
          f"behalten 0.00..{end_sec:.2f}s = {kept:.2f}s von {total:.2f}s")
    return dst


def do_silence(wav):
    if not os.path.exists(wav):
        print(f"[cut] Nicht gefunden: {wav}"); return
    seam = _find_silence_seam(wav)
    if seam is None:
        print("[cut] Stille-Naht nicht ermittelbar -> --at SEK manuell."); return
    _make_preview(wav, seam, f"Stille-Naht @ {seam:.2f}s")


def do_cut_at(wav, start_sec, end_sec):
    if not os.path.exists(wav):
        print(f"[cut] Nicht gefunden: {wav}"); return
    _make_preview(wav, end_sec, f"manuell @ {end_sec:.2f}s", start_sec)


def do_commit(wav, quiet=False):
    base, _ = os.path.splitext(wav)
    cut, orig = base + "_cut.wav", base + "_orig.wav"
    if not os.path.exists(cut):
        print(f"[cut] Keine Vorschau {os.path.basename(cut)} -> erst schneiden."); return
    if not os.path.exists(orig):
        shutil.copy2(wav, orig)
        if not quiet:
            print(f"[cut] Original gesichert -> {os.path.basename(orig)}")
    shutil.copy2(cut, wav)
    print(f"[cut] Uebernommen: {os.path.basename(wav)}.")


def do_revert(wav):
    base, _ = os.path.splitext(wav)
    orig = base + "_orig.wav"
    if not os.path.exists(orig):
        print("[cut] Kein Backup -> nichts zu tun."); return
    shutil.copy2(orig, wav)
    print(f"[cut] Wiederhergestellt: {os.path.basename(wav)}.")


def _cleanup_tag(audio_dir, tag):
    """Entfernt _cut.wav + _orig.wav eines Tags. Gibt Anzahl geloeschter Dateien."""
    n = 0
    for suffix in ("_cut.wav", "_orig.wav"):
        p = os.path.join(audio_dir, f"{tag}{suffix}")
        if os.path.exists(p):
            os.remove(p); n += 1
    return n


def do_cleanup(book_id, lang, tag=None):
    audio_dir = _audio_dir(book_id, lang)
    if tag:
        n = _cleanup_tag(audio_dir, tag)
        print(f"[cut] Aufgeraeumt: {tag} ({n} Arbeitsdatei(en) entfernt).")
        return
    # ohne --tag: alle _cut/_orig im Ordner
    removed = 0
    for f in os.listdir(audio_dir):
        if f.endswith("_cut.wav") or f.endswith("_orig.wav"):
            os.remove(os.path.join(audio_dir, f)); removed += 1
    print(f"[cut] Aufgeraeumt: {removed} Arbeitsdatei(en) im Ordner entfernt.")


# ---- 58b-Anbindung -------------------------------------------------------

def _run_58b(book_id, lang, only_tags=None, model="tiny"):
    """Ruft Stage 58b auf und liest den frisch geschriebenen _stt_report.json.
    only_tags: Liste -> gezielter Recheck. Gibt die too_many-Tag-Liste zurueck."""
    from pipeline import stage_58b_stt_validate as stt
    only = ",".join(only_tags) if only_tags else None
    stt.run(book_id, lang=lang, model_size=model, fix=False, only=only)
    audio_dir = _audio_dir(book_id, lang)
    return _flagged_from_report(audio_dir)


def _flagged_from_report(audio_dir):
    rpath = os.path.join(audio_dir, "_stt_report.json")
    if not os.path.exists(rpath):
        return []
    rep = json.load(open(rpath, encoding="utf-8"))
    # rows: [tag, soll, ist, lo, hi]
    return rep.get("too_many", [])


# ---- interaktive Abfrage -------------------------------------------------

def _ask(tag):
    while True:
        ans = input(f"    [{tag}]  anhoeren -> "
                    f"[c]ut / [l]eave / [m SEK] / [s]kip / [q]uit ? ").strip().lower()
        if ans in ("c", "cut"):   return "cut"
        if ans in ("l", "leave"): return "leave"
        if ans in ("s", "skip"):  return "skip"
        if ans in ("q", "quit"):  return "quit"
        if ans.startswith("m"):
            parts = ans.split()
            if len(parts) == 2:
                try: return float(parts[1])
                except ValueError: pass
            print("    -> Format: m 4.2"); continue
        print("    -> c / l / m SEK / s / q")


# ---- STAPEL aus Report ---------------------------------------------------

def do_from_report(book_id, lang, auto=False):
    audio_dir = _audio_dir(book_id, lang)
    rows = _flagged_from_report(audio_dir)
    tags = [r[0] for r in rows]
    if not tags:
        print("[cut] Keine geflaggten (too_many) Tags im Report."); return []
    return _cut_tags(audio_dir, rows, auto=auto)


def _is_clean_double(soll, ist, tol):
    """Glatte Verdopplung? ist ~= 2*soll innerhalb relativer Toleranz tol."""
    if soll <= 0:
        return False
    return abs(ist - 2 * soll) <= max(1, tol * 2 * soll)


def _cut_tags(audio_dir, rows, auto=False, tol=0.4):
    """Schneidet eine Liste geflaggter Tags. rows: [tag,soll,ist,lo,hi].
    Glatte 2x automatisch (Stille-Naht); unsaubere interaktiv (ausser --auto).
    Gibt die Liste der Tags zurueck, die committed wurden."""
    committed = []
    n_cut = n_leave = n_skip = 0
    for row in rows:
        tag, soll, ist = row[0], row[1], row[2]
        wav = os.path.join(audio_dir, f"{tag}.wav")
        if not os.path.exists(wav):
            print(f"  {tag}: WAV fehlt -> uebersprungen"); continue
        seam = _find_silence_seam(wav)
        if seam is None:
            print(f"  {tag}: Stille-Naht nicht ermittelbar -> manuell (--at)"); continue

        clean = _is_clean_double(soll, ist, tol)
        _make_preview(wav, seam, f"Stille-Naht @ {seam:.2f}s | soll {soll} ist {ist}"
                                 f"{' [glatt 2x]' if clean else ' [UNSAUBER]'}")

        if auto or clean:
            # glatte Verdopplung (oder --auto): automatisch uebernehmen
            do_commit(wav, quiet=True); committed.append(tag); n_cut += 1
            if not (auto or clean):
                pass
            print()
            continue

        # unsauber -> ans Ohr
        decision = _ask(tag)
        while isinstance(decision, float):
            _make_preview(wav, decision, f"manuell @ {decision:.2f}s")
            decision = _ask(tag)
        if decision == "cut":
            do_commit(wav, quiet=True); committed.append(tag); n_cut += 1
        elif decision == "leave":
            cf = os.path.splitext(wav)[0] + "_cut.wav"
            if os.path.exists(cf): os.remove(cf)
            print(f"    {tag}: stehen gelassen."); n_leave += 1
        elif decision == "skip":
            print(f"    {tag}: uebersprungen."); n_skip += 1
        elif decision == "quit":
            print("[cut] Abgebrochen."); break
        print()
    print(f"[cut] Schnitt-Bilanz: {n_cut} geschnitten, {n_leave} gelassen, "
          f"{n_skip} uebersprungen.")
    return committed


# ---- KETTE ---------------------------------------------------------------

def do_chain(book_id, lang, auto=False, tol=0.4, model="tiny"):
    audio_dir = _audio_dir(book_id, lang)
    print("=" * 60)
    print(f"[chain] {book_id} / {lang}: 58b -> Schnitt -> Recheck -> Aufraeumen")
    print("=" * 60)

    # 1. Vollscan
    print("\n[chain] Schritt 1: 58b Vollscan ...")
    rows = _run_58b(book_id, lang, only_tags=None, model=model)
    if not rows:
        print("[chain] Keine Doppler-Flags. Nichts zu tun -> fertig."); return
    print(f"[chain] {len(rows)} Flag(s): {', '.join(r[0] for r in rows)}")

    # 2. Schnitt
    print("\n[chain] Schritt 2: Schnitt (glatte 2x auto, unsaubere ans Ohr) ...")
    committed = _cut_tags(audio_dir, rows, auto=auto, tol=tol)
    if not committed:
        print("[chain] Nichts geschnitten -> kein Recheck noetig. Fertig."); return

    # 3. Recheck nur ueber die geschnittenen
    print(f"\n[chain] Schritt 3: 58b-Recheck ueber {len(committed)} geschnittene Tags ...")
    still = _run_58b(book_id, lang, only_tags=committed, model=model)
    still_tags = {r[0] for r in still}
    clean_tags = [t for t in committed if t not in still_tags]

    print("\n[chain] --- Recheck-Ergebnis ---")
    print(f"[chain] sauber nach Schnitt: {len(clean_tags)} "
          f"({', '.join(clean_tags) if clean_tags else '-'})")
    print(f"[chain] flaggt noch:        {len(still_tags)} "
          f"({', '.join(still_tags) if still_tags else '-'})")

    # 4. Abnahmefrage
    if not clean_tags:
        print("\n[chain] Nichts sauber bestaetigt -> kein Aufraeumen. "
              "Arbeitsdateien (_cut/_orig) bleiben fuer dein Ohr liegen.")
        return
    print("\n[chain] Schritt 4: Vor dem Aufraeumen die geschnittenen Tags ANHOEREN.")
    print("        Aufgeraeumt werden NUR die als sauber bestaetigten:")
    print(f"        {', '.join(clean_tags)}")
    ans = input("\n[chain] Aufraeumen (Arbeitsdateien dieser Tags loeschen)? [j/n] ").strip().lower()
    if ans not in ("j", "ja", "y", "yes"):
        print("[chain] Kein Aufraeumen. Alle Arbeitsdateien bleiben liegen.")
        return

    # 5. Aufraeumen NUR der bestaetigten
    removed = 0
    for t in clean_tags:
        removed += _cleanup_tag(audio_dir, t)
    print(f"[chain] Aufgeraeumt: {removed} Arbeitsdatei(en) von {len(clean_tags)} Tags entfernt.")
    if still_tags:
        print(f"[chain] HINWEIS: {len(still_tags)} Tag(s) flaggen noch "
              f"-> Arbeitsdateien BEHALTEN, bitte manuell pruefen "
              f"(--tag <id> --at SEK / --revert).")
    print("[chain] Fertig.")


# ---- CLI -----------------------------------------------------------------

def _opt(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        return sys.argv[i+1] if i+1 < len(sys.argv) else default
    return default


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("Aufruf: python audio_cut.py <book> --lang de --chain [--auto]\n"
              "   oder: --tag <id> (--info|--silence|--at SEK|--commit|--revert)\n"
              "   oder: --from-report [--auto] | --cleanup [--tag <id>]")
        return
    book = args[0]
    lang = _opt("--lang", "de")
    tol = float(_opt("--tol", "0.4") or 0.4)
    model = _opt("--model", "tiny")

    if "--chain" in sys.argv:
        do_chain(book, lang, auto="--auto" in sys.argv, tol=tol, model=model); return
    if "--from-report" in sys.argv:
        do_from_report(book, lang, auto="--auto" in sys.argv); return
    if "--cleanup" in sys.argv:
        do_cleanup(book, lang, tag=_opt("--tag")); return

    tag = _opt("--tag"); direct = _opt("--path")
    if not tag and not direct:
        print("[cut] --tag <id> / --path / --chain / --from-report / --cleanup noetig."); return
    wav = _audio_path(book, lang, tag, direct)

    if "--info" in sys.argv:      do_info(wav)
    elif "--commit" in sys.argv:  do_commit(wav)
    elif "--revert" in sys.argv:  do_revert(wav)
    elif "--silence" in sys.argv: do_silence(wav)
    elif "--at" in sys.argv:      do_cut_at(wav, float(_opt("--start", "0") or 0), float(_opt("--at")))
    else:                         do_info(wav)


if __name__ == "__main__":
    main()
