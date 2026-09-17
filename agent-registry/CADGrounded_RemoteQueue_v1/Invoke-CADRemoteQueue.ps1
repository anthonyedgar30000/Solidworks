[CmdletBinding()]
param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot 'queue-config.json')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RunnerVersion = '1.0.0'

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][string]$Text
    )
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Text, $enc)
}

function Get-PropertyNames {
    param($Object)
    if ($null -eq $Object) { return @() }
    return @($Object.PSObject.Properties | ForEach-Object { $_.Name })
}

function Assert-AllowedProperties {
    param(
        [Parameter(Mandatory=$true)]$Object,
        [Parameter(Mandatory=$true)][string[]]$Allowed,
        [Parameter(Mandatory=$true)][string]$Context
    )
    foreach ($name in (Get-PropertyNames $Object)) {
        if ($Allowed -notcontains $name) {
            throw "$Context contains unsupported property '$name'."
        }
    }
}

function Require-Property {
    param(
        [Parameter(Mandatory=$true)]$Object,
        [Parameter(Mandatory=$true)][string]$Name,
        [Parameter(Mandatory=$true)][string]$Context
    )
    if ((Get-PropertyNames $Object) -notcontains $Name) {
        throw "$Context is missing required property '$Name'."
    }
    return $Object.$Name
}

function Test-ExactString {
    param($Value, [int]$MaxLength = 2048)
    return ($Value -is [string]) -and
           (-not [string]::IsNullOrWhiteSpace($Value)) -and
           ($Value.Length -le $MaxLength)
}

function Parse-DateTimeOffsetStrict {
    param([string]$Value, [string]$FieldName)
    $dto = [DateTimeOffset]::MinValue
    if (-not [DateTimeOffset]::TryParse(
        $Value,
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::RoundtripKind,
        [ref]$dto
    )) {
        throw "$FieldName is not a valid ISO-8601 date-time."
    }
    return $dto
}

function Assert-Job {
    param($Job, $Config)

    Assert-AllowedProperties $Job @(
        'schema_version','job_id','command_id','write_authority',
        'created_utc','expires_utc','source','preconditions','payload'
    ) 'job'

    $schemaVersion = Require-Property $Job 'schema_version' 'job'
    if ([int]$schemaVersion -ne 1) {
        throw "Unsupported schema_version '$schemaVersion'."
    }

    $jobId = Require-Property $Job 'job_id' 'job'
    if (-not (Test-ExactString $jobId 128)) {
        throw 'job_id must be a non-empty string up to 128 characters.'
    }
    if ($jobId -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$') {
        throw 'job_id contains disallowed characters.'
    }

    $commandId = Require-Property $Job 'command_id' 'job'
    if (-not (Test-ExactString $commandId 128)) {
        throw 'command_id must be a non-empty string.'
    }
    if (@($Config.allowed_commands) -notcontains $commandId) {
        throw "command_id '$commandId' is not locally allowlisted."
    }

    $writeAuthority = Require-Property $Job 'write_authority' 'job'
    if ($writeAuthority -cne 'NONE') {
        throw "write_authority must be exactly 'NONE'."
    }

    if ((Get-PropertyNames $Job) -contains 'created_utc') {
        [void](Parse-DateTimeOffsetStrict ([string]$Job.created_utc) 'created_utc')
    }

    if ((Get-PropertyNames $Job) -contains 'expires_utc') {
        $expires = Parse-DateTimeOffsetStrict ([string]$Job.expires_utc) 'expires_utc'
        if ([DateTimeOffset]::UtcNow -gt $expires.ToUniversalTime()) {
            throw "Job expired at $($expires.ToString('o'))."
        }
    }

    if ((Get-PropertyNames $Job) -contains 'source') {
        if (-not (Test-ExactString $Job.source 128)) {
            throw 'source must be a non-empty string up to 128 characters.'
        }
    }

    $payload = Require-Property $Job 'payload' 'job'
    if ($null -eq $payload) {
        throw 'payload must be an object.'
    }

    $requiresDoc = @($Config.require_document_precondition_for) -contains $commandId
    $preconditionNames = @()
    if ((Get-PropertyNames $Job) -contains 'preconditions') {
        if ($null -eq $Job.preconditions) {
            throw 'preconditions must be an object when supplied.'
        }
        Assert-AllowedProperties $Job.preconditions @(
            'document_title_exact','document_path_exact'
        ) 'preconditions'
        $preconditionNames = Get-PropertyNames $Job.preconditions
        if ($preconditionNames -contains 'document_title_exact') {
            if (-not (Test-ExactString $Job.preconditions.document_title_exact 512)) {
                throw 'preconditions.document_title_exact is invalid.'
            }
        }
        if ($preconditionNames -contains 'document_path_exact') {
            if (-not (Test-ExactString $Job.preconditions.document_path_exact 2048)) {
                throw 'preconditions.document_path_exact is invalid.'
            }
        }
    } elseif ($requiresDoc) {
        throw "command_id '$commandId' requires preconditions.document_title_exact."
    }

    if ($requiresDoc -and ($preconditionNames -notcontains 'document_title_exact')) {
        throw "command_id '$commandId' requires preconditions.document_title_exact."
    }

    switch ($commandId) {
        'sw.status' {
            Assert-AllowedProperties $payload @() 'payload'
        }

        'sw.query_components' {
            Assert-AllowedProperties $payload @('top_level_only') 'payload'
            $top = Require-Property $payload 'top_level_only' 'payload'
            if ($top -isnot [bool]) {
                throw 'payload.top_level_only must be boolean.'
            }
        }

        'sw.closest_distance_pair' {
            Assert-AllowedProperties $payload @('a_name_exact','b_name_exact') 'payload'
            $a = Require-Property $payload 'a_name_exact' 'payload'
            $b = Require-Property $payload 'b_name_exact' 'payload'
            if (-not (Test-ExactString $a 1024)) {
                throw 'payload.a_name_exact is invalid.'
            }
            if (-not (Test-ExactString $b 1024)) {
                throw 'payload.b_name_exact is invalid.'
            }
        }

        'sw.query_mates' {
            Assert-AllowedProperties $payload @('component_name_exact') 'payload'
            $componentName = Require-Property $payload 'component_name_exact' 'payload'
            if (-not (Test-ExactString $componentName 1024)) {
                throw 'payload.component_name_exact is invalid.'
            }
        }

        default {
            throw "No local validator exists for '$commandId'."
        }
    }

    return $true
}

