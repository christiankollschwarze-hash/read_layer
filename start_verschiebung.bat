@echo off
rem READ LAYER - AP 54b: Pruefaligner (Modal) -> Verschiebungsdetektor + DeepSeek-Nachlauf -> Wortbruecke -> Regression
rem Aufruf: start_verschiebung.bat [werk]   (Default call-of-the-wild)
rem Liegt work\345_pruefaligner.json schon vor, wird Modal uebersprungen (Call of the Wild: aus AP 54a uebernommen).
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set WERK=%~1
if "%WERK%"=="" set WERK=call-of-the-wild
set LOG=cockpit\logs\verschiebung_%WERK%.txt
echo === %date% %time% %WERK% === > "%LOG%"
for /f "delims=" %%p in ('py -3.11 -c "from config import config;print(config.work_path('%WERK%','345_pruefaligner'))"') do set PA=%%p
if not exist "%PA%" (
  echo [1/4] Modal: Pruefaligner awesome_co
  py -3.11 -m modal run gpu_align/pruefaligner_modal.py --werk %WERK% >> "%LOG%" 2>&1
  if errorlevel 1 ( type "%LOG%" & echo FEHLER Modal & (if not defined NOPAUSE pause) & exit /b 1 )
) else ( echo [1/4] Pruefaligner vorhanden - uebersprungen )
echo [2/4] Verschiebungsdetektor + DeepSeek-Nachlauf (nur markierte Saetze)
py -3.11 -m pipeline.s345_verschiebung %WERK% --nachlauf >> "%LOG%" 2>&1
if errorlevel 1 ( type "%LOG%" & echo FEHLER 345 & (if not defined NOPAUSE pause) & exit /b 1 )
echo [3/4] Wortbruecke
py -3.11 -m pipeline.s525_wortbruecke %WERK% >> "%LOG%" 2>&1
echo [4/4] Regression Manifest + Kosten
py -3.11 tools\regression_54b.py %WERK% >> "%LOG%" 2>&1
py -3.11 -m pipeline.usage_log %WERK% >> "%LOG%" 2>&1
type "%LOG%"
echo.
echo === FERTIG - Bericht: work\345_verschiebung.json, work\525_wortbruecke.json ===
if not defined NOPAUSE pause
