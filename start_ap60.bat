@echo off
rem READ LAYER - AP 60 (27.10.2026): Hoerprobe woertliche Rede, Alice Kap. VII (A Multi-Speaker / B Voice Conversion / Referenz)
rem Keine Aenderung an der Produktion. Schaetzung: Gemini ~0,10 $, Modal ~0,15-0,25 $ (zusammen < 0,40 $).
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
title READ LAYER - AP 60 Hoerprobe woertliche Rede
set LOG=cockpit\logs\ap60.log
echo === 1 Vorbereitung === > %LOG%
py -3.11 tools\ap60_vorbereiten.py >> %LOG% 2>&1
echo === 2 Gemini (A Multi-Speaker + B Erzaehler-Basis) === >> %LOG%
py -3.11 tools\ap60_gemini.py >> %LOG% 2>&1 || goto fehler
echo === 3 Modal (MMS_FA, Chatterbox VC, Whisper, Lautheit) === >> %LOG%
py -3.11 -m modal run gpu_tts/ap60_modal.py >> %LOG% 2>&1 || goto fehler
echo === ENDE === >> %LOG%
findstr /C:"===" /C:"[ap60]" /C:"Error" /C:"Traceback" %LOG%
start "" tests\ap60\ergebnis
pause
exit /b 0
:fehler
echo === FEHLER === >> %LOG%
findstr /C:"===" /C:"[ap60]" /C:"Error" /C:"Traceback" /C:"RuntimeError" %LOG%
pause
exit /b 1
