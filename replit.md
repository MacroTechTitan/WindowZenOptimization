# MTT Windows Infinite Optimizer

## Overview
A Windows system utility application by Macro Tech Titan with a terminal-style dashboard interface. Built with Python/Flask for the web-based prototype, designed to be packaged as a Windows desktop application using PyInstaller + pywebview + NSIS.

**URL**: https://windows.macrotechtitan.com

## Current State
- Landing page at `/` with feature showcase, screenshots, featured image, OG tags, and CTA
- Dashboard app at `/app` with all system monitoring features
- Help & Support section with detailed guides for all 10 features + screenshots
- Real-time system monitoring (CPU, Memory, Disk, Network, Processes)
- **Dashboard**: Top 5 Processes panel with Open Task Manager + Restart Recommended buttons
- System cleaner module with comprehensive Windows cleanup targets (13+ categories)
- **Large Files Finder**: scan Downloads/Desktop/Videos/Documents above threshold MB, delete/archive with dry run
- Registry optimizer with issue detection, recommendations, and fix actions
- **File Organizer**: zero-length files, duplicate detection, installer cleanup
- **Downloads Rules**: archive old files, group by type, move screenshots — with preview + dry run + undo log
- **Undo / Restore Log**: tracks all file moves/startup toggles; undo last move action
- Cybersecurity scanner: port scan, active connections, IP display, vulnerability check + Fix Internet tool
- **Wellness page**: Break timer, Brightness/Display settings, Night Light settings + schedule presets, Focus Mode with Pomodoro (25min work / 5min break cycle)
- **Speed Up page**: Startup Manager (grouped by source, enable/disable with undo), Visual Effects deep link, Power Mode deep link
- Process monitor with startup items management (enable/disable, reboot prompt)
- Deep system analysis (file counts by type, installed software)
- RAM upgrade compatibility guide based on detected hardware
- Scheduler configuration for automated daily cleanup at 5PM
- Settings panel with toggle controls for all cleanup categories
- Live activity log (terminal-style output window)
- Static text ads: landing page (promo bar + mid-page sponsor block) + dashboard (sidebar ad + inline card)
- Email registration gateway: modal → Resend verification email → verified download page
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
- `/` - Landing page (public marketing page) — download buttons open email gate modal
- `/api/register-download` - POST: register email, send Resend verification email
- `/verify-email/<token>` - GET: verify token → redirect to /download/<token>
- `/download/<token>` - GET: verified download page (shows installer link)
- `/admin/api/registrations` - GET: list all email registrations (admin only)
- `/app` - Dashboard application
- `/app/<page>` - Direct page navigation (dashboard, cleaner, help, etc.)
- `/eula` - Standalone EULA page
- `/admin` - Password-protected site admin panel (default password: mttadmin2026, set ADMIN_PASSWORD env var to change)
- `/admin/login` - Admin login endpoint
- `/admin/logout` - Admin logout
- `/admin/api/save-version` - Save version.json (admin only)
- `/admin/api/check-remote-manifest` - Fetch remote update manifest (admin only)
- `/updates/version.json` - Self-hosted update manifest (used as fallback update server)
- `/api/updates/check` - Check windowzen.macrotechtitan.com for newer version
- `/api/updates/apply` - Download and self-patch the installed app (Windows only)
- `/api/network-fix` - Run netsh winsock reset / ipconfig /flushdns etc.
- `/api/undo-log` - GET: list of tracked file/startup operations
- `/api/undo` - POST: revert last undoable action (moves only; deletes are permanent)
- `/api/large-files/scan` - POST: scan for large files above threshold MB
- `/api/large-files/delete` - POST: delete selected large files (dry_run supported)
- `/api/large-files/archive` - POST: archive selected large files to ~/Archive
- `/api/organize/preview` - POST: preview Downloads rules (archive_old, group_by_type, move_screenshots)
- `/api/organize/execute` - POST: execute organize actions (dry_run supported)
- `/api/*` - All API endpoints

## Key Features
1. **Dashboard** - Real-time CPU/Memory/Disk metrics, Top 5 Processes, Task Manager + Restart buttons
2. **System Cleaner** - Scan & clean 13+ categories of Windows clutter + Large Files Finder
3. **Speed Up** - Startup Manager (source-grouped, undo log), Visual Effects preset, Power Mode
4. **File Organizer** - Zero-length files, duplicates, installers + Downloads Rules + Undo/Restore Log
5. **Registry Optimizer** - Issue detection with fix recommendations (ADVANCED tag)
6. **Process Monitor** - Live process list + startup items management
7. **Wellness Monitor** - Break timer, Brightness & Night Light settings, Focus Mode + Pomodoro
8. **Cybersecurity** - Port scan, active connections, IP display, vulnerability check + Fix Internet
9. **System Info** - RAM details with upgrade guide, motherboard info, deep analysis
10. **Scheduler** - Automated cleanup at 5PM daily, weekly registry scan
11. **Settings** - Toggle controls for every feature with persistence
12. **Undo / Safety** - Global dry run toggles, undo log, confirmation dialogs for destructive ops

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
