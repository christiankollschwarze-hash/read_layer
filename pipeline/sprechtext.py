"""READ LAYER - Sprechtext-Regeln (Stage 400; Text/EPUB/App bleiben unveraendert).

Funktion:  Lesetext -> Sprechtext je Sprache (en, de, es, fr, it) plus Abbildung Sprechtext-Span -> Lesetext-Span
           (fuer 520: FA auf dem Sprechtext, Rueckabbildung auf den Lesetext).
Genutzt:   pipeline/s400_regie.py (schreibt production.sprechtext/abbildung), bis zum Umbau 500 auch
           tools/tts_paket.py, tools/teaser_paket.py, tools/overlay_gemini.py, s500_vertonung_gemini.py.

Standard-Regeln (Reihenfolge):
  1 Kursiv-/Fett-Marken _..._ / *...* weg (alle Sprachen)
  2 Ueberschrift (typ h): roemische Nummer am Anfang ("IX. Titel", "XIV", "IV: Titel", "XIV Titel") -> Zahlwort
  3 Schluesselwort + roemisch ("Chapter IV", "CHAPTER IV", "Book/Part/Act/Scene II", "Kapitel IV", "World War II")
    -> Zahlwort (Grundzahl), auch im Fliesstext
  4 Herrschernamen nur mit Namen davor: "Henry VIII" -> "Henry the Eighth" / "Heinrich der Achte" / "Enrique Octavo" /
    "Louis Quatorze"; Pronomen "I" bleibt ("Then I went")
  5 DE: Datumsspanne, Datum, Uhrzeit, "ca.", Ordinalzahl vor Zeit-/Zaehlwort ("19. Jahrhunderts")
  6 Jahresspanne "1860-1935" -> "1860 bis/to/a/à/a 1935"
Erweiterte Regeln (Stage 400: 1x automatisch bei Sprechtext-Fehler):
  Symbole %, &, § -> Wort; Ordinalzahlen en (1st, 19th); Uhrzeit h:mm; Tausendertrenner; Dezimalzahlen;
  Jahreszahlen 1100-2099 (Jahresform); uebrige Ziffern -> Grundzahl. Zahlwoerter ueber num2words
  (py -3.11 -m pip install num2words); fehlt es, bleiben Ziffern stehen (Gate 400 -> Mensch).
"""
import re

try:
    from num2words import num2words as _n2w
except Exception:                                   # pragma: no cover
    _n2w = None

REGELN_V = 2
SPRACHEN = ("en", "de", "es", "fr", "it")

