@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
echo Starting dashboard + 4 nodes (A-B-C-D) and sending test SOS...
python demo.py --keep
pause
