#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-True {
    param(
        [Parameter(Mandatory=$true)][bool]$Condition,
        [Parameter(Mandatory=$true)][string]$Message
    )
    if (-not $Condition) { throw $Message }
}

$path = Join-Path $PSScriptRoot 'Verify-ContactManifold-FunctionFirst-LateralContacts.ps1'
Assert-True (Test-Path -LiteralPath $path -PathType Leaf) 'Lateral contact manifold verifier is missing.'

$tokens = $null
$parseErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile(
    $path,
    [ref]$tokens,
    [ref]$parseErrors
)

if (@($parseErrors).Count -gt 0) {
    $detail = @($parseErrors | ForEach-Object {
        "Line $($_.Extent.StartLineNumber): $($_.Message)"
    }) -join [Environment]::NewLine
    throw "Lateral contact manifold verifier has PowerShell parse errors:$([Environment]::NewLine)$detail"
}

$source = Get-Content -LiteralPath $path -Raw

foreach ($required in @(
    'function Get-MatrixRank',
    'sw.contact_surface_normals_pair',
    'sw.classify_contact_pair',
    'TANGENT_CYLINDER_PLANE_GENERATOR_LINE',
    'EXTERNAL_TANGENT_PARALLEL_CYLINDER_GENERATOR_LINE',
    'five_dof_restraint_excluding_wrap_rotation',
    "write_authority='NONE'",
        "$ExpectedWorkerVersion = '0.4.5'",
    'mechanical_acceptance_granted=$false'
)) {
    Assert-True ($source.Contains($required)) "Verifier source is missing required token '$required'."
}

foreach ($forbidden in @(
    'sw.set_transform',
    'Transform2 =',
    'SaveAs',
    'Save3',
    'EditRebuild',
    'ForceRebuild',
    'AddMate',
    'CreateMate',
    'SetSuppression'
)) {
    Assert-True (-not $source.Contains($forbidden)) "Verifier source contains forbidden token '$forbidden'."
}

Write-Host 'PASS: lateral contact manifold verifier parses under PowerShell and preserves read-only source contract'
