# Sprechertrennung Erzaehler <-> Figur - call-of-the-wild [de]

## Eichung F0 x VTL (Archivpaare)
- clip: 105 gleich / 5355 verschieden | Massstab F0 1.438 HT, VTL 0.445 HT | D-Schwelle 3.244 (EER 21.7%) | nur F0: 3.21 HT (EER 23.9%) | nur VTL: 0.64 HT (EER 30.3%)
- stueck: 593 gleich / 21773 verschieden | Massstab F0 2.725 HT, VTL 0.65 HT | D-Schwelle 2.566 (EER 29.5%) | nur F0: 4.44 HT (EER 32.0%) | nur VTL: 0.87 HT (EER 36.8%)
- ECAPA: Stueck-Schwelle Kosinus-Abstand 0.609 (EER 2.5%), Clip-Schwelle 0.599 (EER 8.6%)

## Erzaehler: 96.7 Hz, VTL 17.51 cm, HNR 8.7 dB, CPPS 8.3 dB

## Figuren am fertigen Overlay (VC-Ergebnis gegen angrenzende Erzaehler-Rede)
| Figur (Stimme) | F0 VC | VTL VC | dF0 HT | dVTL | D | F0xVTL getrennt | Spannen getrennt | ECAPA verschieden | naeher an Ref | Spannen verschieden (ECAPA) |
|---|---|---|---|---|---|---|---|---|---|---|
| François (Hugo) | 96.6 Hz | 16.67 cm | -0.99 | -5.0 % | 2.1 | NEIN | 0.12 | True | True | 1.0 |
| Hal (Jack) | 120.7 Hz | 16.43 cm | 4.68 | -8.7 % | 4.8 | ja | 0.62 | True | True | 1.0 |
| John Thornton (Walter) | 88.7 Hz | 18.73 cm | -0.93 | 6.7 % | 2.61 | NEIN | 0.35 | False | True | 0.69 |
| Mercedes (Sophie) | 176.4 Hz | 16.12 cm | 10.95 | -7.1 % | 8.14 | ja | 1.0 | True | True | 1.0 |
| Perrault (Malcolm) | 97.2 Hz | 17.16 cm | 0.95 | -2.1 % | 1.06 | NEIN | 0.17 | False | True | 0.57 |

VC-Uebertragung: von der Differenz Zielstimme - Erzaehlerzitat kommen F0 65%, VTL 72% im Ergebnis an.
- John Thornton: vor Nachbesserung D 1.25 (dF0 -0.15, dVTL 3.2 %) -> nach D 2.61 (dF0 -0.93, dVTL 6.7 %)
- Perrault: vor Nachbesserung D 0.64 (dF0 0.32, dVTL -1.5 %) -> nach D 1.06 (dF0 0.95, dVTL -2.1 %)

