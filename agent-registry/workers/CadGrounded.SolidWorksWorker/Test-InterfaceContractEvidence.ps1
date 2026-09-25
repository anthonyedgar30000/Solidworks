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
    "published_reference_manager_binding_state": "VERIFIED_FEATURE_MANAGER_TREE_BRANCH",
    "published_reference_manager": {
      "displayed_tree_text": "Published References",
      "feature_name": "Published References",
      "feature_type": "ConnectRefMgr",
      "tree_path": "0.8"
    },
    "published_reference_manager_binding_note": "Bounded FeatureManager-tree identity and direct parentage only.",
    "geometry_binding_state": "UNRESOLVED",
    "interpretation_note": "Frame and feature identity only; not mechanical acceptance.",
    "api": "IFeature.GetDefinition() -> ICoordinateSystemFeatureData -> Transform -> IMathTransform.ArrayData; IModelDoc2.FeatureManager -> IFeatureManager.GetFeatureTreeRootItem2(swFeatMgrPaneBottom) -> ITreeControlItem.Text/GetFirstChild/GetNext/Object -> IFeature.Name/GetTypeName2",
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
        "feature_type": "MagneticConnectRef",
        "tree_path": "0.8.2",
        "parent_tree_text": "Published References",
        "parent_feature_name": "Published References",
        "parent_feature_type": "ConnectRefMgr"
      },
      {
        "connector_name": "Connector1",
        "feature_type": "MagneticConnectRef",
        "tree_path": "0.8.1",
        "parent_tree_text": "Published References",
        "parent_feature_name": "Published References",
        "parent_feature_type": "ConnectRefMgr"
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
if ([string]$normalized.published_reference_manager.feature_type -cne 'ConnectRefMgr') {
    throw 'Published References manager tree binding did not normalize.'
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
    "published_reference_manager_binding_state": "VERIFIED_FEATURE_MANAGER_TREE_BRANCH",
    "published_reference_manager": {
      "displayed_tree_text": "Published References",
      "feature_name": "Published References",
      "feature_type": "ConnectRefMgr",
      "tree_path": "0.8"
    },
    "published_reference_manager_binding_note": "Bounded FeatureManager-tree identity and direct parentage only.",
    "geometry_binding_state": "UNRESOLVED",
    "interpretation_note": "Frame and feature identity only; not mechanical acceptance.",
    "api": "IFeature.GetDefinition() -> ICoordinateSystemFeatureData -> Transform -> IMathTransform.ArrayData; IModelDoc2.FeatureManager -> IFeatureManager.GetFeatureTreeRootItem2(swFeatMgrPaneBottom) -> ITreeControlItem.Text/GetFirstChild/GetNext/Object -> IFeature.Name/GetTypeName2",
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
        "feature_type": "MagneticConnectRef",
        "tree_path": "0.8.2",
        "parent_tree_text": "Published References",
        "parent_feature_name": "Published References",
        "parent_feature_type": "ConnectRefMgr"
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

$wrongParentBranch = ConvertFrom-InterfaceObservationJson -Json ($valid | ConvertTo-Json -Depth 20)
$wrongParentBranch.data.published_reference_features[0].parent_feature_type = 'WrongParentType'
$wrongParentRejected = $false
try {
    $null = Assert-InterfaceContractObservation `
        -Envelope $wrongParentBranch `
        -ExpectedCoordinateSystems @('PRODUCT_ENTRY_CS', 'PRODUCT_EXIT_CS') `
        -ExpectedConnectors @('Connector2', 'Connector1')
}
catch {
    if ($_.Exception.Message -notmatch 'parent IFeature.GetTypeName2\(\) must be ConnectRefMgr') {
        throw
    }
    $wrongParentRejected = $true
}
if (-not $wrongParentRejected) {
    throw 'Published Reference connector outside the exact manager branch was not rejected.'
}

Write-Output 'PASS: interface contract evidence normalization preserves strict authority and required-field boundaries.'
