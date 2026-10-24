"""STAGE — — Schnitt-Bibliothek (keine Stage)
Funktion:     Schnittfunktionen fuer Sprachaufnahmen.
Wirkungsweise: Energietal-Suche und Konsonanten-Nachlauf; frueher LibriVox-Gleis von Stage 58.
Komponenten:  pipeline/schnitt_lib.py
Zulieferer:   —
Abnehmer:     gpu_lora/lora_modal.py (s900 LoRA)
(Nomenklatur seit 18.10.2026, Uebersicht: docs/Pipeline_Strang_Matrix.xlsx)

--- Bisherige Beschreibung ---
HINWEIS 18.10.2026: Kein Stage-58-Gleis mehr (LibriVox-Audio-Strang archiviert, run.py ruft das
Modul nicht mehr auf). Bleibt, weil gpu_lora/lora_modal.py die Schnittfunktionen nutzt
(_find_valley, _end_consonant_ms, TAIL/SEARCH_PAD/NEXT_GUARD).


READ LAYER — Stage 58 (3rd party): LibriVox-Audio statt TTS
===========================================================
Ersatz fuer Stage 58 (Cloud-TTS), wenn die Fassung fremdes menschliches
PD-Audio nutzt (audio_quelle == "librivox"). Erzeugt DASSELBE Ausgabeformat
wie der TTS-Pfad -- fassungen/<lang>/audio/<tag_id>.wav -- damit der Rest der
Pipeline (Checkpoint _audio_done, Assembler 59, App-Export) NICHT unterscheidet,
woher das Audio kommt.

SPRACHNEUTRAL: run(book_id, lang). Liest die Sprecher-MP3s aus
  fassungen/<lang>/source_audio/   (Kapitelnummer = erste Zahl im Dateinamen)
und richtet sie gegen die Tag-Texte der Sprache <lang> aus 200_tagging.json aus
(bei der Originalsprache = en-Text; bei uebersetzter Aufnahme = uebersetzter Tag-Text).

FAEDELT die bewiesene LibriVox-Kette auf (1 Befehl, pro Kapitel):
  1b  STT ueber das Kapitel-Audio (faster-whisper) -> Wort-Zeitstempel (gecacht)
  1c  STT<->Tag-Text-Abgleich (difflib) -> Korridor je Audio-Tag
  1d  Schnitt am Energietal + Konsonanten-Korrektur -> <tag_id>.wav

RESILIENZ: pro Kapitel wird der STT-Cache abgelegt
  fassungen/<lang>/source_audio/_stt/chapter-NN.json
-> Wiederanlauf nach Abbruch transkribiert NICHT neu. Kein Cache-Trick, nur
   Checkpoint wie bei den anderen Stages.

Konsonanten-Werte (CK am Ohr bestaetigt): Plosiv 70 ms, Frikativ 120 ms.

Aufruf ueber run.py (audio-Linie, Weiche bei Stage 58):
  python run.py call-of-the-wild --line audio --lang en --live
Direkt:
  python -m pipeline.schnitt_lib call-of-the-wild --lang en
"""

import os
import re
import sys
import json
import wave
import difflib

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config

STAGE = "schnitt_lib"

# --- Schnitt-Parameter (CK am Ohr bestaetigt) -------------------------------
PLOSIV_MS    = 70
FRIK_MS      = 120
TAIL_MS      = 80
SEARCH_PAD_S = 0.15
NEXT_GUARD_S = 0.03
CAP_MS       = 260
MIN_MATCH    = 0.4     # Tag unter dieser Match-Quote -> geflaggt (kein Korridor)

# --- STT ---
STT_MODEL = "medium"   # wie librivox_step1b; --model ueberschreibt
STT_LANG_DEFAULT = None  # None -> Sprache der Fassung


# ============================================================
# KONSONANTEN-KORREKTUR (sprachspezifisch; aktuell en-Regeln)
# ============================================================
_DIGRAPHS = ("tch", "sch", "ch", "ck", "sh", "ss", "th", "ng", "ph", "gh")


