# ReadLayer — Board "Später / Adjazenz"

Ideen, die NICHT in den MVP gehören, aber festgehalten werden.
Regel: Hier landen Gedanken, damit sie den Fokus nicht stören — nicht zum sofortigen Bauen.

---

## Modelle & Infrastruktur

### ⚠️ TTS-Kontingent = die Skalierungswand (Erkenntnis Live-Lauf)
- Gemini-TTS (`gemini-2.5-flash-preview-tts`) hat ein enges Tageskontingent.
- Beleg: 3 kurze Fabeln = ~90 Schnipsel -> Tageslimit erschöpft (Abbruch bei 77/90).
- Hochrechnung: Zauberberg (2 Bände, hunderttausende Wörter) = ZEHNTAUSENDE Schnipsel PRO Sprache, x5 Sprachen. Mit diesem Limit pro Vollwerk WOCHEN nur Warten.
- **Fazit:** Übersetzung skaliert (DeepSeek billig/schnell). Vertonung skaliert NICHT, solange sie an Geminis Tageslimit hängt. TTS-Limit ist die zentrale Wand zwischen MVP (bewiesen) und echtem Katalog (Mann/Hugo/Cervantes).
- Optionen in Reihenfolge: (1) höheres Gemini-Tier beantragen (schnell, bleibt fremdes Limit); (2) NVIDIA-Endpoint testen (mittel); (3) eigenes lokales TTS (groß, aber endgültig limit-frei).

### NVIDIA build / NIM als TTS-Pfad (recherchiert + GETESTET — Ergebnis: verworfen)
- **TESTERGEBNIS (CK, Hörtest mit eigenem Aesop-Text):**
  - **Chatterbox** (Resemble.AI): Qualität "sehr ordentlich", aber nur EINE Stimme, und SSML wird MITGESPROCHEN (versteht es nicht).
  - **Magpie TTS Multilingual**: auf Hörbüchern trainiert, 9 Sprachen, je 4 m/w-Stimmen, CER-Werte gut (DE 0,66 / IT 4,0 = schwächste). Pro Sprache je EINE überzeugende Stimme, die anderen mit amerikanischem Zungenschlag (engl. Sprecherpool übertragen). ABER im direkten Vergleich mit eigenem Text: **"meilenweit von Gemini weg"** — Qualität klanglich nicht ausreichend.
- **ENTSCHEIDUNG: NVIDIA-TTS-Pfad verworfen.** Qualitätsabstand zu Gemini zu groß. Limit-Freiheit nützt nichts, wenn der Klang nicht trägt. Kein Riva-gRPC-Integrationsaufwand investieren. Wert des Tests: teuren Irrweg VOR der Integration ausgeschlossen.
- **Technik-Notizen (falls je relevant):** Chatterbox/Magpie laufen über Riva gRPC (nicht REST wie Gemini), `pip install nvidia-riva-client`, Server `grpc.nvcf.nvidia.com:443`, braucht function-id + Bearer-Key. Magpie-Output: Mono PCM 16-bit WAV @ 22,05 kHz (Gemini: 24 kHz). Magpie steuert über Voice+Emotion-Parameter (nicht SSML); kann long-form (sliding window). 40 RPM, kein Tageslimit.

### ⇒ Konsequenz für den TTS-Engpass: bei Gemini bleiben, Durchsatz anders lösen
- Gemini-Klang bleibt konkurrenzlos. Engpass NICHT über Modellwechsel lösen, sondern über:
  1. Höheres Gemini-TTS-Kontingent beantragen (Billing aktiv -> oft möglich). Selber Klang, mehr Durchsatz. **Naheliegendster Pfad.**
  2. Geminis Batch/Long-form ausschöpfen: größere Textblöcke pro Call statt ~90 Einzelschnipsel -> weniger Calls, weniger Limit-Druck, bessere Sprachmelodie über Satzgrenzen. ABER: Konflikt mit satzgenauem Alignment prüfen — evtl. Blöcke vertonen + Timecodes statt Einzelschnipsel.
  3. Lokales TTS bleibt Option, aber dann ein ANDERES Modell als die NVIDIA-Kandidaten (eigene Recherche nötig: XTTS, StyleTTS2, Kokoro, neuere). Erst wenn Volumen es rechtfertigt.

### SSML-Schicht (Stage 05) — bedingt behalten, NICHT abschaffen
- Beobachtung: Gemini-TTS bekam am Ende nur REINEN Text (500-Fix), kein SSML. Trotzdem hörbare Modulation + Tempowechsel in allen 5 Sprachen -> Gemini interpretiert selbst.
- ABER: Lokale TTS-Modelle interpretieren NICHT so eigenständig. Sie brauchen explizite Regie (Pausen/Betonung/Tempo als Markup).
- **Fazit:** Bei Gemini ist SSML evtl. entbehrlich; bei lokalem TTS vermutlich essenziell. Schicht behalten — sie ist die Versicherung für den Modellwechsel. Pausen-Dramaturgie (Manifest-Strukturdaten, NICHT SSML) hat sich als hörbar "genau richtig" bestätigt (CK-Urteil).

### Betriebsregel (gelernt aus Bug)
- `stage07.json` / `manifest.json` NIE im Mock-Modus überschreiben, wenn ein Live-Stand existiert — Mock verfälscht Text (`[DE]`-Platzhalter) und Dateiendungen (`.txt` statt `.wav`). Stage 08 zieht daher Text+Tags+Pausen aus `stage06` und sucht WAVs direkt im Ordner. Sauberer Fix bereits umgesetzt.

