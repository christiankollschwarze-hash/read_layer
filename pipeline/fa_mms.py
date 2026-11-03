"""MMS_FA-Aligner (torchaudio) – gemeinsam fuer 510 (Schnitt), 530 (Raender) und 520 (Wortzeiten), lokal und auf Modal
(gpu_fa/schnitt_modal.py, READLAYER_FA_DEVICE=cuda). Bewusst ohne Pipeline-Importe, damit das Modal-Image schlank bleibt.
(Phase 2, 03.11.2026: aus pipeline/s520_wortzeiten.py herausgeloest.)
"""
import os

import numpy as np


class Aligner:
    """Laedt das Modell EINMAL und richtet dann Schnipsel fuer Schnipsel aus."""

    def __init__(self):
        import torch
        import torchaudio
        from torchaudio.pipelines import MMS_FA as bundle

        self.torch = torch
        self.torchaudio = torchaudio
        # 15.10.2026: READLAYER_FA_DEVICE=cuda (Modal-GPU), sonst CPU wie bisher
        self.dev = os.environ.get("READLAYER_FA_DEVICE", "cpu")
        print(f"[FA] lade MMS_FA ({self.dev}) ...")
        self.model = bundle.get_model().to(self.dev)
        self.tokenizer = bundle.get_tokenizer()
        self.aligner = bundle.get_aligner()
        self.sr = bundle.sample_rate
        # Zeichenvorrat des Modells -- alles andere kann nicht ausgerichtet werden
        try:
            self.zeichen = set(bundle.get_dict().keys())
        except Exception:
            self.zeichen = set("abcdefghijklmnopqrstuvwxyz'")
        print(f"[FA] bereit (Zielrate {self.sr} Hz)")

    def _laden(self, pfad):
        """Liest den Schnipsel direkt mit dem wave-Modul.
        NICHT torchaudio.load verwenden: neuere torchaudio-Versionen leiten das
        auf TorchCodec um und scheitern ohne dieses Zusatzpaket. Die Schnipsel
        aus 500/510/530 sind schlichte 16-Bit-PCM-WAVs -- dafuer genuegt die
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


_Aligner = Aligner
