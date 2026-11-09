# STAGE-SKRIPT – Read Layer Pipeline (Stand 04.11.2026)

Je Stage: Name, Ziel, Bereich, wann sie läuft, **zuliefernde** Stages (direkte Eingänge, deren Gate frei sein muss), **folgende** Stages (die direkt auf ihr aufbauen) und **betroffene** Stages in der Kette (alle, die bei einem Neulauf veraltet sind und neu laufen müssen).

Quelle der Abhängigkeiten: `pipeline/kette.py` (VORGAENGER, Reihenfolge = `pipeline/status.STAGES`); Ziele aus `GATE_KATALOG.md`; „Produziert“ und „Mensch entscheidet“ aus `config/stage_hilfe.json` (dieselben Texte wie das Hilfe-Popup im Cockpit). Regeln: 700 kommt nach der letzten bestellten Stage (alle davor) und ist daher bei jeder Stage betroffen; unter „folgend“ steht 700 nur, wenn sonst nichts folgt; entfällt ein Zulieferer laut Bestellung (095), springt die Kette auf dessen Zulieferer.

## Reihenfolge

080 → 090 → 095 → 100 → 110 → 150 → 115 → 120 → 190 → 195 → 200 → 210 → 300 → 310 → 320 → 330 → 340 → 400 → 410 → 420 → 500 → 510 → 530 → 520 → 540 → 600 → 610 → 615 → 620 → 630 → 640 → 650 → 700 → 710

## Übersicht

| Stage | Name | Bereich | läuft bei | zuliefernd | folgend |
|---|---|---|---|---|---|
| 080 | Mandant & Rechte | Querschicht | immer | – | 090 |
| 090 | Eingangsweiche | Eingang | immer | 080 | 095 |
| 095 | Produktwahl | Eingang | immer | 090 | 100 · 150 |
| 100 | Werk anlegen | Eingang | Gutenberg, user_txt | 095 | 110 |
| 110 | Wikidata | Eingang | Gutenberg, user_txt | 100 | 115 |
| 150 | ePub-Import | Eingang | user_epub, verlag_epub | 095 | 115 |
| 115 | Fassungsweiche | Text | immer | 110 · 150 | 120 |
| 120 | Modernisierung (sanft) | Text | immer | 115 | 190 |
| 190 | Eingangsvertrag | Vertrag | immer | 120 | 195 · 600 |
| 195 | Teilung | Text | immer | 190 | 200 |
| 200 | Tagging | Text | alles außer reinem Text-ePub in Ausgangssprache | 195 | 210 |
| 210 | Profil | Text | Übersetzung oder Audio bestellt | 200 | 300 |
| 300 | Vorübersetzung | Übersetzung | Zielsprache bestellt | 210 | 310 |
| 310 | Übersetzung | Übersetzung | Zielsprache bestellt | 300 | 320 |
| 320 | Integrität | Vertrag | Zielsprache bestellt | 310 | 330 |
| 330 | Rückübersetzung | Übersetzung | Zielsprache bestellt | 320 | 340 · 400 · 600 · 630 |
| 340 | Wort-Alignment | Übersetzung | TÆLLA-Produkt in Zielsprache | 330 | 520 |
| 400 | Regie | Audio | Audio bestellt | 330 | 410 · 500 |
| 410 | Casting | Audio | Audio bestellt | 400 | 420 · 500 · 615 · 640 |
| 420 | Sprecher | Audio | Hörspiel bestellt | 410 | 510 |
| 500 | Vertonung | Audio | Audio bestellt | 400 · 410 | 510 · 530 |
| 510 | Hörspiel-Overlay | Audio | Hörspiel bestellt | 500 · 420 | 530 · 540 |
| 530 | Audio-Prüfung | Audio | Audio bestellt | 500 · 510 | 520 · 540 · 650 |
| 520 | Wortzeiten | Audio | TÆLLA-Audio | 530 · 340 | 540 |
| 540 | Trennung | Audio | Hörspiel bestellt | 510 · 530 · 520 | 700 |
| 600 | Klappentext | Vermarktung | immer | 190 · 330 | 610 · 640 |
| 610 | Cover | Vermarktung | immer | 600 | 615 |
| 615 | Cover final | Vermarktung | immer | 610 · 410 | 620 · 630 · 650 |
| 620 | ePub Ausgangssprache | Ausgabe | Kanal EPUB in Ausgangssprache | 615 · 650 | 700 |
| 630 | ePub Zielsprache | Ausgabe | Kanal EPUB in Zielsprache | 615 · 330 · 650 | 700 |
| 640 | Teaser | Vermarktung | TÆLLA-Produkt | 600 · 410 | 700 |
| 650 | Hörbuch-Assembler | Ausgabe | Hörbuch Basic für Extern oder EPUB3-Audio | 530 · 615 | 620 · 630 |
| 700 | Auslieferungs-Vertrag | Vertrag | immer | alle davor | 710 |
| 710 | Auslieferung | Ausgabe | immer | 700 | – |

## Stages im Einzelnen

### 080 Mandant & Rechte

