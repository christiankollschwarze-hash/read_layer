@echo off
rem READ LAYER - Werk (eine Sprache) KOMPLETT mit LoRA-Adapter vertonen (18.10.2026, AP claude/AP_lora_librivox.md)
rem Aufruf: start_lora_komplett.bat [werk] [lg]   Adapter: book.json tts_lora, sonst config.TTS_LORA (DE: mix_v1), Stimme grossmutter_a
rem Ablauf: Paket (Lexikon muss freigegeben sein) -> Modal Batch 8 + Pruefung im Lauf -> Fertigstellung Modal (58c, Raender,
rem         Tempo aus jobs.json, 58c, Satzpruefung) -> Mock-up-Export (privates Regal)
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set W=%~1
set L=%~2
if "%W%"=="" set W=u-mikemustermann-peter-and-wendy
if "%L%"=="" set L=de
set D=..\taella-app\public\privat\mikemustermann
set LOG=cockpit\logs\lora_komplett_%W%_%L%.log
title READ LAYER - LoRA komplett %W% %L%
echo Laeuft, Fortschritt in %LOG% ...
echo === Paket === > %LOG%
py -3.11 tools\tts_paket.py %W% %L% --ref=grossmutter_a --lexikon-pflicht >> %LOG% 2>&1
if errorlevel 1 goto ende
echo === Adapter im Volume + lokale Sicherung === >> %LOG%
py -3.11 -m modal run gpu_tts/tts_modal_opt.py::adapter_sichern >> %LOG% 2>&1
if errorlevel 1 goto ende
echo === Vertonung Modal (LoRA, Batch 8) === >> %LOG%
py -3.11 -m modal run gpu_tts/tts_modal_opt.py::main --paket %W%_%L% --batch 8 --no-herunterladen >> %LOG% 2>&1
if errorlevel 1 goto ende
echo === Fertigstellen Modal === >> %LOG%
py -3.11 -m modal run gpu_tts/fertig_modal.py --werk %W% --sprachen %L% --variante auto >> %LOG% 2>&1
if errorlevel 1 goto ende
echo === Mock-up-Export === >> %LOG%
if exist %D%\%W% py -3.11 tools\export_demo.py %W% %D% --audio >> %LOG% 2>&1
:ende
echo === ENDE === >> %LOG%
findstr /C:"===" /C:"[tts_paket]" /C:"LoRA" /C:"Tempo" /C:"gesichert" /C:"vorhanden" /C:"MESSUNG" /C:"Pruefung" /C:"fertiggestellt" /C:"entpackt" /C:"Error" /C:"Traceback" %LOG%
pause
