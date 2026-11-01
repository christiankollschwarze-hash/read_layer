@echo off
rem READ LAYER - MAGI EN: Chatterbox-Paket erzeugen (Stufe 502, kostenlos, KEIN Modal-Lauf).
rem Danach Modal-Lauf nur per: start_cb_neu.bat the-gift-of-the-magi en los --alle (Freigabe noetig).
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
cd /d "%~dp0"
set LOG=cockpit\logs\magi_en_paket.log
if not exist cockpit\logs mkdir cockpit\logs
echo === MAGI EN Chatterbox-Paket (Stufe 502) === > %LOG%
py -3.11 -u run.py the-gift-of-the-magi --line audio --lang en --to 500 >> %LOG% 2>&1
type %LOG%
echo.
pause
