"""STAGE 320 — Integritaet
Funktion:     Mechanische Strukturpruefung der Uebersetzung.
Wirkungsweise: Prueft fehlende/leere Sprachen, Tag-ID-Form und Sequenz; Bericht in meta.integrity_report. s330 stoppt bei Fehlern.
Komponenten:  pipeline/s320_integritaet.py
Zulieferer:   s310 Uebersetzung (work/310_uebersetzung.json)
Abnehmer:     s330 Rueckuebersetzung (work/320_integritaet.json)
(Nomenklatur seit 18.10.2026, Uebersicht: docs/Pipeline_Strang_Matrix.xlsx)

--- Bisherige Beschreibung ---

READ LAYER — Stage 54 (Integrity Check)
=======================================
Input:  authors/<autor>/books/<book>/work/310_uebersetzung.json
Output: authors/<autor>/books/<book>/work/320_integritaet.json   (unveraendert durchgereicht)
        + Report auf stdout

Rein MECHANISCH, keine API, keine Kosten. Laeuft IMMER.
Trennt strukturelle Fehler von Qualitaetsfragen (die kommen in 04b).

Prueft:
  1. Vollstaendigkeit  - hat jeder uebersetzbare Tag alle Zielsprachen?
  2. Leere Felder      - ist eine Uebersetzung leer, obwohl Quelle Text hat?
  3. Sequenz-Lueckenlosigkeit - sind die Sequenznummern pro Kapitel lueckenlos?
  4. Tag-ID-Form       - entspricht jede ID dem Schema c<NNN>_<prefix><NNNNN>?
"""

import sys
import os
import json
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config


def _is_translatable(entry: dict) -> bool:
    return entry.get("type") not in config.NO_AUDIO_TYPES


def _tag_pattern():
    cd, sd = config.CHAPTER_DIGITS, config.SEQUENCE_DIGITS
    # NEUES Schema: c<NNN>_<NNNNN>_<typ>  (Kapitel _ globale Sequenz _ Typ-Suffix)
    # Typ = 1-4 Kleinbuchstaben am Ende.
    return re.compile(rf"^c\d{{{cd}}}_\d{{{sd}}}_[a-z]{{1,4}}$")


def check(data: dict) -> dict:
    """Fuehrt alle Pruefungen aus und gibt einen Report zurueck."""
    src = config.SOURCE_LANGUAGE
    targets = config.TARGET_LANGUAGES
    pattern = _tag_pattern()

    report = {
        "missing_language":   [],  # (tag_id, lang)
        "empty_translation":  [],  # (tag_id, lang)
        "bad_tag_id":         [],  # tag_id
        "sequence_gaps":      [],  # (chapter_id, expected, found)
        "total_tags":         0,
        "translatable_tags":  0,
    }

    # Pro Kapitel die Sequenznummern sammeln (fuer Lueckenpruefung)
    seq_by_chapter = {}

    for tag_id, entry in data["content"].items():
        report["total_tags"] += 1

        # 4. Tag-ID-Form
        if not pattern.match(tag_id):
            report["bad_tag_id"].append(tag_id)

        # Sequenznummer: im neuen Schema c<kap>_<NNNNN>_<typ> steht sie in der
        # MITTE. Global pro Kapitel durchnummeriert -> wieder lueckenlos pruefbar.
        chapter_id = tag_id.split("_")[0]
        parts = tag_id.split("_")
        seq = int(parts[1]) if len(parts) >= 3 and parts[1].isdigit() else None
        if seq is not None:
            seq_by_chapter.setdefault(chapter_id, []).append(seq)

        # Vollstaendigkeit / leere Felder nur fuer uebersetzbare Tags
        if _is_translatable(entry):
            report["translatable_tags"] += 1
            for lang in targets:
                if lang not in entry:
                    report["missing_language"].append((tag_id, lang))
                elif not str(entry[lang]).strip():
                    report["empty_translation"].append((tag_id, lang))

    # 3. Sequenz-Lueckenlosigkeit pro Kapitel
    for chapter_id, seqs in seq_by_chapter.items():
        seqs_sorted = sorted(seqs)
        expected = list(range(1, len(seqs_sorted) + 1))
        if seqs_sorted != expected:
            report["sequence_gaps"].append(
                (chapter_id, f"1..{len(seqs_sorted)}", seqs_sorted)
            )

    return report


def print_report(report: dict) -> bool:
    """Gibt den Report aus. Returnt True wenn sauber, False bei Fehlern."""
    print(f"[stage54] Tags gesamt: {report['total_tags']} "
          f"| uebersetzbar: {report['translatable_tags']}")

    clean = True

    if report["bad_tag_id"]:
        clean = False
        print(f"[stage54] FEHLER — ungueltige Tag-IDs: {report['bad_tag_id']}")

    if report["sequence_gaps"]:
        clean = False
        print(f"[stage54] FEHLER — Sequenz-Luecken:")
        for cid, exp, found in report["sequence_gaps"]:
            print(f"    {cid}: erwartet {exp}, gefunden {found}")

    if report["missing_language"]:
        clean = False
        print(f"[stage54] FEHLER — fehlende Sprachen "
              f"({len(report['missing_language'])}):")
        for tag_id, lang in report["missing_language"][:10]:
            print(f"    {tag_id} fehlt: {lang}")
        if len(report["missing_language"]) > 10:
            print(f"    ... und {len(report['missing_language'])-10} weitere")

    if report["empty_translation"]:
        clean = False
        print(f"[stage54] FEHLER — leere Uebersetzungen "
              f"({len(report['empty_translation'])}):")
        for tag_id, lang in report["empty_translation"][:10]:
            print(f"    {tag_id} leer: {lang}")

    if clean:
        print(f"[stage54] OK — Struktur vollstaendig und konsistent.")

    return clean


def run(book_id: str) -> dict:
    in_path = config.work_path(book_id, "310_uebersetzung")
    print(f"[stage54] Lese: {in_path}")
    with open(in_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    report = check(data)
    clean = print_report(report)

    # Report in die Datei schreiben (Transparenz/Audit)
    data["meta"]["integrity_report"] = {
        "clean": clean,
        "missing_language":  report["missing_language"],
        "empty_translation": report["empty_translation"],
        "bad_tag_id":        report["bad_tag_id"],
        "sequence_gaps":     report["sequence_gaps"],
    }

    out_path = config.work_path(book_id, "320_integritaet")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[stage54] Geschrieben: {out_path}")
    return data


if __name__ == "__main__":
    book = sys.argv[1] if len(sys.argv) > 1 else "aesop_three_fables"
    run(book)
