@echo off
rem READ LAYER - Teaser Yellow Wallpaper DE, Runde 3 (19.10.2026): Ordinalzahlen ("19. Jahrhunderts" -> "neunzehnten"),
rem Anfang nur echte Stille schneiden, Batch 8 mit Pruefung im Lauf (verschluckte Silben -> bis 2 Neuversuche).
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set TEASER_LEXIKON_TEST=1
cd /d "%~dp0"
set LOG=cockpit\logs\teaser_nachlauf.log
echo Laeuft, Fortschritt in %LOG% ...
py -3.11 tools\teaser_paket.py bauen the-yellow-wallpaper de w > %LOG% 2>&1
py -3.11 -m modal run gpu_tts/tts_modal_opt.py::main --paket the-yellow-wallpaper_teaser_de_w --batch 8 --zusatz r3 >> %LOG% 2>&1
py -3.11 tools\teaser_paket.py overlay the-yellow-wallpaper de w >> %LOG% 2>&1
py -3.11 tools\teaser_paket.py fertig the-yellow-wallpaper de w >> %LOG% 2>&1
findstr /C:"[teaser]" /C:"MESSUNG" /C:"Pruefung" /C:"Heruntergeladen" /C:"Error" /C:"Traceback" %LOG%
pause
