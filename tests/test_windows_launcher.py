"""Ensure missing per-process dependencies fail before any network/app change."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell.exe")


@unittest.skipUnless(sys.platform == "win32" and POWERSHELL, "Windows PowerShell required")
class WindowsLauncherTest(unittest.TestCase):
    def test_proxy_starts_unelevated_and_filters_are_ready_before_app_restart(self):
        with tempfile.TemporaryDirectory(prefix="vpngo-launcher-") as directory:
            folder = Path(directory)
            (folder / "windows").mkdir()
            (folder / "shared").mkdir()
            launcher = folder / "windows/vpngo.ps1"
            shutil.copyfile(ROOT / "windows/vpngo.ps1", launcher)
            (folder / "windows/proxy-service.ps1").write_text(
                "param($Mode, $ConfigPath, $OwnerSid, $ResultPath)\n"
                "if ($Mode -eq 'Check') { Write-Output '{\"installed\":true,\"needsApply\":true}'; exit 0 }\n"
                "[IO.File]::WriteAllText($ResultPath, '{\"applied\":true}')\nexit 0\n",
                encoding="utf-8",
            )
            (folder / "shared/managed.py").write_text(
                "import json, os, pathlib, sys\n"
                "state = pathlib.Path(os.environ['LOCALAPPDATA']) / 'vpngo/mihomo'\n"
                "state.mkdir(parents=True, exist_ok=True)\n"
                "(state / 'config.yaml').write_text('tun:\\n  enable: false\\n')\n"
                "(state / 'proxifyre.json').write_text('{}')\n"
                "print(json.dumps(dict(process='vpngo-fixture.exe', launch='vpngo-fixture.exe')))\n",
                encoding="utf-8",
            )
            (folder / "shared/windows_backend.py").write_text(
                "import os, pathlib, sys\n"
                "if not pathlib.Path(os.environ['VPNGO_TEST_READY']).exists():\n"
                "    print('controller unavailable', file=sys.stderr)\n"
                "    sys.exit(1)\n", encoding="utf-8",
            )
            (folder / "shared/control.py").write_text(
                "import os, pathlib, sys\n"
                "with pathlib.Path(os.environ['VPNGO_TEST_EVENTS']).open('a') as output:\n"
                "    output.write(sys.argv[2] + '\\n')\n", encoding="utf-8",
            )
            harness = folder / "harness.ps1"
            harness.write_text(r'''
function Get-Process {}
function Stop-Process { Add-Content -LiteralPath $env:VPNGO_TEST_EVENTS -Value 'close-app' }
function Start-Sleep {}
function Start-Process {
    param($FilePath, $ArgumentList, $Verb, $WindowStyle, [switch]$PassThru, [switch]$Wait, $RedirectStandardOutput, $RedirectStandardError)
    if ($FilePath -eq $env:VPNGO_MIHOMO) {
        if ($Verb) { throw 'Mihomo must not request elevation' }
        if ($ArgumentList -contains '-t') { return [pscustomobject]@{ ExitCode = 0 } }
        Add-Content -LiteralPath $env:VPNGO_TEST_EVENTS -Value 'local-proxy'
        Set-Content -LiteralPath $env:VPNGO_TEST_READY -Value 'ready'
        $Engine = [pscustomobject]@{ Id = 123; HasExited = $false; StartTime = [datetime]::UtcNow }
        $Engine | Add-Member ScriptMethod Refresh {}
        return $Engine
    }
    if ([IO.Path]::GetFileName($FilePath) -eq 'powershell.exe') {
        if ($Verb -ne 'RunAs') { throw 'Process filters must request elevation' }
        Add-Content -LiteralPath $env:VPNGO_TEST_EVENTS -Value 'process-filters'
        if ($env:VPNGO_TEST_FILTER_FAIL -eq '1') { throw 'simulated filter failure' }
        $Command = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($ArgumentList[-1]))
        # Run only the prepared fixture helper; do not execute its trailing exit.
        & ([scriptblock]::Create(($Command -replace '; exit \$LASTEXITCODE$', '')))
        return [pscustomobject]@{ ExitCode = 0 }
    }
    Add-Content -LiteralPath $env:VPNGO_TEST_EVENTS -Value 'launch-app'
}
& $env:VPNGO_TEST_LAUNCHER fixture start east
exit $LASTEXITCODE
''', encoding="utf-8")
            for fails in (False, True):
                with self.subTest(filters_fail=fails):
                    events = folder / "events"
                    ready = folder / "ready"
                    events.unlink(missing_ok=True)
                    ready.unlink(missing_ok=True)
                    result = subprocess.run(
                        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
                        env={**os.environ, "LOCALAPPDATA": directory, "VPNGO_MIHOMO": "mihomo-fixture.exe",
                             "VPNGO_PYTHON": sys.executable, "VPNGO_TEST_READY": str(ready),
                             "VPNGO_TEST_EVENTS": str(events), "VPNGO_TEST_LAUNCHER": str(launcher),
                             "VPNGO_TEST_FILTER_FAIL": str(int(fails))},
                        capture_output=True, text=True, timeout=15, check=False,
                    )
                    recorded = events.read_text().splitlines()
                    self.assertEqual(recorded[:2], ["local-proxy", "process-filters"])
                    self.assertNotIn("controller unavailable", result.stderr)
                    if fails:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertNotIn("close-app", recorded)
                        self.assertNotIn("launch-app", recorded)
                    else:
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        self.assertLess(recorded.index("process-filters"), recorded.index("close-app"))
                        self.assertLess(recorded.index("close-app"), recorded.index("launch-app"))

    def test_start_paths_are_blocked_before_any_backend_or_process_change(self):
        with tempfile.TemporaryDirectory(prefix="vpngo-launcher-") as directory:
            project = Path(directory)
            (project / "windows").mkdir()
            launcher = project / "windows/vpngo.ps1"
            shutil.copyfile(ROOT / "windows/vpngo.ps1", launcher)
            shutil.copyfile(ROOT / "windows/proxy-service.ps1", project / "windows/proxy-service.ps1")
            harness = project / "harness.ps1"
            harness.write_text(
                "function Get-ItemProperty { return $null }\n"
                "function Start-Process { throw 'UNEXPECTED_MUTATION' }\n"
                "function Stop-Process { throw 'UNEXPECTED_MUTATION' }\n"
                "& $env:VPNGO_TEST_LAUNCHER @args\nexit $LASTEXITCODE\n",
                encoding="utf-8",
            )
            # No Python backend exists in this fixture: refusal must happen
            # before loading it, starting Mihomo or closing the application.
            for arguments in (
                ["start", "discord"], ["discord"], ["discord", "start"],
                ["on", "discord"], ["discord", "on"],
                ["temp", "east", "discord.exe"],
                ["temp", "east", "discord.exe", "detach"],
                ["temp-wait", "discord.exe", "discord.exe", "session"],
            ):
                with self.subTest(arguments=arguments):
                    result = subprocess.run(
                        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                         str(harness), *arguments],
                        env={**os.environ, "LOCALAPPDATA": directory, "VPNGO_TEST_LAUNCHER": str(launcher)},
                        capture_output=True, text=True, timeout=15, check=False,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    message = " ".join(result.stderr.split())
                    self.assertIn("per-application routing is unavailable", message.lower())
                    self.assertIn("No VPN was started", message)
                    self.assertNotIn("UNEXPECTED_MUTATION", message)
                    self.assertFalse((project / "vpngo").exists())


if __name__ == "__main__":
    unittest.main()