### Eigene / selbstgehostete Modelle (NVIDIA build / NIM, offene Gewichte)
- Plattform: https://build.nvidia.com/models — viele Modelle als API UND als Download ("offene Gewichte").
- Kandidaten gesehen: Qwen3-Next-80B (mehrsprachig, langer Kontext), Nemotron-3-Nano (1M Kontext).
- **Strategischer Wert 1 — Souveränität:** Eigene Modelle auf eigener/gemieteter GPU = Kuratierungslogik und Daten verlassen nie fremde Server. Passt zum Geheimhaltungs-/Schutzgedanken.
- **Strategischer Wert 2 — Kostenvorteil bei Skalierung:** Bei hohem Volumen sinken die Stückkosten gegenüber Pay-per-Call-APIs. Besonders relevant bei Custom-Content, wo pro Kunde eine eigene Produktion läuft — dort summieren sich API-Kosten schnell, eigene Inferenz amortisiert die Fixkosten.
- **Haken:** TTS-Qualität lokal unbewiesen -> Blindtest nötig. Mehr Anbieter = mehr Komplexität. GPU kostet auch im Leerlauf -> Vorteil erst ab Volumen.
- **Architektur-Hinweis:** Dank `api_layer` + Modell-Routing in `config.MODELS` ist das Hinzufügen eines NIM-Endpoints später ein kleiner Eingriff, kein Pipeline-Umbau.
- **Entscheidung:** Für MVP bei DeepSeek + Gemini bleiben. Eigene Modelle evaluieren, wenn (a) Pipeline steht [✓], (b) Volumen/Custom-Geschäft die Fixkosten rechtfertigt.

---

## Weitere Board-Themen (Kurzliste, Details in früheren Gesprächen)
- Graded Readers (vereinfachte PD-Märchen für echten Lerneinstieg)
- Custom-Szenario-Geschichten (kundenindividuell, Premium, Fragebogen = kundengeliefertes Buch-Profil)
- Idiom-/Redewendungs-Datenbank (titelübergreifend, akkumuliert aus Kuration)
- Kritische-Sequenz-Extraktion (nur Idiome/Wortspiele lektorieren lassen)
- Community-Korrektur-Loop (Status statt Credits; "Community-Improved Asset")
- Cover-Generierung (Template + Imagen-Bild + Metadaten, 5 Sprachversionen)
- Adjazenz Bewegtbild (Untertitel/Lip-Sync) — nur Architektur-Validierung, NICHT bauen (Rechte, Timing, Wettbewerb)

---

## Katalog-Aufbau, Geschäftsmodell & Wälzer-Handling (Session Juni 2026)

### Katalog-Pipeline Gutenberg (umgesetzt, Werkzeuge existieren)
- `gutenberg_harvest.py`: zieht über Gutendex-API die populärsten Titel (Top 2000 EN), filtert auf Text/Fiction/EU-PD, schreibt CSV + Roh-JSON. Retry+Backoff gegen Timeouts.
- `gutenberg_enrich.py`: nimmt die markierte Auswahl (Core/X) + 21 Perlen, lädt Volltexte (Cache), rechnet Länge (1-10), Komplexität (Flesch→1-10) und Verarbeitbarkeits-Ampel.
- Stand: 2000 → 760 Kandidaten → 347 ausgewählt → **319 eindeutige Werke** (entdoppelt). Davon 251 grün (sofort produzierbar), 29 gelb (kleine Wäsche), 39 rot (Vers/Drama → Nacherzähl-Linie).
- Monte-Cristo-Check bestätigte Komplexitäts-Skala: K4 deckt sich mit CKs Leseurteil "wenig komplex".
- Ampel V1 war zu streng (Boilerplate/Dialog fälschlich rot); V2 nur Vers/Drama + Massen-Fußnoten (≥200) + Sonderzeichen als echtes Rot.

### PD-Prüfung = Priorität #1 (Regel)
- Vor jeder Produktion: death_year + 70 < aktuelles Jahr für EU/DE. Kein Risiko.
- Christie: EU gesperrt bis 2046 (†1976), egal was US-Listen sagen (US zählt 95 J. ab Erscheinen, werkweise — anderer Flickenteppich). Für EU-Start irrelevant.
- Übersetzer-Copyright beachten: bei übersetzten Werken zählt AUCH Todesjahr des Übersetzers. Umgehung: bei dt. Originalen (Nietzsche, Goethe, Freud †1939=frei) das ORIGINAL nehmen und selbst ins Englische übertragen → eigene Übersetzung, kein fremdes Copyright.
- Jeder 1. Januar bringt neue Kohorte (Tod+70). Public-Domain-Day-Liste im Blick behalten.