function Invoke-WorkerJson {
    param(
        [Parameter(Mandatory=$true)][string]$WorkerExe,
        [Parameter(Mandatory=$true)]$Request,
        [Parameter(Mandatory=$true)][string]$StdoutPath,
        [Parameter(Mandatory=$true)][string]$StderrPath
    )

    $json = $Request | ConvertTo-Json -Depth 30 -Compress

    # The worker's execute-json command reads exactly one request from stdin.
    $json | & $WorkerExe execute-json 1> $StdoutPath 2> $StderrPath
    $exitCode = $LASTEXITCODE

    $stdout = ''
    $stderr = ''
    if (Test-Path -LiteralPath $StdoutPath) {
        $stdout = Get-Content -LiteralPath $StdoutPath -Raw
    }
    if (Test-Path -LiteralPath $StderrPath) {
        $stderr = Get-Content -LiteralPath $StderrPath -Raw
    }

    if ([string]::IsNullOrWhiteSpace($stdout)) {
        throw "Native worker returned no JSON output. ExitCode=$exitCode. stderr=$stderr"
    }

    try {
        $envelope = $stdout | ConvertFrom-Json
    } catch {
        throw "Native worker output was not valid JSON. ExitCode=$exitCode. stdout=$stdout stderr=$stderr"
    }

    return [pscustomobject]@{
        ExitCode = $exitCode
        Envelope = $envelope
        Stdout = $stdout
        Stderr = $stderr
    }
}

