# PROJEKTSTAND — Read Layer

## AP Segment-Lautheit 520 – CODE ERLEDIGT 27.11.2026, Hoertest CK offen (Regler aus, Endfassungen unveraendert)
ANLASS (CK): woertliche Rede teils leiser als der Erzaehler. MESSUNG Monte Cristo DE (LUFS, Segmente >= 3 s): Hoerbuch unauffaellig (Figuren +0,8 LU),
  Hoerspiel: Mercedes 38 %, Danglars 32 %, Caderousse 29 %, Fernand 29 % der Segmente > 3 LU unter dem Erzaehler. Ursache: s511.montage gleicht Figuren nur
  im selben Satz per RMS an den Erzaehler an (reine Figurensaetze gar nicht), 520 normiert nur ganze Kapitel.
NEU pipeline/lautheit.py: Segmente (Spannen 500, Hoerspiel rekonstruiert aus 500 + 510 schnitt.q) vor dem Zusammenfuegen auf -19 LUFS (pyloudnorm);
  < 3 s per aktivem RMS + Kalibrierung (Median LUFS-RMS je Figur/Kapitel, sonst config.LAUTHEIT_KALIB_STD 2,5); Gain +-10 dB, 20-ms-Rampen;
  Offsets je 430-Anweisung config.LAUTHEIT_OFFSETS (fluestern -3, leise -1,5, seufzen/gaehnen -1,5; book.json lautheit_offsets).
  Kapitel-Mastering: acompressor 2:1 ab -20 dBFS bei -23-LUFS-Arbeitspunkt, Lautheit aufs Kapitelziel, True-Peak-Limiter (4x ueberabgetastet,
  nachgeregelt gegen ffmpeg ebur128) -3 dBTP.
s520: Regler segment_lautheit (Standard AUS = bisheriger Weg bitgleich, Kapitel-Hash unveraendert), segment_lufs -19, segment_kurz_s 3,
  segment_gain_max 10, master an|aus; an -> peak_max hoechstens -3. Report work/520_lautheit_<lg>_<spur>.csv, meta.kapitel segment/master.
  begrenzen(spitzen=…), schneiden(mit_start=True) rueckwaertskompatibel. Tests: tests/test_lautheit.py 10 gruen, test_s520 + test_s510 52 gruen.
A/B OHNE NEURENDERN: tools/lautheit_test.py <werk> --kapitel c002,c003,c004 -> work/_520_lautheit_test/de/ (<kap>_vorher/_nachher.wav in App-Reihenfolge,
  lautheit_<spur>.csv, hoerliste.md). Endfassungen/Manifeste/status unberuehrt, 0 $. Ergebnis Hoerspiel c002–c004: Figurensegmente > 3 LU unter Erzaehler
  vorher 3–50 % je Figur -> nachher 0–4 %; Kapitel -19,0 LUFS, True Peak <= -3 dBTP.
OFFEN (CK): (1) c002–c004 vorher/nachher hoeren (Naehte, Fluestern/Leise, Kompression) (2) bei Freigabe: py -3.11 -m pipeline.s520_audio_pruefung
  le-comte-de-monte-cristo-1-1 --segment-lautheit an --lufs -19  (Whisper Modal fuer geaenderte Dateien; danach 530 neu, 710 neu exportieren).
  Sicherung archive/2026-11-27_lautheit/.

## AP Qwen-Stimmdesign – 59 STIMMEN IM ARCHIV 26.11.2026, Casting per Hoertest offen (Prompt PROMPT_qwen_stimmdesign.md)
UPDATE 26.11. nachmittags: CK-Auswahl stimmen_archiv/"auswahl QWEN.json" (59: 30 m, 24 w, 5 k; Rest wegen engl. Faerbung/Betonung verworfen).
  ENTSCHIEDEN (CK): Stimmen treffen Matrix-Charakter nicht immer -> Ablage NUR nach Geschlecht + Stimmlage, Casting nur im Hoertest.
  Name <g>_<lage>_<nr> (m: tief < 95 Hz <= mittel <= 125 Hz < hoch; w: 190/240 Hz), Kinder k_01..k_05 ohne Lage; Nr aufsteigend nach F0 (DE-Clip).
  Ergebnis: m_tief 7, m_mittel 17, m_hoch 6, w_tief 4, w_mittel 15, w_hoch 5, k 5. Zuordnung Matrix-ID+Seed -> Name: tools/qwen_stimmen/zuordnung.json.
  EN-Referenzen per Base-Klon aus DE: 59/59, A10G 333 s, 0,10 $. ECAPA DE<->EN meist 0,6–0,88; AUSREISSER k_03 0,08 (EN-Klon andere Person?) und w_hoch_04 0,47 -> anhoeren.
  Steckbrief: merkmale nur geschlecht + tonlage (Kinder + alter kind), casting "hoertest", herkunft_prompt (nur Nachweis), herkunft_matrix, stimmlage, grundton_hz/_en_hz,
  sichtbarkeit katalog, rechte, speaker_embedding de/en, referenz_weg. stimmen.json 40 -> 99, alte 40 unveraendert.
  pipeline/voice_registry.verfuegbar: casting == "hoertest" wird von 410 NIE automatisch besetzt (test_s410 16 gruen). Sicherung archive/2026-11-26_qwen/.
  Kosten AP gesamt: Probe 0,19 + Kandidaten 0,99 + EN-Klone 0,10 = 1,28 $.
  HOERTEST ALICE KAP. 7 BEREIT (26.11. 16:08): NEU tools/alice_hoertest.py (bauen | vc | erzaehler | seite | alle, --kandidaten "Fig=s1,s2;...").
    Figuren: je 4 laengste Quellzeilen (3–15 s) aus gpu_overlay/alice_c007_fish_de/src (Fish-Erzaehler mit Regie) -> Chatterbox-VC je Kandidat,
    Paket gpu_overlay/alice_c007_hoertest_de, 108 Clips, A10G, 0,06 $. Kandidaten nur nach Geschlecht+Lage: Alice k_03–05 + w_hoch_01–05,
    Hutmacher m_mittel_02/05/08/11/14/17, Maerzhase m_hoch_01–06 (Lagen bewusst getrennt), Haselmaus m_tief_01–07.
    Erzaehler: Absatz Kap. 7 (472 Zeichen) ueber Fish API mit Qwen-Klon als Referenz: w_tief_01–04, w_mittel_02/07, m_tief_04, m_mittel_08 (8 neue private Fish-Stimmen
    im Register stimmen_archiv/_fish/fish_ids.json), 0,06 $. Vergleich: "quelle", "bisher" (Gemini-Ziel / grossmutter_a).
    Seite tools/alice_hoertest/hoertest.html -> casting_auswahl.json {Figur: Stimme}. Kosten tools/alice_hoertest/kosten_log.jsonl.
    fish_motor.fish_id: Transkript beim Anlegen aus steckbrief referenzen[lg].text (Qwen-Clips = Nordwind-AUSZUG), sonst wie bisher ganzer Nordwind. test_fish gruen.
    Abbruch 1. Lauf: Rechner schlief -> Modal-App gestoppt (APP_STATE_STOPPED), Client hing; Neustart mit Wachhalten.
    HINWEIS Tests: site-packages enthaelt ein fremdes Paket "tests" -> "py -m unittest tests.test_fish" findet die Projekttests nicht (test_s410 laeuft aus tests/).
  CK-WAHL 26.11. (tools/alice_hoertest/"casting_auswahl alice.json"): Erzaehler w_tief_02, Alice w_hoch_02, Hutmacher m_mittel_04, Maerzhase m_hoch_01, Haselmaus m_tief_01.
  KAP. 7 KOMPLETT NEU (alice_hoertest.py kapitel <auswahl>): Fish API alle 269 Beitraege in w_tief_02 (Figuren mit Regie, wie ERZ_ALLE) 0,36 $ -> VC 147 Figurenbeitraege
    (gpu_overlay/alice_c007_qwen_de, A10G) 0,06 $ -> tools/alice_hoertest/de/fish_erz_vc_qwen_c007_de.wav (22:32; alt 19:59). Vergleich + Zeitmarken: tools/alice_hoertest/hoervergleich_kap7.md.
    Alte Dateien unangetastet. Zweck des Tests = Eignung der Qwen-Stimmen als VC-Ziel (kein Umbesetzen von Alice, casting.json bleibt).
    CK-URTEIL 26.11.: "nicht perfekt, aber sehr gut fuer den ersten Schuss" -> Qwen-Designstimmen als Chatterbox-VC-Ziel und Fish-Referenz tauglich.
  ERLEDIGT-ALT: CK hoert + waehlt -> Kapitel 7 komplett mit neuer Besetzung (Figuren: VC aller 147 Zeilen; Erzaehler neu ueber Fish ~0,5 $, falls nicht grossmutter_a)
    -> Hoervergleich zu tools/fish_test/de/fish_erz_vc_c007_de.wav. Cockpit-Casting fuer casting=hoertest pruefen.
STAND VORMITTAG (Kandidaten):
Ersatz Gemini Voice Design (Lizenz: keine Nutzung fuer konkurrierende Modelle) durch Qwen3-TTS 1.7B VoiceDesign + Base (Apache-2.0). Nur neue Dateien, nichts Bestehendes geaendert.
NEU gpu_qwen/qwen_modal.py (App readlayer-qwen-stimmen, Volume readlayer-qwen /out/<paket>/ = Resume, GPU L40S|A10G): Funktion erzeugen(jobs) mit design (VoiceDesign, Stapel 8),
  klon (Base, Stapel 8, Rueckfall einzeln), ableiten (Tonhoehe+Formanten, Kinder aus Frauenstimme); embeddings() = ECAPA (speechbrain, wie 540) auf CPU. Pegel -16,5 dBFS wie Fish.
  Cockpit spaeter: modal deploy + Function.from_name("readlayer-qwen-stimmen","erzeugen") (Aufgabe 6, gleiche Funktion).
NEU tools/qwen_stimmen.py: matrix | kandidaten | katalog | referenzen | uebernehmen | xl; Matrix tools/qwen_stimmen/matrix.json = 72 Stimmen:
  30 m + 30 w (Alter jung/jungerw/mittel/reif/alt x Charakter warm/kuehl/verschmitzt/nervoes/rau/weich, je eigene Eigenheit), 10 Kinder direkt + 2 abgeleitet; 18 Erzaehler markiert.
  IDs m_<alter>_<charakter>, w_…, k_<j|m>_<klein|gross>_<art>; Beschreibung DE + EN-Instruct (Studio trocken, "keine reale Person").
BEFUND Probe 26.11. (probe_v1): dieselbe Beschreibung je Sprache getrennt designt = andere Person (ECAPA DE<->EN 0,27). Base-Klon aus DE-Clip: EN 0,64 / ZH 0,83 / DE-Kontrolle 0,95.
  -> ENTSCHEIDUNG Ablauf: Designstimme NUR in DE (Anker), weitere Sprachen per Base-Klon aus dem gewaehlten DE-Clip (Befehl referenzen). Akzent im EN-Klon nur per Gehoer pruefbar.
LAUF matrix_v1: 70 Stimmen x Seeds 11/22/33 DE (Nordwind-Auszug, 20–37 s, Median 27 s) + 6 abgeleitet = 216 Clips, 0 Fehler, 96 min Audio, RTF 0,31, 30 min L40S, 0,99 $ (Modal-Anzeige 1,07 $ inkl. ECAPA-CPU).
  Probelaeufe 0,19 $. Kostenlog tools/qwen_stimmen/kosten_log.jsonl.
  F0-Mediane (Hz): m jung 138 / jungerw 116 / mittel 105 / reif 109 / alt 107; w jung 291 (hoch!) / jungerw 226 / mittel 208 / reif 211 / alt 217; Kinder ~290.
  Abstand (ECAPA naechste andere Stimme): Erwachsene 9/171 > 0,85 (meist w_jung_* untereinander); Kinder untereinander 0,89–0,93 = kaum unterscheidbar, Jungen ~ Maedchen.
OFFEN (CK): (1) tools/qwen_stimmen/hoerkatalog.html hoeren, je Stimme Seed waehlen, auswahl.json exportieren
  (2) py -3.11 tools/qwen_stimmen.py referenzen auswahl.json --paket matrix_v1   (EN-Klon, ~0,35 $; --sprachen en,zh fuer ZH)
  (3) py -3.11 tools/qwen_stimmen.py uebernehmen auswahl.json --paket matrix_v1  -> stimmen_archiv/<id>/ klon_de/en.wav + steckbrief + stimmen.json
  Steckbrief-Felder neu: sichtbarkeit (katalog | exklusiv:<mandant>; NICHT status, das bleibt Lebenszyklus kandidat/freigegeben/abgelehnt – 410/540/voice_registry filtern darauf),
  herkunft (design|sprecher), herkunftsvermerk, rechte {inhaber, laufzeit, werke, sprachen, territorien}, mandant, speaker_embedding je Sprache, aehnlichkeit, referenz_weg, seed.
  Kinder: direkte Beschreibung klingt laut ECAPA sehr gleich -> Hoervergleich direkt vs. abgeleitet (k_m_klein_abgeleitet, k_j_gross_abgeleitet), ggf. Beschreibungen schaerfen.
  w_jung_* liegen hoch (F0 ~290 Hz) – beim Hoeren pruefen, ggf. "medium pitch" statt "bright, medium-high".
  Fluester-Satz nicht im Referenz-Clip (VoiceDesign kann nicht satzweise wechseln; Fluestern ueber Fish-Tags bei der Vertonung).
NOCH NICHT GEMACHT: Aufgabe 5 (Casting Alice auf Matrix umbesetzen + Kap.-7-Hoervergleich, nach Uebernahme), Cockpit "Neue Stimme erzeugen" + Hoerkatalog im Casting,
  Exklusiv-/Sprecherklon-Wege (Rechtenachweis, Einwilligung, Aehnlichkeitsschwelle), Gemini-Stimmen aus alten Beschreibungen neu erzeugen.

## AP Fish Drama 3 auf Modal – CODE ERLEDIGT 25.11.2026, Modal-Lauf + Abnahme offen (Prompt claude/PROMPT_fish_modal_hosting.md)
Sicherung: archive/2026-11-25_fish_modal/ (s500, s503, fish_motor, fish_probe, config, werk_api, monitor.html, run.py, PROJEKTSTAND); Vor-Paket committet e3cc2f1.
Quellen Gewichte (gelesen 25.11.): HF fishaudio/drama-3 (35B MoE, 3B aktiv, FP8-Experten + BF16, Fish Audio Community License), Inferenz fish-speech
  (tools/api_server.py, msgpack /v1/tts, references = Audio + Transkript), >= 48 GB GPU (FP8), Python 3.12, cu129, kein --compile; Codec-Fallback s2-pro/codec.pth.
  Lokaler Server liefert KEINE Wort-Zeitmarken -> MMS_FA (pipeline/fa_mms.py) im selben Container.
Schritt 1 CODE ERLEDIGT (ungetestet auf Modal): NEU gpu_fish/fish_modal.py – Image nvidia/cuda 12.9 + Python 3.12 + fish-speech (Commit wird im Bericht protokolliert),
  Volume readlayer-fish (/drama-3 Gewichte, /out/<key>.* Ergebnisse = Resume), GPU-Liste READLAYER_FISH_GPU (Standard H100,L40S), Server im Container, 4 parallele Anfragen,
  je Block WAV -> 24 kHz mono 16 bit + MMS_FA-Woerter [{w,a,b}]; Modell-Pruefung ueber Checkpoint-config.json (MODELL drama-3, sonst Abbruch = garantiert kein Rueckfall).
  Bericht: GPU, MODELL, COMMIT, KALTSTART, AUDIO, TTS/RTF, WALL. Einmalig Gewichte: py -3.11 -m modal run gpu_fish/fish_modal.py --gewichte-laden (CPU).
Schritt 2 ERLEDIGT: Weiche fish_motor.weg(b, lg, zeichen, einzel) – book.json fish_weg api|modal|auto (oder {lg: weg}), Standard auto; Kundenwerk (mandant != somnio) -> modal;
  Einzelaktion (--satz, Proben) -> api ausser Kundenwerk; auto: Zeichen je Sprache (alle Bloecke inkl. Anweisungen) < config.FISH_MODAL_AB_ZEICHEN (60.000) -> api.
  config.FISH_MODAL_FREI = False bis CK-Freigabe Pruefblock -> modal faellt auf api zurueck (Hinweis), Kundenwerk -> Stopp (Gate weg_<lg>).
  s503: Modal-Stapel modal_stapel() = EIN modal run je Werk x Sprache (Paket gpu_fish/<werk>_<lg>_500, jobs.json + ref/ref.wav + Nordwind-Text), Wiederholungsrunden mit neuem Seed (key Blockhash_v<runde>).
  Manifest-meta fish_weg {lg: weg, grund, wahl, zeichen}, je_sprache weg/weg_grund/modal_bericht, Blockeintrag weg; Blockhash OHNE Weg (Test: Wegwechsel vertont nicht neu).
  Kosten modal: fish_motor.modal_schaetzung (Zeichen -> Audio-s -> GPU-s x RTF 0,25 x H100 3,95 $/h + Kaltstart 300 s, alles Schaetzung in config) in Freigabe/Metrik kosten_je_sprache;
  Ist: usage_log.log_gpu (WALL, gpu aus Bericht, extra kaltstart_s/rtf/audio_s). CLI s500 --fish-weg [LG=]api|modal|auto (setzt book.json). fish_probe: Kundenwerk -> Probe ueber Modal (Paket <werk>_<lg>_probe).
  Tests: tests/test_fish.py TFishWeg (5) + T430.test_500_fish_modal / test_kundenwerk_stopp (Fake modal run) – test_fish 64 gruen.
Schritt 3 VORBEREITET (Lauf durch CK, kostet ~0,03 $ API + ~0,5-1 $ Modal inkl. Kaltstart/Erstdownload): NEU tools/fish_pruefblock.py – ~1.800 Zeichen Alice Kap. 7 DE
  (tools/fish_test/de/block_*.txt, Erzaehler grossmutter_a + [voicing ...]) ueber API und Modal; im selben Modal-Lauf MMS_FA auf das API-Audio (Job mit "audio" in fish_modal.py)
  -> Zeitmarken-Abweichung FA vs. Fish auf GLEICHEM Audio (Wortanfaenge + Schnittgrenzen). Ausgabe tools/fish_pruefblock/<lg>/ (api.wav, modal.wav, bericht.md, modal_bericht.txt), Kosten kosten.jsonl.
  Ablauf CK: (1) einmalig py -3.11 -m modal run gpu_fish/fish_modal.py --gewichte-laden (~40 GB ins Volume, CPU) (2) py -3.11 tools/fish_pruefblock.py
  (3) api.wav vs. modal.wav hoeren, Urteil in bericht.md (4) bei Freigabe config.FISH_MODAL_FREI = True; RTF/Kaltstart aus Bericht in config (FISH_MODAL_RTF, FISH_MODAL_KALTSTART_S), ggf. GPU-Liste.
  RISIKO erster Lauf: Image-Build fish-speech (cu129) + api_server-Flags/Health-Route sind nach Doku gebaut, nicht erprobt -> Fehler im Modal-Log, dann gpu_fish/fish_modal.py anpassen.
Schritt 4 ERLEDIGT (Cockpit Monitor 500): je Fish-Sprache Weg + Grund, Wahl auto/api/modal (-> --fish-weg), Schwelle, Kundenwerk-/Freigabe-Hinweis, Modal-Schaetzung (GPU-min, $, Kaltstart),
  letzter Modal-Lauf (GPU, Kaltstart, WALL, RTF); offen-Spalte "Modal inkl. Kaltstart". Start = "Uebernehmen und 500 starten" (laeuft modal, wenn Weg modal). werk_api _m500_daten fish_weg, _m500_argv fish_weg. node --check ok, test_fish Monitor-Daten/argv gruen.
Schritt 5 TEILWEISE: 540 fuer Fish-Werke: Zielstimme = vc_ziel aus 410 (keine Takes) – s540_trennung.plan_sprache; Modell-Pruefung Self-Hosting ueber Checkpoint (s. Schritt 1);
  Doku: docs/STAGE_SKRIPT.md neu (tools/stage_skript.py mit 430, Texte 500/510/540, Stand 25.11.), Projekt-Doc claude/GATE_NACHTRAG_FISH_430_503_511.md (Nachtrag GATE_KATALOG/GATE_MONITORE/STECKBRIEFE).
  OFFEN: gemischte Motoren je Werk (Gemini/Fish je Sprache) – weiter Stopp ausser --lang (Umbau s500.run: zwei Engines in einem Gate/Manifest, eigenes kleines AP).
Tests (Linux-VM, python3 -m unittest): test_fish 64, test_s500 35, test_s510 33, test_s520 19, test_s530 14, test_s540 21, test_s400/410/420, test_kette, test_status, test_cockpit_werk, test_kunde gruen.
PRUEFBLOCK 25.11. 09:55 (DE, 1.818 Z.): Gewichte im Volume (41,5 GB, 100 s). Modal H100: Kaltstart 65 s, WALL 150 s, ~0,16 $; API ~0,03 $.
  Zeitmarken MMS_FA vs. Fish auf gleichem Audio: Wortanfaenge Median 0,043 s / max 0,142 s, Schnittgrenzen Median 0,024 s / max 0,076 s -> FA-Ersatz traegt.
  CK-Hoerurteil: Modal leiser (gemessen Sprache -22,1 vs. -16,4 dBFS, Pausen 30 % vs. 19 %, 123,5 vs. 115,2 s), Prosodie bei beiden zu schwach, Modal leicht schwaecher.
  -> FIX gpu_fish: Pegel auf -16,5 dBFS Sprache + weicher Limiter -1 dBFS (NACH="pegel1", alte Bloecke im Volume werden neu erzeugt); Kontrollprobe tools/fish_pruefblock/de/modal_pegel.wav.
  Prosodie: Pruefblock hatte nur "[voicing <Figur>]" ohne Steckbrief-Grundhaltung und ohne Moment -> naechster Pruefblock mit 430-Anweisungen.
  Fehlerbehebungen Image: clang (pyaudio), fish-speech in eigener venv /fishenv (protobuf 3.19 brach Modal-Laufzeit).
PROSODIE-STRESSTEST 25.11. 10:16 (tools/fish_prosodie_test.py, Fantasietext, 4 Varianten, fish-speech-Server): CK: Fluestern, Freude, Wut usw. gut abgebildet;
  "stark" (Verstaerker + nonverbal) kaum Unterschied, baut nur unnoetiges Kichern ein -> Anweisungen wie Stage 430 genuegen, Tabelle 430 bleibt. Takes: tools/fish_prosodie_test/de_fishspeech/.
  Kosten: fish-speech-Server arbeitet Anfragen nacheinander ab (RTF 0,56, je Block 2,2 bei 4 parallel) -> ~2,2 $/Audio-h auf H100, teurer als API (~1-1,3 $/h).
UMBAU SGLang-Omni 25.11.: gpu_fish/fish_modal.py ENGINE (Umgebung READLAYER_FISH_ENGINE, Standard sglang; fish = alter Weg, Sicherung archive/.../fish_modal_fishspeech.py).
  sglang-omni in venv /omnienv, sgl-omni serve --model-path /vol/drama-3 --port 8000, /health; POST /v1/audio/speech {input, references [{audio_path, text}], response_format wav}
  (44,1 kHz -> 24 kHz; seed nicht unterstuetzt; Standard temperature 1,0 / top_p 0,9). Bloecke in Teile <= 1.000 Zeichen (vor Tag-Folge "[", sonst Satzende), 16 Bloecke parallel.
  NACH = "<engine>-pegel1" -> Engine-Wechsel erzeugt Bloecke im Volume neu; Download holt nur passende Version. Bericht: ENGINE + Commit.
  Image: ninja-build (SGLang-JIT-Kernel). Referenz > 55 s (SGLang-Limit 60 s) wird per MMS_FA am Satzende gekuerzt (Bericht REFERENZ).
  GEMESSEN 25.11. (Prosodietest, 4 Bloecke, 461 s Audio, H100): KALTSTART 175 s, RTF 0,077 (je Block 0,26), FA 205/205 Woerter, WALL 215 s.
  -> ca. 0,30 $/Audio-h + ca. 0,19 $ Kaltstart je Lauf (fish-speech 2,2 $/h, API ca. 1-1,3 $/h). Config FISH_MODAL_RTF 0,10, KALTSTART 180 s.
  CK 25.11.: SGLang-Takes in Prosodie/Qualitaet hoerbar unveraendert gegenueber fish-speech -> FREIGEGEBEN, config.FISH_MODAL_FREI = True.
  CHATTERBOX-OVERLAY-TEST 25.11. (tools/fish_prosodie_vc.py, Figurenpassagen per VC wie 511): VC glaettet die Prosodie;
  mit Overlay traegt die STARKE Anweisungsvariante besser (ohne Overlay reicht 430-Normal). Schnitt jetzt mit 503-Mechanik
  (erster Lauf: eigene Regel Wortende+150 ms kappte Auslaut-Konsonanten). Idee offen: Figuren direkt in Fish mit Figurenreferenz statt VC.
  UMGESETZT 25.11.: 430 Regler overlay_plus (Std 1, 0-2; --overlay-plus): Figuren mit vc_ziel (= 511-Overlay) bekommen
  Moment-Intensitaet +1 (very/extremely); Beitrag-Feld overlay. Test T430Overlay; tests.test_fish 65 gruen.
