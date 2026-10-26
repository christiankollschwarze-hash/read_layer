@echo off
rem AP 58 Winnie-the-Pooh: Textkette 200-400 (DeepSeek) + Stage 340 + Bildanker. Stage 120 entfaellt (Original, tools/pooh_vorbereiten.py).
rem Log: cockpit\logs\ap58_text.log   Kosten: authors\milne-aa\books\winnie-the-pooh\work\kosten.jsonl
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
rem AP 58: Qualitaetstor 330 bewusst weiter (89/1403 unter 90 = freie, idiomatische Uebersetzung; Schnitt 96)
set READLAYER_WEITER=1
cd /d "%~dp0"
set WERK=winnie-the-pooh
set LOG=cockpit\logs\ap58_text.log
title READ LAYER - AP 58 Pooh Textkette
echo Textkette laeuft, Fortschritt in %LOG% ...
py -3.11 run.py %WERK% --line audio --from 200 --to 400 --live > %LOG% 2>&1
findstr /C:"[FEHLER]" %LOG% >nul && ( echo === FEHLER 200-400 === >> %LOG% & type %LOG% & pause & exit /b 1 )
py -3.11 tools\ap58_pruefen.py text >> %LOG% 2>&1
py -3.11 -m pipeline.s340_wortalignment %WERK% >> %LOG% 2>&1
if errorlevel 1 ( echo === FEHLER 340 === >> %LOG% & type %LOG% & pause & exit /b 1 )
py -3.11 tools\pooh_bildanker.py >> %LOG% 2>&1
py -3.11 tools\ap58_pruefen.py kosten >> %LOG% 2>&1
echo === FERTIG === >> %LOG%
type %LOG% | findstr /C:"[ap58]" /C:"[bildanker]" /C:"FERTIG"
pause
