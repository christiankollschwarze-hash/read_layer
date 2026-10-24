# ReadLayer — Datenmodell Autor / Werk / Fassung (ENTSCHIEDEN)

> Status: Alle Strukturfragen geklaert (Stand heute). Bereit zur Implementierung.
> Reihenfolge der Umsetzung siehe ganz unten.

## Grundprinzip
Drei Entitaeten, sauber getrennt — jede Tatsache an genau EINER Stelle:
1. **AUTOR**   — Schluessel = Wikidata-Q-ID (z.B. Q42). Existiert einmal, Werke verweisen darauf.
2. **WERK**    — ein literarisches Werk, liegt UNTER seinem Autor. Slug = englisch.
3. **FASSUNG** — konkrete Sprachversion eines Werks (de/en/fr/...), mit Formaten/Status.

Beziehung: Autor 1—n Werk 1—n Fassung.

---

## MARKEN-TRENNUNG: Plattform vs. Label (zukunftssichernd)
Bewusste Trennung von Anfang an, um spaeter Fremdverlage einladen zu koennen, ohne
schmerzhafte nachtraegliche Entflechtung:

- **PLATTFORM (App)** = die Buehne: Schaufenster, Lern-Mechanik ("Ups"), Distribution.
  Neutral, beherbergt mehrere Labels. (Arbeitsname-Kandidat: "ReadLayer" klingt nach
  Technologie/Plattform -> eher App-Name. Finale Namensentscheidung offen.)
- **LABEL / VERLAG** = der Inhalte-Produzent: unsere eigenen e-books/Audios sind EIN Label
  auf der Plattform. Spaeter koennen FREMDE Verlage als weitere Labels publizieren.
  (Eigener, eher verlegerisch/literarisch klingender Name -> sieht auf Cover gut aus. Offen.)

**Modell-Verankerung:** Feld `publisher` (Label-Kennung) auf WERK-Ebene (siehe book.json),
Default = eigenes Label. So filtert die App neutral nach Label; Fremdverlage bekommen
spaeter eigene Kennung.

**WICHTIG (Scope-Disziplin):** JETZT nur die STRUKTUR trennen (dieses Feld + Konzept).
NICHT jetzt: zweite Markenidentitaet ausarbeiten (Logos/Namen/CI) oder Multi-Verlags-
Funktionen bauen (Rechteverwaltung, Abrechnung, Publisher-Onboarding). Das ist Phase 3/4,
nach dem ersten ausgelieferten eigenen Werk. Platzhalter-Labelname reicht fuers Erste.

OFFENE NAMENS-ENTSCHEIDUNG (in Ruhe, kein Blocker):
- Ist "ReadLayer" die App (Plattform) oder das Label? Instinkt: App.
- Eigenes Label braucht dann eigenen Namen.

---

## ID-SCHEMA (global eindeutig)
```
<AutorID>_<book-slug-englisch>_<sprache>
Beispiel:  Q42_time-machine_de
```
- **Slug immer ENGLISCH** (sprachuebergreifender Anker, international etabliert, stabil).
  Bei nicht-engl. Originalen ist der Slug die engl. Form des Titels
  (z.B. Dumas -> `count-of-monte-cristo`, NICHT `comte-de-monte-cristo`).
  Begruendung: Slug bezeichnet das WERK sprachneutral; die Sprache steckt in der Endung.
- Gleichlautende Werke verschiedener Autoren = KEIN Problem: Werk liegt unter dem Autor,
  die Struktur trennt sie automatisch.

---

## ENTITAET 1: AUTOR  (Schluessel: Wikidata-Q-ID)
Quelle HART = Wikidata, Quelle WEICH = Wikipedia (getrennt markiert).
**Uebersetzer werden NICHT im Autor gefuehrt** (siehe Fassung/Werk).

