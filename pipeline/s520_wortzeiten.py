"""STAGE 520 — Wortzeiten
Funktion:     Wort-Zeitstempel fuer Karaoke-Highlighting.
Wirkungsweise: Forced Alignment (torchaudio MMS_FA) je Satz-WAV, Bindung an die Wortanker aus s340.
Komponenten:  pipeline/s520_wortzeiten.py; auf Modal: gpu_fa/fa_modal.py, gpu_tts/fertig_modal.py
Zulieferer:   s500 Vertonung (WAVs), s340 Wort-Alignment (work/340_wortalignment.json)
Abnehmer:     s710 Cloud-Export, TAELLA-App (work/520_wortzeiten_<lang>.json)
(Nomenklatur seit 18.10.2026, Uebersicht: docs/Pipeline_Strang_Matrix.xlsx)

--- Bisherige Beschreibung ---

READ LAYER — Stage 58c: Wort-Zeitstempel (Karaoke-Grundlage)
=============================================================
Input:  fassungen/<lang>/audio/<tag_id>.wav   (Satz-Schnipsel aus 58b)
        work/340_wortalignment.json                    (Wortanker: i + en_span)
Output: work/520_wortzeiten_<lang>.json
        { tag_id: [ {"i": <54a-Index>, "t0": <s>, "t1": <s>}, ... ] }

ZWECK: Beim Abspielen soll das gerade gesprochene Wort im Lesetext leuchten.
Dafuer braucht jedes EN-Wort Start/Ende IM SCHNIPSEL.

WARUM FORCED ALIGNMENT UND NICHT STT:
Der Satztext ist bereits exakt bekannt -- es muss nichts ERKANNT, sondern nur
zeitlich ZUGEORDNET werden. Forced Alignment (torchaudio MMS_FA) bekommt den
Text vorgegeben und kann sich daher nicht verhoeren; es verteilt genau diesen
Text auf das Audio. STT dagegen raet den Wortlaut, und gerade bei kurzen
Schnipseln neigt es zum Erfinden. Der STT-Vorlauf in 58b bleibt davon
unberuehrt: dort liefert er den ungefaehren Korridor fuer den SATZSCHNITT --
seine passende Aufgabe.

WARUM AUF SCHNIPSEL-EBENE:
Die Zeiten entstehen direkt clip-relativ. Damit entfaellt die gesamte
Umrechnung kapitelrelativer Zeiten (Clip-Startpunkte aufaddieren, Drift
korrigieren, fehlende Schnipsel abfangen) -- und mit ihr deren Fehlerquellen.
Ein Schnipsel ist ausserdem kurz genug, dass Forced Alignment nicht driftet.

DIE TOKENISIERUNGS-BRUECKE (unveraendert wichtig):
Stage 54a zerlegt mit `\\S+`  -> "house-dog" = 1 Token, "grass," = 1 Token
Diese Stage braucht reine Lautwoerter -> "house", "dog" getrennt, ohne Komma
Die Indizes laufen also auseinander und duerfen NICHT direkt verrechnet
werden. Gemeinsame Wahrheit ist die ZEICHENPOSITION im Satztext: jedes
Lautwort kennt seinen Offset, jeder 54a-Anker seinen `en_span`. Ein
Zeitstempel wird dem Anker zugeschlagen, in dessen Span sein Offset faellt;
mehrere Lautwoerter im selben Span (z.B. "house"+"dog") werden zu EINEM
Zeitfenster zusammengefasst (min start, max end).

ROHE QUELLSEKUNDEN, KEINE TEMPO-VERRECHNUNG:
Die Werte gelten fuer Abspielgeschwindigkeit 1.0 und werden bewusst NICHT
umgerechnet. Ein Geschwindigkeitsregler aendert `playbackRate`, nicht
`currentTime` -- der Vergleich Zeitstempel<->currentTime stimmt damit bei
jedem Tempo von selbst. (Was der Player hingegen skalieren MUSS, sind die
dramaturgischen `pause_after_ms`: die stecken nicht im Audio.)

RESILIENZ: Das Ergebnis wird alle CHECKPOINT_ALLE Schnipsel zwischengespeichert.
Ein erneuter Lauf ueberspringt bereits vermessene Tags (--force vermisst neu).

UMGEBUNG: braucht torchaudio -> Python 3.11 verwenden:
  py -3.11 -m pipeline.s520_wortzeiten call-of-the-wild --lang en
  py -3.11 -m pipeline.s520_wortzeiten call-of-the-wild --lang en --limit 50
  py -3.11 -m pipeline.s520_wortzeiten call-of-the-wild --lang de

ZIELSPRACHE (ab 2026-10-09): Fuer --lang de (bzw. jede Sprache != Quellsprache)
werden die Schnipsel aus fassungen/<lang>/audio mit dem Zieltext aus 54a
(content[tid][<lang>]) ausgerichtet. Umlaute/Akzente werden fuer das Modell
romanisiert (ae->a, ss fuer sz, Akzente weg) -- die Zeichen-Offsets bleiben im
Originaltext. Gebunden wird dort an die \\S+-Tokens des Zieltexts:
"i" = Tokenindex im Zieltext (fuer die Quellsprache weiter der 54a-Anker-Index,
der ebenfalls auf \\S+ beruht). Die App liest beides gleich: i -> \\S+-Token.
"""

