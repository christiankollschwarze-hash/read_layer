# TODO / KONZEPT — Kurzsatz-Doppler [Update 3, 18.06.2026 — WEG A GEBAUT]

> Prompt-Weg ist tot (4 Varianten, siehe unten). WEG A (Audio-Schnitt) ist jetzt
> GEBAUT und an Sleepy Hollow BEWAEHRT. WEG B (Tagger-Merge) bleibt optional.

## Befund (unveraendert)
Gemini-TTS verdoppelt sehr kurze Saetze (<6 W) durch Wiederholung. Deterministisch,
sitzt unterhalb der Prompt-Ebene. Sleepy Hollow/de hatte 4 solche Faelle
(00403, 00455, 00458, 00460).

## ERLEDIGTE SACKGASSE: Prompt-Haertung (4 Varianten, alle 8/8/8)
1. Generisch "Do NOT repeat..." 2. Verschaerft "say once, stop, single utterance"
3. Nachgestellt "task complete, do not repeat the previous sentence"
4. Numerisch "Read the sentence 1 time, exactly 1 spoken instance"
ALLE wirkungslos. Prompt-Weg definitiv tot, nicht erneut versuchen.

## WEG A — AUDIO-SCHNITT (GEBAUT, BEWAEHRT) ✓
Werkzeug: **audio_cut.py** (Wurzelverzeichnis, nur stdlib `wave`, keine Abhaengigkeit).

Prinzip: kurzer Satz wird doppelt gesprochen -> WAV an der Naht zwischen den zwei
Durchlaeufen schneiden, hintere Haelfte verwerfen. EINE WAV pro Tag bleibt ->
Alignment erhalten, kein Cross-Language-Problem, kein Datenmodell-Umbau.

Schnittpunkt: STILLE-NAHT-Erkennung (RMS-Minimum im Band [40%,60%] der Dauer,
leicht zur Mitte gewichtet). An Sleepy Hollow getroffen: bei allen 4 Faellen exakt
richtig (auch beim unsauberen 00403: erkannt 4.37s = Mitte, Schnitt sass).

### Workflow (halbautomatisch, mit Ohr-Kontrolle)
1. `python -m pipeline.stage_58b_stt_validate <book> --lang de`
   -> flaggt too_many in _stt_report.json
2. `python tools\audio_cut.py <book> --lang de --from-report`
   -> pro geflaggtem Tag: Stille-Naht-Vorschau <tag>_cut.wav + interaktive Frage:
        [c]ut   -> uebernehmen (commit, Original -> _orig.wav)
        [l]eave -> stehen lassen (Vorschau verwerfen)
        [m SEK] -> mit eigener Sekunde neu schneiden, dann erneut fragen
        [s]kip  -> ueberspringen (Vorschau bleibt)
        [q]uit  -> Stapel abbrechen
   -> Bilanz am Ende. --auto schaltet Abfrage ab (blind committen, NICHT empfohlen).

### Einzel-Modus (Notfall/Feintuning)
  --info     Dauer + Mitte + erkannte Stille-Naht
  --silence  Vorschau per Stille-Naht
  --at SEK   Vorschau manuell
  --commit   uebernehmen   --revert   aus _orig.wav zurueck

### Sicherheitsnetz
  - Schnitt schreibt zuerst <tag>_cut.wav, Original unangetastet.
  - --commit sichert Original nach <tag>_orig.wav (reversibel via --revert).
  - 58b-Flag bleibt das Ventil: nur invalide Tags kommen ueberhaupt in den Stapel.

### Rolle in der Pipeline
  Eigenstaendiges Werkzeug NACH 58b (nicht in 58b integriert -- bewusst, weil das
  Ohr im Loop bleibt). Pro Werk ein kurzer Schritt: 58b -> audio_cut --from-report.

## WEG B — Tagger-Merge (OPTIONAL, nicht gebaut)
Nur falls Kurzsaetze GRUNDSAETZLICH raus sollen (statt nachtraeglich schneiden):
Kurzsatz + Nachbar zu EINEM Tag auf der englischen Quelle (Stage 50, vor
Uebersetzung) -> keine Wiederholung, alle Sprachen erben gleiche Struktur.
PREIS: gemergte Saetze nicht einzeln antippbar (TAELLA). Mit Weg A gebaut ist
B vorerst NICHT noetig.

## STATUS
- Sleepy Hollow/de: alle 4 Doppler geschnitten -> 0 Flags, 100% sauber. ABGESCHLOSSEN.
- audio_cut.py bewaehrt -> Standard-Reparaturschritt fuer kuenftige Werke.
