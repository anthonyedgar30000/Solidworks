$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Dll = Join-Path $RepoRoot "src\CADGrounded.SolidWorksAddin\bin\Release\net48\CADGrounded.SolidWorksAddin.dll"
$RegAsm = "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\RegAsm.exe"

if (-not (Test-Path $Dll)) {
    throw "Add-in DLL not found. Run scripts\build-addin.ps1 first.`nExpected: $Dll"
}

if (-not (Test-Path $RegAsm)) {
    throw "64-bit .NET Framework RegAsm not found: $RegAsm"
}

Write-Host "Registering COM add-in (run PowerShell as Administrator)..."
& $RegAsm $Dll /codebase
if ($LASTEXITCODE -ne 0) {
    throw "RegAsm failed with exit code $LASTEXITCODE"
}

Write-Host "Registered CADGrounded SolidWorks Bridge. Restart SOLIDWORKS, then check Tools > Add-Ins."
