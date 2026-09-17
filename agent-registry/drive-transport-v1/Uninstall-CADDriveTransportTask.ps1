[CmdletBinding()]
param(
    [string]$TaskName = 'CADGrounded Drive Transport ReadOnly'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $task) {
    Write-Output "Task not installed: $TaskName"
    exit 0
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Output "Removed task: $TaskName"
