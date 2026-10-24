# BOARD — LibriVox-Onboarding & Sprecher-Qualitätslayer

> Festgehalten 21.06.2026. Gehört in den "Später/Adjazenz"-Strang, aber mit
> hoher strategischer Priorität: löst die TTS-Skalierungswand für den
> KATALOG-AUFBAU (nicht für das Beiprodukt DE-Audio).

## STAND
Aus drei zusammengesetzten Einsichten dieser Session:
1. Für ein TÆLLA-Asset wird kein TTS gebraucht, wenn fertiges Audio vorliegt —
   FA (torchaudio MMS_FA) richtet vorhandenes Audio gegen bekannten Text aus.
2. Die FA-Stufe ist quellen-agnostisch: ob das Audio aus eigenem TTS oder aus
   einer fremden Aufnahme stammt, ist ihr egal.
3. LibriVox liefert genau das fehlende Stück — menschlich gesprochenes,
   gemeinfreies Audio in tausendfacher Zahl, gratis, PD sauber.

## BEFUND (die eigentliche Tragweite)
- **TTS fällt aus dem englischen Katalog-Pfad heraus.** EN-Erzählung = LibriVox
  (fertig). EN-Text satzaligned = FA(LibriVox-Audio + Gutenberg-Etext).
  DE-Seite = DeepSeek (billig, durchsatzstark). "Upps" funktioniert.
  → Der Kern-Eintrag eines PD-Klassikers entsteht OHNE eine Sekunde Gemini-TTS.
- Die BOARD-Wand "Vertonung skaliert nicht" wird hier UMGANGEN, nicht gelöst:
  für den EN-Strang wird gar nicht vertont.
- **Nicht abgedeckt (ehrlich):** DE-Audio (Faulheitsmodus, SOMNIO-Hörbuchlinie)
  hängt weiter am TTS-Limit. Das ist aber das Beiprodukt, nicht die Katalogbreite.
- **Gleiche Maschine wie Verlags-Onboarding:** fremdes Audio + Text rein,
  aligntes bilinguales Asset raus. "Rechteinhaber" = hier die Public Domain.
  → LibriVox ist die Erprobungs-Strecke für den Self-Service-Pfad, BEVOR der
  erste echte Verlag einzieht.

## TECHNISCHE ONBOARDING-PROBLEME (zu lösen, KEINE Rechtsfragen)
1. **Intro/Outro-Boilerplate**: LibriVox-Aufnahmen tragen "Section X, read by …
   for LibriVox.org" / "End of section" — steht NICHT im Etext → FA-Drift am
   Rand. Lösungsmuster existiert (Überschriften-Kauderwelsch-Fix, kurzer
   kontextfreier Prompt-Gedanke; hier: Rand-Erkennung + Abschneiden vor FA).
2. **Editions-Abgleich**: Sprecher las aus EINEM Etext (meist von LibriVox
   verlinkt). Stimmt unsere raw.txt nicht mit SEINER Vorlage überein → FA driftet.
   → Verlinkten Quell-Etext bevorzugen; Mengenprüfung (faster-whisper Soll-Ist)
   als Drift-Wächter.
3. **Multi-Sektion / Kapitel-Splits**: LibriVox-Dateien folgen Sektionen, nicht
   zwingend unseren Kapitelgrenzen → Zuordnung Datei↔Kapitel nötig.
4. **Multi-Reader-Bücher**: viele Titel haben pro Sektion einen ANDEREN Sprecher.
   Für Lernprodukt Stimmbruch → entweder ablehnen oder pro-Sektion-Stimme
   bewusst behandeln. (Solo-Aufnahmen sind das Gold.)
5. **Audioformat**: LibriVox = MP3. FA/Assembler arbeiten auf PCM/WAV (LINEAR16).
   → Decode-/Normalisierungsschritt (Samplerate, mono/stereo) vorschalten.
6. **Satzsegmentierung**: STT/FA liefert Wörter; "Upps" braucht SATZgrenzen →
   Satz-Segmentierung vor dem FA-Schnitt (gilt nur, falls kein sauberer Etext
   als Satzquelle dient; mit Etext kommt die Segmentierung von dort).