function Test-DocumentPreconditions {
    param($Job, $StatusEnvelope)

    if ((Get-PropertyNames $Job) -notcontains 'preconditions') {
        return
    }

    $doc = $StatusEnvelope.data.document
    if ($null -eq $doc) {
        throw 'SOLIDWORKS status did not return an active document.'
    }

    $names = Get-PropertyNames $Job.preconditions

    if ($names -contains 'document_title_exact') {
        $expected = [string]$Job.preconditions.document_title_exact
        $actual = [string]$doc.title
        if (-not [string]::Equals($expected, $actual, [StringComparison]::Ordinal)) {
            throw "Document title precondition failed. Expected='$expected' Actual='$actual'."
        }
    }

    if ($names -contains 'document_path_exact') {
        $expectedPath = [string]$Job.preconditions.document_path_exact
        $actualPath = [string]$doc.path
        if (-not [string]::Equals(
            $expectedPath,
            $actualPath,
            [StringComparison]::OrdinalIgnoreCase
        )) {
            throw "Document path precondition failed. Expected='$expectedPath' Actual='$actualPath'."
        }
    }
}

function New-TerminalRecord {
    param(
        [string]$State,
        [string]$JobId,
        [string]$RequestSha256,
        [string]$RequestFileName,
        [string]$StartedUtc,
        [string]$FinishedUtc,
        $StatusEnvelope,
        $WorkerEnvelope,
        [string]$ErrorText
    )

    return [ordered]@{
        schema_version = 1
        runner_version = $RunnerVersion
        state = $State
        job_id = $JobId
        request_sha256 = $RequestSha256
        request_file_name = $RequestFileName
        started_utc = $StartedUtc
        finished_utc = $FinishedUtc
        status_observation = $StatusEnvelope
        worker_response = $WorkerEnvelope
        error = $ErrorText
        runner_write_authority = 'NONE'
    }
}

if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    throw "Config file not found: $ConfigPath"
}

$config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
if ([int]$config.schema_version -ne 1) {
    throw "Unsupported config schema_version '$($config.schema_version)'."
}

$queueRoot = [string]$config.queue_root
$workerExe = [string]$config.worker_exe
if (-not (Test-Path -LiteralPath $workerExe -PathType Leaf)) {
    throw "Native worker not found: $workerExe"
}

$dirs = @{}
foreach ($name in @(
    'incoming','processing','completed','failed','rejected','results','logs'
)) {
    $path = Join-Path $queueRoot $name
    [void](New-Item -ItemType Directory -Force -Path $path)
    $dirs[$name] = $path
}

$mutex = New-Object System.Threading.Mutex($false, [string]$config.poll_lock_name)
$hasMutex = $false

