[CmdletBinding()]
param(
    [string]$ExpectedDocumentTitle = 'IXOR_Benchmark_v42_ASSET_INTERFACE_TEST_PORTABLE',
    [string]$ExpectedDocumentPath = 'C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v42_ASSET_INTERFACE_TEST_PORTABLE.SLDASM',
    [string]$PythonExe = 'python',
    [switch]$SkipBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# This verifier is local-only. It does not create an asset, insert a component,
# move/transform a component, create a mate, save, rebuild, or communicate with
# the Remote Queue. It fails closed on any observation or no-mutation mismatch.
$ExpectedWorkerVersion = '0.4.0'
$WorkerRoot = $PSScriptRoot
. (Join-Path $WorkerRoot 'FileEvidence.ps1')
. (Join-Path $WorkerRoot 'ComponentStateEvidence.ps1')
. (Join-Path $WorkerRoot 'InterfaceContractEvidence.ps1')
. (Join-Path $WorkerRoot 'InterfaceConnectorDiagnosticEvidence.ps1')
$WorkerExe = Join-Path $WorkerRoot 'bin\Release\net8.0-windows\win-x64\CadGrounded.SolidWorksWorker.exe'
$OutputRoot = Join-Path $WorkerRoot 'verification-output\interface-contract-v42'
$ReasoningRoot = [System.IO.Path]::GetFullPath((Join-Path $WorkerRoot '..\..\reasoning'))
$ContractPath = Join-Path $ReasoningRoot 'reference_cases\v42_product_flow.cad-interface-contract.v1.json'
$LiveVerifierPath = Join-Path $ReasoningRoot 'cad_interface_live_verifier.py'

$CoordinateSystems = @('PRODUCT_ENTRY_CS', 'PRODUCT_EXIT_CS')
$Connectors = @('Connector2', 'Connector1')

function Invoke-WorkerJson {
    param([Parameter(Mandatory=$true)][string[]]$Arguments)

    $text = (& $WorkerExe @Arguments | Out-String).Trim()
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "Worker command failed. ExitCode=$exitCode Arguments=$($Arguments -join ' ')"
    }
    if ([string]::IsNullOrWhiteSpace($text)) {
        throw "Worker command returned no JSON. Arguments=$($Arguments -join ' ')"
    }

    $envelope = $text | ConvertFrom-Json
    if (-not [bool](Get-RequiredObservationPropertyValue -Object $envelope -Name 'ok' -Context 'worker envelope')) {
        $error = Get-OptionalObservationPropertyValue -Object $envelope -Name 'error'
        $message = if ($null -ne $error) { Get-OptionalObservationPropertyValue -Object $error -Name 'message' } else { $null }
        throw "Worker returned ok=false. Command=$($envelope.command_id) Error=$message"
    }
    return $envelope
}

