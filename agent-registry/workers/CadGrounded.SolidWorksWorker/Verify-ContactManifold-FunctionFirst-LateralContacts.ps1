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
$OutputRoot = Join-Path $WorkerRoot 'verification-output\function-first-lateral-contact-manifold'
$Bottle = 'BENCH_BOTTLE_D48_H180-2'
$Conveyor = 'BENCH_CONVEYOR_L900_W82_H950-1'
$Pairs = @(
    [ordered]@{ id = 'wrap_belt'; b = 'FITCHECK_DRIVEN_WRAP_BELT_5x160x93_V25-1'; expected_type = 'plane' },
    [ordered]@{ id = 'roller_1'; b = 'FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-1'; expected_type = 'cylinder' },
    [ordered]@{ id = 'roller_2'; b = 'FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-2'; expected_type = 'cylinder' }
)
$TargetComponents = @($Bottle,$Conveyor) + @($Pairs | ForEach-Object { $_.b })
$Tol = 1e-6

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
    $requestJson = $Request | ConvertTo-Json -Depth 40 -Compress
    $text = ($requestJson | & $WorkerExe execute-json | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Worker execute-json failed. ExitCode=$LASTEXITCODE" }
    if ([string]::IsNullOrWhiteSpace($text)) { throw 'Worker execute-json returned no JSON.' }
    $envelope = $text | ConvertFrom-Json
    if (-not [bool]$envelope.ok) { throw "Worker returned ok=false. Command=$($envelope.command_id) Error=$($envelope.error.message)" }
    return $envelope
}

function Assert-ExpectedStatus {
    param([Parameter(Mandatory=$true)]$Envelope)
    if ([string]$Envelope.command_id -cne 'sw.status') { throw "Expected sw.status envelope." }
    if ([string]$Envelope.data.worker_version -cne $ExpectedWorkerVersion) { throw "Worker version mismatch. Actual='$($Envelope.data.worker_version)'." }
    if ([string]$Envelope.data.write_authority -cne 'NONE') { throw 'Worker write authority is not NONE.' }
    if ([string]$Envelope.data.document.title -cne $ExpectedDocumentTitle) { throw 'Active document title mismatch.' }
    if (-not [string]::Equals([string]$Envelope.data.document.path,$ExpectedDocumentPath,[StringComparison]::OrdinalIgnoreCase)) { throw 'Active document path mismatch.' }
    if ([string]$Envelope.data.document.active_configuration -cne $ExpectedConfiguration) { throw 'Active configuration mismatch.' }
}

function Get-DocumentState {
    param([Parameter(Mandatory=$true)]$StatusEnvelope)
    [ordered]@{
        solidworks_process_id = [string]$StatusEnvelope.data.solidworks_process_id
        title = [string]$StatusEnvelope.data.document.title
        path = [string]$StatusEnvelope.data.document.path
        active_configuration = [string]$StatusEnvelope.data.document.active_configuration
        save_flag = $StatusEnvelope.data.document.save_flag
    }
}

function Get-Dot3 {
    param([double[]]$A,[double[]]$B)
    ([double]$A[0]*[double]$B[0]) + ([double]$A[1]*[double]$B[1]) + ([double]$A[2]*[double]$B[2])
}

function Get-Cross3 {
    param([double[]]$A,[double[]]$B)
    $ax=[double]$A[0]; $ay=[double]$A[1]; $az=[double]$A[2]
    $bx=[double]$B[0]; $by=[double]$B[1]; $bz=[double]$B[2]
    @(
        ($ay*$bz)-($az*$by),
        ($az*$bx)-($ax*$bz),
        ($ax*$by)-($ay*$bx)
    )
}

function Get-Magnitude3 {
    param([double[]]$A)
    [Math]::Sqrt((Get-Dot3 -A $A -B $A))
}

function Get-Unit3 {
    param([double[]]$A)
    $m=Get-Magnitude3 -A $A
    if($m -le $Tol){ throw 'Cannot normalize near-zero vector.' }
    @(([double]$A[0]/$m),([double]$A[1]/$m),([double]$A[2]/$m))
}

function Get-ContactNormals {
    param([string]$Other)
    Invoke-WorkerRequest -Request @{
        command_id='sw.contact_surface_normals_pair'
        payload=@{
            document_title_exact=$ExpectedDocumentTitle
            document_path_exact=$ExpectedDocumentPath
            active_configuration_exact=$ExpectedConfiguration
            a_name_exact=$Bottle
            b_name_exact=$Other
        }
    }
}

