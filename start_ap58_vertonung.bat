@echo off
rem AP 58 Winnie-the-Pooh: Vollvertonung mehrstimmig EN + DE (Gemini-Standardstimmen, Casting CK-frei 26.10.)
rem   1 hoerprobe_mehrstimmig alle Kapitel --satzdateien -> fassungen\<lg>\audio\<tag>.wav (Segment-Cache: Kap. I wird wiederverwendet)
rem   2 Manifest work\500_vertonung.json   3 Wortzeiten Modal (fa_modal)   4 Stage 560 Sprachpruefung EN + DE (inkl. 525 + Demo-Export)
rem Log: cockpit\logs\ap58_vertonung.log  (Stage 560: cockpit\logs\s560_winnie-the-pooh_<lg>.txt)
rem Kosten Schaetzung: Gemini TTS ~3,6 $, Modal ~1-3 $, Stage 560 ~1 $. Dauer ca. 2-4 h.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
cd /d "%~dp0"
set WERK=winnie-the-pooh
set LOG=cockpit\logs\ap58_vertonung.log
title READ LAYER - AP 58 Pooh Vertonung
echo Vertonung laeuft, Fortschritt in %LOG% ...
echo === Vertonung %date% %time% === > %LOG%
py -3.11 tools\hoerprobe_mehrstimmig.py %WERK% alle en,de --satzdateien >> %LOG% 2>&1
if errorlevel 1 ( echo === FEHLER Vertonung === >> %LOG% & type %LOG% & pause & exit /b 1 )
py -3.11 tools\manifest_schreiben.py %WERK% >> %LOG% 2>&1
py -3.11 -m modal run gpu_fa/fa_modal.py --werk %WERK% --sprachen en,de >> %LOG% 2>&1
if errorlevel 1 ( echo === FEHLER Wortzeiten Modal === >> %LOG% & type %LOG% & pause & exit /b 1 )
py -3.11 tools\ap58_pruefen.py kosten >> %LOG% 2>&1
set NOSTOP=1
call start_s560.bat %WERK% en
call start_s560.bat %WERK% de
py -3.11 tools\ap58_pruefen.py kosten >> %LOG% 2>&1
echo === FERTIG === >> %LOG%
findstr /C:"[hoerprobe]" /C:"Fehler" /C:"[manifest]" /C:"[ap58]" /C:"FERTIG" /C:"Traceback" %LOG%
pause
