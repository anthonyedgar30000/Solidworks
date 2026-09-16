[CmdletBinding()]
param(
    [string]$TaskName = 'CADGrounded Remote Queue ReadOnly',
    [string]$RunnerPath = (Join-Path $PSScriptRoot 'Invoke-CADRemoteQueue.ps1'),
    [string]$ConfigPath = (Join-Path $PSScriptRoot 'queue-config.json'),
    [int]$EveryMinutes = 1
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($EveryMinutes -lt 1) {
    throw 'EveryMinutes must be at least 1.'
}

if (-not (Test-Path -LiteralPath $RunnerPath -PathType Leaf)) {
    throw "Runner not found: $RunnerPath"
}
if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    throw "Config not found: $ConfigPath"
}

$RunnerPath = (Resolve-Path -LiteralPath $RunnerPath).Path
$ConfigPath = (Resolve-Path -LiteralPath $ConfigPath).Path

$psExe = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$args = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$RunnerPath`" -ConfigPath `"$ConfigPath`""

$action = New-ScheduledTaskAction -Execute $psExe -Argument $args
$trigger = New-ScheduledTaskTrigger `
    -Once `
    -At ((Get-Date).AddMinutes(1)) `
    -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

# SOLIDWORKS is an interactive desktop COM application.  The queue task must run
# as the same logged-on user so the native worker can attach to the live
# SOLIDWORKS instance in that user's session.
$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal `
    -UserId $userId `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description 'CADGrounded read-only JSON queue runner. Same interactive user; no generic code execution; no CAD write commands.' `
    -Force | Out-Null

Write-Output "Installed task: $TaskName"
Write-Output "Runner: $RunnerPath"
Write-Output "Config: $ConfigPath"
Write-Output "Interval: $EveryMinutes minute(s)"
