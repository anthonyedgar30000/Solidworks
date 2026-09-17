[CmdletBinding()]
param(
    [string]$TaskName = 'CADGrounded Drive Transport ReadOnly',
    [string]$TransportPath = (Join-Path $PSScriptRoot 'Invoke-CADDriveTransport.ps1'),
    [string]$ConfigPath = (Join-Path $PSScriptRoot 'transport-config.json'),
    [int]$EveryMinutes = 1
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($EveryMinutes -lt 1) {
    throw 'EveryMinutes must be at least 1.'
}
if (-not (Test-Path -LiteralPath $TransportPath -PathType Leaf)) {
    throw "Transport script not found: $TransportPath"
}
if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    throw "Transport config not found: $ConfigPath"
}

$TransportPath = (Resolve-Path -LiteralPath $TransportPath).Path
$ConfigPath = (Resolve-Path -LiteralPath $ConfigPath).Path

$psExe = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$args = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$TransportPath`" -ConfigPath `"$ConfigPath`""
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

# Run under the same interactive Windows identity that owns the rclone OAuth
# profile and the local CADGrounded queue tree.
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
    -Description 'CADGrounded Google Drive JSON transport only. No SOLIDWORKS API or CAD write authority.' `
    -Force | Out-Null

Write-Output "Installed task: $TaskName"
Write-Output "User: $userId"
Write-Output "Transport: $TransportPath"
Write-Output "Config: $ConfigPath"
Write-Output "Interval: $EveryMinutes minute(s)"
