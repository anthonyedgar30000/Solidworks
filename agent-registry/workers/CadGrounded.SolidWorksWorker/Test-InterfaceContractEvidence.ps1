[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'InterfaceContractEvidence.ps1')

$ExpectedCoordinateSystemTransformSource = 'IFeature.GetDefinition() -> ICoordinateSystemFeatureData -> Transform -> IMathTransform.ArrayData'

function ConvertFrom-InterfaceObservationJson {
    param([Parameter(Mandatory=$true)][string]$Json)

    return $Json | ConvertFrom-Json
}

$valid = ConvertFrom-InterfaceObservationJson -Json @'
{
  "ok": true,
  "command_id": "sw.query_interface_contract",
  "source_classification": "verified_from_solidworks_api",
  "data": {
    "write_authority": "NONE",
    "model_mutation": false,
    "result_scope": "EXACT_NAMED_FEATURES_ONLY",
    "evidence": "verified_from_solidworks_api",
    "document": {
      "title": "FIXTURE.SLDASM",
      "path": "C:\\fixture\\FIXTURE.SLDASM",
      "type": "assembly",
      "active_configuration": "Default",
      "save_flag": 0
    },
    "coordinate_systems": [
      {
        "feature_name": "PRODUCT_ENTRY_CS",
        "feature_type": "CoordSys",
        "transform16": [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0],
        "origin_mm": [0, 0, 0],
        "transform_source": "IFeature.GetDefinition() -> ICoordinateSystemFeatureData -> Transform -> IMathTransform.ArrayData"
      },
      {
        "feature_name": "PRODUCT_EXIT_CS",
        "feature_type": "CoordSys",
        "transform16": [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0.9, 0, 1, 0, 0, 0],
        "origin_mm": [0, 900, 0],
        "transform_source": "IFeature.GetDefinition() -> ICoordinateSystemFeatureData -> Transform -> IMathTransform.ArrayData"
      }
    ],
    "published_reference_features": [
      {
        "connector_name": "Connector2",
        "feature_type": "MagneticConnectRef"
      },
      {
        "connector_name": "Connector1",
        "feature_type": "MagneticConnectRef"
      }
    ]
  }
}
'@

$normalized = Assert-InterfaceContractObservation `
    -Envelope $valid `
    -ExpectedCoordinateSystems @('PRODUCT_ENTRY_CS', 'PRODUCT_EXIT_CS') `
    -ExpectedConnectors @('Connector2', 'Connector1')

if ([string]$normalized.coordinate_systems['PRODUCT_EXIT_CS'].feature_type -cne 'CoordSys') {
    throw 'Expected coordinate-system normalization result was not returned.'
}
if ([string]$normalized.coordinate_systems['PRODUCT_ENTRY_CS'].transform_source -cne $ExpectedCoordinateSystemTransformSource) {
    throw 'Coordinate-system transform provenance did not preserve the required IFeature.GetDefinition() getter chain.'
}
if ([string]$normalized.published_reference_features['Connector1'].feature_type -cne 'MagneticConnectRef') {
    throw 'Expected connector normalization result was not returned.'
}

$missingTransform = ConvertFrom-InterfaceObservationJson -Json @'
{
  "ok": true,
  "command_id": "sw.query_interface_contract",
  "source_classification": "verified_from_solidworks_api",
  "data": {
    "write_authority": "NONE",
    "model_mutation": false,
    "result_scope": "EXACT_NAMED_FEATURES_ONLY",
    "evidence": "verified_from_solidworks_api",
    "document": {
      "title": "FIXTURE.SLDASM",
      "path": "C:\\fixture\\FIXTURE.SLDASM",
      "type": "assembly",
      "active_configuration": "Default",
      "save_flag": 0
    },
    "coordinate_systems": [
      {
        "feature_name": "PRODUCT_ENTRY_CS",
        "feature_type": "CoordSys",
        "origin_mm": [0, 0, 0],
        "transform_source": "IFeature.GetDefinition() -> ICoordinateSystemFeatureData -> Transform -> IMathTransform.ArrayData"
      }
    ],
    "published_reference_features": [
      {
        "connector_name": "Connector2",
        "feature_type": "MagneticConnectRef"
      }
    ]
  }
}
'@

$missingRequiredRejected = $false
try {
    $null = Assert-InterfaceContractObservation `
        -Envelope $missingTransform `
        -ExpectedCoordinateSystems @('PRODUCT_ENTRY_CS') `
        -ExpectedConnectors @('Connector2')
}
catch {
    if ($_.Exception.Message -notmatch 'Required interface observation field is absent') {
        throw
    }
    $missingRequiredRejected = $true
}
if (-not $missingRequiredRejected) {
    throw 'Missing required interface transform16 was not rejected.'
}

Write-Output 'PASS: interface contract evidence normalization preserves strict authority and required-field boundaries.'
