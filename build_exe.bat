@echo off
setlocal

echo ============================
echo  Cognex XML Tool EXE Build
echo ============================
echo.

REM Always run from the folder containing this batch file.
pushd "%~dp0"

echo Installing/updating PyInstaller...
python -m pip install --upgrade pyinstaller
if errorlevel 1 (
    echo.
    echo Failed to install/update PyInstaller.
    popd
    popd
pause
    exit /b 1
)

echo.
echo Cleaning old build outputs...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "Cognex XML Tool.spec" del /q "Cognex XML Tool.spec"

echo.
echo Building standalone EXE...
python -m PyInstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --icon "assets\cognex_xml_tool.ico" ^
    --add-data "assets\cognex_xml_tool.ico;assets" ^
    --add-data "assets\cognex_xml_tool.png;assets" ^
    --name "Cognex XML Tool" ^
    cognex_xml_tool.py

if errorlevel 1 (
    echo.
    echo Build failed.
    popd
    popd
pause
    exit /b 1
)

echo.
echo Build complete.
echo EXE created at: dist\Cognex XML Tool.exe
echo.
popd
pause
