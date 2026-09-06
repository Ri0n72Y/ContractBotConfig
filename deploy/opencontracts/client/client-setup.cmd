@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0client-setup.ps1"
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" (
  echo.
  echo ContractBot setup failed. Error code: %EXITCODE%
  echo Keep this window open and send the error above to the administrator.
  pause
  exit /b %EXITCODE%
)
echo.
echo ContractBot setup completed successfully.
echo Restart WorkBuddy/CodeBuddy, then open this folder as the workspace.
pause
exit /b 0
