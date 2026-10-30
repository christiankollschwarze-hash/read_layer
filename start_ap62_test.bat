@echo off
rem READ LAYER - AP 62 Test: Stufe 510 (Hoerspiel-Hybrid) fuer Alice Kap. VII im Testordner tests\ap62\
rem Produktion und fertige Werke bleiben unberuehrt. Aufruf: start_ap62_test.bat [liste|los]
rem Standard = liste (kostenlos). "los" startet Gemini + Modal.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
cd /d "%~dp0"
set MODUS=%~1
if "%MODUS%"=="" set MODUS=liste
set LOG=cockpit\logs\ap62_test.log
if not exist cockpit\logs mkdir cockpit\logs
echo === AP 62 Test %MODUS%: alice-s-adventures-in-wonderland, Kap. VII, de+en === > %LOG%
py -3.11 -u tools\hybrid_test_ap62.py alice-s-adventures-in-wonderland c007 de,en %MODUS% >> %LOG% 2>&1
type %LOG%
echo.
echo Protokoll: tests\ap62\alice-s-adventures-in-wonderland\work\hybrid_de.json
pause
