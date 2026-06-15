@echo off
chcp 65001 >nul
echo ===============================
echo   梗导师 · 启动脚本 (Windows)
echo ===============================

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo 未找到 Python，请先安装 Python（https://www.python.org/downloads/）
    echo 安装时记得勾选 "Add Python to PATH"
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do echo 使用 %%i

:: 创建虚拟环境（如果不存在）
if not exist ".venv" (
    echo.
    echo 正在创建虚拟环境...
    python -m venv .venv
)

:: 激活虚拟环境
call .venv\Scripts\activate.bat

:: 安装依赖
echo.
echo 正在安装依赖（首次运行需要几分钟）...
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo.
echo 启动应用...
echo 浏览器访问: http://127.0.0.1:8000
echo 按 Ctrl+C 停止
echo.

python main.py

pause
