@echo off
REM Fish-Erzaehler (Regie) -> Chatterbox-VC auf Modal, Alice Kap. 7 DE
cd /d %~dp0
py -3.11 -m modal run gpu_overlay/overlay_modal.py --paket alice_c007_fish_de
pause
