#Requires -Version 5.1
<#
.SYNOPSIS
    Compile-only preflight for the fixed read-only pair interference checker.
.DESCRIPTION
    Talks directly to the local CADGrounded MCP endpoint. It reads sw_status,
    then submits one fixed C# interference checker to sw_execute_code with
    apply=false. The C# is compiled only; it is NOT executed.

    The only caller-supplied values are two component-name substrings. They are
    embedded as escaped C# string literals and are used only for Component2.Name2
    matching inside the fixed source. No caller-supplied code is accepted.

    This utility exists to validate the exact SOLIDWORKS interop syntax and to
    inspect the bridge preflight-token response before the registry worker gains
    a fixed sw.check_interference_pair read operation.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidateLength(1,128)]
    [string]$ANameContains,

    [Parameter(Mandatory=$true)]
    [ValidateLength(1,128)]
    [string]$BNameContains,

    [string]$McpUrl = 'http://127.0.0.1:8765/mcp'
)

$ErrorActionPreference = 'Stop'
$headers = @{ Accept = 'application/json, text/event-stream' }

function Convert-SseToObject {
    param([Parameter(Mandatory=$true)][string]$Content)
    $data = @()
    foreach ($line in ($Content -split "`r?`n")) {
        if ($line -match '^data:\s?(.*)$') { $data += $Matches[1] }
    }
    if ($data.Count -eq 0) { throw 'MCP response contained no SSE data payload.' }
    return (($data -join "`n") | ConvertFrom-Json -ErrorAction Stop)
}

function Invoke-McpRpc {
    param(
        [Parameter(Mandatory=$true)][string]$Method,
        [Parameter(Mandatory=$true)][object]$Params,
        [int]$Id = 1
    )
    $body = @{
        jsonrpc = '2.0'; id = $Id; method = $Method; params = $Params
    } | ConvertTo-Json -Depth 100 -Compress
    $r = Invoke-WebRequest -Uri $McpUrl -Method Post -ContentType 'application/json' `
        -Headers $headers -Body $body -UseBasicParsing -TimeoutSec 30
    $obj = Convert-SseToObject -Content $r.Content
    if ($null -ne $obj.error) {
        throw ('MCP JSON-RPC error: ' + ($obj.error | ConvertTo-Json -Depth 20 -Compress))
    }
    return $obj
}

function Escape-CSharpStringLiteral {
    param([Parameter(Mandatory=$true)][string]$Value)
    return $Value.Replace('\','\\').Replace('"','\"').Replace("`r",'\r').Replace("`n",'\n')
}

$init = Invoke-McpRpc -Method 'initialize' -Id 1 -Params @{
    protocolVersion = '2025-06-18'
    capabilities = @{}
    clientInfo = @{ name='cad-interference-preflight'; version='0.1.0' }
}

$tools = Invoke-McpRpc -Method 'tools/list' -Id 2 -Params @{}
$toolNames = @($tools.result.tools | ForEach-Object { $_.name })
foreach ($required in @('sw_status','sw_execute_code')) {
    if ($toolNames -notcontains $required) { throw "Required MCP tool is missing: $required" }
}

$statusRpc = Invoke-McpRpc -Method 'tools/call' -Id 3 -Params @{
    name = 'sw_status'
    arguments = @{}
}
$statusEnvelope = $statusRpc.result.structuredContent
if ($null -eq $statusEnvelope -or $statusEnvelope.ok -ne $true -or $null -eq $statusEnvelope.result.active_document) {
    throw 'sw_status did not return a successful active-document result.'
}
$doc = $statusEnvelope.result.active_document
if ([string]::IsNullOrWhiteSpace([string]$doc.title)) { throw 'Active document has no title.' }
if ([string]$doc.document_type -notmatch '(?i)assembly') { throw 'Active document is not an assembly.' }

$aLiteral = Escape-CSharpStringLiteral -Value $ANameContains
$bLiteral = Escape-CSharpStringLiteral -Value $BNameContains

$source = @"
using System;
using System.Collections;
using System.Collections.Generic;
using SolidWorks.Interop.sldworks;

public static class BridgeScript
{
    public static object Run(SldWorks app)
    {
        const string aNeedle = \"$aLiteral\";
        const string bNeedle = \"$bLiteral\";

        ModelDoc2 model = app.ActiveDoc as ModelDoc2;
        if (model == null)
            return new Dictionary<string, object> { { \"ok\", false }, { \"error\", \"no_active_document\" } };

        AssemblyDoc asm = model as AssemblyDoc;
        if (asm == null)
            return new Dictionary<string, object> { { \"ok\", false }, { \"error\", \"active_document_not_assembly\" } };

        object rawComponents = asm.GetComponents(true);
        Array components = rawComponents as Array;
        if (components == null)
            return new Dictionary<string, object> { { \"ok\", false }, { \"error\", \"components_unavailable\" } };

        Component2 a = null;
        Component2 b = null;
        int aMatches = 0;
        int bMatches = 0;

        foreach (object item in components)
        {
            Component2 c = item as Component2;
            if (c == null) continue;
            string name = c.Name2 ?? string.Empty;
            if (name.IndexOf(aNeedle, StringComparison.OrdinalIgnoreCase) >= 0) { a = c; aMatches++; }
            if (name.IndexOf(bNeedle, StringComparison.OrdinalIgnoreCase) >= 0) { b = c; bMatches++; }
        }

        if (aMatches != 1 || bMatches != 1)
            return new Dictionary<string, object> {
                { \"ok\", false }, { \"error\", \"component_match_not_unique\" },
                { \"a_matches\", aMatches }, { \"b_matches\", bMatches }
            };

        object interferingComponents;
        object interferingFaces;
        object[] pair = new object[] { a, b };

        // CoincidentInterference=true lets us distinguish coincidence/touch from
        // a clear pair. Intersecting faces indicate actual geometric intersection.
        asm.ToolsCheckInterference2(2, pair, true, out interferingComponents, out interferingFaces);

        Array compArray = interferingComponents as Array;
        Array faceArray = interferingFaces as Array;
        int compCount = compArray == null ? 0 : compArray.Length;
        int faceCount = faceArray == null ? 0 : faceArray.Length;

        string classification = \"clear\";
        if (compCount > 0 && faceCount == 0) classification = \"touching_or_coincident\";
        if (faceCount > 0) classification = \"intersecting\";

        return new Dictionary<string, object> {
            { \"ok\", true },
            { \"source_classification\", \"verified_from_solidworks_api\" },
            { \"api\", \"IAssemblyDoc.ToolsCheckInterference2\" },
            { \"component_a\", a.Name2 },
            { \"component_b\", b.Name2 },
            { \"classification\", classification },
            { \"interfering_component_entries\", compCount },
            { \"intersecting_face_entries\", faceCount },
            { \"coincident_interference_enabled\", true }
        };
    }
}
"@

$preflight = Invoke-McpRpc -Method 'tools/call' -Id 4 -Params @{
    name = 'sw_execute_code'
    arguments = @{
        source = $source
        expected_document_title = [string]$doc.title
        expected_document_path = [string]$doc.path
        apply = $false
    }
}

[pscustomobject][ordered]@{
    mode = 'compile_only_no_execution'
    document_title = [string]$doc.title
    document_path = [string]$doc.path
    component_a_contains = $ANameContains
    component_b_contains = $BNameContains
    mcp_result = $preflight.result
} | ConvertTo-Json -Depth 100
