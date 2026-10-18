@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" -Install
if errorlevel 1 (
  echo.
  echo Setup failed. See docs\installation.md and docs\troubleshooting.md.
  pause
)
