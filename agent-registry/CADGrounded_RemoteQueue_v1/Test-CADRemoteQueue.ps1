[CmdletBinding()]
param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot 'queue-config.json')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
$incoming = Join-Path ([string]$config.queue_root) 'incoming'
[void](New-Item -ItemType Directory -Force -Path $incoming)

$jobId = 'smoke-status-' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')

$job = [ordered]@{
    schema_version = 1
    job_id = $jobId
    command_id = 'sw.status'
    write_authority = 'NONE'
    created_utc = [DateTimeOffset]::UtcNow.ToString('o')
    source = 'local-smoke-test'
    payload = [ordered]@{}
}

$jobPath = Join-Path $incoming "$jobId.job.json"
$enc = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText(
    $jobPath,
    ($job | ConvertTo-Json -Depth 10),
    $enc
)

& (Join-Path $PSScriptRoot 'Invoke-CADRemoteQueue.ps1') -ConfigPath $ConfigPath

$resultPath = Join-Path (Join-Path ([string]$config.queue_root) 'results') "$jobId.result.json"
if (-not (Test-Path -LiteralPath $resultPath)) {
    throw "Smoke test did not produce expected result: $resultPath"
}

Get-Content -LiteralPath $resultPath -Raw
