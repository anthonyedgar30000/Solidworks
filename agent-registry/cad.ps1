#Requires -Version 5.1
<#
.SYNOPSIS
    Short read-only commands for the existing local CAD Agent Registry worker.
.DESCRIPTION
    Talks only to http://127.0.0.1:18181. Uses the registry contract from
    Solidworks commit 14e0902. Does not start a worker, call the CAD bridge
    directly, enable CAD writes, alter execution policy, or call an LLM.

    The existing registry, bridge worker, CADGrounded server, and SOLIDWORKS
    must be running for new status/components jobs. Stored results need only
    the registry. Results are timestamped snapshots, not mechanical approval.

    A timeout stops this client waiting; it does not cancel the queued job.
    No job submission is retried automatically. Use result/jobs to inspect
    existing work before submitting a replacement.
.EXAMPLE
    .\cad.ps1 status
.EXAMPLE
    .\cad.ps1 components
.EXAMPLE
    .\cad.ps1 components -AllLevels -Json
.EXAMPLE
    .\cad.ps1 result db3b2247-315d-4b01-a379-a483f417deaa
.EXAMPLE
    .\cad.ps1 jobs
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('help', 'status', 'components', 'result', 'jobs')]
    [string]$Command = 'help',

    [Parameter(Position = 1)]
    [string]$JobId,

    [ValidateRange(1, 120)]
    [int]$WaitSeconds = 30,

    [switch]$AllLevels,
    [switch]$Json
)

$ErrorActionPreference = 'Stop'
$cadRegistry = 'http://127.0.0.1:18181'

if ($Command -eq 'help') {
    @'
Local CAD read commands (use the existing running worker):
  .\cad.ps1 status                 Queue an active-document read
  .\cad.ps1 components             Queue a top-level component read
  .\cad.ps1 components -AllLevels   Include nested components
  .\cad.ps1 components -Json        Return one JSON snapshot
  .\cad.ps1 result <job-id>         Retrieve a stored snapshot; no CAD call
  .\cad.ps1 jobs                   List the 20 most recent registry jobs

Options: -WaitSeconds 30, -Json, -Verbose
CAD writes and arbitrary code execution are not exposed by this helper.
'@
    return
}

if ($JobId -and $Command -ne 'result') {
    throw 'A job ID is accepted only with the result command.'
}
if ($AllLevels -and $Command -ne 'components') {
    throw '-AllLevels is accepted only with the components command.'
}

function Invoke-CadRegistry {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Route,
        [ValidateSet('Get', 'Post')]
        [string]$Method = 'Get',
        [hashtable]$Payload
    )

    $request = @{
        Uri                = $cadRegistry + $Route
        Method             = $Method
        TimeoutSec         = 5
        MaximumRedirection = 0
    }
    if ($Method -eq 'Post') {
        $request.ContentType = 'application/json; charset=utf-8'
        $request.Body = [System.Text.Encoding]::UTF8.GetBytes(
            ($Payload | ConvertTo-Json -Depth 10 -Compress)
        )
    }
    $response = Invoke-RestMethod @request
    return $response
}

if ($Command -eq 'jobs') {
    $items = @(Invoke-CadRegistry -Route '/jobs?limit=20')
    $rows = @($items | Select-Object id, command_id, state, claimed_by,
        agent_id, idempotency_key, created_at, updated_at, error_text)
    if ($Json) {
        ConvertTo-Json -InputObject $rows -Depth 10 -Compress
    } else {
        $rows | Format-List
    }
    return
}

