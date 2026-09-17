[CmdletBinding()]
param(
    [string]$SourceConfigPath = (Join-Path $PSScriptRoot 'queue-config.json')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$sourceConfig = Get-Content -LiteralPath $SourceConfigPath -Raw | ConvertFrom-Json
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ('cadgrounded-expired-id-' + [Guid]::NewGuid().ToString('N'))

try {
    [void](New-Item -ItemType Directory -Force -Path $tempRoot)
    $incoming = Join-Path $tempRoot 'incoming'
    [void](New-Item -ItemType Directory -Force -Path $incoming)

    $config = [ordered]@{
        schema_version = 1
        runner_version = '1.0.0'
        queue_root = $tempRoot
        worker_exe = [string]$sourceConfig.worker_exe
        poll_lock_name = 'CADGroundedRemoteQueueExpiredIdentityTest-' + [Guid]::NewGuid().ToString('N')
        max_job_bytes = 65536
        max_jobs_per_run = 10
        allowed_commands = @('sw.status')
        require_document_precondition_for = @()
    }

    $configPath = Join-Path $tempRoot 'queue-config.json'
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText(
        $configPath,
        ($config | ConvertTo-Json -Depth 10),
        $enc
    )

    $jobId = 'expired-id-regression-' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
    $job = [ordered]@{
        schema_version = 1
        job_id = $jobId
        command_id = 'sw.status'
        write_authority = 'NONE'
        created_utc = [DateTimeOffset]::UtcNow.AddMinutes(-30).ToString('o')
        expires_utc = [DateTimeOffset]::UtcNow.AddMinutes(-10).ToString('o')
        source = 'expired-job-id-regression-test'
        payload = [ordered]@{}
    }

    $jobPath = Join-Path $incoming ($jobId + '.job.json')
    [System.IO.File]::WriteAllText(
        $jobPath,
        ($job | ConvertTo-Json -Depth 10),
        $enc
    )

    & (Join-Path $PSScriptRoot 'Invoke-CADRemoteQueue.ps1') -ConfigPath $configPath | Out-Null

    $resultPath = Join-Path (Join-Path $tempRoot 'results') ($jobId + '.result.json')
    if (-not (Test-Path -LiteralPath $resultPath)) {
        throw "Expected correlated terminal result was not produced: $resultPath"
    }

    $result = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
    if ([string]$result.job_id -cne $jobId) {
        throw "job_id correlation failed. Expected='$jobId' Actual='$($result.job_id)'"
    }
    if ([string]$result.request_file_name -cne ($jobId + '.job.json')) {
        throw "request_file_name correlation failed: $($result.request_file_name)"
    }
    if ([string]$result.state -cne 'rejected') {
        throw "Expected rejected state, got '$($result.state)'."
    }
    if ([string]$result.runner_write_authority -cne 'NONE') {
        throw "runner_write_authority changed unexpectedly."
    }
    if ([string]$result.error -notlike 'Job expired at *') {
        throw "Expected expiry rejection, got '$($result.error)'."
    }

    [pscustomobject]@{
        ok = $true
        job_id = $jobId
        state = [string]$result.state
        error = [string]$result.error
        runner_write_authority = [string]$result.runner_write_authority
    } | ConvertTo-Json -Depth 5
}
finally {
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}