try {
    $hasMutex = $mutex.WaitOne(0)
    if (-not $hasMutex) {
        Write-Output 'Another CADGrounded queue runner instance is active. Exiting.'
        exit 0
    }

    $jobs = @(
        Get-ChildItem -LiteralPath $dirs['incoming'] -Filter '*.json' -File |
        Sort-Object LastWriteTimeUtc |
        Select-Object -First ([int]$config.max_jobs_per_run)
    )

    foreach ($incomingFile in $jobs) {
        $started = [DateTimeOffset]::UtcNow.ToString('o')
        $requestSha = $null
        $jobId = $null
        $processingPath = $null
        $logDir = Join-Path $dirs['logs'] ([DateTime]::UtcNow.ToString('yyyy-MM-dd'))
        [void](New-Item -ItemType Directory -Force -Path $logDir)

        try {
            if (($incomingFile.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'Reparse points / symlinks are not accepted in incoming.'
            }

            if ($incomingFile.Length -gt [int64]$config.max_job_bytes) {
                throw "Job exceeds max_job_bytes=$($config.max_job_bytes)."
            }

            $processingPath = Join-Path $dirs['processing'] $incomingFile.Name
            if (Test-Path -LiteralPath $processingPath) {
                throw "Processing collision for '$($incomingFile.Name)'."
            }

            Move-Item -LiteralPath $incomingFile.FullName -Destination $processingPath

            $requestSha = (Get-FileHash -LiteralPath $processingPath -Algorithm SHA256).Hash.ToLowerInvariant()
            $raw = Get-Content -LiteralPath $processingPath -Raw
            $job = $raw | ConvertFrom-Json

            [void](Assert-Job $job $config)
            $jobId = [string]$job.job_id

            foreach ($terminalDirName in @('completed','failed','rejected')) {
                $existingTerminal = Join-Path $dirs[$terminalDirName] "$jobId.job.json"
                if (Test-Path -LiteralPath $existingTerminal) {
                    throw "Replay detected: terminal request already exists for job_id '$jobId'."
                }
            }

            $statusStdout = Join-Path $logDir "$jobId.status.stdout.json"
            $statusStderr = Join-Path $logDir "$jobId.status.stderr.txt"
            $statusRequest = [ordered]@{
                command_id = 'sw.status'
                payload = [ordered]@{}
            }
            $statusResult = Invoke-WorkerJson -WorkerExe $workerExe -Request $statusRequest -StdoutPath $statusStdout -StderrPath $statusStderr
            if ($statusResult.ExitCode -ne 0 -or -not $statusResult.Envelope.ok) {
                throw "SOLIDWORKS status preflight failed. ExitCode=$($statusResult.ExitCode)."
            }
            if ([string]$statusResult.Envelope.data.write_authority -cne 'NONE') {
                throw 'Native worker status did not report write_authority NONE.'
            }

            Test-DocumentPreconditions $job $statusResult.Envelope

            $workerStdout = Join-Path $logDir "$jobId.worker.stdout.json"
            $workerStderr = Join-Path $logDir "$jobId.worker.stderr.txt"
            $workerRequest = [ordered]@{
                command_id = [string]$job.command_id
                payload = $job.payload
            }
            $workerResult = Invoke-WorkerJson -WorkerExe $workerExe -Request $workerRequest -StdoutPath $workerStdout -StderrPath $workerStderr

            $finished = [DateTimeOffset]::UtcNow.ToString('o')
            $state = if ($workerResult.ExitCode -eq 0 -and $workerResult.Envelope.ok) { 'completed' } else { 'failed' }
            $errorText = if ($state -eq 'completed') { $null } else { "Native worker command failed. ExitCode=$($workerResult.ExitCode)." }
            $terminal = New-TerminalRecord -State $state -JobId $jobId -RequestSha256 $requestSha -RequestFileName $incomingFile.Name -StartedUtc $started -FinishedUtc $finished -StatusEnvelope $statusResult.Envelope -WorkerEnvelope $workerResult.Envelope -ErrorText $errorText

            $resultPath = Join-Path $dirs['results'] "$jobId.result.json"
            Write-Utf8NoBom -Path $resultPath -Text ($terminal | ConvertTo-Json -Depth 50)

            $terminalRequestPath = Join-Path $dirs[$state] "$jobId.job.json"
            Move-Item -LiteralPath $processingPath -Destination $terminalRequestPath
            $processingPath = $null
        }
        catch {
            $finished = [DateTimeOffset]::UtcNow.ToString('o')
            $errorText = $_.Exception.Message
            if ([string]::IsNullOrWhiteSpace($jobId)) {
                $jobId = [IO.Path]::GetFileNameWithoutExtension([IO.Path]::GetFileNameWithoutExtension($incomingFile.Name))
                if ([string]::IsNullOrWhiteSpace($jobId)) { $jobId = 'unknown' }
            }
            if ([string]::IsNullOrWhiteSpace($requestSha) -and $processingPath -and (Test-Path -LiteralPath $processingPath)) {
                $requestSha = (Get-FileHash -LiteralPath $processingPath -Algorithm SHA256).Hash.ToLowerInvariant()
            }

            $terminal = New-TerminalRecord -State 'rejected' -JobId $jobId -RequestSha256 $requestSha -RequestFileName $incomingFile.Name -StartedUtc $started -FinishedUtc $finished -StatusEnvelope $null -WorkerEnvelope $null -ErrorText $errorText
            $resultPath = Join-Path $dirs['results'] "$jobId.result.json"
            Write-Utf8NoBom -Path $resultPath -Text ($terminal | ConvertTo-Json -Depth 50)

            if ($processingPath -and (Test-Path -LiteralPath $processingPath)) {
                $rejectedPath = Join-Path $dirs['rejected'] "$jobId.job.json"
                if (Test-Path -LiteralPath $rejectedPath) {
                    $rejectedPath = Join-Path $dirs['rejected'] ("$jobId." + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '.job.json')
                }
                Move-Item -LiteralPath $processingPath -Destination $rejectedPath
                $processingPath = $null
            }
        }
    }
}
finally {
    if ($hasMutex) { [void]$mutex.ReleaseMutex() }
    $mutex.Dispose()
}
