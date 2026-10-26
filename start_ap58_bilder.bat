@echo off
rem AP 58: 27 Pooh-Bilder (Gemini-Ausgabe) ins Werk kopieren -> images\bilder\pooh_NNN.jpg, dann Bildanker aktualisieren
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
set QUELLE=%USERPROFILE%\Claude\gemini-mcp\output
set ZIEL=authors\milne-aa\books\winnie-the-pooh\images\bilder
if not exist "%ZIEL%" mkdir "%ZIEL%"
set N=0
for %%F in ("%QUELLE%\*-pooh_*.jpg") do (
  set NAME=%%~nxF
  copy /Y "%%F" "%ZIEL%\!NAME:~16!" >nul
  set /a N+=1
)
echo %N% Bilder nach %ZIEL% kopiert (Soll 27).
if exist authors\milne-aa\books\winnie-the-pooh\work\200_tagging.json py -3.11 tools\pooh_bildanker.py
pause
