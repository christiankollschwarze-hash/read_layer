@echo off
rem READ LAYER - Hoerspiel-Pruefung: Trennung Figur <-> Erzaehler am fertigen Overlay messen
rem Aufruf:  start_trennung_messen.bat <werk> [lg^|de,en] [--korrektur] [--eichen]
rem   1) Paket bauen (falls fehlt) + fertiges Overlay als naechste Runde r1, r2, ... + Praat (lokal)
rem   2) ECAPA + pyannote auf Modal (je Sprache ein T4, hoechstens 10 gleichzeitig, ca. 0,03 $ je Lauf)
rem   3) Auswertung + Rueckfluss nach casting.json (pruefung je Figur) -> Cockpit "Hoerspiel-Pruefung"
setlocal EnableDelayedExpansion
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if "%~1"=="" (
  echo Aufruf: start_trennung_messen.bat ^<werk^> [lg^|de,en] [--korrektur] [--eichen]
  pause & exit /b 1
)
set WERK=%~1
set LGS=%~2
if "%LGS%"=="" set LGS=de
if "%LGS:~0,2%"=="--" set LGS=de
set EXTRA=
for %%A in (%*) do (
  if "%%~A"=="--korrektur" set EXTRA=!EXTRA! --korrektur
  if "%%~A"=="--eichen" set EXTRA=!EXTRA! --eichen
)
set AUSW=
echo %EXTRA% | find "--eichen" >nul && set AUSW=--eichen
title READ LAYER - Hoerspiel-Pruefung %WERK% [%LGS%]
set LOG=cockpit\logs\trennung_%WERK%.txt
echo === %date% %time% %WERK% [%LGS%] === > "%LOG%"
set PAKETE=
for %%L in (%LGS:,= %) do (
  echo [1/3] Paket + Runde + Praat: %WERK% %%L
  py -3.11 tools\trennung_messen.py %WERK% %%L --runde auto %EXTRA% >> "%LOG%" 2>&1
  if errorlevel 1 ( type "%LOG%" & echo FEHLER bei %%L & pause & exit /b 1 )
  if defined PAKETE (set PAKETE=!PAKETE!,%WERK%_%%L) else (set PAKETE=%WERK%_%%L)
)
echo [2/3] Modal (ECAPA + pyannote): %PAKETE%
py -3.11 -m modal run gpu_messung/messung_modal.py --pakete %PAKETE% >> "%LOG%" 2>&1
if errorlevel 1 ( type "%LOG%" & echo FEHLER Modal & pause & exit /b 1 )
for %%L in (%LGS:,= %) do (
  echo [3/3] Auswertung + Rueckfluss: %WERK% %%L
  py -3.11 tools\trennung_auswerten.py %WERK% %%L %AUSW% >> "%LOG%" 2>&1
)
type "%LOG%"
echo.
echo === FERTIG - Tor im Cockpit: Hoerspiel-Pruefung ===
pause
