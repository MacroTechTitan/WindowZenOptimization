"""Deep Clean target definitions and the report (scan) phase.

This module NEVER deletes. It enumerates each target, sizes what could be
reclaimed, and returns a report the UI shows before the user triggers the
separate apply phase in cleaners/deepclean.py.
"""
import os
import glob
import subprocess
from datetime import datetime, timedelta

from core.state import IS_WINDOWS, _WIN_NO_WINDOW
from core.util import log_activity, format_bytes

try:
    import winreg
except ImportError:      # non-Windows dev box
    winreg = None

# Risk labels surfaced in the UI.
RISK_SAFE = "safe"          # regenerated automatically, no user data
RISK_CAUTION = "caution"    # reclaims a lot, has a real trade-off
RISK_HIGH = "high"          # irreversible capability loss, opt-in only

LOG_MAX_AGE_DAYS = 30


def _home():
    return os.path.expanduser("~")


def _sysroot():
    return os.environ.get("SystemRoot", "C:\\Windows")


def _localappdata():
    return os.environ.get("LOCALAPPDATA", os.path.join(_home(), "AppData", "Local"))


def _programdata():
    return os.environ.get("ProgramData", "C:\\ProgramData")


# ─── Browser cache directories (cache ONLY — never cookies/history/passwords) ──
def _chromium_cache_dirs(base):
    """Cache subdirs across every profile of a Chromium-family browser."""
    dirs = []
    if not os.path.isdir(base):
        return dirs
    try:
        profiles = [p for p in os.listdir(base)
                    if p == "Default" or p.startswith("Profile ")]
    except (OSError, PermissionError):
        return dirs
    for prof in profiles:
        proot = os.path.join(base, prof)
        for sub in ("Cache", "Code Cache", "GPUCache",
                    os.path.join("Service Worker", "CacheStorage"),
                    os.path.join("Service Worker", "ScriptCache")):
            d = os.path.join(proot, sub)
            if os.path.isdir(d):
                dirs.append(d)
    return dirs


def _firefox_cache_dirs():
    pattern = os.path.join(_localappdata(), "Mozilla", "Firefox", "Profiles", "*", "cache2")
    return [d for d in glob.glob(pattern) if os.path.isdir(d)]


def browser_cache_dirs():
    """{browser: [cache dirs]} — cache directories only, by design."""
    la = _localappdata()
    return {
        "Chrome": _chromium_cache_dirs(os.path.join(la, "Google", "Chrome", "User Data")),
        "Edge": _chromium_cache_dirs(os.path.join(la, "Microsoft", "Edge", "User Data")),
        "Brave": _chromium_cache_dirs(
            os.path.join(la, "BraveSoftware", "Brave-Browser", "User Data")),
        "Firefox": _firefox_cache_dirs(),
    }


def _all_browser_cache_dirs():
    out = []
    for dirs in browser_cache_dirs().values():
        out.extend(dirs)
    return out


def _old_log_files():
    """Log files older than LOG_MAX_AGE_DAYS in known log directories."""
    cutoff = datetime.now() - timedelta(days=LOG_MAX_AGE_DAYS)
    roots = [
        os.path.join(_sysroot(), "Logs"),
        os.path.join(_sysroot(), "Panther"),
        os.path.join(_programdata(), "Microsoft", "Windows", "WER", "ReportArchive"),
        os.path.join(_localappdata(), "Microsoft", "Windows", "WER", "ReportArchive"),
    ]
    found = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        try:
            for dirpath, _, filenames in os.walk(root):
                for f in filenames:
                    if not f.lower().endswith((".log", ".etl", ".dmp", ".old", ".txt")):
                        continue
                    fp = os.path.join(dirpath, f)
                    try:
                        if datetime.fromtimestamp(os.path.getmtime(fp)) < cutoff:
                            found.append(fp)
                    except (OSError, PermissionError):
                        pass
        except (OSError, PermissionError):
            pass
    return found


def _appdata():
    return os.environ.get("APPDATA", os.path.join(_home(), "AppData", "Roaming"))


