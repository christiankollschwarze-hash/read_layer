# NAECHSTES WERK — The Flag (Homer Greene) [Anlege-Merkzettel]

> Vorgemerkt 18.06.2026. Steht auf der Shortlist. Quelle: Project Gutenberg.
> ZUERST die zwei PRUEF-Punkte klaeren, DANN anlegen.

## ZUERST PRUEFEN (vor jeder Produktion)
1. **PD-Status / Todesjahr Homer Greene** -- PFLICHT (Regel: death_year + 70 < 2026).
   - Homer Greene vermutlich 1853-1940 -> +1940 -> EU-frei seit 2011. ABER:
     vor Produktion VERIFIZIEREN (obskurer Autor, nicht aus dem Kopf garantierbar).
   - Englisches Original -> kein Uebersetzer-Copyright erwartet.
2. **Gutenberg-ID + Einzeltext** -- die ID aus dem Gutenberg-Eintrag holen, dann
   nach dem Ziehen ersten Blick in raw.txt: Einzeltext oder Sammelband?

## INHALT / KURATION (Vorab-Hinweis)
- "The Flag" (vermutl. 1917) = patriotischer Erste-Weltkriegs-Jugendroman.
  -> faellt evtl. in Kategorie "historischer Kontext / Inhaltshinweis"
     (Kriegsbegeisterung der Zeit). Kein Ausschluss, aber beim Klappentext +
     Grundnote beachten.

## STIMME (offen, nach Klang waehlen)
- BEFUND aus Yellow Wallpaper: Aoede = doppler-arm; Despina/Charon doppler-anfaelliger
  bei Kurzsaetzen (aber per audio_cut reparierbar).
- LEHRE (Yellow Wallpaper): bei psychologisch dichten Stoffen traegt die NUECHTERNE
  Stimme den Schrecken oft besser als die emotionale. Bei "The Flag" (Abenteuer/
  Patriotik) darf es ggf. lebhafter sein -> Stimme/Regler am Stoff ausrichten.
- Vor Vollwerk: kurzer Probe-/Doppler-Test der Kandidatenstimme.

## ABLAUF (lokal, bewaehrt)
1. `python tools\00_anlegen.py --gutenberg <id>` -> raw.txt pruefen (Einzeltext?).
2. `python -m pipeline.stage_01_wikidata --author <slug> --propose` -> `--confirm <Q-ID>`.
3. book.json: publisher=SOMNIO, audio_voice=<Stimme>, audio_regler={...},
   audio_pron_skip=[].
4. Textkette OHNE TTS: `python run.py <slug> --line audio --to 56 --live`.
5. EPUB+Cover: `python run.py <slug> --line epub --to 31 --live` (zieht stage06).
6. Vertonung pro Sprache: `python run.py <slug> --line audio --from 58 --lang de --live`
   (neuer run.py ist per-lang -> EN ueberspringt DE nicht mehr).
7. QS: `python -m pipeline.stage_58b_stt_validate <slug> --lang de`
   dann `python tools\audio_cut.py <slug> --lang de --chain` (Doppler schneiden).
   Langer "zu wenig"-Satz -> gezielt neu vertonen (WAV loeschen, stage_58 resume).
8. Gesamt-WAV zum Probehoeren: `python join_audio.py <slug> --lang de`.
   (Stage 59 ist VERALTET -> join_audio.py nutzen, siehe TODO.)

## STATUS
- Noch nicht angelegt. Wartet auf PD-Verifikation + Gutenberg-ID.
