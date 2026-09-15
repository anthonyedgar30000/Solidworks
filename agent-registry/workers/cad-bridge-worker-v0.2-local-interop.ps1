<#
.SYNOPSIS
    Read-only local SOLIDWORKS bridge worker for the CAD Agent Registry.

.DESCRIPTION
    Polls the local CAD Agent Registry for queued READ jobs, claims them as
    solidworks-bridge-01, executes the supported SOLIDWORKS reads locally
    through compiled C# + SolidWorks.Interop.sldworks.ISldWorks, and posts
    results back to the registry.

    This version DOES NOT call MCP for CAD execution.

    HARD ALLOWLIST:
      sw.status
      sw.query_components

    HARD BLOCKED:
      sw.set_transform
      sw.insert_component
      sw.execute_code
      and every other unregistered command

    IMPORTANT:
      Run this worker at the same Windows integrity level as the SOLIDWORKS GUI.
      In the current setup SOLIDWORKS is non-elevated, so run this worker from
      a normal, non-Administrator PowerShell window.

.PARAMETER RegistryUrl
    CAD Agent Registry base URL.

.PARAMETER McpUrl
    Retained only for backward-compatible launch scripts. Ignored by v0.2.

.PARAMETER BridgeAgentId
    Registry identity used by this worker.

.PARAMETER PollSeconds
    Delay between polls when no eligible job exists.

.PARAMETER SolidWorksRoot
    Installed SOLIDWORKS program directory containing
    SolidWorks.Interop.sldworks.dll.

.PARAMETER Once
    Process at most one queued allowed job, then exit.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File `
      C:\ChatGPT\Solidworks\agent-registry\workers\cad-bridge-worker.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File `
      C:\ChatGPT\Solidworks\agent-registry\workers\cad-bridge-worker.ps1 -Once
#>

[CmdletBinding()]
param(
    [string]$RegistryUrl = "http://127.0.0.1:18181",

    # Kept so old launch commands do not break. This worker no longer uses MCP.
    [string]$McpUrl = "",

    [string]$BridgeAgentId = "solidworks-bridge-01",

    [int]$PollSeconds = 2,

    [string]$SolidWorksRoot = "C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS",

    [switch]$Once
)

$ErrorActionPreference = "Stop"

$AllowedRegistryCommands = @{
    "sw.status"           = $true
    "sw.query_components" = $true
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

function Test-IsAdministrator {
    $principal = [Security.Principal.WindowsPrincipal](
        [Security.Principal.WindowsIdentity]::GetCurrent()
    )

    return $principal.IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )
}

