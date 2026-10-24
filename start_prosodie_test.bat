@echo off
rem READ LAYER - Testlauf Prosodie-Vokabelheft v0.1 (23.10.2026)
rem 30 Saetze (15 DE, 15 EN) je zweimal: A ohne Markup, B mit Markup. Modal L4, geschaetzt 0,10-0,30 $.
rem Ergebnis: gpu_tts\prosodie_test_v01\hoertest.html (oeffnet sich am Ende)
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
title READ LAYER - Prosodie-Test v0.1
set LOG=cockpit\logs\prosodie_test_v01.log
echo === Paket === > %LOG%
py -3.11 tools\prosodie_markup.py paket >> %LOG% 2>&1
if errorlevel 1 goto ende
echo === Vertonung (Modal) === >> %LOG%
py -3.11 -m modal run gpu_tts/prosodie_test_modal.py >> %LOG% 2>&1
if errorlevel 1 goto ende
echo === Hoertest-Seite === >> %LOG%
py -3.11 tools\prosodie_markup.py seite >> %LOG% 2>&1
start "" gpu_tts\prosodie_test_v01\hoertest.html
:ende
echo === ENDE === >> %LOG%
findstr /C:"===" /C:"[prosodie]" /C:"Error" /C:"Traceback" %LOG%
pause
