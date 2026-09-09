@echo off
chcp 65001 >nul
setlocal
REM ============================================================
REM  YOLOv8-Agent 小麦农业平台 —— 一键启动（局域网 + 公网 cpolar）
REM  启动逻辑在 run_ui.py（import wheat.app，不改框架代码）
REM  cpolar 客户端位于本目录 tools/cpolar/
REM ============================================================
cd /d "%~dp0"

REM ---- 1. 可选登录保护（公网暴露强烈建议开启）----
REM 取消下面两行注释并改成自己的账号密码：
REM set UI_AUTH_USER=admin
REM set UI_AUTH_PASS=请123456789

REM ---- 2. 若已配置 cpolar 隧道，后台拉起（公网访问用）----
set "CPOLAR=%~dp0tools\cpolar\bin"
where cpolar >nul 2>nul
if %errorlevel%==0 (
    start "cpolar" /min cmd /c "cpolar start hello-agents-7865"
    echo [cpolar] 已尝试启动隧道 hello-agents-7865
) else if exist "%CPOLAR%\cpolar.exe" (
    start "cpolar" /min cmd /c ""%CPOLAR%\cpolar.exe" start hello-agents-7865"
    echo [cpolar] 已尝试用本地客户端启动隧道 hello-agents-7865
) else (
    echo [cpolar] 未检测到 cpolar，跳过公网隧道（局域网访问不受影响）
)

REM ---- 3. 前台运行平台（run_ui.py 绑定 0.0.0.0）----
echo [app] 正在启动 http://0.0.0.0:7865 ...
"D:\pyhon\ana\ana3\python.exe" run_ui.py

echo.
echo 平台已退出。按任意键关闭窗口。
pause >nul
