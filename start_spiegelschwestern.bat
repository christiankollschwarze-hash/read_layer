@echo off
rem READ LAYER - AP4 Audio "Die Spiegelschwestern" (22.10.2026). Schritte einzeln in dieser Reihenfolge, CK-Tor dazwischen:
rem   1 probe     DE-Paket (Erzaehler je Kapitel) + Namensprobe Lexikon -> work\_cb_probe\de\neu anhoeren,
rem               dann work\aussprache_de.json "freigegeben": true. Stimmen vorab: stimmen_archiv\<stimme>\muster_de.wav
rem   2 sprecher  Stage 420 (DeepSeek, Ich-Erzaehler je Kapitel) + Kontrollansicht work\Kontrollansicht_de.docx -> CK prueft;
rem               Besetzung work\casting.json ("tor": "freigegeben" setzen)
rem   3 de        DE komplett mit Gemini 3.8 Flash TTS (22.10. CK): Stimme je Kapitel (Mehring designt, Zwillinge Zephyr),
rem               Wortzeiten (Modal), Zwillings-Sprechweise. Lexikon muss freigegeben sein.
rem   4 en        EN komplett: Chatterbox-Standardstimme, Tempo 0,91, ohne Hoerspiel
rem   5 hoerspiel DE Overlay: Figuren per Chatterbox VC, Zwillingsrede in Mehring-Kapiteln direkt mit Gemini Zephyr,
rem               Montage + Trennungsmessung -> Cockpit "Hoerspiel-Pruefung"
rem   6 teaser    Klappentext-Teaser Herr A: DE Klon ueber mix_v1, EN Standard + Overlay
rem   7 export    Mock-up (taella-app\public\demo) mit Audio + Hoerspiel-Saetzen
rem Aufruf: start_spiegelschwestern.bat <probe|sprecher|de|en|hoerspiel|teaser|export>
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set W=die-spiegelschwestern
set S=%~1
if "%S%"=="" ( echo Aufruf: start_spiegelschwestern.bat ^<probe^|sprecher^|de^|en^|hoerspiel^|teaser^|export^> & pause & exit /b 1 )
set LOG=cockpit\logs\spiegelschwestern_%S%.log
title READ LAYER - Spiegelschwestern %S%
echo Laeuft, Fortschritt in %LOG% ...
echo === %S% %date% %time% === > %LOG%
goto %S%

:probe
py -3.11 tools\tts_paket.py %W% de --ref=m_mittel_tief_ruhig >> %LOG% 2>&1 || goto ende
py -3.11 -m modal run gpu_tts/tts_modal_opt.py::adapter_sichern >> %LOG% 2>&1
py -3.11 tools\cb_neu.py %W% de liste --lexikon --probe 15 >> %LOG% 2>&1 || goto ende
py -3.11 -m modal run gpu_tts/tts_modal_opt.py::main --paket %W%_de_neu --batch 8 --zusatz n%RANDOM% >> %LOG% 2>&1 || goto ende
py -3.11 tools\cb_neu.py %W% de einspielen >> %LOG% 2>&1
goto ende

:sprecher
py -3.11 -m pipeline.s420_sprecher %W% >> %LOG% 2>&1 || goto ende
py -3.11 tools\kontrollansicht_docx.py %W% de >> %LOG% 2>&1
goto ende

:de
py -3.11 -c "import sys,json;sys.exit(0 if json.load(open(r'authors\unbekannt\books\%W%\work\aussprache_de.json',encoding='utf-8')).get('freigegeben') else 1)" || ( echo Lexikon nicht freigegeben - Abbruch >> %LOG% & goto ende )
py -3.11 tools\gemini_parallel.py %W% de --jobs 2 >> %LOG% 2>&1 || goto ende
rem 22.10.: Wort-Alignment (340, DeepSeek) fehlte -> Pflicht fuer Wortzeiten (fa_modal laedt es hoch)
if not exist authors\unbekannt\books\%W%\work\340_wortalignment.json py -3.11 -m pipeline.s340_wortalignment %W% >> %LOG% 2>&1
py -3.11 -m modal run gpu_fa/fa_modal.py --werk %W% --sprachen de >> %LOG% 2>&1 || goto ende
py -3.11 tools\sprechweise.py %W% de >> %LOG% 2>&1
goto ende

:en
py -3.11 tools\tts_paket.py %W% en >> %LOG% 2>&1 || goto ende
py -3.11 -m modal run gpu_tts/tts_modal_opt.py::main --paket %W%_en --batch 8 --no-herunterladen >> %LOG% 2>&1 || goto ende
py -3.11 -m modal run gpu_tts/fertig_modal.py --werk %W% --sprachen en --variante b8 >> %LOG% 2>&1
goto ende

:hoerspiel
py -3.11 tools\overlay_vorbereiten.py %W% de >> %LOG% 2>&1 || goto ende
py -3.11 -m modal run gpu_overlay/overlay_modal.py --paket %W%_de >> %LOG% 2>&1 || goto ende
py -3.11 tools\overlay_gemini.py %W% de >> %LOG% 2>&1 || goto ende
py -3.11 tools\overlay_montage.py %W% de >> %LOG% 2>&1 || goto ende
call start_trennung_messen.bat %W% de
goto ende

:teaser
call :tlauf de m 0
call :tlauf en m 1
goto ende

:export
py -3.11 tools\export_demo.py %W% ..\taella-app\public\demo --audio --hoerspiel >> %LOG% 2>&1
goto ende

:tlauf
py -3.11 tools\teaser_paket.py bauen %W% %1 %2 >> %LOG% 2>&1 || exit /b 1
py -3.11 -m modal run gpu_tts/tts_modal_opt.py::main --paket %W%_teaser_%1_%2 >> %LOG% 2>&1 || exit /b 1
py -3.11 tools\teaser_paket.py overlay %W% %1 %2 >> %LOG% 2>&1 || exit /b 1
if "%3"=="1" py -3.11 -m modal run gpu_overlay/overlay_modal.py --paket %W%_teaser_%1_%2 >> %LOG% 2>&1
py -3.11 tools\teaser_paket.py fertig %W% %1 %2 >> %LOG% 2>&1
exit /b 0

:ende
echo === ENDE === >> %LOG%
findstr /C:"===" /C:"[tts_paket]" /C:"[cb_neu]" /C:"[stage57b]" /C:"[sprechweise]" /C:"[overlay]" /C:"[overlay_gemini]" /C:"[parallel]" /C:"[montage]" /C:"[korrektur]" /C:"[teaser]" /C:"MESSUNG" /C:"Pruefung" /C:"fertiggestellt" /C:"Error" /C:"Traceback" %LOG%
pause
