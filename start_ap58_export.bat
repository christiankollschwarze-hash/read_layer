@echo off
rem AP 58: Demo-Export Winnie-the-Pooh mit Abbildungen (nach Stage 560 EN+DE)
cd /d %~dp0
set PYTHONUNBUFFERED=1
set LOG=cockpit\logs\ap58_export.log
echo Export laeuft, Log: %LOG%
py -3.11 tools\export_demo.py winnie-the-pooh --audio > "%LOG%" 2>&1
type "%LOG%"
echo.
echo Fertig. Im Browser: http://localhost:5173 (Book-Shop, Winnie-the-Pooh)
pause
