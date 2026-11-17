@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3.11 -m venv .venv
    if errorlevel 1 python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" exit /b 1
".venv\Scripts\python.exe" -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11 or newer is required'"
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
if not exist ".env" copy /b ".env.example" ".env" >nul
echo Setup complete. Configure .env if needed, then run run.bat.
pause
