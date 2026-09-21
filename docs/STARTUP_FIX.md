# Fix Startup Manager toggles

Three bugs in the startup enable/disable feature.

## Bug 1 — Disable deletes the entry (data loss)
routes/apps.py api_startup_toggle: disabling does winreg.DeleteValue,
permanently removing the Run entry. Re-enable then needs the original
path, which is lost after a refresh — so disabled items can't be turned
back on.

Fix: disable must be REVERSIBLE, not destructive. Use the Windows
StartupApproved mechanism the OS itself uses:
  HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run
  HKLM\...\StartupApproved\Run
Write a binary value under StartupApproved for the item: enabled state
= 02 00 00 00 ... , disabled = 03 00 00 00 ... (standard Windows format;
first byte 2=enabled, 3=disabled, rest zeroed/timestamp). This leaves the
actual Run entry intact and just flags it disabled — exactly what Task
Manager does. Never DeleteValue the Run entry.
If StartupApproved is too complex, the fallback is: on disable, move the
Run value into a backup key (e.g. our own ...\Run_MTT_Disabled) preserving
name+value, and on enable move it back. Either way the original command is
preserved so re-enable always works.

## Bug 2 — HKLM writes fail silently; frontend lies about success
Backend returns 500 on registry failure (good), but the frontend
toggleStartupItem in static/js/app.js awaits the fetch and shows a
SUCCESS notification WITHOUT checking response.ok or the JSON status.
So failed HKLM toggles report success.

Fix:
- Frontend: check res.ok / parsed status. Only show success on real
  success. On failure, show the backend error message and REVERT the
  toggle switch to its prior state so the UI reflects reality.
- Elevation: HKLM requires admin. The app already runs with a UAC
  manifest (--uac-admin) when packaged, so the built exe is elevated and
  HKLM writes should work. But detect the access-denied case and return a
  clear message ("Administrator rights required for all-users startup
  items") instead of a raw registry error.

## Bug 3 — verify HKCU path works
HKCU items (Docker, OneDrive) need no admin and must toggle correctly via
the StartupApproved approach. Test enable->disable->enable round-trips and
confirm the item's autostart state actually changes and survives a list
refresh.

## Guardrails
- Toggling is reversible; never lose the original command/path.
- Log each toggle via existing log_activity + log_undo (undo already
  exists — make sure undo restores correctly under the new approach).
- python -c "import app" clean. No route changes needed (same endpoint).
- After fix, rebuild and test in the ELEVATED packaged exe, both an HKLM
  and an HKCU item, with a list refresh in between.

Commit as its own commit.
