@echo off
rem READ LAYER - MAGI DE: Vertonung komplett mit Gemini TTS (Stufe 500, nur DE).
rem Kosten: Gemini je Satz (ca. 150 Saetze). Keine Stufe 510 (Hoerspiel-Gate = offen), kein Casting.
rem Kostenerfassung (Reader/Hoerbuch/Hoerspiel je Sprache) ist in diesem Lauf noch NICHT eingebaut.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
cd /d "%~dp0"
set LOG=cockpit\logs\magi_de.log
if not exist cockpit\logs mkdir cockpit\logs
echo === MAGI DE Gemini Vertonung (Stufe 500, --to 500) === > %LOG%
py -3.11 -u run.py the-gift-of-the-magi --line audio --lang de --to 500 >> %LOG% 2>&1
type %LOG%
echo.
pause
