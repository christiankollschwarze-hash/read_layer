"""Einfache Spracherkennung fuer die Sprachliste (en, de, es, fr, it) ueber Funktionswoerter.
Ohne externe Bibliothek, deterministisch. Gedacht fuer Gates (300 ff.): "ist dieser Text in Sprache X?".

  erkennen(text) -> (sprache | None, {sprache: anteil})
  ist(text, lg)  -> True/False/None (None = zu kurz bzw. nicht entscheidbar)
"""

import re

_W = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?", re.U)

STOPP = {
    "en": "the and of to is that with his her it you he she not for had but which have were this from they at by would",
    "de": "und der die das nicht ich sie ist ein eine einen mit zu den dem auf sich es war im von des er wie auch hatte noch wurde nach aus",
    "fr": "le les et des une est qui ne pas il elle dans pour sur avec au ce se je mais était sont son ses lui cette",
    "es": "el los las y que en una es por con no se lo su para al como más pero sus le fue esta muy",
    "it": "il le e di che una è per non con si lo gli della nel sono come più ma anche questo alla sua dei",
}
STOPP = {k: set(v.split()) for k, v in STOPP.items()}
MIN_WOERTER = 20


def woerter(text):
    return [w.lower() for w in _W.findall(text or "")]


def erkennen(text, sprachen=None, min_woerter=MIN_WOERTER, min_treffer=2):
    w = woerter(text)
    if len(w) < min_woerter:
        return None, {}
    sp = [s for s in (sprachen or STOPP) if s in STOPP]
    treffer = {s: sum(1 for x in w if x in STOPP[s]) for s in sp}
    anteil = {s: treffer[s] / len(w) for s in sp}
    rang = sorted(anteil, key=anteil.get, reverse=True)
    if not rang or anteil[rang[0]] < 0.05 or treffer[rang[0]] < min_treffer:
        return None, anteil
    if len(rang) > 1 and anteil[rang[0]] < 1.3 * anteil[rang[1]]:
        return None, anteil
    return rang[0], anteil


def ist(text, lg, min_woerter=MIN_WOERTER):
    s, _a = erkennen(text, min_woerter=min_woerter)
    if s is None:
        return None
    return s == lg
