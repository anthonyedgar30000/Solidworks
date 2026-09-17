[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ConfigPath,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-PropertyNames {
    param($Object)
    if ($null -eq $Object) { return @() }
    return @($Object.PSObject.Properties | ForEach-Object { $_.Name })
}

function Require-Property {
    param($Object, [string]$Name, [string]$Context)
    if ((Get-PropertyNames $Object) -notcontains $Name) {
        throw "$Context is missing required property '$Name'."
    }
    return $Object.$Name
}

function Test-SafeId {
    param([string]$Value)
    return (-not [string]::IsNullOrWhiteSpace($Value)) -and
           ($Value -match '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')
}

function Test-SafeFileName {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return $false }
    if ([IO.Path]::GetFileName($Value) -cne $Value) { return $false }
    return $Value -match '^[A-Za-z0-9][A-Za-z0-9._-]{0,191}\.json$'
}

if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    throw "Transport config not found: $ConfigPath"
}

$config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
if ([int](Require-Property $config 'schema_version' 'config') -ne 1) {
    throw 'Unsupported transport config schema_version.'
}

$rcloneExe = [string](Require-Property $config 'rclone_exe' 'config')
$rcloneRemote = [string](Require-Property $config 'rclone_remote' 'config')
$driveIncomingId = [string](Require-Property $config 'drive_incoming_folder_id' 'config')
$driveResultsId = [string](Require-Property $config 'drive_results_folder_id' 'config')
$queueRoot = [string](Require-Property $config 'local_queue_root' 'config')
$maxJobBytes = [int64](Require-Property $config 'max_job_bytes' 'config')
$allowedCommands = @($config.allowed_commands)
$deleteRemoteAfterResult = [bool]$config.delete_remote_request_after_verified_result

if ([string]::IsNullOrWhiteSpace($rcloneRemote)) { throw 'rclone_remote is empty.' }
if ($driveIncomingId -eq 'REPLACE_WITH_LOCAL_SECRET' -or [string]::IsNullOrWhiteSpace($driveIncomingId)) {
    throw 'drive_incoming_folder_id is not configured.'
}
if ($driveResultsId -eq 'REPLACE_WITH_LOCAL_SECRET' -or [string]::IsNullOrWhiteSpace($driveResultsId)) {
    throw 'drive_results_folder_id is not configured.'
}

$rcloneCommand = Get-Command $rcloneExe -ErrorAction SilentlyContinue
if ($null -eq $rcloneCommand) {
    throw "rclone executable not found: $rcloneExe"
}
$rcloneExe = $rcloneCommand.Source

$dirs = @{}
foreach ($name in @('incoming','processing','completed','failed','rejected','results')) {
    $path = Join-Path $queueRoot $name
    [void](New-Item -ItemType Directory -Force -Path $path)
    $dirs[$name] = $path
}
$stageDir = Join-Path $queueRoot '.drive-transport-staging'
$logDir = Join-Path $queueRoot 'transport-logs'
[void](New-Item -ItemType Directory -Force -Path $stageDir)
[void](New-Item -ItemType Directory -Force -Path $logDir)
$logPath = Join-Path $logDir (([DateTime]::UtcNow.ToString('yyyy-MM-dd')) + '.log')

function Write-TransportLog {
    param([string]$Message)
    $line = "{0}`t{1}" -f ([DateTimeOffset]::UtcNow.ToString('o')), $Message
    Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
    Write-Output $line
}

function Invoke-Rclone {
    param([Parameter(Mandatory=$true)][string[]]$Arguments)
    $output = @(& $rcloneExe @Arguments 2>&1)
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        throw "rclone failed (exit=$code): $($output -join ' ')"
    }
    return ($output -join [Environment]::NewLine)
}

function Get-RemoteItems {
    param([string]$FolderId)
    $remoteRoot = $rcloneRemote + ':'
    $text = Invoke-Rclone @('lsjson', $remoteRoot, '--drive-root-folder-id', $FolderId, '--files-only')
    if ([string]::IsNullOrWhiteSpace($text)) { return @() }
    return @($text | ConvertFrom-Json)
}

function Get-RemoteFileStat {
    param([string]$FolderId, [string]$FileName)
    $remotePath = ($rcloneRemote + ':' + $FileName)
    $text = Invoke-Rclone @('lsjson', $remotePath, '--drive-root-folder-id', $FolderId, '--stat')
    if ([string]::IsNullOrWhiteSpace($text)) { return $null }
    return ($text | ConvertFrom-Json)
}

$mutex = New-Object System.Threading.Mutex($false, 'CADGroundedDriveTransportV1')
$hasMutex = $false

