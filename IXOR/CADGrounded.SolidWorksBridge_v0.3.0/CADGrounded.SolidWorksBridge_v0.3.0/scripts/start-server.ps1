param(
    [switch]$AllowWrites,
    [switch]$MaxControl,
    [ValidateSet('full', 'intent-readonly')]
    [string]$ToolProfile = 'full',
    [ValidateRange(1, 65535)]
    [int]$Port = 8765
)
$ErrorActionPreference = "Stop"
if ($MaxControl) { $AllowWrites = $true }
if ($ToolProfile -eq 'intent-readonly' -and ($AllowWrites -or $MaxControl)) {
    throw 'The intent-readonly profile cannot be combined with AllowWrites or MaxControl.'
}
$env:SWBRIDGE_ALLOW_WRITES = $(if ($AllowWrites) { "1" } else { "0" })
$env:SWBRIDGE_MAX_CONTROL = $(if ($MaxControl) { "1" } else { "0" })
$env:SWBRIDGE_TOOL_PROFILE = $ToolProfile
$env:SWBRIDGE_PORT = [string]$Port
$root = Split-Path -Parent $PSScriptRoot
Write-Host "Tool profile: $ToolProfile. Port: $Port. Maximum control: $MaxControl. Writes: $AllowWrites."
Push-Location (Join-Path $root "src\mcp-server")
try { & node server.mjs } finally { Pop-Location }
