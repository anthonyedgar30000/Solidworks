[CmdletBinding()]
param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot 'mirror-transport-config.json'),
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

function Write-Utf8NoBom {
    param([string]$Path, [string]$Text)
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Text, $enc)
}

if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    throw "Transport config not found: $ConfigPath"
}

$config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
if ([int](Require-Property $config 'schema_version' 'config') -ne 1) {
    throw 'Unsupported transport config schema_version.'
}

$mirrorRoot = [string](Require-Property $config 'mirror_queue_root' 'config')
$localRoot = [string](Require-Property $config 'local_queue_root' 'config')
$maxJobBytes = [int64](Require-Property $config 'max_job_bytes' 'config')
$allowedCommands = @($config.allowed_commands)
$retireAfterResult = [bool]$config.retire_mirror_request_after_verified_result

# The roots must remain distinct. The mirror is transport staging only; the
# canonical local queue is execution authority.
if ([string]::Equals($mirrorRoot, $localRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'mirror_queue_root and local_queue_root must be different.'
}

$mirrorDirs = @{}
$localDirs = @{}
foreach ($name in @('incoming','results')) {
    $mirrorDirs[$name] = Join-Path $mirrorRoot $name
    [void](New-Item -ItemType Directory -Force -Path $mirrorDirs[$name])
}
foreach ($name in @('incoming','processing','completed','failed','rejected','results')) {
    $localDirs[$name] = Join-Path $localRoot $name
    [void](New-Item -ItemType Directory -Force -Path $localDirs[$name])
}

$stageDir = Join-Path $localRoot '.drive-mirror-transport-staging'
$logDir = Join-Path $localRoot 'transport-logs'
[void](New-Item -ItemType Directory -Force -Path $stageDir)
[void](New-Item -ItemType Directory -Force -Path $logDir)
$logPath = Join-Path $logDir (([DateTime]::UtcNow.ToString('yyyy-MM-dd')) + '.mirror.log')

function Write-TransportLog {
    param([string]$Message)
    $line = "{0}`t{1}" -f ([DateTimeOffset]::UtcNow.ToString('o')), $Message
    Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
    Write-Output $line
}

function Get-LocalTerminalPaths {
    param([string]$JobId)
    return @(
        (Join-Path $localDirs['results'] ($JobId + '.result.json')),
        (Join-Path $localDirs['completed'] ($JobId + '.request.json')),
        (Join-Path $localDirs['failed'] ($JobId + '.request.json')),
        (Join-Path $localDirs['rejected'] ($JobId + '.request.json'))
    )
}

$mutex = New-Object System.Threading.Mutex($false, 'CADGroundedDriveMirrorTransportV1')
$hasMutex = $false
try {
    $hasMutex = $mutex.WaitOne(0)
    if (-not $hasMutex) {
        Write-TransportLog 'another mirror transport instance is active; exiting'
        exit 0
    }

    # Pull Drive Desktop mirror incoming -> canonical local queue incoming.
    foreach ($sourceFile in @(Get-ChildItem -LiteralPath $mirrorDirs['incoming'] -Filter '*.job.json' -File)) {
        $name = $sourceFile.Name
        if (-not (Test-SafeFileName $name)) {
            Write-TransportLog "mirror request skipped: unsafe filename name=$name"
            continue
        }
        if ($sourceFile.Length -gt $maxJobBytes) {
            Write-TransportLog "mirror request skipped: over size cap name=$name size=$($sourceFile.Length)"
            continue
        }

        $stagePath = Join-Path $stageDir ($name + '.' + [Guid]::NewGuid().ToString('N') + '.tmp')
        try {
            Copy-Item -LiteralPath $sourceFile.FullName -Destination $stagePath -Force
            $staged = Get-Item -LiteralPath $stagePath
            if ($staged.Length -gt $maxJobBytes) { throw 'staged request exceeds max_job_bytes' }

            $job = Get-Content -LiteralPath $stagePath -Raw | ConvertFrom-Json
            if ([int](Require-Property $job 'schema_version' 'job') -ne 1) { throw 'unsupported job schema_version' }
            $jobId = [string](Require-Property $job 'job_id' 'job')
            if (-not (Test-SafeId $jobId)) { throw 'unsafe job_id' }
            if ($name -cne ($jobId + '.job.json')) { throw 'filename/job_id mismatch' }
            if ([string](Require-Property $job 'write_authority' 'job') -cne 'NONE') {
                throw 'write_authority must be exactly NONE'
            }
            $commandId = [string](Require-Property $job 'command_id' 'job')
            if ($allowedCommands -notcontains $commandId) {
                throw "command_id is not transport-allowlisted: $commandId"
            }
            [void](Require-Property $job 'payload' 'job')

            $localIncoming = Join-Path $localDirs['incoming'] $name
            $localProcessing = Join-Path $localDirs['processing'] $name
            $terminal = @(Get-LocalTerminalPaths $jobId | Where-Object { Test-Path -LiteralPath $_ })

            if ($terminal.Count -gt 0) {
                Write-TransportLog "mirror request already has local terminal state job_id=$jobId"
                continue
            }
            if ((Test-Path -LiteralPath $localIncoming) -or (Test-Path -LiteralPath $localProcessing)) {
                continue
            }

            if ($DryRun) {
                Write-TransportLog "DRYRUN would enqueue job_id=$jobId command_id=$commandId"
            } else {
                # Atomic within the canonical local filesystem: stage under the
                # local queue root, then rename into incoming.
                Move-Item -LiteralPath $stagePath -Destination $localIncoming
                Write-TransportLog "enqueued job_id=$jobId command_id=$commandId from Drive Desktop mirror"
            }
        }
        catch {
            Write-TransportLog "mirror request not enqueued name=$name error=$($_.Exception.Message)"
        }
        finally {
            if (Test-Path -LiteralPath $stagePath) {
                Remove-Item -LiteralPath $stagePath -Force
            }
        }
    }

    # Push canonical local terminal result -> Drive Desktop mirror results.
    foreach ($resultFile in @(Get-ChildItem -LiteralPath $localDirs['results'] -Filter '*.result.json' -File)) {
        try {
            $record = Get-Content -LiteralPath $resultFile.FullName -Raw | ConvertFrom-Json
            $jobId = [string](Require-Property $record 'job_id' 'result')
            if (-not (Test-SafeId $jobId)) { throw 'unsafe result job_id' }
            if ($resultFile.Name -cne ($jobId + '.result.json')) { throw 'result filename/job_id mismatch' }
            if ([string](Require-Property $record 'runner_write_authority' 'result') -cne 'NONE') {
                throw 'runner_write_authority is not NONE'
            }
            $state = [string](Require-Property $record 'state' 'result')
            if (@('completed','failed','rejected') -notcontains $state) {
                throw "unsupported terminal state: $state"
            }

            $mirrorResult = Join-Path $mirrorDirs['results'] $resultFile.Name
            if ($DryRun) {
                Write-TransportLog "DRYRUN would publish terminal job_id=$jobId state=$state"
                continue
            }

            $tempMirror = $mirrorResult + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
            Copy-Item -LiteralPath $resultFile.FullName -Destination $tempMirror -Force
            if ((Get-FileHash -LiteralPath $tempMirror -Algorithm SHA256).Hash -cne
                (Get-FileHash -LiteralPath $resultFile.FullName -Algorithm SHA256).Hash) {
                Remove-Item -LiteralPath $tempMirror -Force
                throw 'mirror result verification hash mismatch'
            }
            Move-Item -LiteralPath $tempMirror -Destination $mirrorResult -Force
            Write-TransportLog "published terminal job_id=$jobId state=$state to Drive Desktop mirror"

            if ($retireAfterResult -and (Get-PropertyNames $record) -contains 'request_file_name') {
                $requestName = [string]$record.request_file_name
                if ((Test-SafeFileName $requestName) -and $requestName -ceq ($jobId + '.job.json')) {
                    $mirrorRequest = Join-Path $mirrorDirs['incoming'] $requestName
                    if (Test-Path -LiteralPath $mirrorRequest) {
                        Remove-Item -LiteralPath $mirrorRequest -Force
                        Write-TransportLog "retired mirror request after verified local terminal job_id=$jobId"
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