function Select-BottleMainCylinderCandidate {
    param($Envelope,[string]$Label)
    $matches=@($Envelope.data.face_candidates_a | Where-Object {
        [string]$_.surface_observation.surface_type -ceq 'cylinder' -and
        $null -ne $_.surface_observation.cylinder -and
        [Math]::Abs([double]$_.surface_observation.cylinder.radius_mm - 24.0) -lt 1e-6
    })
    if($matches.Count -ne 1){ throw "$Label bottle main-cylinder candidate count=$($matches.Count), expected 1." }
    $axis=@($matches[0].surface_observation.cylinder.axis_direction_assembly)
    if($axis.Count -ne 3 -or [Math]::Abs([Math]::Abs([double]$axis[2])-1.0) -gt 1e-6){ throw "$Label bottle cylinder axis is not assembly-Z parallel." }
    if($null -eq $matches[0].assembly_z_extent_probe){ throw "$Label bottle cylinder has no trimmed Z extent probe." }
    return $matches[0]
}

function Select-OpposedCandidate {
    param($Candidates,[double[]]$BottleNormal,[string]$ExpectedType,[string]$Label)
    $best=$null
    $bestDot=[double]::PositiveInfinity
    foreach($candidate in @($Candidates)){
        if([string]$candidate.surface_observation.surface_type -cne $ExpectedType){ continue }
        $n=@($candidate.unit_normal_assembly | ForEach-Object {[double]$_})
        if($n.Count -ne 3){ continue }
        $dot=Get-Dot3 -A $BottleNormal -B $n
        if($dot -lt $bestDot){ $best=$candidate; $bestDot=$dot }
    }
    if($null -eq $best){ throw "$Label has no '$ExpectedType' opposing candidate." }
    if($bestDot -gt -0.999){ throw "$Label best opposing candidate dot=$bestDot, expected near -1." }
    if($null -eq $best.assembly_z_extent_probe){ throw "$Label opposing face has no trimmed Z extent probe." }
    [pscustomobject]@{candidate=$best;dot=$bestDot}
}

function Get-Overlap {
    param($AExtent,$BExtent,[string]$Label)
    $zMin=[Math]::Max([double]$AExtent.z_min_mm,[double]$BExtent.z_min_mm)
    $zMax=[Math]::Min([double]$AExtent.z_max_mm,[double]$BExtent.z_max_mm)
    $length=$zMax-$zMin
    if($length -le $Tol){ throw "$Label has no positive trimmed axial overlap. min=$zMin max=$zMax." }
    [ordered]@{z_min_mm=$zMin;z_max_mm=$zMax;length_mm=$length}
}

function Get-MatrixRank {
    param([double[][]]$Rows,[double]$Tolerance=1e-9)
    if($Rows.Count -eq 0){ return 0 }
    $m=$Rows.Count
    $n=$Rows[0].Count
    $a=New-Object 'double[,]' $m,$n
    for($i=0;$i -lt $m;$i++){
        if($Rows[$i].Count -ne $n){ throw 'Matrix rows have inconsistent width.' }
        for($j=0;$j -lt $n;$j++){ $a[$i,$j]=[double]$Rows[$i][$j] }
    }
    $rank=0
    $pivotRow=0
    for($col=0;$col -lt $n -and $pivotRow -lt $m;$col++){
        $best=-1; $bestAbs=0.0
        for($r=$pivotRow;$r -lt $m;$r++){
            $cellValue=[double]$a[$r,$col]
            $v=[Math]::Abs($cellValue)
            if($v -gt $bestAbs){$bestAbs=$v;$best=$r}
        }
        if($best -lt 0 -or $bestAbs -le $Tolerance){continue}
        if($best -ne $pivotRow){
            for($j=0;$j -lt $n;$j++){
                $pivotRowValue=[double]$a[$pivotRow,$j]
                $bestRowValue=[double]$a[$best,$j]
                $a[$pivotRow,$j]=$bestRowValue
                $a[$best,$j]=$pivotRowValue
            }
        }

        $pivotValue=[double]$a[$pivotRow,$col]
        for($j=$col;$j -lt $n;$j++){
            $rowValue=[double]$a[$pivotRow,$j]
            $a[$pivotRow,$j]=$rowValue/$pivotValue
        }

        for($r=0;$r -lt $m;$r++){
            if($r -eq $pivotRow){continue}
            $factor=[double]$a[$r,$col]
            if([Math]::Abs($factor) -le $Tolerance){continue}
            for($j=$col;$j -lt $n;$j++){
                $currentValue=[double]$a[$r,$j]
                $pivotRowValue=[double]$a[$pivotRow,$j]
                $a[$r,$j]=$currentValue-($factor*$pivotRowValue)
            }
        }
        $rank++; $pivotRow++
    }
    return $rank
}

