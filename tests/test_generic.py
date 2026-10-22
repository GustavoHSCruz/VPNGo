"""No VPN connection is needed for these application discovery and route tests."""

import atexit
import os
import base64
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import shutil
import stat
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))
# Keep module imports away from the developer's real settings.
TEST_HOME = Path(tempfile.mkdtemp(prefix="vpngo-test-home-"))
atexit.register(shutil.rmtree, TEST_HOME, ignore_errors=True)
os.environ.update(HOME=str(TEST_HOME), XDG_CONFIG_HOME=str(TEST_HOME / ".config"),
                  APPDATA=str(TEST_HOME / "AppData"), LOCALAPPDATA=str(TEST_HOME / "LocalAppData"))

import apps
import control
import generate_mihomo
import managed
import profiles
import vault
from generate_mihomo import build_config, group_name, profile_proxy


class ApplicationDiscoveryTest(unittest.TestCase):
    def test_temporary_executable_prefers_current_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "dota2"
            executable.write_text("#!/bin/sh\nexit 0\n")
            executable.chmod(0o700)
            with patch.object(apps.Path, "cwd", return_value=Path(temporary)):
                self.assertEqual(apps.find_temporary("dota2")["launch"], str(executable))
                self.assertEqual(apps.find_temporary(str(executable))["launch"], str(executable))

    def test_configured_directory_finds_executable(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            registry = directory / "apps.json"
            executable = directory / "Example-App"
            executable.write_text("#!/bin/sh\nexit 0\n")
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
            with patch.object(apps, "REGISTRY", registry), patch.dict(os.environ, {"PATH": ""}):
                apps.add_path(str(directory))
                found = apps.find("example-app")
            self.assertEqual(found["executable"], str(executable))
            self.assertEqual(found["process"], "Example-App")

    def test_missing_application_explains_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(apps, "REGISTRY", Path(temporary) / "apps.json"), patch.dict(os.environ, {"PATH": ""}):
                with self.assertRaisesRegex(apps.AppError, r"vpngo config <path>"):
                    apps.find("missing-vpngo-app")


class MihomoControllerTest(unittest.TestCase):
    def test_controller_is_created_once_and_kept_private(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / "mihomo"
            with patch.object(generate_mihomo, "STATE", state):
                first = generate_mihomo.controller()
                self.assertEqual(generate_mihomo.controller(), first)
                self.assertEqual(first["port"], generate_mihomo.DEFAULT_PORT)
                self.assertGreaterEqual(len(first["secret"]), 32)
                moved = generate_mihomo.controller(9100)
            self.assertEqual(moved, {"port": 9100, "secret": first["secret"]})
            self.assertEqual(json.loads((state / "managed.json").read_text()), {})
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(state.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE((state / "controller.json").stat().st_mode), 0o600)

    def test_mihomo_folder_is_outside_the_program(self):
        self.assertNotIn(str(Path(__file__).resolve().parents[1]), str(apps.mihomo_dir()))


class MihomoRouteTest(unittest.TestCase):
    def setUp(self):
        # These tests exercise selector transactions without an installed driver.
        filters = patch("windows_backend.routing_active", return_value=True)
        filters.start()
        self.addCleanup(filters.stop)

    def test_empty_connection_snapshots_have_no_connections(self):
        for connections in (None, []):
            with self.subTest(connections=connections):
                with patch.object(control, "request", return_value={"connections": connections}):
                    self.assertEqual(list(control.app_connections(9097, "secret", "alpha")), [])

    def test_malformed_connection_snapshots_are_rejected(self):
        for response in (None, {}, {"connections": {}}, {"connections": 0}):
            with self.subTest(response=response):
                with patch.object(control, "request", return_value=response):
                    with self.assertRaises(ValueError):
                        list(control.app_connections(9097, "secret", "alpha"))

    def test_temporary_route_is_removed_after_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            app = {"executable": "/games/dota2", "launch": "/games/dota2", "process": "dota2"}
            with (patch.object(managed, "MANAGED", Path(temporary) / "managed.json"),
                  patch.object(managed, "find_temporary", return_value=app),
                  patch.object(managed, "resolve"),
                  patch.object(managed, "reload_runtime") as reload_runtime):
                session = managed.prepare("./dota2", "east", temporary=True)["session"]
                self.assertTrue(managed.load_managed()["dota2"]["temporary"])
                managed.cleanup_temporary("dota2", session)
                self.assertEqual(managed.load_managed(), {})
                self.assertEqual(reload_runtime.call_count, 2)

    def test_orphaned_temporary_worker_blocks_route_until_stop(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "managed.json"
            data = {"dota2": {"temporary": True, "session": "current", "process": "dota2",
                                "created_at": 1, "worker_pid": 314, "worker_started": "old",
                                "enabled": True, "blocked": False}}
            with (patch.object(managed, "MANAGED", path),
                  patch.object(managed, "process_start", return_value="new"),
                  patch.object(managed, "reload_runtime", return_value=False) as reload_runtime,
                  contextlib.redirect_stderr(io.StringIO())):
                managed.save_managed(data)
                self.assertEqual(managed.reconcile_temporary(), ["dota2"])
                self.assertEqual(managed.reconcile_temporary(), [])
                orphan = managed.load_managed()["dota2"]
                self.assertTrue(orphan["blocked"])
                self.assertFalse(orphan["enabled"])
                self.assertTrue(orphan["orphaned"])
                with self.assertRaises(apps.AppError):
                    managed.bind_temporary("dota2", "current", 314)
                with self.assertRaises(apps.AppError):
                    managed.cleanup_temporary("dota2", "stale")
                managed.cleanup_temporary("dota2", "current")
                self.assertEqual(managed.load_managed(), {})
                self.assertEqual(reload_runtime.call_count, 2)

    def test_new_temporary_session_gets_startup_grace(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "managed.json"
            with (patch.object(managed, "MANAGED", path),
                  patch.object(managed.time, "time", return_value=100),
                  patch.object(managed, "reload_runtime") as reload_runtime):
                managed.save_managed({"dota2": {"temporary": True, "session": "current",
                                                "process": "dota2", "created_at": 90,
                                                "enabled": True}})
                self.assertEqual(managed.reconcile_temporary(), [])
                reload_runtime.assert_not_called()

    def test_legacy_temporary_session_can_be_stopped_after_reconciliation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "managed.json"
            with (patch.object(managed, "MANAGED", path),
                  patch.object(managed, "reload_runtime", return_value=False),
                  contextlib.redirect_stderr(io.StringIO())):
                managed.save_managed({"dota2": {"temporary": True, "process": "dota2",
                                                "enabled": True, "blocked": False}})
                self.assertEqual(managed.reconcile_temporary(), ["dota2"])
                item = managed.load_managed()["dota2"]
                self.assertTrue(item["blocked"])
                managed.cleanup_temporary("dota2", item["session"])
                self.assertEqual(managed.load_managed(), {})

    def test_two_profiles_route_to_different_wireguard_peers(self):
        def wireguard(host, ip):
            return {
                "ipv4": ip, "ipv6": None, "private_key": "private",
                "host": host, "port": 51820, "public_key": "public",
                "allowed": ["0.0.0.0/0"], "psk": "", "keepalive": 0, "mtu": 1420,
            }

        config = build_config(
            {"east": wireguard("east.example", "10.0.0.2"),
             "west": wireguard("west.example", "10.0.1.2")},
            "secret", 9097,
            {"alpha": {"process": "alpha", "profile": "east", "enabled": True},
             "beta": {"process": "beta", "profile": "west", "enabled": True}},
            platform="darwin",
        )
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML is needed for structural YAML assertions")
        parsed = yaml.safe_load(config)
        proxies = {item["name"]: item for item in parsed["proxies"]}
        groups = {item["name"]: item for item in parsed["proxy-groups"]}
        self.assertEqual(proxies[profile_proxy("east")]["peers"][0]["server"], "east.example")
        self.assertEqual(proxies[profile_proxy("west")]["peers"][0]["server"], "west.example")
        self.assertEqual(groups[group_name("alpha")]["default-selected"], profile_proxy("east"))
        self.assertEqual(groups[group_name("beta")]["default-selected"], profile_proxy("west"))

    def test_two_applications_have_independent_selectors(self):
        profile = {
            "ipv4": "10.0.0.2", "ipv6": None, "private_key": "private",
            "host": "example.org", "port": 51820, "public_key": "public",
            "allowed": ["0.0.0.0/0"], "psk": "", "keepalive": 0, "mtu": 1420,
        }
        managed = {
            "alpha": {"process": "alpha", "enabled": True},
            "beta": {"process": "beta", "enabled": False},
        }
        config = build_config(profile, "secret", 9097, managed, platform="darwin")
        self.assertIn(f"PROCESS-NAME,alpha,{group_name('alpha')}", config)
        self.assertIn(f"PROCESS-NAME,beta,{group_name('beta')}", config)
        self.assertNotEqual(group_name("alpha"), group_name("beta"))
        self.assertIn("MATCH,DIRECT", config)
        try:
            import yaml
        except ImportError:
            return
        parsed = yaml.safe_load(config)
        groups = {item["name"]: item for item in parsed["proxy-groups"]}
        self.assertEqual(groups[group_name("alpha")]["default-selected"], "vpngo-wireguard")
        self.assertEqual(groups[group_name("beta")]["default-selected"], "DIRECT")

    def test_stopped_app_stays_blocked_after_config_reload(self):
        profile = {
            "ipv4": "10.0.0.2", "ipv6": None, "private_key": "private",
            "host": "example.org", "port": 51820, "public_key": "public",
            "allowed": ["0.0.0.0/0"], "psk": "", "keepalive": 0, "mtu": 1420,
        }
        config = build_config(profile, "secret", 9097, {
            "alpha": {"process": "alpha", "profile": "default", "enabled": False, "blocked": True},
            "beta": {"process": "beta", "profile": "default", "enabled": True},
        }, platform="darwin")
        self.assertIn(f"name: {group_name('alpha')}\n    type: select\n", config)
        self.assertIn("default-selected: REJECT", config)
        self.assertIn("default-selected: vpngo-wireguard", config)

    def test_closes_only_selected_process_connections(self):
        connections = {
            "connections": [
                {"id": "11111111-aaaa", "metadata": {"process": "alpha"}, "rule": "PROCESS-NAME", "rulePayload": "alpha"},
                {"id": "22222222-bbbb", "metadata": {"process": "beta"}, "rule": "PROCESS-NAME", "rulePayload": "beta"},
            ]
        }
        with patch.object(control, "request", return_value=connections):
            ids = list(control.app_connections(9097, "secret", "alpha"))
        self.assertEqual(ids, ["11111111-aaaa"])

    def test_switch_uses_the_apps_selected_profile(self):
        managed = {"alpha": {"process": "alpha", "profile": "east", "enabled": False},
                   "beta": {"process": "beta", "profile": "west", "enabled": True}}
        calls = []

        def request(_port, _secret, method, path, payload=None):
            calls.append((method, path, payload))
            return {"now": "DIRECT"} if method == "GET" else None

        with tempfile.TemporaryDirectory() as temporary:
            controller = Path(temporary) / "controller.json"
            controller.write_text(json.dumps({"port": 9097, "secret": "test"}))
            with (patch.object(control, "CONTROLLER", controller),
                  patch.object(control, "load_managed", return_value=managed),
                  patch.object(control, "save_managed"),
                  patch.object(control, "request", side_effect=request),
                  patch.object(control, "app_connections", return_value=iter(())),
                  patch.object(sys, "argv", ["control.py", "alpha", "on"]),
                  contextlib.redirect_stdout(io.StringIO())):
                self.assertEqual(control.main(), 0)
        self.assertIn(("PUT", "/proxies/" + group_name("alpha"),
                       {"name": profile_proxy("east")}), calls)
        self.assertFalse(any(group_name("beta") in path for _method, path, _payload in calls))

    def test_live_switch_changes_only_one_selector_and_its_connections(self):
        managed = {
            "alpha": {"process": "alpha", "profile": "east", "enabled": True, "helpers": ["/apps/alpha/helper"]},
            "beta": {"process": "beta", "profile": "east", "enabled": True},
        }
        calls = []
        saved = []

        def request(_port, _secret, method, path, payload=None):
            calls.append((method, path, payload))
            return {"now": profile_proxy("east")} if method == "GET" else None

        with tempfile.TemporaryDirectory() as temporary:
            controller = Path(temporary) / "controller.json"
            controller.write_text(json.dumps({"port": 9097, "secret": "test"}))
            with (patch.object(control, "CONTROLLER", controller),
                  patch.object(control, "load_managed", return_value=managed),
                  patch.object(control, "save_managed", side_effect=lambda item: saved.append(json.loads(json.dumps(item)))),
                  patch.object(control, "request", side_effect=request),
                  patch.object(control, "app_connections", return_value=iter(["11111111-aaaa"])) as connections,
                  patch.object(control, "resolve"),
                  patch.object(sys, "argv", ["control.py", "alpha", "switch", "west"]),
                  contextlib.redirect_stdout(io.StringIO())):
                self.assertEqual(control.main(), 0)
        self.assertIn(("PUT", "/proxies/" + group_name("alpha"),
                       {"name": profile_proxy("west")}), calls)
        self.assertIn(("DELETE", "/connections/11111111-aaaa", None), calls)
        self.assertFalse(any(group_name("beta") in path for _method, path, _payload in calls))
        self.assertEqual(connections.call_count, 2)
        connections.assert_called_with(9097, "test", "alpha", ["/apps/alpha/helper"], group_name("alpha"))
        self.assertEqual(saved[0]["alpha"]["profile"], "west")
        self.assertEqual(saved[0]["beta"]["profile"], "east")

    def test_failed_connection_close_restores_previous_selector(self):
        managed = {"alpha": {"process": "alpha", "profile": "east", "enabled": True}}
        calls = []

        def request(_port, _secret, method, path, payload=None):
            calls.append((method, path, payload))
            if method == "GET":
                return {"now": profile_proxy("east")}
            if method == "DELETE":
                raise urllib.error.HTTPError(path, 500, "failed", {}, None)
            return None

        with tempfile.TemporaryDirectory() as temporary:
            controller = Path(temporary) / "controller.json"
            controller.write_text(json.dumps({"port": 9097, "secret": "test"}))
            with (patch.object(control, "CONTROLLER", controller),
                  patch.object(control, "load_managed", return_value=managed),
                  patch.object(control, "save_managed") as save,
                  patch.object(control, "request", side_effect=request),
                  patch.object(control, "app_connections", return_value=iter(["11111111-aaaa"])),
                  patch.object(control, "resolve"),
                  patch.object(sys, "argv", ["control.py", "alpha", "switch", "west"])):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    control.main()
                caught.exception.close()
        self.assertEqual([payload for method, _path, payload in calls if method == "PUT"],
                         [{"name": profile_proxy("west")}, {"name": profile_proxy("east")}])
        save.assert_not_called()

    def test_stop_blocks_only_selected_application(self):
        managed = {
            "alpha": {"process": "alpha", "profile": "east", "enabled": True},
            "beta": {"process": "beta", "profile": "west", "enabled": True},
        }
        calls = []
        saved = []

        def request(_port, _secret, method, path, payload=None):
            calls.append((method, path, payload))
            if path == "/proxies/" + group_name("alpha") and method == "GET":
                return {"now": profile_proxy("east")}
            if path == "/connections" and method == "GET":
                return {"connections": [
                    {"id": "11111111-aaaa", "metadata": {"process": "alpha"}},
                    {"id": "22222222-bbbb", "metadata": {"process": "beta"}},
                ]}
            return None

        with tempfile.TemporaryDirectory() as temporary:
            controller = Path(temporary) / "controller.json"
            controller.write_text(json.dumps({"port": 9097, "secret": "test"}))
            with (patch.object(control, "CONTROLLER", controller),
                  patch.object(control, "load_managed", return_value=managed),
                  patch.object(control, "save_managed", side_effect=lambda item: saved.append(json.loads(json.dumps(item)))),
                  patch.object(control, "request", side_effect=request),
                  patch.object(sys, "argv", ["control.py", "alpha", "block"]),
                  contextlib.redirect_stdout(io.StringIO())):
                self.assertEqual(control.main(), 0)
        self.assertIn(("PUT", "/proxies/" + group_name("alpha"), {"name": "REJECT"}), calls)
        self.assertIn(("DELETE", "/connections/11111111-aaaa", None), calls)
        self.assertNotIn(("DELETE", "/connections/22222222-bbbb", None), calls)
        self.assertTrue(saved[0]["alpha"]["blocked"])
        self.assertFalse(saved[0]["beta"].get("blocked", False))


class LinuxCommandTest(unittest.TestCase):
    def test_temporary_run_stays_foreground_and_does_not_close_other_instances(self):
        loader = importlib.machinery.SourceFileLoader(
            "vpngo_linux_temp_test", str(ROOT / "linux/vpngo")
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        script = importlib.util.module_from_spec(spec)
        loader.exec_module(script)
        seen = []

        def popen(command, **_kwargs):
            config = Path(command[command.index("--custom") + 1])
            seen.append(config.read_text())  # vopono can read the plain copy while it starts.
            return SimpleNamespace(poll=lambda: 0, wait=lambda: 0)
        with (patch.object(script, "read_profile", return_value="[Interface]\n"),
              patch.object(script, "find_temporary", return_value={"launch": "/games/dota2"}),
              patch.object(script.shutil, "which", return_value="/usr/bin/vopono"),
              patch.object(script.subprocess, "call", return_value=0),
              patch.object(script.subprocess, "Popen", side_effect=popen) as run,
              patch.object(script, "namespace_up", return_value=False),
              patch.object(script, "close_app") as close):
            self.assertEqual(script.temporary_app("east", "dota2"), 0)
        close.assert_not_called()
        command = run.call_args.args[0]
        self.assertEqual(seen, ["[Interface]\n"])
        self.assertFalse(Path(command[command.index("--custom") + 1]).exists())  # Gone once it started.
        self.assertEqual(command[:2], ["vopono", "exec"])
        self.assertEqual(command[-1], "/games/dota2")

    def test_detached_temporary_run_waits_for_namespace(self):
        loader = importlib.machinery.SourceFileLoader(
            "vpngo_linux_detached_test", str(ROOT / "linux/vpngo")
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        script = importlib.util.module_from_spec(spec)
        loader.exec_module(script)
        status = {"namespaces": [{"id": "vg_temp_42_100", "applications": [{"argv": ["/usr/bin/kitty"]}]}]}
        with tempfile.TemporaryDirectory() as temporary:
            with (patch.object(script, "STATE_DIR", Path(temporary)),
                  patch.object(script, "read_profile", return_value="[Interface]\n"),
                  patch.object(script, "find_temporary", return_value={"launch": "/usr/bin/kitty"}),
                  patch.object(script.shutil, "which", return_value="/usr/bin/vopono"),
                  patch.object(script.subprocess, "call", return_value=0),
                  patch.object(script.subprocess, "Popen") as popen,
                  patch.object(script, "run", return_value=SimpleNamespace(returncode=0, stdout=json.dumps(status))),
                  patch.object(script.os, "getpid", return_value=42),
                  patch.object(script.time, "time", return_value=100),
                  contextlib.redirect_stdout(io.StringIO())):
                self.assertEqual(script.temporary_app("east", "kitty", detached=True), 0)
            command = popen.call_args.args[0]
            self.assertEqual(command[:2], ["nohup", "vopono"])
            self.assertEqual(command[-1], "/usr/bin/kitty")
            self.assertEqual((Path(temporary) / "temp.log").stat().st_mode & 0o777, 0o600)

    def test_stop_closes_only_target_namespace_and_cleans_session_files(self):
        loader = importlib.machinery.SourceFileLoader(
            "vpngo_linux_stop_test", str(ROOT / "linux/vpngo")
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        script = importlib.util.module_from_spec(spec)
        loader.exec_module(script)
        calls = []

        def run(*arguments, **_kwargs):
            calls.append(arguments)
            if arguments == ("vopono", "status", "--json"):
                return SimpleNamespace(stdout=json.dumps({"namespaces": [{"id": "vg_other"}]}))
            return SimpleNamespace(stdout="")

        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            for suffix in (".json", ".resolv.conf", ".launch"):
                (state / f"vg_app{suffix}").write_text("test")
            with (patch.object(script, "STATE_DIR", state),
                  patch.object(script, "app_namespace", return_value="vg_app"),
                  patch.object(script, "run", side_effect=run),
                  contextlib.redirect_stdout(io.StringIO())):
                self.assertEqual(script.stop_app("example-app", "/usr/bin/example-app"), 0)
            self.assertIn(("vopono", "stop", "namespace", "vg_app"), calls)
            self.assertFalse(any((state / f"vg_app{suffix}").exists()
                                 for suffix in (".json", ".resolv.conf", ".launch")))
            with (patch.object(script, "app_namespace", return_value=None),
                  patch.object(script, "run") as run_mock,
                  contextlib.redirect_stdout(io.StringIO())):
                self.assertEqual(script.stop_app("example-app"), 0)
            run_mock.assert_not_called()

    def test_namespace_lookup_finds_app_behind_dns_launcher(self):
        loader = importlib.machinery.SourceFileLoader(
            "vpngo_linux_namespace_test", str(ROOT / "linux/vpngo")
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        script = importlib.util.module_from_spec(spec)
        loader.exec_module(script)
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            (state / "vg_app.json").write_text(json.dumps({
                "app": "example-app", "executable": "/usr/bin/example-app", "profile": "east",
            }))
            status = {"namespaces": [{"id": "vg_app", "protocol": "wireguard",
                                      "applications": [{"argv": [str(state / "vg_app.launch")]}]}]}
            with (patch.object(script, "STATE_DIR", state),
                  patch.object(script, "run", return_value=SimpleNamespace(stdout=json.dumps(status)))):
                self.assertEqual(script.app_namespace("example-app", "/usr/bin/example-app"), "vg_app")

    def test_launch_policy_controls_kill_switch_and_dns_wrapper(self):
        loader = importlib.machinery.SourceFileLoader(
            "vpngo_linux_launch_test", str(ROOT / "linux/vpngo")
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        script = importlib.util.module_from_spec(spec)
        loader.exec_module(script)
        secure = script.launch_command("/tmp/east.conf", "vg_app", "/usr/bin/example-app",
                                       {"killswitch": True, "dns": True},
                                       "10.0.0.1", "/tmp/vg_app.launch")
        self.assertNotIn("--no-killswitch", secure)
        self.assertEqual(secure[-1], "/tmp/vg_app.launch")
        self.assertEqual(secure[secure.index("--dns") + 1], "10.0.0.1")
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(script, "STATE_DIR", Path(temporary)):
                launcher = script.dns_launcher("vg_app", Path("/tmp/nsswitch.conf"),
                                               "/usr/bin/example-app")
                self.assertEqual(launcher.stat().st_mode & 0o777, 0o700)
                self.assertIn("dns-launch", launcher.read_text())
                self.assertIn("/usr/bin/example-app", launcher.read_text())
        relaxed = script.launch_command("/tmp/east.conf", "vg_app", "/usr/bin/example-app",
                                        {"killswitch": False, "dns": False})
        self.assertIn("--no-killswitch", relaxed)
        self.assertNotIn("--dns", relaxed)

    def test_start_passes_named_profile(self):
        loader = importlib.machinery.SourceFileLoader(
            "vpngo_linux_test", str(ROOT / "linux/vpngo")
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        script = importlib.util.module_from_spec(spec)
        loader.exec_module(script)
        with (patch.object(script, "find", return_value={"process": "example-app"}),
              patch.object(script, "start_app", return_value=0) as start,
              patch.object(sys, "argv", ["vpngo", "example-app", "start", "east"])):
            self.assertEqual(script.main(), 0)
        start.assert_called_once_with("example-app", {"process": "example-app"}, "east")

    def test_live_switch_rolls_back_after_failed_handshake(self):
        loader = importlib.machinery.SourceFileLoader(
            "vpngo_linux_rollback_test", str(ROOT / "linux/vpngo")
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        script = importlib.util.module_from_spec(spec)
        loader.exec_module(script)
        profile = {
            "host": "203.0.113.2", "port": 51820, "private_key": "private",
            "public_key": "public", "allowed": ["0.0.0.0/0"], "psk": "",
            "keepalive": 0, "ipv4": "10.0.1.2", "ipv4_cidr": "10.0.1.2/32",
            "ipv6": None, "ipv6_cidr": None, "dns": ["10.0.1.1"], "mtu": 1380,
        }
        calls = []

        def netns(_namespace, *arguments, **_kwargs):
            calls.append(arguments)
            if arguments[:2] == ("wg", "showconf"):
                return SimpleNamespace(stdout="[Interface]\nPrivateKey = old\n")
            if arguments[:2] == ("wg", "show"):
                return SimpleNamespace(stdout="0xca6c\n")
            if arguments[:4] == ("ip", "-6", "route", "show"):
                return SimpleNamespace(stdout="")
            if arguments[:4] == ("ip", "-4", "route", "get"):
                return SimpleNamespace(stdout="1.1.1.1 dev wg0\n")
            return SimpleNamespace(stdout="")

        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            dns = state / "resolv.conf"
            dns.write_text("nameserver 10.0.0.1\n")
            session = {"profile": "east", "killswitch": True, "dns": True, "endpoint_exception": None}
            with (patch.object(script, "STATE_DIR", state),
                  patch.object(script, "load_session", return_value=session),
                  patch.object(script, "allowed", return_value=False),
                  patch.object(script, "rule_present", return_value=False),
                  patch.object(script, "parsed_profile", return_value=profile),
                  patch.object(script, "resolved_endpoint", return_value=("203.0.113.2", 51820)),
                  patch.object(script.shutil, "which", return_value="/usr/bin/ping"),
                  patch.object(script, "current_addresses", side_effect=[["10.0.0.2/32"], []]),
                  patch.object(script, "interface_mtu", return_value=1420),
                  patch.object(script, "dns_paths", return_value=(dns, state / "backup")),
                  patch.object(script, "write_dns", side_effect=lambda _path, content: dns.write_text(content)),
                  patch.object(script, "netns", side_effect=netns),
                  patch.object(script, "endpoint_exception") as exception,
                  patch.object(script, "await_handshake", return_value=False),
                  patch.object(script, "save_session") as save,
                  patch.object(script, "reconnect"),
                  patch.object(script, "ensure_vpn_routes")):
                with self.assertRaisesRegex(script.SwitchError, "previous profile was restored"):
                    script.switch_profile("vg_app", "example-app", "wg0", "veth0", "nft", "west")
            self.assertEqual(dns.read_text(), "nameserver 10.0.0.1\n")
            self.assertEqual(len([call for call in calls if call[:2] == ("wg", "setconf")]), 2)
            self.assertIn(("ip", "link", "set", "dev", "wg0", "mtu", "1380"), calls)
            self.assertIn(("ip", "link", "set", "dev", "wg0", "mtu", "1420"), calls)
            self.assertEqual(exception.call_count, 2)
            save.assert_not_called()

    def test_live_switch_commits_only_after_handshake(self):
        loader = importlib.machinery.SourceFileLoader(
            "vpngo_linux_commit_test", str(ROOT / "linux/vpngo")
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        script = importlib.util.module_from_spec(spec)
        loader.exec_module(script)
        profile = {
            "host": "203.0.113.2", "port": 51820, "private_key": "private",
            "public_key": "public", "allowed": ["0.0.0.0/0"], "psk": "",
            "keepalive": 0, "ipv4": "10.0.1.2", "ipv4_cidr": "10.0.1.2/30",
            "ipv6": None, "ipv6_cidr": None, "dns": ["10.0.1.1"], "mtu": 1380,
        }
        session = {"profile": "east", "killswitch": True, "dns": True,
                   "endpoint_exception": ["203.0.113.1", 51820]}

        def netns(_namespace, *arguments, **_kwargs):
            if arguments[:2] == ("wg", "showconf"):
                return SimpleNamespace(stdout="[Interface]\nPrivateKey = old\n")
            if arguments[:2] == ("wg", "show"):
                return SimpleNamespace(stdout="0xca6c\n")
            if arguments[:4] == ("ip", "-6", "route", "show"):
                return SimpleNamespace(stdout="")
            if arguments[:4] == ("ip", "-4", "route", "get"):
                return SimpleNamespace(stdout="1.1.1.1 dev wg0\n")
            return SimpleNamespace(stdout="")

        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            dns = state / "resolv.conf"
            dns.write_text("nameserver 10.0.0.1\n")
            with (patch.object(script, "STATE_DIR", state),
                  patch.object(script, "load_session", return_value=session),
                  patch.object(script, "allowed", return_value=False),
                  patch.object(script, "rule_present", return_value=False),
                  patch.object(script, "parsed_profile", return_value=profile),
                  patch.object(script, "resolved_endpoint", return_value=("203.0.113.2", 51820)),
                  patch.object(script.shutil, "which", return_value="/usr/bin/ping"),
                  patch.object(script, "current_addresses", side_effect=[["10.0.0.2/32"], []]),
                  patch.object(script, "interface_mtu", return_value=1420),
                  patch.object(script, "dns_paths", return_value=(dns, state / "backup")),
                  patch.object(script, "write_dns", side_effect=lambda _path, content: dns.write_text(content)),
                  patch.object(script, "netns", side_effect=netns),
                  patch.object(script, "endpoint_exception") as exception,
                  patch.object(script, "await_handshake", return_value=True),
                  patch.object(script, "save_session") as save,
                  patch.object(script, "reconnect") as reconnect,
                  patch.object(script, "ensure_vpn_routes"),
                  contextlib.redirect_stdout(io.StringIO())):
                script.switch_profile("vg_app", "example-app", "wg0", "veth0", "nft", "west")
            self.assertEqual(session["profile"], "west")
            self.assertEqual(dns.read_text(), "nameserver 10.0.1.1\n")
            self.assertEqual(exception.call_count, 2)
            save.assert_called_once()
            reconnect.assert_called_once_with("vg_app")


class SquirrelAppTest(unittest.TestCase):
    def test_windows_squirrel_apps_start_their_newest_version_through_update(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Discord"
            for version in ("1.0.9", "1.0.10"):
                (root / f"app-{version}").mkdir(parents=True)
                (root / f"app-{version}/Discord.exe").write_bytes(b"")
            (root / "Update.exe").write_bytes(b"")
            with patch.object(apps.os, "name", "nt"):
                found = apps.describe(root / "app-1.0.9/Discord.exe")
        # 1.0.10 is newer than 1.0.9, though it sorts first alphabetically.
        self.assertEqual(Path(found["executable"]).parent.name, "app-1.0.10")
        self.assertEqual(found["process"], "Discord.exe")
        self.assertEqual(found["start_with"][1:], ["--processStart", "Discord.exe"])
        self.assertEqual(Path(found["start_with"][0]).name, "Update.exe")

    def test_other_programs_start_directly(self):
        with tempfile.TemporaryDirectory() as temporary:
            program = Path(temporary) / "app-1.0/tool.exe"
            program.parent.mkdir()
            program.write_bytes(b"")
            with patch.object(apps.os, "name", "nt"):
                self.assertNotIn("start_with", apps.describe(program))  # No Update.exe beside it.


class ProfileRegistryTest(unittest.TestCase):
    def setUp(self):
        # A stand-in for the OS key store, so the tests run anywhere (CI has no user systemd-creds).
        for patcher in (patch.object(vault, "backend", return_value="dpapi"),
                        patch.object(vault, "dpapi", side_effect=lambda data, protect: bytes(
                            byte ^ 0x5A for byte in data))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_register_and_resolve_two_profiles(self):
        private = base64.b64encode(b"p" * 32).decode()
        public = base64.b64encode(b"q" * 32).decode()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry = root / "profiles.json"
            registry.write_text("{}")
            with patch.object(profiles, "REGISTRY", registry):
                for name, address in (("east", "10.0.0.2/32"), ("west", "10.0.1.2/32")):
                    path = root / f"{name}.conf"
                    path.write_text(
                        f"[Interface]\nPrivateKey = {private}\nAddress = {address}\n"
                        f"[Peer]\nPublicKey = {public}\nEndpoint = {name}.example:51820\n"
                        "AllowedIPs = 0.0.0.0/0\n"
                    )
                    profiles.register(path, name)
                    stored = profiles.resolve(name)
                    self.assertEqual(stored.parent, vault.STORE)
                    self.assertNotIn(private, stored.read_text(errors="replace"))
                    self.assertEqual(profiles.read(name), path.read_text())
                self.assertEqual(set(profiles.parsed_profiles()), {"east", "west"})
                profiles.unregister("east")
                self.assertFalse((vault.STORE / "east.dpapi").exists())

    def test_plain_profiles_are_encrypted_and_the_internal_copy_removed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inside = vault.STORE / "old-us.conf"
            inside.parent.mkdir(parents=True, exist_ok=True)
            inside.write_text("[Interface]\nPrivateKey = secret\n")
            outside = root / "br.conf"
            outside.write_text("[Interface]\nPrivateKey = other\n")
            registry = root / "profiles.json"
            registry.write_text(json.dumps({"us": str(inside), "br": str(outside)}))
            with patch.object(profiles, "REGISTRY", registry):
                self.assertEqual(profiles.migrate(), [outside])
                self.assertFalse(inside.exists())
                self.assertTrue(outside.exists())
                self.assertEqual(profiles.read("us"), "[Interface]\nPrivateKey = secret\n")
                self.assertEqual(profiles.migrate(), [])

    def test_plain_file_lives_only_inside_its_block(self):
        with vault.plain_file("us", "[Interface]\n") as path:
            self.assertEqual(path.read_text(), "[Interface]\n")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertFalse(path.parent.exists())


if __name__ == "__main__":
    unittest.main()
