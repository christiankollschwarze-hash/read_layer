"""Kapiteltext-Helfer (Stage 120)
Funktion:     Rohtext entfasern (Gutenberg-Rahmen, Zeilenumbruch), Kapitel erkennen, Titelblock am
              Werkanfang und Schluss-Marker entfernen.
Herkunft:     aus s620_epub_original (Befund 620/630 (11): Front-Matter-Stripper nur noch in 120).
Abnehmer:     s120_modernisierung
"""

import re

from config import config

def _strip_boilerplate(t: str) -> str:
    for mk in ("*** START OF THE PROJECT GUTENBERG", "*** START OF THIS PROJECT GUTENBERG"):
        i = t.find(mk)
        if i != -1:
            nl = t.find("\n", i); t = t[nl + 1:] if nl != -1 else t; break
    for mk in ("*** END OF THE PROJECT GUTENBERG", "*** END OF THIS PROJECT GUTENBERG"):
        i = t.find(mk)
        if i != -1:
            t = t[:i]; break
    # Sicherheitsnetz: Lizenz-/Nachspann-Bloecke, die manchmal trotzdem anhaengen.
    for mk in ("START: FULL LICENSE", "*** START OF THE FULL PROJECT GUTENBERG LICENSE",
               "THE FULL PROJECT GUTENBERG LICENSE", "End of the Project Gutenberg"):
        i = t.find(mk)
        if i != -1:
            t = t[:i]; break
    return t.strip()


_CHAP_RE = re.compile(r"^\s*(chapter|kapitel)\b", re.IGNORECASE)

def _is_heading_block(block: str) -> bool:
    """Ein Block ist eine Ueberschrift, wenn er einzeilig, kurz und ueberwiegend
    Grossbuchstaben ist (Gutenberg-Konvention) ODER mit 'Chapter/Kapitel' beginnt."""
    if "\n" in block:
        return False
    s = block.strip()
    if not s or len(s) > 60:
        return False
    if _CHAP_RE.match(s):
        return True
    # Echte Titel enden NICHT auf einen Punkt; Signaturen/Saetze schon
    # ("HENRY JEKYLL.", "HASTIE LANYON.", "H.J.", "1.F.", "DAMAGE.").
    if s.rstrip("\u201d\u2019\"' ").endswith("."):
        return False
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 2:
        return False
    upper = sum(1 for c in letters if c.isupper())
    return upper / len(letters) >= 0.8

_SMALL = {"a","an","and","the","of","or","to","in","on","at","by","for","with",
          "von","der","die","das","und","oder","im","zu"}

def _titlecase(s: str) -> str:
    """ALL-CAPS-Ueberschrift -> lesbare Schreibung. Gemischte Schreibung bleibt."""
    letters = [c for c in s if c.isalpha()]
    if not letters or sum(c.isupper() for c in letters) / len(letters) < 0.9:
        return s  # nicht durchgaengig Caps -> unveraendert lassen
    words = s.lower().split()
    out = []
    for i, w in enumerate(words):
        out.append(w if (w in _SMALL and i != 0) else (w[:1].upper() + w[1:]))
    return " ".join(out)

def _split_chapters(text: str):
    """Liefert [(titel, [absatz, ...]), ...]. Marker-Konvention zuerst, sonst Heuristik."""
    marker = config.MARKERS.get("chapter", "###CHAPTER###")
    chapters = []

    if marker in text:
        for seg in text.split(marker)[1:]:
            lines = seg.strip("\n").split("\n", 1)
            title = lines[0].strip()
            body = lines[1] if len(lines) > 1 else ""
            chapters.append((title or f"Chapter {len(chapters)+1}", _paragraphs(body)))
        if chapters:
            return chapters

    # Heuristik (blockbasiert):
    #  - Echte Ueberschrift = Caps-Block, dem substanzieller Fliesstext folgt
    #    (bevor die naechste Ueberschrift kommt). Das verwirft TOC-Listen
    #    (Ueberschrift folgt auf Ueberschrift) UND den Vorspann (Titel/Autor).
    #  - Caps-Bloecke OHNE folgenden Fliesstext (z.B. Signaturen) bleiben Absatz.
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    is_hr = lambda b: bool(re.fullmatch(r"[\*\u2014\-\s]{3,}", b))
    heads = [(_is_heading_block(b) and not is_hr(b)) for b in blocks]

    def _body_follows(i: int) -> bool:
        for j in range(i + 1, len(blocks)):
            if heads[j]:
                return False
            if not is_hr(blocks[j]) and len(blocks[j]) >= 120:
                return True
        return False

    cur = None
    started = False
    for i, b in enumerate(blocks):
        if heads[i] and _body_follows(i):
            cur = (_titlecase(b), [])
            chapters.append(cur)
            started = True
        elif not started:
            continue  # Vorspann / Inhaltsverzeichnis vor dem 1. echten Kapitel -> weg
        elif is_hr(b):
            if cur:
                cur[1].append("\u2014\u2014HR\u2014\u2014")
        else:
            cur[1].append(" ".join(l.strip() for l in b.split("\n")))

    if not chapters:
        chapters = [("", _paragraphs(text))]
    return chapters

