@echo off
echo ============================================
echo  SystemOptimizer Pro - Windows Build Script
echo ============================================
echo.

echo [1/5] Installing Python dependencies...
pip install flask psutil apscheduler pywebview pyinstaller
echo.

echo [2/5] Building executable with PyInstaller...
pyinstaller --noconfirm --onedir --windowed ^
    --name "SystemOptimizer Pro" ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    --add-data "settings.json;." ^
    --hidden-import "apscheduler.triggers.cron" ^
    --hidden-import "apscheduler.schedulers.background" ^
    --hidden-import "webview" ^
    desktop_launcher.py
echo.

if not exist "dist\SystemOptimizer Pro\SystemOptimizer Pro.exe" (
    echo ERROR: PyInstaller build failed. Check the output above for errors.
    pause
    exit /b 1
)

echo [3/5] PyInstaller build complete!
echo    Output: dist\SystemOptimizer Pro\
echo.

echo [4/5] Building NSIS installer...
echo    Looking for NSIS...
where makensis >nul 2>nul
if %errorlevel% neq 0 (
    echo.
    echo    NSIS not found on PATH.
    echo    Download NSIS from: https://nsis.sourceforge.io/Download
    echo    After installing, re-run this script.
    echo.
    echo    You can still run the app directly from:
    echo    dist\SystemOptimizer Pro\SystemOptimizer Pro.exe
    echo.
    pause
    exit /b 0
)

makensis installer.nsi
echo.

if exist "SystemOptimizerPro_Setup_v1.0.0.exe" (
    echo [5/5] Installer created successfully!
    echo    Installer: SystemOptimizerPro_Setup_v1.0.0.exe
) else (
    echo [5/5] NSIS build had issues. Check the output above.
)

echo.
echo ============================================
echo  Build finished!
echo ============================================
pause
