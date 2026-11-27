# PROMPT — Stimmdesigner auf Qwen3-TTS umstellen (geplant 26.11.2026)

## Anlass (25.11.2026)
Gemini-Stimmdesign als Quelle für Klon-Referenzen (Fish Drama 3, Chatterbox-VC) und Feintuning ist rechtlich heikel
(Gemini-Bedingungen: keine Nutzung zur Entwicklung konkurrierender Modelle). Ersatz: **Qwen3-TTS VoiceDesign 1.7B**,
Apache-2.0, 10 Sprachen (u. a. DE, EN, ZH, FR, ES, IT).

## Entscheidung
- Stimmen werden mit Qwen3 VoiceDesign aus der Beschreibung erzeugt (lokal oder Modal).
- **Je Sprache eigener Referenz-Clip** aus derselben Designstimme (kein Akzent-Mitschleppen beim Sprachwechsel).
- Bestehende Gemini-Stimmen werden aus denselben Beschreibungen mit Qwen3 neu erzeugt; Gemini-Clips nicht weiter als Referenz/Training nutzen.
- Steckbrief-Herkunftsvermerk: „Qwen3-TTS VoiceDesign, Apache-2.0, keine reale Person“.

## Stimmen-Matrix (CK-Vorschlag 25.11.)
- **30 männlich + 30 weiblich**, je 5 Altersstufen × 6 Charaktere:
  - Alter: jung (18–25), jung-erwachsen (25–35), mittel (35–50), reif (50–65), alt (65+).
  - Charakter: warm/väterlich-mütterlich, kühl/autoritär, verschmitzt/ironisch, nervös/gehetzt, rau/brüchig, weich/verträumt.
- Je Stimme zusätzlich Eigenheiten in der Beschreibung (Tempo, Lispeln, Heiserkeit, Dialektfärbung, Lachen im Ton).
- **Kinderstimmen** (zusätzlich, ~10): Jungen/Mädchen 5–8 und 9–13 Jahre; direkt per Beschreibung in VoiceDesign,
  sonst aus hellen Frauenstimmen abgeleitet (Pitch/Formant-Verschiebung) – beides testen.
- IDs nach Schema `m_<alter>_<charakter>`, `w_…`, `k_…`; Steckbrief je Stimme (Beschreibung, Seed, Datum, Herkunft).
- Erzählerstimmen als Teilmenge markieren (ruhig, lange Passagen tragfähig).

## Cockpit-Anbindung
- Matrix = Standardauswahl beim Casting (Hörkatalog als Auswahlansicht, Filter Alter/Charakter/Geschlecht).
- **Zusätzlich „Neue Stimme erzeugen“ direkt im Cockpit** (CK 25.11.): Beschreibung eingeben bzw. Regler
  (Geschlecht, Alter, Charakter, Eigenheiten) → Qwen3 VoiceDesign auf Modal → 3 Varianten anhören → eine übernehmen →
  automatisch Referenz-Clips je Sprache + Steckbrief, Ablage im Stimmen-Archiv (eigene Stimmen je Kunde/Projekt markiert).
- Freitext-Beschreibung ohne Bezug auf reale Personen/bekannte Sprecher (Hinweis + einfacher Namensfilter).

## Exklusivität (CK 25.11.: große Verlage wollen keine Stimmen, die auch andere nutzen)
- Zwei Stufen im Archiv:
  - **Katalog** (Matrix): geteilt, für TÆLLA-eigene Werke, Freemium, kleine Kunden.
  - **Exklusiv / Hausstimme**: im Cockpit für einen Verlag erzeugt, nur in dessen Mandant sichtbar, nie im Katalog.
- Exklusive Stimme: Seed + Beschreibung + Clips gesperrt (keine Wiederverwendung, Ähnlichkeitsprüfung gegen Katalog
  und andere Exklusivstimmen per Speaker-Embedding, Schwelle festlegen).
