@echo off
rem READ LAYER - nur DE fertigstellen (Grossmutter-Fassung b8_gm liegt schon im Modal-Volume)
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set W=u-mikemustermann-peter-and-wendy
set LOG=cockpit\logs\epub_de_fertig_%W%.log
title READ LAYER - DE fertigstellen
echo Laeuft, Fortschritt in %LOG% ...
py -3.11 -m modal run --detach gpu_tts/fertig_modal.py --werk %W% --sprachen de --variante b8_gm > %LOG% 2>&1
echo === FERTIG === >> %LOG%
findstr /C:"fertiggestellt" /C:"entpackt" /C:"FERTIG" /C:"Error" /C:"Traceback" %LOG%
pause
