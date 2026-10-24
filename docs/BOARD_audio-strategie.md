# BOARD — Audio-Strategie (Nulltarif-Basiskatalog + Pay-on-Demand-Veredelung)

> Festgehalten 12.07.2026. Strategische Synthese: schliesst die im BOARD notierte
> TTS-Skalierungswand ("Vertonung skaliert nicht, solange sie an Geminis Tageslimit
> haengt"). Kernidee: Basiskatalog komplett OHNE TTS-Kosten, Premium-Audio erst on demand.

## Kernstrategie
- **Basiskatalog = null TTS-Kosten**, aus zwei kostenlosen Quellen pro Werk kombiniert:
  - **EN Audio** = kuratierte LibriVox-Aufnahme, aligned auf EN-Originaltext (Stage 58b).
    Gratis; Menschenstimme oft besser als TTS.
  - **DE Audio** = lokales Thorsten-TTS ("Upps"-Stuetzton). Gratis, limit-frei.
    Neutrale Stimmfuehrung ist hier didaktisch sogar passender (Werkzeug, nicht Auffuehrung).
- **Folge:** ganzer Katalog vertonbar ohne einen Cent TTS -> Sprung von "MVP bewiesen"
  zu "echter Katalog" ohne die Kostenlast, die bisher die Schwelle war.

## Pay-on-Demand = Veredelungsstufe
- Wuenscht der Nutzer das **dramatisierte Gemini-Hoerbuch** oder eine **modernisierte
  Fassung**, wird DAS die bezahlte Produktion.
- Deckt sich mit der gestuften Schaufenster-Logik (Zugang gratis, Audio-Veredelung =
  eigentliche Kasse) — nur dass die Einstiegsstufe jetzt schon Audio hat statt nur Text.

## Zwei Audio-Profile = zwei Produktlinien (nicht eine mit Stimmwahl)
- **SOMNIO / eigene PD-Titel:** volles dramatisiertes DE-Audio moeglich (Gemini),
  echtes Hoerbuch-Erlebnis, "Faulheitsmodus" nutzbar.
- **Verlagstitel:** NUR "Upps"-Stuetzaudio (Thorsten), KEIN durchgehendes Hoerbuch,
  kein `full_audio`. Bewusst kein konkurrierendes Uebersetzungs-Hoerbuch (rechtlich +
  produktseitig nicht gewollt).

## Modell-Verankerung (Felder auf FASSUNGs-Ebene)
- `audio_scope: "full" | "upps_only"` — steuert, welche Audio-Tiefe eine Fassung hat.
  Bei `upps_only` entfaellt die Regie-/Kontext-Maschinerie ganz (Thorsten braucht sie nicht).
- **Audio-Herkunft / Qualitaetsstufe pro Fassung** (z.B. `librivox` | `local_tts` |
  `premium_gemini`) — damit die App transparent macht, was der Nutzer hoert, und der
  Pay-on-Demand-Upgrade sauber andockt.

## Technische Konsequenz (Thorsten-Pfad)
- Thorsten in Stage 58 einzuklinken ist NICHT nur "andere Stimme", sondern der schlanke
  `upps_only`-Pfad: Satz -> WAV, KEINE Block-Synthese, KEINE Kontext-Regie. Macht die
  Integration sogar einfacher. Eigener Pfad, kein Schalter — aber kleiner als der Gemini-Weg.
- Gemini-Pfad (Block-Synthese, Kontext-Regie, MMS_FA) bleibt fuer `full`/Premium unangetastet.

## Fuer Call-of-the-Wild-Testdatensatz
- Ist SOMNIO/PD -> bekommt perspektivisch volles DE-Audio. Aendert an dieser Strategie
  nichts; hier nur als Referenz, dass die Testdaten die `full`-Linie sind.

---

## ERGAENZUNG: Sound-Szenarien / Klangteppiche (Sessions ab 18.07.2026)

> Ambient-Atmo (Kutschen, Menge, Wald, Kaminfeuer etc.) als eigene Veredelungsstufe,
> zusaetzlich zur Sprachausgabe. Ausgangspunkt war eine UX-Idee (Ladezeit-Ueberbrueckung
> beim Kapitelwechsel in TAELLA), hat sich im Test zu einer dritten Produktlinie
> (Verlags-Upsell) entwickelt.

### Modellwahl (empirisch getestet, nicht theoretisch entschieden)
- **Gewinner: Seed Audio 1.0** (ByteDance, Text-zu-Audio, ueber fal.ai-Aggregator).
  Empirisch bestaetigt ueber 4 klanglich sehr unterschiedliche Register:
  ruhige Stadt (Jekyll & Hyde, Londoner Strasse), ruhige Wildnis (Call of the Wild,
  Arktis-Nachtlager), Spannung/Gefahr (Call of the Wild, Hundekreis-Konfrontation),
  dichte diegetische Massenszene (Glöckner von Notre-Dame, Narrenfest). Alle vier
  Laeufe als "sehr authentisch" bzw. "grossartig" beurteilt (CK-Hoertest).
- **Lyria 2 (Google, Vertex AI) -- verworfen fuer diesen Zweck.** Insistiert trotz
  starkem Negativ-Prompting ("no music, no melody, ambient only") auf Musik-Komposition
  (lieferte einen "Song" statt Feld-Atmo). Vermutlich strukturell in "instrumental
  music generation" verankert, nicht nur Prompt-Interpretation. Bleibt als Kandidat
  vorgemerkt fuer den Fall, dass irgendwann ECHTE Hintergrundmusik gebraucht wird
  (z.B. Kapitel-Uebergaenge mit Musik statt Atmo) -- fuer Klangteppiche ungeeignet.
- **ThinkSound (Alibaba) -- geprueft, nicht getestet.** Grundsaetzlich video-konditioniert
  (Chain-of-Thought koppelt Ton an tatsaechliche Bildbewegung), kein reines
  Text-zu-Audio. Fuer Standbild/Ken-Burns-Input waere die Kernstaerke (Sync auf
  Bewegungsereignisse) ungenutzt -- nur sinnvoll ueber den Umweg eines echten
  animierten Kurzvideos (Text->Video mit Bewegung->ThinkSound), was Zusatzkosten +
  Komplexitaet ohne belegten Mehrwert bedeutet. Vorgemerkt fuer den Tag, an dem
  READ LAYER mal Bewegtbild vertont (vgl. "Adjazenz Bewegtbild" oben im Board).
- **fal.ai als Aggregator bewaehrt:** ein API-Key deckt Seed Audio, ThinkSound,
  Lyria 2 und Stable Audio ab -- guenstig fuer weitere A/B-Tests ohne neuen Vendor.

### Architektur: WERK-Ebene, nicht FASSUNG-Ebene
- Klangteppiche sind **sprachunabhaengig** (Jekylls Londoner Nachmittag klingt auf
  Englisch, Spanisch oder Japanisch gleich) -> gehoeren strukturell zum WERK, nicht
  zur einzelnen Sprachfassung. Gleiches Muster wie `style.setting`/`quell_uebersetzer`
  im Datenmodell: eine Tatsache, eine Stelle.
- Praktische Folge: Produktionskosten fallen EINMAL pro Werk an, amortisieren sich
  ueber JEDE kuenftige On-Demand-Uebersetzung von selbst. Wer eine neue Sprachfassung
  bestellt, bekommt die volle Produktionsqualitaet (inkl. Atmo) sofort mit --
  spuerbarer Unterschied zu "nur ein KI-Vorleser", staerkt die Positionierung um
  eine dritte Ebene (literarisch + sprachlich synchron + produziert).
- Technisch: Atmo als **separater Stem**, nicht fest in die Narration gemischt.
  Zwei unabhaengige Gruende, gleiche Loesung: (a) Verlags-Self-Service will eigene
  Mischungskontrolle, (b) Sprachunabhaengigkeit verlangt es ohnehin (Stem wird zur
  Laufzeit / im Export mit der jeweiligen Sprachspur zusammengelegt). Ablage
  vermutlich `books/<buch>/audio_scenarios/` (Werk-Ebene), nicht unter `fassungen/<lang>/`.
- **Offene Frage, nicht entschieden:** Wenn Werk-Atmo fuer eine Sprache schon
  produziert ist und ein zweiter Verlag eine WEITERE Sprachfassung desselben PD-Werks
  bestellt -- zahlt der voll fuer etwas ohne neue Produktionskosten? Strukturell
  verwandt mit dem Erstbesteller/Ambassador-Gedanken weiter oben im Board. Vor
  Launch des Verlags-Angebots klaeren.

### Prompting-Regel: diegetisch vs. Score (empirisch bestaetigt)
- Seed Audio unterscheidet zuverlaessig zwischen "Musik komponieren" (Lyrias Falle)
  und "Musik als Teil der Szene" (Kapelle/Trommeln als Festlaerm-Element, nicht
  tragende Melodie). Getestet am Narrenfest (Glöckner von Notre-Dame): "no musical
  score" statt "no music" erlaubt -> Ergebnis "Kapelle und Trommeln im Hintergrund,
  begleitet das Lärmen, aber nicht durchgängig" (CK).
- **Regel fuers Prompting:**
  - Szene mit eigener Klangquelle (Fest, Taverne, Tanzsaal, Umzug, Marktplatz mit
    Spielmann) -> diegetische Musik erlauben, Leitplanke "as part of the crowd/
    scene itself", "not a musical score/composition".
  - Szene ohne plausible Musikquelle (Strasse, Wildnis, stiller Innenraum) -> "no
    music" strikt halten wie bisher.

### Pricing-Logik (zwei Achsen, unterschiedliche Kostentreiber)
- **TTS folgt dem Text:** Abrechnungsbasis bleibt Wortzahl (bestehender Anker,
  Umfang-Score aus der Prio-Liste laesst sich wiederverwenden).
- **Soundscape folgt der Szene:** Abrechnungsbasis ist Anzahl generierter Audios
  (grundsaetzlich 1 pro Kapitel, bei Bedarf mehr pro Kapitel bei mehreren
  Szenen-Tags). Kein Szenen-Dedup/Wiederverwertung ueber Kapitel hinweg --
  bewusst verworfen: Kosten pro Lauf zu gering, um die Komplexitaet (Szenen-ID-
  Ebene, Aehnlichkeits-Erkennung, Mensch-Bestaetigung) zu rechtfertigen, UND
  selbst gleicher Ort klingt je nach Stimmung/Handlung oft bewusst unterschiedlich
  (Taverne froehlich vs. Taverne bei Konfrontation). Immer neu generieren ist
  einfacher, trifft Erzaehlmomente praeziser und zahlt auf den Premium-Anspruch
  (Abwechslung) ein.
- Diese Zwei-Achsen-Logik loest gleichzeitig das "Zauberberg vs. Kleiner Prinz"-
  Problem: Audio-ANZAHL (nicht rohe Kapitelzahl, nicht Wortzahl) ist ein fairerer
  Volumen-Proxy fuer Soundscape-Bedarf, unabhaengig davon wie lang/kurz die
  Kapitel eines Autors sind.

### Verlags-Pricing (drei Einsatz-Kontexte, nicht vermischen)
1. **TAELLA-Ladeueberbrueckung:** client-seitig, generische wiederverwendbare
   Loop-Bibliothek (~15-20 Kategorien), quasi kostenlos, kein Upsell.
2. **SOMNIO-eigene Vollproduktionen:** Kapitel-individuell, Teil der eigenen
   Qualitaetsmarke, nicht separat bepreist.
3. **Verlags-Self-Service (NEU, dieser Abschnitt):** Kapitel-/Szenen-individuell,
   **~1 EUR pro generiertem Audio**, genrebasiert vorgeschlagen (Abenteuer/Wildnis/
   Massenszenen-Titel triggern Upsell-Vorschlag im Portal; Kammerstuecke wie
   "The Yellow Wallpaper" oder "Die Verwandlung" brauchen es kaum -- filtert sich
   durch die Audio-Anzahl-Abrechnung quasi von selbst, kein manuelles Genre-Flag
   noetig). Auch als **Geschaeftsargument fuer Verlage** relevant, nicht nur
   aesthetisch: Streaming-Plattformen (Spotify, Storytel, Scribd, Fluister) zahlen
   ueberwiegend pro gehoerter Minute ($0,005-0,02/Min., teils gepoolt bis "volle
   Hoerung") -- laengere, reichhaltigere Produktion kann sich fuer Verlage direkt
   in Vergues auszahlen. Wird bei READ LAYER bewusst als "kapitelgerechter
   atmosphaerischer Mehrwert" positioniert und verkauft, nicht als "Minuten-
   Streckung" -- wie ein Verlag es einsetzt, ist dessen redaktionelle Entscheidung.

### Kostenanker (neu, analog zum bestehenden TTS-Anker)
- **Soundscape (Seed Audio via fal.ai):** ~$0,12-0,13 pro generiertem Audio/Kapitel-
  Szene (Live-Test 19.07.2026: 5 Laeufe = $0,61 gesamt). Bei ~1 EUR Verkaufspreis
  pro Audio gesunde Marge (grob 5-8x), unabhaengig von Werklaenge (siehe Pricing-
  Logik oben).
- **TTS (Gemini Pro + 8-Satz-Block-Chunks):** Entscheidung fuer Pro bestaetigt,
  Chunking bringt die Kosten nahe an die vorherigen Flash-Einzelsatz-Laeufe heran
  (Bestaetigung der BOARD-Beobachtung "Pro bei Block-Synthese kann trotz 2x-Preis
  guenstiger sein als Flash bei Einzelsatz"). **Exakte $/1000-Woerter-Zahl noch
  offen** -- beim naechsten Live-Lauf neu messen, nicht aus dem Gedaechtnis schaetzen.