def _jump_list_dirs():
    """Recent-items jump lists. These live in the user's profile."""
    recent = os.path.join(_appdata(), "Microsoft", "Windows", "Recent")
    return [
        os.path.join(recent, "AutomaticDestinations"),
        os.path.join(recent, "CustomDestinations"),
    ]


def font_cache_paths():
    """Windows font cache. Rebuilt automatically on the next boot."""
    sysroot = _sysroot()
    return [
        os.path.join(sysroot, "ServiceProfiles", "LocalService", "AppData",
                     "Local", "FontCache"),
        os.path.join(sysroot, "System32", "FNTCACHE.DAT"),
    ]


def memory_dump_paths():
    """Kernel crash dumps. A full MEMORY.DMP is routinely 8-16 GB."""
    sysroot = _sysroot()
    return [
        os.path.join(sysroot, "MEMORY.DMP"),
        os.path.join(sysroot, "LiveKernelReports"),
    ]


def _store_cache_dir():
    return os.path.join(_localappdata(), "Packages",
                        "Microsoft.WindowsStore_8wekyb3d8bbwe", "LocalCache")


# ─── Leftover program directories (REPORT ONLY) ────────────────
# Matching an orphaned folder to an uninstalled program is a heuristic, and a
# wrong guess here would delete a working installation. So this target is
# report-only: it is never cleanable, whatever the client sends.
_VENDOR_DIRS_TO_SKIP = {
    "common files", "windows nt", "windowsapps", "windowspowershell",
    "microsoft", "microsoft office", "microsoft visual studio", "internet explorer",
    "windows defender", "windows mail", "windows media player", "windows photo viewer",
    "windows portable devices", "windows security", "windows sidebar",
    "modifiableatidesktop", "uninstall information", "reference assemblies",
    "msbuild", "dotnet", "package cache", "temp", "desktop.ini",
}


def _installed_program_names():
    """(display names, install locations) from the Uninstall registry hives."""
    names, locations = set(), set()
    if winreg is None:
        return names, locations
    hives = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, path in hives:
        try:
            with winreg.OpenKey(hive, path) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        with winreg.OpenKey(key, winreg.EnumKey(key, i)) as sub:
                            try:
                                names.add(str(winreg.QueryValueEx(sub, "DisplayName")[0]).lower())
                            except OSError:
                                pass
                            try:
                                loc = str(winreg.QueryValueEx(sub, "InstallLocation")[0]).strip()
                                if loc:
                                    locations.add(os.path.normcase(os.path.abspath(loc)))
                            except OSError:
                                pass
                    except OSError:
                        continue
        except OSError:
            continue
    return names, locations


def leftover_program_dirs():
    """Program directories with no matching Uninstall registry entry.

    Read-only and advisory. A folder appears here when nothing in the
    Uninstall hives claims it — which usually means a sloppy uninstaller,
    but can equally mean a portable app or a per-user install the hives do
    not cover. That ambiguity is why the target never deletes.
    """
    if not IS_WINDOWS or winreg is None:
        return []
    names, locations = _installed_program_names()
    if not names and not locations:
        return []       # registry unreadable — report nothing rather than everything

    bases = [
        os.environ.get("ProgramFiles", os.path.join(_sysdrive_root(), "Program Files")),
        os.environ.get("ProgramFiles(x86)", os.path.join(_sysdrive_root(), "Program Files (x86)")),
        os.path.join(_localappdata(), "Programs"),
    ]
    found = []
    for base in bases:
        if not os.path.isdir(base):
            continue
        try:
            entries = os.listdir(base)
        except (OSError, PermissionError):
            continue
        for name in entries:
            full = os.path.join(base, name)
            if not os.path.isdir(full):
                continue
            low = name.lower()
            if low in _VENDOR_DIRS_TO_SKIP:
                continue
            if os.path.normcase(os.path.abspath(full)) in locations:
                continue
            # A folder is claimed if any installed product name contains it or
            # it contains any product name — vendors rarely name the two the same.
            if any(low in n or n in low for n in names if n):
                continue
            found.append(full)
    return found