function Assert-ExpectedStatus {
    param([Parameter(Mandatory=$true)]$Envelope)

    if ([string](Get-RequiredObservationPropertyValue -Object $Envelope -Name 'command_id' -Context 'status envelope') -cne 'sw.status') {
        throw "Expected sw.status envelope."
    }
    if ([string](Get-RequiredObservationPropertyValue -Object $Envelope -Name 'source_classification' -Context 'status envelope') -cne 'verified_from_solidworks_api') {
        throw 'sw.status must be verified_from_solidworks_api.'
    }
    $data = Get-RequiredObservationPropertyValue -Object $Envelope -Name 'data' -Context 'status envelope'
    if ([string](Get-RequiredObservationPropertyValue -Object $data -Name 'worker_version' -Context 'status data') -cne $ExpectedWorkerVersion) {
        throw "Worker version mismatch. Expected='$ExpectedWorkerVersion'."
    }
    if ([string](Get-RequiredObservationPropertyValue -Object $data -Name 'write_authority' -Context 'status data') -cne 'NONE') {
        throw 'Worker write_authority is not NONE.'
    }
    $document = Get-RequiredObservationPropertyValue -Object $data -Name 'document' -Context 'status data'
    if ([string](Get-RequiredObservationPropertyValue -Object $document -Name 'title' -Context 'status document') -cne $ExpectedDocumentTitle) {
        throw "Active document title mismatch. Expected='$ExpectedDocumentTitle'."
    }
    $actualPath = [string](Get-RequiredObservationPropertyValue -Object $document -Name 'path' -Context 'status document')
    if (-not [string]::Equals($actualPath, $ExpectedDocumentPath, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Active document path mismatch. Expected='$ExpectedDocumentPath' Actual='$actualPath'."
    }
    foreach ($field in @('type', 'active_configuration', 'save_flag')) {
        $value = Get-RequiredObservationPropertyValue -Object $document -Name $field -Context 'status document'
        if ($field -in @('type', 'active_configuration') -and [string]::IsNullOrWhiteSpace([string]$value)) {
            throw "Required status document field is empty. Field='$field'."
        }
    }
}

function Get-DocumentState {
    param([Parameter(Mandatory=$true)]$StatusEnvelope)

    $data = Get-RequiredObservationPropertyValue -Object $StatusEnvelope -Name 'data' -Context 'status envelope'
    $document = Get-RequiredObservationPropertyValue -Object $data -Name 'document' -Context 'status data'
    return [ordered]@{
        title = [string](Get-RequiredObservationPropertyValue -Object $document -Name 'title' -Context 'status document')
        path = [string](Get-RequiredObservationPropertyValue -Object $document -Name 'path' -Context 'status document')
        type = [string](Get-RequiredObservationPropertyValue -Object $document -Name 'type' -Context 'status document')
        active_configuration = [string](Get-RequiredObservationPropertyValue -Object $document -Name 'active_configuration' -Context 'status document')
        save_flag = Get-RequiredObservationPropertyValue -Object $document -Name 'save_flag' -Context 'status document'
    }
}

function Get-WholeAssemblyComponentState {
    param([Parameter(Mandatory=$true)]$ComponentsEnvelope)

    $data = Get-RequiredObservationPropertyValue -Object $ComponentsEnvelope -Name 'data' -Context 'components envelope'
    $components = @(
        Get-RequiredObservationPropertyValue -Object $data -Name 'components' -Context 'components data'
    )
    $names = @()
    $seen = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($component in $components) {
        $name = [string](Get-RequiredObservationPropertyValue -Object $component -Name 'name2' -Context 'component inventory row')
        if (-not $seen.Add($name)) {
            throw "Component inventory contains duplicate exact Name2 '$name'; complete state comparison cannot proceed."
        }
        $names += $name
    }
    if ($names.Count -eq 0) {
        throw 'Component inventory is empty; complete state comparison cannot proceed.'
    }

    return [ordered]@{
        component_count = $names.Count
        components = Get-TargetState -ComponentsEnvelope $ComponentsEnvelope -TargetComponents $names
    }
}

if (-not $SkipBuild) {
    & (Join-Path $WorkerRoot 'build.cmd')
    if ($LASTEXITCODE -ne 0) {
        throw "build.cmd failed with exit code $LASTEXITCODE."
    }
}

if (-not (Test-Path -LiteralPath $WorkerExe -PathType Leaf)) {
    throw "Worker executable not found after build: $WorkerExe"
}
if (-not (Test-Path -LiteralPath $ContractPath -PathType Leaf) -or -not (Test-Path -LiteralPath $LiveVerifierPath -PathType Leaf)) {
    throw 'Required deterministic contract verifier source is unavailable.'
}

[void](New-Item -ItemType Directory -Force -Path $OutputRoot)

$versionText = (& $WorkerExe version | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $versionText -cne "CadGrounded.SolidWorksWorker $ExpectedWorkerVersion") {
    throw "Worker version command mismatch. Actual='$versionText'."
}

$statusBefore = Invoke-WorkerJson -Arguments @('status')
Assert-ExpectedStatus $statusBefore
$documentStateBefore = Get-DocumentState -StatusEnvelope $statusBefore
$fileBefore = Get-FileEvidence -Path $ExpectedDocumentPath
$componentsBefore = Invoke-WorkerJson -Arguments @('components', '--all')
$wholeAssemblyStateBefore = Get-WholeAssemblyComponentState -ComponentsEnvelope $componentsBefore

$connectorDiagnosticArguments = @('interface-connectors-diagnostic')
foreach ($name in $Connectors) {
    $connectorDiagnosticArguments += @('--connector', $name)
}
$connectorDiagnosticResult = Invoke-WorkerJson -Arguments $connectorDiagnosticArguments
$connectorDiagnosticRawPath = Join-Path $OutputRoot 'sw.diagnose_interface_connectors.raw.json'
$connectorDiagnosticResult | ConvertTo-Json -Depth 60 | Set-Content -LiteralPath $connectorDiagnosticRawPath -Encoding UTF8
$connectorDiagnosticState = Assert-InterfaceConnectorDiagnosticObservation `
    -Envelope $connectorDiagnosticResult `
    -ExpectedConnectors $Connectors

$componentsAfterConnectorDiagnostic = Invoke-WorkerJson -Arguments @('components', '--all')
$wholeAssemblyStateAfterConnectorDiagnostic = Get-WholeAssemblyComponentState -ComponentsEnvelope $componentsAfterConnectorDiagnostic
$statusAfterConnectorDiagnostic = Invoke-WorkerJson -Arguments @('status')
Assert-ExpectedStatus $statusAfterConnectorDiagnostic
$documentStateAfterConnectorDiagnostic = Get-DocumentState -StatusEnvelope $statusAfterConnectorDiagnostic
$fileAfterConnectorDiagnostic = Get-FileEvidence -Path $ExpectedDocumentPath

if (($wholeAssemblyStateBefore | ConvertTo-Json -Depth 40 -Compress) -cne ($wholeAssemblyStateAfterConnectorDiagnostic | ConvertTo-Json -Depth 40 -Compress)) {
    throw 'Complete component transform/state evidence changed during read-only connector diagnostic.'
}
if (($documentStateBefore | ConvertTo-Json -Depth 20 -Compress) -cne ($documentStateAfterConnectorDiagnostic | ConvertTo-Json -Depth 20 -Compress)) {
    throw 'Active document identity, configuration, or dirty/save state changed during read-only connector diagnostic.'
}
if ($fileBefore.sha256 -cne $fileAfterConnectorDiagnostic.sha256 -or
    $fileBefore.length -ne $fileAfterConnectorDiagnostic.length -or
    $fileBefore.last_write_time_utc -cne $fileAfterConnectorDiagnostic.last_write_time_utc) {
    throw 'Assembly file evidence changed during read-only connector diagnostic.'
}

$connectorDiagnosticSummary = [ordered]@{
    schema_version = 1
    test = 'sw.diagnose_interface_connectors v42 no-mutation verification'
    result = 'PASS'
    expected_document = [ordered]@{
        title = $ExpectedDocumentTitle
        path = $ExpectedDocumentPath
    }
    worker_version = $ExpectedWorkerVersion
    command_id = 'sw.diagnose_interface_connectors'
    write_authority = 'NONE'
    model_mutation = $false
    remote_queue_authorized = $false
    document_state_before = $documentStateBefore
    document_state_after = $documentStateAfterConnectorDiagnostic
    file_before = $fileBefore
    file_after = $fileAfterConnectorDiagnostic
    component_state_before = $wholeAssemblyStateBefore
    component_state_after = $wholeAssemblyStateAfterConnectorDiagnostic
    connector_diagnostic = $connectorDiagnosticState
    published_asset_coordinate_system_geometric_coincidence_state = 'UNRESOLVED'
    mechanical_acceptance_granted = $false
    evidence_contract = [ordered]@{
        establishes = @(
            'direct IModelDoc2.FeatureByName observation for exact requested connector names',
            'recursive feature-traversal observation for ConnectRefMgr and exact requested connector names',
            'pre/post document, complete component-state, and assembly-file comparison for the diagnostic'
        )
        does_not_establish = @(
            'Published Asset connector-to-coordinate-system geometric coincidence',
            'whether a direct-only result should change the interface-contract reader before separate review',
            'asset insertion, snap/mate behavior, physical contact, collision clearance, or interference absence',
            'degrees of freedom, support, force, preload, temporal operation, or mechanical acceptance'
        )
    }
}
$connectorDiagnosticSummaryPath = Join-Path $OutputRoot 'connector-diagnostic-summary.json'
$connectorDiagnosticSummary | ConvertTo-Json -Depth 80 | Set-Content -LiteralPath $connectorDiagnosticSummaryPath -Encoding UTF8

$interfaceArguments = @('interface-contract')
foreach ($name in $CoordinateSystems) {
    $interfaceArguments += @('--coordinate-system', $name)
}
foreach ($name in $Connectors) {
    $interfaceArguments += @('--connector', $name)
}
$interfaceResult = Invoke-WorkerJson -Arguments $interfaceArguments
$interfaceState = Assert-InterfaceContractObservation `
    -Envelope $interfaceResult `
    -ExpectedCoordinateSystems $CoordinateSystems `
    -ExpectedConnectors $Connectors

$rawObservationPath = Join-Path $OutputRoot 'sw.query_interface_contract.raw.json'
$interfaceResult | ConvertTo-Json -Depth 60 | Set-Content -LiteralPath $rawObservationPath -Encoding UTF8
$liveVerificationPath = Join-Path $OutputRoot 'live-verification.json'
& $PythonExe $LiveVerifierPath $ContractPath $rawObservationPath --out $liveVerificationPath --summary
if ($LASTEXITCODE -ne 0) {
    throw 'Deterministic live interface verifier rejected the native observation; no contract rebaseline was performed.'
}
$liveVerification = Get-Content -LiteralPath $liveVerificationPath -Raw | ConvertFrom-Json
if ([string](Get-RequiredInterfaceObservationPropertyValue -Object $liveVerification -Name 'live_verification_state' -Context 'deterministic live verification') -cne 'VERIFIED_CURRENT') {
    throw "Live interface verifier did not produce VERIFIED_CURRENT. Actual='$($liveVerification.live_verification_state)'."
}
if ((Get-RequiredInterfaceObservationPropertyValue -Object $liveVerification -Name 'mechanical_acceptance_granted' -Context 'deterministic live verification') -ne $false) {
    throw 'Live interface verifier must not grant mechanical acceptance.'
}

$componentsAfter = Invoke-WorkerJson -Arguments @('components', '--all')
$wholeAssemblyStateAfter = Get-WholeAssemblyComponentState -ComponentsEnvelope $componentsAfter
$statusAfter = Invoke-WorkerJson -Arguments @('status')
Assert-ExpectedStatus $statusAfter
$documentStateAfter = Get-DocumentState -StatusEnvelope $statusAfter
$fileAfter = Get-FileEvidence -Path $ExpectedDocumentPath

if (($wholeAssemblyStateBefore | ConvertTo-Json -Depth 40 -Compress) -cne ($wholeAssemblyStateAfter | ConvertTo-Json -Depth 40 -Compress)) {
    throw 'Complete component transform/state evidence changed during read-only interface-contract query.'
}
if (($documentStateBefore | ConvertTo-Json -Depth 20 -Compress) -cne ($documentStateAfter | ConvertTo-Json -Depth 20 -Compress)) {
    throw 'Active document identity, configuration, or dirty/save state changed during read-only interface-contract query.'
}
if ($fileBefore.sha256 -cne $fileAfter.sha256 -or
    $fileBefore.length -ne $fileAfter.length -or
    $fileBefore.last_write_time_utc -cne $fileAfter.last_write_time_utc) {
    throw 'Assembly file evidence changed during read-only interface-contract query.'
}

$verification = [ordered]@{
    schema_version = 1
    test = 'sw.query_interface_contract v42 no-mutation verification'
    result = 'PASS'
    expected_document = [ordered]@{
        title = $ExpectedDocumentTitle
        path = $ExpectedDocumentPath
    }
    worker_version = $ExpectedWorkerVersion
    command_id = 'sw.query_interface_contract'
    write_authority = 'NONE'
    model_mutation = $false
    remote_queue_authorized = $false
    coordinate_systems = $CoordinateSystems
    published_reference_connectors = $Connectors
    document_state_before = $documentStateBefore
    document_state_after = $documentStateAfter
    file_before = $fileBefore
    file_after = $fileAfter
    component_state_before = $wholeAssemblyStateBefore
    component_state_after = $wholeAssemblyStateAfter
    connector_diagnostic = $connectorDiagnosticState
    connector_diagnostic_artifact = $connectorDiagnosticSummaryPath
    interface_observation = $interfaceState
    deterministic_live_verification = $liveVerification
    published_asset_coordinate_system_geometric_coincidence_state = 'UNRESOLVED'
    mechanical_acceptance_granted = $false
    evidence_contract = [ordered]@{
        establishes = @(
            'exact current assembly/document/configuration binding',
            'exact named MagneticConnectRef feature identity/type',
            'exact named CoordSys feature identity/type and transform baseline comparison',
            'pre/post document, complete component-state, and assembly-file comparison'
        )
        does_not_establish = @(
            'Published Asset connector-to-coordinate-system geometric coincidence',
            'asset insertion, snap/mate behavior, physical contact, collision clearance, or interference absence',
            'degrees of freedom, support, force, preload, temporal operation, or mechanical acceptance'
        )
    }
}

$verificationPath = Join-Path $OutputRoot 'verification-summary.json'
$verification | ConvertTo-Json -Depth 80 | Set-Content -LiteralPath $verificationPath -Encoding UTF8

Write-Host 'PASS: sw.query_interface_contract v42 verification'
Write-Host "Evidence: $verificationPath"
