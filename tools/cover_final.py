"""Weiterleitung (19.10.2026): Stage liegt jetzt in pipeline/s615_cover_final.py.
Bleibt nur, bis das Cockpit neu gestartet ist; danach ins Archiv."""
import os, runpy, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
runpy.run_module("pipeline.s615_cover_final", run_name="__main__")
