@echo off
rem READ LAYER - DE vertonen + Werk komplett auf Modal fertigstellen (Wortzeiten, Raender, Tempo 0,91, Wortzeiten), dann ein Paket je Sprache laden
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set W=%~1
if "%W%"=="" set W=u-mikemustermann-peter-and-wendy
set LOG=cockpit\logs\epub_modal_%W%.log
title READ LAYER - Modal komplett %W%
echo Laeuft, Fortschritt in %LOG% ...
echo === DE vertonen === > %LOG%
py -3.11 tools\tts_paket.py %W% de --ref=grossmutter_a >> %LOG% 2>&1
py -3.11 -m modal run gpu_tts/tts_modal_opt.py::main --paket %W%_de --batch 8 --no-herunterladen >> %LOG% 2>&1
echo === EN + DE fertigstellen === >> %LOG%
py -3.11 -m modal run gpu_tts/fertig_modal.py --werk %W% --sprachen en,de >> %LOG% 2>&1
echo === FERTIG === >> %LOG%
findstr /C:"===" /C:"MESSUNG" /C:"fertiggestellt" /C:"entpackt" /C:"FERTIG" /C:"Error" /C:"Traceback" %LOG%
pause
