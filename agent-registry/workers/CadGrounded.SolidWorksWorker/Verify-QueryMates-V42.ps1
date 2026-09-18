[CmdletBinding()]
param(
    [string]$ExpectedDocumentTitle = 'IXOR_Benchmark_v42_ROLLER_GUIDE_HARDSTOP_FIT_CHECK_PORTABLE',
    [string]$ExpectedDocumentPath = 'C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v42_ROLLER_GUIDE_HARDSTOP_FIT_CHECK_PORTABLE.SLDASM',
    [switch]$SkipBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ExpectedWorkerVersion = '0.3.0'
$WorkerRoot = $PSScriptRoot
$WorkerExe = Join-Path $WorkerRoot 'bin\Release\net8.0-windows\win-x64\CadGrounded.SolidWorksWorker.exe'
$OutputRoot = Join-Path $WorkerRoot 'verification-output\query-mates-v42'

$TargetComponents = @(
    'FITCHECK_DRIVEN_WRAP_BELT_5x160x93_V25-1',
    'FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-1',
    'FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-2',
    'FITCHECK_INDEX_STOP_FINGER_54p25x6x20_V37-1',
    'FITCHECK_INDEX_STOP_FINGER_54p25x6x20_V37-2',
    'BENCH_BOTTLE_D48_H180-2'
)

function Invoke-WorkerJson {
    param([Parameter(Mandatory=$true)][string[]]$Arguments)

    $text = (& $WorkerExe @Arguments | Out-String).Trim()
    $exitCode = $LASTEXITCODE

    if ([string]::IsNullOrWhiteSpace($text)) {
        throw "Worker command returned no JSON. ExitCode=$exitCode Arguments=$($Arguments -join ' ')"
    }

    try {
        $envelope = $text | ConvertFrom-Json
    } catch {
        throw "Worker output was not valid JSON. ExitCode=$exitCode Arguments=$($Arguments -join ' ') Raw=$text"
    }

    if (-not [bool]$envelope.ok) {
        $errorType = [string]$envelope.error.type
        $errorMessage = [string]$envelope.error.message
        $errorHResult = [string]$envelope.error.hresult
        throw "Worker returned ok=false. ExitCode=$exitCode Command=$($envelope.command_id) ErrorType=$errorType HResult=$errorHResult Error=$errorMessage"
    }

    if ($exitCode -ne 0) {
        throw "Worker returned ok=true with nonzero exit code. ExitCode=$exitCode Arguments=$($Arguments -join ' ')"
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
}

function Get-TargetState {
    param([Parameter(Mandatory=$true)]$ComponentsEnvelope)

    $state = [ordered]@{}
    foreach ($name in $TargetComponents) {
        $matches = @($ComponentsEnvelope.data.components | Where-Object { [string]$_.name2 -ceq $name })
        if ($matches.Count -ne 1) {
            throw "Exact Component2.Name2 must resolve uniquely. name='$name' matches=$($matches.Count)."
        }
        $c = $matches[0]
        $state[$name] = [ordered]@{
            name2 = [string]$c.name2
            path = [string]$c.path
            suppression_state = $c.suppression_state
            fixed_component = $c.fixed_component
            parent_name = $c.parent_name
            rotation9 = @($c.rotation9)
            translation_mm = @($c.translation_mm)
            transform_source = [string]$c.transform_source
        }
    }
    return $state
}

function Get-FileEvidence {
    param([Parameter(Mandatory=$true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Expected assembly file not found: $Path"
    }

    $item = Get-Item -LiteralPath $Path
    $sha256 = $null
    $sha256Status = 'available'
    $sha256Error = $null

    try {
        $sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
    } catch {
        $sha256Status = 'unavailable_while_open'
        $sha256Error = $_.Exception.Message
    }

    return [ordered]@{
        length = $item.Length
        last_write_time_utc = $item.LastWriteTimeUtc.ToString('o')
        sha256 = $sha256
        sha256_status = $sha256Status
        sha256_error = $sha256Error
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

$fileBefore = Get-FileEvidence -Path $ExpectedDocumentPath
$componentsBefore = Invoke-WorkerJson -Arguments @('components','--all')
$targetStateBefore = Get-TargetState -ComponentsEnvelope $componentsBefore

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

    $mateResults[$name] = $result.data
    $safeName = $name -replace '[^A-Za-z0-9._-]', '_'
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath (Join-Path $OutputRoot "$safeName.mates.json") -Encoding UTF8
}

$componentsAfter = Invoke-WorkerJson -Arguments @('components','--all')
$targetStateAfter = Get-TargetState -ComponentsEnvelope $componentsAfter
$statusAfter = Invoke-WorkerJson -Arguments @('status')
Assert-ExpectedStatus $statusAfter
$fileAfter = Get-FileEvidence -Path $ExpectedDocumentPath

$processIdBefore = [string]$statusBefore.data.solidworks_process_id
$processIdAfter = [string]$statusAfter.data.solidworks_process_id
if ($processIdBefore -cne $processIdAfter) {
    throw "SOLIDWORKS process identity changed during verification. Before='$processIdBefore' After='$processIdAfter'."
}

$beforeJson = $targetStateBefore | ConvertTo-Json -Depth 20 -Compress
$afterJson = $targetStateAfter | ConvertTo-Json -Depth 20 -Compress
if ($beforeJson -cne $afterJson) {
    throw 'Target component transform/state evidence changed during read-only mate queries.'
}

if ($fileBefore.length -ne $fileAfter.length -or
    $fileBefore.last_write_time_utc -cne $fileAfter.last_write_time_utc) {
    throw 'Assembly file metadata changed during read-only mate queries.'
}

if ($null -ne $fileBefore.sha256 -and
    $null -ne $fileAfter.sha256 -and
    $fileBefore.sha256 -cne $fileAfter.sha256) {
    throw 'Assembly file SHA-256 changed during read-only mate queries.'
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
    file_before = $fileBefore
    file_after = $fileAfter
    target_state_before = $targetStateBefore
    target_state_after = $targetStateAfter
    mate_results = $mateResults
    limitation = 'PASS proves the same SOLIDWORKS process remained bound and no observed target transform/state or assembly-file length/write-time change occurred. SHA-256 is compared when the open file is readable; SOLIDWORKS may lock the file and make hashing unavailable. PASS does not prove absence of every possible in-memory mutation, mechanical acceptance, spring preload, contact force, or operating sequence.'
}

$verificationPath = Join-Path $OutputRoot 'verification-summary.json'
$verification | ConvertTo-Json -Depth 60 | Set-Content -LiteralPath $verificationPath -Encoding UTF8

Write-Host "PASS: sw.query_mates v42 verification"
Write-Host "Evidence: $verificationPath"