### Geschäftsmodell: gestuftes Schaufenster + On-Demand
- **3 Produkttiefen:** (1) Schaufenster = Cover+Klappentext (fast gratis), (2) Lesevariante = EN/DE-Satz-Alignment, schon bezahlt (Übersetzung 3 ct), echtes Lese-Lernprodukt mit "Ups", (3) Audio = on demand, der eigentliche Umsatz.
- **2 Produktionsmodi:** reaktiv (Standard, kein Risiko, Audio erst nach Kauf) + proaktiv (datenbasiert, NUR aus Überschuss bereits amortisierter Titel, als Lager-Puffer gegen Nachfragespitzen — sonst Pipeline-Stau = wochenlange Wartezeit im Erfolgsfall). Proaktiv produziertes Audio bleibt VERSCHLOSSEN bis Erstkauf.
- **Klappentext-Struktur:** (1) Titel, (2) Einordnung (aus Buchtext ableiten, nicht aus Modell-"Wissen" → kein Fabulieren bei unbekannten Titeln), (3) echter Textauszug (= ehrlicher Schwierigkeits-Selbsttest für den Lerner!), (4) Worte zum Autor. Reihenfolge dramaturgisch: Köder (Auszug) vor Einordnung. Volle Klappentexte nur für Blockbuster, Rest nur Text.
- **Coins / Ambassador:** Erstbesteller einer Sprachfassung = Ambassador (zeitstempel-eindeutig). Bekommt "Presented by"-Tag (Stolz/Identifikation) + Coins auf Folgeverkäufe. Coins = NUR systeminternes Guthaben (Payback-Logik), KEIN Geldfluss zwischen Nutzern (rechtlich heikel/Strukturvertrieb). Gedeckt durch reale Verkäufe. Start simpel; Missbrauchsschutz (keine Selbstkäufe) später.
- **Abo:** erst wenn Regal voll. Einzelkäufe finanzieren Katalogaufbau + liefern Nachfragedaten. WICHTIG: Einzelkäufern "gekauft bleibt gekauft" zusichern, sonst Frühkäufer-Frust beim Abo-Start.
- **Faulheitsmodus:** App auch nur als dt. Hörbuch nutzbar (müde Tage) = Churn-Bremse, kostet nichts (dt. Vertonung fällt eh an). Rückfall-Nutzen, NICHT Hauptverkaufsargument (sonst Konkurrenz zu Audible/BookBeat).
- **Tagesfluss-Vision:** ein Buch fließt durch den Tag — lernen (Auto) → genießen (DE, müde) → lesen (Bett), immer an derselben Stelle. Setzt Modus-Sync voraus (technisch teuerstes Feature, später).

### Zeitgenössische Inhalte (Erweiterung, NICHT Start)
- Großverlage: "kalter Hauch von Argwohn und Trägheit" (CK), KI-Stimmen-Skepsis, exklusive Audio-Deals. Erst mit Beweisen/Traktion angehen, nicht mit Idee.
- Besserer Weg von unten: Self-Publishing-Autoren (halten Rechte selbst, wollen Reichweite), CC-Werke, Fach-Autoren. Win-Win, schnelle Einzelentscheidung. ABER: mehr Kuratierungslast (kein Zeit-Filter), Verträge pro Titel, KI-Stimmen-Einwilligung nötig.
- Reihenfolge: erst Klassiker-Fundament (gehört dir, sofort startbar), dann Indie/CC, dann ggf. Verlage.

### Wälzer-Aufteilung in Bände (Workflow festgelegt)
- **Problem:** L9-L10-Brocken (Monte Cristo 460k Wörter, Middlemarch, Karamazov) — als Einzelvertonung zu lang/teuer/abschreckend.
- **Workflow (CK):** KI gibt KORRIDOR für Schnitt (an Kapitelgrenzen, nie mittendrin) + Zusammenfassung (Doppelnutzen mit Klappentext). CK schneidet + benennt Band ("Band 1: Der Narrenkönig"). Maschine = mechanisch/Vorarbeit, Mensch = dramaturgischer Schnitt + Titel.
- **Korridor-Kriterien:** dramaturgischer Einschnitt UND ausgewogene Bandlängen (können kollidieren → CK entscheidet).
- **Doppelnutzen:** Monte Cristo war Feuilletonroman → Bandstruktur stellt historische Episodenform wieder her (Narrativ "wie Dumas' Leser es 1844 erlebten"). Bände = mehrere Verkaufseinheiten + natürliche Kaufkette (Spannung treibt Folgekauf). Löst Längen-Kostenproblem + schafft Verkaufskette zugleich.
- **KONSISTENZ-REGEL (kritisch):** Erst GANZES Werk durch Profil (Stage 01) + Übersetzung, DANN schneiden. Sonst driftet Figurenglossar/Stil über Bandgrenzen ("der Zeitreisende" ≠ "der Reisende durch die Zeit").
- **Architektur:** Ebene "Werk" (Profil, Glossar, Stimme, Stil = eine Quelle der Wahrheit) + Ebene "Band" (nur Kapitelzuordnung + Band-Titel). Bände GREIFEN auf Werk-Stimme zu (keine Vererbungskette Band→Band, die reißen könnte). Ermöglicht zeitversetzte On-Demand-Bandproduktion ohne Konsistenzverlust.
- Stimmwahl an REPRÄSENTATIVER (auch späterer/intensiverer) Passage testen, nicht nur am ruhigen Anfang.

### Low-Cost-Zone vor Vertonung (Arbeitsregel)
- Alles vor TTS (Tagging, Profil, Übersetzung, Backtranslation, Klappentext, Zusammenfassung, Schnitt-Korridore) = Cent-Kosten → beliebig viele Edit-Schleifen + werktreue Komplettübersetzung mit Kontextbewahrung leistbar.
- Trennlinie: links experimentieren frei, rechts (Vertonung) wird teuer + on demand.

