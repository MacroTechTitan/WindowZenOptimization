@echo off
setlocal enabledelayedexpansion
echo ============================================
echo  MTT Windows Infinite Optimizer - Build Script
echo ============================================
echo.

echo [1/6] Reading version from version.json...
REM No pipe in the command below on purpose: a '|' inside for /f backticks
REM gets eaten by cmd before PowerShell ever sees it.
for /f "usebackq delims=" %%v in (`powershell -NoProfile -Command "(ConvertFrom-Json (Get-Content -Raw version.json)).version"`) do set APPVERSION=%%v
if "%APPVERSION%"=="" (
    echo ERROR: Could not read the version from version.json.
    pause
    exit /b 1
)
echo    Version: %APPVERSION%
set SETUPNAME=MTT_InfiniteOptimizer_Setup_v%APPVERSION%.exe
echo    Installer will be: %SETUPNAME%
echo.

echo [2/6] Installing Python dependencies...
pip install flask psutil apscheduler pywebview pyinstaller
echo.

echo [3/6] Building executable with PyInstaller...
pyinstaller --noconfirm --onedir --windowed ^
    --uac-admin ^
    --name "MTT Windows Infinite Optimizer" ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    --add-data "settings.json;." ^
    --add-data "version.json;." ^
    --hidden-import "apscheduler.triggers.cron" ^
    --hidden-import "apscheduler.schedulers.background" ^
    --hidden-import "apscheduler.triggers.interval" ^
    --hidden-import "apscheduler.triggers.date" ^
    --hidden-import "webview" ^
    --exclude-module "resend" ^
    --exclude-module "httpx" ^
    --exclude-module "anyio" ^
    desktop_launcher.py
echo.

if not exist "dist\MTT Windows Infinite Optimizer\MTT Windows Infinite Optimizer.exe" (
    echo ERROR: PyInstaller build failed. Check the output above for errors.
    pause
    exit /b 1
)

echo [4/6] PyInstaller Build complete!
echo    Output: dist\MTT Windows Infinite Optimizer\
echo.

REM ===========================================================================
REM TODO CODE-SIGNING (post EV certificate) - sign the APPLICATION EXE here.
REM Must run AFTER PyInstaller and BEFORE makensis, so the signed exe is the
REM one packaged into the installer.
REM
REM   signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 ^
REM       /n "Macro Tech Titan" ^
REM       "dist\MTT Windows Infinite Optimizer\MTT Windows Infinite Optimizer.exe"
REM   if %errorlevel% neq 0 ( echo ERROR: app exe signing failed & pause & exit /b 1 )
REM
REM Both binaries must be signed: the app exe (above) and the installer
REM (see the second TODO block after makensis).
REM ===========================================================================

echo [5/6] Building NSIS installer...
echo    Looking for NSIS...
set MAKENSIS=
where makensis >nul 2>nul
if %errorlevel% equ 0 set MAKENSIS=makensis
if "!MAKENSIS!"=="" if exist "%ProgramFiles(x86)%\NSIS\makensis.exe" set MAKENSIS=%ProgramFiles(x86)%\NSIS\makensis.exe
if "!MAKENSIS!"=="" if exist "%ProgramFiles%\NSIS\makensis.exe" set MAKENSIS=%ProgramFiles%\NSIS\makensis.exe

if "!MAKENSIS!"=="" (
    echo.
    echo    NSIS not found on PATH or in Program Files.
    echo    Download NSIS from: https://nsis.sourceforge.io/Download
    echo    After installing, re-run this script.
    echo.
    echo    You can still run the app directly from:
    echo    dist\MTT Windows Infinite Optimizer\MTT Windows Infinite Optimizer.exe
    echo.
    pause
    exit /b 0
)

echo    Using: !MAKENSIS!
"!MAKENSIS!" /DAPPVERSION=%APPVERSION% installer.nsi
echo.

if exist "%SETUPNAME%" (
    echo [6/6] Installer created successfully!
    echo    Installer: %SETUPNAME%
) else (
    echo [6/6] NSIS build had issues. Check the output above.
    pause
    exit /b 1
)

REM ===========================================================================
REM TODO CODE-SIGNING (post EV certificate) - sign the INSTALLER here.
REM Must run AFTER makensis has produced %SETUPNAME%.
REM
REM   signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 ^
REM       /n "Macro Tech Titan" "%SETUPNAME%"
REM   if %errorlevel% neq 0 ( echo ERROR: installer signing failed & pause & exit /b 1 )
REM
REM Verify afterwards with:  signtool verify /pa /v "%SETUPNAME%"
REM ===========================================================================

echo.
echo ============================================
echo  Build finished!
echo  Version:   %APPVERSION%
echo  Installer: %SETUPNAME%
echo ============================================
pause
