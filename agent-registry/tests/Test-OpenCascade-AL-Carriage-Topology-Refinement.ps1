Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$recordPath = Join-Path $root 'reasoning\runtime\opencascade-al-carriage-topology-refinement-evidence-20260927T0712Z.json'
$priorPath = Join-Path $root 'reasoning\runtime\opencascade-al-carriage-source-geometry-evidence-20260927T041237890Z.json'
$docPath = Join-Path $root 'docs\OPENCASCADE_STEP_PILOT_V1.md'

foreach ($path in @($recordPath,$priorPath,$docPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required topology-refinement contract file is missing: $path"
    }
}

$record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
$prior = Get-Content -LiteralPath $priorPath -Raw | ConvertFrom-Json
$doc = [System.IO.File]::ReadAllText($docPath)

function Assert-True {
    param([bool]$Condition,[string]$Message)
    if (-not $Condition) { throw $Message }
}

Assert-True ($record.schema_version -eq 1) 'Unexpected EvidenceRecord schema_version.'
Assert-True ($record.record_type -ceq 'evidence') 'record_type must remain evidence.'
Assert-True ($record.evidence_type -ceq 'deterministic_calculation') 'Topology refinement must remain deterministic_calculation evidence.'
Assert-True ($record.evidence_state -ceq 'MEASURED_CALCULATED') 'Topology refinement must remain MEASURED_CALCULATED.'
Assert-True ($record.source_authority -ceq 'DETERMINISTIC_CALCULATION') 'Topology refinement exceeds allowed source authority.'
Assert-True ($record.source_classification -ceq 'opencascade_step_inspection') 'Unexpected source classification.'
Assert-True ($record.geometry_state -ceq 'SOURCE_GEOMETRY') 'Topology refinement must remain SOURCE_GEOMETRY.'
Assert-True ($record.temporal_scope.coverage -ceq 'POINT_ONLY') 'Topology refinement may not claim interval coverage.'
Assert-True ($record.temporal_scope.validity_state -ceq 'UNKNOWN') 'Topology refinement source-geometry validity must remain UNKNOWN at admission.'
Assert-True ($record.mechanical_acceptance_granted -eq $false) 'Topology refinement must not grant mechanical acceptance.'
Assert-True ($record.ambiguity_bucket -ceq 'IDENTITY_AMBIGUOUS') 'Semantic identity ambiguity must remain explicit.'

$expectedBundle = 'dc9cb4cc01a30dfd90ea88997f877d671fdfede0eecb30910b0bf894a6062ac4'
$expectedStep = 'bfcd381045f4e115be81ea22a349dfeccc6453ae49a00acab25c547205b50c5b'
$expectedPilot = '482a95396829ed36317b7db965e4471cbd305ddf'
$expectedPriorId = 'opencascade.al-carriage.source-geometry.sha256-707f4147e8ca9572b8040fe9e5654576bcfa047681a703cb06a5cff3f3504886'

Assert-True ($record.provenance.sha256 -ceq $expectedBundle) 'Frozen bundle root SHA256 changed unexpectedly.'
Assert-True ($record.subject.identity_exact -ceq 'CAB 6130648_01 Carriage Schlitten AL') 'Unexpected exact subject identity.'
Assert-True ($record.subject.document_path_exact -ceq 'C:\ChatGPT\Solidworks\IXOR\6130648_01_Carriage_Schlitten_AL (2)\6130648_01_Carriage_Schlitten_AL.stp') 'Unexpected exact OEM STEP path.'
Assert-True (@($record.dependencies) -contains "evidence_id:$expectedPriorId") 'Prior deterministic EvidenceRecord dependency is missing.'
Assert-True (@($record.dependencies) -contains "github:commit/$expectedPilot") 'Pilot lineage dependency is missing.'
Assert-True (@($record.dependencies) -contains "oem-step:sha256-$expectedStep") 'OEM STEP hash dependency is missing.'
Assert-True (@($record.dependencies) -contains "bundle-root:sha256-$expectedBundle") 'Frozen bundle dependency is missing.'

Assert-True ($prior.evidence_id -ceq $expectedPriorId) 'Prior immutable EvidenceRecord identity changed.'

