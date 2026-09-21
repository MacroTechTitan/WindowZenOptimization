"""Reversible startup-item enable/disable via the Windows StartupApproved key.

This is the same mechanism Task Manager uses: the Run entry itself is never
touched, and a 12-byte binary flag under
...\\Explorer\\StartupApproved\\Run marks it enabled or disabled. The first
byte is even (0x02) for enabled and odd (0x03) for disabled; for disabled
entries the remaining 8 bytes are the FILETIME it was disabled.
"""
import struct
import time

RUN_PATH = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
APPROVED_PATH = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"

ADMIN_REQUIRED_MSG = "Administrator rights required for all-users startup items"

# Seconds between 1601-01-01 (FILETIME epoch) and 1970-01-01 (Unix epoch).
_FILETIME_EPOCH_DELTA = 11644473600


class StartupToggleError(Exception):
    """A toggle failed; `message` is safe to show to the user."""

    def __init__(self, message, status=500):
        super().__init__(message)
        self.message = message
        self.status = status


def _hive(winreg, hive_name):
    return {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}.get(
        hive_name, winreg.HKEY_CURRENT_USER)


def _approved_value(enabled):
    if enabled:
        return bytes([0x02]) + bytes(11)
    filetime = int((time.time() + _FILETIME_EPOCH_DELTA) * 10_000_000)
    return bytes([0x03, 0, 0, 0]) + struct.pack("<Q", filetime)


def read_approved_states(winreg, hive_name):
    """Return {value_name: enabled_bool} for every StartupApproved flag in a hive.
    Items without a flag are enabled (Windows' default)."""
    states = {}
    try:
        key = winreg.OpenKey(_hive(winreg, hive_name), APPROVED_PATH)
    except OSError:
        return states
    try:
        i = 0
        while True:
            try:
                name, value, vtype = winreg.EnumValue(key, i)
            except OSError:
                break
            if vtype == winreg.REG_BINARY and value:
                states[name] = (value[0] & 1) == 0
            i += 1
    finally:
        winreg.CloseKey(key)
    return states


def set_startup_enabled(name, hive_name, enabled, path=""):
    """Enable or disable a Run entry by writing its StartupApproved flag.

    The Run value is only ever read, never deleted. If it is missing (e.g. an
    entry removed by an older build) and `path` is supplied, enabling
    recreates it so the item can come back.
    Raises StartupToggleError with a user-facing message on failure."""
    import winreg

    reg_hive = _hive(winreg, hive_name)
    try:
        # Confirm the Run entry exists (or restore it) before flagging it.
        try:
            with winreg.OpenKey(reg_hive, RUN_PATH) as run_key:
                winreg.QueryValueEx(run_key, name)
        except FileNotFoundError:
            if not (enabled and path):
                raise StartupToggleError(f"Startup item '{name}' was not found in {hive_name}\\Run", 404)
            with winreg.CreateKeyEx(reg_hive, RUN_PATH, 0, winreg.KEY_SET_VALUE) as run_key:
                winreg.SetValueEx(run_key, name, 0, winreg.REG_SZ, path)

        with winreg.CreateKeyEx(reg_hive, APPROVED_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_BINARY, _approved_value(enabled))
    except PermissionError:
        if hive_name == "HKLM":
            raise StartupToggleError(ADMIN_REQUIRED_MSG, 403)
        raise StartupToggleError(f"Access denied writing startup settings for '{name}'", 403)
    except StartupToggleError:
        raise
    except OSError as e:
        raise StartupToggleError(f"Registry error toggling '{name}': {e}", 500)

    # Read back so we never report a change that didn't stick.
    if read_approved_states(winreg, hive_name).get(name, True) != bool(enabled):
        raise StartupToggleError(f"Toggle for '{name}' did not persist in the registry", 500)