```
authors/<Q-ID>/author.json
{
  "wikidata_id": "Q42",
  "verified": true,                       // ID menschlich bestaetigt (Verifikationsschritt)
  "name_display": "H. G. Wells",
  "name_sort": "Wells, Herbert George",

  // -- HART (Wikidata) --
  "geburtsjahr": 1866,                    // P569
  "todesjahr": 1946,                      // P570
  "geburtsort": "Bromley, England",       // P19
  "wirkungssprache": "en",                // = Default fuer Namensaussprache (Variante D);
                                          //   leitet sich i.d.R. aus Originalsprache der Werke ab
  "notable_works": [                      // P800 (nur die paar Hauptwerke, NICHT Gesamtwerk)
     {"wikidata_id": "Q...", "titel": "The War of the Worlds", "jahr": 1898}
  ],

  // -- WEICH (Wikipedia, interpretierend) --
  "epoche": "Viktorianisch / fruehe Moderne",
  "stilrichtung": ["Science-Fiction-Pionier", "Sozialkritik"],
  "bedeutung_kurz": "Mitbegruender der modernen Science-Fiction.",
  "quelle_weich": "wikipedia:en:H._G._Wells",

  // -- BESTAND (Knotenpunkt fuer App-Suche: welche MEINER Werke?) --
  "werke_im_bestand": ["time-machine", "war-of-the-worlds"]
}
```

---

## ENTITAET 2: WERK  (liegt unter dem Autor; Slug = englisch)
```
authors/<Q-ID>/books/<book-slug>/book.json
{
  "book_slug": "time-machine",
  "author_id": "Q42",                     // VERWEIS (keine Autordaten doppeln)
  "publisher": "<eigenes-label>",         // LABEL-Kennung (Marken-Trennung Plattform/Label).
                                          //   Default = eigenes Label; Fremdverlage spaeter eigene Kennung.
  "work_wikidata_id": "Q...",             // falls vorhanden (nicht jedes Werk hat eine)

  // -- HART (Wikidata/Gutenberg) --
  "titel_original": "The Time Machine",
  "originalsprache": "en",
  "erscheinungsjahr": 1895,               // P577
  "gutenberg_id": "35",

  // -- QUELL-UEBERSETZER (nur wenn QUELLE eine Uebersetzung ist!) --
  // Wichtig fuer PD-Pruefung. NICHT zu verwechseln mit unseren eigenen Sprachfassungen.
  // Leer = Quelle ist Originalsprache -> PD-Pruefung laeuft ueber den AUTOR.
  "quell_uebersetzer": "",                // z.B. "..." bei dt. Uebersetzung eines russ. Originals
  "quell_uebersetzer_todesjahr": null,    // maßgeblich fuer PD, falls Uebersetzer gesetzt

  // -- KLASSIFIKATION --
  "thema_codes": ["FBC"],                 // INTERN: Thema (kuratierte Teilmenge, s.u.)
  "bisac_codes": [],                      // EXTERN: erst im Nachgang generieren, wenn Distribution es verlangt
  "genre_eigen": "Science-Fiction",       // aus Werktext (Stage 09)

  // -- AUS WERKTEXT (Stage 09, ehrlich abgeleitet) --
  "ton": "intellektuell",
  "schauplatz": "...",
  "essenz": "...",
  "leseprobe_zitat": "...",
  "inhaltshinweise": [],
  "sicherheit": "unkritisch",

  // -- WEICH zum Werk (Wikipedia) --
  "bedeutung_werk": "...",

  // -- FASSUNGEN (unsere Sprachversionen) --
  "fassungen": [
     {"sprache": "de", "formate": ["teaser_audio", "full_audio"], "status": "fertig"},
     {"sprache": "en", "formate": ["teaser_audio"], "status": "teaser"}
  ]
}
```

---

## PD-PRUEFUNG (Regel, vom Titel rueckwaerts)
```
Hat der Titel einen quell_uebersetzer eingetragen?
   JA  -> pruefe quell_uebersetzer_todesjahr  (Uebersetzerrecht ist die juengere, maßgebliche Schranke)
   NEIN-> pruefe todesjahr des AUTORS          (Quelle = Original)
Gemeinfrei (EU) wenn maßgebliches Todesjahr + 70 < aktuelles Jahr.
```
Begruendung: Bei uebersetzter Quelle ist der Uebersetzer der spaetere Rechteinhaber;
beim Original der Autor. Die Pruefung findet automatisch den richtigen.

