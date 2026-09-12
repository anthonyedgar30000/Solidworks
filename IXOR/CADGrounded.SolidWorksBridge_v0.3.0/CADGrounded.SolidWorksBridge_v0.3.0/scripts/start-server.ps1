param([switch]$AllowWrites, [switch]$MaxControl)
$ErrorActionPreference = "Stop"
if ($MaxControl) { $AllowWrites = $true }
$env:SWBRIDGE_ALLOW_WRITES = $(if ($AllowWrites) { "1" } else { "0" })
$env:SWBRIDGE_MAX_CONTROL = $(if ($MaxControl) { "1" } else { "0" })
$root = Split-Path -Parent $PSScriptRoot
Write-Host "Maximum control: $MaxControl. Writes: $AllowWrites."
Push-Location (Join-Path $root "src\mcp-server")
try { & node server.mjs } finally { Pop-Location }
