@echo off
rem READ LAYER - AP 61: Hoerspiel-Hybrid einbauen (Erzaehler-Einschuebe aus One-Voice-Take, Figurenrede aus Erstlauf)
rem Aufruf: start_hybrid.bat <werk> [de^|en^|beide] [liste^|takes^|los]   - wiederaufnehmbar
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
cd /d "%~dp0"
if "%~1"=="" ( echo Aufruf: start_hybrid.bat ^<werk^> [de^|en^|beide] [liste^|takes^|los] & pause & exit /b 1 )
set LGS=%~2
if "%LGS%"=="" set LGS=beide
if /I "%LGS%"=="beide" set LGS=de en
set MODUS=%~3
if "%MODUS%"=="" set MODUS=liste
for %%L in (%LGS%) do (
  echo === %%L %MODUS% ===
  py -3.11 -u tools\hybrid_einbau.py %1 %%L --%MODUS%
  if errorlevel 1 ( echo === ABBRUCH %%L - erneut starten setzt fort === & pause & exit /b 1 )
  if /I "%MODUS%"=="los" (
    py -3.11 -m modal run gpu_fa/fa_modal.py --werk %~1 --sprachen %%L
    if errorlevel 1 py -3.11 -m pipeline.s520_wortzeiten %1 --lang %%L
    call start_sprachpruefung.bat %1 %%L
  )
)
echo === FERTIG ===
pause
