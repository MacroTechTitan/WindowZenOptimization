"""Internet Optimizer endpoints.

Exactly the eight endpoints in the Sprint 3 spec, no more:
  GET  /api/network/diagnose
  POST /api/network/quick-fix
  POST /api/network/deep-reset      (requires {"confirm": true})
  POST /api/network/set-dns
  GET  /api/network/dns-benchmark
  GET  /api/network/mtu-probe
  POST /api/network/set-mtu
  POST /api/network/browser-cache

`netsh advfirewall reset` is deliberately NOT implemented anywhere in this
module. It is out of scope and would irreversibly destroy every firewall
rule on the machine.
"""
import os

from flask import Blueprint, jsonify, request

from core.state import IS_WINDOWS
from core.util import log_activity, log_undo, format_bytes
from core.safety import send_to_recycle_bin, guard_batch, check_deletable
from scanners.deepclean import browser_cache_dirs
from scanners.network import (
    DNS_PRESETS, run_cmd, list_adapters, dns_per_adapter, mtu_per_adapter,
    winsock_catalog, dns_benchmark, mtu_probe,
    load_network_state, save_network_state, remember_dns, remember_mtu,
)

bp = Blueprint("network", __name__)

# Shown wherever advanced TCP knobs might be expected. We do not offer them.
ADVANCED_TCP_NOTE = (
    "Advanced — typically minimal effect on modern Windows. TCP autotuning, RSS "
    "and ECN are left at their defaults on purpose: Windows tunes these itself "
    "and changing them rarely improves real throughput.")


def _adapter_names():
    return {a["name"] for a in list_adapters()}


# ─── 1. Diagnose (read-only) ───────────────────────────────────
@bp.route("/api/network/diagnose")
def api_network_diagnose():
    """Read-only snapshot: DNS per adapter, MTU, adapters, Winsock catalog."""
    adapters = list_adapters()
    dns = dns_per_adapter()
    mtu = mtu_per_adapter()
    catalog = winsock_catalog()
    log_activity("Network diagnostics collected (read-only)", "INFO")
    return jsonify({
        "status": "ok",
        "adapters": adapters,
        "dns": dns,
        "mtu": mtu,
        "winsock": catalog,
        "presets": DNS_PRESETS,
        "saved": load_network_state(),
        "advanced_note": ADVANCED_TCP_NOTE,
        "platform_supported": IS_WINDOWS,
    })


# ─── 2. Quick fix ──────────────────────────────────────────────
@bp.route("/api/network/quick-fix", methods=["POST"])
def api_network_quick_fix():
    """flushdns + release + renew. No reboot, nothing destructive."""
    steps = [
        (["ipconfig", "/flushdns"], "Flush DNS resolver cache"),
        (["ipconfig", "/release"], "Release the current DHCP lease"),
        (["ipconfig", "/renew"], "Request a fresh IP address"),
    ]
    results = []
    for args, label in steps:
        rc, out = run_cmd(args, timeout=60)
        results.append({"command": " ".join(args), "label": label,
                        "exit_code": rc, "output": out[:2000]})
        log_activity(f"Quick fix: {label} (exit {rc})",
                     "SUCCESS" if rc == 0 else "WARN")
    return jsonify({
        "status": "ok",
        "steps": results,
        "needs_reboot": False,
        "message": "Quick fix complete. No reboot required.",
    })


