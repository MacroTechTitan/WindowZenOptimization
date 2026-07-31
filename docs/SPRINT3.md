# Sprint 3: Free-Tier Features + NSIS Installer

## Global safety rules (apply to EVERY destructive feature below)
These are hard constraints. Violating any is a failed sprint.
- DRY-RUN FIRST. Every feature that can delete or modify has two phases:
  a scan/report phase that changes nothing, and a separate apply phase
  triggered by an explicit second user action. Never delete during scan.
- RECYCLE BIN, NOT PERMANENT. All file/folder deletions go to the
  Recycle Bin via the Windows shell (SHFileOperation with FOF_ALLOWUNDO,
  or send2trash-style logic). Permanent delete only if the user
  explicitly opts in per-action AND the size exceeds recycle capacity,
  in which case warn loudly first.
- RESTORE POINT before any batch delete or system-clean apply. Call
  PowerShell Checkpoint-Computer (or WMI SystemRestore.CreateRestorePoint)
  once before the batch. If restore-point creation fails, warn the user
  and require explicit confirmation to proceed without one.
- NEVER touch: C:\Windows core (except documented clean targets via
  DISM/temp), Program Files binaries, System32, user Documents unless
  explicitly selected, or anything under an active cloud-sync root.
- EXCLUDE by default: C:\Windows, C:\Program Files, C:\Program Files (x86),
  C:\ProgramData\Package Cache, and any path the user hasn't opted into.
- Every apply action logs via the existing log_activity with clear
  before/after (paths, bytes reclaimed).

## Architecture
Follow the Sprint 2 module structure. New scanners go in scanners/,
new cleaners in cleaners/, new routes as blueprints in routes/. Do NOT
put logic back in app.py. Register every new blueprint in app.py and
confirm the url_map grows by exactly the routes you add.

## Feature 1 — Deep Clean (expand existing cleaner)
New file scanners/deepclean.py + cleaners/deepclean.py + routes/deepclean.py.
Report phase enumerates size reclaimable per target; apply phase cleans
selected targets. Targets:
- %TEMP% and C:\Windows\Temp
- Windows Update cache (C:\Windows\SoftwareDistribution\Download) —
  stop wuauserv/bits before, restart after
- WinSxS component store via: DISM /Online /Cleanup-Image /StartComponentCleanup
  (run as subprocess, capture output, this is the big reclaim)
- Delivery Optimization cache
- Thumbnail cache + icon cache
- Recycle Bin (offer to empty, with size shown)
- Windows Error Reporting + crash dumps (C:\Windows\Minidump, LocalDumps)
- Prefetch (report only, low value, default OFF)
- Old Windows install (Windows.old) if present — big, prompt clearly
- Per-browser caches: Chrome, Edge, Firefox, Brave (cache dirs only,
  NEVER cookies/history/passwords)
- Log files older than N days in known log dirs
Each target: name, path(s), reclaimable bytes, risk label, default
on/off. WinSxS and Windows.old default OFF (require opt-in).

## Feature 2 — Large File Finder
New scanners/largefiles.py + routes/largefiles.py.
- Scan USER-SELECTED roots only (default suggestions: Downloads,
  Desktop, user home; NOT whole drive by default). Windows/Program
  Files excluded.
- Surface files >500MB (threshold configurable), sorted desc.
- Categorize by extension: video, installer/archive, disk image, model
  file, other.