function New-WrenchRow {
    param([double[]]$PointMm,[double[]]$Reaction,[double[]]$ReferenceMm)

    $px=[double]$PointMm[0]
    $py=[double]$PointMm[1]
    $pz=[double]$PointMm[2]
    $rx0=[double]$ReferenceMm[0]
    $ry0=[double]$ReferenceMm[1]
    $rz0=[double]$ReferenceMm[2]

    $armX=$px-$rx0
    $armY=$py-$ry0
    $armZ=$pz-$rz0
    $arm=@($armX,$armY,$armZ)

    $moment=Get-Cross3 -A $arm -B $Reaction
    @(
        [double]$Reaction[0],[double]$Reaction[1],[double]$Reaction[2],
        [double]$moment[0],[double]$moment[1],[double]$moment[2]
    )
}

if(-not $SkipBuild){
    & (Join-Path $WorkerRoot 'build.cmd')
    if($LASTEXITCODE -ne 0){ throw "build.cmd failed with exit code $LASTEXITCODE." }
}
if(-not (Test-Path -LiteralPath $WorkerExe -PathType Leaf)){ throw "Worker executable not found: $WorkerExe" }

[void](New-Item -ItemType Directory -Force -Path $OutputRoot)

$statusBefore=Invoke-WorkerJson -Arguments @('status')
Assert-ExpectedStatus $statusBefore
$documentStateBefore=Get-DocumentState $statusBefore
$fileBefore=Get-FileEvidence -Path $ExpectedDocumentPath
$componentsBefore=Invoke-WorkerJson -Arguments @('components','--all')
$targetStateBefore=Get-TargetState -ComponentsEnvelope $componentsBefore -TargetComponents $TargetComponents

$conveyorNormals=Get-ContactNormals -Other $Conveyor
$conveyorBottle=@($conveyorNormals.data.face_candidates_a | Where-Object {
    $n=@($_.unit_normal_assembly)
    $n.Count -eq 3 -and [Math]::Abs([double]$n[2]+1.0) -lt 1e-6
})
$conveyorOther=@($conveyorNormals.data.face_candidates_b | Where-Object {
    $n=@($_.unit_normal_assembly)
    $n.Count -eq 3 -and [Math]::Abs([double]$n[2]-1.0) -lt 1e-6
})
if($conveyorBottle.Count -lt 1 -or $conveyorOther.Count -lt 1){ throw 'Conveyor opposed assembly-Z normal pair unresolved.' }
$referencePoint=@(
    [double]$conveyorNormals.data.closest_point_a_mm[0],
    [double]$conveyorNormals.data.closest_point_a_mm[1],
    [double]$conveyorNormals.data.closest_point_a_mm[2]
)

$manifolds=@()
$finiteRows=New-Object System.Collections.Generic.List[object]
[void]$finiteRows.Add((New-WrenchRow -PointMm $referencePoint -Reaction @(0.0,0.0,1.0) -ReferenceMm $referencePoint))

