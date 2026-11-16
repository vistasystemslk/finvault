@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1"
if errorlevel 1 goto failed
if not exist "dist\FinVault.exe" goto failed
echo.
echo Build complete: dist\FinVault.exe
pause
exit /b 0

:failed
echo.
echo Build failed. See the messages above for the cause.
pause
exit /b 1
