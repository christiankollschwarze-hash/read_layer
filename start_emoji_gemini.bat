@echo off
rem READ LAYER - Emoji-Referenzen mit Gemini (Schauspieler-Regie) -> Chatterbox -> VC auf Margaret (23.10.2026)
rem Gemini: 14 Mustersaetze DE (ca. 2 min Audio, Cent-Betrag). Modal: ca. 0,10-0,15 $. Emo-DB laeuft hier NICHT mit (--emodb -).
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
title READ LAYER - Emoji-Referenzen Gemini
set LOG=cockpit\logs\emoji_gemini.log
echo === Gemini-Mustersaetze === > %LOG%
py -3.11 tools\emoji_referenzen_gemini.py %* >> %LOG% 2>&1
if errorlevel 1 goto ende
call start_stimmung_vc_test.bat --emodb -
:ende
findstr /C:"===" /C:"[emoji]" /C:"Error" /C:"Traceback" %LOG%
pause
