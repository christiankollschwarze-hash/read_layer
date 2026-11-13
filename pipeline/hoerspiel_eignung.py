"""Hoerspiel-Eignung eines Werks (Empfehlung fuer 095 Produktwahl, 13.11.2026).
Lokal, 0 $, ohne LLM: misst am Rohtext
  - Anteil woertlicher Rede (Zeichen in Anfuehrungszeichen „…“ “…” "…" «…» »…«),
  - Sprechervielfalt (Namen an Redeverben: "said Tom", "Tom asked", "sagte Anna", …),
  - Buehnenform (Sprecherzeilen "HAMLET." / "Tom:" am Zeilenanfang, ACT/SCENE/AKT/SZENE).
Liegt schon ein Profil (210) vor, zaehlt dessen Figurenliste als Sprecherzahl mit.
Urteil: geeignet | bedingt | ungeeignet | unbekannt (kein Rohtext), dazu Stufe-Empfehlung und Gruende.
"""
import json
import os
import re

REDE_GUT = 0.25          # Anteil woertlicher Rede ab dem ein Hoerspiel traegt
REDE_MIN = 0.12          # darunter kaum Szenen mit Figurenstimmen
SPRECHER_GUT = 4         # wiederkehrende Sprecher (>= SPRECHER_TREFFER Redebegleitsaetze)
SPRECHER_MIN = 2
SPRECHER_TREFFER = 3
BUEHNE_MIN = 30          # Sprecherzeilen fuer Buehnenform
MAX_ZEICHEN = 2_000_000  # Rechenzeit begrenzen (Stichprobe vom Anfang)

_REDE = re.compile(r"„[^“”\"]{1,1500}[“”\"]|“[^”]{1,1500}”|\"[^\"]{1,1500}\"|«[^»]{1,1500}»|»[^«]{1,1500}«")
_VERBEN = (r"said|asked|cried|replied|answered|whispered|shouted|exclaimed|continued|returned|muttered|"
           r"sagte|fragte|rief|antwortete|flüsterte|schrie|erwiderte|meinte|murmelte|"
           r"dijo|preguntó|respondió|gritó|dit|demanda|répondit|cria|disse|chiese|rispose|gridò")
_NAME = r"([A-ZÄÖÜÀ-Ý][a-zäöüßà-ÿ]{2,}(?:\s[A-ZÄÖÜ][a-zäöüß]{2,})?)"
_NACH = re.compile(rf"\b(?:{_VERBEN})\s+{_NAME}")
_VOR = re.compile(rf"{_NAME}\s+(?:{_VERBEN})\b")
_BUEHNE = re.compile(r"^[ \t]{0,4}([A-ZÄÖÜ][A-ZÄÖÜ .'-]{1,28}[A-ZÄÖÜ])(?:\.|:|[ \t]*$)|^[ \t]{0,4}([A-ZÄÖÜ][a-zäöüß]{2,15}):\s", re.M)
_AKT = re.compile(r"^\s*(ACT|SCENE|AKT|SZENE|ACTO|ESCENA|ACTE|SCÈNE|ATTO)\s+[IVXLC\d]+", re.M | re.I)
_KEIN_NAME = {"The", "And", "But", "Then", "She", "He", "They", "It", "This", "That", "Der", "Die", "Das", "Sie", "Er",
              "Und", "Aber", "Dann", "Was", "Wie", "When", "What", "Yes", "Nein", "Well", "Now", "Chapter", "Kapitel"}
_MARKEN = {"ACT", "SCENE", "AKT", "SZENE", "CHAPTER", "KAPITEL", "BOOK", "BUCH", "PART", "TEIL", "THE", "END", "NOTE"}


def rohtext(ordner):
    for f in ("raw_modernized.txt", "raw.txt"):
        p = os.path.join(ordner, f)
        if os.path.exists(p):
            with open(p, encoding="utf-8", errors="ignore") as fh:
                return fh.read(MAX_ZEICHEN)
    return None


def figuren_aus_profil(ordner):
    p = os.path.join(ordner, "work", "210_profil.json")
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    ch = (d.get("profile") or d).get("characters") if isinstance(d, dict) else None
    return len(ch) if isinstance(ch, (dict, list)) else None


def messen(text):
    text = (text or "").replace("\r", "")
    flach = re.sub(r"\s+", " ", text)            # Gutenberg-Zeilenumbrueche: Rede ueber Zeilen hinweg
    n = max(1, len(flach))
    rede = sum(len(m.group()) for m in _REDE.finditer(flach))
    namen = {}
    for rx in (_NACH, _VOR):
        for m in rx.finditer(flach):
            w = m.group(1)
            if w.split()[0] not in _KEIN_NAME:
                namen[w] = namen.get(w, 0) + 1
    sprecher = sorted((k for k, v in namen.items() if v >= SPRECHER_TREFFER), key=lambda k: -namen[k])
    buehne = {}
    for m in _BUEHNE.finditer(text):
        w = (m.group(1) or m.group(2)).strip()
        if w.split()[0].title() not in _KEIN_NAME and w.split()[0].upper() not in _MARKEN:
            buehne[w] = buehne.get(w, 0) + 1
    zeilen = sum(v for v in buehne.values() if v >= 2)
    akte = len(_AKT.findall(text))
    return {"zeichen": len(text), "rede_anteil": round(rede / n, 3), "sprecher": sprecher[:12],
            "n_sprecher": len(sprecher), "buehne_zeilen": zeilen,
            "buehne_rollen": len([k for k, v in buehne.items() if v >= 3]), "akte": akte}


def bewerten(text, figuren=None):
    """-> {urteil, stufe, gruende[], werte{}}."""
    if not text:
        return {"urteil": "unbekannt", "stufe": None, "werte": {},
                "gruende": ["Rohtext fehlt noch (nach 100/150 neu bewerten)"]}
    w = messen(text)
    n_sp = max(w["n_sprecher"], w["buehne_rollen"], figuren or 0)
    w["figuren_210"] = figuren
    g = []
    drama = w["buehne_zeilen"] >= BUEHNE_MIN and w["buehne_rollen"] >= SPRECHER_MIN
    if drama:
        g.append(f"Bühnenform: {w['buehne_zeilen']} Sprecherzeilen, {w['buehne_rollen']} Rollen"
                 + (f", {w['akte']} Akt-/Szenenmarken" if w["akte"] else ""))
        return {"urteil": "geeignet", "stufe": "drama", "werte": w, "gruende": g + ["Text ist bereits Dialog – Stufe drama"]}
    g.append(f"wörtliche Rede {w['rede_anteil']:.0%} (gut ab {REDE_GUT:.0%}, Minimum {REDE_MIN:.0%})")
    g.append(f"{n_sp} wiederkehrende Sprecher" + (f" ({', '.join(w['sprecher'][:5])})" if w["sprecher"] else "")
             + (f"; Profil 210: {figuren} Figuren" if figuren is not None else ""))
    if w["rede_anteil"] >= REDE_GUT and n_sp >= SPRECHER_GUT:
        u = "geeignet"
    elif w["rede_anteil"] >= REDE_MIN and n_sp >= SPRECHER_MIN:
        u = "bedingt"
        g.append("Erzähler trägt den Großteil – Hörspiel wirkt nur in Dialogszenen")
    else:
        u = "ungeeignet"
        g.append("kaum Szenen mit verteilten Stimmen – Hörbuch empfohlen")
    return {"urteil": u, "stufe": "premium" if u != "ungeeignet" else None, "werte": w, "gruende": g}


def fuer_werk(ordner):
    return bewerten(rohtext(ordner), figuren_aus_profil(ordner))
