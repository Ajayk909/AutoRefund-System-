@echo off
setlocal EnableExtensions
REM ==========================================================================
REM  AutoRefund - start the whole system on this Windows PC
REM
REM    start-autorefund.bat          production build of the UI + browser
REM    start-autorefund.bat kiosk    same, Microsoft Edge in full-screen kiosk mode
REM    start-autorefund.bat dev      Vite dev server with hot reload
REM
REM  Backend  : http://127.0.0.1:5000/api   (window "AutoRefund Backend")
REM  Frontend : http://127.0.0.1:5173       (window "AutoRefund Frontend")
REM  Stop everything with stop-autorefund.bat
REM ==========================================================================
set "ROOT=%~dp0"
set "BACKEND=%ROOT%self_refund_backend"
set "FRONTEND=%ROOT%self_refund_frontend"
set "PYEXE=%BACKEND%\.venv\Scripts\python.exe"
set "MODE=%~1"
set "URL=http://127.0.0.1:5173"

if not exist "%PYEXE%" (
    echo [ERROR] Run setup-autorefund.bat first.
    pause
    exit /b 1
)
if not exist "%BACKEND%\.env" (
    echo [ERROR] self_refund_backend\.env is missing. Run setup-autorefund.bat first.
    pause
    exit /b 1
)

echo Starting AutoRefund backend...
start "AutoRefund Backend" /D "%BACKEND%" cmd /k ""%PYEXE%" run.py"

echo Waiting for the backend to respond...
set /a TRIES=0
:wait_backend
set /a TRIES+=1
curl.exe -s -o nul -f http://127.0.0.1:5000/api/health && goto :backend_up
if %TRIES% GEQ 30 (
    echo [ERROR] Backend did not start within 30 seconds. Check the "AutoRefund Backend" window
    echo         and self_refund_backend\logs\autorefund.log
    pause
    exit /b 1
)
timeout /t 1 /nobreak >nul
goto :wait_backend
:backend_up
echo Backend is running.

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

echo Waiting for the frontend...
set /a TRIES=0
:wait_frontend
set /a TRIES+=1
curl.exe -s -o nul -f %URL% && goto :frontend_up
if %TRIES% GEQ 30 (
    echo [ERROR] Frontend did not start. Check the "AutoRefund Frontend" window.
    pause
    exit /b 1
)
timeout /t 1 /nobreak >nul
goto :wait_frontend
:frontend_up

if /i "%MODE%"=="kiosk" (
    start "" msedge --kiosk %URL% --edge-kiosk-type=fullscreen --no-first-run
) else (
    start "" %URL%
)
echo AutoRefund is running at %URL%
exit /b 0
