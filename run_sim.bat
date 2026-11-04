@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python -m sim.run %*
echo Figures and CSV are in the results folder.
start "" results
pause
