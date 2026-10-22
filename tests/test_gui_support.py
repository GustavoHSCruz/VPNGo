"""`vpngo status --json` and `vpngo --install-gui`, without a real VPN or download."""

import atexit
import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))
TEST_HOME = Path(tempfile.mkdtemp(prefix="vpngo-test-home-"))
atexit.register(shutil.rmtree, TEST_HOME, ignore_errors=True)
os.environ.update(HOME=str(TEST_HOME), XDG_CONFIG_HOME=str(TEST_HOME / ".config"),
                  APPDATA=str(TEST_HOME / "AppData"), LOCALAPPDATA=str(TEST_HOME / "LocalAppData"))

import assignments
import commands
import gui_install
import profiles
import state
from apps import AppError


class StatusJsonTest(unittest.TestCase):
    def setUp(self):
        self.state_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.state_dir, ignore_errors=True)
        patcher = patch.object(state, "LINUX_STATE", self.state_dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        for patcher in (patch.object(profiles, "load", return_value={"us": "/x/us.conf", "br": "/x/br.conf"}),
                        patch.object(state, "load_profiles", return_value={"us": "/x/us.conf", "br": "/x/br.conf"}),
                        patch.object(state, "load_assignments", return_value={
                            "vesktop": {"profile": "us", "killswitch": True, "dns": False},
                            "steam": {"profile": "br", "killswitch": True, "dns": False}}),
                        patch.object(state, "load_apps", return_value={"files": {"spotify": "/x/spotify"},
                                                                       "directories": []})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def vopono(self, namespaces):
        result = subprocess.CompletedProcess([], 0, json.dumps({"namespaces": namespaces}), "")
        return patch.multiple(state, shutil=type("S", (), {"which": staticmethod(lambda name: "/usr/bin/vopono")}),
                              subprocess=type("P", (), {"run": staticmethod(lambda *a, **k: result),
                                                        "TimeoutExpired": subprocess.TimeoutExpired}))

    def namespace(self, identifier, app, profile, direct=False):
        (self.state_dir / f"{identifier}.json").write_text(json.dumps({"app": app, "profile": profile}))
        if direct:
            (self.state_dir / f"{identifier}.resolv.conf").write_text("nameserver 10.2.0.1\n")
        return {"id": identifier, "protocol": "wireguard", "applications": [{"pid": 1}]}

    def test_linux_routes_come_from_vopono_sessions_without_privileges(self):
        namespaces = [self.namespace("vg_vesktop_us_1_2", "Vesktop", "us"),
                      self.namespace("vg_steam_br_3_4", "steam", "br", direct=True),
                      {"id": "someone-else", "protocol": "wireguard", "applications": [{"pid": 9}]}]
        with self.vopono(namespaces), patch.object(state.sys, "platform", "linux"):
            data = state.snapshot("1.0.0")
        by_name = {app["name"]: app for app in data["apps"]}
        self.assertEqual(data["schema"], 1)
        self.assertEqual(data["profiles"], ["br", "us"])
        self.assertEqual(set(by_name), {"vesktop", "steam", "spotify"})
        self.assertEqual((by_name["vesktop"]["state"], by_name["vesktop"]["active_profile"]), ("vpn", "us"))
        self.assertEqual(by_name["steam"]["state"], "direct")
        self.assertEqual((by_name["spotify"]["state"], by_name["spotify"]["profile"]), ("stopped", "default"))

    def test_linux_reports_start_time_endpoint_and_traffic(self):
        namespace = self.namespace("vg_vesktop_us_1_2", "vesktop", "us")
        namespace.update(created_at="2026-10-21T22:19:55Z", server={"hostname": "146.70.230.82:51820"})
        with (self.vopono([namespace]), patch.object(state.sys, "platform", "linux"),
              patch.object(state, "veth_counters", return_value={"vg_vesktop_us_1_2": {"rx_bytes": 900, "tx_bytes": 40}})):
            app = next(app for app in state.snapshot("1.0.0")["apps"] if app["name"] == "vesktop")
        self.assertEqual(app["started_at"], 1792621195.0)
        self.assertEqual(app["endpoint"], "146.70.230.82:51820")
        self.assertEqual((app["rx_bytes"], app["tx_bytes"]), (900, 40))

    def test_veth_counters_read_the_host_side_of_each_namespace(self):
        statistics = self.state_dir / "sys/vbf_d/statistics"
        statistics.mkdir(parents=True)
        (statistics / "tx_bytes").write_text("1500\n")   # host transmits = the app receives
        (statistics / "rx_bytes").write_text("300\n")
        outputs = {("netns", "list"): [{"name": "vg_a", "id": 5}],
                   ("link", "show", "type", "veth"): [{"ifname": "vbf_d", "link_netnsid": 5},
                                                      {"ifname": "veth0", "link_netnsid": 1}]}

        def run(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, json.dumps(outputs[tuple(command[2:])]), "")
        real_path = state.Path
        with (patch.object(state.subprocess, "run", side_effect=run),
              patch.object(state, "Path", side_effect=lambda value, *rest: real_path(
                  str(value).replace("/sys/class/net", str(self.state_dir / "sys")), *rest))):
            self.assertEqual(state.veth_counters(), {"vg_a": {"rx_bytes": 1500, "tx_bytes": 300}})

    def test_namespace_without_running_apps_is_stopped(self):
        namespace = self.namespace("vg_vesktop_us_1_2", "vesktop", "us")
        namespace["applications"] = []
        with self.vopono([namespace]), patch.object(state.sys, "platform", "linux"):
            data = state.snapshot("1.0.0")
        self.assertEqual(next(app for app in data["apps"] if app["name"] == "vesktop")["state"], "stopped")

    def test_mihomo_selectors_map_to_routes(self):
        mihomo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, mihomo, ignore_errors=True)
        (mihomo / "managed.json").write_text(json.dumps({
            "vesktop": {"profile": "us"}, "steam": {"profile": "br"}, "spotify": {"profile": "us", "blocked": True}}))
        (mihomo / "controller.json").write_text(json.dumps({"port": 9097, "secret": "s"}))
        from generate_mihomo import group_name
        selected = {group_name("vesktop"): "vpngo-wireguard-us", group_name("steam"): "DIRECT",
                    group_name("spotify"): "REJECT"}
        connections = {"connections": [
            {"chains": [group_name("vesktop")], "download": 1000, "upload": 10},
            {"chains": ["x"], "metadata": {"inboundName": group_name("vesktop") + "-in"}, "download": 5, "upload": 2},
            {"chains": [group_name("steam")], "download": 7, "upload": 1}]}

        def request(port, secret, method, path):
            return connections if path == "/connections" else {"now": selected[path.split("/")[-1]]}
        import control
        with (patch("apps.mihomo_dir", return_value=mihomo),
              patch.object(control, "request", side_effect=request),
              patch.object(state, "endpoint", return_value="1.2.3.4:51820"),
              patch.object(state.sys, "platform", "darwin")):
            data = state.snapshot("1.0.0")
        by_name = {app["name"]: app for app in data["apps"]}
        self.assertEqual({name: app["state"] for name, app in by_name.items()},
                         {"vesktop": "vpn", "steam": "direct", "spotify": "stopped"})
        self.assertEqual((by_name["vesktop"]["rx_bytes"], by_name["vesktop"]["tx_bytes"]), (1005, 12))
        self.assertEqual(by_name["vesktop"]["endpoint"], "1.2.3.4:51820")

    def test_command_prints_json(self):
        with (patch("state.snapshot", return_value={"schema": 1, "apps": []}),
              contextlib.redirect_stdout(io.StringIO()) as output):
            self.assertEqual(commands.main(["status", "--json"]), 0)
        self.assertEqual(json.loads(output.getvalue()), {"schema": 1, "apps": []})


class InstallGuiTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.mirror = self.root / "mirror"
        self.mirror.mkdir()
        self.home = self.root / "home"
        environment = {"HOME": str(self.home), "VPNGO_GUI_VERSION": "1.2.3",
                       "VPNGO_GUI_RELEASE_URL": self.mirror.as_uri(), "XDG_DATA_HOME": ""}
        patcher = patch.dict(os.environ, environment)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(gui_install, "install_dependencies", side_effect=self.fake_venv)
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def fake_venv(venv, requirements):
        python = gui_install.venv_python(venv)
        python.parent.mkdir(parents=True, exist_ok=True)
        if not python.exists():
            python.symlink_to(sys.executable)

    def publish(self, version="1.2.3", reported=None, corrupt=False):
        top = f"vpngo-gui-{version}"
        files = {
            "run.py": "import sys\nfrom vpngo_gui.__main__ import main\nsys.exit(main())\n",
            "vpngo_gui/__init__.py": "",
            "vpngo_gui/__main__.py": f"def main():\n    print('vpngo-gui {reported or version}')\n    return 0\n",
            "requirements.txt": "",
        }
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for name, text in files.items():
                data = text.encode()
                info = tarfile.TarInfo(f"{top}/{name}")
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        data = buffer.getvalue()
        (self.mirror / f"{top}.tar.gz").write_bytes(data + (b"x" if corrupt else b""))
        (self.mirror / "SHA256SUMS").write_text(f"{hashlib.sha256(data).hexdigest()}  {top}.tar.gz\n")

    def install(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return gui_install.install()

    def test_installs_verified_release_with_launcher_and_cli_record(self):
        self.publish()
        self.assertEqual(self.install(), 0)
        prefix = self.home / ".local/share/vpngo-gui"
        self.assertTrue((prefix / "app/vpngo_gui/__main__.py").is_file())
        self.assertEqual(json.loads((prefix / "cli.json").read_text())["command"], gui_install.cli_command())
        if os.name != "nt":
            launcher = self.home / ".local/bin/vpngo-gui"
            output = subprocess.run([str(launcher), "--version"], capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(output.stdout.strip(), "vpngo-gui 1.2.3")

    def test_checksum_mismatch_installs_nothing(self):
        self.publish(corrupt=True)
        with self.assertRaisesRegex(AppError, "Checksum mismatch"):
            self.install()
        self.assertFalse((self.home / ".local/share/vpngo-gui/app").exists())

    def test_failed_upgrade_restores_previous_version(self):
        self.publish("1.2.3")
        self.install()
        self.publish("1.2.4", reported="broken")
        with patch.dict(os.environ, {"VPNGO_GUI_VERSION": "1.2.4"}), self.assertRaisesRegex(AppError, "did not start"):
            self.install()
        main = self.home / ".local/share/vpngo-gui/app/vpngo_gui/__main__.py"
        self.assertIn("1.2.3", main.read_text())
        self.assertFalse((self.home / ".local/share/vpngo-gui/app.old").exists())


if __name__ == "__main__":
    unittest.main()
