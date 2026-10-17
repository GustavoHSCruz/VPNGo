"""App allowlists, route-free config, service rollback and local SOCKS TCP/UDP."""

import base64
import contextlib
import io
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))
import control
import generate_mihomo
import managed
import windows_backend as backend
from apps import AppError

POWERSHELL = shutil.which("powershell.exe")
MIHOMO = os.environ.get("VPNGO_MIHOMO") or shutil.which("mihomo.exe")
PROFILE = dict(ipv4="10.0.0.2", ipv6=None, private_key=base64.b64encode(b"a" * 32).decode(),
               host="127.0.0.1", port=51820, public_key=base64.b64encode(b"b" * 32).decode(),
               allowed=["0.0.0.0/0"], psk="", keepalive=0, mtu=1420)


def app(process="Discord.exe", enabled=True):
    return dict(process=process, profile="default", enabled=enabled, helpers=[])


class WindowsConfigTest(unittest.TestCase):
    def test_config_has_no_global_capture_and_listeners_match_process_rules(self):
        data = {"discord": app(), "browser": app("browser.exe", False)}
        config = generate_mihomo.build_config(PROFILE, "test-secret", 9097, data, platform="win32")
        desired = backend.build_proxifyre_config(data, "test-secret", 9097)
        self.assertIn("tun:\n  enable: false\n  auto-route: false\n  strict-route: false", config)
        self.assertNotIn("auto-route: true", config)
        self.assertNotIn("dns-hijack", config)
        self.assertNotIn("PROCESS-NAME", config)
        self.assertNotIn("PROCESS-PATH", config)
        self.assertIn("MATCH,REJECT", config)
        self.assertEqual(desired["excludes"], ["mihomo.exe", "ProxiFyre.exe"])
        self.assertTrue(desired["bypassLan"])
        for name, rule in zip(sorted(data), desired["proxies"]):
            self.assertEqual(rule["appNames"], [data[name]["process"]])
            self.assertEqual(rule["supportedProtocols"], ["TCP", "UDP"])
            self.assertEqual(rule["supportedAddressFamilies"], ["IPv4", "IPv6"])
            port = rule["socks5ProxyEndpoint"].split(":")[1]
            self.assertIn(f"listen: 127.0.0.1\n    port: {port}\n    udp: true", config)
            self.assertIn(f"proxy: {generate_mihomo.group_name(name)}", config)
            self.assertIn(f'username: "{rule["username"]}"', config)
            self.assertIn(f'password: "{rule["password"]}"', config)

    def test_existing_port_stays_bound_to_its_app_when_a_new_name_collides(self):
        new_port = backend.listener_ports({"new": app()}, 9097)["new"]
        data = {"old": {**app("old.exe"), "windows_port": new_port}, "new": app()}
        self.assertTrue(backend.assign_ports(data, 9097))
        self.assertEqual(data["old"]["windows_port"], new_port)
        self.assertNotEqual(data["new"]["windows_port"], new_port)
        self.assertFalse(backend.assign_ports(data, 9097))

    def test_global_system_and_ambiguous_process_matches_are_rejected(self):
        for process in ("", "*", "svchost.exe", "mihomo.exe", "C:\\Discord.exe", "discord"):
            with self.subTest(process=process), self.assertRaises(AppError):
                backend.build_proxifyre_config({"app": app(process)}, "test", 9097)
        with self.assertRaises(AppError):
            backend.build_proxifyre_config({"a": app(), "b": app("DISCORD.EXE")}, "test", 9097)
        with self.assertRaises(AppError):
            backend.build_proxifyre_config({"a": {**app(), "helpers": ["C:\\Windows\\explorer.exe"]}}, "test", 9097)

    def test_mac_config_retains_its_existing_tun_backend(self):
        config = generate_mihomo.build_config(PROFILE, "test", 9097, platform="darwin")
        self.assertIn("auto-route: true", config)
        self.assertIn("dns-hijack", config)

    def test_old_global_runtime_is_rejected_before_config_reload(self):
        calls = []
        def request(_port, _secret, method, path, payload=None):
            calls.append((method, path))
            return {"tun": {"enable": True}}
        with (patch.object(managed, "render", return_value={"port": 9097, "secret": "test"}),
              patch.object(managed, "load_managed", return_value={}),
              patch.object(managed.sys, "platform", "win32"), patch.object(control, "request", side_effect=request)):
            with self.assertRaisesRegex(AppError, "old global"):
                managed.reload_runtime()
        self.assertFalse(any(method == "PUT" for method, _path in calls))

    def test_connection_cleanup_uses_listener_identity(self):
        group = generate_mihomo.group_name("discord")
        connections = {"connections": [
            {"id": "11111111-aaaa", "metadata": {"inboundName": group + "-in"}},
            {"id": "22222222-bbbb", "metadata": {"inboundName": "other-in"}},
        ]}
        with patch.object(control, "request", return_value=connections):
            self.assertEqual(list(control.app_connections(9097, "test", "Discord.exe", group=group)), ["11111111-aaaa"])


