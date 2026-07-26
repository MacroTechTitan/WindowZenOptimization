"""File organizer scan: zero-length, duplicates, stray installers."""
import os
import hashlib
from datetime import datetime

from core.state import file_organizer_results
from core.util import log_activity, format_bytes


def run_file_organizer_scan(custom_folder=""):
    file_organizer_results["status"] = "scanning"
    log_activity("Starting file organizer scan...", "TASK")
    home = os.path.expanduser("~")
    if custom_folder and os.path.isdir(custom_folder):
        scan_dirs = [custom_folder]
        log_activity(f"Scanning custom folder: {custom_folder}")
    else:
        scan_dirs = [
            os.path.join(home, "Documents"),
            os.path.join(home, "Downloads"),
            os.path.join(home, "Desktop"),
        ]

    zero_length = []
    for scan_dir in scan_dirs:
        if not os.path.isdir(scan_dir):
            continue
        try:
            for dirpath, dirnames, filenames in os.walk(scan_dir):
                for f in filenames:
                    try:
                        fp = os.path.join(dirpath, f)
                        if os.path.isfile(fp) and os.path.getsize(fp) == 0:
                            zero_length.append({"path": fp, "size": 0, "name": f})
                    except (OSError, PermissionError):
                        pass
        except (OSError, PermissionError):
            pass
    file_organizer_results["zero_length"] = zero_length[:100]
    log_activity(f"Found {len(zero_length)} zero-length files.")

    hash_map = {}
    duplicates = []
    dup_dirs = scan_dirs if custom_folder else [
        os.path.join(home, "Documents"),
        os.path.join(home, "Downloads"),
    ]
    for scan_dir in dup_dirs:
        if not os.path.isdir(scan_dir):
            continue
        try:
            for dirpath, dirnames, filenames in os.walk(scan_dir):
                for f in filenames:
                    try:
                        fp = os.path.join(dirpath, f)
                        if not os.path.isfile(fp):
                            continue
                        fsize = os.path.getsize(fp)
                        if fsize == 0 or fsize > 100 * 1024 * 1024:
                            continue
                        h = hashlib.md5()
                        with open(fp, "rb") as fh:
                            chunk = fh.read(8192)
                            while chunk:
                                h.update(chunk)
                                chunk = fh.read(8192)
                        file_hash = h.hexdigest()
                        if file_hash in hash_map:
                            duplicates.append({
                                "path": fp,
                                "size": fsize,
                                "size_fmt": format_bytes(fsize),
                                "name": f,
                                "duplicate_of": hash_map[file_hash],
                            })
                        else:
                            hash_map[file_hash] = fp
                    except (OSError, PermissionError, IOError):
                        pass
        except (OSError, PermissionError):
            pass
    file_organizer_results["duplicates"] = duplicates[:100]
    log_activity(f"Found {len(duplicates)} duplicate files.")

    installers = []
    downloads_dir = os.path.join(home, "Downloads")
    if os.path.isdir(downloads_dir):
        try:
            for f in os.listdir(downloads_dir):
                fp = os.path.join(downloads_dir, f)
                if os.path.isfile(fp) and f.lower().endswith((".exe", ".msi")):
                    try:
                        fsize = os.path.getsize(fp)
                        installers.append({
                            "path": fp,
                            "size": fsize,
                            "size_fmt": format_bytes(fsize),
                            "name": f,
                        })
                    except (OSError, PermissionError):
                        pass
        except (OSError, PermissionError):
            pass
    file_organizer_results["installers"] = installers[:100]
    file_organizer_results["last_scan"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_organizer_results["status"] = "complete"
    log_activity(f"Found {len(installers)} software installers.", "SUCCESS")
    log_activity("File organizer scan complete.", "SUCCESS")

