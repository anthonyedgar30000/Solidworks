[CmdletBinding()]
param(
    [string]$ExpectedDocumentTitle = 'IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE',
    [string]$ExpectedDocumentPath = 'C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE.SLDASM',
    [string]$ExpectedConfiguration = 'V43_WRAP',
    [switch]$SkipBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ExpectedWorkerVersion = '0.4.2'
$WorkerRoot = $PSScriptRoot
. (Join-Path $WorkerRoot 'FileEvidence.ps1')
. (Join-Path $WorkerRoot 'ComponentStateEvidence.ps1')
. (Join-Path $WorkerRoot 'JsonFileEvidence.ps1')

$WorkerExe = Join-Path $WorkerRoot 'bin\Release\net8.0-windows\win-x64\CadGrounded.SolidWorksWorker.exe'
$OutputRoot = Join-Path $WorkerRoot 'verification-output\classify-contact-v43-prism-reaction-base'
$ComponentA = 'FITCHECK_PRISM_LINK_15x10x25_V43-1'
$ComponentB = 'FITCHECK_PRISM_REACTION_BASE_70x120x20_V43-1'
$TargetComponents = @($ComponentA, $ComponentB)

function Invoke-WorkerJson {
    param([Parameter(Mandatory=$true)][string[]]$Arguments)

    $text = (& $WorkerExe @Arguments | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Worker command failed. ExitCode=$LASTEXITCODE Arguments=$($Arguments -join ' ')"
    }
    if ([string]::IsNullOrWhiteSpace($text)) {
        throw "Worker command returned no JSON. Arguments=$($Arguments -join ' ')"
    }

    $envelope = $text | ConvertFrom-Json
    if (-not [bool]$envelope.ok) {
        throw "Worker returned ok=false. Command=$($envelope.command_id) Error=$($envelope.error.message)"
    }
    return $envelope
}

function Invoke-WorkerRequest {
    param([Parameter(Mandatory=$true)]$Request)

    $requestJson = $Request | ConvertTo-Json -Depth 10 -Compress
    $text = ($requestJson | & $WorkerExe execute-json | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Worker execute-json failed. ExitCode=$LASTEXITCODE"
    }
    if ([string]::IsNullOrWhiteSpace($text)) {
        throw 'Worker execute-json returned no JSON.'
    }

    $envelope = $text | ConvertFrom-Json
    if (-not [bool]$envelope.ok) {
        throw "Worker returned ok=false. Command=$($envelope.command_id) Error=$($envelope.error.message)"
    }
    return $envelope
}

function Assert-ExpectedStatus {
    param([Parameter(Mandatory=$true)]$Envelope)

    if ([string]$Envelope.command_id -cne 'sw.status') {
        throw "Expected sw.status envelope, got '$($Envelope.command_id)'."
    }
    if ([string]$Envelope.data.worker_version -cne $ExpectedWorkerVersion) {
        throw "Worker version mismatch. Expected='$ExpectedWorkerVersion' Actual='$($Envelope.data.worker_version)'."
    }
    if ([string]$Envelope.data.write_authority -cne 'NONE') {
        throw "Worker write_authority is not NONE. Actual='$($Envelope.data.write_authority)'."
    }
    if ([string]$Envelope.data.document.title -cne $ExpectedDocumentTitle) {
        throw "Active document title mismatch. Expected='$ExpectedDocumentTitle' Actual='$($Envelope.data.document.title)'."
    }
    if (-not [string]::Equals([string]$Envelope.data.document.path, $ExpectedDocumentPath, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Active document path mismatch. Expected='$ExpectedDocumentPath' Actual='$($Envelope.data.document.path)'."
    }
    if ([string]$Envelope.data.document.active_configuration -cne $ExpectedConfiguration) {
        throw "Active configuration mismatch. Expected='$ExpectedConfiguration' Actual='$($Envelope.data.document.active_configuration)'."
    }
    if ($null -eq $Envelope.data.document.save_flag) {
        throw 'sw.status did not return the document save flag needed for the no-mutation comparison.'
    }
}

function Get-DocumentState {
    param([Parameter(Mandatory=$true)]$StatusEnvelope)

    return [ordered]@{
        title = [string]$StatusEnvelope.data.document.title
        path = [string]$StatusEnvelope.data.document.path
        type = [string]$StatusEnvelope.data.document.type
        active_configuration = [string]$StatusEnvelope.data.document.active_configuration
        save_flag = $StatusEnvelope.data.document.save_flag
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
$targetStateBefore = Get-TargetState -ComponentsEnvelope $componentsBefore -TargetComponents $TargetComponents

$contactEnvelope = Invoke-WorkerRequest -Request @{
    command_id = 'sw.classify_contact_pair'
    payload = @{
        a_name_exact = $ComponentA
        b_name_exact = $ComponentB
    }
}

if ([string]$contactEnvelope.command_id -cne 'sw.classify_contact_pair') {
    throw "Unexpected command id. Actual='$($contactEnvelope.command_id)'."
}
if ([string]$contactEnvelope.source_classification -cne 'verified_from_solidworks_api') {
    throw "Unexpected source classification. Actual='$($contactEnvelope.source_classification)'."
}
if ([string]$contactEnvelope.data.component_a.name2 -cne $ComponentA -or
    [string]$contactEnvelope.data.component_b.name2 -cne $ComponentB) {
    throw 'Contact query returned a component identity different from the exact requested pair.'
}
if ($contactEnvelope.data.model_mutation -ne $false -or
    [string]$contactEnvelope.data.write_authority -cne 'NONE') {
    throw 'Contact query did not satisfy the no-mutation / write-authority contract.'
}
if ($null -eq $contactEnvelope.data.minimum_distance_mm -or
    [string]::IsNullOrWhiteSpace([string]$contactEnvelope.data.classification)) {
    throw 'Contact query omitted required distance or classification evidence.'
}

$componentsAfter = Invoke-WorkerJson -Arguments @('components', '--all')
$targetStateAfter = Get-TargetState -ComponentsEnvelope $componentsAfter -TargetComponents $TargetComponents
$statusAfter = Invoke-WorkerJson -Arguments @('status')
Assert-ExpectedStatus $statusAfter
$documentStateAfter = Get-DocumentState -StatusEnvelope $statusAfter
$fileAfter = Get-FileEvidence -Path $ExpectedDocumentPath

if (($targetStateBefore | ConvertTo-Json -Depth 20 -Compress) -cne
    ($targetStateAfter | ConvertTo-Json -Depth 20 -Compress)) {
    throw 'Target component transform/state evidence changed during read-only contact query.'
}
if (($documentStateBefore | ConvertTo-Json -Depth 10 -Compress) -cne
    ($documentStateAfter | ConvertTo-Json -Depth 10 -Compress)) {
    throw 'Active document identity, configuration, or dirty/save state changed during read-only contact query.'
}
if ($fileBefore.sha256 -cne $fileAfter.sha256 -or
    $fileBefore.length -ne $fileAfter.length -or
    $fileBefore.last_write_time_utc -cne $fileAfter.last_write_time_utc) {
    throw 'Assembly file evidence changed during read-only contact query.'
}

$executedAtUtc = [DateTime]::UtcNow.ToString('o')
$verification = [ordered]@{
    schema_version = 1
    test = 'sw.classify_contact_pair v43 Prism link-to-reaction-base current-pose no-mutation verification'
    result = 'PASS'
    executed_at_utc = $executedAtUtc
    expected_document = [ordered]@{
        title = $ExpectedDocumentTitle
        path = $ExpectedDocumentPath
        expected_configuration = $ExpectedConfiguration
        configuration_binding = 'PREASSERTED_AND_OBSERVED'
    }
    worker_version = $ExpectedWorkerVersion
    write_authority = 'NONE'
    remote_queue_authorized = $false
    target_components = [ordered]@{
        a_name_exact = $ComponentA
        b_name_exact = $ComponentB
    }
    document_state_before = $documentStateBefore
    document_state_after = $documentStateAfter
    file_before = $fileBefore
    file_after = $fileAfter
    target_state_before = $targetStateBefore
    target_state_after = $targetStateAfter
    contact_result = $contactEnvelope.data
    evidence_contract = [ordered]@{
        status = 'OBSERVATION_READY_ONLY'
        local_native_command = 'sw.classify_contact_pair'
        establishes = @(
            'exact current-pose pair identity',
            'minimum distance and returned current-pose contact classification',
            'pre/post document, target-state, and assembly-file comparison'
        )
        does_not_establish = @(
            'mechanical linkage outside the exact pair',
            'physical closure owner',
            'stroke, preload, force, stiffness, or reaction capacity',
            'operating motion, reachable envelope, timing, capture, release, or mechanical acceptance'
        )
    }
    limitation = 'The PASS result binds only this exact current-pose pair. Positive clearance excludes contact for the pair at this pose; it does not establish global mechanism topology or mechanical function.'
}

$verificationPath = Join-Path $OutputRoot 'verification-summary.json'
Write-JsonFileUtf8NoBom -Value $verification -LiteralPath $verificationPath -Depth 60

Write-Host 'PASS: sw.classify_contact_pair v43 Prism link-to-reaction-base current-pose verification'
Write-Host "Evidence: $verificationPath"
