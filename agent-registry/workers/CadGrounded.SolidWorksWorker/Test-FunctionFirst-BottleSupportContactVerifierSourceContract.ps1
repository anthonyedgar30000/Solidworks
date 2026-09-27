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

$verifierPath = Join-Path $PSScriptRoot 'Verify-ClassifyContact-FunctionFirst-BottleSupport.ps1'
Assert-True (Test-Path -LiteralPath $verifierPath -PathType Leaf) 'Function-first bottle support/contact verifier is missing.'

$source = [System.IO.File]::ReadAllText($verifierPath)

foreach ($required in @(
    "ExpectedWorkerVersion = '",
    "ExpectedConfiguration = 'V43_WRAP'",
    "BENCH_BOTTLE_D48_H180-2",
    "BENCH_CONVEYOR_L900_W82_H950-1",
    "FITCHECK_DRIVEN_WRAP_BELT_5x160x93_V25-1",
    "FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-1",
    "FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-2",
    "FITCHECK_INDEX_STOP_FINGER_54p25x6x20_V37-1",
    "FITCHECK_INDEX_STOP_FINGER_54p25x6x20_V37-2",
    "sw.classify_contact_pair",
    "write_authority -cne 'NONE'",
    'model_mutation -ne $false',
    "Get-TargetState",
    "Get-FileEvidence",
    'mechanical_acceptance_granted = $false',
    "investigation_role_candidate values are routing labels, not engineering conclusions"
)) {
    Assert-True ($source.Contains($required)) "Verifier is missing required bounded-read invariant: $required"
}

$pairCount = ([regex]::Matches($source, '\[ordered\]@\{ a = \$Bottle; b = ')).Count
Assert-True ($pairCount -eq 6) "Expected exactly six function-first bottle candidate pairs; found $pairCount."

foreach ($forbidden in @(
    'sw.set_transform',
    'sw.insert_component',
    'AddMate',
    'CreateMate',
    'EditRebuild',
    'ForceRebuild',
    'SaveAs',
    'Save3',
    'SetTransformAndSolve2'
)) {
    Assert-True (-not $source.Contains($forbidden)) "Verifier contains forbidden CAD write token '$forbidden'."
}

foreach ($boundary in @(
    'which observed pair is a required functional support or restraint',
    'surface normals or restraint rank',
    'support sufficiency against gravity or tipping',
    'friction, traction, preload, force, stiffness, or reaction capacity',
    'interval-wide contact, capture, label transfer, release, or reachable-state clearance',
    'mechanical acceptance'
)) {
    Assert-True ($source.Contains($boundary)) "Verifier omits required epistemic boundary '$boundary'."
}

Write-Host 'PASS: function-first bottle support/contact verifier source contract'
