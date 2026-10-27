@echo off
rem READ LAYER - AP 60 Variante C: Hybrid (Erzaehlerspur + Figurenrede aus Erstlauf), lokal, 0 $
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
py -3.11 -m pip install -q pyloudnorm
py -3.11 tools\ap60_c.py
start "" tests\ap60\ergebnis
pause
