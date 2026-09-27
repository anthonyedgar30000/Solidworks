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
$OutputRoot = Join-Path $WorkerRoot 'verification-output\contact-surface-normal-v43-bottle-conveyor'
$Bottle = 'BENCH_BOTTLE_D48_H180-2'
$Conveyor = 'BENCH_CONVEYOR_L900_W82_H950-1'
$TargetComponents = @($Bottle, $Conveyor)

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
    $requestJson = $Request | ConvertTo-Json -Depth 20 -Compress
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

function Assert-UnitNormals {
    param(
        [Parameter(Mandatory=$true)]$Candidates,
        [Parameter(Mandatory=$true)][string]$Label
    )

    if (@($Candidates).Count -lt 1) { throw "$Label returned no face-normal candidates." }
    foreach ($row in @($Candidates)) {
        if ([string]$row.normal_state -eq 'normal_unresolved') { continue }
        $n = @($row.unit_normal_assembly)
        if ($n.Count -ne 3) { throw "$Label returned a non-3D normal." }
        $mag = [Math]::Sqrt(
            [double]$n[0] * [double]$n[0] +
            [double]$n[1] * [double]$n[1] +
            [double]$n[2] * [double]$n[2])
        if ([Math]::Abs($mag - 1.0) -gt 1e-6) { throw "$Label returned a non-unit normal magnitude=$mag." }
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

$contact = Invoke-WorkerRequest -Request @{
    command_id = 'sw.classify_contact_pair'
    payload = @{
        a_name_exact = $Bottle
        b_name_exact = $Conveyor
    }
}
if ([string]$contact.command_id -cne 'sw.classify_contact_pair') { throw 'Unexpected contact classifier command id.' }
if ([string]$contact.source_classification -cne 'verified_from_solidworks_api') { throw 'Unexpected contact classifier source classification.' }
if ([string]$contact.data.component_a.name2 -cne $Bottle -or [string]$contact.data.component_b.name2 -cne $Conveyor) { throw 'Contact classifier returned wrong exact pair.' }
if ($contact.data.model_mutation -ne $false -or [string]$contact.data.write_authority -cne 'NONE') { throw 'Contact classifier violated read-only boundary.' }
if ([string]$contact.data.classification -cne 'contact_or_coincidence_within_tolerance') {
    throw "Bottle-conveyor pair is not exact contact/coincidence at this pose. classification='$($contact.data.classification)'."
}
if ($null -eq $contact.data.intersection_volume_mm3 -or [Math]::Abs([double]$contact.data.intersection_volume_mm3) -gt 0.001) {
    throw "Bottle-conveyor pair has unresolved/non-zero intersection volume='$($contact.data.intersection_volume_mm3)'."
}

$normals = Invoke-WorkerRequest -Request @{
    command_id = 'sw.contact_surface_normals_pair'
    payload = @{
        document_title_exact = $ExpectedDocumentTitle
        document_path_exact = $ExpectedDocumentPath
        active_configuration_exact = $ExpectedConfiguration
        a_name_exact = $Bottle
        b_name_exact = $Conveyor
    }
}
if ([string]$normals.command_id -cne 'sw.contact_surface_normals_pair') { throw 'Unexpected surface-normal command id.' }
if ([string]$normals.source_classification -cne 'verified_from_solidworks_api') { throw 'Unexpected surface-normal source classification.' }
if ([string]$normals.data.component_a.name2 -cne $Bottle -or [string]$normals.data.component_b.name2 -cne $Conveyor) { throw 'Surface-normal query returned wrong exact pair.' }
if ($normals.data.model_mutation -ne $false -or [string]$normals.data.write_authority -cne 'NONE') { throw 'Surface-normal query violated read-only boundary.' }
if ([string]$normals.data.face_normal_state -cne 'face_normal_candidates_observed') {
    throw "Surface-normal face binding unresolved. state='$($normals.data.face_normal_state)'."
}
Assert-UnitNormals -Candidates $normals.data.face_candidates_a -Label 'Bottle'
Assert-UnitNormals -Candidates $normals.data.face_candidates_b -Label 'Conveyor'

$componentsAfter = Invoke-WorkerJson -Arguments @('components','--all')
$targetStateAfter = Get-TargetState -ComponentsEnvelope $componentsAfter -TargetComponents $TargetComponents
$statusAfter = Invoke-WorkerJson -Arguments @('status')
Assert-ExpectedStatus $statusAfter
$documentStateAfter = Get-DocumentState $statusAfter
$fileAfter = Get-FileEvidence -Path $ExpectedDocumentPath

if (($targetStateBefore | ConvertTo-Json -Depth 30 -Compress) -cne ($targetStateAfter | ConvertTo-Json -Depth 30 -Compress)) {
    throw 'Target component state changed during read-only bottle-conveyor observation.'
}
if (($documentStateBefore | ConvertTo-Json -Depth 10 -Compress) -cne ($documentStateAfter | ConvertTo-Json -Depth 10 -Compress)) {
    throw 'Document/process/configuration/save state changed during read-only bottle-conveyor observation.'
}
if ($fileBefore.sha256 -cne $fileAfter.sha256 -or $fileBefore.length -ne $fileAfter.length -or $fileBefore.last_write_time_utc -cne $fileAfter.last_write_time_utc) {
    throw 'Assembly file evidence changed during read-only bottle-conveyor observation.'
}

$verification = [ordered]@{
    schema_version = 1
    test = 'v43 Bottle2-to-conveyor contact surface-normal current-pose no-mutation verification'
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
    contact_classification = $contact.data
    contact_surface_normals = $normals.data
    evidence_contract = [ordered]@{
        status = 'OBSERVATION_READY_ONLY'
        establishes = @(
            'exact current-pose Bottle2-to-conveyor pair identity',
            'contact/coincidence classification with zero B-rep intersection volume at the recorded pose',
            'candidate face normals at the API closest/contact points in transformed temporary-body assembly coordinates',
            'pre/post document, target-state, and assembly-file no-mutation comparison'
        )
        does_not_establish = @(
            'that world +Z is the support/reaction direction',
            'that the observed contact is sufficient product support across any interval',
            'friction, force, preload, stiffness, pressure, or load capacity',
            'which mechanism family should be selected',
            'mechanical acceptance'
        )
    }
    limitation = 'PASS observes current-pose contact and local face-normal candidates only. Support semantics require a separately justified vertical/gravity-axis binding and engineering interpretation.'
}

$verificationPath = Join-Path $OutputRoot 'verification-summary.json'
Write-JsonFileUtf8NoBom -Value $verification -LiteralPath $verificationPath -Depth 80
Write-Host 'PASS: v43 Bottle2-to-conveyor contact surface-normal verification'
Write-Host "Evidence: $verificationPath"
