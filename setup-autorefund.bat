@echo off
setlocal EnableExtensions
REM ==========================================================================
REM  AutoRefund - one-time setup on Windows 10/11
REM  Creates the Python virtual environment, installs backend and frontend
REM  dependencies and creates self_refund_backend\.env from the template.
REM  Safe to run again (it only installs/updates packages).
REM ==========================================================================
set "ROOT=%~dp0"
set "BACKEND=%ROOT%self_refund_backend"
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
REM A Linux venv (bin\ instead of Scripts\) cannot be used on Windows.
REM It is renamed, never deleted.
if exist "%BACKEND%\.venv\bin" if not exist "%BACKEND%\.venv\Scripts" (
    echo Found a Raspberry Pi/Linux virtual environment - renaming it to .venv-raspberrypi-old
    ren "%BACKEND%\.venv" ".venv-raspberrypi-old"
    if errorlevel 1 goto :fail
)

REM ---- Backend -------------------------------------------------------------
if not exist "%BACKEND%\.venv\Scripts\python.exe" (
    echo Creating Python virtual environment...
    %PY% -m venv "%BACKEND%\.venv"
    if errorlevel 1 goto :fail
)
echo Installing backend packages...
"%BACKEND%\.venv\Scripts\python.exe" -m pip install --upgrade pip
"%BACKEND%\.venv\Scripts\python.exe" -m pip install -r "%BACKEND%\requirements-dev.txt"
if errorlevel 1 goto :fail

if not exist "%BACKEND%\.env" (
    copy "%BACKEND%\.env.example" "%BACKEND%\.env" >nul
    echo Created self_refund_backend\.env - EDIT IT to set your database password.
) else (
    echo self_refund_backend\.env already exists - left unchanged.
)

REM ---- pyzbar runtime check ------------------------------------------------
"%BACKEND%\.venv\Scripts\python.exe" -c "import pyzbar.pyzbar" >nul 2>nul
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
echo   1. Edit self_refund_backend\.env  (DATABASE_URL password, hardware settings)
echo   2. Run init-database.bat           (creates tables, optional demo data)
echo   3. Run check-hardware.bat          (camera / scale check)
echo   4. Run start-autorefund.bat
echo.
pause
exit /b 0

:fail
echo.
echo Setup did not finish. Fix the error above and run setup-autorefund.bat again.
pause
exit /b 1
