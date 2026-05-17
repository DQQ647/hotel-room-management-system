@echo off
cd /d "%~dp0"
echo Starting Hotel Room Management System...
echo.
where python >nul 2>nul
if %errorlevel%==0 (
  python backend\app.py
) else (
  py -3 backend\app.py
)
pause
