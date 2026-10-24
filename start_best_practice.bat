@echo off
rem READ LAYER - Best-Practice-Lauf (Emoji-Bibliothek, Pausen-/Betonungsregeln, FA-Pruefung, VC, Fluestertrick) mit anderer Werkstimme (23.10.2026), ca. 0,20 $
rem Aufruf: start_best_practice.bat [stimme]   Standard herr_a (Arthur)
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set READLAYER_STIMME=%~1
if "%READLAYER_STIMME%"=="" set READLAYER_STIMME=herr_a
title READ LAYER - Best Practice %READLAYER_STIMME%
set LOG=cockpit\logs\best_practice_%READLAYER_STIMME%.log
py -3.11 -m modal run gpu_tts/arthur_best_practice.py > %LOG% 2>&1
findstr /C:"[best]" /C:"Error" /C:"Traceback" %LOG%
start "" gpu_tts\stimmung_vc_test\ergebnis_%READLAYER_STIMME%
pause
