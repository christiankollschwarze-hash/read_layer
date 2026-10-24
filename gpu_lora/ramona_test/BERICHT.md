# LoRA-Testlauf ramona_test (17.10.2026 22:54)

## Daten

- sterben_1208_librivox: 973/2092 Saetze, 1.57 h; verworfen {'_referenz_woerter': 29929, '_woerter': 29892, '_ref_treffer': 28078, 'keine_pause_nach_satz': 785, '_audio_min': 201.1, 'abschrift_unsicher': 111, 'ziffern': 96, 'pruefung_vorlauf': 50, 'pruefung_nachklang': 28, 'zu_kurz': 22, 'zu_lang_ungeteilt': 16, 'ansage_librivox': 7, 'pruefung_verschmiert': 3, 'pruefung_zu_lang': 1}
- frauleinelse_2403_librivox: 728/2290 Saetze, 0.9 h; verworfen {'_woerter': 26360, '_referenz_woerter': 25242, '_ref_treffer': 20142, 'keine_pause_nach_satz': 934, 'abschrift_unsicher': 474, '_audio_min': 167.4, 'zu_kurz': 53, 'pruefung_vorlauf': 51, 'pruefung_nachklang': 28, 'zu_lang_ungeteilt': 8, 'pruefung_verschmiert': 6, 'pruefung_zu_lang': 4, 'ansage_librivox': 4, '_ref_datei_whisper': 1}
- pinocchio_2403_librivox: 891/2523 Saetze, 1.41 h; verworfen {'_referenz_woerter': 37020, '_woerter': 36981, '_ref_treffer': 33243, 'keine_pause_nach_satz': 742, 'abschrift_unsicher': 664, '_audio_min': 243.7, 'pruefung_vorlauf': 104, 'pruefung_nachklang': 41, 'zu_kurz': 28, 'pruefung_zu_lang': 18, 'pruefung_verschmiert': 12, 'ziffern': 10, 'zu_lang_ungeteilt': 10, 'ansage_librivox': 3}

## Training

- 2538 Saetze Training / 54 Validierung, Rang 32, lr 0.0002, 3 Epochen, 477 Schritte, 2.1 GPU-min (A100)
- Validierung (Sprachtoken-Verlust): 0: 4.036 -> 250: 3.7666 -> 477: 3.7717
- bester Checkpoint: step_00250.safetensors

## Bewertung Peter Pan Kap. 1 DE (grossmutter_a = fremde Stimme, ramona = Trainingsstimme)

| Variante | Stimme | Checkpoint | Pruefung ok | Auffaellig | Aehnlich Referenz | Aehnlich Ramona | Streuung HT | Spanne HT | s/Satz | Ausklang s | abgeschnitten |
|---|---|---|---|---|---|---|---|---|---|---|---|
| basis | grossmutter_a | - | 132/140 | nachklang 6, zu_lang 2 | 0.9406 | 0.79 | 6.31 | 10.63 | 12.27 | 0.38 | 7/140 |
| lora_bester | grossmutter_a | step_00250.safetensors | 140/140 | - | 0.9224 | 0.7902 | 5.88 | 10.73 | 9.94 | 0.12 | 25/140 |
| lora_letzter | grossmutter_a | step_00477.safetensors | 140/140 | - | 0.9175 | 0.7884 | 5.56 | 10.66 | 10.04 | 0.12 | 42/140 |
| ramona_basis | ramona | - | 119/140 | zu_lang 1, nachklang 19, verschmiert 1 | 0.9135 | 0.9142 | 4.27 | 9.36 | 11.16 | 0.5 | 24/140 |
| ramona_lora | ramona | step_00250.safetensors | 140/140 | - | 0.9094 | 0.9125 | 4.24 | 9.17 | 10.01 | 0.14 | 11/140 |

Hoeren: gpu_lora/ramona_test/bewertung/<variante>/ (gleiche Saetze, gleicher Zufallsstartwert).
Aehnlich Referenz soll gleich bleiben (Klangfarbe grossmutter_a); steigt 'Aehnlich Ramona' deutlich, faerbt der Adapter die Stimme.