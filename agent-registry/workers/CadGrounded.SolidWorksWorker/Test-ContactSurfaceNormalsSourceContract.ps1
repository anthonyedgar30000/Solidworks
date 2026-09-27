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

$sourcePath = Join-Path $PSScriptRoot 'Program.cs'
Assert-True (Test-Path -LiteralPath $sourcePath -PathType Leaf) 'Program.cs is missing.'
$source = Get-Content -LiteralPath $sourcePath -Raw

foreach ($token in @(
    '"sw.contact_surface_normals_pair"',
    'ContactSurfaceNormalsPair(',
    'RequireExactActiveDocument(',
    'IModelDoc2.ClosestDistance',
    'GetClosestPointOn(',
    'face.Normal',
    'EvaluateAtPoint(',
    'FaceInSurfaceSense()',
    'IBody2.ApplyTransform',
    'model_mutation = false',
    'write_authority = "NONE"',
    'does not classify physical interference, support, reaction capacity, friction, preload, or mechanism function'
)) {
    Assert-True ($source.Contains($token)) "Contact-surface normal source is missing required token '$token'."
}

$methodStart = $source.IndexOf('public object ContactSurfaceNormalsPair(')
$methodEnd = $source.IndexOf('public object ClassifyContactPair(', $methodStart)
Assert-True ($methodStart -ge 0 -and $methodEnd -gt $methodStart) 'Could not isolate ContactSurfaceNormalsPair source.'
$method = $source.Substring($methodStart, $methodEnd - $methodStart)

foreach ($forbidden in @(
    'Transform2 =',
    'SaveAs',
    'Save3',
    'EditRebuild',
    'ForceRebuild',
    'AddMate',
    'CreateMate',
    'SelectByID',
    'SetSuppression'
)) {
    Assert-True (-not $method.Contains($forbidden)) "Contact-surface normal method contains forbidden mutation token '$forbidden'."
}

Assert-True ($method.Contains('distanceM <= contactToleranceM')) 'Face normals must only be evaluated at contact/coincidence tolerance.'
Assert-True ($method.Contains('not_evaluated_positive_clearance')) 'Positive clearance must not masquerade as a contact-surface normal observation.'
Assert-True ($method.Contains('contact_point_face_binding_unresolved')) 'Missing face binding must remain explicitly unresolved.'

Write-Host 'PASS: sw.contact_surface_normals_pair source/authority contract'
