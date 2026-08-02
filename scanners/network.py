"""Network diagnostics helpers for the Internet Optimizer.

Read-only probes plus the small amount of state we must persist so a DNS
or MTU change can be reverted (previous values are saved before any change
is applied).

Deliberately NOT here: netsh advfirewall reset. It is out of scope and
would irreversibly destroy every firewall rule on the machine.
"""
import os
import re
import json
import subprocess
import threading

from core.state import IS_WINDOWS, _WIN_NO_WINDOW, BASE_DIR
from core.util import log_activity

NETWORK_STATE_FILE = os.path.join(BASE_DIR, "network_state.json")
_state_lock = threading.Lock()

# DNS presets offered in the UI.
DNS_PRESETS = {
    "cloudflare": {"label": "Cloudflare", "servers": ["1.1.1.1", "1.0.0.1"]},
    "google": {"label": "Google", "servers": ["8.8.8.8", "8.8.4.4"]},
    "quad9": {"label": "Quad9", "servers": ["9.9.9.9", "149.112.112.112"]},
    "dhcp": {"label": "Restore to DHCP (automatic)", "servers": []},
}

BENCHMARK_SERVERS = ["1.1.1.1", "8.8.8.8", "9.9.9.9"]
BENCHMARK_DOMAINS = ["example.com", "wikipedia.org", "github.com",
                     "cloudflare.com", "microsoft.com"]

MTU_PROBE_HOST = "8.8.8.8"
IP_HEADER_OVERHEAD = 28          # 20 byte IP header + 8 byte ICMP header


