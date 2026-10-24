@echo off
rem READ LAYER - LoRA-Mischlauf mix_v2 (CK 23.10.2026): Ramona-Dominanz austreiben
rem Sprecher: Julia Niedermaier (5424, alles DE) + Bernd Ungerer (9565) + Hokuspokus (2037, neu), je ~18 h Rohaudio, nivelliert
rem Julia + Bernd: fertige Schnipsel aus mix_v1 uebernommen (kein neues Holen/Whisper/Schnitt). Ramona nicht im Training.
rem Bewertung: basis / mix_v2 / mix_v1 (Vergleich) auf grossmutter_a + Gegenprobe Ramona; Spalte "Aehnlich Ramona" = Dominanz-Mass
rem Aufruf:  start_lora_mix_v2.bat [schritt]   schritt = alle (Standard) | holen | abschrift | schnitt | training | bewertung | ab_schnitt
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set SCHRITT=%~1
if "%SCHRITT%"=="" set SCHRITT=alle
set LOG=cockpit\logs\lora_mix_v2.txt
title READ LAYER - LoRA mix_v2 [%SCHRITT%]
echo LoRA mix_v2, Schritt %SCHRITT% - Protokoll: %LOG%
py -3.11 -m modal run gpu_lora/lora_modal.py --schritt %SCHRITT% --lauf mix_v2 --mix v2 --vergleich mix_v1:step_01000.safetensors --stimmen herr_a %2 >> "%LOG%" 2>&1
if errorlevel 1 ( type "%LOG%" & echo FEHLER & pause & exit /b 1 )
type gpu_lora\mix_v2\BERICHT.md 2>nul
echo.
echo === FERTIG - gpu_lora\mix_v2\BERICHT.md ===
pause
