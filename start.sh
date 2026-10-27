#!/usr/bin/env bash
# ==============================================================================
# Weibo Crawler - macOS / Linux 一键启动脚本 (start.sh)
# 用法:
#   ./start.sh              # 默认启动 Web 可视化控制台并自动打开浏览器 (http://127.0.0.1:15001)
#   ./start.sh --port 15002 # 指定端口启动 Web 控制台
#   ./start.sh --cli        # 直接以纯命令行模式运行爬虫 (python weibo.py)
# ==============================================================================

set -e

# 切换到脚本所在的项目根目录（支持从任意路径或 Finder 双击调用）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "======================================================="
echo "🚀 Weibo Crawler 一键启动工具 (macOS / Linux)"
echo "📂 工作目录: $SCRIPT_DIR"
echo "======================================================="

# 1. 自动初始化配置文件 config.json
if [ ! -f "config.json" ] && [ -f "config.json.example" ]; then
    echo "📝 未检测到 config.json，正在从 config.json.example 自动初始化..."
    cp config.json.example config.json
fi

# 2. 探测可用的 Python 解释器与虚拟环境
PYTHON_BIN=""
if [ -x ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
elif [ -x "venv/bin/python" ]; then
    PYTHON_BIN="venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "❌ 错误: 未检测到 Python 环境，请先安装 Python 3.8+ (https://www.python.org/)"
    exit 1
fi

echo "🐍 使用 Python 环境: $($PYTHON_BIN --version 2>&1) ($PYTHON_BIN)"

# 3. 检查核心依赖是否已安装，若缺失则自动创建虚拟环境并安装依赖
if ! "$PYTHON_BIN" -c "import flask, requests, json5, lxml" >/dev/null 2>&1; then
    echo "📦 检测到缺少运行依赖，正在准备虚拟环境并自动安装 requirements.txt..."
    if [ ! -d "venv" ] && [ ! -d ".venv" ]; then
        "$PYTHON_BIN" -m venv venv
        PYTHON_BIN="venv/bin/python"
    fi
    "$PYTHON_BIN" -m pip install --upgrade pip -q
    "$PYTHON_BIN" -m pip install -r requirements.txt
    echo "✅ 依赖安装完成！"
fi

# 4. 判断运行模式（--cli 运行纯命令行爬虫，默认启动 Web 控制台）
if [ "$1" = "--cli" ]; then
    shift
    echo "🕷️ 正在以 CLI 命令行模式启动爬虫 (weibo.py)..."
    exec "$PYTHON_BIN" weibo.py "$@"
else
    # 解析端口参数（默认 15001）
    PORT=15001
    ARGS=("$@")
    for ((i=0; i<${#ARGS[@]}; i++)); do
        if [ "${ARGS[$i]}" = "--port" ] && [ $((i+1)) -lt ${#ARGS[@]} ]; then
            PORT="${ARGS[$((i+1))]}"
        fi
    done

    # 后台延迟 1.5 秒自动打开默认浏览器
    (
        sleep 1.5
        URL="http://127.0.0.1:${PORT}"
        if command -v open >/dev/null 2>&1; then
            open "$URL" >/dev/null 2>&1 || true
        elif command -v xdg-open >/dev/null 2>&1; then
            xdg-open "$URL" >/dev/null 2>&1 || true
        fi
    ) &

    echo "🌐 正在启动 Web 可视化控制台 (停止服务请按 Ctrl + C)..."
    exec "$PYTHON_BIN" service.py "$@"
fi
