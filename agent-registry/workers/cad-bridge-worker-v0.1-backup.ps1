<#
.SYNOPSIS
    Read-only CADGrounded SOLIDWORKS bridge worker.

.DESCRIPTION
    Polls the local CAD Agent Registry for queued READ jobs, claims them as
    solidworks-bridge-01, calls the local CADGrounded MCP endpoint, and posts
    the result back to the registry.

    HARD ALLOWLIST:
      sw.status
      sw.query_components

    This script will NOT execute:
      sw.set_transform
      sw.insert_component
      sw.execute_code

    Default endpoints:
      Registry: http://127.0.0.1:18181
      MCP:      http://127.0.0.1:8765/mcp

.PARAMETER Once
    Process at most one queued allowed job, then exit.

.PARAMETER PollSeconds
    Delay between polls when no eligible job exists.

.PARAMETER RegistryUrl
    CAD Agent Registry base URL.

.PARAMETER McpUrl
    CADGrounded MCP URL.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File C:\ChatGPT\cad-bridge-worker.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File C:\ChatGPT\cad-bridge-worker.ps1 -Once
#>

[CmdletBinding()]
param(
    [string]$RegistryUrl = "http://127.0.0.1:18181",
    [string]$McpUrl = "http://127.0.0.1:8765/mcp",
    [string]$BridgeAgentId = "solidworks-bridge-01",
    [int]$PollSeconds = 2,
    [switch]$Once
)

$ErrorActionPreference = "Stop"

$AllowedRegistryCommands = @{
    "sw.status" = "sw_status"
    "sw.query_components" = "sw_query_components"
}

$Headers = @{
    Accept = "application/json, text/event-stream"
}

function Write-Log {
    param(
        [string]$Message,
        [ValidateSet("INFO","PASS","WARN","FAIL")]
        [string]$Level = "INFO"
    )

    $ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $color = switch ($Level) {
        "PASS" { "Green" }
        "WARN" { "Yellow" }
        "FAIL" { "Red" }
        default { "Cyan" }
    }

    Write-Host "[$ts][$Level] $Message" -ForegroundColor $color
}

function Convert-SseToObject {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Content
    )

    # MCP server currently returns:
    #   event: message
    #   data: {...json...}
    #
    # Support multiple data: lines just in case.
    $dataLines = @()

    foreach ($line in ($Content -split "`r?`n")) {
        if ($line -match '^data:\s?(.*)$') {
            $dataLines += $Matches[1]
        }
    }

    if ($dataLines.Count -eq 0) {
        throw "MCP response contained no SSE data payload. Raw response: $Content"
    }

    $jsonText = ($dataLines -join "`n").Trim()

    if ([string]::IsNullOrWhiteSpace($jsonText)) {
        throw "MCP SSE data payload was empty."
    }

    return ($jsonText | ConvertFrom-Json)
}

function Invoke-McpRpc {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Method,

        [Parameter(Mandatory=$true)]
        [object]$Params,

        [int]$Id = 1
    )

    $body = @{
        jsonrpc = "2.0"
        id = $Id
        method = $Method
        params = $Params
    } | ConvertTo-Json -Depth 100 -Compress

    $r = Invoke-WebRequest `
        -Uri $McpUrl `
        -Method Post `
        -ContentType "application/json" `
        -Headers $Headers `
        -Body $body `
        -UseBasicParsing `
        -TimeoutSec 30

    if ($r.StatusCode -lt 200 -or $r.StatusCode -ge 300) {
        throw "MCP HTTP failure: status $($r.StatusCode)"
    }

    $obj = Convert-SseToObject -Content $r.Content

    if ($null -ne $obj.error) {
        $err = $obj.error | ConvertTo-Json -Depth 20 -Compress
        throw "MCP JSON-RPC error: $err"
    }

    return $obj
}

function Send-McpNotification {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Method,

        [object]$Params = @{}
    )

    $body = @{
        jsonrpc = "2.0"
        method = $Method
        params = $Params
    } | ConvertTo-Json -Depth 50 -Compress

    try {
        # Notifications may produce an empty success response, 202, or an SSE body.
        Invoke-WebRequest `
            -Uri $McpUrl `
            -Method Post `
            -ContentType "application/json" `
            -Headers $Headers `
            -Body $body `
            -UseBasicParsing `
            -TimeoutSec 10 | Out-Null
    } catch {
        # Some minimal MCP servers do not require notifications/initialized.
        Write-Log "MCP notification '$Method' was not accepted; continuing because direct tool calls are supported. $($_.Exception.Message)" "WARN"
    }
}

