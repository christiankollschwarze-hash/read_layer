@echo off
rem READ LAYER - privater Upload: Vollvertonung EN + DE, Chatterbox Multilingual, Batch 8, Stimme grossmutter_a (Modal, alle Kapitel parallel)
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set W=%~1
if "%W%"=="" set W=u-mikemustermann-peter-and-wendy
set LOG=cockpit\logs\epub_vertonen_%W%.log
title READ LAYER - Vollvertonung %W%
echo Vollvertonung laeuft, Fortschritt in %LOG% ...
echo === EN === > %LOG%
py -3.11 tools\tts_paket.py %W% en --ref=grossmutter_a >> %LOG% 2>&1
py -3.11 -m modal run gpu_tts/tts_modal_opt.py::main --paket %W%_en --batch 8 >> %LOG% 2>&1
echo === DE === >> %LOG%
py -3.11 tools\tts_paket.py %W% de --ref=grossmutter_a >> %LOG% 2>&1
py -3.11 -m modal run gpu_tts/tts_modal_opt.py::main --paket %W%_de --batch 8 >> %LOG% 2>&1
echo === FERTIG === >> %LOG%
findstr /C:"MESSUNG" /C:"Heruntergeladen" /C:"FEHLER" /C:"Error" %LOG%
pause
