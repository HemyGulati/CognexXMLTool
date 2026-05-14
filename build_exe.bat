@echo off
setlocal

REM Cognex XML Tool - Windows EXE build script
REM Author: Hemy Gulati
REM
REM This script creates a standalone Windows executable using PyInstaller.
REM Output file:
REM     dist\Cognex XML Tool.exe

cd /d "%~dp0"

echo.
echo ============================
echo  Cognex XML Tool EXE Build
echo ============================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo Python was not found. Install Python 3.10+ and tick "Add Python to PATH".
    pause
    exit /b 1
)

REM Clean previous build outputs so the new EXE is built from the current source.
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "Cognex XML Tool.spec" del /q "Cognex XML Tool.spec"


echo Installing/updating PyInstaller...
python -m pip install --upgrade pyinstaller
if errorlevel 1 (
    echo Failed to install PyInstaller.
    pause
    exit /b 1
)

echo.
echo Building standalone EXE...
python -m PyInstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name "Cognex XML Tool" ^
    cognex_xml_tool.py

if errorlevel 1 (
    echo.
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo Build complete:
echo dist\Cognex XML Tool.exe
echo.
echo The app will auto-load cognex_xml_tool_config.json from the same folder as the EXE if that file exists.
echo.
pause
