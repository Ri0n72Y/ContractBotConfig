@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0client-setup.ps1"
if errorlevel 1 (
  echo.
  echo ContractBot installation failed.
  pause
)
endlocal
