# NAECHSTES WERK — The Flag (Homer Greene) [Anlege-Merkzettel v3]

> Vorgemerkt 18.06.2026. Auf der Shortlist. Quelle: Project Gutenberg.
> Ersetzt v2. NEU: LMU-Einstufung + Beleg-Checks fuers Marketing-Argument.

## STRATEGISCHER WINKEL (CK, 18.06.) -- STARK
- **Thema Immigration / amerik. Identitaet -> hochaktuell.** Gemeinfreier Stoff
  mit Gegenwartsrelevanz = Aufmerksamkeits-Anker (vgl. BOARD: Odyssee/Nolan-Logik,
  hier thematisch statt an Termin gebunden).
- **AKADEMISCH GEADELT:** LMU Muenchen stuft The Flag als wertvolle amerikanische
  Literatur ein -> externes Qualitaetssiegel, kein Eigenlob. Entkraeftet "PD =
  zweitklassig". Passt zur kultivierten Positionierung.
- **Marktluecke doppelt belegt:** akademisch wertvoll UND auf Deutsch nicht
  verfuegbar (Amazon/Audible: nichts auf DE). -> kein Wettbewerb, sondern
  ERSCHAFFUNG der deutschen (Hoer-)Fassung. Kernthese in Reinform: Differenzierung
  durch Veredelung/Zugaenglichmachung, nicht durch Masse.
- **Eigene DE-Uebersetzung aus gemeinfreiem EN-Original (DeepSeek)** -> umgeht
  Uebersetzer-Copyright, Fassung gehoert dir.

## BELEG-CHECKS (vor dem Verkaufsversprechen -- schuetzt vor angreifbarem Claim)
1. **"Gibt's nicht auf Deutsch" absichern:** Amazon/Audible ist Indikator, nicht
   Vollbeweis. Zusaetzlich pruefen: DNB (Deutsche Nationalbibliothek),
   Projekt Gutenberg-DE, antiquarisch. Wenn wirklich nichts -> echtes Pfund.
2. **LMU-Einstufung belegbar halten:** WO gesehen? (Leseliste / Seminar /
   Bibliographie). Quelle festhalten, sonst Hoerensagen-Argument.

## WAECHTER (Recht + Kuration)
3. **PD / Todesjahr Homer Greene** -- PFLICHT (death_year + 70 < 2026).
   ~1853-1940 -> EU-frei seit 2011 erwartet, ABER verifizieren (obskurer Autor).
4. **Aktualitaet = Chance UND Sensibilitaet.** WK1-Einwanderungsroman ~1917 traegt
   Haltungen seiner Zeit (patriotisch-assimilatorisch). "Hochaktuell" nur MIT
   ehrlichem historischem Rahmen (gestufte Grundnote) -- NICHT eine 1917er-Sicht
   unkommentiert als 2026-Kommentar verkaufen. Bewusst setzen, nicht nachschieben.
5. **Gutenberg-ID + Einzeltext** -- ID holen, raw.txt pruefen.

## STIMME (nach Klang, am Stoff ausgerichtet)
- Befund Yellow Wallpaper: Aoede doppler-arm; Despina/Charon kurzsatzanfaellig
  (per audio_cut reparierbar). Bei Abenteuer/Patriotik darf es lebhafter sein
  als bei der nuechtern-verstoerenden Gelben Tapete. Vor Vollwerk Doppler-Test.

## ABLAUF (lokal, bewaehrt -- Stand 18.06.)
1. `python tools\00_anlegen.py --gutenberg <id>` -> raw.txt pruefen.
2. `stage_01_wikidata --author <slug> --propose` -> `--confirm <Q-ID>`.
3. book.json: publisher=SOMNIO, audio_voice=<Stimme>, audio_regler={...}.
4. Textkette: `python run.py <slug> --line audio --to 56 --live`.
5. EPUB+Cover: `python run.py <slug> --line epub --to 31 --live`.
6. Vertonung: `python run.py <slug> --line audio --from 58 --lang de --live`
   (run.py per-lang -> EN ueberspringt DE nicht mehr).
7. QS: `stage_58b_stt_validate <slug> --lang de` dann
   `tools\audio_cut.py <slug> --lang de --chain`. Langer "zu wenig"-Satz -> neu vertonen.
8. Probehoeren: `python join_audio.py <slug> --lang de` (Stage 59 veraltet).

## STATUS
- Noch nicht angelegt. Wartet auf: PD-Verifikation + DNB/Gutenberg-DE-Check
  + LMU-Quelle festhalten + Gutenberg-ID.
