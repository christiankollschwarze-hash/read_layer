"""STAGE 190 — Eingangsvertrag (neu, QP-4; GATE_KATALOG.md Zeile 190, 01.11.2026)
Funktion:     Prueft vor der Textkette (195/200 ff.), ob der Eingang vollstaendig und in sich stimmig ist.
              Beide Wege (Gutenberg ueber 100–120, User-ePub ueber 150/115/120). Schreibt nichts ausser status.json.
Eingang:      raw_modernized.txt (###TITLE/AUTHOR/CHAPTER###), work/modernized/chapter-N.json,
              book.json (quelle, fassung, produkte/zielsprachen, mandant, rechte), author.json bzw. book.json autor_name,
              status.json (Gates 090–120, Kapitelzahl aus Gate 120).
Gate (alles Pflicht, sonst Stopp):
              Vorstufen 090, 095, 100, 110, 150, 115, 120 frei oder entfaellt (kein Mock-Ergebnis im Live-Lauf);
              book.json vollstaendig und gueltig (keine abgeleiteten Pflichtfelder, bestellung.fehler() leer);
              Autor vorhanden; raw_modernized.txt mit TITLE/AUTHOR-Kopf, AUTHOR = Autor;
              chapter-N.json lueckenlos 1..N, je Kapitel Absaetze (Titel ausser bei nur einem Kapitel), keine offenen Luecken (fehlend);
              Kapitelzahl Marken = Checkpoints = Gate 120;
              Textabgleich raw_modernized <-> Summe Checkpoints (Woerter inkl. Kapiteltitel) <= 1 %;
              keine Mock-Texte im Live-Lauf.
              alles gruen -> auto; sonst Stopp mit Ruecksprung auf die Stage, deren Datei fehlt.
Kosten:       0 $ (kein LLM).
Regler:       keine (Freigabe eines Stopps nur per Admin-Override: python -m pipeline.status ... --override 190).
Aufruf:
  python -m pipeline.s190_vertrag <werk> [--wer CK]
Exit: 0 auto, 2 Stopp.
"""
import argparse
import difflib
import json
import os
import re
import sys

from config import config
from pipeline import bestellung, gate, manifest, mock, s090_eingang, status

STAGE = "190"
VORSTUFEN = ("090", "095", "100", "110", "150", "115", "120")
TEXT_MAX = 0.01
HR = "——HR——"
# abgeleitetes Pflichtfeld -> Stage, die es schreibt
FELD_STAGE = {"fassung": "115", "produkte": "095", "mandant": "080", "rechte": "090"}


