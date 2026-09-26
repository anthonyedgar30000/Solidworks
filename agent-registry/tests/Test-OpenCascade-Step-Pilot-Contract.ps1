Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pilotPath = Join-Path $root 'sidecars\pilots\opencascade-al-carriage-pilot.v1.json'
$docPath = Join-Path $root 'docs\OPENCASCADE_STEP_PILOT_V1.md'
$scriptPath = Join-Path $root 'sidecars\opencascade\Prepare-OpenCascade-Step-Pilot-V1.ps1'

foreach ($path in @($pilotPath, $docPath, $scriptPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required Open CASCADE pilot file is missing: $path"
    }
}

$pilot = Get-Content -LiteralPath $pilotPath -Raw | ConvertFrom-Json

if ($pilot.pilot_id -cne 'opencascade-al-carriage-6130648-v1') { throw 'Unexpected pilot identity.' }
if ($pilot.state -cne 'NOT_EXECUTED') { throw 'Repository pilot fixture must not claim execution.' }
if ($pilot.mechanical_acceptance_granted -ne $false) { throw 'Pilot fixture must not grant mechanical acceptance.' }
if ($pilot.input.sha256_expected -cne 'bfcd381045f4e115be81ea22a349dfeccc6453ae49a00acab25c547205b50c5b') { throw 'Pilot input hash changed unexpectedly.' }
if ($pilot.tool.package -cne 'cad-mcp-server' -or $pilot.tool.package_version -cne '0.6.1') { throw 'Pilot tool package/version is not pinned as expected.' }
if ($pilot.result_admission.evidence_type -cne 'deterministic_calculation') { throw 'Pilot result must enter as deterministic_calculation evidence.' }
if ($pilot.result_admission.evidence_state -cne 'MEASURED_CALCULATED') { throw 'Pilot result must remain MEASURED_CALCULATED.' }
if ($pilot.result_admission.source_authority -cne 'DETERMINISTIC_CALCULATION') { throw 'Pilot result exceeds allowed source authority.' }
if ($pilot.result_admission.mechanical_acceptance_granted -ne $false) { throw 'Pilot result admission must not grant mechanical acceptance.' }

foreach ($target in @($pilot.historical_comparison_targets)) {
    if ($target.comparison_only -ne $true) { throw "Historical target $($target.claim_id) must remain comparison-only." }
}

$scriptText = [System.IO.File]::ReadAllText($scriptPath)
foreach ($required in @(
    'Get-FileHash -LiteralPath $StepPath -Algorithm SHA256',
    '$nodeMajor -lt 24',
    'launch_performed = $false',
    'install_performed = $false',
    'mechanical_acceptance_granted = $false',
    'No package was installed or launched.'
)) {
    if (-not $scriptText.Contains($required)) { throw "Pilot preflight script is missing required invariant: $required" }
}

$forbiddenPatterns = @(
    '(?im)^\s*&?\s*npx\s+-y\s+cad-mcp-server@',
    '(?im)\bnpm\s+install\b',
    '(?im)\bStart-Process\b',
    '(?im)\bInvoke-WebRequest\b',
    '(?im)\bSet-Content\s+.*\.stp',
    '(?im)\bRemove-Item\s+.*\.stp'
)
foreach ($pattern in $forbiddenPatterns) {
    if ([regex]::IsMatch($scriptText, $pattern)) { throw "Pilot preflight script contains forbidden execution/mutation pattern: $pattern" }
}

$docText = [System.IO.File]::ReadAllText($docPath)
foreach ($required in @(
    'historical comparison targets',
    'The Open CASCADE result must be recorded independently even if it disagrees.',
    'does **not** install or launch the MCP server',
    'The result is **not** a `SolidWorksObservation`.'
)) {
    if (-not $docText.Contains($required)) { throw "Pilot documentation is missing required epistemic boundary: $required" }
}

Write-Host 'PASS: Open CASCADE AL-carriage pilot source contract'