$feature = $record.payload.result.source_geometry.partial_cylindrical_feature
Assert-True ((@($feature.face_ids) -join ',') -ceq 'face:160,face:161') 'Expected face:160 + face:161 topology binding.'
Assert-True ([Math]::Abs([double]$feature.nominal_diameter_mm - 7.0) -lt 0.000001) 'Expected nominal 7 mm partial cylinder.'
Assert-True ([Math]::Abs([double]$feature.axial_extent_mm - 8.0) -lt 0.000001) 'Expected 8 mm axial extent.'
Assert-True ([Math]::Abs([double]$feature.sectional_cylindrical_coverage_deg - 258.492266) -lt 0.000001) 'Unexpected cylindrical coverage.'
Assert-True ([Math]::Abs([double]$feature.sectional_non_cylindrical_coverage_deg - 101.507734) -lt 0.000001) 'Unexpected non-cylindrical coverage.'
Assert-True ($feature.axis_center_contains_body -eq $false) 'Expected candidate-axis center to remain outside body material.'

$sampling = $record.payload.result.source_geometry.occupancy_sampling_r4_mm
Assert-True ($sampling.coarse.sample_count -eq 16) 'Expected 16 coarse occupancy observations.'
Assert-True ($sampling.refinement.sample_count -eq 16) 'Expected 16 corrected refinement observations.'
Assert-True ((@($sampling.coarse.void_samples_deg) -join ',') -ceq '67.5,90,247.5,270') 'Unexpected coarse void sample pattern.'
Assert-True ((@($sampling.refinement.void_samples_deg) -join ',') -ceq '50,55,60,65,230,235,240,245') 'Unexpected corrected refinement void samples.'
Assert-True ((@($sampling.refinement.material_samples_deg) -join ',') -ceq '95,100,105,110,275,280,285,290') 'Unexpected corrected refinement material samples.'

$reference = $record.payload.result.source_geometry.reference_axis
Assert-True ($reference.face_id -ceq 'face:3') 'Expected face:3 reference axis binding.'
Assert-True ([Math]::Abs([double]$reference.nominal_diameter_mm - 10.0) -lt 0.000001) 'Expected nominal 10 mm face:3 cylinder.'
Assert-True ([Math]::Abs([double]$reference.partial_feature_axis_spacing_mm - 77.0) -lt 0.000001) 'Expected 77 mm deterministic axis spacing.'

$negative = @{}
foreach ($item in @($record.payload.result.negative_evidence)) {
    $negative[[string]$item.hypothesis] = [string]$item.status
}
Assert-True ($negative['complete nominal 7 mm cylindrical bore'] -ceq 'DISPROVEN') 'Complete-bore hypothesis must remain disproven.'
Assert-True ($negative['blind nominal 7 mm bore'] -ceq 'DISPROVEN') 'Blind-bore hypothesis must remain disproven.'
Assert-True ($negative['external nominal 7 mm cylindrical boss'] -ceq 'DISPROVEN') 'External-boss hypothesis must remain disproven.'

$limits = @{}
foreach ($item in @($record.payload.result.semantic_limits)) {
    $limits[[string]$item.claim] = [string]$item.state
}
Assert-True ($limits['partial cylindrical feature is the roller-mount feature'] -ceq 'SUPPORTED_NOT_VERIFIED') 'Roller-mount semantic identity was improperly promoted.'
Assert-True ($limits['face:3 axis is the functional carriage pivot axis'] -ceq 'SUPPORTED_NOT_VERIFIED') 'Pivot semantic identity was improperly promoted.'

foreach ($requiredNonClaim in @(
    'not a SolidWorksObservation',
    'not live SOLIDWORKS state',
    'not independent verification of roller-mount semantic identity',
    'not independent verification of functional pivot semantic identity',
    'not mechanical acceptance'
)) {
    Assert-True (@($record.payload.result.explicit_non_claims) -contains $requiredNonClaim) "Missing explicit non-claim: $requiredNonClaim"
}

Assert-True ($doc.Contains('Post-pilot topology clarification')) 'Pilot documentation is missing the topology clarification.'
Assert-True ($doc.Contains('historical comparison labels, not current geometry semantics')) 'Pilot documentation does not preserve historical-label semantics.'
Assert-True ($doc.Contains('dc9cb4cc01a30dfd90ea88997f877d671fdfede0eecb30910b0bf894a6062ac4')) 'Pilot documentation is missing the frozen evidence bundle root.'

Write-Host 'PASS: Open CASCADE AL-carriage topology-refinement evidence contract'
