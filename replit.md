# MTT Windows Infinite Optimizer

## Overview
A Windows system utility application by Macro Tech Titan with a terminal-style dashboard interface. Built with Python/Flask for the web-based prototype, designed to be packaged as a Windows desktop application using PyInstaller + pywebview + NSIS.

**URL**: https://windowzen.macrotechtitan.com

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
- **Recommendations Engine**: AI-powered system advisor scoring CPU/RAM/disk/uptime/habits; filter by category & priority, dismiss/snooze, export history; `recommendations_state.json` persistence
- **Profiles & Presets**: 4 built-in profiles (Performance, Work, Night Comfort, Battery Saver) + custom CRUD; apply/restore-previous; `profiles.json` storage
- **Scheduled Maintenance**: 8 default tasks (daily/weekly/monthly scan+reminder types); toggle, run now, add/delete custom tasks; full history log with export; `maintenance_schedules.json` + `maintenance_history.json`
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
- `/admin/api/download-files` - GET: list files in static/downloads/ (admin only)
- `/admin/api/upload-installer` - POST: upload .exe or .zip to static/downloads/ (admin only, 500 MB max)
- `/admin/api/download-files/delete` - POST: delete a file from static/downloads/ (admin only)
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
- `/api/recommendations` - GET: get all active recommendations with priority counts
- `/api/recommendations/dismiss` - POST: dismiss a recommendation by id
- `/api/recommendations/snooze` - POST: snooze a recommendation (hours param)
- `/api/recommendations/reset-dismissed` - POST: clear all dismissed/snoozed state
- `/api/recommendations/history` - GET: list of past dismiss/snooze actions
- `/api/recommendations/export` - GET: download recommendations as JSON
- `/api/profiles` - GET: list all profiles + active profile + history
- `/api/profiles/apply` - POST: apply a profile by id
- `/api/profiles/save` - POST: create or update a custom profile
- `/api/profiles/delete` - POST: delete a custom profile by id
- `/api/profiles/restore-previous` - POST: re-apply the previous profile
- `/api/maintenance/tasks` - GET: list all maintenance tasks
- `/api/maintenance/tasks/toggle` - POST: enable/disable a task
- `/api/maintenance/tasks/run` - POST: run a task immediately
- `/api/maintenance/tasks/save` - POST: create a custom task
- `/api/maintenance/tasks/delete` - POST: delete a custom task
- `/api/maintenance/history` - GET: maintenance run history
- `/api/maintenance/history/export` - GET: download history as JSON
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
13. **Recommendations Engine** - AI-scored prioritized system tips; dismiss/snooze/filter/export
14. **Profiles & Presets** - 4 built-in + custom profiles; one-click apply + restore-previous
15. **Scheduled Maintenance** - 8 recurring tasks; toggle/run/add/delete; full history log

## Branding
- **Name**: MTT Windows Infinite Optimizer
- **Company**: Macro Tech Titan
- **URL**: windowzen.macrotechtitan.com
- **Logo**: static/images/mtt-logo.png
- **Featured Image**: static/images/featured-image.png

## User Preferences
- Python preferred language
- Fancy terminal style UI
- Microsoft Store compliance focus
- No keylogger functionality
- Windows desktop app (pywebview + PyInstaller + NSIS)
- Landing page at root for publishing

## Pending Integrations / TODOs
- **SendGrid list sync**: User wants emails captured via the download gate to be added to a SendGrid contact list automatically. The SendGrid Replit integration was not connected (dismissed). To implement: either connect the SendGrid integration via Replit's integration panel, OR store SENDGRID_API_KEY and SENDGRID_LIST_ID as secrets and wire up a `add_to_sendgrid_list(email)` call inside `register_download()` in app.py (after saving to registrations.json). Use SendGrid's Marketing Contacts API: PUT https://api.sendgrid.com/v3/marketing/contacts.