function Test-Registry {
    $health = Invoke-RestMethod `
        -Uri "$RegistryUrl/health" `
        -TimeoutSec 5

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
            "local-interop:sw.status",
            "local-interop:sw.query_components"
        )
    } | ConvertTo-Json -Depth 10

    Invoke-RestMethod `
        -Uri "$RegistryUrl/agents/heartbeat" `
        -Method Post `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 5 | Out-Null
}

function Initialize-SolidWorksInterop {
    $swDll = Join-Path $SolidWorksRoot "SolidWorks.Interop.sldworks.dll"

    if (-not (Test-Path -LiteralPath $swDll)) {
        throw "SOLIDWORKS interop DLL not found: $swDll"
    }

    if ($McpUrl) {
        Write-Log "McpUrl was supplied but is ignored by local-interop worker v0.2." "WARN"
    }

    $isAdmin = Test-IsAdministrator

    if ($isAdmin) {
        Write-Log "Worker is elevated. Your running SOLIDWORKS GUI was previously non-elevated; GetActiveObject may fail across that integrity boundary." "WARN"
    } else {
        Write-Log "Worker is non-elevated, matching the tested SOLIDWORKS GUI context." "PASS"
    }

    if (-not ("CadLocalBridge2026" -as [type])) {
        Write-Log "Compiling typed SOLIDWORKS C# interop adapter."

        $source = @'
using System;
using System.Collections;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using SolidWorks.Interop.sldworks;

public static class CadLocalBridge2026
{
    private const int SW_DOC_PART = 1;
    private const int SW_DOC_ASSEMBLY = 2;
    private const int SW_DOC_DRAWING = 3;

    private static ISldWorks GetApp()
    {
        object raw;

        try
        {
            raw = Marshal.GetActiveObject("SldWorks.Application");
        }
        catch (COMException ex)
        {
            throw new InvalidOperationException(
                "Could not attach to the running SOLIDWORKS instance. " +
                "Make sure SOLIDWORKS is open and this worker runs at the same " +
                "Windows integrity level as SOLIDWORKS. COM: " + ex.Message,
                ex
            );
        }

        try
        {
            return (ISldWorks)raw;
        }
        catch (Exception ex)
        {
            throw new InvalidOperationException(
                "Attached to the COM object but could not query ISldWorks. " +
                ex.Message,
                ex
            );
        }
    }

    private static string DocumentTypeName(int typeId)
    {
        switch (typeId)
        {
            case SW_DOC_PART:
                return "part";
            case SW_DOC_ASSEMBLY:
                return "assembly";
            case SW_DOC_DRAWING:
                return "drawing";
            default:
                return "unknown";
        }
    }

    private static double[] ToDoubleArray(object raw)
    {
        if (raw == null)
            return null;

        Array array = raw as Array;

        if (array == null)
            return null;

        double[] values = new double[array.Length];

        for (int i = 0; i < array.Length; i++)
            values[i] = Convert.ToDouble(array.GetValue(i));

        return values;
    }

    private static double[] Slice(double[] values, int start, int count)
    {
        if (values == null || start < 0 || count < 0 || start + count > values.Length)
            return null;

        double[] result = new double[count];

        Array.Copy(values, start, result, 0, count);

        return result;
    }

    private static double[] Scale(double[] values, double factor)
    {
        if (values == null)
            return null;

        double[] result = new double[values.Length];

        for (int i = 0; i < values.Length; i++)
            result[i] = values[i] * factor;

        return result;
    }

    private static void AddError(List<string> errors, string field, Exception ex)
    {
        errors.Add(field + ": " + ex.Message);
    }

    public static Dictionary<string, object> Status()
    {
        ISldWorks sw = GetApp();

        Dictionary<string, object> result =
            new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);

        result["ok"] = true;
        result["adapter"] = "compiled-csharp-isldworks";
        result["app_revision"] = sw.RevisionNumber();
        result["visible"] = sw.Visible;

        ModelDoc2 doc = sw.ActiveDoc as ModelDoc2;

        result["active_document"] = (doc != null);

        if (doc == null)
        {
            result["document_title"] = null;
            result["document_path"] = null;
            result["document_type"] = null;
            result["document_type_id"] = null;
            return result;
        }

        int typeId = doc.GetType();

        result["document_title"] = doc.GetTitle();
        result["document_path"] = doc.GetPathName();
        result["document_type"] = DocumentTypeName(typeId);
        result["document_type_id"] = typeId;

        return result;
    }

    public static Dictionary<string, object> QueryComponents(bool topLevelOnly)
    {
        ISldWorks sw = GetApp();
        ModelDoc2 doc = sw.ActiveDoc as ModelDoc2;

        if (doc == null)
            throw new InvalidOperationException("No active SOLIDWORKS document.");

        int documentType = doc.GetType();

        if (documentType != SW_DOC_ASSEMBLY)
        {
            throw new InvalidOperationException(
                "sw.query_components requires an active assembly. " +
                "Active document type is " + DocumentTypeName(documentType) + "."
            );
        }

        AssemblyDoc assembly = (AssemblyDoc)doc;

        object rawComponents = assembly.GetComponents(topLevelOnly);
        Array componentArray = rawComponents as Array;

        List<object> components = new List<object>();

        if (componentArray != null)
        {
            foreach (object rawComponent in componentArray)
            {
                Component2 component = rawComponent as Component2;

                if (component == null)
                    continue;

                Dictionary<string, object> item =
                    new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);

                List<string> fieldErrors = new List<string>();

                item["name"] = component.Name2;

                try
                {
                    item["source_path"] = component.GetPathName();
                }
                catch (Exception ex)
                {
                    item["source_path"] = null;
                    AddError(fieldErrors, "source_path", ex);
                }

                try
                {
                    item["referenced_configuration"] = component.ReferencedConfiguration;
                }
                catch (Exception ex)
                {
                    item["referenced_configuration"] = null;
                    AddError(fieldErrors, "referenced_configuration", ex);
                }

                Component2 parent = null;

                try
                {
                    parent = component.GetParent() as Component2;
                    item["parent_name"] = parent == null ? null : parent.Name2;
                    item["is_top_level"] = (parent == null);
                }
                catch (Exception ex)
                {
                    item["parent_name"] = null;
                    item["is_top_level"] = null;
                    AddError(fieldErrors, "parent", ex);
                }

                try
                {
                    item["suppressed"] = component.IsSuppressed();
                }
                catch (Exception ex)
                {
                    item["suppressed"] = null;
                    AddError(fieldErrors, "suppressed", ex);
                }

                try
                {
                    item["suppression_state"] = component.GetSuppression();
                }
                catch (Exception ex)
                {
                    item["suppression_state"] = null;
                    AddError(fieldErrors, "suppression_state", ex);
                }

                // SOLIDWORKS documents IsFixed as meaningful for root-level components.
                if (parent == null)
                {
                    try
                    {
                        item["fixed"] = component.IsFixed();
                    }
                    catch (Exception ex)
                    {
                        item["fixed"] = null;
                        AddError(fieldErrors, "fixed", ex);
                    }
                }
                else
                {
                    item["fixed"] = null;
                    item["fixed_note"] =
                        "Not reported for nested components from the root assembly context.";
                }

                try
                {
                    MathTransform transform = component.Transform2;

                    if (transform == null)
                    {
                        item["transform_array"] = null;
                        item["rotation9"] = null;
                        item["translation_m"] = null;
                        item["translation_mm"] = null;
                        item["scale"] = null;
                    }
                    else
                    {
                        double[] values = ToDoubleArray(transform.ArrayData);

                        item["transform_array"] = values;

                        if (values != null && values.Length >= 13)
                        {
                            double[] rotation9 = Slice(values, 0, 9);
                            double[] translationM = Slice(values, 9, 3);

                            item["rotation9"] = rotation9;
                            item["translation_m"] = translationM;
                            item["translation_mm"] = Scale(translationM, 1000.0);
                            item["scale"] = values[12];
                        }
                        else
                        {
                            item["rotation9"] = null;
                            item["translation_m"] = null;
                            item["translation_mm"] = null;
                            item["scale"] = null;
                        }
                    }
                }
                catch (Exception ex)
                {
                    item["transform_array"] = null;
                    item["rotation9"] = null;
                    item["translation_m"] = null;
                    item["translation_mm"] = null;
                    item["scale"] = null;
                    AddError(fieldErrors, "Transform2", ex);
                }

                try
                {
                    // Approximate SOLIDWORKS component bounding box.
                    // Reference planes and sketches are deliberately excluded.
                    double[] boxM = ToDoubleArray(component.GetBox(false, false));

                    if (boxM != null && boxM.Length >= 6)
                    {
                        double[] boxMm = Scale(boxM, 1000.0);

                        item["getbox_m"] = boxM;
                        item["getbox_mm"] = boxMm;
                        item["box_min_mm"] = Slice(boxMm, 0, 3);
                        item["box_max_mm"] = Slice(boxMm, 3, 3);
                    }
                    else
                    {
                        item["getbox_m"] = null;
                        item["getbox_mm"] = null;
                        item["box_min_mm"] = null;
                        item["box_max_mm"] = null;
                    }
                }
                catch (Exception ex)
                {
                    item["getbox_m"] = null;
                    item["getbox_mm"] = null;
                    item["box_min_mm"] = null;
                    item["box_max_mm"] = null;
                    AddError(fieldErrors, "GetBox", ex);
                }

                item["geometry_note"] =
                    "GetBox is approximate SOLIDWORKS geometry and is not a precision interference measurement.";

                item["field_errors"] = fieldErrors.ToArray();

                components.Add(item);
            }
        }

        Dictionary<string, object> result =
            new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);

        result["ok"] = true;
        result["adapter"] = "compiled-csharp-isldworks";
        result["document_title"] = doc.GetTitle();
        result["document_path"] = doc.GetPathName();
        result["top_level_only"] = topLevelOnly;
        result["component_count"] = components.Count;
        result["components"] = components.ToArray();

        return result;
    }
}
'@

        Add-Type `
            -TypeDefinition $source `
            -ReferencedAssemblies $swDll

        Write-Log "Typed C# SOLIDWORKS interop adapter compiled." "PASS"
    }

    # Prove that the worker can actually attach and make a typed API call.
    try {
        $probe = [CadLocalBridge2026]::Status()
    }
    catch {
        $message = $_.Exception.Message

        if ($message -match "Could not attach") {
            throw "$message`nIf SOLIDWORKS is open normally, close this shell and start a normal non-Administrator PowerShell window."
        }

        throw
    }

    Write-Log "SOLIDWORKS typed interop attached. Revision: $($probe['app_revision'])" "PASS"

    if ($probe["active_document"]) {
        Write-Log "Active document: $($probe['document_title'])" "PASS"
    } else {
        Write-Log "SOLIDWORKS is attached but no document is currently active." "WARN"
    }
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
    }
    catch {
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

    switch ($registryCommand) {
        "sw.status" {
            Write-Log "Executing local typed SOLIDWORKS status read for job $($Job.id)."

            $localResult = [CadLocalBridge2026]::Status()
        }

        "sw.query_components" {
            # This command deliberately accepts only one payload field.
            $topLevelOnly = $true

            if ($null -ne $Job.payload -and $null -ne $Job.payload.top_level_only) {
                $topLevelOnly = [bool]$Job.payload.top_level_only
            }

            Write-Log "Executing local typed component query for job $($Job.id); top_level_only=$topLevelOnly."

            $localResult = [CadLocalBridge2026]::QueryComponents($topLevelOnly)
        }

        default {
            throw "POLICY_BLOCK: unsupported command: $registryCommand"
        }
    }

    return @{
        source = "solidworks-local-interop"
        registry_command = $registryCommand
        adapter = "CadLocalBridge2026"
        policy = "read-only-worker-v0.2"
        result = $localResult
    }
}

