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
$CandidateId = 'CANDIDATE_V43_PRISM_AS_PROJECT_PROPOSAL'
$VariantId = 'CANDIDATE_V43_PRISM_DUAL_INDEPENDENT_PIVOT_ARMS_V1'
$TestId = 'TEST_POP_V43_PRISM_DUAL_PIVOT_EXACT_HYPOTHETICAL_SWEEP'

$WorkerRoot = $PSScriptRoot
. (Join-Path $WorkerRoot 'FileEvidence.ps1')
. (Join-Path $WorkerRoot 'ComponentStateEvidence.ps1')
. (Join-Path $WorkerRoot 'JsonFileEvidence.ps1')

$WorkerExe = Join-Path $WorkerRoot 'bin\Release\net8.0-windows\win-x64\CadGrounded.SolidWorksWorker.exe'
$OutputRoot = Join-Path $WorkerRoot 'verification-output\pop-v43-prism-dual-pivot-exact-hypothetical-sweep'

$SampleFractions = @(0.0, 0.25, 0.50, 0.75, 1.0)

$Branch1 = [ordered]@{
    arm = 'FITCHECK_PRISM_ARM1_33p0824x10x5_V43-1'
    roller = 'FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-1'
    pivot_xy_mm = @(-202.5, -249.56817558934128)
    open_angle_deg = -75.86423677166873
}
$Branch2 = [ordered]@{
    arm = 'FITCHECK_PRISM_ARM2_18p6806x10x5_V43-1'
    roller = 'FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-2'
    pivot_xy_mm = @(-202.5, -189.56817558934128)
    open_angle_deg = 64.37359663899446
}

$MoverNames = @(
    $Branch1.arm,
    $Branch1.roller,
    $Branch2.arm,
    $Branch2.roller
)

$LabelFacetNames = 1..28 | ForEach-Object {
    "FITCHECK_REFERENCE_LABEL_FACET_0p2x5p0118x50_V35-$($_)"
}

$StaticObstacleNames = @(
    'BENCH_BOTTLE_D48_H180-1',
    'BENCH_BOTTLE_D48_H180-2',
    'BENCH_BOTTLE_D48_H180-3',
    'BENCH_BOTTLE_D48_H180-4',
    'BENCH_BOTTLE_D48_H180-5',
    'BENCH_CONVEYOR_L900_W82_H950-1',
    'FITCHECK_DRIVEN_WRAP_BELT_5x160x93_V25-1',
    'FITCHECK_INDEX_STOP_FINGER_54p25x6x20_V37-1',
    'FITCHECK_INDEX_STOP_FINGER_54p25x6x20_V37-2',
    'FITCHECK_PRISM_REACTION_BASE_70x120x20_V43-1',
    'FITCHECK_PRISM_GUIDE_RAIL_100x10x10_V43-1',
    'FITCHECK_PRISM_GUIDE_RAIL_100x10x10_V43-2',
    'FITCHECK_PRISM_ACTUATOR_ENVELOPE_45x35x35_V43-1',
    'FITCHECK_PRISM_CARRIER_SLIDER_15x80x60_V43-1',
    'FITCHECK_PRISM_LINK_15x10x25_V43-1',
    'FITCHECK_PRISM_LINK_15x10x25_V43-2',
    'SP100_6130656_NATIVE_PORTABLE_V17-1',
    'IXOR_6130800_NATIVE_PORTABLE_V17-1',
    '6130648_01_Carriage_Schlitten_AL_NATIVE_PORTABLE_V22-1',
    '6130649_01_Carriage_Schlitten_AR_NATIVE_PORTABLE_V20-1',
    '6130460_03_AR60_NATIVE_PORTABLE_V18-2'
) + $LabelFacetNames

$CrossBranchPairs = @(
    @($Branch1.arm, $Branch2.arm),
    @($Branch1.arm, $Branch2.roller),
    @($Branch1.roller, $Branch2.arm),
    @($Branch1.roller, $Branch2.roller)
)

