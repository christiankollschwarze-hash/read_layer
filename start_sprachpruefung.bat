@echo off
rem READ LAYER - Sprachpruefung der Satz-Audios (kippt die Aussprache ins Englische/Franzoesische?)
rem Aufruf:  start_sprachpruefung.bat <werk> [lg]
rem   1) Paket (16-kHz-FLAC + Solltexte)  2) Modal: Whisper large-v3 je Satz  3) Rangliste + Namen-Statistik
rem Danach Cockpit "Sprachpruefung": verdaechtige Saetze anhoeren, kippt / ok markieren.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if "%~1"=="" ( echo Aufruf: start_sprachpruefung.bat ^<werk^> [lg] & pause & exit /b 1 )
set LG=%~2
if "%LG%"=="" set LG=de
set LOG=cockpit\logs\sprachpruefung_%~1_%LG%.txt
title READ LAYER - Sprachpruefung %~1 [%LG%]
echo [1/3] Paket ...
py -3.11 tools\sprachpruefung.py %1 %LG% --paket > "%LOG%" 2>&1
if errorlevel 1 ( type "%LOG%" & pause & exit /b 1 )
echo [2/3] Modal (Whisper) ...
py -3.11 -m modal run gpu_sprache/sprache_modal.py --paket %~1_%LG% >> "%LOG%" 2>&1
if errorlevel 1 ( type "%LOG%" & echo FEHLER Modal & pause & exit /b 1 )
echo [3/3] Auswertung ...
py -3.11 tools\sprachpruefung.py %1 %LG% --auswerten >> "%LOG%" 2>&1
type "%LOG%"
echo.
echo === FERTIG - Cockpit: Sprachpruefung ===
pause
