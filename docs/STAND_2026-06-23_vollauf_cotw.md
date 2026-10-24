# READ LAYER — Vollauf-Ergebnis Call of the Wild (en-Audio, LibriVox)

> Nachtrag zu STAND_2026-06-22b. Der gestartete Vollauf der en-Audiofassung ist
> DURCH und am Ohr validiert. Haelt das konkrete Ergebnis fest.

## ERGEBNIS: VOLLAUF GELUNGEN
python run.py call-of-the-wild --only 58 --line audio --lang en --live
- Laufzeit: 16605 s (~4,6 h) fuer alle 7 Kapitel (STT medium/int8 dominiert).
- **1629 Schnipsel** geschrieben nach fassungen/en/audio/ (<tag_id>.wav), 12 geflaggt.
- Lauf wurde einmal manuell unterbrochen, hat dank STT-Cache pro Kapitel
  selbststaendig fortgesetzt (Resilienz bewaehrt).
- **CK-Hoertest: keine Fehler, alles prima geschnitten.** Konsonanten ganz,
  richtige Saetze, saubere Schnitte ueber alle Kapitel.

## MATCH-RATEN JE KAPITEL (Sprecher-Treue, Abweichungs-Ampel)
- c001: 194 Einheiten, 95.2%, Korridor 194/194
- c002: 166, 95.8%, 164/166 (2 geflaggt)
- c003: 279, 95.7%, 276/279 (3 geflaggt) — dialogreich
- c004: 180, 94.9%, 180/180
- c005: 306, 95.3%, 304/306 (2 geflaggt)
- c006: 248, 95.4%, 245/248 (3 geflaggt)
- c007: 268, 98.2%, 266/268 (2 geflaggt) — laengstes Kapitel, hoechster Match
- Durchweg 94.9–98.2% -> Jeff Clark folgt dem Text treu, keine Editions-Abweichung.
  Nur ~0,7% geflaggt (erwartete Kurz-Dialoge ohne Anker).

## BEDEUTUNG
Erster vollstaendiger LibriVox-Audiokatalog eines Werks im kanonischen
AUTOR/WERK/FASSUNG-Modell, tag-aligned (c<NNN>_<seq>_<typ>.wav), ununterscheidbar
von TTS-Audio. Die gesamte LibriVox-Integration (4 Abzweige + Weiche pro Fassung)
ist damit als bewiesenes Produkt bestaetigt, nicht nur als Code.

## NAECHSTE SCHRITTE (unveraendert aus STAND_2026-06-22b)
1. Deutsche Uebersetzung in der Satz-Alignment-Struktur (Stages 52-56, DeepSeek) ->
   de-Tag-Texte an denselben Tag-IDs -> "Upps"-Lernprodukt. de-Audio = TTS.
2. Audio-Cover (quadratisch 1:1, >=2400x2400, Titel+Autor, Sprecher optional, KEIN
   Disclaimer aufs Cover) aus derselben Tusche-Illustration wie EPUB-Cover.
3. Cover/Colophon-Credit (Stage 30): dezenter LibriVox-Vermerk im Cover-Fuss UND
   voller Disclaimer im Colophon (liest credit/source_disclaimer aus book.json).
4. --lang-Luecke: en-LibriVox-Fassung laeuft nur mit explizitem --lang en (run.py
   _target_languages nimmt sonst nur TARGET_LANGUAGES). Spaeter sauber loesen.
