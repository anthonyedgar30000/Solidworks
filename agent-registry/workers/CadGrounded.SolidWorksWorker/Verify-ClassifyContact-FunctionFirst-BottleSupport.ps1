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
$OutputRoot = Join-Path $WorkerRoot 'verification-output\function-first-bottle-support-contact'

$Bottle = 'BENCH_BOTTLE_D48_H180-2'
$Pairs = @(
    [ordered]@{ a = $Bottle; b = 'BENCH_CONVEYOR_L900_W82_H950-1'; investigation_role_candidate = 'vertical_support_candidate' },
    [ordered]@{ a = $Bottle; b = 'FITCHECK_DRIVEN_WRAP_BELT_5x160x93_V25-1'; investigation_role_candidate = 'wrap_drive_contact_candidate' },
    [ordered]@{ a = $Bottle; b = 'FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-1'; investigation_role_candidate = 'lateral_support_candidate_1' },
    [ordered]@{ a = $Bottle; b = 'FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-2'; investigation_role_candidate = 'lateral_support_candidate_2' },
    [ordered]@{ a = $Bottle; b = 'FITCHECK_INDEX_STOP_FINGER_54p25x6x20_V37-1'; investigation_role_candidate = 'index_restraint_candidate_1' },
    [ordered]@{ a = $Bottle; b = 'FITCHECK_INDEX_STOP_FINGER_54p25x6x20_V37-2'; investigation_role_candidate = 'index_restraint_candidate_2' }
)
$TargetComponents = @($Pairs | ForEach-Object { $_.a; $_.b } | Select-Object -Unique)