def _sysdrive_root():
    return os.environ.get("SystemDrive", "C:") + os.sep


# ─── Target table ──────────────────────────────────────────────
# default_on=False means the user must opt in explicitly before the apply
# phase will touch it (spec: WinSxS and Windows.old default OFF).
DEEPCLEAN_TARGETS = {
    "user_temp": {
        "label": "User Temp (%TEMP%)",
        "description": "Per-user temporary files left behind by applications.",
        "risk": RISK_SAFE,
        "default_on": True,
        "paths_fn": lambda: [os.environ.get(
            "TEMP", os.path.join(_localappdata(), "Temp"))],
        "mode": "contents",
    },
    "windows_temp": {
        "label": "Windows Temp (C:\\Windows\\Temp)",
        "description": "System-wide temporary files. Requires Administrator.",
        "risk": RISK_SAFE,
        "default_on": True,
        "paths_fn": lambda: [os.path.join(_sysroot(), "Temp")],
        "mode": "contents",
    },
    "windows_update_cache": {
        "label": "Windows Update Cache",
        "description": ("Downloaded update payloads in SoftwareDistribution\\Download. "
                        "Windows Update and BITS are stopped first and restarted after. "
                        "Windows re-downloads anything it still needs."),
        "risk": RISK_CAUTION,
        "default_on": False,
        "paths_fn": lambda: [os.path.join(_sysroot(), "SoftwareDistribution", "Download")],
        "mode": "contents",
        "services": ["wuauserv", "bits"],
    },
    "winsxs": {
        "label": "WinSxS Component Store (DISM)",
        "description": ("Runs DISM /Online /Cleanup-Image /StartComponentCleanup. "
                        "Usually the largest single reclaim, but superseded update "
                        "components are removed permanently and cannot be uninstalled "
                        "afterwards. Can take 10-30 minutes."),
        "risk": RISK_HIGH,
        "default_on": False,
        "paths_fn": lambda: [],
        "mode": "dism",
    },
    "delivery_optimization": {
        "label": "Delivery Optimization Cache",
        "description": "Peer-to-peer update chunks cached for other PCs on your network.",
        "risk": RISK_SAFE,
        "default_on": True,
        "paths_fn": lambda: [
            os.path.join(_sysroot(), "SoftwareDistribution", "DeliveryOptimization"),
            os.path.join(_sysroot(), "ServiceProfiles", "NetworkService",
                         "AppData", "Local", "Microsoft", "Windows", "DeliveryOptimization"),
        ],
        "mode": "contents",
    },
    "thumbnail_icon_cache": {
        "label": "Thumbnail & Icon Cache",
        "description": "thumbcache_*.db and iconcache_*.db — Explorer rebuilds these on demand.",
        "risk": RISK_SAFE,
        "default_on": True,
        "paths_fn": lambda: [os.path.join(_localappdata(), "Microsoft", "Windows", "Explorer")],
        "mode": "patterns",
        "file_patterns": ["thumbcache_*.db", "iconcache_*.db"],
    },
    "recycle_bin": {
        "label": "Recycle Bin",
        "description": ("Empties the Recycle Bin. This is permanent by definition — "
                        "everything in it is already a file you deleted."),
        "risk": RISK_CAUTION,
        "default_on": False,
        "paths_fn": lambda: [],
        "mode": "recycle_bin",
    },
    "error_reports": {
        "label": "Error Reports & Crash Dumps",
        "description": "Windows Error Reporting queues, C:\\Windows\\Minidump and LocalDumps.",
        "risk": RISK_SAFE,
        "default_on": True,
        "paths_fn": lambda: [
            os.path.join(_localappdata(), "Microsoft", "Windows", "WER"),
            os.path.join(_localappdata(), "CrashDumps"),
            os.path.join(_programdata(), "Microsoft", "Windows", "WER"),
            os.path.join(_sysroot(), "Minidump"),
        ],
        "mode": "contents",
    },
    "prefetch": {
        "label": "Prefetch (report only)",
        "description": ("C:\\Windows\\Prefetch speeds up app launches. Low reclaim value "
                        "and clearing it slows the next few launches, so this target is "
                        "REPORT ONLY and is never cleaned."),
        "risk": RISK_CAUTION,
        "default_on": False,
        "report_only": True,
        "paths_fn": lambda: [os.path.join(_sysroot(), "Prefetch")],
        "mode": "contents",
    },
    "windows_old": {
        "label": "Previous Windows Installation (Windows.old)",
        "description": ("Your previous Windows install, kept so you can roll back. "
                        "Often 10-30 GB. Removing it means you can NO LONGER go back "
                        "to the previous Windows version."),
        "risk": RISK_HIGH,
        "default_on": False,
        "paths_fn": lambda: [os.path.join(
            os.environ.get("SystemDrive", "C:") + os.sep, "Windows.old")],
        "mode": "tree",
    },
    "browser_caches": {
        "label": "Browser Caches (Chrome, Edge, Firefox, Brave)",
        "description": ("Cached web content only. Cookies, history, saved passwords and "
                        "bookmarks are never touched. Close the browser first."),
        "risk": RISK_SAFE,
        "default_on": True,
        "paths_fn": _all_browser_cache_dirs,
        "mode": "tree",
    },
    "old_logs": {
        "label": f"Log Files older than {LOG_MAX_AGE_DAYS} days",
        "description": "Stale .log/.etl/.dmp files in Windows log directories.",
        "risk": RISK_SAFE,
        "default_on": True,
        "paths_fn": _old_log_files,
        "mode": "files",
    },

    # ── Sprint 3 additions ─────────────────────────────────────
    "dns_cache": {
        "label": "DNS Resolver Cache",
        "description": ("Runs ipconfig /flushdns. Clears cached name lookups, which "
                        "fixes sites resolving to a stale IP. Frees no disk space — "
                        "the cache lives in memory."),
        "risk": RISK_SAFE,
        "default_on": False,
        "paths_fn": lambda: [],
        "mode": "command",
        "command": ["ipconfig", "/flushdns"],
    },
    "leftover_programs": {
        "label": "Leftover Files from Uninstalled Programs (report only)",
        "description": ("Program folders with no matching entry in the Uninstall "
                        "registry hives — usually left by a sloppy uninstaller, but "
                        "equally often a portable app or a per-user install. That "
                        "ambiguity is why this target is REPORT ONLY and is never "
                        "cleaned; review the list and remove folders yourself."),
        "risk": RISK_CAUTION,
        "default_on": False,
        "report_only": True,
        "paths_fn": leftover_program_dirs,
        "mode": "report_dirs",
    },
    "jump_lists": {
        "label": "Jump Lists & Recent Items",
        "description": ("Recently-opened file shortcuts behind taskbar jump lists. "
                        "Clearing them empties your recent-items history; the files "
                        "themselves are untouched. Goes to the Recycle Bin."),
        "risk": RISK_CAUTION,
        "default_on": False,
        "paths_fn": _jump_list_dirs,
        "mode": "contents",
    },
    "font_cache": {
        "label": "Font Cache",
        "description": ("FontCache service data and FNTCACHE.DAT. Windows rebuilds "
                        "both on the next boot. The Font Cache service is stopped "
                        "first and restarted afterwards."),
        "risk": RISK_SAFE,
        "default_on": False,
        "paths_fn": font_cache_paths,
        "mode": "system_permanent",
        "services": ["FontCache"],
    },
    "store_cache": {
        "label": "Microsoft Store Cache",
        "description": ("Runs wsreset.exe, which resets the Store cache without "
                        "changing installed apps or sign-in. The reported size is "
                        "the Store's LocalCache folder."),
        "risk": RISK_SAFE,
        "default_on": False,
        "paths_fn": lambda: [_store_cache_dir()],
        "mode": "command",
        "command": ["wsreset.exe"],
        "size_paths": True,
    },
    "memory_dumps": {
        "label": "Memory Dumps (MEMORY.DMP, LiveKernelReports)",
        "description": ("Kernel crash dumps. A full MEMORY.DMP is routinely 8-16 GB. "
                        "Only useful for debugging a blue screen you have already "
                        "analysed — once deleted the crash cannot be investigated."),
        "risk": RISK_CAUTION,
        "default_on": False,
        "paths_fn": memory_dump_paths,
        "mode": "system_permanent",
    },
}


