# Close the VPNGo interface installed by `vpngo --install-gui`, so the Windows installers can
# replace or remove its files. A running interface holds files in its venv: pip cannot update
# them and an uninstaller cannot delete them, which leaves a broken venv. The venv's
# pythonw.exe is a launcher that starts the base Python's pythonw.exe; both carry the
# interface's folder in their command line, so both are matched by it.
$Gui = Join-Path $env:LOCALAPPDATA 'vpngo-gui\'
Get-CimInstance Win32_Process |
    Where-Object { $_.Name -in 'python.exe', 'pythonw.exe' -and $_.CommandLine -and
                   $_.CommandLine.IndexOf($Gui, [StringComparison]::OrdinalIgnoreCase) -ge 0 } |
    ForEach-Object {
        Write-Output "Closing the VPNGo interface (process $($_.ProcessId))."
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
exit 0
