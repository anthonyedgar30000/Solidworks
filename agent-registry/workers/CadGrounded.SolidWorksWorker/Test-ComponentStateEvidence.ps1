[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'ComponentStateEvidence.ps1')

function ConvertFrom-ComponentObservationJson {
    param([Parameter(Mandatory=$true)][string]$Json)

    return $Json | ConvertFrom-Json
}

$topLevelEnvelope = ConvertFrom-ComponentObservationJson -Json @'
{
  "data": {
    "components": [
      {
        "name2": "TOP_LEVEL_CAPTURE_PART-1",
        "path": "C:\\fixture\\top-level.sldprt",
        "suppression_state": 3,
        "fixed_component": true,
        "is_top_level": true,
        "rotation9": [1, 0, 0, 0, 1, 0, 0, 0, 1],
        "translation_mm": [0, 0, 0],
        "transform_source": "Component2.Transform2"
      }
    ]
  }
}
'@

$topLevelState = Get-TargetState -ComponentsEnvelope $topLevelEnvelope -TargetComponents @('TOP_LEVEL_CAPTURE_PART-1')
$topLevelRow = $topLevelState['TOP_LEVEL_CAPTURE_PART-1']
if ($null -ne $topLevelRow['parent_name']) {
    throw "Top-level component parent_name should normalize to null when omitted. Actual='$($topLevelRow['parent_name'])'."
}
if ($topLevelRow['is_top_level'] -ne $true) {
    throw 'Top-level component did not preserve is_top_level=true.'
}

$nestedEnvelope = ConvertFrom-ComponentObservationJson -Json @'
{
  "data": {
    "components": [
      {
        "name2": "NESTED_CAPTURE_PART-1",
        "path": "C:\\fixture\\nested.sldprt",
        "suppression_state": 3,
        "fixed_component": false,
        "is_top_level": false,
        "parent_name": "CAPTURE_CARRIER-1",
        "rotation9": [1, 0, 0, 0, 1, 0, 0, 0, 1],
        "translation_mm": [1, 2, 3],
        "transform_source": "Component2.Transform2"
      }
    ]
  }
}
'@

$nestedState = Get-TargetState -ComponentsEnvelope $nestedEnvelope -TargetComponents @('NESTED_CAPTURE_PART-1')
$nestedRow = $nestedState['NESTED_CAPTURE_PART-1']
if ([string]$nestedRow['parent_name'] -cne 'CAPTURE_CARRIER-1') {
    throw "Nested component parent_name was not preserved. Actual='$($nestedRow['parent_name'])'."
}
if ($nestedRow['is_top_level'] -ne $false) {
    throw 'Nested component did not preserve is_top_level=false.'
}

$missingRequiredEnvelope = ConvertFrom-ComponentObservationJson -Json @'
{
  "data": {
    "components": [
      {
        "name2": "MISSING_REQUIRED_FIELD-1",
        "suppression_state": 3,
        "fixed_component": false,
        "is_top_level": true,
        "rotation9": [1, 0, 0, 0, 1, 0, 0, 0, 1],
        "translation_mm": [0, 0, 0],
        "transform_source": "Component2.Transform2"
      }
    ]
  }
}
'@

$requiredFieldRejected = $false
try {
    $null = Get-TargetState -ComponentsEnvelope $missingRequiredEnvelope -TargetComponents @('MISSING_REQUIRED_FIELD-1')
}
catch {
    if ($_.Exception.Message -notmatch 'Required component observation field is absent') {
        throw
    }
    $requiredFieldRejected = $true
}
if (-not $requiredFieldRejected) {
    throw 'Missing required component-state field was not rejected.'
}

Write-Output 'PASS: component state normalization preserves optional parent_name and rejects missing required fields.'
