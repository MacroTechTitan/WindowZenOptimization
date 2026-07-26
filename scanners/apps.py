"""Installed-application inventory and uninstall helpers (App & Bloat Manager)."""
from core.state import IS_WINDOWS


_BLOAT_KEYWORDS = ["trial", "toolbar", "helper", "oem", "updater", "wizard", "coupon",
                   "browser", "search", "driver update", "driver booster", "cleaner",
                   "optimizer", "speedup", "speed up", "tune", "tuneup", "booster", "lite"]

_SAFE_PUBLISHERS = ["microsoft", "intel", "amd", "nvidia", "realtek", "apple", "google",
                    "adobe", "logitech", "autodesk", "valve", "epic games", "blizzard"]

_SKIP_DISPLAY_NAMES = ["microsoft visual c++", "microsoft .net", "windows sdk",
                       "directx", "visual studio redistributable", "vcredist",
                       "microsoft edge webview", "windows driver", "security update"]


def _is_likely_bloat(app):
    name = (app.get("name") or "").lower()
    publisher = (app.get("publisher") or "").lower()
    size_mb = app.get("size_mb") or 0

    for skip in _SKIP_DISPLAY_NAMES:
        if skip in name:
            return False, "system"

    for kw in _BLOAT_KEYWORDS:
        if kw in name:
            return True, "likely_bloat"

    if not publisher:
        return False, "unknown"

    for safe in _SAFE_PUBLISHERS:
        if safe in publisher:
            return False, "trusted"

    if size_mb > 2048:
        return False, "large_app"

    return False, "normal"


def _scan_apps_from_registry():
    apps = []
    if not IS_WINDOWS:
        return _get_demo_apps()

    try:
        import winreg
        reg_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]
        seen = set()
        for hive, path in reg_paths:
            try:
                key = winreg.OpenKey(hive, path)
                count = winreg.QueryInfoKey(key)[0]
                for i in range(count):
                    try:
                        sub_name = winreg.EnumKey(key, i)
                        sub_key = winreg.OpenKey(key, sub_name)
                        def _rv(k, n, default=""):
                            try:
                                return winreg.QueryValueEx(k, n)[0] or default
                            except Exception:
                                return default
                        display_name = _rv(sub_key, "DisplayName")
                        if not display_name or display_name in seen:
                            winreg.CloseKey(sub_key)
                            continue
                        seen.add(display_name)
                        size_bytes = 0
                        try:
                            size_bytes = int(_rv(sub_key, "EstimatedSize") or 0) * 1024
                        except Exception:
                            pass
                        install_date = _rv(sub_key, "InstallDate")
                        if install_date and len(install_date) == 8:
                            try:
                                install_date = f"{install_date[:4]}-{install_date[4:6]}-{install_date[6:]}"
                            except Exception:
                                pass
                        app_entry = {
                            "name": display_name,
                            "publisher": _rv(sub_key, "Publisher"),
                            "version": _rv(sub_key, "DisplayVersion"),
                            "install_date": install_date,
                            "install_location": _rv(sub_key, "InstallLocation"),
                            "uninstall_cmd": _rv(sub_key, "UninstallString"),
                            "size_mb": round(size_bytes / (1024 * 1024), 1) if size_bytes else 0,
                        }
                        is_bloat, bloat_tag = _is_likely_bloat(app_entry)
                        app_entry["is_bloat"] = is_bloat
                        app_entry["tag"] = bloat_tag
                        apps.append(app_entry)
                        winreg.CloseKey(sub_key)
                    except Exception:
                        pass
                winreg.CloseKey(key)
            except Exception:
                pass
    except ImportError as e:
        # winreg is unavailable — on Windows this is a real failure, not a cue to
        # fabricate a demo app list.
        raise RuntimeError(f"Registry access is unavailable: {e}")

    apps.sort(key=lambda x: x["name"].lower())
    return apps


