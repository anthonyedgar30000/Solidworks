#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-True {
    param([Parameter(Mandatory=$true)][bool]$Condition,[Parameter(Mandatory=$true)][string]$Message)
    if (-not $Condition) { throw $Message }
}

$path = Join-Path $PSScriptRoot 'Verify-ContactSurfaceNormals-FunctionFirst-BottleContacts.ps1'
Assert-True (Test-Path -LiteralPath $path -PathType Leaf) 'Four-pair bottle-contact-normal verifier is missing.'
$source = Get-Content -LiteralPath $path -Raw

foreach ($token in @(
    'BENCH_BOTTLE_D48_H180-2',
    'BENCH_CONVEYOR_L900_W82_H950-1',
    'FITCHECK_DRIVEN_WRAP_BELT_5x160x93_V25-1',
    'FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-1',
    'FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-2',
    'sw.classify_contact_pair',
    'sw.contact_surface_normals_pair',
    'contact_or_coincidence_within_tolerance',
    'face_normal_candidates_observed',
    "write_authority = 'NONE'",
    'model_mutation',
    'mechanical_acceptance_granted = $false'
)) {
    Assert-True ($source.Contains($token)) "Verifier source is missing required token '$token'."
}

foreach ($forbidden in @(
    'FITCHECK_INDEX_STOP_FINGER_54p25x6x20_V37-1',
    'FITCHECK_INDEX_STOP_FINGER_54p25x6x20_V37-2',
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

Assert-True ($source.Contains('Target component state changed during read-only four-pair normal observation.')) 'Verifier is missing target-state no-mutation guard.'
Assert-True ($source.Contains('Assembly file evidence changed during read-only four-pair normal observation.')) 'Verifier is missing assembly-file no-mutation guard.'
Assert-True ($source.Contains('Functional support/restraint semantics require separate axis binding')) 'Verifier is missing semantic interpretation boundary.'

Write-Host 'PASS: function-first four-pair contact-normal verifier source contract'
