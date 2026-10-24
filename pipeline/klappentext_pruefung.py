"""Klappentext-Pruefung (18.10.2026)
Funktion:     Prueft work/600_klappentext.json auf bekannte Fehlerbilder.
Wirkungsweise: reine Regelpruefung, kein Modellaufruf, keine Abhaengigkeit von config
              (wird von s600 UND vom Cockpit importiert).
Komponenten:  pipeline/klappentext_pruefung.py
Abnehmer:     s600 Klappentext (Reparatur), cockpit/server.py (Status + Tor-Anzeige)

Fehler (blockieren den Schritt):
  - Block leer / Sprache leer
  - DE-Satz = EN-Satz oder DE-Satz nicht deutsch  -> per Reparatur nachuebersetzbar
  - Gutenberg-/Lizenz-/Transcriber-Text im Klappentext oder Zitat  -> Neuerzeugung
Hinweise (blockieren nicht, erscheinen am Tor):
  - Klappentext beschreibt Einleitung/Edition statt Werk
  - Koeder-Zitat steht nicht woertlich im Quelltext
"""
import re

BLOECKE = ("koeder", "einordnung", "autor")
_BOILER = re.compile(
    r"project gutenberg|gutenberg\.org|\bgutenberg\b|\be-?books?\b|\betext\b|www\.|https?://|"
    r"transcriber|produced by|small print|under the terms|licen[cs]e included|"
    r"for the use of anyone anywhere|distributed proofread", re.I)
_EINL = re.compile(
    r"\b(introduction|preface|annotat\w*|editor'?s?|scholarly edition|this edition|commented|"
    r"einleitung|vorwort|anmerkungen|herausgeber|kommentierte ausgabe|diese ausgabe|edition)\b", re.I)
_DE = re.compile(r"\b(und|der|die|das|nicht|ich|sie|ist|ein|eine|einer|mit|zu|den|dem|auf|sich|es|war|wurde|im|von|des|er|seine|ihre|wie|f\u00fcr|\u00fcber|geboren)\b", re.I)
_EN = re.compile(r"\b(the|and|of|was|is|to|with|this|his|her|that|which|from|into|by)\b", re.I)


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _ist_deutsch(t):
    if len((t or "").split()) < 4:
        return True                      # zu kurz fuer Urteil (z. B. Name)
    en, de = len(_EN.findall(t)), len(_DE.findall(t))
    return not (en >= 2 and en > de)


def pruefe(kt, quelltext=None):
    """kt = Inhalt von 600_klappentext.json. Liefert
    {"ok": bool, "fehler": [..], "hinweise": [..], "nachuebersetzen": [(block, i)], "neu": bool}"""
    fehler, hinweise, nach, neu = [], [], [], False
    bl = (kt or {}).get("blurb") or {}
    meta = (kt or {}).get("meta") or {}
    for b in BLOECKE:
        items = bl.get(b) or []
        if not items:
            fehler.append(f"{b}: leer"); neu = True; continue
        for i, s in enumerate(items):
            en, de = str(s.get("en", "")).strip(), str(s.get("de", "")).strip()
            if not en:
                fehler.append(f"{b}[{i}]: EN leer"); neu = True
            if not de:
                fehler.append(f"{b}[{i}]: DE leer"); nach.append((b, i))
            elif _norm(de) == _norm(en) and len(en.split()) >= 4:
                fehler.append(f"{b}[{i}]: DE = EN (unuebersetzt)"); nach.append((b, i))
            elif not _ist_deutsch(de):
                fehler.append(f"{b}[{i}]: DE nicht deutsch"); nach.append((b, i))
            for lg, t in (("en", en), ("de", de)):
                m = _BOILER.search(t)
                if m:
                    fehler.append(f"{b}[{i}].{lg}: Gutenberg/Lizenz-Text ('{m.group(0)}')"); neu = True
    for f in ("leseprobe_zitat", "essenz"):
        m = _BOILER.search(str(meta.get(f, "")))
        if m:
            fehler.append(f"{f}: Gutenberg/Lizenz-Text ('{m.group(0)}')"); neu = True
    einl = " ".join(str(s.get("en", "")) for s in (bl.get("einordnung") or [])) + " " + str(meta.get("essenz", ""))
    treffer = sorted({m.group(0).lower() for m in _EINL.finditer(einl)})
    if len(treffer) >= 2:
        hinweise.append("beschreibt evtl. Einleitung/Edition statt Werk (" + ", ".join(treffer[:4]) + ")")
    q = meta.get("leseprobe_zitat") or ""
    if q and quelltext and _norm(q)[:60] not in _norm(quelltext):
        hinweise.append("Koeder-Zitat steht nicht woertlich im Quelltext")
    return {"ok": not fehler, "fehler": fehler, "hinweise": hinweise,
            "nachuebersetzen": nach, "neu": neu}
