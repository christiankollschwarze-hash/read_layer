@echo off
rem READ LAYER - AP 60: nur Schritt 3 (Modal) erneut, Gemini-Dateien bleiben
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set LOG=cockpit\logs\ap60_modal.log
py -3.11 -m modal run gpu_tts/ap60_modal.py > %LOG% 2>&1
findstr /C:"[ap60]" /C:"Error" %LOG%
start "" tests\ap60\ergebnis
pause
