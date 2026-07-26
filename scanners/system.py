"""System metrics, RAM details, motherboard info, and wellness tracking."""
import subprocess
import platform
import psutil
from datetime import datetime

from core.state import IS_WINDOWS, _WIN_NO_WINDOW, activity_data
from core.util import format_bytes


def get_ram_details():
    ram_info = {
        "installed_gb": round(psutil.virtual_memory().total / (1024 ** 3), 1),
        "max_capacity_gb": 0,
        "slots_used": 0,
        "slots_total": 0,
        "ram_type": "Unknown",
    }
    if IS_WINDOWS:
        try:
            result = subprocess.run(
                ["wmic", "memorychip", "get", "Capacity,SMBIOSMemoryType,DeviceLocator"],
                capture_output=True, text=True, timeout=10,
                creationflags=_WIN_NO_WINDOW
            )
            lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
            if len(lines) > 1:
                ram_info["slots_used"] = len(lines) - 1
                type_map = {"20": "DDR", "21": "DDR2", "24": "DDR3", "26": "DDR4", "34": "DDR5"}
                for line in lines[1:]:
                    parts = line.split()
                    if parts:
                        try:
                            cap = int(parts[0])
                            ram_info["max_capacity_gb"] += round(cap / (1024 ** 3), 1)
                        except (ValueError, IndexError):
                            pass
                        for p in parts:
                            if p in type_map:
                                ram_info["ram_type"] = type_map[p]
            result2 = subprocess.run(
                ["wmic", "memphysical", "get", "MaxCapacity,MemoryDevices"],
                capture_output=True, text=True, timeout=10,
                creationflags=_WIN_NO_WINDOW
            )
            lines2 = [l.strip() for l in result2.stdout.strip().splitlines() if l.strip()]
            if len(lines2) > 1:
                parts2 = lines2[1].split()
                if len(parts2) >= 2:
                    try:
                        ram_info["max_capacity_gb"] = round(int(parts2[0]) / (1024 * 1024), 1)
                        ram_info["slots_total"] = int(parts2[1])
                    except (ValueError, IndexError):
                        pass
        except Exception:
            pass
    else:
        try:
            result = subprocess.run(
                ["dmidecode", "-t", "memory"],
                capture_output=True, text=True, timeout=10
            )
            output = result.stdout
            slots_total = output.count("Memory Device")
            slots_used = slots_total - output.count("No Module Installed")
            ram_info["slots_total"] = slots_total
            ram_info["slots_used"] = slots_used
            for line in output.splitlines():
                line = line.strip()
                if line.startswith("Type:") and "DDR" in line:
                    ram_info["ram_type"] = line.split(":")[-1].strip()
                    break
                if line.startswith("Maximum Capacity:"):
                    cap_str = line.split(":")[-1].strip()
                    if "GB" in cap_str:
                        try:
                            ram_info["max_capacity_gb"] = float(cap_str.replace("GB", "").strip())
                        except ValueError:
                            pass
                    elif "TB" in cap_str:
                        try:
                            ram_info["max_capacity_gb"] = float(cap_str.replace("TB", "").strip()) * 1024
                        except ValueError:
                            pass
        except Exception:
            ram_info["slots_total"] = 2
            ram_info["slots_used"] = 1
            ram_info["max_capacity_gb"] = ram_info["installed_gb"]
            try:
                with open("/proc/meminfo", "r") as f:
                    for line in f:
                        if line.startswith("MemTotal:"):
                            kb = int(line.split()[1])
                            ram_info["installed_gb"] = round(kb / (1024 * 1024), 1)
                            break
            except Exception:
                pass
    if ram_info["max_capacity_gb"] == 0:
        ram_info["max_capacity_gb"] = ram_info["installed_gb"]
    ram_info["upgrade_recommendations"] = get_ram_upgrade_recommendations(ram_info)
    return ram_info


