#!/bin/bash
set -e

echo "==============================="
echo "  梗导师 · 启动脚本 (Mac/Linux)"
echo "==============================="

# 检查 Python
if ! command -v python3 &>/dev/null; then
    echo ""
    echo "❌ 未找到 Python3，请先安装 Python（https://www.python.org/downloads/）"
    exit 1
fi

PYTHON=$(command -v python3)
echo "✅ 使用 Python: $($PYTHON --version)"

# 创建虚拟环境（如果不存在）
if [ ! -d ".venv" ]; then
    echo ""
    echo "📦 正在创建虚拟环境..."
    $PYTHON -m venv .venv
fi

# 激活虚拟环境
source .venv/bin/activate

# 安装依赖
echo ""
echo "📥 正在安装依赖（首次运行需要几分钟）..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo ""
echo "🚀 启动应用..."
echo "   浏览器访问: http://127.0.0.1:8000"
echo "   按 Ctrl+C 停止"
echo ""

python main.py
