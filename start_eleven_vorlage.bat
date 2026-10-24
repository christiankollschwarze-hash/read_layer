@echo off
rem READ LAYER - ElevenLabs-Prosodie als Vorlage -> Chatterbox -> VC auf Margaret (23.10.2026), ca. 0,10 $
rem Vorlagen: gpu_tts\stimmung_vc_test\muster\*_eleven.mp3 (DE-Saetze aus dem v4-Vergleich). Emo-DB laeuft nicht mit.
cd /d "%~dp0"
call start_stimmung_vc_test.bat --emodb -