def get_ram_upgrade_recommendations(ram_info):
    installed = ram_info.get("installed_gb", 0)
    max_cap = ram_info.get("max_capacity_gb", 0)
    slots_total = ram_info.get("slots_total", 0)
    slots_used = ram_info.get("slots_used", 0)
    ram_type = ram_info.get("ram_type", "Unknown")
    slots_free = max(0, slots_total - slots_used)

    rec = {
        "can_upgrade": False,
        "current_summary": f"{installed} GB {ram_type} installed across {slots_used} slot(s)",
        "max_supported": f"{max_cap} GB",
        "slots_free": slots_free,
        "compatible_type": ram_type if ram_type != "Unknown" else "Check motherboard manual",
        "suggestions": [],
        "compatible_modules": [],
        "notes": [],
    }

    speed_map = {
        "DDR3": {"speeds": ["1333 MHz", "1600 MHz", "1866 MHz"], "form_factor": "240-pin DIMM (desktop) / 204-pin SO-DIMM (laptop)", "voltage": "1.5V (standard) / 1.35V (DDR3L)"},
        "DDR4": {"speeds": ["2133 MHz", "2400 MHz", "2666 MHz", "3000 MHz", "3200 MHz", "3600 MHz"], "form_factor": "288-pin DIMM (desktop) / 260-pin SO-DIMM (laptop)", "voltage": "1.2V"},
        "DDR5": {"speeds": ["4800 MHz", "5200 MHz", "5600 MHz", "6000 MHz", "6400 MHz", "7200 MHz"], "form_factor": "288-pin DIMM (desktop) / 262-pin SO-DIMM (laptop)", "voltage": "1.1V"},
        "DDR2": {"speeds": ["667 MHz", "800 MHz"], "form_factor": "240-pin DIMM (desktop)", "voltage": "1.8V"},
        "DDR": {"speeds": ["400 MHz"], "form_factor": "184-pin DIMM (desktop)", "voltage": "2.5V"},
    }

    if ram_type in speed_map:
        spec = speed_map[ram_type]
        rec["compatible_modules"] = [
            {"spec": f"{ram_type}", "speeds": spec["speeds"], "form_factor": spec["form_factor"], "voltage": spec["voltage"]},
        ]

    if max_cap > installed and slots_free > 0:
        rec["can_upgrade"] = True
        upgrade_amount = max_cap - installed
        per_stick = upgrade_amount / slots_free if slots_free > 0 else upgrade_amount

        common_stick_sizes = [4, 8, 16, 32, 64]
        best_stick = min(common_stick_sizes, key=lambda x: abs(x - per_stick))
        if best_stick < per_stick:
            idx = common_stick_sizes.index(best_stick)
            if idx + 1 < len(common_stick_sizes):
                best_stick = common_stick_sizes[idx + 1]

        rec["suggestions"].append({
            "option": f"Add {slots_free}x {best_stick}GB {ram_type} module(s)",
            "result": f"Total: {installed + (best_stick * slots_free)} GB",
            "difficulty": "Easy - empty slot(s) available",
        })

        if slots_used > 0:
            max_per_slot_sizes = [s for s in common_stick_sizes if s * slots_total <= max_cap]
            if max_per_slot_sizes:
                max_stick = max_per_slot_sizes[-1]
                if max_stick * slots_total > installed:
                    rec["suggestions"].append({
                        "option": f"Replace all with {slots_total}x {max_stick}GB {ram_type} module(s)",
                        "result": f"Total: {max_stick * slots_total} GB (maximum)",
                        "difficulty": "Moderate - requires removing existing RAM",
                    })

    elif max_cap > installed and slots_free == 0 and slots_total > 0:
        rec["can_upgrade"] = True
        max_per_slot_sizes = [s for s in [4, 8, 16, 32, 64] if s * slots_total <= max_cap]
        if max_per_slot_sizes:
            max_stick = max_per_slot_sizes[-1]
            if max_stick * slots_total > installed:
                rec["suggestions"].append({
                    "option": f"Replace with {slots_total}x {max_stick}GB {ram_type} module(s)",
                    "result": f"Total: {max_stick * slots_total} GB",
                    "difficulty": "Moderate - must remove existing modules",
                })
        rec["notes"].append("All RAM slots are occupied. Upgrading requires replacing existing modules with higher capacity ones.")

    elif max_cap <= installed:
        rec["notes"].append("Your system is already at maximum RAM capacity.")

    if ram_type == "Unknown":
        rec["notes"].append("RAM type could not be detected. Check your motherboard manual or use a tool like CPU-Z to identify the correct RAM type before purchasing.")
    else:
        rec["notes"].append(f"Always buy {ram_type} modules — other types (e.g., {'DDR4' if ram_type == 'DDR5' else 'DDR5'}) are physically incompatible and will not fit.")

    if slots_used >= 2:
        rec["notes"].append("For best performance, install RAM in matched pairs (same capacity, speed, and brand) to enable dual-channel mode.")

    if ram_type in ["DDR3", "DDR2", "DDR"]:
        rec["notes"].append(f"{ram_type} is an older standard. Consider whether upgrading the entire system (motherboard + CPU + RAM) might be more cost-effective.")

    return rec


