# SystemOptimizer Pro

## Overview
A Windows system utility application with a terminal-style dashboard interface. Built with Python/Flask for the web-based prototype, designed to be packaged as a Windows desktop application using PyInstaller + pywebview + Inno Setup.

## Current State
- Web-based dashboard prototype fully functional
- Real-time system monitoring (CPU, Memory, Disk, Network, Processes)
- System cleaner module with comprehensive Windows cleanup targets
- Registry optimizer panel with real winreg support on Windows
- Wellness monitoring with activity scoring
- Scheduler configuration for automated daily cleanup at 5PM
- Settings panel with toggle controls for all cleanup categories
- Live activity log (terminal-style output window)
- Desktop launcher (pywebview) ready for Windows packaging
- Inno Setup installer script included

## Architecture
- **Backend**: Python 3.11 + Flask
- **Frontend**: Vanilla HTML/CSS/JS with terminal aesthetic
- **Monitoring**: psutil for system metrics
- **Scheduling**: APScheduler for automated tasks
- **Desktop**: pywebview for native Windows window
- **Packaging**: PyInstaller + Inno Setup for Windows installer
- **Style**: JetBrains Mono font, dark terminal theme with scanline effect

## Project Structure
```
app.py                  - Flask backend, API endpoints, system modules, cleanup logic
desktop_launcher.py     - pywebview desktop wrapper for Windows native window
build_installer.bat     - Windows build script (PyInstaller)
installer.iss           - Inno Setup installer configuration
settings.json           - Persisted user settings
templates/
  dashboard.html        - Main dashboard HTML template
static/
  css/style.css         - Terminal-style CSS theme
  js/app.js             - Frontend JavaScript (metrics polling, UI updates)
```

## Cleanup Targets (Windows)
### Safe to Delete
- System temp files (C:\Windows\Temp)
- User temp files (%TEMP%, AppData\Local\Temp)
- Browser cache (Chrome, Edge, Firefox, IE)
- Recycle Bin
- Thumbnails (thumbcache, iconcache)
- Downloaded Program Files (legacy ActiveX/Java)
- DirectX Shader Cache
- Windows Error Reports & Crash Dumps
- Delivery Optimization Files
- Windows Defender temp files
- System log files

### Use Caution
- Windows Update Cleanup (lose rollback ability)
- Previous Windows Installation (Windows.old)

## Key Features
1. Dashboard - Real-time CPU/Memory/Disk metrics with progress bars
2. System Cleaner - Scan & clean 13+ categories of Windows clutter
3. Registry Optimizer - Registry issue detection, startup item analysis
4. Process Monitor - Live process list with CPU/Memory usage
5. Wellness Monitor - Activity tracking, wellness score, break reminders
6. Scheduler - Automated cleanup at 5PM daily, weekly registry scan
7. Settings - Toggle controls for every cleanup target with persistence

## User Preferences
- Python preferred language
- Fancy terminal style UI
- Microsoft Store compliance focus
- No keylogger functionality
- Windows desktop app (pywebview + PyInstaller + Inno Setup)