### Nacherzähl-Linie (eigenes Produkt, später)
- Versepen/Dramen (Homer, Dante, Faust, Shakespeare) NICHT durch satzbasierte Pipeline — Vers bindet ganze Aufmerksamkeit, Spracherwerb damit unmöglich.
- Lösung: Prosa-Nacherzählung (Tradition: Lambs "Tales from Shakespeare" 1807). KEINE Respektlosigkeit, sondern Vermittlung — ABER ehrlich kennzeichnen ("in Prosa nacherzählt"), NICHT als Original ausgeben (sonst Bruch des "kein gecovertes Original"-Prinzips).
- Eigene Produktlinie, redaktionelle Sorgfaltsarbeit (kein Pipeline-Massendurchlauf), nach dem Start.
- Eigene engl. Übertragung aus gemeinfreiem Original = gehört dir (umgeht Übersetzer-Copyright).
- Odyssee-Werbechance: Nolan-Film 17.7.2026 — auf Homer-Suchwelle aufspringen ERLAUBT, aber Film/Plakat/Damon/Marke NICHT anfassen (Universal-Markenrecht). Nur Homers Werk bewerben, nicht den Film. Ein Aufmerksamkeits-MOMENT, Katalog nicht daran hängen.

### Monetarisierung der Einstiegsstufe: Freemium + kuratierte Werbung
- **Modell:** Gratis-Nutzung mit Werbung; 2,99/Monat entfernt Werbung. Etabliert, null Erklärungsaufwand, Einstiegshürde = 0 (holt die ~5 Mio Gutenberg-Gratis-Downloader ab).
- **Drei Einnahmeströme:** Werbung (Gratis-Nutzer) + Abo 2,99 (werbefrei) + Vollkäufe (eigentliche Kasse). Abo ist v.a. KONVERSIONS-Werkzeug: macht anonyme Gratis-Nutzer zu bekannten Zahlern mit hinterlegtem Zahlungsmittel → Vollkauf wird 1 Klick.
- **2,99 NICHT als "keine Werbung" verkaufen, sondern als "ungestörter Lernfluss"** — betont Lernwert statt Ärgernis-Entfernen, passt zur Premium-Marke.
- **Werbe-Nordstern = Klassik Radio:** dezent, kuratiert, an gebildetes Publikum (Reisen, Kultur, Bildung, Verlage), in den ÜBERGÄNGEN — niemals im Hör-/Lern-/"Ups"-Fluss (zerstört das Kernerlebnis, im Auto sogar gefährlich ablenkend).
- **REALISMUS-Wächter:** Kuratierte Premium-Werbung verlangt REICHWEITE (Direktdeals). Junge App ist anfangs auf programmatische Netzwerke (AdMob etc.) angewiesen → liefern grellen Müll, optimiert auf Klick nicht Würde, beschädigt Premium-Anmutung. Klassik-Radio-Qualität ist das ZIEL, nicht der Start.
- **Start-Empfehlung:** Einstiegsstufe anfangs werbefrei ODER nur EIGENWERBUNG ("dieser Titel auch als Vollproduktion verfügbar") — passt perfekt, markenkonform, treibt direkt die Vollkäufe. Fremdwerbung à la Klassik Radio erst einführen, wenn Reichweite Direktdeals/Werbe-Kontrolle erlaubt.
- **Zielkonflikt bewusst:** max. Werbeertrag vs. Markenwürde — nicht beides maximal. Bei diesem konzentrations-/anspruchsbasierten Produkt Würde priorisieren.
- **Offene Frage (zu prüfen):** Lässt sich Werbe-SELEKTION (Kategorien aus-/einschließen) in Google AdMob / Apple-Ad-Netzwerken technisch umsetzen? — Ja, grundsätzlich: Netzwerke bieten Kategorie-/Content-Filter und Block-Listen, aber grobkörnig. Echte Kuratierung ("nur Kultur/Bildung") nur über Direktvermarktung oder Premium-Vermarkter ab gewisser Reichweite. Für Start: Eigenwerbung umgeht das Problem ganz.

### Heikle Titel: drei Sorten, drei Behandlungen (Erkenntnis dt. Katalog)
Beim Sichten des deutschen Katalogs (847 Kandidaten) tauchten heikle Titel auf. Sie brauchen UNTERSCHIEDLICHE Behandlung — nicht über einen Kamm scheren:

1. **Historisch belastet** (z.B. Bettauer "Die Stadt ohne Juden" — antifaschistische Satire, aber Titel verstörend + von Falschen vereinnahmbar; Feuchtwanger/Hauff "Jud Süß").
   → RAUS aus Standard-Katalog. Grund: Werk funktioniert NUR mit Einordnung/Kontext, den das automatische Schaufenster (Auto-Klappentext, Pipeline-Vertonung) NICHT liefern kann. Kriterium allgemein: *Wenn ein Werk nur mit erklärendem Rahmen funktioniert, gehört es nicht in ein Schaufenster ohne Rahmen.* Missbrauchs-/Missverständnisrisiko + DE/AT-Sensibilität bei NS-Bezug zu hoch.

2. **Erotik / nicht jugendfrei** (z.B. Sacher-Masoch "Venus im Pelz", †1895, PD sauber).
   → NICHT raus (legitime Literatur, keine Vereinnahmungsgefahr), aber GATING nötig:
   - Eigene Kategorie "Reife Inhalte" + Altersabfrage/Gating, nicht im offenen Schaufenster zwischen Märchen.
   - **App-Store-Realität:** explizite Inhalte können Alterseinstufung der GESAMTEN App hochsetzen (Apple besonders streng) → Reichweite-Einschränkung. Muss bewusst entschieden werden.
   - **Markenfrage:** kultivierte Positionierung ("Cocktailparty-Stolz") — Erotik nicht unvereinbar, aber verändert Anmutung.
   - **Entscheidung:** NICHT im Start-Katalog. Eigenes Kapitel später, wenn App steht und "Reife Literatur"-Kategorie mit ordentlichem Gating bewusst aufgesetzt wird.

