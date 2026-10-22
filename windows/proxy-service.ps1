param(
    [ValidateSet('Check','Apply','Stop','Validate')][string]$Mode = 'Check',
    [string]$ConfigPath,
    [string]$OwnerSid = ([Security.Principal.WindowsIdentity]::GetCurrent().User.Value),
    [string]$ResultPath
)

$ErrorActionPreference = 'Stop'
$ServiceName = 'ProxiFyreService'

function Read-DesiredConfig {
    if (-not $ConfigPath -or -not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
        throw 'Missing generated ProxiFyre configuration.'
    }
    $Text = [IO.File]::ReadAllText($ConfigPath)
    $Desired = $Text | ConvertFrom-Json
    if ($Desired.bypassLan -ne $true -or $Desired.logLevel -ne 'Info' -or
        @($Desired.excludes).Count -ne 2 -or
        $Desired.excludes[0] -ne 'mihomo.exe' -or $Desired.excludes[1] -ne 'ProxiFyre.exe') {
        throw 'Invalid VPNGo process routing configuration.'
    }
    $Protected = @('python','python3','powershell','pwsh','cmd','conhost','explorer','svchost','system','mihomo','proxifyre')
    foreach ($Proxy in $Desired.proxies) {
        if ($Proxy.socks5ProxyEndpoint -notmatch '^127\.0\.0\.1:(2[0-9]{4})$' -or
            @($Proxy.appNames).Count -eq 0 -or
            ($Proxy.supportedProtocols -join ',') -cne 'TCP,UDP' -or
            ($Proxy.supportedAddressFamilies -join ',') -cne 'IPv4,IPv6' -or
            $Proxy.username -notmatch '^vpngo-[a-f0-9]{12}$' -or
            $Proxy.password -notmatch '^[a-f0-9]{64}$') {
            throw 'Only authenticated loopback TCP/UDP proxies are allowed.'
        }
        foreach ($AppName in $Proxy.appNames) {
            if ([string]::IsNullOrWhiteSpace($AppName) -or $AppName -match '[*?\r\n]' -or
                $AppName -notmatch '\.exe$' -or
                $Protected -contains [IO.Path]::GetFileNameWithoutExtension($AppName)) {
                throw 'Global, wildcard and shared-system-process proxy rules are forbidden.'
            }
            if ($AppName -match '[/\\]' -and -not [IO.Path]::IsPathRooted($AppName)) {
                throw 'Helper matches must be absolute executable paths.'
            }
        }
    }
    return @{ Text = $Text; Config = $Desired }
}

function Get-Installation {
    $Entry = Get-ItemProperty -LiteralPath "HKLM:\SYSTEM\CurrentControlSet\Services\$ServiceName" -ErrorAction SilentlyContinue
    if (-not $Entry -or $Entry.ImagePath -notmatch '^(?:"([^"]+\.exe)"|(.+?\.exe))(?:\s|$)') {
        throw 'Install ProxiFyre 2.6.4 or newer first: powershell -ExecutionPolicy Bypass -File windows\install-backend.ps1. No VPN was started.'
    }
    $Executable = if ($Matches[1]) { $Matches[1] } else { $Matches[2] }
    $Executable = [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($Executable))
    $ProtectedRoot = @($env:ProgramFiles, ${env:ProgramFiles(x86)}) | Where-Object {
        $_ -and $Executable.StartsWith(([IO.Path]::GetFullPath($_).TrimEnd('\') + '\'), [StringComparison]::OrdinalIgnoreCase)
    }
    if (-not $ProtectedRoot -or [IO.Path]::GetFileName($Executable) -ine 'ProxiFyre.exe' -or
        -not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        throw 'Use the official ProxiFyre installer in Program Files; user-writable service payloads are not supported.'
    }
    $VersionText = [Diagnostics.FileVersionInfo]::GetVersionInfo($Executable).FileVersion
    if ($VersionText -notmatch '^(\d+\.\d+\.\d+)' -or [version]$Matches[1] -lt [version]'2.6.4') {
        throw 'ProxiFyre 2.6.4 or newer is required for exact process matching and IPv6 support.'
    }
    $Directory = Split-Path -Parent $Executable
    $RuntimeConfig = Join-Path $Directory 'app-config.json'
    $OwnerFile = Join-Path $Directory 'vpngo-owner.json'
    $Owner = $null
    if (Test-Path -LiteralPath $OwnerFile) {
        $Owner = [IO.File]::ReadAllText($OwnerFile) | ConvertFrom-Json
        if ($Owner.sid -ne $OwnerSid -or $Owner.schema -ne 1) {
            throw 'This ProxiFyre installation is managed by another VPNGo user.'
        }
    } elseif (Test-Path -LiteralPath $RuntimeConfig) {
        throw 'ProxiFyre already has a configuration. VPNGo will not overwrite it; use a dedicated installation.'
    }
    return @{ ConfigPath = $RuntimeConfig; OwnerPath = $OwnerFile; OwnerDigest = $Owner.digest;
              Service = (Get-Service -Name $ServiceName -ErrorAction Stop) }
}

function Get-TextDigest([string]$Text) {
    $Hasher = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($Hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text)))).Replace('-', '').ToLowerInvariant() }
    finally { $Hasher.Dispose() }
}

