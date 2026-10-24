@echo off
rem READ LAYER - Sprachkipper neu vertonen (Lexikon + deutsche Regie), nur betroffene Saetze
rem Aufruf:  start_neu_vertonen.bat <werk> [lg] [liste^|probe^|los] [--nur-whisper]
rem   liste  zeigt die Auswahl (kostenlos)   probe  12 Saetze alt/neu nach work\_neuvertonung\probe
rem   los    alle ausgewaehlten Saetze neu, dann Wortzeiten (58c) + Sprachpruefung der neuen Saetze
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if "%~1"=="" ( echo Aufruf: start_neu_vertonen.bat ^<werk^> [lg] [liste^|probe^|los] & pause & exit /b 1 )
set LG=%~2
if "%LG%"=="" set LG=de
set MODUS=%~3
if "%MODUS%"=="" set MODUS=liste
title READ LAYER - Neuvertonung %~1 [%LG%] %MODUS%
py -3.11 tools\neu_vertonen.py %1 %LG% --%MODUS% %4 %5 %6 %7 %8 %9
if errorlevel 1 ( pause & exit /b 1 )
if /I "%MODUS%"=="los" (
  echo Wortzeiten der neuen Saetze - Modal-GPU, sonst lokal ...
  py -3.11 -m modal run gpu_fa/fa_modal.py --werk %~1 --sprachen %LG%
  if errorlevel 1 py -3.11 -m pipeline.s520_wortzeiten %1 --lang %LG%
  call start_sprachpruefung.bat %1 %LG%
)
echo.
echo === FERTIG ===
pause
