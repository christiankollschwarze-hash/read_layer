@echo off
rem READ LAYER - privater ePub-Upload: Textkette (Tagger bis Regie + Wort-Alignment 54a), ohne Vertonung
rem Aufruf: start_epub_text.bat <werk> [ab-stage, Standard 50]   Log: cockpit\logs\epub_text_<werk>.log
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set WERK=%~1
if "%WERK%"=="" set WERK=u-mikemustermann-peter-and-wendy
set LOG=cockpit\logs\epub_text_%WERK%.log
set VON=%~2
if "%VON%"=="" set VON=50
title READ LAYER - Textkette %WERK%
echo Textkette laeuft, Fortschritt in %LOG% ...
py -3.11 run.py %WERK% --line audio --from %VON% --to 400 --live > %LOG% 2>&1
findstr /C:"[FEHLER]" %LOG% >nul && ( echo === FEHLER Stage 50-56 === >> %LOG% & type %LOG% & pause & exit /b 1 )
py -3.11 -m pipeline.s340_wortalignment %WERK% >> %LOG% 2>&1
if errorlevel 1 ( echo === FEHLER Stage 54a === >> %LOG% & type %LOG% & pause & exit /b 1 )
echo === FERTIG === >> %LOG%
echo === FERTIG ===
pause
