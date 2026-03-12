@echo off
REM Run APF Manifesto in development mode (no build needed).
REM Requires: pip install kivy kivymd Pillow  (or activate your venv first)
cd /d "%~dp0"
python main.py
pause
