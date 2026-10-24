# TODO / KONZEPT — Kurzsatz-Doppler (Saetze < 5 Woerter) [Update 18.06.2026]

> Ersetzt/ergaenzt die erste Notiz. Wichtigstes Update: Prompt-basierte Loesungen
> sind ERWIESEN wirkungslos (drei Varianten getestet). Loesung muss ausserhalb
> des prompt-Feldes liegen.

## Befund (stabil ueber mehrere Laeufe)
Sleepy Hollow/de, hartnaeckige Doppler, wuerfeln sich NICHT weg:
    c001_00403  (5 W) -> gehoert ~10-11
    c001_00455  "Was sollte er tun?"        (4 W) -> gehoert 8 = 2x
    c001_00458  "Er erhielt keine Antwort."  (4 W) -> gehoert 8 = 2x
    c001_00460  "Noch immer keine Antwort."  (4 W) -> gehoert 8 = 2x
CK hat reingehoert: ECHTE Doppler (Satz zweimal gesprochen). Ursache: sehr kurze
Aeusserung -> Modell fuellt durch Wiederholung. Deterministisch -> kein Wuerfeln hilft.

## ERLEDIGTE SACKGASSE: Prompt-Haertung (3 Varianten getestet, ALLE wirkungslos)
Alle im prompt-Feld (Regie), am Kurzsatz-Zweig in stage_58 _build_prompt:
1. Generisch: "...Do NOT add, invent, repeat or read anything else."   -> 8/8/8
2. Verschaerft: "Say it ALOUD EXACTLY ONCE, then STOP. Do not echo... single utterance." -> 8/8/8
3. Nachgestellte Aufgabe (CK-Idee): "After you have spoken it, your task is
   complete. Do not repeat the previous sentence!"                      -> 8/8/8
FAZIT: Gemini-TTS ignoriert Anti-Wiederholungs-Anweisungen bei sehr kurzen Saetzen
zuverlaessig. Prompt-Weg ist TOT. Nicht erneut versuchen.

## VERBLEIBENDE ECHTE WEGE (ausserhalb des Prompts)
### A) "Zweite Haelfte abschneiden" (Output-Fix) -- billig, alignment-erhaltend
- Beobachtung: die glatten Faelle verdoppeln EXAKT (ist = 2*soll, z.B. 8 = 2*4).
- Idee: wenn STT erkennt ist ~= 2*soll -> Audio in der Mitte (an der Stille zwischen
  den zwei Durchlaeufen) schneiden, hintere Haelfte verwerfen.
- Vorteile: kein Datenmodell-Umbau, EINE WAV pro Tag bleibt (Alignment erhalten),
  kein Cross-Language-Problem.
- Risiken: nur sauber bei GLATTER Verdopplung. c001_00403 (10-11 statt 8) ist
  unsauberer -> Erkennung muss Toleranz haben oder solche Faelle anders behandeln.
  Stille-Erkennung in der Mitte noetig (nicht stur bei 50% schneiden).
- Werkzeug: kleiner Audio-Schnitt (z.B. pydub/wave + Stille-Detektion). Neu zu bauen.

### B) Merge auf TAGGER-Ebene (Input/Wurzel) -- gruendlich, aber Eingriff
- Kurzsatz + Nachbar zu EINEM Audio-Tag zusammenfassen, auf der ENGLISCHEN QUELLE
  (Stage 50, VOR Uebersetzung). Dadurch erben alle Sprachfassungen dieselbe
  Tag-Struktur -> CK's Cross-Language-Disalignment-Bedenken ENTSCHAERFT.
- Genug Material pro Aeusserung -> keine Fuell-Wiederholung mehr.
- Soll-Wortzahl = Summe -> STT-Mengenpruefung bleibt korrekt.
- Manifest/Assembler sehen weiter saubere 1:1 Tag<->WAV.
- Pause des kombinierten Tags = Pause des letzten Teilsatzes.
- PREIS: gemergte Saetze nicht mehr einzeln antippbar (TAELLA). Nur fuer Saetze
  anwenden, die als Lernstoff entbehrlich sind ("Er erhielt keine Antwort.").
- Schwelle N konfigurierbar (Vorschlag <=4-5 Woerter).

## EMPFEHLUNG
- A zuerst (billig, alignment-erhaltend) an den glatten 2x-Faellen testen. Wenn die
  Erkennung "ist ~= 2*soll -> schneiden" robust ist, elegante Loesung ohne Umbau.
- B als gruendliche Langfristloesung, wenn Kurzsaetze grundsaetzlich raus sollen.
- Beide sind "neues Werkzeug bauen" -> eigene Session, nicht nebenbei.

## Heute-Stand (akzeptiert)
- Sleepy Hollow/de: 4 Kurzsatz-Doppler bleiben stehen = 99,2% sauber. Werk
  ABGESCHLOSSEN. Fix kommt mit Weg A oder B in eigener Session.
