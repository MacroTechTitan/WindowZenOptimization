# Sprint 3 UX + Deep Clean consolidation

## A. Duplicate + Large File Finder UX fixes
1. Filename-first display — each row leads with the filename in bold;
   truncate the path in the MIDDLE (start + end with ellipsis) so the
   filename is never cut off; full path on hover. Apply to duplicates
   AND large files.
2. "Select all duplicates" button — auto-selects every copy except one
   survivor per group. Survivor = the copy with no "(1)/(2)/(copy)"
   suffix, else the oldest modified. Never selects the survivor, never
   pre-selected on load.
3. Replace the confirm() popup with a dedicated Review screen for Step 2
   showing ONLY files marked for deletion, total count, bytes reclaimed,
   destination (Recycle Bin), and restore-point status inline. One
   "Delete to Recycle Bin" button. guard_batch restore-point-failure
   warning shows inline here, not as a browser popup.
4. Custom folder picker on both finders — scan an arbitrary path (for
   the OneDrive/FL Studio mirror case and testing); validate it exists;
   same Windows/Program Files exclusions; refuse system roots.

## B. Consolidate nav
Make Deep Clean a hub with sub-sections (Deep Clean, Large Files,
Duplicates, Zero-length) instead of three top-level pages. Nav/IA change
only — keep all backends and route paths intact.

## C. New Zero-length file finder
Following the duplicates pattern: report-only + reviewed delete,
user-selected roots, NEVER auto-select. Hard-exclude anything under
C:\Windows, Program Files, ProgramData, any AppData path; `__init__.py`;
`*.lock`/`*.lck`; `.gitkeep`; `desktop.ini`; known sentinels. Deletion
through core.safety `send_to_recycle_bin` + `guard_batch`, same Review
screen. UI warns empty files may be placeholders/locks.

## D. Expand Deep Clean system targets
Confirm existing ones and ADD: DNS cache flush (`ipconfig /flushdns`),
leftover files from uninstalled programs (orphaned dirs with no Uninstall
registry entry — REPORT ONLY), jump lists/Recent MRU (report+opt), old
`*.log` files older than N days, font cache, Windows Store cache
(`wsreset`), memory dumps (`C:\Windows\MEMORY.DMP`). System targets stay
allowlist-guarded permanent deletes, NOT recycle bin.

All new user-file deletions go through core.safety — no raw `os.remove`.
Commit per section. Report url_map count and confirm no raw deletes in
new user-file paths.

---

# Implementation notes

## A1 — filename-first rows
`App._pathParts(path)` splits a path into `{name, folder}` and
`App._midTrunc(text, max)` truncates in the middle (`head…tail`) so the
tail — which carries the filename and the deepest folder — survives. Each
row renders:

```
<strong>filename.ext</strong>          (never truncated)
C:\Users\me\…\Projects\FL Studio       (middle-truncated, title=full path)
```

`title` on both lines carries the untruncated absolute path, so hovering
shows it in full. Used by the duplicates list, the large-file list, the
zero-length list, and every Review-screen row.

## A2 — survivor selection
`App._survivorOf(group)` returns the copy that must never be selected:

1. Take the copies whose filename has no copy-suffix — `name (1)`,
   `name (2)`, `name - Copy`, `name - Copy (3)`, `name copy`.
2. If any remain, the survivor is the OLDEST modified of those.
3. Otherwise the survivor is the oldest modified of the whole group.

`mtime` (epoch float) is emitted per copy by `scanners/duplicates.py` so
the comparison does not depend on the display string. The button only
ticks boxes; nothing is selected on load, and the server-side
"at least one copy must survive" guard in `routes/duplicates.py` is
unchanged and still authoritative.

## A3 — Review screen
One shared in-page overlay (`#review-screen` in `templates/dashboard.html`,
driven by `App.openReview(cfg)`), used by all three finders. It lists ONLY
the items marked for deletion and shows:

* total count and total bytes to reclaim,
* destination — Recycle Bin, with the "recoverable" wording,
* restore-point status inline: "will be created before deletion" before
  the run, and — when `guard_batch` returns 409 `restore_point_failed` —
  the failure text plus a second, explicit "Delete without a restore
  point" button, rendered INSIDE the review screen.

No `confirm()`/`alert()` remains on the duplicates, large-file or
zero-length delete paths.

## A4 — custom folder picker
New shared blueprint `routes/scanroots.py`:

* `POST /api/scan-roots/validate` — `{path}` → `{ok, path, label,
  cloud_synced}` or `{ok: false, message}`.

It refuses: a path that does not exist or is not a directory, anything
`core.safety.is_excluded_path` refuses, and — independently of
`documented_exceptions` — anything under `%SystemRoot%`,
`%ProgramFiles%`, `%ProgramFiles(x86)%` or `%ProgramData%`, plus bare
drive roots. Validated folders are added to the finder's root list as a
ticked checkbox; they are ordinary roots from then on, so the scanners'
own exclusion walk still applies.

