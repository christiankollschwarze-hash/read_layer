# NAECHSTES WERK — The Flag (Homer Greene) [Anlege-Merkzettel v2]

> Vorgemerkt 18.06.2026. Auf der Shortlist. Quelle: Project Gutenberg.
> Ersetzt v1. NEU: strategischer Winkel (Immigration / Luecke).

## STRATEGISCHER WINKEL (CK, 18.06.)
- **Thema Immigration / amerik. Identitaet -> hochaktuell.** Gemeinfreier Stoff,
  der durch die Gegenwart neue Relevanz bekommt = Aufmerksamkeits-Anker
  (vgl. BOARD: Odyssee/Nolan-Logik, nur thematisch statt an Termin gebunden).
- **Luecke = Kernthese in Reinform:** Buch kaum auf DEUTSCH zu finden, als AUDIO
  gar nicht. -> kein Wettbewerb mit existierender Ausgabe, sondern ERSCHAFFUNG
  der deutschen Hoerfassung. Differenzierung durch Veredelung, nicht durch Masse
  (CK-Prinzip: Volumen ist kein Moat, Qualitaet der Verarbeitung schon).
- **Eigene DE-Uebersetzung aus dem gemeinfreien EN-Original (DeepSeek)** -> umgeht
  jedes Uebersetzer-Copyright, Fassung gehoert dir. Genau die Waelzer-/Nacherzaehl-
  Logik.

## WAECHTER (vor Produktion ernst nehmen)
1. **PD / Todesjahr Homer Greene** -- PFLICHT (death_year + 70 < 2026).
   ~1853-1940 -> EU-frei seit 2011 erwartet, ABER verifizieren (obskurer Autor).
2. **"Kaum auf Deutsch" = Vermutung, nicht Fakt.** Vor dem Verkaufswinkel kurz
   gegenchecken, dass es WIRKLICH keine etablierte dt. Uebersetzung gibt
   (sonst Uebersetzer-Copyright + Luecke-Argument schwaecher). Eigene Uebersetzung
   ist davon unberuehrt, aber das Marketing-Argument haengt dran.
3. **Aktualitaet = Chance UND Sensibilitaet.** WK1-Einwanderungsroman von ~1917
   traegt Haltungen seiner Zeit (patriotisch-assimilatorisch, evtl. heute anders
   gelesen). Wenn "hochaktuell" als Winkel -> historischen Kontext EHRLICH
   mitliefern (gestufte Grundnote). Stoff funktioniert MIT Rahmen, nicht ohne.
   NICHT eine 1917er-Sicht unkommentiert als 2026-Kommentar verkaufen.
4. **Gutenberg-ID + Einzeltext** -- ID holen, raw.txt pruefen (Einzeltext?).

## STIMME (nach Klang, am Stoff ausgerichtet)
- Befund Yellow Wallpaper: Aoede doppler-arm; Despina/Charon kurzsatzanfaellig
  (per audio_cut reparierbar). Bei Abenteuer/Patriotik darf es lebhafter sein
  als bei der nuechtern-verstoerenden Gelben Tapete.
- Vor Vollwerk kurzer Doppler-Test der Kandidatenstimme.

## ABLAUF (lokal, bewaehrt -- Stand 18.06.)
1. `python tools\00_anlegen.py --gutenberg <id>` -> raw.txt pruefen.
2. `stage_01_wikidata --author <slug> --propose` -> `--confirm <Q-ID>`.
3. book.json: publisher=SOMNIO, audio_voice=<Stimme>, audio_regler={...}.
4. Textkette: `python run.py <slug> --line audio --to 56 --live`.
5. EPUB+Cover: `python run.py <slug> --line epub --to 31 --live`.
6. Vertonung: `python run.py <slug> --line audio --from 58 --lang de --live`
   (run.py ist jetzt per-lang -> EN ueberspringt DE nicht mehr).
7. QS: `stage_58b_stt_validate <slug> --lang de` dann
   `tools\audio_cut.py <slug> --lang de --chain`. Langer "zu wenig"-Satz -> gezielt
   neu vertonen.
8. Probehoeren: `python join_audio.py <slug> --lang de` (Stage 59 veraltet).

## STATUS
- Noch nicht angelegt. Wartet auf PD-Verifikation + "keine dt. Fassung"-Check
  + Gutenberg-ID.
