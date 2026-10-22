"""Machine-readable snapshot of every app's route, for `vpngo status --json`.

Reads only what an unprivileged user can read: vopono's namespace list, the
session files and the host side of each namespace's veth on Linux, the local
Mihomo controller on macOS and Windows. It never asks for a password, so a
front end can refresh it as often as it likes.

Per running app it reports when the session started, the VPN server endpoint,
and cumulative byte counters (rx = received by the app, tx = sent by it); a
front end turns the counters into rates by sampling them over time.
"""

import json
import re
import shutil
import subprocess
import sys
import urllib.error
from datetime import datetime
from pathlib import Path

from apps import AppError, key, load as load_apps
from assignments import load as load_assignments
from profiles import load as load_profiles


LINUX_STATE = Path.home() / ".local/state/vpngo"
NAMESPACE = re.compile(r"[A-Za-z0-9_.-]{1,64}")


def iso_epoch(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def veth_counters():
    """Byte counters of each network namespace's veth, seen from the host side (no root needed).

    The host side receives what the app sends and transmits what the app receives.
    """
    def ip_json(*arguments):
        try:
            result = subprocess.run(["ip", "-j", *arguments], capture_output=True, text=True, timeout=5, check=False)
            data = json.loads(result.stdout or "[]") if result.returncode == 0 else []
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return []
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
    ids = {item.get("id"): item.get("name") for item in ip_json("netns", "list") if "id" in item}
    counters = {}
    for link in ip_json("link", "show", "type", "veth"):
        namespace = ids.get(link.get("link_netnsid"))
        statistics = Path("/sys/class/net") / str(link.get("ifname", "")) / "statistics"
        if not namespace or not statistics.is_dir():
            continue
        try:
            counters[namespace] = {"rx_bytes": int((statistics / "tx_bytes").read_text()),
                                   "tx_bytes": int((statistics / "rx_bytes").read_text())}
        except (OSError, ValueError):
            continue
    return counters


def linux_routes():
    """Running apps from vopono, matched to the session file vpngo wrote at start."""
    if not shutil.which("vopono"):
        return {}
    try:
        result = subprocess.run(["vopono", "status", "--json"], capture_output=True, text=True,
                                timeout=10, check=False)
        data = json.loads(result.stdout) if result.returncode == 0 else {}
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return {}
    routes = {}
    counters = veth_counters() if data.get("namespaces") else {}
    for namespace in data.get("namespaces", []):
        identifier = str(namespace.get("id", ""))
        session_file = LINUX_STATE / f"{identifier}.json"
        if (not NAMESPACE.fullmatch(identifier) or not namespace.get("applications") or
                not session_file.is_file()):
            continue
        try:
            session = json.loads(session_file.read_text(encoding="utf-8"))
            name = key(str(session.get("app", "")))
        except (OSError, ValueError, AppError):
            continue
        # turn_off keeps the namespace resolver backup until turn_on restores it.
        direct = (LINUX_STATE / f"{identifier}.resolv.conf").exists()
        routes[name] = {"state": "direct" if direct else "vpn",
                        "active_profile": session.get("profile"),
                        "started_at": iso_epoch(namespace.get("created_at")),
                        "endpoint": (namespace.get("server") or {}).get("hostname"),
                        **counters.get(identifier, {})}
    return routes


def mihomo_routes():
    """Selector state of every app Mihomo manages; empty when Mihomo is not running."""
    from apps import mihomo_dir
    from generate_mihomo import group_name, profile_proxy
    state = mihomo_dir()
    try:
        managed = json.loads((state / "managed.json").read_text(encoding="utf-8"))
        settings = json.loads((state / "controller.json").read_text(encoding="utf-8"))
        port, secret = int(settings["port"]), settings["secret"]
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    from control import request
    filters_active = True
    if sys.platform == "win32" and managed:
        from windows_backend import routing_active
        filters_active = routing_active()
    try:
        connections = request(port, secret, "GET", "/connections").get("connections") or []
    except (OSError, ValueError, AttributeError, urllib.error.URLError):
        connections = []
    routes = {}
    for name, item in managed.items():
        try:
            current = request(port, secret, "GET", "/proxies/" + group_name(name))["now"]
        except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError):
            return {}  # Mihomo is down: nothing is routed.
        profile = item.get("profile", "default")
        if item.get("blocked") or current == "REJECT":
            continue
        state_name = ("vpn" if current == profile_proxy(profile) else
                      "direct" if current == "DIRECT" else "partial")
        if not filters_active:
            state_name = "partial"
        group = group_name(name)
        mine = [connection for connection in connections
                if group in (connection.get("chains") or []) or
                (connection.get("metadata") or {}).get("inboundName") == group + "-in"]
        routes[name] = {"state": state_name, "active_profile": profile,
                        "temporary": bool(item.get("temporary")),
                        "started_at": item.get("started_at") or item.get("created_at"),
                        "endpoint": endpoint(profile),
                        # Totals of the open connections; they drop when connections close.
                        "rx_bytes": sum(int(connection.get("download") or 0) for connection in mine),
                        "tx_bytes": sum(int(connection.get("upload") or 0) for connection in mine)}
    return routes


def endpoint(profile):
    try:
        from profiles import resolve
        from generate_mihomo import parse_wireguard
        parsed = parse_wireguard(resolve(profile))
        host = parsed["host"]
        return f"[{host}]:{parsed['port']}" if ":" in host else f"{host}:{parsed['port']}"
    except (AppError, OSError, ValueError, KeyError):
        return None


def snapshot(version):
    profiles = sorted(load_profiles())
    saved = load_assignments()
    registered = load_apps()["files"]
    routes = linux_routes() if sys.platform.startswith("linux") else mihomo_routes()
    default_killswitch = sys.platform.startswith("linux")
    apps = []
    for name in sorted(set(saved) | set(registered) | set(routes)):
        item = saved.get(name, {})
        route = routes.get(name, {})
        apps.append({
            "name": name,
            "profile": item.get("profile", "default"),
            "state": route.get("state", "stopped"),
            "active_profile": route.get("active_profile"),
            "temporary": route.get("temporary", False),
            "started_at": route.get("started_at"),
            "endpoint": route.get("endpoint"),
            "rx_bytes": route.get("rx_bytes"),
            "tx_bytes": route.get("tx_bytes"),
            "killswitch": item.get("killswitch", default_killswitch),
            "dns": item.get("dns", False),
        })
    return {"schema": 1, "version": version, "platform": sys.platform,
            "profiles": profiles, "apps": apps}
