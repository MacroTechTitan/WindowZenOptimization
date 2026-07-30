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