- **Ziel:** Legt fest, wem das Werk gehört (Somnio, User, Verlag) und wer welche Aktion ausführen darf. Jede Gate-Entscheidung wird mit wer/wann protokolliert.
- **Produziert:** Mandant und Besitzer im Werk (book.json); Wer/Wann zu jeder Gate-Entscheidung im Protokoll.
- **Mensch entscheidet:** Nichts im Normalfall. Fehlt die Berechtigung, stoppt die Stage – dann entscheidet der Admin über Rolle oder Zuordnung.
- **Bereich / läuft bei:** Querschicht · immer
- **Zuliefernd:** –
- **Folgend:** 090 Eingangsweiche
- **Betroffen in der Kette (bei Neulauf):** 090 · 095 · 100 · 110 · 150 · 115 · 120 · 190 · 195 · 200 · 210 · 300 · 310 · 320 · 330 · 340 · 400 · 410 · 420 · 500 · 510 · 530 · 520 · 540 · 600 · 610 · 615 · 620 · 630 · 640 · 650 · 700 · 710 (33 Stages)
- **Gesamte Vorkette:** –

### 090 Eingangsweiche

- **Ziel:** Bestimmt die Eingangsart (Gutenberg, mitgebrachte TXT, User-/Verlags-ePub, Fremd-Audio geparkt), prüft Rechte-Versicherung und DRM und leitet zu 100 oder 150 weiter.
- **Produziert:** Eingangsart und Quellprofil im Werk; Weiterleitung zu 100 (Gutenberg/TXT) oder 150 (ePub).
- **Mensch entscheidet:** Bei fehlender Rechte-Versicherung oder Fremd-Audio stoppt die Stage. Der Mensch ergänzt die Rechteangabe oder wählt die richtige Eingangsart.
- **Bereich / läuft bei:** Eingang · immer
- **Zuliefernd:** 080 Mandant & Rechte
- **Folgend:** 095 Produktwahl
- **Betroffen in der Kette (bei Neulauf):** 095 · 100 · 110 · 150 · 115 · 120 · 190 · 195 · 200 · 210 · 300 · 310 · 320 · 330 · 340 · 400 · 410 · 420 · 500 · 510 · 530 · 520 · 540 · 600 · 610 · 615 · 620 · 630 · 640 · 650 · 700 · 710 (32 Stages)
- **Gesamte Vorkette:** 080

### 095 Produktwahl

- **Ziel:** Hält die Bestellung fest (Sprache × Inhalt × Stufe × Kanal), prüft sie gegen die Gültigkeitsmatrix und setzt daraus, welche Stages laufen und welche entfallen.
- **Produziert:** Bestellliste im Werk; Liste der Stages, die laufen bzw. entfallen.
- **Mensch entscheidet:** Bei Nutzer- und Verlagswerken bestätigt der Mensch Bestellung und Kostenangebot; BETA-Produkte immer. Ungültige Kombinationen werden korrigiert.
- **Bereich / läuft bei:** Eingang · immer
- **Zuliefernd:** 090 Eingangsweiche
- **Folgend:** 100 Werk anlegen, 150 ePub-Import
- **Betroffen in der Kette (bei Neulauf):** 100 · 110 · 150 · 115 · 120 · 190 · 195 · 200 · 210 · 300 · 310 · 320 · 330 · 340 · 400 · 410 · 420 · 500 · 510 · 530 · 520 · 540 · 600 · 610 · 615 · 620 · 630 · 640 · 650 · 700 · 710 (31 Stages)
- **Gesamte Vorkette:** 080 · 090

### 100 Werk anlegen