3. **Klingt heikel, ist harmlos** → normal behandeln.

Bauchgefühl trennt Gruppe 1 zuverlässig (CK-Reflex bei Bettauer war goldrichtig). Gruppe 2 = bewusste Produktentscheidung für später. Generell: dt. Literatur der 1920er/frühen 30er enthält mehr historisch aufgeladene Titel als der englische Katalog → wacher Blick beim Sichten.

### Inhaltshinweise pro Buch (Qualitätsmerkmal ggü. bloßer PD-Abbildung)
Gedanke (CK): pro Buch Hinweise zu Gewalt, Frauenfeindlichkeit, diskriminierender Sprache im historischen Kontext, Suizid-Darstellung etc. — als Respekt vor dem mündigen Hörer UND als Differenzierung gegenüber Konkurrenz, die PD-Werke nur kommentarlos abbildet.

**Warum sinnvoll:** PD-Literatur ist alt → voll von zeittypischen Haltungen/Sprache, die heute verstören (rassistische Begriffe, Frauenbilder, Kolonialblick). Informierter Hörer statt ahnungsloser Überraschung. Qualitäts-/Seriositätssignal.

**Tücken (Wächter):**
- KI unzuverlässig in BEIDE Richtungen: ÜBERSIEHT (subtile Passage ohne Schlagwort) = gefährlicher, weil falsche Sicherheit; ÜBERWARNT (jede Ohrfeige = "Gewalt") = stumpft ab, entwertet System.
- Warnung = VERSPRECHEN = Haftung. "Wo keine Warnung, ist nichts" — wird bei Lücke gebrochen, schlimmer als gar nicht gewarnt. Vollständigkeits-Erwartung mit KI-Prüfung nicht einlösbar.
- Kulturell umkämpft: manche schätzen Triggerwarnungen, andere empfinden sie als Bevormundung/Zensur des Erbes. → dezent + optional (ausklappbar, nicht aufdringlich vorangestellt).

**Gewählter Ansatz (gestuft):**
1. **Pauschale Grundnote für ALLE historischen Werke** (immer korrekt, keine falsche Vollständigkeits-Garantie, rechtlich sicher, automatisierbar): "Dieses Werk stammt aus [Jahr] und spiegelt Haltungen und Sprache seiner Zeit, die heute als diskriminierend oder verstörend empfunden werden können."
2. **Spezifische Hinweise nur bei EINDEUTIGEN Fällen, von Mensch geprüft** — nicht KI-Massendurchlauf. Lieber wenige verlässliche als flächendeckend-fehleranfällige.
3. **KI assistiert, entscheidet nicht:** liest Werk, SCHLÄGT VOR "hier evtl. Hinweis zu X", Mensch verantwortet. Gleiches Mensch-Maschine-Muster wie Titelauswahl/Wälzer-Schnitt — hier besonders wichtig, weil Verantwortung schwerer wiegt.

### Werktyp "Epos-Case": uralte Vers-Stoffe als Aufmerksamkeits-Bringer (Nacherzähl-Linie)
Erkenntnis: Homer (Odyssee/Ilias), Nibelungenlied, Dante, Beowulf, Gilgamesch, Edda/Sagas, Rolandslied, 1001 Nacht u.a. fallen alle durch DASSELBE Raster — ein eigener Werktyp, systematisch zu behandeln statt einzeln zu zerdenken.

**Gemeinsame Merkmale:**
- Uralt + HERRENLOS-frei: kein Rechteinhaber, kein "Fafnir auf dem Hort" (anders als Karl May). Stoff gehört wirklich allen.
- Original = Versepik → durch satzbasierte Pipeline NICHT vertonbar. Teils zusätzlich unverständliche Sprachstufe (Mittelhochdeutsch etc.).
- Lösung = Prosa-NACHERZÄHLUNG: entweder alte gemeinfreie neuhochdt./engl. Übertragung ODER (sauberer) EIGENE Nacherzählung → gehört dann uns, da Quellstoff frei.
- ACHTUNG Fassungs-Falle: MODERNE Nacherzählungen sind geschützt (z.B. Nibelungen: Lechner, Behmel 2001). Stoff frei ≠ jede Fassung frei. Nur alte freie Quelle oder Eigenfassung.
- Kulturelle Gründungsmythen → hohe Bekanntheit, natürliche Aufmerksamkeit, große Reichweite.
- Brauchen SENSIBILITÄT: Gewalt, archaische Frauenbilder → Inhaltshinweise. Nibelungen ZUSÄTZLICH ideologische NS-Vorbelastung ("Nibelungentreue", Wagner-Vereinnahmung) → bewusst, sachlich, dem Stoff dienend aufbereiten; NICHT die pathetisch-heroische NS-Lesart bedienen.

**Strategische Einordnung:**
- Höherer Aufwand (redaktionelle Sorgfaltsarbeit, kein Pipeline-Massendurchlauf) — aber große Aufmerksamkeits-Bringer. Bewusst investieren.
- Ehrliche Kennzeichnung "in Prosa nacherzählt" (kein "Original"-Etikettenschwindel, wahrt das "kein gecovertes Original"-Prinzip).
- **Timing-Unterschied:** Odyssee hat ZEITFENSTER (Nolan-Film 17.7.2026, Suchwelle — Film/Marke NICHT anfassen, nur Homers Stoff). Nibelungen haben GEDULD (dt. Dauerpräsenz, kein Hollywood-Anlass nötig). → Odyssee zeitlich priorisieren, Nibelungen laufen nicht weg.
- Eigene Prosa-Übertragung aus freiem Stoff = schützenswerte Eigenleistung (Schöpfungshöhe vorausgesetzt) — aber als PRODUKTNUTZEN denken, nicht als Rechts-Schutzschild.

