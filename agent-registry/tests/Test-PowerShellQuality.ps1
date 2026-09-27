#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$moduleRoot = Join-Path $repoRoot 'agent-registry/powershell/CADGrounded.Tools'
$testPath = Join-Path $PSScriptRoot 'CADGrounded.EvidenceBoundary.Tests.ps1'

Import-Module PSScriptAnalyzer -MinimumVersion 1.22 -ErrorAction Stop
Import-Module Pester -MinimumVersion 6.0 -ErrorAction Stop

# These rules are an initial, narrow gate for the governed command surface.
# Expand only after measuring findings in the existing scripts.
$files = @(
    (Join-Path $moduleRoot 'CADGrounded.Tools.psm1'),
    (Join-Path $moduleRoot 'CADGrounded.Tools.psd1'),
    $testPath,
    $PSCommandPath
)
$rules = @('PSAvoidUsingInvokeExpression', 'PSAvoidUsingPlainTextForPassword', 'PSAvoidUsingConvertToSecureStringWithPlainText')
$findings = @($files | ForEach-Object {
    Invoke-ScriptAnalyzer -Path $_ -IncludeRule $rules
})
if ($findings.Count -gt 0) {
    $findings | Format-Table -AutoSize | Out-String | Write-Host
    throw "PSScriptAnalyzer found $($findings.Count) prohibited pattern(s)."
}

$result = Invoke-Pester -Path $testPath -PassThru -Output Detailed
if ($result.FailedCount -gt 0 -or $result.PassedCount -eq 0) {
    throw "Pester evidence-boundary suite failed: $($result.FailedCount) failed, $($result.PassedCount) passed."
}
Write-Host "PASS: PowerShell quality gates ($($result.PassedCount) Pester tests)"