# ─── 3. Deep reset ─────────────────────────────────────────────
@bp.route("/api/network/deep-reset", methods=["POST"])
def api_network_deep_reset():
    """winsock reset + int ip reset. Requires explicit confirmation."""
    data = request.get_json(silent=True) or {}
    if not data.get("confirm"):
        return jsonify({
            "status": "error",
            "message": ("Confirmation required. This resets the Winsock catalog and "
                        "the TCP/IP stack: your connection will drop and the PC must "
                        "be restarted before networking behaves normally. Re-send "
                        "with confirm=true."),
            "requires": "confirm",
            "warning": {
                "connection_drops": True,
                "reboot_required": True,
                "resets": ["Winsock catalog", "TCP/IP stack"],
            },
        }), 400

    steps = [
        (["netsh", "winsock", "reset"], "Reset the Winsock catalog"),
        (["netsh", "int", "ip", "reset"], "Reset the TCP/IP stack"),
    ]
    results = []
    for args, label in steps:
        rc, out = run_cmd(args, timeout=120)
        results.append({"command": " ".join(args), "label": label,
                        "exit_code": rc, "output": out[:2000]})
        log_activity(f"Deep reset: {label} (exit {rc})",
                     "SUCCESS" if rc == 0 else "WARN")
        if rc != 0 and "administrator" in out.lower():
            results[-1]["output"] += "\nThis command requires Administrator privileges."

    log_undo("network_reset", "Network deep reset (Winsock + TCP/IP)",
             {"reboot_required": True})
    log_activity("Network deep reset complete — REBOOT REQUIRED", "WARN")
    return jsonify({
        "status": "ok",
        "steps": results,
        "needs_reboot": True,
        "message": ("Winsock and TCP/IP have been reset. You must RESTART the "
                    "computer before networking will work normally again."),
    })


# ─── 4. Set DNS ────────────────────────────────────────────────
@bp.route("/api/network/set-dns", methods=["POST"])
def api_network_set_dns():
    """{adapter, dns} to apply, or {adapter, restore:true} to put it back."""
    data = request.get_json(silent=True) or {}
    adapter = (data.get("adapter") or "").strip()
    if not adapter:
        return jsonify({"status": "error", "message": "An adapter name is required."}), 400
    if IS_WINDOWS and adapter not in _adapter_names():
        return jsonify({"status": "error",
                        "message": f"Unknown adapter '{adapter}'."}), 400

    # Capture what is there now so the change can always be reverted.
    live = {d["adapter"]: d for d in dns_per_adapter()}
    cur = live.get(adapter, {"servers": [], "dhcp": True})
    remember_dns(adapter, cur.get("servers", []), cur.get("dhcp", True))

    if data.get("restore"):
        saved = load_network_state().get("previous_dns", {}).get(adapter)
        if not saved:
            return jsonify({"status": "error",
                            "message": f"No saved DNS for '{adapter}'."}), 400
        servers = [] if saved.get("dhcp") else saved.get("servers", [])
    else:
        preset = data.get("preset")
        if preset:
            if preset not in DNS_PRESETS:
                return jsonify({"status": "error",
                                "message": f"Unknown preset '{preset}'."}), 400
            servers = DNS_PRESETS[preset]["servers"]
        else:
            servers = data.get("dns") or []
            if isinstance(servers, str):
                servers = [servers]
        for s in servers:
            if not isinstance(s, str) or not s.replace(".", "").isdigit():
                return jsonify({"status": "error",
                                "message": f"Invalid DNS address '{s}'."}), 400

    results = []
    if not servers:
        rc, out = run_cmd(["netsh", "interface", "ipv4", "set", "dnsservers",
                           f"name={adapter}", "source=dhcp"], timeout=60)
        results.append({"command": f'set dnsservers name="{adapter}" source=dhcp',
                        "exit_code": rc, "output": out[:1000]})
        log_activity(f"DNS for '{adapter}' set back to automatic (DHCP)",
                     "SUCCESS" if rc == 0 else "WARN")
    else:
        for i, server in enumerate(servers):
            if i == 0:
                args = ["netsh", "interface", "ipv4", "set", "dnsservers",
                        f"name={adapter}", "static", server, "primary", "no"]
            else:
                args = ["netsh", "interface", "ipv4", "add", "dnsservers",
                        f"name={adapter}", server, f"index={i + 1}"]
            rc, out = run_cmd(args, timeout=60)
            results.append({"command": " ".join(args[3:]), "exit_code": rc,
                            "output": out[:1000]})
        log_activity(f"DNS for '{adapter}' set to {', '.join(servers)} "
                     f"(previous: {cur.get('servers') or 'DHCP'})", "SUCCESS")

    run_cmd(["ipconfig", "/flushdns"], timeout=30)
    return jsonify({
        "status": "ok",
        "adapter": adapter,
        "applied": servers or ["DHCP (automatic)"],
        "previous": cur,
        "steps": results,
        "message": ("DNS restored." if data.get("restore")
                    else "DNS updated and the resolver cache was flushed."),
    })