# ─── Sizing helpers (read-only) ────────────────────────────────
def _size_of_tree(path):
    count = size = 0
    try:
        for dirpath, _, filenames in os.walk(path):
            for f in filenames:
                try:
                    fp = os.path.join(dirpath, f)
                    if os.path.isfile(fp):
                        size += os.path.getsize(fp)
                        count += 1
                except (OSError, PermissionError):
                    pass
    except (OSError, PermissionError):
        pass
    return count, size


def recycle_bin_size():
    """(count, bytes) currently sitting in the Recycle Bin."""
    if not IS_WINDOWS:
        return 0, 0
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "$i=(New-Object -ComObject Shell.Application).NameSpace(10).Items(); "
             "$s=0; foreach($x in $i){$s+=$x.ExtendedProperty('Size')}; "
             "Write-Output \"$(@($i).Count) $s\""],
            capture_output=True, text=True, timeout=60,
            creationflags=_WIN_NO_WINDOW)
        parts = proc.stdout.strip().split()
        if len(parts) >= 2:
            return int(parts[0]), int(parts[1] or 0)
    except Exception:
        pass
    return 0, 0


def dism_analyze():
    """DISM /AnalyzeComponentStore — read-only WinSxS reclaim estimate."""
    result = {"available": False, "reclaimable": False, "output": "", "recommend": ""}
    if not IS_WINDOWS:
        result["output"] = "DISM is Windows-only (preview mode)."
        return result
    try:
        proc = subprocess.run(
            ["dism.exe", "/Online", "/Cleanup-Image", "/AnalyzeComponentStore"],
            capture_output=True, text=True, timeout=900,
            creationflags=_WIN_NO_WINDOW)
        result["output"] = (proc.stdout or "") + (proc.stderr or "")
        result["available"] = proc.returncode == 0
        for line in result["output"].splitlines():
            low = line.lower()
            if "component store cleanup recommended" in low:
                result["recommend"] = line.strip()
                result["reclaimable"] = low.strip().endswith("yes")
        if proc.returncode != 0 and "elevated" in result["output"].lower():
            result["output"] += "\nDISM requires Administrator privileges."
    except subprocess.TimeoutExpired:
        result["output"] = "DISM analysis timed out after 15 minutes."
    except FileNotFoundError:
        result["output"] = "dism.exe not found on this system."
    except Exception as e:
        result["output"] = f"DISM analysis failed: {e}"
    return result


