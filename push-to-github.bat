@echo off
setlocal EnableExtensions
REM ==========================================================================
REM  Publish this folder to https://github.com/Ajayk909/AutoRefund-System-
REM
REM  Uses autorefund-migration.bundle (the prepared migration commits) to turn
REM  this folder into a Git repository WITHOUT changing any files in it, then
REM  pushes to GitHub. Never force-pushes. Requires Git for Windows.
REM ==========================================================================
set "REMOTE=https://github.com/Ajayk909/AutoRefund-System-.git"
set "BUNDLE=%~dp0autorefund-migration.bundle"
cd /d "%~dp0"

where git >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Git is not installed. Get it from https://git-scm.com/download/win
    goto :fail
)

if not exist ".git" (
    if not exist "%BUNDLE%" (
        echo [ERROR] %BUNDLE% not found.
        goto :fail
    )
    git bundle verify "%BUNDLE%" || goto :fail
    git init -b main || goto :fail
    git fetch "%BUNDLE%" main || goto :fail
    REM Point main at the migration commit; keeps the files on disk as they are.
    git reset --mixed FETCH_HEAD || goto :fail
)

git remote get-url origin >nul 2>nul
if errorlevel 1 git remote add origin %REMOTE%

echo.
echo Checking GitHub (a sign-in window may appear)...
git fetch origin || goto :fail

git merge-base --is-ancestor origin/main HEAD
if errorlevel 1 (
    echo.
    echo [STOP] GitHub has commits that are not in this folder. Nothing was pushed.
    echo        Review them with:  git log HEAD..origin/main
    echo        then merge them:   git merge origin/main
    goto :fail
)

echo.
echo Files that differ from the prepared commit ^(should be empty or only your own edits^):
git status --short
echo.
echo Commits that will be pushed:
git log --oneline origin/main..HEAD
echo.
set "OK="
set /p OK="Push these commits to GitHub now? [y/N]: "
if /i not "%OK%"=="y" goto :fail

git push -u origin main || goto :fail
echo.
echo Pushed. You can delete autorefund-migration.bundle now.
pause
exit /b 0

:fail
echo.
pause
exit /b 1
