"""Shared safety primitives for every destructive Sprint 3 feature.

Nothing in this module deletes anything by itself. It provides the four
hard guarantees the sprint spec requires of every destructive path:

1. EXCLUSIONS   — ``check_deletable`` refuses Windows core, Program Files,
                  the Package Cache, and anything under an active cloud-sync
                  root. Every apply path must call it per item.
2. RECYCLE BIN  — ``send_to_recycle_bin`` uses SHFileOperationW with
                  FOF_ALLOWUNDO so removals stay recoverable. It refuses to
                  run at all when the batch would overflow the bin (which
                  would silently turn into a permanent delete) unless the
                  caller explicitly opted in for that action.
3. RESTORE POINT— ``create_restore_point`` wraps Checkpoint-Computer and
                  reports failure honestly so callers can require explicit
                  confirmation before continuing without one.
4. AUDIT        — helpers log through the existing ``log_activity`` with
                  before/after paths and bytes.

The SHFILEOPSTRUCTW layout below is the default-aligned one (56 bytes on
x64). It was verified empirically against a probe file: the file left the
filesystem and the Recycle Bin item count increased by one, confirming an
undoable delete rather than a permanent one.
"""
import os
import ctypes
import subprocess
from ctypes import wintypes

from core.state import IS_WINDOWS, _WIN_NO_WINDOW
from core.util import log_activity, format_bytes

# ─── Shell file-operation constants ────────────────────────────
FO_DELETE = 0x0003
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_NOERRORUI = 0x0400


class SHFILEOPSTRUCTW(ctypes.Structure):
    """shellapi.h SHFILEOPSTRUCTW — default alignment (do NOT set _pack_).

    A packed layout misaligns pFrom/pTo and faults inside shell32.
    """
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", ctypes.c_ushort),          # FILEOP_FLAGS == WORD
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


# ─── Never-touch roots ─────────────────────────────────────────
def _sysdrive():
    return os.environ.get("SystemDrive", "C:")


def excluded_roots():
    """Directories no destructive feature may ever write into."""
    sysroot = os.environ.get("SystemRoot", os.path.join(_sysdrive(), "\\Windows"))
    programdata = os.environ.get("ProgramData", os.path.join(_sysdrive(), "\\ProgramData"))
    roots = [
        sysroot,                                              # C:\Windows (incl. System32)
        os.environ.get("ProgramFiles", os.path.join(_sysdrive(), "\\Program Files")),
        os.environ.get("ProgramFiles(x86)", os.path.join(_sysdrive(), "\\Program Files (x86)")),
        os.path.join(programdata, "Package Cache"),
    ]
    return [os.path.normcase(os.path.abspath(r)) for r in roots if r]


# Documented clean targets that live under an excluded root but are explicitly
# allowed by the spec (temp + update caches reached via the Deep Clean feature).
def documented_exceptions():
    sysroot = os.environ.get("SystemRoot", os.path.join(_sysdrive(), "\\Windows"))
    return [os.path.normcase(os.path.abspath(p)) for p in (
        os.path.join(sysroot, "Temp"),
        os.path.join(sysroot, "SoftwareDistribution", "Download"),
        os.path.join(sysroot, "SoftwareDistribution", "DeliveryOptimization"),
        os.path.join(sysroot, "Minidump"),
        os.path.join(sysroot, "Logs"),
        os.path.join(sysroot, "Prefetch"),
        # Sprint 3 Deep Clean system targets. Listed here only so
        # check_deletable does not blanket-refuse them for sitting under
        # %SystemRoot%; what may actually delete them is the much narrower
        # allowlist in cleaners/deepclean.deepclean_system_roots().
        os.path.join(sysroot, "MEMORY.DMP"),
        os.path.join(sysroot, "LiveKernelReports"),
        os.path.join(sysroot, "ServiceProfiles", "LocalService", "AppData",
                     "Local", "FontCache"),
        os.path.join(sysroot, "System32", "FNTCACHE.DAT"),
    )]