- Heuristic flag: old installers (*.exe/*.msi in Downloads with an older
  version when a newer same-product file exists).
- Report only. Deletion is per-file, user-selected, to Recycle Bin,
  with restore point before batch.

## Feature 3 — Duplicate File Finder
New scanners/duplicates.py + routes/duplicates.py.
- Three-pass: group by size, then partial hash (first + last 64KB),
  then full SHA-256 only on partial-hash collisions. Do NOT full-hash
  everything.
- Scan user-selected roots only, same exclusions.
- Report groups of identical files with total reclaimable size.
- User selects which copies to remove (NEVER auto-select). Removal to
  Recycle Bin, restore point before batch.
- FILE-level only this sprint. Folder-level duplicate detection is
  Phase 2 (see docs/BACKLOG_PHASE2.md) — do NOT implement it here.

## Feature 4 — AI Storage Report (READ-ONLY)
New scanners/ai_storage.py + routes/ai_storage.py.
- REPORT ONLY. No deletion, no pruning this sprint (that's Pro/Phase 2).
- Detect and size these caches if present:
  - Ollama models: %USERPROFILE%\.ollama\models
  - HuggingFace: %USERPROFILE%\.cache\huggingface (report per-model and
    flag multiple revisions of same model as "orphaned revisions")
  - LM Studio models dir
  - ComfyUI / checkpoints if a common path exists
  - pip cache, conda pkgs cache
  - torch hub cache
- Output: per-tool total size, per-model breakdown where possible,
  count of stale/duplicate revisions. This is the differentiator — make
  the report clear and specific. Managing/pruning is explicitly OUT.

## Feature 5 — Internet Optimizer
New routes/network.py (+ helper module if needed).
Read-only diagnostics + tiered fixes. Implement EXACTLY these, no more:
- GET /api/network/diagnose — current DNS per adapter, detected MTU,
  adapter list, Winsock LSP catalog (netsh winsock show catalog).
- POST /api/network/quick-fix — ipconfig /flushdns, /release, /renew.
  No reboot. Non-interactive, CREATE_NO_WINDOW is fine here.
- POST /api/network/deep-reset — requires {"confirm": true}. Runs
  netsh winsock reset, netsh int ip reset. Response states reboot
  required. UI must show a modal warning (connection will drop, restart
  needed) before calling.
- POST /api/network/set-dns — {adapter, dns} or {restore:true}. Save
  previous DNS before changing. Presets: Cloudflare 1.1.1.1, Google
  8.8.8.8, Quad9 9.9.9.9, Restore to DHCP.
- GET /api/network/dns-benchmark — time resolution of a fixed domain
  set against 1.1.1.1, 8.8.8.8, 9.9.9.9, and current DHCP DNS; return
  sorted with a recommendation.
- GET /api/network/mtu-probe — binary-search largest unfragmented packet
  via ping -f -l; return optimal + current per adapter.
- POST /api/network/set-mtu — {adapter, mtu}, netsh set subinterface
  mtu store=persistent, save previous.
- POST /api/network/browser-cache — {browsers[], action:scan|clear};
  scan returns cache size per browser/profile; clear removes cache dirs
  ONLY (never cookies/history/passwords).
- ABSOLUTELY DO NOT implement netsh advfirewall reset. Out of scope,
  destroys all firewall rules irreversibly.
- Any advanced TCP tweak UI (autotuning/RSS/ECN): label "Advanced —
  typically minimal effect on modern Windows." Do not promise speed.

## Feature 6 — NSIS Installer
- Assume NSIS is installed and makensis is on PATH (user installs it
  separately). Update installer.nsi as needed so it packages the current
  dist/ output from PyInstaller.
- Installer must: install to Program Files, create Start Menu +
  optional desktop shortcut, write an uninstaller, register in
  Add/Remove Programs, and request admin (the app needs elevation).
- Output a single MTT_...Setup.exe. Keep the existing versioned naming
  scheme but source the version from version.json so it's not hardcoded.
- Do NOT add code-signing steps yet — that comes after the EV cert
  issues. Leave a clearly-marked TODO comment in the build script where
  the signtool step will go (sign both the app exe and the installer).

## UI
For each feature add a page under the existing dashboard nav, following
the current template/CSS conventions. Each destructive feature's UI must
have a clear two-step flow: Scan (report) then a separate Review &
Delete/Apply action, with the restore-point and recycle-bin behavior
surfaced to the user.

## Verification gate
- python -c "import app" clean after each feature.
- url_map rule count = 89 + (new routes added). Print the new routes.
- cmd //c build_installer.bat reaches PyInstaller "Build complete".
- Commit after EACH feature, not batched. If any destructive path can't
  be made safe per the global rules, STOP and report instead of shipping
  it unsafe.

## What NOT to do
- No folder-level duplicate deletion (Phase 2).
- No AI cache pruning/management (Pro/Phase 2), report only.
- No overclocking, no per-tab browser memory (cut earlier).
- No code-signing wiring yet (post-cert).
- Do not weaken any global safety rule for convenience.