---

## ORDNERSTRUKTUR
```
authors/
  Q42/
    author.json
    books/
      time-machine/
        book.json
        raw.txt
        work/    stage00.json ... stage10.json
        output/  final.json, teaser_audio/, full_audio/
      war-of-the-worlds/
        ...
index.json          # zentrale Map: book-slug -> author_id (siehe unten)
```

### Anlege-Reihenfolge (Author First, O2 — idempotent)
```
1. Autor vorhanden?  (Wikidata-ID pruefen)
     NEIN -> Autor anlegen (authors/<Q>/author.json), Verifikationsschritt
     JA   -> Schritt 1 ueberspringen
2. Werk anlegen      (authors/<Q>/books/<slug>/)
3. Sprachfassung anlegen (Eintrag in book.json "fassungen")
```
Kein Cache — direkt real anlegen. Mehrfaches Ausfuehren = keine Doppelanlage (idempotent).

### Index-Map (O3)
- `index.json` im Root: bildet `book-slug -> author_id` ab.
- Zweck: work_path(book_slug) kann den Autor nachschlagen, ohne ihn ueberall mitzuschleppen.
- DISZIPLIN: NUR die Anlege-Logik (Schritt 1-3) schreibt in den Index, an EINER Code-Stelle.
  Nicht von Hand, nicht verstreut. Sonst laufen Ordner und Index auseinander.
- Empfehlung: kleiner "Index-Check" (prueft, ob Ordner == Index), als Diagnose bei vielen Buechern.

---

## KLASSIFIKATION (F2 entschieden)
- **Intern: Thema** — aber NICHT die komplette (riesige, teils lizenzbehaftete) Hierarchie.
  Stattdessen eine KURATIERTE TEILMENGE der Thema-Codes, die zu gemeinfreier Literatur passen
  (Belletristik-Klassiker, die paar Dutzend bei uns vorkommenden Genres). Als eigene schlanke Liste.
- **Extern: BISAC u.a.** — erst IM NACHGANG generieren, wenn ein Distributionsweg (StreetLib/BookBeat)
  sie verlangt. Thema -> BISAC ist eine bekannte Mapping-Aufgabe.
- OFFEN (zu recherchieren): welches System erwartet StreetLib/BookBeat konkret?

---

## NAMENSAUSSPRACHE (Variante D, Anbindung ans Modell)
- Autorname wird in der **wirkungssprache** des Autors ausgesprochen (Feld am Autor).
- Stage 10 (Teaser) nutzt: wenn Schnipsel-Sprache != wirkungssprache -> D-Prompt mit Name+Sprache.
- Seltene Ausnahmen (Conrad: Pole, schrieb Englisch) bewusst in Kauf genommen, keine Uebersteuerung.

---

## ENTSCHEIDUNGEN (alle getroffen)
- Autor/Werk/Fassung getrennt; jede Tatsache an einer Stelle. ✓
- Autor-Schluessel = Wikidata-Q-ID. ✓
- ID-Schema <Q>_<slug-en>_<sprache>, Slug immer englisch. ✓
- Wikidata = hart, Wikipedia = weich, getrennt markiert. ✓
- Verifikationsschritt fuer Autor-ID (Mensch bestaetigt einmal). ✓
- Author First Anlege-Reihenfolge, idempotent, kein Cache. ✓
- Zentrale index.json (slug->author), nur von Anlege-Logik gepflegt. ✓
- Uebersetzer NICHT am Autor; quell_uebersetzer am WERK (optional); PD-Pruefung vom Titel rueckwaerts. ✓
- Thema intern (kuratierte Teilmenge), BISAC extern im Nachgang. ✓
- Namensaussprache aus wirkungssprache (Variante D). ✓
- Marken-Trennung Plattform/Label: STRUKTUR jetzt (publisher-Feld am Werk), zweite Marken-
  identitaet + Multi-Verlags-Funktionen spaeter (Phase 3/4). Namensfrage App vs. Label offen. ✓

