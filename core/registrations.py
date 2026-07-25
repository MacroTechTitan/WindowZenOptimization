"""Download registration persistence."""
import os
import json
import threading

REGISTRATIONS_FILE = "registrations.json"
_reg_lock = threading.Lock()


def load_registrations():
    if os.path.exists(REGISTRATIONS_FILE):
        try:
            with open(REGISTRATIONS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_registrations(data):
    try:
        with open(REGISTRATIONS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass
