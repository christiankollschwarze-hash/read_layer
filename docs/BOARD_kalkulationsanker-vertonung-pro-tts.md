# BOARD - Kalkulationsanker Vertonung (Pro-TTS), gemessen an Yellow Wallpaper

> Festgehalten 21.06.2026. Erster ECHTER Messwert (kein Schaetzwert) fuer die
> TTS-Stueckkosten. Loest die offene 20-EUR/Buch-Frage. Gegenprobe an groesserem
> Volumen (Pan) steht noch aus.

## Der Anker (gemessen)
- Yellow Wallpaper, voll vertont (Gemini 2.5 PRO TTS, Stimme Despina):
  **1,25 EUR** realer Vertex-Verbrauch (Differenz-Messung Zaehler vor/nach Lauf).
- Exakte Textmenge aus stage06.json: **258 vertonte Saetze = 5.790 DE-Woerter**
  (EN 6.085 -> DE hier ~5% KUERZER; Gilmans knapper Stil, die "DE laenger"-Faustregel
  greift nicht immer).
- **=> 0,216 EUR / 1000 DE-Woerter (Pro).**  Flash = Haelfte (~0,11 EUR/1000).

## Hochrechnung (linear, Pro)
- 85.000 DE-Woerter  -> ~18,4 EUR
- 105.000 (350 Seiten) -> ~22,7 EUR
- 120.000 -> ~25,9 EUR
- Deckt sich mit beiden frueheren Schaetzungen: die 17-18 EUR (85k) UND die
  konservative ~24 EUR (350 S./105k) waren beide richtig - nur unterschiedliche
  Buchlaengen. Die Output-Token-Rechnung (25 Token/Sek x 20 $/1M) traegt sauber.

## Konsequenzen
- Pro pro Buch je nach Laenge ~18-26 EUR/Sprache. 5-Sprachen-Faecher mittleres
  Werk: grob ~100-130 EUR.
- Pan (20k EN -> ~19k DE) als Anker-Lauf: ~4 EUR erwartet. Wert des Pan-Laufs ist
  die Gegenprobe bei GROESSEREM Volumen (wo der reine Audio-Output dominiert und
  der Chunk-/Input-Amortisationsvorteil anteilig kleiner wird).
- Geschaeftsmodell haelt: On-Demand-Audio NACH Kauf -> 18-26 EUR/verkaufte
  Sprachfassung ist ueber den Verkaufspreis darstellbar, kein Vorabrisiko.

## Mess-Methode (fuer kuenftige Anker, reproduzierbar)
1. Voll-Lauf an TTS-ruhigem Tag, Differenz = Zaehler nach - Zaehler vor.
2. DE-Wortzahl aus stage06.json: nur type=="s"-Tags, \w+-Zaehlung.
3. EUR / DE-Woerter * 1000 = Anker. Billing-Latenz beachten (ggf. Folgetag lesen).
4. Wort-Alignment im Lauf kostet 0 (lokales FA) -> verzerrt die Messung nicht.

## Monatskontext (Juni, reale CSV)
- Cloud TTS gesamt Juni 7,65 EUR (mehrere Werke + alle Tests), Gemini API 2,40 EUR,
  Summe 10,06 EUR. Entwicklung bleibt dank Reuse + kurzer Tests im Cent-/Euro-Bereich.
