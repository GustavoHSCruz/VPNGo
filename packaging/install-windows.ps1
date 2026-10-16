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
    foreach ($Path in @($New, $Old)) {
        if (Test-Path -LiteralPath $Path) { Remove-Item -LiteralPath $Path -Recurse -Force }
    }
    Move-Item -LiteralPath (Join-Path $Work "vpngo-$Version-windows") -Destination $New
    if (Test-Path -LiteralPath $App) { Move-Item -LiteralPath $App -Destination $Old }
    Move-Item -LiteralPath $New -Destination $App
    if (Test-Path -LiteralPath $Old) { Remove-Item -LiteralPath $Old -Recurse -Force }

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $App 'windows\install.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'The vpngo command installer failed.' }
    Write-Output "vpngo $Version installed in $App"
    if (-not $env:VPNGO_MIHOMO -and -not (Get-Command mihomo.exe -ErrorAction SilentlyContinue) -and
            -not (Test-Path -LiteralPath (Join-Path $HOME 'bin\mihomo.exe'))) {
        Write-Output 'Next: install Mihomo (step 1 of the Windows guide).'
    }
} finally {
    Remove-Item -LiteralPath $Work -Recurse -Force -ErrorAction SilentlyContinue
}