def scan_target(key, target):
    """Size a single target. Read-only."""
    mode = target.get("mode", "contents")
    entry = {
        "key": key,
        "label": target["label"],
        "description": target["description"],
        "risk": target["risk"],
        "default_on": target["default_on"],
        "report_only": target.get("report_only", False),
        # The UI needs the mode to say truthfully whether a target is
        # recycled or permanently deleted.
        "mode": mode,
        "permanent": mode == "system_permanent",
        "paths": [],
        "count": 0,
        "bytes": 0,
        "note": "",
    }

    if mode == "recycle_bin":
        count, size = recycle_bin_size()
        entry["count"], entry["bytes"] = count, size
        entry["note"] = "Emptying the Recycle Bin is permanent."
        return entry

    if mode == "dism":
        analysis = dism_analyze()
        entry["note"] = (analysis.get("recommend")
                         or ("DISM reports no cleanup recommended."
                             if analysis["available"] else analysis["output"][:400]))
        entry["dism"] = analysis
        entry["note"] = entry["note"] or "Run as Administrator for a WinSxS estimate."
        return entry

    try:
        paths = target["paths_fn"]()
    except Exception:
        paths = []

    if mode == "command":
        # The work is a subprocess, not a delete. Size the cache it resets
        # where there is one to size, so the row is not silently blank.
        if target.get("size_paths"):
            for p in paths:
                if os.path.isdir(p):
                    count, size = _size_of_tree(p)
                    entry["count"] += count
                    entry["bytes"] += size
                    entry["paths"].append(p)
        entry["note"] = "Runs " + " ".join(target.get("command", [])) + "."
        if not entry["bytes"]:
            entry["note"] += " Frees no disk space directly."
        return entry

    if mode == "report_dirs":
        # Report only — sized so the user can judge, never cleaned.
        for p in paths:
            count, size = _size_of_tree(p)
            entry["count"] += count
            entry["bytes"] += size
            entry["paths"].append(p)
        entry["note"] = (f"{len(paths)} folder(s) with no Uninstall registry entry. "
                         f"Report only — nothing here is deleted."
                         if paths else "No unclaimed program folders found.")
        return entry

    if mode == "system_permanent":
        for p in paths:
            if os.path.isfile(p):
                try:
                    entry["bytes"] += os.path.getsize(p)
                    entry["count"] += 1
                    entry["paths"].append(p)
                except (OSError, PermissionError):
                    pass
            elif os.path.isdir(p):
                count, size = _size_of_tree(p)
                entry["count"] += count
                entry["bytes"] += size
                entry["paths"].append(p)
        entry["note"] = ("Deleted permanently, not recycled — the Recycle Bin cannot "
                         "usefully hold these and Windows regenerates them.")
        return entry

    if mode == "files":
        for fp in paths:
            try:
                if os.path.isfile(fp):
                    entry["bytes"] += os.path.getsize(fp)
                    entry["count"] += 1
            except (OSError, PermissionError):
                pass
        entry["paths"] = paths[:200]
        return entry

    if mode == "patterns":
        for base in paths:
            if not os.path.isdir(base):
                continue
            for pattern in target.get("file_patterns", []):
                for match in glob.glob(os.path.join(base, "**", pattern), recursive=True):
                    try:
                        if os.path.isfile(match):
                            entry["bytes"] += os.path.getsize(match)
                            entry["count"] += 1
                            entry["paths"].append(match)
                    except (OSError, PermissionError):
                        pass
        return entry

    # "contents" (delete what's inside) and "tree" (delete the dir itself)
    for p in paths:
        if not os.path.exists(p):
            continue
        count, size = _size_of_tree(p)
        entry["count"] += count
        entry["bytes"] += size
        entry["paths"].append(p)
    return entry


