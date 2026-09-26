[CmdletBinding()]
param(
    [string]$ExpectedDocumentTitle = 'IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE',
    [string]$ExpectedDocumentPath = 'C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE.SLDASM',
    [string]$ExpectedConfiguration = 'V43_WRAP',
    [switch]$SkipBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ExpectedWorkerVersion = '0.4.4'
$WorkerRoot = $PSScriptRoot
. (Join-Path $WorkerRoot 'FileEvidence.ps1')
. (Join-Path $WorkerRoot 'ComponentStateEvidence.ps1')
. (Join-Path $WorkerRoot 'JsonFileEvidence.ps1')

$WorkerExe = Join-Path $WorkerRoot 'bin\Release\net8.0-windows\win-x64\CadGrounded.SolidWorksWorker.exe'
$OutputRoot = Join-Path $WorkerRoot 'verification-output\classify-contact-at-transform-v43'
$Bottle = 'BENCH_BOTTLE_D48_H180-2'
$Roller = 'FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-1'
$TargetComponents = @($Bottle, $Roller)

$ExpectedBottleRotation = @(0.0,1.0,0.0,-1.0,0.0,0.0,0.0,0.0,1.0)
$ExpectedBottleTranslation = @(-153.42061528267112,-214.0,950.0)
$ExpectedRollerRotation = @(1.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,1.0)
$ExpectedRollerTranslation = @(-169.41764267046375,-249.56817558934128,995.0)

function Invoke-WorkerJson {
    param([Parameter(Mandatory=$true)][string[]]$Arguments)

    $text = (& $WorkerExe @Arguments | Out-String).Trim()
    $exitCode = $LASTEXITCODE
    if ([string]::IsNullOrWhiteSpace($text)) {
        throw "Worker command returned no JSON. ExitCode=$exitCode Arguments=$($Arguments -join ' ')"
    }

    $envelope = $text | ConvertFrom-Json
    if (-not [bool]$envelope.ok) {
        throw "Worker returned ok=false. ExitCode=$exitCode Command=$($envelope.command_id) ErrorType=$($envelope.error.type) Error=$($envelope.error.message)"
    }
    if ($exitCode -ne 0) {
        throw "Worker returned ok=true with nonzero exit code. ExitCode=$exitCode"
    }
    return $envelope
}

function Invoke-WorkerRequest {
    param([Parameter(Mandatory=$true)]$Request)

    $requestJson = $Request | ConvertTo-Json -Depth 20 -Compress
    $text = ($requestJson | & $WorkerExe execute-json | Out-String).Trim()
    $exitCode = $LASTEXITCODE
    if ([string]::IsNullOrWhiteSpace($text)) {
        throw "Worker execute-json returned no JSON. ExitCode=$exitCode"
    }

    $envelope = $text | ConvertFrom-Json
    if (-not [bool]$envelope.ok) {
        throw "Worker returned ok=false. ExitCode=$exitCode Command=$($envelope.command_id) ErrorType=$($envelope.error.type) Error=$($envelope.error.message)"
    }
    if ($exitCode -ne 0) {
        throw "Worker returned ok=true with nonzero exit code. ExitCode=$exitCode"
    }
    return $envelope
}

function Assert-ExpectedStatus {
    param([Parameter(Mandatory=$true)]$Envelope)

    if ([string]$Envelope.command_id -cne 'sw.status') { throw "Expected sw.status, got '$($Envelope.command_id)'." }
    if ([string]$Envelope.data.worker_version -cne $ExpectedWorkerVersion) {
        throw "Worker version mismatch. Expected='$ExpectedWorkerVersion' Actual='$($Envelope.data.worker_version)'."
    }
    if ([string]$Envelope.data.write_authority -cne 'NONE') { throw 'Worker write_authority is not NONE.' }
    if ([string]$Envelope.data.document.title -cne $ExpectedDocumentTitle) { throw 'Active document title mismatch.' }
    if (-not [string]::Equals([string]$Envelope.data.document.path,$ExpectedDocumentPath,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Active document path mismatch.'
    }
    if ([string]$Envelope.data.document.active_configuration -cne $ExpectedConfiguration) {
        throw "Active configuration mismatch. Expected='$ExpectedConfiguration' Actual='$($Envelope.data.document.active_configuration)'."
    }
    if ($null -eq $Envelope.data.solidworks_process_id) { throw 'sw.status omitted solidworks_process_id.' }
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

function Get-ExactComponent {
    param(
        [Parameter(Mandatory=$true)]$ComponentsEnvelope,
        [Parameter(Mandatory=$true)][string]$Name
    )
    $matches = @($ComponentsEnvelope.data.components | Where-Object { [string]$_.name2 -ceq $Name })
    if ($matches.Count -ne 1) { throw "Exact component must resolve uniquely. name='$Name' matches=$($matches.Count)." }
    return $matches[0]
}

function Assert-VectorNear {
    param(
        [Parameter(Mandatory=$true)]$Actual,
        [Parameter(Mandatory=$true)][double[]]$Expected,
        [Parameter(Mandatory=$true)][double]$Tolerance,
        [Parameter(Mandatory=$true)][string]$Label
    )
    $a = @($Actual)
    if ($a.Count -ne $Expected.Count) { throw "$Label length mismatch." }
    for ($i=0; $i -lt $Expected.Count; $i++) {
        if ([Math]::Abs([double]$a[$i] - $Expected[$i]) -gt $Tolerance) {
            throw "$Label mismatch at index $i. Expected=$($Expected[$i]) Actual=$($a[$i])."
        }
    }
}

function Assert-ContactEnvelopeBase {
    param([Parameter(Mandatory=$true)]$Envelope)

    if ([string]$Envelope.command_id -cne 'sw.classify_contact_pair_at_transform') { throw 'Unexpected command id.' }
    if ([string]$Envelope.source_classification -cne 'verified_from_solidworks_api') { throw 'Unexpected source classification.' }
    if ([string]$Envelope.data.component_a.name2 -cne $Bottle -or [string]$Envelope.data.component_b.name2 -cne $Roller) {
        throw 'Contact-at-transform query returned the wrong exact component pair.'
    }
    if ($Envelope.data.model_mutation -ne $false -or [string]$Envelope.data.write_authority -cne 'NONE') {
        throw 'Contact-at-transform query violated no-mutation/write-authority contract.'
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
    throw "Worker version command mismatch. Actual='$versionText'."
}

$statusBefore = Invoke-WorkerJson -Arguments @('status')
Assert-ExpectedStatus $statusBefore
$documentStateBefore = Get-DocumentState $statusBefore
$fileBefore = Get-FileEvidence -Path $ExpectedDocumentPath
$componentsBefore = Invoke-WorkerJson -Arguments @('components','--all')
$targetStateBefore = Get-TargetState -ComponentsEnvelope $componentsBefore -TargetComponents $TargetComponents

$bottleRow = Get-ExactComponent -ComponentsEnvelope $componentsBefore -Name $Bottle
$rollerRow = Get-ExactComponent -ComponentsEnvelope $componentsBefore -Name $Roller
Assert-VectorNear -Actual $bottleRow.rotation9 -Expected $ExpectedBottleRotation -Tolerance 1e-12 -Label 'Bottle rotation'
Assert-VectorNear -Actual $bottleRow.translation_mm -Expected $ExpectedBottleTranslation -Tolerance 1e-9 -Label 'Bottle translation'
Assert-VectorNear -Actual $rollerRow.rotation9 -Expected $ExpectedRollerRotation -Tolerance 1e-12 -Label 'Roller rotation'
Assert-VectorNear -Actual $rollerRow.translation_mm -Expected $ExpectedRollerTranslation -Tolerance 1e-9 -Label 'Roller translation'

$bottleX = [Convert]::ToDouble($bottleRow.translation_mm[0], [Globalization.CultureInfo]::InvariantCulture)
$bottleY = [Convert]::ToDouble($bottleRow.translation_mm[1], [Globalization.CultureInfo]::InvariantCulture)
$rollerX = [Convert]::ToDouble($rollerRow.translation_mm[0], [Globalization.CultureInfo]::InvariantCulture)
$rollerY = [Convert]::ToDouble($rollerRow.translation_mm[1], [Globalization.CultureInfo]::InvariantCulture)
$rollerZ = [Convert]::ToDouble($rollerRow.translation_mm[2], [Globalization.CultureInfo]::InvariantCulture)

$dx = [double]($rollerX - $bottleX)
$dy = [double]($rollerY - $bottleY)
$radialDistance = [double][Math]::Sqrt(($dx * $dx) + ($dy * $dy))
if ([Math]::Abs($radialDistance - 39.0) -gt 1e-9) {
    throw "Expected current bottle/roller center separation 39 mm; observed $radialDistance mm."
}

$ux = [double]($dx / $radialDistance)
$uy = [double]($dy / $radialDistance)

$outwardX = [double]($rollerX + $ux)
$outwardY = [double]($rollerY + $uy)
$inwardX = [double]($rollerX - $ux)
$inwardY = [double]($rollerY - $uy)

$currentRollerTranslation = [double[]]@($rollerX, $rollerY, $rollerZ)
$outwardTranslation = [double[]]@($outwardX, $outwardY, $rollerZ)
$inwardTranslation = [double[]]@($inwardX, $inwardY, $rollerZ)

$commonPayload = [ordered]@{
    document_title_exact = $ExpectedDocumentTitle
    document_path_exact = $ExpectedDocumentPath
    active_configuration_exact = $ExpectedConfiguration
    a_name_exact = $Bottle
    b_name_exact = $Roller
}

$baseline = Invoke-WorkerRequest -Request @{
    command_id = 'sw.classify_contact_pair_at_transform'
    payload = $commonPayload
}
Assert-ContactEnvelopeBase $baseline
if ([string]$baseline.data.classification -cne 'contact_or_coincidence_within_tolerance') {
    throw "Baseline classification mismatch. Actual='$($baseline.data.classification)'."
}
if ($null -eq $baseline.data.minimum_distance_mm -or [Math]::Abs([double]$baseline.data.minimum_distance_mm) -gt 0.001) {
    throw "Baseline minimum distance is not within the 0.001 mm contact tolerance. Actual='$($baseline.data.minimum_distance_mm)'."
}
if ([Math]::Abs([double]$baseline.data.intersection_volume_mm3) -gt 0.001) {
    throw "Baseline unexpectedly intersects. volume_mm3='$($baseline.data.intersection_volume_mm3)'."
}

$outwardPayload = [ordered]@{}
foreach ($key in $commonPayload.Keys) { $outwardPayload[$key] = $commonPayload[$key] }
$outwardPayload['b_candidate_transform'] = [ordered]@{
    rotation9 = @($rollerRow.rotation9 | ForEach-Object { [double]$_ })
    translation_mm = $outwardTranslation
}
$outward = Invoke-WorkerRequest -Request @{
    command_id = 'sw.classify_contact_pair_at_transform'
    payload = $outwardPayload
}
Assert-ContactEnvelopeBase $outward
if ([string]$outward.data.classification -cne 'noninterfering_contact_or_clearance_unresolved') {
    throw "Outward hypothetical classification mismatch. Actual='$($outward.data.classification)'."
}
if ($null -ne $outward.data.minimum_distance_mm) {
    throw "Outward hypothetical minimum distance must remain unresolved; actual='$($outward.data.minimum_distance_mm)'."
}
if ([Math]::Abs([double]$outward.data.intersection_volume_mm3) -gt 0.001) {
    throw "Outward hypothetical pose unexpectedly intersects. volume_mm3='$($outward.data.intersection_volume_mm3)'."
}
if ([string]$outward.data.api_distance -cne 'unresolved_for_hypothetical_nonintersecting_temporary_bodies') {
    throw "Outward hypothetical distance provenance mismatch. Actual='$($outward.data.api_distance)'."
}

$inwardPayload = [ordered]@{}
foreach ($key in $commonPayload.Keys) { $inwardPayload[$key] = $commonPayload[$key] }
$inwardPayload['b_candidate_transform'] = [ordered]@{
    rotation9 = @($rollerRow.rotation9 | ForEach-Object { [double]$_ })
    translation_mm = $inwardTranslation
}
$inward = Invoke-WorkerRequest -Request @{
    command_id = 'sw.classify_contact_pair_at_transform'
    payload = $inwardPayload
}
Assert-ContactEnvelopeBase $inward
if ([string]$inward.data.classification -cne 'physical_interference') {
    throw "Inward hypothetical classification mismatch. Actual='$($inward.data.classification)'."
}
if ($null -eq $inward.data.minimum_distance_mm -or [Math]::Abs([double]$inward.data.minimum_distance_mm) -gt 1e-12) {
    throw "Inward hypothetical minimum distance should be zero. Actual='$($inward.data.minimum_distance_mm)'."
}
$expectedInwardVolume = 530.263410890774
if ([Math]::Abs([double]$inward.data.intersection_volume_mm3 - $expectedInwardVolume) -gt 0.001) {
    throw "Inward B-rep intersection volume mismatch. Expected='$expectedInwardVolume' Actual='$($inward.data.intersection_volume_mm3)'."
}

$componentsAfter = Invoke-WorkerJson -Arguments @('components','--all')
$targetStateAfter = Get-TargetState -ComponentsEnvelope $componentsAfter -TargetComponents $TargetComponents
$statusAfter = Invoke-WorkerJson -Arguments @('status')
Assert-ExpectedStatus $statusAfter
$documentStateAfter = Get-DocumentState $statusAfter
$fileAfter = Get-FileEvidence -Path $ExpectedDocumentPath

if (($targetStateBefore | ConvertTo-Json -Depth 20 -Compress) -cne ($targetStateAfter | ConvertTo-Json -Depth 20 -Compress)) {
    throw 'Target component transform/state evidence changed during hypothetical evaluations.'
}
if (($documentStateBefore | ConvertTo-Json -Depth 10 -Compress) -cne ($documentStateAfter | ConvertTo-Json -Depth 10 -Compress)) {
    throw 'SOLIDWORKS process identity, active document identity, configuration, or dirty/save state changed during hypothetical evaluations.'
}
if ($fileBefore.sha256 -cne $fileAfter.sha256 -or
    $fileBefore.length -ne $fileAfter.length -or
    $fileBefore.last_write_time_utc -cne $fileAfter.last_write_time_utc) {
    throw 'Assembly file evidence changed during hypothetical evaluations.'
}

$verification = [ordered]@{
    schema_version = 1
    test = 'sw.classify_contact_pair_at_transform v43 radial +/-1 mm no-mutation regression'
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
    target_components = [ordered]@{
        bottle = $Bottle
        roller = $Roller
    }
    candidate_construction = [ordered]@{
        current_center_distance_mm = $radialDistance
        radial_unit_xy = @($ux,$uy)
        outward_translation_mm = $outwardTranslation
        inward_translation_mm = $inwardTranslation
        displacement_mm = 1.0
    }
    document_state_before = $documentStateBefore
    document_state_after = $documentStateAfter
    file_before = $fileBefore
    file_after = $fileAfter
    target_state_before = $targetStateBefore
    target_state_after = $targetStateAfter
    baseline_result = $baseline.data
    outward_result = $outward.data
    inward_result = $inward.data
    evidence_contract = [ordered]@{
        status = 'OBSERVATION_READY_ONLY'
        local_native_command = 'sw.classify_contact_pair_at_transform'
        establishes = @(
            'current-pose contact classification for this exact pair and snapshot',
            'positive hypothetical B-rep overlap establishes interference for the exact inward candidate',
            'hypothetical B-rep non-intersection does not get promoted to clearance without a validated temporary-body distance primitive',
            'pre/post SOLIDWORKS process/document, target-state, and assembly-file comparison'
        )
        does_not_establish = @(
            'general-purpose hypothetical clearance distance',
            'force, preload, stiffness, reaction capacity, or motion feasibility',
            'reachable-state envelope, timing, capture/release sequence, or mechanical acceptance'
        )
    }
    limitation = 'This PASS is a bounded capability regression for one exact v43 pair and two exact +/-1 mm radial candidate transforms. It does not establish a general collision-free motion path or mechanical acceptance.'
}

$verificationPath = Join-Path $OutputRoot 'verification-summary.json'
Write-JsonFileUtf8NoBom -Value $verification -LiteralPath $verificationPath -Depth 80

Write-Host 'PASS: sw.classify_contact_pair_at_transform v43 radial +/-1 mm regression'
Write-Host "Evidence: $verificationPath"