# ─── 5. DNS benchmark (read-only) ──────────────────────────────
@bp.route("/api/network/dns-benchmark")
def api_network_dns_benchmark():
    """Time a fixed domain set against 1.1.1.1, 8.8.8.8, 9.9.9.9 and current DNS."""
    current = []
    for d in dns_per_adapter():
        for s in d.get("servers", []):
            if s not in current:
                current.append(s)
    log_activity("DNS benchmark started", "TASK")
    result = dns_benchmark(current)
    result["status"] = "ok"
    result["current_dns"] = current
    log_activity(f"DNS benchmark complete — fastest: {result.get('recommendation')}",
                 "SUCCESS")
    return jsonify(result)


# ─── 6. MTU probe (read-only) ──────────────────────────────────
@bp.route("/api/network/mtu-probe")
def api_network_mtu_probe():
    """Binary-search the largest unfragmented packet; report optimal + current."""
    host = request.args.get("host") or "8.8.8.8"
    log_activity(f"MTU probe started against {host}", "TASK")
    result = mtu_probe(host)
    result["status"] = "ok"
    result["advanced_note"] = ADVANCED_TCP_NOTE
    log_activity(f"MTU probe complete — optimal {result.get('optimal_mtu')}", "SUCCESS")
    return jsonify(result)


# ─── 7. Set MTU ────────────────────────────────────────────────
@bp.route("/api/network/set-mtu", methods=["POST"])
def api_network_set_mtu():
    """{adapter, mtu} — persists, saving the previous value first."""
    data = request.get_json(silent=True) or {}
    adapter = (data.get("adapter") or "").strip()
    if not adapter:
        return jsonify({"status": "error", "message": "An adapter name is required."}), 400

    if data.get("restore"):
        saved = load_network_state().get("previous_mtu", {}).get(adapter)
        if saved is None:
            return jsonify({"status": "error",
                            "message": f"No saved MTU for '{adapter}'."}), 400
        mtu = int(saved)
    else:
        try:
            mtu = int(data.get("mtu"))
        except (TypeError, ValueError):
            return jsonify({"status": "error", "message": "A numeric mtu is required."}), 400
        if not (576 <= mtu <= 9000):
            return jsonify({
                "status": "error",
                "message": f"MTU {mtu} is out of range. Use 576-9000; 1500 is the "
                           f"Ethernet standard and values below 1280 break IPv6.",
            }), 400

    current = {m["adapter"]: m["mtu"] for m in mtu_per_adapter()}
    if IS_WINDOWS and adapter not in current:
        return jsonify({"status": "error",
                        "message": f"Unknown adapter '{adapter}'."}), 400
    previous = current.get(adapter)
    if previous is not None:
        remember_mtu(adapter, previous)

    rc, out = run_cmd(["netsh", "interface", "ipv4", "set", "subinterface",
                       adapter, f"mtu={mtu}", "store=persistent"], timeout=60)
    ok = rc == 0
    log_activity(f"MTU for '{adapter}' set to {mtu} (previous: {previous}) — "
                 f"exit {rc}", "SUCCESS" if ok else "WARN")
    if ok and previous is not None:
        log_undo("mtu_change", f"MTU for '{adapter}' changed to {mtu}",
                 {"adapter": adapter, "from": previous, "to": mtu})
    return jsonify({
        "status": "ok" if ok else "error",
        "adapter": adapter,
        "mtu": mtu,
        "previous": previous,
        "exit_code": rc,
        "output": out[:1000],
        "advanced_note": ADVANCED_TCP_NOTE,
        "message": (f"MTU set to {mtu} (persistent)." if ok else
                    "Could not set the MTU — Administrator privileges are required."),
    })


