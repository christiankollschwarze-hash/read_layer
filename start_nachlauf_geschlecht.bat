@echo off
rem READ LAYER - Nachlauf 19.10.2026: autor_geschlecht (Wikidata P21) + hauptfigur_geschlecht (DeepSeek Flash) im Bestand
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set LOG=cockpit\logs\nachlauf_geschlecht.log
title READ LAYER - Nachlauf Geschlecht
echo Laeuft, Fortschritt in %LOG% ...
py -3.11 tools\nachlauf_geschlecht.py > %LOG% 2>&1
findstr /C:"[autoren]" /C:"[werke]" /C:"FEHLER" /C:"Traceback" %LOG%
pause
