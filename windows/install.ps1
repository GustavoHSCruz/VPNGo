$ErrorActionPreference = 'Stop'
$Script = Join-Path $PSScriptRoot 'vpngo.ps1'
$InstallDir = Join-Path $HOME 'bin'
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
$Shim = Join-Path $InstallDir 'vpngo.cmd'
if (Test-Path -LiteralPath $Shim) {
    Copy-Item -LiteralPath $Shim -Destination ($Shim + '.backup.' + (Get-Date -Format 'yyyyMMddHHmmss'))
}
$Body = '@echo off' + "`r`n" + 'chcp 65001 >nul' + "`r`n" + 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $Script + '" %*' + "`r`n"
[System.IO.File]::WriteAllText($Shim, $Body, [System.Text.UTF8Encoding]::new($false))
$UserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$Parts = @($UserPath -split ';' | Where-Object { $_ })
if ($Parts -notcontains $InstallDir) {
    [Environment]::SetEnvironmentVariable('Path', (($Parts + $InstallDir) -join ';'), 'User')
}
Write-Output "Installed $Shim. Open a new terminal before using vpngo."
