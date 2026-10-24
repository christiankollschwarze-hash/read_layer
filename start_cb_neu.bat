@echo off
rem READ LAYER - Saetze mit Chatterbox NEU vertonen (17.10.2026)
rem Aufruf: start_cb_neu.bat <werk> <de|en> <liste|probe|los> [Quellen: --pruefung --nachklang --lexikon --kuration --prosodie --tags a,b]
rem   Namensprobe (Lexikon): probe --lexikon -> jeder Eintrag mind. einmal (bis 15 Saetze); LoRA aus book.json tts_lora
rem   liste = nur zeigen (kostet nichts) | probe = 6 Saetze nach work\_cb_probe\<lg>\ (alt+neu) | los = vertonen + einspielen + Wortzeiten + Pruefung + Mock-up
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set W=%~1
set L=%~2
set M=%~3
if "%W%"=="" set W=u-mikemustermann-peter-and-wendy
if "%L%"=="" set L=de
if "%M%"=="" set M=liste
set Q=%4 %5 %6 %7 %8 %9
if "%~4"=="" set Q=--pruefung --kuration
set N=6
echo %Q% | findstr /C:"--lexikon" >nul && set N=15
set LOG=cockpit\logs\cb_neu_%W%_%L%.log
title READ LAYER - Neuvertonung %W% %L% (%M%)
echo === %M% %W% %L% %Q% === > %LOG%
if /I "%M%"=="probe" (
  py -3.11 tools\cb_neu.py %W% %L% liste %Q% --probe %N% >> %LOG% 2>&1
) else (
  py -3.11 tools\cb_neu.py %W% %L% liste %Q% >> %LOG% 2>&1
)
if errorlevel 1 goto ende
if /I "%M%"=="liste" goto ende
py -3.11 -m modal run gpu_tts/tts_modal_opt.py::adapter_sichern >> %LOG% 2>&1
echo === Vertonung (Modal, Batch 8, Pruefung im Lauf) === >> %LOG%
py -3.11 -m modal run gpu_tts/tts_modal_opt.py::main --paket %W%_%L%_neu --batch 8 --zusatz n%RANDOM% >> %LOG% 2>&1
echo === Einspielen === >> %LOG%
py -3.11 tools\cb_neu.py %W% %L% einspielen >> %LOG% 2>&1
if /I "%M%"=="probe" goto ende
echo === Wortzeiten der neuen Saetze === >> %LOG%
py -3.11 -m modal run gpu_fa/fa_modal.py --werk %W% --sprachen %L% >> %LOG% 2>&1
echo === Abschluss: Satzpruefung + Mock-up === >> %LOG%
py -3.11 tools\cb_neu.py %W% %L% abschluss >> %LOG% 2>&1
:ende
echo === ENDE === >> %LOG%
findstr /C:"===" /C:"[cb_neu]" /C:"[tts_paket]" /C:"MESSUNG" /C:"Pruefung" /C:"[satzpruefung]" /C:"Zurueck:" /C:"Error" /C:"Traceback" %LOG%
pause
