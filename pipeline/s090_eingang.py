"""STAGE 090 — Eingangsweiche (neu; GATE_KATALOG.md, 01.11.2026)
Funktion:     Legt die Eingangsart (`quelle`) in book.json fest und leitet weiter:
              gutenberg / user_txt -> 100 · user_epub / verlag_epub -> 150 · fremd_audio -> geparkt (Stopp).
Gate:         Eingangsart gesetzt; Gutenberg-ID gueltig; ePub: Rechte-Versicherung (art + wer/wann),
              DRM-frei, verlag_epub nur bei Mandant verlag:<id>. Erfuellt -> auto; sonst Stopp
              (Ruecksprung 090). fremd_audio -> immer Stopp (loses Ende, FA bei Fremd-Audio ungeloest).
Regler:       --quelle, --gutenberg-id, --versichern ART (setzt rechte.versichert wer/wann),
              --bearbeitung ja|nein, --ziel de,fr (Wunsch fuer 095 -> book.json wunsch.zielsprachen),
              --epub DATEI (DRM-Pruefung an der Datei).
Book-ID:      = Werkordner; geprueft (Kleinbuchstaben/Ziffern/-, book_slug = Ordner), nicht umbenannt.
Befund 090:   LibriVox-Altfelder (audio_quelle librivox/thorsten) -> nur Hinweis, wirkungslos.
Kosten:       0 $ (kein LLM).

Aufruf:
  python -m pipeline.s090_eingang <werk> [--quelle user_epub] [--versichern eigene] [--wer CK]
Exit: 0 auto, 2 Stopp.
"""
import argparse
import datetime
import os
import re
import sys

from pipeline import bestellung, gate, s080_mandant

STAGE = "090"
QUELLEN = bestellung.QUELLEN
WEITER = {"gutenberg": "100", "user_txt": "100", "user_epub": "150", "verlag_epub": "150", "fremd_audio": None}
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def eingangsart(roh):
    """Gesetzte oder abgeleitete Eingangsart (Altwerke ohne `quelle`)."""
    q = (roh.get("quelle") or "").strip().lower()
    if q:
        return q, False
    if roh.get("herkunft") in ("privat_upload", "eigenwerk", "epub", "user_epub") or roh.get("quelle_epub"):
        return "user_epub", True
    return "gutenberg", True


def _gid(v):
    try:
        return int(str(v).strip()) if str(v).strip() else None
    except ValueError:
        return None


def drm_pruefen(pfad):
    """(ok, text) – DRM-Pruefung wie 150 (encryption.xml/LCP)."""
    from pipeline import s150_epub_import as s150
    try:
        z, _ = s150.oeffnen(pfad)
        z.close()
        return True, f"{os.path.basename(pfad)}: DRM-frei"
    except s150.EpubFehler as e:
        return False, f"{os.path.basename(pfad)}: {e}"


def _epub_datei(ordner, roh, epub):
    if epub:
        return epub
    d = (roh.get("quelle_epub") or {}).get("datei")
    if d:
        for p in (os.path.join(ordner, d), os.path.join(ordner, "quelle", d)):
            if os.path.exists(p):
                return p
    return None


def pruefen(g, werk, ordner, roh, b, epub=None):
    """Alle Pruefungen 090 auf Gate g. Rueckgabe Eingangsart."""
    q, abgeleitet = eingangsart(roh)
    g.pflicht("eingangsart", q in QUELLEN, wert=q, ruecksprung="090",
              text=f"Eingangsart {q!r}" + (" (abgeleitet)" if abgeleitet else ""))
    g.metrik("eingangsart", q)
    g.metrik("weiter", WEITER.get(q) or "geparkt")

    bid = os.path.basename(os.path.normpath(werk))
    g.pflicht("book_id", bool(SLUG.match(bid)), wert=bid, ruecksprung="090",
              text=f"Book-ID {bid!r} (Kleinbuchstaben, Ziffern, -)")
    slug = roh.get("book_slug")
    od = os.path.basename(os.path.normpath(ordner))
    g.hinweis("book_slug", (not slug or slug == bid) and od == bid, wert=slug,
              text=f"Book-ID {bid!r} / book_slug {slug!r} / Ordner {od!r}")

    if q == "fremd_audio":
        g.pflicht("fremd_audio", False, wert=q, ruecksprung="090",
                  text="fremd_audio geparkt (FA bei Fremd-Audio ungeloest, Test LibriVox Call of the Wild)")
    elif q == "gutenberg":
        gid = _gid(roh.get("gutenberg_id"))
        g.pflicht("gutenberg_id", bool(gid and gid > 0), wert=roh.get("gutenberg_id"), ruecksprung="090",
                  text=f"Gutenberg-ID {roh.get('gutenberg_id')!r}")
    elif q == "user_txt":
        tq = roh.get("textquelle") or {}
        g.pflicht("textquelle", tq.get("art") == "datei" and bool(tq.get("quelle")), wert=tq, ruecksprung="090",
                  text=f"mitgebrachte TXT {tq.get('quelle')!r}" if tq.get("quelle") else "TXT-Quelle fehlt")
    elif q in ("user_epub", "verlag_epub"):
        r = b.rechte
        v = r.get("versichert") if isinstance(r.get("versichert"), dict) else None
        g.pflicht("rechte_art", r.get("art") in bestellung.RECHTE_ARTEN, wert=r.get("art"), ruecksprung="090",
                  text=f"Rechteart {r.get('art')!r}")
        g.pflicht("rechte_versichert", bool(v and v.get("wer") and v.get("wann")), wert=v, ruecksprung="090",
                  text="Rechte-Versicherung (wer/wann) " + ("vorhanden" if v else "fehlt"))
        pfad = _epub_datei(ordner, roh, epub)
        if pfad:
            ok, t = drm_pruefen(pfad)
            g.pflicht("drm_frei", ok, wert=t, ruecksprung="090", text=t)
        elif roh.get("quelle_epub"):
            g.pflicht("drm_frei", True, wert="150-Import", text="DRM-frei (bereits durch 150 eingelesen)")
        else:
            g.pflicht("drm_frei", r.get("drm_frei") is True, wert=r.get("drm_frei"), ruecksprung="090",
                      text="DRM-Status " + ("versichert" if r.get("drm_frei") else "unbekannt (keine ePub-Datei)"))
        if q == "verlag_epub":
            g.pflicht("mandant_verlag", b.mandant_art == "verlag", wert=b.mandant, ruecksprung="080",
                      text=f"verlag_epub braucht Mandant verlag:<id> (ist {b.mandant})")

    aq = str(roh.get("audio_quelle") or "")
    g.hinweis("librivox_altfeld", not aq.startswith(("librivox", "thorsten")), wert=aq,
              text=f"LibriVox/Thorsten-Altfeld audio_quelle {aq!r}" + (" ignoriert" if aq else ""))
    w = (roh.get("wunsch") or {}).get("zielsprachen")
    if w:
        g.metrik("wunsch_zielsprachen", w)
    return q