$ExpectedCurrentTranslationsMm = @{
    'FITCHECK_PRISM_ARM1_33p0824x10x5_V43-1' = @(-185.95882133523187,-249.56817558934128,995.0)
    'FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-1' = @(-169.41764267046375,-249.56817558934128,995.0)
    'FITCHECK_PRISM_ARM2_18p6806x10x5_V43-1' = @(-193.15969871476827,-189.56817558934128,995.0)
    'FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-2' = @(-183.81939742953654,-189.56817558934128,995.0)
}

function Invoke-WorkerJson {
    param([Parameter(Mandatory=$true)][string[]]$Arguments)
    $text = (& $WorkerExe @Arguments | Out-String).Trim()
    $exitCode = $LASTEXITCODE
    if ([string]::IsNullOrWhiteSpace($text)) {
        throw "Worker returned no JSON. ExitCode=$exitCode Arguments=$($Arguments -join ' ')"
    }
    $envelope = $text | ConvertFrom-Json
    if (-not [bool]$envelope.ok) {
        throw "Worker returned ok=false. Command=$($envelope.command_id) ErrorType=$($envelope.error.type) Error=$($envelope.error.message)"
    }
    if ($exitCode -ne 0) {
        throw "Worker returned ok=true with nonzero exit code. ExitCode=$exitCode"
    }
    return $envelope
}

$script:WorkerServer = $null

function Get-WorkerServer {
    if ($null -ne $script:WorkerServer -and -not $script:WorkerServer.HasExited) {
        return $script:WorkerServer
    }

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $WorkerExe
    $psi.Arguments = 'serve-stdio'
    $psi.WorkingDirectory = $WorkerRoot
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    if (-not $process.Start()) {
        throw 'Failed to start persistent worker serve-stdio process.'
    }

    $script:WorkerServer = $process
    return $script:WorkerServer
}

function Stop-WorkerServer {
    if ($null -eq $script:WorkerServer) { return }
    try { $script:WorkerServer.StandardInput.Close() } catch {}
    try {
        if (-not $script:WorkerServer.WaitForExit(2000)) {
            $script:WorkerServer.Kill()
            [void]$script:WorkerServer.WaitForExit(2000)
        }
    } catch {}
    try { $script:WorkerServer.Dispose() } catch {}
    $script:WorkerServer = $null
}

function Invoke-WorkerRequest {
    param([Parameter(Mandatory=$true)]$Request)

    $requestJson = $Request | ConvertTo-Json -Depth 30 -Compress
    $process = Get-WorkerServer

    try {
        $process.StandardInput.WriteLine($requestJson)
        $process.StandardInput.Flush()
        $text = $process.StandardOutput.ReadLine()
    }
    catch {
        $stderr = ''
        try { $stderr = $process.StandardError.ReadToEnd() } catch {}
        throw "Persistent worker I/O failed. Error=$($_.Exception.Message) Stderr=$stderr"
    }

    if ([string]::IsNullOrWhiteSpace($text)) {
        $exit = $null
        $stderr = ''
        try {
            if ($process.HasExited) {
                $exit = $process.ExitCode
                $stderr = $process.StandardError.ReadToEnd()
            }
        } catch {}
        throw "Persistent worker returned no JSON. ExitCode=$exit Stderr=$stderr"
    }

    $envelope = $text | ConvertFrom-Json
    if (-not [bool]$envelope.ok) {
        throw "Worker returned ok=false. Command=$($envelope.command_id) ErrorType=$($envelope.error.type) Error=$($envelope.error.message)"
    }
    return $envelope
}