def _last_word(s):
    ws = re.findall(r"[A-Za-z']+", s or "")
    return ws[-1].lower().strip("'") if ws else ""


def _end_consonant_ms(text, plosiv_ms=PLOSIV_MS, frik_ms=FRIK_MS, cap_ms=CAP_MS):
    """Summiert die Nachlauf-Zeiten der ausklingenden End-Konsonantlaute.
    Whisper hoert leise stimmlose Auslaute nicht -> Wortende zu frueh -> Korridor
    nach hinten schieben, damit das Tal hinter dem Konsonanten liegt."""
    w = _last_word(text)
    if not w:
        return 0
    if w.endswith('e') and not w.endswith(('ce', 'se', 'ze')):
        return 0
    if re.search(r'(ow|aw|ew|gh|ay|ey|oy|y)$', w):
        return 0
    total, i = 0, len(w)
    while i > 0:
        matched = None
        for dg in _DIGRAPHS:
            if w[:i].endswith(dg):
                matched = dg; break
        laut = matched if matched else w[i-1]
        i -= len(laut)
        if laut in ("th", "ng", "ph", "gh"):
            break
        if laut in ("ch", "sch", "tch", "sh", "ss", "s", "z", "x", "f"):
            total += frik_ms
            if laut == "x":
                total += plosiv_ms
            continue
        if laut in ("ck",) or laut in ("t", "d", "k", "g", "p", "b", "c"):
            total += plosiv_ms
            continue
        break
    return min(total, cap_ms)


# ============================================================
# WAV / STT
# ============================================================
def _read_wav_int16(path):
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    return x, sr


def _write_wav(path, x_int16, sr):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(x_int16.tobytes())


def _mp3_to_wav16k(mp3_path, wav_path):
    """MP3 -> WAV 16 kHz mono via direktem ffmpeg-Aufruf (wie librivox_step1)."""
    import subprocess
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(mp3_path), "-ac", "1", "-ar", "16000",
         "-f", "wav", str(wav_path)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _stt_transcribe(wav_path, model_size, lang):
    """faster-whisper ueber das ganze Kapitel, Wort-Zeitstempel (wie step1b)."""
    from faster_whisper import WhisperModel
    print(f"    [stt] Modell '{model_size}' (cpu/int8) laedt ...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        str(wav_path), language=lang, beam_size=1,
        word_timestamps=True, vad_filter=False)
    words = []
    nseg = 0
    for s in segments:
        nseg += 1
        if s.words:
            for w in s.words:
                words.append({"w": w.word.strip(),
                              "start": round(w.start, 3),
                              "end": round(w.end, 3)})
        print(f"\r    [stt] ... bis {s.end/60:5.1f} min ({nseg} seg, {len(words)} W)   ",
              end="", flush=True)
    print()
    return {"model": model_size, "language": lang,
            "audio_duration_s": round(info.duration, 1) if info else None,
            "n_words": len(words), "words": words}