- Optional Katalogstimme exklusiv kaufen → wird aus dem Katalog genommen (nur wenn noch nicht in veröffentlichten Werken).
- Vertraglich: Nutzungsrecht exklusiv je Verlag, Herkunftsnachweis aus Steckbrief; Upgrade später: Feintuning als Hausstimme.

## Echte Sprecherstimmen klonen (CK 25.11.: Verlage mit vertraglich erworbenen Sprecherrechten)
- Qwen3 Base klont aus kurzer Referenz (ab ~3 s; für Qualität 10–30 s je Sprache).
- Cockpit-Weg „Sprecherstimme hochladen“: nur mit Nachweis der Rechte:
  - Bestätigung des Verlags, dass der Vertrag **ausdrücklich KI-Stimmklon/synthetische Nutzung** abdeckt
    (klassische Sprecherverträge regeln oft nur Aufnahmen), Vertragsdatum, Laufzeit, Umfang (Werke, Sprachen).
  - Einwilligungsaufnahme des Sprechers (fester Satz + Datum) als Beleg im Steckbrief.
- Stimme automatisch `exklusiv:<mandant>`, nie Katalog, nie für Training anderer Stimmen.
- Laufzeitende/Widerruf → Stimme sperren; bereits erzeugte Audios gemäß Vertrag.
- Kennzeichnung: KI-generiert mit Stimme von <Sprecher> (AI Act); Wasserzeichen an.

### Sprecherstimme in Fremdsprachen (CK 25.11.)
- Bekannte Sprecher/Stimmen in Sprachen einsetzen, die sie selbst nicht sprechen (Vorbild: US-Stars in Werbung JP/CN).
- Weg: Referenz in Muttersprache des Sprechers → Qwen3 Base cross-lingual → Zielsprache; daraus Referenz-Clip je
  Zielsprache erzeugen, Sprecher (oder Verlag) gibt jeden Sprach-Clip frei.
- Akzent: Regler „Akzent behalten / neutralisieren“ (Wiedererkennung vs. muttersprachlicher Klang) – im Test prüfen.
- Rechte-Felder je Stimme um **Sprachen und Territorien** erweitern; Lizenz je Sprache separat abrechenbar
  (Erlösbeteiligung Sprecher je Sprache).
- Muttersprachliche Abnahme der Zielsprach-Fassung (Aussprache, Betonung) vor Auslieferung.

## Aufgaben
1. Qwen3-TTS (VoiceDesign + Base) auf Modal oder lokal lauffähig machen.
2. Matrix-Beschreibungen schreiben (DE-Beschreibung + EN-Prompt), 60 + ~10 Stimmen erzeugen; je Stimme 3 Seeds, CK wählt.
3. Je Sprache (DE, EN; später ZH) Referenz-Clip 10–30 s, WAV 24/48 kHz mono, trocken, mit Transkript; Frage/Ausruf/Flüstern-Sätze.
4. Hörkatalog (HTML-Seite mit Player je Stimme, Filter Alter/Charakter/Geschlecht) für die Auswahl.
5. Casting aus casting.json auf Matrix-Stimmen umbesetzen; Test Alice Kap. 7 mit Fish-Erzähler + Chatterbox-VC;
   Hörvergleich zu `de/fish_erz_vc_c007_de.wav`. Märzhase/Hutmacher in der Tonlage weiter auseinanderlegen.
6. Erzeugungs-Ablauf als Modal-Funktion kapseln, damit das Cockpit ihn später direkt aufrufen kann.
7. Archiv-Feld `status` (katalog / exklusiv:<mandant>), `herkunft` (design / sprecher), Rechte-Felder
   (Laufzeit, Werke, Sprachen, Territorien) und Speaker-Embedding je Stimme mit anlegen.
8. Cross-lingual-Probe: eine DE-Designstimme → EN und ZH, Akzent bewerten (Fangyoung für ZH).
9. Kostenlog wie im Fish-Test.