foreach($pair in $Pairs){
    $contact=Invoke-WorkerRequest -Request @{
        command_id='sw.classify_contact_pair'
        payload=@{a_name_exact=$Bottle;b_name_exact=[string]$pair.b}
    }
    if([string]$contact.data.classification -cne 'contact_or_coincidence_within_tolerance'){ throw "Pair '$($pair.id)' is not touching." }
    if($null -eq $contact.data.intersection_volume_mm3 -or [Math]::Abs([double]$contact.data.intersection_volume_mm3) -gt 0.001){ throw "Pair '$($pair.id)' has unresolved/non-zero intersection." }

    $normals=Get-ContactNormals -Other ([string]$pair.b)
    $bottleFace=Select-BottleMainCylinderCandidate -Envelope $normals -Label ([string]$pair.id)
    $bottleNormal=Get-Unit3 -A @($bottleFace.unit_normal_assembly | ForEach-Object {[double]$_})
    $other=Select-OpposedCandidate -Candidates $normals.data.face_candidates_b -BottleNormal $bottleNormal -ExpectedType ([string]$pair.expected_type) -Label ([string]$pair.id)
    $otherFace=$other.candidate
    $overlap=Get-Overlap -AExtent $bottleFace.assembly_z_extent_probe -BExtent $otherFace.assembly_z_extent_probe -Label ([string]$pair.id)

    $contactPoint=@(
        [double]$normals.data.closest_point_a_mm[0],
        [double]$normals.data.closest_point_a_mm[1],
        [double]$normals.data.closest_point_a_mm[2]
    )
    $reaction=@(-[double]$bottleNormal[0],-[double]$bottleNormal[1],-[double]$bottleNormal[2])

    $classification=$null
    $analytic=$null

    if([string]$pair.expected_type -ceq 'plane'){
        $classification='TANGENT_CYLINDER_PLANE_GENERATOR_LINE'
        $analytic=[ordered]@{
            bottle_radius_mm=[double]$bottleFace.surface_observation.cylinder.radius_mm
            opposed_normal_dot=[double]$other.dot
        }
    } else {
        $otherCylinder=$otherFace.surface_observation.cylinder
        if($null -eq $otherCylinder){ throw "Pair '$($pair.id)' counterpart cylinder parameters unresolved." }
        $aAxis=Get-Unit3 -A @($bottleFace.surface_observation.cylinder.axis_direction_assembly | ForEach-Object {[double]$_})
        $bAxis=Get-Unit3 -A @($otherCylinder.axis_direction_assembly | ForEach-Object {[double]$_})
        $axisDot=Get-Dot3 -A $aAxis -B $bAxis
        if([Math]::Abs([Math]::Abs($axisDot)-1.0) -gt 1e-6){ throw "Pair '$($pair.id)' cylinder axes are not parallel." }

        $ap=@($bottleFace.surface_observation.cylinder.axis_point_assembly_mm | ForEach-Object {[double]$_})
        $bp=@($otherCylinder.axis_point_assembly_mm | ForEach-Object {[double]$_})
        $bpx=[double]$bp[0]
        $bpy=[double]$bp[1]
        $bpz=[double]$bp[2]
        $apx=[double]$ap[0]
        $apy=[double]$ap[1]
        $apz=[double]$ap[2]
        $deltaX=$bpx-$apx
        $deltaY=$bpy-$apy
        $deltaZ=$bpz-$apz
        $delta=@($deltaX,$deltaY,$deltaZ)
        $cross=Get-Cross3 -A $delta -B $aAxis
        $axisDistance=Get-Magnitude3 -A $cross
        $radiusSum=[double]$bottleFace.surface_observation.cylinder.radius_mm+[double]$otherCylinder.radius_mm
        if([Math]::Abs($axisDistance-$radiusSum) -gt 1e-5){ throw "Pair '$($pair.id)' external cylinder tangency mismatch. axisDistance=$axisDistance radiusSum=$radiusSum." }

        $classification='EXTERNAL_TANGENT_PARALLEL_CYLINDER_GENERATOR_LINE'
        $analytic=[ordered]@{
            bottle_radius_mm=[double]$bottleFace.surface_observation.cylinder.radius_mm
            counterpart_radius_mm=[double]$otherCylinder.radius_mm
            cylinder_axis_parallel_dot=[double]$axisDot
            cylinder_axis_distance_mm=[double]$axisDistance
            radius_sum_mm=[double]$radiusSum
            tangency_residual_mm=([double]$axisDistance)-([double]$radiusSum)
            opposed_normal_dot=[double]$other.dot
        }
    }

    foreach($z in @([double]$overlap.z_min_mm,[double]$overlap.z_max_mm)){
        $sample=@([double]$contactPoint[0],[double]$contactPoint[1],$z)
        [void]$finiteRows.Add((New-WrenchRow -PointMm $sample -Reaction $reaction -ReferenceMm $referencePoint))
    }

    $manifolds += [ordered]@{
        pair_id=[string]$pair.id
        a_name_exact=$Bottle
        b_name_exact=[string]$pair.b
        contact_point_mm=$contactPoint
        bottle_face=$bottleFace
        counterpart_face=$otherFace
        classification=$classification
        analytic_tangency=$analytic
        trimmed_axis_overlap=$overlap
        finite_line_model_samples_mm=@(
            @([double]$contactPoint[0],[double]$contactPoint[1],[double]$overlap.z_min_mm),
            @([double]$contactPoint[0],[double]$contactPoint[1],[double]$overlap.z_max_mm)
        )
    }
}

$rows=@($finiteRows | ForEach-Object { [double[]]$_ })
$rank=Get-MatrixRank -Rows $rows -Tolerance 1e-9
$nullity=6-$rank
$wrapTwist=@(0.0,0.0,0.0,0.0,0.0,1.0)
$wrapResiduals=@()
foreach($row in $rows){
    $sum=0.0
    for($j=0;$j -lt 6;$j++){
        $rowValue=[double]$row[$j]
        $twistValue=[double]$wrapTwist[$j]
        $sum += $rowValue*$twistValue
    }
    $wrapResiduals += $sum
}
$maxWrapResidual=($wrapResiduals | ForEach-Object {
    $residualValue=[double]$_
    [Math]::Abs($residualValue)
} | Measure-Object -Maximum).Maximum