if ($Command -eq 'result') {
    $parsedJobId = [guid]::Empty
    if (-not [guid]::TryParse($JobId, [ref]$parsedJobId)) {
        throw 'Use: .\cad.ps1 result <valid-job-id>'
    }
    $job = Invoke-CadRegistry -Route ('/jobs/' + $parsedJobId.ToString())
} else {
    # Each new invocation is distinct. Never silently reuse another request.
    $requestKey = 'cad-cli-' + [guid]::NewGuid().ToString('N')
    $agentId = 'human-' + $requestKey
    Invoke-CadRegistry -Route '/agents/heartbeat' -Method Post -Payload @{
        id = $agentId
        role = 'human'
        capabilities = @('cad.read')
    } | Out-Null

    $registryCommand = 'sw.status'
    $arguments = @{}
    if ($Command -eq 'components') {
        $registryCommand = 'sw.query_components'
        $arguments = @{ top_level_only = (-not $AllLevels.IsPresent) }
    }

    try {
        $job = Invoke-CadRegistry -Route '/jobs' -Method Post -Payload @{
            command_id = $registryCommand
            agent_id = $agentId
            payload = $arguments
            idempotency_key = $requestKey
        }
    } catch {
        throw "Submission could not be confirmed. Request key: $requestKey. Run .\cad.ps1 jobs and inspect this key before submitting again. $($_.Exception.Message)"
    }

    $submittedId = [string]$job.id
    if ([string]::IsNullOrWhiteSpace($submittedId)) {
        throw "Registry response has no job ID. Inspect .\cad.ps1 jobs for request key $requestKey; do not resubmit yet."
    }
    Write-Verbose "Submitted job $submittedId. Request key: $requestKey"

    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        while ($job.state -in @('queued', 'running')) {
            if ($watch.Elapsed.TotalSeconds -ge $WaitSeconds) {
                break
            }
            Start-Sleep -Milliseconds 500
            $job = Invoke-CadRegistry -Route ('/jobs/' + $submittedId)
        }
    } catch {
        throw "Could not read job $submittedId. The job may still be running. Recover with .\cad.ps1 result $submittedId. $($_.Exception.Message)"
    } finally {
        $watch.Stop()
    }
    if ($job.state -ne 'completed') {
        throw "Job $submittedId is $($job.state). $($job.error_text) No retry or cancellation was sent. Inspect with .\cad.ps1 result $submittedId."
    }
}

if ($job.command_id -notin @('sw.status', 'sw.query_components')) {
    throw 'This helper displays only status and component-read results.'
}

$snapshot = [ordered]@{
    job_id = $job.id
    command = $job.command_id
    state = $job.state
    worker = $job.claimed_by
    recorded_at = $job.updated_at
    error = $job.error_text
}

if ($job.state -ne 'completed') {
    # Explicit result retrieval reports pending/failed jobs without executing.
    if ($Json) {
        $snapshot | ConvertTo-Json -Depth 10 -Compress
    } else {
        [pscustomobject]$snapshot | Format-List
    }
    return
}

$mcpResult = $job.result.result
$envelope = $mcpResult.structuredContent
if ($mcpResult.isError -eq $true -or $null -eq $envelope -or $envelope.ok -ne $true -or $null -eq $envelope.result) {
    throw "Job $($job.id) has no successful structured CAD result. The registry completed flag alone is insufficient."
}
$data = $envelope.result
if ($job.command_id -eq 'sw.query_components' -and $null -eq $data.components) {
    throw "Job $($job.id) has no components field; count is unknown."
}
if ($job.command_id -eq 'sw.status' -and $data.PSObject.Properties.Name -notcontains 'active_document') {
    throw "Job $($job.id) has no active_document field."
}
$snapshot['data'] = $data

if ($Json) {
    $snapshot | ConvertTo-Json -Depth 100 -Compress
    return
}

$summary = [ordered]@{
    Job = $job.id
    State = $job.state
    Worker = $job.claimed_by
    RecordedAt = $job.updated_at
}
if ($job.command_id -eq 'sw.status') {
    $summary['Document'] = $data.active_document.title
    $summary['Path'] = $data.active_document.path
    $summary['Type'] = $data.active_document.document_type
    $summary['Bridge'] = $data.bridge_version
} else {
    $summary['Document'] = $data.document_title
    $summary['Components'] = @($data.components).Count
}
[pscustomobject]$summary | Format-List

if ($job.command_id -eq 'sw.query_components') {
    $data.components | Select-Object name2, fixed, suppressed | Format-Table -AutoSize
}