# ─── Persisted previous values ─────────────────────────────────
def load_network_state():
    try:
        if os.path.exists(NETWORK_STATE_FILE):
            with open(NETWORK_STATE_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {"previous_dns": {}, "previous_mtu": {}}


def save_network_state(state):
    try:
        with open(NETWORK_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        log_activity(f"Could not persist network state: {e}", "WARN")


def remember_dns(adapter, servers, dhcp):
    with _state_lock:
        state = load_network_state()
        state.setdefault("previous_dns", {})
        # Never overwrite the original capture with our own change.
        if adapter not in state["previous_dns"]:
            state["previous_dns"][adapter] = {"servers": servers, "dhcp": dhcp}
            save_network_state(state)


def remember_mtu(adapter, mtu):
    with _state_lock:
        state = load_network_state()
        state.setdefault("previous_mtu", {})
        if adapter not in state["previous_mtu"]:
            state["previous_mtu"][adapter] = mtu
            save_network_state(state)


# ─── Subprocess helper ─────────────────────────────────────────
def run_cmd(args, timeout=30):
    """Run a command non-interactively and return (rc, output)."""
    if not IS_WINDOWS:
        return 0, f"[preview mode] would run: {' '.join(args)}"
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                              creationflags=_WIN_NO_WINDOW)
        return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return -1, f"Timed out after {timeout}s"
    except FileNotFoundError:
        return -1, f"{args[0]} not found"
    except Exception as e:
        return -1, str(e)


# ─── Adapters, DNS, MTU ────────────────────────────────────────
def list_adapters():
    """Connected/known network interfaces with their admin+connect state."""
    adapters = []
    if not IS_WINDOWS:
        return [{"name": "Ethernet", "state": "Connected", "admin": "Enabled",
                 "type": "Dedicated"}]
    rc, out = run_cmd(["netsh", "interface", "show", "interface"])
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[0] in ("Admin", "Administrateur") or set(line.strip()) == {"-"}:
            continue
        if parts[0] not in ("Enabled", "Disabled"):
            continue
        adapters.append({
            "admin": parts[0],
            "state": parts[1],
            "type": parts[2],
            "name": " ".join(parts[3:]),
        })
    return adapters


def dns_per_adapter():
    """Configured DNS servers per interface, and whether they came from DHCP."""
    result = []
    if not IS_WINDOWS:
        return [{"adapter": "Ethernet", "servers": ["1.1.1.1"], "dhcp": False}]
    rc, out = run_cmd(["netsh", "interface", "ipv4", "show", "dnsservers"])
    current = None
    for raw in out.splitlines():
        line = raw.strip()
        m = re.match(r'Configuration for interface "(.+)"', line)
        if m:
            current = {"adapter": m.group(1), "servers": [], "dhcp": False}
            result.append(current)
            continue
        if current is None:
            continue
        if "DHCP" in line and "Statically" not in line:
            current["dhcp"] = True
        for ip in re.findall(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", line):
            if ip not in current["servers"]:
                current["servers"].append(ip)
    return result


def mtu_per_adapter():
    """Current MTU per IPv4 subinterface."""
    result = []
    if not IS_WINDOWS:
        return [{"adapter": "Ethernet", "mtu": 1500}]
    rc, out = run_cmd(["netsh", "interface", "ipv4", "show", "subinterfaces"])
    for raw in out.splitlines():
        line = raw.rstrip()
        parts = line.split()
        if len(parts) < 5 or not parts[0].isdigit():
            continue
        try:
            mtu = int(parts[0])
        except ValueError:
            continue
        result.append({"adapter": " ".join(parts[4:]), "mtu": mtu})
    return result


def winsock_catalog():
    """Winsock LSP catalog entries (netsh winsock show catalog)."""
    entries = []
    if not IS_WINDOWS:
        return {"entries": [{"name": "MSAFD Tcpip [TCP/IP]", "type": "Protocol"}],
                "count": 1, "truncated": False}
    rc, out = run_cmd(["netsh", "winsock", "show", "catalog"], timeout=60)
    for raw in out.splitlines():
        line = raw.strip()
        m = re.match(r"^(Winsock Catalog Provider Entry|Name Space Provider Entry)", line)
        if m:
            continue
        m = re.match(r"^(Description|Entry Type|Provider Path|Name Space Provider Id)\s*:\s*(.+)$", line)
        if m and m.group(1) == "Description":
            entries.append({"name": m.group(2).strip(), "type": "Protocol"})
    truncated = len(entries) > 60
    return {"entries": entries[:60], "count": len(entries), "truncated": truncated}


# ─── DNS benchmark ─────────────────────────────────────────────
_PS_BENCH = r"""
$ErrorActionPreference = 'SilentlyContinue'
$servers = @({servers})
$domains = @({domains})
$out = @()
foreach ($s in $servers) {{
  $times = @()
  $fails = 0
  foreach ($d in $domains) {{
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $r = $null
    try {{ $r = Resolve-DnsName -Name $d -Server $s -Type A -DnsOnly -QuickTimeout -ErrorAction Stop }} catch {{ }}
    $sw.Stop()
    if ($r) {{ $times += $sw.Elapsed.TotalMilliseconds }} else {{ $fails++ }}
  }}
  $avg = if ($times.Count -gt 0) {{ [math]::Round(($times | Measure-Object -Average).Average, 1) }} else {{ -1 }}
  $out += [pscustomobject]@{{ server = $s; avg_ms = $avg; ok = $times.Count; failed = $fails }}
}}
$out | ConvertTo-Json -Compress
"""


def dns_benchmark(extra_servers=None):
    """Time a fixed domain set against the public resolvers plus current DNS."""
    servers = list(BENCHMARK_SERVERS)
    for s in (extra_servers or []):
        if s and s not in servers:
            servers.append(s)

    if not IS_WINDOWS:
        demo = [{"server": s, "avg_ms": 20.0 + i * 5, "ok": len(BENCHMARK_DOMAINS),
                 "failed": 0, "current": False} for i, s in enumerate(servers)]
        return {"results": demo, "recommendation": demo[0]["server"],
                "domains": BENCHMARK_DOMAINS, "demo": True}

    script = _PS_BENCH.format(
        servers=",".join(f"'{s}'" for s in servers),
        domains=",".join(f"'{d}'" for d in BENCHMARK_DOMAINS))
    rc, out = run_cmd(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                      timeout=180)
    results = []
    try:
        parsed = json.loads(out)
        if isinstance(parsed, dict):
            parsed = [parsed]
        for row in parsed:
            results.append({
                "server": row.get("server"),
                "avg_ms": row.get("avg_ms", -1),
                "ok": row.get("ok", 0),
                "failed": row.get("failed", 0),
            })
    except Exception:
        return {"results": [], "recommendation": None, "domains": BENCHMARK_DOMAINS,
                "error": f"Benchmark failed: {out[:300]}"}

    current = set(extra_servers or [])
    for r in results:
        r["current"] = r["server"] in current
        r["preset"] = next((k for k, v in DNS_PRESETS.items()
                            if r["server"] in v["servers"]), None)

    usable = [r for r in results if r["avg_ms"] and r["avg_ms"] > 0]
    usable.sort(key=lambda r: r["avg_ms"])
    unusable = [r for r in results if r not in usable]
    ordered = usable + unusable

    recommendation = None
    note = ""
    if usable:
        best = usable[0]
        recommendation = best["server"]
        cur = next((r for r in usable if r["current"]), None)
        if cur and cur["server"] == best["server"]:
            note = "Your current DNS is already the fastest of those tested."
        elif cur:
            delta = cur["avg_ms"] - best["avg_ms"]
            note = (f"{best['server']} answered {delta:.1f} ms faster on average than "
                    f"your current DNS. Real-world browsing gains are usually small "
                    f"and most lookups are cached.")
        else:
            note = (f"{best['server']} was fastest across {len(BENCHMARK_DOMAINS)} "
                    f"lookups.")

    return {"results": ordered, "recommendation": recommendation,
            "domains": BENCHMARK_DOMAINS, "note": note, "demo": False}


# ─── MTU probe ─────────────────────────────────────────────────
def _ping_fits(payload, host, timeout=8):
    """True when a payload-sized packet crosses the path without fragmenting."""
    rc, out = run_cmd(["ping", "-f", "-l", str(payload), "-n", "1", "-w", "2000", host],
                      timeout=timeout)
    low = out.lower()
    if "needs to be fragmented" in low or "packet needs to be fragmented" in low:
        return False
    if "100% loss" in low or "request timed out" in low or "general failure" in low:
        return False
    return rc == 0 and ("ttl=" in low or "bytes=" in low)


def mtu_probe(host=MTU_PROBE_HOST):
    """Binary-search the largest unfragmented payload; MTU = payload + 28."""
    current = mtu_per_adapter()
    if not IS_WINDOWS:
        return {"optimal_mtu": 1500, "optimal_payload": 1472, "host": host,
                "current": current, "demo": True,
                "note": "Preview mode — no probe was run."}

    lo, hi = 1200, 1472          # 1472 payload == 1500 MTU, the Ethernet default
    if not _ping_fits(lo, host):
        return {"optimal_mtu": None, "optimal_payload": None, "host": host,
                "current": current, "demo": False,
                "note": (f"Could not reach {host} with a {lo}-byte unfragmented ping. "
                         f"The host may block ICMP, or you are offline — no MTU "
                         f"recommendation can be made.")}

    if _ping_fits(hi, host):
        best = hi
    else:
        best = lo
        while lo <= hi:
            mid = (lo + hi) // 2
            if _ping_fits(mid, host):
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1

    optimal = best + IP_HEADER_OVERHEAD
    note = (f"Largest unfragmented payload to {host} is {best} bytes, so the path "
            f"MTU is {optimal}.")
    if optimal >= 1500:
        note += " That is the standard Ethernet MTU — no change needed."
    else:
        note += (" Lowering the adapter MTU to this value can stop fragmentation on "
                 "PPPoE/VPN links. On most connections the effect is small.")
    return {"optimal_mtu": optimal, "optimal_payload": best, "host": host,
            "current": current, "demo": False, "note": note}