function Write-Atomic([string]$Path, [string]$Content) {
    $Temporary = $Path + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    try {
        [IO.File]::WriteAllText($Temporary, $Content, [Text.UTF8Encoding]::new($false))
        if (Test-Path -LiteralPath $Path) {
            [IO.File]::Replace($Temporary, $Path, [NullString]::Value)
        } else {
            [IO.File]::Move($Temporary, $Path)
        }
    } finally {
        if (Test-Path -LiteralPath $Temporary) { Remove-Item -LiteralPath $Temporary -Force }
    }
}

function Invoke-Operation {
    if ($Mode -eq 'Validate') { Read-DesiredConfig | Out-Null; return @{ valid = $true } }
    $Installation = Get-Installation
    $Service = $Installation.Service
    if ($Mode -eq 'Stop') {
        Stop-Service -Name $ServiceName -ErrorAction Stop
        $Service.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(15))
        return @{ stopped = $true }
    }
    $Desired = if ($ConfigPath) { Read-DesiredConfig } else { $null }
    $NeedsApply = $true
    if ($Desired) {
        $NeedsRunning = @($Desired.Config.proxies).Count -gt 0
        $ExpectedState = if ($NeedsRunning) { 'Running' } else { 'Stopped' }
        if (Test-Path -LiteralPath $Installation.ConfigPath) {
            $NeedsApply = ([IO.File]::ReadAllText($Installation.ConfigPath) -cne $Desired.Text) -or
                          ($Service.Status.ToString() -ne $ExpectedState) -or
                          ($Installation.OwnerDigest -cne (Get-TextDigest $Desired.Text))
        } elseif (-not $NeedsRunning -and $Service.Status -eq 'Stopped') {
            $NeedsApply = $false
        }
    }
    if ($Mode -eq 'Check') {
        return @{ installed = $true; needsApply = $NeedsApply; running = ($Service.Status -eq 'Running') }
    }
    if (-not $Desired) { throw 'Apply requires a generated configuration.' }
    if (-not $NeedsApply) { return @{ applied = $true } }
    $OldText = if (Test-Path -LiteralPath $Installation.ConfigPath) { [IO.File]::ReadAllText($Installation.ConfigPath) } else { $null }
    $HadOwner = Test-Path -LiteralPath $Installation.OwnerPath
    $OldOwner = if ($HadOwner) { [IO.File]::ReadAllText($Installation.OwnerPath) } else { $null }
    $WasRunning = $Service.Status -eq 'Running'
    try {
        Stop-Service -Name $ServiceName -ErrorAction Stop
        $Service.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(15))
        Write-Atomic $Installation.ConfigPath $Desired.Text
        Write-Atomic $Installation.OwnerPath (@{ schema = 1; sid = $OwnerSid; digest = (Get-TextDigest $Desired.Text) } | ConvertTo-Json)
        if (@($Desired.Config.proxies).Count -gt 0) {
            Start-Service -Name $ServiceName -ErrorAction Stop
            $Service.WaitForStatus('Running', [TimeSpan]::FromSeconds(15))
            Start-Sleep -Seconds 1
            $Service.Refresh()
            if ($Service.Status -ne 'Running') { throw 'ProxiFyre stopped during startup. Check its logs and Windows Packet Filter installation.' }
        }
    } catch {
        $Failure = $_
        Stop-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($null -ne $OldText) { Write-Atomic $Installation.ConfigPath $OldText }
        elseif (Test-Path -LiteralPath $Installation.ConfigPath) { Remove-Item -LiteralPath $Installation.ConfigPath -Force }
        if ($HadOwner) { Write-Atomic $Installation.OwnerPath $OldOwner }
        elseif (Test-Path -LiteralPath $Installation.OwnerPath) {
            Remove-Item -LiteralPath $Installation.OwnerPath -Force
        }
        if ($WasRunning) { Start-Service -Name $ServiceName -ErrorAction SilentlyContinue }
        throw $Failure
    }
    return @{ applied = $true }
}

$Mutex = $null
$Acquired = $false
try {
    if ($Mode -in @('Apply','Stop')) {
        $Principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
        if (-not $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
            throw 'Applying per-application filters requires administrator permission.'
        }
        $Mutex = [Threading.Mutex]::new($false, 'Global\VPNGo-ProxiFyre')
        try { $Acquired = $Mutex.WaitOne(15000) } catch [Threading.AbandonedMutexException] { $Acquired = $true }
        if (-not $Acquired) { throw 'Another VPNGo command is updating the process filters. Try again.' }
    }
    $Result = Invoke-Operation | ConvertTo-Json -Compress
    if ($ResultPath) { [IO.File]::WriteAllText($ResultPath, $Result) } else { Write-Output $Result }
    exit 0
} catch {
    $Result = @{ error = $_.Exception.Message } | ConvertTo-Json -Compress
    if ($ResultPath) { [IO.File]::WriteAllText($ResultPath, $Result) } else { [Console]::Error.WriteLine($_.Exception.Message) }
    exit 1
} finally {
    if ($Acquired) { $Mutex.ReleaseMutex() }
    if ($Mutex) { $Mutex.Dispose() }
}
