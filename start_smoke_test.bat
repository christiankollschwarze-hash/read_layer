@echo off
rem READ LAYER - Smoke-Test (E7, 24.10.2026): Regressionstest "The Mirror Sisters / Die Spiegelschwestern"
rem Nach jedem Arbeitspaket einmal komplett laufen lassen. Nur bestehende Stages, Export nur als Manifest (--dry).
rem Ablauf: EPUB bauen -> 150 Import -> 200-330 Text -> 340 -> 400 Regie -> 410 Casting -> 420 Sprecher
rem         -> QF-4 (offenes Tor stoppt 500) -> Freigabe -> 500 Chatterbox (DE mix_v1, EN Standard)
rem         -> 520/530 fertig_modal -> 600-630 ePub -> 700 Guard -> 710 Manifest -> Bericht
rem Log: cockpit\logs\smoke_test.txt   Bericht: cockpit\logs\smoke_test_bericht.txt
rem Pruefstopp-Override fuer einen Lauf: Datei tests\smoke\override_weiter.txt anlegen (danach wieder entfernen).
rem Ohne Pause am Ende (fuer Aufruf aus anderen Skripten): set SMOKE_NOPAUSE=1
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
title READ LAYER - Smoke-Test
set W=u-smoketest-the-mirror-sisters
set WD=users\smoketest\works\%W%
set LOG=cockpit\logs\smoke_test.txt
set S=py -3.11 tests\smoke\smoke.py
rem Eigenes Stimmenregister (Kopie, legt smoke.py setup an): globales stimmen_archiv\stimmen.json bleibt unveraendert
set READLAYER_STIMMEN_REGISTER=%CD%\%WD%\stimmen_test.json
if not exist cockpit\logs mkdir cockpit\logs
echo Laeuft, Fortschritt in %LOG% ...
echo === SMOKE-TEST START %date% %time% === > %LOG%
rem Bewusster Override der Pruefstopps 320/330 (QF-6) nur, wenn tests\smoke\override_weiter.txt existiert
if exist tests\smoke\override_weiter.txt ( set READLAYER_WEITER=1& echo OVERRIDE: READLAYER_WEITER=1 aktiv ^(tests\smoke\override_weiter.txt^) >> %LOG% )
if exist cockpit\logs\smoke_test_zeiten.jsonl del cockpit\logs\smoke_test_zeiten.jsonl
rem Vorlauf: nur das Testwerk frisch anlegen (sonst greifen alte Checkpoints)
if exist "%WD%" rmdir /s /q "%WD%"

%S% schritt epub_bauen -- py -3.11 tests\smoke\build_epub.py >> %LOG% 2>&1 || goto fehler
%S% schritt 150_import -- py -3.11 -m pipeline.s150_epub_import tests\smoke\spiegelschwestern.epub --user smoketest --force >> %LOG% 2>&1 || goto fehler
%S% setup %W% >> %LOG% 2>&1 || goto fehler
%S% schritt 200-330_textkette -- py -3.11 tests\smoke\smoke.py linie %W% --line audio --from 200 --to 330 >> %LOG% 2>&1 || goto fehler
%S% schritt 340_wortalignment -- py -3.11 -m pipeline.s340_wortalignment %W% >> %LOG% 2>&1 || goto fehler
%S% schritt 400-410_regie_casting -- py -3.11 tests\smoke\smoke.py linie %W% --line audio --from 400 --to 410 >> %LOG% 2>&1 || goto fehler
%S% schritt 420_sprecher -- py -3.11 -m pipeline.s420_sprecher %W% >> %LOG% 2>&1 || goto fehler
%S% schritt QF4_tor_stoppt_500 -- py -3.11 tests\smoke\smoke.py tor_test %W% >> %LOG% 2>&1 || goto fehler
%S% schritt 410_hand_besetzung -- py -3.11 tests\smoke\smoke.py besetzen %W% >> %LOG% 2>&1 || goto fehler
%S% schritt 410_freigeben -- py -3.11 -m pipeline.s410_casting %W% --freigeben >> %LOG% 2>&1 || goto fehler
%S% schritt tor_freigegeben -- py -3.11 tests\smoke\smoke.py tor_frei %W% >> %LOG% 2>&1 || goto fehler
%S% schritt 500_paket_de -- py -3.11 tools\tts_paket.py %W% de >> %LOG% 2>&1 || goto fehler
%S% schritt 500_paket_en -- py -3.11 tools\tts_paket.py %W% en >> %LOG% 2>&1 || goto fehler
%S% schritt 500_modal_de -- py -3.11 -m modal run gpu_tts/tts_modal_opt.py::main --paket %W%_de --batch 8 --no-herunterladen >> %LOG% 2>&1 || goto fehler
%S% schritt 500_modal_en -- py -3.11 -m modal run gpu_tts/tts_modal_opt.py::main --paket %W%_en --batch 8 --no-herunterladen >> %LOG% 2>&1 || goto fehler
%S% schritt 520-530_fertig_modal -- py -3.11 -m modal run gpu_tts/fertig_modal.py --werk %W% --sprachen en,de --variante auto >> %LOG% 2>&1 || goto fehler
%S% schritt 600-630_epub -- py -3.11 tests\smoke\smoke.py linie %W% --line epub --from 600 --to 630 >> %LOG% 2>&1 || goto fehler
%S% schritt 700_guard -- py -3.11 -m pipeline.s700_guard %W% >> %LOG% 2>&1 || goto fehler
%S% schritt 710_manifest_en -- py -3.11 -m pipeline.s710_cloud_export %W% --lang en --dry --manifest-only >> %LOG% 2>&1 || goto fehler
%S% schritt 710_manifest_de -- py -3.11 -m pipeline.s710_cloud_export %W% --lang de --dry --manifest-only >> %LOG% 2>&1 || goto fehler

%S% bericht %W% >> %LOG% 2>&1
set RC=%ERRORLEVEL%
rem Aufraeumen (Smoke #9): TTS-Werkordner des Testwerks entfernen
if exist gpu_tts\%W%_de rmdir /s /q gpu_tts\%W%_de
if exist gpu_tts\%W%_en rmdir /s /q gpu_tts\%W%_en
echo === SMOKE-TEST ENDE rc=%RC% %date% %time% === >> %LOG%
type cockpit\logs\smoke_test_bericht.txt
if not "%SMOKE_NOPAUSE%"=="1" pause
exit /b %RC%

:fehler
echo === SMOKE-TEST ABBRUCH %date% %time% === >> %LOG%
%S% bericht %W% >> %LOG% 2>&1
rem Aufraeumen (Smoke #9): TTS-Werkordner des Testwerks entfernen
if exist gpu_tts\%W%_de rmdir /s /q gpu_tts\%W%_de
if exist gpu_tts\%W%_en rmdir /s /q gpu_tts\%W%_en
findstr /C:"=== SCHRITT" /C:"[STOPP]" /C:"[FEHLER]" /C:"Traceback" /C:"Error" %LOG%
type cockpit\logs\smoke_test_bericht.txt
if not "%SMOKE_NOPAUSE%"=="1" pause
exit /b 1
