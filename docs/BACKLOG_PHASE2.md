# Phase 2 Backlog — Post-Ship

Features deferred from v1. Not scoped for build yet. Each needs its own
spec + guardrails before implementation.

## Folder-level duplicate detection (user-requested)
Detect when an ENTIRE folder is an exact copy of another (the OneDrive /
FL Studio multi-hundred-GB mirror case). Different + higher-risk than
file-level dedup: the prompt is "delete this whole folder."
Guardrails required:
- Manifest compare (relative paths + sizes + full hashes); only flag on
  complete exact match, never near-matches.
- Never auto-pick which copy to delete — user chooses, both paths shown
  with sizes and dates.
- Detect active cloud-sync roots (OneDrive/Dropbox/Google Drive); block
  delete on synced folders — deleting local may propagate to cloud.
- Recycle Bin by default, not permanent; warn if size exceeds bin limit.
- Dry-run report first; deletion is a separate explicit action.
- Default to user-selected roots, not whole-drive; exclude Windows /
  Program Files.

## Other Phase 2 candidates (unscoped — ideas)
- Scheduled / policy-driven cleaning (rules engine, not manual buttons)
- Startup + scheduled-task manager (disable OEM junk, measure boot impact)
- Service tuning profiles (SysMain/Superfetch, etc. — reversible)
- Per-process network monitor (which app is saturating the pipe;
  catches silent multi-GB model downloads)
- Standby memory auto-purge daemon (threshold-based) [likely PRO]
- Model cache policy engine — prune old HF revisions, dedupe blobs
  across Ollama/LM Studio/ComfyUI [likely PRO]
- Bloat intelligence feed — server-updated safe-to-remove database [PRO,
  the recurring-revenue anchor]
- Performance profiles w/ revert ("Inference Mode") [likely PRO]
- Multi-machine license sync [PRO]
- Browser AI cache intelligence — per-origin breakdown, scheduled evict
- Driver update checker (report only; never auto-install drivers)
- Disk health / SMART report
- Restore-point creation before any destructive batch (safety net)

## Cybersecurity module (Sprint 4 / v1.1 — report-only)
HARD RULE: report-only posture checks. No malware detection engine, no
auto-remediation, no reading/displaying/transmitting file CONTENTS.
Surface signals and misconfigurations; never render verdicts or auto-fix.
Reuse core/safety + the folder picker; check existing scanners/security.py
first (may be a demo stub).

- Windows security posture audit (read-only): Defender on + updated,
  firewall enabled per profile, BitLocker status, UAC level, SmartScreen
  enabled, Windows Update current, automatic updates on. Nobody bundles
  this cleanly — the headline feature.
- Account/auth hygiene: blank-password accounts, auto-login enabled,
  Guest account active, members of Administrators group, RDP enabled/
  exposed.
- Network exposure: listening ports + owning process, SMBv1 enabled
  (EternalBlue vector), open shares.
- Startup/persistence surface: boot-run items, scheduled tasks, items
  from unusual locations. Report, not judge.
- Unencrypted-secrets FINDER (path-only): scan user-selected dirs for
  files likely to hold plaintext credentials — .env, *.pem, *.ppk,
  id_rsa, files named password/credentials, config files matching
  password= patterns. REPORT PATHS ONLY. Never open, read, display,
  log, upload, or delete contents. Message: "these may contain plaintext
  secrets — review/encrypt them."

Explicitly OUT: malware signature scanning, heuristic threat verdicts,
quarantine, auto-disable/auto-change of any security setting, reading
credential-file contents. A "suspicious indicators" report (unsigned
startup exes, processes from temp, hosts-file edits) is allowed ONLY
if clearly labeled "signals to review, not confirmed threats — run a
real AV scan."

## Additional clutter / edge cases (future)
Safe/auto (system-scoped, behind allowlist guard):
- CBS/Windows Update logs (C:\Windows\Logs\CBS)
- Windows.old (verify existing coverage)
- LiveKernelReports + per-app AppData CrashDumps
- Windows Installer orphaned .msp/.msi (C:\Windows\Installer) — REPORT-ONLY, "likely orphaned" heuristic, some needed for repair

Report-only (user decides):
- Old software installers in Downloads — same product, keep newest, flag older versions (high value)
- Orphaned AppData for uninstalled programs (cross-ref uninstall registry; conservative, false positives delete real data)
- Old DriverStore packages (via pnputil/DISM, not manual)
- hiberfil.sys — offer to disable hibernation, warn it kills fast startup
- Package caches: npm, pip, yarn, NuGet, Docker (dangling images/build cache — tens of GB)
- Orphaned node_modules in old projects (dev-focused)
- VSS shadow copies / old restore points — prune older

Edge cases:
- Per-drive Recycle Bin ($Recycle.Bin on every drive, not just C:)
- Skip cloud placeholders (OneDrive/Dropbox online-only) — do NOT trigger downloads/deletes (the 2TB-mirror trap)
- Non-default browser profiles (each has own cache)
- WSL ext4.vhdx bloat — report-only, advanced

AI-wedge note: package-manager + Docker caches overlap the AI storage report audience (50-100GB hoards) — consider surfacing there, not generic deep clean.

## Deep Clean parity with Windows Disk Cleanup (next build)
Deep clean missed categories that Windows cleanmgr picks up. Add / verify:
- Delivery Optimization (verify it actually fires — spec claims it, didn't run)
- Temporary Internet Files
- DirectX Shader Cache
- Windows Update Cleanup (can be GBs)
- Old Windows Update / upgrade log files
- Language Resource Files
- Device driver packages (old versions)
- System error memory dump + minidump files
- (Leave Windows ESD installation files OUT by default — removing breaks Reset this PC)
Implementation note: prefer driving Windows' own handlers via cleanmgr
StateFlags registry + `cleanmgr /sagerun:N`, run elevated, to guarantee
parity with Disk Cleanup rather than hand-coding each path. Report bytes
per category. All system-scoped permanent deletes stay behind the
existing allowlist guard.
