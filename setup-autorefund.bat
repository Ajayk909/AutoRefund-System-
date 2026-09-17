@echo off
setlocal EnableExtensions
REM ==========================================================================
REM  AutoRefund - one-time setup on Windows 10/11
REM  Installs the Core API (self_refund_backend), the Windows kiosk agent
REM  (kiosk_agent) and the kiosk UI (self_refund_frontend), and creates their
REM  .env files from the templates. Safe to run again.
REM ==========================================================================

set "ROOT=%~dp0"
set "BACKEND=%ROOT%self_refund_backend"
set "AGENT=%ROOT%kiosk_agent"
set "FRONTEND=%ROOT%self_refund_frontend"

echo.
echo === AutoRefund setup ===
echo.

REM ---- Python --------------------------------------------------------------
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo [ERROR] Python 3.11+ was not found.
    echo         Install it from https://www.python.org/downloads/windows/
    echo         and tick "Add python.exe to PATH".
    goto :fail
)
%PY% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
    echo [ERROR] Python 3.11 or newer is required.
    %PY% --version
    goto :fail
)
%PY% --version

REM ---- Node.js -------------------------------------------------------------
where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js was not found. Install the LTS version from https://nodejs.org/
    goto :fail
)
for /f "delims=" %%v in ('node --version') do echo Node.js %%v

REM ---- Old Raspberry Pi virtualenv -----------------------------------------
if exist "%BACKEND%\.venv\bin" if not exist "%BACKEND%\.venv\Scripts" (
    echo Found a Raspberry Pi/Linux virtual environment - renaming it to .venv-raspberrypi-old
    ren "%BACKEND%\.venv" ".venv-raspberrypi-old"
    if errorlevel 1 goto :fail
)

REM ---- Core API ------------------------------------------------------------
if not exist "%BACKEND%\.venv\Scripts\python.exe" (
    echo Creating Core API virtual environment...
    %PY% -m venv "%BACKEND%\.venv"
    if errorlevel 1 goto :fail
)
echo Installing Core API packages...
"%BACKEND%\.venv\Scripts\python.exe" -m pip install --upgrade pip
"%BACKEND%\.venv\Scripts\python.exe" -m pip install -r "%BACKEND%\requirements-dev.txt"
if errorlevel 1 goto :fail
if not exist "%BACKEND%\.env" (
    copy "%BACKEND%\.env.example" "%BACKEND%\.env" >nul
    echo Created self_refund_backend\.env - EDIT IT to set your database password.
) else (
    echo self_refund_backend\.env already exists - left unchanged.
)

REM ---- Kiosk agent ---------------------------------------------------------
if not exist "%AGENT%\.venv\Scripts\python.exe" (
    echo Creating kiosk agent virtual environment...
    %PY% -m venv "%AGENT%\.venv"
    if errorlevel 1 goto :fail
)
echo Installing kiosk agent packages...
"%AGENT%\.venv\Scripts\python.exe" -m pip install --upgrade pip
"%AGENT%\.venv\Scripts\python.exe" -m pip install -r "%AGENT%\requirements-dev.txt"
if errorlevel 1 goto :fail
if not exist "%AGENT%\.env" (
    copy "%AGENT%\.env.example" "%AGENT%\.env" >nul
    echo Created kiosk_agent\.env
    if exist "%BACKEND%\.env" (
        "%AGENT%\.venv\Scripts\python.exe" "%AGENT%\scripts\import_backend_settings.py" "%BACKEND%\.env" "%AGENT%\.env"
    )
) else (
    echo kiosk_agent\.env already exists - left unchanged.
)

REM ---- pyzbar runtime check (camera barcode decoding, kiosk agent) ---------
"%AGENT%\.venv\Scripts\python.exe" -c "import pyzbar.pyzbar" >nul 2>nul
if errorlevel 1 (
    echo.
    echo [WARNING] pyzbar could not load the ZBar DLL. Camera receipt scanning of
    echo           Code-128 barcodes needs the "Visual C++ Redistributable for
    echo           Visual Studio 2013 ^(x64^)" from Microsoft:
    echo           https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist
    echo           The handheld USB scanner works without it.
    echo.
)

REM ---- Frontend ------------------------------------------------------------
echo Installing frontend packages...
pushd "%FRONTEND%"
call npm ci
if errorlevel 1 (
    popd
    goto :fail
)
popd

echo.
echo === Setup complete ===
echo Next steps:
echo   1. Edit self_refund_backend\.env  (DATABASE_URL password)
echo   2. Run init-database.bat           (tables, demo data, kiosk agent key)
echo   3. Check kiosk_agent\.env          (camera / scale settings)
echo   4. Run check-hardware.bat          (camera / scale check)
echo   5. Run start-autorefund.bat
echo.
pause
exit /b 0

:fail
echo.
echo Setup did not finish. Fix the error above and run setup-autorefund.bat again.
pause
exit /b 1