function Invoke-WorkerJson {
    param([Parameter(Mandatory=$true)][string[]]$Arguments)
    $text = (& $WorkerExe @Arguments | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Worker command failed. ExitCode=$LASTEXITCODE Arguments=$($Arguments -join ' ')" }
    if ([string]::IsNullOrWhiteSpace($text)) { throw "Worker command returned no JSON. Arguments=$($Arguments -join ' ')" }
    $envelope = $text | ConvertFrom-Json
    if (-not [bool]$envelope.ok) { throw "Worker returned ok=false. Command=$($envelope.command_id) Error=$($envelope.error.message)" }
    return $envelope
}

function Invoke-WorkerRequest {
    param([Parameter(Mandatory=$true)]$Request)
    $requestJson = $Request | ConvertTo-Json -Depth 10 -Compress
    $text = ($requestJson | & $WorkerExe execute-json | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Worker execute-json failed. ExitCode=$LASTEXITCODE" }
    if ([string]::IsNullOrWhiteSpace($text)) { throw 'Worker execute-json returned no JSON.' }
    $envelope = $text | ConvertFrom-Json
    if (-not [bool]$envelope.ok) { throw "Worker returned ok=false. Command=$($envelope.command_id) Error=$($envelope.error.message)" }
    return $envelope
}

function Assert-ExpectedStatus {
    param([Parameter(Mandatory=$true)]$Envelope)
    if ([string]$Envelope.command_id -cne 'sw.status') { throw "Expected sw.status envelope, got '$($Envelope.command_id)'." }
    if ([string]$Envelope.data.worker_version -cne $ExpectedWorkerVersion) { throw "Worker version mismatch. Expected='$ExpectedWorkerVersion' Actual='$($Envelope.data.worker_version)'." }
    if ([string]$Envelope.data.write_authority -cne 'NONE') { throw "Worker write_authority is not NONE. Actual='$($Envelope.data.write_authority)'." }
    if ([string]$Envelope.data.document.title -cne $ExpectedDocumentTitle) { throw 'Active document title mismatch.' }
    if (-not [string]::Equals([string]$Envelope.data.document.path, $ExpectedDocumentPath, [StringComparison]::OrdinalIgnoreCase)) { throw 'Active document path mismatch.' }
    if ([string]$Envelope.data.document.active_configuration -cne $ExpectedConfiguration) { throw 'Active configuration mismatch.' }
    if ($null -eq $Envelope.data.document.save_flag) { throw 'sw.status did not return the document save flag needed for no-mutation comparison.' }
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
if (-not (Test-Path -LiteralPath $WorkerExe -PathType Leaf)) { throw "Worker executable not found after build: $WorkerExe" }

[void](New-Item -ItemType Directory -Force -Path $OutputRoot)

$versionText = (& $WorkerExe version | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $versionText -cne "CadGrounded.SolidWorksWorker $ExpectedWorkerVersion") { throw "Worker version command mismatch. Actual='$versionText'." }

$statusBefore = Invoke-WorkerJson -Arguments @('status')
Assert-ExpectedStatus $statusBefore
$documentStateBefore = Get-DocumentState -StatusEnvelope $statusBefore
$fileBefore = Get-FileEvidence -Path $ExpectedDocumentPath
$componentsBefore = Invoke-WorkerJson -Arguments @('components', '--all')
$targetStateBefore = Get-TargetState -ComponentsEnvelope $componentsBefore -TargetComponents $TargetComponents

$pairResults = @()
foreach ($pair in $Pairs) {
    $contactEnvelope = Invoke-WorkerRequest -Request @{
        command_id = 'sw.classify_contact_pair'
        payload = @{
            a_name_exact = $pair.a
            b_name_exact = $pair.b
        }
    }
    if ([string]$contactEnvelope.command_id -cne 'sw.classify_contact_pair') { throw "Unexpected command id for pair '$($pair.a)' -> '$($pair.b)'." }
    if ([string]$contactEnvelope.source_classification -cne 'verified_from_solidworks_api') { throw "Unexpected source classification for pair '$($pair.a)' -> '$($pair.b)'." }
    if ([string]$contactEnvelope.data.component_a.name2 -cne $pair.a -or [string]$contactEnvelope.data.component_b.name2 -cne $pair.b) { throw 'Contact query returned the wrong exact component pair.' }
    if ($contactEnvelope.data.model_mutation -ne $false -or [string]$contactEnvelope.data.write_authority -cne 'NONE') { throw 'Contact query violated the no-mutation/write-authority boundary.' }
    if ($null -eq $contactEnvelope.data.minimum_distance_mm -or [string]::IsNullOrWhiteSpace([string]$contactEnvelope.data.classification)) { throw 'Contact query omitted distance/classification.' }

    $pairResults += [ordered]@{
        a_name_exact = $pair.a
        b_name_exact = $pair.b
        investigation_role_candidate = $pair.investigation_role_candidate
        result = $contactEnvelope.data
    }
}

$componentsAfter = Invoke-WorkerJson -Arguments @('components', '--all')
$targetStateAfter = Get-TargetState -ComponentsEnvelope $componentsAfter -TargetComponents $TargetComponents
$statusAfter = Invoke-WorkerJson -Arguments @('status')
Assert-ExpectedStatus $statusAfter
$documentStateAfter = Get-DocumentState -StatusEnvelope $statusAfter
$fileAfter = Get-FileEvidence -Path $ExpectedDocumentPath

if (($targetStateBefore | ConvertTo-Json -Depth 30 -Compress) -cne ($targetStateAfter | ConvertTo-Json -Depth 30 -Compress)) { throw 'Target component transform/state evidence changed during read-only bottle-support contact queries.' }
if (($documentStateBefore | ConvertTo-Json -Depth 10 -Compress) -cne ($documentStateAfter | ConvertTo-Json -Depth 10 -Compress)) { throw 'SOLIDWORKS process/document/configuration/save state changed during read-only bottle-support contact queries.' }
if ($fileBefore.sha256 -cne $fileAfter.sha256 -or $fileBefore.length -ne $fileAfter.length -or $fileBefore.last_write_time_utc -cne $fileAfter.last_write_time_utc) { throw 'Assembly file evidence changed during read-only bottle-support contact queries.' }

$verification = [ordered]@{
    schema_version = 1
    test = 'function-first bottle current-pose support/contact candidate classification'
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
    bottle_name_exact = $Bottle
    target_components = $TargetComponents
    document_state_before = $documentStateBefore
    document_state_after = $documentStateAfter
    file_before = $fileBefore
    file_after = $fileAfter
    target_state_before = $targetStateBefore
    target_state_after = $targetStateAfter
    pair_results = $pairResults
    evidence_contract = [ordered]@{
        status = 'OBSERVATION_READY_ONLY'
        local_native_command = 'sw.classify_contact_pair'
        establishes = @(
            'exact current-pose component-pair identities',
            'minimum distances and B-rep-backed current-pose classifications returned by the reviewed worker',
            'pre/post document, target-component-state, and assembly-file no-mutation comparison'
        )
        does_not_establish = @(
            'which observed pair is a required functional support or restraint',
            'surface normals or restraint rank',
            'support sufficiency against gravity or tipping',
            'friction, traction, preload, force, stiffness, or reaction capacity',
            'joint type, permitted DOF, or kinematic ownership',
            'interval-wide contact, capture, label transfer, release, or reachable-state clearance',
            'mechanical acceptance'
        )
    }
    limitation = 'PASS establishes only exact current-pose pair classifications. investigation_role_candidate values are routing labels, not engineering conclusions. Functional support/restraint roles remain unresolved until separately derived from required DOF plus suitable surface/normal and constraint evidence.'
    mechanical_acceptance_granted = $false
}

$verificationPath = Join-Path $OutputRoot 'verification-summary.json'
Write-JsonFileUtf8NoBom -Value $verification -LiteralPath $verificationPath -Depth 80
Write-Host 'PASS: function-first bottle support/contact current-pose verification'
