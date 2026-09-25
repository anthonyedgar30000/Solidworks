[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'InterfaceContractEvidence.ps1')
. (Join-Path $PSScriptRoot 'FeatureManagerTreeDiagnosticEvidence.ps1')

function ConvertFrom-FeatureManagerTreeDiagnosticJson {
    param([Parameter(Mandatory=$true)][string]$Json)

    return $Json | ConvertFrom-Json
}

$validJson = @'
{
  "ok": true,
  "command_id": "sw.diagnose_feature_manager_tree",
  "source_classification": "verified_from_solidworks_api",
  "data": {
    "write_authority": "NONE",
    "model_mutation": false,
    "remote_queue_authorized": false,
    "result_scope": "EXACT_DISPLAYED_TREE_TEXTS_ONLY",
    "evidence": "verified_from_solidworks_api",
    "feature_manager_tree_root_available": true,
    "document": {
      "title": "FIXTURE.SLDASM",
      "path": "C:\\fixture\\FIXTURE.SLDASM",
      "type": "assembly",
      "active_configuration": "Default",
      "save_flag": 0
    },
    "request": {
      "displayed_tree_texts": ["Published References", "Ground Plane", "Connector1", "Connector2"],
      "feature_manager_pane": "swFeatMgrPaneBottom"
    },
    "tree_observations": [
      {"displayed_tree_text": "Published References", "tree_depth": 1, "tree_path": "0.2", "object_type": 0, "object_is_null": true},
      {"displayed_tree_text": "Ground Plane", "tree_depth": 1, "tree_path": "0.3", "object_type": 1, "object_is_null": false, "object_runtime_dotnet_type": "System.__ComObject", "object_is_com_object": true, "feature_name": "Ground Plane", "feature_type": "GroundPlane"},
      {"displayed_tree_text": "Connector1", "tree_depth": 2, "tree_path": "0.2.0", "object_type": 0, "object_is_null": false, "object_runtime_dotnet_type": "System.__ComObject", "object_is_com_object": true},
      {"displayed_tree_text": "Connector2", "tree_depth": 2, "tree_path": "0.2.1", "object_type": 1, "object_is_null": false, "object_runtime_dotnet_type": "System.__ComObject", "object_is_com_object": true, "feature_name": "Connector2", "feature_type": "MagneticConnectRef"}
    ],
    "tree_text_diagnostics": [
      {"requested_displayed_tree_text": "Published References", "exact_match_count": 1, "classification": "OBSERVED"},
      {"requested_displayed_tree_text": "Ground Plane", "exact_match_count": 1, "classification": "OBSERVED"},
      {"requested_displayed_tree_text": "Connector1", "exact_match_count": 1, "classification": "OBSERVED"},
      {"requested_displayed_tree_text": "Connector2", "exact_match_count": 1, "classification": "OBSERVED"}
    ],
    "diagnostic_state": "ALL_REQUESTED_TREE_TEXTS_OBSERVED"
  }
}
'@

$expectedTexts = @('Published References', 'Ground Plane', 'Connector1', 'Connector2')
$valid = ConvertFrom-FeatureManagerTreeDiagnosticJson -Json $validJson
$normalized = Assert-FeatureManagerTreeDiagnosticObservation -Envelope $valid -ExpectedTreeTexts $expectedTexts

if ([string]$normalized.diagnostic_state -cne 'ALL_REQUESTED_TREE_TEXTS_OBSERVED') {
    throw 'FeatureManager tree diagnostic state was not preserved.'
}
if ($normalized.tree_observations.Count -ne 4) {
    throw 'FeatureManager tree observations were not preserved.'
}
if ($normalized.tree_observations[0].object_is_null -ne $true) {
    throw 'A null FeatureManager tree Object observation was not preserved.'
}
if ([string]$normalized.tree_observations[3].feature_type -cne 'MagneticConnectRef') {
    throw 'Resolved IFeature type metadata was not preserved.'
}

$missingObjectNull = ConvertFrom-FeatureManagerTreeDiagnosticJson -Json ($validJson.Replace('"object_type": 0, "object_is_null": true', '"object_type": 0'))
$missingRequiredRejected = $false
try {
    $null = Assert-FeatureManagerTreeDiagnosticObservation -Envelope $missingObjectNull -ExpectedTreeTexts $expectedTexts
}
catch {
    if ($_.Exception.Message -notmatch 'Required interface observation field is absent') {
        throw
    }
    $missingRequiredRejected = $true
}
if (-not $missingRequiredRejected) {
    throw 'FeatureManager tree observation without object_is_null was not rejected.'
}

$outOfScope = ConvertFrom-FeatureManagerTreeDiagnosticJson -Json ($validJson.Replace('"Published References", "tree_depth"', '"Unrequested Tree Node", "tree_depth"'))
$outOfScopeRejected = $false
try {
    $null = Assert-FeatureManagerTreeDiagnosticObservation -Envelope $outOfScope -ExpectedTreeTexts $expectedTexts
}
catch {
    if ($_.Exception.Message -notmatch 'outside the exact requested-text scope') {
        throw
    }
    $outOfScopeRejected = $true
}
if (-not $outOfScopeRejected) {
    throw 'FeatureManager tree observation outside the requested-text scope was not rejected.'
}

Write-Output 'PASS: FeatureManager tree diagnostic evidence normalization preserves bounded read-only tree observations.'
