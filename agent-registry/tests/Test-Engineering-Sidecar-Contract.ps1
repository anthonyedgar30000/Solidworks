Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$schemaPath = Join-Path $root 'schemas\engineering-sidecar-manifest.v1.schema.json'
$catalogPath = Join-Path $root 'sidecars\catalog.v1.json'
$docPath = Join-Path $root 'docs\ENGINEERING_SIDECARS_V1.md'

foreach ($path in @($schemaPath, $catalogPath, $docPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required sidecar contract file is missing: $path"
    }
}

$schema = Get-Content -LiteralPath $schemaPath -Raw | ConvertFrom-Json
$catalog = Get-Content -LiteralPath $catalogPath -Raw | ConvertFrom-Json

if ($schema.title -cne 'CADGrounded Engineering Sidecar Manifest v1') {
    throw 'Unexpected sidecar schema title.'
}

if ($catalog.schema_version -ne 1) {
    throw 'Unexpected sidecar catalog schema version.'
}

if ($catalog.catalog_state -cne 'RESEARCH_ONLY') {
    throw 'Sidecar catalog must remain research-only.'
}

if ($catalog.mechanical_acceptance_granted -ne $false) {
    throw 'Sidecar catalog must not grant mechanical acceptance.'
}

$requiredIds = @(
    'opencascade-step-inspector',
    'freecad-candidate-sandbox',
    'openmodelica-operating-state-simulator'
)

foreach ($id in $requiredIds) {
    $matches = @($catalog.sidecars | Where-Object { $_.sidecar_id -ceq $id })
    if ($matches.Count -ne 1) {
        throw "Expected exactly one sidecar manifest for $id."
    }
}

foreach ($sidecar in @($catalog.sidecars)) {
    if ($sidecar.authority.authority_ceiling -cne 'DETERMINISTIC_CALCULATION') {
        throw "Sidecar $($sidecar.sidecar_id) exceeds deterministic-calculation authority."
    }
    if ($sidecar.authority.may_observe_solidworks_live -ne $false) {
        throw "Sidecar $($sidecar.sidecar_id) must not observe SOLIDWORKS live state in v1."
    }
    if ($sidecar.authority.may_modify_solidworks -ne $false) {
        throw "Sidecar $($sidecar.sidecar_id) must not modify SOLIDWORKS."
    }
    if ($sidecar.authority.may_grant_mechanical_acceptance -ne $false) {
        throw "Sidecar $($sidecar.sidecar_id) must not grant mechanical acceptance."
    }
    if ($sidecar.allowed_evidence_type -cne 'deterministic_calculation') {
        throw "Sidecar $($sidecar.sidecar_id) must emit deterministic-calculation evidence only."
    }
    if ($sidecar.status -cne 'RESEARCH_CANDIDATE') {
        throw "Sidecar $($sidecar.sidecar_id) was promoted without a separately reviewed local verification."
    }

    foreach ($required in @('tool_identity','tool_version','input_artifact_hashes','method','recorded_at')) {
        if (@($sidecar.required_provenance) -cnotcontains $required) {
            throw "Sidecar $($sidecar.sidecar_id) is missing required provenance field $required."
        }
    }
}

$step = $catalog.sidecars | Where-Object { $_.sidecar_id -ceq 'opencascade-step-inspector' }
if ($step.mutation_scope -cne 'READ_ONLY_SOURCE') {
    throw 'Open CASCADE STEP inspector must remain read-only source scope.'
}

$freecad = $catalog.sidecars | Where-Object { $_.sidecar_id -ceq 'freecad-candidate-sandbox' }
foreach ($forbidden in @('execute_python','execute_python_async','macro_operations')) {
    if (@($freecad.forbidden_tool_families) -cnotcontains $forbidden) {
        throw "FreeCAD governed adapter must forbid $forbidden."
    }
}

$modelica = $catalog.sidecars | Where-Object { $_.sidecar_id -ceq 'openmodelica-operating-state-simulator' }
if ($modelica.mutation_scope -cne 'SIMULATION_MODEL_ONLY') {
    throw 'OpenModelica sidecar must be restricted to simulation-model mutation.'
}

$docText = [System.IO.File]::ReadAllText($docPath)
foreach ($literal in @(
    'MCP is transport. It is not authority.',
    'SOLIDWORKS remains the live geometry/state authority.',
    'No external software is installed by this branch.'
)) {
    if (-not $docText.Contains($literal)) {
        throw "Engineering sidecar document is missing required authority statement: $literal"
    }
}

Write-Host 'PASS: CADGrounded engineering sidecar v1 source contract'
