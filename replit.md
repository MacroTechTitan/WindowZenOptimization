# SystemOptimizer Pro

## Overview
A Windows system utility application with a terminal-style dashboard interface. Built with Python/Flask for the web-based prototype, designed to be packaged as a Windows desktop application using PyInstaller + Inno Setup.

## Current State
- Web-based dashboard prototype fully functional
- Real-time system monitoring (CPU, Memory, Disk, Network, Processes)
- System cleaner module with scan/clean wizards
- Registry optimizer panel
- Wellness monitoring with activity scoring
- Scheduler configuration for automated tasks
- Settings panel with toggle controls
- Live activity log (terminal-style output window)

## Architecture
- **Backend**: Python 3.11 + Flask
- **Frontend**: Vanilla HTML/CSS/JS with terminal aesthetic
- **Monitoring**: psutil for system metrics
- **Scheduling**: APScheduler for automated tasks
- **Style**: JetBrains Mono font, dark terminal theme with scanline effect

## Project Structure
```
app.py                  - Flask backend, API endpoints, system modules
templates/
  dashboard.html        - Main dashboard HTML template
static/
  css/style.css         - Terminal-style CSS theme
  js/app.js             - Frontend JavaScript (metrics polling, UI updates)
```

## Key Features
1. Dashboard - Real-time CPU/Memory/Disk metrics with progress bars
2. System Cleaner - Scan & clean temp files, Chrome cache, junk files
3. Registry Optimizer - Registry issue detection panel
4. Process Monitor - Live process list with CPU/Memory usage
5. Wellness Monitor - Activity tracking, wellness score, break reminders
6. Scheduler - Automated cleanup at 5PM daily
7. Settings - Toggle controls for all features

## User Preferences
- Python preferred language
- Fancy terminal style UI
- Microsoft Store compliance focus
- No keylogger functionality