## Diarisierung
- DER vc_collar0.0: 0.396 (Verwechslung 92.2 s von 528.1 s)
- DER vc_collar0.25: 0.252 (Verwechslung 69.9 s von 441.2 s)
- DER vc_n6_collar0.25: 0.226 (Verwechslung 58.5 s von 441.2 s)
- DER v1_collar0.0: 0.363 (Verwechslung 73.1 s von 528.1 s)
- DER v1_collar0.25: 0.224 (Verwechslung 55.8 s von 441.2 s)
- DER v1_n6_collar0.25: 0.245 (Verwechslung 65.1 s von 441.2 s)
- DER orig_collar0.0: 0.235 (Verwechslung 0.0 s von 528.1 s)
- DER orig_collar0.25: 0.102 (Verwechslung 0.0 s von 441.5 s)
- DER orig_n1_collar0.25: 0.102 (Verwechslung 0.0 s von 441.5 s)
- DER k2_collar0.0: 0.369 (Verwechslung 78.1 s von 528.1 s)
- DER k2_collar0.25: 0.226 (Verwechslung 58.2 s von 441.2 s)
- DER k2_n6_collar0.25: 0.226 (Verwechslung 58.2 s von 441.2 s)
- DER r2_collar0.0: 0.361 (Verwechslung 78.8 s von 528.1 s)
- DER r2_collar0.25: 0.219 (Verwechslung 58.9 s von 441.2 s)
- DER r2_n6_collar0.25: 0.203 (Verwechslung 51.7 s von 441.2 s)
- DER r3_collar0.0: 0.347 (Verwechslung 67.4 s von 528.1 s)
- DER r3_collar0.25: 0.205 (Verwechslung 50.1 s von 441.2 s)
- DER r3_n6_collar0.25: 0.205 (Verwechslung 50.1 s von 441.2 s)
- orig: 1 Sprecher erkannt, Wechsel {'ref_wechsel': 0, 'hyp_wechsel': 0}
- v1: 5 Sprecher erkannt, Wechsel {'ref_wechsel': 115, 'hyp_wechsel': 46, 'recall': 0.261, 'precision': 0.717}
- vc: 4 Sprecher erkannt, Wechsel {'ref_wechsel': 115, 'hyp_wechsel': 30, 'recall': 0.209, 'precision': 0.8}
- k2: 5 Sprecher erkannt, Wechsel {'ref_wechsel': 115, 'hyp_wechsel': 39, 'recall': 0.261, 'precision': 0.821}
- r2: 5 Sprecher erkannt, Wechsel {'ref_wechsel': 115, 'hyp_wechsel': 37, 'recall': 0.252, 'precision': 0.865}
- r3: 6 Sprecher erkannt, Wechsel {'ref_wechsel': 115, 'hyp_wechsel': 45, 'recall': 0.27, 'precision': 0.711}

Anteil Redezeit, die pyannote NICHT dem Erzaehler zuordnet:

| Figur | orig | v1 | vc | k2 | r2 | r3 | orig (Sprecherzahl vorgegeben) | v1 (Sprecherzahl vorgegeben) | vc (Sprecherzahl vorgegeben) | k2 (Sprecherzahl vorgegeben) | r2 (Sprecherzahl vorgegeben) | r3 (Sprecherzahl vorgegeben) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Erzaehler | 0.0 | 0.04 | 0.01 | 0.01 | 0.01 | 0.02 | 0.0 | 0.07 | 0.06 | 0.1 | 0.06 | 0.02 |
| François | - | 0.86 | 0.05 | 0.16 | 0.0 | 0.37 | - | 0.82 | 0.9 | 0.93 | 0.7 | 0.37 |
| Hal | - | 0.91 | 0.9 | 0.92 | 0.9 | 0.9 | - | 0.92 | 0.88 | 0.92 | 0.9 | 0.9 |
| John Thornton | - | 0.0 | 0.01 | 0.4 | 0.38 | 0.4 | - | 0.41 | 0.28 | 0.4 | 0.38 | 0.4 |
| Mercedes | - | 0.99 | 0.99 | 0.99 | 0.99 | 0.99 | - | 0.99 | 0.99 | 0.99 | 0.99 | 0.99 |
| Perrault | - | 0.13 | 0.0 | 0.0 | 0.0 | 0.39 | - | 0.39 | 0.24 | 0.52 | 0.39 | 0.39 |
- (ECAPA-Fenster-Clustering: Schwelle fuer 1,5-s-Fenster nicht geeicht -> nicht gewertet)

## Vorhersage beim Casting: Zielstimme (Referenz) gegen Erzaehler des Werks
| Figur | D F0xVTL | getrennt laut Regel | ECAPA Ref-Erz | Ergebnis VC: ECAPA verschieden |
|---|---|---|---|---|
| François | 3.26 | ja | 0.803 | True |
| Hal | 5.58 | ja | 0.77 | True |
| John Thornton | 1.26 | NEIN | 0.525 | False |
| Mercedes | 9.01 | ja | 0.849 | True |
| Perrault | 1.77 | NEIN | 0.696 | False |

