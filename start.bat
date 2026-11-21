@echo off
chcp 65001 >nul
rem Force Python UTF-8 mode so service.py emoji output survives redirected pipes (GBK consoles)
set "PYTHONUTF8=1"
setlocal enabledelayedexpansion

rem ==============================================================================
rem  Weibo Crawler - Windows one-click launcher (start.bat)
rem  Usage:
rem    start.bat              (default) start the web console on port 15001
rem    start.bat --port 15002 (specify the web console port)
rem    start.bat --cli        (run the crawler in CLI mode: python weibo.py)
rem
rem  NOTE: keep this file ASCII-only. A UTF-8 batch file with multibyte
rem  characters plus "chcp 65001" desyncs the cmd.exe parser and breaks
rem  execution ("'#' is not recognized", "... was unexpected at this time.").
rem ==============================================================================

title Weibo Crawler Web Console
cd /d "%~dp0"

echo =======================================================
echo  Weibo Crawler launcher (Windows)
echo  Work dir: %CD%
echo =======================================================

rem 1. Initialize config\config.json from the example if missing
if not exist "config\config.json" if not exist "config.json" (
    if exist "config\config.json.example" (
        echo [config] config\config.json not found, copying from config\config.json.example ...
        copy /y "config\config.json.example" "config\config.json" >nul
    )
)

rem 2. Detect a usable Python interpreter (prefer an existing venv)
set "PYTHON_BIN="
if exist ".venv\Scripts\python.exe" set "PYTHON_BIN=.venv\Scripts\python.exe"
if not defined PYTHON_BIN if exist "venv\Scripts\python.exe" set "PYTHON_BIN=venv\Scripts\python.exe"
if not defined PYTHON_BIN (
    where python >nul 2>nul && set "PYTHON_BIN=python"
)
if not defined PYTHON_BIN (
    where py >nul 2>nul && set "PYTHON_BIN=py -3"
)
if not defined PYTHON_BIN (
    echo [error] Python not found. Install Python 3.8+ with "Add Python to PATH" checked.
    echo         Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "delims=" %%v in ('!PYTHON_BIN! --version 2^>^&1') do set "PY_VER=%%v"
echo [python] Using !PY_VER!  (!PYTHON_BIN!)

rem 3. Ensure core dependencies are importable; install them if missing
!PYTHON_BIN! -c "import flask, requests, json5, lxml" >nul 2>nul
if !errorlevel! neq 0 (
    echo [deps] Missing dependencies; preparing the venv and installing requirements.txt ...
    if not exist "venv\Scripts\python.exe" if not exist ".venv\Scripts\python.exe" (
        !PYTHON_BIN! -m venv venv
        if exist "venv\Scripts\python.exe" (
            set "PYTHON_BIN=venv\Scripts\python.exe"
        )
    )
    !PYTHON_BIN! -m pip install --upgrade pip -q
    !PYTHON_BIN! -m pip install -r requirements.txt
    if !errorlevel! neq 0 (
        echo [error] Dependency installation failed. Check your network, or run:
        echo         pip install -r requirements.txt
        pause
        exit /b 1
    )
    echo [deps] Dependencies installed.
)

rem 4. Run mode: --cli runs the crawler CLI; default starts the web console
if "%~1"=="--cli" (
    echo [run] Starting the crawler in CLI mode: weibo.py ...
    !PYTHON_BIN! weibo.py
    pause
    exit /b 0
)

set "PORT=15001"
if "%~1"=="--port" (
    if not "%~2"=="" set "PORT=%~2"
)

echo [run] Starting web console: http://127.0.0.1:!PORT!
echo [hint] Keep this window open. Press Ctrl+C to stop the service.
start "" "http://127.0.0.1:!PORT!"
!PYTHON_BIN! service.py %*

pause