- **Ziel:** Legt Autor, Werk, Index-Eintrag und Rohtext (raw.txt) an. Prüft Marken, Länge, Sprache (nur Sprachliste) und EU-Gemeinfreiheit bzw. PD-/Rechte-Nachweis.
- **Produziert:** Autor- und Werkdatei, Index-Eintrag und Rohtext (raw.txt).
- **Mensch entscheidet:** Fehlt das Todesjahr oder ist der Autor zu jung verstorben, trägt der Mensch das Todesjahr ein oder belegt die Rechte (PD-Beleg, Rechteinhaber, andere Quelle). Der Rohtext kann im Editor bereinigt werden.
- **Bereich / läuft bei:** Eingang · Gutenberg, user_txt
- **Zuliefernd:** 095 Produktwahl
- **Folgend:** 110 Wikidata
- **Betroffen in der Kette (bei Neulauf):** 110 · 115 · 120 · 190 · 195 · 200 · 210 · 300 · 310 · 320 · 330 · 340 · 400 · 410 · 420 · 500 · 510 · 530 · 520 · 540 · 600 · 610 · 615 · 620 · 630 · 640 · 650 · 700 · 710 (29 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095

### 110 Wikidata

- **Ziel:** Verifiziert den Autor (Lebensdaten, Q-ID) und das Werk (Werk-Q-ID, Titel je Sprache) gegen Wikidata; zweite PD-Prüfung.
- **Produziert:** Verifizierte Autorendaten, Werk-ID, Erscheinungsjahr und Titel je Sprache.
- **Mensch entscheidet:** Bei mehreren oder keinen Treffern wählt der Mensch den richtigen Autor bzw. das Werk. Maschinell vorgeschlagene Titel werden geprüft oder ersetzt.
- **Bereich / läuft bei:** Eingang · Gutenberg, user_txt
- **Zuliefernd:** 100 Werk anlegen
- **Folgend:** 115 Fassungsweiche
- **Betroffen in der Kette (bei Neulauf):** 115 · 120 · 190 · 195 · 200 · 210 · 300 · 310 · 320 · 330 · 340 · 400 · 410 · 420 · 500 · 510 · 530 · 520 · 540 · 600 · 610 · 615 · 620 · 630 · 640 · 650 · 700 · 710 (28 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100

### 150 ePub-Import

- **Ziel:** Liest ein ePub ein: Kapitel, Text, Metadaten, Bilder/Fußnoten, Cover und vorhandenen Klappentext; prüft Inhaltsanteil, Sprache, DRM.
- **Produziert:** Kapitel, Text, Metadaten, Bilder/Fußnoten, Cover und vorhandenen Klappentext.
- **Mensch entscheidet:** Ist der erkannte Inhaltsanteil zu klein oder gibt es Warnungen, entscheidet der Mensch, welche Seiten bleiben, und korrigiert Titel, Autor, Sprache.
- **Bereich / läuft bei:** Eingang · user_epub, verlag_epub
- **Zuliefernd:** 095 Produktwahl
- **Folgend:** 115 Fassungsweiche
- **Betroffen in der Kette (bei Neulauf):** 115 · 120 · 190 · 195 · 200 · 210 · 300 · 310 · 320 · 330 · 340 · 400 · 410 · 420 · 500 · 510 · 530 · 520 · 540 · 600 · 610 · 615 · 620 · 630 · 640 · 650 · 700 · 710 (28 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095

### 115 Fassungsweiche

- **Ziel:** Legt die Fassung fest (heute modernisiert/original; entschieden: original | modernisiert | einfach | gekürzt | glace) und prüft das Bearbeitungsrecht.
- **Produziert:** Die gewählte Fassung im Werk.
- **Mensch entscheidet:** Bei Nutzer- und Verlagswerken wählt der Mensch die Fassung (mit Kostenangebot). Fehlt das Bearbeitungsrecht, stoppt die Stage.
- **Bereich / läuft bei:** Text · immer
- **Zuliefernd:** 110 Wikidata, 150 ePub-Import
- **Folgend:** 120 Modernisierung (sanft)
- **Betroffen in der Kette (bei Neulauf):** 120 · 190 · 195 · 200 · 210 · 300 · 310 · 320 · 330 · 340 · 400 · 410 · 420 · 500 · 510 · 530 · 520 · 540 · 600 · 610 · 615 · 620 · 630 · 640 · 650 · 700 · 710 (27 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150

### 120 Modernisierung (sanft)

- **Ziel:** Erkennt Kapitel (künftig eigene Stage 118) und modernisiert den Text sanft; prüft Absatzabdeckung, Längen, Ausreißer, Eigennamen, Lizenzreste.
- **Produziert:** Modernisierter Text je Kapitel.
- **Mensch entscheidet:** Weichen Kapitel oder einzelne Absätze auffällig ab (Länge, Eigennamen), prüft der Mensch die Gegenüberstellung, setzt Kapitelgrenzen oder ersetzt Absätze.
- **Bereich / läuft bei:** Text · immer
- **Zuliefernd:** 115 Fassungsweiche
- **Folgend:** 190 Eingangsvertrag
- **Betroffen in der Kette (bei Neulauf):** 190 · 195 · 200 · 210 · 300 · 310 · 320 · 330 · 340 · 400 · 410 · 420 · 500 · 510 · 530 · 520 · 540 · 600 · 610 · 615 · 620 · 630 · 640 · 650 · 700 · 710 (26 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150 · 115

### 190 Eingangsvertrag

- **Ziel:** Rein automatischer Vertrag: alle Pflichtdateien des Textwegs vorhanden, Kapitelzahl stimmig, Text deckungsgleich. Danach gilt der Werktext als fest.
- **Produziert:** Nur ein Prüfergebnis (keine neue Datei).
- **Mensch entscheidet:** Nichts – die Stage ist rein automatisch. Bei Stopp wird die Stage korrigiert, deren Datei fehlt (meist 120 oder 150).
- **Bereich / läuft bei:** Vertrag · immer
- **Zuliefernd:** 120 Modernisierung (sanft)
- **Folgend:** 195 Teilung, 600 Klappentext
- **Betroffen in der Kette (bei Neulauf):** 195 · 200 · 210 · 300 · 310 · 320 · 330 · 340 · 400 · 410 · 420 · 500 · 510 · 530 · 520 · 540 · 600 · 610 · 615 · 620 · 630 · 640 · 650 · 700 · 710 (25 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150 · 115 · 120

### 195 Teilung

- **Ziel:** Teilt sehr lange Werke (> ca. 400.000 Zeichen) an Kapitelgrenzen in Teile <slug>-1…n; danach läuft die Kette in den Teilen weiter.
- **Produziert:** Teilungsvorschlag; nach Freigabe eigene Teil-Werke (Teil 1 … n).
- **Mensch entscheidet:** Ist das Werk zu lang, nimmt der Mensch den Schnitt an, verschiebt ihn oder lehnt die Teilung ab.
- **Bereich / läuft bei:** Text · immer
- **Zuliefernd:** 190 Eingangsvertrag
- **Folgend:** 200 Tagging
- **Betroffen in der Kette (bei Neulauf):** 200 · 210 · 300 · 310 · 320 · 330 · 340 · 400 · 410 · 420 · 500 · 510 · 530 · 520 · 540 · 600 · 610 · 615 · 620 · 630 · 640 · 650 · 700 · 710 (24 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150 · 115 · 120 · 190

### 200 Tagging

- **Ziel:** Zerlegt den Text in Knoten (ein Knoten = ein Satz, Typen s/dl/p/qt/h …) mit festen IDs – das Gerüst für Übersetzung, Audio und App.
- **Produziert:** Satzliste (Knoten) mit Typ (Satz, Dialog, Überschrift …) und fester ID.
- **Mensch entscheidet:** Weicht der zerlegte Text vom Original ab oder stecken mehrere Sätze in einem Knoten, prüft der Mensch die Liste und lässt Kapitel neu zerlegen.
- **Bereich / läuft bei:** Text · alles außer reinem Text-ePub in Ausgangssprache
- **Zuliefernd:** 195 Teilung
- **Folgend:** 210 Profil
- **Betroffen in der Kette (bei Neulauf):** 210 · 300 · 310 · 320 · 330 · 340 · 400 · 410 · 420 · 500 · 510 · 530 · 520 · 540 · 600 · 610 · 615 · 620 · 630 · 640 · 650 · 700 · 710 (23 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150 · 115 · 120 · 190 · 195

### 210 Profil

- **Ziel:** Erstellt das Werkprofil: Stil, Figuren (Übersetzung, Aussprache), Unübersetztes, Glossar, Redewendungen; steuert Übersetzung und Casting.
- **Produziert:** Werkprofil: Stil, Figurenliste (mit Aussprache und Übersetzung), Glossar, Redewendungen.
- **Mensch entscheidet:** Bei Hörspiel immer, sonst bei Auffälligkeiten: Der Mensch prüft die Figurenliste (sie steuert das Casting) und korrigiert Namen.
- **Bereich / läuft bei:** Text · Übersetzung oder Audio bestellt
- **Zuliefernd:** 200 Tagging
- **Folgend:** 300 Vorübersetzung
- **Betroffen in der Kette (bei Neulauf):** 300 · 310 · 320 · 330 · 340 · 400 · 410 · 420 · 500 · 510 · 530 · 520 · 540 · 600 · 610 · 615 · 620 · 630 · 640 · 650 · 700 · 710 (22 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150 · 115 · 120 · 190 · 195 · 200

### 300 Vorübersetzung

- **Ziel:** Übersetzt kapitelweise als Anker für die satzgenaue Übersetzung (je Zielsprache).
- **Produziert:** Kapitelweise Vorübersetzung je Zielsprache.
- **Mensch entscheidet:** Nichts – rein automatisch. Problemkapitel laufen in 310 ohne Anker weiter.
- **Bereich / läuft bei:** Übersetzung · Zielsprache bestellt
- **Zuliefernd:** 210 Profil
- **Folgend:** 310 Übersetzung
- **Betroffen in der Kette (bei Neulauf):** 310 · 320 · 330 · 340 · 400 · 410 · 420 · 500 · 510 · 530 · 520 · 540 · 600 · 610 · 615 · 620 · 630 · 640 · 650 · 700 · 710 (21 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150 · 115 · 120 · 190 · 195 · 200 · 210

### 310 Übersetzung

- **Ziel:** Übersetzt jeden Knoten in jede bestellte Zielsprache; prüft Abdeckung, Sprache, Länge, Glossar, Kapitelschema.
- **Produziert:** Übersetzung je Satz und Zielsprache.
- **Mensch entscheidet:** Bleiben Sätze nach automatischer Wiederholung auffällig (falsche Sprache, Länge, Glossar), korrigiert der Mensch einzelne Sätze oder springt zum Profil (210) zurück.
- **Bereich / läuft bei:** Übersetzung · Zielsprache bestellt
- **Zuliefernd:** 300 Vorübersetzung
- **Folgend:** 320 Integrität
- **Betroffen in der Kette (bei Neulauf):** 320 · 330 · 340 · 400 · 410 · 420 · 500 · 510 · 530 · 520 · 540 · 600 · 610 · 615 · 620 · 630 · 640 · 650 · 700 · 710 (20 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150 · 115 · 120 · 190 · 195 · 200 · 210 · 300

### 320 Integrität

- **Ziel:** Rein automatischer Vertrag: ID-Menge, Quelltext und Zielsprachen gegenüber 200/310 vollständig und unverändert.
- **Produziert:** Nur ein Prüfergebnis.
- **Mensch entscheidet:** Nichts – rein automatisch. Bei Stopp wird 310 oder 200 korrigiert.
- **Bereich / läuft bei:** Vertrag · Zielsprache bestellt
- **Zuliefernd:** 310 Übersetzung
- **Folgend:** 330 Rückübersetzung
- **Betroffen in der Kette (bei Neulauf):** 330 · 340 · 400 · 410 · 420 · 500 · 510 · 530 · 520 · 540 · 600 · 610 · 615 · 620 · 630 · 640 · 650 · 700 · 710 (19 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150 · 115 · 120 · 190 · 195 · 200 · 210 · 300 · 310

### 330 Rückübersetzung

- **Ziel:** Bewertet jede Übersetzung per Rückübersetzung (Score je Satz), repariert geflaggte Sätze; liefert den endgültigen Zieltext.
- **Produziert:** Bewertung je Satz; reparierte Sätze; der endgültige Zieltext.
- **Mensch entscheidet:** Liegen zu viele Sätze unter der Schwelle (bei Verlagen immer), sieht der Mensch Original / Übersetzung / Rückübersetzung und nimmt an, lässt neu übersetzen oder ersetzt von Hand.
- **Bereich / läuft bei:** Übersetzung · Zielsprache bestellt
- **Zuliefernd:** 320 Integrität
- **Folgend:** 340 Wort-Alignment, 400 Regie, 600 Klappentext, 630 ePub Zielsprache
- **Betroffen in der Kette (bei Neulauf):** 340 · 400 · 410 · 420 · 500 · 510 · 530 · 520 · 540 · 600 · 610 · 615 · 620 · 630 · 640 · 650 · 700 · 710 (18 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150 · 115 · 120 · 190 · 195 · 200 · 210 · 300 · 310 · 320

### 340 Wort-Alignment

- **Ziel:** Ordnet Wörter Quelle ↔ Ziel zu (Anker für Wort-Tippen und Karaoke), inkl. Prüfaligner für verschobene Anker.
- **Produziert:** Wort-Zuordnungen (Anker) je Satz und Zielsprache.
- **Mensch entscheidet:** Sind Zuordnungen unvollständig oder verschoben, setzt der Mensch Anker per Klick (Quellwort → Zielwort).
- **Bereich / läuft bei:** Übersetzung · TÆLLA-Produkt in Zielsprache
- **Zuliefernd:** 330 Rückübersetzung
- **Folgend:** 520 Wortzeiten
- **Betroffen in der Kette (bei Neulauf):** 520 · 540 · 700 · 710 (4 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150 · 115 · 120 · 190 · 195 · 200 · 210 · 300 · 310 · 320 · 330

### 400 Regie

- **Ziel:** Erzeugt je Knoten und Audiosprache den Sprechtext (Zahlen, römische Ziffern, Aussprache), Pausen und bei Premium/Drama Regieanweisungen.
- **Produziert:** Sprechtext, Pausen und Regiehinweise je Satz und Audiosprache.
- **Mensch entscheidet:** Bleiben Sprechtext-Fehler oder fehlt bei Premium die Aussprache, prüft der Mensch Text und Sprechtext (mit Hörprobe) und pflegt die Aussprache.
- **Bereich / läuft bei:** Audio · Audio bestellt
- **Zuliefernd:** 330 Rückübersetzung
- **Folgend:** 410 Casting, 500 Vertonung
- **Betroffen in der Kette (bei Neulauf):** 410 · 420 · 500 · 510 · 530 · 520 · 540 · 615 · 620 · 630 · 640 · 650 · 700 · 710 (14 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150 · 115 · 120 · 190 · 195 · 200 · 210 · 300 · 310 · 320 · 330

### 410 Casting

- **Ziel:** Besetzt Erzähler und (Hörspiel) Figuren mit Stimmen; prüft Passung und Abstand; casting.json ist die einzige Stimmablage.
- **Produziert:** Besetzung (casting.json): Stimme je Rolle und Sprache.
- **Mensch entscheidet:** Bei neu entworfenen Stimmen und immer beim Hörspiel: Der Mensch hört Proben, besetzt um und gibt das Casting frei.
- **Bereich / läuft bei:** Audio · Audio bestellt
- **Zuliefernd:** 400 Regie
- **Folgend:** 420 Sprecher, 500 Vertonung, 615 Cover final, 640 Teaser
- **Betroffen in der Kette (bei Neulauf):** 420 · 500 · 510 · 530 · 520 · 540 · 615 · 620 · 630 · 640 · 650 · 700 · 710 (13 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150 · 115 · 120 · 190 · 195 · 200 · 210 · 300 · 310 · 320 · 330 · 400

### 420 Sprecher

- **Ziel:** Ordnet jedem Satzsegment den Sprecher zu (Erzähler oder Figur) – Drehbuch fürs Hörspiel.
- **Produziert:** Sprecherzuordnung je Satzsegment (das Drehbuch).
- **Mensch entscheidet:** Bei unsicheren Zuordnungen (bei Verlagen immer) wählt der Mensch den Sprecher je Segment oder teilt Segmente.
- **Bereich / läuft bei:** Audio · Hörspiel bestellt
- **Zuliefernd:** 410 Casting
- **Folgend:** 510 Hörspiel-Overlay
- **Betroffen in der Kette (bei Neulauf):** 510 · 530 · 520 · 540 · 620 · 630 · 650 · 700 · 710 (9 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150 · 115 · 120 · 190 · 195 · 200 · 210 · 300 · 310 · 320 · 330 · 400 · 410

### 500 Vertonung

- **Ziel:** Vertont jeden Satz (Basic Chatterbox, Premium/Drama Gemini) nach Kostenfreigabe; prüft jeden Satz per Forced Alignment.
- **Produziert:** Eine Audiodatei je Satz und Audiosprache (Rohfassung).
- **Mensch entscheidet:** Liegen die Kosten über dem Budget, gibt der Mensch frei. Auffällige Sätze hört er an und lässt sie neu vertonen oder nimmt sie an.
- **Bereich / läuft bei:** Audio · Audio bestellt
- **Zuliefernd:** 400 Regie, 410 Casting
- **Folgend:** 510 Hörspiel-Overlay, 530 Audio-Prüfung
- **Betroffen in der Kette (bei Neulauf):** 510 · 530 · 520 · 540 · 620 · 630 · 650 · 700 · 710 (9 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150 · 115 · 120 · 190 · 195 · 200 · 210 · 300 · 310 · 320 · 330 · 400 · 410

### 510 Hörspiel-Overlay

- **Ziel:** Erzeugt Figuren-Takes und montiert sie in die Hörspielspur; die Hörbuchspur bleibt unberührt.
- **Produziert:** Hörspielspur je Satz mit Figurenanteil; die Hörbuchspur bleibt unverändert.
- **Mensch entscheidet:** Die Hörspiel-Freigabe macht immer ein Mensch (Hörprobe je Figur); auffällige Sätze werden neu gebaut oder in Erzählerfassung belassen.
- **Bereich / läuft bei:** Audio · Hörspiel bestellt
- **Zuliefernd:** 500 Vertonung, 420 Sprecher
- **Folgend:** 530 Audio-Prüfung, 540 Trennung
- **Betroffen in der Kette (bei Neulauf):** 530 · 520 · 540 · 620 · 630 · 650 · 700 · 710 (8 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150 · 115 · 120 · 190 · 195 · 200 · 210 · 300 · 310 · 320 · 330 · 400 · 410 · 420 · 500

### 530 Audio-Prüfung

- **Ziel:** Erstellt die Endfassung: Ränder, Tempo, Lautheit je Kapitel, Sprachprüfung je Satz; gekippte Sätze zurück an 500/510.
- **Produziert:** Endfassung des Audios je Satz; Pegel je Kapitel.
- **Mensch entscheidet:** Bei zu vielen Verdachtsfällen hört der Mensch die Liste (Roh/Endfassung) und lässt Sätze neu bauen, neu vertonen oder nimmt sie mit Grund an.
- **Bereich / läuft bei:** Audio · Audio bestellt
- **Zuliefernd:** 500 Vertonung, 510 Hörspiel-Overlay
- **Folgend:** 520 Wortzeiten, 540 Trennung, 650 Hörbuch-Assembler
- **Betroffen in der Kette (bei Neulauf):** 520 · 540 · 620 · 630 · 650 · 700 · 710 (7 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150 · 115 · 120 · 190 · 195 · 200 · 210 · 300 · 310 · 320 · 330 · 400 · 410 · 420 · 500 · 510

### 520 Wortzeiten

- **Ziel:** Misst Wortzeiten auf der Endfassung (Karaoke) und überträgt sie über die Anker (525) auf die andere Sprache.
- **Produziert:** Zeitstempel je Wort und Satz.
- **Mensch entscheidet:** Sind Wortzeiten auffällig, prüft der Mensch die Karaoke-Vorschau, lässt neu messen oder verschiebt Wortgrenzen.
- **Bereich / läuft bei:** Audio · TÆLLA-Audio
- **Zuliefernd:** 530 Audio-Prüfung, 340 Wort-Alignment
- **Folgend:** 540 Trennung
- **Betroffen in der Kette (bei Neulauf):** 540 · 700 · 710 (3 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150 · 115 · 120 · 190 · 195 · 200 · 210 · 300 · 310 · 320 · 330 · 340 · 400 · 410 · 420 · 500 · 510 · 530

### 540 Trennung

- **Ziel:** Prüft, ob Figurenstimmen hörbar vom Erzähler getrennt sind (ECAPA); Nachrunde oder Umbesetzen.
- **Produziert:** Messergebnis je Figur (Stimmabstand).
- **Mensch entscheidet:** Ist eine Figur nicht klar getrennt, entscheidet der Mensch nach Hörprobe: umbesetzen oder annehmen.
- **Bereich / läuft bei:** Audio · Hörspiel bestellt
- **Zuliefernd:** 510 Hörspiel-Overlay, 530 Audio-Prüfung, 520 Wortzeiten
- **Folgend:** 700 Auslieferungs-Vertrag
- **Betroffen in der Kette (bei Neulauf):** 700 · 710 (2 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150 · 115 · 120 · 190 · 195 · 200 · 210 · 300 · 310 · 320 · 330 · 340 · 400 · 410 · 420 · 500 · 510 · 530 · 520

### 600 Klappentext

- **Ziel:** Übernimmt oder erzeugt den Klappentext (Köder, Einordnung, Autor) je Sprache mit Pflichtvermerken; Metadaten für Cover und Teaser.
- **Produziert:** Klappentext je Sprache (Köder, Einordnung, Autor) und Metadaten wie Genre und Ton.
- **Mensch entscheidet:** Bei Nutzer- und Verlagswerken und bei Auffälligkeiten (Autorfakten, Sicherheit) prüft der Mensch die Shop-Vorschau und korrigiert Sätze.
- **Bereich / läuft bei:** Vermarktung · immer
- **Zuliefernd:** 190 Eingangsvertrag, 330 Rückübersetzung
- **Folgend:** 610 Cover, 640 Teaser
- **Betroffen in der Kette (bei Neulauf):** 610 · 615 · 620 · 630 · 640 · 650 · 700 · 710 (8 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150 · 115 · 120 · 190 · 195 · 200 · 210 · 300 · 310 · 320 · 330

### 610 Cover

- **Ziel:** Erzeugt die Cover-Illustration (ohne Text) einmal je Werk und prüft sie bildtechnisch.
- **Produziert:** Cover-Illustration.
- **Mensch entscheidet:** Fällt die Bildprüfung durch (oder bei Nutzer-/Verlagswerken), gibt der Mensch ein Motiv vor, wählt eine Variante oder lädt ein eigenes Bild hoch.
- **Bereich / läuft bei:** Vermarktung · immer
- **Zuliefernd:** 600 Klappentext
- **Folgend:** 615 Cover final
- **Betroffen in der Kette (bei Neulauf):** 615 · 620 · 630 · 650 · 700 · 710 (6 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150 · 115 · 120 · 190 · 195 · 200 · 210 · 300 · 310 · 320 · 330 · 600

### 615 Cover final

- **Ziel:** Setzt Titel, Autor, Vermerke und ggf. Sprecher auf die Illustration – je Sprache × Variante (Text, Audio, quadratisch); einmalige Sichtfreigabe.
- **Produziert:** Fertige Cover je Sprache und Variante (Text, Audio, quadratisch).
- **Mensch entscheidet:** Einmal je Werk sieht der Mensch alle Cover und gibt sie frei; Titel, Umbruch und Schrift lassen sich mit Vorschau anpassen.
- **Bereich / läuft bei:** Vermarktung · immer
- **Zuliefernd:** 610 Cover, 410 Casting
- **Folgend:** 620 ePub Ausgangssprache, 630 ePub Zielsprache, 650 Hörbuch-Assembler
- **Betroffen in der Kette (bei Neulauf):** 620 · 630 · 650 · 700 · 710 (5 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150 · 115 · 120 · 190 · 195 · 200 · 210 · 300 · 310 · 320 · 330 · 400 · 410 · 600 · 610

### 620 ePub Ausgangssprache

- **Ziel:** Baut das ePub der Ausgangssprache (Text, bei Hörbuch Basic EPUB3 mit Media Overlay); epubcheck Pflicht.
- **Produziert:** ePub-Datei (Text, bei Hörbuch Basic auch mit Audio).
- **Mensch entscheidet:** Bei Verlagen immer (Vorschau), sonst nur bei zusammengeklebten Absätzen.
- **Bereich / läuft bei:** Ausgabe · Kanal EPUB in Ausgangssprache
- **Zuliefernd:** 615 Cover final, 650 Hörbuch-Assembler
- **Folgend:** 700 Auslieferungs-Vertrag
- **Betroffen in der Kette (bei Neulauf):** 700 · 710 (2 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150 · 115 · 120 · 190 · 195 · 200 · 210 · 300 · 310 · 320 · 330 · 400 · 410 · 420 · 500 · 510 · 530 · 600 · 610 · 615 · 650

### 630 ePub Zielsprache

- **Ziel:** Baut das ePub je Zielsprache aus dem Text nach 330 (Text bzw. Audio-Variante).
- **Produziert:** ePub-Datei je Zielsprache.
- **Mensch entscheidet:** Wie 620.
- **Bereich / läuft bei:** Ausgabe · Kanal EPUB in Zielsprache
- **Zuliefernd:** 615 Cover final, 330 Rückübersetzung, 650 Hörbuch-Assembler
- **Folgend:** 700 Auslieferungs-Vertrag
- **Betroffen in der Kette (bei Neulauf):** 700 · 710 (2 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150 · 115 · 120 · 190 · 195 · 200 · 210 · 300 · 310 · 320 · 330 · 400 · 410 · 420 · 500 · 510 · 530 · 600 · 610 · 615 · 650

### 640 Teaser

- **Ziel:** Vertont den Klappentext als Hör-Teaser für das Katalog-Schaufenster der App.
- **Produziert:** Gesprochener Klappentext je Sprache.
- **Mensch entscheidet:** Bei auffälligen Sätzen (bei Verlagen immer) hört der Mensch die Liste und lässt neu vertonen.
- **Bereich / läuft bei:** Vermarktung · TÆLLA-Produkt
- **Zuliefernd:** 600 Klappentext, 410 Casting
- **Folgend:** 700 Auslieferungs-Vertrag
- **Betroffen in der Kette (bei Neulauf):** 700 · 710 (2 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150 · 115 · 120 · 190 · 195 · 200 · 210 · 300 · 310 · 320 · 330 · 400 · 410 · 600

### 650 Hörbuch-Assembler

- **Ziel:** Fügt die Satz-Clips zu Kapiteldateien (MP3/M4B) mit Ansagen, Metadaten, Cover und Satz-Zeitmarken zusammen.
- **Produziert:** Kapiteldateien (MP3/M4B) und Zeitmarken je Satz.
- **Mensch entscheidet:** Bei externen Kanälen einmal je Sprache: Hörprobe von Anfang, Schluss und Ansagen.
- **Bereich / läuft bei:** Ausgabe · Hörbuch Basic für Extern oder EPUB3-Audio
- **Zuliefernd:** 530 Audio-Prüfung, 615 Cover final
- **Folgend:** 620 ePub Ausgangssprache, 630 ePub Zielsprache
- **Betroffen in der Kette (bei Neulauf):** 620 · 630 · 700 · 710 (4 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150 · 115 · 120 · 190 · 195 · 200 · 210 · 300 · 310 · 320 · 330 · 400 · 410 · 420 · 500 · 510 · 530 · 600 · 610 · 615

### 700 Auslieferungs-Vertrag

- **Ziel:** Prüft vor jeder Auslieferung, dass für jedes bestellte Produkt alle Pflicht-Artefakte vorhanden, frei und aktuell sind.
- **Produziert:** Prüfbericht je Produkt, Sprache und Kanal.
- **Mensch entscheidet:** Bei Verlagen die Endabnahme. Sonst nichts – fehlt etwas, springt die Kette zur verursachenden Stage.
- **Bereich / läuft bei:** Vertrag · immer
- **Zuliefernd:** alle bestellten Stages davor
- **Folgend:** 710 Auslieferung
- **Betroffen in der Kette (bei Neulauf):** 710 (1 Stages)
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150 · 115 · 120 · 190 · 195 · 200 · 210 · 300 · 310 · 320 · 330 · 340 · 400 · 410 · 420 · 500 · 510 · 530 · 520 · 540 · 600 · 610 · 615 · 620 · 630 · 640 · 650

### 710 Auslieferung

- **Ziel:** Liefert aus: TÆLLA-Cloud (Manifest, Audio, Wortzeiten, Cover, Teaser), EPUB-Download, Extern-Paket; erstes Freischalten im Katalog durch Mensch.
- **Produziert:** Hochgeladene Dateien, Katalogeintrag, ePub-Download bzw. Plattform-Paket.
- **Mensch entscheidet:** Das erste Freischalten im öffentlichen Katalog und der Upload auf externe Plattformen erfolgen durch den Menschen.
- **Bereich / läuft bei:** Ausgabe · immer
- **Zuliefernd:** 700 Auslieferungs-Vertrag
- **Folgend:** –
- **Betroffen in der Kette (bei Neulauf):** –
- **Gesamte Vorkette:** 080 · 090 · 095 · 100 · 110 · 150 · 115 · 120 · 190 · 195 · 200 · 210 · 300 · 310 · 320 · 330 · 340 · 400 · 410 · 420 · 500 · 510 · 530 · 520 · 540 · 600 · 610 · 615 · 620 · 630 · 640 · 650 · 700

## Entschieden, noch nicht in der Kette (Fassungsweiche 115, CK 03.11.2026)

| Stage | Name | Ziel | zuliefernd | folgend |
|---|---|---|---|---|
| 118 | Kapitel | Kapitelplan manuell prüfbar (aus 120 herausgelöst), läuft bei allen Fassungen und nach 150 (übernimmt Verlags-Kapitelprüfung) | 115 (bzw. 150) | 120 / 122 / 124 / 125 |
| 122 | Einfache Sprache | Fassung „einfach“ | 118 | 190 |
| 124 | Gekürzte Lesung | Fassung „gekürzt“ (Nummer Vorschlag) | 118 | 190 |
| 125 | Glace | Fassung „glace“ | 118 | 190 |

Außerhalb der Pipeline: 900 LoRA-Training, 910 Sprecherauswahl LibriVox (Schnittstelle nur über freigegebene Adapter in 410/500). 345 ist Teil von 340, 525 Teil von 520.