def get_motherboard_info():
    mb_info = {
        "manufacturer": "Unknown",
        "product": "Unknown",
        "serial_number": "Unknown",
    }
    if IS_WINDOWS:
        try:
            result = subprocess.run(
                ["wmic", "baseboard", "get", "Manufacturer,Product,SerialNumber"],
                capture_output=True, text=True, timeout=10,
                creationflags=_WIN_NO_WINDOW
            )
            lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
            if len(lines) > 1:
                parts = lines[1].split(None, 2)
                if len(parts) >= 1:
                    mb_info["manufacturer"] = parts[0]
                if len(parts) >= 2:
                    mb_info["product"] = parts[1]
                if len(parts) >= 3:
                    mb_info["serial_number"] = parts[2]
        except Exception:
            pass
    else:
        try:
            result = subprocess.run(
                ["dmidecode", "-t", "baseboard"],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("Manufacturer:"):
                    mb_info["manufacturer"] = line.split(":", 1)[-1].strip()
                elif line.startswith("Product Name:"):
                    mb_info["product"] = line.split(":", 1)[-1].strip()
                elif line.startswith("Serial Number:"):
                    mb_info["serial_number"] = line.split(":", 1)[-1].strip()
        except Exception:
            mb_info["manufacturer"] = "Linux System"
            mb_info["product"] = platform.machine()
    return mb_info


def get_system_metrics():
    cpu_percent = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("C:\\" if IS_WINDOWS else "/")
    net = psutil.net_io_counters()
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    uptime = datetime.now() - boot_time

    try:
        temps = psutil.sensors_temperatures()
        cpu_temp = None
        if temps:
            for name, entries in temps.items():
                if entries:
                    cpu_temp = entries[0].current
                    break
    except (AttributeError, Exception):
        cpu_temp = None

    processes = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            info = proc.info
            if info["cpu_percent"] and info["cpu_percent"] > 0.1:
                processes.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    processes.sort(key=lambda x: x.get("cpu_percent", 0), reverse=True)

    return {
        "cpu": {
            "percent": cpu_percent,
            "cores": psutil.cpu_count(logical=False) or 1,
            "threads": psutil.cpu_count(logical=True) or 1,
            "freq": psutil.cpu_freq().current if psutil.cpu_freq() else 0,
            "temp": cpu_temp,
        },
        "memory": {
            "total": memory.total,
            "used": memory.used,
            "available": memory.available,
            "percent": memory.percent,
            "total_fmt": format_bytes(memory.total),
            "used_fmt": format_bytes(memory.used),
            "available_fmt": format_bytes(memory.available),
        },
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": disk.percent,
            "total_fmt": format_bytes(disk.total),
            "used_fmt": format_bytes(disk.used),
            "free_fmt": format_bytes(disk.free),
        },
        "network": {
            "bytes_sent": format_bytes(net.bytes_sent),
            "bytes_recv": format_bytes(net.bytes_recv),
            "packets_sent": net.packets_sent,
            "packets_recv": net.packets_recv,
        },
        "system": {
            "platform": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor() or "N/A",
            "uptime": str(uptime).split(".")[0],
            "boot_time": boot_time.strftime("%Y-%m-%d %H:%M"),
        },
        "ram_details": get_ram_details(),
        "motherboard": get_motherboard_info(),
        "top_processes": processes[:10],
    }


def update_wellness():
    import random
    now = datetime.now()
    hour = now.hour
    if 9 <= hour <= 17:
        activity_data["active_minutes"] += 1
        if random.random() < 0.1:
            activity_data["idle_minutes"] += 1
    activity_data["last_activity"] = now.isoformat()
    active = activity_data["active_minutes"]
    idle = activity_data["idle_minutes"]
    breaks = activity_data["break_count"]
    score = min(100, max(0, 85 - (active // 60) * 2 + breaks * 5 + (idle // 10)))
    activity_data["wellness_score"] = score