# ============================================================ Zahlwoerter
_W = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
_DE = "null eins zwei drei vier fünf sechs sieben acht neun zehn elf zwölf dreizehn vierzehn fünfzehn sechzehn siebzehn achtzehn neunzehn".split()
_DE10 = {2: "zwanzig", 3: "dreißig", 4: "vierzig", 5: "fünfzig", 6: "sechzig", 7: "siebzig", 8: "achtzig", 9: "neunzig"}
_EN = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_EN10 = {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty", 6: "sixty", 7: "seventy", 8: "eighty", 9: "ninety"}
_EN_ORD = {1: "first", 2: "second", 3: "third", 5: "fifth", 8: "eighth", 9: "ninth", 12: "twelfth"}
_ROEM_GUELTIG = re.compile(r"^M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")
_ROEM_TOKEN = re.compile(r"(?<![\w])([IVXLCDM]+)(?![\w])")


def ist_roemisch(s):
    return bool(s) and bool(_ROEM_GUELTIG.match(s))


def roemisch_zu_int(s):
    n, vor = 0, 0
    for c in reversed(s):
        v = _W[c]
        n += -v if v < vor else v
        vor = max(vor, v)
    return n


def zahlwort(n, lg="de"):
    """Grundzahl als Wort; de/en bis 100 eingebaut, sonst num2words (None, wenn nicht moeglich)."""
    if lg in ("de", "en") and 0 <= n <= 100:
        if n == 100:
            return "hundert" if lg == "de" else "one hundred"
        if n < 20:
            return (_DE if lg == "de" else _EN)[n]
        z, e = divmod(n, 10)
        if lg == "de":
            return _DE10[z] if not e else ("ein" if e == 1 else _DE[e]) + "und" + _DE10[z]
        return _EN10[z] + ("" if not e else "-" + _EN[e])
    return _n2w_sicher(n, lg)


def _n2w_sicher(n, lg, to="cardinal"):
    if _n2w is None or lg not in SPRACHEN:
        return None
    try:
        return _n2w(n, lang=lg, to=to)
    except Exception:
        return None


def ordinalwort(n, lg="de"):
    """Ordnungszahl (Grundform: eighth / achte / octavo / huitième / ottavo)."""
    w = _n2w_sicher(n, lg, "ordinal")
    if w:
        return w
    if lg == "de" and 0 < n < 100:
        return ordinal_de(n, "der")
    if lg == "en" and 0 < n < 20:
        b = _EN_ORD.get(n) or _EN[n] + "th"
        return b.replace("tt", "t") if n == 8 else b
    return None


def _gross(w):
    return w[:1].upper() + w[1:] if w else w


# ============================================================ Spur mit Abbildung
class _Spur:
    """Text mit Herkunft je Zeichen (Lesetext-Span) ueber mehrere Ersetzungsdurchgaenge."""

    def __init__(self, text):
        self.l = text
        self.t = text
        self.h = [(i, i + 1, None) for i in range(len(text))]
        self.blk = 0

    def sub(self, rx, fn):
        out, herk, pos = [], [], 0
        for m in rx.finditer(self.t):
            r = fn(m)
            if r is None:
                continue
            ers = [(m.start(), m.end(), r)] if isinstance(r, str) else sorted(r)
            for a, b, txt in ers:
                if a < pos or (txt == self.t[a:b]):
                    continue
                out.append(self.t[pos:a])
                herk.extend(self.h[pos:a])
                if b > a:
                    os_, oe = min(x[0] for x in self.h[a:b]), max(x[1] for x in self.h[a:b])
                    self.blk += 1
                    out.append(txt)
                    herk.extend([(os_, oe, self.blk)] * len(txt))
                pos = b
        if not out:
            return self
        out.append(self.t[pos:])
        herk.extend(self.h[pos:])
        self.t, self.h = "".join(out), herk
        return self

    def abbildung(self):
        """[[s0, s1, l0, l1], ...] fuer ersetzte Bloecke und Loeschungen (s0 == s1); Rest 1:1 fortlaufend."""
        out, erw, i, n = [], 0, 0, len(self.t)
        while i < n:
            os_, oe, blk = self.h[i]
            if blk is None:
                if os_ > erw:
                    out.append([i, i, erw, os_])
                erw = max(erw, oe)
                i += 1
                continue
            j = i
            while j < n and self.h[j][2] == blk:
                j += 1
            if os_ > erw:
                out.append([i, i, erw, os_])
            out.append([i, j, os_, oe])
            erw = max(erw, oe)
            i = j
        if erw < len(self.l):
            out.append([n, n, erw, len(self.l)])
        return out


def herkunft(abb, n_sprech):
    """Je Sprechtext-Zeichen (l0, l1) im Lesetext, aus der Abbildung rekonstruiert."""
    out, erw, pos = [], 0, 0
    for a, b, c, d in sorted(abb, key=lambda x: (x[0], x[1])):
        while pos < a:
            out.append((erw, erw + 1))
            erw += 1
            pos += 1
        if a == b:
            erw = d
            continue
        out.extend([(c, d)] * (b - a))
        erw = max(erw, d)
        pos = b
    while pos < n_sprech:
        out.append((erw, erw + 1))
        erw += 1
        pos += 1
    return out


def lesespan(abb, s0, s1, n_sprech=None):
    """Sprechtext-Span [s0, s1) -> Lesetext-Span (l0, l1)."""
    h = herkunft(abb, n_sprech if n_sprech is not None else max([s1] + [x[1] for x in abb]))
    teil = h[s0:s1] or h[max(0, s0 - 1):s0]
    if not teil:
        return (0, 0)
    return (min(x[0] for x in teil), max(x[1] for x in teil))


# ============================================================ Standard-Regeln
_KURSIV = re.compile(r"(?<![\w])[_*]+|[_*]+(?![\w])")


def _r_kursiv(sp, lg, typ):
    return sp.sub(_KURSIV, lambda m: "")


_KOPF = re.compile(r"^\s*([IVXLCDM]+)(?![\w])")


def _r_ueberschrift(sp, lg, typ):
    if typ != "h":
        return sp

    def f(m):
        tok = m.group(1)
        rest = sp.t[m.end():]
        if not ist_roemisch(tok) or (len(tok) == 1 and tok not in "IVX"):
            return None                                 # "L.", "C.", "M." am Anfang = Initiale
        ok = (rest.strip() == "" or rest[:1] in ".:" or rest.lstrip()[:1] in "-–—"
              or (len(tok) >= 2 and rest[:1].isspace()))
        n = roemisch_zu_int(tok)
        w = zahlwort(n, lg) if ok and 0 < n <= 3999 else None
        return [(m.start(1), m.end(1), _gross(w))] if w else None
    return sp.sub(_KOPF, f)


_SCHLUESSEL = {
    "en": "Chapter|Chap\\.|Ch\\.|Book|Part|Act|Scene|Volume|Vol\\.|Canto|Section|Stave|Letter|Article|Psalm|World War",
    "de": "Kapitel|Kap\\.|Bd\\.|Buch|Teil|Akt|Aufzug|Szene|Auftritt|Band|Gesang|Abschnitt|Brief|Artikel|Psalm",
    "es": "Capítulo|Libro|Parte|Acto|Escena|Tomo|Canto|Carta|Artículo",
    "fr": "Chapitre|Livre|Partie|Acte|Scène|Tome|Chant|Lettre|Article",
    "it": "Capitolo|Libro|Parte|Atto|Scena|Volume|Canto|Lettera|Articolo",
}
_SCHL_RX = re.compile(r"(?<![\w])(?i:(" + "|".join(_SCHLUESSEL.values()) + r"))(\s+)([IVXLCDM]+)(?![\w])")


def _r_schluessel(sp, lg, typ):
    def f(m):
        tok = m.group(3)
        if not ist_roemisch(tok):
            return None
        w = zahlwort(roemisch_zu_int(tok), lg)
        if not w:
            return None
        if m.group(1).isupper() and len(m.group(1)) > 1:
            w = w.upper()
        elif lg == "en":
            w = "-".join(_gross(x) for x in w.split("-"))
        return [(m.start(3), m.end(3), w)]
    return sp.sub(_SCHL_RX, f)


_HERR = re.compile(r"(?<![\w])([A-ZÄÖÜÉÈÀÂÎÔÛÇÑ][\w'’-]{1,})(\s+)([IVXLCDM]+)(?![\w])")
_KEIN_NAME = {x.lower() for x in (
    "The A An And But Or So Then When If As Yes No Oh Now What Where Why How There Here Said Thought Because Until "
    "While Before After Perhaps Maybe Well Still Yet Though Although Since Once Unless Whether Did Do Does Was Were "
    "Am Is Are Had Have Has Could Would Should Must May Might Shall Will Can Let Than That This These Those Who Whom "
    "Which Whose Sir Madam Mr Mrs Miss Dr Lord Lady King Queen Pope Saint St Der Die Das Den Dem Des Ein Eine Und Aber "
    "Dann Als Wenn Ob El La Los Las Le Les Il Lo Gli Un Une Una Uno Y Et E Pero Mais Ma").split()}


def _r_herrscher(sp, lg, typ):
    def f(m):
        name, tok = m.group(1), m.group(3)
        if name.lower().strip("'’") in _KEIN_NAME or not ist_roemisch(tok):
            return None
        if tok == "I":
            nach = sp.t[m.end():m.end() + 1]
            if nach and nach not in ".,;:!?)»”\"'’":
                return None
        n = roemisch_zu_int(tok)
        if not 0 < n <= 50:
            return None
        if lg == "fr":
            w = "Premier" if n == 1 else _gross(zahlwort(n, "fr") or "")
        else:
            o = ordinalwort(n, lg)
            if not o:
                return None
            w = {"en": "the " + _gross(o), "de": "der " + _gross(o)}.get(lg, _gross(o))
        if not w:
            return None
        ende = m.end(3)
        if lg == "de" and re.match(r"\.\s+[a-zäöüß]", sp.t[ende:]):
            ende += 1                                   # "Heinrich VIII. war" -> "Heinrich der Achte war"
        return [(m.start(3), ende, w)]
    return sp.sub(_HERR, f)


# --- DE-Regeln (19./22.10.2026)
_ORD_NOMEN = (r"Jahrhundert|Jahrtausend|Jahrzehnt|Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|"
              r"November|Dezember|Geburtstag|Lebensjahr|Kapitel|Akt|Szene|Auflage|Band|Mal|Stock|Stockwerk|Platz|Tag|Woche|Monat")
_ORD = re.compile(r"(?:(\w+)\s+)?\b(\d{1,2})\.\s+(?=(?:" + _ORD_NOMEN + r")\w*\b)")
_ORD_SONDER = {1: "erst", 3: "dritt", 7: "siebt", 8: "acht"}
_ORD_STARK = {"der", "die", "das", "ins", "aufs", "fürs", "durchs", "ans"}
_DAT_SPANNE = re.compile(r"\b(\d{1,2})\.\s*[–-]\s*(\d{1,2})\.\s+(?=(?:" + _ORD_NOMEN + r")\w*\b)")
_DATUM = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
_UHR = re.compile(r"\b(\d{1,2}):(\d{2})\s*Uhr\b")
_CA = re.compile(r"\bca\.")


def ordinal_de(n, artikel=""):
    stamm = _ORD_SONDER.get(n) or (zahlwort(n, "de") + ("t" if n < 20 else "st"))
    return stamm + ("e" if artikel.lower() in _ORD_STARK else "en")


def _r_de(sp, lg, typ):
    if lg != "de":
        return sp

    def spanne(m):
        a, b = int(m.group(1)), int(m.group(2))
        if not (0 < a < 32 and 0 < b < 32):
            return None
        return [(m.start(1), m.end(2) + 1, f"{ordinal_de(a)} bis {ordinal_de(b)}")]

    def datum(m):
        t, mo = int(m.group(1)), int(m.group(2))
        if not (0 < t < 32 and 0 < mo < 13):
            return None
        return [(m.start(1), m.end(2) + 1, f"{ordinal_de(t)} {ordinal_de(mo)} ")]

    def uhr(m):
        h, mi = int(m.group(1)), int(m.group(2))
        if h > 24 or mi > 59:
            return None
        hw = "ein" if h == 1 else zahlwort(h, "de")
        return f"{hw} Uhr" + (f" {zahlwort(mi, 'de')}" if mi else "")

    def ordz(m):
        n = int(m.group(2))
        if not 0 < n < 100:
            return None
        return [(m.start(2), m.end(2) + 1, ordinal_de(n, m.group(1) or ""))]

    sp.sub(_DAT_SPANNE, spanne).sub(_DATUM, datum).sub(_UHR, uhr).sub(_CA, lambda m: "circa")
    return sp.sub(_ORD, ordz)


_SPANNE = re.compile(r"\b(\d{3,4})\s*[-–]\s*(\d{3,4})\b")
_BIS = {"de": "bis", "en": "to", "es": "a", "fr": "à", "it": "a"}


def _r_spanne(sp, lg, typ):
    return sp.sub(_SPANNE, lambda m: [(m.end(1), m.start(2), f" {_BIS.get(lg, 'to')} ")])


STANDARD = (_r_kursiv, _r_ueberschrift, _r_schluessel, _r_herrscher, _r_de, _r_spanne)

# ============================================================ Erweiterte Regeln
_SYMBOL = {"%": {"en": "percent", "de": "Prozent", "es": "por ciento", "fr": "pour cent", "it": "per cento"},
           "&": {"en": "and", "de": "und", "es": "y", "fr": "et", "it": "e"},
           "§": {"en": "section", "de": "Paragraf", "es": "párrafo", "fr": "paragraphe", "it": "paragrafo"}}
_KOMMA = {"en": "point", "de": "Komma", "es": "coma", "fr": "virgule", "it": "virgola"}
_RX_PROZ = re.compile(r"\s?%")
_RX_UND = re.compile(r"\s*&\s*")
_RX_PAR = re.compile(r"§+\s*")
_RX_ORD_EN = re.compile(r"\b(\d+)(st|nd|rd|th)\b")
_RX_ZEIT = re.compile(r"\b(\d{1,2}):(\d{2})\b")
_RX_TSD = {"en": re.compile(r"\b\d{1,3}(?:,\d{3})+\b"), "_": re.compile(r"\b\d{1,3}(?:\.\d{3})+\b")}
_RX_DEZ = re.compile(r"\b(\d+)[.,](\d+)\b")
_RX_BEREICH = re.compile(r"\b(\d{1,4})\s*[–-]\s*(\d{1,4})\b")
_RX_JAHR = re.compile(r"\b(1[1-9]\d\d|20\d\d)\b")
_RX_ZAHL = re.compile(r"\d+")
_RX_LEER = re.compile(r"[ \t]{2,}")


def _r_symbole(sp, lg, typ):
    w = {k: v.get(lg, v["en"]) for k, v in _SYMBOL.items()}
    return (sp.sub(_RX_PROZ, lambda m: " " + w["%"]).sub(_RX_UND, lambda m: f" {w['&']} ")
            .sub(_RX_PAR, lambda m: w["§"] + " "))


_MONATE = {
    "en": "January February March April May June July August September October November December",
    "de": "Januar Februar März April Mai Juni Juli August September Oktober November Dezember",
    "es": "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre",
    "fr": "janvier février mars avril mai juin juillet août septembre octobre novembre décembre",
    "it": "gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre novembre dicembre"}
_RX_DATUM = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")


def _r_datum(sp, lg, typ):
    """dd.mm.yyyy in allen Sprachen ausser de (de: Standardregel) -> Tag Monat Jahr."""
    if lg == "de":
        return sp

    def f(m):
        t, mo = int(m.group(1)), int(m.group(2))
        if not (0 < t < 32 and 0 < mo < 13):
            return None
        mon = _MONATE.get(lg, _MONATE["en"]).split()[mo - 1]
        if lg == "en":
            o = ordinalwort(t, "en")
            tag = f"the {o} of {mon}" if o else None
        elif lg == "fr":
            tag = f"{'premier' if t == 1 else zahlwort(t, 'fr')} {mon}"
        elif lg == "es":
            tag = f"{zahlwort(t, 'es')} de {mon} de"
        else:
            tag = f"{'primo' if t == 1 else zahlwort(t, lg)} {mon}"
        return [(m.start(1), m.end(2) + 1, tag + " ")] if tag and "None" not in tag else None
    return sp.sub(_RX_DATUM, f)


def _r_zahlen(sp, lg, typ):
    if lg == "en":
        sp.sub(_RX_ORD_EN, lambda m: ordinalwort(int(m.group(1)), "en"))

    def zeit(m):
        h, mi = int(m.group(1)), int(m.group(2))
        if h > 24 or mi > 59:
            return None
        hw, mw = zahlwort(h, lg), zahlwort(mi, lg)
        if not hw or not mw:
            return None
        if mi == 0:
            return hw + (" o'clock" if lg == "en" else "")
        return f"{hw} {'oh ' if lg == 'en' and mi < 10 else ''}{mw}"
    sp.sub(_RX_ZEIT, zeit)
    sp.sub(_RX_TSD["en" if lg == "en" else "_"], lambda m: zahlwort(int(re.sub(r"\D", "", m.group(0))), lg))

    def dez(m):
        a = zahlwort(int(m.group(1)), lg)
        b = [zahlwort(int(c), lg) for c in m.group(2)]
        if not a or not all(b):
            return None
        return f"{a} {_KOMMA.get(lg, 'point')} {' '.join(b)}"
    sp.sub(_RX_DEZ, dez)
    sp.sub(_RX_BEREICH, lambda m: [(m.end(1), m.start(2), f" {_BIS.get(lg, 'to')} ")])
    sp.sub(_RX_JAHR, lambda m: _n2w_sicher(int(m.group(1)), lg, "year"))
    sp.sub(_RX_ZAHL, lambda m: zahlwort(int(m.group(0)), lg) if len(m.group(0)) <= 9 else None)
    return sp.sub(_RX_LEER, lambda m: " ")


ERWEITERT = (_r_symbole, _r_datum, _r_zahlen)


# ============================================================ Oeffentlich
def sprechtext_abb(text, lg="de", typ=None, erweitert=False):
    """-> (sprechtext, abbildung [[s0, s1, l0, l1], ...])."""
    if not text:
        return text, []
    sp = _Spur(text)
    for r in STANDARD + (ERWEITERT if erweitert else ()):
        r(sp, lg, typ)
    return sp.t, sp.abbildung()


def sprechtext(text, lg="de", typ=None, erweitert=False):
    """Alle Sprechtext-Regeln in Reihenfolge (hier neue Regeln anhaengen)."""
    return sprechtext_abb(text, lg, typ, erweitert)[0]


def _einzeln(regel):
    def f(text, lg="de", typ="h"):
        return regel(_Spur(text), lg, typ).t if text else text
    return f


ueberschrift = _einzeln(_r_ueberschrift)
kursiv_weg = _einzeln(_r_kursiv)
jahresspannen = _einzeln(_r_spanne)


def ordinalzahlen(text, lg="de"):
    return _Spur(text).sub(_ORD, lambda m: [(m.start(2), m.end(2) + 1, ordinal_de(int(m.group(2)), m.group(1) or ""))]
                           if 0 < int(m.group(2)) < 100 else None).t if text and lg == "de" else text


def datum_uhrzeit(text, lg="de"):
    return _r_de(_Spur(text), lg, None).t if text else text


# ---- Pruefungen (Gate 400)
def roemisch_offen(s, ueberschrift_=False):
    """Unaufgeloeste roemische Zahlen: Ueberschrift jede (ausser Pronomen I), Fliesstext ab zwei Zeichen."""
    out = []
    for m in _ROEM_TOKEN.finditer(s or ""):
        tok = m.group(1)
        if not ist_roemisch(tok):
            continue
        if len(tok) >= 2:
            out.append(tok)
        elif ueberschrift_ and tok in ("V", "X"):
            nach = s[m.end():].strip()
            if not nach or nach[:1] in ".:-–—":
                out.append(tok)
        elif ueberschrift_ and tok == "I" and s[m.end():m.end() + 1] in (".", ":", ""):
            out.append(tok)
    return out


_RESTE = re.compile(r"[\d§&%]")


def reste(s):
    return _RESTE.findall(s or "")


if __name__ == "__main__":
    for t, lg, ty in [("IX. Der Nimmervogel", "de", "h"), ("CHAPTER IV", "en", "h"), ("Henry VIII was king.", "en", "s"),
                      ("Heinrich VIII. war König.", "de", "s"), ("Then I went home.", "en", "s"),
                      ("World War II ended in 1945 & 50% wept.", "en", "s")]:
        print(t, "->", sprechtext(t, lg, ty), "|", sprechtext(t, lg, ty, erweitert=True))
