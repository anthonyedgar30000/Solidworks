[CmdletBinding()]
param(
    [string]$ExpectedDocumentTitle = 'IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE',
    [string]$ExpectedDocumentPath = 'C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE.SLDASM',
    [string]$ExpectedConfiguration = 'V43_WRAP',
    [switch]$SkipBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ExpectedWorkerVersion = '0.4.5'
$WorkerRoot = $PSScriptRoot
. (Join-Path $WorkerRoot 'FileEvidence.ps1')
. (Join-Path $WorkerRoot 'ComponentStateEvidence.ps1')
. (Join-Path $WorkerRoot 'JsonFileEvidence.ps1')
$WorkerExe = Join-Path $WorkerRoot 'bin\Release\net8.0-windows\win-x64\CadGrounded.SolidWorksWorker.exe'
$OutputRoot = Join-Path $WorkerRoot 'verification-output\query-mates-v43-prism-full-chain'

$TargetComponents = @(
    'FITCHECK_PRISM_CARRIER_SLIDER_15x80x60_V43-1',
    'FITCHECK_PRISM_LINK_15x10x25_V43-1',
    'FITCHECK_PRISM_LINK_15x10x25_V43-2',
    'FITCHECK_PRISM_ARM1_33p0824x10x5_V43-1',
    'FITCHECK_PRISM_ARM2_18p6806x10x5_V43-1',
    'FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-1',
    'FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-2'
)

function Invoke-WorkerJson {
    param([Parameter(Mandatory=$true)][string[]]$Arguments)
    $text = (& $WorkerExe @Arguments | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Worker command failed. ExitCode=$LASTEXITCODE Arguments=$($Arguments -join ' ')" }
    if ([string]::IsNullOrWhiteSpace($text)) { throw "Worker command returned no JSON. Arguments=$($Arguments -join ' ')" }
    $envelope = $text | ConvertFrom-Json
    if (-not [bool]$envelope.ok) { throw "Worker returned ok=false. Command=$($envelope.command_id) Error=$($envelope.error.message)" }
    return $envelope
}

function Assert-ExpectedStatus {
    param([Parameter(Mandatory=$true)]$Envelope)
    if ([string]$Envelope.command_id -cne 'sw.status') { throw 'Expected sw.status envelope.' }
    if ([string]$Envelope.data.worker_version -cne $ExpectedWorkerVersion) { throw 'Worker version mismatch.' }
    if ([string]$Envelope.data.write_authority -cne 'NONE') { throw 'Worker write_authority is not NONE.' }
    if ([string]$Envelope.data.document.title -cne $ExpectedDocumentTitle) { throw 'Active document title mismatch.' }
    if (-not [string]::Equals([string]$Envelope.data.document.path,$ExpectedDocumentPath,[StringComparison]::OrdinalIgnoreCase)) { throw 'Active document path mismatch.' }
    if ([string]$Envelope.data.document.active_configuration -cne $ExpectedConfiguration) { throw 'Active configuration mismatch.' }
    if ($null -eq $Envelope.data.document.save_flag) { throw 'sw.status omitted save_flag.' }
}

function Get-DocumentState {
    param([Parameter(Mandatory=$true)]$StatusEnvelope)
    return [ordered]@{
        solidworks_process_id = [string]$StatusEnvelope.data.solidworks_process_id
        title = [string]$StatusEnvelope.data.document.title
        path = [string]$StatusEnvelope.data.document.path
        type = [string]$StatusEnvelope.data.document.type
        active_configuration = [string]$StatusEnvelope.data.document.active_configuration
        save_flag = $StatusEnvelope.data.document.save_flag
    }
}

if (-not $SkipBuild) {
    & (Join-Path $WorkerRoot 'build.cmd')
    if ($LASTEXITCODE -ne 0) { throw "build.cmd failed with exit code $LASTEXITCODE." }
}
if (-not (Test-Path -LiteralPath $WorkerExe -PathType Leaf)) { throw "Worker executable not found: $WorkerExe" }

[void](New-Item -ItemType Directory -Force -Path $OutputRoot)
$versionText = (& $WorkerExe version | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $versionText -cne "CadGrounded.SolidWorksWorker $ExpectedWorkerVersion") {
    throw "Worker version mismatch. Actual='$versionText'."
}

$statusBefore = Invoke-WorkerJson -Arguments @('status')
Assert-ExpectedStatus $statusBefore
$documentStateBefore = Get-DocumentState $statusBefore
$fileBefore = Get-FileEvidence -Path $ExpectedDocumentPath
$componentsBefore = Invoke-WorkerJson -Arguments @('components','--all')
$targetStateBefore = Get-TargetState -ComponentsEnvelope $componentsBefore -TargetComponents $TargetComponents

$mateResults = [ordered]@{}
$coverage = [ordered]@{}
foreach ($name in $TargetComponents) {
    $result = Invoke-WorkerJson -Arguments @('mates','--component',$name)

    if ([string]$result.command_id -cne 'sw.query_mates') { throw "Unexpected command id for '$name'." }
    if ([string]$result.data.write_authority -cne 'NONE' -or $result.data.model_mutation -ne $false) {
        throw "Mate query violated no-write/no-mutation boundary for '$name'."
    }
    if ([string]$result.data.component.name2 -cne $name) { throw "Mate query returned wrong component for '$name'." }

    $mateRows = @($result.data.mates)
    $mateResults[$name] = $result.data
    $coverage[$name] = [ordered]@{
        fixed_component = $result.data.component.fixed_component
        parent_chain = @($result.data.component.parent_chain)
        parentage_errors = @($result.data.component.parentage_errors)
        referenced_configuration = $result.data.component.referenced_configuration
        incident_mate_count = $mateRows.Count
        mate_variation_values_observed = @(
            $mateRows | Where-Object {
                $null -ne $_.minimum_variation -or $null -ne $_.maximum_variation
            }
        ).Count
    }

    $safeName = $name -replace '[^A-Za-z0-9._-]','_'
    Write-JsonFileUtf8NoBom -Value $result -LiteralPath (Join-Path $OutputRoot "$safeName.mates.json") -Depth 60
}

$componentsAfter = Invoke-WorkerJson -Arguments @('components','--all')
$targetStateAfter = Get-TargetState -ComponentsEnvelope $componentsAfter -TargetComponents $TargetComponents
$statusAfter = Invoke-WorkerJson -Arguments @('status')
Assert-ExpectedStatus $statusAfter
$documentStateAfter = Get-DocumentState $statusAfter
$fileAfter = Get-FileEvidence -Path $ExpectedDocumentPath

if (($targetStateBefore | ConvertTo-Json -Depth 30 -Compress) -cne ($targetStateAfter | ConvertTo-Json -Depth 30 -Compress)) {
    throw 'Target component state changed during read-only mate queries.'
}
if (($documentStateBefore | ConvertTo-Json -Depth 10 -Compress) -cne ($documentStateAfter | ConvertTo-Json -Depth 10 -Compress)) {
    throw 'Document/process/configuration/save state changed during read-only mate queries.'
}
if ($fileBefore.sha256 -cne $fileAfter.sha256 -or $fileBefore.length -ne $fileAfter.length -or $fileBefore.last_write_time_utc -cne $fileAfter.last_write_time_utc) {
    throw 'Assembly file evidence changed during read-only mate queries.'
}

$verification = [ordered]@{
    schema_version = 1
    test = 'sw.query_mates v43 Prism full-chain kinematic-binding no-mutation verification'
    result = 'PASS'
    executed_at_utc = [DateTime]::UtcNow.ToString('o')
    expected_document = [ordered]@{
        title = $ExpectedDocumentTitle
        path = $ExpectedDocumentPath
        expected_configuration = $ExpectedConfiguration
        configuration_binding = 'PREASSERTED_AND_OBSERVED'
    }
    worker_version = $ExpectedWorkerVersion
    write_authority = 'NONE'
    remote_queue_authorized = $false
    target_components = $TargetComponents
    document_state_before = $documentStateBefore
    document_state_after = $documentStateAfter
    file_before = $fileBefore
    file_after = $fileAfter
    target_state_before = $targetStateBefore
    target_state_after = $targetStateAfter
    mate_results = $mateResults
    kinematic_observation_coverage = $coverage
    evidence_contract = [ordered]@{
        status = 'OBSERVATION_READY_ONLY'
        local_native_command = 'sw.query_mates'
        establishes = @(
            'exact full-chain target identity/state',
            'incident active-assembly mate definitions and suppression observations',
            'mate variation values when exposed',
            'explicit zero mate counts as negative evidence',
            'pre/post no-mutation comparison'
        )
        does_not_establish = @(
            'physical joint correctness',
            'DOF when constraints are incomplete or absent',
            'motion direction, stroke, endpoints, or actuator ownership',
            'preload, force, stiffness, contact pressure, or reaction capacity',
            'reachable motion, sequence, or mechanical acceptance'
        )
    }
    limitation = 'PASS binds only exact active-assembly mate observations for the seven named components at the recorded V43_WRAP point. If relevant mates are absent, kinematic state remains unresolved; contact adjacency is not promoted to a motion law.'
}

$verificationPath = Join-Path $OutputRoot 'verification-summary.json'
Write-JsonFileUtf8NoBom -Value $verification -LiteralPath $verificationPath -Depth 80
Write-Host 'PASS: sw.query_mates v43 Prism full-chain kinematic-binding verification'
Write-Host "Evidence: $verificationPath"
