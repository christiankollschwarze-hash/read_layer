@echo off
rem READ LAYER - LoRA-Mischlauf (CK 18.10.2026): Julia Niedermaier (alles DE, 18 h) + Bernd Ungerer + Ramona (je ~18 h, kleine Werke zuerst)
rem Aufruf:  start_lora_mix.bat [schritt]   schritt = alle (Standard) | holen | abschrift | schnitt | training | bewertung | ab_schnitt
rem Deckel im Training: kein Sprecher > 40 %. Ergebnis: gpu_lora\mix_v1\BERICHT.md, bewertung\<variante>\*.wav, hoerliste.txt
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set SCHRITT=%~1
if "%SCHRITT%"=="" set SCHRITT=alle
set LOG=cockpit\logs\lora_mix_v1.txt
title READ LAYER - LoRA Mischlauf [%SCHRITT%]
echo LoRA-Mischlauf, Schritt %SCHRITT% - Protokoll: %LOG%
py -3.11 -m modal run gpu_lora/lora_modal.py --schritt %SCHRITT% --lauf mix_v1 --mix standard %2 >> "%LOG%" 2>&1
if errorlevel 1 ( type "%LOG%" & echo FEHLER & pause & exit /b 1 )
type gpu_lora\mix_v1\BERICHT.md 2>nul
echo.
echo === FERTIG - gpu_lora\mix_v1\BERICHT.md ===
pause
