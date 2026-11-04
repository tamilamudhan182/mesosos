@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
set /p NAME=Node name (e.g. laptop1): 
set /p DASH=Dashboard URL if this is the gateway (blank = normal node): 
if "%DASH%"=="" (python -m node.node --name %NAME% --port 7001 --web 8001 --cli) else (python -m node.node --name %NAME% --port 7001 --web 8001 --dashboard %DASH% --cli)
pause
