#!/bin/bash
# 剪映 AI 剪辑技能 — Linux 部署脚本
# 用法: bash deploy.sh

set -e

echo "======================================"
echo "  剪映 AI 剪辑技能 — 部署"
echo "======================================"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 检查 Python
if ! command -v python3 &>/dev/null; then
    echo "[错误] 未找到 python3，请先安装 Python 3.10+"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "[OK] Python $PYTHON_VERSION"

# 检查 FFmpeg
if ! command -v ffmpeg &>/dev/null; then
    echo "[警告] 未找到 ffmpeg，字幕功能可能不可用"
    echo "  安装: sudo apt install ffmpeg 或 sudo yum install ffmpeg"
else
    echo "[OK] FFmpeg $(ffmpeg -version 2>&1 | head -1 | awk '{print $3}')"
fi

# 安装依赖
echo ""
echo "[1/3] 安装 Python 依赖..."
pip3 install -q -r requirements.txt
echo "[OK] 依赖安装完成"

# 检查环境变量
echo ""
echo "[2/3] 检查环境变量..."
if [ -f .env ]; then
    source .env 2>/dev/null || true
fi

if [ -z "$DOUBAO_API_KEY" ] || [[ "$DOUBAO_API_KEY" == your-* ]]; then
    echo "[警告] DOUBAO_API_KEY 未配置"
    echo "  请设置: export DOUBAO_API_KEY=你的API Key"
    echo "  或在 .env 文件中配置"
else
    echo "[OK] DOUBAO_API_KEY 已配置"
fi

# 启动服务
echo ""
echo "[3/3] 启动服务..."
echo ""
echo "======================================"
echo "  剪映 AI 剪辑技能服务"
echo "  地址: http://0.0.0.0:9800"
echo "  文档: http://0.0.0.0:9800/docs"
echo "======================================"
echo ""

export PYTHONIOENCODING=utf-8
python3 server.py
