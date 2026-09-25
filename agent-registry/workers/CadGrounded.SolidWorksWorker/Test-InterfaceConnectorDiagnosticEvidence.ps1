[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'InterfaceContractEvidence.ps1')
. (Join-Path $PSScriptRoot 'InterfaceConnectorDiagnosticEvidence.ps1')

function ConvertFrom-InterfaceConnectorDiagnosticJson {
    param([Parameter(Mandatory=$true)][string]$Json)

    return $Json | ConvertFrom-Json
}

$validJson = @'
{
  "ok": true,
  "command_id": "sw.diagnose_interface_connectors",
  "source_classification": "verified_from_solidworks_api",
  "data": {
    "write_authority": "NONE",
    "model_mutation": false,
    "remote_queue_authorized": false,
    "result_scope": "EXACT_CONNECTOR_NAMES_PLUS_CONNECT_REF_MANAGER",
    "evidence": "verified_from_solidworks_api",
    "document": {
      "title": "FIXTURE.SLDASM",
      "path": "C:\\fixture\\FIXTURE.SLDASM",
      "type": "assembly",
      "active_configuration": "Default",
      "save_flag": 0
    },
    "direct_lookup": [
      {"requested_name": "Connector2", "found": true, "feature_name": "Connector2", "feature_type": "MagneticConnectRef"},
      {"requested_name": "Connector1", "found": true, "feature_name": "Connector1", "feature_type": "MagneticConnectRef"}
    ],
    "traversal_observations": [
      {"feature_name": "ConnectRefMgr", "feature_type": "ConnectRefMgr", "tree_depth": 0, "is_top_level": true, "tree_path": "5"}
    ],
    "connector_diagnostics": [
      {"requested_name": "Connector2", "direct_lookup_state": "FOUND_EXPECTED_TYPE", "traversal_match_count": 0, "traversal_expected_type_match_count": 0, "classification": "DIRECT_LOOKUP_TRAVERSAL_PATH_DEFECT"},
      {"requested_name": "Connector1", "direct_lookup_state": "FOUND_EXPECTED_TYPE", "traversal_match_count": 0, "traversal_expected_type_match_count": 0, "classification": "DIRECT_LOOKUP_TRAVERSAL_PATH_DEFECT"}
    ],
    "diagnostic_state": "DIRECT_LOOKUP_TRAVERSAL_PATH_DEFECT"
  }
}
'@

$valid = ConvertFrom-InterfaceConnectorDiagnosticJson -Json $validJson
$normalized = Assert-InterfaceConnectorDiagnosticObservation `
    -Envelope $valid `
    -ExpectedConnectors @('Connector2', 'Connector1')

if ([string]$normalized.diagnostic_state -cne 'DIRECT_LOOKUP_TRAVERSAL_PATH_DEFECT') {
    throw 'Direct-lookup/traversal path defect state was not preserved.'
}
if ([string]$normalized.direct_lookup['Connector2'].feature_type -cne 'MagneticConnectRef') {
    throw 'Direct connector lookup type was not preserved.'
}
if ($normalized.traversal_observations.Count -ne 1 -or [string]$normalized.traversal_observations[0].feature_name -cne 'ConnectRefMgr') {
    throw 'Traversal anchor observation was not preserved.'
}

$missingTreeDepth = ConvertFrom-InterfaceConnectorDiagnosticJson -Json ($validJson.Replace('"tree_depth": 0, ', ''))
$missingRequiredRejected = $false
try {
    $null = Assert-InterfaceConnectorDiagnosticObservation `
        -Envelope $missingTreeDepth `
        -ExpectedConnectors @('Connector2', 'Connector1')
}
catch {
    if ($_.Exception.Message -notmatch 'Required interface observation field is absent') {
        throw
    }
    $missingRequiredRejected = $true
}
if (-not $missingRequiredRejected) {
    throw 'Traversal observation without tree_depth was not rejected.'
}

Write-Output 'PASS: interface connector diagnostic evidence normalization preserves direct/traversal and read-only boundaries.'
