# TECHNIK — CTO-Statusdatei (TÆLLA / Read Layer / SOMNIO)

Stand: 17.10.2026 · Erstfassung, ergänzt 08:10

## 1 Zielarchitektur
Read Layer (lokal, Windows, `C:\Users\sabin\read_layer\`, Stufen 00–60 + Cockpit)
→ Cloud-Export (Stage 60: Manifeste, Wortzeiten, Audio → GCS-Bucket)
→ TÆLLA (React/Vite, später Capacitor/Android) liest nur Manifest + Bucket.
Rechenlast: Text = DeepSeek-API · TTS Premium = Gemini · TTS Basis/VC/Alignment/Messung = Modal (L4/T4).
Verlagszugang später: ePub-Upload (Stage 05) → Cockpit-Tore → Export (TÆLLA-Paket und/oder EPUB 3 mit Media Overlays).

## 2 Stack-Entscheidungen (gültig)
| Bereich | Entscheidung | Kennzahl |
|---|---|---|
| Text (11–56, 57b) | DeepSeek v4 flash/pro, Denkmodus aus, Nebenzeit | ~0,09 $/1.000 Wörter |
| TTS Premium | Gemini 3.8 Flash TTS, designte Stimmen | ~0,81 $/Audio-h (ab 2027 ×2), 10.000 Anfragen/Tag |
| TTS Basis | Chatterbox (EN) / Multilingual (DE) auf Modal L4 | ~0,94 $/Audio-h, Tempo-Anpassung 0,73 |
| Hörspiel-Schicht | Gemini-Basis + Chatterbox VC + Montage per Wortzeiten + Trennungsmessung | ~0,50 $/Werk VC |
| Wortzeiten 58c | MMS_FA auf Modal | Roman ~12 min statt 3–8 h CPU |
| Kimi K3 | nur Flaggschiff-Titel (57b) | ~7 $/Roman |
| Rechtlich | Keine Gemini-Ausgaben als Klon-/VC-Vorlage oder Trainingsdaten | juristische Prüfung vor produktiver VC |
| Versionsverwaltung | Git, privates GitHub-Repo je Projekt, ohne Audio/Modelle/Schlüssel | 0 € |

## 3 GPU: Miete vs. eigen
Entscheidung: **Modal bleibt**, bis Messung Gegenteil zeigt.
Messgröße: GPU-Stunden/Monat. Schwelle für eigene GPU = Monatsmiete > Abschreibung + Strom einer Karte (Größenordnung 24-GB-Karte). Erst ab Katalog-Serienlauf (Vorlesen-Stufe für alle Werke) relevant. → Investition = „CFO prüfen“.
Sofort: Modal-Volume für Modellgewichte (spart Download je Lauf).

## 4 Technische Schulden (priorisiert)
1. **Keine Versionsverwaltung** – ANGESTOSSEN 17.10. (CK): A-002, AP claude/AP_git_einfuehrung.md, an Pipeline + Frontend, je Lead als erstes in der nächsten Sitzung.
2. `run.py` liefert Exit-Code 0 trotz Fehler → korrigieren (Pipeline, klein).
3. Modellwechsel 16.10. (alle Textstages → DeepSeek) nicht je Stage getestet → Regel 2 (ERKENNTNIS 17.10.) nachholen: 52, 55, 56 am Peter-Pan-Lauf.
4. Kosten 57/57b fehlen in `kosten.jsonl` → Kostenmodell je Werk unvollständig.
5. Mock-up lädt Ruf der Wildnis aus `public/` statt `public/demo/` (Frontend).
6. Gemini-Tageslimit ist Engpass → 8-Satz-Pakete für Basis-TTS umsetzen.
7. Lange Jobs nur per Windows-Batch (VM-Prozesse sterben) – dokumentiert, kein Handlungsbedarf.
8. Hauptordner read_layer ist vermüllt (.bak-Dateien, Logs, Start-Batches im Root) → nach Git-Einführung aufräumen (Logs nach `logs\`, Batches nach `start\`).

## 5 Offene Architekturthemen
| Thema | Stand | Nächster Schritt | Zuordnung |
|---|---|---|---|
| Cloud-Export (GCS) | Stage 60 vorhanden, Upload bewusst manuell | Bucket-Struktur + signierte URLs festlegen | Pipeline |
| ePub-Ingest (Stage 05) | AP Peter Pan läuft | Messung Chatterbox ≤ 0,50 €/50k Zeichen | Pipeline |
| BFSG / Media Overlays | Konzept (BOARD 10.10.) | Proof: Ruf der Wildnis als EPUB 3 + SMIL, Test Apple Books/Thorium, Ace-Check | Pipeline |
| Verlags-Self-Service | Cockpit lokal (127.0.0.1) | erst nach Pilotkunde; bis dahin Auftragsproduktion durch CK | – |
| DRM | offen | PD-Titel ohne DRM; Verlagstitel: signierte, kurzlebige Audio-URLs + keine Downloads im Web; LCP erst auf Verlagswunsch | Frontend |
| Datenschutz | Kuratormodus schreibt lokal | vor Nutzerkonten: DSGVO-Konzept (Konto, Kuration, Hörtest-Daten), EU-Region Bucket | Frontend |
| Android | AP vorgemerkt | nach Cloud-Export | Frontend |

## 6 Anforderungen (Bewertung)
| ID | Machbarkeit | Aufwand | An | Rückfrage / Stand |
|---|---|---|---|---|
| A-001 Alignment Fremd-Audio | hoch – Bausteine vorhanden (58_3rd_prty STT-Abgleich, 58c Wortzeiten, Strom-Modus) | M (Ingest-Schnittstelle + Lieferformat) | Pipeline | Lieferformat: TÆLLA-Paket, EPUB 3 Media Overlays oder beides? Audioformat/Kapitelschnitt der Verlage? Text als ePub? |
| A-002 Git-Einführung | hoch | S (½ Tag) | Pipeline + Frontend | angenommen; Schlüsselsuche vor erstem Commit Pflicht; `bereiche\` mit versionieren |

## 7 Ablage & Rechte (CK 17.10.2026)
- Arbeitsordner `read_layer\bereiche\` angelegt: marketing\, vertrieb\, finanzen\, technik\ (+ README.md).
- MARKETING.md, VERTRIEB.md, FINANZEN.md und TAELLA_UG_Unternehmensgegenstand.md aus dem Root dorthin verschoben.
- CTO schreibt in `bereiche\technik\` und darf an operativen Pipeline-Komponenten arbeiten (pipeline\, tools\, config\, gpu_*\, cockpit\, run.py).
- PIPELINE.md und FRONTEND.md existieren noch nicht → Leads legen sie in ihrer ersten Sitzung an.

## 8 Messen vor Entscheiden – laufende Messungen
- Chatterbox optimiert (Peter Pan): Kosten je 50k Zeichen, Fehlerquote, GPU-h/Audio-h.
- DeepSeek-Stages 52/55/56 vs. Gemini (Ausgabe, Token, Kosten).
