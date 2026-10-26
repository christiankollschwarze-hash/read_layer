@echo off
rem READ LAYER - AP 57: Stage 560 fuer Alice, dann Baskerville (DE). Logs: cockpit\logs\s560_<werk>_de.txt
cd /d "%~dp0"
set NOSTOP=1
call start_s560.bat alice-s-adventures-in-wonderland de
call start_s560.bat the-hound-of-the-baskervilles de
echo === AP 57 FERTIG - Berichte: work\BERICHT_560_de.md je Werk ===
pause
