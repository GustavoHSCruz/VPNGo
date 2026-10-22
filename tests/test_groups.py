"""Groups, removing apps and profiles, and the per-route clock, without a real VPN."""

import atexit
import contextlib
import io
import json
import os
import shutil
import sys
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

import apps
import assignments
import commands
import groups
import profiles
import route_clock
from apps import AppError


def quiet():
    stack = contextlib.ExitStack()
    stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
    stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
    return stack


class RouteClockTest(unittest.TestCase):
    def test_time_and_traffic_per_route(self):
        record = route_clock.begin("vpn", since=100)
        record = route_clock.switch(record, "direct", {"rx_bytes": 5000, "tx_bytes": 700}, now=160)
        self.assertIs(route_clock.switch(record, "direct", now=170), record)
        view = route_clock.view(record, {"rx_bytes": 5600, "tx_bytes": 800}, now=190)
        self.assertEqual(view, {"route_since": 160, "vpn_seconds": 60, "direct_seconds": 30,
                                "route_rx_bytes": 600, "route_tx_bytes": 100})
        back = route_clock.switch(record, "vpn", now=200)
        self.assertEqual(route_clock.view(back, now=210)["direct_seconds"], 40)
        self.assertEqual(route_clock.view(back, now=210)["vpn_seconds"], 70)

    def test_recreated_counters_count_from_zero(self):
        record = route_clock.begin("vpn", since=0, counters={"rx_bytes": 900, "tx_bytes": 9})
        self.assertEqual(route_clock.view(record, {"rx_bytes": 40, "tx_bytes": 2}, now=1)["route_rx_bytes"], 40)


class GroupCommandTest(unittest.TestCase):
    def setUp(self):
        self.config = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.config, ignore_errors=True)
        for module, name in ((apps, "apps.json"), (assignments, "assignments.json"), (groups, "groups.json"),
                             (profiles, "profiles.json")):
            patcher = patch.object(module, "REGISTRY", self.config / name)
            patcher.start()
            self.addCleanup(patcher.stop)
        for patcher in (patch.object(commands.sys, "platform", "linux"),
                        patch("apps.find", return_value={}), patch("assignments.find", return_value={})):
            patcher.start()
            self.addCleanup(patcher.stop)
        conf = self.config / "us.conf"
        conf.write_text("x")
        profiles.save({"us": str(conf), "br": str(conf)})

    def routes(self, **states):
        return patch.object(commands, "running_routes", return_value={
            name: {"state": state, "active_profile": "us"} for name, state in states.items()})

    def test_an_app_belongs_to_one_group(self):
        with quiet():
            commands.main(["group", "add", "Games", "steam", "vesktop"])
            commands.main(["group", "add", "chat", "vesktop"])
        self.assertEqual(groups.load(), {"games": {"apps": ["steam"]}, "chat": {"apps": ["vesktop"]}})
        with quiet():
            commands.main(["group", "remove", "chat", "vesktop"])
        self.assertEqual(groups.load(), {"games": {"apps": ["steam"]}})
        with quiet():
            commands.main(["group", "add", "chat", "vesktop"])
            commands.main(["group", "rename", "games", "Play"])
        self.assertEqual(list(groups.load()), ["play", "chat"])
        with self.assertRaisesRegex(AppError, "already exists"):
            commands.main(["group", "rename", "play", "chat"])

    def test_group_on_starts_stopped_apps_and_turns_direct_ones_on(self):
        groups.save({"games": {"apps": ["steam", "vesktop", "spotify"]}})
        calls = []
        real_main = commands.main

        def main(args=None):
            if args and args[0] == "group":
                return real_main(args)
            calls.append(args)
            return 0
        with self.routes(vesktop="direct", spotify="vpn"), patch.object(commands, "main", side_effect=main), quiet():
            self.assertEqual(real_main(["group", "on", "games"]), 0)
        self.assertEqual(calls, [["start", "steam"], ["on", "vesktop"]])

    def test_group_switch_switches_live_and_assigns_the_rest(self):
        groups.save({"games": {"apps": ["steam", "vesktop"]}})
        calls = []
        with (self.routes(vesktop="vpn"), patch.object(commands, "resolve"),
              patch.object(commands, "main", side_effect=lambda args: calls.append(args) or 0), quiet()):
            self.assertEqual(commands.group_command(["switch", "games", "br"]), 0)
        self.assertEqual(calls, [["assign", "steam", "br"], ["switch", "vesktop", "br"]])

    def test_a_failure_continues_and_reports(self):
        groups.save({"games": {"apps": ["steam", "vesktop"]}})

        def main(args):
            if args[1] == "steam":
                raise AppError("boom")
            return 0
        with self.routes(), patch.object(commands, "main", side_effect=main) as called, quiet():
            self.assertEqual(commands.group_command(["stop", "games"]), 0)  # Both already stopped.
            self.assertEqual(called.call_count, 0)
        with self.routes(steam="vpn", vesktop="vpn"), patch.object(commands, "main", side_effect=main) as called, \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(commands.group_command(["off", "games"]), 1)
        self.assertEqual(called.call_count, 2)
        self.assertIn("steam", errors.getvalue())

    def test_remove_app_forgets_everything_but_refuses_while_running(self):
        apps.save({"files": {"steam": "/x/steam"}, "directories": []})
        assignments.save({"steam": {"profile": "us", "killswitch": True, "dns": False}})
        groups.save({"games": {"apps": ["steam"]}})
        with self.routes(steam="vpn"), self.assertRaisesRegex(AppError, "Stop it first"):
            commands.main(["app", "remove", "steam"])
        with self.routes(), quiet():
            self.assertEqual(commands.main(["app", "remove", "Steam"]), 0)
        self.assertEqual((apps.load()["files"], assignments.load(), groups.load()), ({}, {}, {}))
        with self.routes(), self.assertRaisesRegex(AppError, "not registered"):
            commands.main(["app", "remove", "steam"])

    def test_remove_profile_refuses_while_used(self):
        assignments.save({"steam": {"profile": "us", "killswitch": True, "dns": False}})
        with self.routes(), self.assertRaisesRegex(AppError, "used by steam"):
            commands.main(["profile", "remove", "us"])
        with self.routes(), quiet():
            self.assertEqual(commands.main(["profile", "remove", "br"]), 0)
        self.assertEqual(set(profiles.load()), {"us"})


if __name__ == "__main__":
    unittest.main()