function Test-Registry {
    $health = Invoke-RestMethod -Uri "$RegistryUrl/health" -TimeoutSec 5
    if (-not $health.ok) {
        throw "Registry health check returned ok=false."
    }
    Write-Log "Registry healthy: $RegistryUrl" "PASS"
}

function Register-BridgeHeartbeat {
    $body = @{
        id = $BridgeAgentId
        role = "bridge"
        capabilities = @(
            "claim-read-jobs",
            "return-results",
            "mcp:sw_status",
            "mcp:sw_query_components"
        )
    } | ConvertTo-Json -Depth 10

    Invoke-RestMethod `
        -Uri "$RegistryUrl/agents/heartbeat" `
        -Method Post `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 5 | Out-Null
}

function Initialize-Mcp {
    Write-Log "Initializing MCP at $McpUrl"

    $init = Invoke-McpRpc `
        -Method "initialize" `
        -Id 1 `
        -Params @{
            protocolVersion = "2025-06-18"
            capabilities = @{}
            clientInfo = @{
                name = "cad-registry-bridge-worker"
                version = "0.1.0"
            }
        }

    if ($null -eq $init.result) {
        throw "MCP initialize returned no result."
    }

    Write-Log "MCP initialized: $($init.result.serverInfo.name) v$($init.result.serverInfo.version), protocol $($init.result.protocolVersion)" "PASS"

    Send-McpNotification -Method "notifications/initialized" -Params @{}

    $tools = Invoke-McpRpc -Method "tools/list" -Id 2 -Params @{}
    $toolNames = @($tools.result.tools | ForEach-Object { $_.name })

    foreach ($required in @("sw_status", "sw_query_components")) {
        if ($toolNames -notcontains $required) {
            throw "Required MCP tool is missing: $required"
        }
    }

    Write-Log "Required read-only MCP tools discovered." "PASS"
}

function Get-QueuedJobs {
    $jobs = Invoke-RestMethod `
        -Uri "$RegistryUrl/jobs?state=queued&limit=100" `
        -Method Get `
        -TimeoutSec 5

    if ($null -eq $jobs) {
        return @()
    }

    return @($jobs)
}

function Claim-Job {
    param(
        [Parameter(Mandatory=$true)]
        [string]$JobId
    )

    $body = @{
        bridge_agent_id = $BridgeAgentId
    } | ConvertTo-Json

    return Invoke-RestMethod `
        -Uri "$RegistryUrl/jobs/$JobId/claim" `
        -Method Post `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 5
}

function Complete-Job {
    param(
        [Parameter(Mandatory=$true)]
        [string]$JobId,

        [Parameter(Mandatory=$true)]
        [hashtable]$Output
    )

    $body = @{
        bridge_agent_id = $BridgeAgentId
        success = $true
        output = $Output
    } | ConvertTo-Json -Depth 100

    Invoke-RestMethod `
        -Uri "$RegistryUrl/jobs/$JobId/result" `
        -Method Post `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 10 | Out-Null
}

function Fail-Job {
    param(
        [Parameter(Mandatory=$true)]
        [string]$JobId,

        [Parameter(Mandatory=$true)]
        [string]$ErrorMessage,

        [hashtable]$Output = @{}
    )

    $body = @{
        bridge_agent_id = $BridgeAgentId
        success = $false
        output = $Output
        error = $ErrorMessage
    } | ConvertTo-Json -Depth 100

    try {
        Invoke-RestMethod `
            -Uri "$RegistryUrl/jobs/$JobId/result" `
            -Method Post `
            -ContentType "application/json" `
            -Body $body `
            -TimeoutSec 10 | Out-Null
    } catch {
        Write-Log "Could not mark job $JobId failed: $($_.Exception.Message)" "FAIL"
    }
}

