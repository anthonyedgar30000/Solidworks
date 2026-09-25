[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'FileEvidence.ps1')

function Wait-ForMarker {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)]$Job
    )

    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    while (-not (Test-Path -LiteralPath $Path)) {
        if ($Job.State -eq 'Failed') {
            $jobOutput = Receive-Job -Job $Job -Keep 2>&1 | Out-String
            throw "File-holder job failed before readiness marker: $jobOutput"
        }
        if ([DateTime]::UtcNow -ge $deadline) {
            throw "Timed out waiting for file-holder readiness marker. JobState=$($Job.State)"
        }
        Start-Sleep -Milliseconds 25
    }
}

function Start-FileHolder {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][string]$ReadyPath,
        [Parameter(Mandatory=$true)][string]$ReleasePath,
        [Parameter(Mandatory=$true)][string]$ShareName
    )

    return Start-Job -ScriptBlock {
        param($HeldPath, $Ready, $Release, $RequestedShareName)

        $share = [System.IO.FileShare]([System.Enum]::Parse(
            [System.IO.FileShare],
            [string]$RequestedShareName
        ))
        $stream = $null
        try {
            $stream = [System.IO.FileStream]::new(
                $HeldPath,
                [System.IO.FileMode]::Open,
                [System.IO.FileAccess]::ReadWrite,
                $share
            )
            [System.IO.File]::WriteAllText($Ready, 'ready')
            $deadline = [DateTime]::UtcNow.AddSeconds(10)
            while (-not (Test-Path -LiteralPath $Release)) {
                if ([DateTime]::UtcNow -ge $deadline) {
                    throw 'Timed out waiting for release marker.'
                }
                Start-Sleep -Milliseconds 25
            }
        }
        finally {
            if ($null -ne $stream) {
                $stream.Dispose()
            }
        }
    } -ArgumentList @($Path, $ReadyPath, $ReleasePath, $ShareName)
}

function Stop-FileHolder {
    param(
        [Parameter(Mandatory=$true)]$Job,
        [Parameter(Mandatory=$true)][string]$ReleasePath
    )

    if (-not (Test-Path -LiteralPath $ReleasePath)) {
        [System.IO.File]::WriteAllText($ReleasePath, 'release')
    }
    $completed = Wait-Job -Job $Job -Timeout 10
    if ($null -eq $completed) {
        Stop-Job -Job $Job -ErrorAction SilentlyContinue
        throw "Timed out releasing file-holder job. JobState=$($Job.State)"
    }
    Receive-Job -Job $Job -ErrorAction Stop | Out-Null
    Remove-Job -Job $Job -Force
}

function Get-ExpectedSha256 {
    param([Parameter(Mandatory=$true)][string]$Path)

    $stream = $null
    $sha256 = $null
    try {
        $stream = [System.IO.FileStream]::new(
            $Path,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::ReadWrite
        )
        $sha256 = [System.Security.Cryptography.SHA256]::Create()
        return ([System.BitConverter]::ToString($sha256.ComputeHash($stream))).Replace('-', '').ToLowerInvariant()
    }
    finally {
        if ($null -ne $sha256) {
            $sha256.Dispose()
        }
        if ($null -ne $stream) {
            $stream.Dispose()
        }
    }
}

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("cadgrounded-file-evidence-" + [Guid]::NewGuid().ToString('N'))
$compatibleJob = $null
$exclusiveJob = $null
try {
    [System.IO.Directory]::CreateDirectory($tempRoot) | Out-Null
    $filePath = Join-Path $tempRoot 'held-assembly.SLDASM'
    [System.IO.File]::WriteAllText($filePath, 'CADGrounded shared-read regression payload')
    $expectedHash = Get-ExpectedSha256 -Path $filePath

    $compatibleReady = Join-Path $tempRoot 'compatible.ready'
    $compatibleRelease = Join-Path $tempRoot 'compatible.release'
    # Start-Job holds the stream in a child process, not the test process.
    $compatibleJob = Start-FileHolder -Path $filePath -ReadyPath $compatibleReady -ReleasePath $compatibleRelease -ShareName 'ReadWrite'
    Wait-ForMarker -Path $compatibleReady -Job $compatibleJob
    try {
        $evidence = Get-FileEvidence -Path $filePath
        if ([string]$evidence.sha256 -cne $expectedHash) {
            throw "Shared-read SHA-256 mismatch. Expected='$expectedHash' Actual='$($evidence.sha256)'."
        }
        if ([int64]$evidence.length -ne [int64](Get-Item -LiteralPath $filePath).Length) {
            throw 'Shared-read length observation did not remain stable.'
        }
    }
    finally {
        if ($null -ne $compatibleJob) {
            Stop-FileHolder -Job $compatibleJob -ReleasePath $compatibleRelease
            $compatibleJob = $null
        }
    }

    $exclusiveReady = Join-Path $tempRoot 'exclusive.ready'
    $exclusiveRelease = Join-Path $tempRoot 'exclusive.release'
    $exclusiveJob = Start-FileHolder -Path $filePath -ReadyPath $exclusiveReady -ReleasePath $exclusiveRelease -ShareName 'None'
    Wait-ForMarker -Path $exclusiveReady -Job $exclusiveJob
    try {
        $rejected = $false
        try {
            $null = Get-FileEvidence -Path $filePath
        }
        catch {
            if ($_.Exception.Message -notmatch 'stable shared read') {
                throw
            }
            $rejected = $true
        }
        if (-not $rejected) {
            throw 'Exclusive file lock was not rejected by the file-evidence reader.'
        }
    }
    finally {
        if ($null -ne $exclusiveJob) {
            Stop-FileHolder -Job $exclusiveJob -ReleasePath $exclusiveRelease
            $exclusiveJob = $null
        }
    }

    Write-Output 'PASS: shared read succeeds and exclusive lock is rejected.'
}
finally {
    if ($null -ne $compatibleJob) {
        try { Stop-FileHolder -Job $compatibleJob -ReleasePath (Join-Path $tempRoot 'compatible.release') } catch {}
    }
    if ($null -ne $exclusiveJob) {
        try { Stop-FileHolder -Job $exclusiveJob -ReleasePath (Join-Path $tempRoot 'exclusive.release') } catch {}
    }
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}
