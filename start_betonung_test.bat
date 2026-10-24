@echo off
rem READ LAYER - Wortbetonung nur mit Chatterbox: 6 Betonungs- + 6 Pausensaetze, Emoji-Bibliothek + VC + Fluestertrick (23.10.2026), ca. 0,10 $
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
title READ LAYER - Betonungstest
set LOG=cockpit\logs\betonung_test.log
py -3.11 -m modal run gpu_tts/betonung_test.py > %LOG% 2>&1
findstr /C:"[betonung]" /C:"Error" /C:"Traceback" %LOG%
start "" gpu_tts\stimmung_vc_test\ergebnis_betonung
pause
