"""Phase 2, Fundament 6: Kette nach Katalog-Reihenfolge (GATE_KATALOG.md, 01.11.2026).

  bedarf(b, roh)            Menge der Stages, die laut Bestellung (095) laufen; Rest entfaellt
  bedarf_setzen(werk)       -> status.bedarf_setzen (nur bei Aenderung, sonst kein Protokolleintrag)
  VORGAENGER[stage]         direkte Eingaenge laut Katalog (Gate muss frei sein)
  wirksame_vorgaenger(...)  Vorgaenger, die entfallen oder (noch) nicht in der Kette laufen,
                            werden durch ihre eigenen Vorgaenger ersetzt (transitiv)
  sprachen(stage, b)        Sprachliste je Stage (None = sprachunabhaengig)

Reihenfolge = status.STAGES. Keine Ausfuehrung hier (das macht run.py).
"""
from pipeline import bestellung, status

AUDIO = ("hoerbuch", "hoerspiel")

# Direkte Eingaenge laut Katalogzeilen bzw. Reihenfolge-Kopf. 700 = alle Stages davor (s. unten).
VORGAENGER = {
    "080": [],
    "090": ["080"],
    "095": ["090"],
    "100": ["095"],
    "110": ["100"],
    "150": ["095"],
    "115": ["110", "150"],
    "120": ["115"],
    "190": ["120"],
    "195": ["190"],
    "200": ["195"],
    "210": ["200"],
    "300": ["210"],
    "310": ["300"],
    "320": ["310"],
    "330": ["320"],
    "340": ["330"],
    "400": ["330"],
    "410": ["400"],
    "420": ["410"],
    "500": ["400", "410"],
    "510": ["500", "420"],
    "530": ["500", "510"],
    "520": ["530", "340"],
    "540": ["520"],
    "600": ["330"],          # bei Uebersetzung nach 330, sonst (330 entfaellt) transitiv nach 190
    "610": ["600"],
    "615": ["610", "410"],   # Audio-Variante zusaetzlich nach Freigabe 410
    "620": ["615", "650"],   # Audio-Variante nach 650
    "630": ["615", "330", "650"],
    "640": ["600", "410"],
    "650": ["530", "615"],
    "700": None,             # nach der letzten bestellten Stage: alle Stages davor
    "710": ["700"],
}


def vorgaenger(stage):
    s = status._norm(stage)
    v = VORGAENGER[s]
    if v is None:
        return status.STAGES[:status.STAGES.index(s)]
    return list(v)


def wirksame_vorgaenger(stage, laeuft, in_kette):
    """Vorgaenger, deren Gate geprueft wird. Entfaellt ein Vorgaenger (nicht in laeuft), zaehlt er als
    frei und faellt weg (wie status.ist_frei). Laeuft er, ist aber (noch) nicht in der Kette (nicht in
    in_kette: nicht gebaut/manuell), treten seine Vorgaenger an seine Stelle."""
    laeuft, in_kette = set(laeuft), set(in_kette)
    out, gesehen = [], set()
    stapel = list(reversed(vorgaenger(stage)))
    while stapel:
        v = stapel.pop()
        if v in gesehen or v not in laeuft:
            continue
        gesehen.add(v)
        if v in in_kette:
            out.append(v)
        else:
            stapel.extend(reversed(vorgaenger(v)))
    return sorted(set(out), key=status.STAGES.index)


# ------------------------------------------------------------------ Bedarf aus Bestellung
def eingangsart(roh):
    from pipeline import s090_eingang
    return s090_eingang.eingangsart(roh)[0]


def bedarf(b, roh=None):
    """Stages, die laut Bestellung laufen (Spalte 'Laeuft bei (aus 095)')."""
    roh = roh if roh is not None else b.roh
    P = b.produkte
    q = b.quellsprache
    ziel = [lg for lg in b.zielsprachen]
    audio = [p for p in P if p["inhalt"] in AUDIO]
    hoerspiel = [p for p in P if p["inhalt"] == "hoerspiel"]
    taella = [p for p in P if "taella" in p["kanaele"]]

    s = {"080", "090", "095", "115", "120", "190", "195", "600", "610", "615", "700", "710"}
    if eingangsart(roh) == "gutenberg":
        s |= {"100", "110"}
    else:
        s.add("150")
    # 200: alles ausser reinem Text-EPUB in Ausgangssprache
    if any(not (p["inhalt"] == "text" and set(p["kanaele"]) <= {"epub"} and p["sprache"] == q) for p in P):
        s.add("200")
    if ziel or audio:
        s.add("210")
    if ziel:
        s |= {"300", "310", "320", "330"}
    if any(p["sprache"] in ziel for p in taella):
        s.add("340")
    if audio:
        s |= {"400", "410", "500", "530"}
    if hoerspiel:
        s |= {"420", "510", "540"}
    if any(p["inhalt"] in AUDIO for p in taella):
        s.add("520")
    if taella:
        s.add("640")
    if any(p["inhalt"] == "hoerbuch" and p["stufe"] == "basic" and ({"extern", "epub"} & set(p["kanaele"]))
           for p in P):
        s.add("650")
    if any("epub" in p["kanaele"] and p["sprache"] == q for p in P):
        s.add("620")
    if any("epub" in p["kanaele"] and p["sprache"] in ziel for p in P):
        s.add("630")
    if roh.get("geteilt_in"):            # 195: Werk in Teile zerlegt -> weiter nur in den Teilen
        s = {x for x in s if x <= "195"}
    return s


def bedarf_setzen(werk, wer="095"):
    """Bestellung lesen, Bedarf in status.json schreiben (nur bei Aenderung).
    Rueckgabe (bestellung, laeuft, fehler). Bei Fehlern in der Bestellung wird nichts geschrieben."""
    b = bestellung.lesen(werk)
    f = b.fehler()
    if f:
        return b, set(), f
    soll = bedarf(b)
    d = status.laden(werk)
    ist_entf = {s for s in status.STAGES if (d["stages"].get(s) or {}).get("zustand") == "entfaellt"}
    ist_laeuft = {s for s in status.STAGES if s in d["stages"]} - ist_entf
    if not (set(d["stages"]) >= set(status.STAGES) and ist_laeuft == soll):
        status.bedarf_setzen(werk, soll, wer=wer)
    return b, soll, []


# ------------------------------------------------------------------ Sprachen je Stage
def sprachen(stage, b):
    """Sprachliste einer Stage, die je Sprache laeuft; None = einmal je Werk."""
    s = status._norm(stage)
    if s == "500":
        return b.audiosprachen()
    if s == "510":
        return b.audiosprachen("hoerspiel")
    if s == "520":
        return [lg for lg in b.audiosprachen() if any(p["inhalt"] in AUDIO
                for p in b.produkte_fuer(sprache=lg, kanal="taella"))]
    if s == "630":
        return [lg for lg in b.zielsprachen if b.hat(sprache=lg, kanal="epub")]
    if s == "710":
        return [lg for lg in b.sprachen if b.kanaele(lg)]
    return None
