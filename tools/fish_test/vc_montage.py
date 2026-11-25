"""Nach start_alice_fish_vc.bat: Figuren-Beitraege durch VC-Ergebnis ersetzen und Kapitel zusammensetzen."""
import sys, os, json, zipfile, wave, pathlib, io
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).parent)); os.environ["ERZ_ALLE"] = "1"
import fish_einzeln as E, fish_test as F
lg = "de"; ROOT = F.ROOT
z = zipfile.ZipFile(ROOT / "gpu_overlay/alice_c007_fish_de/ergebnis.zip")
vc = {pathlib.Path(n).stem: z.read(n) for n in z.namelist() if n.startswith("vc/") and n.endswith(".wav")}
def lade(b):
    with wave.open(io.BytesIO(b)) as w:
        sr = w.getframerate(); a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32)
    if sr != 24000: a = np.interp(np.arange(0, len(a), sr / 24000), np.arange(len(a)), a)
    return a.astype(np.int16).tobytes()
tr = E.turns_mit_absatz(lg); d = F.OUT / f"{lg}_erz_regie"; fehlt = 0
with wave.open(str(F.OUT / lg / f"fish_erz_vc_{F.KAP}_{lg}.wav"), "wb") as out:
    out.setnchannels(1); out.setsampwidth(2); out.setframerate(24000)
    for n, x in enumerate(tr, 1):
        if n > 1: out.writeframes(b"\x00\x00" * int(24000 * (E.PAUSE_ABSATZ if x["absatz"] else E.PAUSE_TURN)))
        jid = f"t{n:04d}"
        if x["fig"] != "Erzaehler" and jid in vc: out.writeframes(lade(vc[jid]))
        else:
            fehlt += x["fig"] != "Erzaehler"
            out.writeframes(lade((d / f"{jid}.wav").read_bytes()))
print("fertig, ohne VC:", fehlt)
