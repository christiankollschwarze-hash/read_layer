"""READ LAYER - Sprechtext-Regeln (nur fuer die Vertonung; Text/EPUB/Mock-up bleiben unveraendert). 18.10.2026
Regel 1 (CK): Kapitelnummern in roemischen Ziffern am Anfang einer Ueberschrift (type "h") werden als Zahlwort gesprochen:
  "IX. Der Nimmervogel" -> "Neun. Der Nimmervogel" (de) / "Nine. The Never Bird" (en).
Regel 2 (CK 19.10.2026): Ordinalzahlen vor Zeit-/Zaehlwoertern ausschreiben ("19. Jahrhunderts" -> "neunzehnten Jahrhunderts").
Regel 4-7 (22.10.2026, AP4 Spiegelschwestern): Kursiv-Marken _..._/*...* weg (alle Sprachen); DE: Datumsspanne
  "28.–31. August" -> "achtundzwanzigsten bis einunddreissigsten August", Datum "16.08.2007" -> "sechzehnten achten 2007",
  Uhrzeit "7:15 Uhr" -> "sieben Uhr fünfzehn", "ca." -> "circa".
Genutzt von tools/tts_paket.py (Chatterbox) und pipeline/s500_vertonung_gemini.py (Gemini)."""
import re

_ROEM = re.compile(r"^\s*([IVXLC]+)\.(\s+|$)")
_W = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
_DE = "null eins zwei drei vier fünf sechs sieben acht neun zehn elf zwölf dreizehn vierzehn fünfzehn sechzehn siebzehn achtzehn neunzehn".split()
_DE10 = {2: "zwanzig", 3: "dreißig", 4: "vierzig", 5: "fünfzig", 6: "sechzig", 7: "siebzig", 8: "achtzig", 9: "neunzig"}
_EN = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_EN10 = {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty", 6: "sixty", 7: "seventy", 8: "eighty", 9: "ninety"}


def roemisch_zu_int(s):
    n, vor = 0, 0
    for c in reversed(s):
        v = _W[c]
        n += -v if v < vor else v
        vor = max(vor, v)
    return n


def zahlwort(n, lg="de"):
    if n == 100:
        return "hundert" if lg == "de" else "one hundred"
    if n < 20:
        return (_DE if lg == "de" else _EN)[n]
    z, e = divmod(n, 10)
    if lg == "de":
        return _DE10[z] if not e else ("ein" if e == 1 else _DE[e]) + "und" + _DE10[z]
    return _EN10[z] + ("" if not e else "-" + _EN[e])


def ueberschrift(text, lg="de", typ="h"):
    """Roemische Kapitelnummer am Anfang einer Ueberschrift -> Zahlwort (gross geschrieben)."""
    if typ != "h" or not text:
        return text
    m = _ROEM.match(text)
    if not m:
        return text
    n = roemisch_zu_int(m.group(1))
    if not 0 < n <= 100:
        return text
    w = zahlwort(n, "de" if lg == "de" else "en")
    return (w[0].upper() + w[1:]) + "." + m.group(2) + text[m.end():]


# Regel 2 (CK 19.10.2026): Ordinalzahl vor Zeit-/Zaehlwort ausschreiben (DE):
#   "des 19. Jahrhunderts" -> "des neunzehnten Jahrhunderts", "das 19. Jahrhundert" -> "das neunzehnte Jahrhundert",
#   "am 4. Juli" -> "am vierten Juli". Sonst sprach Chatterbox "neunzehn Jahrhunderts".
_ORD_NOMEN = (r"Jahrhundert|Jahrtausend|Jahrzehnt|Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|"
              r"November|Dezember|Geburtstag|Lebensjahr|Kapitel|Akt|Szene|Auflage|Band|Mal|Stock|Stockwerk|Platz|Tag|Woche|Monat")
_ORD = re.compile(r"(?:(\w+)\s+)?\b(\d{1,2})\.\s+(?=(?:" + _ORD_NOMEN + r")\w*\b)")
_ORD_SONDER = {1: "erst", 3: "dritt", 7: "siebt", 8: "acht"}
_ORD_STARK = {"der", "die", "das", "ins", "aufs", "fürs", "durchs", "ans"}


def ordinal_de(n, artikel=""):
    stamm = _ORD_SONDER.get(n) or (zahlwort(n, "de") + ("t" if n < 20 else "st"))
    return stamm + ("e" if artikel.lower() in _ORD_STARK else "en")


def ordinalzahlen(text, lg="de"):
    if lg != "de" or not text:
        return text

    def ers(m):
        n = int(m.group(2))
        if not 0 < n < 100:
            return m.group(0)
        vor = m.group(1) or ""
        return (vor + " " if vor else "") + ordinal_de(n, vor) + " "
    return _ORD.sub(ers, text)


# Regel 3 (19.10.2026): Jahresspanne "1860-1935" / "1876–1916" -> "1860 bis 1935" (en: "to"), sonst "minus".
_SPANNE = re.compile(r"\b(\d{3,4})\s*[-–]\s*(\d{3,4})\b")


def jahresspannen(text, lg="de"):
    return _SPANNE.sub(lambda m: f"{m.group(1)} {'bis' if lg == 'de' else 'to'} {m.group(2)}", text) if text else text


# Regel 4 (22.10.2026): Markdown-Kursiv/-Fett aus dem Import (_SMS-Text_, *Wort*) nicht mitsprechen.
_KURSIV = re.compile(r"(?<![\w])[_*]+|[_*]+(?![\w])")


def kursiv_weg(text, lg="de"):
    return _KURSIV.sub("", text) if text else text


# Regel 5 (22.10.2026, DE): Datumsspanne "28.–31. August" / "6.-7. November" -> "... bis ..."
_DAT_SPANNE = re.compile(r"\b(\d{1,2})\.\s*[–-]\s*(\d{1,2})\.\s+(?=(?:" + _ORD_NOMEN + r")\w*\b)")
# Regel 6 (DE): Datum "16.08.2007" -> "sechzehnten achten 2007"
_DATUM = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
# Regel 7 (DE): Uhrzeit "7:15 Uhr" -> "sieben Uhr fünfzehn", "10:00 Uhr" -> "zehn Uhr"
_UHR = re.compile(r"\b(\d{1,2}):(\d{2})\s*Uhr\b")


def datum_uhrzeit(text, lg="de"):
    if lg != "de" or not text:
        return text

    def spanne(m):
        a, b = int(m.group(1)), int(m.group(2))
        if not (0 < a < 32 and 0 < b < 32):
            return m.group(0)
        return f"{ordinal_de(a)} bis {ordinal_de(b)} "

    def datum(m):
        t, mo = int(m.group(1)), int(m.group(2))
        if not (0 < t < 32 and 0 < mo < 13):
            return m.group(0)
        return f"{ordinal_de(t)} {ordinal_de(mo)} {m.group(3)}"

    def uhr(m):
        h, mi = int(m.group(1)), int(m.group(2))
        if h > 24 or mi > 59:
            return m.group(0)
        hw = "ein" if h == 1 else zahlwort(h, "de")
        return f"{hw} Uhr" + (f" {zahlwort(mi, 'de')}" if mi else "")

    text = _DAT_SPANNE.sub(spanne, text)
    text = _DATUM.sub(datum, text)
    text = _UHR.sub(uhr, text)
    return re.sub(r"\bca\.", "circa", text)


def sprechtext(text, lg="de", typ=None):
    """Alle Sprechtext-Regeln in Reihenfolge (hier neue Regeln anhaengen)."""
    text = datum_uhrzeit(kursiv_weg(ueberschrift(text, lg, typ), lg), lg)
    return jahresspannen(ordinalzahlen(text, lg), lg)


if __name__ == "__main__":
    for t in ["I. Peter bricht durch", "IX. Der Nimmervogel", "XXIV. Test", "Ich. Kein Kapitel", "XVII."]:
        print(t, "->", ueberschrift(t, "de"), "|", ueberschrift(t, "en"))
