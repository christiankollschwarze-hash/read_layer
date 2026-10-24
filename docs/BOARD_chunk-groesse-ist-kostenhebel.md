# BOARD - Chunk-Groesse ist der Kostenhebel (nicht das Modell)

> Festgehalten 21.06.2026. Empirischer Beleg aus zwei Tagen realer Vertex-Abrechnung.
> Gehoert thematisch unter "Modelle & Infrastruktur" (TTS-Kontingent / Skalierungswand).

## Befund (Zwei-Tage-Vergleich, reale Abrechnung)
- **18.06.: 3,86 EUR mit FLASH** - nur kleine Werke, aber noch SATZ-FUER-SATZ
  (jeder Schnipsel ein eigener Call, jedes Mal die volle Regie-Praeambel als Input-Token).
- **20./21.06.: Cent-Bereich mit PRO** - dieselbe Werkklasse, aber BLOCK-Vertonung
  (Stage 58 neu: Regie 1x pro Block statt 1x pro Satz).
- Bemerkenswert: Wechsel auf das DOPPELT so teure Modell (Pro statt Flash) und
  TROTZDEM weniger Kosten. Der Chunk-Effekt ueberkompensiert den Modellpreis-Aufschlag.

## Mechanik (wo der Hebel sitzt)
- Spar-Hebel = INPUT-Token (Regie/Prompt), nicht Audio-Output-Token.
- Block amortisiert den Regie-Overhead: bei 8 Saetzen/Block zahlt man die Praeambel
  1x statt 8x. Bei kurzen Werken mit viel Schnipsel-Overhead = dramatische Ersparnis.
- WICHTIG (Grenze des Effekts): Audio-OUTPUT-Token bleiben gleich (gleiche Woerter =
  gleiche Sekunden). Bei einem ROMAN dominiert irgendwann der reine Audio-Output
  (~1,2 Mio. Token bei 350 Seiten) und der ist von der Chunk-Groesse UNBERUEHRT.
  -> Chunk-Vorteil ist bei Kurzwerken gross, bei Romanen anteilig kleiner.

## Tarif (offiziell bestaetigt, cloud.google.com/text-to-speech/pricing)
- Gemini 2.5 PRO TTS: Input 1 $/1M Text-Token, Output 20 $/1M AUDIO-Token.
- Gemini 2.5 FLASH TTS: exakt die Haelfte (0,50 $ / 10 $).
- Audio-Token = 25 Token pro Sekunde Audio. SKU Pro-Output: DCF3-CB17-8262.

## Monatszahl Juni (Kontext, reale CSV)
- Cloud Text-to-Speech GESAMT Juni: **7,65 EUR** (Jekyll 10 Kap. + Sleepy Hollow +
  Yellow Wallpaper + ALLE Tests/Tuning-Laeufe).
- Gemini API (Textseite): 2,40 EUR. Summe Entwicklungsmonat: 10,06 EUR.
- Niedrig auch, weil fruehe Tests z.T. auf Flash liefen + viel Reuse (kein TTS).

## Strategische Folge
- Block-Vertonung war nicht nur eine QUALITAETS-, sondern auch eine KOSTEN-Entscheidung.
  Sie macht den **Pro-only-Plan** erst tragfaehig (einheitliche Premium-Linie statt
  Flash/Pro-Zweiteilung -> markensauber, eine Variable weniger).
- Flash NICHT verwerfen, aber als WERKZEUG parken (Faulheitsmodus-DE, Einsteiger-
  Kurzformen), nicht als Qualitaetsstufe. Bei Roman x 5 Sprachen x Pro summiert sich
  auch ein kleiner Stueckpreis -> Hebel im Hinterkopf behalten.

## Offen (der entscheidende Anker)
- **The Great God Pan (Machen, ~20k EN-Woerter)** als erster echter Voll-Lauf ->
  misst, wo bei groesserem Volumen der Audio-Output den amortisierten Input-Vorteil
  einholt. Erst dann ist der 24-EUR/Buch-Wert (Pro, 350 S.) bestaetigt oder widerlegt.
- Mess-Logik: DIFFERENZ (Zaehler nach Lauf - Zaehler vor Lauf) / DE-Wortzahl =
  EUR/1000 Woerter bei Pro. Flash-Wert = Haelfte davon (ohne erneut messen).
- Vorsicht Billing-Latenz: Endwert ggf. am Folgetag nochmal pruefen.
- Wort-Alignment im Lauf kostet 0 EUR extra (lokales FA) -> verzerrt die Messung nicht.
- Voraussetzung: Stage 58 als stabil abgenommen (Sentinel-Blockenden sauber).
