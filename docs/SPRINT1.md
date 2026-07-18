# Sprint 1: Correctness and Trust Fixes

Work through these in order. Commit after each numbered item.
Do not refactor app.py structurally. Do not add new features.

## 1. FIX UNINSTALL (api_apps_uninstall, ~line 3183)

Current: subprocess.Popen(cmd, shell=True, creationflags=_WIN_NO_WINDOW)

Broken because: CREATE_NO_WINDOW hides the uninstaller's own UI so it
hangs invisibly; no UAC elevation so most UninstallStrings fail
silently; raw string isn't parsed for quoting or MSI GUIDs.

Rewrite to:
- Parse UninstallString. If it matches MsiExec.exe /X{GUID} or /I{GUID}
  (case-insensitive), normalize to msiexec.exe with args: /x {GUID} /qb
- Otherwise split into exe path + args honoring quoted paths (shlex with
  posix=False, or regex for the leading quoted/unquoted path).
- Launch via ctypes.windll.shell32.ShellExecuteW(None, "runas", exe,
  args, working_dir, 1). SW_SHOWNORMAL=1 so the uninstaller UI appears.
- ShellExecuteW returns int; <= 32 is an error. Map 5 (access denied /
  UAC declined), 2 (file not found), 31 (no association) to clear
  messages. Return {"ok": false, "error": ...}.
- Keep the existing log_activity call and non-Windows demo branch.
- Do NOT use creationflags=_WIN_NO_WINDOW here.

Add POST /api/apps/verify-uninstall - re-reads the registry for a given
DisplayName, returns whether still present, so the UI can confirm
removal after the user finishes the uninstaller wizard.

## 2. REMOVE SELF-UPDATE

Delete /api/updates/apply entirely. An unsigned self-updating elevated
app is a malware vector.

Rewrite /api/updates/check to query the GitHub Releases API:
https://api.github.com/repos/MacroTechTitan/WindowZenOptimization/releases/latest
Compare tag_name against the embedded local version. Return
{"update_available": bool, "latest": "...", "url": "<html_url>"}.
UI shows "Update available - Download" linking to the release page. The
app never modifies itself; the NSIS installer handles upgrade-in-place.

## 3. PURGE DEMO FALLBACKS

Find every demo/fake data path (_get_demo_apps and any others - grep for
"demo", "DEMO", "_get_demo"). On Windows, a failed scan must return an
honest error, never fabricated data. Keep non-Windows demo paths ONLY if
clearly labelled as such in the response payload.

## 4. FIX UI OVERLAP

In the registry scan results table, the risk badge column ("Low" /
"Caution") overlaps the toggle switch column. Fix the column widths /
flex layout in the relevant template + CSS so the badge, warning icon,
and toggle line up in their own columns with no overlap.

## 5. BUILD SCRIPT

In build_installer.bat, add --uac-admin to the PyInstaller invocation
(the whole app needs elevation for temp cleaning, DISM, uninstalls).
Remove the --hidden-import "pkg_resources" line - it's deprecated and
fails to resolve.
