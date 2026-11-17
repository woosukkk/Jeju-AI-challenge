@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat first.
    pause
    exit /b 1
)
set "SOURCE=%~1"
if "%SOURCE%"=="" set "SOURCE=data_source\jeju_store.csv"
if not exist "%SOURCE%" (
    echo Data file not found: %SOURCE%
    echo Put the Jeju store CSV at data_source\jeju_store.csv or pass its path.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m trade_itsuda.ingest "%SOURCE%"
if errorlevel 1 (
    pause
    exit /b 1
)
echo Import complete. Start the app with run.bat.
pause
