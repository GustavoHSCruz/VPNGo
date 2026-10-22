"""Download, verify and install the VPNGo graphical interface (`vpngo --install-gui`).

The interface lives in its own repository and release. It is installed beside
vpngo in a private virtual environment, so PySide6 never touches the system
Python, and running the command again upgrades it in place.

VPNGO_GUI_VERSION installs another release. VPNGO_GUI_RELEASE_URL downloads
from another location, such as a local mirror. VPNGO_GUI_PREFIX changes the
install folder.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from apps import AppError


REPOSITORY = "GustavoHSCruz/VPNGo-gui"
PROJECT = Path(__file__).resolve().parent.parent


def prefix():
    if os.environ.get("VPNGO_GUI_PREFIX"):
        return Path(os.environ["VPNGO_GUI_PREFIX"]).expanduser()
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local") / "vpngo-gui"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "vpngo-gui"


def fetch(url, target=None):
    request = urllib.request.Request(url, headers={"User-Agent": "vpngo"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
    except OSError as error:
        raise AppError(f"Could not download {url}: {error}") from None
    if target is None:
        return data
    target.write_bytes(data)
    return target


def latest_version():
    data = json.loads(fetch(f"https://api.github.com/repos/{REPOSITORY}/releases/latest"))
    tag = str(data.get("tag_name", ""))
    if not tag.startswith("v"):
        raise AppError("Could not find the latest interface release.")
    return tag[1:]


def verified_archive(work, version):
    asset = f"vpngo-gui-{version}.tar.gz"
    base = os.environ.get("VPNGO_GUI_RELEASE_URL") or \
        f"https://github.com/{REPOSITORY}/releases/download/v{version}"
    archive = fetch(f"{base}/{asset}", work / asset)
    sums = fetch(f"{base}/SHA256SUMS").decode("utf-8")
    expected = next((line.split()[0] for line in sums.splitlines()
                     if len(line.split()) == 2 and line.split()[1].lstrip("*") == asset), None)
    if not expected:
        raise AppError(f"{asset} is not listed in SHA256SUMS.")
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
        raise AppError(f"Checksum mismatch for {asset}; the download is corrupt or was altered.")
    return archive


def cli_command():
    """How the interface runs this vpngo installation."""
    if sys.platform == "win32":
        return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                str(PROJECT / "windows/vpngo.ps1")]
    return [str(PROJECT / ("macos/vpngo" if sys.platform == "darwin" else "linux/vpngo"))]


def venv_python(venv):
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def install_dependencies(venv, requirements):
    """A system PySide6 (for example the distribution's package) is reused when present."""
    if not venv_python(venv).is_file():
        subprocess.run([sys.executable, "-m", "venv", "--system-site-packages", str(venv)], check=True)
    print("Installing the interface dependencies (PySide6); the first install downloads about 250 MB...",
          flush=True)
    subprocess.run([str(venv_python(venv)), "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                    "-r", str(requirements)], check=True)


def write_launchers(root):
    app = root / "app"
    if os.name == "nt":
        python = root / "venv/Scripts/pythonw.exe"
        launcher = Path.home() / "bin/vpngo-gui.cmd"
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.write_text(f'@echo off\r\nstart "" "{python}" "{app / "run.py"}" %*\r\n', encoding="utf-8")
        return launcher
    launcher = Path.home() / ".local/bin/vpngo-gui"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text(f'#!/bin/sh\nexec "{root / "venv/bin/python"}" "{app / "run.py"}" "$@"\n', encoding="utf-8")
    launcher.chmod(0o755)
    if sys.platform.startswith("linux"):
        applications = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "applications"
        applications.mkdir(parents=True, exist_ok=True)
        (applications / "vpngo-gui.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=VPNGo\n"
            "Comment=Route apps through WireGuard\nComment[pt_BR]=Aplicativos pela VPN WireGuard\n"
            f"Exec={launcher}\nIcon={app / 'vpngo_gui/assets/vpngo.svg'}\n"
            "Categories=Network;\nStartupWMClass=vpngo-gui\n", encoding="utf-8")
    return launcher


def install():
    version = os.environ.get("VPNGO_GUI_VERSION") or latest_version()
    root = prefix()
    root.mkdir(parents=True, exist_ok=True)
    if (root / "app.old").exists():
        raise AppError(f"{root / 'app.old'} exists; remove it after checking the previous interrupted upgrade.")
    print(f"Downloading the VPNGo interface {version}...", flush=True)
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        archive = verified_archive(work, version)
        print("Checksum verified.", flush=True)
        with tarfile.open(archive) as source:
            source.extractall(work, filter="data")
        unpacked = work / f"vpngo-gui-{version}"
        if not (unpacked / "run.py").is_file() or not (unpacked / "vpngo_gui/__init__.py").is_file():
            raise AppError("The interface archive has an unexpected layout.")
        install_dependencies(root / "venv", unpacked / "requirements.txt")
        shutil.rmtree(root / "app.new", ignore_errors=True)
        shutil.move(str(unpacked), root / "app.new")
    had_app = (root / "app").exists()
    if had_app:
        (root / "app").rename(root / "app.old")
    (root / "app.new").rename(root / "app")
    try:
        (root / "cli.json").write_text(json.dumps({"command": cli_command()}, indent=2) + "\n", encoding="utf-8")
        launcher = write_launchers(root)
        check = subprocess.run([str(venv_python(root / "venv")), str(root / "app/run.py"), "--version"],
                               capture_output=True, text=True, check=False)
        if check.stdout.strip() != f"vpngo-gui {version}":
            raise AppError("The installed interface did not start: " + (check.stderr.strip() or check.stdout.strip()))
    except BaseException:
        shutil.rmtree(root / "app", ignore_errors=True)
        if had_app:
            (root / "app.old").rename(root / "app")
            print("vpngo: the previous interface was restored.", file=sys.stderr)
        raise
    shutil.rmtree(root / "app.old", ignore_errors=True)
    print(f"VPNGo interface {version} installed in {root / 'app'}.")
    print(f"Open it from the application menu or run: {launcher}")
    return 0