# Only unambiguous folder names go here — a generic word like "box" would
# false-positive on ordinary user folders.
CLOUD_SYNC_DIRNAMES = (
    "onedrive", "dropbox", "google drive", "googledrive",
    "icloud drive", "iclouddrive", "box sync", "boxsync",
    "pcloud", "nextcloud", "owncloud", "resilio sync",
    "creative cloud files", "tresorit",
)


def cloud_sync_roots():
    """Best-effort list of active cloud-sync roots on this machine."""
    roots = []
    home = os.path.expanduser("~")
    for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        val = os.environ.get(var)
        if val:
            roots.append(val)
    for name in ("OneDrive", "Dropbox", "Google Drive", "GoogleDrive", "My Drive",
                 "iCloudDrive", "Box", "Box Sync", "pCloud", "Nextcloud",
                 "ownCloud", "MEGA", "Creative Cloud Files", "Tresorit"):
        candidate = os.path.join(home, name)
        if os.path.isdir(candidate):
            roots.append(candidate)
    # Marker files left by the desktop clients.
    for marker in (".dropbox", ".dropbox.cache"):
        if os.path.exists(os.path.join(home, marker)):
            roots.append(os.path.join(home, "Dropbox"))
    seen, out = set(), []
    for r in roots:
        n = os.path.normcase(os.path.abspath(r))
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _is_under(path, root):
    path = os.path.normcase(os.path.abspath(path))
    root = os.path.normcase(os.path.abspath(root))
    return path == root or path.startswith(root + os.sep)


def is_excluded_path(path):
    """(True, reason) when the path sits in a never-touch root."""
    if not path:
        return True, "empty path"
    try:
        target = os.path.abspath(path)
    except (OSError, ValueError):
        return True, "unresolvable path"

    for allowed in documented_exceptions():
        if _is_under(target, allowed):
            return False, ""

    for root in excluded_roots():
        if _is_under(target, root):
            return True, f"protected system location ({root})"

    # Refuse a bare drive root or the user profile root itself.
    drive, tail = os.path.splitdrive(target)
    if tail in ("", os.sep, "/"):
        return True, "drive root"
    if os.path.normcase(target) == os.path.normcase(os.path.expanduser("~")):
        return True, "user profile root"
    return False, ""


def is_cloud_sync_path(path):
    """(True, root) when the path is inside an active cloud-sync folder.

    Deleting a locally-synced file propagates the delete to the cloud, so
    every destructive feature blocks on this.
    """
    if not path:
        return False, ""
    target = os.path.normcase(os.path.abspath(path))
    for root in cloud_sync_roots():
        if _is_under(target, root):
            return True, root
    for part in target.split(os.sep):
        name = part.strip().lower()
        if name in CLOUD_SYNC_DIRNAMES:
            return True, part
        # Business tenants use "OneDrive - Contoso" / "Dropbox (Contoso)".
        if name.startswith("onedrive -") or name.startswith("dropbox ("):
            return True, part
    return False, ""


def check_deletable(path):
    """Single gate every destructive path must call per item.

    Returns (ok: bool, reason: str).
    """
    excluded, reason = is_excluded_path(path)
    if excluded:
        return False, f"Blocked — {reason}"
    synced, root = is_cloud_sync_path(path)
    if synced:
        return False, f"Blocked — inside cloud-sync folder ({root}); deleting would propagate to the cloud"
    return True, ""


def filter_deletable(paths):
    """Split an incoming list into (allowed, blocked[{path, reason}])."""
    allowed, blocked = [], []
    for p in paths:
        ok, reason = check_deletable(p)
        if ok:
            allowed.append(p)
        else:
            blocked.append({"path": p, "reason": reason})
    return allowed, blocked


# ─── Recycle Bin capacity ──────────────────────────────────────
def _volume_guid(drive):
    r"""\\?\Volume{GUID}\ for a drive letter, or '' when unavailable."""
    if not IS_WINDOWS:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(64)
        mount = drive if drive.endswith("\\") else drive + "\\"
        ok = ctypes.windll.kernel32.GetVolumeNameForVolumeMountPointW(
            wintypes.LPCWSTR(mount), buf, ctypes.c_ulong(64))
        return buf.value if ok else ""
    except Exception:
        return ""


