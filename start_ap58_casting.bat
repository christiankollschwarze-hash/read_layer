@echo off
rem AP 58 Winnie-the-Pooh: Casting (Gemini-Standardstimmen) -> Stage 420 Sprecherzuordnung (DeepSeek) -> Hoerprobe Kapitel I EN + DE (Gemini)
rem Ergebnis anhoeren: authors\milne-aa\books\winnie-the-pooh\work\_hoerprobe\<en|de>\c002.wav   Log: cockpit\logs\ap58_casting.log
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
cd /d "%~dp0"
set WERK=winnie-the-pooh
set LOG=cockpit\logs\ap58_casting.log
title READ LAYER - AP 58 Pooh Casting
echo Casting laeuft, Fortschritt in %LOG% ...
py -3.11 tools\pooh_casting.py > %LOG% 2>&1
py -3.11 -m pipeline.s420_sprecher %WERK% >> %LOG% 2>&1
if errorlevel 1 ( echo === FEHLER 420 === >> %LOG% & type %LOG% & pause & exit /b 1 )
py -3.11 tools\hoerprobe_mehrstimmig.py %WERK% c002 en,de --ohne-freigabe >> %LOG% 2>&1
py -3.11 tools\ap58_pruefen.py kosten >> %LOG% 2>&1
echo === FERTIG === >> %LOG%
findstr /C:"[casting]" /C:"[stage57b]" /C:"[hoerprobe]" /C:"[ap58]" /C:"FERTIG" /C:"Traceback" %LOG%
pause
