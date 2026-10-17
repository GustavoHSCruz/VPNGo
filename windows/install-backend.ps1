param([switch]$DownloadOnly)

$ErrorActionPreference = 'Stop'
$Version = '2.6.4'
$Architecture = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
$Architecture = switch ($Architecture) { 'AMD64' { 'x64' }; 'ARM64' { 'arm64' }; 'x86' { 'x86' }; default { throw 'Unsupported Windows architecture.' } }
$Hashes = @{
    x64 = 'afaf3ac8a2069f9653adb1b4a63b31d1edd8aa109ccdc367cf0d4462e78f5027'
    arm64 = '33abd7392471c146912033580c5c9056a723cad272b66ef4efb414a8f02c1502'
    x86 = '39eb06835b999aeb0531e2a8063d5370aec1b96903ce6bd4353c469d313f5e09'
}
$Directory = Join-Path $env:LOCALAPPDATA 'vpngo\downloads'
New-Item -ItemType Directory -Path $Directory -Force | Out-Null
$Name = "ProxiFyre-$Version-win-$Architecture-setup.exe"
$Installer = Join-Path $Directory $Name
$Uri = "https://github.com/wiresock/proxifyre/releases/download/v$Version/$Name"
if (-not (Test-Path -LiteralPath $Installer) -or
    (Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash -ine $Hashes[$Architecture]) {
    Invoke-WebRequest -Uri $Uri -OutFile $Installer -UseBasicParsing
}
if ((Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash -ine $Hashes[$Architecture]) {
    throw 'ProxiFyre installer SHA-256 verification failed. Nothing was installed.'
}
Write-Output "Verified ProxiFyre $Version installer: $Installer"
if ($DownloadOnly) { return }
# This explicit setup command installs Windows Packet Filter and runtimes.
# It does not start proxying traffic. VPNGo applies an app allowlist later.
$Install = Start-Process -FilePath $Installer -ArgumentList @('/install','/quiet','/norestart') `
    -Verb RunAs -WindowStyle Hidden -PassThru -Wait
if ($Install.ExitCode -eq 3010) { throw 'ProxiFyre installed; restart Windows before using vpngo.' }
if ($Install.ExitCode -ne 0) { throw "ProxiFyre setup failed (exit $($Install.ExitCode))." }
Write-Output 'ProxiFyre installed. Run vpngo start <app> to apply process filters.'
