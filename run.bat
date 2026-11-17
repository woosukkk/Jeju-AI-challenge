@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat first.
    pause
    exit /b 1
)
echo Open http://localhost:8501 in your browser. Press Ctrl+C here to stop.
".venv\Scripts\python.exe" -m streamlit run app.py --server.address=127.0.0.1 --server.port=8501 --server.headless=true --browser.gatherUsageStats=false
