@echo off
rem READ LAYER - ElevenLabs Eleven v4 (fal.ai) mit denselben 14 Emoji-Saetzen DE+EN (23.10.2026), ca. 0,25 $
rem Optionen: --voice Rachel --stability 0.3 --nur wuetend,ironisch
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
title READ LAYER - ElevenLabs-Vergleich
py -3.11 tools\elevenlabs_vergleich.py %* > cockpit\logs\elevenlabs_vergleich.log 2>&1
type cockpit\logs\elevenlabs_vergleich.log
py -3.11 tools\ergebnis_ordnen.py
start "" gpu_tts\stimmung_vc_test\ergebnis
pause
