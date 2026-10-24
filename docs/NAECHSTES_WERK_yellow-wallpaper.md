# NAECHSTES WERK — The Yellow Wallpaper (Anlege-Merkzettel)

> Vorbereitet 15.06.2026, waehrend Sleepy Hollow (Werk 1) fertig vertont.
> ERST Werk 1 abschliessen (voller STT-Check + --fix), DANN dieses anlegen.

## Eckdaten
- **Titel:** The Yellow Wallpaper
- **Autorin:** Charlotte Perkins Gilman (1860-1935)
- **Erscheinungsjahr:** 1892
- **Vorgeschlagener book_slug:** `the-yellow-wallpaper`
- **Vorgeschlagener author_slug:** `gilman-cp` (Muster wie irving-w / stevenson-rl)
- **Gutenberg eBook #1952** -- LOKAL VERIFIZIEREN beim ersten `raw.txt`-Blick:
  ist es der EINZELTEXT (nicht eine Sammelausgabe)? Bei #1952 vermutlich Einzeltext,
  aber kurz gegenpruefen (sonst Front-Matter-/Mehrtext-Problem).

## PD-Status: GLASKLAR
- Gilman +1935 -> EU-frei seit 2006 (1935+70=2005). Risikolos.
- Englisches Original -> KEIN Uebersetzer-Copyright. Kein quell_uebersetzer noetig.

## Struktur: Einzelerzaehlung OHNE Kapitel (wie Sleepy Hollow)
- Tagebuch-/Ich-Erzaehlform, fortlaufend, keine Kapitelmarken.
- Der heute gebaute Front-Matter-Stripper (stage_30 / stage_11) greift -> Titelblock
  am Anfang wird nicht mitvertont. Kapitel-Heuristik hier irrelevant.
- NICHT der Test fuer den mehrteiligen Kapitel-Pfad (das braucht spaeter einen
  echten Roman mit Kapiteln).

## STIMME: Aoede (CK-Wahl)
- Weibliche Gemini-Stimme, passt zur weiblichen Ich-Erzaehlerin.
- Voraussetzung: Speaker-Definer (stage_58 NEU4) muss eingespielt sein
  (book.json -> "audio_voice", Fallback config.TTS_VOICE, CLI --voice).
- In book.json eintragen: `"audio_voice": "Aoede"`.
- Weil der Text KURZ ist (~6.000 Woerter): Aoede kann am GANZEN Werk getestet
  werden, ohne Kontingent/Zeit-Schmerz -> idealer voller Stimm-Test an echtem Stoff.

## REGLER (Startwerte, dann per Gatekeeper feinhoeren)
- Vorschlag analog Sleepy Hollow: `"audio_regler": {"betonung": 2, "emotion": 4, "tempo": 6}`.
- VOR dem Vollwerk: `tts_probe the-yellow-wallpaper --betonung .. --emotion .. --tempo ..`
  (Gatekeeper) -> Aoede + Regler an 3 Saetzen hoeren, nachziehen, dann freigeben.

## INHALTSHINWEIS (Pflicht laut BOARD-Logik)
- Stoff: psychischer Zusammenbruch / postpartale Depression, Isolation, "rest cure",
  unzuverlaessige Erzaehlerin. -> gestufte Grundnote setzen
  ("Werk aus [1892], spiegelt Haltungen/Sprache seiner Zeit ...") + ggf. spezifischer
  Hinweis (psychische Krise), MENSCH-geprueft, nicht KI-Massendurchlauf.
- Gehoert ins Schaufenster, nicht in die Vertonung.

## ANLEGE-KETTE (lokal, nach Werk-1-Abschluss)
1. `anlegen.py` (Gutenberg #1952 lokal ziehen) -> raw.txt pruefen (Einzeltext?).
2. `stage_01_wikidata --author gilman-cp --propose` -> Q-ID bestaetigen (--confirm).
   (NIE Q-ID raten -- immer erst --propose; vgl. Jekyll-Vorfall.)
3. book.json: publisher=SOMNIO, `audio_voice: "Aoede"`, `audio_regler: {2,4,6}`,
   `audio_pron_skip: []`.
4. stage_11_modernize -> raw_modernized.txt (Front-Matter-Stripper greift).
5. stage_31_translate (de) bzw. Audio-Textkette (50-55).
6. stage_56_direction -> Regie (Regler + Befehlsform-Aussprache).
7. tts_probe (Gatekeeper, Aoede + Regler) -> hoeren -> freigeben.
8. stage_58 (--lang de, dann en) -> stage_58b (STT, --fix).

## NICHT VERGESSEN
- Speaker-Definer (NEU4) lokal einspielen, BEVOR dieses Werk vertont wird.
- Gutenberg-ID #1952 lokal gegen raw.txt verifizieren.
