@echo off
rem READ LAYER - LoRA-Testlauf Ramona (AP claude/AP_lora_librivox.md): eigenes Chatterbox-Gewicht aus LibriVox
rem Aufruf:  start_lora_test.bat [schritt]      schritt = alle (Standard) | holen | abschrift | schnitt | training | bewertung
rem   ~10 h Rohaudio (Pinocchio, Fraeulein Else, Sterben) -> Whisper -> Schnitt+Pruefung -> LoRA (A100) -> Peter Pan Kap. 1
rem Ergebnis: gpu_lora\ramona_test\BERICHT.md, bewertung\<variante>\*.wav, hoerliste.txt
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set SCHRITT=%~1
if "%SCHRITT%"=="" set SCHRITT=alle
set LOG=cockpit\logs\lora_ramona_test.txt
title READ LAYER - LoRA Testlauf Ramona [%SCHRITT%]
echo LoRA-Testlauf Ramona, Schritt %SCHRITT% - Protokoll: %LOG%
py -3.11 -m modal run gpu_lora/lora_modal.py --schritt %SCHRITT% --lauf ramona_test %2 >> "%LOG%" 2>&1
if errorlevel 1 ( type "%LOG%" & echo FEHLER & pause & exit /b 1 )
type gpu_lora\ramona_test\BERICHT.md 2>nul
echo.
echo === FERTIG - gpu_lora\ramona_test\BERICHT.md ===
pause
