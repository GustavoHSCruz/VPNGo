#!/usr/bin/env python3
"""Build the per-system release archives, installers and SHA256SUMS for one version.

The archives are reproducible: entries are sorted, owned by root, and stamped
with the commit time (or SOURCE_DATE_EPOCH), so the same commit always yields
the same bytes.
"""

import argparse
import gzip
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
COMMON = ("LICENSE", "NOTICE", "README.md", "docs/", "shared/")
SYSTEMS = {
    "linux": ("linux/", "tests/manual/"),
    "macos": ("macos/",),
    "windows": ("windows/",),
}
INSTALLERS = {
    "install-linux.sh": "linux",
    "install-macos.sh": "macos",
    "install-windows.ps1": "windows",
}
# One archive per system, in the format its installer and package manager download.
ARCHIVES = {"linux": "tar.gz", "macos": "tar.gz", "windows": "zip"}
VERSION_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?")
DEFAULT_REPOSITORY = "GustavoHSCruz/VPNGo"


def git(*arguments):
    return subprocess.run(["git", *arguments], cwd=ROOT, check=True,
                          stdout=subprocess.PIPE, text=True).stdout


def tracked_files():
    """Map each tracked path to whether git records it as executable."""
    files = {}
    for line in git("ls-files", "-s", "-z").split("\0"):
        if line:
            meta, path = line.split("\t", 1)
            files[path] = meta.split()[0] == "100755"
    return files


def select(files, system):
    prefixes = COMMON + SYSTEMS[system]
    chosen = {path: executable for path, executable in files.items()
              if path.startswith(prefixes) and "__pycache__" not in path}
    if not any(path.startswith(f"{system}/") for path in chosen):
        raise SystemExit(f"No {system} launcher files are tracked.")
    return dict(sorted(chosen.items()))


def entries(files, version, top):
    """Yield (archive path, mode, data or None for a directory) in a stable order."""
    directories = {top}
    for path in files:
        parts = Path(path).parts[:-1]
        for index in range(1, len(parts) + 1):
            directories.add(f"{top}/{'/'.join(parts[:index])}")
    for directory in sorted(directories):
        yield directory + "/", 0o755, None
    items = [(f"{top}/{path}", 0o755 if executable else 0o644, (ROOT / path).read_bytes())
             for path, executable in files.items()]
    items.append((f"{top}/VERSION", 0o644, f"{version}\n".encode()))
    yield from sorted(items)


def tar_bytes(items, epoch):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for name, mode, data in items:
            info = tarfile.TarInfo(name.rstrip("/"))
            info.mode, info.mtime = mode, epoch
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            if data is None:
                info.type = tarfile.DIRTYPE
                archive.addfile(info)
            else:
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def zip_bytes(items, epoch):
    stamp = max(epoch, 315532800)  # ZIP cannot store dates before 1980.
    date_time = time.gmtime(stamp)[:6]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, mode, data in items:
            info = zipfile.ZipInfo(name, date_time)
            info.create_system = 3  # Unix, so permissions survive on Linux and macOS.
            if data is None:
                info.external_attr = (0o40000 | mode) << 16 | 0x10
                archive.writestr(info, b"")
            else:
                info.external_attr = (0o100000 | mode) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, data, compresslevel=9)
    return buffer.getvalue()


def gzip_bytes(tar, epoch):
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=epoch, compresslevel=9) as output:
        output.write(tar)
    return buffer.getvalue()


def linux_packages(items, version, epoch):
    """Build the .deb and .rpm with nfpm from the same files as the Linux archives."""
    nfpm = shutil.which(os.environ.get("NFPM", "nfpm"))
    if not nfpm:
        raise SystemExit("--linux-packages needs nfpm (https://nfpm.goreleaser.com) on PATH or in NFPM.")
    with tempfile.TemporaryDirectory() as temporary:
        root, out = Path(temporary) / "root", Path(temporary) / "out"
        out.mkdir()
        top = items[0][0].rstrip("/")
        for name, mode, data in items:
            path = root / "tree" / name[len(top) + 1:]
            if data is None:
                path.mkdir(parents=True, exist_ok=True)
                path.chmod(mode)
            else:
                path.write_bytes(data)
                path.chmod(mode)
        for path in sorted(root.rglob("*"), reverse=True):  # Files before their folders.
            os.utime(path, (epoch, epoch))
        env = {**os.environ, "VPNGO_VERSION": version, "SOURCE_DATE_EPOCH": str(epoch)}
        for packager in ("deb", "rpm"):
            subprocess.run([nfpm, "package", "--config", str(ROOT / "packaging/nfpm.yaml"),
                            "--packager", packager, "--target", f"{out}/"],
                           check=True, env=env, cwd=root, stdout=subprocess.DEVNULL)
        return {path.name: path.read_bytes() for path in sorted(out.iterdir())}


def installer(name, version, repository):
    text = (ROOT / "packaging" / name).read_text(encoding="utf-8")
    for placeholder in ("@VERSION@", "@REPOSITORY@"):
        if placeholder not in text:
            raise SystemExit(f"{name} is missing {placeholder}.")
    return text.replace("@VERSION@", version).replace("@REPOSITORY@", repository).encode()


def main():
    cli = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    cli.add_argument("--version", required=True, help="release version without the leading v, e.g. 1.2.3")
    cli.add_argument("--out", type=Path, default=ROOT / "dist", help="output directory (default: dist)")
    cli.add_argument("--linux-packages", action="store_true",
                     help="also build the .deb and .rpm packages (needs nfpm)")
    cli.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPOSITORY),
                     help="GitHub owner/name the installers download from")
    args = cli.parse_args()
    if not VERSION_PATTERN.fullmatch(args.version):
        cli.error("version must look like 1.2.3 or 1.2.3-rc.1, without a leading v")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
        cli.error("repository must be owner/name")
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH") or git("log", "-1", "--format=%ct").strip())

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    stale = [path for path in out.iterdir() if path.name.startswith(("vpngo-", "vpngo_")) or
             path.name in INSTALLERS or path.name == "SHA256SUMS"]
    for path in stale:
        path.unlink()

    files = tracked_files()
    assets = {}
    for system in SYSTEMS:
        top = f"vpngo-{args.version}-{system}"
        items = list(entries(select(files, system), args.version, top))
        suffix = ARCHIVES[system]
        assets[f"{top}.{suffix}"] = (zip_bytes(items, epoch) if suffix == "zip" else
                                     gzip_bytes(tar_bytes(items, epoch), epoch))
        if system == "linux" and args.linux_packages:
            assets.update(linux_packages(items, args.version, epoch))
    for name in INSTALLERS:
        assets[name] = installer(name, args.version, args.repository)

    lines = []
    for name, data in sorted(assets.items()):
        target = out / name
        target.write_bytes(data)
        target.chmod(0o755 if name.endswith(".sh") else 0o644)
        lines.append(f"{hashlib.sha256(data).hexdigest()}  {name}\n")
    (out / "SHA256SUMS").write_text("".join(lines), encoding="utf-8")
    print(f"Built vpngo {args.version}: {len(assets)} files and SHA256SUMS in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
