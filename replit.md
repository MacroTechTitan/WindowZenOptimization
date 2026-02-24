# SystemOptimizer Pro

## Overview
A Windows system utility application with a terminal-style dashboard interface. Built with Python/Flask for the web-based prototype, designed to be packaged as a Windows desktop application using PyInstaller + pywebview + Inno Setup/NSIS.

## Current State
- Web-based dashboard prototype fully functional
- Real-time system monitoring (CPU, Memory, Disk, Network, Processes)
- System cleaner module with comprehensive Windows cleanup targets (13+ categories)
- Registry optimizer with issue detection, recommendations, and fix actions
- File Organizer: zero-length files, duplicate detection, installer cleanup
- Cybersecurity scanner: port scan, active connections, IP display, vulnerability check
- Wellness monitoring with 40-min break timer, sound alerts, screen brightness tips
- Process monitor with startup items management (enable/disable, reboot prompt)
- Deep system analysis (file counts by type, installed software)
- Scheduler configuration for automated daily cleanup at 5PM
- Settings panel with toggle controls for all cleanup categories
- Live activity log (terminal-style output window)
- Desktop launcher (pywebview) ready for Windows packaging
- NSIS + Inno Setup installer scripts included

## Architecture
- **Backend**: Python 3.11 + Flask
- **Frontend**: Vanilla HTML/CSS/JS with terminal aesthetic
- **Monitoring**: psutil for system metrics
- **Scheduling**: APScheduler for automated tasks
- **Security**: socket for port scanning, psutil for connection monitoring
- **Desktop**: pywebview for native Windows window
- **Packaging**: PyInstaller + NSIS/Inno Setup for Windows installer
- **Style**: JetBrains Mono font, dark terminal theme with scanline effect

## Project Structure
```
app.py                  - Flask backend, API endpoints, all system modules
desktop_launcher.py     - pywebview desktop wrapper for Windows native window
build_installer.bat     - Windows build script (PyInstaller + NSIS)
installer.nsi           - NSIS installer configuration
installer.iss           - Inno Setup installer configuration (alternative)
LICENSE.txt             - End user license agreement
settings.json           - Persisted user settings
templates/
  dashboard.html        - Main dashboard HTML template (all pages)
static/
  css/style.css         - Terminal-style CSS theme
  js/app.js             - Frontend JavaScript (metrics, UI, all features)
```

## Key Features
1. **Dashboard** - Real-time CPU/Memory/Disk metrics with progress bars
2. **System Cleaner** - Scan & clean 13+ categories of Windows clutter
3. **File Organizer** - Find zero-length files, duplicates, leftover installers
4. **Registry Optimizer** - Issue detection with fix recommendations
5. **Process Monitor** - Live process list + startup items management
6. **Wellness Monitor** - 40-min break timer with sound, brightness tips
7. **Cybersecurity** - Port scan, active connections, IP display, vulnerability check
8. **System Info** - RAM details, motherboard info, deep analysis
9. **Scheduler** - Automated cleanup at 5PM daily, weekly registry scan
10. **Settings** - Toggle controls for every feature with persistence

## Cleanup Targets (Windows)
### Safe to Delete
- System temp files, User temp files, Browser cache (Chrome/Edge/Firefox)
- Recycle Bin, Thumbnails, Downloaded Program Files, DirectX Shader Cache
- Windows Error Reports, Delivery Optimization Files, Defender temp files, Log files

### Use Caution
- Windows Update Cleanup, Previous Windows Installation (Windows.old)

## API Endpoints
- GET/POST /api/settings, /api/metrics, /api/logs
- POST /api/scan, /api/clean, GET /api/scan-results, /api/clean-status
- GET/POST /api/registry, /api/registry/scan, /api/registry/fix
- GET /api/startup-items, POST /api/startup-items/toggle, /api/system/reboot
- GET /api/activity, /api/wellness/break-check, POST /api/wellness/dismiss-break
- GET/POST /api/security/scan
- GET/POST /api/system/deep-analysis
- GET/POST /api/file-organizer/scan, /api/file-organizer/results, /api/file-organizer/delete
- GET /api/scheduler

## User Preferences
- Python preferred language
- Fancy terminal style UI
- Microsoft Store compliance focus
- No keylogger functionality
- Windows desktop app (pywebview + PyInstaller + NSIS)
