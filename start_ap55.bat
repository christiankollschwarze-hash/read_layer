@echo off
rem READ LAYER - AP 55 (26.10.2026): Punkt e + g aus AP 54c
rem  e) Die Spiegelschwestern (DE-Original): Pruefaligner (Modal) -> 345 + DeepSeek-Nachlauf -> 525 (inkl. Hoerspiel ths) -> Regression
rem  g) zweiter DeepSeek-Nachlauf nur fuer die noch markierten Saetze (CotW 2, Alice 14, Sleepy 3, AYLI 2, Jekyll 16, P&W 11, Baskerville 17)
rem     Bericht Lauf 1 bleibt als work\345_verschiebung_vorher.json
rem  danach Demo-Export ins Mock-up (Manifeste mit t/tz/ths).
rem Kosten geschaetzt: DeepSeek ~0,0002 $/Satz x ~85 Saetze ~0,02 $ + Modal Spiegelschwestern ~0,002 $ -> gesamt < 0,03 $.
rem Aufruf: start_ap55.bat   (Logs: cockpit\logs\verschiebung_<werk>.txt)
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set NOPAUSE=1
cd /d "%~dp0"
for %%W in (die-spiegelschwestern call-of-the-wild alice-s-adventures-in-wonderland the-legend-of-sleepy-hollow as-you-like-it jekyll-and-hyde peter-and-wendy the-hound-of-the-baskervilles) do (
  echo ===== %%W =====
  call start_verschiebung.bat %%W
  if errorlevel 1 ( echo FEHLER %%W - weiter mit naechstem Werk ) else (
    if exist ..\taella-app\public\demo\%%W\audio_hoerspiel (
      py -3.11 tools\export_demo.py %%W --audio --hoerspiel >> cockpit\logs\verschiebung_%%W.txt 2>&1
    ) else if exist ..\taella-app\public\demo\%%W\manifest_en.json (
      py -3.11 tools\export_demo.py %%W --audio >> cockpit\logs\verschiebung_%%W.txt 2>&1
    )
  )
)
echo.
echo === Zusammenfassung 345 (vorher -^> nachher markiert) ===
py -3.11 tools\ap55_bilanz.py
echo === FERTIG - Logs: cockpit\logs\verschiebung_*.txt ===
pause
