@echo off
rem READ LAYER - AP 54c: Verschiebungsdetektor + Wortbruecke (start_verschiebung.bat) fuer alle fertigen EN-Werke,
rem danach Manifest mit Wortzeiten t/tz/zspans: s710 --manifest-only (GCS) + Demo-Export ins Mock-up.
rem Werke = 340 + Wortzeiten EN+DE vorhanden, Quelle EN. Nicht dabei: call-of-the-wild (AP 54b erledigt),
rem die-spiegelschwestern (DE-Original; s345 setzt Quelle EN voraus).
rem Kosten geschaetzt ~0,02 $ je 32k Woerter (Modal T4 Pruefaligner + DeepSeek-Nachlauf), gesamt ~0,13-0,20 $.
rem Aufruf: start_verschiebung_alle.bat   (Log je Werk: cockpit\logs\verschiebung_<werk>.txt)
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set NOPAUSE=1
cd /d "%~dp0"
for %%W in (alice-s-adventures-in-wonderland the-legend-of-sleepy-hollow as-you-like-it jekyll-and-hyde peter-and-wendy the-hound-of-the-baskervilles) do (
  echo ===== %%W =====
  call start_verschiebung.bat %%W
  if errorlevel 1 ( echo FEHLER %%W - weiter mit naechstem Werk ) else (
    py -3.11 -m pipeline.s710_cloud_export %%W --lang en --manifest-only >> cockpit\logs\verschiebung_%%W.txt 2>&1
    if exist ..\taella-app\public\demo\%%W\manifest_en.json py -3.11 tools\export_demo.py %%W --audio >> cockpit\logs\verschiebung_%%W.txt 2>&1
  )
)
echo === FERTIG - Logs: cockpit\logs\verschiebung_*.txt ===
pause
