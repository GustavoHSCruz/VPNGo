"""Named WireGuard configurations shared by all platform launchers."""

import json
import os
import re
import sys
import zipfile
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
    name = profile_key(name)
    source = Path(path).expanduser().resolve(strict=True)
    if not source.is_file():
        raise AppError(f"WireGuard configuration is not a file: {source}")
    store(name, source.read_text(encoding="utf-8"))
    return source


def store(name, text):
    """Validate WireGuard text and save it, encrypted, as profile name."""
    import vault
    from generate_mihomo import parse_wireguard_text
    name = profile_key(name)
    parse_wireguard_text(text)
    sealed = vault.seal(name, text)
    data = load()
    previous = data.get(name)
    data[name] = str(sealed)
    save(data)
    if previous and Path(previous) != sealed:
        vault.discard(previous)


MAX_CONF_BYTES = 64 * 1024  # A WireGuard client file is well under 1 KiB.


def import_name(filename):
    """A profile name from a file name: wg-NL-FREE-12.conf becomes wg-nl-free-12."""
    stem = re.sub(r"[^a-z0-9_-]+", "-", Path(filename).stem.casefold()).strip("-_")
    if stem and not stem[0].isalpha():
        stem = "p-" + stem
    return profile_key(stem[:32].rstrip("-_"))


def import_sources(paths):
    """(origin, file name, text) of every .conf in the given files, folders and .zip archives.

    A folder is read without its subfolders; an archive is read in memory, never extracted.
    """
    found = []
    for value in paths:
        path = Path(value).expanduser().resolve(strict=True)
        if path.is_dir():
            files = sorted(item for item in path.iterdir() if item.suffix.casefold() == ".conf" and item.is_file())
            found += [(str(item), item.name, item) for item in files]
        elif zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                for member in sorted(archive.infolist(), key=lambda item: item.filename):
                    name = Path(member.filename).name
                    if member.is_dir() or not name.casefold().endswith(".conf") or name.startswith("."):
                        continue
                    origin = f"{path}:{member.filename}"
                    if member.file_size > MAX_CONF_BYTES:
                        found.append((origin, name, AppError("File is too large to be a WireGuard configuration.")))
                    else:
                        found.append((origin, name, archive.read(member).decode("utf-8")))
        elif path.is_file():
            found.append((str(path), path.name, path))
        else:
            raise AppError(f"Not a file, folder or .zip archive: {path}")
    return found


def import_profiles(paths):
    """Save each .conf found in paths as a profile named after its file.

    Returns (saved, failed): saved maps each profile name to its origin; failed lists
    (origin, error) for files that were refused. One bad file does not stop the others.
    """
    saved, failed = {}, []
    for origin, filename, content in import_sources(paths):
        try:
            if isinstance(content, Exception):
                raise content
            name = import_name(filename)
            if name in saved:
                raise AppError(f"Profile name '{name}' is already taken by {saved[name]}; rename one file.")
            if isinstance(content, Path):
                if content.stat().st_size > MAX_CONF_BYTES:
                    raise AppError("File is too large to be a WireGuard configuration.")
                content = content.read_text(encoding="utf-8")
            store(name, content)
            saved[name] = origin
        except (AppError, OSError, ValueError, UnicodeDecodeError) as error:
            failed.append((origin, error))
    return saved, failed


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
