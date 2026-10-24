"""READ LAYER — Satzpruefung IM Vertonungslauf (17.10.2026, CK: Pruefungen gehoeren in den Standardprozess).
Richtet jedes erzeugte Stueck per Forced Alignment (torchaudio MMS_FA, wie Stage 58c) gegen seinen Text aus und
findet: Ton nach dem letzten Wort (Nachklang, Wortfetzen), Ton vor dem ersten Wort, verschmierte Woerter
(letztes Wort viel zu spaet), zu kurz (Satz abgebrochen) oder zu lang. tts_modal_opt.py erzeugt solche Stuecke
neu (bis 2x); bleibt nur ein Nachklang uebrig, wird hinter dem letzten Wort gekappt.
"""
import re
import unicodedata
import numpy as np
import torch

MS_JE_ZEICHEN = 0.051      # Chatterbox roh (Median, 17.10.)
SCHWELLE_DB, RAHMEN, MIN_S = -40.0, 0.02, 0.25


def lautwoerter(text):
    out = []
    for m in re.finditer(r"[^\W\d_]+(?:'[^\W\d_]+)*", text):
        w = unicodedata.normalize("NFKD", m.group().lower().replace("ß", "ss"))
        w = "".join(c for c in w if not unicodedata.combining(c)).strip("'")
        if w:
            out.append(w)
    return out


class Pruefer:
    def __init__(self, device="cuda"):
        import torchaudio
        from torchaudio.pipelines import MMS_FA as bundle
        self.ta = torchaudio
        self.dev = device
        self.model = bundle.get_model().to(device)
        self.tokenizer = bundle.get_tokenizer()
        self.aligner = bundle.get_aligner()
        self.sr = bundle.sample_rate
        try:
            self.zeichen = set(bundle.get_dict().keys())
        except Exception:
            self.zeichen = set("abcdefghijklmnopqrstuvwxyz'")

    def _ton(self, x, sr, von, bis):
        n = int(sr * RAHMEN)
        a = x[max(0, int(von * sr)):max(0, int(bis * sr))]
        k = len(a) // n
        if k <= 0:
            return 0.0
        r = np.sqrt((a[:k * n].reshape(k, n) ** 2).mean(1)) + 1e-9
        return float((20 * np.log10(r) > SCHWELLE_DB).sum() * RAHMEN)

    @torch.inference_mode()
    def pruefe(self, text, wav, sr):
        """wav: Tensor (1, n). Rueckgabe dict: grund (None = ok), letzt (s, Ende letztes Wort), dauer."""
        x = wav.reshape(-1).float().cpu().numpy()
        dauer = len(x) / sr
        erw = max(0.3, len(text) * MS_JE_ZEICHEN)
        erg = {"grund": None, "letzt": None, "dauer": round(dauer, 2)}
        if dauer < 0.35 * erw and erw > 1.5:
            erg["grund"] = "zu_kurz"
            return erg
        if dauer > 2.0 * erw + 1.2:
            erg["grund"] = "zu_lang"
        woerter = [w for w in lautwoerter(text) if all(c in self.zeichen for c in w)]
        if not woerter:
            return erg
        w16 = self.ta.functional.resample(wav.reshape(1, -1).float(), sr, self.sr).to(self.dev)
        try:
            em, _ = self.model(w16)
            spans = self.aligner(em[0], self.tokenizer(woerter))
            if isinstance(spans, tuple):
                spans = spans[0]
        except Exception:
            erg["grund"] = erg["grund"] or "nicht_ausrichtbar"
            return erg
        f = w16.shape[1] / em.shape[1] / self.sr
        erst, letzt = spans[0][0].start * f, spans[-1][-1].end * f
        erg["letzt"] = round(letzt, 3)
        if erg["grund"]:
            return erg
        if letzt > erw * 1.6 + 0.6:
            erg["grund"] = "verschmiert"
        elif self._ton(x, sr, 0, erst - 0.08) >= MIN_S:
            erg["grund"] = "vorlauf"
        elif self._ton(x, sr, letzt + 0.15, dauer) >= MIN_S:
            erg["grund"] = "nachklang"
        return erg


def kappen(wav, sr, ende_s):
    n = min(wav.shape[-1], int(ende_s * sr))
    w = wav[..., :n].clone()
    f = min(n, int(0.03 * sr))
    w[..., n - f:] *= torch.linspace(1, 0, f)
    return w
