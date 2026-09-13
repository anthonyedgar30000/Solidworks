#Requires -Version 5.1
<#
.SYNOPSIS
    Print the input schema for one local CADGrounded MCP tool without executing it.
.DESCRIPTION
    Connects only to the local MCP endpoint, performs initialize + tools/list,
    and prints the selected tool metadata. It does not submit registry jobs,
    call tools/call, or execute any SOLIDWORKS operation.
.EXAMPLE
    .\cad-mcp-tool-schema.ps1 -ToolName sw_execute_code
#>
[CmdletBinding()]
param(
    [string]$ToolName = 'sw_execute_code',
    [string]$McpUrl = 'http://127.0.0.1:8765/mcp'
)

$ErrorActionPreference = 'Stop'
$headers = @{ Accept = 'application/json, text/event-stream' }

function Convert-SseToObject {
    param([Parameter(Mandatory=$true)][string]$Content)
    $dataLines = @()
    foreach ($line in ($Content -split "`r?`n")) {
        if ($line -match '^data:\s?(.*)$') { $dataLines += $Matches[1] }
    }
    if ($dataLines.Count -eq 0) {
        throw 'MCP response contained no SSE data payload.'
    }
    (($dataLines -join "`n").Trim()) | ConvertFrom-Json
}

function Invoke-McpRpc {
    param(
        [Parameter(Mandatory=$true)][string]$Method,
        [Parameter(Mandatory=$true)][object]$Params,
        [int]$Id = 1
    )
    $body = @{
        jsonrpc = '2.0'
        id = $Id
        method = $Method
        params = $Params
    } | ConvertTo-Json -Depth 100 -Compress

    $r = Invoke-WebRequest -Uri $McpUrl -Method Post `
        -ContentType 'application/json' -Headers $headers -Body $body `
        -UseBasicParsing -TimeoutSec 30

    if ($r.StatusCode -lt 200 -or $r.StatusCode -ge 300) {
        throw "MCP HTTP failure: status $($r.StatusCode)"
    }
    $obj = Convert-SseToObject -Content $r.Content
    if ($null -ne $obj.error) {
        throw ('MCP JSON-RPC error: ' + ($obj.error | ConvertTo-Json -Depth 20 -Compress))
    }
    $obj
}

$init = Invoke-McpRpc -Method 'initialize' -Id 1 -Params @{
    protocolVersion = '2025-06-18'
    capabilities = @{}
    clientInfo = @{ name = 'cad-mcp-tool-schema'; version = '0.1.0' }
}

$tools = Invoke-McpRpc -Method 'tools/list' -Id 2 -Params @{}
$match = @($tools.result.tools | Where-Object { $_.name -ceq $ToolName })

if ($match.Count -ne 1) {
    $names = @($tools.result.tools | ForEach-Object { $_.name }) -join ', '
    throw "Tool '$ToolName' not found exactly once. Available tools: $names"
}

[pscustomobject][ordered]@{
    server_name = $init.result.serverInfo.name
    server_version = $init.result.serverInfo.version
    protocol = $init.result.protocolVersion
    tool_name = $match[0].name
    description = $match[0].description
    input_schema = $match[0].inputSchema
} | ConvertTo-Json -Depth 100
