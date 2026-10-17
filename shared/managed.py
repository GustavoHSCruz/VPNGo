#!/usr/bin/env python3
"""Keep Mihomo process rules in sync with the applications vpngo launches."""

import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error

from apps import AppError, find, find_temporary, key
from assignments import get as assignment_for
from generate_mihomo import STATE, build_config, controller, group_name, private_write, profile_proxy
from profiles import parsed_profiles, profile_key, resolve


MANAGED = STATE / "managed.json"
STARTUP_GRACE_SECONDS = 60


def load_managed():
    return json.loads(MANAGED.read_text(encoding="utf-8")) if MANAGED.exists() else {}


def save_managed(data):
    MANAGED.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".managed-", dir=MANAGED.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(data, output, indent=2)
        os.replace(temporary, MANAGED)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def process_start(pid):
    """Return an OS process creation marker, so reused PIDs are not mistaken for workers."""
    if not isinstance(pid, int) or pid <= 0:
        return None
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.GetProcessTimes.argtypes = (wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                           ctypes.c_void_p, ctypes.c_void_p)
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        try:
            created = wintypes.FILETIME()
            exited = wintypes.FILETIME()
            kernel_time = wintypes.FILETIME()
            user_time = wintypes.FILETIME()
            if not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                          ctypes.byref(kernel_time), ctypes.byref(user_time)):
                return None
            return str((created.dwHighDateTime << 32) | created.dwLowDateTime)
        finally:
            kernel.CloseHandle(handle)
    result = subprocess.run(["ps", "-p", str(pid), "-o", "lstart="],
                            capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def bind_temporary(application, session, pid):
    name = key(application)
    data = load_managed()
    item = data.get(name)
    if not item or not item.get("temporary") or item.get("session") != session or item.get("orphaned"):
        raise AppError(f"Temporary session for '{application}' is no longer active.")
    started = process_start(pid)
    if not started:
        raise AppError(f"Temporary worker PID {pid} is not running.")
    item["worker_pid"] = pid
    item["worker_started"] = started
    save_managed(data)


def reconcile_temporary():
    data = load_managed()
    now = time.time()
    changed = []
    for name, item in data.items():
        if not item.get("temporary"):
            continue
        if not item.get("session"):
            # v0.3.0 temporary records did not identify their worker.
            item["session"] = secrets.token_urlsafe(24)
            item["created_at"] = 0
        if item.get("orphaned"):
            if not item.get("orphaned_synced"):
                changed.append(name)
            continue
        pid = item.get("worker_pid")
        if not pid and now - item.get("created_at", now) < STARTUP_GRACE_SECONDS:
            continue
        if pid and item.get("worker_started") and process_start(pid) == item["worker_started"]:
            continue
        item["orphaned"] = True
        item["blocked"] = True
        item["enabled"] = False
        changed.append(name)
    if changed:
        save_managed(data)
        try:
            running = reload_runtime()
        except (OSError, ValueError, urllib.error.URLError) as error:
            print(f"vpngo: orphaned route is recorded as blocked, but Mihomo did not accept the update: {error}",
                  file=sys.stderr)
            return changed
        for name in changed:
            data[name]["orphaned_synced"] = True
        save_managed(data)
        if running:
            from control import app_connections, request
            settings = controller()
            for name in changed:
                item = data[name]
                try:
                    for identifier in set(app_connections(int(settings["port"]), settings["secret"],
                                                          item["process"], item.get("helpers", []),
                                                          group_name(name))):
                        try:
                            request(int(settings["port"]), settings["secret"], "DELETE",
                                    "/connections/" + identifier)
                        except urllib.error.HTTPError as error:
                            if error.code != 404:
                                raise
                except (ValueError, urllib.error.URLError) as error:
                    print(f"vpngo: could not close every connection for '{name}': {error}", file=sys.stderr)
        for name in changed:
            print(f"vpngo: temporary session for '{name}' lost its worker; route blocked. "
                  f"Run 'vpngo stop {name}' to close it and clear the route.", file=sys.stderr)
    return changed


def render():
    settings = controller()
    data = load_managed()
    if sys.platform == "win32":
        from windows_backend import assign_ports
        if assign_ports(data, int(settings["port"])):
            save_managed(data)
    private_write(STATE / "config.yaml", build_config(
        parsed_profiles(), settings["secret"], int(settings["port"]), data))
    if sys.platform == "win32":
        from windows_backend import write_config
        write_config(STATE, data, settings)
    return settings


def reload_runtime():
    data = load_managed()
    settings = render()
    from control import request
    port, secret = int(settings["port"]), settings["secret"]
    try:
        request(port, secret, "GET", "/version")
    except urllib.error.HTTPError:
        raise
    except urllib.error.URLError:
        return False
    if sys.platform == "win32":
        config = request(port, secret, "GET", "/configs")
        if not isinstance(config, dict) or config.get("tun", {}).get("enable", False):
            raise AppError("Stop the old global Mihomo TUN before using app-only routing.")
    request(port, secret, "PUT", "/configs?force=true", {"path": str(STATE / "config.yaml")})
    for attempt in range(20):
        try:
            for managed_name, item in data.items():
                request(port, secret, "PUT", "/proxies/" + group_name(managed_name),
                        {"name": "REJECT" if item.get("blocked") else
                         profile_proxy(item.get("profile", "default")) if item["enabled"] else "DIRECT"})
            return True
        except urllib.error.HTTPError as error:
            if error.code != 404 or attempt == 19:
                raise
            time.sleep(0.2)
    return True


def prepare(application, profile="default", temporary=False):
    app = find_temporary(application) if temporary else find(application)
    assignment = {"helpers": [], "dns": False} if temporary else assignment_for(application)
    profile = profile_key(profile)
    resolve(profile)
    name = key(app["process"]) if temporary else key(application)
    data = load_managed()
    if temporary and name in data:
        raise AppError(f"'{application}' already has a managed route; run 'vpngo stop {name}' before a temporary run.")
    for other_name, item in data.items():
        if other_name != name and item["process"].casefold() == app["process"].casefold():
            raise AppError(
                f"'{application}' and '{other_name}' use the same process name; "
                "Mihomo cannot route them independently by name."
            )
        if other_name != name and set(item.get("helpers", [])) & set(assignment.get("helpers", [])):
            raise AppError(f"'{application}' and '{other_name}' share a helper executable; route it through only one app.")
        if other_name != name and (
            app["executable"] in item.get("helpers", []) or
            item["executable"] in assignment.get("helpers", [])
        ):
            raise AppError(f"'{application}' and '{other_name}' have conflicting executable paths.")
    previous = json.loads(json.dumps(data))
    data[name] = {**app, "profile": profile, "enabled": True, "blocked": False,
                  "helpers": assignment.get("helpers", []), "dns": assignment.get("dns", False)}
    if sys.platform == "win32" and previous.get(name, {}).get("windows_port"):
        data[name]["windows_port"] = previous[name]["windows_port"]
    if temporary:
        data[name].update(temporary=True, session=secrets.token_urlsafe(24), created_at=time.time())
    save_managed(data)
    try:
        reload_runtime()
    except Exception:
        save_managed(previous)
        try:
            reload_runtime()
        except Exception:
            pass
        raise
    return {**app, "session": data[name]["session"]} if temporary else app


def cleanup_temporary(application, session):
    name = key(application)
    data = load_managed()
    if name not in data:
        return
    if not data[name].get("temporary") or data[name].get("session") != session:
        raise AppError(f"'{application}' has no temporary route to remove.")
    del data[name]
    save_managed(data)
    reload_runtime()


def main():
    if len(sys.argv) > 1 and sys.argv[1] not in {"temp-bind", "temp-cleanup"}:
        reconcile_temporary()
    if len(sys.argv) == 3 and sys.argv[1] == "temp-resolve":
        print(json.dumps(find_temporary(sys.argv[2]), ensure_ascii=False))
        return 0
    if len(sys.argv) == 4 and sys.argv[1] == "temp-prepare":
        print(json.dumps(prepare(sys.argv[2], sys.argv[3], temporary=True), ensure_ascii=False))
        return 0
    if len(sys.argv) == 5 and sys.argv[1] == "temp-bind":
        bind_temporary(sys.argv[2], sys.argv[3], int(sys.argv[4]))
        return 0
    if len(sys.argv) == 4 and sys.argv[1] == "temp-cleanup":
        cleanup_temporary(sys.argv[2], sys.argv[3])
        return 0
    if sys.argv[1:] == ["reload"]:
        print("Mihomo configuration reloaded." if reload_runtime() else "Mihomo is not running; configuration is ready.")
        return 0
    if len(sys.argv) == 3 and sys.argv[1] == "inspect":
        print(json.dumps(load_managed().get(key(sys.argv[2])), ensure_ascii=False))
        return 0
    if len(sys.argv) not in {3, 4} or sys.argv[1] not in {"prepare", "resolve"} or (sys.argv[1] == "resolve" and len(sys.argv) != 3):
        print("Usage: managed.py prepare <application> [profile] | resolve <application> | reload", file=sys.stderr)
        return 2
    app = prepare(sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else "default") if sys.argv[1] == "prepare" else find(sys.argv[2])
    print(json.dumps(app, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AppError, OSError, ValueError, KeyError, json.JSONDecodeError,
            urllib.error.URLError) as error:
        print(f"vpngo: {error}", file=sys.stderr)
        sys.exit(1)