def _ensure_stt(mp3_path, cache_path, model_size, lang, force=False):
    """Liefert das STT-Transkript fuer ein Kapitel. Cache = Resilienz-Checkpoint."""
    if os.path.exists(cache_path) and not force:
        d = json.load(open(cache_path, encoding="utf-8"))
        print(f"    [stt] Cache: {os.path.basename(cache_path)} "
              f"({d.get('n_words')} Woerter)")
        return d
    tmp_wav = cache_path.replace(".json", ".wav")
    print(f"    [stt] {os.path.basename(mp3_path)} -> WAV ...")
    _mp3_to_wav16k(mp3_path, tmp_wav)
    d = _stt_transcribe(tmp_wav, model_size, lang)
    json.dump(d, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    try:
        os.remove(tmp_wav)
    except OSError:
        pass
    return d


# ============================================================
# TAG-KORRIDORE (1c gegen Tag-Texte)  +  SCHNITT (1d)
# ============================================================
def _norm(w):
    return re.sub(r"[^a-z0-9]", "", w.lower())


def _audio_units(stage00, chapter_key, lang):
    """Audio-tragende Einheiten EINES Kapitels in Lesefolge, AUSSCHLIESSLICH
    aus dem content (Single Source of Truth = Stage 50).

    KEIN kuenstlicher Header mehr: Der Kapitel-Header ist seit dem Stage-50-Fix
    ein regulaerer content-Knoten (c<N>_00001_h, Text aus der ###CHAPTER###-Marke)
    und wird hier -- wie jeder andere audio-tragende Tag -- ganz normal erfasst
    (h ist nicht in NO_AUDIO_TYPES). 58b ERFINDET keine Struktur, es richtet nur
    das Audio gegen die vorhandene Wahrheit aus. So kann Text<->Audio bei den
    Headern nicht mehr auseinanderlaufen."""
    content = stage00["content"]
    units = []
    for tid, v in content.items():
        if not tid.startswith(chapter_key + "_"):
            continue
        if v.get("type") in config.NO_AUDIO_TYPES:
            continue
        txt = v.get(lang, "") or v.get(config.SOURCE_LANGUAGE, "")
        units.append((tid, v.get("type"), txt))
    return units


def _corridors(units, stt_words):
    """difflib-Abgleich Tag-Woerter <-> STT-Woerter -> Korridor je Einheit."""
    tag_words, word_unit = [], []
    for ui, (_tid, _typ, txt) in enumerate(units):
        for w in re.findall(r"\w+", txt):
            nw = _norm(w)
            if nw:
                tag_words.append(nw); word_unit.append(ui)
    stt_norm = [_norm(w["w"]) for w in stt_words]

    sm = difflib.SequenceMatcher(a=tag_words, b=stt_norm, autojunk=False)
    tag2stt = {}
    for ai, bj, size in sm.get_matching_blocks():
        for k in range(size):
            tag2stt[ai + k] = bj + k

    rows = []
    for ui, (tid, typ, txt) in enumerate(units):
        idxs = [i for i, u in enumerate(word_unit) if u == ui]
        st = [stt_words[tag2stt[i]]["start"] for i in idxs if i in tag2stt]
        en = [stt_words[tag2stt[i]]["end"]   for i in idxs if i in tag2stt]
        nw, nm = len(idxs), len(st)
        ok = bool(st and en) and (nm / max(1, nw) >= MIN_MATCH)
        rows.append({"tag_id": tid, "typ": typ, "text": txt,
                     "start_s": (min(st) if ok else None),
                     "end_s":   (max(en) if ok else None),
                     "n_match": nm, "n_word": nw})
    matched = len(tag2stt)
    return rows, matched, len(tag_words)


def _find_valley(x, sr, lo_s, hi_s):
    lo = max(0, int(lo_s * sr)); hi = min(len(x), int(hi_s * sr))
    if hi - lo < int(0.02 * sr):
        return (lo_s + hi_s) / 2.0
    seg = x[lo:hi].astype(np.float32) / 32768.0
    win, hop = int(0.025 * sr), int(0.010 * sr)
    if len(seg) < win:
        return (lo_s + hi_s) / 2.0
    nfr = 1 + (len(seg) - win) // hop
    rms = np.empty(nfr)
    for i in range(nfr):
        fr = seg[i*hop:i*hop+win]
        rms[i] = np.sqrt(np.mean(fr*fr) + 1e-12)
    k = int(np.argmin(rms))
    return lo_s + (k*hop + win/2) / sr


def _cut_and_write(rows, wav_path, audio_dir):
    """Schnitt am Tal (1d) je Korridor; schreibt <tag_id>.wav. Gibt n_written."""
    x, sr = _read_wav_int16(wav_path)
    anchored = [r for r in rows if r["start_s"] is not None]
    merged = [r["tag_id"] for r in rows if r["start_s"] is None]
    tail_s = TAIL_MS / 1000.0

    cuts = []
    n = len(anchored)
    for i in range(n - 1):
        end_n = anchored[i]["end_s"]
        start_n1 = anchored[i+1]["start_s"]
        cons_ms = _end_consonant_ms(anchored[i]["text"])
        end_corr = end_n + cons_ms / 1000.0
        gap = start_n1 - end_n
        if gap < 0.05:                       # Whisper-Luecke entartet -> Tal vertrauen
            lo, hi = end_corr - SEARCH_PAD_S, end_corr + 0.8
            next_clamp = hi
        else:
            lo, hi = end_corr - SEARCH_PAD_S, start_n1 + SEARCH_PAD_S
            next_clamp = start_n1 - NEXT_GUARD_S
        vt = _find_valley(x, sr, lo, hi)
        cut = min(vt + tail_s, next_clamp)
        cut = max(cut, end_corr)
        cuts.append(cut)

    bounds = [anchored[0]["start_s"]] + cuts + [anchored[-1]["end_s"]]
    os.makedirs(audio_dir, exist_ok=True)
    n_written = 0
    for i in range(len(anchored)):
        a_s, b_s = bounds[i], bounds[i+1]
        if b_s <= a_s:
            continue
        a, b = int(a_s * sr), int(b_s * sr)
        _write_wav(os.path.join(audio_dir, f"{anchored[i]['tag_id']}.wav"),
                   x[a:b], sr)
        n_written += 1
    return n_written, merged


# ============================================================
# HAUPTPROZESS
# ============================================================
def _chapter_num(filename):
    m = re.search(r"(\d+)", filename)
    return int(m.group(1)) if m else 0


def run(book_id, lang=None, model_size=None, force=False):
    lang = lang or config.SOURCE_LANGUAGE
    model_size = model_size or STT_MODEL
    bdir = config.book_dir(book_id)
    src_dir = os.path.join(bdir, "fassungen", lang, "source_audio")
    audio_dir = os.path.join(bdir, "fassungen", lang, "audio")
    stt_dir = os.path.join(src_dir, "_stt")
    os.makedirs(stt_dir, exist_ok=True)

    if not os.path.isdir(src_dir):
        raise FileNotFoundError(
            f"Kein Sprecher-Audio: {src_dir} (audio_quelle=librivox erwartet MP3s hier).")

    mp3s = sorted([f for f in os.listdir(src_dir) if f.lower().endswith(".mp3")],
                  key=_chapter_num)
    if not mp3s:
        raise FileNotFoundError(f"Keine MP3s in {src_dir}.")

    stage00 = json.load(open(config.work_path(book_id, "200_tagging"), encoding="utf-8"))
    chapters = list(stage00["meta"]["chapters"].keys())   # ['c001', ...] in Reihenfolge

    if len(mp3s) != len(chapters):
        print(f"[stage58_3rd] WARNUNG: {len(mp3s)} MP3s, aber {len(chapters)} Kapitel "
              f"in 200_tagging -> Strom-Modus (Abgleich ueber das ganze Buch).")

    print(f"[stage58_3rd] LibriVox-Audio [{lang}] | {len(mp3s)} Kapitel | "
          f"Plosiv {PLOSIV_MS}ms Frikativ {FRIK_MS}ms")

    stt_lang = lang   # faster-whisper-Sprachcode = Fassungssprache
    total_written, total_flagged = 0, []

    def _schneide(idx, mp3, units, label):
        nonlocal total_written, total_flagged
        mp3_path = os.path.join(src_dir, mp3)
        cache_path = os.path.join(stt_dir, f"chapter-{idx+1:02d}.json")
        stt = _ensure_stt(mp3_path, cache_path, model_size, stt_lang, force=force)
        rows, matched, n_tagwords = _corridors(units, stt["words"])
        cov = [r for r in rows if r["start_s"] is not None]
        rate = 100.0 * matched / max(1, n_tagwords)
        print(f"    [align] {label}: {len(units)} Einheiten | Match {rate:.1f}% | "
              f"Korridor {len(cov)}/{len(rows)}")
        if cov:
            cut_wav = os.path.join(stt_dir, f"chapter-{idx+1:02d}_cut.wav")
            _mp3_to_wav16k(mp3_path, cut_wav)
            n_written, merged = _cut_and_write(rows, cut_wav, audio_dir)
            try:
                os.remove(cut_wav)
            except OSError:
                pass
        else:
            n_written, merged = 0, [r["tag_id"] for r in rows]
        total_written += n_written
        total_flagged += merged
        print(f"    [cut] {n_written} Schnipsel -> fassungen/{lang}/audio/")
        if merged:
            print(f"    [cut] ohne Korridor (geflaggt): {len(merged)}")
        return rows, stt

    if len(mp3s) == len(chapters):
        # Normalfall: LibriVox-Abschnitt = Kapitel
        for idx, mp3 in enumerate(mp3s):
            print(f"\n  Kapitel {idx+1}/{len(mp3s)}  ({chapters[idx]})  {mp3}")
            _schneide(idx, mp3, _audio_units(stage00, chapters[idx], lang), chapters[idx])
    else:
        # STROM-MODUS: Abschnitte != Kapitel. Alle Einheiten des Buchs in Lesefolge;
        # jede MP3 gleicht gegen das Fenster ab, das hinter der zuletzt gefundenen Einheit beginnt.
        alle = []
        for ch in chapters:
            alle += _audio_units(stage00, ch, lang)
        nwort = [len(re.findall(r"\w+", u[2])) for u in alle]
        print(f"[stage58_3rd] STROM-MODUS: {len(mp3s)} Abschnitte gegen {len(alle)} Einheiten "
              f"({len(chapters)} Kapitel)")
        zeiger, gefunden = 0, set()
        for idx, mp3 in enumerate(mp3s):
            if zeiger >= len(alle):
                print(f"  [strom] Text zu Ende, {mp3} uebersprungen")
                break
            cache_path = os.path.join(stt_dir, f"chapter-{idx+1:02d}.json")
            stt0 = _ensure_stt(os.path.join(src_dir, mp3), cache_path, model_size, stt_lang, force=force)
            ziel = int(len(stt0["words"]) * 1.3) + 300          # Fenster: etwas mehr Text als gesprochen
            ende, summe = zeiger, 0
            while ende < len(alle) and (summe < ziel or idx == len(mp3s) - 1):
                summe += nwort[ende]; ende += 1
            print(f"\n  Abschnitt {idx+1}/{len(mp3s)}  {mp3}  -> Einheiten {zeiger}..{ende-1}")
            rows, _ = _schneide(idx, mp3, alle[zeiger:ende], f"Abschnitt {idx+1}")
            treffer = [i for i, r in enumerate(rows) if r["start_s"] is not None]
            gefunden.update(rows[i]["tag_id"] for i in treffer)
            if treffer:
                zeiger += treffer[-1] + 1
            else:
                print(f"  [strom] WARNUNG: kein Treffer in {mp3} -- Zeiger bleibt")
        # Fensterueberhang ist kein Fehler: geflaggt ist nur, was in KEINEM Abschnitt gefunden wurde
        total_flagged = [u[0] for u in alle if u[0] not in gefunden]

    print(f"\n[stage58_3rd] fertig [{lang}]: {total_written} Schnipsel geschrieben, "
          f"{len(total_flagged)} geflaggt -> {audio_dir}")
    return audio_dir


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    def _opt(name, d=None):
        return sys.argv[sys.argv.index(name)+1] if name in sys.argv and \
            sys.argv.index(name)+1 < len(sys.argv) else d
    if "--live" in sys.argv:
        config.RUN_MODE = "live"
    run(args[0] if args else "call-of-the-wild",
        lang=_opt("--lang"), model_size=_opt("--model"),
        force=("--force" in sys.argv))