### Quelle Wikisource: Kurzformen (Märchen/Fabeln/Sagen) für Einsteiger
Entdeckung (CK): Wikisource für Romane fast irrelevant, ABER riesiges Verzeichnis an Märchen, Fabeln, Sagen.

**Warum strukturell so:** Wiki-Mechanik (viele Hände, kleinteilig) begünstigt KURZE abgeschlossene Texte. Gutenberg digitalisiert ganze Bücher (romanlastig) → Wikisource füllt genau die Lücke, die Gutenberg lässt.

**Warum wertvoll fürs Lernprodukt:** Kurzformen = didaktisch Gold für Einsteiger. Ganze Fabel in 5 Min = komplettes Erfolgserlebnis (Anfang→Pointe), sprachlich einfach, narrativ klar, kulturell vertraut (Kontext erleichtert Fremdsprach-Verstehen), kurz genug dass häufiges "Ups" nicht frustriert. Deckt die Einsteiger-Kurzform ab, die der romanlastige Gutenberg-Bestand vermissen lässt.

**Tücken:**
- Andere ERNTETECHNIK: kein sauberer Volltext wie Gutendex, sondern MediaWiki-API + Wiki-Markup parsen, Vorlagen entfernen, Werke teils auf viele Unterseiten verteilt. Eigenes Werkzeug nötig.
- QUALITÄT schwankt (offenes Wiki). Auf Korrektur-Status achten ("validiert" vs. roh) — sonst Tippfehler vertont.
- Übersetzer-/Bearbeiter-Falle (wie immer): Andersen=dän., Grimm=dt. Sammlung, Aesop=griech., La Fontaine=frz. → alte freie Übersetzung oder Original nehmen.
- Lizenz-Feinheit: gemeinfreier Kerntext frei, aber Wikisource-redaktionelle Zutaten (Anmerkungen, Einleitungen) ggf. CC mit Namensnennung → nur Kerntext nehmen.

**"Bügeleisen"-Bedarf (CK-Beobachtung):** Sprache teils SO angestaubt, dass Schüler es "weird" finden → vor Nutzung modernisieren. WICHTIG: anders als beim Roman (wo alte Sprache zum Werk gehört) ist bei Märchen-als-Lerntext das Altdeutsch reine Reibung ohne literarischen Mehrwert → Glätten didaktisch geboten.
- ZWEI Hitzestufen unterscheiden: (1) SANFT = veraltete Wortformen/Schachtelsätze glätten, Substanz/Ton/Handlung unangetastet → legitim, bleibt "das Märchen". (2) HEISS = echte Neufassung → eigenes Produkt, MUSS als "modernisiert/nacherzählt" gekennzeichnet werden.
- GEFAHR: KI rutscht unkontrolliert von sanft zu heiß (dichtet um, kürzt, "verbessert"), walzt den knappen Volkston-Charme zu glattem KI-Einheitsbrei platt. Falten raus, aber Stoff nicht plattwalzen. → kontrollierter, dokumentierter Glättungsgrad + menschliche Kontrolle.

**Einordnung:** Ergänzungsquelle für EIN Segment (Einsteiger-Kurzform), kein Gutenberg-Ersatz. Nicht jetzt — erst wenn Onboarding/leichte Einstiegstexte konkret fehlen. Dann erste Adresse.

### Quelle/Referenz: Public Domain Library (publicdomainlibrary.org)
Schön gemachte PD-Seite (EPUB/Kindle/Kobo-Downloads, kostenlos). Mehrere Lehren:

**Cover-Design als Markenzeichen:**
- Einheitliche Designsprache über alle Titel (flächige Farben, konsequente Versalien-Typo, wiederkehrendes Sonnen-/Stern-Emblem) macht aus PD-Sammlung eine MARKE. Hebt sofort über rohes Gutenberg-Niveau.
- LEHRE: eigene einheitliche Designsprache entwickeln. Prinzip (Einheitlichkeit = Wiedererkennung) lernen, Gestaltung NICHT kopieren — deren konkretes Cover-Design ist geschützte schöpferische Leistung (wie grüne Karl-May-Bände: Text frei, Verpackung geschützt).
- Besonders wichtig für KI-GENERIERTE Cover: festes Template (Typo-Anordnung, Farblogik, Markenelement) → 300 Auto-Cover wirken wie FAMILIE statt 300 zufällige KI-Bilder.
- Titel-AUSWAHL darf man sich abschauen (Allgemeingut, Gegencheck zur eigenen Liste); konkretes Design nicht.

**EPUB als Quellformat (Fallback-Gedanke CK):**
- Saubere EPUBs sind strukturierter als Gutenberg-Rohtext (Kapitelmarken, Absätze, kein Boilerplate) → weniger Pipeline-Vorarbeit, weniger Parsing-Ärger (vgl. Stage-04b-Anführungszeichen-Crash).
- ABER: fremde PD-EPUB-Seiten nur für Top-Titel (kleine Sammlung, nur Mega-Klassiker), und Editions-/Übersetzerprüfung nötig (welche Übersetzung haben sie genommen? → Übersetzer-Copyright).
- BESSERE Umsetzung des Gedankens: Gutenberg bietet SELBST EPUBs (neben .txt) → gleiche rechtlich geklärte Quelle, aber strukturierteres Format. Sauberer als fremde Seite.

