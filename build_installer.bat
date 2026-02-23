@echo off
echo ============================================
echo  SystemOptimizer Pro - Windows Build Script
echo ============================================
echo.

echo [1/4] Installing Python dependencies...
pip install flask psutil apscheduler pywebview pyinstaller
echo.

echo [2/4] Building executable with PyInstaller...
pyinstaller --noconfirm --onedir --windowed ^
    --name "SystemOptimizer Pro" ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    --add-data "settings.json;." ^
    --icon "static/icon.ico" ^
    --hidden-import "apscheduler.triggers.cron" ^
    --hidden-import "apscheduler.schedulers.background" ^
    --hidden-import "webview" ^
    desktop_launcher.py
echo.

echo [3/4] Build complete!
echo    Output: dist\SystemOptimizer Pro\
echo.

echo [4/4] To create a Windows installer, use Inno Setup with installer.iss
echo    Download Inno Setup: https://jrsoftware.org/isinfo.php
echo.
echo ============================================
echo  Build finished successfully!
echo ============================================
pause
