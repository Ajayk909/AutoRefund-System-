@echo off
REM Stops the backend and frontend windows opened by start-autorefund.bat
taskkill /FI "WINDOWTITLE eq AutoRefund Backend*" /T /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq AutoRefund Frontend*" /T /F >nul 2>nul
echo AutoRefund stopped.
