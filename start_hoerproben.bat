@echo off
rem READ LAYER - AP 63: Klon-Hoerproben (Nordwind) fuer alle Archivstimmen. Aufruf: start_hoerproben.bat [liste|los]
rem liste = Anzahl + Kosten (kostenlos) | los = Gemini-Lauf (Freigabe noetig)
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
cd /d "%~dp0"
set M=%~1
if "%M%"=="" set M=liste
if not exist cockpit\logs mkdir cockpit\logs
py -3.11 -u tools\hoerproben_archiv.py %M% > cockpit\logs\hoerproben_%M%.log 2>&1
type cockpit\logs\hoerproben_%M%.log
echo.
pause
