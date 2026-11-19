@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo [거래잇수다 설치] 가상환경을 만들고 필요한 패키지를 설치합니다. 인터넷이 필요하며 3~5분 걸립니다.
if not exist ".venv\Scripts\python.exe" (
    py -3.11 -m venv .venv >nul 2>&1
    if not exist ".venv\Scripts\python.exe" python -m venv .venv >nul 2>&1
)
if not exist ".venv\Scripts\python.exe" goto no_python
".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 goto old_python
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto pip_failed
if not exist ".env" copy /b ".env.example" ".env" >nul
echo.
echo 설치가 끝났습니다.
echo 다음: import_data.bat 실행(상가 데이터 가져오기, 약 10초) → run.bat 실행 → 브라우저에서 http://localhost:8501
pause
exit /b 0

:no_python
echo.
echo [설치 실패] Python 3.11을 찾지 못했습니다.
echo  1) https://www.python.org/downloads/ 에서 Python 3.11(Windows installer 64-bit)을 내려받아 설치하세요.
echo  2) 설치 첫 화면에서 "Add python.exe to PATH"에 체크하세요.
echo  3) 설치가 끝나면 이 setup.bat을 다시 실행하세요.
pause
exit /b 1

:old_python
echo.
echo [설치 실패] Python 3.11 이상이 필요합니다. 지금 찾은 Python은 더 낮은 버전입니다.
echo  python.org에서 Python 3.11을 설치한 뒤, 이 폴더의 .venv 폴더를 지우고 setup.bat을 다시 실행하세요.
pause
exit /b 1

:pip_failed
echo.
echo [설치 실패] 패키지를 내려받지 못했습니다. 인터넷 연결을 확인한 뒤 setup.bat을 다시 실행하세요.
echo  학교·기관 네트워크라 막혔다면 관리자에게 pypi.org 접속을 요청하세요.
pause
exit /b 1
