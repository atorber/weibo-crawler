@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: ==============================================================================
:: Weibo Crawler - Windows 一键启动脚本 (start.bat)
:: 用法:
::   双击 start.bat          # 默认启动 Web 可视化控制台并自动打开浏览器 (http://127.0.0.1:15001)
::   start.bat --port 15002  # 指定端口启动 Web 控制台
::   start.bat --cli         # 直接以纯命令行模式运行爬虫 (python weibo.py)
:: ==============================================================================

title Weibo Crawler Web Console
cd /d "%~dp0"

echo =======================================================
echo 🚀 Weibo Crawler 一键启动工具 (Windows)
echo 📂 工作目录: %CD%
echo =======================================================

:: 1. 自动初始化配置文件 config.json
if not exist "config.json" (
    if exist "config.json.example" (
        echo 📝 未检测到 config.json，正在从 config.json.example 自动初始化...
        copy /y "config.json.example" "config.json" >nul
    )
)

:: 2. 探测可用的 Python 解释器与虚拟环境
set "PYTHON_BIN="
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_BIN=.venv\Scripts\python.exe"
) else if exist "venv\Scripts\python.exe" (
    set "PYTHON_BIN=venv\Scripts\python.exe"
) else (
    where python >nul 2>nul
    if !errorlevel! equ 0 (
        set "PYTHON_BIN=python"
    ) else (
        where py >nul 2>nul
        if !errorlevel! equ 0 (
            set "PYTHON_BIN=py -3"
        )
    )
)

if "!PYTHON_BIN!"=="" (
    echo ❌ 错误: 未检测到 Python 环境，请先安装 Python 3.8+ 并勾选 "Add Python to PATH"
    echo 🔗 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "delims=" %%v in ('!PYTHON_BIN! --version 2^>^&1') do set "PY_VER=%%v"
echo 🐍 使用 Python 环境: !PY_VER! (!PYTHON_BIN!)

:: 3. 检查核心依赖是否已安装，若缺失则自动创建虚拟环境并安装依赖
!PYTHON_BIN! -c "import flask, requests, json5, lxml" >nul 2>nul
if !errorlevel! neq 0 (
    echo 📦 检测到缺少运行依赖，正在准备虚拟环境并自动安装 requirements.txt...
    if not exist "venv\Scripts\python.exe" if not exist ".venv\Scripts\python.exe" (
        !PYTHON_BIN! -m venv venv
        if exist "venv\Scripts\python.exe" (
            set "PYTHON_BIN=venv\Scripts\python.exe"
        )
    )
    !PYTHON_BIN! -m pip install --upgrade pip -q
    !PYTHON_BIN! -m pip install -r requirements.txt
    if !errorlevel! neq 0 (
        echo ❌ 依赖安装失败，请检查网络连接或手动执行 pip install -r requirements.txt
        pause
        exit /b 1
    )
    echo ✅ 依赖安装完成！
)

:: 4. 判断运行模式（--cli 运行纯命令行爬虫，默认启动 Web 控制台）
if "%~1"=="--cli" (
    echo 🕷️ 正在以 CLI 命令行模式启动爬虫 (weibo.py)...
    !PYTHON_BIN! weibo.py
    pause
    exit /b 0
)

set "PORT=15001"
if "%~1"=="--port" (
    if not "%~2"=="" set "PORT=%~2"
)

echo 🌐 正在启动 Web 可视化控制台: http://127.0.0.1:!PORT!
echo 💡 提示: 保持此窗口开启，按 Ctrl + C 可停止服务
start "" "http://127.0.0.1:!PORT!"
!PYTHON_BIN! service.py %*

pause
