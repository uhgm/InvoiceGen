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
REM invoice-generator-tool.exe が作られます。
REM Inno Setup 6 が入っていれば、配布用のインストーラー
REM dist\invoice-generator-tool-windows-setup.exe も作ります（installer.iss）。
REM ふだんは GitHub Actions が自動で作るので、このファイルは手で作りたいとき用です。
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
echo [1/4] ビルド専用の仮想環境を用意しています（.build-venv）...
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

echo [2/4] PyInstallerでexeを作成しています...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del /q invoice-generator-tool.spec 2>nul
".build-venv\Scripts\pyinstaller.exe" --name invoice-generator-tool --onedir --windowed --add-data "assets;assets" invoice_generator.py
if errorlevel 1 (
    echo [ERROR] ビルドに失敗しました。
    pause
    exit /b 1
)

echo [3/4] インストーラーを作っています（Inno Setup 6 が入っている場合だけ）...
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
    echo   Inno Setup 6 が見つからないので、インストーラーは作りません（exeだけ作りました）。
    goto :done
)
for /f "usebackq delims=" %%v in (`".build-venv\Scripts\python.exe" -c "import app_common; print(app_common.APP_VERSION_NUM)"`) do set "APPVER=%%v"
"%ISCC%" /DAppVersion=%APPVER% installer.iss
if errorlevel 1 (
    echo [ERROR] インストーラーの作成に失敗しました。
    pause
    exit /b 1
)

:done
echo [4/4] 完了
echo.
echo =============================================
echo   ビルド完了！
echo =============================================
echo.
echo dist\invoice-generator-tool\ フォルダの中に
echo invoice-generator-tool.exe ができました。
echo Inno Setup 6 があれば、dist\invoice-generator-tool-windows-setup.exe
echo （配布用のインストーラー）もできています。
echo.
pause
