[CmdletBinding()]
param(
    [string]$PythonExe = 'python'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'JsonFileEvidence.ps1')

$ReasoningRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\reasoning'))
$ContractPath = Join-Path $ReasoningRoot 'reference_cases\v42_product_flow.cad-interface-contract.v1.json'
$LiveVerifierPath = Join-Path $ReasoningRoot 'cad_interface_live_verifier.py'

if (-not (Test-Path -LiteralPath $ContractPath -PathType Leaf) -or
    -not (Test-Path -LiteralPath $LiveVerifierPath -PathType Leaf)) {
    throw 'Required deterministic interface verifier fixtures are unavailable.'
}

$temporaryDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ("cadgrounded-json-file-evidence-" + [Guid]::NewGuid().ToString('N'))
[void][System.IO.Directory]::CreateDirectory($temporaryDirectory)

try {
    # This is a static evidence fixture only. It does not connect to
    # SOLIDWORKS and cannot establish any live CAD fact.
    $contract = Get-Content -LiteralPath $ContractPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $coordinateSystems = @(
        foreach ($interface in $contract.interfaces) {
            [ordered]@{
                feature_name = $interface.api_frame.feature_name
                feature_type = $interface.api_frame.feature_type
                transform16 = @($interface.api_frame.transform16)
                origin_mm = @($interface.api_frame.origin_mm)
                transform_source = 'IFeature.GetDefinition() -> ICoordinateSystemFeatureData -> Transform -> IMathTransform.ArrayData'
            }
        }
    )
    $connectors = @(
        foreach ($interface in $contract.interfaces) {
            $connectorName = [string]$interface.native_published_reference.connector_name
            $treePath = if ($connectorName -ceq 'Connector2') { '0.8.2' } else { '0.8.1' }
            [ordered]@{
                connector_name = $connectorName
                feature_type = $interface.native_published_reference.feature_type
                tree_path = $treePath
                parent_tree_text = 'Published References'
                parent_feature_name = 'Published References'
                parent_feature_type = 'ConnectRefMgr'
            }
        }
    )
    $observation = [ordered]@{
        ok = $true
        command_id = 'sw.query_interface_contract'
        source_classification = 'verified_from_solidworks_api'
        data = [ordered]@{
            document = [ordered]@{
                title = $contract.document.title_exact
                path = $contract.document.path_exact
                type = 'assembly'
                active_configuration = 'Default'
                save_flag = 0
            }
            request = [ordered]@{
                coordinate_system_feature_names = @($coordinateSystems | ForEach-Object { $_.feature_name })
                published_reference_connector_names = @($connectors | ForEach-Object { $_.connector_name })
            }
            coordinate_systems = $coordinateSystems
            published_reference_features = $connectors
            published_reference_manager = [ordered]@{
                displayed_tree_text = 'Published References'
                feature_name = 'Published References'
                feature_type = 'ConnectRefMgr'
                tree_path = '0.8'
            }
            result_scope = 'EXACT_NAMED_FEATURES_ONLY'
            published_reference_manager_binding_state = 'VERIFIED_FEATURE_MANAGER_TREE_BRANCH'
            published_reference_manager_binding_note = 'Bounded FeatureManager-tree identity and direct parentage only.'
            geometry_binding_state = 'UNRESOLVED'
            interpretation_note = 'Frame and feature identity only; not mechanical acceptance.'
            api = 'IFeature.GetDefinition() -> ICoordinateSystemFeatureData -> Transform -> IMathTransform.ArrayData; IModelDoc2.FeatureManager -> IFeatureManager.GetFeatureTreeRootItem2(swFeatMgrPaneBottom) -> ITreeControlItem.Text/GetFirstChild/GetNext/Object -> IFeature.Name/GetTypeName2'
            model_mutation = $false
            write_authority = 'NONE'
            evidence = 'verified_from_solidworks_api'
        }
    }

    $observationPath = Join-Path $temporaryDirectory 'sw.query_interface_contract.raw.json'
    Write-JsonFileUtf8NoBom -Value $observation -LiteralPath $observationPath -Depth 80

    $bytes = [System.IO.File]::ReadAllBytes($observationPath)
    if ($bytes.Length -lt 1 -or $bytes[0] -ne [byte]0x7B) {
        throw 'BOM-free JSON artifact must begin with the opening JSON object byte ({).'
    }
    if ($bytes.Length -ge 3 -and
        $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        throw 'JSON artifact unexpectedly begins with UTF-8 BOM bytes EF BB BF.'
    }

    $strictUtf8 = [System.Text.UTF8Encoding]::new($false, $true)
    $strictText = $strictUtf8.GetString($bytes)
    if (-not $strictText.StartsWith('{', [StringComparison]::Ordinal)) {
        throw 'Strict UTF-8 decoding did not retain an opening JSON object.'
    }
    $roundTrip = $strictText | ConvertFrom-Json
    if ([string]$roundTrip.command_id -cne 'sw.query_interface_contract' -or
        [string]$roundTrip.source_classification -cne 'verified_from_solidworks_api' -or
        [string]$roundTrip.data.evidence -cne 'verified_from_solidworks_api' -or
        [string]$roundTrip.data.geometry_binding_state -cne 'UNRESOLVED' -or
        [string]$roundTrip.data.write_authority -cne 'NONE' -or
        $roundTrip.data.model_mutation -ne $false -or
        [string]$roundTrip.data.published_reference_manager.feature_type -cne 'ConnectRefMgr') {
        throw 'JSON writer changed required command, authority, geometry, or FeatureManager evidence fields.'
    }

    $reportPath = Join-Path $temporaryDirectory 'live-verification.json'
    & $PythonExe $LiveVerifierPath $ContractPath $observationPath --out $reportPath --summary
    if ($LASTEXITCODE -ne 0) {
        throw 'Python live interface verifier rejected the BOM-free fixture under strict utf-8 input.'
    }
    $report = [System.IO.File]::ReadAllText($reportPath, $strictUtf8) | ConvertFrom-Json
    if ([string]$report.live_verification_state -cne 'VERIFIED_CURRENT' -or
        $report.mechanical_acceptance_granted -ne $false -or
        [string]$report.published_asset_coordinate_system_geometric_coincidence.'V42.PRODUCT_ENTRY' -cne 'UNRESOLVED' -or
        [string]$report.published_asset_coordinate_system_geometric_coincidence.'V42.PRODUCT_EXIT' -cne 'UNRESOLVED') {
        throw 'Python verification did not preserve the interface-only, unresolved-geometry boundary.'
    }
}
finally {
    if ([System.IO.Directory]::Exists($temporaryDirectory)) {
        [System.IO.Directory]::Delete($temporaryDirectory, $true)
    }
}

Write-Output 'PASS: JSON evidence artifacts are UTF-8 without BOM and round-trip through the strict Python verifier.'
