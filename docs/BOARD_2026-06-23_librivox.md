# BOARD-Ergänzung — LibriVox / Fremd-Audio-Onboarding (Stand 22.–23.06.2026)

> Fortschreibung zu BOARD.md. Eigene Datei wegen Groesse des Originals.
> Sammelt die strategischen + technischen Erkenntnisse rund um die LibriVox-
> Integration (fremdes menschliches PD-Audio als Pipeline-Quelle). Details in
> STAND_2026-06-22.md, STAND_2026-06-22b.md, STAND_2026-06-23_*.md.

---

## DURCHBRUCH: LibriVox loest die TTS-Skalierungswand (fuer vorhandene Aufnahmen)
- Die im BOARD notierte TTS-Kontingent-Wand (Gemini-Tageslimit) gilt nur fuer
  SELBST vertontes Audio. Wo eine gute LibriVox-Aufnahme existiert, faellt die
  Vertonung ganz weg -> kein TTS-Limit, kein Durchsatzproblem.
- Bewiesen: "The Call of the Wild" (7 Kapitel, Jeff Clark) komplett geschnitten,
  1629 tag-alignte Schnipsel, am Ohr fehlerfrei. Ein ganzes Werk ohne 1 TTS-Call.
- NEUER Engpass ist STT statt TTS: faster-whisper medium/int8 ~24 min/Kapitel
  auf CKs Laptop (~4,6 h fuer 7 Kapitel). Skaliert ueber GPU/Batch (s.u.), aber
  ungefaehrlich, weil einmalig pro Werk + Cache pro Kapitel.

## STRATEGISCH: Innovator's-Dilemma-Segment, jetzt mit gratis Audio-Rohstoff
- LibriVox = grosser Bestand menschlicher PD-Sprecher, rechtlich voellig frei
  (schneiden/uebersetzen/kommerziell, keine Nennungspflicht; nur US-PD zugesichert
  -> eigene EU-PD-Pruefung Todesjahr+70 bleibt Pflicht pro Titel).
- Das macht den Longtail-/Klassiker-Katalog NOCH guenstiger: wo Audio existiert,
  kostet die Audiospur fast nichts (nur STT + Schnitt = Cent-/Strombereich).
- Qualitaet streut (Freiwillige) -> Sprecher-Auswahl wird zum Kuratierungshebel.
  Die Abweichungs-Ampel (s.u.) macht Sprecher-Treue messbar VOR dem Schnitt.

## MARKTEINSTIEG: zuerst deutschsprachiger Markt (CK)
- Grund: Sprach-Barriere bei Lizenz-/Vertragsverhandlungen -> CK verhandelt,
  prueft Rechte, kennt Sensibilitaeten am sichersten auf Deutsch.
- Deutsche LibriVox-Aufnahmen speisen die de-Fassung, EN/andere Uebersetzung
  danebengelegt. ES wichtig fuer US-Markt (zweitgroesste Sprachgruppe).
- Voraussetzung dafuer war die sprachneutrale Architektur-Entscheidung (Weiche
  pro Fassung an audio_quelle, NICHT an der Sprache) -> kein Umbau noetig fuer
  den DE-Start. Gemischte Werke moeglich (z.B. es=LibriVox, en=TTS).

## ARCHITEKTUR-PRINZIP (bestaetigt): Rollen trennen, nicht ein Werkzeug ueberlasten
- Die gescheiterte "Salami" (FA blind durchs Audio) lehrte: FA darf nicht Richter
  UND Angeklagter sein (ausrichten + sich selbst per Score bewerten).
- Loesung STT-First: STT verankert grob (Korridore aus Wort-Zeiten), das Energie-
  TAL schneidet fein, der Rohtext/Tag-Text sagt was wohin gehoert. Drei
  unabhaengige Zeugen statt einem ueberlasteten. -> robust, driftfrei.
- Uebertragbar: gilt als Muster fuer kuenftige "ein Schritt soll zu viel auf
  einmal"-Situationen.

## QA-LEHRE (wichtig fuer alle Literatur-Uebersetzung): Backtrans-Score != Qualitaet
- Beim CotW-DE-Lauf: Durchschnitt 96.2, aber 109 Saetze "unter Schwelle" (meist 85).
- BEFUND: niedrige Scores sind oft FREIE, GUTE Uebersetzungen. Der Backtranslation-
  Scorer belohnt WOERTLICHKEIT; idiomatische Loesungen kommen rueckuebersetzt nicht
  wortgleich beim Original an.
