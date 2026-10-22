"""Machine-readable snapshot of every app's route, for `vpngo status --json`.

Reads only what an unprivileged user can read: vopono's namespace list, the
session files and the host side of each namespace's veth on Linux, the local
Mihomo controller on macOS and Windows. It never asks for a password, so a
front end can refresh it as often as it likes.

Per running app it reports when the session started, when its current route
began and the time spent on each route, the VPN server endpoint, and byte
counters (rx = received by the app, tx = sent by it) in total and since the
current route began; a front end turns the counters into rates by sampling
them over time.
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
import route_clock


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
        backup = LINUX_STATE / f"{identifier}.resolv.conf"
        direct = backup.exists()
        started_at = iso_epoch(namespace.get("created_at"))
        record = session.get("route")
        unknown_base = False
        if not isinstance(record, dict) or record.get("state") != ("direct" if direct else "vpn"):
            # Sessions from before v0.7.0: the route began at the switch (the backup's time) or at the start.
            try:
                since = backup.stat().st_mtime if direct else started_at
            except OSError:
                since = started_at
            record = route_clock.begin("direct" if direct else "vpn", since)
            if direct and since and started_at:
                record["vpn_seconds"] = max(0.0, since - started_at)  # Best estimate: on the VPN until then.
            # The counters at that switch were never recorded, so traffic "since the switch" is unknown.
            unknown_base = direct
        routes[name] = {"state": "direct" if direct else "vpn",
                        "active_profile": session.get("profile"),
                        "started_at": started_at,
                        # Saved at start since v0.7.0; vopono leaves it empty for custom profiles.
                        "endpoint": (session.get("endpoint") or (namespace.get("server") or {}).get("hostname")
                                     or endpoint(session.get("profile") or "default")),
                        "executable": session.get("executable"),
                        **counters.get(identifier, {}),
                        **route_clock.view(record, None if unknown_base else counters.get(identifier))}
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
        started_at = item.get("started_at") or item.get("created_at")
        # Totals of the open connections; they drop when connections close, and a switch closes them all.
        counters = {"rx_bytes": sum(int(connection.get("download") or 0) for connection in mine),
                    "tx_bytes": sum(int(connection.get("upload") or 0) for connection in mine)}
        record = item.get("route") if isinstance(item.get("route"), dict) else None
        if state_name in route_clock.ROUTES and (not record or record.get("state") != state_name):
            record = route_clock.begin(state_name, started_at)
        routes[name] = {"state": state_name, "active_profile": profile,
                        "temporary": bool(item.get("temporary")),
                        "started_at": started_at,
                        "endpoint": endpoint(profile),
                        "executable": item.get("launch") or item.get("executable"),
                        **counters, **route_clock.view(record, counters)}
    return routes


def running_processes():
    """Lower-case names of this user's running programs, in one call; empty when it cannot tell.

    Linux names are cut to 15 characters, as the kernel keeps them.
    """
    try:
        if sys.platform == "win32":
            output = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=10,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False).stdout
            return {Path(line.split('","')[0].strip('"')).stem.casefold() for line in output.splitlines() if line}
        import os
        output = subprocess.run(["ps", "-u", str(os.getuid()), "-o", "comm="], capture_output=True, text=True,
                                timeout=10, check=False).stdout
        return {Path(line.strip()).name.casefold() for line in output.splitlines() if line.strip()}
    except (OSError, subprocess.TimeoutExpired):
        return set()


def opened_outside(name, processes, registered=None):
    """True when a stopped app's program is running anyway: someone opened it without vpngo.

    On Windows only a registered path is used: searching Program Files on every refresh is too slow.
    """
    from apps import describe, find
    try:
        if registered:
            process = Path(describe(Path(registered))["process"])
        elif sys.platform == "win32":
            return False
        else:
            process = Path(find(name)["process"])
    except (AppError, OSError, KeyError):
        return False
    wanted = (process.stem if sys.platform == "win32" else process.name).casefold()
    return wanted in processes or wanted[:15] in processes


def endpoint(profile):
    try:
        from profiles import parsed as parsed_profile
        parsed = parsed_profile(profile)
        host = parsed["host"]
        return f"[{host}]:{parsed['port']}" if ":" in host else f"{host}:{parsed['port']}"
    except (AppError, OSError, ValueError, KeyError):
        return None


def snapshot(version):
    from groups import load as load_groups
    profiles = sorted(load_profiles())
    saved = load_assignments()
    registered = load_apps()["files"]
    groups = load_groups()
    routes = linux_routes() if sys.platform.startswith("linux") else mihomo_routes()
    default_killswitch = sys.platform.startswith("linux")
    apps = []
    grouped = {app for entry in groups.values() for app in entry["apps"]}
    processes = None
    for name in sorted(set(saved) | set(registered) | set(routes) | grouped):
        item = saved.get(name, {})
        route = routes.get(name, {})
        # Who opened it: vpngo for a routed app; "outside" when its program runs without a route.
        origin = "vpngo" if route else None
        if not route:
            processes = running_processes() if processes is None else processes
            origin = "outside" if opened_outside(name, processes, registered.get(name)) else None
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
            "route_since": route.get("route_since"),
            "vpn_seconds": route.get("vpn_seconds"),
            "direct_seconds": route.get("direct_seconds"),
            "route_rx_bytes": route.get("route_rx_bytes"),
            "route_tx_bytes": route.get("route_tx_bytes"),
            # Only paths already known: searching for an app here would slow every refresh.
            "executable": route.get("executable") or registered.get(name),
            "origin": origin,
            "group": next((group for group, entry in groups.items() if name in entry["apps"]), None),
            "killswitch": item.get("killswitch", default_killswitch),
            "dns": item.get("dns", False),
        })
    return {"schema": 1, "version": version, "platform": sys.platform,
            "profiles": profiles, "apps": apps,
            "groups": [{"name": group, "apps": entry["apps"]} for group, entry in sorted(groups.items())]}
