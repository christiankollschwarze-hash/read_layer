"""
READ LAYER — audio_fa.py  (Forced-Alignment-Schnitt, EINE Quelle der Wahrheit)
==============================================================================
Portiert 1:1 den bewaehrten Schnitt-Kern aus test_block_schnitt.py (der
177=177-Gewinner). Stage 58 importiert hieraus; der Prototyp kann spaeter
ebenfalls hierher zeigen, statt eine eigene Kopie zu halten.

Prinzip: Der Satztext wird VORGEGEBEN -> MMS_FA (torchaudio) zwingt den
bekannten Wortlaut auf die Zeitachse. Kein STT-Raten, kein kumulativer Versatz
durch Kettenwoerter. Geschnitten wird am ENERGIE-TAL zwischen FA-Wortende und
FA-Folgewort (haelt das letzte Wort GANZ im Clip). fa_pre haelt den Vorlauf
klein, damit das Tal nicht in den Plosiv-Auslaut (-t/-k/-p) rutscht.

Trennung der Verantwortung (anders als im Prototyp):
  - fa_cut(...)        ANALYSIERT nur -> Schnittpunkte + Status je Grenze.
  - slice_block(...)   SCHREIBT benannte Segmente (Stage 58 vergibt die tag_ids).
So bleibt fa_cut rein/testbar; die Datei-/Namensvergabe liegt bei Stage 58.

Setzt torch + torchaudio voraus (MMS_FA-Gewicht ~1.2 GB beim 1. Lauf).
"""

import os, re, wave, contextlib

SR_DEFAULT = 24000            # Gemini-TTS LINEAR16: 24 kHz mono 16-bit
SAMPLE_WIDTH = 2


# ------------------------------------------------------------------ WAV I/O
def write_wav(path, pcm_bytes, sr=SR_DEFAULT):
    with contextlib.closing(wave.open(path, "wb")) as w:
        w.setnchannels(1); w.setsampwidth(SAMPLE_WIDTH); w.setframerate(sr)
        w.writeframes(pcm_bytes)


def read_wav(path):
    with contextlib.closing(wave.open(path, "rb")) as w:
        return w.readframes(w.getnframes()), w.getframerate()


def wordcount(text):
    return len(re.findall(r"\w+", text, flags=re.UNICODE))


def tol(n):
    """Mengen-Toleranz: absoluter Puffer schuetzt kurze Saetze, Prozent haelt lange eng."""
    return 2 + 0.15 * n


def _trim_silence(pcm_bytes, sr, thresh=60, lead_pad_ms=30, trail_pad_ms=120):
    """Beschneidet fuehrende/abschliessende Stille. Schwelle BEWUSST niedrig
    (60 statt 200): leise stimmlose Auslaute (-s/-sch/-t-Release) liegen knapp
    ueber dem Stille-Floor und sollen NICHT mitgetrimmt werden. Schluss-Puffer
    grosszuegig (120 ms), Anfang knapp (30 ms) -> Auslaut bleibt ganz, ohne
    vorne den Folgesatz-Anlauf einzufangen."""
    import numpy as np
    x = np.frombuffer(pcm_bytes, dtype="<i2")
    if x.size == 0:
        return b""
    loud = np.where(np.abs(x) > thresh)[0]
    if loud.size == 0:
        return b""
    a = max(0, int(loud[0]) - int(sr * lead_pad_ms / 1000))
    b = min(x.size, int(loud[-1]) + 1 + int(sr * trail_pad_ms / 1000))
    return x[a:b].tobytes()


# ------------------------------------------------------------------ Akustik-Helfer
def _load_wav_16k_mono(wav_path):
    """Laedt WAV als 16-kHz-mono float32 (MMS_FA/Feature-Bezug). Eigene I/O
    umgeht torchaudio>=2.11-/torchcodec-Abhaengigkeiten."""
    import numpy as np
    pcm, sr = read_wav(wav_path)
    x = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    if sr != 16000:
        n_out = int(round(len(x) * 16000 / sr))
        x = np.interp(np.linspace(0, len(x) - 1, n_out),
                      np.arange(len(x)), x).astype(np.float32)
    return x