def recycle_bin_capacity(path):
    """Bytes the Recycle Bin will accept on the volume holding ``path``.

    Reads the per-volume MaxCapacity policy when present; otherwise falls
    back to 5%% of the volume (the conservative Windows default), so we warn
    early rather than late.
    """
    drive = os.path.splitdrive(os.path.abspath(path))[0] or _sysdrive()
    total = 0
    try:
        total = ctypes.c_ulonglong(0)
        free = ctypes.c_ulonglong(0)
        avail = ctypes.c_ulonglong(0)
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(
            wintypes.LPCWSTR(drive + "\\"), ctypes.byref(avail),
            ctypes.byref(total), ctypes.byref(free))
        total = total.value
    except Exception:
        total = 0

    guid = _volume_guid(drive)
    if guid:
        try:
            import winreg
            key_path = (r"Software\Microsoft\Windows\CurrentVersion\Explorer"
                        r"\BitBucket\Volume" "\\" + guid.strip("\\").split("\\")[-1])
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as k:
                max_mb, _ = winreg.QueryValueEx(k, "MaxCapacity")
                if isinstance(max_mb, int) and max_mb > 0:
                    return max_mb * 1024 * 1024
        except Exception:
            pass
    return int(total * 0.05) if total else 0


def check_recycle_capacity(paths, total_bytes):
    """(fits, capacity_bytes) for a pending batch."""
    if not paths or not IS_WINDOWS:
        return True, 0
    cap = recycle_bin_capacity(paths[0])
    if cap <= 0:
        return True, 0
    return total_bytes <= cap, cap


# ─── Recycle Bin delete ────────────────────────────────────────
def send_to_recycle_bin(paths, allow_permanent=False, total_bytes=None):
    """Move ``paths`` to the Recycle Bin. Never permanently deletes silently.

    ``allow_permanent`` must be set explicitly by the caller (surfaced to the
    user per-action) before a batch larger than the bin is attempted — the
    shell would otherwise turn that into an unrecoverable delete.

    Returns {recycled, blocked, errors, bytes, permanent, capacity}.
    """
    result = {"recycled": [], "blocked": [], "errors": [], "bytes": 0,
              "permanent": False, "capacity": 0, "message": ""}
    if not paths:
        return result

    allowed, blocked = filter_deletable(paths)
    result["blocked"] = blocked
    for b in blocked:
        log_activity(f"Delete refused: {b['path']} — {b['reason']}", "WARN")
    existing = [p for p in allowed if os.path.exists(p)]
    if not existing:
        return result

    if total_bytes is None:
        total_bytes = 0
        for p in existing:
            try:
                if os.path.isfile(p):
                    total_bytes += os.path.getsize(p)
                else:
                    for dirpath, _, filenames in os.walk(p):
                        for f in filenames:
                            try:
                                total_bytes += os.path.getsize(os.path.join(dirpath, f))
                            except (OSError, PermissionError):
                                pass
            except (OSError, PermissionError):
                pass

    fits, capacity = check_recycle_capacity(existing, total_bytes)
    result["capacity"] = capacity
    if not fits and not allow_permanent:
        msg = (f"Refused: {format_bytes(total_bytes)} exceeds the Recycle Bin "
               f"capacity of {format_bytes(capacity)} on this volume. Windows "
               f"would delete these items PERMANENTLY instead of recycling them. "
               f"Re-run with permanent delete explicitly confirmed, or remove "
               f"fewer items at a time.")
        result["message"] = msg
        result["errors"].append({"path": "(batch)", "error": msg})
        log_activity(f"Recycle refused — batch {format_bytes(total_bytes)} > bin "
                     f"capacity {format_bytes(capacity)}; not deleting", "WARN")
        return result

    if not fits and allow_permanent:
        result["permanent"] = True
        log_activity(f"PERMANENT DELETE confirmed by user for {len(existing)} item(s), "
                     f"{format_bytes(total_bytes)} — exceeds Recycle Bin capacity "
                     f"{format_bytes(capacity)}", "WARN")

    if not IS_WINDOWS:
        # Non-Windows preview build: report what would happen, delete nothing.
        result["recycled"] = list(existing)
        result["bytes"] = total_bytes
        result["message"] = "Preview mode (non-Windows): nothing was deleted."
        return result

    flags = FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_SILENT
    if not result["permanent"]:
        flags |= FOF_ALLOWUNDO

    buf = "\0".join(existing) + "\0\0"
    op = SHFILEOPSTRUCTW()
    op.hwnd = None
    op.wFunc = FO_DELETE
    op.pFrom = buf
    op.pTo = None
    op.fFlags = flags
    op.fAnyOperationsAborted = 0
    op.hNameMappings = None
    op.lpszProgressTitle = None

    try:
        rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    except Exception as e:
        result["errors"].append({"path": "(batch)", "error": str(e)})
        log_activity(f"Recycle operation failed: {e}", "ERROR")
        return result

    if rc != 0:
        result["errors"].append({"path": "(batch)", "error": f"Shell error code {rc}"})
        log_activity(f"Recycle operation returned shell error {rc}", "ERROR")

    for p in existing:
        if not os.path.exists(p):
            result["recycled"].append(p)
        else:
            result["errors"].append({"path": p, "error": "still present after operation"})

    result["bytes"] = total_bytes
    where = "permanently deleted" if result["permanent"] else "moved to Recycle Bin"
    log_activity(f"{len(result['recycled'])} item(s) {where} — "
                 f"{format_bytes(total_bytes)} reclaimed", "SUCCESS")
    for p in result["recycled"]:
        log_activity(f"  {where}: {p}", "INFO")
    return result


