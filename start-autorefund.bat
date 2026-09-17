@echo off
setlocal EnableExtensions
REM ==========================================================================
REM  AutoRefund - start the whole system on this Windows PC
REM
REM    start-autorefund.bat          production build of the UI + browser
REM    start-autorefund.bat kiosk    same, Microsoft Edge in full-screen kiosk mode
REM    start-autorefund.bat dev      Vite dev server with hot reload
REM
REM  Core API    : http://127.0.0.1:5000/api   (window "AutoRefund Backend")
REM  Kiosk agent : http://127.0.0.1:5100/api   (window "AutoRefund Kiosk Agent")
REM  Kiosk UI    : http://127.0.0.1:5173       (window "AutoRefund Frontend")
REM  Stop everything with stop-autorefund.bat
REM ==========================================================================

set "ROOT=%~dp0"
set "BACKEND=%ROOT%self_refund_backend"
set "AGENT=%ROOT%kiosk_agent"
set "FRONTEND=%ROOT%self_refund_frontend"
set "PYEXE=%BACKEND%\.venv\Scripts\python.exe"
set "AGENTPY=%AGENT%\.venv\Scripts\python.exe"
set "MODE=%~1"
set "URL=http://127.0.0.1:5173"

if not exist "%PYEXE%" (
    echo [ERROR] Run setup-autorefund.bat first.
    pause
    exit /b 1
)
if not exist "%AGENTPY%" (
    echo [ERROR] The kiosk agent is not installed. Run setup-autorefund.bat first.
    pause
    exit /b 1
)
if not exist "%BACKEND%\.env" (
    echo [ERROR] self_refund_backend\.env is missing. Run setup-autorefund.bat first.
    pause
    exit /b 1
)
if not exist "%AGENT%\.env" (
    echo [ERROR] kiosk_agent\.env is missing. Run setup-autorefund.bat first.
    pause
    exit /b 1
)
findstr /r /c:"^KIOSK_DEV_KEY=ardev_" "%AGENT%\.env" >nul
if errorlevel 1 (
    echo [WARNING] kiosk_agent\.env has no KIOSK_DEV_KEY. Customer returns will show
    echo           "This kiosk is not set up yet". Run init-database.bat and answer Y
    echo           to creating the kiosk agent key.
)

echo Starting AutoRefund Core API...
start "AutoRefund Backend" /D "%BACKEND%" cmd /k ""%PYEXE%" run.py"
call :wait_for http://127.0.0.1:5000/api/health "Core API" "AutoRefund Backend" "self_refund_backend\logs\autorefund.log" || exit /b 1

echo Starting kiosk agent...
start "AutoRefund Kiosk Agent" /D "%AGENT%" cmd /k ""%AGENTPY%" run_agent.py"
call :wait_for http://127.0.0.1:5100/api/health "Kiosk agent" "AutoRefund Kiosk Agent" "kiosk_agent\logs\kiosk-agent.log" || exit /b 1

if /i "%MODE%"=="dev" (
    start "AutoRefund Frontend" /D "%FRONTEND%" cmd /k "npm run dev"
) else (
    echo Building the kiosk UI...
    pushd "%FRONTEND%"
    call npm run build
    if errorlevel 1 (
        popd
        echo [ERROR] Frontend build failed.
        pause
        exit /b 1
    )
    popd
    start "AutoRefund Frontend" /D "%FRONTEND%" cmd /k "npm run preview"
)
call :wait_for %URL% "Kiosk UI" "AutoRefund Frontend" "the window" || exit /b 1

if /i "%MODE%"=="kiosk" (
    start "" msedge --kiosk %URL% --edge-kiosk-type=fullscreen --no-first-run
) else (
    start "" %URL%
)
echo AutoRefund is running at %URL%
exit /b 0

:wait_for
echo Waiting for %~2...
set /a TRIES=0
:wait_loop
set /a TRIES+=1
curl.exe -s -o nul -f %~1 && (
    echo %~2 is running.
    exit /b 0
)
if %TRIES% GEQ 30 (
    echo [ERROR] %~2 did not start within 30 seconds. Check the "%~3" window
    echo         and %~4
    pause
    exit /b 1
)
timeout /t 1 /nobreak >nul
goto :wait_loop