$componentsAfter=Invoke-WorkerJson -Arguments @('components','--all')
$targetStateAfter=Get-TargetState -ComponentsEnvelope $componentsAfter -TargetComponents $TargetComponents
$statusAfter=Invoke-WorkerJson -Arguments @('status')
Assert-ExpectedStatus $statusAfter
$documentStateAfter=Get-DocumentState $statusAfter
$fileAfter=Get-FileEvidence -Path $ExpectedDocumentPath

if(($targetStateBefore | ConvertTo-Json -Depth 30 -Compress) -cne ($targetStateAfter | ConvertTo-Json -Depth 30 -Compress)){ throw 'Target component state changed during manifold verification.' }
if(($documentStateBefore | ConvertTo-Json -Depth 10 -Compress) -cne ($documentStateAfter | ConvertTo-Json -Depth 10 -Compress)){ throw 'Document/process/configuration/save state changed during manifold verification.' }
if($fileBefore.sha256 -cne $fileAfter.sha256 -or $fileBefore.length -ne $fileAfter.length -or $fileBefore.last_write_time_utc -cne $fileAfter.last_write_time_utc){ throw 'Assembly file evidence changed during manifold verification.' }

$verification=[ordered]@{
    schema_version=1
    test='function-first exact lateral contact manifold and ideal finite-line restraint verification'
    result='PASS'
    executed_at_utc=[DateTime]::UtcNow.ToString('o')
    worker_version=$ExpectedWorkerVersion
    expected_document=[ordered]@{
        title=$ExpectedDocumentTitle
        path=$ExpectedDocumentPath
        expected_configuration=$ExpectedConfiguration
        configuration_binding='PREASSERTED_AND_OBSERVED'
    }
    write_authority='NONE'
    remote_queue_authorized=$false
    bound_wrap_axis_assembly=@(0.0,0.0,1.0)
    reference_point_mm=$referencePoint
    document_state_before=$documentStateBefore
    document_state_after=$documentStateAfter
    file_before=$fileBefore
    file_after=$fileAfter
    target_state_before=$targetStateBefore
    target_state_after=$targetStateAfter
    lateral_contact_manifolds=$manifolds
    ideal_maintained_frictionless_finite_line_model=[ordered]@{
        coordinate_order=@('vx','vy','vz','omega_x','omega_y','omega_z')
        constraint_rows=$rows
        rank=$rank
        nullity=$nullity
        wrap_axis_rotation_residuals=$wrapResiduals
        wrap_axis_rotation_max_abs_residual=[double]$maxWrapResidual
        wrap_axis_rotation_is_null_mode=([double]$maxWrapResidual -le 1e-9)
        five_dof_restraint_excluding_wrap_rotation=if($rank -ge 5 -and [double]$maxWrapResidual -le 1e-9){'SUPPORTED_BY_IDEAL_FINITE_LINE_NORMAL_MODEL'}else{'NOT_SUPPORTED_BY_IDEAL_FINITE_LINE_NORMAL_MODEL'}
    }
    evidence_contract=[ordered]@{
        status='OBSERVATION_READY_ONLY'
        establishes=@(
            'exact current-pose analytic surface type for the bottle and opposing face at each of the three lateral contacts',
            'trimmed-face assembly-Z extent from bounded closest-point probes on transformed temporary B-rep faces',
            'cylinder-plane or parallel-cylinder tangency classification where supported by the observed analytic surfaces',
            'positive axial overlap length for each classified generator-line contact',
            'rank/nullity of an ideal maintained frictionless finite-line constraint model using two separated samples per observed lateral line contact',
            'pre/post document, target-state, and assembly-file no-mutation comparison'
        )
        does_not_establish=@(
            'unilateral contact maintenance, preload, compliance, deformation, or force capacity',
            'friction, traction, driven wrap torque, or rotation source',
            'gravity/up semantics',
            'interval-wide contact or reachable motion',
            'that the current V43 belt or rollers are required in the final mechanism',
            'mechanism selection or mechanical acceptance'
        )
    }
    limitation='Finite-line rank is an ideal rigid maintained-contact geometric model. It must not be promoted into real tilt restraint without contact-maintenance/preload/compliance evidence.'
    mechanical_acceptance_granted=$false
}

$verificationPath=Join-Path $OutputRoot 'verification-summary.json'
Write-JsonFileUtf8NoBom -Value $verification -LiteralPath $verificationPath -Depth 100
Write-Host 'PASS: function-first lateral contact manifold verification'
Write-Host "Evidence: $verificationPath"
