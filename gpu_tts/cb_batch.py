"""READ LAYER — Batch-Inferenz fuer Chatterbox Multilingual (17.10.2026).

Statt eines Satzes je Durchgang rechnet der T3-Teil (Text -> Sprach-Token) B Saetze gleichzeitig:
alle Saetze links aufgefuellt (padding) in EINEM Transformer-Batch (2B Zeilen wegen CFG), KV-Cache gemeinsam.
Die Integritaetspruefung des Originals (AlignmentStreamAnalyzer: Fehlstart, langer Nachklang, Wiederholung,
EOS-Unterdrueckung) ist je Zeile nachgebaut; die Aufmerksamkeit der drei Ausrichtungskoepfe wird EINMAL
per Hook abgegriffen (das Original haengt bei jedem Satz neue Hooks an -> wird mit der Zeit langsamer).
S3Gen (Token -> Audio) laeuft danach je Satz wie im Original, inkl. Wasserzeichen.

Ausbau 17.10.2026 (abends):
  - Regler je Zeile: ex (exaggeration, Ausdruck) und cfg (cfg_weight, kleiner = ruhiger/langsamer) als Listen.
  - s3batch=True: S3Gen-Flow (CFM, der teure Teil) fuer alle Saetze eines Batches in EINEM Durchgang
    (Flow kann Batches mit token_len-Maske); HiFiGAN + Wasserzeichen danach je Satz. Rauschen ist zufaellig,
    darum nicht bitgleich mit dem Original -> per Hoerprobe/Messung freigeben.

Nutzung:
    from cb_batch import BatchTTS
    bt = BatchTTS(model)                   # model = ChatterboxMultilingualTTS (Standardstimme oder prepare_conditionals)
    wavs = bt.generate(["Satz 1", "Satz 2"], language_id="de")   # Liste von Tensoren (1, n), sr = model.sr
"""
import numpy as np
import torch
import torch.nn.functional as F
from transformers.generation.logits_process import (
    RepetitionPenaltyLogitsProcessor, TopPLogitsWarper, MinPLogitsWarper)

ALIGNED_HEADS = [(12, 15), (13, 11), (9, 2)]   # wie chatterbox AlignmentStreamAnalyzer


def sprech_norm(text):
    """Eigene Bereinigung statt chatterbox.punc_norm (17.10.2026): punc_norm macht aus '...'/'…', ':', ';'
    ein Komma und aus '—' einen Bindestrich -> Pausen- und Spannungszeichen gehen verloren. Hier bleiben sie
    erhalten (nur vereinheitlicht). Grossschreibung hilft NICHT: der Multilingual-Tokenizer schreibt alles klein."""
    import re
    if not text:
        return "."
    text = " ".join(text.split())
    for alt, neu in (("…", "..."), ("–", "—"), (" - ", " — "), ("„", '"'), ("“", '"'), ("”", '"'),
                     ("‚", "'"), ("‘", "'"), ("’", "'"), ("»", '"'), ("«", '"'), (" ,", ",")):
        text = text.replace(alt, neu)
    text = re.sub(r"\.{4,}", "...", text)
    if text[0].islower():
        text = text[0].upper() + text[1:]
    if not text.rstrip('"\' ').endswith((".", "!", "?", "—", ",", "...")):
        text += "."
    return text


