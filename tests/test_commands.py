"""Exercise the common command surface without starting VPN processes."""

import atexit
import base64
import contextlib
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))
# Keep module imports away from the developer's real settings.
TEST_HOME = Path(tempfile.mkdtemp(prefix="vpngo-test-home-"))
atexit.register(shutil.rmtree, TEST_HOME, ignore_errors=True)
os.environ.update(HOME=str(TEST_HOME), XDG_CONFIG_HOME=str(TEST_HOME / ".config"),
                  APPDATA=str(TEST_HOME / "AppData"), LOCALAPPDATA=str(TEST_HOME / "LocalAppData"))

import apps
import assignments
import commands
import profiles
import managed
import vault


class UnifiedCommandTest(unittest.TestCase):
    def setUp(self):
        # Most cases below describe the Linux CLI. Windows has an explicit case.
        platform = patch.object(commands.sys, "platform", "linux")
        platform.start()
        self.addCleanup(platform.stop)
        reconcile = patch.object(managed, "reconcile_temporary", return_value=[])
        reconcile.start()
        self.addCleanup(reconcile.stop)
        # A stand-in for the OS key store: CI runners have neither user systemd-creds nor a keyring.
        for patcher in (patch.object(vault, "backend", return_value="dpapi"),
                        patch.object(vault, "dpapi", side_effect=lambda data, protect: bytes(
                            byte ^ 0x5A for byte in data))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_temporary_run_uses_profile_without_saving_assignment(self):
        with (patch.object(commands, "resolve"),
              patch.object(commands, "backend", return_value=0) as backend,
              patch.object(commands, "assign") as assign):
            self.assertEqual(commands.main(["--temp", "east", "./dota2"]), 0)
            self.assertEqual(commands.main(["start", "./dota2", "east", "--temp"]), 0)
        self.assertEqual(backend.call_count, 2)
        backend.assert_any_call("--temp", "east", "./dota2")
        assign.assert_not_called()

    def test_detached_temporary_run_accepts_only_documented_flags(self):
        with (patch.object(commands, "resolve"),
              patch.object(commands, "backend", return_value=0) as backend,
              patch.dict(os.environ, {"VPNGO_LANG": "en-US"}),
              contextlib.redirect_stderr(io.StringIO()) as errors):
            self.assertEqual(commands.main(["--temp", "east", "kitty", "-d"]), 0)
            self.assertEqual(commands.main(["start", "kitty", "east", "--temp", "--detach"]), 0)
            self.assertEqual(commands.main(["--tempo", "east", "kitty"]), 2)
            self.assertEqual(commands.main(["--temp", "east", "kitty", "--detatch"]), 2)
        self.assertEqual(backend.call_count, 2)
        backend.assert_any_call("--temp", "east", "kitty", "-d")
        self.assertIn("vpngo --temp <profile> <executable> [-d]", errors.getvalue())

    def test_short_usage_and_described_help(self):
        with patch.dict(os.environ, {"VPNGO_LANG": "en-US"}), contextlib.redirect_stderr(io.StringIO()) as output:
            self.assertEqual(commands.main([]), 2)
        self.assertEqual(output.getvalue().count("\n"), 4)
        with patch.dict(os.environ, {"VPNGO_LANG": "en-US"}), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(commands.main(["help"]), 0)
        self.assertIn("Run once without saving", output.getvalue())
        self.assertIn("-d, --detach", output.getvalue())
        self.assertIn("vpngo help <command>", output.getvalue())

    def test_every_command_has_read_only_topic_help(self):
        topics = (
            "help", "profile", "profile add", "profile list", "assign", "start",
            "--temp", "switch", "stop", "status", "on", "off", "policy",
            "policy killswitch", "policy dns", "helper", "helper add", "config", "version",
            "setup", "profiles", "-d", "profile remove", "profile import", "check", "app", "app remove", "group", "update",
        )
        with (patch.dict(os.environ, {"VPNGO_LANG": "en-US"}),
              patch.object(commands, "backend") as backend):
            for topic in topics:
                with self.subTest(topic=topic), contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(commands.main(["help", *topic.split()]), 0)
                    self.assertTrue(output.getvalue().startswith("Usage: vpngo"))
            backend.assert_not_called()
        with (patch.dict(os.environ, {"VPNGO_LANG": "pt-BR"}),
              contextlib.redirect_stdout(io.StringIO()) as output):
            self.assertEqual(commands.main(["help", "switch"]), 0)
            self.assertIn("Troca o perfil VPN", output.getvalue())

    def test_unknown_help_topic_is_an_error(self):
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(commands.main(["help", "unknown"]), 2)
        self.assertIn("vpngo help", errors.getvalue())

    def test_windows_temporary_run_uses_positional_backend_token(self):
        with (patch.object(commands.sys, "platform", "win32"),
              patch.object(commands, "resolve"),
              patch.object(commands, "backend", return_value=0) as backend):
            self.assertEqual(commands.main(["--temp", "east", "dota2.exe"]), 0)
            self.assertEqual(commands.main(["--temp", "east", "dota2.exe", "-d"]), 0)
        backend.assert_any_call("temp", "east", "dota2.exe")
        backend.assert_any_call("temp", "east", "dota2.exe", "detach")

    def test_assignment_persists_and_start_uses_it(self):
        private = base64.b64encode(b"a" * 32).decode()
        public = base64.b64encode(b"b" * 32).decode()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "example-app.exe"
            executable.write_text("#!/bin/sh\nexit 0\n")
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
            wireguard = root / "east.conf"
            wireguard.write_text(
                f"[Interface]\nPrivateKey = {private}\nAddress = 10.0.0.2/32\nDNS = 10.0.0.1\n"
                f"[Peer]\nPublicKey = {public}\nEndpoint = 203.0.113.1:51820\n"
                "AllowedIPs = 0.0.0.0/0\n"
            )
            (root / "profiles.json").write_text("{}")
            with (patch.object(apps, "REGISTRY", root / "apps.json"),
                  patch.object(profiles, "REGISTRY", root / "profiles.json"),
                  patch.object(assignments, "REGISTRY", root / "assignments.json"),
                  patch.object(commands, "backend", return_value=0) as backend,
                  contextlib.redirect_stdout(io.StringIO())):
                apps.add_path(executable)
                self.assertEqual(commands.main(["profile", "add", "east", str(wireguard)]), 0)
                self.assertEqual(commands.main(["assign", "example-app", "east"]), 0)
                self.assertEqual(commands.main(["policy", "example-app", "killswitch", "on"]), 0)
                self.assertEqual(commands.main(["policy", "example-app", "dns", "on"]), 0)
                self.assertEqual(commands.main(["start", "example-app"]), 0)
                self.assertEqual(assignments.get("example-app")["profile"], "east")
                self.assertTrue(assignments.get("example-app")["dns"])
            backend.assert_called_once_with("example-app", "start", "east")
            saved = json.loads((root / "assignments.json").read_text())
            self.assertEqual(saved["example-app"]["profile"], "east")
            if os.name == "posix":
                self.assertEqual((root / "assignments.json").stat().st_mode & 0o777, 0o600)

    def test_profile_import_names_profiles_after_files_and_skips_bad_ones(self):
        private = base64.b64encode(b"a" * 32).decode()
        public = base64.b64encode(b"b" * 32).decode()
        conf = (f"[Interface]\nPrivateKey = {private}\nAddress = 10.0.0.2/32\n"
                f"[Peer]\nPublicKey = {public}\nEndpoint = 203.0.113.1:51820\nAllowedIPs = 0.0.0.0/0\n")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / "downloads"
            (folder / "nested").mkdir(parents=True)
            (folder / "wg-NL-FREE-12.conf").write_text(conf)
            (folder / "broken.conf").write_text("[Interface]\n")
            (folder / "notes.txt").write_text(conf)
            (folder / "nested" / "deep.conf").write_text(conf)
            archive = root / "proton.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("configs/JP FREE#3.conf", conf)
                output.writestr("configs/wg-nl-free-12.conf", conf)
                output.writestr("__MACOSX/._x.conf", "junk")
            (root / "profiles.json").write_text("{}")
            with (patch.object(profiles, "REGISTRY", root / "profiles.json"),
                  patch.dict(os.environ, {"VPNGO_LANG": "en-US"}),
                  contextlib.redirect_stdout(io.StringIO()) as output,
                  contextlib.redirect_stderr(io.StringIO()) as errors):
                self.assertEqual(commands.main(["profile", "import", str(folder), str(archive)]), 1)
                self.assertEqual(sorted(profiles.load()), ["jp-free-3", "wg-nl-free-12"])
                self.assertIn("2 profile(s) imported", output.getvalue())
                self.assertIn("broken.conf", errors.getvalue())
                self.assertIn("already taken", errors.getvalue())
                self.assertNotIn("deep", output.getvalue() + errors.getvalue())
                self.assertIn("Address", profiles.read("jp-free-3"))
                (root / "empty").mkdir()
                with self.assertRaises(apps.AppError):
                    commands.main(["profile", "import", str(root / "empty")])
        self.assertEqual(profiles.import_name("2024 server.conf"), "p-2024-server")
        self.assertEqual(profiles.import_name("x" * 40 + ".conf"), "x" * 32)

    def test_failed_switch_keeps_previous_assignment(self):
        with (patch.object(commands, "resolve"),
              patch.object(commands, "backend", return_value=1),
              patch.object(commands, "assign") as assign):
            self.assertEqual(commands.main(["switch", "example-app", "west"]), 1)
        assign.assert_not_called()

    def test_check_runs_on_linux_only(self):
        with patch.object(commands, "backend", return_value=0) as backend:
            self.assertEqual(commands.main(["check", "firefox"]), 0)
            backend.assert_called_once_with("firefox", "check")
            with patch.object(commands.sys, "platform", "darwin"), self.assertRaises(apps.AppError):
                commands.main(["check", "firefox"])
            backend.assert_called_once()

    def test_stop_uses_application_backend(self):
        with patch.object(commands, "backend", return_value=0) as backend:
            self.assertEqual(commands.main(["stop", "example-app"]), 0)
        backend.assert_called_once_with("example-app", "stop")

    def test_version_reads_release_file_or_reports_dev(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            with patch.object(commands, "PROJECT", project):
                self.assertEqual(commands.version(), "dev")
                (project / "VERSION").write_text("1.2.3\n")
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(commands.main(["version"]), 0)
            self.assertEqual(output.getvalue(), "vpngo 1.2.3\n")


if __name__ == "__main__":
    unittest.main()