## IDEE — SPRECHER-QUALITÄTSLAYER (der Kern dieser Notiz)
**Problem:** Freiwilligen-Aufnahmen streuen stark in Qualität. Für ein HÖRBUCH
egal — für ein SPRACHLERN-Produkt nicht: der Lerner IMITIERT die Aussprache.
Schlechte Aufnahme = falsch gelerntes Vorbild. Also: nicht jede Aufnahme nehmen,
sondern KURATIEREN — nach messbaren Parametern, mit menschlichem Schlussurteil.
Muster wie überall: Maschine schlägt vor / flaggt, Mensch entscheidet.
Analog zur bestehenden Text-Ampel → eine **Sprecher-/Aufnahme-Ampel**.

### Tier 1 — automatisch messbar (billig, direkt am Signal)
- **SNR / Rauschteppich**: Hintergrundrauschen, Brumm.
- **Clipping / Verzerrung**: Peak-Analyse.
- **Lautheits-Konstanz**: LUFS-Varianz über Datei/Sektionen.
- **Technischer Boden**: Samplerate, Bittiefe.
- **Sprechtempo (WPM)**: Wortzahl/Dauer (fällt aus FA ab). Zu schnell = schlecht
  für Lerner.
- **Pausen-/Rhythmus-Regelmäßigkeit**.
- **FA-Alignment-Konfidenz**: Durchschnitts-Score aus MMS_FA. NIEDRIG = Drift,
  Nuscheln, falsche Edition, Ad-libs. **Doppelnutzen: dieser Wert fällt im
  Ausricht-Schritt ohnehin an — Qualitätssignal gratis.**
- **Solo vs. Multi-Speaker**: Diarisierung flaggt >1 Stimme über Sektionen.

### Tier 2 — modellbasiert (mittel)
- **Verständlichkeit/Klarheit als STT-Übereinstimmung**: starkes STT laufen
  lassen, gegen Etext vergleichen — hohe Übereinstimmung = klarer Sprecher.
- **Phonem-Klarheit**: das schon vorgemerkte Phonem-QA-System (wav2vec2 CTC +
  eSpeak) hier UMWIDMEN — Phonem-Konfidenz als Klarheits-Proxy.
- **Akzent-Klassifikation**: Referenz-Akzent (RP/General American) vs. starker
  Regionalakzent. Schwerer; ggf. nur menschliche Stichprobe.

### Tier 3 — menschliches Schlussurteil (flag-for-review, finale Schranke)
- **Natürlichkeit / Angenehmheit** (subjektiv).
- **Über-Dramatisierung / manierierte Lesung**.
- **Akzent-Akzeptanz fürs Lernziel**.
- **Go/No-Go**. In Sprachen, die CK nicht selbst beurteilt (IT/ES/FR):
  Native-Speaker-Mikro-Crowd (schon vorgemerkt) ist hier die menschliche Schranke.

### Resonanz mit Vorhandenem (nichts davon ist neu zu erfinden)
- FA-Alignment-Score → freies Qualitätssignal aus der Pipeline.
- STT-Mengenprüfung → Drift-/Vollständigkeits-Signal.
- Phonem-QA (wav2vec2 + eSpeak) → von Aussprachefehler-Erkennung zu
  Sprecher-Klarheits-Scoring umgewidmet.
- Ampel-Muster → Sprecher-Ampel statt Text-Ampel.
- Native-Speaker-Crowd → menschliche Schranke für Fremdsprachen.

## TODO (priorisiert, kein Blocker für Laufendes)
1. **Probelauf an EINEM gut beleumundeten Solo-LibriVox-Titel**: Audio + Etext →
   Boilerplate ab → FA → satzaligned → DeepSeek → "Upps"-Paar. An EINEM Titel die
   technische Kette beweisen (Cents, nicht Roman).
2. **FA-Alignment-Konfidenz als Metrik exponieren** (fällt eh an) → erstes,
   billigstes Qualitäts-Gate.
3. **Boilerplate-Erkennung** (Intro/Outro) als eigener Vorschritt.
4. **MP3→WAV-Normalisierung** vorschalten.
5. Sprecher-Ampel als schlanke Scorecard (Tier 1 zuerst, Tier 2/3 später).
6. Solo-vs-Multi-Reader-Filter (Diarisierung oder LibriVox-Metadaten auswerten).

## EINORDNUNG
LibriVox löst die Katalog-BREITE im EN-Strang vom TTS-Limit. Der Qualitätslayer
ist der Preis dafür, dass es ein LERN-Produkt bleibt und kein bloßes
PD-Audio-Recycling. Genau diese Kuratierung ist auch die Differenzierung
gegenüber jedem, der LibriVox nur roh weiterreicht.