def _frame_features(wav_path):
    """Pro 25-ms-Frame: Zeit(Mitte), RMS-Lautstaerke, spektrale Flachheit.
    Plus Lautstaerke-Floor (5%) und Sprechpegel (75%) als Bezug."""
    import numpy as np
    x = _load_wav_16k_mono(wav_path)
    sr, win, hop = 16000, 400, 160
    nfr = 1 + (len(x) - win) // hop if len(x) >= win else 0
    wnd = np.hanning(win)
    times = np.empty(nfr); rms = np.empty(nfr); flat = np.empty(nfr)
    for i in range(nfr):
        fr = x[i*hop:i*hop+win] * wnd
        rms[i] = np.sqrt(np.mean(fr*fr) + 1e-12)
        ps = np.abs(np.fft.rfft(fr))**2 + 1e-12
        flat[i] = np.exp(np.mean(np.log(ps))) / np.mean(ps)
        times[i] = (i*hop + win/2) / sr
    floor = float(np.percentile(rms, 5)) if nfr else 0.0
    speech = float(np.percentile(rms, 75)) if nfr else 0.0
    return times, rms, flat, floor, speech


def _energy_valley(times, rms, speech, a, c, pre=0.18, post=0.30):
    """Findet das leiseste TAL (echte akustische Naht) im Fenster zwischen
    Wortende a und Folgewort-Anfang c. Gibt (Schnittzeit, Tal-Tiefe) zurueck.
    Tal-Tiefe = leisester RMS / Sprechpegel: klein = tiefe Stille (sauber),
    gross (~>0.4) = keine echte Pause (verschliffen)."""
    import numpy as np
    lo, hi = a - pre, c + post
    m = (times >= lo) & (times <= hi)
    if not m.any():
        return (a + c) / 2.0, 1.0
    wt, wr = times[m], rms[m]
    k = int(np.argmin(wr))
    depth = float(wr[k] / speech) if speech > 0 else 1.0
    return float(wt[k]), depth


def syllables(word):
    """Grobe, sprachuebergreifende Silbenzaehlung (Vokalgruppen inkl. Umlaute)."""
    w = word.lower()
    groups = re.findall(r"[aeiouyàâäáãåæéèêëíìîïóòôöõøúùûüýÿœ]+", w)
    return max(1, len(groups))


def _romanize(w):
    """Grobe Romanisierung fuer MMS_FA (kennt nur a-z + Apostroph): Umlaute/ss
    aufloesen, Akzente entfernen, Rest auf a-z' filtern. Vokalkern bleibt
    erhalten -> reicht fuers Alignment (nicht fuer Anzeige)."""
    w = w.lower()
    table = {"ä": "a", "ö": "o", "ü": "u", "ß": "ss",
             "á": "a", "à": "a", "â": "a", "ã": "a", "å": "a",
             "é": "e", "è": "e", "ê": "e", "ë": "e",
             "í": "i", "ì": "i", "î": "i", "ï": "i",
             "ó": "o", "ò": "o", "ô": "o", "õ": "o", "ø": "o",
             "ú": "u", "ù": "u", "û": "u",
             "ç": "c", "ñ": "n", "ý": "y", "œ": "oe", "æ": "ae"}
    for k, v in table.items():
        w = w.replace(k, v)
    return re.sub(r"[^a-z']", "", w)


# ------------------------------------------------------------------ FA-Schnitt (Analyse)
_FA_CACHE = {}


