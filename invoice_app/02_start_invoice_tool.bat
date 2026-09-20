@echo off
cd /d "%~dp0"

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0invoice_generator.py"
    exit /b 0
)

where py >nul 2>nul
if %errorlevel%==0 (
    start "" py -w "%~dp0invoice_generator.py" 2>nul
    if %errorlevel%==0 exit /b 0
    py "%~dp0invoice_generator.py"
    exit /b 0
)

where python >nul 2>nul
if %errorlevel%==0 (
    python "%~dp0invoice_generator.py"
    exit /b 0
)

echo.
echo [ERROR] Setup has not been completed yet.
echo Please double-click "01_setup.bat" first.
echo.
pause
