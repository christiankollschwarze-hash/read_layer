# IDEE / KONZEPT — Batch-Vertonung & sauberes Satz-Teilen (SOMNIO-Linie)

> Festgehalten 15.06.2026. NICHT der naechste Schritt -- Board/Konzept. Erst muss
> Sleepy Hollow fertig + die TAELLA-Linie stabil sein. Hier konserviert, weil heute
> die ganze Schnitt-Frage durchrecherchiert wurde (mit Doku-Belegen).

## Das Problem (Ursprung)
Die satzweise Vertonung gibt dem Modell den Nachbarsatz-KONTEXT kuenstlich im
prompt-Feld mit ("interpret this, speak ONLY sentence 2"). Gemini-TTS haelt die
"nur die Mitte"-Grenze NICHT konstant -> vertont gelegentlich Nachbarsaetze mit
(Doppler) ODER liest Aussprache-Hinweise mit ("sprich Terry Town"). An Sleepy
Hollow/de hoerbar gehaeuft (CK: ~9 Doppler bis Satz 75).

CK-Idee: Statt Einzelsaetze BLOECKE (mehrere Saetze) in EINEM Call vertonen.
Vorteile waeren GLEICH ZWEI:
  1. Kontext ist dann PHYSISCH im Audio -> keine kuenstliche Kontext-Regie noetig
     -> Doppler-Quelle + "Hinweis-mitgelesen"-Quelle BEIDE weg.
  2. Weniger Calls -> schont das request-Limit (s. STAND_2026-06-15 TTS-Limit).
Die Herausforderung verschiebt sich damit auf: das SAUBERE TEILEN des Blocks
zurueck in satzgenaue Schnipsel (fuer TAELLA-Alignment + den Assembler).

## Die drei Schnitt-Methoden (heute durchgespielt, mit Doku-Belegen)

| Methode | Genauigkeit | Mit Charon/Gemini-Klang? |
|---|---|---|
| SSML `<mark>` Timepoints | EXAKT (ms), Modell nennt die Naht | NEIN -- nur klassische Stimmen |
| Gemini-Audio als Aligner (MM:SS) | ZU GROB (sekundengenau) | ja, aber unbrauchbar fuers Schneiden |
| faster-whisper word_timestamps | ~ms, NAEHERUNGSWEISE | JA |

### Methode 1: SSML `<mark>` -- deterministisch, aber falsche Stimme
- Du setzt `<mark name="s1"/>` zwischen die Saetze im SSML-Input; Google gibt eine
  TIMEPOINT-Liste zurueck (s1 -> 0.000s, s2 -> 3.812s ...). Die Marke steht im
  TEXT, NICHT im Audio; das Audio bleibt sauber. Du schneidest die eine WAV an den
  genannten Millisekunden. Kein Raten.
- HAKEN (Doku-belegt): Timepoints gibt es nur fuer die KLASSISCHE Cloud-TTS-API
  (SSML-faehige Stimmen: Neural2 etc.). Google verweist fuer "praezise
  Anforderungen" ausdruecklich auf die klassische API -> im Umkehrschluss:
  Gemini-TTS kann es NICHT.
  Quelle: https://docs.cloud.google.com/text-to-speech/docs/gemini-tts (DE)
- Die klassischen Stimmen wurden aber WEGEN KLANG verworfen (Magpie/Chatterbox-Test
  13.06.: "meilenweit von Gemini weg"). -> Stimme, die sauberes Teilen erlaubt, ist
  die, die wir nicht wollen. SACKGASSE fuer den Charon-Klang.

### Methode 2: Gemini als Aligner (Audio rein -> Zeitstempel) -- zu grob
- Gemini-API kann Audio VERSTEHEN und auf Zeitstempel verweisen. Verlockend, weil
  "direkt von Google" und faster-whisper ersetzend.
- HAKEN (Doku-belegt): Granularitaet ist **MM:SS** -- SEKUNDENgenau.
  Beispiel-Prompt der Doku: "Provide a transcript of the speech from 02:30 to 03:29."
  Quelle: https://ai.google.dev/gemini-api/docs/audio (DE)
- Fuer Satzschnitte zu grob: in 1 s stecken 2-3 Woerter -> Naht bis ~1 s daneben ->
  schneidet ins Wort. SCHLECHTER als Whisper. UNBRAUCHBAR fuers Schneiden.
- Nebenfund derselben Seite: `countTokens(model, contents=[audiofile])` zaehlt die
  Tokens einer AUDIODATEI vorab. Nuetzlich, um Audio-EINGABE-Kosten zu kalkulieren
  (z.B. wenn man Audio in Gemini fuettert). NICHT die TTS-Ausgabe-Tokens -- die
  kommen aus usage_metadata der TTS-Antwort. Fuers Schneiden irrelevant.

### Methode 3: faster-whisper word_timestamps -- der einzige gangbare Weg
- Block vertonen (Charon), dann per faster-whisper `word_timestamps=True` die
  Wort-Zeitstempel holen, Soll-Saetze gegen die Ist-Transkription mappen
  (Sequenz-Alignment, da Whisper-Text != Soll-Text), an Satzgrenzen schneiden.
- ~Millisekunden-genau, aber NAEHERUNGSWEISE: Naht muss auf ~50 ms sitzen, sonst
  halbes Wort. Braucht groesseres Modell als 'tiny' (small/medium), Stille-Snapping
  an der Naht, Drift im langen Block beachten (-> kurze Bloecke).
- GROSSER VORTEIL: faster-whisper ist schon im Haus (STT-Mengenpruefung, Stage 58b).
  Der Schritt von "zaehl Woerter" zu "gib Wort-Zeitstempel" ist DIESELBE Bibliothek,
  ein Parameter mehr. Kein Fremdkoerper.

## EMPFEHLUNG / Architektur-Einordnung
- **Zwei Produktlinien, zwei Methoden** -- der Zielkonflikt loest sich sauber:
  - **TAELLA (Lernen):** bleibt SATZWEISE mit Reglern (Stage 56). Doppler faengt
    die STT-Mengenpruefung + Auto-Fix (Stage 58b). Feinregie wichtig, Batch nicht
    noetig. KEIN Aenderungsbedarf.
  - **SOMNIO (Hoerbuch):** Kandidat fuer BATCH + Methode 3 (faster-whisper-Schnitt).
    Fluessiger Klang ueber Satzgrenzen, weniger Calls. Feinregie dort weniger
    kritisch.
- **Erster billiger Test, wenn es so weit ist:** faster-whisper mit
  word_timestamps=True auf EINEN 5-Satz-Block werfen und messen, wie sauber die
  Naehte sitzen. DAS entscheidet, ob der Batch-Weg fuer SOMNIO traegt -- bevor
  irgendetwas Grosses gebaut wird.
- **NICHT jetzt.** Erst Sleepy Hollow fertig, TAELLA-Linie stabil. Dann SOMNIO.

## Status der Doppler-Behebung HEUTE (kurzfristig, unabhaengig von Batch)
- Sleepy Hollow/de: Doppler haeufen sich -> erst echte Rate ueber das ganze Werk
  ziehen (Stage 58b ohne --fix), dann entscheiden:
  - Rate ~2% -> Stage 58b --fix reicht (geflaggte loeschen + Resume-Neuvertonung).
  - Rate deutlich hoeher -> an die WURZEL: Kontext-Regie in Stage 58 KUERZEN
    (kuerzerer Nachbar-Kontext = Modell vertont zuverlaessiger nur die Mitte;
    empirisch belegt 12.06.) oder bei sehr kurzen Zielsaetzen Kontext ganz weglassen.
