"""`vpngo update`: install the latest release over this installation.

It runs the release's own installer for this system (the same one users run by hand, and the
one the release workflow tests upgrading with), after checking it against the release's
SHA256SUMS. The installer verifies the archive, swaps the program folder, checks the new
version and restores the previous one if anything fails. Settings and profiles live outside
the program folder and are kept.

Only release installations update this way: a source checkout says "dev", and a package
manager (Homebrew, Scoop, AUR, .deb, .rpm) updates with its own upgrade command.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from apps import AppError


REPOSITORY = "GustavoHSCruz/VPNGo"
PROJECT = Path(__file__).resolve().parent.parent
INSTALLERS = {"linux": "install-linux.sh", "darwin": "install-macos.sh", "win32": "install-windows.ps1"}


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "vpngo"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    except OSError as error:
        raise AppError(f"Could not download {url}: {error}") from None


def parse(version):
    try:
        return tuple(int(part) for part in version.split("-")[0].split("."))
    except ValueError:
        return None


def latest_version():
    data = json.loads(fetch(f"https://api.github.com/repos/{REPOSITORY}/releases/latest"))
    tag = str(data.get("tag_name", ""))
    if not tag.startswith("v") or not parse(tag[1:]):
        raise AppError("Could not find the latest vpngo release.")
    return tag[1:]


def system():
    return "linux" if sys.platform.startswith("linux") else sys.platform


def release_install():
    """The folder the release installer manages (<prefix>/app), or why this copy cannot update itself."""
    if PROJECT.name != "app" or not (PROJECT / "VERSION").is_file():
        return None
    return PROJECT.parent


def update(current, check_only=False):
    if current == "dev":
        raise AppError("This is a source checkout (version 'dev'); update it with git pull.")
    prefix = release_install()
    if prefix is None:
        raise AppError("This vpngo was installed by a package manager; update it with that manager's "
                       "upgrade command (brew upgrade, scoop update, your distribution's updater).")
    if system() not in INSTALLERS:
        raise AppError(f"vpngo update is not available on {sys.platform}.")
    latest = latest_version()
    if parse(latest) <= parse(current):
        print(f"vpngo {current} is the latest version.")
        return 0
    if check_only:
        print(f"vpngo {latest} is available (installed: {current}). Run 'vpngo update' to install it.")
        return 0
    base = os.environ.get("VPNGO_RELEASE_URL") or f"https://github.com/{REPOSITORY}/releases/download/v{latest}"
    name = INSTALLERS[system()]
    installer = fetch(f"{base}/{name}")
    sums = fetch(f"{base}/SHA256SUMS").decode("utf-8")
    expected = next((line.split()[0] for line in sums.splitlines()
                     if len(line.split()) == 2 and line.split()[1].lstrip("*") == name), None)
    if not expected or hashlib.sha256(installer).hexdigest() != expected:
        raise AppError(f"The {name} download does not match SHA256SUMS; nothing was changed.")
    print(f"Updating vpngo {current} to {latest}...", flush=True)
    with tempfile.TemporaryDirectory(prefix="vpngo-update-") as work:
        script = Path(work) / name
        script.write_bytes(installer)
        if system() == "win32":
            command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
        else:
            command = ["sh", str(script)]
        environment = {**os.environ, "VPNGO_VERSION": latest, "VPNGO_PREFIX": str(prefix)}
        # Run from outside the program folder: the installer replaces it.
        return subprocess.run(command, env=environment, cwd=work, check=False).returncode