- Konkreter Beleg: c001_00012_s (Score 60) war eine ausgezeichnete epochengerechte
  Uebersetzung ("groom"->Pferdeknecht, "held forth"->das Regiment fuehren). CK: "gut getroffen".
- REGEL: Score ist VERDACHTSFILTER (wo hinschauen), kein Urteil (was falsch ist).
  KEINE blinde Schwellen-Automatik "alles unter 90 nacharbeiten" -> wuerde gute
  freie Uebersetzungen verschlechtern (woertlicher, hoelzerner). Mensch sichtet
  Stichprobe, korrigiert nur echte Treffer (sinnentstellend/ausgelassen/anachronistisch).
- Bei LibriVox-Linie (freie Literaturuebersetzung) faellt der Score SYSTEMATISCH
  strenger aus -> Filter entsprechend grosszuegig lesen.

## NEUE QUALITAETSFUNKTION (gratis Nebenprodukt): Sprecher-/Aufnahme-Ampel
- Der STT<->Text-Abgleich liefert pro Kapitel eine Match-Rate. Sie misst, ob die
  Aufnahme zum Text passt -- VOR jedem Schnitt.
- CotW: 94.9-98.2% ueber alle Kapitel -> Sprecher folgt dem Text treu. Saecke ein
  Kapitel ab, weicht der Sprecher ab (andere Edition/Auslassung) -> gezielt reinhoeren.
- Direkt nutzbar fuer den spaeteren Self-Service-Verlagspfad: Verlag laedt Audio +
  Skript, System sagt SOFORT ob beide zusammenpassen, bevor Rechenzeit fliesst.

## DURCHSATZ-NOTIZ (kein Board-Eintrag gewuenscht, aber relevant): STT per GPU
- STT ist der neue Zeitfresser (~24 min/Kapitel CPU). GPU/GPU-Miete als Batch-Job
  passt zum schubweisen Durchsatz und an die bereits notierte Cloud-Run-Jobs-Linie.
- Erst angehen bei stabilem Durchsatz + sinnvoller Schubgroesse. Bis dahin: lokal,
  ueber Nacht, mit Cache pro Kapitel (Wiederanlauf kostet nichts).

## AUDIO-COVER-STANDARD (recherchiert) -- fuer die spaetere Cover-Familie
- Hoerbuch-Cover = QUADRATISCH 1:1 (haeufigste Ablehnungsursache wenn nicht),
  min. 2400x2400 (besser 3000), RGB, JPG/PNG/TIF. Titel + Autor PFLICHT,
  Sprecher optional. KEIN Marketing/Klappentext/Disclaimer aufs Bild (ACX-Norm).
- Folge fuer READ LAYER: zwei Cover-Ausgaben aus DERSELBEN Tusche-Illustration
  (Stage 21) -- EPUB 2:3 hoch (Stage 30, vorhanden) + Audio 1:1 quadratisch (neu).
  LibriVox-Credit "Recording: <Sprecher>" auf dem Audio-Cover ok; Disclaimer NUR
  in Metadaten/Colophon.
- ACX/Audible = De-facto-Standard; StreetLib/BookBeat/TAELLA teils eigene Specs,
  aber 2400x2400 quadratisch RGB ist die sichere Grundlage.

## OFFENE PUNKTE (LibriVox-bezogen)
- Audio-Cover-Stage (quadratisch) bauen.
- Cover/Colophon-Credit (Stage 30): dezenter Vermerk im Cover-Fuss + voller
  Disclaimer im Colophon, liest credit/source_disclaimer aus book.json-Fassung.
- run.py --lang-Luecke: en-LibriVox-Fassung laeuft nur mit explizitem --lang en
  (Quellsprache nicht in TARGET_LANGUAGES). Saubere Loesung spaeter.
- -th/-ng-Auslaute weiter beobachten (aktuell weich=0 in der Konsonanten-Korrektur).
- Cut-Wiki vertagt: Sammelstelle fuer echte Schnitt-Ausnahmen, erst fuellen wenn Funde.