function Assert-ExpectedStatus {
    param([Parameter(Mandatory=$true)]$Envelope)
    if ([string]$Envelope.command_id -cne 'sw.status') { throw 'Expected sw.status envelope.' }
    if ([string]$Envelope.data.worker_version -cne $ExpectedWorkerVersion) { throw 'Worker version mismatch.' }
    if ([string]$Envelope.data.write_authority -cne 'NONE') { throw 'Worker write_authority is not NONE.' }
    if ([string]$Envelope.data.document.title -cne $ExpectedDocumentTitle) { throw 'Active document title mismatch.' }
    if (-not [string]::Equals([string]$Envelope.data.document.path,$ExpectedDocumentPath,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Active document path mismatch.'
    }
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

function Get-ExactComponent {
    param(
        [Parameter(Mandatory=$true)]$ComponentsEnvelope,
        [Parameter(Mandatory=$true)][string]$Name
    )
    $rows = @($ComponentsEnvelope.data.components | Where-Object { [string]$_.name2 -ceq $Name })
    if ($rows.Count -ne 1) {
        throw "Exact component identity must resolve uniquely. name='$Name' matches=$($rows.Count)"
    }
    return $rows[0]
}


function Get-OptionalJsonPropertyValue {
    param(
        [Parameter(Mandatory=$true)]$Object,
        [Parameter(Mandatory=$true)][string]$Name
    )

    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return $null
    }
    return $property.Value
}

function Assert-VectorNear {
    param(
        [Parameter(Mandatory=$true)]$Actual,
        [Parameter(Mandatory=$true)][double[]]$Expected,
        [double]$Tolerance = 1e-9,
        [string]$Label = 'vector'
    )
    $a = @($Actual)
    if ($a.Count -ne $Expected.Count) { throw "$Label length mismatch." }
    for ($i=0; $i -lt $Expected.Count; $i++) {
        if ([Math]::Abs([double]$a[$i] - $Expected[$i]) -gt $Tolerance) {
            throw "$Label mismatch at index $i. Expected=$($Expected[$i]) Actual=$($a[$i])."
        }
    }
}

function Multiply-Rotation3RowMajor {
    param(
        [Parameter(Mandatory=$true)][double[]]$A,
        [Parameter(Mandatory=$true)][double[]]$B
    )
    if ($A.Count -ne 9 -or $B.Count -ne 9) { throw 'Rotation matrices must have 9 entries.' }
    $result = [double[]]@(0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0)
    for ($row=0; $row -lt 3; $row++) {
        for ($col=0; $col -lt 3; $col++) {
            $sum = 0.0
            for ($inner=0; $inner -lt 3; $inner++) {
                $ia = [int](($row * 3) + $inner)
                $ib = [int](($inner * 3) + $col)
                $sum += [double]$A[$ia] * [double]$B[$ib]
            }
            $ic = [int](($row * 3) + $col)
            $result[$ic] = [double]$sum
        }
    }
    return ,$result
}

function Get-RotationZRowMajor {
    param([Parameter(Mandatory=$true)][double]$AngleDeg)
    $theta = $AngleDeg * [Math]::PI / 180.0
    $c = [Math]::Cos($theta)
    $s = [Math]::Sin($theta)
    # SOLIDWORKS MathTransform stores translation in the lower-left row,
    # so candidate transforms are treated here with row-vector composition.
    return [double[]]@(
        $c,  $s, 0.0,
        -$s, $c, 0.0,
        0.0, 0.0, 1.0
    )
}

function Get-RotatedCandidateTransform {
    param(
        [Parameter(Mandatory=$true)]$ComponentRow,
        [Parameter(Mandatory=$true)][double[]]$PivotXYMm,
        [Parameter(Mandatory=$true)][double]$AngleDeg
    )
    $currentRotation = [double[]]@($ComponentRow.rotation9 | ForEach-Object { [double]$_ })
    $currentTranslation = [double[]]@($ComponentRow.translation_mm | ForEach-Object { [double]$_ })
    $rz = Get-RotationZRowMajor -AngleDeg $AngleDeg
    $newRotation = Multiply-Rotation3RowMajor -A $currentRotation -B $rz

    $theta = $AngleDeg * [Math]::PI / 180.0
    $c = [Math]::Cos($theta)
    $s = [Math]::Sin($theta)
    $dx = $currentTranslation[0] - $PivotXYMm[0]
    $dy = $currentTranslation[1] - $PivotXYMm[1]

    $newX = $PivotXYMm[0] + ($dx * $c) - ($dy * $s)
    $newY = $PivotXYMm[1] + ($dx * $s) + ($dy * $c)

    return [ordered]@{
        rotation9 = @($newRotation)
        translation_mm = @($newX,$newY,$currentTranslation[2])
    }
}

function Get-MoverTransformMap {
    param(
        [Parameter(Mandatory=$true)]$ComponentsEnvelope,
        [Parameter(Mandatory=$true)][double]$Fraction
    )
    if ($Fraction -lt 0.0 -or $Fraction -gt 1.0) { throw "Fraction out of range: $Fraction" }
    $map = [ordered]@{}
    foreach ($branch in @($Branch1,$Branch2)) {
        $angle = [double]$branch.open_angle_deg * $Fraction
        foreach ($name in @([string]$branch.arm,[string]$branch.roller)) {
            $row = Get-ExactComponent -ComponentsEnvelope $ComponentsEnvelope -Name $name
            $map[$name] = Get-RotatedCandidateTransform -ComponentRow $row -PivotXYMm ([double[]]$branch.pivot_xy_mm) -AngleDeg $angle
        }
    }
    return $map
}

function Invoke-PairAtTransforms {
    param(
        [Parameter(Mandatory=$true)][string]$A,
        [Parameter(Mandatory=$true)][string]$B,
        $ATransform,
        $BTransform
    )
    $payload = [ordered]@{
        document_title_exact = $ExpectedDocumentTitle
        document_path_exact = $ExpectedDocumentPath
        active_configuration_exact = $ExpectedConfiguration
        a_name_exact = $A
        b_name_exact = $B
    }
    if ($null -ne $ATransform) { $payload['a_candidate_transform'] = $ATransform }
    if ($null -ne $BTransform) { $payload['b_candidate_transform'] = $BTransform }

    try {
        $env = Invoke-WorkerRequest -Request @{
            command_id = 'sw.classify_contact_pair_at_transform'
            payload = $payload
        }
    }
    catch {
        throw "Pair evaluation failed for '$A' <-> '$B'. $($_.Exception.Message)"
    }
    if ([string]$env.command_id -cne 'sw.classify_contact_pair_at_transform') { throw 'Unexpected command id.' }
    if ([string]$env.source_classification -cne 'verified_from_solidworks_api') { throw 'Unexpected source classification.' }
    if ($env.data.model_mutation -ne $false -or [string]$env.data.write_authority -cne 'NONE') {
        throw "No-mutation/write-authority violation for '$A' <-> '$B'."
    }
    return $env.data
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

$AllTrackedNames = @($MoverNames + $StaticObstacleNames | Sort-Object -Unique)
foreach ($name in $AllTrackedNames) {
    [void](Get-ExactComponent -ComponentsEnvelope $componentsBefore -Name $name)
}
foreach ($name in $MoverNames) {
    $row = Get-ExactComponent -ComponentsEnvelope $componentsBefore -Name $name
    Assert-VectorNear -Actual $row.translation_mm -Expected ([double[]]$ExpectedCurrentTranslationsMm[$name]) -Tolerance 1e-9 -Label "$name current translation"
}
$targetStateBefore = Get-TargetState -ComponentsEnvelope $componentsBefore -TargetComponents $AllTrackedNames

$sampleRows = New-Object System.Collections.Generic.List[object]
$interferenceRows = New-Object System.Collections.Generic.List[object]
$indeterminateRows = New-Object System.Collections.Generic.List[object]

foreach ($fraction in $SampleFractions) {
    $transformMap = Get-MoverTransformMap -ComponentsEnvelope $componentsBefore -Fraction ([double]$fraction)
    $angle1 = [double]$Branch1.open_angle_deg * [double]$fraction
    $angle2 = [double]$Branch2.open_angle_deg * [double]$fraction

    $pairRows = New-Object System.Collections.Generic.List[object]

    foreach ($mover in $MoverNames) {
        foreach ($obstacle in $StaticObstacleNames) {
            $data = Invoke-PairAtTransforms -A $mover -B $obstacle -ATransform $transformMap[$mover] -BTransform $null
            $row = [ordered]@{
                sample_fraction = [double]$fraction
                angle_branch1_deg = $angle1
                angle_branch2_deg = $angle2
                a_name_exact = $mover
                b_name_exact = $obstacle
                classification = [string]$data.classification
                intersection_body_count = Get-OptionalJsonPropertyValue -Object $data -Name 'intersection_body_count'
                intersection_volume_mm3 = Get-OptionalJsonPropertyValue -Object $data -Name 'intersection_volume_mm3'
                minimum_distance_mm = Get-OptionalJsonPropertyValue -Object $data -Name 'minimum_distance_mm'
                api_distance = [string](Get-OptionalJsonPropertyValue -Object $data -Name 'api_distance')
            }
            $pairRows.Add($row)
            if ([string]$data.classification -ceq 'physical_interference') {
                $interferenceRows.Add($row)
            }
            elseif ([string]$data.classification -match '^indeterminate_') {
                $indeterminateRows.Add($row)
            }
        }
    }

    foreach ($pair in $CrossBranchPairs) {
        $a = [string]$pair[0]
        $b = [string]$pair[1]
        $data = Invoke-PairAtTransforms -A $a -B $b -ATransform $transformMap[$a] -BTransform $transformMap[$b]
        $row = [ordered]@{
            sample_fraction = [double]$fraction
            angle_branch1_deg = $angle1
            angle_branch2_deg = $angle2
            a_name_exact = $a
            b_name_exact = $b
            classification = [string]$data.classification
            intersection_body_count = Get-OptionalJsonPropertyValue -Object $data -Name 'intersection_body_count'
            intersection_volume_mm3 = Get-OptionalJsonPropertyValue -Object $data -Name 'intersection_volume_mm3'
            minimum_distance_mm = Get-OptionalJsonPropertyValue -Object $data -Name 'minimum_distance_mm'
            api_distance = [string](Get-OptionalJsonPropertyValue -Object $data -Name 'api_distance')
        }
        $pairRows.Add($row)
        if ([string]$data.classification -ceq 'physical_interference') {
            $interferenceRows.Add($row)
        }
        elseif ([string]$data.classification -match '^indeterminate_') {
            $indeterminateRows.Add($row)
        }
    }

    $sampleRows.Add([ordered]@{
        fraction = [double]$fraction
        branch1_angle_deg = $angle1
        branch2_angle_deg = $angle2
        candidate_transforms = $transformMap
        pair_count = $pairRows.Count
        physical_interference_count = @($pairRows | Where-Object { $_.classification -ceq 'physical_interference' }).Count
        indeterminate_count = @($pairRows | Where-Object { $_.classification -match '^indeterminate_' }).Count
        nonintersecting_contact_or_clearance_unresolved_count = @($pairRows | Where-Object { $_.classification -ceq 'noninterfering_contact_or_clearance_unresolved' }).Count
        current_pose_contact_or_coincidence_count = @($pairRows | Where-Object { $_.classification -ceq 'contact_or_coincidence_within_tolerance' }).Count
        pair_results = @($pairRows)
    })
}

$componentsAfter = Invoke-WorkerJson -Arguments @('components','--all')
$targetStateAfter = Get-TargetState -ComponentsEnvelope $componentsAfter -TargetComponents $AllTrackedNames
$statusAfter = Invoke-WorkerJson -Arguments @('status')
Assert-ExpectedStatus $statusAfter
$documentStateAfter = Get-DocumentState $statusAfter
$fileAfter = Get-FileEvidence -Path $ExpectedDocumentPath

if (($targetStateBefore | ConvertTo-Json -Depth 40 -Compress) -cne ($targetStateAfter | ConvertTo-Json -Depth 40 -Compress)) {
    throw 'Tracked component transform/state evidence changed during the no-mutation hypothetical sweep.'
}
if (($documentStateBefore | ConvertTo-Json -Depth 10 -Compress) -cne ($documentStateAfter | ConvertTo-Json -Depth 10 -Compress)) {
    throw 'SOLIDWORKS process/document/configuration/save state changed during the no-mutation hypothetical sweep.'
}
if ($fileBefore.sha256 -cne $fileAfter.sha256 -or
    $fileBefore.length -ne $fileAfter.length -or
    $fileBefore.last_write_time_utc -cne $fileAfter.last_write_time_utc) {
    throw 'Assembly file evidence changed during the no-mutation hypothetical sweep.'
}

$resultState = if ($indeterminateRows.Count -gt 0) {
    'UNRESOLVED_TOOLING_OR_GEOMETRY'
}
elseif ($interferenceRows.Count -gt 0) {
    'INTERFERENCE_OBSERVED_AT_SAMPLED_STATE'
}
else {
    'NO_BREP_INTERFERENCE_OBSERVED_AT_SAMPLED_STATES_CLEARANCE_UNRESOLVED'
}

$verification = [ordered]@{
    schema_version = 1
    test_id = $TestId
    test = 'v43 PRISM dual-independent-pivot sampled exact B-rep hypothetical interference sweep'
    result = $resultState
    executed_at_utc = [DateTime]::UtcNow.ToString('o')
    candidate_id = $CandidateId
    candidate_motion_variant_id = $VariantId
    expected_document = [ordered]@{
        title = $ExpectedDocumentTitle
        path = $ExpectedDocumentPath
        expected_configuration = $ExpectedConfiguration
        configuration_binding = 'PREASSERTED_AND_OBSERVED'
    }
    worker_version = $ExpectedWorkerVersion
    source_classification = 'verified_from_solidworks_api'
    write_authority = 'NONE'
    model_mutation = $false
    mechanical_acceptance_granted = $false
    sample_fractions = $SampleFractions
    motion_hypothesis = [ordered]@{
        branch_1 = $Branch1
        branch_2 = $Branch2
        interpretation = 'Arm+roller pairs are transformed as rigid pairs about the preflight hypothetical +Z pivots. Links, slider, rails, base, actuator envelope and all obstacle components remain at their current assembly poses. This is a diagnostic POP hypothesis, not an authored mechanism.'
    }
    obstacle_set = $StaticObstacleNames
    cross_branch_pairs = $CrossBranchPairs
    document_state_before = $documentStateBefore
    document_state_after = $documentStateAfter
    file_before = $fileBefore
    file_after = $fileAfter
    tracked_state_before = $targetStateBefore
    tracked_state_after = $targetStateAfter
    physical_interferences = @($interferenceRows)
    indeterminate_results = @($indeterminateRows)
    samples = @($sampleRows)
    evidence_contract = [ordered]@{
        status = 'OBSERVATION_READY_ONLY'
        establishes = @(
            'positive B-rep intersection for any exact sampled candidate pair that returns physical_interference',
            'absence of positive B-rep intersection for sampled pairs that return noninterfering_contact_or_clearance_unresolved',
            'exact candidate transforms used for each sampled hypothetical pose',
            'pre/post document, file and tracked-component no-mutation comparison'
        )
        does_not_establish = @(
            'positive clearance magnitude for hypothetical nonintersecting temporary bodies',
            'continuous collision-free motion between samples',
            'pivot/bearing existence or authored kinematic ownership',
            'contact maintenance, preload, compliance, force, friction, traction or reaction capacity',
            'actuator identity, synchronization law, sequence timing or mechanical acceptance'
        )
        fail_closed_rule = 'Hypothetical nonintersecting temporary-body results remain contact-versus-clearance unresolved. They must not be reported as a positive clearance value.'
    }
    limitation = 'This test is a sampled one-sided exact B-rep interference screen for one explicit project-authored dual-pivot POP hypothesis. Passing sampled nonintersection cannot establish continuous reachable clearance or mechanical acceptance.'
}

$verificationPath = Join-Path $OutputRoot 'verification-summary.json'
Write-JsonFileUtf8NoBom -Value $verification -LiteralPath $verificationPath -Depth 100

Stop-WorkerServer

Write-Host "RESULT: $resultState"
Write-Host "Evidence: $verificationPath"

if ($resultState -eq 'UNRESOLVED_TOOLING_OR_GEOMETRY') { exit 2 }
if ($resultState -eq 'INTERFERENCE_OBSERVED_AT_SAMPLED_STATE') { exit 3 }
exit 0
