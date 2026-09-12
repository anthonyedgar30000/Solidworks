$ErrorActionPreference = "Stop"
if (Get-Process SLDWORKS -ErrorAction SilentlyContinue) {
    throw "Save your documents and close SOLIDWORKS before upgrading."
}
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Open PowerShell as Administrator to register the COM add-in."
}
$root = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $root "src\mcp-server")
try {
    & npm.cmd install
    if ($LASTEXITCODE -ne 0) { throw "npm install failed." }
    & npm.cmd test
    if ($LASTEXITCODE -ne 0) { throw "Node tests failed." }
} finally { Pop-Location }
& (Join-Path $PSScriptRoot "build-addin.ps1")
& (Join-Path $PSScriptRoot "register-addin.ps1")
Write-Host "Upgrade registered. Reopen SOLIDWORKS and v12, then run scripts\start-server.ps1."
