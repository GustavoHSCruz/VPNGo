param(
    [Parameter(Position=0)][string]$Application,
    [Parameter(Position=1)][string]$Action,
    [Parameter(Position=2)][string]$Profile
)

$ErrorActionPreference = 'Stop'
$Project = Split-Path -Parent $PSScriptRoot
$State = Join-Path $Project 'state'
$Python = if ($env:VPNGO_PYTHON) { $env:VPNGO_PYTHON } else { 'python' }
$Controller = Join-Path $Project 'shared/control.py'

function Invoke-Python([string]$Script, [string[]]$Arguments) {
    $Result = & $Python (Join-Path $Project $Script) @Arguments
    if ($LASTEXITCODE -ne 0) { throw "vpngo command failed: $Script" }
    return $Result
}

function Invoke-Control([string]$Name, [string]$Command) {
    Invoke-Python 'shared/control.py' @($Name, $Command)
}

try {
    if (-not $Application) {
        throw 'Usage: vpngo config <path> | setup <wireguard.conf> [profile] | profiles | <application> [start [profile]|stop|on|off|status]'
    }
    if ($Application -in @('profile','assign','start','stop','switch','status','on','off','policy','helper','version')) {
        $CliArgs = @($Application)
        if ($Action) { $CliArgs += $Action }
        if ($Profile) { $CliArgs += $Profile }
        if ($args) { $CliArgs += $args }
        & $Python (Join-Path $Project 'shared/commands.py') @CliArgs
        exit $LASTEXITCODE
    }
    if ($Application -eq 'profiles') {
        if ($Action -or $Profile) { throw 'Usage: vpngo profiles' }
        Invoke-Python 'shared/profiles.py' @('list')
        exit 0
    }
    if ($Application -eq 'config') {
        if (-not $Action -or $Profile) { throw 'Usage: vpngo config <bin-dir|executable>' }
        Invoke-Python 'shared/apps.py' @('config', $Action)
        exit 0
    }
    if ($Application -eq 'setup') {
        if (-not $Action) { throw 'Usage: vpngo setup <wireguard.conf> [profile]' }
        if ($Profile) {
            Invoke-Python 'shared/generate_mihomo.py' @($Action, $Profile)
        } else {
            Invoke-Python 'shared/generate_mihomo.py' @($Action)
        }
        exit 0
    }
    if (-not $Action) { $Action = 'start' }
    if ($Action -notin @('start','stop','on','off','status')) {
        throw 'Usage: vpngo <application> [start|stop|on|off|status]'
    }
    if ($Profile -and $Action -ne 'start') { throw 'A profile can only be supplied with start.' }
    if ($Action -ne 'start') {
        if ($Action -eq 'stop') {
            $AppJson = Invoke-Python 'shared/managed.py' @('inspect', $Application)
            if (-not $AppJson -or $AppJson -eq 'null') {
                Write-Output "$Application`: already stopped."
                exit 0
            }
            $App = $AppJson | ConvertFrom-Json
            $ProcessName = [System.IO.Path]::GetFileNameWithoutExtension($App.process)
            $Protected = @('python','python3','powershell','pwsh','cmd','conhost','explorer','svchost','system')
            if ($ProcessName -in $Protected) {
                throw "Refusing to close shared system process '$ProcessName' automatically."
            }
            $BlockFailed = $false
            try { Invoke-Control $Application 'block' | Out-Null } catch { $BlockFailed = $true }
            Get-Process -Name $ProcessName -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
            foreach ($HelperPath in $App.helpers) {
                $HelperName = [System.IO.Path]::GetFileNameWithoutExtension($HelperPath)
                if ($HelperName -and $HelperName -notin $Protected) {
                    Get-Process -Name $HelperName -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
                }
            }
            if ($BlockFailed -or (Get-Process -Name $ProcessName -ErrorAction SilentlyContinue)) {
                throw "$Application stop incomplete; the route remains blocked if Mihomo accepted it."
            }
            Write-Output "$Application`: application closed; its Mihomo route is blocked. Other applications stay connected."
            exit 0
        }
        Invoke-Control $Application $Action
        exit 0
    }

    if (-not $Profile) { $Profile = 'default' }
    $AppJson = Invoke-Python 'shared/managed.py' @('prepare', $Application, $Profile)
    $App = $AppJson | ConvertFrom-Json
    $ProcessName = [System.IO.Path]::GetFileNameWithoutExtension($App.process)
    if ($ProcessName -in @('python','python3','powershell','pwsh','cmd','conhost','explorer','svchost','system')) {
        throw "Refusing to close shared system process '$ProcessName' automatically."
    }
    $Mihomo = if ($env:VPNGO_MIHOMO) { $env:VPNGO_MIHOMO } else {
        (Get-Command mihomo.exe -ErrorAction Stop).Source
    }
    & $Python $Controller $Application status *> $null
    if ($LASTEXITCODE -ne 0) {
        $Config = Join-Path $State 'config.yaml'
        $Arguments = @('-d', ('"' + $State + '"'), '-f', ('"' + $Config + '"'))
        Start-Process -FilePath $Mihomo -ArgumentList $Arguments -Verb RunAs | Out-Null
        $Ready = $false
        for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
            Start-Sleep -Seconds 1
            & $Python $Controller $Application status *> $null
            if ($LASTEXITCODE -eq 0) { $Ready = $true; break }
        }
        if (-not $Ready) { throw 'Mihomo did not start. Check its elevated window and state/config.yaml.' }
    }
    Invoke-Control $Application 'on'
    Get-Process -Name $ProcessName -ErrorAction SilentlyContinue | Stop-Process -Force
    Invoke-Control $Application 'reconnect' | Out-Null
    Start-Sleep -Seconds 1
    Start-Process -FilePath $App.launch
    Write-Output "$Application started through the VPN."
} catch {
    Write-Error $_
    exit 1
}