import os
import re
import sys
import json
import unicodedata

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config

STAGE = "520"
CHECKPOINT_ALLE = 200


# ---------------------------------------------------------------------------
# Text -> Lautwoerter mit Zeichen-Offset
# ---------------------------------------------------------------------------
def _lautwoerter(text):
    """Zerlegt den Satztext in Woerter, wie das Aussprachemodell sie erwartet:
    nur Buchstaben und Apostroph, kleingeschrieben, ohne Interpunktion.
    Behaelt den Zeichen-Offset im ORIGINALTEXT -- das ist die Bruecke zu 54a.
    Rueckgabe: [ {"c0":..., "c1":..., "w": "house"} ]"""
    out = []
    for m in re.finditer(r"[^\W\d_]+(?:'[^\W\d_]+)*", text):
        w = _romanisieren(m.group().lower()).strip("'")
        if w:
            out.append({"c0": m.start(), "c1": m.end(), "w": w})
    return out


def _romanisieren(w):
    """Umlaute/Akzente auf den a-z-Zeichenvorrat von MMS_FA abbilden:
    ae/oe/ue -> a/o/u, sz -> ss, Akzente entfernen (ca -> ca)."""
    w = w.replace("\u00df", "ss")
    w = unicodedata.normalize("NFKD", w)
    return "".join(c for c in w if not unicodedata.combining(c))


def _bind_to_tokens(zeiten, text):
    """Zielsprache: Lautwort-Zeiten den \\S+-Tokens des Satztexts zuordnen
    (gleiche Logik wie _bind_to_anchors, nur mit eigenen Spans)."""
    tokens = [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]
    key = config.align_keys()[0]   # Quell-Span-Schluessel je Werk (22.10.2026)
    align = [{"i": i, key: [a, b]} for i, (a, b) in enumerate(tokens)]
    return _bind_to_anchors(zeiten, align)


def _bind_to_anchors(zeiten, align):
    """Ordnet Lautwort-Zeiten den 54a-Ankern zu -- ueber die Zeichenposition,
    nicht ueber den Wortindex (siehe Kopfkommentar). zeiten = [{c0,c1,t0,t1}]."""
    treffer = {}
    key = config.align_keys()[0]   # en_span (EN-Werk) bzw. de_span (DE-Werk)
    for z in zeiten:
        mitte = (z["c0"] + z["c1"]) / 2.0
        for a in align:
            sp = a.get(key)
            if not (isinstance(sp, list) and len(sp) == 2):
                continue
            if sp[0] <= mitte <= sp[1]:
                i = a.get("i")
                if i in treffer:
                    treffer[i][0] = min(treffer[i][0], z["t0"])
                    treffer[i][1] = max(treffer[i][1], z["t1"])
                else:
                    treffer[i] = [z["t0"], z["t1"]]
                break
    return [{"i": i, "t0": round(v[0], 3), "t1": round(v[1], 3)}
            for i, v in sorted(treffer.items())]


