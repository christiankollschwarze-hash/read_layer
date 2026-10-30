# PROJEKTSTAND — Read Layer

## OFFENE PUNKTE – priorisiert (Stand 16.10.2026 15:00; ersetzt die verstreuten "Offen"-Listen weiter unten)
Regel: hoechstens 1 Arbeitspaket + 1 Hintergrundjob gleichzeitig. Neues landet hier, nicht sofort in Arbeit.

LAEUFT
- Baskerville DE: Neuvertonung betroffener Saetze mit Aussprache-Lexikon (start_neu_vertonen.bat) -> danach Sprachpruefung, CK hoert.

A – direkt am Produkt
1. App: Umschalter Hoerspiel/Erzaehler + Export (export_demo.py --hoerspiel); Mock-up laedt Ruf der Wildnis noch aus public/ statt public/demo/ -> bereinigen.
2. Hoerspiel-Pruefung Alice, Baskerville (nach Neuvertonung), Wie es euch gefaellt: Overlay + start_trennung_messen.bat + Cockpit-Tor (PROZESS_abstandsregel Punkt 7).
3. Kuratormodus Teil 2 (docs/AP_kuratormodus_teil2.md) – vorher AP abgleichen: satzweises Neu-Vertonen (tools/neu_vertonen.py) und Sprachpruefung gibt es inzwischen; Aussprache-Anmerkungen Baskerville/AYLI ggf. schon erledigt.
0. NEU 17.10.: AP Chatterbox-Neuvertonung satzweise (Projekt-Doc claude/AP_chatterbox_neuvertonung.md) - Peter Pan: 41 Nachklang-Saetze, Eigennamen-Lexikon DE, CK-Markierung, Tempo 0,91.
0b. NEU 22.10.: Eigenes Werk "Die Spiegelschwestern" (DE-Original): AP1-AP4 ERLEDIGT (22.10. 21:08, im Mock-up). Offen: Teaser in App (Stage 550, allgemein), EN "Kammer", Mikrofonklang Schulleiterin.
0c. NEU 23.10.: Test Prosodie-Vokabelheft v0.1 (docs/prosodie/) - start_prosodie_test.bat: 30 Testsaetze A ohne/B mit Markup (Chatterbox Modal, DE mix_v1), Parser tools/prosodie_markup.py, Hoertest gpu_tts/prosodie_test_v01/hoertest.html (V/S/B/P/A, CSV). CK 23.10.: Ergebnis traegt nicht (Pausen-Chunks verlieren Kontext) -> verworfen.
0d. NEU 23.10.: Test 'Stimmung einfangen, Klang tauschen': fremder Profi-Clip (nicht LibriVox) als Chatterbox-Referenz -> Chatterbox VC auf Margaret. start_stimmung_vc_test.bat, Clips nach gpu_tts/stimmung_vc_test/muster/<stimmung>_x.(wav|mp3|...). Quelle Emo-DB (TU Berlin, Schauspieler; Download im Modal-Job nach Volume /emodb, Sprecher 08+03, Stimmungen wuetend/traurig/aengstlich/froehlich). Lizenz vor produktiver Nutzung pruefen. CK 23.10. 10:54: TRAEGT - 'das ist der Weg' (Stimmung aus Schauspieler-Clip ueberlebt VC auf Margaret). Naechstes AP: Stimmungs-Bibliothek (Emo-DB je Stimmung/Sprecher) + Pipeline-Einbau (Stimmungsklasse je Satz -> Clip als Referenz -> Chatterbox -> VC auf Werkstimme); Emo-DB-Lizenz klaeren. Gegenprobe Gemini (Variante R 17.10. trug nicht, Regie zu zurueckhaltend): tools/emoji_referenzen_gemini.py (14 Emojis, Schauspieler-Regie, Margaret) -> start_emoji_gemini.bat. Offen: CK hoert Gemini vs. Emo-DB. Benchmark ElevenLabs Eleven v4 (fal, elevenlabs/tts/eleven-v4, 0,08 $/1k Zeichen, Audio-Tags): start_elevenlabs_vergleich.bat -> ergebnis/*_4_elevenlabs.mp3.  ElevenLabs-Prosodie als Vorlage (CK: Prosodie top, Klonen schwach -> Klang per Chatterbox VC): start_eleven_vorlage.bat; Gemini-Vorlagen nach muster/_erledigt.
0f. ERGEBNIS CK-Hoertest 23.10. 12:18 (X-Favoriten auf 3_umgewandelt, je Stimmung+Sprache): Gemini 15/28, ElevenLabs 8/28 (erschrocken, fluesternd, Teile freundlich/liebevoll/nachdenklich/verschmitzt), Emo-DB 5/28 (traurig DE+EN, wuetend EN, aengstlich DE, froehlich EN). Gemini traegt jetzt (anders als Variante R 17.10.) dank Schauspieler-Regie. EMOJI-BIBLIOTHEK v1: stimmen_archiv/_emoji/<stimmung>_<lg>.wav + emoji_bibliothek.json (28 Vorlagen; 😐 = Werkstimme selbst). Emo-DB-Lizenz betrifft nur noch 5 Vorlagen (ersetzbar). Offen: Betonungstest (start_betonung_test.bat), dann AP Pipeline-Einbau. FLUESTERN: Chatterbox uebernimmt echtes Fluestern nicht -> Audiotrick tools/fluestern.py (WORLD-Vocoder, Anregung -> Rauschen, Formanten bleiben; --hauch/--hochpass/--pegel/--klar). v1 (CK: zu tief, Roboter) -> v2: f0=0 (reines Rauschen), Formanten +8 %, Hochpass 500 Hz, Hoehen +4 dB. CK 12:27 FESTGELEGT: Standard = formant 1.08, Hochpass 700 Hz, Hoehen +7 dB, Pegel -10 dB (ergebnis/flüsternd/<lg>/7_final_fluestern.wav). Pipeline: bei 🤫 als letzter Schritt nach VC. Trick gehoert ans ENDE der Kette (VC macht Fluestern wieder stimmhaft).
0g. ERGEBNIS Betonung/Pausen CK 23.10. 13:08 (ergebnis_betonung, X): Betonung - a_ohne 3/6, e_split_pause 2/6 (nur Kontrast er/he), b_pause 1/6, c_strich + d_split 0 -> Chatterbox betont kaum; Regel: *Wort* sparsam, nur Kontrastbetonung kurzer Woerter, Umsetzung e_split_pause. Pausen - p_split 4/6 (inkl. p_split_betont), a_ohne 2/6 bei sehr kurzen Saetzen (Wait./Quiet now.) -> Regel: Split an | nur wenn beide Chunks >= ~4 Woerter, sonst Satz am Stueck. CK: '...'/'—' und Splits erzeugen oft Stoergeraeusche + falschen Schnitt am Satzende -> im Einbau Chunk-Enden per Forced Alignment kappen (cb_pruefung/MMS_FA wie Standardlauf, letztes Wortende + Ausblenden) statt Pegel-Schwelle; Chunk mit Nachklang neu erzeugen. Best-Practice-Lauf mit anderer Stimme: start_best_practice.bat [herr_a] -> ergebnis_<stimme>/<Stimmung>/<lg>/1_neutral + 2_best_practice. Pausenregel praezisiert: Split ausser ein Nachbar ist kurzer ganzer Satz (<4 Woerter, .!?); *Wort* nur <=3 Buchstaben.
0h. IDEE CK 23.10. 13:43 Ramona-Dominanz im DE-LoRA (mix_v1 = 3 LibriVox-Erzaehler) aufloesen: Fund 'chatterbox-nano-de-lora' (Pseudonaut, MIT) - Adapter selbst NICHT nutzbar (Nano = 110M, EN-only, anderes Modell als unser Multilingual). Nutzbar: Datensatz MrDragonFox/DE_Emilia_Yodas_680h (CC BY 4.0, kommerziell mit Namensnennung, viele Sprecher, Spontansprache). Vorschlag: mix_v2 = Emilia-DE-Auswahl (20-40 h, Qualitaetsfilter) + Julia/Bernd, ohne Ramona; Training wie bisher (Bedingung = anderer Satz desselben Sprechers - ist bei uns schon so). Vergleich mix_v1 / mix_v2 / ohne LoRA an Emoji-Saetzen.
0e. ZIELBILD CK 23.10. 11:42 "Emoji-Weg": Prosodie von Premium-TTS (Gemini 3.8 Flash / ElevenLabs v4) NUR fuer die Emoji-Vorlagen (einmalig, Cent-Betraege, stimmenunabhaengig, weil VC den Klang ersetzt), Klang/Cloning + ganzes Werk mit Chatterbox auf Modal (~1 $/Audio-h + VC-Anteil). Ablauf je Satz: Stimmungsklasse (DeepSeek, 14 Emojis statt 5 Klassen in prosodie_marken.py) -> Emoji-Vorlage als Referenz -> Chatterbox -> VC auf Werkstimme. CK 11:45: DeepSeek-Regie liefert ausser Emoji auch Pausen (| || |||) und Wortbetonung (*Wort*), geschlossenes Markup, sparsam (Learning Juni: keine freie Regie). KORREKTUR CK 11:48: Pausen = Chunk-Split JA, aber jeder Chunk nach | bekommt die Emoji-Vorlage erneut als Referenz (Kontext/Stimmung bleibt). Betonung ist nicht nur Lautstaerke (auch Tonhoehe, Dauer, Timing) -> keine Nachbearbeitung per Pegel. CK 11:50: Betonung ZUERST mit Chatterbox testen (start_betonung_test.bat: Varianten ohne/Denkpause/Gedankenstriche/Split-am-Wort mit Emoji-Ref je Chunk). Alternative spaeter: Saetze mit *Wort* von Premium-TTS (ElevenLabs/Gemini, Betonung im Text) sprechen lassen -> Chatterbox VC auf Werkstimme (nur markierte Saetze, sparsam = billig). Offen: Hoerurteil Gemini vs. ElevenLabs vs. Emo-DB als Vorlage; dann AP Pipeline-Einbau.
4. Hoertest fuer Dritte teilen (Artifact "TÆLLA Hörtest Stimmen", Teilnehmer als Mitwirkende) + auswerten (tools/blindtest_auswerten.py).

B – Pipeline/Prozess
4b. NEU 26.10.: AP 54a Vergleichslauf lokaler Aligner (SimAlign mBERT m/a/i, awesome-align mBERT + awesome-align-with-co) gegen s340 (DeepSeek-Wortanker), Werk Call of the Wild.
    GELAUFEN 26.10. (Hugging Face in Claude-Sandboxen gesperrt -> Lauf ueber Modal): start_aligner_vergleich.bat [werk]
    -> gpu_align/align_vergleich_modal.py (3x T4 ganzes Werk + 3x CPU 4 Kerne/100 Saetze fuer NUC-Hochrechnung, geschaetzt < 0,20 $)
    -> tools/aligner_vergleich_auswerten.py -> work/_aligner_vergleich/tabelle.md, auswertung.json, laufzeit.json, stichprobe_<aligner>.txt.
    Metriken: Abdeckung (54a-Metrik = Anteil EN-Woerter nicht 'unresolved'; 340 aktuell 98,13 %, Validierung 17.07.: 97,0 %; Wert 96,98 % nicht im Projektstand gefunden),
    Deckung mit 54a-Ankern, Null-Einigkeit. Achtung: Abdeckung allein misst keine Richtigkeit (Aligner setzt fast immer einen Anker) -> Entscheidung ueber Deckung + Stichprobe.
    Ausgabeformat (Grundlage Tokenisierungsbruecke 54a<->MMS_FA): je Satz {"id","w":[[i,[[de_start,de_end],...]],...]}; i = EN-Index wie s340.tokenize_en (\S+),
    Spans = Zeichenpositionen im DE-Satz, Satzzeichen-Links verworfen, mehrere DE-Spans je EN-Wort moeglich. Auswertung mit Testdaten geprueft (26.10.).
    ERGEBNIS 26.10. 12:38 (Modal, work/_aligner_vergleich/tabelle.md): Abdeckung / Deckung mit 54a / Null-Einigkeit / T4 s / $ je Buch / CPU-4-Kerne s
      54a DeepSeek 98,13 / 100 / 100 / - / ~0,08 / -
      awesome_co 89,98 / 87,68 / 43,7 / 39 / 0,006 / 427 ; awesome_mbert 87,71 / 85,03 / 42,2 / 33 / 0,005 / 366
      simalign i 93,55 / 87,67 / 25,8 / 288 / 0,047 / 353 ; simalign m 98,42 / 88,03 / 6,2 ; simalign a 83,41 / 81,65 / 50,3
    Stichprobe (Unteragent, 40 Saetze je Aligner, nur Abweichungen): awesome_co R40/A30/B43/F4, simalign_i R44/A45/B44/F4.
      Aligner: fehlende Anker (Funktionswoerter, Mehrwort, Partikelverben), Nachbar-Verwechslung. 54a: Verschiebungsketten um 1 Wort
      (fast alle A-Faelle, z. B. c004_00118_s, c007_00105_s), Mehrwort-Anker zu breit.
    ENTSCHEIDUNG (Empfehlung Claude): 54a NICHT ersetzen. awesome-align-with-co (awesome_co) als PRUEFALIGNER neben 54a einbauen:
      Verschiebungsketten erkennen (Folge von >= 3 EN-Woertern, bei denen awesome_co den Nachbaranker von 54a trifft) -> Satz neu an DeepSeek.
      Kosten ~0,006 $/Buch (T4), CPU/NUC ~7 min/Buch moeglich. Ausgabeformat siehe oben (gilt fuer awesome_co).
    Naechstes AP: Tokenisierungsbruecke 54a <-> MMS_FA (+ Verschiebungsdetektor mit awesome_co).
4c. AP 54b 26.10.: Tokenisierungsbruecke + Verschiebungsdetektor - FERTIG inkl. DeepSeek-Nachlauf und Manifest-Export (26.10. 13:04).
    Sicherung: archive/2026-10-26_54b/ (s340/s520/s710, fa_modal, fertig_modal, export_*, PROJEKTSTAND, CotW-work 340/520/710/kosten).
    NEU pipeline/s525_wortbruecke.py (EINE Stelle fuer Lautwoerter + Token-Bindung; s520 importiert sie, fa_modal/fertig_modal laden sie mit):
      Zeichenposition = Bruecke; ’->' ; Token ohne Zeit zwischen Nachbarn interpoliert; fehlende de_span neu verortet
      (gap_fallback nur <=2 Woerter ohne Satzende, unresolved/mehrteilig "x ... y" -> mehrere Spans); Teil-Token (Kompositum) = Zeitanteil nach Buchstaben.
      Ausgabe work/525_wortbruecke.json {i, t, tq, zspans, tz, sq}; s710 haengt t/tz (+ reparierten de_span, zspans) an jeden Anker im EN-Manifest.
    NEU pipeline/s345_verschiebung.py + gpu_align/pruefaligner_modal.py: awesome_co trifft Nachbaranker von 340 bei >=3 EN-Woertern gleicher Richtung
      -> nur diese Saetze an DeepSeek (340-Prompt + Hinweis); uebernommen nur bei weniger Kettentreffern und <=10 % Ankerverlust; Sicherung work/340_wortalignment_vor345.json.
    Start: start_verschiebung.bat [werk] (Modal nur, wenn work/345_pruefaligner.json fehlt; CotW: aus 54a uebernommen) -> 345 --nachlauf -> 525 -> tools/regression_54b.py -> Kostenlog.
    Tokenisierung CotW (31.754 EN-Token): 1:1 31.219; mehrere Lautwoerter 534 (272 ’-Apostroph, 260 Bindestrich, 41 Gedankenstrich); 0 Lautwoerter 1 (1897).
      DE (31.067): mehrere Lautwoerter 76, 0 Lautwoerter 49 (–, 1897). Anker ohne de_span 1.042 (gap 449, unresolved 593), Mehrtoken-Spans 418, Teil-Token 44.
    MESSUNG CotW (Anteil EN-Woerter):  vorher / nachher Bruecke
      Anker (DE-Span) 87,81 / 88,68 ; Wortzeit EN 99,74 / 99,75 ; Wortzeit DE 87,80 / 88,68 ; Anker+EN+DE 87,58 / 88,46
      Rest: 8,9 % "none" (korrekt ohne Entsprechung), 573 unresolved = geratene Woerter (bleiben ohne Anker), 8 Saetze ohne EN-Audio.
    Regression Manifest EN: 0 fremde Abweichungen, 278 reparierte de_span, 31.676 Anker mit t, 28.159 mit tz.
    Detektor CotW: 72/1637 Saetze markiert, 389 Woerter; Stichprobe 20 (Unteragent): 16 echt, 4 teilweise, 0 Fehlalarm (work/345_stichprobe.txt).
      Trockenlauf Nachlauf (Pruefaligner als Ersatzantwort): Annahmelogik ok (66/72 uebernommen). Kosten: Pruefaligner 0 $ (aus 54a), DeepSeek geschaetzt < 0,01 $.
    NACHLAUF 26.10. 13:00 (start_verschiebung.bat): 71/72 Saetze uebernommen; danach 2 Saetze / 6 Woerter markiert (vorher 72/389).
      MESSUNG nach Nachlauf (vorher 340 neu / nach Bruecke): Anker 88,39 / 89,22 ; Wortzeit EN 99,74 / 99,75 ; Wortzeit DE 88,38 / 89,22 ; Anker+EN+DE 88,16 / 89,00
      Gesamt AP 54b: Anker+EN+DE 87,58 -> 89,00 %. Regression: 0 fremde Abweichungen, 265 reparierte Spans, 31.676 Anker mit t, 28.330 mit tz -> OK.
      Kosten DeepSeek 345: 8 Aufrufe, 0,0145 $ (Pruefaligner 0 $).
    ERLEDIGT 26.10. 13:04: s710 call-of-the-wild --lang en --manifest-only -> manifest_en.json (1906 Knoten, 1629 mit Audio, t/tz je Anker) in gs://readlayer-taella-content/werke/london-j_call-of-the-wild/.
    Naechster Schritt: Frontend liest t/tz/zspans fuer Wort-Hervorhebung EN+DE; start_verschiebung.bat fuer weitere Werke.
4d. AP 54c 26.10.: Wort-Hervorhebung EN+DE (Wort + Gegenwort) im Mock-up - GEBAUT, Browser-Hoertest offen (Dev-Server lief nicht).
    Sicherung: archive/2026-10-26_54c/ (ListenView.jsx, useListen.js, App.css, Demo-Manifeste CotW, export_demo/export_app, start_verschiebung.bat, PROJEKTSTAND).
    Bestand: Loader taella-app/src/lib/loader.js liest align nur aus dem Manifest der Originalsprache; genutzt bisher en_span/de_span
      (Satz.jsx: Flyover-Phrase; ListenView: Untertitel-Karaoke per Span-Ueberlappung) + wordtimes_<lang>.json (export_app.py aus 520).
    Export: kein Code-Umbau noetig - export_demo.py nutzt s710._build_manifest (haengt t/tz/zspans an). DE-Manifest braucht nichts (Gegenrichtung aus EN-Ankern).
      CotW neu exportiert (export_demo --audio --hoerspiel): 31.754 Anker, 31.676 mit t, 28.330 mit tz.
    Frontend: NEU src/lib/wortpaar.js (Fenster je Anker; EN: t, DE: tz je zspan; n:1 zusammengefasst; Zeichenzustand -> Teil-Token-Markierung).
      ListenView: Untertitel-Schalter CC -> andere Sprache -> EN·DE (beide Zeilen) -> aus; gehoerte Zeile Token-Karaoke + Ankerfenster im Token,
      Gegenzeile Gegenwort hervorgehoben; ohne Anker kein Gegenwort; Hoerspiel-Clip -> bisheriger Weg (t/tz gelten nur fuer Erzaehler-Audio). App.css: .listen-subs, .listen-sub--gegen.
      Syntax geprueft (esbuild). Commit taella-app offen.
    Test ohne Browser: tools/test_wortpaar_54c.mjs (Kap. c001/c004/c007): EN 13.178 Woerter, 89,1 % mit Gegenwort; DE 11.764, 100 %;
      Abweichung Ankerzeit/520-Tokenzeit Median 0 ms, P95 0 ms (gleiche Quelle). Stichprobe 20 (Unteragent, work/_54c/stichprobe20.tsv):
      R 15 / T 3 / F 1 / LF 1 - Fehler liegen in den 54a-Ankern (would->haetten, destined ohne Anker), nicht in der Hervorhebung.
    BROWSER-TEST 26.10. 14:05 (Ruf der Wildnis, Erzaehler, EN·DE): synchron in beiden Richtungen (DE hast->ain't got, murren->coming; EN had->waren, skyward->in die Hoehe).
      Befund lange Saetze: zweite Zeile ragte in Zeitleiste -> Schriftgroesse aus Gesamtlaenge beider Zeilen (ListenView subLen) -> passt. Commit taella-app offen (git braucht Loeschrecht).
    OFFEN nach AP 54c (Stand 26.10. 14:05) -> abgearbeitet in AP 55 (Punkt 4e):
      a) Commit taella-app: src/lib/wortpaar.js (neu), src/components/ListenView.jsx, src/App.css, public/demo/* (Manifeste CotW, Alice, Sleepy Hollow, AYLI, Jekyll, Baskerville, katalog.json).
         Claude braucht dafuer Loeschrecht im Ordner taella-app (git-Sperrdateien) - sonst CK selbst committen.
      b) Teil-Token (Kompositum) im Browser noch nicht live gesehen (nur Simulation tools/test_wortpaar_54c.mjs).
      c) Hoerspiel-Modus: kein Wort+Gegenwort (t/tz gelten nur fuers Erzaehler-Audio). Braucht Wortbruecke auf 520_wortzeiten_<lang>_hoerspiel.json.
      d) Lesemodus (Reader) hebt beim Hoeren weder Satz noch Wort hervor (bestehendes Verhalten, FRONTEND.md).
      e) Die Spiegelschwestern (DE-Original): s345/s525 setzen Quelle EN voraus -> Richtung DE->EN nachruesten, dann start_verschiebung.bat.
      f) GCS: Manifeste der 6 Werke (s710 --manifest-only) ohne Audio-Pfade, weil dort kein Audio liegt -> Cloud-Upload Audio (Punkt 10) bevor App aus GCS liest.
      g) Ankerqualitaet 54a: Stichprobe 20 -> 1 falsch, 1 fehlend, 3 teilweise; nach Nachlauf noch markiert: Alice 14, Sleepy 3, AYLI 2, Jekyll 16, P&W 11, Baskerville 17 Saetze.
         Option: zweiter Nachlauf nur fuer diese Saetze (Kosten < 0,01 $/Werk).
      h) Weitere Werke mit 340 aber ohne Wortzeiten EN+DE (u. a. Carmilla, Great God Pan, Time Machine, Hamlet): erst Vertonung + 520, dann start_verschiebung.bat.
    Weitere Werke: start_verschiebung_alle.bat (start_verschiebung.bat jetzt mit NOPAUSE) fuer Alice, Sleepy Hollow, AYLI, Jekyll, Peter & Wendy, Baskerville
      (~191.500 Woerter, geschaetzt 0,13-0,20 $), danach s710 --manifest-only + export_demo --audio. Nicht dabei: Spiegelschwestern (DE-Original, s345 setzt EN voraus).
    GELAUFEN 26.10. 13:55 (start_verschiebung_alle.bat), Anker+EN+DE nach Bruecke / Nachlauf uebernommen / Regression:
      Alice 92,86 % / 26 von 34 / 0 fremde Abw. ; Sleepy Hollow 94,98 % / 34 von 37 / 0 ; AYLI 93,67 % / 29 von 30 / 0
      Jekyll 94,23 % / 48 von 60 / 0 ; Peter & Wendy 94,94 % / 37 von 47 / 0 ; Baskerville 92,55 % / 99 von 113 / 0
      Kosten: Modal je Werk 0,005-0,007 $, DeepSeek 345 ~0,01 $ je Werk -> gesamt ~0,09 $. Demo-Export ok (5 Werke; Peter & Wendy nicht im Demo).
      Hinweis: s710 --manifest-only fand fuer diese Werke keine Audio-Pfade in GCS (Manifeste in GCS ohne Audio, wie vorher).
4e. AP 55 26.10.: Offene Punkte aus AP 54c abgearbeitet (Stand 26.10. ~15:00).
    Sicherung: archive/2026-10-26_55/ (s345/s520/s525/s710, export_demo/export_app/regression_54b, wortpaar.js/ListenView/useListen/loader, Demo-Manifeste Spiegelschwestern, PROJEKTSTAND).
    a) ERLEDIGT: Commit taella-app d5ee987 (AP 54c) + 9c48947 (AP 55). Loeschrecht taella-app fuer git in dieser Sitzung erteilt.
    b) ERLEDIGT Browser (CotW c001_00048_dl, DE gehoert): Teil-Token live - "Verdreh" <-> "Twist", "s" <-> "it,", "wuergst" <-> "choke" (Markierung mitten im Wort).
    c) ERLEDIGT Hoerspiel-Modus: s525 liest zusaetzlich 520_wortzeiten_<lg>_hoerspiel.json -> je Anker ths (Quell-Clip) / tzhs (Ziel-Clip);
       s710 haengt ths/tzhs an; wortpaar.js/ListenView: laufender Clip Hoerspiel -> ths/tzhs statt t/tz. regression_54b erlaubt ths/tzhs.
       Spiegelschwestern: 164 Hoerspiel-Saetze, 906 Anker mit ths; Browser: synchron (Weiblich->Female, soweit->as far as, n:1 ok), keine Konsolenfehler.
       Einschraenkung: nur wo 520_..._hoerspiel existiert (tools/overlay_montage.py schreibt sie). CotW hat 63 Hoerspiel-Clips DE, aber keine Hoerspiel-Wortzeiten -> dort Fallback (bisherige Karaoke) bis overlay_montage neu laeuft.
    e) CODE ERLEDIGT: s525/s345/pruefaligner_modal setzen Richtung per config.werk_sprachen(werk) (vorher SOURCE_LANGUAGE vor dem ersten work_path gelesen -> DE-Werk lief als EN).
       s525 Spiegelschwestern (DE->EN) gelaufen: Anker+Quelle+Ziel 79,92 -> 85,96 % (7.940 Woerter); Regression 0 fremde Abweichungen; Demo neu exportiert.
       OFFEN: Pruefaligner (Modal) + 345-Nachlauf Spiegelschwestern -> start_ap55.bat (Windows; VM hat kein Modal/DeepSeek-Netz).
    g) VORBEREITET: zweiter Nachlauf = 345 --nachlauf erneut (erkennt nur noch markierte Saetze). Rest: CotW 2, Alice 14, Sleepy 3, AYLI 2, Jekyll 16, P&W 11, Baskerville 17 = 65 Saetze.
       Kosten geschaetzt aus Lauf 1 (~0,0002 $/Satz): ~0,015 $ + Spiegelschwestern (Modal ~0,002 $, DeepSeek ~0,005 $) -> gesamt < 0,03 $.
       s345 behaelt den Bericht von Lauf 1 als work/345_verschiebung_vorher.json. Start: start_ap55.bat (e + g + Demo-Export), Bilanz: tools/ap55_bilanz.py.
    BEWERTET, nicht gebaut:
    d) Reader-Hervorhebung beim Hoeren: rein Frontend, wortpaar.js liefert Zeichenzustand schon -> Hoerzustand (idx/time) an Reader/Satz.jsx geben. 1 AP, nach Bestaetigung b/c im Alltag. Prioritaet mittel.
    f) GCS-Audio: Voraussetzung fuer App aus GCS (Punkt 10, Android). Gehoert in das AP Cloud-Audio; vorher nicht noetig (Mock-up laeuft lokal). Prioritaet mit Punkt 10.
    h) Weitere Werke (Carmilla, Great God Pan, Time Machine, Hamlet): erst Vertonung + 520 (Modal ~1 $/Audio-h), dann start_verschiebung.bat (~0,02 $/Werk). Nur wenn Werk ins Demo/Programm soll.
    GELAUFEN 26.10. 15:05 (start_ap55.bat), markiert vorher -> nachher / uebernommen / Anker+Quelle+Ziel; Regression ueberall 0 fremde Abweichungen:
      Spiegelschwestern 1->0 / 1/1 / 85,94 % ; CotW 2->0 / 2/2 / 89,02 % ; Alice 14->4 / 11/14 / 92,95 % ; Sleepy 3->1 / 2/3 / 94,96 %
      AYLI 2->0 / 2/2 / 93,68 % ; Jekyll 16->4 / 12/16 / 94,22 % ; P&W 11->3 / 8/11 / 94,98 % ; Baskerville 17->2 / 16/17 / 92,57 %
      Gesamt: 66 -> 14 markierte Saetze (54 uebernommen). Kosten: Modal Spiegelschwestern 0,004 $, DeepSeek ~0,015 $ (Schaetzung). Demo-Export neu.
    Rest-14 Saetze: kein dritter Lauf (DeepSeek verwirft dort wiederholt) -> bei Bedarf Kuratormodus/Hand.
    Offen aus AP 55: Commit taella-app der neu exportierten Demo-Manifeste; CotW-Hoerspiel-Wortzeiten (overlay_montage); d) Reader-Hervorhebung als eigenes AP.
4f. AP 56 26.10.: Folgepunkte aus AP 55 (Stand 26.10. ~16:00). Sicherung: archive/2026-10-26_56/ (read_layer: PROJEKTSTAND, overlay_montage, export_demo, s525; taella-app: Reader/Satz/Page/ListenView/App, wortpaar/useListen/loader, CotW-Demo-JSONs).
    1) ERLEDIGT CotW-Hoerspiel-Wortzeiten DE: Pruefung vorhandene vc/-Clips = Erzaehler + (vc_korr-Spanne - ersetzte Stelle), 63/63 exakt (0,0 s) -> KEIN Montage-Neulauf.
       tools/overlay_montage.py neu: --nur-wortzeiten (Spannenlaengen aus spannen/vc_korr) -> work/520_wortzeiten_de_hoerspiel.json (63 Saetze).
       s525 CotW: 700 Anker tzhs (DE-Hoerspiel-Ziel), Anker+Quelle+Ziel 89,02 %; regression_54b 0 fremde Abweichungen. export_demo --audio --hoerspiel.
       Browser: Hoerspiel EN·DE (c001_00194_dl, Perrault) Wort + Gegenwort synchron (er<>he, Blick<>eyes, fiel<>lit). Commit taella-app fcfdd1d.
    2) ERLEDIGT d) Lesen beim Hoeren: Reader-Knopf im Hoeren laesst den Ton weiterlaufen (ListenView unsichtbar, Steuerpille Pause/Hoeren/x).
       src/lib/hoerzustand.js (Store, nur der gehoerte Satz rendert neu); wortpaar.hoerZeichen() = gleicher Weg wie ListenView (Token-Karaoke + Ankerzeit, Hoerspiel ths).
       Satz.jsx: Satz getoent + aktuelles Wort markiert, Flyover bleibt. Seite folgt dem gehoerten Satz (ab Satzbeginn; manuelles Blaettern wird bis zum naechsten Satz respektiert).
       Browser CotW Hoerspiel DE: Satz/Wort laufen mit, Pause/Weiter/zurueck zum Hoeren/Schliessen ok, keine Konsolenfehler. Commit taella-app 6ac0840.
    3) ERLEDIGT Rest-14 als Kurator-Vorlage (nichts geaendert): tools/ap56_rest_liste.py -> je Werk work/345_rest_kurator.json + docs/AP56_rest_saetze_345.md
       (Alice 4, Jekyll 4, P&W 3, Baskerville 2, Sleepy 1; je Wort: Quellwort | jetzt s340 | Pruefaligner-Vorschlag).
    Nicht gebaut (bei Bedarf): f) GCS-Audio (mit Punkt 10), h) weitere Werke vertonen.
    Offen: CK prueft Lesen beim Hoeren im Alltag; Rest-14 im Kuratormodus entscheiden (Uebernahme Pruefaligner-Vorschlag waere eigenes kleines Werkzeug).
4g. AP 57 26.10.: Stage 560 Sprachpruefung mit Neuvertonung (CK: DE-Audio kippt ins Englische, Alice + Baskerville; Gemini bleibt).
    Sicherung: archive/2026-10-26_57/ (sprachpruefung, neu_vertonen, sprache_modal, start_*.bat, run.py, Baskerville-Pruefung vorher).
    GEBAUT (nicht gelaufen - Modal/Gemini nur Windows):
    - gpu_sprache/sprache_modal.py: immer zweiter Whisper-Durchgang in der Zielsprache erzwungen, mit Wort-Konfidenz ("woerter").
    - tools/sprachpruefung.py: neu wort_unsicher (Wort-Konfidenz < 0,25) + wort_en (englische Form gehoert, im EN-Satz, nicht im Soll) -> Stufe verdacht.
      Befund alte Baskerville-Daten: p_de + wort_en allein fangen feine Akzente kaum -> Wort-Konfidenz ist der neue Hauptmelder.
    - tools/s560_sprachpruefung.py: --auswahl (gekippt | p<0,5 | wort_en | >=2 unsichere Woerter oder eines <0,10 | CK kippt; CK ok nie;
      CK-kippt-Urteile nach Neuvertonung ungueltig; max. 2 Runden je Satz; HALT bei > 20 % Auswahl, Exit 4) und --bericht
      (work/BERICHT_560_<lg>.md Rest fuer Kuratormodus + aussprache_<lg>_vorschlag.json, nicht angewendet).
    - tools/neu_vertonen.py --stage560: Gemini (config MODELS tts = gemini-3.8-flash-tts, wie Alice 11.10./Baskerville 12.10. vertont),
      gleiche Stimme je Figur (casting/sprecher), deutsche Regie, Lexikon nur wenn freigegeben; Lauf mit quelle s560 + modell protokolliert.
    - start_s560.bat <werk> [lg]: Pruefen -> Auswahl -> Gemini -> Wortzeiten (fa_modal, sonst s520) -> Pruefen, bis 2 Runden; dann Bericht, s525, Demo-Export.
      start_ap57.bat = Alice, dann Baskerville. Trockentest Auswahl/Liste/Bericht an alten Baskerville-Daten ok.
    OFFEN: CK startet start_ap57.bat. Schwellen (P_WORT 0,25 / 0,10) nach Alice-Lauf mit Cockpit-Urteilen kalibrieren;
      bei HALT erst Bericht ansehen, dann mit S560_OHNE_GRENZE=1 starten. Kosten Schaetzung: Whisper ~0,3-0,5 $/Werk, Gemini nur Auswahl.
4h. AP 58 26.10.: Vollproduktion Winnie-the-Pooh + Illustrationen (laeuft). Sicherung: archive/2026-10-26_58/.
    ERLEDIGT 1 Import: Werk milne-aa/winnie-the-pooh (Gutenberg #67098, Quelle _epub_import/winnie-the-pooh/: pg67098.txt + HTML-ZIP).
       book.json: rechte gemeinfrei, gemeinfrei_eu_ab/veroeffentlichen_ab 2027-01-01 (Milne +1956), Shepard-Bilder nicht verwendet;
       glossar_fest (Pu, Ferkel, I-Ah, Eule, Kaenga, Ruh, Kaninchen, Christopher Robin ...), DE-Titel "Winnie-der-Pu" (titel_pruefen).
       KEINE Modernisierung (Original 1:1): tools/pooh_vorbereiten.py schreibt work/modernized/ + raw_modernized.txt (11 Kapitel inkl. Einleitung).
       Lieder als eigene Knoten: neuer Tag-Typ vs (Strophe, Zeilen mit \n; 18 Strophen). Vorbereitung setzt config.VERS_MARKE, s200 macht daraus vs.
       Geaendert: config (TAG_TYPES/PAUSE vs, VERS_MARKE), s200 (Regel + Marke->vs), s210 (book.json glossar_fest), s310 (Vers-Hinweis: Reim,
       gleiche Zeilenzahl), s420/audio_plausi/sprachpruefung/tts_paket (vs = Audio-Typ), s630 (vs eigener Absatz).
    ERLEDIGT 2 Bildanker: tools/pooh_bildanker.py (27 Bilder, Anker = letzter Satz des Absatzes bzw. Kapitelueberschrift) -> work/bilder.json
       nach Tagging; Probe gegen Quelltext 21/21 Textanker eindeutig.
    3 Bild-Probe: 5 Bilder (Nr. 4, 7, 14, 54, 114) Gemini 3.1 Flash Bild, One-Line, nur Text; Ausgabe C:\Users\sabin\Claude\gemini-mcp\output\*pooh_*.jpg
       (Ordner fuer Claude nicht freigegeben). CK 26.10. 17:47: alle 5 brauchbar.
    ERLEDIGT 3 Rest: 22 Bilder erzeugt (alle 27 fertig). 5 Prompts von Gemini blockiert (IP-Filter: Baer+Ferkel/Ensemble-Szenen 27, 30, 39, 85, 90)
       -> neu mit neutralen Figuren ("round little toy animal", ohne Namen) erzeugt. Gemini-Pruefung 22/22: eine Linie, kein Text, kein grober Fehler.
       Kosten ~27 x 0,039 $ = ~1,05 $ (blockierte Anfragen kosten nichts). Kopieren ins Werk: start_ap58_bilder.bat -> images/bilder/pooh_NNN.jpg.
    ERLEDIGT Cover (CK 26.10. 18:06): Bild 103 (Schirmboot) = Titelbild. images/cover.jpg = 2:3-Flaeche #faf8f4, Bild mittig (Grund angeglichen);
       s615 gelaufen -> fassungen/en|de/output/cover_final_*.jpg ("Winnie-the-Pooh" / "Winnie-der-Pu"). Kein s610-Lauf (0 $).
    Textkette 26.10.: 200-340 gelaufen (0,75 $), 18/18 Strophen vs, Uebersetzung vollstaendig, 27/27 Bildanker. DE-Titel "Winnie-der-Pu" CK-frei.
       Tor 330: 89/1403 unter Score 90 (61 davon 85-89; Schnitt 96) = idiomatische DE-Fassung -> READLAYER_WEITER=1 in start_ap58_text.bat.
    ERLEDIGT Stage 400 (Regie). Text komplett bis 400 + 340.
    Casting vorbereitet (tools/pooh_casting.py -> work/casting.json, Tor offen): Gemini-Standardstimmen EN+DE gleich,
       Erzaehler Algieba; Pu Umbriel, Ferkel Leda, I-Ah Algenib, Eule Rasalgethi, Kaenga Sulafat, Ruh Laomedeia, Kaninchen Fenrir,
       Christopher Robin Puck. Figurenrede spaeter direkt mit Gemini (overlay_gemini), keine VC. Lieder (vs) -> singende Figur (s420).
       start_ap58_casting.bat: s420 + Hoerprobe Kapitel I EN/DE (work/_hoerprobe/<lg>/c002.wav), ~0,5 $. Danach CK-Freigabe.
    ERLEDIGT Casting: s420 gelaufen (sprecher.json; 32 unsichere Saetze in work/sprecher_pruefen.txt, Rueckfaelle = Erzaehler),
       Hoerprobe Kap. I EN 17,3 / DE 18,1 min, TTS 0,39 $. CK 19:03 abgenommen -> casting.json tor freigegeben, book.json stimmen_freigabe/besetzung.
    Vollvertonung: start_ap58_vertonung.bat (hoerprobe_mehrstimmig alle --satzdateien -> manifest_schreiben -> fa_modal EN+DE -> start_s560 EN + DE).
       Schaetzung: TTS ~3,6 $ (22.500 Woerter, ~3 h Audio je Sprache), Modal ~1-3 $, s560 ~1 $.
    OFFEN (alt): CK startet start_ap58_text.bat (200-400 + 340 + Bildanker, Pruefung tools/ap58_pruefen.py). Dann Casting (s410 + Freigabe), Vertonung EN/DE,
       start_s560.bat, Reader (Knoten typ bild). Kosten: docs/AP58_kosten.md (Schaetzung ~12-16 $; Bild-Probe ~0,20 $).
4i. AP 60 27.10.: Hoerprobe woertliche Rede - Kontext-Tripel (A) vs. Voice Conversion (B) gegen Sprachdrift kurzer Repliken (Folge AP 57).
    Sicherung: archive/2026-10-27_60/ (PROJEKTSTAND vorher + neue Skripte). Produktion unveraendert.
    Testpassage: Alice Kap. VII, c007_00033..c007_00049 (10 Saetze, 12 Rede-Segmente: Maerzhase, Alice, Hutmacher, Haselmaus), 9 Einheiten (Tripel).
    GEBAUT (nicht gelaufen - Gemini/Modal nur Windows): start_ap60.bat ->
    - tools/ap60_vorbereiten.py: tests/ap60/passage.json (Segmente aus sprecher.json, Stimmen aus casting.json), Referenz = fassungen/<lg>/audio, Stimmproben = stimmen_archiv/<stimme>/muster_<lg>.wav.
    - tools/ap60_gemini.py: A = je Tripel EIN Multi-Speaker-Aufruf (speech_config [{speaker, voice}], max. 2 Stimmen), B-Basis = Satz komplett mit Erzaehlerstimme.
      Sprache fest: Feld "language" (de-DE/en-GB) in speech_config; lehnt die API ab -> ohne Feld, nur style (vermerkt in gemini_bericht.json: sprachfeld_angenommen).
    - gpu_tts/ap60_modal.py: MMS_FA schneidet Rede-Segmente (A, B, Referenz), B: Chatterbox VC auf Figurenstimme; Whisper large-v3 Sprach-ID je Segment;
      je Sprache 3 durchgehende Dateien, loudnorm -18 LUFS, Pause 0,6 s -> tests/ap60/ergebnis/<lg>_A_multispeaker|B_voiceconversion|Referenz.wav, tabelle.md.
    Schaetzung: Gemini ~0,10 $ (~6 min Audio), Modal ~0,15-0,25 $. OFFEN: CK startet start_ap60.bat, hoert ab; Ergebnis/Tabelle hier nachtragen.
    GELAUFEN 27.10.: Gemini 60 s, 0,065 $, Sprachfeld language (de-DE/en-GB) von der API ANGENOMMEN (Multi-Speaker = ein Text-Item je Turn mit speech_metadata.speaker).
      Hoerproben tests/ap60/ergebnis/ (A, B, Referenz je Sprache). Whisper-Tabelle fehlt (1. Lauf: requests fehlte im Image; Neulauf start_ap60_modal.bat haengt > 20 min im VC-Schritt).
    ENTSCHEIDUNG CK 27.10. 16:24: Weg B (Voice Conversion) VERWORFEN wegen Rechendauer.
    HOERURTEIL CK 27.10. 16:37: Referenz = direkte Rede mit Abstand am ausdrucksstaerksten, aber Inquit-Saetze ("sagte Alice") verrutscht.
      A Multi-Speaker = Inquits sauber, Prosodie der Rede leidet, teils falsche Stimme zum Text. B VC = Stimme/Text stimmen, Inquits sauber, Prosodie hinter Referenz.
    FAZIT CK: Hybrid (Variante C) - Figurenrede aus dem Erstlauf (Segment je Figur wie Produktion), Erzaehlerspur aus One-Voice-Vertonung
      (ganzer Satz mit Erzaehlerstimme, Inquits per MMS_FA herausgeschnitten). Hoerspiel-Anspruch rechtfertigt Mehrkosten (zweite Erzaehler-Take nur fuer Saetze mit Rede).
    ZIELPROZESS Hoerspiel (CK 27.10. 16:52, abgenommen):
      1. Erzaehlerfassung: ganzes Werk mit vorab festgelegter Erzaehlstimme (bleibt auch im Hoerspiel); bei wechselnder Ich-Perspektive (z. B. Spiegelschwestern) Erzaehlstimme je Kapitel.
      2. Saetze mit direkter Rede extrahieren, Figuren zuweisen (s420 / sprecher.json).
      3. Casting je Figur mit Charakterbeschreibung (z. B. "Mann, 50, Seemann, raue tiefe Stimme, leicht engl. Akzent") (s410).
      4. Figurenrede vertonen (Segment einzeln, Sprachfeld language gesetzt, KEIN "pronounced as in English") und in der Hoerspielfassung
         NUR die Rede-Segmente der Erzaehlersaetze ersetzen (Schnitt per MMS_FA); Einschuebe ("sagte Alice") bleiben aus der Erzaehlerfassung.
      Nebenbefund: tools/hoerprobe_mehrstimmig.py _aussprache setzt "<Name> pronounced as in English" -> Ursache fuer "said Alice" in DE; streichen.
4j. AP 61 28.10.: Hoerspiel-Hybrid (Variante C, CK-abgenommen) ins Werk - zuerst Alice. Sicherung archive/2026-10-28_61/.
    GEBAUT: tools/hybrid_einbau.py + start_hybrid.bat <werk> [de|en|beide] [liste|takes|los].
    Je gemischtem Satz (Erzaehler+Figur in sprecher.json): Erzaehler-Take ganzer Satz (Gemini, Sprachfeld language, Cache work/_hybrid/<lg>/erz/),
    Einschuebe aus Take, Figurenrede aus Erstlauf (Sicherung fassungen/<lg>/audio_alt_<datum>_hybrid/), Schnitt MMS_FA lokal, RMS-Angleich Erzaehler an Figur.
    Kein sauberer Schnitt -> Satz bleibt alt. Danach Wortzeiten (fa_modal, Fallback s520) + Sprachpruefung. Protokoll work/hybrid_<lg>.json.
    Alice: je 706 gemischte Saetze, ~101 min (de) / ~97 min (en) -> Gemini ~2,7 $ fuer beide Sprachen. OFFEN: CK startet, Hoerprobe Kap. VII.
    29.10.: DE FERTIG - 705/706 eingebaut (c010_00006_dl alt: kein Schnitt), Gemini 1,37 $, Wortzeiten neu, Sprachpruefung DE 1529 Saetze: 4 gekippt, 9 Verdacht
      (keiner in Einschueben; "Wau!", "Hinab, hinab" wie bisher). hybrid_einbau.py wiederaufnehmbar (fertig.txt, Sicherung audio_alt_20261028_hybrid). EN OFFEN (nur 13 Takes).
    29.10.: EN FERTIG - 703/706 eingebaut (alt: c002_00042_dl + c005_00144_dl = Gemini "policy" 400, c010_00006_dl kein Schnitt), Gemini ~1,30 $,
      Wortzeiten neu (1529), Sprachpruefung EN: 0 gekippt, 18 Verdacht (Interjektionen/Zahlen, keine Drift). AP 61 Alice ABGESCHLOSSEN, Gesamt ~2,7 $.
      fa_modal.py / sprache_modal.py: gpu=["L4","A10G","T4"] (Fallback bei L4-Engpass, 29.10. 20 min Warteschlange). OFFEN: CK-Hoerabnahme in der App.
4k. AP 62 VORGEMERKT (29.10.): Hoerspiel-Hybrid als feste Pipeline-Stufe (Prompt von CK in neuer Sitzung). Reihenfolge der Aufgaben:
    Stufe benennen/einhaengen -> Sprachfeld zentral in tts_client.py + "pronounced as in English" entfernen -> Montage aus hybrid_einbau.py uebernehmen
    -> Schnitt auf Modal (L4/A10G/T4, CPU-Rueckfall) -> Policy-Ablehnungen automatisch Rueckfall. Test: Dialog-Kapitel neues Werk + Alice Kap. VII Gegenprobe.
5. Drama-Erkennung automatisch (Cockpit/Stage 11); Dramen (Macbeth, Hamlet, Romeo and Juliet, Tempest, Earnest, Lysistrata, Pygmalion) Text neu ab Stage 11.
6. 57b-Rueckfaelle automatisch in kleinen Paketen wiederholen; Kosten von 57/57b ins Kostenlog.
7. Stimmen der Musterwerke nachtraeglich per Probe/Freigabe pruefen (Kandidaten ohne CK-Freigabe).
8. ENTSCHIEDEN (CK 16.10. 15:03): Modal-Volume fuer Modellgewichte (Chatterbox, Whisper large-v3, pyannote, ECAPA) statt Download je Lauf.
   Kosten 0 $ (Volumes 0,09 $/GiB-Monat, 1 TiB/Monat frei; ~10 GB). Erst NACH Baskerville-Neuvertonung + Sprachpruefung umbauen (gpu_sprache laeuft sonst mit).
   Vorbild: archive/2026-10-18_audit/gpu_tts/tts_modal.py bzw. gpu_tts/tts_modal_opt.py (Volume readlayer-tts). Betroffen: gpu_overlay, gpu_messung, gpu_sprache, gpu_fa.

C – Geschaeft
9. Ertragsmodell (taella_ertragsmodell.xlsx) mit Produkttreppe + Patenschaften; offen: Umfangsdeckel, Produktionsfrist, Verkauf ueber taella.io; Wettbewerbsanalyse (Lern-Apps).
10. Android-Testversion (Capacitor) + Cloud-Audio (GCS-Bucket).

MERKLISTE (kein Termin)
- Chatterbox: exaggeration/cfg_weight-Test, laengere Referenz; Referenz-Export je Stimme; eigene GPU + lokales TTS.
- Rechtliches: Google-Nutzungsbedingungen, juristische Pruefung Stimmumwandlung (IT-Recht) vor produktivem Einsatz.
- Cockpit: Wikidata (Stage 01), LibriVox-Import, TAELLA-Paket, "Neu erzeugen" nach Ablehnung.
- Startliste: Grimms' Fairy Tales = Uebersetzung; Earnest = Drama. DeepSeek flash vs. pro an einem Kapitel. Thorsten-Tempo (length_scale).

## 22.10.2026 — Eigenes Werk "Die Spiegelschwestern" (CK = Autor) — AP1+AP2 erledigt, AP3 offen
Nordic-Noir-Novelle, Original DEUTSCH (erstes Werk mit Quellsprache DE). Text-Quelle: Claude-Doc
https://claude.ai/artifact/AuG739m52MPogV1JMefprr (Tab 1 = Novelle, Prolog + 11 Kapitel + Epilog, ca. 51 kB;
Tab 2 = Figuren-Steckbriefe). Export als Markdown ueber Docs-Export, nicht abtippen.
Vorgaben CK: Autor "Unbekannt" (keine Wikidata-Abfrage), Rechte = eigene Rechte (nicht PD, keine Todesjahr-Pruefung),
Uebersetzung DE->EN, Klappentext DE + EN (Stage 600), Cover im PD-Stil (Strichzeichnung, 610/615),
Hoerspiel-Schicht NUR DE (Steckbriefe Tab 2: Zwillinge = eine Grundstimme, zwei Sprechweisen),
EN = Chatterbox-Standardstimme ohne Hoerspiel-Schicht. Teaser: Krimi -> Herr A (DE mix_v1 + Ref herr_a, EN Overlay herr_a).
Befund 22.10.: Pipeline kann DE als Quelle NICHT. config.SOURCE_LANGUAGE="en"/TARGET_LANGUAGES=["de"] global;
book.json "originalsprache" lesen nur s110, s620, aussprache_lexikon, titel_auto. Textkette 200-340 und s520 haengen am
globalen Wert; feste "en" in s310, s340, s710; Frontend (loader.js) nimmt EN als Anker.
Arbeitspakete (je eine Sitzung):
  AP1 ERLEDIGT 22.10.2026 (Sicherung: archive\2026-10-22_sprachweiche\, inkl. taella-app\):
      - config.py: WERK_SPRACHPAARE {en:[de], de:[en]}; book_dir() setzt SOURCE/TARGET/ALL_LANGUAGES aus book.json
        "originalsprache" (Cache je Werk); config.werk_sprachen(book), config.align_keys().
      - run.py: werk_sprachen() am Laufbeginn; Stage-620-Check ohne Import-Zeit-Sprache.
      - s340: Ergebnisschluessel je Richtung (EN-Werk unveraendert en/en_span/de/de_span; DE-Werk de/de_span/en/en_span);
        eigener DE->EN-Prompt (_build_prompt_de_en), EN->DE-Prompt unangetastet.
      - s520: Quell-Span ueber align_keys(). s710: _slim_align je Richtung, Align ins Manifest der Originalsprache,
        Manifest-Feld "originalsprache".
      - taella-app: loader.js ankert im Manifest der Originalsprache (meta.originalsprache); Satz.jsx richtungsneutral.
      - Regression: Call of the Wild Manifest EN+DE alt/neu identisch (bis auf "erstellt"); s340 EN-Ausgabe identisch.
      - CK pruefen: Mock-up neu laden, Flyover/Karaoke bei Call of the Wild kurz anschauen.
      Bewusst offen (gehoert zu AP3/AP4, dort am Werk testen): s600 Klappentext (komponiert EN, uebersetzt EN->DE),
      s420 Sprecherzuordnung (liest Feld "en"), s410 haupt_lg, tools/sprachpruefung + export_app (EN-Fallbacks).
  AP1 (Plan) Sprachweiche je Werk: Quell-/Zielsprache aus book.json statt global; feste "en" raus; 54a-Prompt richtungsneutral;
      Frontend-Anker = Originalsprache. Regression: ein EN-Werk (z. B. Call of the Wild) muss unveraendert laufen.
  AP2 ERLEDIGT 22.10.2026 (Sicherung: archive\2026-10-22_eigenwerk\):
      - Text: Claude-Doc Tab 1 als Markdown exportiert -> _epub_import\die-spiegelschwestern.md (50.919 Byte, identisch mit Export).
      - NEU tools\s160_eigenwerk_import.py (Markdown -> Werk): authors\unbekannt\books\die-spiegelschwestern\ mit book.json
        (originalsprache de, rechte "eigene", herkunft eigenwerk, erscheinungsjahr 2026, Fassung de), raw.txt (Markdown),
        raw_modernized.txt (###-Marken), work\modernized\chapter-1..13.json (Prolog, Kapitel 1-11, Epilog; 408 Absaetze,
        ~48.000 Zeichen, Szenenwechsel als HR). Stage 120 entfaellt (wie ePub-Import). Kopfzeilen (Erzaehlerin + Ort/Zeit)
        bleiben eigene Absaetze. Index: die-spiegelschwestern -> unbekannt.
      - author.json unbekannt: name_display "Unbekannt", name_display_en "Unknown", wikidata_abfrage false
        (gilt auch fuer Beowulf u. a. dort; vorher leer -> Slug "unbekannt" im EPUB).
      - config: werk_rechte(book)/eigene_rechte(book) aus book.json "rechte" (Default gemeinfrei).
      - s110: keine Wikidata-Abfrage fuer eigene Werke und Autor unbekannt.
      - Cockpit: rechte=eigene -> PD-Tor automatisch frei, Flag "eigene Rechte"; naechster Schritt "text".
      - s620: eigenes Werk -> Impressum/dc:rights "(c) 2026 SOMNIO. Alle Rechte vorbehalten." (EN: All rights reserved.),
        keine Gutenberg-Quelle, nicht "modernisiert". Test-EPUB DE gebaut (nur Testordner, nicht in fassungen\).
      - Regression: Call of the Wild Metadaten/Impressum unveraendert.
      - Guard s700 braucht 400_regie -> Pruefung in AP3 nach Lauf bis 400.
      - BEFUND fuer AP3/AP4: Kursiv als _..._ (SMS-Texte, Ort/Zeit-Zeilen) wird weder im EPUB (s620) noch in der
        Vertonung (sprechtext) umgesetzt -> Unterstriche erscheinen im EPUB; gilt auch fuer EN-Werke (z. B. Lysistrata).
      - Naechster Lauf (AP3): python run.py die-spiegelschwestern --line audio --to 400 --live ; danach s700, 600/610.
  AP3 STAND 22.10.2026 16:40: Lauf bis 400 fertig (Rueckuebersetzung Schnitt 95,4; 10 % < 90 = literarische Kurzsaetze,
      bewusst weiter mit READLAYER_WEITER=1; 6 EN-Saetze in 310/330 von Hand verbessert). Guard s700 GRUEN (1.045 Saetze DE/EN).
      Klappentext 600 ok; s600: eigenes Werk -> kein Autor-Block, EN-Koeder aus Werkuebersetzung (eigenwerk_anpassen).
      Cover 610 von CK abgenommen. EN-Titel (CK): "The Mirror Sisters" (book.json fassungen en).
      Offen: EN "Kammer" uneinheitlich (box room/little room/room).
      615-630 (16:38): Pillow fehlte in CKs Python -> kein Cover final, SVG-Cover im ePub. EN-ePub nur 292 statt 408 Absaetze:
      Tagger (200) setzt p-Marken unvollstaendig (Prolog ohne eine). Fix s630 _absatzgrenzen(): Absatzgrenzen aus
      work/modernized/chapter-N.json per Textabgleich (nur wenn Kapitel komplett aufgeht) -> 408 Absaetze.
      Dabei gefunden: Tagger hat 2 Saetze VERSCHLUCKT (Kap. 4: "Ich stehe auf.", "Seine Stimme ist ganz ruhig.") ->
      in 200/310/320/330/400 an den Folge-/Vorsatz angehaengt (DE+EN). Jetzt Quelltext = 400_regie in allen 13 Kapiteln.
      BEFUND allgemein: Satzverlust im Tagger auch bei Call of the Wild (Kap. 2/4, z. B. "A shout from Francois hailed
      his appearance") -> 320 Integritaet prueft das nicht. Eigenes AP: Volltext-Abgleich Quelle vs. 200 als Pruefstopp.
      AP3 ERLEDIGT 22.10.2026 16:43: Pillow installiert; Cover final DE/EN, ePub DE (437 Abs. nach Mobil-Teilung) +
      EN "The Mirror Sisters" (415 Abs.) in fassungen\<lg>\output\. CK: ePubs gegenlesen.
      Naechstes: AP4 Audio (neue Sitzung).
  AP4 GEBAUT 22.10.2026 17:30 (noch nichts auf Modal/DeepSeek gelaufen; Sicherung archive\2026-10-22_ap4_audio\):
      - Steckbriefe (Doc Tab 2) -> work\steckbriefe.md. DREI Ich-Erzaehler je Kapitel: Mehring c001,c008-c011,c013;
        Cindy c002,c004,c006,c007,c012; Katharina c003,c005. Klappentext-Erzaehler = Herr A (nur Teaser).
      - work\casting.json (Vorschlag Claude, tor "offen", hoerspiel_sprachen ["de"]): plan.erzaehler_je_kapitel,
        plan.sprechweise, 16 Figuren aus dem Archiv (D aus Praat-Profilen): Mehring=m_mittel_tief_ruhig (Malcolm),
        Zwillinge=w_jung_mittel_verschmitzt (Sophie), Werner=m_alt_tief_cholerisch (D 4,80 zu Mehring),
        Maximilian=m_mittel_hoeher_thornton_2 (4,15), Schneider=m_alt_hoch_hochmuetig (5,87), Clarissa=w_mittel_mittel_cholerisch
        (4,62 zu Zwillingen), Sommer=w_jung_mittel_aengstlich (6,59), Sophie(Figur)=w_kind_hoch_neugierig (7,79), Brenner=w_alt_tief_cholerisch,
        Aydin=w_jung_mittel_ruhig, Richter=w_mittel_hoch_cholerisch, Okafor=w_jung_hoch_ruhig, Prof. Auswahl=m_mittel_hoch_nervoes,
        Schulleiterin=grossmutter_b (ohne Praat-Profil, Abstand messen), Fahrer=m_alt_mittel_ruhig. Keine Neu-Designs noetig.
      - Zwillings-Sprechweise (nach dem Vertonen, Praat): Cindy -1 HT/Formant 0,98, Katharina +1 HT/1,02; Kap. 6 (c007) gleitend
        Cindy -> +0,5/1,01; Cindy-Rede c008-c011 +0,5/1,01; Kap. 11 (c012) zurueck zu Cindy. Werte in casting.json frei justierbar.
        NEU tools\sprechweise.py (Erzaehl-Audio, Originale audio_vor_sprechweise\); overlay_korrektur nutzt dieselben Werte fuer Rede.
      - tts_paket.py: Erzaehlerstimme je Kapitel automatisch (refs + stil je Satz) fuer Hoerspiel-Sprachen; gilt auch fuer cb_neu;
        Teaser-Pakete ausgenommen. EN = Standardstimme (keine refs).
      - s420 sprachneutral (Quelle/Ziel aus book.json) + Prompt-Hinweis Ich-Erzaehler je Kapitel (eigene Rede -> Figurenname).
      - overlay_vorbereiten: Rede des Kapitel-Erzaehlers im eigenen Kapitel kein VC.
      - sprechtext.py Regeln 4-7 (alle Werke): Kursiv _..._ weg (Befund AP2), DE Datumsspanne "28.–31. August",
        Datum "16.08.2007", Uhrzeit "7:15 Uhr" -> "sieben Uhr fuenfzehn", "ca." -> "circa".
      - work\aussprache_de.json (15 Eintraege, freigegeben=false): Aydin, Okafor, Steilshoop, Blankenese, Holstenglacis,
        Lindqvist, MIT, LKA, ETH, UKE, DNA, K. v. T., "P gegen NP", "SIE SOLL AUFHOEREN".
      - Start: start_spiegelschwestern.bat probe -> (CK: Lexikon freigeben) sprecher -> (CK: Kontrollansicht, Besetzung tor
        "freigegeben") -> de -> en -> hoerspiel -> (Cockpit Hoerspiel-Pruefung) -> teaser -> export. Kosten ~1 $ gesamt.
      - Offen: Schulleiterin "Mikrofonklang" (Effekt) nicht umgesetzt; EN "Kammer" uneinheitlich (aus AP3).
      - 22.10. 17:07 Namensprobe (Chatterbox) gelaufen: 12 Saetze, 0,02 $, Erzaehler je Kapitel korrekt.
      - 22.10. 17:20 UMSTELLUNG DE auf Gemini 3.8 Flash TTS (CK): Mehring = designte Stimme m_mittel_tief_ruhig (voice_axuapv2e9fp7),
        Zwillinge = Gemini-Standardstimme Zephyr (185 Hz). casting.json plan.vertonung/gemini_stimmen/overlay_gemini.
        tools\gemini_parallel.py: --voice je Kapitel aus casting. s500: freigegebenes Aussprache-Lexikon jetzt auch fuer Gemini.
        Zephyr nie VC-Vorlage (Regel 14.10.) -> Zwillingsrede in Mehring-Kapiteln: NEU tools\overlay_gemini.py (Spanne direkt mit
        Gemini Zephyr, Raender geschnitten); Zwillingsrede im Zwillingskapitel: Originalspanne + Sprechweise ("kopie").
        overlay_vorbereiten -> jobs_gemini.json; overlay_korrektur/montage lesen sie mit. EN bleibt Chatterbox-Standardstimme.
        Kosten DE-Basis ~0,75-1 $ (Einfuehrungspreis bis 31.12.2026), AP4 gesamt ~1,50-2 $.
        Offen: Wortzeiten der Hoerspiel-Saetze mit Gemini-Spannen (andere Laenge) nach Montage neu; neu_vertonen.py kennt
        nur eine Stimme je Werk (Stimme je Kapitel nachruesten, falls Saetze neu muessen).
      - 22.10. 19:00 DE-BASIS FERTIG (Gemini): 1.045 Saetze, 340 Wortalignment (fehlte, jetzt in start_..bat de), Wortzeiten 1.045 (Modal 8 min),
        Sprechweise 582 Saetze (Originale audio_vor_sprechweise). Lauf 1 mit --jobs 5 brach ab (RAM, FA beim Blockschnitt) -> --jobs 2.
        Naechstes: CK hoert c002/c003 (Zwillinge) + Mehring; dann en, hoerspiel (sprecher.json liegt vor), teaser, export.
      - 22.10. 19:50 EN fertig (1.045 Saetze, 0,73 $; ep-Typ jetzt in tts_paket.TYPEN; cb_neu-Fix Standardstimme). Sprechweise CK: passt.
      - 22.10. 20:10 Hoerspiel r2: ok 9 Figuren; umbesetzen laut Messung: Mehring, Werner, Schneider, Schulleiterin.
        Entscheidung: Mehring-Rede in Zwillingskapiteln direkt mit Gemini (overlay_gemini, eigene Stimme); Schneider freigeben
        (pyannote 100 %, D 6,9, ECAPA 0,56 knapp); Werner + Schulleiterin umbesetzen (umbesetzen.py misst jetzt gegen den
        Erzaehler der Kapitel, in denen die Figur spricht; trennung.erzaehler_profil(kapitel=)). overlay_montage ueberschreibt
        Gemini-Spannen nicht mehr mit alten VC-Ergebnissen. Modal-Mail 10-GPU-Limit (EN-Lauf, 13 Kapitel parallel) = nur Wartezeit.
      - 22.10. 20:50 r3: Werner/Schneider/Schulleiterin weiter "umbesetzen" (Umbesetzung erzeugte keine Kandidaten). Entscheidung:
        alle drei wie Mehring DIREKT MIT GEMINI in ihrer designten Archivstimme (overlay_gemini: Bernard, Percival, Agnes);
        deren Formant-Korrekturen ausgesetzt (casting korrektur_alt). Montage filtert jetzt auch Teilpakete gegen Gemini-Spannen.
        Ablauf: overlay_vorbereiten -> overlay_gemini --force -> overlay_montage -> CK hoert (audio_overlay\hoerliste.txt) -> Tor.
      - 22.10. 21:00 Hoerspiel-Tor DE FREI (CK). Offener Punkt Wortzeiten erledigt: overlay_montage schreibt
        work\520_wortzeiten_<lg>_hoerspiel.json (Spanne gestreckt, danach versetzt), export_demo --hoerspiel setzt sie ein.
        Rest AP4: overlay_montage einmal neu (fuer die Wortzeiten), teaser, export.
      AP4 ERLEDIGT 22.10.2026 21:08: Teaser DE (Herr A ueber mix_v1, 33 s) + EN (Standard + Overlay herr_a, 26 s) in
      fassungen\<lg>\teaser\teaser_<lg>_m.wav; Export Mock-up taella-app\public\demo\die-spiegelschwestern (DE mit Hoerspiel
      164 Saetze + Hoerspiel-Wortzeiten, EN 1.045 Saetze; Katalog 13 Werke).
      Kosten AP4 ca. 2,50 $ (Gemini DE ~1 $, EN Chatterbox 0,73 $, Overlay/Messung/Teaser/340 Rest).
      CK pruefen: Werk im Mock-up anhoeren (Hoerspiel DE, Karaoke in Gemini-Einschueben), Teaser anhoeren.
      Nachholen (Regel Tests ins Archiv): work\_cb_probe -> archive\2026-10-22_tests\ (Datei gesperrt beim Verschieben).
      Learnings: gemini_parallel max. 2 Kapitel (RAM beim Blockschnitt); Stage 340 gehoert vor Wortzeiten (Audio-Linie pruefen);
      Gemini-Direktsprechen der Figurenrede (designte Archivstimme) trennt sicherer als Chatterbox-VC, wenn VC nicht reicht.
  AP2 (Plan) Werk anlegen: Import (Rohtext/ePub), Autor "Unbekannt", Rechte-Feld "eigene Rechte", Guard/Export pruefen.
  AP3 Textkette: Uebersetzung DE->EN, Klappentext DE/EN, Cover.
  AP4 Audio: DE Vertonung + Hoerspiel-Schicht nach Steckbriefen; EN Standardstimme; Teaser Herr A.
  Aussprache-Lexikon vorab: Mehring, Aydin (Aydın), Okafor, Steilshoop, Blankenese, Holstenglacis, Lindqvist.

## 19.10.2026 — Klappentext-Teaser mit Chatterbox (CK) — Testsequenzen bereit
Regel + Stimmen: docs\PROZESS_klappentext_erzaehler.md (Projekt: claude/PROZESS_klappentext_erzaehler.md). Nach Abnahme: Stage 550 Teaser (Audio-Linie), Export 710, Katalog-Klick im Mock-up.
- s110: autor_geschlecht aus Wikidata P21; s600: meta.hauptfigur_geschlecht (Schema + Prompt). Sicherung: archive\2026-10-19_teaser\.
- Bestand: start_nachlauf_geschlecht.bat (tools\nachlauf_geschlecht.py; Wikidata + DeepSeek Flash, wenige Cent).
- Tests: start_teaser_test.bat (tools\teaser_paket.py; Modal tts_modal_opt + overlay_modal) -> <werk>\fassungen\<lg>\teaser\teaser_<lg>_<var>.wav
  Yellow Wallpaper DE w / EN w, Call of the Wild DE m_klon / DE m_vc / EN m. Lokale Schritte in der VM getestet, Modal noch nicht gelaufen.
- Runde 1 gehoert (CK 19.10.): DE maennlich = Klon herr_a ueber mix_v1 (Overlay-Variante verworfen). EN: Rauschen zwischen
  Saetzen + zu schnell; DE: englische Eigennamen deutsch betont. Runde-1-Dateien: archive\2026-10-19_teaser\runde1\.
- Runde 2 (start_teaser_test.bat): Satzraender per Pegelschwelle geschnitten, EN-Tempo 0,80, Aussprache-Lexikon angewendet.
- Aussprache aus dem Glossar: s210 fragt je Name/Begriff tts_<lg> (Lautschreibung) ab; tools\aussprache_lexikon.py baut daraus
  work\aussprache_<lg>.json (freigegeben: false bis Hoerprobe). Bestand: start_aussprache_bestand.bat.
- Runde 2 YW DE (CK): "19. Jahrhunderts" als "neunzehn" gesprochen, Silbe im 1. Satz verschluckt. Ursachen: Satztrennung nach
  "19." + kein Ordinal-Sprechtext; Randschnitt vorn (-35 dB) zu scharf. Fix: pipeline\sprechtext.py Regel 2 (Ordinalzahlen vor
  Jahrhundert/Monat/...) + Regel 3 (Jahresspanne "bis"/"to") -- gilt auch fuer die Werk-Vertonung; teaser_paket: keine Trennung nach
  Ordinalzahl, Anfang nur bei -55 dB schneiden, Batch 8 mit Pruefung im Lauf. Neu: start_teaser_nachlauf.bat (Runde 3, nur YW DE).
- OFFEN: Abnahme Runde 3 YW DE; danach Lexika freigeben, Stage 550 + Export + Mock-up.

## 18.10.2026 — Neue Nomenklatur umgesetzt (CK)
Code pipeline\sNNN_<aufgabe>.py, Checkpoints work\NNN_<aufgabe>.json; Hunderter = Phase. Uebersicht: docs\Pipeline_Strang_Matrix.xlsx (Projekt: claude/PIPELINE_strang_matrix.md).
- 26 Dateien umbenannt (z. B. stage_55_backtranslation -> s330_rueckuebersetzung, tools\00_anlegen -> tools\s100_anlegen, stage_58_3rd_prty -> schnitt_lib).
- Jede Stage-Datei traegt oben: Funktion, Wirkungsweise, Komponenten, Zulieferer, Abnehmer.
- Verweise angepasst in run.py (Stage-Schluessel jetzt 120/200/.../710), Cockpit, Bats, tools, Modal-Skripten (63 Dateien).
- run.py-Aufrufe: --to 400 (statt 56), --from 500 (statt 58), --from 600 --to 610 (statt 20/21), --from 620 --to 630 (statt 30/31).
- 665 Checkpoints in 264 work-Ordnern umbenannt, z. B. stage06.json -> 400_regie.json, stage58c_worttiming_de.json -> 520_wortzeiten_de.json.
  Ruecknahme: py archive\2026-10-18_umbenennung\umbenennung_2026-10-18.py zurueck. Code vorher: archive\2026-10-18_umbenennung\code_vorher\.
- Laeuft gerade ein Job mit altem Code, schreibt er alte Namen (stage06.json ...) -> danach "werke" des Skripts erneut laufen lassen.
- archive\2026-10-18_umbenennung\_abgebrochen_loeschbar\ (635 MB, abgebrochener erster Sicherungsversuch) kann geloescht werden.

## 18.10.2026 — LibriVox-Audio-Strang archiviert (CK)
LibriVox-Aufnahmen ersetzen keine eigene Vertonung mehr. Sicherungen: <datei>.bak_20261018_lv.
- run.py: Stage-58-Weiche ohne LibriVox-Gleis (_audio_quelle entfernt).
- stage_11_modernize: LibriVox-Modus entfernt -> immer sanfte Modernisierung.
- tools/00_anlegen: keine LibriVox-Fassung mehr beim Anlegen.
- Cockpit (server.py, index.html): LibriVox-Pruefung, LV-MP3, Audio-EN-Schnitt, LibriVox-Tor und Konflikt-Hinweis entfernt;
  Wortzeit EN gilt als offen, sobald EN-Audio vorliegt (vorher nur bei LibriVox-Werken).
- Archiv archive/2026-10-18_audit/tools_librivox/: librivox_fetch, librivox_pruefen, librivox_ernte, librivox_pd, zuruecksetzen_librivox.
- BLEIBT: tools/librivox_curate.py + start_librivox_sprecher.bat (Sprecherauswahl LoRA, daten/speakers.json);
  pipeline/stage_58_3rd_prty.py als Bibliothek (lora_modal nutzt die Schnittfunktionen); stage_30_epub Sprecher-Credit fuer bestehende LibriVox-Fassungen.

## 18.10.2026 — Quick Fixes aus Pipeline-Audit umgesetzt (QF-1 bis QF-10)
Grundlage: Projekt-Docs claude/AUDIT_pipeline_2026-10-18.md, claude/AP_audit_massnahmen_2026-10-18.md, claude/PROZESS_quellprofile.md.
Sicherungen: <datei>.bak_20261018_qf neben jeder geaenderten Datei. Getestet: Syntax + Import aller Linien-Stages, Stopp-Logik 56; KEIN Live-Lauf.
- QF-1 Stage 20: kein Gemini-Direktaufruf mehr -> api_layer, deepseek-v4-pro (profiler) fuer Metadaten + Klappentext; Quelle raw_modernized.txt.
- QF-2 run.py: cover.jpg zaehlt als Cover; --force erreicht Stage 21.
- QF-3 Stage 40: stage10.json nur bei vollstaendigen Snippets.
- QF-4 run.py: Stage 58 startet nur bei Casting-Tor "freigegeben" (sonst STOPP mit Hinweis).
- QF-5 run.py: Stage 59 aus der Audio-Linie (defekt, Neudefinition S-3).
- QF-6 Pruefstopps: 55 startet nicht bei Stage-54-Fehlern; 56 startet nicht bei > 3 % Saetzen unter Score 90 (config FLAG_MAX_ANTEIL). Bewusst weiter: $env:READLAYER_WEITER="1".
- QF-7 Stage 52: max_tokens 32000 + Warnung bei vermutlich abgeschnittener Vorübersetzung.
- QF-8 Stage 57/57b: max_tokens 16000; 57 rettet abgeschnittenes Steckbrief-JSON.
- QF-9 Stage 58 Thorsten: Code-Default 1.0 (Entscheidung 10.10.) bleibt; nur CLI-Hilfe korrigiert (zeigte 1.3).
- QF-10 archiviert nach archive/2026-10-18_audit/: pipeline/stage_modernize.py, pipeline/stage_58b_stt_validate.py, gpu_tts/tts_modal.py, alle alten *.bak*.
  Hinweis: tools/audio_cut.py (_run_58b) haengt an der alten 58b -- war schon vorher nicht lauffaehig (Signatur), kein Aufrufer.
Naechster Schritt laut AP: Git einfuehren, Smoke-Test-Werk, dann Haertung H-1 ff.

## 12.10.2026 06:30 — Nachtlauf-Ergebnis
- Alice: KOMPLETT (EN+DE je 1.529 Satz-WAVs, 24 Kapitel-WAVs, Wortzeiten EN+DE, EPUB EN+DE). 0 Fehler.
- Baskerville + As You Like It: Gemini-TTS-Tageslimit (10.000 Anfragen/Tag, Tier 2) erreicht -> tts_client fiel
  auf fal.ai zurueck, das keine designten Stimmen kennt (422). Fehlend: Baskerville EN c017/c018 teilweise + DE komplett,
  AYLI DE komplett. Zusaetzlich Baskerville 57b ab c005 abgebrochen (kaputtes JSON) -> EN c005-c018 nur Erzaehler.
- Fixes: tts_client kein fal-Ueberlauf fuer voice_-IDs; 57b wiederholt in Teilen (60/30/20 Saetze).
- start_vertonung_fortsetzen.bat wartet bis 09:05 (Limit-Reset 00:00 PT), dann 57b Baskerville, Vertonung (Cache),
  Manifeste, 58c (Baskerville EN --force). Bedarf ca. 7.500 Anfragen (< 10.000).
- Lehre: Tageslimit TTS = ca. 10.000 Saetze/Tag -> Serienplanung danach (ca. 2 Werke mittlerer Laenge EN+DE/Tag).

## 11.10.2026 20:45 — Drama-Modus gebaut + Nachtlaeufe
- Alice: Vertonung EN+DE fertig (1.529 Satz-WAVs je Sprache, 24 Kapitel-WAVs, 0 Fehler). Abschluss laeuft
  (start_alice_abschluss.bat: Manifest, 58c EN/DE, EPUB 30/31).
- Baskerville: start_baskerville_nachtlauf.bat (wartet auf Text, dann 57/57b/Vertonung/54a/58c/EPUB).
- As You Like It: start_as_you_like_it_nachtlauf.bat — NEU tools/drama_vorbereiten.py (Drama-Tor):
  stage00.json deterministisch aus raw_modernized.txt (Akte als Kapitel, Repliken mit "sprecher",
  Regie als type s/rolle regie), alte Staende in work/_vor_drama_*. 57 bekommt "NAME: text",
  57b uebernimmt Sprecher ohne KI. Rollennamen werden NIE gesprochen -> Anzeige im CC-/Mitlesefenster
  (Feature-Idee CK: Drama flüssig hoeren und sehen, wer spricht; App: Rollenname ueber Replik, Farbe je Figur).
- Offen: Drama-Erkennung automatisch im Cockpit/Stage 11 (bisher manuell per Skript); App-Anzeige sprecher.
- GEBAUT 11.10. 21:00 (ungetestet am echten Werk): stage_60 _build_manifest -> sprecher/rolle je Satz + modus;
  taella-app: loader.js (sprecher, rolle, meta.modus), Page.jsx (Block je Replik + Rollenname), neu
  components/SprecherLabel.jsx (Kapitaelchen, Farbe je Figur), Satz.jsx (satz--regie), ListenView.jsx (Name ueber
  Untertitel), App.css. Backups *.bak_20261011. Test, sobald As You Like It exportiert ist.
- AP TAELLA-App Drama-Modus: (1) Export (tools/export_demo.py, Stage 60) traegt meta.modus="drama" + je Tag
  sprecher/sprecher_de/rolle in die Manifeste; (2) Reader/CC-Fenster: Rollenname (Kapitaelchen) ueber jeder
  neuen Replik, Farbe je Figur (aus Besetzung), Regie kursiv, Akt/Szene als Zwischenueberschrift;
  (3) Figurenliste (Dramatis Personae) mit Stimme antippbar; (4) Fallback: Werke ohne modus unveraendert.

## 11.10.2026 18:00 — Laeuft / Offen
- LAEUFT: alice_komplett.bat (57b alle Kapitel + Vertonung EN/DE, Satz-WAVs in fassungen/<lang>/audio/).
- Vorbereitet: start_hoerprobe_as_you_like_it.bat (Akt II, Test ohne Rollennamen).
- NEU AP "Drama-Tor" (CK): Buehnenstuecke erkennen (book.json/Startliste: Werkart Drama; Heuristik
  Rollennamen-Zeilen, Akt/Szene, Regieanweisungen). Fuer Dramen: Stage 11 modernisiert NUR Repliktext, Rollennamen
  bleiben als Feld erhalten; Stage 50 taggt Repliken mit "sprecher" + Regieanweisung als eigener Typ; Kapitel =
  Akte (Szenen als Unterkapitel), keine Rollennamen als Kapitel. 57b uebernimmt Sprecher direkt aus dem Tag.
  Betroffen u. a.: As You Like It, Macbeth, Hamlet, Romeo and Juliet, The Tempest, Importance of Being Earnest,
  Lysistrata, Pygmalion -> nach Umbau Text neu ab Stage 11.
- Baskerville: DeepSeek 402 (Guthaben) -> nach Aufladen --from 53.
- CK 11.10.: In DE-Fassungen englische Eigennamen ENGLISCH aussprechen (Rosalind, Orlando, Touchstone ...).
  Umsetzung: Aussprache-Hinweis aus profile.characters/pronunciation (Stage 51/56) auch in der mehrstimmigen
  Vertonung (tools/hoerprobe_mehrstimmig.py setzt bisher style="") je Segment mitgeben; Profil-Prompt fuer DE:
  Namen = englische Aussprache, ausser etablierte deutsche Namensform (z. B. 'Herzkoenigin').

## 11.10.2026 16:30 — Mehrstimmige Hoerprobe Alice ABGENOMMEN (CK: "so nehmen")
- Alice Kap. 1 + 7, EN + DE: work/_hoerprobe/<lang>/c001.wav, c007.wav. Erzaehlerin grossmutter_a + 15 Figurenstimmen.
- Neu: pipeline/stage_57b_sprecher.py (Sprecher-Zuordnung je Satz, Zitat vs. Begleitsatz, EN+DE getrennt,
  Pruefung Segmente == Originaltext) -> work/sprecher.json. tools/hoerprobe_mehrstimmig.py (Segment-Cache, 4 parallel).
- CASTING_MAX_ENSEMBLE = 15. Zu aehnlich markiert: Siebenschlaefer~Maus, Taube~Herzkoenigin.
- Baskerville: Stage 53 abgebrochen mit DeepSeek 402 (Guthaben leer) -> nach Aufladen: run.py ... --from 53 --to 56.
- Naechste Schritte: Alice komplett (12 Kapitel EN+DE) mehrstimmig; Einbau in Stage 58 (1 WAV je Satz, Wortzeiten 58c).

## Arbeitspakete ab 11.10.2026 (CK)
1. LAEUFT (Start 11.10. 13:36): Text modernisiert + Uebersetzung ueber alle Werke im Cockpit (DeepSeek-Nebenzeit:
   Wochenende ganz, Mo-Fr 12:00-03:00 und 06:00-08:00 MESZ). LibriVox deaktiviert: book.json audio_quelle
   'librivox' -> 'librivox_archiv' (55 Werke, Backups book.json.bak_20261011). 8 Konflikt-Werke aus _alt_20261010
   zurueckgeholt, LibriVox-Textstand in work/_librivox_20261011/. Cockpit: 6 DeepSeek-Plaetze, Audio DE (Thorsten)
   pausiert (SCHRITTE_PAUSIERT), Backup cockpit/server.py.bak_20261011. Kosten bisher ~0,09 $ je 1000 Woerter
   (Text 11-56); 237 Werke / 26,7 Mio. Woerter offen.
2. Aufraeumen: alles ausserhalb Core-Produktion aus dem Projektordner (verschieben, nicht loeschen).
3. Musterwerke mit designten Stimmen + Mehrstimmigkeit vertonen (vorher: Sprecher-Zuordnung je Dialogsatz,
   Hoerprobe der 8 Alice-Kandidaten).
4. Cover-Labels als Overlay: TEXT bzw. TEXT & AUDIO DE/EN, tauschbar sobald Audio nachproduziert.
5. Fertige Werke nach Freigabe hochladen + Kopie in Mock-Up-Ordner.

## Stand 11.10.2026 — Stimmen-Archiv + Stage 57 Casting (gebaut)
- Entscheidung: Produktion ueber Gemini 3.8 Flash TTS (Interactions-API) mit designten Stimmen; Chatterbox auf CPU
  zu langsam (~25x Echtzeit). Designstimmen gehen NICHT ueber generateContent/Batch -> Standardpreis
  (~0,81 $/Hoerstunde 2026, ab 2027 doppelt). 3 Premium-Werke DE+EN ~24 $.
- Stimmen-Archiv `stimmen_archiv/` (Register `stimmen.json`, je Stimme Ordner mit hoerprobe/muster_en/muster_de/
  steckbrief.json). Erzaehler: grossmutter_a (Maerchen), herr_a (Krimi/Abenteuer), herr_b (grosse Werke).
  Alter Ordner `_stimmen` ist Kopie-Quelle und kann geloescht werden.
- Framework `pipeline/voice_registry.py`: Merkmal-Schema, Passung (0-100, Schwelle 70), Ensemble-Sperre
  (eine Stimme = eine Rolle je Werk), Unterscheidbarkeit (Merkmale + gemessener Grundton, min. 12 %),
  Design-Prompt mit Abgrenzung zum Ensemble, Kinderfiguren = erwachsene Sprecherin (Gemini blockt Kinderstimmen).
- `pipeline/stage_57_casting.py` (run.py AUDIO_LINE zwischen 56 und 58; nur aktiv bei book.json
  besetzung_modus oder config.CASTING_AKTIV). Ausgabe `work/casting.json`; `--design` designt fehlende Stimmen;
  `--freigeben` schreibt audio_voice + besetzung in book.json. Config-Block CASTING_* in config.py.
- Test Alice (Quelle _alt_20261010/work/stage06.json): 34 Figuren, Erzaehler grossmutter_a, 8 neue Figurenstimmen
  (Kandidaten). Tor offen -> Hoerprobe durch CK.
- Backups: config.py/run.py/PROJEKTSTAND.md .bak_20261011, Alice book.json.bak_20261011.

## Offen (Casting)
1. CK hoert die 8 Alice-Kandidaten (stimmen_archiv/<name>/muster_*.wav) -> freigeben/ablehnen.
2. CASTING_MAX_ENSEMBLE fuer Alice zu klein (8): Raupe, Grinsekatze, Maerzhase, Maus sprechen als Statisten.
3. Sprecher-Zuordnung je Dialogsatz (wer spricht welches Zitat, Zitat vs. Begleitsatz trennen) fehlt noch;
   bis dahin nutzt Stage 58 nur den Erzaehler (book.json audio_voice).
4. Plausibilitaet Grundton vs. Merkmal (z. B. Mock Turtle 'tief' gemessen 182 Hz) als Pruefung ergaenzen.

## Stand 10.10.2026 — Arbeitspaket Cockpit v1 (gebaut)
- Start: `cockpit_start.bat` (Doppelklick) -> http://127.0.0.1:8765. Nur Standardbibliothek, laeuft mit py -3.11.
- Dateien: `cockpit/server.py`, `cockpit/index.html`, `cockpit/startliste.json` (aus ReadLayer_Start_List_priorisiert.xlsx),
  Freigaben in `daten/freigaben.json`, Logs in `cockpit/logs/`.
- Ablauf je Werk: PD-Tor -> Anlegen -> Text (run.py audio --to 56) -> Uebersetzungs-Tor -> Klappentext+Cover (epub 20-21)
  -> Cover-Tor -> Audio DE (58, lang de) -> Audio-Tor -> Export EPUB (epub 30-31) -> Export-Tor. LibriVox-Tor nicht blockierend.
- Lauf: markierte Werke nacheinander bis zum naechsten offenen Tor; Option "nur Nebenzeit" fuer DeepSeek-Schritte.
- Schutz: Werke mit Gemini-Teilvertonung (Jekyll) werden NICHT automatisch mit Thorsten ergaenzt.
- Pipeline-Aenderung: `config.TTS_ENGINE_DE = "thorsten"`; run.py-Weiche Stage 58 -> stage_58_local_tts fuer DE ohne LibriVox.
  Backups: run.py.bak_20261010, config/config.py.bak_20261010.
- Testordner `cockpit/_test` kann geloescht werden.
- NEU: Schritt "Demo-Ordner" nach dem Export-Tor: `tools/export_demo.py <slug> [demo-ordner] [--audio]`
  -> `taella-app/public/demo/<slug>/` (Manifeste, Cover, Klappentext, Wortzeiten) + `demo/katalog.json`.
  Ohne Audio (Default; Hoerbuch ~1 GB). Upload in den Bucket (Stage 60) bewusst NICHT im Cockpit.

- NEU Token-/Kostenzaehler: `pipeline/usage_log.py`; jeder API-Aufruf (api_layer DeepSeek+Gemini, Stage 20 Klappentext,
  Stage 21 Cover, tts_client Gemini-TTS) schreibt `work/kosten.jsonl` (Stage, Modell, Token ein/Cache/aus, USD-Schaetzung).
  Preise in `config.PREISE` (Gemini-Preise pruefen). Auswertung: `py -3.11 -m pipeline.usage_log <book_id>`.
  Cockpit-Spalte "Kosten" (Tooltip je Stage). Backups *.bak_20261010.

- NEU Cockpit parallel (16:20): 5 Bahnen (Anlegen, Text/DeepSeek, Klappentext+Cover/Gemini, Audio/Thorsten, Export+Demo),
  je Bahn ein Job, je Werk ein Schritt zur Zeit, kuerzeste Werke zuerst. Auftraege in `daten/auftraege.json`
  (uebersteht Neustart). Nebenzeit-Sperre nur noch fuer Text. Backup: cockpit/*.bak_20261010_v1.

- NEU LibriVox-Pruefung (17:50): Cockpit-Schritt "librivox" nach Anlegen, VOR Text (`tools/librivox_pruefen.py`).
  Treffer in daten/werke_gruen.csv (Solo, Englisch, Sprecher-Urteil gut>mit, nie raus) -> raw.txt = Quelltext der
  Aufnahme, book.json Fassung en audio_quelle=librivox -> Stage 11 laesst EN wortgetreu. Kein Treffer -> "keine".
  Text schon verarbeitet + Treffer -> "konflikt" (Cockpit zeigt es). Betroffen: Frankenstein, Earnest, Alice,
  Call of Cthulhu (uebersetzt), Happy Prince (modernisiert). 58 von 262 Startlisten-Werken haben einen Treffer.
  MP3-Download (librivox_fetch) noch kein Cockpit-Schritt.

## Offen / naechste Schritte
1. Erster echter Lauf: The Cask of Amontillado (PD freigeben, Lauf starten).
2. Thorsten-Tempo pruefen: stage_58_local_tts DEFAULT_LENGTH_SCALE = 1.3 (fuer Upps gedehnt) — fuer Hoerbuch evtl. 1.0.
3. Wikidata (Stage 01, propose/confirm) ist noch manuell, nicht im Cockpit.
4. Noch nicht im Cockpit: LibriVox-Import (tools/librivox_*), TAELLA-Paket (Stage 60 / export_app), "Neu erzeugen" nach Ablehnung.
5. Startliste korrigieren: Grimms' Fairy Tales = Uebersetzung (Uebersetzer-Todesjahr); Importance of Being Earnest = Drama.
6. DeepSeek: Uebersetzer-Modell deepseek-v4-pro vs. deepseek-flash an einem Kapitel vergleichen (Kosten/Qualitaet).
7. Kartoffelbox (MIT) als TTS_ENGINE_DE einrichten, sobald GPU-Weg entschieden.

# Arbeitspaket: Read-Layer-Cockpit (lokal) — Startplan

Stand: 10.10.2026. Fuer PROJEKTSTAND.md; Umsetzung in neuer Sitzung.

## Ziel
Lokales HTML-Frontend um die bestehende Pipeline (`run.py`): ein Knopf pro Werk produziert alles,
Kontrolltore halten den Lauf an, Freigaben im Stapel. Spaeter Basis fuer das Verlagsportal.

## Rahmen (entschieden)
- Alles lokal (C:\Users\sabin\read_layer\), FastAPI-Server + eine HTML-Seite.
- DE-Stimme Default: Thorsten. TTS-Engine als Eintrag in config.py (`TTS_ENGINE_DE`),
  damit Kartoffelbox (MIT, Chatterbox-Finetune) spaeter nur umgeschaltet wird.
- EN-Audio: LibriVox, aligned auf EN-Text.
- Standards (EPUB-Accessibility, Ace, Media Overlays) zurueckgestellt, stueckweise aufruesten.
  Jetzt nur Platzhalter: Satz-IDs + Audio-Zeiten aufheben, Feld `cover_alt` in book.json.

## Textmodell (DeepSeek, Stand 10.10.2026)
- config.py MODELS["translator"] von "deepseek-chat" auf "deepseek-flash" (V4.1-Flash) umstellen;
  vorher Testaufruf, ob "deepseek-chat" noch antwortet.
- Denkmodus AUS fuer Batch-Stages (Default ist an -> bezahlte Output-Token).
- Batch-Laeufe nur in Nebenzeit (halber Preis): werktags NICHT 03-06 und 08-12 Uhr Berlin (Sommerzeit),
  Wochenende ganztaegig. Im Cockpit als Zeitfenster-Sperre fuer den Batch-Start.
- Statischen Stil-/Epochen-Vorspann an den Prompt-Anfang -> Cache-Treffer ($0.003/1M).
- Grobe Kosten Textkette fuer 187 Werke: ~60-80 USD.

## Ablauf pro Werk (ein Lauf)
| # | Schritt | Tor (Freigabe, im Stapel moeglich) |
|---|---|---|
| 0 | PD-Pruefung (Autor bzw. Quell-Uebersetzer +70) | Tor 0: PD ok |
| 1 | Anlegen + Wikidata (08b) | — |
| 2 | Modernisieren, Uebersetzen, Rueckuebersetzung | Tor 1: Uebersetzung (Score-Liste, Auffaellige einzeln) |
| 3 | Klappentext + Cover | Tor 2: Cover + Klappentext + sicherheit-Flag (Raster) |
| 4 | LibriVox-Import + Alignment EN | Tor 3: Fassung passt zum Text? Stichproben Schnitt |
| 5 | Vertonung DE (Thorsten) + STT-Pruefung | Tor 4: Ausreisser + Stichproben anhoeren |
| 6 | Export EPUB + TAELLA-Paket (epubcheck) | Tor 5: Exportpruefung |

Ein offenes Tor blockiert nur dieses Werk; andere laufen weiter.

## Cockpit-Ansichten
1. Katalog: Werke x Schritte, Status je Zelle (Status-Scanner aus Ordnerstruktur).
2. Warteschlange: Werke waehlen, Reihenfolge, Fortschritt.
3. Torseiten (je Tor eine Sammelansicht): alle markieren, Ausreisser abwaehlen, freigeben;
   Ablehnung mit Notiz -> Schritt neu.
4. Export.

## Produktionsliste (aus ReadLayer_Start_List_priorisiert.xlsx)
262 Werke gesamt. Produktionsreif = Ampel nicht rot, keine Uebersetzung, PD ok: **187 Werke,
~18,6 Mio. Woerter** (grob 2.000 h DE-Audio).
Pruefen vor Lauf: "Grimms' Fairy Tales" ist als Nicht-Uebersetzung markiert, ist aber eine
engl. Uebersetzung (Uebersetzer-Todesjahr klaeren). "Importance of Being Earnest" ist ein
Drama, trotz Ampel gruen -> Nacherzaehl-Linie.

### Batch 1 (kurz, Prio-Reihenfolge, <40k Woerter)
| Prio | Gutenberg-ID | Titel | Woerter |
|---|---|---|---|
| 1 | 1952 | The Yellow Wallpaper | 6.085 |
| 4 | 11 | Alice's Adventures in Wonderland | 26.525 |
| 5 | 43 | Dr. Jekyll and Mr. Hyde (teilweise produziert) | 25.631 |
| 6 | 215 | The Call of the Wild (Testdatensatz, weit produziert) | 31.824 |
| 9 | 921 | De Profundis | 17.753 |
| 16 | 35 | The Time Machine | 32.453 |
| 18 | 55 | The Wonderful Wizard of Oz | 39.649 |
| 19 | 1063 | The Cask of Amontillado | 2.329 |
| 22 | 41 | The Legend of Sleepy Hollow | 12.214 |
| 23 | 551 | The Land That Time Forgot | 37.215 |

Empfehlung: zuerst Cask of Amontillado + Yellow Wallpaper als Durchstich (klein, billig),
dann Rest von Batch 1.

## Schritte fuer die naechste Sitzung
1. Bestand sichten: run.py, Stage-Liste, Ordnerstruktur, vorhandene Status-Daten.
2. Status-Scanner (liest Ordner -> Status je Werk/Schritt) als Kern.
3. FastAPI-Server: Endpunkte Katalog, Lauf starten, Tor freigeben/ablehnen.
4. HTML-Seite Katalog + eine Torseite (Cover) als erster Durchstich.
5. Durchstich mit Cask of Amontillado.

## 10.10.2026 abends — Cockpit: LibriVox-Spur + Wortzeiten, DeepSeek x3
- LibriVox-Konflikte zurueckgesetzt (8 Werke, Altstand in <buch>/_alt_20261010/, Cover+Klappentext behalten).
- DeepSeek-Bahn mit 3 Plaetzen (SLOTS in cockpit/server.py), kuerzeste Werke zuerst.
- Neue Cockpit-Schritte:
  - lv_audio (netz): tools/librivox_fetch.py -> fassungen/en/source_audio
  - audio_en (align): run.py --from 58 --to 58 --lang en -> stage_58_3rd_prty (STT, Abgleich, Schnitt); fertig ab 90 % der Saetze
  - woerter (deepseek): stage_54a_alignment (Wortanker EN<->DE)
  - wortzeit_en / wortzeit_de (align): stage_58c_worttiming (Forced Alignment MMS_FA)
  - demo wartet jetzt auf Wortzeiten DE + EN
- Befund: 54a/58c liefen bisher nur bei Call of the Wild -> allen anderen Werken fehlten die Wortzeiten.
- Backups: cockpit/server.py.bak_20261010_v6 (vor DeepSeek x3), _v7 (vor LibriVox-Spur).
- Cover mit Typografie je Sprache: stage_30_epub.py schreibt jetzt fassungen/<lang>/output/cover_final_<lang>.jpg
  (Titel in der Sprache, Autor, Sprachlabel, Sprecherzeile "Read by <LibriVox-Sprecher>" / "Gelesen von Thorsten · KI-Stimme", Verlag).
  Backup stage_30_epub.py.bak_20261010_cover.
- Neuer Cockpit-Schritt "titel" (netz): tools/titel_auto.py -> Wikidata-Werk automatisch waehlen (Film/Oper raus),
  Laendertitel uebernehmen; sonst Uebersetzer-Fallback mit titel_pruefen=true (am Cover-Tor sichtbar). Netzfehler = Schritt scheitert.
  Export wartet auf "titel". Backups server.py.bak_20261010_v8, index.html.bak_20261010_v2.
- Bereits exportierte Werke bekommen neue Cover erst nach erneutem Export (30/31).
- Fixes nach erstem Lauf (21:55):
  - stage_58_3rd_prty: STROM-MODUS, wenn LibriVox-Abschnitte != Kapitel (Abgleich ueber das ganze Buch mit Zeiger). Backup .bak_20261010.
  - librivox_fetch schreibt source_audio/_vollstaendig.json; Cockpit wertet LV-Download erst damit als fertig (wirkt nach Neustart).
  - titel_auto: Suchvarianten (ohne Zusatz nach Komma), keine Treffer = Fallback statt Fehler, DE == englischer Originaltitel -> Vorschlag + pruefen.

## NAECHSTES ARBEITSPAKET (ab 11.10.2026): Grosser Kundendienst
Siehe Projekt-Dokument claude/AP_grosser_kundendienst.md:
1. Produktionsschritte einzeln definieren (Eingabe/Ausgabe/Fertig-Kriterium/Tor)
2. read_layer aufraeumen (Test-Muell verschieben, nicht loeschen)
3. Freie TTS-Modelle testen: Qualitaet, Umgebung, Steuerbarkeit der Modulation, Wort-Zeitstempel ja/nein
4. Erst danach Serienlauf

## 12.10.2026 — Freigabe-Tor fuer Stimmen (CK)
- Regel: inventory first (Archiv vor Neudesign, besteht seit Stage 57). Neue/ungepruefte Stimmen werden NICHT mehr ohne CK-Freigabe voll vertont.
- Ablauf: 57 Casting -> 57b Sprecher -> `tools/stimmen_probe.py <book>` (je Figur ein typischer Satzteil EN+DE aus dem Skript, Ordner work/_stimmen_probe/ + liste.txt, Kopie ins Stimmen-Archiv)
  -> CK hoert -> ok: `py -3.11 -m pipeline.stage_57_casting <book> --freigeben` | nein: `tools/stimme_neu_designen.py <book> "<Figur>" --notiz "tiefere Stimme"` (Notiz mit Vorrang im Design-Prompt; alte Stimme abgelehnt + Notiz) -> neue Probe.
- Probe-Saetze liegen im Segment-Cache (gleicher Schluessel) -> werden bei der Vertonung recycelt.
- `hoerprobe_mehrstimmig.py` stoppt ohne Freigabe (Exit 2); Ausnahme `--ohne-freigabe` oder book.json `stimmen_freigabe`. Alice, Baskerville, AYLI: `stimmen_freigabe` = nachtraeglich.
- Offen: Stimmen der 3 Musterwerke (27 Kandidaten) nachtraeglich per Probe/Freigabe pruefen.

## 12.10.2026 — Kosten: Gemini nur noch Bild + TTS (CK)
- Analyse 11./12.10.: Kostenfalle = Stage 55 Validator gemini-2.5-flash (45,85 $; 17,5 Mio. Ausgabe-Token, fast nur Denk-Token). Danach caster/57b gemini-2.5-pro (14,87 $).
- Umgestellt (config.MODELS): tagger, validator, ssml -> deepseek-v4-flash; profiler (+caster/57b) -> deepseek-v4-pro. Gemini bleibt fuer TTS, Voice Design, Cover.
- DEEPSEEK_MAX_OUT = 16000 (api_layer kappt max_tokens); 57b fragt in Teilen zu 40 Saetzen.
- TTS-Kosten werden jetzt geloggt (Token aus Audiolaenge, 25/s); Preis gemini-3.8-flash-tts 0,50/9,00 $ je Mio. (bis 31.12.2026, dann doppelt) = ca. 0,81 $ je Audiostunde.
- Backups: *.bak_20261012 / *.bak_20261012b. Erster DeepSeek-Lauf fuer tagger/profiler beim naechsten Werk pruefen (Qualitaet, JSON).

## 12.10.2026 — Hauptordner aufgeraeumt
- Einmal-/Test-Skripte, alte .bat, Logs, _stimmen, _stimmen_test, _tempo_test, _tmp_cover_test, "LibriVox Source" -> archive/2026-10-12_aufraeumen/ (bat, py, logs, ordner, sonstiges). Prozesslandkarte -> docs/.
- Im Hauptordner bleiben nur: Pipeline-Ordner, run.py, cockpit_start.bat, PROJEKTSTAND.md, README.md, new_books.json (Anlege-Vorlage) und die gerade laufenden start_*.bat mit ihren Logs (nach Abschluss ebenfalls ins Archiv).
- Offene Punkte (Merkliste): Referenz-Export je Stimme (10-30 s EN/DE aus Segment-Cache, fuer Chatterbox/Fine-Tuning); eigene GPU + lokales TTS (Training nur mit freigegebenem eigenem Material); Google-Nutzungsbedingungen pruefen; Modellvergleich OpenRouter (Kimi K3, Qwen, MiniMax). 57b DeepSeek v4 Pro vs. Gemini Pro: 93 % EN / 91 % DE Uebereinstimmung -> DeepSeek bleibt.

## 12.10.2026 — Kuratormodus im Mock-Up (Testumgebung) — Teil 1 gebaut
- Einstellungen -> "Kuratormodus (Testumgebung)". Lesen: Satz lang druecken; Hoeren: Stift-Taste (pausiert) -> Anmerkung (Kategorie Sprecher/Aussprache/Uebersetzung/Text/Audio/Wortzeit/Sonstiges, Notiz, ggf. richtiger Sprecher).
- Ablage: Vite-Dev-Server (taella-app/vite.config.js, /api/kuration) schreibt in read_layer/authors/<autor>/books/<slug>/work/kuration.jsonl (status "offen"). Ohne Server Fallback localStorage.
- Markierung im Lesen: notierte Saetze punktiert unterstrichen, unsichere Sprecher (sprecher.json "pruefen") leicht hinterlegt.
- 57b meldet Unsicherheiten ("u": 1) -> sprecher.json "pruefen" + work/sprecher_pruefen.txt.
- Offen Teil 2: Ruecklauf-Werkzeug (kuration.jsonl abarbeiten: Sprecher-Korrektur -> sprecher.json -> nur betroffene Saetze neu vertonen -> 58c -> export_demo; Text/Uebersetzung als Aufgabenliste). Idee CK: spaeter Lektorat durch Nutzer gegen Plattform-Credits.

## 12.10.2026 — Entscheidungen Nachmittag (CK)
- Modellvergleich 57b (Baskerville c006+c011, Referenz Gemini 2.5 Pro): Kimi K3 96/96 % (0 Rueckfaelle, ~7 $/Roman), DeepSeek v4 Pro 93/91 % (~1 $/Roman), MiniMax M3 66/77 %, Qwen 3.5 Plus 35/38 % (JSON-Probleme). -> DeepSeek bleibt Standard; Kimi als Option fuer Flaggschiff-Titel. Offen: Rueckfaelle automatisch in kleinen Paketen wiederholen.
- Kuenftiger Standard Mehrstimmigkeit: BASIS = Erzaehler vertont jeden Satz komplett (Einzelstimmen-Fassung); SCHICHT = Figurenstimmen nur fuer Zitate, Montage per Wortzeiten (Zitat-Spanne im Erzaehler-Satz ersetzen) -> keine Fetzen wie ", sagte Alice". App-Umschalter "eine Stimme / Hoerspiel".
- Pricing: Hoerspiel-Schicht = eigene Preisstufe; Mehraufwand je Werk getrennt ausweisen (Kostenlog nach Schicht: Basis-TTS vs. Casting/57b/Zitat-TTS/Stimmendesign/Lektorat).
- Alice bleibt wie vertont; Fehler per Kuratormodus satzweise.
- Community-Lektorat als Produktbaustein: Mehrfachbestaetigung, Ruf je Nutzer, Credits nur fuer angenommene Korrekturen, CK entscheidet nur Regeln/Streitfaelle.
- Hoerspiel-Schicht technisch: Erzaehler-Basis in 8-Satz-Paketen (stabile Sprache/Prosodie, 1/8 der Anfragen -> Tageslimit reicht fuer ~8x mehr), Schnitt per Wortzeiten. Zitate: Regie aus Begleitsatz ("erwiderte sie schuechtern" -> style) von 57b mitliefern; kurze Zitate mit Kontext (Satz davor/danach) vertonen und per Wortzeiten schneiden. Sprache festigen: TTS_SPRACH_STIL (config) seit 12.10. aktiv; Idee: lokale Spracherkennung je Satz-Audio als Pruefung.
- Pricing (CK): Hoerspiel-Schicht = Pro+ Upgrade; zusaetzlich Auftrags-Hoerspiel (Nutzer beauftragt + bezahlt Produktion, Kostenvoranschlag aus Wortzahl/Dialoganteil/Kostenlog, Nennung als Stifter, danach fuer Pro+ verfuegbar). Dramen = staerkstes Zugpferd (Sprecher im Text, keine Zuordnungskosten).
- Geschaeftsmodell (CK 12.10. Nachmittag): Produktionskosten sind einmalig je Werk (Basis ~5-8 $ Text, ~20-25 $ Audio EN+DE). Produkttreppe: Lesen (alle Werke) -> Vorlesen mit lokaler Standardstimme (alle Werke, ~kostenlos) -> Hoerbuch (designte Erzaehlerstimme, gefragte Titel) -> Hoerspiel (Premium, Dramen zuerst). App-UX = Einmalaufwand mit Wirkung auf ganzen Katalog -> wichtigster Hebel.
- PATENSCHAFT statt Jahresabo (CK): Kunde finanziert Werk/Schicht (Lese-/Hoerbuch-/Hoerspiel-Pate), Nennung als Pate im Werk, 12 Monate Katalogzugang OHNE automatische Verlaengerung; Verlaengerung = naechste Patenschaft. Mehrere Paten je Werk moeglich. Groessenordnung ~50 EUR. Verlagstitel brauchen eigenes Modell (Lizenz an Verlag/Autor; z. B. Einzelkauf/Credits) - klaeren bei erster Verlagsanfrage.
- Abgrenzung: Mehrwert = Schicht (Modernisierung, satzgenaue Uebersetzung, Upps, Wort-Mitlesen, Hoerspiel, Lernspur), nicht der PD-Text. Wettbewerb eher Lern-Apps (z. B. Beelinguapp) -> Wettbewerbsanalyse offen. Ertragsmodell (taella_ertragsmodell.xlsx) mit diesen Zahlen aktualisieren - offen.
- PREISSTRUKTUR (CK-Entwurf 12.10.2026, Waehrung noch $ -> fuer DE in EUR auszeichnen):
  - Patenschaft Hoerbuch 59,99 (Wunschtitel als Hoerbuch produziert + 1 Jahr Hoerbuch-Layer, ohne Hoerspiel/Theater-Modus); Patenschaft Hoerspiel 74,99 (Wunschtitel als Hoerspiel + 1 Jahr Vollzugang). Keine automatische Verlaengerung.
  - Freemium: alle Texttitel + Hoerbuch-Muster (1-2 pro Monat wechselnd).
  - Hoerbuch-Zugang: 5,99/Monat oder 59,99/Jahr. Vollzugang inkl. Hoerspiel + Theater-Modus: 7,99/Monat oder 79,99/Jahr.
  - Offen festzulegen: Umfangsdeckel je Patenschaft (z. B. 15 h Audio/Sprache, darueber Aufpreis/mehrere Paten), Produktionsfrist (z. B. 2-4 Wochen), Verkauf ueber taella.io (Stripe ~3 %) statt In-App.
- Regel Startdateien (CK 12.10.): jede start_*.bat setzt "title READ LAYER - <Job>", damit die CMD-Fenster erkennbar sind. Laufenden Job beenden ohne Fenstersuche: seine .bat verschieben -> cmd bricht beim naechsten Zeilenlesen ab.

## 12.10.2026 abends — GPU-Test lokales TTS (Modal, L4) — Sleepy Hollow, 40 Saetze je Sprache, Klon herr_a
- Einrichtung: start_modal_einrichten.bat (einmalig), start_gpu_test.bat -> gpu_test_sleepy/ergebnis/ (Paket gpu_test_sleepy/: gpu_test.py, modal_test.py, ref_en/de.wav, saetze.json). Modal: 30 $ Freiguthaben/Monat, L4 ~0,80 $/h, Test ~0,35 $.
- Tempo: Chatterbox EN 1,04x, Kartoffelbox DE 0,97x, Chatterbox Multilingual DE 1,15x Echtzeit (=> ~1 GPU-h je Audio-h).
- CK-Urteil (vorlaeufig): Multilingual DE besser als Kartoffelbox. Qualitaet gut, Sprachmelodie nicht ganz auf Gemini-Niveau -> Budget-Stufe "Vorlesen" (alle Werke) auf eigener GPU/Modal; Gemini bleibt Premium (Hoerbuch/Hoerspiel).
- Offen: zweiter Kurztest mit exaggeration/cfg_weight-Varianten + laengerer Referenz (~60 s); spaeter Feinabstimmung auf eigenem freigegebenem Material.
- Befund: Baskerville wurde mit m_mittel_mittel_ruhig_3 statt herr_a erzaehlt (Casting hat book.json erzaehler_stimme uebergangen) -> Casting-Bug pruefen; CK hoert Erzaehler im Mock-Up.

## 13.10.2026 03:30 — Musterwerke komplett im Mock-Up (verifiziert)
- Alice: Audio 1529/1529 EN+DE, Wortzeiten 1529/1529. Baskerville: 3825/3825, Wortzeiten 3825/3825 (Erzaehler m_mittel_mittel_ruhig_3 statt herr_a!). Wie es euch gefaellt: 2483/2483, Wortzeiten 2459/2459 (24 Verse ohne Hervorhebung).
- Katalog Mock-Up: 13 Werke. Alle Lauf-.bat/-Logs ins archive/2026-10-12_aufraeumen/ verschoben. Hauptordner: start_modal_einrichten.bat, start_gpu_test.bat (GPU-Test), Pipeline.
- Naechste Arbeitspakete: Kuratormodus Teil 2 (Ruecklauf), Casting-Bug erzaehler_stimme, Hoerspiel-Schicht (Basis + Zitate), 57b-Rueckfaelle automatisch wiederholen, Ertragsmodell/Patenschaften.

## 13.10.2026 03:40 — CK hoert Baskerville: Befunde + Learnings
- Befunde: (a) DE kippt oft ins Englische (vor TTS_SPRACH_STIL vertont; "X pronounced as in English" faerbt ganze Saetze mit Mr./Sir/Dr.). (b) Dr. Mortimer = Archivstimme m_mittel_hoch_nervoes aus Alice, 232 Hz (Frauenlage), schwankt; Barrymore "alt tief" misst 182 Hz; Holmes = m_mittel_mittel_albern (Alice). (c) Kontext/Betonung der Figuren schwach. Erzaehler = Watson-Stimme (Ich-Erzaehler) - logisch, kein Bug.
- Reparaturpaket Baskerville: lokale Spracherkennung je DE-Satz -> gekippte Saetze neu (mit TTS_SPRACH_STIL); Mortimer (+Barrymore pruefen) neu besetzen + deren Saetze neu.
- LEARNINGS (CK): 1) Hoerprobe vor jeder Vollvertonung - auch fuer Archivstimmen im neuen Werk; vorher automatische Plausibilitaet (F0 vs. Geschlecht/Alter/tonlage, Genre-Herkunft). 2) Zurueck zu 8-Satz-Paketen fuer die Basis. 3) Woertliche Rede als Overlay mit Kontext - bevorzugt Betonung aus dem Einzelstimmen-Lauf uebernehmen: Voice Conversion (Chatterbox VC) Erzaehler-Zitat -> Figurenklang, Montage per Wortzeiten. Naechster Modal-Test: VC mit Baskerville-Zitaten.
- ZIELBILD HOERSPIEL-SCHICHT (CK 13.10. nachts): 1) Gemini spricht die Einzelstimmen-Fassung (Erzaehler inkl. Zitate) in Paketen mit voller Regie (DeepSeek Stufe 56: Stimmung/Staerke/Tempo/Schluesselwoerter je Satz/Zitat, < 1 $/Werk). 2) Chatterbox Voice Conversion wandelt NUR die Zitat-Spannen in die Figurenstimme (Ziel = Gemini-Hoerprobe der designten Figur). 3) Montage per Wortzeiten. -> Gemini vertont jeden Satz nur einmal, Figuren nur einmal designt, VC laeuft auf Modal/GPU ohne Tageslimit. Chatterbox-Pakete nach Dauer (~25 s, Grenze ~35-40 s), ueberlange Saetze an ;/, teilen. Chatterbox-Steuerung nur ueber Referenz-Audio (Bibliothek je Stimmung) + exaggeration/cfg_weight, keine Textanweisungen.

## 14.10.2026 — Sprechernamen-Design (Drama-Modus) gebaut
- Name zentriert ueber Replik/Untertitel (Hoeren: 24 px, Kapitaelchen). Farbe je Figur fuer Name UND Text: Erzaehler/Regie = Schriftfarbe (weiss nachts), Frauen Rottoene (Rose..Weinrot), Maenner Blautoene (Hellblau..Marine), unbekannt grau; Nuance je Figur stabil aus dem Namen; Helligkeit je Theme (--sp-l).
- Geschlecht: stage_60 _sprecher_geschlecht() aus casting.json -> Manifest "sprecher_geschlecht"; App: loader -> setSprecherGeschlecht. AYLI-Demo-Manifeste direkt ergaenzt.
- Nachtnotizen 13.10.: AYLI kippt bei kurzen Sequenzen ebenfalls ins EN/FR -> bestaetigt Einzelstimmen-Basis in Paketen + Overlay. Android-Testversion (Capacitor, APK am Store vorbei) + Cloud-Audio (GCS-Bucket) als Arbeitspaket vorgemerkt.

## 14.10.2026 — Stimmen-Klaviatur + Rechtslage Klonen
- Artifact "TÆLLA Stimmen-Klaviatur" (claude.ai) zeigt alle 36 Archivstimmen (Geschlecht, Grundton, Merkmale, Einsatz Werk/Figur, Status, Hoerprobe DE/EN, Plausibilitaets-Warnung). Archivstimmen haben jetzt englische Rufnamen (stimmen.json Feld "rufname", z. B. herr_a=Arthur, grossmutter_a=Margaret, Watson-Stimme=George, Mortimer-Stimme=Nigel); Systemschluessel unveraendert. Bauskript im Claude-Scratchpad (bau.py/vorlage.html), Daten: stimmen_archiv/_dashboard_daten.json.
- Gemini-Standardstimmen (30, Systemnamen): start_gemini_standardstimmen.bat -> stimmen_archiv/_gemini_standard/ (Hoerproben + Grundton) -> danach in Klaviatur ergaenzen. OFFEN: CK startet die .bat.
- Rechtslage (Gemini API Terms, gueltig ab 23.03.2026): Ausgaben gehoeren uns; verboten: Dienste zur Entwicklung konkurrierender Modelle nutzen, Bestandteile/Modelle extrahieren oder nachbilden. ENTSCHEIDUNG: Gemini-Standardstimmen nur fuer Vertonung bei Gemini, NICHT als Klon-/VC-Vorlage und nicht per Prompt nachbilden. Als Chatterbox-Referenz nur eigene, nach Merkmalen entworfene Stimmen; kein Fine-Tuning auf Gemini-Ausgaben. Vor produktiver Stimmumwandlung juristische Pruefung (IT-Recht).

## 14.10.2026 – Stage 57b Kosten-Hebel (Vorfilter)
- 57b schickt nur noch Absaetze mit Rede-Spur (Anfuehrungszeichen EN/DE, offenes Zitat, Typ dl/qt) + je 1 Nachbarsatz. Abschalten: env READLAYER_57B_ALLE=1. Backup .bak_20261014.
- Rueckpruefung gegen bestehende Zuordnungen: Alice 0 verpasst, Baskerville 1 von ~2.550 (Stapleton), Ruf der Wildnis 0. 124 "Watson"-Saetze = Ich-Erzaehler/Briefe, keine Rede.
- Ersparnis: Ruf der Wildnis ~65 %, Alice ~5 %, Baskerville ~12 % (dialoglastige Werke sparen wenig).
- Kosten von 57/57b werden nicht in kosten.jsonl erfasst (Buchkontext fehlt) -> offen.

## 14.10.2026 – Ruf der Wildnis: Kontrollansicht + Overlay-Test vorbereitet
- Kontrollansicht: work/Kontrollansicht_de.docx (tools/kontrollansicht_docx.py). 13 unsichere 57b-Stellen von CK bestaetigt (sprecher.json "bestaetigt").
- Besetzung CK: François=Hugo, Perrault=Malcolm, Mercedes=Sophie, Mann im roten Pullover=Bernard (Archiv, werkuebergreifend). Bernard hat in 57b keine Zeilen.
- Overlay-Test: tools/overlay_vorbereiten.py -> gpu_overlay/call-of-the-wild_de (77 Spannen, 5 Figuren). GPU: gpu_overlay/overlay_modal.py + overlay_gpu.py (Chatterbox VC + Multilingual DE, L4). Montage: tools/overlay_montage.py (per Identitaetstest geprueft).
- Ablage: fassungen/de/audio_overlay/{vc,tts,spannen,hoerliste.txt}; fassungen/de/audio bleibt unberuehrt.
- Start: start_overlay_test.bat (Log _overlay_test.log).

## 14.10.2026 – Ergebnis Overlay-Test Ruf der Wildnis (CK gehoert)
- Variante A (Chatterbox VC ueber Gemini-Basis) funktioniert am besten -> Standardweg fuer die Hoerspiel-Schicht.
- Variante B (Chatterbox Multilingual neu gesprochen) traegt nicht -> verworfen.
- Problem: Figurenstimme zu nah am Erzaehler -> kaum hoerbarer Unterschied. Erzaehler Arthur 91 Hz, Thornton=Walter 88 Hz, Perrault=Malcolm 90 Hz.
- Regel fuer Casting (umzusetzen): Mindestabstand Figurenstimme zu Erzaehler (Grundton und Klang); Klaviatur-Warnung dafuer.
- Kosten Modal-Lauf: ca. 0,50 $ laut Dashboard (inkl. Image-Bau, Modell-Download).

## 14.10.2026 – FESTGELEGT: Prozess Hoerspiel-Schicht (CK)
1. Vertonung Single-Speaker mit Gemini (Basis-Hoerbuch, fassungen/<lg>/audio).
2. Sprecher fuer woertliche Rede bestimmen (Stage 57 Steckbriefe + 57b Zuordnung, DeepSeek) -> Kontrollansicht Word (tools/kontrollansicht_docx.py): alle Sprecher erkannt?
3. Stimmen festlegen mit Empfehlung. REGEL: Abstand zum Erzaehler muss hoerbar sein (Grundton/Klang; Feinjustage per tonhoehe_ht in casting.json).
4. Overlay mit Chatterbox VC (Modal L4): tools/overlay_vorbereiten.py -> gpu_overlay/overlay_modal.py -> tools/overlay_montage.py.
5. Zweite Audio-Schicht fassungen/<lg>/audio_overlay/vc -> TAELLA Hoerspiel-Modus.
Offen: Abstandsregel in Stage 57 + Klaviatur; Modal-Volume fuer Modellgewichte; App-Umschalter Hoerspiel-Modus + Export; "The man"/Bernard-Zuordnung pruefen.

## 15.10.2026 – Jekyll & Hyde + Sleepy Hollow: Altaudio zurueck, EN mit Chatterbox
- Jekyll: DE-Text in stage06 fehlte fuer Kap. 2/9/10 (seit Juni). Vollstaendige Altfassung in _alt_20261010/fassungen/de/work/chapters.
  tools/de_altfassung_einpflegen.py (DeepSeek aligner, Deckungspruefung 97-103 %, Backup .bak_einpflegen) -> start_jekyll_de.bat
  (danach Gemini DE Kap. 2/9/10, Stimme Standard config.TTS_VOICE). DE-Altaudio 603 Saetze nach fassungen/de/audio kopiert.
- Sleepy Hollow: DE-Altaudio vollstaendig (502), Text identisch -> nach fassungen/de/audio kopiert.
- EN mit Chatterbox: gpu_tts/tts_modal.py (Volume readlayer-tts, Kapitel parallel, Wiederaufnahme, Standardstimme), Paket tools/tts_paket.py.
  start_jekyll_en_chatterbox.bat. Danach 58c Wortzeiten fuer beide Sprachen.
- 15.10.: Chatterbox EN fertig (Jekyll 1183, Sleepy 501; 2,65 h Audio, 2,48 $ Modal = 0,94 $/Audio-h). Plausi 0 auffaellig.
  Chatterbox spricht ~20,5 Zeichen/s, Gemini EN 15,0 (gemessen an Wortzeiten Ruf der Wildnis) -> CK: echtes Gemini-Tempo,
  atempo 0.73 (tools/tempo_anpassen.py, Originale in fassungen/en/audio_chatterbox_roh). Laeuft als Schritt 0 im Abschluss-Batch.
  Hinweis: VM-Hintergrundprozesse sterben mit dem Aufruf -> lange Jobs immer per Windows-Batch.
- 15.10.: Gemini-Vertonung parallel: tools/gemini_parallel.py <book> <lang> [--jobs 5] (je Kapitel ein stage58-Prozess).
  stage_58_cloud_tts: READLAYER_58_OHNE_FA=1 ueberspringt Wortausrichtung (Wortzeiten kommen aus 58c; stage07-Alignment
  wird nirgends weiterverwendet) + stage07 wird unter Sperre zusammengefuehrt. Backup .bak_20261015. Ziel: 10 h -> ~2 h.
- 15.10.: Stage 58c auf Modal: gpu_fa/fa_modal.py --werk <b> [--sprachen de,en] [--force] (READLAYER_FA_DEVICE=cuda in 58c, Backup .bak_20261015).
  Lokal gemessen: 58c CPU ~4 s/Satz (Roman DE+EN ~8,5 h) -> Modal geschaetzt 15-20 min, ~0,25 $.
- Jekyll-Befund: stage03 hatte fuer Kap. 2 eine andere DE-Fassung (Cockpit 11.10.), Kap. 9/10 leer; 54a richtete danach aus.
  Vertont ist die Altfassung aus stage06 -> tools/text_nachziehen.py + 54a + 58c (Modal, --force) + Export: start_jekyll_nachziehen.bat.
- 16.10.: Jekyll & Hyde + Sleepy Hollow im Mock-up (taella-app/public/demo, Katalog 15 Werke). Je DE+EN Audio + Wortzeiten.
  58c auf Modal gemessen: Jekyll DE+EN 11,9 min (Upload 3,3), Sleepy 5,7 min (Upload 2,0) — statt ~3,3 h CPU.
  Jekyll: 54a fuer 564 Saetze (Kap. 2/9/10) neu nach Altfassung. Offen: 5 auffaellige DE-Saetze Jekyll (work/audio_plausi_de.txt) pruefen.
- 16.10. CK-Hoertest: keine Unstimmigkeiten; Chatterbox-EN (Standardstimme, Tempo 0.73) "durchaus hoerbar" -> brauchbar als Basisvertonung.
- 16.10. CK: 5 auffaellige DE-Saetze Jekyll gehoert -> unauffaellig (Fehlalarm der Laengenpruefung, vermutlich lange Pausen). Jekyll abgeschlossen.

## 16.10.2026 – Aufraeumen read_layer (verschoben, nichts geloescht)
- archive/2026-10-16_aufraeumen/: logs/ (9 Laufprotokolle), bat/ (11 erledigte Einmal-Batches), ordner/ (gpu_test_sleepy + zip,
  .venv-chatterbox (CPU-Chatterbox, durch Modal ersetzt), gpu_tts/tempo_proben).
- Im Wurzelordner bleiben: cockpit_start.bat, start_gemini_standardstimmen.bat (noch nicht gelaufen), Pipeline-Ordner,
  gpu_fa/gpu_tts/gpu_overlay (Modal-Jobs), stimmen_archiv, models (Thorsten), cache (von config genutzt).

## 16.10.2026 – Abstandsregel Figur <-> Erzaehler (gemessen am fertigen VC-Overlay, Ruf der Wildnis DE)
- Messkette: tools/trennung_messen.py (Paket gpu_messung/<werk>_de: Spannen, Nachbar-Erzaehler laut Wortzeiten, Archiv-Eichclips,
  Pruefspuren + Referenz; Parselmouth F0/Formanten/VTL/HNR/CPPS) -> start_trennung_messen.bat (Modal T4: ECAPA + pyannote 3.1, ~0,03 $/Lauf)
  -> tools/trennung_auswerten.py (BERICHT_trennung.md, auswertung.json, stimmen_archiv/_trennungsregel.json).
- Eichung: 105 Gleich-/5355 Verschieden-Paare (Archiv). ECAPA-Schwelle Kosinus-Abstand 0,599 (EER 8,6 %). F0xVTL: Einheit = typischer
  Unterschied zweier Aufnahmen derselben Stimme (F0 1,44 HT, VTL 0,45 HT); D_schwelle 3,24 (EER 21,7 %), Casting-Ziel D >= 4,06.
- Befunde: (1) Regel Zielstimme vs. Erzaehler DES WERKS sagte das Overlay-Ergebnis 5/5 voraus. (2) Archiv-herr_a vs. herr_a im Werk sind fuer
  ECAPA verschiedene Sprecher -> immer gegen die fertige Einzelstimmen-Fassung messen. (3) Chatterbox VC uebernimmt ~65 % F0 / ~70 % VTL der
  Differenz; Erzaehler hebt Zitate selbst um 1-4 HT, VC nimmt das zurueck. (4) tonhoehe_ht VOR dem VC kommt nur zu ~1/5 an. (5) Tonhoehe
  allein aendert die Sprecheridentitaet kaum; wirksam ist der Formantfaktor NACH dem VC. (6) CK: -3 HT + Formant 0,9 klingt wie Stimmverzerrer.
- Umgesetzt: pipeline/trennung.py (Messung, Regel, Richtung = gemessene VTL weg vom Erzaehler, Natuerlichkeitsgrenzen Formant 0,94-1,10,
  Tonhoehe max +-2 HT, Standard 0); voice_registry.beste_stimme sortiert ok > knapp > zu_nah; Stage 57: erzaehler_stimme gilt fest (auch
  Ich-Erzaehler, Baskerville-Bug), trennung + korrektur je Figur/Sprache in casting.json, neu --trennung [--neu] fuer bestehende Besetzung;
  tools/overlay_korrektur.py + overlay_montage.py wenden korrektur nach VC an (spannen/vc_korr -> vc/). Backups *.bak_20261016.
- Ergebnis Pruefrunde 3 (natuerliche Korrektur, ohne Tonhoehe): Francois 1,10 -> ECAPA 0,71->0,88, pyannote 5->37 %; Perrault 1,10 -> 0,40->0,68,
  0->39 %; Hal/Mercedes unveraendert getrennt (90/99 %); Thornton 0,94 -> 0,46->0,55 = NICHT getrennt -> umbesetzen (kein Archivkandidat mit
  Passung und Abstand; neue Stimme mit Abgrenzung zu Arthur designen, CK-Tor). Kontrolle nur Erzaehler: pyannote 1 Sprecher, 0 s Verwechslung.
  DER 0,252 -> 0,205 (Grundlinie VAD 0,10). pyannote trennt kurze Zitate schwach (Wechsel-Recall ~27 %).
- Stand Audio: fassungen/de/audio_overlay/vc = Runde 3; vc_v1, vc_v2_ohne_korrektur, vc_r2 als Vergleich.
- Klaviatur (claude.ai) zeigt Abstand je Einsatz, Ebene F0xVTL je Werk, Pruefung ECAPA/pyannote (Daten: tools/klaviatur_trennung.py).
- Hoertest fuer Dritte (claude.ai Artifact "TÆLLA Hörtest Stimmen", 25 Paare, Haekchen "kuenstlich"): Teilnehmer als Mitwirkende
  (Contributor) einladen, sonst nur Code am Ende. Auswertung tools/blindtest_auswerten.py. OFFEN.
- Ebenfalls --trennung fuer Alice, Baskerville, AYLI gelaufen (Vorschlaege in casting.json, noch nicht am Overlay geprueft).
- Offen: Thornton neu besetzen; Hoertest; parselmouth auf Windows installieren (py -3.11 -m pip install praat-parselmouth soundfile).
- 16.10.: Gemini-Standardstimmen waren bereits am 14.10. erzeugt (30 Stimmen, DE+EN, standard.json) -> jetzt in der Klaviatur (Filter "nur Gemini-Standard", mit Hoerprobe, Grundton, VTL). start_gemini_standardstimmen.bat nicht erneut noetig -> kann ins Archiv.

## 16.10.2026 – Hoerspiel-Pruefung werkunabhaengig (Arbeitspaket PROZESS_abstandsregel Punkt 1-6)
- Ablauf je Werk: Overlay -> start_trennung_messen.bat <werk> <lg|de,en> -> Cockpit "Hoerspiel-Pruefung" (Tor) ->
  Nachrunde (Overlay neu + bat) oder start_umbesetzen.bat <werk> <lg> "<Figur>" -> Kandidat waehlen (Cockpit) ->
  start_overlay_teil.bat <werk> <lg> "<Figur>" -> start_trennung_messen.bat. Keine Codeaenderung je Werk.
- tools/trennung_messen.py <werk> <lg>: Archiv-Eichung nur mit --eichen (sonst Regel aus _trennungsregel.json, Paket ohne
  Archivsegmente, ~300 statt ~600 Segmente); --runde auto (fertiges Overlay spannen/vc_korr als r1, r2, ...; manifest "runden");
  --korrektur ohne Figurennamen (alle Figuren mit korrektur[lg]; Stufen s1/s2 bis zur Natuerlichkeitsgrenze, ohne Tonhoehe);
  Paket wird neu gebaut, wenn das Overlay neuer ist (z. B. nach Umbesetzung); Stimme je Spanne aus juengstem _teil*-Paket.
- start_trennung_messen.bat <werk> [lg|de,en] [--korrektur] [--eichen]: Paket+Runde+Praat -> Modal -> Auswertung+Rueckfluss.
  gpu_messung/messung_modal.py --pakete a,b,...: je Paket ein T4, hoechstens 10 gleichzeitig (Wellen). messung_gpu.py: alle spur_*.wav.
- tools/trennung_auswerten.py <werk> <lg>: Rueckfluss nach casting.json ensemble[].pruefung[lg] (ECAPA vorher/jetzt, pyannote,
  D, Runde, Urteil, Hoerproben) + hoerspiel_tor[lg]. Urteil: ok | nachrunde (korrektur[lg] eine Stufe weiter, Richtung = VC gegen
  Nachbar-Erzaehler auf der VTL-Achse) | umbesetzen (Grenze erreicht, nach 1 Nachrunde, oder weg von der Zielstimme).
  Ruf der Wildnis DE (r3): Thornton umbesetzen, Francois/Hal/Perrault/Mercedes ok. Backup casting.json.bak_pruefung_20261016.
- Cockpit: neuer Reiter "Hoerspiel-Pruefung" (Ampel je Figur, ECAPA/pyannote/D vorher->jetzt, Hoerproben Erzaehler/vorher/nachher,
  Knoepfe Freigeben/Nachrunde/Umbesetzen, "alle gruenen freigeben", Umbesetzungs-Kandidaten mit Probe + "waehlen").
- tools/blindtest_bauen.py <werk> <lg> [--runde]: Hoertest-Seite aus tools/vorlagen/hoertest_stimmen.html (Paare vor/nach,
  Kontrollen, -20 dBFS, mp3) -> gpu_messung/<werk>_<lg>/blindtest_<runde>/hoertest.html + trials.json; Antworten mit
  version <werk>-<lg>-<runde>. tools/blindtest_auswerten.py <ordner> <werk> <lg>. Artifact NICHT neu veroeffentlicht (laufender Test cotw-de-r3).
- tools/umbesetzen.py: Kandidaten je Richtung (hoeher/heller, groesser/dunkler) per Gemini Voice Design, gemessen gegen den
  Werk-Erzaehler, bis 2 Versuche bis D >= 4,06; --waehlen setzt Stimme, trennung, korrektur, book.json, Register.
  overlay_vorbereiten --nur: fruehere _teil -> _teil_v<n>; overlay_montage wendet alle _teil*-Pakete (aelteste zuerst) an.
- Backups *.bak_20261016b. Offen: Thornton -> start_umbesetzen.bat call-of-the-wild de "John Thornton" (Gemini, nur Windows);
  parselmouth auf Windows; Punkt 7 (Alice, Baskerville, AYLI: Overlay + Pruefung).
- 16.10. 10:05 Ruf der Wildnis DE Runde r6: Thornton umbesetzt auf m_mittel_hoeher_thornton_2 (CK-Wahl, Formant 1,10) ->
  ECAPA 0,45 -> 0,65 (getrennt, naeher an Zielstimme). Alle 5 Figuren ok, Korrekturen innerhalb 0,94-1,10. CK-Freigabe 10:07 -> Hoerspiel-Tor DE frei. Ruf der Wildnis abgeschlossen.
  Fixes: Log aus gpu_messung verlegt (Modal-Upload brach ab), scipy-Zweitmeinung optional.
- 16.10. 11:35 CK: Hoerspiel-Fassung Ruf der Wildnis im TÆLLA-Mock-up gehoert - alle Stimmen passen.
  Achtung: Mock-up oeffnet Ruf der Wildnis aus taella-app/public/ (altes Startwerk), nicht aus public/demo/.
  63 Overlay-Saetze dort in public/audio/de eingesetzt (Erzaehler-Original: public/audio/_de_erzaehler_20261016).
  export_demo.py --hoerspiel setzt die Overlay-Saetze im Demo-Ordner ein. Offen: Umschalter Hoerspiel/Erzaehler in der App.
- Sprachpruefung gebaut (tools/sprachpruefung.py, gpu_sprache/sprache_modal.py Whisper large-v3, start_sprachpruefung.bat,
  Cockpit-Reiter "Sprachpruefung"); Pakete AYLI + Baskerville (teilweise) gebaut, Lauf offen.
- 16.10. 14:10 Sprachpruefung ausgewertet (CK-Urteile: Baskerville 550, AYLI 403). Ursache bestaetigt: Eigennamen.
  Baskerville: kippt mit Namen 94/280, ohne 9/270. AYLI: mit Namen 144/170, ohne 67/233 (v. a. kurze Regiezeilen).
  Whisper (p_de < 0,5) findet AYLI 80 % der Kipper (Praezision 88 %), Baskerville nur 55 % (Praezision 54 %) -
  feine Akzente bleiben unentdeckt -> Reparatur an der Ursache (Aussprache-Lexikon) statt Einzelsatz-Suche.
- 16.10. 14:30 Entscheidung CK: nur betroffene Saetze neu vertonen (mehrstimmige Fassung bleibt), mit Aussprache-Lexikon
  und deutscher Regie. Gebaut: work/aussprache_de.json (Vorschlag Claude: Baskerville 32, AYLI 24 Eintraege, freigegeben=false),
  tools/neu_vertonen.py + start_neu_vertonen.bat <werk> [lg] [liste|probe|los] (Auswahl: Lexikon-Namen + Whisper p<0,5 + CK kippt,
  ohne CK ok; AYLI 325, Baskerville 852 Saetze; alte WAVs -> audio_alt_<datum>, Wortzeiten der Saetze neu, Sprachpruefung nur Neue).
  Offen: CK prueft Lexikon + Hoerprobe (probe), setzt freigegeben=true, dann los.
- 16.10. 14:48 AYLI DE: 325 Saetze neu vertont (Lexikon + deutsche Regie). Whisper: gekippt 92 -> 10, verdacht 111 -> 46,
  auffaellig mit Eigenname 28 % -> 2,6 %; 181 von 211 CK-Kippern jetzt ok. Rest fast nur Ein-Wort-Zeilen (Ab., ORLANDO.) -
  CK: so lassen. Alte WAVs in fassungen/de/audio_alt_20261016. Baskerville-Neuvertonung laeuft.
- 16.10. 14:55 Korrektur: praat-parselmouth ist auf Windows vorhanden (start_trennung_messen.bat misst Praat lokal mit py -3.11: '[praat] 379 gemessen' im Log cockpit/logs/trennung_call-of-the-wild.txt). Offener Punkt 'parselmouth auf Windows' entfaellt.
- 16.10. 16:05 Baskerville DE: 852 + Nachrunde 15 (--nur-whisper) neu vertont. Whisper: gekippt 54 -> 5, auffaellig mit Eigenname
  5,4 % -> 0,7 %. Wortzeiten 3825/3825 (gpu_fa/fa_modal.py laedt jetzt nur Saetze ohne Wortzeiten hoch).
  Beide Werke (AYLI 325, Baskerville 867 Saetze + Wortzeiten) im Mock-up public/demo aktualisiert.
- 16.10. 18:55 AYLI Quellfehler Akt II (Ende Sz. 2 + Sz. 3, raw_modernized.txt): Zeilennummern [85]..[162], Sprechernamen als Zeile,
  Originalzeilen neben Modernisierung -> CK hoerte Nummern + doppelte Saetze. 57 Tags in stage06 auf type "skip" (type_vorher,
  skip_grund; Liste work/_bereinigung_akt2.json, Backup stage06.json.bak_20261016_szene), Demo-Manifeste bereinigt (2483 -> 2426).
  Orlando-Rede "O guter alter Mann ..." (5 Saetze) war ADAM -> sprecher ORLANDO, 17.10. mit Orlandos Stimme neu vertont + im Mock-up. EPUBs neu (17.10.; EN aus work/modernized/chapter-3.json bereinigt, Backup .bak_20261017).
  Andere Werke mit [N]-Praefix: Enchiridion 11, Frankenstein 2 (pruefen).
- 17.10. EPUB Drama erledigt: Stage 30 (EN) baut bei meta.modus=drama aus stage06 wie Stage 31 (DE) - `_build_drama_chapters`: je Replik ein Absatz "SPRECHER. Text", Regie eigene Absaetze, skip faellt weg; DE-Sprechernamen aus casting name_de + `_ROLLEN_DE`. AYLI-Akttitel in stage06 + Manifesten korrigiert (Act II/III/IV, Dritter Akt). Backups *.bak_20261017(_titel).

## 17.10.2026 — ePub-Upload (TAELLA privat) + Chatterbox-Batching: Peter Pan komplett
- Stage 05 ePub-Ingest (pipeline/stage_05_epub_ingest.py): DRM-Pruefung, Cover 1:1 bzw. TAELLA-Cover mit "TAELLA-User: <name>", Klappentext aus OPF, Bereinigung nach epub:type, Bilder/Fussnoten als Anhang mit Link-Marker. Private Werke unter users/<uid>/works/<book_id> (Index "user:<uid>"), nie im Katalog; stage_60 legt privat unter users/<uid>/works ab, kein Katalogeintrag.
- Testwerk: u-mikemustermann-peter-and-wendy (Peter Pan, Standard-Ebooks-Repack von publicdomainlibrary.org), 17 Kap., 250.667 Zeichen. Textkette DeepSeek ~1,15 $ (+0,25 $ Fehlversuche Stage 51).
- Stage 51: DeepSeek lief in Wiederholungsschleife -> Grenzen im Prompt + Kappung/Rettung im Code; DEEPSEEK_MAX_OUT 64000. Regel: kein Modellwechsel ohne Test an kurzem + langem Referenzwerk (claude/ERKENNTNIS_deepseek_listen_2026-10-17.md).
- Chatterbox Multilingual auf Modal: echtes Batching (gpu_tts/cb_batch.py, Batch 8 = Standard) -> 0,35 GPU-h je Audio-h, ~0,25 $ je 50.000 Zeichen (vorher 0,77-0,88 $). Original-Analyzer haengt je Satz neue Hooks an (Bremse) -> behoben.
- Fertigstellung komplett auf Modal (gpu_tts/fertig_modal.py): 58c -> Raender schneiden (tools/raender_schneiden.py, -50/+120 ms; entfernt Chatterbox-Nachklaenge) -> atempo 0,73 -> 58c; ein Paket je Sprache. Start: start_epub_vertonen/modal_komplett/de_neu/de_fertig.bat (mit --detach).
- Fehler: ref.wav wurde durch Upload-Filter ausgeschlossen -> EN/DE erst mit Standardstimme (DE mit englischem Akzent). Behoben + Abbruch, wenn Werkstimme fehlt. DE neu mit grossmutter_a: CK "sehr gut". EN bleibt Standardstimme.
- Kosten Werk komplett zweisprachig ~4,40 $. Upload-Preis-Idee: 1,99 Grund + 0,19/Einheit Uebersetzung + 0,99/Einheit+Sprache Vertonung, 5 % Kulanz; Veredelung nur fuer gemeinfrei/eigene Rechte/Verlagslizenz (Spezifikation "TAELLA ePub-Import" als Doc). Katalog-Rabatt 30/50 % mit Patenschaft.
- Offen: Peter Pan in Katalog (peter-and-wendy, geo_sperre GB, eigenes Cover), Tempo-Regler, S3Gen-Batching, Standard-Ebooks-Regeln fuer Stage 30/31, Kooperation publicdomainlibrary.org (claude/IDEE_kooperation_publicdomainlibrary.md).
- 17.10. Mock-up privates Regal gebaut: Peter Pan (Testuser mikemustermann) via export_demo.py nach taella-app/public/privat/mikemustermann/ (eigene katalog.json, mit Audio DE+EN, 1,8 GB). export_app.py: ohne stage09 Klappentext aus book.json (Backup .bak_20261017). App: Tab "Mein Regal" (loadPrivat, DEMO_USER in lib/katalog.js), private Werke nicht in Entdecken, aber in Favoriten/Begonnen; Detail "Privat · nur fuer dich · TAELLA-User", keine Kapitel-1-Sperre. Backup taella-app/_bak_20261017_privat/. Offen: CK testet im Mock-up; DE-Titel + DE-Klappentext fehlen bei Uploads (nur EN aus OPF).
- 17.10. CK-Hoerbefund Peter Pan: (1) Kauderwelsch zwischen Saetzen = Chatterbox-Nachklang, v. a. bei kurzen Saetzen; Integritaetspruefung in cb_batch faengt ihn nicht. tools/nachklang_suchen.py (Energie ausserhalb der 58c-Wortzeiten) -> DE 35 / EN 87 verdaechtig; tools/nachklang_schneiden.py hat DE 24 / EN 57 nach letztem Wort+120 ms gekappt (Original in fassungen/<lg>/audio_vor_nachklang/, Mock-up-Kopie aktualisiert). Rest DE 11 / EN 30 (Woerter verschmiert) = neu vertonen -> work/nachklang_klassen_<lg>.json; Werkzeug fuer satzweise Chatterbox-Neuvertonung fehlt noch. (2) Tempo-Regler im Hoeren (0,8-1,5x, preservesPitch, taella_tempo). (3) Kuratormodus schrieb private Werke nur in den Browser (vite.config kannte users/ nicht) -> behoben, Offline-Anmerkungen werden beim naechsten Laden nachgereicht. Backup taella-app/_bak_20261017_privat/.
- 17.10. Reader: Blaetter-Tippzonen am Rand entfernt (Woerter am Rand loesten Umblaettern aus); jetzt sichtbare Pfeile links/rechts in der Fusszeile + Wischen + Tasten <-/->. Backup taella-app/_bak_20261017_privat/App_vor_pfeile.*
- 17.10. CK: Grandma mit App-Tempo 1,25 fluessig -> Drosselung kuenftig atempo 0,91 statt 0,73 (fertig_modal.py Default, start_epub_fertig.bat, modal_komplett). Peter Pan bleibt vorerst bei 0,73 (Neuberechnung aus audio_chatterbox_roh moeglich).
- 17.10. Eigennamen (George->Georg, Michael dt.): Text war korrekt, Chatterbox liest sie deutsch. tts_paket.py wendet jetzt work/aussprache_<lg>.json (freigegeben) auch fuer Chatterbox an. Entwurf Peter Pan aussprache_de.json (23 Namen, freigegeben=false) -> CK-Hoerprobe, dann betroffene Saetze neu vertonen.
## 17.10.2026 abends — Chatterbox-Ausbau 1-3 gebaut (noch NICHT auf Modal getestet)
- PRUEFUNG IM STANDARDPROZESS (CK): (a) im Vertonungslauf (tts_modal_opt.py, Batch-Pfad): Dauer je Stueck gegen ~51 ms/Zeichen; zu lang (>2x+1,2 s: Nachklang/verschmiert) oder zu kurz (<0,35x: abgebrochen, z. B. c003_00124_dl) -> bis 2x neu, plausibelste Fassung bleibt; Rest in messung.json "pruefung_rest". (b) nach Fertigstellung: tools/satzpruefung.py --schneiden (fertig_modal.py Schritt 4b + start_epub_fertig.bat 5/5): kappt Nachklang, listet "neu" -> work/satzpruefung_<lg>.json.
- 1 Neuvertonung satzweise: tools/cb_neu.py (liste/einspielen/abschluss) + start_cb_neu.bat <werk> <lg> <liste|probe|los> [--pruefung --nachklang --lexikon --kuration --tags]. Eigenes Paket gpu_tts/<werk>_<lg>_neu (ein Container), Download in audio_neu_<datum>, alte WAVs -> audio_alt_<datum>, Rohfassung -> audio_chatterbox_roh, 58c nur neue Saetze (fa_modal inkrementell), Satzpruefung, Kuration "neu vertont", Mock-up-Export. Lexikon nur mit Freigabe (Probe auch ohne).
- 2 Prosodie: tools/prosodie_marken.py (DeepSeek flash, 5 feste Klassen ruhig/lebhaft/gespannt/ausruf/leise, keine freie Regie) -> work/prosodie_<lg>.json; tts_paket.py --prosodie -> ex/cfg je Satz (STILE); cb_batch: Regler je Zeile. PAUSEN: stage_60 nahm pause_after_ms aus stage54a (leer) -> alle Mock-up-Werke hatten 250 ms Einheitspause; jetzt aus stage06 (350/450/800/900 ms). Peter Pan neu exportiert; uebrige Werke beim naechsten Export. Offen: Satzkontext (2-3 Saetze je Zeile + Schnitt).
- 3 S3Gen-Batching: cb_batch._s3_batch (Flow/CFM fuer den ganzen Batch mit token_len-Maske, HiFiGAN + Wasserzeichen je Satz), Schalter --s3batch.
- Test: start_chatterbox_test.bat [werk] [lg] -> Kap. 1 in A (Standard) / S (+S3-Batch) / P (+Prosodie), Messung (tools/prosodie_messen.py: Tonhoehen-Streuung), Hoerkopien Tempo 0,91 (tools/tempo_ordner.py) unter work/_tts_probe/<lg>_*_tempo. DeepSeek/Modal nur vom Windows-Rechner erreichbar.
- Reihenfolge Peter Pan: (1) start_chatterbox_test.bat -> CK hoert A/S/P; (2) start_cb_neu.bat ... probe --lexikon (Namen) -> Freigabe aussprache_de.json; (3) Neu-Tempo 0,91: py -3.11 -m modal run gpu_tts/fertig_modal.py --werk u-mikemustermann-peter-and-wendy (aus Rohfassung im Volume, inkl. Satzpruefung); (4) start_cb_neu.bat <werk> de los --pruefung --kuration --lexikon, dann en.
- Backups: gpu_tts/*.bak_20261017_ausbau, tools/tts_paket.py.bak_20261017, stage_60_cloud_export.py.bak_20261017_pause.
- 17.10. Ergebnis start_chatterbox_test.bat (Kap. 1 DE): A 0,250 $/50k, S (S3-Batch) 0,219 $ (S3Gen kaum schneller: 156->150 s; Zeit steckt in Vocoder/Wasserzeichen), P (Prosodie ex/cfg je Satz) 0,231 $ - CK: Prosodie KAUM HOERBAR, Tonhoehen-Spanne gleich (10,7 vs 10,9 HT). DeepSeek markierte 55 % nicht-ruhig. -> Regler-Ansatz reicht nicht; naechste Hebel: Satzkontext, Referenz je Stil.
- CK: in den Probedateien teils Wortfetzen am Satzende (Rohfassung ohne Randschnitt; Laengen-Pruefung zu grob). -> Pruefung im Lauf jetzt mit Forced Alignment (gpu_tts/cb_pruefung.py, MMS_FA im TTS-Container): Nachklang/Wortfetzen, Vorlauf, verschmiert, zu kurz/lang -> bis 2x neu, Rest-Nachklang hinter letztem Wort gekappt. Eichen: start_probe_pruefen.bat (lokal, CPU, auf de_b8_probe_A) -> CK vergleicht mit Gehoer.
- 17.10. Stimmungs-Referenzen statt Regler: tools/stimmungs_referenzen.py (Gemini, gleiche Voice-Design-Stimme, 5 Stimmungen x DE/EN -> stimmen_archiv/<stimme>/stil_*.wav), tts_paket.py --stil-refs=<stimme> (je Satz Referenz nach prosodie_<lg>.json), Chatterbox-Conds je Zeile (cb_batch refs, tts_modal_opt refs). Start: start_stimmungen.bat refs -> CK hoert -> start_stimmungen.bat test (Kap. 1 DE Variante R).
- 17.10. Variante R (Stimmungs-Referenzen je Satz, Gemini-Stimmungen grossmutter_a): CK - kaum Prosodie-Gewinn, evtl. etwas fluessiger, weiter emotionsneutral. Pruefung im Lauf (MMS_FA) erstmals live: 9 Nachklang, 1 Vorlauf, 1 zu lang -> 9 neu, 1 gekappt, Rest c001_00128_dl; 0,264 $/50k. Learning: Chatterbox Multilingual uebernimmt Stimmung weder ueber Regler noch ueber Referenz nennenswert (T3 nutzt nur ~6 s Referenz-Token). Naechste Hebel: T (Zeichen erhalten), Hybrid Gemini fuer markierte Gefuehlssaetze, langfristig LoRA.
- 17.10. ENTSCHIEDEN (CK): eigenes Chatterbox-Modellgewicht per LoRA aus LibriVox; DE-Trainingsdaten = alle 22 Solo-Werke von Ramona Deininger-Schnabel (reader 6507, 149,6 h, Profi). AP: Projekt-Doc claude/AP_lora_librivox.md. Start mit Testlauf ~10 h. LibriVox-Sprecherauswahl: start_librivox_sprecher.bat (Cockpit localhost:8765, Urteile daten/verdicts.csv).
- 17.10. Variante T (Zeichen erhalten, cb_batch.sprech_norm): CK - nettes Instrument (Pausen), aber keine echte Prosodie. FAZIT Tag: Regler (P), Stimmungs-Referenzen (R), Zeichen (T) bringen Chatterbox Multilingual keine Prosodie -> Weg ist LoRA (claude/AP_lora_librivox.md). Pruefung im Lauf (cb_pruefung) bleibt Standard.
- 17.10. CK: Satzzeichen erhalten (sprech_norm) ist STANDARD in tts_modal_opt.py (alter Weg nur mit jobs.json "zeichen": "punc_norm").
- 17.10. GRUNDSATZ (CK): LoRA lernt nur Vortragskunst, NIE die Stimme der Sprecher (Stimme = ihr Kapital). Schutzregeln in claude/AP_lora_librivox.md: nur T3, nie Sprecheraufnahmen als Referenz, mehrere Sprecher gemischt (keiner > 40 %), Sprecher-Merkmal je Schnipsel, Freigabe-Tor Stimmaehnlichkeit (ECAPA).

## 17.10.2026 – LoRA-Testlauf Ramona GEBAUT (AP claude/AP_lora_librivox.md), Start offen
- Start: start_lora_test.bat [alle|holen|abschrift|schnitt|training|bewertung] (Log cockpit/logs/lora_ramona_test.txt).
- Daten: Ramona Deininger-Schnabel (LV 6507) Pinocchio + Fraeulein Else + Sterben = 10,2 h Rohaudio. Vollausbau: --werke alle --lauf <neu>.
- gpu_lora/lora_modal.py: holen (archive.org, Original-MP3) -> Whisper large-v3 Wortzeiten (L4, bis 10 parallel) -> Saetze 2-15 s,
  Schnitt per MMS_FA, Aussortieren per cb_pruefung (Tempo auf Sprecherin geeicht), LibriVox-Ansagen/Ziffern/unsichere Abschrift raus
  -> S3-Tokens, Texttokens (sprech_norm wie Produktion), VE, Prosodie-Marke aus Audio (emotion_adv 0,25-0,85; DeepSeek-Marke erst im Vollausbau)
  -> LoRA Rang 32 auf T3-Llama (A100, 3 Epochen, Bedingung = anderer Satz derselben Sprecherin, Verlust mit Token-Versatz, 3 % Validierung)
  -> Bewertung Peter Pan c001 DE, grossmutter_a: basis / bester / letzter Checkpoint (Pruefung im Lauf, VE-Aehnlichkeit Referenz vs. Ramona, Prosodie).
- gpu_lora/lora_kern.py: eigene LoRA (ohne peft), einmischen(t3, pfad) fuer spaeteren Schalter tts_modal_opt.py --lora (AP Schritt 7).
- Ablage Volume readlayer-tts /lora/ramona_test/; lokal gpu_lora/ramona_test/ (BERICHT.md, hoerliste.txt, bewertung/<variante>/).
- Kosten geschaetzt: Whisper ~0,5 $, Schnitt ~0,5 $, Training A100 < 2 $, Bewertung ~1 $ -> ~4 $.
- 17.10. 18:45 Testlauf 1 Ergebnis: nur 0,42 h von 10,2 h verwertbar (310 Saetze) -> Training (57 Schritte) ohne Aussage; Bewertung
  basis 132/140 ok vs. LoRA 124/140, Klangfarbe unveraendert (VE 0,94). Ursachen: Whisper ohne Prompt verliert ueber lange Strecken
  die Satzzeichen (kaum Satzenden), Pausenpflicht aus Whisper-Zeiten verwarf ~350 Saetze.
- Umbau 19:05 (CK: vorhandenen LibriVox-Schnitt nutzen): Schnitt jetzt wie pipeline/stage_58_3rd_prty (Tal zwischen Saetzen +
  Konsonanten-Nachlauf, Funktionen direkt importiert), cb_pruefung bleibt Kontrolle; Whisper als Batch-Pipeline mit Prompt je Abschnitt
  (Satzzeichen); kurze Saetze werden zusammengefasst. Neu starten: start_lora_test.bat alle --neu. Backup lora_modal.py.bak_20261017_test1.
- 17.10. 19:20 Referenztext eingebaut (CK): Schritt holen laedt den "Online text" der LibriVox-Seite (gutenberg.org Plaintext bzw.
  projekt-gutenberg.org alle /chapter/N-Seiten) -> /lora/<lauf>/text/<aid>.json. Schnitt nimmt Woerter + Satzzeichen aus dem Buch,
  Zeiten aus Whisper (difflib fortlaufend ueber alle Dateien, wie Stage 58 3rd party); Satzgrenzen nur, wenn erstes/letztes Wort im
  Audio gefunden. Ohne Referenz oder bei < 60 % Treffern je Datei: Whisper-Text. Alle Schritte laufen auf Modal (L4/A100).
  Backup lora_modal.py.bak_20261017_test2. Start: start_lora_test.bat alle --neu.
- 17.10. 19:20 Gegenprobe Ramona-Stimme (CK) eingebaut: Bewertung zusaetzlich ramona_basis / ramona_lora (Referenz = ~10 s aus
  zurueckgehaltenen Validierungssaetzen). Fertige Varianten werden nicht neu gerechnet. Laufender Lauf nutzt noch den alten Stand
  -> danach: start_lora_test.bat bewertung (rechnet nur die beiden Ramona-Varianten, ~10 min). Backup lora_modal.py.bak_20261017_test3.
- 17.10. 20:39 ERGEBNIS LoRA-Testlauf 2 (Referenztext): 7,1 h Schnipsel (5.053 Saetze), Training 927 Schritte 3,6 min A100,
  Validierung 4,07 -> 3,76 (bester step_00500). Peter Pan c001: Satzpruefung grossmutter_a 132 -> 140/140, Ramona 110 -> 139/140
  (Nachklang fast weg); s/Satz 12,3 -> 9,6 (schneller); Tonhoehen-Streuung 6,31 -> 5,86 (nicht lebendiger); Klangfarbe
  grossmutter_a 0,94 -> 0,92, keine Faerbung Richtung Ramona (0,79). Wirkung uebertraegt sich auf fremde Stimme.
  Offen: CK-Hoertest basis vs. lora_bester (gpu_lora/ramona_test/bewertung, hoerliste.txt).
- 17.10. 20:55 CK-Hoertest: Ramona deutlich besser, ABER LoRA schneidet Satzenden ~400 ms zu frueh ab (beide Stimmen).
  Gemessen: Stille am Satzende basis 0,36 s / ramona_basis 0,28 s vs. LoRA 0,02 s; 88-105 von 140 Saetzen ohne Ausklang.
  Ursache: Trainingsclips endeten am Tal + 80 ms -> Modell lernt Stopp direkt nach dem letzten Laut. Fix: Clip-Ende = letztes Wort
  (MMS_FA) + 0,40 s, begrenzt vor den naechsten Satz; Bericht mit Spalte Ausklang/abgeschnitten.
  Neu starten: start_lora_test.bat ab_schnitt (Schnitt + Training + Bewertung, ~40 min). Backup lora_modal.py.bak_20261017_test4.
- 17.10. 20:54 Testlauf 3 (Ausklang-Fix, 3,9 h Schnipsel, bester step_00250): Ausklang LoRA 0,02 -> 0,12 s (grossmutter_a) / 0,14 s (Ramona),
  abgeschnitten 91 -> 25/140 bzw. 88 -> 11/140; Satzpruefung 140/140 bei beiden. Grundmodell zum Vergleich 0,38 s / 7 abgeschnitten.
- 18.10. 07:52 CK-Hoertest Testlauf 3: Prosodie der LoRA-Varianten VERBESSERT, Stoergeraeusche nach dem Satz verschwunden.
  Kandidat fuer Pipeline: /lora/ramona_test/ckpt/step_00250.safetensors.
  Naechste Schritte (CK): (1) Adapter in Pipeline verankern (tts_modal_opt.py --lora, tts_paket/jobs.json, book.json tts_lora, Tempo neu messen),
  (2) Schnittpunkt kontrollieren (Stichprobe Trainingsclips; ggf. Stille anfuegen statt verwerfen -> wieder ~7 h),
  (3) Peter Pan DE komplett mit grossmutter_a + LoRA vertonen, 58c, Export ins TAELLA-Mock-up.
- 18.10. 07:56 CK: Satzenden "manchmal knapp, aber alles da" -> Adapter step_00250 (ramona_test) wird uebernommen als ramona_v1.
  Spaeter optional: Stille anfuegen statt verwerfen (wieder ~7 h) fuer etwas laengeren Ausklang.
- 18.10. 08:00 CK: "George" klingt wie "Ge-Ortsch" (Bewertung lief mit Rohtext, ohne Lexikon). Fuer Peter Pan komplett:
  Aussprache-Lexikon users/mikemustermann/works/u-mikemustermann-peter-and-wendy/work/aussprache_de.json (George->Dschordsch u. a.,
  23 Eintraege, freigegeben=false) vorher per Namens-Probe mit ramona_v1 von CK freigeben, dann im Vertonungslauf anwenden.
- 18.10. 08:20 ramona_v1 in Pipeline verankert (noch nicht auf Modal gelaufen):
  tts_modal_opt.py: jobs.json "lora" -> lora_kern.einmischen nach from_pretrained; Adapter wird einmalig nach Volume /lora/adapter/ramona_v1.safetensors kopiert
  (Quelle /lora/ramona_test/ckpt/step_00250); Variante bekommt Suffix _ramona_v1 (kein Mischen mit altem b8-Ordner); cb_pruefung-Erwartung aus jobs.json.
  tts_paket.py: --lora=<name>|aus, Standard book.json "tts_lora" (Peter Pan = ramona_v1) -> jobs.json lora, ms_je_zeichen 0,043, tempo 0,76;
  --lexikon-pflicht bricht ab, wenn Lexikon nicht freigegeben. Tempo gemessen: ramona_v1 ~17 % schneller als Grundmodell -> atempo 0,76 = gleiches
  Endtempo wie Grundmodell mit 0,91. fertig_modal.py + cb_neu einspielen nehmen Tempo aus jobs.json.
  cb_neu probe --lexikon = Namensprobe (jeder Eintrag mind. einmal, 21 Eintraege in 9 Saetzen). Backups *.bak_20261018_lora.
  Ablauf: (1) start_cb_neu.bat u-mikemustermann-peter-and-wendy de probe --lexikon -> CK hoert work/_cb_probe/de/neu vs alt
  -> aussprache_de.json "freigegeben": true; (2) start_lora_komplett.bat (Paket, Modal Batch 8, Fertigstellung Modal, Mock-up-Export).
- 18.10. 08:06 Einbau ramona_v1 (Auftrag fuer naechste Sitzung): Adapter liegt im Modal-Volume readlayer-tts unter
  /lora/ramona_test/ckpt/step_00250.safetensors (~90 MB, nur LoRA-Gewichte). Schritte: (a) im Volume nach /lora/adapter/ramona_v1.safetensors
  kopieren, (b) Sicherungskopie lokal read_layer/gpu_lora/adapter/ramona_v1.safetensors, (c) tts_modal_opt.py --lora ramona_v1,
  (d) Namensprobe mit Lexikon -> CK-Freigabe, (e) Peter Pan DE komplett + 58c + Export Mock-up.
- 18.10. 08:12 Auftrag 08:06 abgeglichen: (a)+(c) erledigt (Schalter ueber jobs.json/book.json tts_lora statt CLI-Flag), (b) neu:
  tts_modal_opt.py::adapter_sichern legt /lora/adapter/ramona_v1.safetensors an + Sicherung gpu_lora/adapter/ramona_v1.safetensors;
  laeuft automatisch in start_cb_neu.bat und start_lora_komplett.bat (einmalig, danach uebersprungen). (d)+(e) = Ablauf 08:20.
- 18.10. 08:21 CK: Namensprobe ok, "Peter Pan" -> "Pieter Pan" (Pan im Deutschen gelaeufig); aussprache_de.json Peter Pan freigegeben=true. Naechster Schritt: start_lora_komplett.bat.
- 18.10. 08:30 Regel CK: Logs nur nach cockpit\logs (Skill read-layer-konventionen). 13 start_*.bat umgestellt (Backups .bak_20261018_logs), Root-Logs nach cockpit/logs verschoben. OFFEN: start_lora_komplett.bat erst nach laufendem Lauf umstellen + dessen Log verschieben.
- 18.10. 08:32 Regel CK: Test-Dateien, Proben, Zwischenergebnisse und Testordner nach Gebrauch (z. B. nach Testhoeren) nach archive/<JJJJ-MM-TT>_tests/<urspruenglicher Pfad> verschieben (Skill read-layer-konventionen). Nachholen nach Peter-Pan-Lauf: _cb_probe, _tts_probe, gpu_lora/ramona_test/bewertung, start_*_test.bat u. a.
- 18.10. 08:40 Aufraeumen nach Regel "Tests ins Archiv": 37 Eintraege nach archive/2026-10-18_tests/ (Liste: INHALT.txt): Test-Batches (chatterbox/zeichen/stimmungen/probe/epub_probe), gpu_tts *_testA/P/R/T + *_de_neu, gpu_overlay *_teil_v1/v2, gpu_sprache-Pakete AYLI/Baskerville, cockpit/_test + _demotest.tgz, stimmen_archiv/_test_alice_erzaehlerin, users/testuser, Overlay-Vergleiche Ruf der Wildnis (vc_v1, vc_v2_ohne_korrektur, vc_r2, VERGLEICH-WAV), _hoerprobe/de|en|probe + _neuvertonung (Alice, Baskerville, AYLI; _hoerprobe/_seg bleibt = Segment-Cache). Messlog gpu_messung -> cockpit/logs. GESPERRT (Windows: Datei offen), spaeter nachholen: gpu_lora/ramona_test, Peter Pan work/_cb_probe + _tts_probe. Bleiben bewusst: Sicherungsstaende (_alt_*, audio_alt_*, audio_roh_*, audio_chatterbox_roh, audio_vor_nachklang, _librivox_*), gpu_messung/blindtest (Hoertest offen), start_lora_test.bat (fuer ramona_v2).
- 18.10. 09:25 Peter Pan DE komplett mit grossmutter_a + ramona_v1: 2985/2985 Saetze, 4,1 h Audio, GPU 88 min ~1,18 $ (0,211 $ je 50.000 Zeichen), Pruefung im Lauf 5 neu, Rest 0; Fertigstellung Tempo 0,76, Satzpruefung 0 auffaellig; Mock-up privat exportiert. Log cockpit/logs/lora_komplett_*.log; start_lora_komplett.bat schreibt jetzt dorthin. OFFEN: CK-Hoertest im Mock-up.
- 18.10. 09:45 CK: roemische Kapitelnummern wurden als "i."/"ix." gelesen. Regel neu: pipeline/sprechtext.py (nur Sprechtext, type h: "IX. ..." -> "Neun. ..." / "Nine. ..."), eingebunden in tts_paket.py (Chatterbox) und stage_58_cloud_tts.py (Gemini). cb_neu --ueberschriften. Quickfix Peter Pan: start_cb_neu.bat u-mikemustermann-peter-and-wendy de los --ueberschriften. Backups *.bak_20261018_roemisch.
- 18.10. 09:55 CK: weiteres LoRA-Training mit Sprecher-Variation. Kandidaten DE (daten/speakers.json): Bernd Ungerer (LV 9565) 16 Werke 189 h; Julia Niedermaier (LV 5424) 4 DE-Werke 18 h (Menschen im Krieg, Gemeindekind, Brennendes Geheimnis, Lob der Narrheit). Mischregel: keiner > 40 %.
- 18.10. 10:05 LoRA-Mischlauf gebaut (noch nicht gelaufen): gpu_lora/lora_modal.py --mix standard (MIX_PLAN 5424:alle,9565:julia,6507:julia): Julia Niedermaier 4 DE-Werke 18,1 h; Bernd Ungerer kleine Werke zuerst 18,8 h (Totenhochzeit, Verteidigung des Unsinns, Knaben und Moerder, Karfunkelstein, Ingraban); Ramona kleine zuerst 19,0 h (9 Werke) = 55,9 h Rohaudio. Training: Sprecher je Werk (/lora/mix_v1/werke.json), Deckel 40 % je Sprecher, Bedingung weiter = anderer Satz desselben Werks, VE-Zentrum je Sprecher, Bewertung mit Aehnlichkeit je Sprecher. Start: start_lora_mix.bat (Lauf mix_v1, Log cockpit/logs/lora_mix_v1.txt). Backup lora_modal.py.bak_20261018_mix.
- 18.10. 10:10 CK: Ziel des Mischlaufs = Nivellierung des LoRA (ausgeglichener Vortrag, nicht Stimmengewinn). NIVELLIEREN=True: jeder Sprecher mit gleichen Trainingsstunden (auf kleinsten Anteil gekuerzt); Prosodie-Marke ist ohnehin je Werk normiert, Bedingung = Satz desselben Werks (Stimme wird nicht gelernt).
- 18.10. 10:15 CK: Ramona verschleift oft Interpunktion + starker Singsang. Umgesetzt: (1) Schnitt verwirft Saetze, in denen mehr als die Haelfte der inneren Satzzeichen (, ; : —) keine Pause >= 60 ms hat ("zeichen_verschliffen", alle Sprecher). (2) Ramona im Training halbes Gewicht (SPRECHER_GEWICHT 0,5 -> ~20 %), dabei ihre ruhigsten Saetze (geringste Tonhoehen-Streuung) statt Zufall.
- 18.10. 11:55 TERMIN 19.10.: Umbau Stage-Nomenklatur (CK einverstanden): Dateinamen <Nummer>_<Aufgabe in 1-2 Begriffen> (z. B. XXX_Rueckuebersetzung); Kopf je Datei mit Funktion, Wirkungsweise, beteiligten Komponenten, Zulieferern und Abnehmern; Verweise in run.py, Cockpit, tools, gpu_*, start_*.bat anpassen; Tabelle nach docs/ und in den Claude-Projektspeicher. Vorher: Tabelle von CK (aus anderem Chat) einholen; erst nach Ende des LoRA-Mischlaufs (nutzt stage_58_3rd_prty).
- 18.10. 12:00 LoRA mix_v1 FERTIG: 21,5 h Schnipsel (verworfen u. a. zeichen_verschliffen), nivelliert 9565 7,4 h / 5424 7,4 h / 6507 3,7 h = 17,9 h; Training 8,3 min A100, Validierung 3,86 -> 3,594 (bester step_01000). Peter Pan c001 grossmutter_a: Pruefung 132 -> 139/140, abgeschnitten 11 -> 1, Ausklang 0,16 s, Klangfarbe 0,94 -> 0,93, keine Faerbung zu einem Sprecher. Hoerproben: gpu_lora/mix_v1/hoerprobe/ (passage_1_grundmodell / 2_ramona_v1 / 3_mix_v1, Tempo 0,91/0,76/0,75; satzweise_grund_ramona_mix.wav). Offen: CK-Hoertest ramona_v1 vs mix_v1.
- 18.10. 12:05 ENTSCHIEDEN (CK): LoRA mix_v1 (Volume /lora/mix_v1/ckpt/step_01000) = Standard fuer Deutsch, Single Speaker + Erzaehler. config.TTS_LORA = {"de": "mix_v1"}; tts_paket: book.json tts_lora > config.TTS_LORA[lg] > ohne; mix_v1 ms_je_zeichen 0,0425, Tempo 0,76. tts_modal_opt ADAPTER + adapter_sichern (ohne --lora: alle Adapter, lokal gpu_lora/adapter/). fertig_modal --variante auto (b8_<lora>). start_lora_komplett.bat nutzt Standard. Peter Pan bleibt vorerst ramona_v1 (book.json tts_lora). Backups *.bak_20261018_mixstd.
- 18.10. 19:20 Werk-Audit: docs/AUDIT_werke_2026-10-18.xlsx (255 Werke; 44 in Arbeit). Kontaktboegen/Rohdaten cockpit/logs/audit_tmp. Empfehlung raus: Struwwelpeter, Peter Rabbit, War and Peace Bd. 1 (falsche Quelle), Oedipus (Murray +1957 -> PD ab 2028). Pruefen: Lysistrata, Apology, Symposium, Enchiridion, Peter and Wendy.
- 18.10. 19:45 Cockpit Nr. 1+2 umgesetzt (Backups archive/2026-10-18_vor_cover_final_kt_pruefung):
  (1) neuer Schritt cover_final (tools/cover_final.py, Bahn export) nach Klappentext+Cover; Tor Cover haengt jetzt an cover_final und zeigt das fertige DE-Cover. s620: Sprecherzeile nie mehr LibriVox/Thorsten, nur aktuelle designte Stimme; Autorname ohne Gutenberg-Klammer ("H. G. Wells"). Alte cover_final (6 Werke) -> archive/2026-10-18_cover_final_alt.
  (2) pipeline/klappentext_pruefung.py: Fehler = Block leer, DE=EN / nicht deutsch, Gutenberg-/Lizenztext; Hinweise = Einleitung/Edition statt Werk, Zitat nicht im Text. s600 prueft nach Erzeugung, uebersetzt DE-Saetze gezielt nach, erzeugt bei Gutenberg-Text neu; --pruefen nur pruefen/reparieren. Cockpit: Klappentext+Cover erst erledigt bei bestandener Pruefung; dann Aufruf s600 --pruefen. Stand: 41 Klappentexte durchgefallen, 209 Werke bereit fuer cover_final.
  OFFEN: EPUBs der fertigen Werke tragen noch alte Cover (neuer Export noetig). Autornamen "Horatio, Jr. Alger", "Emperor of Rome Marcus Aurelius" in author.json korrigieren.
- 18.10. 20:00 Cockpit-Lauf 24 Werke: Cover final 24/24 (EN+DE), Klappentext-Reparatur Cthulhu/Earnest/Romeo/Love and Freindship bestanden, Export Sleepy Hollow. Titelkorrektur (Backups archive/2026-10-18_titelkorrektur): Earnest DE "Ernst sein ist alles"/EN "The Importance of Being Earnest"; Christmas Carol DE "Eine Weihnachtsgeschichte"/EN "A Christmas Carol"; author.json plato name_display_de "Platon" (s620 nutzt name_display_<lang>). Cover final dieser 4 Werke neu ueber Cockpit. OFFEN: Jekyll-Titel (4 Zeilen) ueberdeckt Illustration.
- 18.10. 20:35 ENTSCHIEDEN (CK): raus (PD-Tor abgelehnt, mit Notiz): Struwwelpeter (g12116), Peter Rabbit (g14838), Oedipus/Murray (g27673), Peter and Wendy EPUB-Test (g26654). Bleiben: War and Peace (Quelle muss neu: richtige Gutenberg-Datei), Lysistrata, Apology, Symposium, Enchiridion, Peter Pan (peter-pan-b-peter-and-wendy, g16). Backup freigaben: archive/2026-10-18_titelkorrektur/freigaben_vor_raus.json.
- 18.10. 20:40 Cockpit: abgelehntes Cover-Tor loest jetzt Neuerzeugung der Illustration aus (s610 --force, Bahn Gemini); danach cover_final neu und Tor Cover wieder offen. Betrifft Frankenstein (g84) und Roughing It (g3177). Alte Illustrationen: archive/2026-10-18_cover_abgelehnt.
- 18.10. 20:50 s610 Cover-Prompt: Schauplatz aus Klappentext-Meta entfernt (stammt aus Textprobe, verzerrt Motiv); neu optionales book.json "cover_motiv" (englisch) als Motiv-Vorgabe. Frankenstein: "the Creature, a towering, solitary and sorrowful figure, one hand raised toward a single bolt of lightning". Backup archive/2026-10-18_cover_abgelehnt/s610_cover.py.bak.
- 18.10. 21:05 TAELLA-Demo (taella-app/public/demo) nachgezogen, nur Fehlendes/Fehlerhaftes (Sicherungen demo/_alt_20261018): neue Cover final (cover_de/en.jpg) bei 10 Werken, cover.png (nur Illustration) archiviert, blurb.json nur Feld covers, katalog.json Cover-Liste + DE-Titel, manifest_<lang>.json nur Feld titel (DE war ueberall englisch). Audio, wordtimes, Satzinhalte unveraendert. Struwwelpeter, Peter Rabbit, War and Peace aus Demo + Katalog -> demo/_alt_20261018. Enchiridion/Paradyne: Cover final folgt nach Textkorrektur.
- 19.10. 04:35 Nomenklatur: Cover final als Stage 615 eingeordnet -> pipeline\s615_cover_final.py (Kopf nach Schema), run.py EPUB_LINE 615 (fertig = beide cover_final_<lang>.jpg juenger als images\cover.png), Cockpit ruft -m pipeline.s615_cover_final. tools\cover_final.py nur noch Weiterleitung bis Cockpit-Neustart, dann ins Archiv. Matrix (docs\Pipeline_Strang_Matrix.xlsx + Projektspeicher) um 615 und Hilfsmodul klappentext_pruefung ergaenzt; 600 Funktion + 610 Eingabe (cover_motiv) nachgezogen. Backups archive\2026-10-19_s615.

## 23.10.2026 14:50 — LoRA mix_v2 GEBAUT (Ramona-Dominanz austreiben), Start offen
- CK: Training nur mit Julia Niedermaier (5424), Bernd Ungerer (9565), Hokuspokus (2037, LV "gut", 48 DE-Werke 146 h). Ramona raus.
- gpu_lora/lora_modal.py: MIX_PLAENE["v2"] = "5424:alle,9565:julia,2037:julia" (Hokuspokus ~18 h Rohaudio, 13 kleinste Werke).
  Neue Modal-Funktion uebernehmen(): fertige Schnipsel Julia/Bernd aus /lora/mix_v1 (daten, bericht, clips) -> /lora/mix_v2; nur Hokuspokus
  wird geholt/abgeschrieben/geschnitten (1. Start 15:16 Timeout beim Clip-Kopieren -> Clips werden nicht mehr uebernommen). Nivellierung wie mix_v1 (je Sprecher gleiche Stunden).
  Bewertung: --vergleich mix_v1:step_01000.safetensors -> Varianten basis / lora_bester (mix_v2) / mix_v1 + Ramona-Gegenprobe
  (Referenz + VE-Zentrum aus mix_v1). Dominanz-Mass = Spalte "Aehnlich Ramona". Backup lora_modal.py.bak_20261023_mixv2.
- Start: start_lora_mix_v2.bat (Log cockpit/logs/lora_mix_v2.txt). Kosten geschaetzt ~3 $.
- Danach: CK-Hoertest mix_v1 vs mix_v2 (gpu_lora/mix_v2/bewertung) -> ggf. config.TTS_LORA de = mix_v2.

## 24.10.2026 — Hoertest mix_v1 vs. mix_v2 mit Emoji-Weg ("Der große Gott Pan") GEBAUT, Start offen
- CK: Peter Pan ungeeignet (Maerchen vertraegt Singsang) -> Machen "Der große Gott Pan" Kap. 1 Schluss (c001_00122-00160, 39 Saetze, Marys Experiment), bisher nicht vertont.
- gpu_tts/pan_test.py + start_pan_test.bat: DeepSeek-Regie je Satz (Stimmung aus Emoji-Bibliothek, sparsam, gecacht in gpu_tts/pan_test/regie.json)
  -> Emoji-Vorlage -> Chatterbox DE + LoRA (mix_v1 adapter / mix_v2 step_01250) -> VC auf Werkstimme -> ggf. Fluestertrick.
  Varianten grandma_mix_v1/_v2, herr_a_mix_v1/_v2; Einzelsaetze + szene_<variante>.wav + hoerliste.txt. Kosten ca. 0,30 $.
- Bewertungsordner mix_v2 (Peter Pan): hoeren nur basis / mix_v1 / lora_bester (= mix_v2) bzw. herr_a_*; lora_letzter + ramona_* = nur Messung.
- 24.10. 09:30 CK: "Clarke" mit hoerbarem e -> pan_test lief ohne Aussprache-Lexikon (Werk hatte keins, Skript nutzte Rohtext). Fix: pan_test.py wendet
  work/aussprache_de.json an (erzwingen, da Test); start_pan_test.bat baut das Lexikon vorher (tools/aussprache_lexikon.py). Lauf 1 (09:23) = ohne Lexikon.
- 24.10. 09:39 CK: Prosodie im Pan-Test kaum hoerbar (Lauf 1). Aufgedreht fuer Saetze mit Stimmung: exaggeration 1.0 (vorher 0.5), cfg_weight 0.3 (0.5), temperature 0.9 (0.8); neutral unveraendert. Konstanten EXAG_EMO/CFG_EMO/TEMP_EMO in gpu_tts/pan_test.py.

## 29.10.2026 — AP 62: Hoerspiel-Hybrid als Pipeline-Stufe (Teil 1: Punkte 1, 2, 3, 5 gebaut; Punkt 4 OFFEN)
Sicherung: archive/2026-10-29_62/ (PROJEKTSTAND, hybrid_einbau.py, tts_client.py, ap60_gemini.py).
- Punkt 1: pipeline/s510_hoerspiel_hybrid.py, run.py AUDIO_LINE nach 500 eingehaengt (Key 510), done = _hybrid_done. Stufe 510 ist AUS, solange config.HYBRID_WERKE leer ist.
- Punkt 2: config.TTS_SPRACHFELD = True; pipeline/tts_client.py: _speech_cfg() setzt "language" aus lang_code (Rueckfall ohne Feld bei API-Ablehnung, mit Ausgabe). "pronounced as in English" aus tools/hoerprobe_mehrstimmig.py gestrichen (neu_vertonen.py war schon sauber).
- Punkt 3: Montage aus hybrid_einbau.py in s510; wiederaufnehmbar (_hybrid/<lg>/fertig.txt), Fortschritt je 25 Saetze, Fehler (ausser Policy) stoppen die Batch. Protokoll work/hybrid_<lg>.json.
- Punkt 5: Gemini-"policy" -> Satz bleibt unveraendert, Eintrag "policy" im Protokoll (Interpretation: kein Ersatz durch eine andere Fassung).
- Testmodus: config.HYBRID_TESTDIR setzen; schreibt nur dorthin, kopiert Produktions-Audio, 520-Tags bleiben unberuehrt.
- OFFEN Punkt 4: Schnitt noch CPU (_Aligner). Verlagerung auf Modal (gpu L4/A10G/T4, CPU-Rueckfall) noch nicht gebaut.
- OFFEN: 520 (Wortzeiten) hat in run.py done = Datei vorhanden, laeuft nach 510 also nicht von selbst neu. Nach Einbau 520 manuell fuer die Werke starten.
- NICHT gelaufen (nur Code geprueft, py_compile ok). Test-.bat und Kostenschaetzung noch nicht vorbereitet.
- 29.10. Nachtrag Punkt 4 GEBAUT (nicht gelaufen): gpu_fa/schnitt_modal.py (Modal, gpu L4/A10G/T4, Volume readlayer-tts, Pfad s510/<werk>/<lg>/<stamp>/);
  s510 holt Schnittzeiten dort (config.HYBRID_SCHNITT="modal"), bei Modal-Fehler CPU-Rueckfall mit Log. Alte Version: archive/2026-10-29_62/s510_vor_modal.py.
  Offen: Modal-Lauf und Schnittzeiten-Probe; Upload je Lauf ca. 2 WAVs je gemischtem Satz (Alice ~700).
- 29.10. Test-Vorbereitung GEBAUT (nicht gelaufen): start_ap62_test.bat [liste|los] -> tools/hybrid_test_ap62.py
  (alice-s-adventures-in-wonderland, Kap. VII = c007, de+en) -> Testordner tests/ap62/<werk>/ (Audio nur Kapitel kopiert). Produktion unberuehrt.
  Kapitelfilter in s510 (run(chapter=...), liste=True: nur Kosten, kein Gemini/Modal). Erst 'liste' fahren, dann Freigabe fuer 'los'.
