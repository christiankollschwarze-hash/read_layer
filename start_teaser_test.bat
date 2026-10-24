@echo off
rem READ LAYER - Klappentext-Teaser Testsequenzen, Runde 2 (19.10.2026, claude/PROZESS_klappentext_erzaehler.md)
rem   Neu: Aussprache-Lexikon aus dem Glossar (ungeprueft angewendet = Hoerprobe), Satzraender geschnitten, EN-Tempo 0,80,
rem        DE maennlich = Klon Herr A ueber Mix-Gewicht
rem Ergebnis: <werk>\fassungen\<lg>\teaser\teaser_<lg>_<variante>.wav
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set TEASER_LEXIKON_TEST=1
cd /d "%~dp0"
set LOG=cockpit\logs\teaser_test.log
title READ LAYER - Teaser-Test
echo Laeuft, Fortschritt in %LOG% ...
echo === Teaser-Test %date% %time% === > %LOG%
echo === Aussprache-Lexika === >> %LOG%
py -3.11 tools\aussprache_lexikon.py the-yellow-wallpaper de >> %LOG% 2>&1
py -3.11 tools\aussprache_lexikon.py call-of-the-wild de >> %LOG% 2>&1
call :lauf the-yellow-wallpaper de w 0
call :lauf the-yellow-wallpaper en w 1
call :lauf call-of-the-wild de m 0
call :lauf call-of-the-wild en m 1
echo === ENDE === >> %LOG%
findstr /C:"===" /C:"[teaser]" /C:"[aussprache]" /C:"MESSUNG" /C:"Error" /C:"Traceback" %LOG%
pause
exit /b 0

:lauf
echo === %1 %2 %3 === >> %LOG%
py -3.11 tools\teaser_paket.py bauen %1 %2 %3 >> %LOG% 2>&1 || exit /b 1
py -3.11 -m modal run gpu_tts/tts_modal_opt.py::main --paket %1_teaser_%2_%3 >> %LOG% 2>&1 || exit /b 1
py -3.11 tools\teaser_paket.py overlay %1 %2 %3 >> %LOG% 2>&1 || exit /b 1
if "%4"=="1" py -3.11 -m modal run gpu_overlay/overlay_modal.py --paket %1_teaser_%2_%3 >> %LOG% 2>&1
py -3.11 tools\teaser_paket.py fertig %1 %2 %3 >> %LOG% 2>&1
exit /b 0