@unittest.skipUnless(sys.platform == "win32" and POWERSHELL, "Windows PowerShell required")
class WindowsServiceTest(unittest.TestCase):
    def test_existing_unrelated_config_is_refused_and_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            installation = folder / "ProgramFiles/ProxiFyre"
            installation.mkdir(parents=True)
            shutil.copyfile(sys.executable, installation / "ProxiFyre.exe")
            config = installation / "app-config.json"
            original = '{"proxies":[{"appNames":["existing.exe"]}]}'
            config.write_text(original, encoding="utf-8")
            harness = folder / "harness.ps1"
            harness.write_text(r'''
$ErrorActionPreference = 'Stop'
$Tokens = $null; $Errors = $null
$Ast = [Management.Automation.Language.Parser]::ParseFile($env:VPNGO_HELPER, [ref]$Tokens, [ref]$Errors)
$Functions = $Ast.FindAll({ param($Node) $Node -is [Management.Automation.Language.FunctionDefinitionAst] }, $false)
. ([scriptblock]::Create(($Functions.Extent.Text -join "`n")))
$ServiceName = 'ProxiFyreService'; $OwnerSid = 'fixture'
$env:ProgramFiles = Join-Path $env:VPNGO_FIXTURE 'ProgramFiles'
function Get-ItemProperty {
    return [pscustomobject]@{ ImagePath = ('"' + (Join-Path $env:ProgramFiles 'ProxiFyre\ProxiFyre.exe') + '"') }
}
try { Get-Installation | Out-Null; throw 'Unexpectedly accepted unrelated config' }
catch { [Console]::WriteLine($_.Exception.Message) }
''', encoding="utf-8")
            result = subprocess.run(
                [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
                env={**os.environ, "VPNGO_HELPER": str(ROOT / "windows/proxy-service.ps1"), "VPNGO_FIXTURE": directory},
                capture_output=True, text=True, timeout=15, check=False,
            )
            self.assertIn("will not overwrite", result.stdout, result.stdout + result.stderr)
            self.assertEqual(config.read_text(), original)

    def test_elevated_validator_rejects_catch_all_and_nonlocal_proxy(self):
        valid = backend.build_proxifyre_config({"discord": app()}, "test", 9097)
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "desired.json"
            for change in (None, "catch-all", "remote", "system"):
                with self.subTest(change=change):
                    desired = json.loads(json.dumps(valid))
                    if change == "catch-all": desired["proxies"][0]["appNames"] = [""]
                    if change == "remote": desired["proxies"][0]["socks5ProxyEndpoint"] = "example.org:20000"
                    if change == "system": desired["proxies"][0]["appNames"] = ["svchost.exe"]
                    config.write_text(json.dumps(desired), encoding="utf-8")
                    result = subprocess.run(
                        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                         str(ROOT / "windows/proxy-service.ps1"), "-Mode", "Validate", "-ConfigPath", str(config)],
                        capture_output=True, text=True, timeout=15, check=False,
                    )
                    self.assertEqual(result.returncode == 0, change is None, result.stdout + result.stderr)

    def test_service_apply_is_idempotent_and_failed_restart_restores_config(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            desired = backend.build_proxifyre_config({"discord": app()}, "test", 9097)
            (folder / "desired.json").write_text(json.dumps(desired), encoding="utf-8")
            harness = folder / "harness.ps1"
            harness.write_text(r'''
$ErrorActionPreference = 'Stop'
$Tokens = $null; $Errors = $null
$Ast = [Management.Automation.Language.Parser]::ParseFile($env:VPNGO_HELPER, [ref]$Tokens, [ref]$Errors)
$Functions = $Ast.FindAll({ param($Node) $Node -is [Management.Automation.Language.FunctionDefinitionAst] }, $false)
. ([scriptblock]::Create(($Functions.Extent.Text -join "`n")))
$Mode = 'Apply'; $ConfigPath = Join-Path $env:VPNGO_FIXTURE 'desired.json'; $OwnerSid = 'fixture'
$script:Service = [pscustomobject]@{ Status = 'Running' }
$script:Service | Add-Member ScriptMethod WaitForStatus { param($State, $Timeout) }
$script:Service | Add-Member ScriptMethod Refresh {}
$script:Starts = 0; $script:Stops = 0
function Get-Installation {
    $OwnerFile = Join-Path $env:VPNGO_FIXTURE 'owner.json'
    $Owner = if (Test-Path -LiteralPath $OwnerFile) { Get-Content -LiteralPath $OwnerFile -Raw | ConvertFrom-Json } else { $null }
    return @{ ConfigPath = (Join-Path $env:VPNGO_FIXTURE 'app-config.json');
              OwnerPath = $OwnerFile; OwnerDigest = $Owner.digest; Service = $script:Service }
}
function Stop-Service { param($Name, $ErrorAction) $script:Stops++; $script:Service.Status = 'Stopped' }
function Start-Service {
    param($Name, $ErrorAction)
    $script:Starts++
    if ($env:VPNGO_FAIL -eq '1' -and $script:Starts -eq 1) { throw 'simulated restart failure' }
    $script:Service.Status = 'Running'
}
function Start-Sleep {}
try {
    Invoke-Operation | Out-Null
    Invoke-Operation | Out-Null
} catch { $Failure = $_.Exception.Message }
@{ starts = $script:Starts; stops = $script:Stops; error = $Failure; state = $script:Service.Status } | ConvertTo-Json -Compress
''', encoding="utf-8")
            for fails in (False, True):
                with self.subTest(fails=fails):
                    old = '{"previous":true}'
                    (folder / "app-config.json").write_text(old, encoding="utf-8")
                    result = subprocess.run(
                        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
                        env={**os.environ, "VPNGO_HELPER": str(ROOT / "windows/proxy-service.ps1"),
                             "VPNGO_FIXTURE": directory, "VPNGO_FAIL": str(int(fails))},
                        capture_output=True, text=True, timeout=15, check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    status = json.loads(result.stdout)
                    self.assertEqual(status["state"], "Running", status)
                    if fails:
                        self.assertEqual(status["error"], "simulated restart failure")
                        self.assertEqual((folder / "app-config.json").read_text(), old)
                        self.assertEqual(status["starts"], 2)
                    else:
                        self.assertIsNone(status["error"])
                        self.assertEqual(status["starts"], 1)
                        self.assertEqual(json.loads((folder / "app-config.json").read_text()), desired)


def recv_exact(connection, count):
    data = b""
    while len(data) < count:
        chunk = connection.recv(count - len(data))
        if not chunk:
            raise AssertionError("Unexpected SOCKS EOF")
        data += chunk
    return data


def socks_auth(port, username, password):
    connection = socket.create_connection(("127.0.0.1", port), timeout=3)
    connection.sendall(b"\x05\x01\x02")
    if recv_exact(connection, 2) != b"\x05\x02": raise AssertionError("SOCKS authentication was not required")
    username, password = username.encode(), password.encode()
    connection.sendall(b"\x01" + bytes([len(username)]) + username + bytes([len(password)]) + password)
    if recv_exact(connection, 2) != b"\x01\x00": raise AssertionError("SOCKS authentication failed")
    return connection


@unittest.skipUnless(sys.platform == "win32" and POWERSHELL and MIHOMO, "Windows and Mihomo required")
class LocalMihomoTest(unittest.TestCase):
    def network_snapshot(self):
        script = r'''@{ routes = @(Get-NetRoute -DestinationPrefix '0.0.0.0/0','::/0' -ErrorAction SilentlyContinue | Select-Object InterfaceAlias,NextHop,RouteMetric | Sort-Object InterfaceAlias,NextHop); adapters = @(Get-NetAdapter | Select-Object Name,InterfaceDescription | Sort-Object Name); proxy = (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' | Select-Object ProxyEnable,ProxyServer,AutoConfigURL) } | ConvertTo-Json -Depth 5 -Compress'''
        result = subprocess.run([POWERSHELL, "-NoProfile", "-Command", script], capture_output=True, text=True, check=True, timeout=20)
        return json.loads(result.stdout)

    def test_authenticated_tcp_udp_and_unchanged_host_network(self):
        before = self.network_snapshot()
        with tempfile.TemporaryDirectory(prefix="vpngo-socks-test-") as directory:
            folder = Path(directory)
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                controller_port = reservation.getsockname()[1]
            name = "vpngo-local-probe"
            data = {name: app("vpngo-local-probe.exe", enabled=False)}
            config = generate_mihomo.build_config(PROFILE, "test-secret", controller_port, data, platform="win32")
            config_path = folder / "config.yaml"
            config_path.write_text(config, encoding="utf-8")
            checked = subprocess.run([MIHOMO, "-t", "-d", directory, "-f", str(config_path)], capture_output=True, text=True, timeout=15)
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            with (folder / "engine.log").open("w", encoding="utf-8") as log:
                engine = subprocess.Popen([MIHOMO, "-d", directory, "-f", str(config_path)], stdout=log, stderr=log)
                try:
                    deadline = time.monotonic() + 10
                    while True:
                        try:
                            settings = control.request(controller_port, "test-secret", "GET", "/configs")
                            break
                        except OSError:
                            if time.monotonic() >= deadline or engine.poll() is not None:
                                self.fail("Local Mihomo did not start: " + (folder / "engine.log").read_text())
                            time.sleep(0.1)
                    self.assertFalse(settings["tun"]["enable"])
                    self.assertEqual(self.network_snapshot(), before)
                    rule = backend.build_proxifyre_config(data, "test-secret", controller_port)["proxies"][0]
                    port = int(rule["socks5ProxyEndpoint"].split(":")[1])
                    with socket.socket() as tcp_server:
                        tcp_server.bind(("127.0.0.1", 0)); tcp_server.listen(); tcp_server.settimeout(4)
                        def echo_tcp():
                            with tcp_server.accept()[0] as client:
                                client.sendall(client.recv(100))
                        worker = threading.Thread(target=echo_tcp, daemon=True); worker.start()
                        with socks_auth(port, rule["username"], rule["password"]) as connection:
                            connection.sendall(b"\x05\x01\x00\x01" + socket.inet_aton("127.0.0.1") + struct.pack("!H", tcp_server.getsockname()[1]))
                            self.assertEqual(recv_exact(connection, 10)[:2], b"\x05\x00")
                            connection.sendall(b"vpngo-tcp")
                            self.assertEqual(recv_exact(connection, 9), b"vpngo-tcp")
                        worker.join(timeout=5)
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_server:
                        udp_server.bind(("127.0.0.1", 0)); udp_server.settimeout(4)
                        def echo_udp():
                            message, address = udp_server.recvfrom(1024)
                            udp_server.sendto(message, address)
                        worker = threading.Thread(target=echo_udp, daemon=True); worker.start()
                        with socks_auth(port, rule["username"], rule["password"]) as connection:
                            connection.sendall(b"\x05\x03\x00\x01\x00\x00\x00\x00\x00\x00")
                            reply = recv_exact(connection, 10)
                            self.assertEqual(reply[:2], b"\x05\x00")
                            relay = (socket.inet_ntoa(reply[4:8]), struct.unpack("!H", reply[8:10])[0])
                            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_client:
                                udp_client.settimeout(4)
                                packet = b"\x00\x00\x00\x01" + socket.inet_aton("127.0.0.1") + struct.pack("!H", udp_server.getsockname()[1]) + b"vpngo-udp"
                                udp_client.sendto(packet, relay)
                                self.assertEqual(udp_client.recvfrom(1024)[0][10:], b"vpngo-udp")
                        worker.join(timeout=5)
                finally:
                    engine.terminate()
                    try: engine.wait(timeout=5)
                    except subprocess.TimeoutExpired: engine.kill(); engine.wait(timeout=5)
        self.assertEqual(self.network_snapshot(), before)


if __name__ == "__main__":
    unittest.main()
