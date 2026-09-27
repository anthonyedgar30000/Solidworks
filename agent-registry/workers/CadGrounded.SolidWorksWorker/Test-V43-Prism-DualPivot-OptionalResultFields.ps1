Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Verifier = Join-Path $PSScriptRoot 'Verify-Pop-V43-Prism-DualPivot-ExactHypotheticalSweep.ps1'
if (-not (Test-Path -LiteralPath $Verifier -PathType Leaf)) {
    throw "Verifier missing: $Verifier"
}

$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $Verifier,
    [ref]$tokens,
    [ref]$errors
)
if (@($errors).Count -ne 0) {
    throw ("Verifier parser errors: " + (@($errors | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine))
}

$fn = $ast.Find({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
    $node.Name -ceq 'Get-OptionalPropertyValue'
}, $true)
if ($null -eq $fn) {
    throw 'Get-OptionalPropertyValue was not found in the verifier.'
}
. ([ScriptBlock]::Create($fn.Extent.Text))

$presentZero = [pscustomobject]@{
    intersection_volume_mm3 = 0.0
    minimum_distance_mm = 12.5
}
$zeroValue = Get-OptionalPropertyValue -Object $presentZero -Name 'intersection_volume_mm3'
if ($null -eq $zeroValue -or [double]$zeroValue -ne 0.0) {
    throw 'Present zero-valued optional property was not preserved.'
}
$distanceValue = Get-OptionalPropertyValue -Object $presentZero -Name 'minimum_distance_mm'
if ([double]$distanceValue -ne 12.5) {
    throw 'Present optional minimum_distance_mm was not preserved.'
}

$presentNull = [pscustomobject]@{
    intersection_volume_mm3 = $null
}
if ($null -ne (Get-OptionalPropertyValue -Object $presentNull -Name 'intersection_volume_mm3')) {
    throw 'Present null optional property did not return null.'
}

$missing = [pscustomobject]@{
    classification = 'indeterminate_non_solid_geometry'
}
if ($null -ne (Get-OptionalPropertyValue -Object $missing -Name 'intersection_volume_mm3')) {
    throw 'Missing intersection_volume_mm3 did not fail closed to null.'
}
if ($null -ne (Get-OptionalPropertyValue -Object $missing -Name 'minimum_distance_mm')) {
    throw 'Missing minimum_distance_mm did not fail closed to null.'
}

$source = Get-Content -LiteralPath $Verifier -Raw
$directPatterns = @(
    'intersection_volume_mm3 = $data.intersection_volume_mm3',
    'minimum_distance_mm = $data.minimum_distance_mm'
)
foreach ($pattern in $directPatterns) {
    if ($source.Contains($pattern)) {
        throw "Verifier still directly accesses optional result field: $pattern"
    }
}

Write-Host 'PASS: v43 PRISM dual-pivot optional result-field regression'
