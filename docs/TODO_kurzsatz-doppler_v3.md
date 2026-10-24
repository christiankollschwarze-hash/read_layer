# TODO / KONZEPT — Kurzsatz-Doppler (Saetze < 5 Woerter) [Update 2, 18.06.2026]

> Vollstaendiger Stand. Prompt-Weg ist nach VIER getesteten Varianten ERWIESEN tot.
> Loesung muss am Audio (schneiden) oder an der Struktur (Tagger-Merge) ansetzen.

## Befund (stabil ueber viele Laeufe)
Sleepy Hollow/de, hartnaeckige Doppler, deterministisch (kein Wuerfeln hilft):
    c001_00403  (5 W) -> gehoert ~10-11
    c001_00455  "Was sollte er tun?"        (4 W) -> gehoert 8 = 2x
    c001_00458  "Er erhielt keine Antwort."  (4 W) -> gehoert 8 = 2x
    c001_00460  "Noch immer keine Antwort."  (4 W) -> gehoert 8 = 2x
CK hat reingehoert: ECHTE Doppler. Ursache: sehr kurze Aeusserung -> Modell fuellt
durch Wiederholung. Sitzt UNTERHALB der Prompt-Ebene.

## ERLEDIGTE SACKGASSE: Prompt-Haertung -- VIER Varianten, ALLE 8/8/8
Alle im prompt-Feld (Regie), Kurzsatz-Zweig in stage_58 _build_prompt:
1. Generisch: "Do NOT add, invent, repeat or read anything else."        -> 8/8/8
2. Verschaerft: "Say it ALOUD EXACTLY ONCE, then STOP. Do not echo..."   -> 8/8/8
3. Nachgestellte Aufgabe: "After you have spoken it, your task is
   complete. Do not repeat the previous sentence!"                       -> 8/8/8
4. Numerisch (CK): "Read the sentence 1 time. Output must contain exactly
   1 spoken instance of the line."                                        -> 8/8/8
FAZIT: Gemini-TTS ignoriert Anti-Wiederholungs-Anweisungen bei sehr kurzen Saetzen
ZUVERLAESSIG, egal ob Verbot, Verschaerfung, nachgestellte Aufgabe oder Zahl.
PROMPT-WEG IST TOT. Definitiv nicht erneut versuchen.

## VERBLEIBENDE ECHTE WEGE (ausserhalb des Prompts)
### A) "Zweite Haelfte abschneiden" (Output-Fix) -- billig, alignment-erhaltend
- Glatte Faelle verdoppeln EXAKT (ist = 2*soll, 8 = 2*4). Wenn STT ist ~= 2*soll
  erkennt -> Audio an der Stille-Mitte schneiden, hintere Haelfte verwerfen.
- + kein Datenmodell-Umbau, EINE WAV pro Tag bleibt (Alignment erhalten),
  kein Cross-Language-Problem.
- - nur sauber bei glatter Verdopplung; c001_00403 (10-11) unsauberer -> Toleranz
  oder Sonderbehandlung. Stille-Detektion noetig (nicht stur 50%).
- Werkzeug: kleiner Audio-Schnitt (pydub/wave + Stille-Detektion). Neu zu bauen.

### B) Merge auf TAGGER-Ebene (Input/Wurzel) -- gruendlich, aber Eingriff
- Kurzsatz + Nachbar -> EIN Audio-Tag auf der ENGLISCHEN QUELLE (Stage 50, VOR
  Uebersetzung). Alle Sprachfassungen erben dieselbe Tag-Struktur -> Cross-Language-
  Disalignment ENTSCHAERFT. Genug Material -> keine Fuell-Wiederholung.
- Soll-Wortzahl = Summe (STT bleibt korrekt). Manifest/Assembler: saubere 1:1.
- PREIS: gemergte Saetze nicht einzeln antippbar (TAELLA). Nur fuer entbehrlichen
  Lernstoff ("Er erhielt keine Antwort."). Schwelle N konfigurierbar (<=4-5 W).

## EMPFEHLUNG
- A zuerst (billig, alignment-erhaltend) an den glatten 2x-Faellen testen.
- B als Langfristloesung, wenn Kurzsaetze grundsaetzlich raus sollen.
- Beide = neues Werkzeug -> eigene Session.

## Heute-Stand (akzeptiert)
- Sleepy Hollow/de: 4 Kurzsatz-Doppler bleiben = 99,2% sauber. Werk ABGESCHLOSSEN.
- stage_58 Kurzsatz-Zweig steht aktuell auf Variante 4 (numerisch). Schadet
  normalen Kurzsaetzen nicht -> kann bleiben oder auf schlichte Form zurueck.