**Finanzierung über SPENDEN (Beobachtung CK):**
- Sie finanzieren sich über Spenden ("Your 1$ can help share another great book"), NICHT über Verkauf.
- LEHRE/Abgrenzung: Das ist ein REINES LESEPRODUKT (gemeinfreier Text als schönes EPUB) — die bloße Form-Veredelung trägt KEIN Verkaufsmodell, nur Spenden/Goodwill. Bestätigt: wer im PD-Raum VERKAUFEN will, braucht echte funktionale Veredelung (Vertonung + Lernmechanik), nicht nur schöne Form. ReadLayer verkauft FUNKTION, nicht nur Form → rechtfertigt Bezahlmodell, wo PD-Lib nur betteln kann.
- Kein Konkurrent: sie veredeln Form (Lesen), ReadLayer veredelt Funktion (Hören+Lernen). Gleicher Rohstoff, anderes Produkt.

### WUNSCHLISTE: vermisste Weltliteratur-Schwergewichte (Gutenberg-Lücken)
Erkenntnis: Gutenberg ist bei NICHT-englischer Weltliteratur lückenhaft — und zwar gerade bei den HAUPTWERKEN. Auf primär englischsprachiger Plattform sind FR/RU/IT/ES-Klassiker nur zufällig + unvollständig vertreten. Die bisherigen Kataloge zeigen, was Gutenberg HAT, nicht was FEHLT.

**Methoden-Umkehrung:** Nicht "was hat Gutenberg, das gut ist", sondern "welche bekannten Großwerke fehlen mir, und wo hole ich sie gezielt". Diese Liste = Suchprogramm, abzuarbeiten über die RICHTIGEN Quellen (frz./russ. Bestände, Gallica, Zeno.org, Projekt Gutenberg-DE, sprachspezifisches Wikisource), NICHT über Haupt-Gutenberg.

**Vermisste Titel (wächst):**
- Stendhal: "Rot und Schwarz" (Le Rouge et le Noir), "Die Kartause von Parma" — FEHLEN komplett. Gutenberg hat nur Nebenwerke (Römerinnen, Äbtissin von Castro). Stendhal †1842, PD sauber → Lücke ist Verfügbarkeit, nicht Recht.
- Gottfried Keller: "Grüner Heinrich", "Leute von Seldwyla" (Band 1) — Keller fehlte im dt. Harvest fast ganz.
- (vermutlich) Zola, Maupassant, Tolstoi "Krieg und Frieden", weitere FR/RU-Hauptwerke — beim Durchgehen prüfen.

**Bezugsquellen für die Lücken:**
- Französisch: Gutenberg-FR-Zweig, Wikisource-FR, Gallica (BnF-Digitalbibliothek).
- Deutsch (fehlende dt. Klassik + dt. Übersetzungen): Projekt Gutenberg-DE (ANDERE Plattform als US-Gutenberg!), Zeno.org, Wikisource-DE.
- Russisch/andere: jeweiliges Sprach-Wikisource, ggf. eigene Übertragung aus freiem Original.
- Bei Übersetzungen IMMER Übersetzer-Tod prüfen (Übersetzer-Copyright) ODER Original nehmen + selbst übertragen.

**Schwerpunkt (CK):** französische + russische Literatur stark gewünscht; skandinavisch "Beifang" außer Ibsen.

### ✓ ERLEDIGT: Cloud-TTS-Schnittstelle steht (07.06.2026)
Stage 07 Cloud-TTS funktioniert end-to-end. Durchsatz-Wand (Preview-Limit ~85/Tag) durchbrochen.
- Projekt "readlayercloud" (Nr. 224615759334), Billing aktiv.
- APIs aktiviert: Cloud Text-to-Speech UND aiplatform.googleapis.com (Agent Platform / Vertex AI — Gemini-Stimmen laufen darüber!).
- Service-Account service@readlayercloud.iam.gserviceaccount.com mit Rolle "Agent Platform User" (= Vertex AI User, enthält aiplatform.endpoints.predict).
- JSON-Key lokal: C:\Users\sabin\read_layer\JSON_Key\readlayercloud-*.json (GEHEIM, nicht in Git).
- Auth via $env:GOOGLE_APPLICATION_CREDENTIALS auf Key-Pfad.
- Modell: gemini-2.5-flash-tts (NICHT 3.1-preview — beide laufen über aiplatform, 2.5 ist das abgenommene "hier perfekt"). Stimme Charon, MP3.
- Lehre für künftige Einrichtung: BEIDE APIs nötig + Service-Account braucht "Agent Platform User"-Rolle, sonst aiplatform.endpoints.predict denied. IAM-Änderungen brauchen 2-5 Min zum Durchsickern.

NÄCHSTE SCHRITTE (Reihenfolge):
1. Charon-MP3s anhören: Klang ok? Liest er NUR Text (nicht die Regie-Präambel)?
2. Klappentext-Erzeugung als Pipeline-Stage bauen (dreiteilig, satzparallel DE/EN für "Ups"-Demo) — der Schaufenster-Baustein.
3. Ersten Titel komplett als Schaufenster-Teaser: Klappentext erzeugen → kurz vertonen (wenige Schnipsel, Durchsatz unkritisch).
4. Stage 04b Score-Call chunken (kleiner Fix, offen).
5. Ersten Titel end-to-end inkl. Voll-Audio (jetzt möglich, da Durchsatz frei).

