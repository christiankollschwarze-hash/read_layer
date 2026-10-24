"""Einzelne Figurenstimme eines Werks neu designen (mit Abgrenzung zum Ensemble).
Aufruf: py -3.11 tools/stimme_neu_designen.py <book_id> "<Figur EN>" [--notiz "bitte tiefere Stimme"]
                                             [--beschreibung "<englische Stimmbeschreibung>"] [--tonlage tief]
--notiz: CKs Anmerkung zur abgelehnten Probe (deutsch oder englisch) -> geht mit Vorrang in den Design-Prompt.
Alte Stimme -> Status abgelehnt (mit Notiz); casting.json-Plan wird auf die neue Stimme umgestellt.
Danach: tools/stimmen_probe.py <book_id> -> neue Probe anhoeren -> s410_casting --freigeben.
"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from config import config  # noqa
from pipeline import voice_registry as vr, s410_casting as s57  # noqa

def _opt(name):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else None
book, figur_name = sys.argv[1], sys.argv[2]
notiz, beschreibung, tonlage = _opt("--notiz"), _opt("--beschreibung"), _opt("--tonlage")
cp = s57.casting_pfad(book)
c = json.load(open(cp, encoding="utf-8"))
data, _ = s57._quelle_laden(book)
eintrag = next(e for e in c["plan"]["ensemble"] if e["figur"] == figur_name)
figur = dict(eintrag["steckbrief"])
if beschreibung:
    figur["stimm_beschreibung_en"] = beschreibung
if notiz:
    figur["ck_notiz"] = notiz
if tonlage:
    figur["merkmale"] = dict(figur["merkmale"], tonlage=tonlage)
reg = vr.laden()
ensemble = []
for e in [c["plan"]["erzaehler"]] + c["plan"]["ensemble"]:
    if e.get("stimme") and e["figur"] != figur_name and e["stimme"] in reg:
        s = reg[e["stimme"]]
        ensemble.append({"figur": e["figur"], "name": e["stimme"], "merkmale": s.get("merkmale"),
                         "grundton_hz": s.get("grundton_hz"),
                         "beschreibung": (e.get("steckbrief") or {}).get("stimm_beschreibung_en") or s.get("beschreibung", "")})
alt = eintrag.get("stimme")
name = s57._stimmen_name(figur, reg)
print(f"design {name} fuer {figur_name} (alt: {alt}) ...")
neu = vr.neu_designen(name, figur, ensemble, s57._muster(data, figur), book)
ok, grund, _ = vr.unterscheidbar(dict(neu, name=name), ensemble)
print(f"  Grundton {neu.get('grundton_hz')} Hz | unterscheidbar: {ok} {grund}")
reg = vr.laden()
if alt in reg:
    reg[alt]["status"] = "abgelehnt"
    reg[alt]["einsatz"] = f"ersetzt durch {name}" + (f" | CK: {notiz}" if notiz else "")
    vr.speichern(reg)
eintrag.update({"stimme": name, "id": neu["id"], "quelle": "neu", "grundton_hz": neu.get("grundton_hz"),
                "design_prompt": neu.get("beschreibung")})
eintrag.pop("pruefen", None)
if not ok:
    eintrag["pruefen"] = grund
json.dump(c, open(cp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("  casting.json aktualisiert")
print(f"  Weiter: py -3.11 tools/stimmen_probe.py {book}   (neue Probe anhoeren)")
