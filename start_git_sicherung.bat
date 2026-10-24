@echo off
title READ LAYER - Git-Sicherung
set LOG=C:\Users\sabin\read_layer\cockpit\logs\git_sicherung.txt
echo ==== %date% %time% ==== >> "%LOG%"

for %%R in ("C:\Users\sabin\read_layer" "C:\Users\sabin\taella-app") do (
  cd /d %%R
  git add -A >> "%LOG%" 2>&1
  git diff --cached --quiet || git commit -m "Auto-Stand %date%" >> "%LOG%" 2>&1
  git push >> "%LOG%" 2>&1
)
