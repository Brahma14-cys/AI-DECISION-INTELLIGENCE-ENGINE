@echo off
setlocal
cd /d "%~dp0"
echo Starting AI Legal Decision Intelligence Engine...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
endlocal