# ─── 8. Browser cache ──────────────────────────────────────────
@bp.route("/api/network/browser-cache", methods=["POST"])
def api_network_browser_cache():
    """{browsers[], action: scan|clear} — cache directories ONLY.

    Cookies, history, saved passwords and bookmarks are never touched: only
    the per-profile Cache/Code Cache/GPUCache/CacheStorage directories are
    ever enumerated or removed.
    """
    data = request.get_json(silent=True) or {}
    action = (data.get("action") or "scan").lower()
    if action not in ("scan", "clear"):
        return jsonify({"status": "error",
                        "message": "action must be 'scan' or 'clear'."}), 400

    all_dirs = browser_cache_dirs()
    wanted = data.get("browsers") or list(all_dirs.keys())
    unknown = [b for b in wanted if b not in all_dirs]
    if unknown:
        return jsonify({"status": "error",
                        "message": f"Unknown browser(s): {', '.join(unknown)}. "
                                   f"Supported: {', '.join(all_dirs)}."}), 400

    report = []
    targets = []
    for browser in wanted:
        dirs = all_dirs.get(browser, [])
        bsize = 0
        profiles = []
        for d in dirs:
            size = 0
            try:
                for dirpath, _, filenames in os.walk(d):
                    for f in filenames:
                        try:
                            size += os.path.getsize(os.path.join(dirpath, f))
                        except (OSError, PermissionError):
                            pass
            except (OSError, PermissionError):
                pass
            bsize += size
            profiles.append({"path": d, "bytes": size, "bytes_fmt": format_bytes(size)})
            targets.append(d)
        report.append({
            "browser": browser,
            "installed": bool(dirs),
            "bytes": bsize,
            "bytes_fmt": format_bytes(bsize),
            "cache_dirs": profiles,
        })

    total = sum(r["bytes"] for r in report)
    if action == "scan":
        return jsonify({
            "status": "ok", "action": "scan", "browsers": report,
            "total_bytes": total, "total_fmt": format_bytes(total),
            "note": "Cache directories only — cookies, history and passwords are "
                    "not included and are never removed.",
        })

    # ── clear ──
    if not data.get("confirm"):
        return jsonify({
            "status": "error",
            "message": "Confirmation required — scan first, then re-send with "
                       "action='clear' and confirm=true.",
        }), 400

    blocked, allowed = [], []
    for d in targets:
        ok, reason = check_deletable(d)
        (allowed.append(d) if ok else blocked.append({"path": d, "reason": reason}))
    if not allowed:
        return jsonify({"status": "blocked", "blocked": blocked,
                        "message": "No cache directory passed the safety checks."}), 400

    ok, payload = guard_batch(
        allowed, bool(data.get("proceed_without_restore_point", False)),
        description="MTT Optimizer — before clearing browser caches")
    if not ok:
        payload["blocked"] = blocked
        return jsonify(payload), 409

    result = send_to_recycle_bin(
        allowed, allow_permanent=bool(data.get("allow_permanent", False)),
        total_bytes=total)
    result["blocked"].extend(blocked)
    if result["recycled"]:
        log_undo("recycle", f"Cleared browser cache for {', '.join(wanted)}",
                 {"count": len(result["recycled"]), "bytes": result["bytes"],
                  "recoverable": not result["permanent"]})

    return jsonify({
        "status": "ok",
        "action": "clear",
        "cleared": len(result["recycled"]),
        "bytes": result["bytes"],
        "bytes_fmt": format_bytes(result["bytes"]),
        "permanent": result["permanent"],
        "blocked": result["blocked"],
        "errors": result["errors"],
        "message": result["message"] or "Cache directories moved to the Recycle Bin. "
                                        "Cookies, history and passwords were not touched.",
        "restore_point": payload["restore_point"],
    })
