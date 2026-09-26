[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$packageRoot = Split-Path -Parent $PSScriptRoot
$transport = Join-Path $packageRoot 'Invoke-CADDriveMirrorTransport.ps1'
if (-not (Test-Path -LiteralPath $transport -PathType Leaf)) {
    throw "Transport script not found: $transport"
}

$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('cadgrounded-drive-transport-idempotency-' + [Guid]::NewGuid().ToString('N'))
$mirrorRoot = Join-Path $testRoot 'mirror'
$localRoot = Join-Path $testRoot 'local'
$configPath = Join-Path $testRoot 'mirror-transport-config.json'

function Write-JsonUtf8NoBom {
    param([string]$Path, $Value)
    $enc = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 20), $enc)
}

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

try {
    [void](New-Item -ItemType Directory -Force -Path $testRoot)
    [void](New-Item -ItemType Directory -Force -Path (Join-Path $mirrorRoot 'incoming'))
    [void](New-Item -ItemType Directory -Force -Path (Join-Path $mirrorRoot 'results'))
    [void](New-Item -ItemType Directory -Force -Path (Join-Path $localRoot 'results'))

    Write-JsonUtf8NoBom -Path $configPath -Value ([ordered]@{
        schema_version = 1
        mirror_queue_root = $mirrorRoot
        local_queue_root = $localRoot
        max_job_bytes = 65536
        allowed_commands = @('sw.status')
        retire_mirror_request_after_verified_result = $true
    })

    # Scenario 1: first run publishes once; second run must not republish.
    $job1 = 'idempotency-first-publish'
    $request1Name = $job1 + '.job.json'
    $result1Name = $job1 + '.result.json'
    Write-JsonUtf8NoBom -Path (Join-Path (Join-Path $mirrorRoot 'incoming') $request1Name) -Value ([ordered]@{
        schema_version = 1
        job_id = $job1
        write_authority = 'NONE'
        command_id = 'sw.status'
        payload = @{}
    })
    Write-JsonUtf8NoBom -Path (Join-Path (Join-Path $localRoot 'results') $result1Name) -Value ([ordered]@{
        job_id = $job1
        runner_write_authority = 'NONE'
        state = 'completed'
        request_file_name = $request1Name
        result = @{ ok = $true }
    })

    & $transport -ConfigPath $configPath | Out-Null

    $mirrorResult1 = Join-Path (Join-Path $mirrorRoot 'results') $result1Name
    Assert-True (Test-Path -LiteralPath $mirrorResult1 -PathType Leaf) 'First run did not publish the terminal result.'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path (Join-Path $mirrorRoot 'incoming') $request1Name))) 'First run did not retire the verified request.'

    $logPath = Join-Path (Join-Path $localRoot 'transport-logs') (([DateTime]::UtcNow.ToString('yyyy-MM-dd')) + '.mirror.log')
    $pattern1 = "published terminal job_id=$job1 state=completed to Drive Desktop mirror"
    $firstCount = @((Select-String -LiteralPath $logPath -SimpleMatch $pattern1)).Count
    Assert-True ($firstCount -eq 1) "Expected exactly one first-run publish log, found $firstCount."

    & $transport -ConfigPath $configPath | Out-Null
    $secondCount = @((Select-String -LiteralPath $logPath -SimpleMatch $pattern1)).Count
    Assert-True ($secondCount -eq 1) "Second run republished an unchanged terminal result; publish count is $secondCount."

    $localHash1 = (Get-FileHash -LiteralPath (Join-Path (Join-Path $localRoot 'results') $result1Name) -Algorithm SHA256).Hash
    $mirrorHash1 = (Get-FileHash -LiteralPath $mirrorResult1 -Algorithm SHA256).Hash
    Assert-True ($localHash1 -ceq $mirrorHash1) 'Published result hash does not match the canonical local result.'

    # Scenario 2: if an identical mirror result already exists, skip publication
    # but still retire the matching Drive-backed request.
    $job2 = 'idempotency-preverified-retirement'
    $request2Name = $job2 + '.job.json'
    $result2Name = $job2 + '.result.json'
    $localResult2 = Join-Path (Join-Path $localRoot 'results') $result2Name
    $mirrorResult2 = Join-Path (Join-Path $mirrorRoot 'results') $result2Name
    $mirrorRequest2 = Join-Path (Join-Path $mirrorRoot 'incoming') $request2Name

    Write-JsonUtf8NoBom -Path $mirrorRequest2 -Value ([ordered]@{
        schema_version = 1
        job_id = $job2
        write_authority = 'NONE'
        command_id = 'sw.status'
        payload = @{}
    })
    Write-JsonUtf8NoBom -Path $localResult2 -Value ([ordered]@{
        job_id = $job2
        runner_write_authority = 'NONE'
        state = 'completed'
        request_file_name = $request2Name
        result = @{ ok = $true }
    })
    Copy-Item -LiteralPath $localResult2 -Destination $mirrorResult2 -Force

    & $transport -ConfigPath $configPath | Out-Null

    $pattern2 = "published terminal job_id=$job2 state=completed to Drive Desktop mirror"
    $preverifiedPublishCount = @((Select-String -LiteralPath $logPath -SimpleMatch $pattern2)).Count
    Assert-True ($preverifiedPublishCount -eq 0) "Preverified result was unnecessarily republished $preverifiedPublishCount time(s)."
    Assert-True (-not (Test-Path -LiteralPath $mirrorRequest2)) 'Preverified result did not allow matching request retirement.'

    Write-Output 'PASS: mirror result publication is idempotent and verified-result request retirement is preserved.'
}
finally {
    if (Test-Path -LiteralPath $testRoot) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}