function Process-OneJob {
    $queued = Get-QueuedJobs

    $eligible = @(
        $queued |
            Where-Object {
                $AllowedRegistryCommands.ContainsKey([string]$_.command_id)
            } |
            Sort-Object created_at
    )

    if ($eligible.Count -eq 0) {
        return $false
    }

    $job = $eligible[0]

    try {
        $claimed = Claim-Job -JobId $job.id
    }
    catch {
        # Another worker may have won the compare-and-set claim.
        Write-Log "Could not claim job $($job.id); it may have been claimed by another worker. $($_.Exception.Message)" "WARN"
        return $false
    }

    Write-Log "Claimed $($claimed.command_id) job $($claimed.id)" "PASS"

    try {
        $output = Invoke-AllowedCadTool -Job $claimed

        Complete-Job `
            -JobId $claimed.id `
            -Output $output

        Write-Log "Completed job $($claimed.id)" "PASS"
    }
    catch {
        $message = $_.Exception.Message

        Write-Log "Job $($claimed.id) failed: $message" "FAIL"

        Fail-Job `
            -JobId $claimed.id `
            -ErrorMessage $message `
            -Output @{
                source = "solidworks-local-interop"
                registry_command = [string]$claimed.command_id
                policy = "read-only-worker-v0.2"
            }
    }

    return $true
}

# --------------------------------------------------------------------
# Startup
# --------------------------------------------------------------------

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " CADGrounded Local SOLIDWORKS Registry Bridge Worker v0.2" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Registry : $RegistryUrl"
Write-Host "Agent    : $BridgeAgentId"
Write-Host "SW root  : $SolidWorksRoot"
Write-Host "CAD path : compiled C# -> ISldWorks (NO MCP)"
Write-Host ""
Write-Host "Allowed:"
Write-Host "  sw.status"
Write-Host "  sw.query_components"
Write-Host ""
Write-Host "Hard blocked:"
Write-Host "  sw.set_transform"
Write-Host "  sw.insert_component"
Write-Host "  sw.execute_code"
Write-Host "  all other commands"
Write-Host ""

Test-Registry
Initialize-SolidWorksInterop
Register-BridgeHeartbeat

Write-Log "Worker ready. CAD reads are local; no MCP CAD calls will be made." "PASS"

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
    }
    catch {
        Write-Log $_.Exception.Message "FAIL"

        if ($Once) {
            throw
        }

        Start-Sleep -Seconds ([Math]::Max(2, $PollSeconds))
    }
}

Write-Log "Worker stopped." "INFO"
