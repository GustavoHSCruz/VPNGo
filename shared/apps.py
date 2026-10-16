"""Find a named application and store additional executable search locations."""

import json
import os
import plistlib
import re
import shutil
import sys
from pathlib import Path


class AppError(Exception):
    pass


def config_dir():
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData/Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "vpngo"


def mihomo_dir():
    """Mihomo's generated config and controller secret, outside the program folder
    so package upgrades never remove them. The launchers use the same path."""
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local") / "vpngo" / "mihomo"
    return Path.home() / ".local/state/vpngo/mihomo"


REGISTRY = config_dir() / "apps.json"


def key(name):
    value = name.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,79}", value):
        raise AppError("Use an application name without path separators or special characters.")
    return re.sub(r"\.(?:exe|app)$", "", value, flags=re.I).casefold()


def load():
    if not REGISTRY.exists():
        return {"files": {}, "directories": []}
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict) or not isinstance(data.get("directories"), list):
        raise AppError("The application registry is invalid.")
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
    if os.name == "posix":
        temporary.chmod(0o600)
    temporary.replace(REGISTRY)


def is_executable(path):
    return path.is_file() and (os.name == "nt" and path.suffix.lower() == ".exe" or
                               os.name != "nt" and os.access(path, os.X_OK))


def bundle_executable(bundle):
    info = bundle / "Contents/Info.plist"
    if not info.is_file():
        raise AppError(f"Invalid macOS application bundle: {bundle}")
    with info.open("rb") as source:
        binary = plistlib.load(source).get("CFBundleExecutable")
    if not binary:
        raise AppError(f"Application bundle has no executable: {bundle}")
    path = bundle / "Contents/MacOS" / binary
    if not is_executable(path):
        raise AppError(f"Application executable is unavailable: {path}")
    return path.resolve()


def describe(path):
    path = path.expanduser().resolve()
    if sys.platform == "darwin" and path.is_dir() and path.suffix.lower() == ".app":
        executable = bundle_executable(path)
        return {"executable": str(executable), "launch": str(path),
                "process": executable.name, "bundle": str(path)}
    if not is_executable(path):
        raise AppError(f"Not an executable file: {path}")
    return {"executable": str(path), "launch": str(path), "process": path.name}


def add_path(raw_path):
    path = Path(raw_path).expanduser().resolve()
    if not path.exists():
        raise AppError(f"Path does not exist: {path}")
    data = load()
    if sys.platform == "darwin" and path.is_dir() and path.suffix.lower() == ".app":
        data["files"][key(path.stem)] = str(path)
    elif path.is_dir():
        if str(path) not in data["directories"]:
            data["directories"].append(str(path))
    else:
        describe(path)
        data["files"][key(path.stem)] = str(path)
    save(data)
    return path


def directory_match(directory, name):
    if not directory.is_dir():
        return None
    wanted = key(name)
    for child in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
        try:
            if key(child.stem if child.suffix.lower() in {".exe", ".app"} else child.name) == wanted:
                return describe(child)
        except AppError:
            continue
    return None


def standard_paths(name):
    if sys.platform == "darwin":
        for directory in (Path("/Applications"), Path.home() / "Applications"):
            found = directory_match(directory, name)
            if found:
                return found
    if os.name == "nt":
        wanted = key(name)
        roots = [os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramFiles"),
                 os.environ.get("ProgramFiles(x86)")]
        for raw_root in filter(None, roots):
            root = Path(raw_root)
            if not root.is_dir():
                continue
            # Search the normal install areas to a limited depth. Additional
            # locations can always be registered explicitly with `config`.
            for current, dirs, files in os.walk(root):
                depth = len(Path(current).relative_to(root).parts)
                if depth >= 4:
                    dirs[:] = []
                else:
                    dirs[:] = [item for item in dirs if item.lower() not in {"cache", "caches", "node_modules", "temp"}]
                for filename in files:
                    if filename.lower().endswith(".exe"):
                        try:
                            if key(Path(filename).stem) == wanted:
                                return describe(Path(current) / filename)
                        except AppError:
                            continue
    return None


def find(name):
    wanted = key(name)
    data = load()
    explicit = data["files"].get(wanted)
    if explicit:
        try:
            return describe(Path(explicit))
        except AppError:
            raise AppError(f"Configured application is unavailable: {explicit}") from None
    candidate = shutil.which(name)
    if candidate:
        return describe(Path(candidate))
    for raw_directory in os.environ.get("PATH", "").split(os.pathsep):
        if raw_directory:
            found = directory_match(Path(raw_directory), name)
            if found:
                return found
    for raw_directory in data["directories"]:
        found = directory_match(Path(raw_directory), name)
        if found:
            return found
    found = standard_paths(name)
    if found:
        return found
    raise AppError(f"Application '{name}' was not found. Add its executable or bin folder with: vpngo config <path>")


def find_temporary(name):
    """Resolve a one-off executable without adding it to the app registry."""
    if os.path.isabs(name) or os.sep in name or (os.altsep and os.altsep in name):
        return describe(Path(name))
    local = Path.cwd() / name
    if local.exists():
        return describe(local)
    if os.name == "nt" and not local.suffix:
        executable = local.with_suffix(".exe")
        if executable.exists():
            return describe(executable)
    return find(name)


if __name__ == "__main__":
    try:
        if len(sys.argv) == 3 and sys.argv[1] == "config":
            print(f"Application path registered: {add_path(sys.argv[2])}")
        elif len(sys.argv) == 3 and sys.argv[1] == "resolve":
            print(json.dumps(find(sys.argv[2]), ensure_ascii=False))
        else:
            raise AppError("Usage: vpngo config <bin-dir|executable>")
    except (AppError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"vpngo: {error}", file=sys.stderr)
        sys.exit(1)
