@echo off
rem READ LAYER - DE neu vertonen mit Grossmutter-Stimme (deutsches Muster), Fertigstellung auf Modal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set W=u-mikemustermann-peter-and-wendy
set LOG=cockpit\logs\epub_de_neu_%W%.log
title READ LAYER - DE Grossmutter %W%
echo Laeuft, Fortschritt in %LOG% ...
echo === DE Paket mit grossmutter_a === > %LOG%
py -3.11 tools\tts_paket.py %W% de --ref=grossmutter_a >> %LOG% 2>&1
echo === DE vertonen === >> %LOG%
py -3.11 -m modal run gpu_tts/tts_modal_opt.py::main --paket %W%_de --batch 8 --zusatz gm --no-herunterladen >> %LOG% 2>&1
findstr /C:"Traceback" /C:"Werkstimme" %LOG% >nul && ( echo === ABBRUCH === >> %LOG% & type %LOG% & pause & exit /b 1 )
echo === DE fertigstellen === >> %LOG%
py -3.11 -m modal run gpu_tts/fertig_modal.py --werk %W% --sprachen de --variante b8_gm >> %LOG% 2>&1
echo === FERTIG === >> %LOG%
findstr /C:"===" /C:"MESSUNG" /C:"fertiggestellt" /C:"entpackt" /C:"Error" /C:"Traceback" %LOG%
pause
