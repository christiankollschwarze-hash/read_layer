@echo off
rem READ LAYER - Chatterbox echtes Batching: Probe Kapitel 1 EN, Batch 8 und 16 (Vergleich: Basis 0,77 $ je 50k Zeichen)
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set W=u-mikemustermann-peter-and-wendy
set LOG=cockpit\logs\epub_batch_%W%.log
title READ LAYER - Batching-Probe
echo Batching-Probe laeuft, Fortschritt in %LOG% ...
echo === EN Batch 8 === > %LOG%
py -3.11 -m modal run gpu_tts/tts_modal_opt.py::main --paket %W%_en --kapitel-nur c001 --batch 8 >> %LOG% 2>&1
echo === EN Batch 16 === >> %LOG%
py -3.11 -m modal run gpu_tts/tts_modal_opt.py::main --paket %W%_en --kapitel-nur c001 --batch 16 >> %LOG% 2>&1
echo === FERTIG === >> %LOG%
findstr /C:"MESSUNG" /C:"c001:" /C:"Error" /C:"FEHLER" %LOG%
pause
