"""Named WireGuard configurations shared by all platform launchers."""

import json
import os
import re
import sys
from pathlib import Path

from apps import AppError, config_dir


REGISTRY = config_dir() / "profiles.json"


def profile_key(name):
    value = name.casefold()
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", value):
        raise AppError("Profile names must start with a letter and contain only letters, digits, '_' or '-'.")
    return value


def load():
    if REGISTRY.is_file():
        data = json.loads(REGISTRY.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not all(
            isinstance(value, str) and profile_key(name) == name
            for name, value in data.items()
        ):
            raise AppError("The VPN profile registry is invalid.")
        return data
    legacy = config_dir() / "wireguard.conf"
    return {"default": str(legacy.resolve())} if legacy.is_file() else {}


def save(data):
    REGISTRY.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if os.name == "posix":
        REGISTRY.parent.chmod(0o700)
    temporary = REGISTRY.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(data, output, indent=2)
        output.write("\n")
    if os.name == "posix":
        temporary.chmod(0o600)
    temporary.replace(REGISTRY)


def register(path, name="default"):
    name = profile_key(name)
    source = Path(path).expanduser().resolve(strict=True)
    if not source.is_file():
        raise AppError(f"WireGuard configuration is not a file: {source}")
    from generate_mihomo import parse_wireguard
    parse_wireguard(source)
    data = load()
    data[name] = str(source)
    save(data)
    return source


def resolve(name="default"):
    name = profile_key(name)
    data = load()
    if name not in data:
        raise AppError(f"VPN profile '{name}' was not found. Add it with: vpngo profile add {name} <wireguard.conf>")
    source = Path(data[name])
    if not source.is_file():
        raise AppError(f"WireGuard configuration for profile '{name}' is unavailable: {source}")
    return source


def parsed_profiles():
    from generate_mihomo import parse_wireguard
    return {name: parse_wireguard(resolve(name)) for name in load()}


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["list"]:
            print("\n".join(sorted(load())) or "No VPN profiles configured.")
        else:
            raise AppError("Usage: vpngo profiles")
    except (AppError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"vpngo: {error}", file=sys.stderr)
        sys.exit(1)