def _paragraphs(body: str):
    out = []
    for block in re.split(r"\n\s*\n", body):
        b = block.strip()
        if b:
            out.append(" ".join(l.strip() for l in b.split("\n")))
    return out

def _rewrap(text: str) -> str:
    """Entfasert hart umbrochenen Text zu echten Absatz-Bloecken.
    Feste Regel fuer ALLE Titel -- robust gegen normal UND doppelt
    zeilengeschaltete Gutenberg-Dateien:
      - normal (wenige Leerzeilen): Leerzeile = Absatzgrenze, Zeilen verbinden.
      - doppelt (Leerzeile nach jeder Zeile): Fuell-Heuristik -- eine kurze
        Schlusszeile beendet den Absatz; 2+ Leerzeilen sind harte Grenzen.
    Ueberschriften (kurze Caps-Zeilen) bleiben eigene Bloecke.
    Ausgabe: Bloecke durch genau eine Leerzeile getrennt."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    nonempty = [l for l in lines if l.strip()]
    if not nonempty:
        return text
    blanks = sum(1 for l in lines if not l.strip())
    double_spaced = blanks >= 0.6 * len(nonempty)
    lens = sorted(len(l.rstrip()) for l in nonempty)
    wrapw = lens[int(len(lens) * 0.9)]          # 90%-Perzentil der Zeilenlaenge
    thresh = max(40, int(wrapw * 0.66))         # "kurze" Zeile -> Absatzende

    blocks, cur, blank_run = [], [], 0
    def flush():
        if cur:
            blocks.append(" ".join(cur)); cur.clear()

    for l in lines:
        s = l.strip()
        if not s:
            blank_run += 1
            if not double_spaced:
                flush()
            elif blank_run >= 2:
                flush()
            continue
        blank_run = 0
        if _is_heading_block(s):     # Ueberschrift steht allein
            flush(); blocks.append(s); continue
        cur.append(s)
        if double_spaced and len(l.rstrip()) < thresh:
            flush()                  # kurze Schlusszeile beendet den Absatz
    flush()
    return "\n\n".join(blocks)


# ============================================================
# FRONT-MATTER-STRIPPER: entfernt den werkinternen Titelblock am Anfang des ersten Kapitels
# (doppelter Titel, "by Autor", Attribution, Epigraph), der sonst getaggt+
# vertont und im EPUB doppelt gezeigt wird. Konservativ: greift nur bei
# bestaetigtem Titel/Autor-Duplikat und nie ueber den ersten echten Absatz.
# ============================================================
_FM_MIN_PROSE = 200     # ein "echter" Erzaehl-Absatz ist lang
_FM_SCAN_LIMIT = 15     # nur ganz am Anfang suchen

def _fm_norm(s: str) -> str:
    return re.sub(r"[^\w]", "", (s or "").lower())

def strip_leading_front_matter(paragraphs, title: str = "", author: str = ""):
    """Liefert die Absatzliste OHNE fuehrenden Titelblock. Entfernt nur fuehrende Absaetze, die
    selbst Titelblock sind (Titel-/Autor-Duplikat, 'by Autor', HR, leer, ohne Kleinbuchstaben),
    und nur, wenn ein Titel- oder 'by Autor'-Duplikat den Block bestaetigt. Der erste andere Absatz
    bleibt immer stehen – auch kurze Erzaehlsaetze (Fix 02.11.2026, Yellow Wallpaper: vorher wurde
    bis zum ersten Absatz >= _FM_MIN_PROSE Zeichen gestrichen)."""
    hr = "\u2014\u2014HR\u2014\u2014"
    paras = list(paragraphs)
    tnorm, anorm = _fm_norm(title), _fm_norm(author)
    ende, confirmed = 0, False
    for p in paras[:_FM_SCAN_LIMIT]:
        n = _fm_norm(p or "")
        titel = bool(tnorm and n and (n == tnorm or (len(n) >= 5 and tnorm.startswith(n))))
        byline = (bool(re.match(r"(?i)^\s*by(\s+\w|\s*$)", p or "")) and len(p) < 120)
        autor = bool(anorm and n == anorm)
        vermerk = bool(p) and len(p) < 300 and bool(re.search(
            r"(?i)\b(translated by|reprinted by|copyright|all rights reserved|illustrated by)\b", p))
        if titel or byline:
            confirmed = True
        if titel or byline or autor or vermerk or not p or p == hr \
                or not re.search(r"[a-z\u00e0-\u00ff]", p):
            ende += 1
            continue
        break
    return paras[ende:] if confirmed and ende < len(paras) else paras

def strip_trailing_end_marker(paragraphs):
    """Entfernt einen blanken Schluss-Marker ('THE END', 'FINIS') am Werkende.
    Echter Inhalt (z.B. 'Postscript'-Abschnitte) bleibt stehen."""
    paras = list(paragraphs)
    while paras:
        last = paras[-1].strip().rstrip(".")
        if last.upper() in ("THE END", "FINIS", "END") and len(last) <= 8:
            paras.pop()
        else:
            break
    return paras
