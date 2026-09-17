@echo off
setlocal EnableExtensions
REM ==========================================================================
REM  AutoRefund - hardware check (camera, scale). Run with the devices plugged in.
REM  The barcode scanner is checked by scanning into Notepad (see README).
REM ==========================================================================
set "BACKEND=%~dp0self_refund_backend"
set "PYEXE=%BACKEND%\.venv\Scripts\python.exe"
if not exist "%PYEXE%" (
    echo [ERROR] Run setup-autorefund.bat first.
    pause
    exit /b 1
)
pushd "%BACKEND%"
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
