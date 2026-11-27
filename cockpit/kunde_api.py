"""
READ LAYER — Kunden-API (AP Kunden-Cockpit, 23.11.2026)
=======================================================
Nur fuer Kundenrollen (verlag/autor). Liefert ausschliesslich gefilterte Daten (Whitelist je Feld):
keine Kosten/USD, keine Stage-Nummern, Modul-, Modell- oder Engine-Namen, keine Logs, keine Pfade.
Fremde Werke -> KeinZugriff (Server antwortet 404, verraet nicht, ob es das Werk gibt).

Routen (cockpit/server.py):  GET /api/kunde/ich | /api/kunde/werke | /api/kunde/werk/<id>
Ausbau (Folgepunkte):  Preise (pipeline/preis.py), Fortschritt (fortschritt.json), Freigaben, Downloads.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import bestellung, s080_mandant  # noqa: E402

SPRACHEN = {"de": "Deutsch", "en": "Englisch", "es": "Spanisch", "fr": "Französisch", "it": "Italienisch",
            "zh": "Chinesisch", "nl": "Niederländisch", "pt": "Portugiesisch", "pl": "Polnisch"}
INHALTE = {"text": "E-Book / Lesefassung", "hoerbuch": "Hörbuch", "hoerspiel": "Hörspiel", "hook": "Hook (Kurz-Teaser)"}
STUFEN = {"basic": "Standard", "premium": "Premium", "drama": "Inszeniert"}
ROLLEN = {"verlag": "Verlag", "autor": "Autor/in"}


class KeinZugriff(Exception):
    pass


def _sprache(lg):
    return SPRACHEN.get(lg, (lg or "").upper())


def ich(wer):
    reg = s080_mandant.register()
    e = (reg.get("nutzer") or {}).get(wer) or {}
    r = s080_mandant.rolle(wer, reg)
    return {"name": e.get("name") or wer, "rolle": ROLLEN.get(r, ""), "tarif": s080_mandant.tarif(wer, reg)}


def _alle_werke():
    from cockpit import werk_api            # erst hier: werk_api ist gross, Kunden-API soll ohne laufen koennen
    return werk_api.werke_liste()


def werke(wer):
    out = []
    for w in _alle_werke():
        if s080_mandant.eigenes_werk(w["book_id"], wer):
            out.append({"id": w["book_id"], "titel": w.get("titel") or "", "autor": w.get("autor") or ""})
    return {"werke": out}


def _produkte(b):
    out = []
    for p in b.produkte:
        name = INHALTE.get(p.get("inhalt"), "")
        if p.get("inhalt") != "text" and p.get("stufe") in STUFEN:
            name += f" ({STUFEN[p['stufe']]})"
        out.append({"sprache": _sprache(p.get("sprache")), "produkt": name})
    return out


def werk(book_id, wer):
    if not s080_mandant.eigenes_werk(book_id, wer):
        raise KeinZugriff(book_id)
    b = bestellung.lesen(book_id)
    titel = autor = ""
    for w in _alle_werke():
        if w["book_id"] == book_id:
            titel, autor = w.get("titel") or "", w.get("autor") or ""
            break
    return {"id": book_id, "titel": titel or b.roh.get("titel_original") or "", "autor": autor,
            "originalsprache": _sprache(b.quellsprache), "produkte": _produkte(b)}
