# IDEE / ZUSATZPRODUKTE — Fassungsvarianten: TAELLA Glace, gekuerzte Lesung, Einfache Sprache

> Festgehalten 03.11.2026 (aktualisiert 12:52). Zusatzprodukte / Aufpreis-Optionen,
> NICHT naechster Schritt. Zeitpunkt: nach Neuaufbau Cockpit, VOR dem Frontend.

## Ueberblick: drei Varianten aus EINEM Knotenbestand

| Fassung (`fassung`) | Inhalt                                         | Laenge        |
|---------------------|------------------------------------------------|---------------|
| (Vollfassung)       | alle Knoten                                    | 100 %         |
| `gekuerzt`          | Auswahl von Originalknoten, nur Streichungen   | ca. 40-60 %   |
| `glace`             | wenige Originalknoten (Zitate) + neuer Erzaehltext | ca. 15 Min. |
| `einfach`           | Satz-fuer-Satz umformuliert (Einfache Sprache) | ~100 %        |

- Jede Variante = eigenes Produkt: eigener Titel, eigene ID, eigener Katalogeintrag,
  unabhaengig produziert und vertrieben.
- Verknuepfung im Datenmodell ueber `stamm_id` (Verweis aufs Ausgangswerk):
  Wiederverwendung von Zitatknoten/Uebersetzung/Audio + Sprung zwischen Fassungen
  in der App ("Hier weiterhoeren" / "Auch erhaeltlich als ...").
- Weiche: Stage Modernisierung (190). Einfache Sprache passt direkt dorthin
  (gleiche Logik wie "sanft modernisiert", nur staerker; Struktur bleibt -> Rest
  der Pipeline unveraendert). Glace ist strukturell (braucht ganzes Werk) ->
  nutzt die Weiche, braucht aber eigenen Verdichtungsschritt.

## Cockpit-Neuaufbau: JETZT schon im Datenmodell vorsehen
- `fassung` als offene Werteliste (nicht nur modernisiert ja/nein):
  modernisiert, einfach, gekuerzt, glace, ...
- Feld `stamm_id` im Werk-Datensatz (darf leer sein).
- Bedienelemente koennen spaeter kommen, die Felder nicht.

## Teaser ist bereits abgedeckt
- s600 Klappentext + s640 Teaser-Audio = Teaser. Keine eigene Teaser-Variante noetig.
- s600 enthaelt das Zitat-Prinzip schon im Kleinen: Koeder-Passage ueber
  `koeder_ids`, Zielsprachen = dieselben Knoten aus 330 (nie frei uebersetzt).
  Metadaten `hauptfiguren`, `essenz`, `ton`, `genre` vorhanden -> Glace baut
  auf diesem Muster auf (ein Zitat -> Zitat-Bestand).

## 1. Gekuerzte Lesung (`gekuerzt`)
- Nur Originaltext, nur Streichungen (Saetze/Absaetze) -> keine Halluzination moeglich.
- Knoten-IDs bleiben -> Uebersetzung, Sprechanweisungen, Alignment, Audio
  wiederverwendbar; bei fertigem Stammwerk kaum neue Vertonung.
- LLM schlaegt Streichungen vor (Nebenhandlungen, Beschreibungen, Wiederholungen);
  Pruefung: Handlung lueckenlos? Schnittstellen sauber?
- Ueberleitungssaetze nur ausnahmsweise, gekennzeichnet + geprueft.
- Rechte: bei geschuetzten Werken Bearbeitung -> Zustimmung Autor/Verlag.

## 2. Einfache Sprache (`einfach`)
- Begriff "Einfache Sprache" offen nutzen (nicht geschuetzt; Normen DIN ISO 24495-1 /
  DIN 8581-1 freiwillig). NICHT mit DIN-Konformitaet werben, solange nicht geprueft.
- "Leichte Sprache" meiden (Erwartung geprueft durch Zielgruppe, DIN SPEC 33429;
  ohne Pruefgruppe nicht glaubwuerdig). Oeffentliche Ausschreibungen damit ausser Reichweite.
- Abnehmer: Schulen, Deutschlernende (DaZ), Bibliotheken; PD-Klassiker rechtlich frei,
  passt zum Sprachlern-Strang.
- Nebenaspekt BFSG: § 18 BFSGV verlangt bei E-Books mit Audio synchrone Text-Audio-
  Bereitstellung -> satzgenaues Alignment + EPUB3 als Verlagsdienstleistung
  "barrierefreies EPUB3" (EPUB3 selbst muss zusaetzlich WCAG / EPUB Accessibility 1.1 erfuellen).

## 3. TAELLA Glace (`glace`) — Kurzfassung im Blinkist-Format
Name: CK nennt das Format "Glace"; extern nur als "TAELLA Glace" ("tell a glace").
~15 Min. (~3.500 Woerter, 8-10 Abschnitte), Text (EPUB3) + Audio.
Kosten: Audio ca. 2-3 % eines vollen Hoerbuchs, LLM-Verdichtung Cent-Betrag.

