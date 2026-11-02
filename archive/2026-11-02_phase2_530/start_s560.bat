@echo off
rem READ LAYER - Stage 560 Sprachpruefung mit Neuvertonung (AP 57, 26.10.2026)
rem Aufruf:  start_s560.bat <werk> [lg]       z. B. start_s560.bat alice-s-adventures-in-wonderland
rem   Pruefen (Whisper large-v3 auf Modal) -> Auswahl -> Gemini-Neuvertonung (gleiche Stimmen) -> Wortzeiten
rem   -> erneut Pruefen, hoechstens 2 Runden je Satz. Rest: work\BERICHT_560_<lg>.md (Kuratormodus).
rem   Danach Wortbruecke (s525) + Demo-Export. Alte WAVs: fassungen\<lg>\audio_alt_<datum>\
rem Kosten (Schaetzung): Whisper ~0,3-0,5 $ je Werk (erste Pruefung), Nachpruefung nur neue Saetze; Gemini nur fuer Auswahl.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set NOPAUSE=1
cd /d "%~dp0"
if "%~1"=="" ( echo Aufruf: start_s560.bat ^<werk^> [lg] & pause & exit /b 1 )
set W=%~1
set LG=%~2
if "%LG%"=="" set LG=de
set GRENZE_ARG=
if "%S560_OHNE_GRENZE%"=="1" set GRENZE_ARG=--ohne-grenze
set LOG=cockpit\logs\s560_%W%_%LG%.txt
title READ LAYER - Stage 560 %W% [%LG%]
echo === Stage 560 %W% [%LG%] %date% %time% === > "%LOG%"
for /L %%R in (1,1,3) do (
  echo [Runde %%R] Pruefen ...
  call :pruefen || goto fehler
  if %%R==3 goto bericht
  py -3.11 tools\s560_sprachpruefung.py %W% %LG% --auswahl %GRENZE_ARG% >> "%LOG%" 2>&1
  if errorlevel 4 goto grenze
  if errorlevel 3 goto bericht
  if errorlevel 1 goto fehler
  echo [Runde %%R] Neu vertonen ^(Gemini^) ...
  py -3.11 tools\neu_vertonen.py %W% %LG% --los --stage560 >> "%LOG%" 2>&1
  if errorlevel 1 goto fehler
  echo [Runde %%R] Wortzeiten ...
  py -3.11 -m modal run gpu_fa/fa_modal.py --werk %W% --sprachen %LG% >> "%LOG%" 2>&1
  if errorlevel 1 py -3.11 -m pipeline.s520_wortzeiten %W% --lang %LG% >> "%LOG%" 2>&1
)
:bericht
py -3.11 tools\s560_sprachpruefung.py %W% %LG% --bericht >> "%LOG%" 2>&1
echo Wortbruecke + Demo-Export ...
py -3.11 -m pipeline.s525_wortbruecke %W% >> "%LOG%" 2>&1
if exist ..\taella-app\public\demo\%W%\manifest_en.json py -3.11 tools\export_demo.py %W% --audio >> "%LOG%" 2>&1
type "%LOG%"
echo === FERTIG - Bericht: work\BERICHT_560_%LG%.md ===
if not "%NOSTOP%"=="1" pause
exit /b 0

:pruefen
py -3.11 tools\sprachpruefung.py %W% %LG% --paket >> "%LOG%" 2>&1 || exit /b 1
py -3.11 -m modal run gpu_sprache/sprache_modal.py --paket %W%_%LG% >> "%LOG%" 2>&1 || exit /b 1
py -3.11 tools\sprachpruefung.py %W% %LG% --auswerten >> "%LOG%" 2>&1 || exit /b 1
exit /b 0

:grenze
type "%LOG%"
echo HALT: zu viele Saetze ausgewaehlt - nichts neu vertont. Bericht: work\BERICHT_sprachpruefung_%LG%.md
if not "%NOSTOP%"=="1" pause
exit /b 4

:fehler
type "%LOG%"
echo FEHLER - siehe %LOG%
pause
exit /b 1
