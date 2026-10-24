@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
start "" http://127.0.0.1:8765
py -3.11 cockpit\server.py
pause