### ✓ ERLEDIGT: Klappentext-Erzeugung (Stage A + B) steht (07.06.2026)
Zweistufige Schaufenster-Textkette, an Time Machine (Kap. 1) getestet, liefert gute Qualitaet.

**Stage A — Metadaten-Extraktion** (stage_A_metadata.py):
- Liest Rohtext (Anfang 12k Z. + Mitteprobe 6k Z.), Gemini gemini-3.5-flash, ERZWUNGENES JSON-Schema.
- Extrahiert WEICHE Metadaten: genre, subgenres, ton, schauplatz, zeit, hauptfiguren, essenz, leseprobe_zitat (woertlich!), inhaltshinweise, sicherheit (unkritisch/pruefen).
- KERNPRINZIP greift: leitet alles AUS DEM TEXT ab, NICHT aus Modell-Vorwissen -> kein Fabulieren. Beweis: bei Kap.1 keine Eloi/Morlocks erfunden.
- sicherheit-Flag = automatischer Vorfilter fuer heikle/Gating-Titel.

**Stage B — Klappentext-Komposition** (stage_B_blurb.py):
- Nimmt NUR das Stage-A-JSON + harte Metadaten (--autor --tod --titel), liest Buchtext NICHT erneut -> kann auch nicht fabulieren.
- Dreiteilig (BOARD "Koeder vor Einordnung"): 1. Koeder=woertl. Zitat, 2. Einordnung, 3. Autor.
- Jeder Block = satzparallele DE/EN-Paare -> direkt fuer "Ups"-Demo nutzbar.
- ERZWUNGENES JSON-Schema. Test bestand: Koeder woertlich, Einordnung ehrlich (keine Vorwissen-Erfindung), Autor faktisch, Paare deckungsgleich.
- WARNUNG: Autor-Block nutzt Modell-Vorwissen -> bei OBSKUREN Autoren pruefen/mehr Fakten mitgeben. Bei bekannten (Wells) unkritisch.

**ZUGANG Textstufen:** Gemini AI-Studio-Key (generativelanguage.googleapis.com), $env:GEMINI_API_KEY. Simpel, kein Service-Account noetig (Textgenerierung hat kein Durchsatzproblem).

**Komplette Pre-Audio-Schaufenster-Kette steht jetzt:**
  Rohtext -> Stage A (Metadaten) -> Stage B (Klappentext DE/EN) -> [kurze Vertonung via Cloud-TTS, Durchsatz unkritisch]

NAECHSTE SCHRITTE:
1. Gegentest an VOLLSTAENDIGEM Rohtext (nicht nur Kap.1): bleibt Extraktion bei Anfang+Mitte sauber?
2. Teaser-Vertonung: Klappentext-Saetze (Koeder+Einordnung) durch Stage 07 Cloud-TTS -> erster kompletter Schaufenster-Eintrag (Text+Audio).
3. Stage 04b Score-Call chunken (kleiner Fix, offen).
4. Ersten Titel end-to-end inkl. Voll-Audio.

### Erkenntnis: Eigennamen-Aussprache bei Charon (kein SSML!)
Charon/Gemini-TTS unterstuetzt KEIN SSML (bestaetigt) -> keine <lang>/<sub>-Tags fuer Aussprache.
ABER: prompt-gesteuert -> kontextueller Hinweis funktioniert.

**Getestet (Wells-Satz, dt., 3 Prompt-Varianten):**
- A (neutral): "Ha Ge Wells" — falsch (dt. Buchstabierung).
- B (Befehl "sprich engl. Namen englisch"): zu grob — sprach auch das JAHR englisch. Uebergeneralisiert.
- C (kontextuell "der Text erwaehnt H. G. Wells, sprich DIESEN Namen englisch"): KORREKT — nur der Name englisch, Rest deutsch. GEWINNER.

**Regel (im teaser_tts.py verdrahtet, ~95% korrekt):**
- Autorname wird in der AUSGANGSSPRACHE DES WERKS ausgesprochen (Dumas frz., Wells engl., Dostojewski russ.).
- Quellsprache kommt aus Metadaten (schon vorhanden, kein neues Feld) -> --quellsprache.
- Hinweis (C-Prompt) wird NUR angehaengt, wenn Schnipsel-Sprache != Quellsprache (dt. Satz / engl. Autor). Sonst kein Hinweis.
- Konkreter Name explizit nennen (nicht allgemeine Regel) — sonst Uebergeneralisierung wie Variante B.
- KEINE Uebersteuerung fuer Ausnahmen (Conrad etc.) — bewusst in Kauf genommen, 95% reicht.
- Spaeter ggf. Glossar-basiert verallgemeinern (pro Eigenname Aussprache-Hinweis), wenn auch Namen IM Werktext betroffen.

### Feinschliff Aussprache: Ueberbetonung geloest (Variante D)
Problem nach C-Prompt: Name korrekt englisch, aber Charon UEBERBETONTE ihn (albern).
Ursache: Aufmerksamkeit im Prompt -> Charon liest sie als Sprech-Betonung.
Getestet 4 Varianten (C aktuell, D unbetont, E beilaeufig, F minimal) -> D gewinnt.
D-Formulierung (jetzt im teaser_tts.py verdrahtet):
  "It contains the name '<AUTOR>' - pronounce it with <SPRACHE> phonetics, but completely
   naturally and WITHOUT special emphasis, as just another word in the flowing sentence:"
-> Aussprache korrekt UND natuerlich eingebettet. Generalisiert ueber --autor + --quellsprache.
Zweisprachiger Teaser damit rund: korrekte Aussprache + natuerliche Betonung, auto pro Autor.