## UMSETZUNGS-REIHENFOLGE (morgen / naechste Schritte)
1. config.py: Pfade auf authors/<Q>/books/<slug>/ + index.json-Aufloesung (work_path schlaegt Autor nach).
2. index.json + Anlege-Logik (Author First, idempotent) + Index-Check.
3. Stage 08b: Wikidata-Aufloesung (wbsearchentities) -> Vorschlag -> Verifikation -> harte Fakten;
   Wikipedia -> weiche Angaben. Zweiphasig (Vorschlag separat, Abruf automatisch).
4. author.json / book.json Schemata final festklopfen (dieses Dokument).
5. Stage 09/10 auf das Modell umstellen (author_id-Verweis, Namensaussprache aus wirkungssprache).
6. Kuratierte Thema-Teilmenge definieren.
7. Bestehende 2 Buecher (Aesop, Time Machine) in die neue Struktur ueberfuehren.

## NOCH ZU RECHERCHIEREN (kein Blocker)
- Welche Klassifikation erwartet StreetLib/BookBeat (Thema? BISAC? eigenes?).
- Thema-Codes: welche Teilmenge frei nutzbar, Lizenzbedingungen EDItEUR.

---

## MARKE / LABEL — Favorit (Stand: in Markenpruefung)
**Name (Kandidat): "Somniosus Publishing"**
- Herleitung: *Somniosus microcephalus* = Groenlandhai, langlebigstes bekannte Wirbeltier
  (Exemplare moeglicherweise 400+ Jahre). Sinnbild fuer Werke, die Jahrhunderte ueberdauern.
  Zugleich "Schlaf-Hai" (behaebig) -> schoene Nebenassoziation fuer abendliches Hoeren.
- **Wappentier:** Groenlandhai als Signet im Imprint. Loest das "Bedeutung erschliesst sich
  nicht von selbst"-Problem: das Bild traegt die Geschichte. Passt als wiederkehrendes
  Cover-Markenelement (einheitliche Designsprache, vgl. Public Domain Library).
- Schreibweise offen: "Somniosus" (bedeutungstreu, aber lang/sperrig) vs. Kurzform "Somnios".
- Umsetzung: Designer-Freunde vorhanden. WICHTIG: Nutzungsrechte am Signet schriftlich
  vollstaendig an den Verlag uebertragen lassen (auch/gerade unter Freunden) -> sonst
  Urheberrechts-Unklarheit ausgerechnet im Markenkern.
- STATUS: Markenpruefung laeuft (CK). Zu pruefen: TMview Klassen 9/41/16 (Wort), Wiener
  Klassifikation fuer das Hai-Bildzeichen, Klangraum "somn-" (Somnium/Somnos/Somnio sind
  im Schlaf/Wellness-Bereich verbreitet), Domain, App-Store. Anmeldung erst EU, spaeter
  ggf. Madrid (USA als Perspektivmarkt). Endgueltige Freigabe = anwaltlich.
- Scope: Name+Wappen-KONZEPT steht. Logo-Ausarbeitung + Anmeldung = Phase 3/4, kein Blocker.

---

## EPUB-PRODUKTION — Qualitaetsmassstab (Notiz)
Das EPUB-Setting/Layout von Public Domain Library (publicdomainlibrary.org) gilt als
Qualitaets-MASSSTAB fuer die eigene EPUB-Produktion: sauberes professionelles Satzbild,
einheitliche Typografie, ordentliche Struktur (Kapitelmarken etc.).
- Prinzip uebernehmen (Niveau, Einheitlichkeit), Gestaltung NICHT kopieren (= geschuetzt).
- Form-Veredelung ergaenzt die Funktions-Veredelung (Vertonung+Lernen).
- Eigene EPUB-Designsprache, konsistent ueber den Katalog (Familie statt Zufall),
  passend zum Somniosus-Wappentier-Stil.
- Konkrete Umsetzung: spaeter (Phase Produktion), kein Blocker jetzt.
