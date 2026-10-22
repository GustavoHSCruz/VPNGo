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
    """Copy a WireGuard file into vpngo's profiles folder, encrypted (see vault.py).

    The original file is not changed; it is no longer needed afterwards.
    """
    import vault
    from generate_mihomo import parse_wireguard_text
    name = profile_key(name)
    source = Path(path).expanduser().resolve(strict=True)
    if not source.is_file():
        raise AppError(f"WireGuard configuration is not a file: {source}")
    text = source.read_text(encoding="utf-8")
    parse_wireguard_text(text)
    sealed = vault.seal(name, text)
    data = load()
    previous = data.get(name)
    data[name] = str(sealed)
    save(data)
    if previous and Path(previous) != sealed:
        vault.discard(previous)
    return source


def unregister(name):
    """Forget a profile and delete its encrypted copy. A file it was added from stays where it is."""
    import vault
    name = profile_key(name)
    data = load()
    if name not in data:
        raise AppError(f"VPN profile '{name}' was not found.")
    path = data.pop(name)
    save(data)
    vault.discard(path)
    return name


def resolve(name="default"):
    """The stored file of a profile (encrypted, or a plain .conf registered before v0.7.0)."""
    name = profile_key(name)
    data = load()
    if name not in data:
        raise AppError(f"VPN profile '{name}' was not found. Add it with: vpngo profile add {name} <wireguard.conf>")
    source = Path(data[name])
    if not source.is_file():
        raise AppError(f"WireGuard configuration for profile '{name}' is unavailable: {source}")
    return source


def read(name="default"):
    """A profile's WireGuard text, decrypted in memory."""
    import vault
    return vault.unseal(resolve(name))


def parsed(name="default"):
    from generate_mihomo import parse_wireguard_text
    return parse_wireguard_text(read(name))


def parsed_profiles():
    return {name: parsed(name) for name in load()}


def migrate():
    """Encrypt profiles registered as plain .conf paths (before v0.7.0).

    Returns the plain files left outside vpngo's folder, for the user to delete; a plain copy
    inside the profiles folder is deleted once its encrypted copy reads back correctly.
    """
    import vault
    data = load()
    pending = {name: Path(path) for name, path in data.items() if not vault.sealed(path) and Path(path).is_file()}
    if not pending:
        return []
    left = []
    for name, path in pending.items():
        sealed = vault.seal(name, path.read_text(encoding="utf-8"))
        data[name] = str(sealed)
        save(data)
        if path.resolve().parent == vault.STORE.resolve():
            path.unlink()
        else:
            left.append(path)
    return left


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["list"]:
            print("\n".join(sorted(load())) or "No VPN profiles configured.")
        else:
            raise AppError("Usage: vpngo profiles")
    except (AppError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"vpngo: {error}", file=sys.stderr)
        sys.exit(1)
