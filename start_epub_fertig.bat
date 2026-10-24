@echo off
rem READ LAYER - privater Upload fertigstellen: Wortzeiten -> Raender schneiden -> Tempo 0,91 -> Wortzeiten neu
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set W=%~1
if "%W%"=="" set W=u-mikemustermann-peter-and-wendy
set LOG=cockpit\logs\epub_fertig_%W%.log
title READ LAYER - Fertigstellen %W%
echo Fertigstellung laeuft, Fortschritt in %LOG% ...
echo. > %LOG%
for %%L in (en de) do (
  echo === %%L 1/4 Wortzeiten Rohfassung === >> %LOG%
  py -3.11 -m modal run gpu_fa/fa_modal.py --werk %W% --sprachen %%L --force >> %LOG% 2>&1
  echo === %%L 2/4 Raender schneiden === >> %LOG%
  py -3.11 tools\raender_schneiden.py %W% %%L >> %LOG% 2>&1
  echo === %%L 3/4 Tempo 0,91 === >> %LOG%
  py -3.11 tools\tempo_anpassen.py %W% %%L 0.91 >> %LOG% 2>&1
  echo === %%L 4/4 Wortzeiten Endfassung === >> %LOG%
  py -3.11 -m modal run gpu_fa/fa_modal.py --werk %W% --sprachen %%L --force >> %LOG% 2>&1
  echo === %%L 5/5 Satzpruefung === >> %LOG%
  py -3.11 tools\satzpruefung.py %W% %%L --schneiden >> %LOG% 2>&1
)
echo === FERTIG === >> %LOG%
findstr /C:"===" /C:"[raender]" /C:"[tempo]" /C:"[satzpruefung]" /C:"Zurueck:" /C:"Error" /C:"Traceback" %LOG%
pause
