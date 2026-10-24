# IDEE / VEREDELUNG — Mehrstimmige Vertonung (Figurenstimmen)

> Festgehalten 13.06.2026. Bewusst als spaeteres Premium-Feature ("Veredelung"),
> NICHT als naechster Schritt. Erst muss die Basis-Vertonung (eine Stimme, sauber,
> satzgenaues Alignment) stehen und gut klingen.

## Die Idee (CK)
Statt innerhalb eines Satzes nur die Stimmlage zu wechseln, jeder FIGUR eine
eigene Gemini-Stimme zuweisen. Erzaehler = eine Stimme (z.B. Charon), Figuren
je eine andere. Pro Schnipsel waehlt Stage 58 die passende Stimme.

## Warum das zur bestehenden Architektur passt (gut!)
- Gemini-TTS Multi-Speaker (mehrere Stimmen in EINEM Job) ist laut Doku
  UNZUVERLAESSIG — beide Sprecher rendern teils mit gleichem Timbre.
- Der von Google EMPFOHLENE Weg fuer echte Figurenstimmen ist exakt READ LAYERs
  Architektur: jede Sprecherzeile als EIGENER Single-Speaker-Job, dann
  zusammenfuegen. Heisst: KEIN Architektur-Umbau noetig, nur Erweiterung —
  pro dl-Schnipsel ein `voice`-Feld, Stage 58 waehlt danach.
- Satzgenaues Alignment bleibt erhalten (jeder Satz weiter ein Schnipsel).

## Was schon da ist (halber Weg gebaut)
- Profiler (Stage 51) liest `profile.characters` bereits aus — urspruenglich
  fuer korrekte Namens-Aussprache (Beispiel-Erinnerung: "Glöckner von Notre Dame",
  Aussprache "Dauphin"). Diese Figurenliste ist die Grundlage fuer Stimm-Zuweisung.

## Der harte Teil (das eigentliche Risiko)
- Schwer ist NICHT die Stimm-Zuweisung, sondern die SPRECHER-IDENTIFIKATION:
  Wer spricht welchen Dialogsatz? Oft steht keine Attribution im Text
  ("sagte Utterson" fehlt bei Wechselrede). Muss inferiert werden.
- Bei langen unattribuierten Dialogen kann die Zuweisung kippen -> falsche
  Figur mit falscher Stimme. Fuer Lernprodukt verwirrend, fuer Hoerbuch Bruch.
- CK-Einschaetzung: traut Gemini Pro zu, die Sprecher korrekt zu identifizieren.
  "Käme auf den Versuch an." -> als Experiment offen, nicht vorab verworfen.

## Einordnung / Empfehlung
- Premium-Merkmal fuer eine DRAMATISIERTE SOMNIO-Hoerbuch-Linie.
- Fuer das SPRACHLERN-Audio eher EINE konsistente Stimme pro Sprache
  (didaktisch klarer; Zuweisungsfehler waeren dort ein echtes Risiko).
- Reihenfolge: erst Basis-Vertonung solide, DANN Mehrstimmigkeit obendrauf.

## Konkreter erster Test, wenn es so weit ist (billig)
- Sprecher-Identifikation als eigene Analyse-Stufe (LLM, Gemini Pro) auf einem
  dialogreichen Kapitel testen: liefert sie wer-spricht-was zuverlaessig?
- Parallel: denselben Satz durch mehrere Erzaehlstimmen jagen (Charon/Orus/
  Kore/Zephyr) — tts_prosody_test.py um variable Stimme erweitern (2-Satz-Probe
  kostet fast nichts).

## Technische Fakten (Gemini-TTS, recherchiert 13.06.2026)
- 30 Stimmen, nach astronomischen Koerpern benannt, Default "Puck".
- Erzaehlung empfohlen: Charon, Orus. Neutral: Kore, Zephyr. Dramatisch: Fenrir, Puck.
- Geschlechtsaufteilung der 30 Stimmen NICHT verlaesslich aus Doku ablesbar —
  in Google AI Studio / Cloud-Console pro Stimme angezeigt + anhoerbar. Dort verifizieren.
- Multi-Speaker-Config: max. 2 Sprecher, differenziert Timbre NICHT zuverlaessig.
- Stimme pro Figur ueber alle Kapitel KONSISTENT halten (Modell nicht stateful).
