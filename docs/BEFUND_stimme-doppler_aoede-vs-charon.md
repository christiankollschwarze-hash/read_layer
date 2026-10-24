# BEFUND — Stimme beeinflusst Doppler-Rate (Aoede vs. Charon)

> Festgehalten 18.06.2026. Relevant fuer kuenftige Stimmwahl pro Werk.

## Beobachtung (empirisch, gemessen + gehoert)
- **Charon / Sleepy Hollow / de**: mehrere hartnaeckige Kurzsatz-Doppler
  (Saetze <5 Woerter werden verdoppelt). Deterministisch, durch keinen Prompt
  zu beheben -> mussten per audio_cut.py geschnitten werden.
- **Aoede / The Yellow Wallpaper**:
  - EN, 258 Schnipsel: **0 Doppler**.
  - DE, 258 Schnipsel: **0 Doppler** (1 Satz ABGESCHNITTEN "zu wenig" --
    andere Fehlerklasse, durch gezieltes Neu-Vertonen behoben).

## Schlussfolgerung
Die Doppler-Neigung bei kurzen Saetzen haengt NICHT nur von der Satzlaenge ab,
sondern auch von der STIMME (bzw. Stimme-Sprache-Kombination). Aoede ist in
beiden Sprachen deutlich doppler-resistenter als Charon.

## Konsequenz fuer die Produktion
- Stimmwahl ist auch ein QUALITAETS-Hebel, nicht nur Klangfarbe.
- Vor einem Vollwerk lohnt ein kurzer Doppler-Test der Kandidatenstimme an
  einem kurzsatzreichen Abschnitt (tts_probe / Mini-Lauf).
- Aoede = bewaehrte doppler-arme Stimme (weiblich). Charon (maennlich) braucht
  bei kurzsatzreichen Werken die audio_cut-Nachbearbeitung.
- OFFEN: weitere Stimmen entsprechend einordnen (Orus, Kore, Zephyr ...) --
  pro Stimme einmal ein kurzsatzreicher Test, Ergebnis hier sammeln.

## Verbleibende Fehlerklasse (stimmunabhaengig)
- "Zu wenig / abgeschnitten": einzelner Schnipsel wird unvollstaendig vertont.
  Nicht-deterministisch -> gezielt neu vertonen (WAV loeschen, stage_58 Resume),
  mit dem Ohr nachpruefen. Trat bei Aoede/DE genau 1x auf.

## Status der zwei ersten Werke
- Sleepy Hollow (Charon): 100% sauber nach manuellem Schnitt. ABGESCHLOSSEN.
- The Yellow Wallpaper (Aoede): EN + DE je 0 Doppler, 1 abgeschnittener Satz
  repariert. ABGESCHLOSSEN.