def _fa_word_spans(wav_path, words):
    """GEMEINSAMER FA-Kern (MMS_FA). words = flache Wortliste.
    Gibt (word_times, n_tokens):
      word_times[i] = (start_s, end_s, score) -- Zeiten relativ zum WAV-Anfang,
                      oder None, wenn das Wort kein MMS-Token ergab.
      n_tokens      = Gesamtzahl ausgerichteter Tokens (0 -> nichts ausrichtbar).
    EINE Quelle der Wahrheit fuer fa_cut (Schnitt) UND align_words (UI-Timing).
    Setzt torch + torchaudio voraus (MMS_FA-Gewicht ~1.2 GB beim 1. Lauf)."""
    import torch, torchaudio
    import torchaudio.functional as AF

    bundle = torchaudio.pipelines.MMS_FA
    sr_fa = bundle.sample_rate                       # 16000
    cached = _FA_CACHE.get("mms")
    if cached is None:
        model = bundle.get_model(with_star=False)
        DICT = bundle.get_dict(star=None)
        _FA_CACHE["mms"] = (model, DICT)
    else:
        model, DICT = cached

    x16 = _load_wav_16k_mono(wav_path)
    wav = torch.from_numpy(x16).unsqueeze(0)
    with torch.inference_mode():
        emission, _ = model(wav)
    num_frames = emission.size(1)
    ratio = wav.size(1) / num_frames

    def fr2s(fr):
        return fr * ratio / sr_fa

    # Tokenisierung: pro Wort eine Token-Liste (gefiltert aufs MMS-Alphabet)
    flat, lengths = [], []
    for w in words:
        tk = [DICT[c] for c in _romanize(w) if c in DICT]
        flat += tk
        lengths.append(len(tk))
    if not flat:
        return [None] * len(words), 0

    targets = torch.tensor([flat], dtype=torch.int32)
    aligned, scores = AF.forced_align(emission, targets, blank=0)
    aligned, scores = aligned[0], scores[0].exp()
    spans = AF.merge_tokens(aligned, scores)

    word_times, k = [], 0
    for L in lengths:
        sp = spans[k:k + L]
        k += L
        if sp:
            sc = sum(s.score * len(s) for s in sp) / max(1, sum(len(s) for s in sp))
            word_times.append((fr2s(sp[0].start), fr2s(sp[-1].end), float(sc)))
        else:
            word_times.append(None)
    return word_times, len(flat)


def align_words(wav_path, text):
    """Richtet EINEN fertigen Schnipsel-WAV gegen seinen Satztext aus.
    Gibt Wortzeiten SCHNIPSEL-RELATIV (0 = Schnipselanfang) in Millisekunden:
      [{"word", "start_ms", "end_ms", "fa_score"}]  in Textreihenfolge.
    start_ms/end_ms = None, falls ein Wort nicht ausgerichtet werden konnte.
    Fuer UI-Highlighting (Karaoke/Untertitel) auf der nativen Audio-Sprache."""
    words = re.findall(r"\w+", text, flags=re.UNICODE)
    if not words:
        return []
    word_times, _n = _fa_word_spans(wav_path, words)
    out = []
    for w, t in zip(words, word_times):
        if t is None:
            out.append({"word": w, "start_ms": None, "end_ms": None, "fa_score": 0.0})
        else:
            out.append({"word": w, "start_ms": round(t[0] * 1000),
                        "end_ms": round(t[1] * 1000), "fa_score": round(t[2], 2)})
    return out