class _ZeilenAnalyse:
    """Nachbau AlignmentStreamAnalyzer.step fuer EINE Zeile, inkrementell (O(1) je Schritt)."""

    def __init__(self, S, eos):
        self.S, self.eos = S, eos
        self.T = 0
        self.curr_frame_pos = 0
        self.text_position = 0
        self.started = False
        self.complete = False
        self.completed_at = None
        self.first4_max = 0.0
        self.last2 = []             # letzte 2 Zeilen (fuer false_start)
        self.tail_sum = np.zeros(3)  # Summe A[completed_at:, -3:]
        self.rep_sum = 0.0           # Summe A[completed_at:, :-5].max(1)
        self.tokens = []

    def schritt(self, chunk, next_token):
        """chunk: (t, S) numpy (t = Zahl neuer Frames). Gibt (eos_unterdruecken, eos_erzwingen) zurueck."""
        S = self.S
        chunk = chunk.copy()
        chunk[:, self.curr_frame_pos + 1:] = 0
        cur = int(chunk[-1].argmax())
        if -4 < cur - self.text_position < 7:
            self.text_position = cur
        for row in chunk:
            self.T += 1
            self.first4_max = max(self.first4_max, float(row[:4].max()) if S else 0.0)
            self.last2 = (self.last2 + [row])[-2:]
            if self.complete:
                self.tail_sum += row[-3:] if S >= 3 else 0
                self.rep_sum += float(row[:-5].max()) if S > 5 else 0.0
        l2 = np.stack(self.last2)
        false_start = (not self.started) and (l2[-2:, -2:].max() > 0.1 or self.first4_max < 0.5)
        self.started = not false_start
        if not self.complete and self.text_position >= S - 3:
            self.complete = True
            self.completed_at = self.T     # Original: A[completed_at:] -> erst Zeilen ab dem naechsten Schritt
        long_tail = self.complete and self.tail_sum.max() >= 5
        alignment_repetition = self.complete and self.rep_sum > 5
        if next_token is not None:
            self.tokens = (self.tokens + [next_token])[-8:]
        token_repetition = len(self.tokens) >= 3 and len(set(self.tokens[-2:])) == 1
        unterdruecken = cur < S - 3 and S > 5
        erzwingen = bool(long_tail or alignment_repetition or token_repetition)
        self.curr_frame_pos += 1
        return unterdruecken, erzwingen


