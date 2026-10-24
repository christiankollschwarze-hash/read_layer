"""READ LAYER - LoRA-Kern fuer Chatterbox T3 (17.10.2026, AP claude/AP_lora_librivox.md).
Eigene kleine LoRA-Umsetzung (ohne peft: chatterbox-tts pinnt transformers 5.x).
  einbauen(t3, rang, alpha)  -> LoRA-Schichten in die Llama-Projektionen von t3.tfmr, nur diese sind trainierbar
  speichern(t3, pfad, meta)  -> nur die LoRA-Gewichte (.safetensors, wenige MB)
  einmischen(t3, pfad)       -> fuer die Vertonung: W += B@A*skala direkt ins Grundmodell (kein Laufzeit-Aufwand)
Einsatz in der Vertonung (spaeter tts_modal_opt.py --lora <name>): nach from_pretrained einmischen(model.t3, pfad).
"""
import json
import math
import torch
import torch.nn as nn

ZIELE = ("q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj")


class LoRALinear(nn.Module):
    def __init__(self, basis: nn.Linear, rang: int, alpha: float, dropout: float = 0.05):
        super().__init__()
        self.basis = basis
        self.skala = alpha / rang
        self.A = nn.Parameter(torch.empty(rang, basis.in_features, device=basis.weight.device))
        self.B = nn.Parameter(torch.zeros(basis.out_features, rang, device=basis.weight.device))
        nn.init.kaiming_uniform_(self.A, a=math.sqrt(5))
        self.drop = nn.Dropout(dropout)

    def forward(self, x):
        return self.basis(x) + (self.drop(x) @ self.A.t() @ self.B.t()) * self.skala


def einbauen(t3, rang=32, alpha=64, dropout=0.05):
    for p in t3.parameters():
        p.requires_grad_(False)
    n = 0
    for name, modul in list(t3.tfmr.named_modules()):
        for kind, sub in list(modul.named_children()):
            if kind in ZIELE and isinstance(sub, nn.Linear):
                setattr(modul, kind, LoRALinear(sub, rang, alpha, dropout))
                n += 1
    return n


def lora_parameter(t3):
    return [p for m in t3.tfmr.modules() if isinstance(m, LoRALinear) for p in (m.A, m.B)]


def speichern(t3, pfad, meta: dict):
    from safetensors.torch import save_file
    zust = {}
    for name, m in t3.tfmr.named_modules():
        if isinstance(m, LoRALinear):
            zust[f"{name}.A"] = m.A.detach().float().cpu().contiguous()
            zust[f"{name}.B"] = m.B.detach().float().cpu().contiguous()
    meta = {k: str(v) for k, v in meta.items()}
    save_file(zust, pfad, metadata=meta)


@torch.no_grad()
def einmischen(t3, pfad, staerke: float = 1.0):
    """LoRA-Gewichte ins Grundmodell rechnen. staerke < 1 schwaecht den Adapter ab (Hoerversuch)."""
    from safetensors import safe_open
    with safe_open(pfad, framework="pt") as f:
        meta = f.metadata() or {}
        skala = float(meta.get("alpha", 64)) / float(meta.get("rang", 32)) * staerke
        namen = sorted({k.rsplit(".", 1)[0] for k in f.keys()})
        module = dict(t3.tfmr.named_modules())
        for name in namen:
            lin = module[name]
            A = f.get_tensor(f"{name}.A").to(lin.weight.device, torch.float32)
            B = f.get_tensor(f"{name}.B").to(lin.weight.device, torch.float32)
            lin.weight.add_(((B @ A) * skala).to(lin.weight.dtype))
    t3.compiled = False          # Inferenz-Backend neu aufbauen
    return len(namen)
