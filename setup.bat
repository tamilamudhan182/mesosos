@echo off
cd /d "%~dp0"
echo [Mesh-SOS] Creating virtual environment...
python -m venv .venv || (echo Python not found. Install Python 3.10+ and tick "Add python.exe to PATH". & pause & exit /b 1)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt || (echo pip install failed - check internet & pause & exit /b 1)
echo [Mesh-SOS] Setup done. Now run run_local_demo.bat
pause
