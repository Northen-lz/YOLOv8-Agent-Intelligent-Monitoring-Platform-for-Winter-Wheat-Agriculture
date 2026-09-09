@echo off
chcp 65001 >nul
title 爪案 · 猫狗品牌全案策划台
cd /d "%~dp0"

REM ---- 1. 可选登录保护（公网暴露强烈建议开启）----
REM 取消下面两行注释并改成自己的账号密码：
REM set UI_AUTH_USER=admin
REM set UI_AUTH_PASS=改成强密码

REM ---- 2. 启动平台（默认 http://127.0.0.1:7866）----
"D:\pyhon\ana\ana3\python.exe" run_ui.py
pause
