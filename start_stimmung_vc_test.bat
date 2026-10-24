@echo off
rem READ LAYER - Test: Stimmung aus fremdem Clip -> Chatterbox -> VC auf Margaret (23.10.2026)
rem Clips vorher nach gpu_tts\stimmung_vc_test\muster\  (Name: wuetend_x.mp3, fluesternd_x.wav ... - mp3, m4a, wav, webm, ogg; max. 10 s werden genutzt)
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
title READ LAYER - Stimmung/VC-Test
rem Standard: Emo-DB-Sprecher 08,03 + eigene Clips aus muster\. Andere: start_stimmung_vc_test.bat --emodb 09,10 | ohne Emo-DB: --emodb -
set T=gpu_tts\stimmung_vc_test
set LOG=cockpit\logs\stimmung_vc_test.log
copy /y stimmen_archiv\grossmutter_a\muster_de.wav %T%\ref_grossmutter_a_de.wav >nul
copy /y stimmen_archiv\grossmutter_a\muster_en.wav %T%\ref_grossmutter_a_en.wav >nul
echo === Lauf (Modal L4) === > %LOG%
py -3.11 -m modal run gpu_tts/stimmung_vc_test.py %* >> %LOG% 2>&1
echo === ENDE === >> %LOG%
findstr /C:"===" /C:"[stimmung]" /C:"Error" /C:"Traceback" %LOG%
py -3.11 tools\ergebnis_ordnen.py
start "" %T%\ergebnis
pause