## Korrektur nach VC (Formantfaktor, Tonhoehe)
| Figur | Variante | Formant | HT | dF0 | dVTL | D | ECAPA Abstand Erz | verschieden | naeher an Ref | Spannen verschieden |
|---|---|---|---|---|---|---|---|---|---|---|
| François | ohne | 1.0 | 0 | -0.99 | -5.0 % | 2.1 | 0.706 | True | True | 1.0 |
| François | r2 | 0.885 | -3 | -3.64 | -3.4 % | 2.87 | 0.534 | False | False | 0.91 |
| François | r3 | 1.1 | 0 | -1.05 | -13.0 % | 5.47 | 0.883 | True | True | 1.0 |
| Hal | ohne | 1.0 | 0 | 4.68 | -8.7 % | 4.8 | 0.678 | True | True | 1.0 |
| Hal | r2 | 1.0 | 0 | 4.68 | -8.7 % | 4.8 | 0.678 | True | True | 1.0 |
| Hal | r3 | 1.0 | 0 | 4.68 | -8.7 % | 4.8 | 0.678 | True | True | 1.0 |
| John Thornton | ohne | 1.0 | 0 | -0.93 | 6.7 % | 2.61 | 0.462 | False | True | 0.69 |
| John Thornton | k1 | 0.95 | -2 | -3.0 | 5.1 % | 2.85 | 0.545 | False | True | 0.81 |
| John Thornton | k2 | 0.91 | -3 | -4.04 | -2.0 % | 2.92 | 0.61 | True | True | 0.85 |
| John Thornton | k3 | 0.87 | -4 | -4.61 | -18.0 % | 8.36 | 0.639 | True | True | 0.92 |
| John Thornton | kf | 0.91 | 0 | -0.95 | -0.3 % | 0.67 | 0.599 | False | True | 0.92 |
| John Thornton | kp | 1.0 | -3 | -3.65 | 6.6 % | 3.56 | 0.501 | False | True | 0.77 |
| John Thornton | r2 | 0.885 | -3 | -4.0 | -14.1 % | 6.52 | 0.618 | True | True | 0.88 |
| John Thornton | r3 | 0.94 | 0 | -0.91 | 5.8 % | 2.29 | 0.548 | False | True | 0.81 |
| Mercedes | ohne | 1.0 | 0 | 10.95 | -7.1 % | 8.14 | 0.83 | True | True | 1.0 |
| Mercedes | r2 | 1.0 | 0 | 10.95 | -7.1 % | 8.14 | 0.83 | True | True | 1.0 |
| Mercedes | r3 | 1.0 | 0 | 10.95 | -7.1 % | 8.14 | 0.83 | True | True | 1.0 |
| Perrault | ohne | 1.0 | 0 | 0.95 | -2.1 % | 1.06 | 0.401 | False | True | 0.57 |
| Perrault | k1 | 1.053 | 2 | 3.17 | -6.4 % | 3.39 | 0.557 | False | True | 0.71 |
| Perrault | k2 | 1.099 | 3 | 4.21 | -9.9 % | 4.99 | 0.669 | True | True | 1.0 |
| Perrault | k3 | 1.149 | 4 | 5.18 | -11.0 % | 5.79 | 0.787 | True | False | 1.0 |
| Perrault | kf | 1.099 | 0 | 1.08 | -9.5 % | 3.94 | 0.669 | True | True | 1.0 |
| Perrault | kp | 1.0 | 3 | 4.16 | -1.3 % | 2.94 | 0.401 | False | False | 0.43 |
| Perrault | r2 | 1.13 | 3 | 4.16 | -10.9 % | 5.34 | 0.729 | True | False | 1.0 |
| Perrault | r3 | 1.1 | 0 | 1.22 | -9.2 % | 3.84 | 0.675 | True | True | 1.0 |

## Regel
D = sqrt((dF0/skala_f0)^2 + (dVTL/skala_vtl)^2), gemessen Figur(VC-Ergebnis) gegen Erzaehler. getrennt, wenn D >= D_schwelle (EER an Archivpaaren); Casting zielt auf D_ziel (25 % Reserve).
D_schwelle 3.244, D_ziel 4.06