function Invoke-AllowedCadTool {
    param(
        [Parameter(Mandatory=$true)]
        [object]$Job
    )

    $registryCommand = [string]$Job.command_id

    if (-not $AllowedRegistryCommands.ContainsKey($registryCommand)) {
        throw "POLICY_BLOCK: command is not on worker allowlist: $registryCommand"
    }

    $mcpTool = $AllowedRegistryCommands[$registryCommand]

    $arguments = @{}

    switch ($registryCommand) {
        "sw.status" {
            $arguments = @{}
        }

        "sw.query_components" {
            # Only one parameter is accepted from the registry payload.
            # Everything else is deliberately ignored.
            $topLevelOnly = $true

            if ($null -ne $Job.payload -and $null -ne $Job.payload.top_level_only) {
                $topLevelOnly = [bool]$Job.payload.top_level_only
            }

            $arguments = @{
                top_level_only = $topLevelOnly
            }
        }

        default {
            throw "POLICY_BLOCK: unsupported command: $registryCommand"
        }
    }

    Write-Log "Calling MCP tool '$mcpTool' for job $($Job.id)"

    $rpc = Invoke-McpRpc `
        -Method "tools/call" `
        -Id 100 `
        -Params @{
            name = $mcpTool
            arguments = $arguments
        }

    if ($null -eq $rpc.result) {
        throw "MCP tools/call returned no result."
    }

    if ($rpc.result.isError -eq $true) {
        $raw = $rpc.result | ConvertTo-Json -Depth 100 -Compress
        throw "MCP tool reported isError=true: $raw"
    }

    # Prefer structuredContent because it is already machine-readable.
    $structured = $rpc.result.structuredContent

    if ($null -ne $structured -and $null -ne $structured.ok -and $structured.ok -eq $false) {
        $raw = $structured | ConvertTo-Json -Depth 100 -Compress
        throw "CADGrounded returned ok=false: $raw"
    }

    $mcpResult = $rpc.result | ConvertTo-Json -Depth 100 | ConvertFrom-Json

    return @{
        source = "cadgrounded-mcp"
        mcp_endpoint = $McpUrl
        registry_command = $registryCommand
        mcp_tool = $mcpTool
        result = $mcpResult
    }
}

function Process-OneJob {
    $queued = Get-QueuedJobs

    $eligible = @(
        $queued |
            Where-Object { $AllowedRegistryCommands.ContainsKey([string]$_.command_id) } |
            Sort-Object created_at
    )

    if ($eligible.Count -eq 0) {
        return $false
    }

    $job = $eligible[0]

    try {
        $claimed = Claim-Job -JobId $job.id
    } catch {
        # Another worker may have won the compare-and-set claim.
        Write-Log "Could not claim job $($job.id); it may have been claimed by another worker. $($_.Exception.Message)" "WARN"
        return $false
    }

    Write-Log "Claimed $($claimed.command_id) job $($claimed.id)" "PASS"

    try {
        $output = Invoke-AllowedCadTool -Job $claimed
        Complete-Job -JobId $claimed.id -Output $output
        Write-Log "Completed job $($claimed.id)" "PASS"
    } catch {
        $message = $_.Exception.Message
        Write-Log "Job $($claimed.id) failed: $message" "FAIL"

        Fail-Job `
            -JobId $claimed.id `
            -ErrorMessage $message `
            -Output @{
                source = "cadgrounded-mcp"
                registry_command = [string]$claimed.command_id
                policy = "read-only-worker-v0.1"
            }
    }

    return $true
}

# --------------------------------------------------------------------
# Startup
# --------------------------------------------------------------------

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " CADGrounded Read-Only Registry Bridge Worker v0.1" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Registry : $RegistryUrl"
Write-Host "MCP      : $McpUrl"
Write-Host "Agent    : $BridgeAgentId"
Write-Host ""
Write-Host "Allowed:"
Write-Host "  sw.status"
Write-Host "  sw.query_components"
Write-Host ""
Write-Host "Hard blocked:"
Write-Host "  sw.set_transform"
Write-Host "  sw.insert_component"
Write-Host "  sw.execute_code"
Write-Host ""

Test-Registry
Register-BridgeHeartbeat
Initialize-Mcp

Write-Log "Worker ready." "PASS"

$lastHeartbeat = Get-Date

while ($true) {
    try {
        if (((Get-Date) - $lastHeartbeat).TotalSeconds -ge 15) {
            Register-BridgeHeartbeat
            $lastHeartbeat = Get-Date
        }

        $processed = Process-OneJob

        if ($Once) {
            if (-not $processed) {
                Write-Log "No eligible queued job found." "INFO"
            }
            break
        }

        if (-not $processed) {
            Start-Sleep -Seconds $PollSeconds
        }
    } catch {
        Write-Log $_.Exception.Message "FAIL"

        if ($Once) {
            throw
        }

        Start-Sleep -Seconds ([Math]::Max(2, $PollSeconds))
    }
}

Write-Log "Worker stopped." "INFO"
