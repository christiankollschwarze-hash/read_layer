@echo off
rem READ LAYER - Figur umbesetzen: neue Kandidatenstimmen designen (Gemini) und gegen den Werk-Erzaehler messen
rem Aufruf:  start_umbesetzen.bat <werk> <lg> "<Figur>" [hoeher,groesser]
rem Danach:  Cockpit "Hoerspiel-Pruefung" -> Kandidat anhoeren und waehlen -> start_overlay_teil.bat
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if "%~3"=="" (
  echo Aufruf: start_umbesetzen.bat ^<werk^> ^<lg^> "^<Figur^>" [hoeher,groesser]
  pause & exit /b 1
)
set RICHTUNG=%~4
if "%RICHTUNG%"=="" set RICHTUNG=hoeher,groesser
title READ LAYER - Umbesetzen %~3 (%~1 %~2)
py -3.11 tools\umbesetzen.py %1 %2 %3 --richtung %RICHTUNG%
echo.
echo === FERTIG - Kandidaten im Cockpit: Hoerspiel-Pruefung ===
pause
