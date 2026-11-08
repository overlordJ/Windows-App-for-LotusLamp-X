@echo off
title LotusLamp X Controller
echo [LotusLamp X] Checking dependencies...
pip install -q -r "%~dp0requirements.txt"
echo [LotusLamp X] Launching...
python "%~dp0app.py"
pause
