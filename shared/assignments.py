"""Persist application-to-profile assignments and optional routing policies."""

import json
import os
import sys
from pathlib import Path

from apps import AppError, config_dir, find, key
from profiles import profile_key, resolve


REGISTRY = config_dir() / "assignments.json"


def load():
    if not REGISTRY.is_file():
        return {}
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AppError("The application assignment registry is invalid.")
    for name, item in data.items():
        if key(name) != name or not isinstance(item, dict):
            raise AppError("The application assignment registry is invalid.")
        profile_key(item.get("profile", "default"))
        if not isinstance(item.get("killswitch", True), bool) or not isinstance(item.get("dns", False), bool):
            raise AppError("The application assignment registry is invalid.")
        helpers = item.get("helpers", [])
        if not isinstance(helpers, list) or not all(isinstance(value, str) for value in helpers):
            raise AppError("The application assignment registry is invalid.")
    return data


def save(data):
    REGISTRY.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if os.name == "posix":
        REGISTRY.parent.chmod(0o700)
    temporary = REGISTRY.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(data, output, indent=2, ensure_ascii=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        if os.name == "posix":
            temporary.chmod(0o600)
        temporary.replace(REGISTRY)
        if os.name == "posix":
            directory = os.open(REGISTRY.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def get(application):
    return load().get(key(application), {
        "profile": "default", "killswitch": sys.platform == "linux", "dns": False, "helpers": [],
    })


def assign(application, profile):
    find(application)
    profile = profile_key(profile)
    resolve(profile)
    data = load()
    existing = get(application)
    data[key(application)] = {**existing, "profile": profile}
    save(data)
    return data[key(application)]


def set_policy(application, policy, enabled):
    if policy not in {"killswitch", "dns"}:
        raise AppError("Policy must be 'killswitch' or 'dns'.")
    find(application)
    data = load()
    current = get(application)
    data[key(application)] = {**current, policy: enabled}
    save(data)
    return data[key(application)]


def add_helper(application, path):
    find(application)
    helper = Path(path).expanduser().resolve(strict=True)
    if not helper.is_file():
        raise AppError(f"Helper executable not found: {helper}")
    if "," in str(helper) or "\n" in str(helper):
        raise AppError("Helper paths cannot contain commas or newlines in Mihomo rules.")
    data = load()
    current = get(application)
    helpers = list(current.get("helpers", []))
    if str(helper) not in helpers:
        helpers.append(str(helper))
    data[key(application)] = {**current, "helpers": helpers}
    save(data)
    return data[key(application)]
