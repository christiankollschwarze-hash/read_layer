@echo off
rem READ LAYER - Overlay nur fuer eine (umbesetzte oder nachgebesserte) Figur neu rechnen
rem Aufruf:  start_overlay_teil.bat <werk> <lg> "<Figur>"
rem   overlay_vorbereiten --nur -> Modal (Chatterbox VC, L4) -> overlay_montage (wendet alle Teilpakete + Korrektur an)
rem Danach:  start_trennung_messen.bat <werk> <lg>
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if "%~3"=="" (
  echo Aufruf: start_overlay_teil.bat ^<werk^> ^<lg^> "^<Figur^>"
  pause & exit /b 1
)
title READ LAYER - Overlay %~3 (%~1 %~2)
py -3.11 tools\overlay_vorbereiten.py %1 %2 "--nur=%~3"
if errorlevel 1 ( pause & exit /b 1 )
py -3.11 -m modal run gpu_overlay/overlay_modal.py --paket %~1_%~2_teil
if errorlevel 1 ( pause & exit /b 1 )
py -3.11 tools\overlay_montage.py %1 %2
echo.
echo === FERTIG - weiter: start_trennung_messen.bat %~1 %~2 ===
pause