def _lesen(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _woerter(text):
    return [w for w in text.split() if not (w.startswith("###") and w.endswith("###"))]


def marken_lesen(text):
    """raw_modernized.txt -> (titel, autor, [(kapiteltitel, koerper)])."""
    M = config.MARKERS
    titel = autor = None
    kap, aktuell = [], None
    for z in text.replace("\r", "").split("\n"):
        if z.startswith(M["title"]) and titel is None and aktuell is None:
            titel = z[len(M["title"]):].strip()
        elif z.startswith(M["author"]) and autor is None and aktuell is None:
            autor = z[len(M["author"]):].strip()
        elif z.startswith(M["chapter"]):
            aktuell = [z[len(M["chapter"]):].strip(), []]
            kap.append(aktuell)
        elif aktuell is not None:
            aktuell[1].append(z)
    return titel, autor, [(t, "\n".join(k)) for t, k in kap]


def checkpoints(werk):
    """-> (liste [(n, dict)], nummern-fehler). Nur chapter-N.json (ohne .original)."""
    d = os.path.join(config.work_dir(werk), "modernized")
    if not os.path.isdir(d):
        return [], []
    nr = sorted(int(m.group(1)) for f in os.listdir(d) if (m := re.fullmatch(r"chapter-(\d+)\.json", f)))
    luecken = [n for n in range(1, (nr[-1] if nr else 0) + 1) if n not in nr]
    return [(n, _lesen(os.path.join(d, f"chapter-{n}.json"))) for n in nr], luecken


def abweichung(marken, cps):
    """Anteil abweichender Woerter (Titel + Text je Kapitel) zwischen Marken-Text und Checkpoints."""
    diff = gesamt = 0
    for i in range(max(len(marken), len(cps))):
        a = b = []
        if i < len(marken):
            a = _woerter(marken[i][0]) + _woerter(marken[i][1])
        if i < len(cps):
            d = cps[i][1]
            b = _woerter(d.get("title") or "") + _woerter(
                "\n".join(p for p in (d.get("paragraphs") or []) if p and p != HR))
        n = max(len(a), len(b))
        gesamt += n
        if a != b:
            gleich = sum(m.size for m in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks())
            diff += n - gleich
    return (diff / gesamt if gesamt else 1.0), gesamt


def autor_soll(werk, art, roh):
    if art != "user_epub":
        try:
            ap = os.path.join(config.author_dir(config.author_of(werk)), "author.json")
            n = _lesen(ap).get("name_display") or ""
            if n:
                return n, "author.json"
        except Exception:
            pass
    return (roh.get("autor_name") or "").strip(), "book.json"


def kapitel_120(werk, d):
    st = d["stages"].get("120") or {}
    n = (st.get("metriken") or {}).get("kapitel")
    if n is None:
        p = os.path.join(config.work_dir(werk), "120_kapitel.json")
        if os.path.exists(p):
            n = _lesen(p).get("kapitel")
    return n


def run(werk, wer=None, trocken=False):
    """trocken: nur pruefen, status.json bleibt unberuehrt (Cockpit-Monitor 190)."""
    wer = wer or "pipeline"
    g = gate.Gate(werk, STAGE, ruecksprung="120", wer=wer)
    d = status.laden(werk)

    # Vorstufen
    for s in VORSTUFEN:
        z = status.zustand(werk, s, d=d)
        g.pflicht(f"gate_{s}", z in status.FREI, wert=z, ruecksprung=s, text=f"Gate {s} = {z}")
        if not mock.aktiv() and ((d["stages"].get(s) or {}).get("metriken") or {}).get("modus") == "mock":
            g.pflicht(f"gate_{s}_mock", False, ruecksprung=s, text=f"Gate {s} im Mock-Lauf erzeugt")

    # book.json
    ordner = config.book_dir(werk)
    bp = os.path.join(ordner, "book.json")
    if not g.pflicht("book_json", os.path.exists(bp), ruecksprung="090", text="book.json vorhanden"):
        g.entscheide(schreiben=not trocken)
        return g
    b = bestellung.lesen(werk)
    art, art_abg = s090_eingang.eingangsart(b.roh)
    g.metrik("quelle", art)
    g.pflicht("quelle", not art_abg, wert=art, ruecksprung="090",
              text=f"book.json quelle = {b.roh.get('quelle')!r}")
    for feld in ("fassung", "produkte", "mandant", "rechte"):
        g.pflicht(f"feld_{feld}", feld not in b.abgeleitet, ruecksprung=FELD_STAGE[feld],
                  text=f"book.json {feld} " + ("abgeleitet (nicht gesetzt)" if feld in b.abgeleitet else "gesetzt"))
    fe = b.fehler()
    g.pflicht("bestellung", not fe, wert=len(fe), ruecksprung="095",
              text="Bestellung gueltig" + (": " + "; ".join(fe) if fe else ""))
    g.metrik("fassung", b.fassung)
    g.metrik("zielsprachen", b.zielsprachen)
    g.metrik("mandant", b.mandant)

    # Autor
    autor, autor_q = autor_soll(werk, art, b.roh)
    g.pflicht("autor", bool(autor), wert=autor_q, ruecksprung="150" if art == "user_epub" else "100",
              text=f"Autor ({autor_q}) " + (repr(autor) if autor else "fehlt"))

    # raw_modernized.txt
    rp = os.path.join(ordner, "raw_modernized.txt")
    if not g.pflicht("raw_modernized", os.path.exists(rp), text="raw_modernized.txt vorhanden"):
        g.entscheide(schreiben=not trocken)
        return g
    with open(rp, encoding="utf-8") as f:
        text = f.read()
    g.metrik("quelle_hash", manifest.hash_obj(text))
    titel, m_autor, marken = marken_lesen(text)
    g.pflicht("marke_titel", bool(titel), text=f"###TITLE### {titel!r}")
    g.pflicht("marke_autor", m_autor is not None and (not autor or m_autor == autor),
              text=f"###AUTHOR### {m_autor!r}" + (f" (Soll {autor!r})" if autor and m_autor != autor else ""))
    n_marken = len(marken)

    # Checkpoints
    cps, luecken = checkpoints(werk)
    n_cp = len(cps)
    g.pflicht("checkpoints", n_cp > 0 and not luecken, wert=n_cp,
              text=f"chapter-N.json {n_cp}" + (f", Luecken {luecken[:10]}" if luecken else ""))
    # Titel Pflicht ausser bei Einkapitelwerken (Kurzgeschichten ohne Kapitelueberschrift)
    leer = [n for n, c in cps if (n_cp > 1 and not (c.get("title") or "").strip())
            or not [p for p in (c.get("paragraphs") or []) if p and p != HR]]
    g.pflicht("checkpoint_inhalt", not leer, wert=len(leer),
              text="Kapitel mit Titel und Absaetzen" + (f" – leer/ohne Titel: {leer[:10]}" if leer else ""))
    offen = [n for n, c in cps if c.get("fehlend")]
    g.pflicht("checkpoint_fehlend", not offen, wert=len(offen),
              text="keine offenen Absatzluecken" + (f" – Kapitel {offen[:10]}" if offen else ""))

    # Kapitelzahl
    n_120 = kapitel_120(werk, d)
    g.metrik("kapitel", n_cp)
    g.pflicht("kapitelzahl", n_marken == n_cp == n_120,
              wert=f"{n_marken}/{n_cp}/{n_120}",
              text=f"Kapitel Marken {n_marken} = Checkpoints {n_cp} = Gate 120 {n_120}")

    # Textabgleich
    abw, woerter = abweichung(marken, cps)
    g.metrik("woerter", woerter)
    g.metrik("zeichen", len(text))
    g.pruefe("textabweichung", abw <= TEXT_MAX, round(abw, 4), f"<= {TEXT_MAX}", "stopp", "120",
             text=f"Textabweichung raw_modernized <-> Checkpoints {abw:.2%} (Soll <= {TEXT_MAX:.0%})")

    # Mock
    n_mock = text.count("[MOCK")
    g.mock(n_mock, ruecksprung="120")

    g.entscheide(schreiben=not trocken)
    return g


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 190 Eingangsvertrag")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    a = ap.parse_args(argv)
    try:
        g = run(a.werk, a.wer)
    except gate.GateHalt as e:
        print(e)
        return e.exit_code
    print(g.bericht())
    return gate.EXIT[g.ergebnis["ergebnis"]]


if __name__ == "__main__":
    sys.exit(main())
