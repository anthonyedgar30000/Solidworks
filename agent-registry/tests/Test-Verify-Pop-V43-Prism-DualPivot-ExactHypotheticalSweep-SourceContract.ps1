Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Verifier = Join-Path $RepoRoot 'workers\CadGrounded.SolidWorksWorker\Verify-Pop-V43-Prism-DualPivot-ExactHypotheticalSweep.ps1'

if (-not (Test-Path -LiteralPath $Verifier -PathType Leaf)) {
    throw "Verifier missing: $Verifier"
}

$source = Get-Content -LiteralPath $Verifier -Raw

$required = @(
    'TEST_POP_V43_PRISM_DUAL_PIVOT_EXACT_HYPOTHETICAL_SWEEP',
    'CANDIDATE_V43_PRISM_DUAL_INDEPENDENT_PIVOT_ARMS_V1',
    'sw.classify_contact_pair_at_transform',
    'FITCHECK_PRISM_ARM1_33p0824x10x5_V43-1',
    'FITCHECK_PRISM_ARM2_18p6806x10x5_V43-1',
    'FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-1',
    'FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-2',
    'FITCHECK_INDEX_STOP_FINGER_54p25x6x20_V37-1',
    'FITCHECK_INDEX_STOP_FINGER_54p25x6x20_V37-2',
    'noninterfering_contact_or_clearance_unresolved',
    'NO_BREP_INTERFERENCE_OBSERVED_AT_SAMPLED_STATES_CLEARANCE_UNRESOLVED',
    'model_mutation = $false',
    "write_authority = 'NONE'",
    'mechanical_acceptance_granted = $false',
    'Get-FileEvidence',
    'Get-TargetState',
    'SampleFractions = @(0.0, 0.25, 0.50, 0.75, 1.0)',
    '$sampleRows = [System.Collections.Generic.List[object]]::new()',
    '$pairRows = [System.Collections.Generic.List[object]]::new()',
    'pair_results = $pairRows.ToArray()',
    'physical_interferences = $interferenceRows.ToArray()',
    'indeterminate_results = $indeterminateRows.ToArray()',
    'samples = $sampleRows.ToArray()',
    'serve-stdio',
    'Get-WorkerServer',
    'Read-WorkerServerEnvelope',
    'Stop-WorkerServer'
)

foreach ($needle in $required) {
    if (-not $source.Contains($needle)) {
        throw "Verifier source contract missing required token: $needle"
    }
}

$prohibitedPatterns = @(
    'sw_set_transform',
    'sw\.set_transform',
    '\.Transform2\s*=',
    'SetTransformAndSolve',
    'AddComponent',
    'InsertComponent',
    'AddMate',
    'DeleteSelection',
    'EditRebuild',
    'Save3\s*\(',
    'SaveAs\s*\(',
    'SaveDoc',
    'SaveSilent',
    'New-Object\\s+System\\.Collections\\.Generic\\.List\\[object\\]'
)

foreach ($pattern in $prohibitedPatterns) {
    if ($source -match $pattern) {
        throw "Verifier source contains prohibited CAD-mutation primitive/pattern: $pattern"
    }
}

$tokens = $null
$errors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile(
    $Verifier,
    [ref]$tokens,
    [ref]$errors
)
if (@($errors).Count -ne 0) {
    $text = @($errors | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
    throw ("PowerShell parser errors:" + [Environment]::NewLine + $text)
}

Write-Host 'PASS: v43 PRISM dual-pivot exact hypothetical sweep source contract'
