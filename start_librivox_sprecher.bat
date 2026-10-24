@echo off
rem LibriVox-Sprecherauswahl (Audition-Cockpit, Urteile -> daten\verdicts.csv)
cd /d "%~dp0"
start "" http://localhost:8765
py -3.11 tools\librivox_curate.py serve