def fa_cut(block_wav, sentences, valley_ratio=0.45, fa_pre=0.02, cut_guard=0.10):
    """FORCED ALIGNMENT (torchaudio MMS_FA). sentences = [{"id","text"}, ...].
    Analysiert die N-1 Satzgrenzen im Block und gibt je Grenze einen
    Schnittpunkt + Status (OK/FLAG) zurueck. SCHREIBT NICHTS.

    Rueckgabe:
      {"net": {"expected","got","ok"},
       "boundaries": [{"boundary","after_id","status","reason","cut_s",
                       "valley_depth","fa_score","gap_ms","word_end_s",
                       "next_start_s","last_word","syl"}],
       "cuts": [cut_s je OK-Grenze, in Satzreihenfolge]}
    FLAG-Gruende: 'keine FA-Spanne' (Wort nicht ausgerichtet),
                  'verschliffen' (Tal nicht tief genug)."""
    # flache Wortliste + Wortindex-Bereich je Satz (fuer Grenzen-Zuordnung)
    words_flat, sent_range = [], []
    wi = 0
    for s in sentences:
        toks_words = re.findall(r"\w+", s["text"], flags=re.UNICODE)
        first = wi
        words_flat += toks_words
        wi += len(toks_words)
        sent_range.append((first, wi - 1))

    word_times, n_tokens = _fa_word_spans(block_wav, words_flat)
    if not n_tokens:
        return {"net": {"expected": 0, "got": 0, "ok": False}, "boundaries": [], "cuts": []}

    def w_end(i):
        return word_times[i][1] if word_times[i] else None
    def w_start(i):
        return word_times[i][0] if word_times[i] else None
    def w_score(i):
        return word_times[i][2] if word_times[i] else 0.0
    def last_nonempty(lo, hi):
        for i in range(hi, lo - 1, -1):
            if word_times[i]:
                return i
        return None
    def first_nonempty(lo, hi):
        for i in range(lo, hi + 1):
            if word_times[i]:
                return i
        return None

    times, rms, flat_sp, floor, speech = _frame_features(block_wav)

    results, cuts = [], []
    nb = len(sentences)
    for bi in range(nb - 1):
        s0 = sentences[bi]
        lo_b, hi_b = sent_range[bi]
        lo_n, hi_n = sent_range[bi + 1]
        je = last_nonempty(lo_b, hi_b)
        js = first_nonempty(lo_n, hi_n)
        last_tok = re.findall(r"\w+", s0["text"], flags=re.UNICODE)[-1]
        syl = syllables(last_tok)
        if je is None or js is None:
            results.append({"boundary": bi + 1, "after_id": s0["id"], "status": "FLAG",
                            "reason": "keine FA-Spanne", "last_word": last_tok, "syl": syl})
            continue
        a, c = w_end(je), w_start(js)
        gap_ms = round(max(0.0, c - a) * 1000)
        _vcut, depth = _energy_valley(times, rms, speech, a, c, pre=fa_pre)
        # PAUSEN-GETRIEBENER SCHNITT: knapp VOR dem Folgewort schneiden. Bei grosser
        # Pause liegt so der GESAMTE Auslaut (auch leise/stimmlose Konsonanten) sicher
        # im Clip -- alles vor c bleibt erhalten, die Konsonanten-Art ist egal.
        # cut_guard = Sicherheitsabstand vor dem Folgewort (schuetzt dessen Anlaut).
        # Das Energie-Tal dient nur noch der Verschleifungs-Erkennung (depth), nicht
        # mehr dem Schnitt. Clamp: nie vor das Wortende (enge Pause).
        cut_s = max(a, c - cut_guard)
        sc = w_score(je)
        reason = []
        if depth > valley_ratio:
            reason.append("verschliffen")
        status = "OK" if not reason else "FLAG"
        if status == "OK":
            cuts.append(cut_s)
        results.append({"boundary": bi + 1, "after_id": s0["id"], "status": status,
                        "reason": ";".join(reason), "last_word": last_tok,
                        "fa_score": round(sc, 2), "syl": syl,
                        "word_end_s": round(a, 3), "next_start_s": round(c, 3),
                        "gap_ms": gap_ms, "valley_depth": round(depth, 3),
                        "cut_s": round(cut_s, 3)})
    return {"net": {"expected": len(words_flat), "got": len(words_flat), "ok": True},
            "boundaries": results, "cuts": cuts}


# ------------------------------------------------------------------ Segmente schreiben
def slice_block(block_wav, cut_points, out_paths):
    """Zerschneidet block_wav an cut_points (sortierte Sekunden) und schreibt
    JE Segment eine WAV nach out_paths[i] (Rand-Stille getrimmt). len(out_paths)
    muss len(cut_points)+1 sein. Gibt Liste (out_path, geschrieben?) zurueck."""
    import numpy as np
    pcm, sr = read_wav(block_wav)
    x = np.frombuffer(pcm, dtype="<i2")
    total = x.size / sr
    bounds = [0.0] + sorted(cut_points) + [total]
    assert len(out_paths) == len(bounds) - 1, "out_paths muss cuts+1 sein"
    written = []
    for i in range(len(bounds) - 1):
        seg = _trim_silence(x[int(bounds[i]*sr):int(bounds[i+1]*sr)].tobytes(), sr)
        if seg:
            write_wav(out_paths[i], seg, sr)
            written.append((out_paths[i], True))
        else:
            written.append((out_paths[i], False))
    return written