## B — nav hub
`Deep Clean` becomes a collapsible hub in the sidebar containing
`Deep Clean`, `Large Files`, `Duplicates` and `Zero-length`. The hub
header is not itself a page; each sub-item keeps its existing
`data-page` value, so `/app/largefiles`, `/app/duplicates` and every
`/api/...` path are untouched. `App.showPage()` expands the hub whenever
one of its sub-pages is active.

## C — zero-length finder
`scanners/zerolength.py` + `routes/zerolength.py`, mirroring the
duplicates pair.

Hard exclusions applied per file, on top of `is_excluded_path`:

* any path under `%SystemRoot%`, `%ProgramFiles%`, `%ProgramFiles(x86)%`,
  `%ProgramData%`, or any `AppData` / `Application Data` path segment;
* exact names: `__init__.py`, `.gitkeep`, `.keep`, `.placeholder`,
  `.nomedia`, `desktop.ini`, `py.typed`, `.dirstamp`, `.watchmanconfig`,
  `.gitmodules`, `.npmignore`, `.metadata_never_index`;
* extensions: `.lock`, `.lck`, `.pid`, `.sentinel`, `.stamp`, `.marker`,
  `.lockfile`;
* anything inside a `.git`, `.hg`, `.svn`, `node_modules`,
  `site-packages`, `__pycache__` or `$RECYCLE.BIN` directory.

Files are reported, never pre-selected. Deletion goes through
`guard_batch` + `send_to_recycle_bin` exactly like the other finders, and
the page carries a standing warning that a zero-byte file is often a
placeholder or a lock rather than junk.

## D — Deep Clean targets

Confirmed already present: `user_temp`, `windows_temp`,
`windows_update_cache`, `winsxs` (DISM), `delivery_optimization`,
`thumbnail_icon_cache`, `recycle_bin`, `error_reports`, `prefetch`
(report only), `windows_old`, `browser_caches`, `old_logs`
(`*.log`/`*.etl`/`*.dmp`/`*.old`/`*.txt` older than
`LOG_MAX_AGE_DAYS` = 30 — this is the "old *.log files older than N
days" target; N is that module constant).

Added:

| key | what | mode | default |
|---|---|---|---|
| `dns_cache` | `ipconfig /flushdns` | `command` | off |
| `leftover_programs` | program dirs with no Uninstall registry entry | `report_dirs` | off, REPORT ONLY |
| `jump_lists` | Recent items, Automatic/CustomDestinations | `contents` | off |
| `font_cache` | `FontCache` service data + `FNTCACHE.DAT` | `system_permanent` | off |
| `store_cache` | `wsreset.exe` + Store `LocalCache` size | `command` | off |
| `memory_dumps` | `C:\Windows\MEMORY.DMP`, `LiveKernelReports` | `system_permanent` | off |

### Deletion policy in Deep Clean (deliberate split)

`cleaners/deepclean.py` grows a second deleter, and which one a target
uses is a property of the target, not of the caller:

* **`system_permanent`** — allowlist-guarded permanent delete, mirroring
  `cleaners/targets.py`. `deepclean_system_roots()` is computed from the
  `system_permanent` rows of `DEEPCLEAN_TARGETS` in this module (not from
  a caller-supplied dict), and `permanent_delete()` raises
  `PermanentDeleteRefused` for anything outside it. These targets are
  system files the Recycle Bin cannot meaningfully hold: a 16 GB
  `MEMORY.DMP` moved to `C:\$Recycle.Bin` frees nothing, and the font
  cache is regenerated by Windows on the next boot.
* **Recycle Bin** — every pre-existing file-removing target keeps the
  `send_to_recycle_bin` route added by the Sprint 3 safety fixes, and so
  does the one new target that touches user-profile files
  (`jump_lists`). Sprint 3's global rule ("RECYCLE BIN, NOT PERMANENT")
  still governs anything a user could plausibly want back; flipping those
  to permanent would undo commits 750a1ca…0590176.

So "system targets stay allowlist-guarded permanent deletes" is
implemented for the system-only targets, and the Recycle Bin route is
kept where the deleted item is, or could be, the user's. Both paths still
run behind `guard_batch` and per-item `check_deletable`.

`core.safety.documented_exceptions()` gains the two new system paths
(`MEMORY.DMP` + `LiveKernelReports`, `ServiceProfiles\...\FontCache`)
so `check_deletable` does not blanket-refuse them as "under
`%SystemRoot%`"; they remain refused for every other feature by the
allowlist, which is narrower.

## Verification
* `url_map` count before / after, and the added rules listed.
* No `os.remove` / `os.unlink` / `shutil.rmtree` in any user-file path:
  `routes/duplicates.py`, `routes/largefiles.py`, `routes/zerolength.py`,
  `routes/files.py`, `scanners/zerolength.py`.
