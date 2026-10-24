# IDEE / KONZEPT — Pipeline-Dashboard (sichere manuelle Eingriffe statt CMD)

> Festgehalten 15.06.2026. NACHSTER groesserer Schritt, sobald die Pipeline stabil
> arbeitet (CK-Regel: "solange die Pipeline nicht stabil laeuft, keine anderen
> Plaene"). Motivation direkt aus dem Schmerz des Tages: zweimal hat ein
> Kommandozeilen-Eingriff (`Remove-Item *.wav`) ein halbes Werk geloescht.

## Warum (Motivation aus dem Live-Tag)
- Die manuellen Eingriffe laufen alle ueber die PowerShell: WAVs loeschen,
  Stage 56/58/58b einzeln aufrufen, Reglerwerte in book.json von Hand eintragen,
  Report lesen. Jeder dieser Schritte ist fehleranfaellig.
- Konkreter Vorfall 15.06.: ein breites `Remove-Item "$audioDir\*.wav"` (stammte
  aus einem vorgeschlagenen "ganzes-Werk-neu"-Block) loeschte ~488 von 502 WAVs.
  Wieder herstellbar (Audio ist Ausgabeprodukt, stage06 bleibt), aber teuer
  (Vertonungsstunde + Kontingent).
- Lehre: Die teuersten Gueter (WAVs) duerfen nicht an einem unbedachten
  Sternchen-Loeschbefehl haengen. Ein UI mit Sicherheitsabfrage + Auto-Backup
  vor jedem Loeschen verhindert genau das.

## Die Bausteine existieren schon (heute gebaut)
Das Dashboard ist KEINE neue Engine -- nur eine sichere Oberflaeche auf die
heute entstandenen Funktionen:
- `stage_58b_stt_validate --only report` -> nur die geflaggten nachpruefen
- `--fix --passes N` -> geflaggte loeschen + neu wuerfeln + nachpruefen
- `tts_probe` (Gatekeeper) -> Probesaetze EN/DE mit Reglern, vor dem Vollwerk
- `tts_probe --pron-test` -> Aussprache-Formulierungen gegeneinander hoeren
- Regler in book.json (audio_regler), Sperrliste (audio_pron_skip)
- quality_report.json / _stt_report.json -> Statusquelle pro Werk

## Was das Dashboard koennen muss (aus dem Tag abgeleitet)
1. **Werk-Status auf einen Blick**
   - Wie viele WAVs existieren je Fassung (en/de/...) vs. Soll-Tags?
   - Offene Doppler-Flags (aus _stt_report.json), zu-wenige, fehlende.
   - Aktuelle Regler (betonung/emotion/tempo) + Sperrliste.
   - Welche Stages durchlaufen (stage06 da? Audio da? Assembler da?).
2. **Sichere Aktionen als Knoepfe (statt CMD)**
   - "Geflaggte neu vertonen" (= --fix), mit Sicherheitsabfrage.
   - "Gatekeeper-Probe" (n Saetze, aktuelle Regler) -> abhoeren.
   - "STT pruefen" (voll / nur Report).
   - JEDES Loeschen: vorher automatisches Backup nach audio_backup/<zeitstempel>/.
     -> Nie wieder ein halbes Werk durch einen Sternchen-Befehl weg.
3. **Regler als echte Schieberegler**
   - Drei Slider (1-10) schreiben direkt audio_regler in book.json.
   - Danach 1-Klick "Probe" -> hoeren -> "uebernehmen".
   - Loest das heutige "JSON von Hand + Komma-Gefummel"-Problem.
4. **(spaeter) Doppler-Inspektor**
   - Geflaggten Schnipsel anhoeren + Soll-Text daneben -> Mensch entscheidet
     "wirklich kaputt" vs. "Whisper-Messgrenze", statt blind --fix.

## Bauform (offen, zu entscheiden)
- Wahrscheinlich **lokales Web-UI**: kleiner lokaler Server (FastAPI/Flask) +
  Browser-Frontend, da die ganze Pipeline ohnehin lokal auf CKs Rechner laeuft
  und auf das Dateisystem (authors/.../audio, book.json, work/*.json) zugreift.
- Beruehrungspunkt mit TAELLA/LinguaReader: beide sind React-Oberflaechen auf
  dieselbe Datenstruktur (AUTOR/WERK/FASSUNG). Perspektivisch koennte das
  Pipeline-Dashboard Teil derselben Codebasis/Designsprache werden -- aber das
  ist eine bewusste Architekturentscheidung, NICHT um Mitternacht.
- MUSS lokal bleiben (Dateisystemzugriff, Service-Account-Key nie im Browser).

## Einordnung / Reihenfolge
- NICHT jetzt. Erst Pipeline stabil (TAELLA-Audiolinie sauber durch, erste Werke
  fertig). Dann Dashboard, weil es ab dann jeden manuellen Eingriff sicherer +
  schneller macht und die CMD-Fehlerquelle schliesst.
- Kleinster sinnvoller Erststein: read-only Status-Ansicht (WAV-Zahl, Flags,
  Regler) -- noch ohne Aktionen. Schon das ersetzt das CMD-Stochern beim
  Statuscheck und ist risikolos (liest nur).
