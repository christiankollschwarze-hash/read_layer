"""
READ LAYER — Excel -> Anlege-Eingabe (Weg A)
============================================
Verheiratet die ZWEI gemeinsam erarbeiteten Listen ueber die Gutenberg-ID:
  - ReadLayer_angereichert_DE.xlsx : geprueft/kuratiert (EU-frei, Status, Titel,
       Autor, Todesjahr, Lesbarkeit) -> WELCHE Titel.
  - ReadLayer_Titelauswahl_DE.xlsx : enthaelt txt_url -> WOHER der Rohtext.

Erzeugt daraus die Eingabe-Struktur fuer das Anlegen (book_slug, autor_name,
originalsprache, gutenberg_id, txt_url ...). Optional gleich anlegen + Rohtext laden.

WIKIDATA bleibt GETRENNT (Weg A): Q-IDs bleiben leer, Stage 08b fuellt sie spaeter.

AUFRUF (aus dem Projekt-Wurzelverzeichnis):
  # nur Vorschau, was zusammengefuehrt wuerde:
  python aus_excel.py --angereichert ReadLayer_angereichert_DE.xlsx \
                      --auswahl ReadLayer_Titelauswahl_DE.xlsx --dry

  # Eingabe-JSON erzeugen (dann mit anlegen.py weiterverarbeiten):
  python aus_excel.py --angereichert ... --auswahl ... --out new_books.json

  # nur "gruene" + EU-frei uebernehmen (empfohlen):
  python aus_excel.py ... --out new_books.json --nur-gruen

Hinweise:
  - Autor "Nachname, Vorname" wird zu "Vorname Nachname" gedreht (fuer Slug).
  - book_slug = englischer Slug? Gutenberg-Titel ist hier DEUTSCH -> wir slugifizieren
    den vorhandenen Titel. (Bei nicht-englischen Originalen ggf. spaeter haendisch
    den englischen Slug setzen -- siehe Datenmodell. Vorerst: Titel-Slug.)
"""

import sys, os, json, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config

def _load_xlsx(path, header_row):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    hdr = list(rows[header_row - 1])
    out = []
    for r in rows[header_row:]:
        out.append(dict(zip(hdr, r)))
    return out

def _flip_name(name):
    """'Freud, Sigmund' -> 'Sigmund Freud'. Ohne Komma unveraendert.
    Hinweis: Adelstitel ('Joseph, Freiherr von Eichendorff') werden NICHT
    automatisch korrekt -- solche Faelle per autor_slug haendisch ueberschreiben."""
    if name and "," in name:
        nach, vor = name.split(",", 1)
        return f"{vor.strip()} {nach.strip()}".strip()
    return (name or "").strip()

def _clean_title(title):
    """Entfernt MARC-Katalogcodes aus Gutenberg-Titeln.
    'Dr. Mabuse, der Spieler : $b Roman' -> 'Dr. Mabuse, der Spieler. Roman'"""
    import re
    t = title or ""
    t = re.sub(r"\s*:\s*\$[a-z]\s*", ". ", t)   # ': $b Untertitel' -> '. Untertitel'
    t = re.sub(r"\s*\$[a-z]\s*", " ", t)         # verbleibende $x-Codes raus
    t = re.sub(r"\.\s*\.", ".", t)
    t = re.sub(r"\s+", " ", t).strip().rstrip(".")
    return t

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--angereichert", required=True)
    ap.add_argument("--auswahl", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--nur-gruen", action="store_true",
                    help="nur Status=gruen UND EU-frei=JA uebernehmen")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    angereichert = _load_xlsx(args.angereichert, header_row=1)
    auswahl      = _load_xlsx(args.auswahl, header_row=2)  # Header in Zeile 2

    # url-Map aus der Auswahl: id -> txt_url (+ sprache)
    url_by_id = {}
    for d in auswahl:
        gid = str(d.get("id") or "").strip()
        if gid:
            url_by_id[gid] = {"txt_url": d.get("txt_url") or "",
                              "language": d.get("language") or "de"}

    books = []
    skipped = 0
    for d in angereichert:
        gid = str(d.get("id") or "").strip()
        if not gid:
            continue
        if args.nur_gruen:
            if (d.get("Status") != "gruen") or (d.get("EU-frei") != "JA"):
                skipped += 1
                continue
        titel = _clean_title(d.get("Titel"))
        autor = _flip_name(d.get("Autor"))
        match = url_by_id.get(gid, {})
        books.append({
            "titel_original": titel,
            "book_slug": config.slugify(titel),
            "autor_name": autor,
            "autor_slug": "",
            "wikidata_id_autor": "",
            "wikidata_id_werk": "",
            "originalsprache": match.get("language", "de"),
            "erscheinungsjahr": None,
            "gutenberg_id": gid,
            "todesjahr_autor": d.get("†"),          # aus angereichert (fuer spaeter)
            "txt_url": match.get("txt_url", ""),     # Rohtext-Quelle (Download lokal)
            "raw_quelle": ""                          # bleibt leer -> Download via txt_url
        })

    print(f"Zusammengefuehrt: {len(books)} Buecher"
          + (f" (uebersprungen: {skipped} nicht-gruen/nicht-EU-frei)" if args.nur_gruen else ""))
    # Vorschau
    for b in books[:8]:
        has_url = "URL" if b["txt_url"] else "kein-URL"
        print(f"  [{b['gutenberg_id']:>6}] {b['autor_name']:<22} | {b['titel_original'][:40]:<40} | {has_url}")
    if len(books) > 8:
        print(f"  ... und {len(books)-8} weitere")

    # ohne URL?
    ohne = [b for b in books if not b["txt_url"]]
    if ohne:
        print(f"\n  ! {len(ohne)} Buecher OHNE txt_url (nicht in Auswahl-Liste gematcht):")
        for b in ohne[:5]:
            print(f"      id={b['gutenberg_id']} {b['titel_original'][:40]}")

    if args.dry:
        print("\n(DRY: nichts geschrieben)")
        return
    if args.out:
        json.dump({"books": books}, open(args.out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print(f"\n-> Eingabe-JSON geschrieben: {args.out}")
        print(f"   Weiter mit:  python anlegen.py {args.out} --dry")

if __name__ == "__main__":
    main()
