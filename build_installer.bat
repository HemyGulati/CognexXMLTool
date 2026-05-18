@echo off
setlocal

echo =================================
echo  Cognex XML Tool Installer Build
echo =================================
echo.

REM Always run from the folder containing this batch file.
REM This avoids relative path issues when the file is launched from Explorer,
REM PowerShell, Command Prompt, or another working directory.
pushd "%~dp0"

call "%~dp0build_exe.bat"
if errorlevel 1 (
    echo.
    echo EXE build failed. Installer build stopped.
    popd
    pause
    exit /b 1
)

echo.
echo Looking for Inno Setup compiler...
set "ISCC="

where iscc >nul 2>nul
if not errorlevel 1 set "ISCC=iscc"

if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"

if not defined ISCC (
    echo.
    echo Inno Setup was not found.
    echo Checked:
    echo   %ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
    echo   %ProgramFiles%\Inno Setup 6\ISCC.exe
    echo   %LocalAppData%\Programs\Inno Setup 6\ISCC.exe
    echo.
    echo Install Inno Setup 6, then run this file again:
    echo https://jrsoftware.org/isinfo.php
    echo.
    popd
    pause
    exit /b 1
)

echo Found Inno Setup compiler:
echo %ISCC%
echo.

if not exist "%~dp0installer_output" mkdir "%~dp0installer_output"

echo Building installer...
"%ISCC%" /O"%~dp0installer_output" "%~dp0installer\CognexXMLTool.iss"
if errorlevel 1 (
    echo.
    echo Installer build failed. Scroll up and check the Inno Setup error message above.
    echo Common causes are missing dist\Cognex XML Tool.exe or a missing LICENSE.txt file.
    popd
    pause
    exit /b 1
)

echo.
echo Installer build complete.
echo Installer created in:
echo %~dp0installer_output
echo.
popd
pause
