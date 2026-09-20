@echo off
cd /d "%~dp0"

echo =============================================
echo   Invoice Tool - First Time Setup
echo =============================================
echo.
echo Please wait while the required components are installed.
echo (This window will close automatically when done.)
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    set PYCMD=py
    goto :found
)

where python >nul 2>nul
if %errorlevel%==0 (
    set PYCMD=python
    goto :found
)

echo.
echo [ERROR] Python was not found on this computer.
echo Please open "setup_guide.txt" and follow step 1 (Install Python) first.
echo.
pause
exit /b 1

:found
echo Found Python (%PYCMD%). Continuing setup...
echo.

set PYTHONIOENCODING=utf-8
%PYCMD% -m pip install --upgrade pip >nul 2>nul
%PYCMD% -m pip install -r "%~dp0requirements.txt"

if errorlevel 1 (
    echo.
    echo [ERROR] Something went wrong while installing required files.
    echo Please check your internet connection, then double-click
    echo "01_setup.bat" again to retry.
    echo.
    pause
    exit /b 1
)

echo.
echo Creating a shortcut on your Desktop...
cscript //nologo "%~dp0create_shortcut.vbs" "%~dp0" >nul 2>nul

echo.
echo =============================================
echo   Setup complete!
echo =============================================
echo.
echo A shortcut icon has been added to your Desktop.
echo From now on, just double-click that icon to open the tool.
echo (If you can't find it, double-click "02_start_invoice_tool.bat"
echo  in this folder instead.)
echo.
pause
