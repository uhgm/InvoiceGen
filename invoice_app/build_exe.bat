@echo off
REM Windows用exeを作るスクリプト（開発者専用。母上は使いません）。
REM
REM ★これはWindows（64bit）実機で実行してください★
REM PyInstallerはクロスコンパイルできない（Windows用exeはWindows上でしか作れない）ため、
REM このWSL/Linux環境ではexeを作れません。build_deb.sh（Linux用）と役割を分けています。
REM
REM 使い方： このファイルをダブルクリック、またはコマンドプロンプトで
REM     build_exe.bat
REM を実行してください。
REM 実行すると dist\invoice-generator-tool\ フォルダの中に
REM invoice-generator-tool.exe が作られます（そのフォルダごと配布してください）。
cd /d "%~dp0"

echo =============================================
echo   Windows用 exe ビルド
echo =============================================
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
echo [ERROR] Python が見つかりませんでした。setup_guide.txt の手順2を先に行ってください。
pause
exit /b 1

:found
echo [1/3] ビルド専用の仮想環境を用意しています（.build-venv）...
if not exist ".build-venv" (
    %PYCMD% -m venv .build-venv
)
".build-venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".build-venv\Scripts\pip.exe" install -r requirements.txt pyinstaller
if errorlevel 1 (
    echo [ERROR] 必要なファイルのインストールに失敗しました。
    pause
    exit /b 1
)

echo [2/3] PyInstallerでexeを作成しています...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del /q invoice-generator-tool.spec 2>nul
".build-venv\Scripts\pyinstaller.exe" --name invoice-generator-tool --onedir --windowed --add-data "assets;assets" invoice_generator.py
if errorlevel 1 (
    echo [ERROR] ビルドに失敗しました。
    pause
    exit /b 1
)

echo [3/3] 完了
echo.
echo =============================================
echo   ビルド完了！
echo =============================================
echo.
echo dist\invoice-generator-tool\ フォルダの中に
echo invoice-generator-tool.exe ができました。
echo このフォルダごと（中身をバラさずに）配布してください。
echo.
pause
