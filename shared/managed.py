#!/usr/bin/env python3
"""Keep Mihomo process rules in sync with the applications vpngo launches."""

import json
import sys
import time
import urllib.error

from apps import AppError, find, find_temporary, key
from assignments import get as assignment_for
from generate_mihomo import STATE, build_config, controller, group_name, private_write, profile_proxy
from profiles import parsed_profiles, profile_key, resolve


MANAGED = STATE / "managed.json"


def load_managed():
    return json.loads(MANAGED.read_text(encoding="utf-8")) if MANAGED.exists() else {}


def save_managed(data):
    private_write(MANAGED, json.dumps(data, indent=2))


def render():
    settings = controller()
    private_write(STATE / "config.yaml", build_config(
        parsed_profiles(), settings["secret"], int(settings["port"]), load_managed()))
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
        raise AppError(f"'{application}' already has a managed route; stop it before a temporary run.")
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
    if temporary:
        data[name]["temporary"] = True
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
    return app


def cleanup_temporary(application):
    name = key(application)
    data = load_managed()
    if name not in data or not data[name].get("temporary"):
        raise AppError(f"'{application}' has no temporary route to remove.")
    del data[name]
    save_managed(data)
    reload_runtime()


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "temp-resolve":
        print(json.dumps(find_temporary(sys.argv[2]), ensure_ascii=False))
        return 0
    if len(sys.argv) == 4 and sys.argv[1] == "temp-prepare":
        print(json.dumps(prepare(sys.argv[2], sys.argv[3], temporary=True), ensure_ascii=False))
        return 0
    if len(sys.argv) == 3 and sys.argv[1] == "temp-cleanup":
        cleanup_temporary(sys.argv[2])
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
