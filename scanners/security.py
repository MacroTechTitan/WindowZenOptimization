"""Local security scan: open ports, active connections, public IP."""
import json
import socket
import urllib.request
from datetime import datetime

import psutil

from core.state import security_data
from core.util import log_activity


def run_security_scan():
    log_activity("Starting security scan...", "TASK")

    common_ports = [21, 22, 23, 25, 80, 135, 139, 443, 445, 3389, 8080]
    open_ports = []
    for port in common_ports:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("127.0.0.1", port))
            if result == 0:
                service_map = {
                    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP",
                    80: "HTTP", 135: "RPC", 139: "NetBIOS", 443: "HTTPS",
                    445: "SMB", 3389: "RDP", 8080: "HTTP-Proxy"
                }
                open_ports.append({
                    "port": port,
                    "service": service_map.get(port, "Unknown"),
                    "status": "open"
                })
            sock.close()
        except Exception:
            pass
    security_data["open_ports"] = open_ports
    log_activity(f"Port scan complete. {len(open_ports)} open ports found.")

    connections = []
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.status == "ESTABLISHED" and conn.raddr:
                connections.append({
                    "local_address": f"{conn.laddr.ip}:{conn.laddr.port}",
                    "remote_address": f"{conn.raddr.ip}:{conn.raddr.port}",
                    "status": conn.status,
                    "pid": conn.pid,
                })
    except (psutil.AccessDenied, Exception):
        pass
    security_data["active_connections"] = connections[:50]
    log_activity(f"Found {len(connections)} active connections.")

    try:
        req = urllib.request.Request("https://api.ipify.org?format=json", headers={"User-Agent": "SystemOptimizer/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            security_data["public_ip"] = data.get("ip", "Unknown")
    except Exception:
        security_data["public_ip"] = "Unable to determine"

    security_data["last_scan"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_activity("Security scan complete.", "SUCCESS")

