"""Named groups of apps, so one command turns a whole set on, off or onto another profile.

An app belongs to at most one group: adding it to a group moves it out of any other,
which keeps "turn this group on" unambiguous.
"""

import json
import os
import re

from apps import AppError, config_dir, key


REGISTRY = config_dir() / "groups.json"


def group_key(name):
    value = name.strip().casefold()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", value):
        raise AppError("Group names start with a letter or digit and contain only letters, digits, '_' or '-'.")
    return value


def load():
    if not REGISTRY.is_file():
        return {}
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(
            group_key(name) == name and isinstance(item, dict) and isinstance(item.get("apps"), list) and
            all(isinstance(app, str) and key(app) == app for app in item["apps"])
            for name, item in data.items()):
        raise AppError("The group registry is invalid.")
    return data


def save(data):
    REGISTRY.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if os.name == "posix":
        REGISTRY.parent.chmod(0o700)
    temporary = REGISTRY.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(data, output, indent=2, ensure_ascii=False)
        output.write("\n")
    temporary.replace(REGISTRY)


def members(group):
    name = group_key(group)
    data = load()
    if name not in data:
        raise AppError(f"Group '{name}' was not found. Create it with: vpngo group add {name} <app>...")
    return list(data[name]["apps"])


def add(group, applications):
    """Add apps to a group (creating it); returns {app: group it moved from}."""
    from apps import find
    name = group_key(group)
    wanted = []
    for application in applications:
        find(application)
        if key(application) not in wanted:
            wanted.append(key(application))
    data = load()
    moved = {}
    for other, item in data.items():
        if other != name:
            for app in wanted:
                if app in item["apps"]:
                    item["apps"].remove(app)
                    moved[app] = other
    current = data.setdefault(name, {"apps": []})["apps"]
    current.extend(app for app in wanted if app not in current)
    save({other: item for other, item in data.items() if item["apps"] or other == name})
    return moved


def remove(group, applications=()):
    """Remove apps from a group, or the whole group when no app is named. The apps themselves stay."""
    name = group_key(group)
    data = load()
    if name not in data:
        raise AppError(f"Group '{name}' was not found.")
    if applications:
        gone = {key(application) for application in applications}
        missing = gone - set(data[name]["apps"])
        if missing:
            raise AppError(f"Not in group '{name}': {', '.join(sorted(missing))}.")
        data[name]["apps"] = [app for app in data[name]["apps"] if app not in gone]
    if not applications or not data[name]["apps"]:
        del data[name]
    save(data)


def forget(application):
    """Drop an app from every group (when the app itself is removed)."""
    data = load()
    name = key(application)
    if any(name in item["apps"] for item in data.values()):
        for item in data.values():
            if name in item["apps"]:
                item["apps"].remove(name)
        save({group: item for group, item in data.items() if item["apps"]})
