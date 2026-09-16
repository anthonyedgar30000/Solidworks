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

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description 'CADGrounded read-only JSON queue runner. No generic code execution; no CAD write commands.' `
    -Force | Out-Null

Write-Output "Installed task: $TaskName"
Write-Output "Runner: $RunnerPath"
Write-Output "Config: $ConfigPath"
Write-Output "Interval: $EveryMinutes minute(s)"
