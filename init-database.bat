@echo off
setlocal EnableExtensions
REM ==========================================================================
REM  AutoRefund - database initialisation (PostgreSQL on Windows)
REM   1. optionally creates the refund_user login and refund_kiosk database
REM   2. applies the Alembic migrations (creates / updates tables)
REM   3. optionally loads the demo data (DELETES existing data)
REM   4. optionally creates the kiosk agent's development key
REM ==========================================================================
set "ROOT=%~dp0"
set "BACKEND=%ROOT%self_refund_backend"
set "PYEXE=%BACKEND%\.venv\Scripts\python.exe"

if not exist "%PYEXE%" (
    echo [ERROR] Run setup-autorefund.bat first.
    goto :fail
)
if not exist "%BACKEND%\.env" (
    echo [ERROR] self_refund_backend\.env is missing. Run setup-autorefund.bat first.
    goto :fail
)

echo.
set "CREATE="
set /p CREATE="Create the database user and database now? (needs the PostgreSQL 'postgres' password) [y/N]: "
if /i "%CREATE%"=="y" call :create_db || goto :fail

echo.
echo Applying database migrations...
pushd "%BACKEND%"
"%PYEXE%" -m alembic upgrade head
if errorlevel 1 (
    popd
    echo [ERROR] Migration failed. Check DATABASE_URL in self_refund_backend\.env
    echo         and that the PostgreSQL service is running.
    goto :fail
)

echo.
set "SEED="
set /p SEED="Load DEMO data? This DELETES all existing refunds/receipts/products/staff [y/N]: "
if /i "%SEED%"=="y" "%PYEXE%" seed.py

echo.
echo The kiosk agent needs a DEVELOPMENT key to talk to the Core API.
set "MAKEKEY="
set /p MAKEKEY="Create a kiosk agent key now and save it in kiosk_agent\.env? [Y/n]: "
if /i not "%MAKEKEY%"=="n" call :make_key
popd

echo.
echo Database ready.
pause
exit /b 0

:make_key
if not exist "%ROOT%kiosk_agent\.env" (
    echo [WARNING] kiosk_agent\.env is missing - run setup-autorefund.bat, then this again.
    exit /b 0
)
set "KIOSKCODE="
set /p KIOSKCODE="Kiosk code [KIOSK-001]: "
if "%KIOSKCODE%"=="" set "KIOSKCODE=KIOSK-001"
"%PYEXE%" manage_tenancy.py issue-dev-key %KIOSKCODE% --write-env "%ROOT%kiosk_agent\.env"
if errorlevel 1 (
    echo [WARNING] Could not create the key. List kiosks with:  .venv\Scripts\python manage_tenancy.py list
)
exit /b 0

:create_db
set "PSQL="
where psql >nul 2>nul && set "PSQL=psql"
if not defined PSQL (
    for /d %%d in ("%ProgramFiles%\PostgreSQL\*") do if exist "%%d\bin\psql.exe" set "PSQL=%%d\bin\psql.exe"
)
if not defined PSQL (
    echo [ERROR] psql.exe not found. Install PostgreSQL from https://www.postgresql.org/download/windows/
    exit /b 1
)
set "DBPASS="
set /p DBPASS="Choose a password for refund_user (must match DATABASE_URL in .env): "
if "%DBPASS%"=="" (
    echo [ERROR] Password cannot be empty.
    exit /b 1
)
echo You will be asked for the password of the PostgreSQL 'postgres' superuser.
"%PSQL%" -U postgres -h localhost -v ON_ERROR_STOP=1 -v db_password="%DBPASS%" -f "%BACKEND%\scripts\create_database.sql"
exit /b %errorlevel%

:fail
pause
exit /b 1