### Varianten
- Lektuerehilfe (PD-Klassiker): vollstaendige Handlung; Schueler/Studenten;
  keine Kannibalisierung (kein Buchverkauf zu schuetzen, Geschaeft = Patenschaft).
- Verlagstitel: Verlag entscheidet ob/wie (ggf. ohne Aufloesung).
- Belletristik: Inhaltsangabe mit Figuren/Themen statt "Kernideen" (Sachbuch).

### Kernprinzip gegen Halluzinationen
**Zitate frueh und breit markieren, spaet und streng auswaehlen, nie frei ausschreiben.**
1. Woertliche Rede / Gedanken werden NIE verdichtet oder umformuliert.
2. Vorübersetzung bzw. Textdurchlauf markiert Zitat-KANDIDATEN grosszuegig, mit
   Kurzbegruendung ("Wendepunkt", "Leitmotiv") — Relevanz zeigt sich oft erst spaeter.
3. Glace-Schritt (kennt ganzes Werk) waehlt NUR aus diesem Bestand, hinzufuegen verboten.
4. Platzhalter statt Text (`{Q-0417}`), Pipeline fuegt Original ein -> Wortlaut
   weder veraenderbar noch erfindbar.
5. Zitate tragen Sprechanweisungen mit; bei Uebersetzung identisch mit Vollfassung.

Metadaten je Kandidat: ID, Position (Kapitel/Absatz-ID aus Alignment), Sprecher,
Begruendung, Sprechanweisung.

### Pruefung der Einbettung ("Kausalitaet")
| Pruefung    | Wie                                                         | Aufwand      |
|-------------|-------------------------------------------------------------|--------------|
| Sprecher    | Sprecher-Metadatum vs. Zuschreibung                          | regelbasiert |
| Chronologie | Reihenfolge Platzhalter-IDs vs. Werkposition (Rueckblende = Ausnahme) | regelbasiert |
| Kausalitaet | LLM: Satz + Originalstelle +/- einige Absaetze; nur Saetze mit "weil/deshalb/daraufhin" | LLM |
Erzaehlter Teil: jeder Satz mit Quellmarke, zweiter guenstiger LLM-Durchlauf Satz fuer
Satz; Durchfaller -> Microjobber (extra abrechenbar).
Synergie: Sprecher-Identifikation auch fuer IDEE_mehrstimmigkeit.md.

### Markt / Positionierung
- Blinkist: Blinks von eigener Redaktion, Profi-Sprecher, nur Sachbuch; Verlage liefern
  Lizenz, nicht Produkt -> "direkt an Blinkist liefern" unrealistisch.
- Blinkist (seit 2023 Teil von Go1, Kaufpreis geschaetzt 100-200 Mio. $) bietet 2026
  offenbar keine Vollwerke im Kernangebot -> Weg Blink -> Vollwerk endet ausserhalb
  (Affiliate zu Amazon/Audible); Verlag verliert Marge, Daten, Marke.
- TAELLA = SCHAUFENSTER, kein Blinkist-Konkurrent: nimmt Blinkist Verhandlungsmacht.
  Voraussetzungen: echte, sichtbare Alternative; mehrere Verlage; keine Exklusivitaet,
  Rechte bleiben beim Verlag.
- Pitch: "Wir produzieren eure Glace, ihr behaltet die Rechte, ihr habt eine
  Alternative zu Blinkist in der Hand."
- Kannibalisierung: Sachbuch hoch, Roman gering. Gegenmittel: Verlag entscheidet;
  Zitat-Spruenge ins Vollwerk; Glace frei/guenstig, Vollwerk kostenpflichtig.
  CK: "Lieber eine Glace verkaufen als gar nichts."
- KPI im Pilot: Conversion Glace -> Vollwerk (zugleich Gegenbeweis Kannibalisierung).

### Marke (Vorabrecherche 03.11.2026, ohne Gewaehr)
- Keine Wortmarke GLACE in DE/EU, Kl. 9/16/41 gefunden (amtliche Register nicht abfragbar).
- Restrisiko: "GLANCE" (InMobi, US-Marken Kl. 9/41; EU-Schutz unklar).
- Entscheidung CK: nur in Kombination "TAELLA Glace".
- To do: TMview selbst pruefen (GLACE/GLACE/GLANCE, Aemter EM/DE/WO);
  ggf. Wortmarke "TAELLA" Kl. 9/16/41/42 (DPMA ca. 390 EUR).

## Testreihenfolge (vor jeder Produktentscheidung)
Testobjekt: fertig produziertes PD-Werk (z. B. Gloeckner). Je Test vorab Bestanden-
Kriterium festlegen und Kosten pro Werk messen.
1. Gekuerzte Lesung — geringstes Risiko, nutzt vorhandene Schnipsel.
2. Einfache Sprache — Variante Stage 190, kurzes Werk.
3. TAELLA Glace — komplexeste Kette; baut auf Auswahllogik aus 1 auf.
   Strategisch staerkster Tueroeffner -> Pilot mit einem Verlag (eigener Sachbuchtitel).

## Offene Punkte
- Bestanden-Kriterien je Test definieren.
- Preise als Aufpreis-Optionen im Read-Layer-Pilot.
- Markenpruefung TMview.
