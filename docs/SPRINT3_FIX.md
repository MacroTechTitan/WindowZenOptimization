# Sprint 3 Safety Fix — Recycle Bin + Restore Point Are Missing

## Problem (verified in code)
- No send-to-Recycle-Bin function exists anywhere. cleaners/deepclean.py
  line 7 docstring CLAIMS "SHFileOperationW with FOF_ALLOWUNDO" but no
  such call exists in the codebase.
- The only Recycle Bin ops are Clear-RecycleBin (deepclean.py:116,
  targets.py:241) which EMPTY the bin — the opposite of sending files to
  it.
- cleaners/targets.py lines ~261 and ~273 permanently delete user-
  reachable files with os.remove.
- No restore-point call exists — Checkpoint-Computer / CreateRestorePoint
  appear only in docstrings, never invoked.

## Required fixes

### 1. Create ONE real recycle helper in core/util.py
Implement send_to_recycle_bin(paths) using the Windows shell so deletes
are undoable:
- Use ctypes with SHFileOperationW (shell32), FO_DELETE (0x0003) and
  fFlags including FOF_ALLOWUNDO (0x0040), FOF_NOCONFIRMATION (0x0010),
  FOF_SILENT (0x0004), FOF_NOERRORUI (0x0400).
- pFrom must be a double-null-terminated wide string of absolute paths.
- Return (count, bytes_freed, errors). Never raise on a single-file
  failure — collect and continue.
- Non-Windows: fall back to send2trash if available, else refuse and
  return an error (do NOT silently permanent-delete).

### 2. Route USER-FILE deletions through it
Every place that deletes user-selected files goes through
send_to_recycle_bin:
- scanners/duplicates.py + routes/duplicates.py delete path
- scanners/largefiles.py + routes/largefiles.py delete path
- routes/files.py delete/move actions
Confirm NONE of these use os.remove/os.unlink/shutil.rmtree directly.

### 3. Restore point before ANY batch user-file delete
Add create_restore_point(description) in core/util.py:
- PowerShell: Checkpoint-Computer -Description "<desc>"
  -RestorePointType MODIFY_SETTINGS
- If it fails (disabled, throttled by the 24h limit, non-admin), return
  a failure flag. The route must then require an explicit
  {"confirm_without_restore_point": true} before proceeding, and surface
  a clear warning to the UI. Never silently proceed.
- Call it ONCE before a batch, not per file.

### 4. Leave SYSTEM-TEMP deletion permanent — but scope it tightly
Do NOT route %TEMP%, Windows Update cache, thumbnail cache, or other
system-temp cleaning through the Recycle Bin — Recycle-Bin-ing millions
of temp files is wrong and just relocates bloat. These stay permanent
os.remove BUT:
- targets.py and deepclean.py permanent deletes must operate ONLY on
  known-safe system paths (the defined clean targets), never on user-
  selected arbitrary paths.
- Add an assertion/guard: the permanent-delete path refuses any root
  that is not in the known system-target allowlist. If a caller passes
  an arbitrary user path to the permanent deleter, it must refuse.

### 5. Fix the false docstring
Update cleaners/deepclean.py line 7 so it describes what the code
actually does.

## Verification gate
- grep confirms send_to_recycle_bin is defined once in core/util.py and
  imported by duplicates, largefiles, files routes.
- grep confirms no os.remove / os.unlink / shutil.rmtree remains in any
  USER-FILE delete path (system-temp allowlisted deletes may keep it).
- create_restore_point is actually called before batch user deletes.
- python -c "import app" clean; url_map still 112.
- Write a tiny throwaway test: create temp files in a scratch dir, run
  the duplicate/largefile delete against them, and confirm they land in
  the Recycle Bin (recoverable), NOT permanently gone.
