@echo off
rem READ LAYER - Aussprache-Lexika fuer alle Werke aus dem Glossar (19.10.2026). Freigegebene Lexika bleiben unberuehrt.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set LOG=cockpit\logs\aussprache_bestand.log
title READ LAYER - Aussprache-Lexika Bestand
echo Laeuft, Fortschritt in %LOG% ...
py -3.11 tools\aussprache_lexikon.py --alle de > %LOG% 2>&1
findstr /C:"FEHLER" /C:"Traceback" %LOG%
echo Fertig. Details: %LOG%
pause
