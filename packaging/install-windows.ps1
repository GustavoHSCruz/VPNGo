# Download, verify and install vpngo @VERSION@ for Windows.
#
#   powershell -ExecutionPolicy Bypass -File install-windows.ps1
#
# $env:VPNGO_VERSION installs another release. $env:VPNGO_PREFIX changes the
# install folder (default: %LOCALAPPDATA%\vpngo). $env:VPNGO_RELEASE_URL
# downloads from another location, such as a local mirror.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'  # Invoke-WebRequest is much slower with its progress bar.

$Version = if ($env:VPNGO_VERSION) { $env:VPNGO_VERSION } else { '@VERSION@' }
$Repository = '@REPOSITORY@'
$Asset = "vpngo-$Version-windows.zip"
$Base = if ($env:VPNGO_RELEASE_URL) { $env:VPNGO_RELEASE_URL.TrimEnd('/') } else { "https://github.com/$Repository/releases/download/v$Version" }
$Prefix = if ($env:VPNGO_PREFIX) { $env:VPNGO_PREFIX } else { Join-Path $env:LOCALAPPDATA 'vpngo' }

$Work = Join-Path ([IO.Path]::GetTempPath()) ('vpngo-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Work | Out-Null
$BackupCreated = $false
$NewInstalled = $false
$Shim = Join-Path (Join-Path $HOME 'bin') 'vpngo.cmd'
$ShimExisted = Test-Path -LiteralPath $Shim
$OriginalUserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($ShimExisted) { Copy-Item -LiteralPath $Shim -Destination (Join-Path $Work 'vpngo.cmd') }
try {
    Write-Output "Downloading vpngo $Version for Windows..."
    $Archive = Join-Path $Work $Asset
    $Sums = Join-Path $Work 'SHA256SUMS'
    Invoke-WebRequest -UseBasicParsing -Uri "$Base/$Asset" -OutFile $Archive
    Invoke-WebRequest -UseBasicParsing -Uri "$Base/SHA256SUMS" -OutFile $Sums
    $Expected = $null
    foreach ($Line in Get-Content -LiteralPath $Sums) {
        if ($Line -match '^([0-9a-fA-F]{64}) [ *](.+)$' -and $Matches[2] -eq $Asset) {
            $Expected = $Matches[1].ToLowerInvariant()
        }
    }
    if (-not $Expected) { throw "$Asset is not listed in SHA256SUMS." }
    $Actual = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Actual -ne $Expected) { throw "Checksum mismatch for $Asset; the download is corrupt or was altered." }
    Write-Output 'Checksum verified.'

    Expand-Archive -LiteralPath $Archive -DestinationPath $Work -Force
    New-Item -ItemType Directory -Path $Prefix -Force | Out-Null
    $App = Join-Path $Prefix 'app'
    $New = Join-Path $Prefix 'app.new'
    $Old = Join-Path $Prefix 'app.old'
    if (Test-Path -LiteralPath $Old) { throw 'app.old exists; resolve the previous interrupted upgrade before retrying.' }
    if (Test-Path -LiteralPath $New) { Remove-Item -LiteralPath $New -Recurse -Force }
    Move-Item -LiteralPath (Join-Path $Work "vpngo-$Version-windows") -Destination $New
    if (Test-Path -LiteralPath $App) {
        Move-Item -LiteralPath $App -Destination $Old
        $BackupCreated = $true
    }
    $NewInstalled = $true
    Move-Item -LiteralPath $New -Destination $App

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $App 'windows\install.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'The vpngo command installer failed.' }
    $Python = if ($env:VPNGO_PYTHON) { $env:VPNGO_PYTHON } else { 'python' }
    $InstalledVersion = & $Python (Join-Path $App 'shared\commands.py') version
    if ($LASTEXITCODE -ne 0 -or $InstalledVersion -ne "vpngo $Version") {
        throw 'The installed vpngo version did not validate.'
    }
    $BackupCreated = $false
    $NewInstalled = $false
    if (Test-Path -LiteralPath $Old) {
        try { Remove-Item -LiteralPath $Old -Recurse -Force }
        catch { Write-Warning 'Could not remove app.old; remove it before the next upgrade.' }
    }
    Write-Output "vpngo $Version installed in $App"
    if (-not $env:VPNGO_MIHOMO -and -not (Get-Command mihomo.exe -ErrorAction SilentlyContinue) -and
            -not (Test-Path -LiteralPath (Join-Path $HOME 'bin\mihomo.exe'))) {
        Write-Output 'Next: install Mihomo (step 1 of the Windows guide).'
    }
} catch {
    $Failure = $_
    if ($NewInstalled -or $BackupCreated) {
        if ($NewInstalled -and (Test-Path -LiteralPath $App)) {
            Remove-Item -LiteralPath $App -Recurse -Force
        }
        if ($BackupCreated) { Move-Item -LiteralPath $Old -Destination $App }
        if ($ShimExisted) {
            Copy-Item -LiteralPath (Join-Path $Work 'vpngo.cmd') -Destination $Shim -Force
        } elseif (Test-Path -LiteralPath $Shim) {
            Remove-Item -LiteralPath $Shim -Force
        }
        [Environment]::SetEnvironmentVariable('Path', $OriginalUserPath, 'User')
        Write-Warning 'Previous vpngo installation restored.'
    }
    throw $Failure
} finally {
    Remove-Item -LiteralPath $Work -Recurse -Force -ErrorAction SilentlyContinue
}
