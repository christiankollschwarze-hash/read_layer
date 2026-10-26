@echo off
rem READ LAYER - AP 54a: Vergleichslauf SimAlign / awesome-align gegen Stage 340 (DeepSeek)
rem Aufruf: start_aligner_vergleich.bat [werk]   (Default call-of-the-wild)
rem Modal: 3x T4 (ganzes Werk) + 3x CPU (100 Saetze), geschaetzt < 0,20 $
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set WERK=%~1
if "%WERK%"=="" set WERK=call-of-the-wild
set LOG=cockpit\logs\aligner_vergleich_%WERK%.txt
echo === %date% %time% %WERK% === > "%LOG%"
echo [1/2] Modal: Aligner-Laeufe %WERK%
py -3.11 -m modal run gpu_align/align_vergleich_modal.py --werk %WERK% >> "%LOG%" 2>&1
if errorlevel 1 ( type "%LOG%" & echo FEHLER Modal & pause & exit /b 1 )
echo [2/2] Auswertung
py -3.11 tools\aligner_vergleich_auswerten.py %WERK% >> "%LOG%" 2>&1
type "%LOG%"
echo.
echo === FERTIG - Ergebnis: authors\...\%WERK%\work\_aligner_vergleich\tabelle.md ===
pause
