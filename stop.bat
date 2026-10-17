@echo off
setlocal
cd /d "%~dp0"
echo Stopping all AI Legal Engine services...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1" %*
endlocal