def scan_deepclean(keys=None, include_dism=False):
    """Full report phase. Deletes nothing.

    ``include_dism`` is opt-in because /AnalyzeComponentStore is slow and
    needs elevation.
    """
    log_activity("Deep Clean report started (scan only — nothing is deleted)", "TASK")
    selected = keys or list(DEEPCLEAN_TARGETS.keys())
    targets = []
    total = 0
    for key in selected:
        target = DEEPCLEAN_TARGETS.get(key)
        if not target:
            continue
        if target.get("mode") == "dism" and not include_dism:
            targets.append({
                "key": key, "label": target["label"],
                "description": target["description"], "risk": target["risk"],
                "default_on": target["default_on"], "report_only": False,
                "mode": "dism", "permanent": False,
                "paths": [], "count": 0, "bytes": 0,
                "note": "Not analyzed — enable the DISM analysis option to estimate.",
            })
            continue
        entry = scan_target(key, target)
        targets.append(entry)
        if not entry.get("report_only"):
            total += entry["bytes"]

    log_activity(
        f"Deep Clean report complete — {format_bytes(total)} reclaimable across "
        f"{len(targets)} targets", "SUCCESS")
    return {
        "status": "complete",
        "targets": targets,
        "total_bytes": total,
        "total_fmt": format_bytes(total),
        "last_scan": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "platform_supported": IS_WINDOWS,
    }