def _get_demo_apps():
    return [
        {"name": "Discord", "publisher": "Discord Inc.", "version": "1.0.9170", "install_date": "2024-03-15",
         "install_location": "C:\\Users\\User\\AppData\\Local\\Discord", "uninstall_cmd": "C:\\Users\\User\\AppData\\Local\\Discord\\Update.exe --uninstall",
         "size_mb": 312.4, "is_bloat": False, "tag": "normal"},
        {"name": "VLC media player", "publisher": "VideoLAN", "version": "3.0.20", "install_date": "2023-11-01",
         "install_location": "C:\\Program Files\\VideoLAN\\VLC", "uninstall_cmd": "C:\\Program Files\\VideoLAN\\VLC\\uninstall.exe",
         "size_mb": 84.2, "is_bloat": False, "tag": "normal"},
        {"name": "Google Chrome", "publisher": "Google LLC", "version": "124.0.6367.78", "install_date": "2024-04-20",
         "install_location": "C:\\Program Files\\Google\\Chrome", "uninstall_cmd": "C:\\Program Files\\Google\\Chrome\\Application\\124.0.6367.78\\Installer\\setup.exe --uninstall",
         "size_mb": 720.8, "is_bloat": False, "tag": "trusted"},
        {"name": "Spotify", "publisher": "Spotify AB", "version": "1.2.31.1205", "install_date": "2024-01-10",
         "install_location": "C:\\Users\\User\\AppData\\Roaming\\Spotify", "uninstall_cmd": "C:\\Users\\User\\AppData\\Roaming\\Spotify\\Spotify.exe --uninstall",
         "size_mb": 230.5, "is_bloat": False, "tag": "normal"},
        {"name": "Driver Booster 11", "publisher": "IObit", "version": "11.6.0.108", "install_date": "2023-06-05",
         "install_location": "C:\\Program Files (x86)\\IObit\\Driver Booster", "uninstall_cmd": "C:\\Program Files (x86)\\IObit\\Driver Booster\\unins000.exe",
         "size_mb": 185.3, "is_bloat": True, "tag": "likely_bloat"},
        {"name": "PC App Store", "publisher": "Unknown Vendor", "version": "3.4.1", "install_date": "2022-09-12",
         "install_location": "", "uninstall_cmd": "",
         "size_mb": 0, "is_bloat": True, "tag": "likely_bloat"},
        {"name": "Free PDF Toolbar", "publisher": "PDF Toolkit", "version": "2.1.0", "install_date": "2022-04-01",
         "install_location": "", "uninstall_cmd": "C:\\Program Files\\PDF Toolbar\\uninst.exe",
         "size_mb": 12.0, "is_bloat": True, "tag": "likely_bloat"},
        {"name": "Microsoft Visual C++ 2019 Redistributable (x64)", "publisher": "Microsoft Corporation", "version": "14.29.30153",
         "install_date": "2023-01-15", "install_location": "", "uninstall_cmd": "MsiExec.exe /X{...}",
         "size_mb": 22.1, "is_bloat": False, "tag": "system"},
        {"name": "Steam", "publisher": "Valve Corporation", "version": "2.10.91.91", "install_date": "2023-08-20",
         "install_location": "C:\\Program Files (x86)\\Steam", "uninstall_cmd": "C:\\Program Files (x86)\\Steam\\uninstall.exe",
         "size_mb": 1024.6, "is_bloat": False, "tag": "trusted"},
        {"name": "7-Zip 23.01", "publisher": "Igor Pavlov", "version": "23.01.0", "install_date": "2023-12-01",
         "install_location": "C:\\Program Files\\7-Zip", "uninstall_cmd": "C:\\Program Files\\7-Zip\\Uninstall.exe",
         "size_mb": 5.8, "is_bloat": False, "tag": "normal"},
    ]


_UNINSTALL_REG_PATHS = [
    ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ("HKLM", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ("HKCU", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
]


def _build_uninstall_invocation(cmd):
    """Turn a registry UninstallString into (exe, args) suitable for ShellExecuteW.

    MSI uninstall strings (MsiExec.exe /X{GUID} or /I{GUID}) are normalised to a
    quiet-with-basic-UI msiexec call. Everything else is split into a program path
    and its arguments, honouring a leading quoted path.
    """
    import re
    s = (cmd or "").strip()

    guid_match = re.search(r"\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}", s)
    if guid_match and re.search(r"msiexec", s, re.IGNORECASE) and re.search(r"/[xi]\s*\{", s, re.IGNORECASE):
        return "msiexec.exe", f"/x {guid_match.group(0)} /qb"

    if s.startswith('"'):
        end = s.find('"', 1)
        if end != -1:
            return s[1:end], s[end + 1:].strip()
        return s.strip('"'), ""

    # Unquoted path that may itself contain spaces: cut at the first ".exe".
    low = s.lower()
    idx = low.find(".exe")
    if idx != -1:
        return s[:idx + 4], s[idx + 4:].strip()

    parts = s.split(None, 1)
    return parts[0], (parts[1] if len(parts) > 1 else "")


def _registry_has_display_name(display_name):
    """Return True if any Uninstall key still lists this exact DisplayName."""
    import winreg
    hive_map = {"HKLM": winreg.HKEY_LOCAL_MACHINE, "HKCU": winreg.HKEY_CURRENT_USER}
    target = (display_name or "").strip().lower()
    if not target:
        return False
    for hive_name, path in _UNINSTALL_REG_PATHS:
        try:
            key = winreg.OpenKey(hive_map[hive_name], path)
        except OSError:
            continue
        try:
            count = winreg.QueryInfoKey(key)[0]
            for i in range(count):
                try:
                    sub = winreg.OpenKey(key, winreg.EnumKey(key, i))
                except OSError:
                    continue
                try:
                    dn = winreg.QueryValueEx(sub, "DisplayName")[0]
                    if dn and str(dn).strip().lower() == target:
                        return True
                except OSError:
                    pass
                finally:
                    winreg.CloseKey(sub)
        finally:
            winreg.CloseKey(key)
    return False

