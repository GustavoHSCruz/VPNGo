"""Windows app routing: authenticated loopback SOCKS listeners and ProxiFyre rules.

This module never installs a driver, changes Windows routes, or starts a service.
The elevated Windows helper applies only the generated process allowlist.
"""

import hashlib
import hmac
import json
import re
import subprocess
import sys
from pathlib import PureWindowsPath

from apps import AppError


PROTECTED = {"python", "python3", "powershell", "pwsh", "cmd", "conhost",
             "explorer", "svchost", "system", "mihomo", "proxifyre"}


def listener_ports(managed, controller_port):
    """Deterministic, collision-free ports shared by both generated configs."""
    used = {int(controller_port)}
    result = {}
    if len(managed) >= 10000:
        raise AppError("Too many managed applications for Windows SOCKS listeners.")
    for name, item in sorted(managed.items()):
        port = item.get("windows_port")
        if port is not None:
            if not isinstance(port, int) or not 20000 <= port < 30000 or port in used:
                raise AppError("Invalid or conflicting Windows listener ports.")
            used.add(port)
            result[name] = port
    for name in sorted(managed):
        if name in result:
            continue
        port = 20000 + int(hashlib.sha256(name.encode()).hexdigest()[:8], 16) % 10000
        while port in used:
            port = 20000 + (port - 20000 + 1) % 10000
        used.add(port)
        result[name] = port
    return result


def assign_ports(managed, controller_port):
    changed = False
    for name, port in listener_ports(managed, controller_port).items():
        if managed[name].get("windows_port") != port:
            managed[name]["windows_port"] = port
            changed = True
    return changed


def credentials(name, secret):
    username = "vpngo-" + hashlib.sha256(name.encode()).hexdigest()[:12]
    password = hmac.new(secret.encode(), ("socks:" + name).encode(), hashlib.sha256).hexdigest()
    return username, password


def build_proxifyre_config(managed, secret, controller_port):
    ports = listener_ports(managed, controller_port)
    proxies = []
    owners = {}
    for name, item in sorted(managed.items()):
        process = item["process"]
        # Names without separators match whole filenames in ProxiFyre 2.6.4.
        # Never generate its empty-string catch-all or a directory-wide match.
        if not re.fullmatch(r"[A-Za-z0-9_. ()-]{1,100}\.exe", process, re.I):
            raise AppError(f"Unsupported Windows process name: {process}")
        matches = [process]
        for helper in item.get("helpers", []):
            path = PureWindowsPath(helper)
            if not path.is_absolute() or path.suffix.lower() != ".exe":
                raise AppError("Windows helpers must be absolute executable paths.")
            matches.append(str(path))
        for match in matches:
            filename = PureWindowsPath(match).name
            if PureWindowsPath(filename).stem.casefold() in PROTECTED:
                raise AppError(f"Refusing to redirect shared process '{filename}'.")
            token = filename.casefold()
            if token in owners and owners[token] != name:
                raise AppError(f"'{name}' and '{owners[token]}' have conflicting process matches.")
            owners[token] = name
        username, password = credentials(name, secret)
        proxies.append({
            "appNames": matches, "socks5ProxyEndpoint": f"127.0.0.1:{ports[name]}",
            "username": username, "password": password,
            "supportedProtocols": ["TCP", "UDP"],
            "supportedAddressFamilies": ["IPv4", "IPv6"],
        })
    return {"logLevel": "Info", "bypassLan": True, "proxies": proxies,
            "excludes": ["mihomo.exe", "ProxiFyre.exe"]}


def write_config(state, managed, settings):
    from generate_mihomo import private_write
    config = build_proxifyre_config(managed, settings["secret"], int(settings["port"]))
    private_write(state / "proxifyre.json", json.dumps(config, indent=2) + "\n")


def probe(application):
    from control import request
    from generate_mihomo import controller, group_name
    settings = controller()
    port, secret = int(settings["port"]), settings["secret"]
    config = request(port, secret, "GET", "/configs")
    if not isinstance(config, dict) or config.get("tun", {}).get("enable", False):
        raise AppError("Stop the old global Mihomo TUN before using app-only routing.")
    request(port, secret, "GET", "/proxies/" + group_name(application))


def routing_active():
    from pathlib import Path
    from generate_mihomo import STATE
    helper = Path(__file__).resolve().parent.parent / "windows/proxy-service.ps1"
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(helper),
             "-Mode", "Check", "-ConfigPath", str(STATE / "proxifyre.json")],
            capture_output=True, text=True, check=False, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode:
        return False
    status = json.loads(result.stdout)
    return bool(status.get("running") and not status.get("needsApply"))


if __name__ == "__main__":
    import urllib.error
    try:
        if len(sys.argv) != 3 or sys.argv[1] != "probe":
            raise AppError("Usage: windows_backend.py probe <application>")
        from apps import key
        probe(key(sys.argv[2]))
    except (AppError, OSError, ValueError, urllib.error.URLError) as error:
        print(f"vpngo: {error}", file=sys.stderr)
        sys.exit(1)
