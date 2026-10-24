# READ LAYER — Nachtrag: DE-Uebersetzung Call of the Wild (Stages 51-56)

> Ergaenzt STAND_2026-06-23_vollauf_cotw. Nach dem en-LibriVox-Audio lief die
> deutsche Uebersetzungskette durch -> "Upps"-Struktur komplett.

## ERGEBNIS: DE-UEBERSETZUNG STEHT
python run.py call-of-the-wild --line audio --from 51 --to 56 --lang de --live
- Stages 51 (Profiler) -> 56 (Regie), bis 56 (vor Audio). Laufzeit ~6822 s.
- Stage 55 Backtranslation: **Durchschnitts-Score 96.2** | bewertet 1634 |
  unter Schwelle 109 (~6,7%) | **nicht bewertbar 0**. Vergleichbar/besser als
  Jekyll (94.0). 0 nicht-bewertbar = Batching+Retry hat alles erfasst.
- Stage 53 Batch-6 lieferte einmal kaputtes JSON -> automatisch "Versuch 2",
  sauber nachgeholt (api_layer.parse_json-Haertung + Retry-pro-Batch bewaehrt).
  Kein Satz verloren (193/193 in c001 usw.).
- stage06.json geschrieben: en + de + Regie + Pausen an jedem Tag (kanonisch).

## QUALITAET (CK bestaetigt)
- Epochentreue traegt (style.setting aus Stage 51). Beispiel c001:
  "great stables, where a dozen grooms and boys held forth, rows of vine-clad
  servants' cottages..." -> "grosse Stallungen, in denen ein Dutzend
  Pferdeknechte und Jungen das Regiment fuehrten, Reihen von weinbewachsenen
  Dienstbotenhaeuschen..." CK: "wirklich gut getroffen".
- "groom"->Pferdeknecht (nicht modern), "held forth"->das Regiment fuehren,
  "vine-clad"->weinbewachsen. Idiomatisch-viktorianisch, keine Anachronismen.

## WICHTIGE EINORDNUNG: niedrige Backtrans-Scores != schlechte Uebersetzung
- Die 109 "unter Schwelle" (meist 85, knapp unter 90) sind oft FREIE, gute
  Uebersetzungen: der Scorer belohnt Woertlichkeit, freie idiomatische
  Loesungen kommen rueckuebersetzt nicht wortgleich beim Original an.
- AUSREISSER zum Pruefen: c001_00012_s = 60 (einziger wirklich niedriger Wert
  in den ersten 10) -> beim naechsten Mal gezielt anschauen, ob echt falsch
  oder nur frei. NICHT pauschal alle 109 nacharbeiten.

## DAMIT: "Upps"-Lernprodukt komplett fuer Call of the Wild
- EN: LibriVox-Audio (1629 Schnipsel) + Originaltext, tag-aligned.
- DE: epochengerechte Uebersetzung an denselben Tag-IDs.
- Satzweise Lesen/Hoeren/Antippen moeglich. de-Audio (TTS) waere optionaler
  Folgelauf (Stage 58 normal, da Jeff Clark nur EN las).

## OFFEN (unveraendert)
- Audio-Cover (quadratisch), Cover/Colophon-Credit (Stage 30), --lang-Luecke.
- Optional: c001_00012_s pruefen; lesbarer DE-Volltext = EPUB-Lauf (Stage 13/31).