TESTWERK Fish-Strasse 25.11. (CK): NEUES Werk = Le comte de Monte-Cristo, Tome I (Gutenberg 17989, franz. Original; Tome II-IV 17990-17992),
  Ziel de Hoerspiel premium, audio_motor fish. ANGELEGT 25.11. (100 auto, Text von Spiegel mirrors.xmission.com, gutenberg.org war down; 727.599 Z.),
  Eignung geeignet/premium (Rede 26 %, 18 Sprecher); 080/090/095 auto, Angebot 30,99 $ (Audio noch Gemini-Basis; Fish-Modal real ~4 $ statt 16,7 $), Weiche modal.
  BEFUND: authors/dumas-a vermischt Vater (1802-1870) und Sohn (1824-1895; Kameliendame) -> author.json Todesjahr 1895; offen (betrifft 4 Werke).
  115/120: franzoesischer Modernisierungs-Prompt (s120 SYS_SPRACHE fr sanft/mittel; passé simple + vouvoiement bleiben),
  s115.MODERN_SPRACHEN + fr -> Monitor 115 erlaubt 'modernisiert'. test_s115 (ohne Prompt jetzt it) + test_s120 gruen.
  FIX 25.11. 410->420: Gate-Entscheidung 410 'frei' (Cockpit/status, auch override) schrieb casting.json-Freigabe erst beim
  naechsten 410-Lauf -> 420 stoppte ('casting.json freigegeben'), keine Zuordnung sichtbar, Korrekturen nur in 420_korrekturen.json.
  Jetzt status.entscheiden/override -> s410.freigabe_nachziehen. Monte-Cristo 1-1 nachgezogen. test_s410 +1 Assert.
  GEMESSEN 500 Monte-Cristo 1-1 (25.11., H100, SGLang 16 parallel): 187 Bloecke, 0 Fehler, AUDIO 30.268 s (8,4 h), KALTSTART 206 s,
  TTS-RTF 0,022 (je Block 0,34), WALL 877 s, Modal-Rechnung 1,15 $ (= 0,14 $/Audio-h; Gemini-Angebot Teil ~8,70 $; Schaetzung 500 war 4,94 $).
  510 VC (Chatterbox, Modal L4/A10G): 2.440 Figurenbeitraege, 0,62 $ (~22 min). TEIL 1 GESAMT AUDIO 1,77 $ = 0,21 $/Audio-h.
  -> Config: FISH_MODAL_RTF 0,025, FISH_ZEICHEN_JE_AUDIO_S 13,3 (gesprochen), KALTSTART 210, NEU FISH_MODAL_AUFSCHLAG 1,2;
  s503: Modal-Schaetzung auf gesprochenen Zeichen (_klartext ohne [..]/<..>; Block-Text 628k vs gesprochen 401k). Nachrechnung 1,27 $.
  LIZENZ drama-3 (Community License, HF LICENSE, gelesen 25.11.): kommerziell + Self-Hosting ok bei Jahresumsatz < 500k USD (inkl. Affiliates,
  Meldung 30 Tage nach Erreichen, 90 Tage Uebergang), KEIN gehosteter Dienst fuer Dritte; eigene Inhalte + gelieferte fertige Audios ausgenommen;
  Pflicht 'Built with Fish Audio'. Grauzone Kunden-Cockpit (Kunde startet Vertonung selbst). CK: Klaerung business@fish.audio erst zum Business-Start.
  IDEE/AP (CK 25.11.): Stimmenensemble als Markenzeichen – Projekt-Doc claude/IDEE_stimmen_ensemble.md (rufname Pflicht, 4 fehlen:
  Vorschlag Henry/Ernest/Douglas/Gordon fuer die Thornton-Stimmen; Sprecherverzeichnis Abspann/710/App + Kennzeichnung KI-Stimmen).
  IDEE/AP (CK wichtig, 25.11.): Stimmvariabilitaet jenseits Tonhoehe – Projekt-Doc claude/IDEE_stimmvariabilitaet.md
  (Prosodie-Merkmale via Fish-Grundhaltung, Timbre via Archiv/Nachbearbeitung; 410-Abstand mehrdimensional: ECAPA + Tempo + Spektrum;
  Statistengrenze lockern; Archiv-Merkmale Timbre). Dazu: dialogreiche Werke = Premium-Kandidaten (Startliste/Pricing).
  BEFUND 210/420 (Monte-Cristo 1-1): 'le pere Dantes' fehlt in 210-Figuren -> 420 gab seine Saetze Louis XVIII (~20 Seg. c002/c005/c010).
  CK 25.11.: bleibt so (Doppelbesetzung, nie gemeinsam in einer Szene). Offen: 210 erkennt Beinamen-Figuren ('le pere X') nicht.
  BEFUND Kapitelerkennung (Monte-Cristo, 25.11.): roemische Einzelbuchstaben-Kapitel V und X nicht als Kapitel erkannt (in IV/IX
  enthalten, Teil 1 = 15 statt 17 Kap.); Kapiteltitel nur roem. Zahl (echter Titel 'Marseille.--L'arrivee.' in Folgezeile fehlt),
  Kap. I traegt Buchtitel. Offen: Regel 118/120 fixen, Werk ab 120 neu (nach Fish-Test). Teil 1 = Kap. I-XVII (bis 'La chambre de l'abbe').
  430 Momente jetzt Kapitel parallel (config.FISH_REGIE_PARALLEL 5; Checkpoint je Kapitel im Haupt-Thread). Anlass: Monte-Cristo 1-1
  sequentiell ~1 min/Kapitel (30 Kap. ~30 min).
  Bekannt flaky: test_s420 test_kaputt_einzeln_neu_dann_rueckfall (Reihenfolge paralleler Aufrufe).
  Probelaeufe zurueckgenommen:
  die-spiegelschwestern (Eignung ungeeignet) und winnie-the-pooh (095 rueckgaengig; je status.json -> work/_to_delete/).
ABNAHME: (a) Pruefblock + CK-Freigabe ERLEDIGT 25.11. (b) OFFEN: anstehendes Werk 430 -> 500 (modal) -> 510 ohne Handeingriff bis Gate (vorher FISH_MODAL_FREI True, book.json fish_weg modal oder > 60.000 Z.).
.gitignore: gpu_fish/*/ und tools/fish_pruefblock/ (Audio/Jobs).

## AP Fish-Regie + Cockpit-Umbau – CODE ERLEDIGT 25.11.2026, Abnahme offen (Prompt claude/PROMPT_fish_regie_cockpit.md, Stand-Doc claude/STAND_fish_test_2026-11-24.md)
Sicherung: archive/2026-11-25_fish_regie/ (s400/410/420/500/502/510, status, kette, trennung, tts_client, hoerprobe, werk_api, monitor.html, server, gpu_overlay, run.py, config, PROJEKTSTAND).
Schritt 1 ERLEDIGT (Bestand): Neue Stage = 430 "Fish-Regie" (zwischen 420 und 500). Motor-Schalter book.json audio_motor ("gemini"|"fish" oder {lg: motor}; Standard gemini).
  Fish ersetzt nur die Gemini-Stufen (premium/drama); basic bleibt Chatterbox. Bis Modal-Hosting: Fish-API (.env FISH_AUDIO_API).
  Befund Alice: Altwerk (kein status.json, 400 ohne Sprechtext, casting.json Schema 1, sprecher.json alt) -> fuer Abnahme ueber die neue Kette erst 095-420 im neuen Format; Happy Prince ist voll in der Kette (Schema 2, 420).
Schritt 2 ERLEDIGT: pipeline/fish_motor.py – motor(roh,lg), grundhaltung() (deterministisch aus Steckbrief, z. B. "voicing the March Hare: giddy, silly, irascible, fast, high-pitched"),
  Fish-Client (tts_zeitmarken = /v1/tts/stream/with-timestamp SSE UTF-8, Alignment je chunk_seq ersetzt + Offset; tts_einfach fuer Proben; fix_wav; Header model drama-3 gesetzt + geprueft -> ModellRueckfall;
  Semaphore 3; Retry 429/5xx), kosten_usd ($15/Mio Bytes, config.FISH_USD_JE_MIO_BYTES), Stimm-Register stimmen_archiv/_fish/fish_ids.json (uebernimmt tools/fish_test/stimmen_fish.json, 10 IDs; fish_id(..., anlegen=True) legt neu an).
Schritt 3 ERLEDIGT (400/410):
  400: Fish-Sprachen (premium/drama + audio_motor fish) ohne Stilzeile/direction (auch Ansagen); Sprechtext/Abbildung/Pausen/Aussprache-Pruefung/Ansagen unveraendert; meta.regie.fish, Metrik fish. test_s400 gruen.
  410: Engine "fish" statt gemini bei Motor fish (Stimme nutzbar = Klon-Clip der Sprache; fish_id aus Register, Modell fish-drama-3). Je Ensemble-Figur fish_grundhaltung (+ _quelle auto|manuell|ohne) und vc_ziel (= Klon-Clip, Ziel fuer VC 510);
    Erzaehler ohne Grundhaltung. Regler casting_regler.grundhaltung, CLI --grundhaltung FIGUR=TEXT | FIGUR=- (ohne) | FIGUR= (auto); bei freigegebenem Casting nur mit --grund.
    Freigabe-Hash (kern) enthaelt Grundhaltung nur wenn vorhanden -> bestehende Freigaben bleiben gueltig. Gate grundhaltung_<lg>_<st> -> Mensch; Hinweis Anzahl Fish-Stimmmodelle.
    Trennung/korrektur unveraendert (VC-Ziel = Archivstimme, d. h. bestehende D-Messung gilt). tests/test_fish.py (Motor, Grundhaltung, SSE, Modell-Rueckfall, 410 Fish) + test_s410 gruen.
Schritt 4 ERLEDIGT: NEU pipeline/s430_fish_regie.py (Stage 430 Fish-Regie). status.STAGES + kette (VORGAENGER 430 <- 420,410; 500 <- 400,410,430; Bedarf nur bei Hoerspiel premium/drama mit Motor fish; sprachen("430")),
  run.py (UMGEBAUT, Stage-Tabelle), config/stage_hilfe.json (430).
  Ausgabe work/430_fish_regie.json: je Sprache beitraege [{id=<tid>_<seg>, tid, seg, fig, text, text_fish, anweisung, moment, absatz, block}] + bloecke [{nr, kap, ids, zeichen}]; Ansagen als Erzaehler-Beitraege.
  Text = 420-Segmente (die schon auf dem 400-Sprechtext liegen); passen sie nicht mehr zum Sprechtext -> ganzer Satz Erzaehler + Hinweis. Statisten/unbekannte Sprecher -> Erzaehler (unbekannt = Hinweis). Erzaehler-Stuecke eines Satzes zusammengefasst.
  Anweisung "[<Grundhaltung>; <Moment>]" + nonverbal ([laughs]/[sighs]/[yawns]/[gasps]); Moment per DeepSeek (Task caster) festes Vokabular, Checkpoint work/ckpt/430 je Kapitel x Sprache.
  Tabelle: Intensitaet 1/2/3 -> slightly/–/very, Regler emotion <=3 eine Stufe runter, >=7 eine hoch (4 = extremely); tempo >=7 brisk, <=3 unhurried; betonung >=4 -> <emphasis>Wort</emphasis>; vortrag fluestern/leise -> <whisper>/<soft>.
  Bloecke 2.000-2.500 Zeichen an Absatzgrenzen, hart an Satzgrenze > 2.500, Kapitelwechsel = neuer Block (Regler book.json fish_regler block_min/block_max/anweisung_max).
  Manuelle Anweisung: work/430_korrekturen.json (an Texthash), CLI --anweisung LG/ID=TEXT ('-' = weg). Gate: Abdeckung -> Stopp; Anweisung > 200, Figur ohne Grundhaltung -> Mensch; Mensch-Freigabe gilt bei gleichem ausgabe_hash.
  Entscheidung: Hoerbuch-Spur einer Fish-Hoerspielsprache = 500-Aufnahme (Erzaehler spielt die Figuren); nur-Hoerbuch -> 430 entfaellt, 500 vertont ohne Anweisungen.
  Tests: tests/test_fish.py T430 (Anweisung, Markup, Checkpoint, manuell, Bloecke) + test_kette/test_status gruen.
Schritt 5a ERLEDIGT (500 Motor Fish): NEU pipeline/s503_vertonung_fish.py, Einstieg in s500.run (alle Audiosprachen mit Motor fish; gemischte Motoren je Werk -> Stopp, ausser --lang).
  Block-Vertonung (430-Bloecke bzw. Hoerbuch-Bloecke ohne Anweisungen) in der Erzaehlerstimme, Lexikon wie 500, ein API-Aufruf je Block (<= 3 parallel, Retry 429). Fish-Modell fehlt -> wird aus klon_<lg>.wav angelegt.
  Schnitt: Fish-Wortzeitmarken gegen Beitragstexte ueber Buchstabenstrom (robust gegen Tokenisierung), Grenze = leisester Punkt in der Pause zwischen den Woertern -> Satz-WAVs fassungen/<lg>/audio/<tid>.wav (Rohfassung fuer 520).
  Manifest work/500_vertonung.json: <lg>/_fish/<erste Beitrags-ID> (Blockhash) + <lg>/<tid> mit spannen [{id, fig, a, b}] (Grundlage 510-VC), block, pause_ms. Block-WAV + Woerter: work/_500/<lg>/fish/.
  Pruefung: Zeitmarken-Abdeckung je Block 0,85-1,15 (sonst bis versuche x neu), je Satz leer/Clipping/Dauer (Median); Modell-Rueckfall -> Stopp. Kosten $/Byte (config STUECKPREISE fish-drama-3, FISH_USD_JE_MIO_BYTES 15) + Freigabe je Sprache wie bisher; usage_log Stueck.
  --satz ID -> Block des Satzes neu. config: FISH_API, FISH_MODELL, MODAL_A10G_USD_H 1,10 (Schaetzung). Tests: test_fish.T430.test_500_fish (Freigabe, Schnitt, Spannen, Resume, Satz neu) + test_s500 gruen.
Schritt 5b ERLEDIGT (510 Overlay -> VC): NEU pipeline/s511_vc_fish.py, Einstieg in s510.run (Hoerspiel-Sprachen mit Motor fish; gemischt -> Stopp). NEU gpu_overlay/vc_modal.py (Kern overlay_gpu.py/ChatterboxVC,
  laedt nur das eine Paket als Zip hoch, GPU-Fallback L4/A10G/L40S; Start aus der Pipeline per subprocess "modal run", kein .bat).
  Quelle = Figurenspannen aus dem 500-Manifest, Ziel = vc_ziel aus 410; VC-Cache work/_510/<lg>/vc/<id>.wav (+ index.json), Quellen work/_510/<lg>/src/<id>.wav (Hoerliste vorher/nachher).
  Montage je Satz: korrektur[lg] (Praat, wie bisher), Lautheit an die Erzaehlerstuecke, Ueberblendung -> fassungen/<lg>/hoerspiel/<tid>.wav; Manifest 510_overlay.json (engine fish-vc) wie Gemini-Gleis (fuer 520).
  Pruefung je Beitrag: Laenge VC/Quelle in [dauer_min, dauer_max], Nahtsprung <= naht_db, VC fehlt -> Hoerliste 510_pruefung.json (+ beitraege vorher/nachher). Kosten GPU-s = Dialog x 0,25 + 90 s Laden -> A10G-Preis, Freigabe wie 510; usage_log GPU aus WALL-Zeit.
  Werkzeug-Check modal/parselmouth -> Stopp. Hoerspiel-Freigabe immer Mensch (gilt bei gleichem ausgabe_hash). Test: test_fish (500 -> 510 Fish-Kette) + test_s510/test_s520 gruen.
  OFFEN: 540 (Trennung) nutzt Gemini-Takes (take_dir) – fuer Fish-Werke noch nicht angepasst (Figurenstimmen liegen als VC-Cache vor).
Schritt 6 ERLEDIGT (Cockpit): Patches archive/2026-11-25_fish_regie/patch_werk_api.py + patch_monitor.py (einmalig angewandt). NEU pipeline/fish_probe.py (Hoerproben: figur = Erzaehler + Grundhaltung [--vc: + Modal-VC + Korrektur], beitrag = 430-Beitrag mit Anweisung; Ablage work/_probe/fish/<lg>/, proben.json).
  Monitor 400: Stilzeile fuer Fish-Sprachen ausgeblendet, Sprachknopf "premium · Fish, ohne Stilzeile".
  Monitor 410: bei Engine fish Spalte "Fish-Grundhaltung · Probe" (Feld je Figur, '-' ohne, leer automatisch -> --grundhaltung; Knoepfe Fish-Probe / + VC), VC-Abstand Figur<->Figur in HT (rot < 2 HT), Korrektur wie bisher.
  Monitor 420: Hinweis "Zuordnungsfehler = falsche Stimme". NEU Monitor 430: Beitragsliste je Kapitel (Figur, Text mit Markup, Anweisung editierbar, Moment), Figurfilter, "anhoeren" (Fish-API-Probe), Regler Bloecke/Anweisung, Momente neu.
  Monitor 500: Engine/Motor Fish + Modell + Quelle, offen in Saetzen/Bloecken/Bytes/$, Block-Hoerliste (Audio, Zeitmarken-Abdeckung, "Block neu vertonen" = --satz erster Satz).
  Monitor 510: Box "Fish -> VC" (Figuren mit VC-Ziel/Grundhaltung, Korrektur-Regler je Figur -> s510 --korrektur mit Grund, Beitraege vorher Fish / nachher VC je Figur). Kosten 510 in GPU-min/$.
  NICHT gebaut: "Start Modal aus Cockpit" fuer 500 (erst mit Hosting-Paket; 510-VC startet Modal bereits aus der Pipeline). JS-Syntax geprueft (node --check), Tests test_fish (inkl. Monitor-Daten/argv) + test_cockpit_werk/test_kunde gruen.
Schritt 7 ERLEDIGT (Pruefung): Live-Probe Fish-API aus der Pipeline (fish_motor.tts_zeitmarken, Erzaehler grossmutter_a DE, 104 Bytes ~0,002 $): SSE/Umlaute/Zeitmarken ok, Tags nicht in den Zeitmarken,
  Schnitt in die Pause (Grenzen 2,04 s / 3,90 s bei Wortpausen 1,68-2,56 / 3,76-3,92). BEFUND: Fish-Antwort traegt KEINEN Modell-Header -> Rueckfall auf s2.1-pro ist per Header nicht pruefbar (Request-Header model: drama-3 wird gesendet; Pruefung greift nur, falls Fish einen Header liefert).
  Tests: test_fish, test_s400/410/420/500/510/520, test_kette, test_status, test_cockpit_werk, test_kunde gruen (test_kunde einmal flaky: offener Socket). Nicht committet (git braucht Loeschrecht).
ABNAHME (CK, Cockpit, ohne tools/fish_test):
  1. Werk waehlen: Alice ist Altwerk (keine Bestellung/produkte, kein status.json, 400 ohne Sprechtext, casting Schema 1) -> erst Bestellung 095 (de+en Hoerspiel premium) und Kette bis 420 im neuen Format;
     alternativ Kap. 7 als Teilwerk. Danach book.json "audio_motor": "fish".
  2. 400 neu pruefen (Fish ohne Stilzeile) -> 410 neu (Engine fish, Grundhaltung pruefen; Maerzhase: Grundhaltung staerker + VC-Abstand zum Hutmacher in HT ansehen, ggf. Korrektur Tonhoehe/Formant; Fish-Probe / + VC) -> Freigabe.
  3. 420 -> 430 (Momente DeepSeek, Anweisungen ansehen/anhoeren) -> 500 (Kostenfreigabe Fish-API) -> 510 (Kostenfreigabe GPU, vorher/nachher anhoeren, Freigabe) -> 520.
  4. Vergleich mit tools/fish_test/de/fish_erz_vc_c007_de.wav.
OFFEN: 540 fuer Fish-Werke (Takes -> VC-Cache); gemischte Motoren je Werk (Stopp); Start Modal fuer 500 aus Cockpit erst mit Hosting-Paket; Modell-Header-Pruefung (s. o.); docs/STAGE_SKRIPT.md + Projekt-Docs GATE_KATALOG/GATE_MONITORE/STECKBRIEFE um 430 ergaenzen; Fish-API-Key rotieren (aus STAND-Doc).

## AP Kunden-Cockpit – Punkt 1+2 ERLEDIGT 23.11.2026 (Commit dcd42cb; Sicherung archive/2026-11-23_kunde/)
- Rollen (pipeline/s080_mandant.py): neu autor; KUNDEN_ROLLEN verlag/autor; ist_kunde(), eigenes_werk() (verlag auch ueber "mandanten"), tarif() (Nutzer > Mandant > pay-per-job). config/rollen.json: Testkunde verlag-demo (Tarif basic, mandanten user:smoketest -> Smoke-Werk u-smoketest-the-mirror-sisters).
- Anmeldung cockpit/anmeldung.py: Kennwort-Hash (pbkdf2) als "zugang" in rollen.json, setzen: py -3.11 -m cockpit.anmeldung setzen <nutzer>. Sitzung per Cookie (HttpOnly, SameSite=Strict, 12 h, nur im Speicher). Testzugang verlag-demo: config/demo_zugang.txt (gitignored).
- Server (cockpit/server.py): Schranke vor jeder Route. Kundensitzung -> 403 auf allen internen Routen (/, /werk, /monitor, /api/werk..., /datei, /paket.zip, Upload, POSTs). Ohne Sitzung: eigener Rechner = intern wie bisher, von aussen 401. Angemeldete Sitzung schlaegt ?wer=/Formular-wer. Fehlertexte fuer Kunden ohne Details.
- Kunden-API cockpit/kunde_api.py (Whitelist): GET /api/kunde/ich | werke | werk/<id> (fremd/unbekannt -> 404). Admin lokal: ?als=<kunde> zeigt die Kundensicht. Seite /kunde (cockpit/kunde.html): Anmeldung, Werkliste, Werk mit Produkten (Sie-Form).
- Tests: tests/test_kunde.py (9, gruen; u. a. 403-Liste, 401 von aussen, Suche nach verbotenen Begriffen); test_s080, test_cockpit_werk gruen.
- OFFEN (naechste Punkte): 3 Preismodul pipeline/preis.py (mit AP Kostendeckel), 4 Fortschritt/ETC, 5 Schrittleiste + Freigaben (Bestellung, Endabnahme zuerst), Downloads ueber /api/kunde (nicht /datei), 6 Abnahmetest gegen echte Antworten. Serverbindung bleibt 127.0.0.1 – fuer echten Kundenzugang Freigabe nach aussen (HTTPS) noch zu klaeren.

## AP Tausch 520/530 – ERLEDIGT 23.11.2026
ACHTUNG Nummern: Seit 23.11.2026 gilt 520 = Audio-Pruefung (vorher 530), 530 = Wortzeiten (vorher 520), 535 = Wortbruecke (vorher 525, Teil von 530). Aeltere Prompts, Notizen, BOARD-/AP-Dateien, Logs und dieser PROJEKTSTAND unterhalb dieses Abschnitts nutzen die ALTEN Nummern.
- Code: pipeline/s520_audio_pruefung.py, s530_wortzeiten.py, s535_wortbruecke.py; tests/test_s520.py (Audio) / test_s530.py (Wortzeiten); status.STAGES, kette.VORGAENGER (650 haengt jetzt an 520), run.py, Cockpit (werk_api, monitor.html), stage_hilfe.json, config, usage_log (TEIL 535->530), gpu_fa/gpu_tts/gpu_sprache, Altweg-Tools. Ausgaben work/520_pruefung_<lg>.json, 520_hoerliste, 520_entscheidungen; work/530_wortzeiten_<lg>[_hoerspiel].json, 530_pruefung, 530_korrekturen, 535_wortbruecke.json; einheit sekunden_clip_relativ_endfassung_520.
- Migration tools/migration_520_530.py --trocken|--los (Marker work/_migration_520_530.json): 19 Werke umbenannt (16 authors, 2 users + Smoke); status.json bei Kunst des Krieges, Happy Prince, Smoke-Werk, Peter and Wendy. ausgabe_hash 530 (Schluessel 535) und 700-Scopes neu gerechnet, Signaturen nachgezogen -> Freigaben gueltig. Vergleich vorher/nachher: Zustaende, Gates, Ruecksprung, Signatur, Stand identisch; 700-Guard trocken: Endfassung 520 + Wortzeiten 530 ok.
- Doku: docs/STAGE_SKRIPT.md neu erzeugt (PDF nicht), docs/Pipeline_Strang_Matrix.xlsx Zeilen getauscht. OFFEN: Projekt-Doc GATE_KATALOG.md (nur im Projekt, kein lokale Kopie) -> Nachtrag claude/GATE_KATALOG_NACHTRAG_520_530.md; ebenso GATE_MONITORE/STECKBRIEFE/STAGE_SKRIPT im Projekt noch alt.
- Tests: alle Testdateien einzeln gruen bis auf test_s120_fremd (1 Fehler 'p. 12' statt 'p. douze', Umgebung/FR-Zahlwort, nicht vom Tausch).

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
- ERLEDIGT 21.11.2026: AP "Nachbar-Stages bauen" (Eintrag 2026-11-21 unten). NAECHSTES AP: eigene Monitore 620/630 (gemeinsamer ePub-Monitor), 640, 650, 700, 710 – Steckbriefe vorher mit CK (Schema GATE_MONITORE.md). Startprompt: Projekt-Doc claude/PROMPT_monitore_620-710.md; Todo-Liste gesamt: claude/TODO_2026-11-22.md.
- ERLEDIGT 22.11.2026 (Claude, Chat): Deutscher Modernisierungs-Prompt Stage 120. s115_fassung.MODERN_SPRACHEN = ("en", "de"); s120_modernisierung: SYS_SPRACHE {en: SYS, de: {sanft, mittel}} + _sys(param); param["sprache"] nur bei Quellsprache != en (Parameter-Hash englischer Werke unveraendert, kein Neu-Modernisieren). Prompt de: Rechtschreibung auf heute (dass, Ue->Ü, Thür->Tür ...), veraltete Woerter ersetzen, Namen/Umschriften und Verse erhalten. test_s115: Beispiel "ohne Prompt" von de auf fr umgestellt. Tests test_s115 + test_s120 gruen; test_s120_fremd TKette 400 schlaegt nur ohne num2words fehl (Linux-VM, unabhaengig). Anlass: book-of-war-navarra / die-kunst-des-krieges (Navarra 1910). Git-Commit steht aus.
- VON CK ZU TESTEN (22.11.2026): Falle 2 (Freigeben gibt offene Teile mit frei); Art of War Satzenden nach Fix 530 anhoeren (Deckel-350-ms-Faelle auf Atmer pruefen); Art of War 700/710 laufen lassen.
- VORGEMERKT (CK 21.11.2026): AP "Kostendeckel + Pay-per-Job" – 095 fuehrt je Posten Selbstkosten, Deckel (Puffer, Vorschlag +30 %) und Kundenpreis (Deckel + Spanne je Mandant, config); eine Freigabe in 095 = Auftrag + Deckel; kostenpflichtige Stages (300/310/330, 500, 510, 610) laufen bis zum Deckel durch, Ueberschreitung -> Stopp, Ruecksprung 095; Kostenfreigabe je Sprache in Monitor 500/510 und die Sperre aus Falle 1 entfallen; Werksende: Preis/Deckel/Ist nebeneinander. Wartet auf Ergebnisse einer anderen Session (CK).
- UX-STOLPERSTEINE (CK 22.11.2026, Sammelliste fuer den UX-Durchgang nach dem Monitor-Bau; Pruefung je Stage aus Kundensicht: versteht ein Laie, was die Stage will? genau ein sichtbarer naechster Knopf? was darf ein Kunde sehen?):
  1. Kostenfreigabe ueber 0 $ (500/510): Freigabe nur unten im Monitor-Kasten 'Kostenfreigabe je Sprache', Gate-Kopf zeigt nur Hinweis; 'Freigeben' gesperrt -> nur 'Anhalten' sichtbar. Sofortfix Kleinbetrag 22.11.; Loesung = Kostendeckel-AP.
- NACH ALLEN MONITOREN (CK 15.11.2026): Nummern 520/530 tauschen (Laufreihenfolge ist 530 -> 520; Audio-Pruefung soll 520, Wortzeiten 530 heissen). Umfang: Module s520/s530 + Tests, Checkpoints work/520_*/530_* in allen Werken (Umbenennungsskript mit Ruecknahme wie 18.10.), kette.VORGAENGER/status.STAGES/run.py, Gates/Ruecksprungziele, Monitore + stage_hilfe.json, GATE_KATALOG/GATE_MONITORE/STAGE_SKRIPT.
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

## 31.10.2026 — AP 62 ABGENOMMEN (Test Alice Kap. VII, c007, de+en)
- Lauf 30.10.: Schnitt auf Modal (CPU-Rückfall nicht nötig), 102/102 je Sprache eingebaut, 0 Policy, 0 ohne Schnitt. Takes aus Vorlauf, keine neuen Gemini-Kosten.
- Korrigiert: Modal-Image ohne s525 (ergänzt), Testpfad doppelt verschachtelt (aufgelöst), Audio auf Erstlauf zurückgesetzt, fertig.txt -> fertig_altlauf.txt.
- Hörprobe: bestanden (durch Christian). Testergebnis: tests\ap62\alice-s-adventures-in-wonderland\bd\fassungen\{de,en}\audio\.
- Offen: Vergleich gegen AP 61, Kosten je Stunde Audio, Wortzeiten (520) der Test-Fassung neu, leere Hülle tests\ap62\...\alice-s-adventures-in-wonderland\alice-s-adventures-in-wonderland\ manuell löschen.
- Produktion und fertige Werke unberührt. HYBRID_WERKE leer (Stufe 510 aus).

## 31.10.2026 — AP 63 (Teil 1: Punkte 1, 2 teilweise, 6-Hinweis; Sicherung)
- Sicherung: archive/2026-10-31_63/ (hybrid_de.json, hybrid_en.json, test_de_audio/, test_en_audio/). Vor 520-Lauf angelegt.
- Punkt 1 Vergleich AP 61 (Produktion authors/carroll-l/books/alice-s-adventures-in-wonderland/fassungen) vs. Testfassung Kap. VII (c007):
  - de: 164 Dateien je Seite, 102 geaendert (= eingebaut), Dauer 1044,6 s -> 1031,5 s (-13,2 s, -1,3 %)
  - en: 164 Dateien je Seite, 102 geaendert, Dauer 1019,2 s -> 999,2 s (-20,1 s, -2,0 %)
  - Keine Dateien nur auf einer Seite. Auffaelligkeit: Kuerzung je Figurenrede ueber Erzaehler-Einschub; Protokoll zeigt Mischungen "#0alt #1erz #2alt".
- Punkt 2 Kosten: Protokoll enthaelt keine Token-/Kostenangaben, Modal-Log nicht gefunden. Offen.
- Punkt 3 (520 Test-Lauf): zurueckgestellt bis Freigabe.
- Punkt 4 (Policy-Rueckfall): offen, Entscheidung durch Christian. policy-Liste in beiden Protokollen leer.
- Punkt 5 (Rollout-Liste): offen.
- 31.10. Nachtrag (Christian): Kosten beim naechsten Voll-Lauf mitschreiben. Auszulesen je Lauf: Reader EUR je 1000 Woerter je Sprache; Hoerbuch EUR je Audiostunde; Hoerspiel-Zusatzkosten EUR je Audiostunde je Sprache (zusaetzlich zu Hoerbuch). Rollout-Planung (Punkt 5) erst danach.
- 31.10. Leere Huelle tests/ap62/.../alice-s-adventures-in-wonderland/ nach archive/2026-10-31_63/leere_huelle_alice verschoben (Christian).
- 31.10. Hoerspiel-Gate eingebaut (Schritte 1+2, Entwurf): book.json "hoerspiel": "offen" | "ja" | "nein". Neues Modul pipeline/gate.py (hoerspiel_gate). s410.aktiv(), run.py _hybrid_done und s510.run() folgen dem Gate; ohne Eintrag bleibt das Legacy-Verhalten (besetzung_modus, HYBRID_WERKE). Sicherung des Codes: archive/2026-10-31_63/code_vor_gate/. py_compile ok. Noch nicht gelaufen. Offen: Cockpit-Umschalter, Rollback bei "nein", Kostenanzeige (braucht Kostenerfassung im Voll-Lauf).
- 31.10. MAGI (the-gift-of-the-magi) als Kosten-Pruefwerk: book.json hoerspiel=offen gesetzt (Backup archive/2026-10-31_63/book_magi_vor_gate.json). Bleibt offen, bis Kosten bekannt sind.
- 31.10. MAGI DE: Thorsten-Vertonung (150 WAVs, 10.10.) auf Wunsch von Christian nach archive/2026-10-31_63/magi_de_thorsten/audio verschoben. DE-Audio ist damit leer; DE-Stufe 500 (Gemini) wuerde neu laufen -- nicht gestartet.
- 31.10. start_magi_de.bat vorbereitet (Gemini DE, --to 500). Nicht gestartet, Freigabe durch Christian erteilt -- Lauf erfolgt auf dem Rechner.
- 31.10. MAGI DE: Lauf mit lokaler Thorsten-Stimme (config.TTS_ENGINE_DE=thorsten) abgebrochen bei 100/150. Entstandene WAVs nach archive/2026-10-31_63/magi_de_thorsten_teil/. Engine-Wahl muss je Werk/Sprache (book.json) umgestellt werden: DE gemini, EN chatterbox.
- 31.10. tts je Werk/Sprache eingebaut (pipeline/gate.py tts_engine, run.py _stage58_module). MAGI: de=gemini, en=chatterbox. Chatterbox-Modul in der Pipeline fehlt noch: Abbruch statt Fallback.
- 31.10. Chatterbox EN eingebaut: pipeline/s502_vertonung_chatterbox.py (Paket kostenlos ueber tools/cb_neu.py <werk> <lg> liste --alle; Modal nur per start_cb_neu.bat <werk> <lg> los --alle). cb_neu.py: neue Quelle --alle. run.py: tts=chatterbox -> Stufe 502. Sicherung archive/2026-10-31_63/code_vor_cb/. Nicht gelaufen.
- 31.10. start_magi_en_paket.bat vorbereitet (EN Chatterbox-Paket, kostenlos). Noch nicht gelaufen.
- 31.10. MAGI EN Referenzstimme: w_jung_hoch_ruhig (voice_7x79jocb431j, Archiv-Status kandidat). ref.wav = erste 15 s aus stimmen_archiv/w_jung_hoch_ruhig/hoerprobe.wav in gpu_tts/the-gift-of-the-magi_en/. jobs.json nur als Referenz-Traeger (leer).
- 31.10. MAGI EN Chatterbox Modal-Vertonung gelaufen: 150/150 in fassungen/en/audio_neu_20261031 (12,0 min, GPU 5,3 min, ~0,07 $). Einspielen scheiterte: Zielordner fassungen/en/audio fehlte -> angelegt. Offen: einspielen, Wortzeiten (Modal), abschluss.
- 31.10. MAGI EN: work/520_wortzeiten_en.json als leere Basis angelegt (einspielen brauchte sie). Audio bereits eingespielt (150). Offen: einspielen erneut (Protokoll), Wortzeiten (Modal), abschluss.
- 31.10. MAGI Kosten (Ist): DE Gemini 150 Schnipsel, 12,6 min, 2045 Woerter, 0,182 USD (~0,87 USD/h, ~0,089 USD/1000 W, Stimme Charon = Fallback). EN Chatterbox 13,2 min, GPU 0,070 USD (~0,32 USD/h, ohne Wortzeit-Laeufe). Quelle: work/kosten.jsonl. Hoerspiel-Zusatz noch nicht berechnet.
- 31.10. Preishinweis (Christian): Gemini verdoppelt Preise ab 01.01.2027. Szenario DE Gemini ab 2027: 0,36 USD je Lauf (ca. 1,73 USD/h, ca. 0,18 USD/1000 W). Chatterbox/GPU nicht betroffen. Quelle Verdopplung: Christian; im Projekt (RECHT/Stage-Notiz) fuer 3.8 Flash Text ebenfalls 'ab 2027 doppelt' erwaehnt, TTS-Preis dort nicht bestaetigt.
- 31.10. Stimmen-Gate eingebaut: book.json "stimme" (Archiv-Name, je Sprache moeglich). pipeline/gate.py (stimme, gemini_voice, ref_clip, stimmen_pruefung); run.py stoppt vor 500/502 ohne Stimme (nur Werke mit "tts"-Eintrag, Altwerke unveraendert); s500 nimmt Gemini-Stimme/Design-ID aus dem Gate statt Fallback Charon; s502 erzeugt ref.wav (max. 15 s) automatisch aus der gewaehlten Stimme. MAGI: stimme.en = w_jung_hoch_ruhig, DE offen (Gate stoppt). Sicherung archive/2026-10-31_63/code_vor_stimmengate/. Offen: Cockpit-Sprecherauswahl; DE-Charon-Fassung vor Neulauf archivieren.
- 31.10. Referenztext fuer Stimmen-Hoerproben vorbereitet: tools/referenztext_nordwind.py + start_referenztext.bat (Aesop 'North Wind and the Sun' EN aus Archiv, DE ueber Stufe 310, + Frage/Ausruf). Ausgabe stimmen_archiv/_texte/. Nicht gelaufen.
- 31.10. Referenztext Nordwind EN/DE erzeugt (stimmen_archiv/_texte/, 156/151 Woerter, ca. 60 s gelesen). DE-Fassung geprueft: sauber.
- 31.10. Archiv-Regel Stimmen: je Stimme muster_<lg>.wav (ca. 5 s) + klon_<lg>.wav (Nordwind-Text, ca. 60 s). pipeline/hoerprobe.py (erzeuge, fuer_neue_stimme, ref_schnitt an Sprechpause 12-20 s); voice_registry: neue Design-Stimmen bekommen klon_<lg> automatisch; gate.ref_clip nimmt klon_<lg> zuerst; s502 schneidet Referenz an Sprechpause. Nachzug Bestand: tools/hoerproben_archiv.py + start_hoerproben.bat [liste|los]: 69 Stimmen, 138 Proben, ca. 1,86 USD (2026). Nicht gelaufen. Sicherung archive/2026-10-31_63/code_vor_hoerprobe/.
- 31.10. Klon-Hoerproben Bestand erzeugt: 138/138 ok (69 Stimmen x de/en), 52,6-69,9 s je Probe, 137,4 min gesamt, ca. 1,85 USD. Log cockpit/logs/hoerproben_los.log.
- 31.10. MAGI DE Stimme = Despina (book.json stimme.de). Charon-Fassung (150 WAVs) nach archive/2026-10-31_63/magi_de_charon/audio. Neulauf: start_magi_de.bat (ca. 0,18 USD).

- 03.11.2026 Smoke-Werk u-smoketest-the-mirror-sisters: Kette bis 340 gelaufen; 340 Pruefaligner fehlte (Windows-Python ohne Modul modal) -> `pip install modal` nachziehen. 090 Rechte-Versicherung fuer Testwerk als "eigene" (CK) gesetzt.

## 03.11.2026 — Phase 3, AP P3-1: Cockpit Einzeltitel-Ansicht (gebaut)
- Start: cockpit_start.bat -> http://127.0.0.1:8765/werk#<book-id> (Link auch oben im alten Cockpit). Titelwechsel per Book-ID (Liste aus daten/index.json). Kein Bulk.
- cockpit/werk_api.py: Lese-API GET /api/werk/<id>?wer= (Bestellung, Stages in Katalogreihenfolge mit Zustand/Teilen/Befunden/Ruecksprung/Metriken-Auszug/Kosten Ist je Stage/fehlende_teile/veraltet/Manifeste, naechster Schritt, Rechte 080, Protokoll). Liest nur, schreibt status.json nicht (Smoke: sha1 vor/nach gleich).
- Aktionen POST /api/werk/<id>/aktion (entscheiden/zuruecksetzen/override, Grund Pflicht, Rolle aus config/rollen.json) direkt ueber pipeline.status; /lauf (run.py fortsetzen | ab <stage> | nur <stage>, --wer, optional --live) und /regler als Unterprozess, Live-Log cockpit/logs/werk_<id>_<zeit>.log, Exit 0 frei / 1 fehler / 2 stopp / 3 mensch (kein Fehler). Ein Unterprozess je Werk.
- Regler (Whitelist, --flag=wert): 095 --produkt/--default; 410 --freigeben/--grund/Schwellen/--trocken; 615 --titel/--umbruch/--schrift/--position/--transparenz/--sprecher/--neu/--freigeben/--trocken; 710 --bitrate/--nur-manifest/--freigeben/--grund/--dry. Vor Ausfuehrung Befehlsvorschau + Bestaetigung.
- Entscheidungen CK: Hoerproben/Vorschauen (640/615/530) = eigenes AP; Kosten nur Ist (kosten.jsonl).
- Hinweis: config.RUN_MODE ist live -> jeder Lauf aus dem Cockpit ist live (Anzeige rot). Smoke-Abnahme ohne Kosten: run.py --only 080 ueber API -> Exit 0. Naechster Schritt Smoke laut Ansicht: 150 veraltet (095 juenger; lokal).
- Tests: tests/test_cockpit_werk.py (6), zusammen mit status/kette/s080 38 ok.
- Offen: P3-2 Vorschauen (Teaser 640, Cover 615, Hoerliste 530); Restpunkte Nachtrag 23 (3,5,8-12); altes Cockpit (Bulk) nicht erweitert.
- 03.11.2026 Produktions-Ampel (CK, Farben festgelegt): gruen = Produktion laeuft wie geplant · gruen blinkend = Produktion stockt (Stage/Cockpit-Lauf ohne Aktivitaet > 15 min) · orange blinkend = Handlungsbedarf (mensch) · rot = Produktion angehalten (Gate-Stopp) · rot blinkend = unerwarteter Fehler (Stopp "Fehler: ..." aus run.py bzw. Cockpit-Lauf Exit 1) · grau = nichts laeuft, nichts offen. Einzeltitel-Ansicht oben + Kopfzeile ueber alle Werke (auch altes Cockpit), Abfrage alle 4 s (GET /api/werk/<id>/ampel, /api/ampel). Bestand beim Einbau: 14 Werke angehalten an 615, 1 Handlungsbedarf (the-art-of-war 120).
- 03.11.2026 Gate-Monitore: Steckbriefe je Mensch-Gate in Projekt-Doc claude/GATE_MONITORE.md (Start 110 entschieden; PD-Nachweis als gemeinsamer Baustein 100+110). Naechstes Gate: 100.
- 03.11.2026 ALTES COCKPIT EINGEMOTTET (CK): server.py/index.html/startliste.json + daten/auftraege.json/freigaben.json -> archive/2026-11-03_cockpit_alt/. Ursache 18:02: alter Runner setzte beim Serverstart gespeicherte Auftraege fort und rief s615 direkt (an der Kette vorbei) fuer 14 Altwerke auf -> 615 stopp "Gate 610 frei (offen)". Bereinigung der 14 Eintraege offen.
- 03.11.2026 Neues Cockpit = Schrittfolge, je Schritt eine Ansicht (CK): 1 Anmeldung (simuliert, config/rollen.json, sessionStorage) -> 2 Werk (Bestand mit Autor/Titel/Ampel + Suche · EPUB-Upload -> s150 Neuanlage, daten/uploads/ · TXT-Upload: abgelehnt, kein Eingangsweg in 090/150) -> 3 vorerst bisherige Einzeltitel-Ansicht /werk. cockpit/server.py neu und schlank (nur werk_api), nichts startet beim Serverstart.
- 03.11.2026 NEUE EINGANGSART user_txt (CK: "Weiche, die den Rohtext durch die mitgebrachte TXT ersetzt"): bestellung.QUELLEN + TEXT_EINGANG (gutenberg, user_txt); 090 leitet user_txt -> 100 (Pflicht: textquelle art datei); kette.bedarf wie Gutenberg (100, 110, 120; 150 entfaellt); 120 Kapitelerkennung aus raw.txt; Ruecksprungziele 610/615 wie Gutenberg. Neuanlage: python tools/s100_anlegen.py --txt DATEI --titel ... --autor ... --sprache en [--todesjahr N] [--slug] -> authors/<autor>/books/<slug>/, raw.txt = Kopie, book.json quelle user_txt; ohne Todesjahr -> 100 mensch (PD-Nachweis). Bestellung leitet fuer user_txt fassung modernisiert + rechte gemeinfrei ab (PD sichert Gate 100). Cockpit Schritt 2 "TXT hochladen": Formular Titel*/Autor/Todesjahr/Sprache* + Datei (UTF-8) -> Unterprozess, danach "Weiter mit <Werk>". Tests: test_s100 (+3), test_kette (+1). E2E am Wegwerf-Werk geprueft und wieder entfernt.
- 03.11.2026 ENTSCHIEDEN (CK) Fassungsweiche 115: Schalter original | modernisiert | einfach | gekuerzt | glace. Parallele Stages: 118 Kapitel (neu, aus 120 herausgeloest, laeuft bei allen Fassungen), 120 sanft (wie gehabt), 122 Einfache Sprache, 124 Gekuerzte Lesung (Nummer Vorschlag), 125 Glace (ca. 15 Min. Hoerzeit, starke Zusammenfassung, NUR woertliche Rede unveraendert aus dem Original – keine Zitatsammlung). Jede Fassung = eigene Book-ID (<stamm>--einfach usw.) mit fassung + stamm_id (Vermerk Pflicht, Cover-Vermerk 615). Name intern glace, aussen "TAELLA Glace". Steckbriefe: Projekt-Doc claude/GATE_MONITORE.md (100, 110, 115 entschieden; 118/120 offen: Kapitelplan manuell, Pruefschwellen, korrigierter Absatz). Grundsatz CK: NUR COCKPIT – keine Kommandozeilen-Wege fuer den Betrieb.
- 03.11.2026 ENTSCHIEDEN (CK) 118/120: Kapitelplan manuell (Grenzen setzen/entfernen, work/118_kapitel.json); Pruefschwellen 120 fest im Code (config); manuell korrigierter Absatz gilt als geprueft (Vermerk manuell wer/wann, Eigennamen weiter geprueft). Steckbriefe 100/110/115/118/120 entschieden. Naechstes Gate: 150.
- 03.11.2026 ENTSCHIEDEN (CK) 150: sprache -> Stopp (wie 100, Grundsatz 3); 118 laeuft auch nach 150 und uebernimmt Verlag-Kapitelpruefung; Monitor-Bearbeitung: Seiten behalten/entfernen, Titel/Autor/Sprache, Bilder/Fussnoten/Cover (kein ePub-Austausch). Naechstes Gate: 195.
- 03.11.2026 ENTSCHIEDEN (CK) 195: Grenze im Monitor je Werk editierbar; bereits_geteilt nur Hinweis; Ruecksprung kapitel_ueber_grenze 120 -> 118. Naechstes Gate: 200.
- 03.11.2026 ENTSCHIEDEN (CK) 200: kein direktes Editieren des Knotentexts (Treue nur ueber Neu-Taggen); Abkuerzungen im Monitor nur je Werk, je Sprache bleibt config; Ruecksprung Kapitel 120 -> 118. Naechstes Gate: 210.
- 03.11.2026 ENTSCHIEDEN (CK) 210: Listengrenzen im Monitor je Werk; Hoerspiel -> 210 immer Mensch (beibehalten). Steckbriefe bis 210 in claude/GATE_MONITORE.md. Naechstes Gate: 310.
- 03.11.2026 Steckbrief 310 entschieden (CK): Monitor zeigt nur Befundliste je Zielsprache; Glossar-/Namensfehler per Satzkorrektur oder Ruecksprung 210; Regler je Werk: Laenge, Modell, Batch, Anker; Freigabe bleibt an ausgabe_hash gebunden. Naechstes Gate: 330.
- 03.11.2026 Steckbrief 330 entschieden (CK): nur Befundliste (Quelle/Ziel/Rueck/Score); Regler je Werk: Schwelle, Flag-Quote, Umfang (Modelle nicht im Monitor); manuell ersetzter Satz gilt geprueft mit Vermerk wer/wann; Verlag immer Mensch beibehalten. Naechstes Gate: 340.
- 03.11.2026 Steckbrief 340 entschieden (CK): Befundliste mit Wortpaaren/Ankerlinien; Anker manuell per Klick Quellwort->Zielwort (Rechtsklick loescht); Regler je Werk: Schwellen, Kette/Ankerverlust, Pruefaligner an/aus (Modell/Batch nicht); Pruefaligner nicht erreichbar -> 1x automatisch spaeter erneut, dann Mensch (Bau offen). Naechstes Gate: 400.
- 03.11.2026 Steckbrief 400 entschieden (CK): Befundliste Text|Sprechtext; Hoerprobe je Satz auf Klick (P3-2); Aussprache in 210 und 400 pflegbar; Regler je Werk: Betonung/Emotion/Tempo, Pausen, Aussprache ueberspringen, Laenge-/Style-Grenze. Naechstes Gate: 410.
- 03.11.2026 Gate 410 Casting entschieden: Besetzungstabelle mit Hoerprobe; Umbesetzen Archiv+Design; Statist-Schalter je Figur; alle fachlichen Regler je Werk. Naechstes Gate: 420.
- 03.11.2026 Gate 420 Sprecher entschieden: Befundliste als Drehbuch; Sprecher-Dropdown + Segment teilen; fachliche Regler je Werk. GATE_MONITORE bis 420 im Projekt. Naechstes Gate: 500/510.
- 03.11.2026 Gate 500/510 entschieden: Kostenfreigabe je Sprache einzeln (Bau); Hoerliste abspielen/neu/annehmen (annehmen Bau); Probe 5 Saetze; Budget+Pruefschwellen je Werk. Naechstes Gate: 540.
- 03.11.2026 Gate 540 Trennung entschieden: Figurentabelle + Hoerproben A/B; Korrektur hoch/runter, umbesetzen, annehmen; Regler ECAPA/Redezeit/Nachrunde. GATE_MONITORE bis 540 im Projekt. Naechstes Gate: 600.
- 03.11.2026 Gate 600 Klappentext entschieden: Shop-Vorschau je Sprache + Befunde; Satz im Editor + Block neu; Koeder im Werktext markieren; Autor-Fakten -> 110, Sicherheit/Edition annehmen mit Grund (Bau). Naechstes Gate: 610.
- 03.11.2026 Gate 610 Cover entschieden: Bild + Pruefwerte + Prompt; Motiv/Varianten/Upload/Erbe; annehmen trotz Rot mit Grund (Bau). Bestand-Gates alle durch. GATE_MONITORE bis 610 im Projekt. Naechstes: 095, 520, 530, 615.
- 03.11.2026 Gate 095 Produktwahl entschieden: Bestellmatrix + Angebot live; Matrix anklicken (--produkt/--default); BETA gelb mit Hinweis. Naechstes: 520, 530, 615.
- 03.11.2026 Gate 520 Wortzeiten entschieden: Karaoke-Vorschau je Satz; neu messen (--satz) + Wortgrenze ziehen (--zeit); Regler Pruefschwellen + Interpolation. Naechstes: 530, 615.
- 03.11.2026 Gate 530 Audio-Pruefung entschieden: Hoerliste Roh|Endfassung + Kapitelpegel; neu bauen/neu vertonen/annehmen mit Grund (Bau --annehmen); Regler Klang + Schwellen. Naechstes: 615.
- 03.11.2026 Gate 615 Cover final entschieden: Galerie Sprache x Variante, eine Sichtfreigabe; Typo-Felder mit Live-Vorschau. Alle Mensch-Gates haben Steckbriefe; GATE_MONITORE im Projekt. Naechstes: Bau der Monitore/Regler, Altwerk-Bereinigung 615, P3-2 Hoerproben.
- 03.11.2026 Altwerk-Bereinigung 615: 13 Altwerke (nicht 14) hatten vom alten Runner (18:02) nur status.json (615 stopp) + leeres 615_cover_final.json; beide nach archive/2026-11-03_altwerk615/<werk>/ verschoben, Altwerke wieder ohne status.json. the-art-of-war war regulaer, unberuehrt. Naechstes: Bau Monitore/Regler, P3-2 Hoerproben.
- 04.11.2026 Phase 3 Bau: Monitor-Rahmen + Monitor 100 (CK: Rahmen + 100, dann Kettenreihenfolge). cockpit/monitor.html (/monitor#<id>/<stage>): Kettenleiste, Ampel, Gate-Kopf (Befunde, "neu pruefen", Ruecksprung-Knoepfe, Ausnahme frei/stopp mit Grund), je Stage eigener Teil (MON[stage]), sonst allgemeine Datenansicht; Link aus werk.html (Naechster Schritt + je Stage). werk_api: monitor(), monitor_speichern() (Stage-Modul als Unterprozess, Recht bestellen), MONITOR_DATEN/MONITOR_SPEICHERN je Stage; server: /monitor, /vendor/, GET .../monitor/<st>, .../rohtext, POST .../monitor/<st>. Text-Editor CodeMirror 6.0.2 (MIT) lokal cockpit/vendor/codemirror6.min.js. s100 neu: --quellsprache, Nachweise --pd-url | --rechteinhaber [eigene|lizenz] | --pd-quelle (--deckt autor,uebersetzer) in book.json rechte.nachweise (Nachweis erfuellt pd_autor/pd_uebersetzer; Rechteinhaber setzt rechte.art + versichert), --rohtext-aus DATEI --grund (Sicherung work/sicherung/100_raw_<zeit>.txt + Protokoll), sprache -> Stopp (Grundsatz 3); text_laden schreibt newline="" (Ursache \r\r\n in Alt-raw.txt unter Windows). bestellung.rechte_norm behaelt nachweise. Tests s100 (16) + cockpit 7 + status/kette/s080/bestellung/s110 ok. Naechstes: Monitor 110.
- 04.11.2026 Cockpit im TAELLA-Look (CK): Marke 'TÆLLA Labs' (Wortmarke mit rotem Punkt, cockpit/vendor/marke.js), gemeinsames cockpit/vendor/taella.css (Instrument Sans/Serif lokal, SIL OFL; Schwarz/Weiss, Haarlinien; Zustaende nur als kleine Punkte gruen/orange/rot) fuer start/werk/monitor. Monitor: Abschnitt 'Ergebnis' je Stage (GET /api/werk/<id>/ergebnis/<st>: work/<st>_* inkl. Unterordner + feste Werkdateien je Stage, z. B. 100 book.json/raw.txt/author.json); JSON als aufklappbarer Baum (200er-Schritte), Text gekuerzt, Bild/Audio direkt; Kettenleiste als eigene Zeile. Editor-Zwischendatei jetzt work/_editor/.
- 04.11.2026 Stage-Skript: docs/STAGE_SKRIPT.md (je Stage Ziel, zuliefernd, folgend, betroffen bei Neulauf, Vorkette; 118/122/124/125 als entschieden/nicht in Kette), erzeugt von tools/stage_skript.py (Abhaengigkeiten live aus kette.VORGAENGER/status.STAGES); Kopie im Projekt claude/STAGE_SKRIPT.md.
- 04.11.2026 Monitor 110 gebaut: Autor (author.json + Kandidatentabelle mit Wahl/Q-ID manuell), PD-Ampel + Nachweis-Baustein (gemeinsam mit 100, JS nwBaustein/_nachweis_argv), Werk (Q-ID, Kandidaten mit Jaccard, Q-ID manuell), Titel je Sprache editierbar (Uebernehmen bestaetigt als 'manuell'), Kontext Gutenberg-Link + Titelei 60 Zeilen; Option 'neu abfragen'. s110: Kandidaten -> work/110_kandidaten.json, PD-Nachweis erfuellt pd_wikidata (hebt auch Stopp Todesjahr+70 auf), Regler --pd-url/--rechteinhaber/--pd-quelle/--deckt. config.werk_rechte liest rechte als dict (art). Tests s110 8 ok. Naechstes: Monitor 115 (Fassungsweiche).
- 04.11.2026 Hilfe je Stage (CK, fuer Dritte): config/stage_hilfe.json (warum / produziert / was entscheidet der Mensch, 34 Stages), Popup '?' im Monitor-Kopf und je Stage in der Werkansicht (cockpit/vendor/hilfe.js, GET /api/hilfe); Stage-Namen im Cockpit aus der Hilfe; Stage-Skript ergaenzt um Produziert/Mensch entscheidet (PDF neu).

- 2026-11-04: Monitor 115 (Fassungsweiche) fertig: Anzeige Fassung/Default/Mandant/Quellsprache+Prompt/Bearbeitungsrecht/Kosten 120, Wahl modernisiert|original -> s115 --modernisieren, Textprobe aus raw.txt (robust gg. \r\r\n), Ergebnis book.json; test_s115 +1 (39 Tests OK). Naechster Monitor: 118/120.
- 2026-11-04: Monitor 120 (Modernisierung) fertig: Kapitel-Gate erkannt vs. Inhaltsverzeichnis nebeneinander, Bestaetigen (--kapitel-ok), je Kapitel Laenge/Ausreisser/Luecken/manuell + "neu"; Gegenueberstellung Original|modernisiert je Kapitel (nachgeladen ueber neuen Endpunkt /monitor/<st>/teil, Filter auffaellig), Absatz neu (--absatz) oder manuell bearbeiten (--absatz-text); Regler Staerke/Temperatur/Stueck/--force mit Kosten. 56 Tests OK. Befund: the-art-of-war Kapitelerkennung falsch (17 statt 22, Kap.1="Chapter XIII") -> Rohtext in 100 korrigieren. Naechster Monitor: 150.
- 2026-11-04: s120 Kapitel entlang Inhaltsverzeichnis repariert: Sammelueberschriften ohne eigenen Text (INTRODUCTION -> Sun Wu and his Book) werden uebersprungen und aus der Referenz genommen; Kapitelnummer gleich + Titel aehnlich (>=0.75, Schreibvarianten) gilt als Treffer. the-art-of-war jetzt 21/21 Kapitel, Titeltreffer 100 %. test_s120 +1.
- 2026-11-04: Monitor 150 (ePub-Import) fertig: Umfang/Inhaltsanteil/Warnungen, Metadaten Titel(+Kandidaten)/Autor/Sprache, Seitenliste in Spine-Reihenfolge mit Grund/Zeichen + Entscheidung automatisch|behalten|entfernen + Seitenvorschau (Endpunkt teil), Kapitel, Cover/Klappentext, Optionen Cover/Bilder/Fussnoten, --force. Altwerke ohne quelle/: Vorschlag aus _epub_import (--epub), wird beim Neueinlesen nach quelle/ gesichert. 68 Tests OK. Naechster Monitor: 190.
- 2026-11-04: Monitor 190 (Eingangsvertrag) fertig: Vertragsliste als Trockenlauf (s190.run trocken=True, schreibt nichts), offene Pruefungen oben mit Link zum zustaendigen Monitor; keine Regler. Cockpit-Server: Verbindungsabbrueche des Browsers (WinError 10053) still abgefangen (Server neu starten). Befund the-art-of-war: book.json rechte abgeleitet -> 090. Naechster Monitor: 195.
- 2026-11-04 Monitor 195 Teilung: Kapitelbalken mit Schnitt-Klick (✂), Teile-Tabelle (Zeichen, Hörzeit ~55.000 Z/h, Slug, Name), Grenze je Werk, Teilezahl → Vorschlag (teil-Abruf, schreibt nichts), Annehmen/Ablehnen/nur speichern über s195-Regler; bestehende Teile mit 190-Ampel (nur Hinweis). Rücksprung Einzelkapitel bleibt 120, bis 118 existiert. test_s195.test_monitor_195; 60 Tests OK.
- 2026-11-09 Monitor 200 (Tagging) fertig: Kopf (Knoten, Treue vs. 99,5 %, Mehrsatz, ueberlang, Korrekturen gespeichert/verworfen, Kosten Ist + Schaetzung Neu-Taggen ganzes Werk); Kapiteltabelle mit Treue-Ampel, Herkunft, ~$ je Kapitel, "neu taggen"; Mehrsatz-Liste mit vorgeschlagener Trennstelle (s200.trennstelle) + "alle Vorschlaege"; Kapitelansicht (Teil-Abruf) Original | Knoten, Wortabweichungen wie Treue markiert; Wort anklicken = vor dem Wort teilen, ⊕ = mit folgendem zusammen, Typ-Auswahl (je Knoten eine Korrektur pro Lauf); Abkuerzungen je Werk (Chips, + / entfernen), je Sprache nur Anzeige; Regler Modell, Ueberlang-Grenze, alle Kapitel neu; Probe (--trocken). Knotentext nicht editierbar (CK 03.11.). s200: neue Korrekturen je Kapitel von hinten nach vorn (mehrere je Kapitel in einem Lauf gueltig), doppelte Knoten-ID -> Fehler, kosten_schaetzen(), pruefung.json mit zeichen je Kapitel + Mehrsatz-Vorschlag. FIX: _satzweise trennt jetzt in der Werksprache (vorher immer config.SOURCE_LANGUAGE -> DE-Originale nicht nachgetrennt, Mehrsatz-Gate schlug an). Ruecksprung bleibt 120, bis 118 existiert. Tests: test_s200 +4 (20), gesamt 539 OK. Cockpit-Server neu starten. Naechster Monitor: 210.
- 2026-11-09 VORGEMERKT: s200._renumber_chapter schreibt Header-Text und Versmarke unter config.SOURCE_LANGUAGE statt Werksprache (DE-Original: h-Knoten unter "en"). Fix aendert ausgabe_hash der DE-Werke -> bewusst entscheiden.
- 2026-11-09 FIX Schleife 090/190 (Altwerke, z. B. the-art-of-war): book.json ohne rechte -> 190 Stopp "rechte abgeleitet" -> Ruecksprung 090; 090 (gutenberg) prueft Rechte nicht und schrieb nur quelle fest -> frei ohne Wirkung. Jetzt schreibt 090 bei auto auch die abgeleiteten rechte fest (wie quelle). test_s090 +1. Fuer the-art-of-war: Cockpit neu starten, 090 nur, dann 190 nur.
- 2026-11-09 FIX run.py: Zielstage von --only/--from laeuft immer, auch wenn frei (Cockpit "neu pruefen" und "Ruecksprung NNN" auf eine freie Stage wurden nur uebersprungen). Folgestages wie bisher nur bei offen/veraltet/fehlenden Teilen.
- 2026-11-09 Monitor 210 (Profil) fertig: Kopf (Herkunft, Modell, Zielsprachen, Kosten Ist + Schaetzung Neu-Erzeugen ~0,14 $ bei the-art-of-war), Listen Zaehler/Grenze je Werk (Feld, "voll" markiert); Stil + voice_note (fest / fest aufheben); Figuren-Tabelle (Treffer, gender, pronunciation, Zielsprache, tts_<lg> editierbar, Herkunft llm/fest/reihe, entfernen, neue Figur), Klick auf Namen = Textstellen (Teil-Abruf); Glossar editierbar/entfernen/neu, Luecken markiert; Unuebersetztes/Redewendungen nur Anzeige; Reihe: Erbe an/aus, Namensvarianten "dieselbe Figur"; Regler Modell (erzwingt Neu-Erzeugen), Profil neu; Probe (--trocken). s210: FIX Figurenzaehlung Apostroph-Formen (’ vs ', the-art-of-war: Fu Ch'ai/Po P'ei/Wu Ch'i 0 -> 4/4/11), fundstellen(), kosten_schaetzen(), _parse_kv erlaubt Komma im Wert, --grenze wird je Werk in book.json profil_grenzen gespeichert. Tests test_s210 +4, gesamt 544 OK. Cockpit-Server neu starten. Naechster Monitor: 310.
- 2026-11-09 ENTSCHIEDEN (CK) Kappungsregel 210, allgemein: Modell wird um Grenze + 1 gebeten; gekappt erst bei mehr als Grenze. Gekappte Figurenliste -> Mensch nur bei bestelltem Hoerspiel (steuert Casting 410), sonst Hinweis; Glossar/Unuebersetztes/Redewendungen gekappt -> nur Hinweis (Luecken fallen in 310/400 auf). Tests 545 OK.
- 2026-11-09 GRUNDSATZ (CK): the-art-of-war ist nur Musterwerk – Befunde dort werden immer allgemein in der Stage behoben, Tests mit synthetischen Werken.
- 2026-11-09 Monitor 310 (Uebersetzung) fertig: Kopf (Quelle -> Ziele, Saetze/Kapitel/Zeichen, Modell/Batch/Anker, Kosten Ist + Schaetzung alles neu + je Satz), Umschalter je Zielsprache (Befundzahl, offene Aenderungen); je Sprache Abdeckung + Luecken, Werktitel (Hinweis Pruefung 615), Pruefungen sprache/kopie/verschmelzung/schema/laenge/glossar mit Zaehler vs. Schwelle (Glossar -> Link 210), manuell/angenommen, Kapitel ohne Anker. Befundliste (Satz-ID, Quelle | Ziel, Befund-Chips) filterbar nach Befundart/Kapitel; Zieltext anklicken = manuell ersetzen, je Satz "neu uebersetzen" (Kosten) oder "Befund annehmen"; Aenderungen je Sprache einzeln uebernehmen. Regler je Werk: Modell, Batch, Laenge unten/oben, Anker, alle Kapitel neu; Probe (--trocken). s310: --modell/--batch/--laenge/--anker jetzt je Werk in book.json (uebersetzung_modell/_batch/_laenge/_anker); --lang wirkt nur noch auf Regler/Neulauf dieser Sprache, andere Sprachen unveraendert aus 310_uebersetzung.json (vorher fielen sie aus Gate und 310_pruefung.json heraus); unbestellte --lang -> Fehler; kosten_schaetzen(). Tests test_s310 +3 (14), gesamt 548 OK. Cockpit-Server neu starten. Naechster Monitor: 330.
- 2026-11-09 16:40 Musterwerk the-art-of-war: 300 + 310 gelaufen (CK), beide frei/auto; Monitor 310 im Cockpit geprueft. Naechstes: 320 + 330 laufen lassen (Daten fuer Monitor 330), dann Bau Monitor 330 in neuer Sitzung.
- 2026-11-09 Monitor 330 (Rueckuebersetzung) fertig: Kopf (Quelle -> Ziele, Kapitel, Modelle Rueck/Bewertung nur Anzeige, Umfang, Kosten Ist + Schaetzung alles neu bewerten inkl. ~5 % Reparatur + je Satz), Umschalter je Zielsprache (offene Befunde, Aenderungen); je Sprache Score-Schnitt (Soll >= 92, Anzeige), Flags nach Reparatur vs. Grenze (3 % ab 300 Saetzen, darunter <= 10), nicht bewertbar vs. 1 %, Umfang bewertet/ungeprueft, Erledigt repariert/manuell/angenommen mit Vermerken wer/wann. Befundliste (Satz-ID, Quelle | Ziel | Rueck | Score, Befund geflaggt/nicht bewertbar/repariert mit Score und Ziel vorher) filterbar nach Befund/Kapitel; Zieltext anklicken = manuell ersetzen (gilt geprueft), je Satz "neu uebersetzen + bewerten" (Kosten) oder "Flag annehmen"; Kapitel-Chips = Kapitel neu bewerten; Aenderungen je Sprache einzeln. Regler je Werk: Score-Schwelle, Flag-Quote, Umfang alle/Ausreisser + Stichprobe, alle Kapitel neu; Probe (--trocken). s330: --schwelle/--flag-max/--umfang/--stichprobe je Werk in book.json (rueck_*; flag_max wurde vorher nicht aus book.json gelesen); --lang wirkt nur noch auf Regler/Neubewertung dieser Sprache, andere Sprachen laufen per Checkpoint mit (vorher fielen sie aus 330_rueckuebersetzung.json/quality_report/330_pruefung.json heraus); unbestellte --lang -> Fehler; 330_pruefung.json fuehrt reparierte Saetze (befund repariert, score_vorher, ziel_vorher); kosten_schaetzen(). Tests test_s330 +4 (17), gesamt 552 OK. Cockpit-Server neu starten. Offen: 330 fuer the-art-of-war laufen lassen (Daten), Monitor im Cockpit pruefen. Naechster Monitor: 340.
- 2026-11-13 330 the-art-of-war gelaufen (CK): auto, Flags 2,1 %, Schnitt 95,7, 47 repariert; Hinweis Haeufung "Tu Mu" (4 Flags).
- 2026-11-13 Monitor 340 (Wort-Alignment) fertig: Kopf (Ziele = TAELLA-Sprachen, Kapitel, Modell, Pruefaligner an/aus, Kette, Ankerverlust, Kosten Ist + Schaetzung alles neu inkl. Nachlaeufe/Pruefaligner + je Satz), Umschalter je Zielsprache; je Sprache Pruefungen Inhalt/unresolved/verschoben/doppelt vs. Schwelle, Umfang (Saetze, Woerter, fehlt, ohne Pruefaligner), manuelle Anker mit wer/wann. Befundliste (fehlt/Abdeckung-Span/unresolved/verschoben/doppelt/Inhaltswort ohne Anker) filterbar, 20 je Seite, Saetze per Teil-Abruf (?lang&ids): Quellwoerter und Zieltokens als farbige Wortpaare, Problemwoerter markiert, Hover zeigt Anker (Flaeche) + Pruefanker (gestrichelt), Ketten + Nachlauf-Ergebnis. Anker per Klick Quellwort -> Zielwort (Umschalt = mehrere Zielwoerter), Rechtsklick loescht; je Satz "neu alignen", Kapitel-Chips neu alignen. Regler je Werk: Inhalt/unresolved/verschoben/doppelt, Kette, Ankerverlust, Pruefaligner an/aus, alle Kapitel neu; Probe. s340: Regler je Werk in book.json (align_*; vorher wurde auch --pruefaligner nicht gespeichert); Pruefaligner nicht erreichbar -> 1x automatisch nach PRUEFALIGNER_WARTE=60 s erneut, dann Mensch (Steckbrief, Metrik pruefaligner_wiederholt); --lang nur noch Regler/Neulauf dieser Sprache, andere Sprachen per Checkpoint (vorher fielen sie aus der Ausgabe); 340_pruefung.json zusaetzlich Befund ohne_anker, Pruefanker p, ketten, manuell; kosten_schaetzen(). Tests test_s340 +5, gesamt 557 OK. Cockpit-Server neu starten. Offen: nach dem laufenden 340-Lauf (alter Code) 340 einmal "neu pruefen" (Checkpoint, kostenfrei) -> Pruefliste mit Wortpaar-Daten; dann Monitor im Cockpit pruefen. Naechster Monitor: 400.
- 2026-11-13 340 Tempo/Abbruch: Kapitel parallel (ALIGN_PARALLEL, Standard 5 Threads), Nachlauf-Gruppen parallel, Modell je Parallelblock gesetzt; Checkpoint je Kapitel sofort nach Alignment + nach Pruefaligner (Abbruch/Server-Neustart bezahlt nichts doppelt; Anlass: 1. Lauf the-art-of-war 13.11. 08:51 durch Neustart verloren, ~0,28 $); usage_log schreibt kosten.jsonl mit Lock. Tests test_s340 +2, gesamt 559 OK. Kosten 2. Lauf (alter Code, sequenziell) bis Pruefaligner ~0,69 $ / 27 min.
- 2026-11-13 Monitor 095 (Produktwahl) fertig: Bestellmatrix Sprache x Text (TAELLA/ePub) / Hoerbuch (Stufe + Kanaele nach MATRIX) / Hoerspiel (Stufe, TAELLA, Sound-Carpet BETA); Vorschau live (Teil-Abruf ?produkte=JSON): Produkte inkl. automatisch ergaenzter Erzaehlerspur, Fehler, Kette neu/entfaellt mit Stage-Namen, Selbstkosten-Angebot; Uebernehmen (--produkt je Zeile) oder Default aus Wunsch 090. Neuanlage im Cockpit (Start, Upload) fuehrt jetzt direkt in Monitor 095.
- 2026-11-13 NEU pipeline/hoerspiel_eignung.py (CK: Empfehlung Hoerspiel schon bei der Bestellung): lokal, 0 $ – Anteil woertlicher Rede (Rohtext, Zeilenumbrueche geglaettet), wiederkehrende Sprecher an Redeverben (>= 3 Treffer), Buehnenform (Sprecherzeilen, >= 30 und >= 5 je Rolle, Ueberschriften wie CANTO ausgeschlossen); Profil 210 (Figurenzahl) wenn vorhanden. Urteil geeignet (Rede >= 25 % und >= 4 Sprecher; Buehnenform -> Stufe drama) / bedingt (>= 12 %, >= 2) / ungeeignet / unbekannt (kein Rohtext, z. B. Gutenberg vor 100 -> Monitor rechnet live neu). 095: Metrik hoerspiel_eignung; Hoerspiel bestellt bei "ungeeignet" -> Hinweis + Mensch (Gruende werden jetzt zusammengefasst: ungeeignet/BETA/Mandant). Bestand-Probe: Shakespeare/Lysistrata drama, Pride and Prejudice/Emma/Lady Audley/Oz geeignet, Peter Pan/Aesop bedingt, Art of War/Meditations/Divine Comedy ungeeignet. Tests test_s095 +3, gesamt 562 OK. Restdatei cockpit/logs/_mon095.js kann geloescht werden.
- 2026-11-13 400 the-art-of-war gelaufen (CK): Mensch – Ursache 1: num2words fehlt auf dem Rechner (Ziffern blieben: Reste en 154/de 153) -> py -3.11 -m pip install num2words; Ursache 2: roemische Kapitelverweise ("VI. § 21", "Lun Yu, XV. 1").
- 2026-11-13 sprechtext.py REGELN_V 3: roemische Zahl vor § -> "Kapitel sechs, § 21" (en chapter …); Zitierweise "XV. 1"/"XXXII, 2" (ab zwei Zeichen, Zahl folgt) -> Grundzahl; Herrscher-Regel ignoriert Praepositionen (In/Aus/Siehe/Vgl …); roemisch_offen ueberspringt Namen in Versalien ("LI CH’UAN"); s400 zahl_zuschlag zaehlt roemische Bloecke nicht in die Laenge. Probe the-art-of-war (mit num2words): Reste 0, roemisch en 15/de 17 (Rest: alleinstehende Verweise, teils Satzgrenze nach "Kap." -> Abkuerzung in 200) -> Monitor 400 von Hand.
- 2026-11-13 Monitor 400 (Regie) fertig: Kopf (Audiosprachen, Premium, Regler, Namensprache, TTS, Regeln-Version, 0 $), Umschalter je Audiosprache; Pruefungen roemisch_h/roemisch/reste/laenge/style + ohne Aussprache vs. 0, Knoten ohne Text (-> 310); Ansagen mit Sprechtext + Pause; Stil-Zeilen je Typ (Premium). Befundliste (40 je Seite, Filter Befund/Kapitel) Text | Sprechtext mit Wortdiff, Stil-Zeile, manuelle mit wer/wann; Sprechtext anklicken = von Hand setzen, "auf Regeln zuruecksetzen" (=-). Aussprache-Tabelle Figuren/Unuebersetzt: Namen je Sprache, "x-mal ohne", Herkunft 210 (pronunciation/tts_lg), 400-Hinweis editierbar (Vorrang), ueberspringen. Regler je Werk: Betonung/Emotion/Tempo, Pausen je Typ, Laenge-/Style-Grenze. s400: --laenge-max/--style-max je Werk (book.json audio_laenge_max/_style_max), --aussprache BEGRIFF=- loescht, --pron-skip-weg. Hoerprobe je Satz bleibt AP P3-2. Tests test_s400 +2, gesamt 564 OK. Restdatei cockpit/logs/_mon400.js loeschbar. Naechster Monitor: 410.
- 2026-11-13 Monitor-Rahmen: Mensch-Entscheidung nicht mehr eingeklappt ("Ausnahme"), sondern auffaelliger Kasten "Entscheidung noetig" (orange Rahmen) oben im Gate-Kopf UND am Ende jedes Monitors: Begruendung (Pflicht) + "Freigeben – weiter in der Kette" (Hauptknopf) / "Anhalten (Stopp)". Gilt fuer alle Monitore.
- 2026-11-13 Monitor 410 (Casting) fertig: Kopf (Bestellung lg × Stufe × Inhalt, Freigabe wer/wann/gilt, Kosten Ist + Steckbriefe neu ~$ + Voice Design je Stimme, Archiv x/200, Trennregel, Steckbriefe Erzaehler/Figuren/ohne Steckbrief/fremd), Umschalter je Sprache × Stufe; Besetzungstabelle Rolle | Stimme (Rufname, Quelle, Status, Vorgabe ✕) | Hoerprobe (muster/klon aus stimmen_archiv) | Passung | Grundton | Abstand zum Erzaehler (D) | Korrektur Formant/HT | Befunde; "umbesetzen" = Kandidaten aus Archiv + Gemini-Standard (bzw. Chatterbox) nach Passung, mit Hoerprobe, F0-Abstand, D zum Erzaehler, belegte unten; "neu entwerfen" mit Design-Prompt und Kostenhinweis; Statist-Schalter je Figur, Statisten mit "eigene Stimme"; Regler je Werk Schwelle/Grundton-Abstand/max. Ensemble/min. Anteil/Reihen-Erbe; Steckbriefe neu; komplett neu besetzen; Protokoll. s410: Vorgabe '@neu' (--erzaehler LG=@neu, --figur NAME=@neu) entwirft genau diese Rolle (mit --design), danach ersetzt der neue Name die Vorgabe in casting_regler (kein Neu-Design je Lauf); Hinweis neu_offen ohne --design. GEAENDERT: Aenderung eines freigegebenen Castings jetzt mit --grund ohne --neu (Bestand der uebrigen Rollen bleibt, Protokoll "aenderung"); --neu --grund = komplette Neubesetzung wie bisher. --statist hebt eine Stimmvorgabe auf, --figur hebt Statist auf; Korrektur aus Bestand nur bei gleicher Stimme. kosten_schaetzen(), design_preis() (Voice-Design-Stueckpreis in config.STUECKPREISE noch None). Tests test_s410 +3, gesamt 567 OK. Cockpit-Server neu starten. Offen: 410 fuer the-art-of-war laufen lassen (Steckbriefe ~0,035 $) und Monitor im Cockpit pruefen. Naechster Monitor: 420.
- 2026-11-15 Monitor 420 (Sprecher) fertig: Kopf (Hoerspiel-Sprachen, Ausgangssprache, Modus Prosa/Drama, Kosten Ist + alles neu je Sprache + je Satz), Umschalter je Hoerspiel-Sprache; Pruefungen Rueckfaelle/unsicher/Konsistenz vs. Regler, veraltete Korrekturen, Rede-Saetze ohne Segmente, manuell; Besetzung als farbige Chips mit Segmentzahl (Klick filtert). Drehbuch (20 je Seite, Teil-Abruf ?lang&ids): Segmente je Sprecher farbig (Kapitaelchen), Ausgangssprache daneben, Befund-Chips, Herkunft (llm/uebernommen/manuell/drama/rueckfall); "bearbeiten" = Sprecher-Dropdown je Segment + Wort anklicken setzt/entfernt Schnitt davor -> --segmente (vorher geprueft: Besetzung, Rekonstruktion); je Satz "neu zuordnen" (--satz, Kosten), "Korrektur entfernen"; Kapitel-Chips neu zuordnen; Filter nur Befunde/alle mit Rede/Befundart/Kapitel/Sprecher. Regler je Werk Rueckfall-max/Unsicher-max/Konsistenz-min, Drama auto/an/aus, Vorfilter, alles neu. Korrekturen je Sprache einzeln, nicht als Probe (werden sofort geschrieben). s420: kosten_schaetzen(). Tests test_s420 +1, gesamt 568 OK. Cockpit-Server neu starten. the-art-of-war hat kein Hoerspiel (420 entfaellt) -> Monitor am Hoerspiel-Werk pruefen. Naechster Monitor: 500/510.
- 2026-11-15 Happy Prince bis 420 (CK frei). Befund 420: 67 Rueckfaelle "sprecher_unbekannt" = The Remarkable Rocket (Rakete, Feuerwerk) fehlt in 210 (Figurenliste bei 40 gekappt); CK: Werk so lassen. Kapitelerkennung Happy Prince: nur 2 Kapitel fuer 5 Maerchen (118-Kapitelplan bei Bedarf).
- 2026-11-15 410 Getrenntes Casting je Geschichte (CK): Regler geschichten aus | kapitel | c001-c003,c004 (book.json casting_regler, --geschichten). Vorkommen je Figur = Name im Quelltext der Geschichte (s210 figur_treffer); eine Stimme darf mehrere Figuren sprechen, die nie in derselben Geschichte vorkommen; nicht gefunden = gilt ueberall; Erzaehlerstimme bleibt gesperrt. Sperre-Pruefung und Archivsuche je Konflikt; ensemble[].geschichten, rollen[..].geschichten. Monitor 410: Regler-Auswahl + Kapitelgruppen, Spalte Geschichten je Figur; Auswahl "umbesetzen" markiert belegte Stimmen inkl. vorgemerkter Wahl im Browser (nicht waehlbar, unten) -> keine Dopplung mehr ueber den Monitor.
- 2026-11-15 420: genannte Sprecher ausserhalb der Besetzung werden festgehalten (rec unbekannt, 420_pruefung unbekannt, Hinweis "nicht in der Besetzung: Name (nx) -> 210/410"); Monitor 420 zeigt sie im Kopf und am Satz. Tests s410 +1, s420 +1, gesamt 570 OK. Naechster Monitor: 500/510.
- 2026-11-15 Monitor 500 (Vertonung) fertig: Kopf (Kosten Ist, offen geschaetzt, Mandant/Budget, "Lauf jetzt" = Gruende/Hinweise eines Probelaufs), Tabelle je Audiosprache (Engine, Stimme mit Hoerprobe, Audio x/y Saetze + Minuten, fehlt/veraltet, Herkunft neu/uebernommen/fallback, offen Saetze/Zeichen/$) mit Kostenfreigabe je Sprache (Betrag editierbar); Probe N Saetze je Sprache (setzt passende Freigabe); Hoerliste je Sprache (auffaellig/leer/angenommen/Probe) mit Player, Sprechtext, Befund, Versuche; je Satz "neu vertonen" (Kosten, Freigabe automatisch) oder "annehmen" (Grund Pflicht); Regler je Werk Budget/auffaellig-max/Dauer min-max/Wiederholungen; Kostenfreigaben-Protokoll. Daten aus s500.run(trocken) (schreibt nichts, ~9 s bei Happy Prince). s500: --kosten-freigeben LG=USD je Sprache (ohne LG = Gesamt wie bisher; nicht freigegebene Sprachen warten, Gate mensch "kosten_<lg>", Abdeckung dort nur Hinweis); --annehmen ID --lang --grund -> work/500_entscheidungen.json (gilt bei gleichem datei_hash; Gate zaehlt angenommene nicht als auffaellig; Pruefliste "angenommen"); Metrik kosten_je_sprache. Tests s500 +2, gesamt 572 OK. Happy Prince offen: en Chatterbox ~0,48 $, de Gemini ~1,57 $. Naechster Monitor: 510 (Hoerspiel-Overlay), danach 520/530.
- 2026-11-15 Happy Prince 500 abgebrochen nach DE-Vertonung (984 WAVs, ~1,57 $): FA-Satzpruefung lud WAVs mit torchaudio.load -> neue torchaudio-Version verlangt TorchCodec. Zudem schrieb 500 das Manifest erst nach der Pruefung -> bezahltes Audio unverbucht. FIX s500: FaPruefer laedt/schreibt WAVs per wave-Modul (wie fa_mms); Manifest sofort nach dem Vertonen (pruefung "ungeprueft"), naechster Lauf prueft nach ohne TTS-Kosten; Lauf-Marke work/_500/lauf_<lg>.json vor jedem kostenpflichtigen Lauf -> nach Abbruch werden WAVs juenger als der Start (gleiche Engine/Stimme) uebernommen. Marke fuer Happy Prince DE nachtraeglich gesetzt (Start 07:38:31): Probe zeigt de 0 offen, en 984 (Chatterbox ~0,48 $). Tests s500 +2.
- 2026-11-15 Monitor 510 (Hoerspiel-Overlay) fertig: Kopf (Kosten Ist, offen geschaetzt, Mandant/Budget, "Lauf jetzt" aus Probelauf), Tabelle je Hoerspiel-Sprache (Erzaehler 500 mit Hoerprobe, Hoerspiel-Saetze x/y, Herkunft neu/erzaehler/behalten, fehlt/veraltet, offen Saetze/Takes/Zeichen/$) mit Kostenfreigabe je Sprache; Probe N Saetze; Ensemble je Sprache (Figur, Stimme + Gemini-ID, Hoerprobe, Korrektur nur Anzeige -> 410, Saetze); Ensemble-Stichprobe je Figur (Drehbuch farbig, Hoerspiel | Erzaehlerfassung 500); Hoerliste (auffaellig/Probe/behalten/Grenze von Hand) mit Befund + Werten (Naht dB, FA, Stueck, Dauer x), Drehbuch mit Quelle je Segment und Schnitt a–b, Player Hoerspiel + Quellen (Takes, Erzaehler 500); je Satz "neu bauen" (Kosten), "Erzaehlerfassung behalten"/"wieder bauen", Schnittgrenzen je Segment setzen bzw. von Hand aufheben (0 $); Regler je Werk Budget/auffaellig-max/Dauer/Versuche/Naht-dB/Ueberblendung/FA-min/Stueck-min (Schnitt Modal/CPU, Lautheit nicht im Monitor); Kostenfreigaben-Protokoll. s510: --kosten-freigeben [LG=]USD je Sprache (wie 500; nicht freigegebene Sprachen warten, Gate mensch kosten_<lg>, Abdeckung dort nur Hinweis), Protokoll 510_kosten.json mit sprache; Metrik kosten_je_sprache (saetze/takes/zeichen/usd). werk_api _m510_daten/_m510_argv. Tests test_s510 +3 (30), gesamt 577 OK. Sicherung archive/2026-11-15_m510/. Happy Prince: Monitor laeuft (3,6 s), de 522 Hoerspiel-Saetze, 523 Takes ~0,70 $; 510 live erst nach Gate 500 frei (EN offen). Cockpit-Server neu starten. Naechster Monitor: 520/530.
- 2026-11-15 Monitor 520 (Wortzeiten + 525) fertig: Tabelle je Sprache x Spur (Saetze, gemessen, zu messen, Lautwoerter mit Zeit vs. Schwelle, unplausible Wortdauer, Befunde, von Hand, Lesetext != 340), Wortbruecke Anker mit Zeit je Zielsprache (-> 340); Pruefliste (auffaellig + von Hand) mit Filter; Karaoke je Satz (Teil-Abruf ?lang&spur&ids, auch beliebige Satz-ID): Endfassung 530 abspielen, Wort laeuft mit, Woerter ohne Zeit markiert; Wort anklicken -> Anfang/Ende setzen (Feld oder "= Abspielposition"), anhoeren, merken; je Satz "neu messen"; Regler Lautwoerter-min, Anker-min, Wortdauer min/max, Unplausibel-max, Toleranz, Interpolation (FA/Wiederholen nicht im Monitor). s520: --zeit allein prueft danach die ganze Stage (vorher nur Teillauf --lang/--spur). Monitor 530 (Audio-Pruefung) fertig: Tabelle je Sprache x Spur (Endfassung x/y + Minuten, FA offen, Tempo, Rand max, Sprachpruefung je Stufe, Hoerliste), Kapitelpegel (LUFS vor/nach, Verstaerkung, begrenzt, Spitze; ausserhalb rot); Hoerliste gekippt/Verdacht/ohne FA/angenommen mit erkannter Sprache, CER, erkanntem Text, Player Roh (500/510) | Endfassung; je Satz "neu bauen", "annehmen" (Grund Pflicht), Link neu vertonen 500/510; Regler Tempo je Sprache, Rand vor/nach/max, LUFS-Ziel/Toleranz, Spitze, Verdacht-max, ohne-FA-max, CER-Verdacht, Nachvertonungen, Nachvertonen an/aus. s530 NEU --annehmen ID --grund (mit --lang/--spur) -> work/530_entscheidungen.json (gilt bei gleichem datei_hash der Endfassung; angenommene Saetze zaehlen nicht als gekippt/Verdacht/ohne FA; Hoerliste "angenommen"; danach ganze Stage geprueft). werk_api _m520_daten/_teil/_argv, _m530_daten/_argv. Tests test_s520 +1, test_s530 +1, gesamt 579 OK. Sicherung archive/2026-11-15_m520_530/. Happy Prince: Daten 520 0,8 s, 530 8,6 s (Probelauf). Altwerke (Alice u. a.) haben 520 nur im Altformat -> Monitor zeigt nichts, bis die Kette dort laeuft. Cockpit-Server neu starten. Naechster Monitor: 540 (Trennung), danach 600/610/615.
- 2026-11-15 Monitor 540 (Trennung Figur <-> Erzaehler) fertig: Kopf (Regel-Version, ECAPA-Schwelle Regel/je Werk, D-Schwelle, Messung modal/cpu, neu noetig je Sprache ~0,03 $); je Hoerspiel-Sprache Erzaehler mit Hoerprobe, Kontrolle Hoerbuchspur (pyannote Sprecher, != 1 -> Link 500), Wechsel-Recall, Umfang (Figuren/Stuecke/Saetze/Erzaehlersaetze, Regionen wortzeiten/schnitt), Plan-Fehler/Hinweise, Messung aktuell/veraltet (Eingangs-Hash); Figurentabelle Figur | Stimme + Ziel-Hoerprobe | Korrektur (Formant/HT, Vorschlag, Protokoll) | Rede (Saetze/Stuecke/s) | ECAPA Erz. vs. Schwelle | Ziel | D | pyannote | Runde | Urteil + Grund + Annahme | Hoerprobe A Figur / B Erzaehler | Handeln: Korrekturstufe ▲/▼ (Stufen 0,94/0,97/1,0/1,05/1,10), HT, Korrektur entfernen, annehmen, -> 410 umbesetzen; Regler ECAPA-Schwelle, Redezeit-min, Nachrunde, Messung neu; Protokoll 540_entscheidungen. s540: --korrektur und --annehmen mehrfach je Aufruf, danach EIN Neubau 510 -> 530 -> 520; run() gibt g.plaene zurueck (Probelauf). werk_api _m540_daten/_m540_argv. Tests test_s540 +2 (21), gesamt 581 OK. Sicherung archive/2026-11-15_m540/. Happy Prince nicht angefasst; Monitor dort pruefen, wenn 510 -> 530 -> 520 durch sind. Cockpit-Server danach neu starten. Naechster Monitor: 600/610/615.
- 2026-11-16 510 Pegel-Ursache (CK): Happy Prince de 101/522 auffaellig (92 Naht, 9 Dauer) schon seit dem 1. Volllauf 15.11. 16:54, NICHT durch 540-Korrektur. Ursache: montage() glich die Figur an den RMS der GANZEN Erzaehlerfassung 500 an; die stehenbleibenden Einschuebe ("sagte er") liegen im Mittel 4,7 dB darunter -> Figur ~6 dB lauter als der Erzaehler daneben (97 % der Naehte). Fix s510 VERSION 2: Bezug = aktiver Pegel (_db_aktiv: 30-ms-Rahmen, Pausen/Ueberblendung raus) der Erzaehlerstuecke im Satz, ohne Einschub die ganze Fassung; Naht-Pruefung ebenfalls aktiver Pegel. Schaetzung Happy Prince: Naehte > 3 dB 131 -> 4. Tests test_s510 +2 (32). Sicherung archive/2026-11-16_510_pegel/. VERSION 2 macht alle Hoerspiel-Saetze offen; Takes bleiben (Take-Hash unveraendert) -> Neuschnitt 0 $ (nur noch auffaellige bekommen in der Wiederholung neue Takes). OFFEN Happy Prince: Freigaben 510/540 (16.11. 12:43) zuruecknehmen, dann 510 -> 530 -> 520 (Hoerspiel-Wortzeiten waren leer) -> 540. Die 11 Nachrunde-Korrekturen aus 540 stehen in casting.json und werden mitgebaut.
- 2026-11-16 Happy Prince nach 510 v2: 510 auffaellig 101 -> 15 (9 Dauer kurze Ausrufe, 6 Naht), Wiederholung 0,016 $, CK frei 14:03; 530/520 neu (520 Hoerspiel-Wortzeiten jetzt 522/522), 540 Messung modal 272 s mit den 11 Korrekturen: 8 jetzt getrennt (u. a. Happy Prince 0,555->0,603, Swallow 0,557->0,626), 3 umbesetzen (little boy 0,411, Duck 0,562, Green Linnet 0,597 knapp), 9 zu kurz, 23 ok, Kontrolle Hoerbuch 1 Sprecher. CK frei 14:57 (Gate-Freigabe, keine Einzelannahme). Modal-Tracebacks im Log = Aufraeumen des Modal-Clients, Messung erfolgreich.
- 2026-11-16 Monitor 600 (Klappentext) fertig: Kopf (Modus/Herkunft/Sprachen/Modell, Genre-Auswahl aus fester Liste mit Gruppe, Hauptfigur-Geschlecht, Ton/Essenz, Laenge je Sprache vs. Laenge-max, Kosten Ist + alles neu/Koeder neu/Block neu); Shop-Vorschau je Sprache nebeneinander (Koeder kursiv, Einordnung, Autor, Vermerke), Befunde am Satz rot (leer/Sprache/Kopie/Lizenz/Markup, Koeder nicht woertlich, Vermerk), Satz anklicken = ersetzen (Einordnung/Autor; manuell mit 'm'), Block neu erzeugen (Koeder/Einordnung/Autor, Kosten); Koeder: Werktext 190 im Editor (nur lesen, Strg+F), Markierung als Koeder uebernehmen oder Modell-Vorschlag zurueck (Zielsprachen aus 330); Pruefungen Autor-Fakten (ungedeckt + author.json, -> 110), Sicherheit/Edition annehmen mit Grund (gilt/veraltet); Regler Modus (uebernehmen nur mit ePub-Klappentext, Verlag gesperrt), Laenge-max, komplett neu; Protokoll. s600: NEU --annehmen sicherheit|edition --grund (600_entscheidungen.json angenommen, gilt bei gleichem ausgabe_hash), --laenge-max je Werk in book.json klappentext_regler (vorher nicht gespeichert), kosten_schaetzen(), run() liefert befunde/laenge_max (Probe). Altformat-600 (alle Bestandswerke) -> Monitor meldet 'einmal laufen lassen'. werk_api _m600_daten/_teil/_argv. Tests test_s600 +3 (24), gesamt 586 OK. Sicherung archive/2026-11-16_m600/. Cockpit-Server neu starten. Naechster Monitor: 610, dann 615.
- 2026-11-16 Monitor 610 (Cover-Illustration) fertig: Bild gross + Pruefwerte je Metrik (Breite, Format, Randfarbe, Text im Bild, Motivhoehe, Zentrum, Linien) vs. Schwelle, Herkunft/Modell/Stimmung aus 600, Prompt + Versuche, Kosten Ist/je Bild; Motiv (englisch), Bildweg behalten | neu erzeugen | Varianten 2-6 (Galerie mit Rot-Chips, waehlen 0 $) | eigenes Bild hochladen (/api/upload art=cover -> daten/uploads), Reihen-Erbe; trotz Rot annehmen mit Grund (gilt/veraltet); Schwellen je Werk; Protokoll. s610: NEU --annehmen --grund (610_entscheidungen angenommen, gilt bei gleichem bild_hash), kosten_schaetzen() (0,039 $/Bild), run() liefert g.bild (Probe). GEAENDERT: automatische Neuerzeugung bei Rot nur noch fuer frisch erzeugte bzw. erstmals uebernommene Bestandsbilder – vorher erzeugte jedes 'neu pruefen' eines roten Bildes kostenpflichtig neu. Monitor 615 (Cover final) fertig: Galerie Sprache x Variante (Zustand, Probe, Pruefpunkte, 'Datei veraltet'), eine Sichtfreigabe fuer alle offenen Varianten (nur ohne offene Aenderungen); Typo-Felder Titel je Sprache, Umbruch (Zeilen mit |), Schrift auto/84-48, Position, Deckkraft Titelkasten, Sprecherzeile – Live-Vorschau je Kachel ueber Teil-Abruf (Probe, schreibt nichts). s615: --trocken uebernimmt Titel/Umbruch/Layout-Regler jetzt im Speicher (vorher in der Probe ignoriert). Bestandswerke: Happy Prince/Art of War 610 rot (Breite 832 px; Motivhoehe bzw. Randfarbe) -> im Monitor entscheiden. werk_api _m610_*/_m615_*, upload art cover. Tests s610 +2 (24), s615 +2 (24), gesamt 590 OK. Sicherung archive/2026-11-16_m610_615/. Cockpit-Server neu starten. Damit haben alle Mensch-Gates einen Monitor -> naechstes: Tausch 520/530 (Merkliste).
- 2026-11-20 Art of War 500 (Befund): Gate 500 war am 19.11. per 'Freigeben' frei gesetzt, ohne Kostenfreigabe -> 0 Saetze vertont, 530 stoppte mit Ruecksprung 500 (Schleife). Lauf mit --kosten-freigeben de/en ab 20.11. 04:45; Gemini lief seriell (~6 h fuer DE). FIX s500 Gemini PARALLEL: Regler 'parallel' (Standard 4, 1-8, je Werk vertonung_regler; Monitor 500 'Gemini parallel'), Bloecke/Solo-Saetze per ThreadPool, Blockschnitt (MMS_FA fa_cut/slice_block) unter Sperre seriell (RAM, Learning 22.10.), QuotaError haelt weitere Auftraege an, Fertiges bleibt verbucht. Kosten unveraendert. Tests test_s500 +1 (30), alle Testdateien OK. Sicherung archive/2026-11-20_500_parallel/. Wirkt ab dem naechsten 500-Lauf (laufender Art-of-War-Lauf nutzt noch den alten Code). Offen: Gate-'Freigeben' bei reinem Kostenbefund 500/510 sperren.
- 2026-11-20 s510 Takes PARALLEL (gleiche Mechanik wie 500): Regler 'parallel' (Standard 4, 1-8, book.json hoerspiel_regler; Monitor 510 'Gemini parallel'); Policy-Ablehnung -> Satz 'policy', weitere Takes des Satzes entfallen; QuotaError haelt alles an. Schnitt (Modal/CPU) unveraendert gebuendelt. Tests test_s510 +1 (33) OK. Sicherung archive/2026-11-20_500_parallel/.
- 2026-11-20 s500 Satzpruefung Gemini auf MODAL-GPU (Befund Art of War DE: 2742 Saetze ~5 h seriell auf CPU, FaPruefer war fest "cpu"): NEU gpu_tts/pruef_modal.py (App readlayer-pruef500, gleicher Pruefer cb_pruefung.py mit cuda, 150 Saetze je Aufruf, L4/A10G/T4), s500 pruefen_viele()/pruefen_modal() (WAVs 16 kHz mono ins Volume readlayer-tts /s500/<werk>/<lg>/<zeit>, danach geloescht; GPU-Sekunden usage_log teil=pruefung), CPU-Rueckfall je fehlendem/fehlerhaftem Satz bzw. bei Modal-Ausfall; unter 20 Saetzen, Mock und Testpruefer lokal. Regler 'fa' modal|cpu (Standard modal, CLI --fa; Monitor 500 noch ohne Schalter). Wiederholungen (gemini_reparieren) pruefen weiter einzeln lokal. Probe: tools/test_pruef_modal.py <werk> --lang de --n 40 (Modal vs CPU, schreibt nichts). Tests test_s500 +4 (34) OK. Sicherung archive/2026-11-20_500_pruefung_gpu/. Laufender Art-of-War-Lauf nutzt noch den alten Code -> EN: Lauf waehrend der EN-Vertonung abbrechen und neu starten (WAVs werden uebernommen, ungeprueft -> nur Pruefung). Offen: FA-IndexError beim Blockschnitt (Art of War c020_00077..00101 -> Fallback einzeln).
- 2026-11-21 Art of War bis 615 frei. Befunde: (1) 620 stoppte 'Gate 650 nicht frei' – Kettenreihenfolge hatte 650 nach 620/630/640, obwohl 620/630 (Audio-Variante) 650 brauchen. FIX: status.STAGES (+ tools/stage_skript.py, run.py-Kopf) jetzt ... 615, 650, 620, 630, 640, 700, 710; Tests status/kette/cockpit/s620/s650/s700/s710 OK; Sicherung archive/2026-11-20_500_parallel/ (status.py, stage_skript.py, run.py). (2) 650 stoppte 'Gate 615 en:quadrat (mensch)': 615 war ueber den allgemeinen Knopf 'Freigeben' frei gesetzt, die Teile (6 Varianten) blieben mensch -> Sichtfreigabe im Monitor 615 noetig (gleiche Falle wie 500 Kostenfreigabe). (3) KORREKTUR Claude: 650 HAT Mensch-Pruefungen (ansagen, dauer, kapitel_laenge, profil_*, Kanal extern immer Mensch) – ebenso 620 (geklebt, Verlag-Vorschau), 640 (auffaellig), 700 (Verlag), 710; der Gate-Katalog vom 03.11. listet sie nicht (spaeter gebaut). Ohne Mensch-Pruefung im Code: 080, 090, 300, 320, 630 (190 hat Anzeige-Monitor). CK-Idee: Stages ohne Mensch-Entscheidung an eine Nachbar-Stage haengen; Stages mit Mensch-Pruefung brauchen einen Monitor -> AP 'Nachbar-Stages bauen' beginnt mit Bestandsaufnahme aus dem Code.
- 2026-11-21 AP Nachbar-Stages GEBAUT. Bestandsaufnahme aus dem Code: ohne Mensch-Pruefung nur 080, 090, 300, 320 (nur pflicht/gleich/mock -> Stopp). 630 ist KEIN Nachbar: laeuft ueber s620.lauf, also wie 620 geklebt -> Mensch (200) und Verlag-Vorschau immer Mensch -> CK: 620+630 bekommen einen gemeinsamen ePub-Monitor. Ohne Monitor mit Mensch-Pruefung: 620/630, 640 (auffaellig, Verlag), 650 (ansagen, dauer, kapitel_laenge, profil LUFS/Peak/Rauschen, Kanal extern immer), 700 (Verlag-Endabnahme), 710 (Katalog-Erstfreischaltung, externer Upload, Verlag) -> Folge-AP. BAU: kette.NACHBAR {080:095, 090:095, 300:310, 320:330} + nachbar()/mitlaeufer(). run.py: --only/--from <Nachbar> nimmt die Mitlaeufer mit (ohne --force; frei = skip, offen/veraltet = laeuft). werk_api: Felder nachbar/mitlaeufer/nur_kosten je Stage, naechster.monitor (300 haelt -> Monitor 310), monitor() liefert mitlaeufer; 'Uebernehmen und neu pruefen' stellt run.py --only <Mitlaeufer> voran, wenn dieser offen/veraltet ist (Laeufe.start nimmt jetzt eine Folge von Aufrufen, Abbruch beim ersten Exit != 0, Stopp bricht die Folge ab). monitor.html: Mitlaeufer als kleine graue gestrichelte Unterschritte in der Kettenleiste (Link -> Nachbar-Monitor), Gate-Kopf zeigt je Mitlaeufer Zustand, bei Halt Befunde + Ruecksprung-Knoepfe; allgemeine Ansicht ohne 'Monitor noch nicht gebaut' (Nachbar-Stages: 'braucht keinen Monitor – laeuft automatisch mit <Nachbar> oder springt zurueck'). werk.html: Mitlaeufer grau eingerueckt, Monitor-Link -> Nachbar. FALLE 1: 500/510 reiner Kostenbefund (alle Gruende 'Kosten ... nicht freigegeben' bzw. 'Kostenfreigabe je Sprache noetig') -> 'Freigeben' gesperrt (Server aktion + Monitor-Kasten 'Kostenfreigabe noetig' + werk.html ohne frei-Knopf); Anhalten und Admin-Override bleiben. FALLE 2 (CK: alle offenen Teile mit freigeben): 'Freigeben' auf Stage-Ebene gibt jeden Teil im Zustand mensch frei (je Teil ein Protokolleintrag), Stopp-Teile bleiben; Kasten nennt die Zahl offener Teile. Tests: test_kette +2 (21), test_cockpit_werk +4 (11), test_status/test_gate OK (je Datei einzeln). Sicherung archive/2026-11-21_nachbar/. Cockpit-Server neu starten.
- 2026-11-21 FIX 530 Auslaute (CK hoerte Art of War: Satzenden DE+EN zu scharf, Endkonsonanten weg). Ursache: 500 schneidet auslautsicher (Pausenschnitt + Trim Schwelle 60 + 120 ms), aber 530 schnitt jeden Satz neu ab FA-Wortende + 120 ms (+30 ms Ausblendung); MMS_FA setzt das Wortende vor leise stimmlose Auslaute, die Konsonanten-Regeln (schnitt_lib, Plosiv 70/Frikativ 120 ms) galten in 530 nie. Messung Art of War (800 Saetze je Sprache): Klang hinter dem Schnitt bei DE 34 %, EN 49 %. FIX s530: klang() geht ab FA-Grenze nach aussen, solange Klang (> p95 -40 dB) folgt, Luecken bis 80 ms (Plosiv-Verschluss), hoechstens 350 ms hinten / 200 ms vorn (Atmer draussen); Raender vor/nach und Pruefung rand_max ab Klanganfang/-ende; Ausblendung Ende 10 ms. Art of War: Ende im Median +60 ms (DE) / +92 ms (EN), Deckel 350 ms bei 3 % / 0,6 %. SCHNITT=2 im Satz- und Kapitel-Hash -> 530 schneidet beim naechsten Lauf alles neu aus der Rohfassung 500 (keine Neuvertonung, FA bleibt gecacht; Whisper-Pruefung und 520 laufen fuer die neuen Endfassungen erneut). Wirkt auch fuer Teaser 640 (gleiches schneiden). Tests test_s530 +1 (19), test_s640 OK. Sicherung archive/2026-11-21_530_auslaut/. Art of War: Cockpit 'ab 530' (run.py --from 530), dann CK hoert.
- 2026-11-22 FIX 500/510 Kleinbetrag: Art of War 500 hing an 'Kosten ~0.00 $ fuer 9 Saetze (en chatterbox) nicht freigegeben' (Somnio-Budget 0,00 $; Nachvertonung der in 530 gekippten Saetze), 'Freigeben' seit 21.11. gesperrt -> CK konnte nur anhalten. Jetzt: Sprache mit Schaetzung < config.KOSTEN_KLEINBETRAG_USD (Standard 0,01 $) braucht keine Kostenfreigabe. Tests test_s500 +1 (35), test_s510 OK (Tests setzen Kleinbetrag 0). Sicherung archive/2026-11-22_kleinbetrag/. Art of War: Monitor 500 '500 neu pruefen', danach 530 (Befunde unveraendert seit 20.11.: spitze_de 20, gekippt de 1 / en 9 c002_*_qt, verdacht de 6,2 % / en 5,5 % -> im Monitor 530 anhoeren/annehmen).
- 2026-11-15 VORGEMERKT (CK): Tausch der Stage-Nummern 520/530 nach Abschluss aller Monitore (Merkliste oben).
- 2026-11-15 Monitor-Rahmen (CK): laeuft ein Lauf des Werks, zeigt der Gate-Kopf "laeuft seit ..." (Art + Stage aus dem Befehl) und den letzten Stand vor dem Lauf; alte Befunde und Kasten "Entscheidung noetig" sind ausgeblendet, bis der Lauf fertig ist (danach laedt der Monitor neu). Nur cockpit/monitor.html, Sicherung archive/2026-11-15_m520_530/monitor_vor_laufkopf.html. Anlass: 510 Happy Prince zeigte waehrend des Laufs den alten Kostenbefund.
- 2026-11-22 Monitor 650 (Hoerbuch) fertig: Kasten "Naechster Schritt" ganz oben (UX-Regel CK 22.11.: genau ein Hauptknopf – Aenderungen uebernehmen | Hoerprobe anhoeren + oben freigeben | Ruecksprung | 650 bauen | fertig -> naechste Stage); je Sprache Zustand (Gruende in Laiensprache), Hoerprobe ePub/Plattform, Freigabe Plattform (wer/wann/Grund), Cover _quadrat, Dauer, M4B; Ansagen aus 400 mit Player; Kapiteltabelle je Profil (Dauer, LUFS, Spitze, Rauschen, Stille vorn/hinten, Rate/Bitrate rot ausserhalb, Player); Regler Ausgabe mp3/m4b/beide, Ansagen an/aus, Sprache neu bauen; Profilwerte nur Admin (Server prueft). RAHMEN: MON[stage].entscheidungText() ersetzt den Standardtext im Kasten "Entscheidung noetig", MON[stage].freigeben(grund) ersetzt die allgemeine Freigabe (650 -> s650 --freigeben, setzt die einmalige Hoerprobe-Freigabe); Helfer schritt()/schrittFertig(). s650 NEU --grund zur Freigabe. werk_api _m650_daten/_m650_argv. Tests test_s650 +1 (8), test_cockpit_werk OK. Sicherung archive/2026-11-22_monitore/. BEFUND: 650 baut nur Hoerbuch-Stufe basic (profile_fuer) -> Art of War DE (Hoerbuch premium, Kanal extern) bekommt KEIN Hoerbuch; Monitor zeigt das als Hinweis -> entscheiden. BEFUND Art of War: Ansage Autor "by active 6th century B.C. Sunzi." (Lebensdaten in den Namen geraten, 110/400).
- 2026-11-22 Monitor 620/630 (ePub) fertig – EIN Monitor fuer beide Stages (/monitor#<id>/620 und /630 zeigen dieselbe Ansicht, Gate-Kopf je Stage): Kasten "Naechster Schritt" (Aenderungen uebernehmen | Leseansicht + oben freigeben | -> andere Stage | Ruecksprung | bauen | fertig); Reiter je Sprache (Original 620 / Ziel 630, ● = wartet), Kacheln je Variante Text/Audio mit Pruefwerten vs. Soll (epubcheck, Textabgleich, Kapitel, Vermerke, Bilder, Fussnoten, Rueckfall 630, SMIL), geklebte Kapitel (-> 200), Rueckfall-IDs (-> 310), epubcheck-Meldungen, Download; LESEANSICHT aus dem gebauten XHTML (Teil-Abruf ?scope&seite: Spine-Seiten, CSS und Bilder inline, iframe srcdoc; CK 21.11. kein epub.js); Audio-Variante: Kapitel-MP3 aus dem ePub nach work/_620/<scope>/ entpackt (Cache), Satzmarkierung laut SMIL beim Abspielen, Klick auf Satz springt. Regler Mobil-Absaetze an/aus + Laenge, Bilder, Fussnoten, Sprache neu bauen, Kolophon nur Admin; Regler gelten fuer 620+630 -> Speichern startet s620 (mit Reglern) und s630 nacheinander (monitor_speichern nimmt jetzt auch eine Folge von Aufrufen). s620/s630 NEU --grund zur Freigabe. Tests test_s620 +2 (25), test_cockpit_werk, test_s650 OK.
- 2026-11-22 Monitor 640 (Teaser) fertig: Kasten "Naechster Schritt" (Aenderungen uebernehmen mit Kostenangabe | Teaser am Stueck anhoeren + oben freigeben | Ruecksprung | starten | fertig); je Sprache Zustand (Laiensprache), "am Stueck" (Saetze nacheinander), Stimme/Engine/Herkunft (Stopp-Grund + Ruecksprung), Stil/Tempo, Kosten bisher/alles neu; Satzliste Block | Text (+ Whisper-Abschrift bei Abweichung) | Player | Befund in Laiensprache / angenommen / Text geaendert | neu vertonen (~$ je Satz) / annehmen mit Grund; Regler je Sprache Stimme/Engine/Tempo/Stil (leer = automatisch), Aussprachehinweis Autor, alle Saetze neu; Probe = Kostenschaetzung. Verlag-Freigabe ueber den Rahmen (gilt bei gleichem ausgabe_hash). werk_api _m640_daten/_m640_argv. Tests test_s640 +1 (16) OK.
- 2026-11-22 Monitor 700 (Auslieferungs-Vertrag) fertig: Kasten "Naechster Schritt" (Aenderungen uebernehmen | 700 pruefen | erstes rotes Produkt -> Sprung in die Stage des Befunds | oben abnehmen | fertig); Produkttabelle (Sprache · Inhalt/Stufe -> Kanal in Klartext, Zustand, Bausteine je Stage als gruen/rote Chips mit Sprung in den Monitor der Stage, Befund als Tooltip, liefern ja/nein); zurueckhalten mit Grund / wieder liefern (mehrere -> Folge von s700-Aufrufen); Verlag-Endabnahme je Produkt ("abnehmen", Stage-Freigabe nimmt alle ab). Daten aus work/700_guard.json – KEIN Probelauf in der Anzeige (hasht alle Auslieferungsdateien, Art of War ~75 s). werk_api _m700_daten/_m700_argv. Tests test_s700 +1 (16) OK.
- 2026-11-22 Monitor 710 (Auslieferung) fertig: Kasten "Naechster Schritt" (Aenderungen | -> 700, solange 700 nicht frei | oben freigeben | neu starten | ausliefern, vorher Probelauf); Katalogstatus (freigeschaltet/zurueckgezogen/privat), Kanaele je Sprache mit Zustand und lieferbaren 700-Scopes, je Ziel (gcs/lokal) Scopes mit Dateien/MB/Inhalt/Ergebnis, Plattform-Paket je Sprache (Ordner, Metadaten Titel/Autor/Sprecher/ISBN/Dauer, Plattformen zulaessig/nein/Rueckfrage, hochgeladen wer/wann). Regler Ziel, Bitrate TAELLA, nur Manifest, nur Kanal; Probelauf (--dry, Dateiliste im Lauf-Log). "Freigeben" im Kasten Entscheidung = --freigeben (Katalog) und/oder --extern-hochgeladen LG je nach offenem Teil. Werk zurueckziehen nur Admin (Server prueft). Rahmen: entscheideStandard(). Daten aus work/710_export.json. werk_api _m710_daten/_m710_argv. Tests test_s710 +1 (20), test_cockpit_werk/test_kette/test_status OK. Render-Probe aller 5 Monitore (node, Art-of-War-Daten): fehlerfrei, je genau ein Hauptknopf. ALLE MONITORE GEBAUT. Cockpit-Server neu starten.
- 2026-11-22 BEFUNDE Art of War (Probelauf 700, nur lesen): alle Audio-Produkte veraltet (Gate 500 22.11. 10:08 neuer als 530 21.11. 23:18; 520 aelter als 530; 650 aelter als 530) -> 530 -> 520 -> 650 -> 620 neu laufen lassen. de:hoerbuch-premium:extern stoppt in 700 an der Gemini-Regel (config.GEMINI_AUDIO_KANAELE nur taella; ACX nimmt kein Gemini-Audio) -> im Monitor 700 zurueckhalten. Titelseite ePub und Ansage nennen den Autor "active 6th century B.C. Sunzi" (Lebensdaten im Namen, Quelle 110). (Die Meldungen "Cover-/ePub-Datei fehlt" im Linux-Probelauf kommen von Windows-Pfaden mit Backslash im Manifest – unter Windows kein Befund.)
- UX-STOLPERSTEINE Nachtrag (22.11.): 2. Monitor-Kasten "Entscheidung noetig" spricht jetzt je Stage Laiensprache (650/620/640/700/710); die aelteren Monitore 100–615 nutzen noch den Standardtext und haben keinen Kasten "Naechster Schritt" -> im UX-Durchgang nachziehen (Helfer schritt()/schrittFertig(), Hooks entscheidungText/freigeben). 3. Verlag-Endabnahme 700 je Produkt ueber Browser-Eingabefenster (prompt) -> im UX-Durchgang durch Feld ersetzen.
- 2026-11-22 ENTSCHIEDEN (CK): Fremdsprachige Saetze im Quelltext (Art of War: 5 franz. Amiot-Zitate) werden in 120 in die Werksprache UEBERTRAGEN und ERSETZEN das Original (Lese- und Hoertext nur Werksprache; Original in 120_fremd.json). Abkuerzungen/Zahlen (ch., p., pp., ff., Kap., S. …) werden in 400 per Tabelle je Sprache ausgesprochen, Rest als Befund im Monitor 400. Startprompt: claude/PROMPT_abkuerzungen_fremdsprache.md (Teil A 400, Teil B 120).
- 2026-11-22 AP Abkuerzungen Teil A GEBAUT (Stage 400, 0 $; Startprompt claude/PROMPT_abkuerzungen_fremdsprache.md). Sicherung archive/2026-11-22_abk_fremd/.
  NEU config/abk_sprech_en.json + abk_sprech_de.json (Eintraege abk/wort/bedingung immer|zahl|nach_zahl|name/plural/zahl_sprechen; gleiche Abk. mehrfach = Alternativen; DE zusaetzlich Bl. -> Blatt), je Werk davor book.json abk_sprech {lg: [...] oder {abk: wort}} (wort "" = bleibt stehen, kein Befund).
  pipeline/sprechtext.py: Regel _r_abk (vor Schluessel-Roemisch), REGELN_V 3 -> 4; folgende Zahl/Bereich/roem. Zahl als Wort ("p. 12" -> page twelve, "pp. 12–14" -> pages twelve to fourteen, "ch. 148-162" -> chapters ... to ..., "vol. I. p. 4" -> volume one, page four, "S. 12 ff." -> Seite zwoelf folgende); Satzende-Punkt bleibt ("etc." am Ende -> "et cetera."); Gross am Satzanfang (Cf. -> Compare). Mehrdeutig: p./S. nur mit Zahl, f. nur nach Zahl (sonst Folio -> Befund), ed. vor Name = edited by / nach Zahl = edition, tr. vor Name. Ordinalzahlen "6th" -> sixth ueber erweiterte Regeln (geprueft).
  s400: neue Pruefung abkuerzung_<lg> (st.abk_offen, Schwelle 0 -> Mensch; Initiale "J. S. Bach"/"P. Smith" kein Befund); --abk-sprech LG:ABK=WORT schreibt book.json abk_sprech (WORT - loescht). Monitor 400: Befundart "Abkuerzung offen", Kasten "Abkuerzungen · Werktabelle" (vormerken/loeschen, Sprachtabelle aufklappbar); werk_api liefert abk je Sprache.
  Satzgrenzen 200: NEU config/abk_en.txt (chap, chaps, p, pp, f, ff, sqq, vols, op, cit, loc, ibid, ed, tr) + abk_de.txt (f, ff, anm, hg, hrsg, bl); s200.abk_liste nimmt zusaetzlich alle Teile der Sprech-Abkuerzungen (Sprache + Werk) -> Listen koennen nicht mehr auseinanderlaufen; Test prueft den Abgleich.
  Tests: NEU tests/test_abk_sprech.py (12, synthetische Werke); einzeln gruen: test_s400 18, test_s200 16, test_cockpit_werk 11, test_s410 16, test_s420 15, test_s500 35, test_s510 33, test_s520 14, test_s530 19, test_s540 21, test_manifest 5, test_gate 6.
  PROBELAUF Art of War 400 (--trocken, nichts geschrieben): Befund abkuerzung en 2 (c008_00017_s "f. 1", c019_00162_s "f. 3" = Folio -> im Monitor 400 "f." -> "folio" mit Bedingung zahl in die Werktabelle oder Sprechtext von Hand), de 0; roemisch en 15 / de 17 unveraendert. Sprechtext geaendert en 151 / de 150 Saetze -> in 500 neu zu vertonen (Kosten vorher im Monitor 500, CK-Freigabe). Befund 200: "chap." am Satzende zerlegte Saetze (c008_00116_fn, c016_00018_s; DE "zweiundzwanzig ff." c008_00004_s) -> wird mit 200-Neulauf behoben (Reihenfolge laut Startprompt: Teil B, dann 120 -> 200 -> 400).
  NAECHSTES: Teil B (Fremdsprache 120).
- 2026-11-22 15:35 ENTSCHIEDEN (CK, ersetzt "Fremdsprache immer ersetzen"): (1) Abkuerzungen werden schon in 120 im Lesetext der MODERNISIERTEN Fassung ausgeschrieben (Teil A2, gleiche Tabelle wie 400, Ziffern bleiben; Fassung original -> nur 400 spricht aus). (2) Fremdsprachige Zitate werden in 120 geflaggt; je Zitat Entscheidung im Monitor 120: uebertragen (ersetzt Original, Original in 120_fremd.json) | Original behalten (Sprachkennung am Knoten, 310 uebersetzt nicht, 400/500 sprechen in Originalsprache) | kein Fremdtext. Startprompt aktualisiert: claude/PROMPT_abkuerzungen_fremdsprache.md, naechster Auftrag "Teil A2 bauen".
- 2026-11-22 15:33 BESTAETIGT (CK): "Original behalten" = Satz bleibt in allen Fassungen im Original (310 uebersetzt nicht), Hoerbuch spricht ihn in Originalsprache. Beispiel: "Je ne regrette rien" bleibt so.
- 2026-11-22 15:40 NACHTRAG Teil A: "ff." nur nach Zahl aufloesen (EN+DE); "ch. 34, ff. 4, 5" = Folios -> Befund (Art of War c019_00581_s, c020_00027_s). Befund 200 Art of War: ~20 Saetze nach "chap."/"ch." zerlegt (c008, c015, c016, c018-c020); LLM-Checkpoint hat sie ganz -> 200 aus Checkpoints (0 $) mit neuer Abk-Liste repariert sie. Tests test_abk_sprech 12, test_s400 18 gruen.
- 2026-11-22 AP Fremdsprache Teil B GEBAUT (Stage 120, jede Fassung; Entscheidung CK 15:33). Sicherung archive/2026-11-22_abk_fremd/ (s120, s310, s500, s502, s530, Tests).
  NEU pipeline/s120_fremd.py: Erkennung satzweise lokal (lingua, Ersatz Funktionswoerter mit Hinweis im Gate; Kursivtitel/Eigennamen zaehlen nicht; Gegenprobe Funktionswoerter der Werksprache gegen Fehlalarme wie "Such is the art of manœuvering."), aufeinanderfolgende Fundsaetze = EIN Zitat. work/120_fremd.json (Zitate, Stellen, Entscheidung offen|uebertragen|behalten|kein, Uebertragung je Satz, herkunft llm|hand, angenommen). Regler book.json fremd_regler {schwelle 0.5, min_woerter 4, vorgabe einzeln|alle_uebertragen|alle_behalten}.
  s120: Schritt nach der Modernisierung; "uebertragen" -> LLM (Modell wie 120, Kontext davor/danach, Kosten-Metrik fremd_kosten_usd) -> eingesetzt in chapter-N.json (Basis in paragraphs_vor_fremd, Ruecknahme jederzeit) + raw_modernized.txt. Gate: fremd_offen / fremd_uebertragung (nicht angenommen) / fremd_einsetzen -> Mensch. CLI --fremd ID=E, --fremd-text ID=S1 || S2, --fremd-annehmen ID|alle, --fremd-neu ID, --fremd-schwelle/-min/-vorgabe. Modernisierungs-Prompt: fremdsprachige Passagen unveraendert lassen (ohne PROMPT_V-Wechsel -> kein Neulauf bestehender Kapitel).
  Kette "Original behalten": 200 setzt sprache_satz=<lg> am Knoten; 310 kopiert das Original ohne LLM/Befunde; 330/340 ueberspringen; 400 Sprechtext nach Regeln der Satzsprache + production.sprache[tid][lg] + Stil-Hinweis "quotation in French" (auch basic); 500 Einheit traegt sprache, Hinweis im Gate (Chatterbox: spricht mit dem Modell der Spur – OFFEN: Sprache je Job in gpu_tts/tts_modal_opt.py); 530 ueberspringt Whisper-Sprachpruefung.
  Monitor 120: Kasten "Fremdsprachige Zitate" (Original | Uebertragung | Sprache/p | Entscheidung; annehmen, neu uebertragen, von Hand mit ||, alle offenen uebertragen/behalten, Regler); werk_api _m120_fremd + argv.
  Tests: NEU tests/test_s120_fremd.py (12, synthetisch); alle Testdateien test_s1xx–s7xx, cockpit_werk, kette, gate, abk_sprech einzeln gruen (auch ohne lingua geprueft).
  Probe Art of War (nur lesen): lingua findet genau 1 Zitat (Kap. 2, fr, p 0,98, 6 Saetze = Amiot), keine Fehlalarme.
  VORAUSSETZUNG Windows: py -3.11 -m pip install lingua-language-detector (ca. 100 MB; ohne -> Ersatzverfahren, Hinweis im Gate).
  NAECHSTES Art of War: 120 laufen lassen -> Monitor 120 Zitat entscheiden -> 200 -> 210 -> 300–340 (betroffene Kapitel) -> 400 (Folio-Befunde: f./ff. -> folio/folios in die Werktabelle) -> 500 nach Kostenfreigabe -> 530 -> 520 -> 650 -> 620/630 -> (640) -> 700 -> 710.
- 2026-11-22 AP Abkuerzungen Teil A2 GEBAUT (Stage 120, nur Fassung modernisiert, 0 $; Entscheidung CK 15:35). Sicherung archive/2026-11-22_abk_fremd/A2/ (s120_modernisierung, sprechtext, s400, s200, werk_api, monitor.html, abk_sprech_*.json, PROJEKTSTAND).
  NEU pipeline/s120_abk.py: Schritt nach Modernisierung + Fremdsprache; gleiche Tabelle wie 400 (sprechtext.abk_tabelle: config/abk_sprech_<lg>.json + book.json abk_sprech), gleiche Bedingungen; Ziffern/roem. Zahlen bleiben ("ch. 65" -> chapter 65, "pp. 12–14" -> pages 12–14, "S. 12 ff." -> Seite 12 und folgende, "Cf." -> Compare, "etc." am Satzende -> "et cetera."). Feld lesetext/lesetext_plural je Eintrag (DE f./ff. lesetext "und folgende"). Behaltene Fremdzitate werden nicht angefasst. Basis bleibt paragraphs_vor_fremd (= Basis vor allen Nachschritten); Ruecknahme book.json abk_lesetext false.
  sprechtext.py: NEU abk_lesetext() (Sprechtext 400 unveraendert, REGELN_V bleibt 4); Tabellen-Eintraege tragen Herkunft _q werk|sprache.
  work/120_abk.json {aktiv, stellen [id K:A:ABK#n, abk, wort, herkunft sprache|werk|hand, kontext], befunde [vorschlaege], entscheidungen, verwaist}. Gate: abk_offen (Schwelle 0 -> Mensch), Metriken abk_ausgeschrieben/abk_herkunft, Hinweis abk_verwaist.
  CLI 120: --abk ID=WORT (leer = bleibt stehen, offen = zuruecksetzen), --abk-werk LG:ABK=WORT (book.json abk_sprech, wie 400), --abk-lesetext an|aus.
  Monitor 120: Kasten "Abkuerzungen im Lesetext" (offene Stellen mit Kontext: ausschreiben/eigenes Wort/bleibt stehen + Werktabelle; ausgeschriebene Stellen aufklappbar, einzeln stehen lassen; Schalter an/aus); werk_api _m120_abk + argv.
  Tests: NEU tests/test_s120_abk.py (10, synthetisch) gruen; einzeln gruen test_s120, test_abk_sprech, test_s400, test_s200, test_cockpit_werk, test_kette, test_gate, test_s310, test_s500. test_s120_fremd: 11 ok, 1 Fehler test_400_sprache_und_hinweis nur in der Linux-VM (num2words fehlt dort fuer "douze"; unabhaengig von A2).
  PROBE Art of War (nur lesen): 165 Stellen (ch. 70, Cf. 31, p. 19, chap. 16, etc. 11 ...), 4 Befunde = Folios c8:4 "f. 1", c19:46 "f. 3", c19:156 "ff. 4, 5", c20:3 "ff. 1, 2" -> im Monitor 120 per Werktabelle en:f.=folio / en:ff.=folios (Bedingung zahl) oder je Stelle. Nicht in Tabelle (bleiben): "fol.", "cent.".
  NAECHSTES Art of War: 120 laufen lassen -> Monitor 120 (Zitat entscheiden, 4 Folio-Befunde) -> 200 -> 210 -> 300–340 (betroffene Kapitel) -> 400 (findet keine Abkuerzungen mehr) -> 500 (Kostenfreigabe CK) -> 530 -> 520 -> 650 -> 620/630 -> (640) -> 700 -> 710.

- 2026-11-22 AP PARALLELE SPUREN + ZENTRALE ANBIETERGRENZEN (TODO 22.11. Punkte 7+8, Startprompt claude/PROMPT_parallel_spuren.md). Sicherung (Stand vorher) archive/2026-11-22_parallel/ (s310, api_layer, usage_log, tts_client, config, werk_api, monitor.html, werk.html, PROJEKTSTAND), Messdaten archive/2026-11-22_parallel/messung/.
  INVENTUR 080–710 (nur gelesen; Laufzeit = letzter Lauf > 5 s aus cockpit/logs/werk_*.log "--- Stage X (Ns)", AoW = The Art of War 2.729 Saetze, HP = Happy Prince 980 Saetze):
  | Stage | rechnet | Anbieter/Modell | Einheit | heute | Laufzeit letzter Lauf |
  |---|---|---|---|---|---|
  | 080/090/095/100/115/150/190/195 | lokal CPU | – | Werk | seriell | < 1 s |
  | 110 Wikidata | lokal + API | Wikidata, DeepSeek v4-pro (Fallback) | Werk | seriell | 5 s (HP) |
  | 120 Modernisierung (+Fremd, Abk) | API | DeepSeek (modernizer = translator v4-pro) | Kapitel | seriell | 886 s (AoW) |
  | 200 Tagging | API | DeepSeek v4-flash | Kapitel | seriell | 424 s (AoW), max 541 |
  | 210 Profil | API | DeepSeek v4-pro | Werk (1 Aufruf) | – | 60 s (AoW), max 256 (HP) |
  | 300 Voruebersetzung | API | DeepSeek v4-pro | Kapitel x Sprache x Abschnitt | seriell | 1.763 s (AoW), max 1.986 |
  | 310 Uebersetzung | API | DeepSeek v4-pro | Batch 25 Saetze, Kapitel x Sprache | seriell -> JETZT 12 Spuren | 1.689 s (AoW), 285 s (HP) |
  | 320 Integritaet | lokal CPU | – | Werk | seriell | < 1 s |
  | 330 Rueckuebersetzung | API | DeepSeek v4-flash (rueck + Bewertung) | Kapitel x Sprache | seriell | 1.322 s (AoW), 565 s (HP) |
  | 340 Wortalignment (+345) | API (+Modal T4 Pruefaligner) | DeepSeek v4-flash | Kapitel | parallel 5 | 395 s (HP) |
  | 400 Regie | lokal CPU | – | Satz | seriell | 2 s |
  | 410 Casting | API | DeepSeek v4-pro, Gemini Voice Design/TTS-Muster | Figur | seriell | 76 s (HP) |
  | 420 Sprecher | API | DeepSeek v4-pro | Kapitel x Sprache, Teile | seriell | 971 s (HP) |
  | 500 Vertonung | API / Modal GPU | Gemini 3.8 Flash TTS (parallel 4) / Chatterbox Modal L4; Pruefung Modal | Satz/Block | Gemini parallel 4 | 4.444 s (HP) |
  | 510 Hoerspiel | API + Modal/CPU | Gemini TTS Takes (parallel 4), Schnitt Modal | Take/Satz | parallel 4 | 366 s (HP) |
  | 530 Audio-Pruefung | Modal + lokal | FA Modal, Whisper lokal/Modal, Schnitt/LUFS CPU | Satz, Kapitel | teils | 1.832 s (AoW), max 2.578 |
  | 520 Wortzeiten (+525) | Modal GPU / CPU | MMS_FA | Satz | gebuendelt | 99 s, max 440 (HP) |
  | 540 Trennung | Modal T4 / CPU | ECAPA/pyannote | Figur | gebuendelt | 272 s (HP) |
  | 600 Klappentext | API | DeepSeek v4-pro | Block | seriell | 13 s |
  | 610 Cover | API | Gemini Flash Image | Bild | seriell | 10 s |
  | 615 Cover final | lokal CPU | – | Variante | seriell | 2 s |
  | 650 Hoerbuch | lokal CPU | ffmpeg | Kapitel | seriell | 709 s (AoW) |
  | 620/630 ePub | lokal CPU | epubcheck | Variante | seriell | 28 / 7 s (AoW) |
  | 640 Teaser | API + Modal | Gemini TTS/Chatterbox, FA Modal | Satz | teils | 1.738 s (AoW) |
  | 700 Guard | lokal CPU | Hashes | Produkt | seriell | 55 s (AoW) |
  | 710 Auslieferung | lokal + Netz | GCS | Datei | seriell | (nicht gemessen) |
  REIHENFOLGE der Umstellung (Wartezeit x Trennbarkeit): 310 (erledigt) -> 300 -> 330 -> 420 -> 120 -> 200 -> 340 (von 5 auf Grenze/Spuren) -> Audio: 500 Gemini (Taktgeber steht schon) / 530 + 640 + 520/510/540 an Modal-Grenze (10 Jobs) -> 650 (ffmpeg je Kapitel parallel, CPU). Nicht lohnend: 210 (1 Aufruf), 600/610/615/620/630/700/710.
  BAU:
  - NEU pipeline/grenzen.py: EIN Zaehler ueber alle Stages/Werke/Prozesse, dateibasiert mit Sperre (cache/grenzen/, msvcrt bzw. fcntl). platz(anbieter) = Semaphor mit Ablaufzeit (abgestuerzter Prozess blockiert hoechstens ttl_s); takt(anbieter) = Taktgeber Ziel-RPM + Tageszaehler RPD, Tageswechsel Mitternacht Pazifik = 09:00 MEZ (eigene Sommerzeit-Rechnung, Windows ohne tzdata), Tagesgrenze -> TagesgrenzeError mit Reset-Zeit; melde_429/pause_429 (5-10-20-40 s, Deckel 120 s, Streuung), zaehler(), stand() (py -m pipeline.grenzen zeigt Belegung + Rest heute).
  - config.GRENZEN: modal 10 gleichzeitig (ttl 6 h) – NOCH NICHT ANGESCHLOSSEN; deepseek 12 gleichzeitig (Konto 500 pro / 2.500 flash, ttl 900 s); gemini_tts rpm_ziel 500 (Grenze 1.000), rpd 10.000. Umgebung READLAYER_GRENZE_<ANBIETER>=N. config.SPUREN_310 = 12.
  - api_layer: jeder DeepSeek-Versuch belegt einen Platz (waehrend der 429-/Fehler-Pause frei); 429 gezaehlt + steigende Pause; call_model(..., modell=) je Aufruf (310 schreibt config.MODELS nicht mehr um – Race bei Spuren). tts_client._gemini_call: takt("gemini_tts") vor jedem Versuch (gilt ab sofort fuer 500/510/640 Gemini), Tagesgrenze -> QuotaError (500/510 halten wie bisher sauber an), 429 gezaehlt.
  - usage_log: Kontext je Thread (Neben-Threads setzen nur ihren eigenen Kontext; Haupt-Thread wie bisher global) -> Sprache je Kostenzeile stimmt bei parallelen Spuren.
  - s310: Planung je Kapitel x Sprache (Checkpoint lesen, offene Saetze in Batches wie bisher), dann ALLE Batches in einem Pool mit --spuren N (Standard 12, book.json uebersetzung_spuren, Monitor-Regler); Kapitel wird abgeschlossen (Nachforderung 2x, Einzelsatz 1x, Checkpoint) sobald sein letzter Batch zurueck ist -> Wiederaufnahme je Kapitel; Zusammenfuehren in fester Reihenfolge ueber IDs; Gate, Pruefungen, Ausgabeformat unveraendert. Fehler wie fehlender Key bricht den Rest ab (Kapitel fertig = gesichert). Metriken spuren, saetze_offen, laufzeit_s, erwartet_s, http_429. s310.erwartung(werk) = offene Saetze + Schaetzung ohne LLM.
  - NEU pipeline/fortschritt.py (Punkt 7, nur 310 angeschlossen): work/_fortschritt/<stage>.json {einheit, erledigt, gesamt, start, rate, rest_s, fertig_um, erwartet_s, erwartet_fertig, spuren, zustand}; Schaetzung vorab = Median s je 1.000 Zeichen frueherer Laeufe gleicher (sonst naechster, grob umgerechnet ^0,8) Spurenzahl (cache/fortschritt_raten.json, je Lauf >= 5 s automatisch nachgetragen; Startwerte aus kosten.jsonl nachgemessen: Smoke 4,83, HP 3,30, AoW 6,67 s/1.000 Z seriell); waehrend des Laufs aktuelle Rate, bis 20 % mit der Schaetzung gemischt.
  - Cockpit: werk_api Ampel liefert je laufender Stage den Fortschritt; Monitor (alle Stages mit fortschritt.json, jetzt 310): Balken + Restzeit + Fertig-Uhrzeit + Erwartung beim Start im Gate-Kopf "laeuft"; Monitor 310 Zeile "Laufzeit" (offen N Saetze ~x min, fertig ~hh:mm; alle Kapitel neu ~y min) + Regler Spuren; werk.html kompakter Balken in der Zeile der laufenden Stage. Cockpit-Server neu starten.
  TESTS: NEU tests/test_grenzen.py (10: Threads, zweiter Prozess, Ablauf, Takt/RPD, Tageswechsel, Pazifik-Zeit, 429, Umgebung, usage_log je Thread), NEU tests/test_s310_spuren.py (6: Ergebnis spuren 1 = spuren 4 in IDs/Text/Reihenfolge, Spitze = Spurenzahl, Modell je Aufruf, Wiederaufnahme nach Abbruch, Fortschritt + Schaetzung, Neulauf/Probe ohne LLM). Einzeln gruen: test_s310 14, test_s320 9, test_kette 21, test_status 8, test_gate 6, test_cockpit_werk 11, test_s300 12, test_s330 17, test_s340 22, test_s500 35, test_s510 33, test_s200 16, test_s210 17, test_s120 18. Render-Probe Monitor 310 (node, AoW-Daten) ok.
  MESSUNG Smoke-Werk u-smoketest-the-mirror-sisters (122 Saetze, 2 Kapitel, 1 Zielsprache, 5 Batches; live in der VM, --kapitel alle):
    310 seriell (--spuren 1): 35,4 s (frueher alter Code: 24 s / 35 s) -> 12 Spuren: 8,5 s (Faktor ~4; Grenze = 5 Batches, langsamster Batch bestimmt).
    Kosten 310: seriell 0,00774 $ / 12 Spuren 0,00772 $ (je 6 Aufrufe, gleiche Cache-Treffer 8.576 Token; ohne Cache-Treffer 0,0128 $ wie 03.11.) -> parallel kostet nicht mehr. http_429 = 0.
    Ergebnis: 122/122 IDs gleich und in gleicher Reihenfolge, 121/122 Saetze wortgleich (1 Abweichung = LLM-Streuung), Gate 310 AUTO, 320 frei.
    Hochrechnung AoW (1.689 s seriell): Kapitel x Batches ~110 Batches -> bei 12 Spuren ~3–5 min statt 28 min (wird beim naechsten AoW-310 gemessen; Schaetzung im Monitor).
  HINWEIS: Art of War steht in 310 auf 'laeuft' seit 16:54 (alter Code, Werk inzwischen geparkt) – nicht angefasst; ggf. im Cockpit zuruecksetzen. Hochrechnung AoW daher erst bei Wiederaufnahme messbar. VM: python-dotenv nachinstalliert (nur Messlaeufe in der VM).
  OFFEN: (1) Modal-Grenze an die Modal-Aufrufe anschliessen (500 Chatterbox/Pruefung, 510, 520, 530, 540, 640, 340-Pruefaligner) – mit der Umstellung der Audio-Stages. (2) 120/200/210/300 schreiben config.MODELS noch global um -> beim Umstellen auf modell= je Aufruf. (3) Fortschritt fuer die uebrigen Stages beim jeweiligen Umbau. (4) Gemini-Tageszaehler beginnt heute bei 0 (kennt Aufrufe vor dem Einbau nicht); Restkontingent noch nicht in der Laufzeitanzeige von 500/510 (Fertigstellung am Folgetag). (5) Gemini-Bild (610) ohne Takt (geringe Menge). (6) Naechste Stage laut Reihenfolge: 300.

- 2026-11-22 abends AP PARALLELE SPUREN ALLE STAGES (CK 19:16 "alle relevanten Stages", Ziel grundsaetzliche Beschleunigung, nicht werkbezogen). Sicherung Stand vorher: archive/2026-11-22_parallel2/ (s120, s200, s210, s300, s310, s330, s340, s410, s420, s500, s510, s520, s530, s540, s640, s650, config, PROJEKTSTAND).
  NEU pipeline/spuren.py (gemeinsamer Baustein aus dem 310-Muster): anzahl() = Argument > book.json-Feld > config.SPUREN[stage] > config.SPUREN_STANDARD (12); parallel(werk, stage, jobs, fn, n) = ThreadPool, Ergebnisse in Job-Reihenfolge, Fehler bricht ab (gestartete Jobs laufen zu Ende, sind gesichert), spuren=1 ohne Threads, Fortschritt work/_fortschritt/<stage>.json + Erwartung; metriken() (spuren, laufzeit_s, http_429, erwartet_s, jobs_parallel); summe() fuer Zaehler je Job; modal_map(fn, eingaben, kwargs) = Ersatz fuer fn.map in Wellen unter der Modal-Grenze; modal_platz() fuer modal run/.remote. grenzen.plaetze(anbieter, wunsch) = mehrere Plaetze auf einmal.
  config: SPUREN_STANDARD 12, SPUREN {500: 8, 510: 8, 650: CPU-Kerne - 1}.
  UMGESTELLT (Ergebnis je Kapitel sofort gesichert, Zusammenfuehren in fester Reihenfolge, Gate/Ausgabe unveraendert, Modell je Aufruf statt config.MODELS umschreiben):
    120 Modernisierung: Kapitel parallel + Gruppen je Kapitel parallel (book.json modernisierung_spuren). Hinweis: 120 schreibt chapter-N.json weiter erst am Ende (nach Fremd/Abk) -> keine Wiederaufnahme je Kapitel (offen).
    200 Tagging: Kapitel parallel, Checkpoint je Kapitel (tagging_spuren).
    300 Voruebersetzung: Kapitel x Sprache parallel + Abschnitte je Kapitel parallel (voruebersetzung_spuren, --spuren).
    310 (frueher heute): Batches aller Kapitel in einem Pool (uebersetzung_spuren, Monitor-Regler).
    330 Rueckuebersetzung: Kapitel x Sprache parallel + Batches je Kapitel parallel + Reparatur je Satz parallel (rueck_spuren, --spuren); 330-Reparatur bucht Kosten ueber s310.llm(stage=) statt s310.STAGE global umzuschalten.
    340 Wortalignment: Standard von 5 auf 12 Spuren (ALIGN_PARALLEL ueberschreibt weiter).
    420 Sprecher: Kapitel je Sprache parallel + Teile je Kapitel parallel, Checkpoint je Kapitel sofort (sprecher_spuren, --spuren).
    500/510 Gemini: Standard parallel 4 -> 8, Regler bis 16 (Monitor 500/510, werk_api); Takt 500 RPM + RPD zentral.
    650 Hoerbuch: Kapitel parallel (zusammensetzen, normieren, ffmpeg kodieren/messen) mit CPU-Kerne - 1 Spuren; Pruefung danach in fester Reihenfolge.
    MODAL-GRENZE (10 Jobs ueber alle Stages/Werke) angeschlossen: 340 Pruefaligner (.remote), 500 Chatterbox (modal run, s502.modal_lauf, auch 640), 500 Satzpruefung, 510/520 Wortzeiten, 530 Whisper, 640 Whisper (je modal_map statt .map), 540 Messung.
  NICHT umgestellt: 210 (ein Aufruf), 410 (ein Steckbrief-Aufruf), 600/610/615/620/630/700/710 (kurz), 530/520/540 lokale CPU-Anteile (Schnitt, LUFS, Praat) – erst messen, was dort dauert.
  TESTS: alle 46 Testdateien einzeln gruen ausser test_s120_fremd 1 Fehler (bekannt, nur VM: num2words fehlt). Neu/erweitert: test_grenzen 12 (plaetze, modal_map, spuren.parallel), test_s300 +1 (Spuren 4 = Spuren 1), test_s200 +1 (dito); test_s300/test_s200 laufen sonst mit SPUREN_STANDARD 1 (Antwort-Warteschlange in fester Reihenfolge). test_s650 zusaetzlich mit 4 Spuren gruen.
  MESSUNG Smoke-Werk (2 Kapitel, live VM, --kapitel alle): 300 seriell 25,1 s -> 12 Spuren 11,5–15,4 s (je Kapitel 1 Aufruf, laengstes Kapitel bestimmt); 330 seriell 86,0 s -> Kapitel parallel 42,1 s -> + Batches + Reparatur parallel 16,5 s; 310 35,4 -> 8,5 s (s. o.). Kosten: 300 0,0062 $ (ohne Cache) / 0,0048 $ (mit Cache); 330 ~0,0086 $ seriell / 0,0081 bzw. 0,0063 $ parallel -> kein Mehrpreis.
  OFFEN: (1) Spuren-Regler im Monitor nur fuer 310; uebrige Stages ueber book.json-Feld/CLI --spuren (Balken + Erwartung zeigt jeder Monitor automatisch, sobald die Stage fortschritt.json schreibt). (2) 120 Wiederaufnahme je Kapitel. (3) 530/520/540/640 lokale Rechenanteile profilieren und ggf. nach Modal. (4) Gemini-Restkontingent in der Laufzeitanzeige 500/510. (5) Erster Volllauf eines grossen Werks: Raten werden automatisch nachgetragen, Erwartung danach genauer. (6) Cockpit-Server neu starten.
- 2026-11-22 21:10 Modal-TTS Abholen beschleunigt (CK: WAV-Download fast laengster Schritt, Die Kunst des Krieges 563 WAVs). gpu_tts/tts_modal_opt.py: kapitel() packt nach dem Vertonen alle WAVs des Kapitels als FLAC (verlustfrei, Proben identisch, Sprache ~halbe Groesse) in out/<paket>_<variante>/_pack/<kap>.tar; _holen() laedt zuerst diese Pakete (8 parallel, 1 Abruf je Kapitel statt je Satz), entpackt zu WAV PCM16, Rest wie bisher einzeln (16 parallel); Log "Pakete: N Kapitel, x WAVs, y MB in z s" + Gesamtzeit. Packfehler im Modal -> stat pack_fehler, Abholen faellt auf Einzeldateien zurueck. Sicherung archive/2026-11-22_parallel2/tts_modal_opt.py. Wirkt ab dem naechsten modal run (500 Chatterbox, 640). Offen: Zeit vorher/nachher am naechsten Lauf ablesen.
- 2026-11-22 21:45 FORTSCHRITT AUDIO (CK: Zeit-Balken bei Audio-Laeufen fehlte). Sicherung Stand vorher: archive/2026-11-22_parallel2/ (Dateien von 19:20; die hier genannten Aenderungen kamen danach).
  500 Gemini: Balken je Sprache in Saetzen (Gewicht Zeichen, Raten getrennt als 500_gemini), Hinweis wenn das Gemini-Tageskontingent heute nicht reicht (Rest + Tageswechsel). 500/640 Chatterbox (s502.modal_lauf): modal run jetzt per Popen, Ausgabe wird weiter ins Log geschrieben und mitgelesen -> Balken "Kapitel (+ Abholen)" (je Kapitelzeile +1, "Heruntergeladen:" = letzter Schritt; Raten 500_chatterbox). 510: Balken in Takes (Raten 510_takes). 530: Kapitel je Spur PARALLEL (Schnitt, Tempo = ffmpeg je Satz, Lautheit; config.SPUREN 530 = CPU-Kerne - 1), Manifest-Eintraege + Speichern je Kapitel unter Sperre (Wiederaufnahme bleibt), Balken "Kapitel <lg>/<spur>". fortschritt.Fortschritt(art=) trennt Raten je Art innerhalb einer Stage.
  Tests einzeln gruen: s500 35, s510 33, s520 14, s530 19 (auch mit 4 Spuren), s540 21, s650 8, cockpit_werk 11, grenzen 12, s310_spuren 6, kette 21, status 8; modal_lauf mit Ersatz-Prozess geprueft (Balken 3/3, Log unveraendert).
  OFFEN: 520 (Wortzeiten, ein Modal-map) und 540 (ein Modal-Job) ohne Balken; 530 FA-Schritt (Modal) und Whisper-Schritt ohne eigenen Balken (nur Kapitelphase); 510-Schnitt nach den Takes ohne Balken.
- 2026-11-22 22:45 640 "laeuft sich tot" (CK, Die Kunst des Krieges EN). Befund: kein Haenger, sondern Runden-Schleife mit Kaltstarts: EN 3 Saetze Befund "dauer" (dauer_q 1,63–1,64 bei Grenze 1,6 = Sprechtempo Chatterbox EN) -> bis 2x Neuvertonung; je Runde Modal-Chatterbox (~2 min) + FA (Modal) + Whisper (Modal, Kaltstart 234 GPU-s ~0,05 $ fuer 5 Saetze), ohne Logzeile zwischen FA und Whisper. FIX s640: (1) Sprachpruefung unter 20 Saetzen lokal (faster_whisper, sonst Modal wie bisher), Logzeilen fuer FA- und Whisper-Schritt; (2) Dauer bis 15 % ausserhalb der Grenze (DAUER_KNAPP) -> keine automatische Neuvertonung, Befund bleibt fuer Monitor 640 (anhoeren/annehmen). Tests test_s640 16 OK. Sicherung archive/2026-11-22_parallel2/s640_teaser_vor_2240.py. Der laufende Lauf nutzt noch den alten Code.
  INHALTSBEFUND 600/640 Die Kunst des Krieges: EN-Teaser sagt "Bruno Navarro ... died in 1925" und "over 2,200 years", DE "Bruno Navarra ... verstarb 1905" und "2500 Jahre" -> Klappentext 600 (Autor-Block/Einordnung) je Sprache pruefen.
- 2026-11-23 09:35 Abgleich nach Tausch 520/530: Spuren-/Fortschritts-Aenderungen vom 22.11. sind in s520_audio_pruefung (Kapitel parallel, modal_map) und s530_wortzeiten angekommen, config.SPUREN '520' und GRENZEN-Kommentar richtig. cache/fortschritt_raten.json: Schluessel '530' (Audio-Pruefung, Lauf 22.11. 21:42) auf '520' umbenannt. Tests s520 19, s530 14, s640 16, grenzen 12 gruen.
- 2026-11-23 10:30 AP UX-DURCHGANG (Startprompt Projekt-Doc claude/PROMPT_cockpit_ux.md). Sicherung archive/2026-11-23_ux/ (monitor.html, hilfe.js).
  (1) Monitore 100–615 (alle ohne eigene Fassung, auch 190/195/095 und Stages ohne Monitor): neuer Kasten "Naechster Schritt" (#schritt0 zwischen Gate-Kopf und Monitor, naechsterStandard()): laeuft -> warten; mensch -> Kasten oben lesen und freigeben bzw. korrigieren + Uebernehmen; nur Kosten -> unten je Sprache; stopp -> Ruecksprung bzw. (ohne Ruecksprungziel) Hilfetext "Was hilft"; frei -> weiter zur naechsten Stage, bei fehlenden Teilen/veraltet Knopf "starten/neu pruefen"; offen -> wartet auf Vorgaenger (Link) oder Knopf "starten" (nur mit Laufrecht). Nachbar-Stages -> Link zum Monitor der Hauptstage.
  (2) Kasten "Entscheidung noetig" ohne eigenen entscheidungText: Laientext aus config/stage_hilfe.json (warum/mensch) + Anzahl Befunde + offene Teile (entscheidungStandard()). Texte pflegen in stage_hilfe.json, nicht im Code. HILFE wird beim Start ueber /api/hilfe geladen.
  (3) 700 Endabnahme je Produkt: Begruendungsfeld in der Zeile statt Browser-Eingabefenster (prompt). monitor.html enthaelt kein prompt() mehr.
  Pruefung: node --check gruen; naechsterStandard/entscheidungStandard mit Stub-Daten (mensch/stopp/offen/frei/veraltet) geprueft. Kein Server-Code geaendert.
  OFFEN: Sichtpruefung im Browser (Cockpit-Server neu starten); stage-spezifische Feinschliffe dort, wo der Standardtext nicht reicht (Kandidaten: 120, 310, 500/510 – Kostenfreigabe bleibt bis AP Kostendeckel).
- 2026-11-23 11:15 ROEMISCHE ZAHLEN IM SPRECHTEXT (CK: Kapitelnummern "Suntzu: I." in Die Kunst des Krieges falsch vertont; soll fuer Kundenwerke automatisch laufen). Ort: Stage 400 / pipeline/sprechtext.py (nur Sprechtext, Lesetext/ePub unveraendert). REGELN_V 4 -> 5. Sicherung archive/2026-11-23_roemisch/.
  Neu: (1) Ueberschrift: roemische Zahl auch nach Trenner ":"/"–"/"—" ("Suntzu: I. Titel" -> "Suntzu: Eins. Titel"). (2) Ordnungszahl vor Zeit-/Zaehlwort (_ORD_NOMEN): "im XIX. Jahrhundert" -> "im neunzehnten Jahrhundert", "der XIX. Band" -> "der neunzehnte Band"; fr "XIXe siècle" (braucht num2words). (3) DE-Herrscher gebeugt nach Wort davor (Titel wie Koenig/Papst uebersprungen): Dativ-/Akkusativ-/Genitiv-Praepositionen und Artikel, Genitiv-s ("Zeit Ludwigs XIV." -> "Ludwigs des Vierzehnten"), Genitiv-Apostroph ("Franz’ I. Niederlage"), Aufzaehlung mit und/oder uebernimmt den Fall. (4) Zaehlwort statt Herrscher: "Klasse IV" -> "Klasse vier" (_ZAEHL). (5) Initiale "Hans V., ..." bleibt.
  Nebenbefund behoben: Abkuerzungsregel v4 machte aus "3 p.m." -> "3 pagem." (EN). config/abk_sprech_en.json: "p.m." bleibt (Eintrag vor "p."). Betraf noch keine 400-Ausgabe, waere beim naechsten 400-Lauf aufgetreten (z. B. Die Spiegelschwestern EN, 4 Stellen).
  Tests: neu tests/test_sprech_roemisch.py (21 Faelle + Gate ruhig + Abbildung); test_s400 (Erwartung "von Heinrich dem Achten") und test_abk_sprech (regeln_v 5) angepasst; zusammen 33 OK. Vergleich alt/neu ueber alle 36 Werke mit 400-Ausgabe: 46 Saetze/Ueberschriften aendern sich (34 davon Kunst des Krieges), Stichprobe geprueft.
  Wirkung: erst beim naechsten 400-Lauf je Werk; fuer bereits vertonte Werke danach 500 nur fuer geaenderte Saetze. Die Kunst des Krieges geparkt -> erst bei Wiederaufnahme.
  OFFEN: LLM-Rueckfall fuer nicht sicher beugbare Faelle (400 ist bisher 0 $ / ohne LLM) – eigenes kleines AP, falls Gate 400 bei Kundenwerken weiter "roemisch" meldet.
- 2026-11-23 11:40 MONITOR 400: PROTOKOLL DER SPRECHTEXT-ANPASSUNGEN (CK: transparent machen, was 400 fuer die Aussprache geaendert hat). Neuer Kasten je Audiosprache zwischen Pruefungen und Befundliste: Anzahl Stellen/Saetze, Filter je Art (Roemische Zahl, Zahl/Datum/Uhrzeit, Abkuerzung, Symbol, Formatierung entfernt, von Hand, Sonstiges), Tabelle "Im Buch -> Gesprochen" (bis 300 Saetze), Download als CSV (alle Stellen + ganzer Satz). Daten aus 400_regie.json (production.sprechtext + abbildung), Art per sprechtext.aenderungsart()/protokoll(); kein neuer Lauf noetig. Die Kunst des Krieges: de 38 Stellen (19 Zahl, 17 roemisch, 1 Formatierung, 1 Sonstiges), en 33.
  KETTENLEISTE: veraltete Stages (Vorgaenger nach ihnen geaendert oder Teile fehlen) jetzt gestrichelt mit "↻" und Tooltip (kette_kurz.veraltet). Die Kunst des Krieges nach 400-Neulauf: 410 und 500 veraltet.
  Tests: test_s400, test_sprech_roemisch, test_cockpit_werk gruen; node --check monitor.html gruen.
- 2026-11-23 14:50 MONITOR 710 UMGEBAUT (CK: "710 will nicht komplett ausliefern, unklar warum"). Befund: kein Fehler – 710 wartet je Werk auf (a) erstes Freischalten im TAELLA-Katalog und (b) manuellen Upload der Plattform-Pakete (extern). UX-Fehler: Gruende zeigten Kommandozeilen-Befehle; ein "Freigeben" bestaetigte zugleich Katalog UND "extern hochgeladen" (falsche Bestaetigung moeglich).
  Neu: "Freigeben" im Kasten "Entscheidung noetig" schaltet nur den Katalog frei. Plattform-Upload je Sprache im Kasten "Plattform-Paket": Knopf "Als ZIP herunterladen" (neue Server-Route /paket.zip?p=<ordner>), Haken "ist hochgeladen" + Pflichtfeld "wo?" + "Upload bestaetigen". Naechster Schritt nennt Katalog und Plattformen getrennt, inkl. Hinweis "Kanal in 700 zurueckhalten". s710-Gruende in Laiensprache (CLI-Flag nur noch in Klammern). Wirkt fuer die Gruende ab dem naechsten 710-Lauf.
  Tests: test_s710 (Text "Erstes Freischalten") + test_cockpit_werk gruen; node --check gruen. Sicherung archive/2026-11-23_roemisch/ (s710_cloud_export.py, server.py). Cockpit-Server neu starten.
  VORGEMERKT (CK-Entscheidung offen): Frische-Kaskade nach Ergebnis-Hash statt Zeitstempel (410-Neulauf ohne Stimmaenderung machte 615/640 unnoetig veraltet).
- 2026-11-23 15:00 710 STANDARDZIEL = LOKAL (CK: solange keine Mobile App existiert, ist das Mockup taella-app/public das Ziel; danach beides, Mockup bleibt Kurationsplattform). config.AUSLIEFERUNG_ZIEL Standard "lokal" (Status/Gate laufen gegen das Mockup); neu config.AUSLIEFERUNG_ZUSATZ (Liste, Env "a,b"): jeder 710-Standardlauf beliefert diese Ziele mit (ohne Status, Entscheidungen gelten mit). Umstellung nach App-Start: AUSLIEFERUNG_ZIEL=gcs, AUSLIEFERUNG_ZUSATZ=lokal. Tests test_s710 + test_cockpit_werk gruen.
  Die Kunst des Krieges: wurde heute 14:14 nach gcs ausgeliefert (TAELLA frei); fuer das Mockup 710 einmal neu starten.


## Fish-Audio-Test (24.11.2026) – Stand
- Details: Projekt-Doc claude/STAND_fish_test_2026-11-24.md; Ordner tools/fish_test/
- Offen: start_alice_fish_vc.bat (GPU-Fallback L4/A10G/L40S) -> python tools/fish_test/vc_montage.py -> de/fish_erz_vc_c007_de.wav
- Fish-Key nach Tests rotieren.

## 26.11.2026 – Modellwahl EU/Verlagsmodus: Entscheidung D (CK)
- **Regie & Co** (200, 210, 410, 420, 430, 600, Validator 330, 340, 345) → **Mistral Large 3** (Mistral-API, FR).
- **Übersetzung** (120, 300, 310, 330) → **DeepSeek V4.1 Flash bei OVHcloud** (FR, MIT-Gewichte, EU-Server).
- Ziel: Kunden offene Gewichte anbieten, keine US-/China-Server. Kostenschätzung 2,05 $/Werk (Listenpreis, heute 3,98 $; real heute ~2 $ durch DeepSeek-Nebenzeit).
- Tests Kapitel 1 Baskerville (tools/test_qwen_uebersetzung.py, Ergebnisse in Claude outputs/qwen_test/): DS V4.1 Flash bestes Ergebnis (0 Fehler, 0,0067 $); Qwen 3.5 397B und Ling 3.1 Flash schwächer; Mistral Large 3 noch ohne vollständigen Lauf.
- Offen: Mistral-Konto meldet „tier_not_allowed“ (Large) bzw. „billing_no_api_budget_configured“ → API-Plan in console.mistral.ai aktivieren; OVHcloud-AI-Endpoints-Konto anlegen; dann Qualitätstest Regie (420/430) mit Mistral Large 3 und Umsetzung Schalter modus in book.json.
- Mistral bietet kein DeepSeek an (API: invalid model).
- Quellen: computeprices.com (DS V4.1 Flash Anbieterpreise), mistral.ai/pricing, OpenRouter-Modellliste, Benchmark: Claude outputs/qwen_test/BENCHMARK_kosten_mistral_deepseek_2026-11-26.md
- 26.11. Nachtrag: Mistral-API eingerichtet. Übersetzungstest Kapitel 1 Baskerville direkt über Mistral (mistral-large-2512 = Large 3, ohne Denkmodus; mistral-large-latest = Large 4 mit Denk-Token, nicht nutzen): 150/150 Sätze, 0 Fehler, korrekte Anführungszeichen, neue Rechtschreibung, 0,017 $/Kapitel. Qualität mindestens gleichauf mit DS V4.1 Flash (DS: „Dear, dear“ → „Teuer, teuer“). → Empfehlung: Szenario C (alles Mistral), OVHcloud vorerst nicht nötig. Entscheidung CK offen.
- api_layer: Mistral-Zweig (Modellname mistral-*/magistral-*/ministral-*), config MISTRAL_API_KEY + PREISE mistral-large-2512/-small-latest, usage_log liest Mistral-Cache-Token. Mistral-Konto anfangs mit niedrigem Ratenlimit (HTTP 429) → max. 3 gleichzeitige Anfragen. Regie-Test 420: tools/test_regie_mistral.py (schreibt nicht in work/), Referenzwerk the-happy-prince-and-other-tales (Casting Schema 2), noch nicht gelaufen.
- 26.11. Regie-Test 420 (tools/test_regie_mistral.py, the-happy-prince c001 de, 80 Kandidatensätze): Mistral Large 3 nur 64 % gleich mit Produktion (DeepSeek V4 Pro); 14× anderer Sprecher, 5× andere Segmentierung, 4 Rückfälle, 27 Aufrufe statt 2 (Teil-Antworten nicht rekonstruierbar). Typisch: Nebenfiguren (Stadträte, Waisenkinder, Mathematiklehrer) → Erzähler, teils falsche Figur. → Regie mit Large 3 so nicht tauglich; nächster Kandidat Mistral Medium 3.5. Mistral-Konto: 15 Anfragen/min, 400k Token/min → für Produktion höhere Stufe nötig. Ergebnis: Claude outputs/regie_test/the-happy-prince-and-other-tales_c001_de.json
- 26.11. Regie-Test 420 mit DeepSeek V4.1 Flash (OpenRouter, gleiche 80 Sätze): Sprecher in allen Sätzen mit Rede identisch zur Produktion (V4 Pro); 22 Abweichungen nur formal (reine Erzählsätze als „Erzaehler“ ausgegeben statt weggelassen), 3 Rückfälle, 7 Aufrufe, 19 s. → V4.1 Flash ersetzt V4 Pro in der Regie ohne Qualitätsverlust. Hinweis: .env-Eintrag open_router (Zeile 14) ist ungültig (401), config liest ihn vor OPEN_ROUTER_API_KEY → bereinigen.
- 26.11. UMSTELLUNG (CK): config.MODELS alle DeepSeek-Textaufgaben → "deepseek-flash" (= V4.1-Flash-1017). Betrifft profiler, pretranslator, translator, caster (→ 410/420/430/600/210), modernizer (s120 Rückfallwert), tagger, backtranslator, validator, ssml, aligner. Preis laut DeepSeek-Preisliste 26.11.: 0,006 Cache / 0,30 In / 1,20 Out $/Mio., Nebenzeit halb (Hauptzeit Mo–Fr 01–04 + 06–10 UTC = 02–05 + 07–11 MEZ). "deepseek-v4-flash" ist abgekündigt (läuft schon auf V4.1 Flash). GRENZEN konto + deepseek-flash 2500. Rauchtest api_layer ok. Erwartung: ~1,60 $/Werk Listenpreis (vorher 3,98 $), real ~0,80 $. config: OPEN_ROUTER_API_KEY wird jetzt gelesen. Quelle: https://api-docs.deepseek.com/quick_start/pricing/

- 2026-11-26 18:50 AP EU-VERLAGSMODUS Schritt 1+2 (Startprompt claude/PROMPT_eu_variante.md, Stand Update 17:00: Uebersetzung Mistral, Regie & Co DS V4.1 Flash @ OVHcloud).
  KARTIERUNG IM CODE VERIFIZIERT – zusaetzlich zur Vorab-Tabelle gefunden (Daten verlassen das Haus):
    (a) tts_client._fal_call: Gemini-TTS-Ueberlauf ueber fal.ai (US) bei backend "fal" oder _overflow_active -> im Verlagsmodus hart sperren.
    (b) voice_registry.py: POST generativelanguage.googleapis.com/v1beta/voices (410 Voice Design, AI Studio) -> im Verlagsmodus durch Qwen3-TTS VoiceDesign (gpu_qwen/qwen_modal.py, Apache-2.0, Design-Prompt je Zielsprache, Test 26.11. ok) ersetzen; qwen_modal.py hat noch KEIN region= -> region="eu" setzen. Gemini-Voice-Design dann ganz aus (auch Lizenzthema).
    (c) fish_motor (430 Momente-LLM laeuft ueber api_layer "caster"; 503/511 TTS + Stimmregistrierung ueber api.fish.audio) -> sperren, bis Fish selbst gehostet auf Modal region="eu".
    (d) s610_cover + tts_client INTERACTIONS_URL: AI Studio (generativelanguage), nicht Vertex.
    (e) s110_wikidata: nur Autor-/Titelname, nur PD-Pfad (gutenberg/user_txt) -> unkritisch; Verlagspfad 095->150->115->120.
    (f) api_layer Mistral-Zweig nutzt api.mistral.ai -> fuer Verlagsmodus api.eu.mistral.ai (EU-Regionalinferenz) setzen.
    (g) OpenRouter nur ueber Modellpraefix "or/" (in MODELS nicht genutzt) -> im Verlagsmodus sperren.
    Modal: 340 Pruefaligner, 500/640 Chatterbox, 510/520 Wortzeiten, 530/640 Whisper, 540 Messung, 511 VC. 710 GCS europe-west3.
  RECHTSLAGE:
    Mistral: DPA (legal.mistral.ai, 12.03.2026); API-Daten standardmaessig kein Training (Opt-out im Admin pruefen); Standard 30 Tage Abuse-Log; ZDR fuer Pay-as-you-go auf Antrag beim Support; EU-Verarbeitung ueber api.eu.mistral.ai; Unterauftragnehmer trust.mistral.ai.
    OVHcloud AI Endpoints: EU-Hosting, kein Training, ZDR ("nur Abrechnungsdaten"), ISO 27001/SOC 2/HDS; Vertrag = AI-Endpoints-Bedingungen + Public Cloud Special Conditions; 400 Anfragen/min je Projekt und Modell.
    Google/ElevenLabs/Modal: wie Recherche 23.11.
  HINWEIS: Mistral-Uebersetzungstest Kap. 1 Baskerville ist schon gelaufen (150/150, 0 Fehler, 0,017 $) und DS V4.1 Flash Regie-Test 420 ebenfalls (Sprecher identisch) -> Qualitaetsfragen 310/420 im Kern beantwortet; offen 330/340 Gate-Quote mit Mistral, 430 mit DS Flash @ OVH, TTS Vertex vs. AI Studio.
  NAECHSTE SCHRITTE CK: Mistral ZDR beantragen + Training-Opt-out pruefen; OVHcloud-AI-Endpoints-Konto (Public-Cloud-Projekt); dann Schritt 3 Kosten + Schritt 5 Schalter.
  QUELLEN: https://docs.mistral.ai/admin/monitor-comply/zero-data-retention · https://docs.mistral.ai/studio/regional-inference · https://legal.mistral.ai/terms/data-processing-addendum · https://www.ovhcloud.com/en/public-cloud/ai-endpoints · https://docs.ovhcloud.com/en/guides/public-cloud/ai-machine-learning/ai-endpoints-capabilities
- 2026-11-26 18:53 ENTSCHEIDUNG CK: Modal OHNE festen Standort (kein region="eu", kein Aufschlag x1,15), bis ein Verlagskunde es fordert. PD-Produktionen (SOMNIO) brauchen es nicht. Gilt fuer alle Modal-Funktionen (Qwen, Chatterbox, Fish, Whisper, FA). Qwen-Gewichte liegen bereits im Modal-Volume readlayer-qwen (/vol/hf). Spaeter: region nur im Modus verlag setzen.
- 2026-11-26 18:55 GRUNDSATZ CK: Selbst gehostete offene Gewichte (Qwen, Chatterbox, Whisper, FA, ggf. Fish) bleiben auch im Standardmodus erste Wahl – kein Nachteil heute, und der Verlagsmodus (Ausweichen vor US-Zugriff/China) wird dann nur noch ein Schalter: Region setzen bzw. Anbieter wechseln, kein Modelltausch.
- 2026-11-26 18:57 ENTSCHEIDUNG CK Cover: Im Verlagsmodus ist 610 (Gemini-Bild) AUS; der Verlag liefert sein vorhandenes Cover, 615 setzt nur Titel/Format. Kein selbst gehostetes Bildmodell (keine Kernkompetenz). Bleibende Ersatz-Bausteine Verlagsmodus damit nur noch: Gemini-TTS und Fish-API.
- 2026-11-26 18:58 VORGEMERKT (CK: Monitor-UX einzeln abarbeiten, je eigenes AP) – Verlagsmodus-Bezug: (1) Modus-Kennzeichen im Werkskopf/Kettenleiste; (2) Freigabe Gemini-TTS (Wer/Wann, Hinweistext) vor 500/510/640; (3) Cover-Upload statt 610 im Monitor 615; (4) Protokoll gesperrter Aufrufe (api_layer-Sperre) sichtbar; (5) Voice Design 410 ueber Qwen statt Gemini.