# ---------------------------------------------------------------------------
# Forced Alignment (torchaudio MMS_FA)
# ---------------------------------------------------------------------------
class _Aligner:
    """Laedt das Modell EINMAL und richtet dann Schnipsel fuer Schnipsel aus."""

    def __init__(self):
        import torch
        import torchaudio
        from torchaudio.pipelines import MMS_FA as bundle

        self.torch = torch
        self.torchaudio = torchaudio
        # 15.10.2026: READLAYER_FA_DEVICE=cuda (Modal-GPU), sonst CPU wie bisher
        self.dev = os.environ.get("READLAYER_FA_DEVICE", "cpu")
        print(f"[{STAGE}] lade MMS_FA ({self.dev}) ...")
        self.model = bundle.get_model().to(self.dev)
        self.tokenizer = bundle.get_tokenizer()
        self.aligner = bundle.get_aligner()
        self.sr = bundle.sample_rate
        # Zeichenvorrat des Modells -- alles andere kann nicht ausgerichtet werden
        try:
            self.zeichen = set(bundle.get_dict().keys())
        except Exception:
            self.zeichen = set("abcdefghijklmnopqrstuvwxyz'")
        print(f"[{STAGE}] bereit (Zielrate {self.sr} Hz)")

    def _laden(self, pfad):
        """Liest den Schnipsel direkt mit dem wave-Modul.
        NICHT torchaudio.load verwenden: neuere torchaudio-Versionen leiten das
        auf TorchCodec um und scheitern ohne dieses Zusatzpaket. Die Schnipsel
        aus 58b sind schlichte 16-Bit-PCM-WAVs -- dafuer genuegt die
        Standardbibliothek. Das Resampling unten ist reine Tensor-Rechnung und
        von der Umleitung nicht betroffen."""
        import wave
        with wave.open(str(pfad), "rb") as w:
            sr = w.getframerate()
            nch = w.getnchannels()
            sw = w.getsampwidth()
            roh = w.readframes(w.getnframes())
        if sw != 2:
            raise ValueError(f"erwarte 16-Bit-PCM, gefunden {sw * 8} Bit")
        x = np.frombuffer(roh, dtype="<i2").astype("float32") / 32768.0
        if nch > 1:
            x = x.reshape(-1, nch).mean(axis=1)
        wav = self.torch.from_numpy(x).unsqueeze(0)
        if sr != self.sr:
            wav = self.torchaudio.functional.resample(wav, sr, self.sr)
        return wav

    def ausrichten(self, pfad, woerter):
        """woerter = Liste von Lautwoertern (str). Gibt [(t0,t1)] je Wort zurueck,
        None fuer Woerter, die das Modell nicht darstellen kann."""
        brauchbar = [i for i, w in enumerate(woerter)
                     if w and all(c in self.zeichen for c in w)]
        if not brauchbar:
            return [None] * len(woerter)

        text = [woerter[i] for i in brauchbar]
        wav = self._laden(pfad).to(self.dev)
        with self.torch.inference_mode():
            emission, _ = self.model(wav)
            # MMS_FA-Aligner liefert direkt die Liste der Wort-Spans (kein Tupel)
            spans = self.aligner(emission[0], self.tokenizer(text))
            if isinstance(spans, tuple):
                spans = spans[0]

        # Zeitachse: Emissionsraster -> Sekunden
        faktor = wav.shape[1] / emission.shape[1]
        ergebnis = [None] * len(woerter)
        for pos, sp in zip(brauchbar, spans):
            t0 = faktor * sp[0].start / self.sr
            t1 = faktor * sp[-1].end / self.sr
            if t1 > t0:
                ergebnis[pos] = (t0, t1)
        return ergebnis