try {
    $hasMutex = $mutex.WaitOne(0)
    if (-not $hasMutex) {
        Write-TransportLog 'another transport instance is active; exiting'
        exit 0
    }

    # Pull Drive incoming -> local canonical queue incoming.
    foreach ($item in (Get-RemoteItems $driveIncomingId)) {
        if ([bool]$item.IsDir) { continue }
        $name = [string]$item.Name
        if ($name -notmatch '\.job\.json$') { continue }
        if ([int64]$item.Size -gt $maxJobBytes) {
            Write-TransportLog "remote request skipped: over size cap name=$name size=$($item.Size)"
            continue
        }
        if (-not (Test-SafeFileName $name)) {
            Write-TransportLog "remote request skipped: unsafe filename name=$name"
            continue
        }

        $existingTransit = @(
            (Join-Path $dirs['incoming'] $name),
            (Join-Path $dirs['processing'] $name)
        ) | Where-Object { Test-Path -LiteralPath $_ }
        if ($existingTransit.Count -gt 0) { continue }

        $stagePath = Join-Path $stageDir ($name + '.' + [Guid]::NewGuid().ToString('N') + '.tmp')
        try {
            $remotePath = $rcloneRemote + ':' + $name
            [void](Invoke-Rclone @('copyto', $remotePath, $stagePath, '--drive-root-folder-id', $driveIncomingId))

            $stageInfo = Get-Item -LiteralPath $stagePath
            if ($stageInfo.Length -gt $maxJobBytes) { throw 'downloaded request exceeds max_job_bytes' }

            $job = Get-Content -LiteralPath $stagePath -Raw | ConvertFrom-Json
            if ([int](Require-Property $job 'schema_version' 'job') -ne 1) { throw 'unsupported job schema_version' }
            $jobId = [string](Require-Property $job 'job_id' 'job')
            if (-not (Test-SafeId $jobId)) { throw 'unsafe job_id' }
            if ($name -cne ($jobId + '.job.json')) { throw 'filename/job_id mismatch' }
            $writeAuthority = [string](Require-Property $job 'write_authority' 'job')
            if ($writeAuthority -cne 'NONE') { throw "write_authority must be exactly NONE" }
            $commandId = [string](Require-Property $job 'command_id' 'job')
            if ($allowedCommands -notcontains $commandId) { throw "command_id is not transport-allowlisted: $commandId" }
            [void](Require-Property $job 'payload' 'job')

            $terminalExists = @(
                (Join-Path $dirs['results'] ($jobId + '.result.json')),
                (Join-Path $dirs['completed'] ($jobId + '.request.json')),
                (Join-Path $dirs['failed'] ($jobId + '.request.json')),
                (Join-Path $dirs['rejected'] ($jobId + '.request.json'))
            ) | Where-Object { Test-Path -LiteralPath $_ }

            if ($terminalExists.Count -gt 0) {
                Write-TransportLog "remote request already has local terminal state job_id=$jobId"
                continue
            }

            if ($DryRun) {
                Write-TransportLog "DRYRUN would enqueue job_id=$jobId command_id=$commandId"
            } else {
                $destination = Join-Path $dirs['incoming'] $name
                if (Test-Path -LiteralPath $destination) { throw 'local incoming collision' }
                Move-Item -LiteralPath $stagePath -Destination $destination
                Write-TransportLog "enqueued job_id=$jobId command_id=$commandId"
            }
        }
        catch {
            Write-TransportLog "remote request not enqueued name=$name error=$($_.Exception.Message)"
        }
        finally {
            if (Test-Path -LiteralPath $stagePath) {
                Remove-Item -LiteralPath $stagePath -Force
            }
        }
    }

    # Push local terminal results -> Drive results, verify, then retire request.
    foreach ($resultFile in @(Get-ChildItem -LiteralPath $dirs['results'] -Filter '*.result.json' -File)) {
        try {
            $record = Get-Content -LiteralPath $resultFile.FullName -Raw | ConvertFrom-Json
            $jobId = [string](Require-Property $record 'job_id' 'result')
            if (-not (Test-SafeId $jobId)) { throw 'unsafe result job_id' }
            if ($resultFile.Name -cne ($jobId + '.result.json')) { throw 'result filename/job_id mismatch' }
            $runnerAuthority = [string](Require-Property $record 'runner_write_authority' 'result')
            if ($runnerAuthority -cne 'NONE') { throw 'runner_write_authority is not NONE' }
            $state = [string](Require-Property $record 'state' 'result')
            if (@('completed','failed','rejected') -notcontains $state) { throw "unsupported terminal state: $state" }

            if ($DryRun) {
                Write-TransportLog "DRYRUN would publish terminal job_id=$jobId state=$state"
                continue
            }

            $remoteResultPath = $rcloneRemote + ':' + $resultFile.Name
            [void](Invoke-Rclone @('copyto', $resultFile.FullName, $remoteResultPath, '--drive-root-folder-id', $driveResultsId))
            $remoteStat = Get-RemoteFileStat $driveResultsId $resultFile.Name
            if ($null -eq $remoteStat -or [string]$remoteStat.Name -cne $resultFile.Name) {
                throw 'Drive result verification failed after upload'
            }
            Write-TransportLog "published terminal job_id=$jobId state=$state"

            if ($deleteRemoteAfterResult -and (Get-PropertyNames $record) -contains 'request_file_name') {
                $requestName = [string]$record.request_file_name
                if ((Test-SafeFileName $requestName) -and $requestName -ceq ($jobId + '.job.json')) {
                    try {
                        [void](Get-RemoteFileStat $driveIncomingId $requestName)
                        $remoteRequestPath = $rcloneRemote + ':' + $requestName
                        [void](Invoke-Rclone @('deletefile', $remoteRequestPath, '--drive-root-folder-id', $driveIncomingId))
                        Write-TransportLog "retired Drive request after verified terminal job_id=$jobId"
                    }
                    catch {
                        Write-TransportLog "Drive request retirement skipped/failed job_id=$jobId error=$($_.Exception.Message)"
                    }
                }
            }
        }
        catch {
            Write-TransportLog "local result not published name=$($resultFile.Name) error=$($_.Exception.Message)"
        }
    }
}
finally {
    if ($hasMutex) { [void]$mutex.ReleaseMutex() }
    $mutex.Dispose()
}
