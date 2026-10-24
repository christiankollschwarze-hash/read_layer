@echo off
rem READ LAYER - Hoertest mix_v1 vs mix_v2 mit Emoji-Weg: Der grosse Gott Pan Kap.1 Schluss, Grandma + Herr A (24.10.2026), ca. 0,30 $
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
title READ LAYER - Pan-Test
set LOG=cockpit\logs\pan_test.log
if not exist authors\machen-a\books\the-great-god-pan\work\aussprache_de.json py -3.11 tools\aussprache_lexikon.py the-great-god-pan de
py -3.11 -m modal run gpu_tts/pan_test.py > %LOG% 2>&1
findstr /C:"[pan]" /C:"Error" /C:"Traceback" %LOG%
start "" gpu_tts\pan_test
pause
