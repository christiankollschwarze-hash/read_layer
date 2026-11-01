@echo off
rem READ LAYER - AP 63: Referenztext "Nordwind und Sonne" EN/DE fuer Stimmen-Hoerproben (ein LLM-Aufruf, < 1 Cent)
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
py -3.11 -u tools\referenztext_nordwind.py
echo.
pause