# ─── System Restore point ──────────────────────────────────────
def create_restore_point(description="MTT Optimizer — before batch clean"):
    """Create a System Restore checkpoint before a destructive batch.

    Returns {created, message, skipped_reason}. Callers MUST refuse to
    proceed on failure unless the user explicitly confirmed going without
    one (``proceed_without_restore_point``).
    """
    out = {"created": False, "message": "", "description": description}
    if not IS_WINDOWS:
        out["message"] = "Restore points are Windows-only; skipped in preview mode."
        return out
    try:
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command",
               "Checkpoint-Computer -Description "
               f"'{description[:250]}' -RestorePointType 'MODIFY_SETTINGS'"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180,
                              creationflags=_WIN_NO_WINDOW)
        if proc.returncode == 0:
            out["created"] = True
            out["message"] = "System Restore point created."
            log_activity(f"Restore point created: {description}", "SUCCESS")
        else:
            err = (proc.stderr or proc.stdout or "").strip().splitlines()
            detail = err[0] if err else f"exit code {proc.returncode}"
            out["message"] = (
                f"Could not create a restore point: {detail}. This usually means "
                f"the app is not running as Administrator, System Protection is "
                f"off for this drive, or Windows already made one in the last 24h.")
            log_activity(f"Restore point FAILED: {detail}", "WARN")
    except subprocess.TimeoutExpired:
        out["message"] = "Restore point creation timed out after 180s."
        log_activity("Restore point creation timed out", "WARN")
    except Exception as e:
        out["message"] = f"Could not create a restore point: {e}"
        log_activity(f"Restore point error: {e}", "WARN")
    return out


def guard_batch(paths, proceed_without_restore_point=False,
                description="MTT Optimizer — before batch clean"):
    """Restore-point gate shared by every batch apply path.

    Returns (ok, payload). When ok is False the caller must abort and hand
    the payload back to the UI so the user can explicitly confirm.
    """
    rp = create_restore_point(description)
    if rp["created"] or proceed_without_restore_point:
        if not rp["created"]:
            log_activity("Proceeding WITHOUT a restore point — explicitly confirmed by user", "WARN")
        return True, {"restore_point": rp}
    return False, {
        "status": "restore_point_failed",
        "restore_point": rp,
        "message": rp["message"],
        "requires": "proceed_without_restore_point",
        "pending_items": len(paths),
    }