class BatchTTS:
    def __init__(self, model):
        self.m = model
        self.t3 = model.t3
        self.hp = self.t3.hp
        tf = self.t3.tfmr
        tf.config._attn_implementation = "eager"   # Gewichte der Ausrichtungskoepfe werden gebraucht (wie Original)
        self._attn = [None] * len(ALIGNED_HEADS)
        self._handles = []
        for k, (layer, head) in enumerate(ALIGNED_HEADS):
            def hook(module, inp, out, k=k, head=head):
                if isinstance(out, tuple) and len(out) > 1 and out[1] is not None:
                    self._attn[k] = out[1][:, head]          # (2B, q, kv) auf der GPU
            self._handles.append(tf.layers[layer].self_attn.register_forward_hook(hook))

    @torch.inference_mode()
    def _t3_batch(self, text_tokens_list, cfg_weight=0.5, temperature=0.8, repetition_penalty=2.0,
                  min_p=0.05, top_p=1.0, max_new_tokens=1000, conds=None, cfgs=None):
        t3, hp, dev = self.t3, self.hp, self.t3.device
        B = len(text_tokens_list)
        conds = conds or [self.m.conds.t3] * B
        cfgs = cfgs or [cfg_weight] * B
        bos = torch.tensor([[hp.start_speech_token]], dtype=torch.long, device=dev)
        bos_emb = t3.speech_emb(bos) + t3.speech_pos_emb.get_fixed_embedding(0)       # (1,1,D)
        seqs, len_cond, text_lens = [], None, []
        for b, tt in enumerate(text_tokens_list):         # tt: (n,) inkl. SOT/EOT
            tt2 = tt.unsqueeze(0).repeat(2, 1).to(dev)
            sos = hp.start_speech_token * torch.ones_like(tt2[:, :1])
            emb, len_cond = t3.prepare_input_embeds(t3_cond=conds[b], text_tokens=tt2, speech_tokens=sos,
                                                    cfg_weight=max(float(cfgs[b]), 1e-3))
            emb = torch.cat([emb, bos_emb.expand(2, 1, -1)], dim=1)                    # (2, L_i, D)
            seqs.append(emb)
            text_lens.append(tt.numel())
        L = max(s.size(1) for s in seqs)
        D = seqs[0].size(2)
        embeds = torch.zeros(2 * B, L, D, dtype=seqs[0].dtype, device=dev)
        mask = torch.zeros(2 * B, L, dtype=torch.long, device=dev)
        pads = []
        for b, s in enumerate(seqs):
            p = L - s.size(1)
            pads.append(p)
            embeds[2 * b:2 * b + 2, p:] = s
            mask[2 * b:2 * b + 2, p:] = 1
        pos = (mask.cumsum(-1) - 1).clamp(min=0)
        # Textbereich je Zeile (Original: text_tokens_slice = (len_cond, len_cond + len_text))
        i0 = torch.tensor([pads[b] + len_cond for b in range(B)], device=dev)
        Smax = max(text_lens)
        S = torch.tensor(text_lens, device=dev)
        spalten = i0[:, None] + torch.arange(Smax, device=dev)[None]                    # (B, Smax)
        gueltig = torch.arange(Smax, device=dev)[None] < S[:, None]
        spalten = torch.where(gueltig, spalten, torch.zeros_like(spalten))

        analyse = [_ZeilenAnalyse(text_lens[b], hp.stop_speech_token) for b in range(B)]
        rep = RepetitionPenaltyLogitsProcessor(penalty=float(repetition_penalty))
        minp, topp = MinPLogitsWarper(min_p=min_p), TopPLogitsWarper(top_p=top_p)
        cfg = torch.tensor([float(c) for c in cfgs], device=dev)[:, None]                # (B,1) je Zeile

        out = t3.tfmr(inputs_embeds=embeds, attention_mask=mask, position_ids=pos, use_cache=True, return_dict=True)
        past = out.past_key_values
        last_h = out.last_hidden_state[:, -1:]                                          # (2B,1,D)
        generated = torch.full((B, 1), hp.start_speech_token, dtype=torch.long, device=dev)
        fertig = torch.zeros(B, dtype=torch.bool, device=dev)
        ergebnis = [[] for _ in range(B)]
        erster = True
        for i in range(max_new_tokens):
            logits2 = t3.speech_head(last_h)[:, -1, :]                                  # (2B,V)
            c, u = logits2[0::2], logits2[1::2]
            logits = c + cfg * (c - u)                                                  # (B,V)
            # Ausrichtung: Aufmerksamkeit der Bedingungs-Zeilen auf den jeweiligen Textbereich
            att = torch.stack(self._attn).mean(0)[0::2]                                 # (B, q, kv)
            if erster:
                # Original: aligned_attn[j:, i:j] -> Abfragen ab Textende (SOS + BOS)
                q_idx = torch.arange(L - 2, L, device=dev)
                att = att[:, q_idx]                                                     # (B,2,kv)
            chunk = torch.gather(att, 2, spalten[:, None, :].expand(-1, att.size(1), -1))
            chunk = (chunk * gueltig[:, None, :]).float().cpu().numpy()                 # (B,t,Smax)
            letzte = generated[:, -1].tolist()
            unter = torch.zeros(B, dtype=torch.bool)
            zwing = torch.zeros(B, dtype=torch.bool)
            fertig_cpu = fertig.tolist()
            for b in range(B):
                if fertig_cpu[b]:
                    continue
                u_, z_ = analyse[b].schritt(chunk[b, :, :text_lens[b]], letzte[b])
                unter[b], zwing[b] = u_, z_
            unter, zwing = unter.to(dev), zwing.to(dev)
            eos = hp.stop_speech_token
            logits[unter, eos] = -2 ** 15
            if zwing.any():
                logits[zwing] = -2 ** 15
                logits[zwing, eos] = 2 ** 15
            logits = rep(generated, logits)
            if temperature != 1.0:
                logits = logits / temperature
            logits = minp(generated, logits)
            logits = topp(generated, logits)
            nxt = torch.multinomial(torch.softmax(logits, dim=-1), 1)                   # (B,1)
            nxt = torch.where(fertig[:, None], torch.full_like(nxt, eos), nxt)
            generated = torch.cat([generated, nxt], 1)
            ist_eos = (nxt[:, 0] == eos)
            fertig = fertig | ist_eos
            if bool(fertig.all()):
                break
            emb = t3.speech_emb(nxt) + t3.speech_pos_emb.get_fixed_embedding(i + 1)     # (B,1,D)
            emb = emb.repeat_interleave(2, dim=0)                                       # (2B,1,D)
            mask = torch.cat([mask, torch.ones(2 * B, 1, dtype=mask.dtype, device=dev)], 1)
            pos = pos[:, -1:] + 1
            out = t3.tfmr(inputs_embeds=emb, attention_mask=mask, position_ids=pos, past_key_values=past,
                          use_cache=True, return_dict=True)
            past = out.past_key_values
            last_h = out.last_hidden_state
            erster = False
        toks = generated[:, 1:]                                                         # ohne BOS
        res = []
        for b in range(B):
            t = toks[b]
            e = (t == hp.stop_speech_token).nonzero()
            if len(e):
                t = t[:e[0, 0]]
            res.append(t)
        return res

    def _cond_ex(self, ex, basis=None):
        """T3-Bedingung mit eigenem Ausdruckswert (gecacht); basis = T3Cond einer Stimmungs-Referenz."""
        import dataclasses
        ex = round(float(ex), 2)
        c = basis if basis is not None else self.m.conds.t3
        cache = self.__dict__.setdefault("_conds_ex", {})
        k = (id(c), ex)
        if k not in cache:
            cache[k] = dataclasses.replace(c, emotion_adv=torch.full_like(c.emotion_adv, ex))
        return cache[k]

    @torch.inference_mode()
    def _s3_batch(self, speech, ref_dict=None):
        """S3Gen-Flow fuer alle Saetze zusammen, HiFiGAN je Satz (Ausgabe wie m.s3gen.inference)."""
        m, s3 = self.m, self.m.s3gen
        lens = [int(st.numel()) for st in speech]
        T = max(lens)
        tok = torch.zeros(len(speech), T, dtype=torch.long, device=m.device)
        for b, st in enumerate(speech):
            tok[b, :lens[b]] = st
        mels = s3.flow_inference(tok, speech_token_lens=torch.tensor(lens, device=m.device),
                                 ref_dict=ref_dict or m.conds.gen, finalize=True)
        wavs = []
        for b in range(len(speech)):
            mel = mels[b:b + 1, :, :lens[b] * s3.flow.token_mel_ratio].to(dtype=s3.dtype)
            wav, _ = s3.hift_inference(mel, None)
            wav[:, :len(s3.trim_fade)] *= s3.trim_fade
            wavs.append(wav)
        return wavs

    @torch.inference_mode()
    def generate(self, texte, language_id, exaggeration=0.5, ex=None, cfg=None, s3batch=False, refs=None, **kw):
        """refs: je Zeile ein Conditionals-Objekt (Stimmungs-Referenz, 17.10.2026) oder None = m.conds."""
        from chatterbox.mtl_tts import punc_norm
        m = self.m
        assert m.conds is not None, "Standardstimme fehlt (prepare_conditionals)"
        tok = []
        norm = sprech_norm if getattr(self, "zeichen_erhalten", False) else punc_norm
        for t in texte:
            tt = m.tokenizer.text_to_tokens(norm(t), language_id=language_id.lower())[0]
            tt = F.pad(tt, (1, 0), value=self.hp.start_text_token)
            tt = F.pad(tt, (0, 1), value=self.hp.stop_text_token)
            tok.append(tt)
        import time
        t0 = time.time()
        refs = refs or [None] * len(texte)
        ex = ex or [float(m.conds.t3.emotion_adv.reshape(-1)[0])] * len(texte)
        conds = [self._cond_ex(e, r.t3 if r is not None else None) for e, r in zip(ex, refs)]
        speech = self._t3_batch(tok, conds=conds, cfgs=cfg, **kw)
        torch.cuda.synchronize() if torch.cuda.is_available() else None
        t1 = time.time()
        wavs = [None] * len(speech)
        speech = [st[st < 6561].to(m.device) for st in speech]
        voll = [b for b, st in enumerate(speech) if st.numel() > 0]
        for b in range(len(speech)):
            if speech[b].numel() == 0:
                wavs[b] = torch.zeros(1, int(m.sr * 0.2))
        gen = lambda b: refs[b].gen if refs[b] is not None else m.conds.gen
        roh = {}
        if s3batch:
            gruppen = {}
            for b in voll:
                gruppen.setdefault(id(gen(b)), []).append(b)
            for g in gruppen.values():
                if len(g) > 1:
                    roh.update(zip(g, self._s3_batch([speech[b] for b in g], gen(g[0]))))
                else:
                    roh[g[0]] = m.s3gen.inference(speech_tokens=speech[g[0]], ref_dict=gen(g[0]))[0]
        else:
            roh = {b: m.s3gen.inference(speech_tokens=speech[b], ref_dict=gen(b))[0] for b in voll}
        for b, wav in roh.items():
            wav = wav.squeeze(0).detach().cpu().numpy()
            wav = m.watermarker.apply_watermark(wav, sample_rate=m.sr)
            wavs[b] = torch.from_numpy(wav).unsqueeze(0)
        self.zeit_t3 = getattr(self, "zeit_t3", 0.0) + (t1 - t0)
        self.zeit_s3 = getattr(self, "zeit_s3", 0.0) + (time.time() - t1)
        return wavs
