[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$programPath = Join-Path $PSScriptRoot 'Program.cs'
if (-not (Test-Path -LiteralPath $programPath -PathType Leaf)) { throw "Program.cs not found: $programPath" }
$source = Get-Content -LiteralPath $programPath -Raw

function Assert-Contains {
    param([string]$Text, [string]$Needle, [string]$Message)
    if (-not $Text.Contains($Needle)) { throw $Message }
}

Assert-Contains $source '"sw.classify_contact_pair_at_transform"' 'Native allowlist/dispatch does not contain sw.classify_contact_pair_at_transform.'
Assert-Contains $source 'public object ClassifyContactPairAtTransform(' 'ClassifyContactPairAtTransform method is missing.'
Assert-Contains $source 'IComponent2.GetBodies3(swSolidBody)' 'Hypothetical result provenance no longer names GetBodies3.'
Assert-Contains $source 'IBody2.Copy + IBody2.ApplyTransform on temporary copies only' 'Hypothetical temporary-body transform provenance is missing.'
Assert-Contains $source 'unresolved_for_hypothetical_nonintersecting_temporary_bodies' 'Hypothetical non-intersection must fail closed when temporary-body distance is unresolved.'
Assert-Contains $source 'IBody2.Operations2(SWBODYINTERSECT)' 'Hypothetical B-rep intersection provenance is missing.'
Assert-Contains $source 'model_mutation = false' 'Worker source no longer reports model_mutation=false.'
Assert-Contains $source 'write_authority = "NONE"' 'Worker source no longer reports write_authority=NONE.'

if ($source -match '\.Transform2\s*=') { throw 'Worker source contains a Component2.Transform2 assignment.' }

$start = $source.IndexOf('public object ClassifyContactPairAtTransform(', [StringComparison]::Ordinal)
$end = $source.IndexOf('private static IBody2[] GetSolidBodies(', $start, [StringComparison]::Ordinal)
if ($start -lt 0 -or $end -le $start) { throw 'Could not isolate ClassifyContactPairAtTransform source region.' }
$region = $source.Substring($start, $end - $start)

Assert-Contains $region 'evaluationIsCurrentPose' 'Current-pose guard is missing.'
Assert-Contains $region '_doc.ClosestDistance' 'Current-pose distance path is missing.'
Assert-Contains $region 'noninterfering_contact_or_clearance_unresolved' 'Hypothetical non-intersection fail-closed classification is missing.'

foreach ($forbidden in @('.Select','EditRebuild','ForceRebuild','Save','SetSuppression','AddMate','CreateMate')) {
    if ($region.Contains($forbidden)) { throw "Hypothetical-transform path contains forbidden token: $forbidden" }
}

foreach ($required in @('RequireExactActiveDocument(','GetSolidBodies(','CopyAndTransformBody(','Operations2(','maxBodyPairs','TransformArraysEquivalent(')) {
    if (-not $region.Contains($required)) { throw "Hypothetical-transform path is missing required token: $required" }
}

Write-Output 'PASS: hypothetical contact-at-transform source contract preserves bounded read-only behavior.'

if ($region.Contains('.GetDistance(')) { throw 'Hypothetical-transform path must not invoke unvalidated entity distance on temporary geometry.' }
