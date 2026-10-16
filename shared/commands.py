#!/usr/bin/env python3
"""Shared command interface for Linux, macOS and Windows launchers."""

import json
import subprocess
import sys
from pathlib import Path

from apps import AppError, add_path, find, key
from assignments import add_helper, assign, get, load, set_policy
from profiles import load as load_profiles, profile_key, register, resolve


PROJECT = Path(__file__).resolve().parent.parent
GLOBAL_COMMANDS = {"profile", "assign", "start", "stop", "switch", "status", "on", "off", "policy", "helper"}


def backend(*arguments):
    if sys.platform == "win32":
        command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                   str(PROJECT / "windows/vpngo.ps1"), *arguments]
    elif sys.platform == "darwin":
        command = [str(PROJECT / "macos/vpngo"), *arguments]
    else:
        command = [str(PROJECT / "linux/vpngo"), *arguments]
    return subprocess.run(command, check=False).returncode


def configure_profile(path, profile):
    profile = profile_key(profile)
    if sys.platform in {"darwin", "win32"}:
        result = subprocess.run([sys.executable, str(PROJECT / "shared/generate_mihomo.py"), path, profile], check=False)
        if result.returncode:
            return result.returncode
        return subprocess.run([sys.executable, str(PROJECT / "shared/managed.py"), "reload"], check=False).returncode
    source = register(path, profile)
    print(f"VPN profile '{profile}' registered from {source}.")
    return 0


def usage():
    print("Usage: vpngo profile add <name> <wireguard.conf> | profile list | "
          "assign <app> <profile> | start <app> [profile] | stop <app> | switch <app> <profile> | "
          "status|on|off <app> | policy <app> killswitch|dns on|off | "
          "helper add <app> <executable>", file=sys.stderr)
    return 2


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return usage()
    command = args[0]
    if command == "profile":
        if len(args) == 2 and args[1] == "list":
            print("\n".join(sorted(load_profiles())) or "No VPN profiles configured.")
            return 0
        if len(args) == 4 and args[1] == "add":
            return configure_profile(args[3], args[2])
        return usage()
    if command == "assign" and len(args) == 3:
        item = assign(args[1], args[2])
        print(f"{args[1]} assigned to profile '{item['profile']}'.")
        return 0
    if command == "start" and len(args) in {2, 3}:
        application = args[1]
        profile = args[2] if len(args) == 3 else get(application)["profile"]
        resolve(profile)
        if sys.platform in {"darwin", "win32"} and get(application)["killswitch"]:
            raise AppError("A fail-closed per-app kill switch is not available on this platform.")
        result = backend(application, "start", profile)
        if result == 0 and len(args) == 3:
            assign(application, profile)
        return result
    if command == "switch" and len(args) == 3:
        application, profile = args[1], profile_key(args[2])
        resolve(profile)
        if sys.platform in {"darwin", "win32"}:
            result = subprocess.run([sys.executable, str(PROJECT / "shared/control.py"),
                                     application, "switch", profile], check=False).returncode
        else:
            result = backend(application, "switch", profile)
        if result == 0:
            assign(application, profile)
        return result
    if command == "stop" and len(args) == 2:
        return backend(args[1], "stop")
    if command in {"status", "on", "off"} and len(args) == 2:
        result = backend(args[1], command)
        if result == 0 and command == "status":
            item = get(args[1])
            print(f"Saved settings for next start: profile {item['profile']}; kill switch "
                  f"{'on' if item['killswitch'] else 'off'}; DNS isolation "
                  f"{'on' if item['dns'] else 'off'}")
        return result
    if command == "policy" and len(args) == 4:
        application, policy, value = args[1:]
        if policy not in {"killswitch", "dns"}:
            return usage()
        if value not in {"on", "off"}:
            return usage()
        if value == "on" and sys.platform in {"darwin", "win32"}:
            raise AppError(f"Strict per-app {policy} is unavailable on {sys.platform}; "
                           "the Mihomo TUN backend cannot guarantee it.")
        if policy == "dns" and value == "on" and not get(application)["killswitch"]:
            raise AppError("Enable the kill switch before DNS isolation.")
        if policy == "killswitch" and value == "off" and get(application)["dns"]:
            raise AppError("Disable DNS isolation before disabling the kill switch.")
        item = set_policy(application, policy, value == "on")
        print(f"{application}: {policy} {'on' if item[policy] else 'off'} "
              "(takes effect on the next start).")
        return 0
    if command == "helper" and len(args) == 4 and args[1] == "add":
        item = add_helper(args[2], args[3])
        print(f"Helper registered for {args[2]}: {item['helpers'][-1]} (takes effect on the next start).")
        return 0
    return usage()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AppError, OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"vpngo: {error}", file=sys.stderr)
        sys.exit(1)