# ---------------------------------------------------------------------------
# Hauptlauf
# ---------------------------------------------------------------------------
def _speichern(out_path, lang, ergebnis):
    json.dump({"sprache": lang,
               "einheit": "sekunden_clip_relativ_bei_tempo_1.0",
               "tags": ergebnis},
              open(out_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)


def run(book_id, lang=None, limit=None, force=False):
    lang = lang or config.SOURCE_LANGUAGE
    audio_dir = os.path.join(config.book_dir(book_id), "fassungen", lang, "audio")
    if not os.path.isdir(audio_dir):
        raise FileNotFoundError(
            f"Keine Schnipsel: {audio_dir} (Stage 58b zuerst laufen lassen).")

    p54 = config.work_path(book_id, "340_wortalignment")
    if not os.path.exists(p54):
        raise FileNotFoundError(f"{p54} fehlt -- Stage 54a zuerst laufen lassen.")
    stage54a = json.load(open(p54, encoding="utf-8"))
    content = stage54a.get("content", {})

    out_path = config.work_path(book_id, f"{STAGE}_wortzeiten_{lang}")
    ergebnis = {}
    if os.path.exists(out_path) and not force:
        try:
            ergebnis = json.load(open(out_path, encoding="utf-8")).get("tags", {})
        except Exception:
            ergebnis = {}
        if ergebnis:
            print(f"[{STAGE}] Checkpoint: {len(ergebnis)} Tags bereits vermessen "
                  f"(--force vermisst neu)")

    quellsprache = (lang == config.SOURCE_LANGUAGE)
    aufgaben = []
    for tid, v in content.items():
        align = v.get("align")
        if tid in ergebnis or (quellsprache and not align):
            continue
        wav = os.path.join(audio_dir, f"{tid}.wav")
        if not os.path.exists(wav):
            continue
        text = v.get(lang, "") or ""
        if text.strip():
            aufgaben.append((tid, wav, text, align))

    if limit:
        aufgaben = aufgaben[:int(limit)]

    gesamt_anker = sum(len(v["align"]) for v in content.values() if v.get("align"))
    print(f"[{STAGE}] {book_id} [{lang}] | {len(aufgaben)} Schnipsel zu vermessen")
    if not aufgaben:
        print(f"[{STAGE}] nichts zu tun.")
        return ergebnis

    al = _Aligner()

    n_ok = n_leer = 0
    n_wort_gesamt = n_wort_zeit = 0
    fehler = []

    for k, (tid, wav, text, align) in enumerate(aufgaben, 1):
        laut = _lautwoerter(text)
        if not laut:
            n_leer += 1
            continue
        try:
            zeiten = al.ausrichten(wav, [x["w"] for x in laut])
        except Exception as e:
            fehler.append((tid, str(e)[:120]))
            continue

        treffer = []
        for x, z in zip(laut, zeiten):
            n_wort_gesamt += 1
            if z is None:
                continue
            n_wort_zeit += 1
            treffer.append({"c0": x["c0"], "c1": x["c1"], "t0": z[0], "t1": z[1]})

        eintraege = (_bind_to_anchors(treffer, align) if quellsprache
                     else _bind_to_tokens(treffer, text))
        if eintraege:
            ergebnis[tid] = eintraege
            n_ok += 1
        else:
            n_leer += 1

        if k % 25 == 0 or k == len(aufgaben):
            print(f"\r  {k}/{len(aufgaben)} Schnipsel | {n_ok} mit Zeiten"
                  f"{f' | {len(fehler)} Fehler' if fehler else ''}   ",
                  end="", flush=True)
        if k % CHECKPOINT_ALLE == 0:
            _speichern(out_path, lang, ergebnis)
    print()

    _speichern(out_path, lang, ergebnis)

    mit_zeit = sum(len(v) for v in ergebnis.values())
    print()
    print("=" * 68)
    print(f"[{STAGE}] Tags mit Wortzeiten: {len(ergebnis)}")
    print(f"[{STAGE}] Lautwoerter ausgerichtet: {n_wort_zeit}/{n_wort_gesamt} "
          f"({100.0*n_wort_zeit/max(1,n_wort_gesamt):.1f}%)")
    print(f"[{STAGE}] Wortanker im Werk: {gesamt_anker} | mit Zeitstempel: {mit_zeit} "
          f"({100.0*mit_zeit/max(1,gesamt_anker):.1f}%)")
    if n_leer:
        print(f"[{STAGE}] Schnipsel ohne verwertbares Ergebnis: {n_leer}")
    if fehler:
        print(f"[{STAGE}] Fehler bei {len(fehler)} Schnipseln, z.B.:")
        for tid, msg in fehler[:5]:
            print(f"    {tid}: {msg}")
    print(f"[{STAGE}] Geschrieben: {out_path}")
    return ergebnis


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    def _opt(name, d=None):
        return sys.argv[sys.argv.index(name) + 1] if name in sys.argv and \
            sys.argv.index(name) + 1 < len(sys.argv) else d
    run(args[0] if args else "call-of-the-wild",
        lang=_opt("--lang"), limit=_opt("--limit"),
        force=("--force" in sys.argv))
