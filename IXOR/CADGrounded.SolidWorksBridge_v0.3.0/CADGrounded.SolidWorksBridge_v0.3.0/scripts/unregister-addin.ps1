$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Dll = Join-Path $RepoRoot "src\CADGrounded.SolidWorksAddin\bin\Release\net48\CADGrounded.SolidWorksAddin.dll"
$RegAsm = "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\RegAsm.exe"

if (-not (Test-Path $Dll)) {
    throw "Add-in DLL not found: $Dll"
}

Write-Host "Unregistering COM add-in (run PowerShell as Administrator)..."
& $RegAsm $Dll /unregister
if ($LASTEXITCODE -ne 0) {
    throw "RegAsm unregister failed with exit code $LASTEXITCODE"
}

Write-Host "Unregistered. Restart SOLIDWORKS if it was open."
