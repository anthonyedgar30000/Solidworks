[CmdletBinding()]
param(
    [string]$ExpectedDocumentTitle = 'IXOR_Benchmark_v42_ROLLER_GUIDE_HARDSTOP_FIT_CHECK_PORTABLE',
    [string]$ExpectedDocumentPath = 'C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v42_ROLLER_GUIDE_HARDSTOP_FIT_CHECK_PORTABLE.SLDASM',
    [switch]$SkipBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ExpectedWorkerVersion = '0.4.2'
$WorkerRoot = $PSScriptRoot
. (Join-Path $WorkerRoot 'FileEvidence.ps1')
. (Join-Path $WorkerRoot 'ComponentStateEvidence.ps1')
$WorkerExe = Join-Path $WorkerRoot 'bin\Release\net8.0-windows\win-x64\CadGrounded.SolidWorksWorker.exe'
$OutputRoot = Join-Path $WorkerRoot 'verification-output\query-mates-v42'

$TargetComponents = @(
    'FITCHECK_DRIVEN_WRAP_BELT_5x160x93_V25-1',
    'FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-1',
    'FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-2'
)

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
    if (-not [string]::Equals(
        [string]$Envelope.data.document.path,
        $ExpectedDocumentPath,
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Active document path mismatch. Expected='$ExpectedDocumentPath' Actual='$($Envelope.data.document.path)'."
    }
    if ($null -eq $Envelope.data.document.active_configuration) {
        throw 'sw.status did not return the active configuration needed for the no-mutation comparison.'
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

function Get-CaptureOwnerBindingCoverage {
    param([Parameter(Mandatory=$true)]$MateResults)

    $coverage = [ordered]@{}
    foreach ($name in $TargetComponents) {
        $data = $MateResults[$name]
        $mateRows = @($data.mates)
        $otherComponents = @(
            $mateRows |
                ForEach-Object { @($_.entities) } |
                ForEach-Object { $_ } |
                Where-Object {
                    -not [string]::IsNullOrWhiteSpace([string]$_.reference_component_name2) -and
                    [string]$_.reference_component_name2 -cne $name
                } |
                Select-Object -ExpandProperty reference_component_name2 -Unique
        )
        $coverage[$name] = [ordered]@{
            parent_chain = @($data.component.parent_chain)
            parentage_errors = @($data.component.parentage_errors)
            fixed_component = $data.component.fixed_component
            referenced_configuration = $data.component.referenced_configuration
            incident_mate_count = $mateRows.Count
            incident_component_names = $otherComponents
            mate_variation_values_observed = @(
                $mateRows | Where-Object {
                    $null -ne $_.minimum_variation -or $null -ne $_.maximum_variation
                }
            ).Count
        }
    }
    return $coverage
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
$componentsBefore = Invoke-WorkerJson -Arguments @('components','--all')
$targetStateBefore = Get-TargetState -ComponentsEnvelope $componentsBefore -TargetComponents $TargetComponents

$mateResults = [ordered]@{}
foreach ($name in $TargetComponents) {
    $result = Invoke-WorkerJson -Arguments @('mates','--component',$name)

    if ([string]$result.command_id -cne 'sw.query_mates') {
        throw "Unexpected command id for '$name': '$($result.command_id)'."
    }
    if ([string]$result.data.write_authority -cne 'NONE') {
        throw "sw.query_mates did not report write_authority NONE for '$name'."
    }
    if ($result.data.model_mutation -ne $false) {
        throw "sw.query_mates did not report model_mutation=false for '$name'."
    }
    if ([string]$result.data.component.name2 -cne $name) {
        throw "sw.query_mates returned wrong component. Expected='$name' Actual='$($result.data.component.name2)'."
    }
    if ($null -eq $result.data.component.parent_chain -or
        $null -eq $result.data.component.fixed_component -or
        $null -eq $result.data.component.referenced_configuration) {
        throw "sw.query_mates did not return the required parentage/component-state binding fields for '$name'."
    }

    $mateResults[$name] = $result.data
    $safeName = $name -replace '[^A-Za-z0-9._-]', '_'
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath (Join-Path $OutputRoot "$safeName.mates.json") -Encoding UTF8
}

$componentsAfter = Invoke-WorkerJson -Arguments @('components','--all')
$targetStateAfter = Get-TargetState -ComponentsEnvelope $componentsAfter -TargetComponents $TargetComponents
$statusAfter = Invoke-WorkerJson -Arguments @('status')
Assert-ExpectedStatus $statusAfter
$documentStateAfter = Get-DocumentState -StatusEnvelope $statusAfter
$fileAfter = Get-FileEvidence -Path $ExpectedDocumentPath

$beforeJson = $targetStateBefore | ConvertTo-Json -Depth 20 -Compress
$afterJson = $targetStateAfter | ConvertTo-Json -Depth 20 -Compress
if ($beforeJson -cne $afterJson) {
    throw 'Target component transform/state evidence changed during read-only mate queries.'
}

$documentBeforeJson = $documentStateBefore | ConvertTo-Json -Depth 10 -Compress
$documentAfterJson = $documentStateAfter | ConvertTo-Json -Depth 10 -Compress
if ($documentBeforeJson -cne $documentAfterJson) {
    throw 'Active document identity, configuration, or dirty/save state changed during read-only mate queries.'
}

if ($fileBefore.sha256 -cne $fileAfter.sha256 -or
    $fileBefore.length -ne $fileAfter.length -or
    $fileBefore.last_write_time_utc -cne $fileAfter.last_write_time_utc) {
    throw 'Assembly file evidence changed during read-only mate queries.'
}

$verification = [ordered]@{
    schema_version = 1
    test = 'sw.query_mates v42 no-mutation verification'
    result = 'PASS'
    expected_document = [ordered]@{
        title = $ExpectedDocumentTitle
        path = $ExpectedDocumentPath
    }
    worker_version = $ExpectedWorkerVersion
    write_authority = 'NONE'
    target_components = $TargetComponents
    remote_queue_authorized = $false
    document_state_before = $documentStateBefore
    document_state_after = $documentStateAfter
    file_before = $fileBefore
    file_after = $fileAfter
    target_state_before = $targetStateBefore
    target_state_after = $targetStateAfter
    mate_results = $mateResults
    capture_owner_binding_coverage = Get-CaptureOwnerBindingCoverage -MateResults $mateResults
    evidence_contract = [ordered]@{
        status = 'OBSERVATION_READY_ONLY'
        local_native_command = 'sw.query_mates'
        remote_queue_authorized = $false
        establishes = @(
            'exact target identity and parent chain',
            'incident active-assembly mate identities/types/suppression observation',
            'reported mate variation values when the API exposes them',
            'pre/post document, target-state, and assembly-file comparison'
        )
        does_not_establish = @(
            'physical closure owner',
            'spring preload, force, stiffness, or contact pressure',
            'operating motion, reachable envelope, or temporal sequence',
            'mechanical acceptance'
        )
    }
    limitation = 'PASS proves no observed active-document configuration/save-state, target transform/state, or assembly-file change during these queries. Mate and parentage data may narrow the capture-owner frontier but cannot by themselves prove physical closure, preload, contact force, operating motion, or mechanical acceptance.'
}

$verificationPath = Join-Path $OutputRoot 'verification-summary.json'
$verification | ConvertTo-Json -Depth 60 | Set-Content -LiteralPath $verificationPath -Encoding UTF8

Write-Host "PASS: sw.query_mates v42 verification"
Write-Host "Evidence: $verificationPath"
