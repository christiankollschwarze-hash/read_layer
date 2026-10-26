# AP 58 Winnie-the-Pooh - Kosten (Schaetzung vorab, Ist je Schritt)

Grundlage: 22.600 Woerter (Alice 26.500, Baskerville 58.900). Schaetzung aus kosten.jsonl Baskerville/Alice skaliert.

| Schritt | Werkzeug | Schaetzung | Ist |
|---|---|---|---|
| 1 Import + Vorbereitung (ohne Modernisierung) | lokal | 0,00 $ | 0,00 $ |
| 1 Text 200-400 (Tagging, Profil, Vor-/Uebersetzung, Integritaet, Rueckuebersetzung, Regie) | DeepSeek | ~0,50 $ | |
| 1 Stage 340 Wort-Alignment | lokal/DeepSeek | ~0,05 $ | |
| 2 Bildanker | lokal | 0,00 $ | 0,00 $ |
| 3 Bild-Probe 5 Bilder | Gemini Flash Bild | ~0,20 $ | ~0,20 $ |
| 3 Rest 22 Bilder | Gemini Flash Bild | ~0,90 $ | ~0,86 $ |
| 4 Casting (Steckbriefe + Voice Design) | DeepSeek/Gemini | ~0,20 $ | |
| 4 Vertonung EN + DE | Gemini TTS | ~7-9 $ (Alice EN ~5 $ je Fassung, skaliert) | |
| 4 Wortzeiten 520 + 525 | Modal | ~2-4 $ (~1 $/Audio-h, ~2,5 h je Sprache) | |
| 4 Stage 560 Sprachpruefung EN + DE | Modal Whisper + Gemini (Auswahl) | ~1 $ | |
| 5 Reader + Demo-Export | lokal | 0,00 $ | |
| **Summe** | | **~12-16 $** | |

Ist-Werte: work/kosten.jsonl des Werks (usage_log), Bilder in work/bilder.json (kosten_usd).
