"""Klappentext-Pruefung (Regeln fuer Gate 600, Umbau Phase 2, 03.11.2026)
Funktion:     Reine Regelpruefungen fuer work/600_klappentext.json, kein Modellaufruf.
Komponenten:  pipeline/klappentext_pruefung.py (von s600 und vom Cockpit importiert)
Abnehmer:     s600 Klappentext (Gate), cockpit/server.py (Anzeige)

Regeln (je Sprache der Sprachliste, nicht nur DE/EN):
  boiler(t)        Gutenberg-/Lizenz-/Transcriber-Text
  markup(t)        Markup-Reste (_kursiv_, *...*, --, HTML-Tags)
  markup_weg(t)    entfernt Markup deterministisch
  einleitung(t)    Treffer "Einleitung/Edition statt Werk"
  sprache_falsch(t, lg)  erkannte Sprache != lg (tools/sprache, Funktionswoerter)
  kopie(q, z, src) Zielsatz = Quellsatz (unuebersetzt)
  enthalten(teil, text)  normalisierter Volltext-Abgleich (Koeder woertlich)
  jahre(t), namen(texte)  Fakten im Autor-Block
  pruefe(kt)       Kurzpruefung fuer das Cockpit (ok/fehler/hinweise), nutzt das Gate-Ergebnis in kt["pruefung"]
"""
import re

BLOECKE = ("koeder", "einordnung", "autor")
SPRACHE_MIN_WOERTER = 6

_BOILER = re.compile(
    r"project gutenberg|gutenberg\.org|\bgutenberg\b|\be-?books?\b|\betext\b|www\.|https?://|"
    r"transcriber|produced by|small print|under the terms|licen[cs]e included|"
    r"for the use of anyone anywhere|distributed proofread", re.I)
_EINL = re.compile(
    r"\b(introduction|preface|annotat\w*|editor'?s?|scholarly edition|this edition|commented|"
    r"einleitung|vorwort|anmerkungen|herausgeber|kommentierte ausgabe|diese ausgabe|edition|"
    r"introducci[oó]n|pr[oó]logo|pr[eé]face|introduzione|prefazione|[eé]dition critique|edizione)\b", re.I)
_MARKUP = re.compile(r"(?<![\w])_[^_\n]+_(?![\w])|\*[^*\n]+\*|--|<[^>]{1,40}>")
_JAHR = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
_NAME = re.compile(r"\b[A-ZÀ-ÖØ-Þ][\w’'\-]{2,}")


def norm(s):
    return re.sub(r"[\W_]+", "", (s or "").lower())


def boiler(t):
    m = _BOILER.search(t or "")
    return m.group(0) if m else None


def markup(t):
    return _MARKUP.findall(t or "")


def markup_weg(t):
    t = re.sub(r"(?<![\w])_([^_\n]+)_(?![\w])", r"\1", t or "")
    t = re.sub(r"\*([^*\n]+)\*", r"\1", t)
    t = re.sub(r"<[^>]{1,40}>", "", t)
    t = t.replace("--", "–")
    return re.sub(r"[ \t]+", " ", t).strip()


def einleitung(t):
    return sorted({m.group(0).lower() for m in _EINL.finditer(t or "")})


def sprache_falsch(t, lg):
    """Erkannte Sprache, wenn sie von lg abweicht; None bei passend oder nicht entscheidbar."""
    from tools import sprache
    erk, _a = sprache.erkennen(t, min_woerter=SPRACHE_MIN_WOERTER)
    return erk if erk and erk != lg else None


def kopie(q, z, src):
    from tools import sprache
    if not q or not z:
        return False
    funktion = sum(1 for w in sprache.woerter(q) if w in sprache.STOPP.get(src, ()))
    return funktion >= 2 and norm(q) == norm(z)


def enthalten(teil, text):
    n = norm(teil)
    return bool(n) and n in norm(text)


def jahre(t):
    return sorted(set(_JAHR.findall(t or "")))


def namen(texte):
    """Eigennamen-Kandidaten: grossgeschriebene Woerter, die in mind. zwei Sprachfassungen gleich stehen
    (Namen und Orte bleiben ueber Sprachen gleich, Gattungswoerter nicht)."""
    mengen = [set(_NAME.findall(t or "")) for t in texte if t]
    if len(mengen) < 2:
        return []
    zaehl = {}
    for m in mengen:
        for w in m:
            zaehl[w] = zaehl.get(w, 0) + 1
    return sorted(w for w, n in zaehl.items() if n >= 2)


def pruefe(kt, quelltext=None):
    """Kurzpruefung fuer das Cockpit: Gate-Ergebnis aus kt['pruefung'] plus Regelbefunde ohne Modell."""
    fehler, hinweise = [], []
    bl = (kt or {}).get("blurb") or {}
    for b in BLOECKE:
        for i, s in enumerate(bl.get(b) or []):
            for lg, t in (s or {}).items():
                if boiler(t):
                    fehler.append(f"{b}[{i}].{lg}: Lizenztext")
                if markup(t):
                    fehler.append(f"{b}[{i}].{lg}: Markup")
    p = (kt or {}).get("pruefung") or {}
    fehler += [x for x in p.get("fehler", []) if x not in fehler]
    hinweise += p.get("hinweise", [])
    if not any(bl.get(b) for b in BLOECKE):
        fehler.append("Klappentext leer")
    return {"ok": not fehler, "fehler": fehler, "hinweise": hinweise, "nachuebersetzen": [], "neu": False}
