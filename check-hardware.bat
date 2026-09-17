@echo off
setlocal EnableExtensions
REM ==========================================================================
REM  AutoRefund - hardware check (camera, scale). Run with the devices plugged in.
REM  The kiosk agent owns the hardware, so this uses kiosk_agent\.env settings.
REM  Stop AutoRefund first (stop-autorefund.bat): only one program may use the
REM  camera and scale at a time. The barcode scanner is checked by scanning
REM  into Notepad (see README).
REM ==========================================================================

set "AGENT=%~dp0kiosk_agent"
set "PYEXE=%AGENT%\.venv\Scripts\python.exe"

if not exist "%PYEXE%" (
    echo [ERROR] Run setup-autorefund.bat first.
    pause
    exit /b 1
)

pushd "%AGENT%"
echo.
echo === Camera ===
"%PYEXE%" check_camera.py
echo.
echo === USB HID devices (look for your scale's VID/PID) ===
"%PYEXE%" test_scale.py --list
echo.
echo === Scale readings (put an item on the scale) ===
"%PYEXE%" test_scale.py
popd
echo.
pause
