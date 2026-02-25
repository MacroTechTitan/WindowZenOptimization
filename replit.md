# MTT Windows Infinite Optimizer

## Overview
A Windows system utility application by Macro Tech Titan with a terminal-style dashboard interface. Built with Python/Flask for the web-based prototype, designed to be packaged as a Windows desktop application using PyInstaller + pywebview + NSIS.

**URL**: https://windows.macrotechtitan.com

## Current State
- Landing page at `/` with feature showcase, screenshots, featured image, OG tags, and CTA
- Dashboard app at `/app` with all system monitoring features
- Help & Support section with detailed guides for all 10 features + screenshots
- Real-time system monitoring (CPU, Memory, Disk, Network, Processes)
- System cleaner module with comprehensive Windows cleanup targets (13+ categories)
- Registry optimizer with issue detection, recommendations, and fix actions
- File Organizer: zero-length files, duplicate detection, installer cleanup
- Cybersecurity scanner: port scan, active connections, IP display, vulnerability check
- Wellness monitoring with 40-min break timer, sound alerts, screen brightness tips
- Process monitor with startup items management (enable/disable, reboot prompt)
- Deep system analysis (file counts by type, installed software)
- RAM upgrade compatibility guide based on detected hardware
- Scheduler configuration for automated daily cleanup at 5PM
- Settings panel with toggle controls for all cleanup categories
- Live activity log (terminal-style output window)
- Desktop launcher (pywebview) ready for Windows packaging
- NSIS + Inno Setup installer scripts included
- MTT branding with logo throughout app and landing page
- Featured widescreen image at static/images/featured-image.png

## Architecture
- **Backend**: Python 3.11 + Flask
- **Frontend**: Vanilla HTML/CSS/JS with terminal aesthetic
- **Monitoring**: psutil for system metrics
- **Scheduling**: APScheduler for automated tasks
- **Security**: socket for port scanning, psutil for connection monitoring
- **Desktop**: pywebview for native Windows window
- **Packaging**: PyInstaller + NSIS/Inno Setup for Windows installer
- **Style**: JetBrains Mono + Inter fonts, dark terminal theme with scanline effect
- **Deployment**: gunicorn on autoscale target

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
  landing.html          - Public landing page (root URL) with OG meta tags
  dashboard.html        - Main dashboard HTML template (all app pages + help)
static/
  css/style.css         - Terminal-style CSS theme
  js/app.js             - Frontend JavaScript (metrics, UI, all features)
  images/               - MTT logo and featured image
  screenshots/          - Auto-captured screenshots for help & landing page
```

## Routes
- `/` - Landing page (public marketing page)
- `/app` - Dashboard application
- `/app/<page>` - Direct page navigation (dashboard, cleaner, help, etc.)
- `/api/*` - All API endpoints

## Key Features
1. **Dashboard** - Real-time CPU/Memory/Disk metrics with progress bars
2. **System Cleaner** - Scan & clean 13+ categories of Windows clutter
3. **File Organizer** - Find zero-length files, duplicates, leftover installers
4. **Registry Optimizer** - Issue detection with fix recommendations
5. **Process Monitor** - Live process list + startup items management
6. **Wellness Monitor** - 40-min break timer with sound, brightness tips
7. **Cybersecurity** - Port scan, active connections, IP display, vulnerability check
8. **System Info** - RAM details with upgrade guide, motherboard info, deep analysis
9. **Scheduler** - Automated cleanup at 5PM daily, weekly registry scan
10. **Settings** - Toggle controls for every feature with persistence

## Branding
- **Name**: MTT Windows Infinite Optimizer
- **Company**: Macro Tech Titan
- **URL**: windows.macrotechtitan.com
- **Logo**: static/images/mtt-logo.png
- **Featured Image**: static/images/featured-image.png

## User Preferences
- Python preferred language
- Fancy terminal style UI
- Microsoft Store compliance focus
- No keylogger functionality
- Windows desktop app (pywebview + PyInstaller + NSIS)
- Landing page at root for publishing
