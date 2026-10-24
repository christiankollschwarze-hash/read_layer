# PROZESS Klappentext-Erzähler (Teaser) — 19.10.2026

Entscheidung CK: Der Klappentext wird je Werk mit Chatterbox vertont, in der Audio-Linie produziert, über 710 exportiert und im TÆLLA-Katalog per Klick auf das Werk angespielt, bis der Nutzer weiterklickt. Gemini ist für alle Werke zu teuer. Neue Stage-Nummer nach Abnahme: **550 Teaser** (bisher 640).

## 1. Stimmen

| Erzähler | Deutsch | Englisch |
|---|---|---|
| weiblich | Mix-Stimme: LoRA `mix_v1` + Referenz `grossmutter_a` | Chatterbox-Standard + Overlay (VC) `grossmutter_a` |
| männlich | `herr_a` über das Mix-Gewicht (Test: Klon direkt *oder* Mix-Stimme + Overlay) | Chatterbox-Standard + Overlay (VC) `herr_a` |

## 2. Zuordnung Genre → Erzähler

| Gruppe | Genre-Werte (Stage 600, Stand 19.10.2026) | Erzähler | Ausnahme |
|---|---|---|---|
| Märchen & Fabel | Märchen, Volksmärchen, Fabeln | weiblich | – |
| Liebe | Romanze, Romance, Liebesroman, Historische Romanze | weiblich | – |
| Bühne | Drama, Tragödie, Theaterstück, Komödie | weiblich | – |
| Krimi | Krimi, Kriminalroman, Kriminalliteratur, Kriminalgeschichte, Thriller, Spionageroman, True Crime | männlich | – |
| Abenteuer | Abenteuerroman, Abenteuer, Western | männlich | – |
| Science-Fiction | Science-Fiction, Science-Fantasy | männlich | – |
| Horror | Horror, Horrorgeschichte, Schauerliteratur, Geistergeschichte | männlich | – |
| Roman allgemein | Roman, Belletristik, Klassiker, Literatur | männlich | weibliche Hauptfigur → weiblich |
| Historisch | Historischer Roman, Historischer Bericht | männlich | weibliche Hauptfigur → weiblich |
| Fantastik | Fantasy, Fantasyliteratur, Phantastik, Phantastische Literatur | männlich | weibliche Hauptfigur → weiblich |
| Mythos & Epos | Epos, Epische Sage, Sage, Legenden, Mythologie | männlich | weibliche Hauptfigur → weiblich |
| Kinder & Jugend | Jugendliteratur, Kinderbuch, Bilderbuch, Tiergeschichte | weiblich | männliche Hauptfigur → männlich |
| Kurzprosa | Kurzgeschichte(n), Erzählung | Geschlecht des Autors | – |
| Sachtext | Philosophie, Sachbuch, Memoiren, Autobiografie, Reisebericht, Reiseliteratur | Geschlecht des Autors | – |
| Lyrik | Dichtung, Poesie | Geschlecht des Autors | – |
| Sonstiges | Satire, Literarische Einleitung, unklar | Geschlecht des Autors | – |

Unbekannter Genre-Wert oder fehlende Angabe → Gruppe „Sonstiges“ (Geschlecht des Autors); Autor unbekannt → weiblich.

## 3. Datenfelder

- `work/600_klappentext.json → meta.hauptfigur_geschlecht` (weiblich | maennlich | unklar) — Stage 600 seit 19.10.2026, Bestand per `tools\nachlauf_geschlecht.py`.
- `author.json → autor_geschlecht` (Wikidata P21) — Stage 110 seit 19.10.2026, Bestand per `tools\nachlauf_geschlecht.py`.

## 4. Testsequenzen (vor Abnahme)

`start_teaser_test.bat` → je Werk `fassungen\<lg>\teaser\teaser_<lg>_<variante>.wav`

| Werk | Sprache | Variante | Aufbau |
|---|---|---|---|
| The Yellow Wallpaper (Roman allgemein, weibliche Hauptfigur → weiblich) | DE | w | mix_v1 + grossmutter_a |
| | EN | w | Standard + VC grossmutter_a |
| Call of the Wild (Abenteuer → männlich) | DE | m_klon | mix_v1 + Referenz herr_a |
| | DE | m_vc | mix_v1 + grossmutter_a, dann VC herr_a |
| | EN | m | Standard + VC herr_a |

Reihenfolge im Teaser: Köder → Einordnung → Autor; Pause 350 ms zwischen Sätzen, 800 ms zwischen Blöcken; Tempo wie Werk (mix_v1 0,76, Standard 0,91).

## 5. Nach Abnahme

1. Stage 550 Teaser in der Audio-Linie (Zuordnung automatisch nach Abschnitt 2, Modal).
2. 710 Cloud-Export: Teaser-MP3 je Sprache + Eintrag im Manifest/Katalog.
3. TÆLLA-Mock-up: Single Click auf ein Werk im Katalog spielt den Teaser, bis der Nutzer weiterklickt.
