"""Exercise release installer rollback with local, checksum verified archives."""

import hashlib
import io
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION = "9.8.7"


def archive(mirror, system, install_status, reported_version):
    asset = f"vpngo-{VERSION}-{system}.tar.gz"
    top = f"vpngo-{VERSION}-{system}"
    with tarfile.open(mirror / asset, "w:gz") as output:
        for name, content in {
            f"{system}/install.sh": ("#!/bin/sh\nmkdir -p \"$HOME/.local/bin\"\n"
                                     f"ln -sfn \"$VPNGO_PREFIX/app/{system}/vpngo\" \"$HOME/.local/bin/vpngo\"\n"
                                     f"exit {install_status}\n"),
            f"{system}/vpngo": f"#!/bin/sh\necho 'vpngo {reported_version}'\n",
        }.items():
            data = content.encode()
            item = tarfile.TarInfo(f"{top}/{name}")
            item.mode = 0o755
            item.size = len(data)
            output.addfile(item, io.BytesIO(data))
    digest = hashlib.sha256((mirror / asset).read_bytes()).hexdigest()
    (mirror / "SHA256SUMS").write_text(f"{digest}  {asset}\n")


class InstallerRollbackTest(unittest.TestCase):
    def run_installer(self, system, install_status, reported_version):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mirror = root / "mirror"
            mirror.mkdir()
            prefix = root / "installed"
            old = prefix / "app"
            old.mkdir(parents=True)
            (old / "marker").write_text("previous version")
            shim = root / ".local/bin/vpngo"
            shim.parent.mkdir(parents=True)
            shim.symlink_to(root / "other-install/vpngo")
            archive(mirror, system, install_status, reported_version)
            env = {**os.environ, "HOME": str(root), "VPNGO_PREFIX": str(prefix),
                   "VPNGO_VERSION": VERSION, "VPNGO_RELEASE_URL": mirror.as_uri()}
            result = subprocess.run(["sh", str(ROOT / "packaging" / f"install-{system}.sh")],
                                    env=env, capture_output=True, text=True, check=False)
            return result, (prefix / "app" / "marker").exists(), (prefix / "app.old").exists(), \
                (prefix / "app" / system / "vpngo").exists(), shim.readlink()

    def test_failed_inner_install_restores_previous_version(self):
        for system in ("linux", "macos"):
            with self.subTest(system=system):
                result, old_restored, backup_left, _new_present, shim = self.run_installer(system, 1, VERSION)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertTrue(old_restored)
                self.assertFalse(backup_left)
                self.assertEqual(shim.name, "vpngo")
                self.assertEqual(shim.parent.name, "other-install")

    def test_wrong_version_restores_previous_version(self):
        for system in ("linux", "macos"):
            with self.subTest(system=system):
                result, old_restored, backup_left, _new_present, shim = self.run_installer(system, 0, "0.0.0")
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertTrue(old_restored)
                self.assertFalse(backup_left)
                self.assertEqual(shim.parent.name, "other-install")

    def test_valid_version_commits_upgrade(self):
        for system in ("linux", "macos"):
            with self.subTest(system=system):
                result, old_restored, backup_left, new_present, shim = self.run_installer(system, 0, VERSION)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertFalse(old_restored)
                self.assertFalse(backup_left)
                self.assertTrue(new_present)
                self.assertEqual(shim.name, "vpngo")
                self.assertEqual(shim.parent.name, system)


if __name__ == "__main__":
    unittest.main()