def run(werk, wer=None, quelle=None, gutenberg_id=None, versichern=None, bearbeitung=None, ziel=None,
        epub=None):
    """Gate 090. Regler schreiben vor der Pruefung in book.json. Rueckgabe auto | stopp."""
    wer = s080_mandant.nutzer(wer)
    ordner = bestellung.werkordner(werk)
    felder = {}
    if quelle:
        if quelle not in QUELLEN:
            raise ValueError(f"--quelle {quelle!r} ungueltig, erlaubt {QUELLEN}")
        felder["quelle"] = quelle
    if versichern or bearbeitung is not None:
        b0 = bestellung.lesen(werk)
        r = dict(b0.rechte)
        if versichern:
            r["art"] = versichern
            r["versichert"] = {"wer": wer, "wann": datetime.datetime.now().isoformat(timespec="seconds")}
        if bearbeitung is not None:
            r["bearbeitung"] = bearbeitung
        felder["rechte"] = r
    if ziel is not None:
        b0 = bestellung.lesen(werk)
        zs = [z.strip().lower() for z in ziel if z.strip()]
        falsch = [z for z in zs if z not in bestellung.sprachliste() or z == b0.quellsprache]
        if falsch:
            raise ValueError(f"--ziel {falsch}: nicht in Sprachliste oder = Quellsprache {b0.quellsprache}")
        felder["wunsch"] = dict(b0.roh.get("wunsch") or {}, zielsprachen=zs)
    if felder or gutenberg_id is not None:
        s080_mandant.darf(werk, "bestellen", wer)
    if felder:
        bestellung.schreiben(werk, **felder)
    if gutenberg_id is not None:
        bestellung.feld_setzen(werk, gutenberg_id=int(gutenberg_id))

    b = bestellung.lesen(werk)
    g = gate.Gate(werk, STAGE, ruecksprung="090", wer=wer)
    q = pruefen(g, werk, ordner, b.roh, b, epub)
    e = g.entscheide()
    if e == "auto":
        # abgeleitete Eingangsart und Rechte festschreiben (09.11.2026: Altwerke ohne rechte liefen sonst
        # in die Schleife 190 "rechte abgeleitet" -> Ruecksprung 090 -> 090 frei, schreibt nichts)
        fest = {} if b.roh.get("quelle") else {"quelle": q}
        if "rechte" in b.abgeleitet:
            fest["rechte"] = b.rechte
        if fest:
            bestellung.schreiben(werk, **fest)
    print(g.bericht())
    if e == "auto":
        print(f"[090] {q} -> weiter mit {WEITER[q]}")
    return e


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 090 Eingangsweiche")
    ap.add_argument("werk")
    ap.add_argument("--wer")
    ap.add_argument("--quelle", choices=QUELLEN)
    ap.add_argument("--gutenberg-id")
    ap.add_argument("--versichern", choices=bestellung.RECHTE_ARTEN, metavar="ART",
                    help="Rechte-Versicherung setzen (gemeinfrei/eigene/lizenz/verlag)")
    ap.add_argument("--bearbeitung", choices=("ja", "nein"))
    ap.add_argument("--ziel", help="Zielsprachen-Wunsch fuer 095, z. B. de,fr")
    ap.add_argument("--epub", help="ePub-Datei fuer die DRM-Pruefung")
    a = ap.parse_args(argv)
    e = run(a.werk, a.wer, a.quelle, a.gutenberg_id, a.versichern,
            None if a.bearbeitung is None else a.bearbeitung == "ja",
            a.ziel.split(",") if a.ziel is not None else None, a.epub)
    return gate.EXIT[e]


if __name__ == "__main__":
    sys.exit(main())
