@echo off
chcp 65001 >nul 2>&1
title MiMo API Proxy

REM ============================================================
REM   请在下面设置你的 MiMo API Key
REM   获取方式：登录 https://xiaomimimo.com 控制台，复制 Token Plan Key
REM   如果已经设置过环境变量 MIMO_API_KEY，这里可以留空
REM ============================================================
if "%MIMO_API_KEY%"=="" (
    set MIMO_API_KEY=
)

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found! Please install Python 3.8+
    echo Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

pip show flask >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing dependencies...
    pip install flask requests
)

echo [INFO] Starting MiMo API Proxy...
python mimo_proxy.py --port 1999
pause
