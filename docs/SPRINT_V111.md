# v1.1.1 Polish: Branding + Activity Log

## Part A — Wire in MTT branding
Assets are in static/branding/: mtt-app.ico, mtt-installer.ico,
favicon.ico, favicon-16x16.png, favicon-32x32.png, apple-touch-icon.png,
mtt-logo-256.png, mtt-logo-512.png, mtt-splash.jpg.

1. App exe icon: add --icon="static/branding/mtt-app.ico" to the
   PyInstaller invocation in build_installer.bat. Ensure static/branding
   is bundled (it's under static/ which is already added via --add-data;
   confirm).
2. Installer icon: in installer.nsi set the installer icon and uninstaller
   icon to static\branding\mtt-installer.ico. Set Start Menu / desktop
   shortcut icon to point at the installed mtt-app.ico.
3. Favicons: add favicon links to the <head> of the base template used by
   dashboard and landing (favicon.ico, favicon-16x16.png, favicon-32x32.png,
   apple-touch-icon.png) pointing at static/branding/.
4. In-app logo: replace the existing static/images/mtt-logo.png usage in
   the header/sidebar with static/branding/mtt-logo-256.png (use 512 for
   retina if the slot is large). Keep existing layout.
5. Splash: use static/branding/mtt-splash.jpg as the FULL background of
   splash.html and templates/splash_loading.html. The image ALREADY
   contains the WindowZen title, four pillars, and tagline — do NOT render
   any app title/tagline text on top of it (would double the text). Keep
   only a loading indicator (spinner or bar). Size the image to cover.

## Part B — Downloadable Activity Log
A unified log of every destructive operation, shown after the action and
downloadable as a file. Covers: deep clean, duplicate deletion, large-file
deletion, zero-length deletion.

Backend:
- Create a shared logging helper (e.g. core/activity_log.py) that records
  each destructive operation as a structured entry: timestamp, operation
  type, per-item results (path, bytes, action=recycled|permanent),
  totals (count, bytes reclaimed), whether a restore point was created,
  and anything skipped with the reason.
- Every destructive route (deepclean apply, duplicates delete, largefiles
  delete, zero-length delete) appends its result to the current
  operation's log entry via this helper.
- Add endpoints:
  GET /api/activity-log/recent  -> returns the last N operation logs (JSON)
  GET /api/activity-log/download?format=txt|json -> returns a downloadable
      file of the most recent operation (or all recent), Content-Disposition
      attachment. Provide BOTH txt (human-readable) and json (structured).

Frontend:
- After any destructive operation completes, show a summary panel: what was
  cleaned/removed, per-target counts and bytes, total reclaimed, restore-
  point status, timestamp.
- Add a "Download log" control offering .txt and .json.
- Optionally show a short "recent activity" history (last few operations)
  on the Deep Clean hub.

## Guardrails
- Do not change any deletion logic or the core/safety behavior — only ADD
  logging around it.
- Never log secrets or anything sensitive; paths and byte counts only.
- python -c "import app" must stay clean; report the url_map delta (new
  activity-log routes).
- After implementing, run build_installer.bat and confirm the app exe and
  installer both build AND show the MTT icon, and that both are signed
  (env vars are set) and verified.

## Commit per part (branding, then activity log).
