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
      sw.check_interference_pair

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
    Retained only for backward-compatible launch scripts. Ignored by v0.3.

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
    "sw.status"                  = $true
    "sw.query_components"        = $true
    "sw.check_interference_pair" = $true
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
            "local-interop:sw.query_components",
            "local-interop:sw.check_interference_pair"
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
    $swConstDll = Join-Path $SolidWorksRoot "SolidWorks.Interop.swconst.dll"

    if (-not (Test-Path -LiteralPath $swDll)) {
        throw "SOLIDWORKS interop DLL not found: $swDll"
    }

    if (-not (Test-Path -LiteralPath $swConstDll)) {
        throw "SOLIDWORKS constants interop DLL not found: $swConstDll"
    }

    # IMPORTANT:
    # Add-Type can compile against a DLL path without making that assembly
    # resolvable later when the generated type executes. Load the SOLIDWORKS
    # interop assemblies into this PowerShell AppDomain first. This matches the
    # typed C# probe that was proven to work against SOLIDWORKS 2026 SP3.2.
    [Reflection.Assembly]::LoadFrom($swDll) | Out-Null
    [Reflection.Assembly]::LoadFrom($swConstDll) | Out-Null

    Write-Log "SOLIDWORKS interop assemblies loaded into the worker AppDomain." "PASS"

    if ($McpUrl) {
        Write-Log "McpUrl was supplied but is ignored by local-interop worker v0.3." "WARN"
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

    private static int CountArray(object raw)
    {
        Array array = raw as Array;
        return array == null ? 0 : array.Length;
    }

    private static double[] PointMillimetres(object raw)
    {
        double[] point = ToDoubleArray(raw);

        if (point == null || point.Length < 3)
            return null;

        return new double[]
        {
            point[0] * 1000.0,
            point[1] * 1000.0,
            point[2] * 1000.0
        };
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

    public static Dictionary<string, object> CheckInterferencePair(
        string aNameContains,
        string bNameContains
    )
    {
        if (String.IsNullOrWhiteSpace(aNameContains))
            throw new ArgumentException("a_name_contains must not be empty.");

        if (String.IsNullOrWhiteSpace(bNameContains))
            throw new ArgumentException("b_name_contains must not be empty.");

        ISldWorks sw = GetApp();
        ModelDoc2 doc = sw.ActiveDoc as ModelDoc2;

        if (doc == null)
            throw new InvalidOperationException("No active SOLIDWORKS document.");

        int documentType = doc.GetType();

        if (documentType != SW_DOC_ASSEMBLY)
        {
            throw new InvalidOperationException(
                "sw.check_interference_pair requires an active assembly. " +
                "Active document type is " + DocumentTypeName(documentType) + "."
            );
        }

        AssemblyDoc assembly = (AssemblyDoc)doc;
        Array componentArray = assembly.GetComponents(true) as Array;

        if (componentArray == null)
            throw new InvalidOperationException("Top-level components are unavailable.");

        Component2 componentA = null;
        Component2 componentB = null;
        int aMatches = 0;
        int bMatches = 0;

        foreach (object rawComponent in componentArray)
        {
            Component2 component = rawComponent as Component2;

            if (component == null || component.IsSuppressed())
                continue;

            string name = component.Name2 ?? String.Empty;

            if (name.IndexOf(aNameContains, StringComparison.OrdinalIgnoreCase) >= 0)
            {
                componentA = component;
                aMatches++;
            }

            if (name.IndexOf(bNameContains, StringComparison.OrdinalIgnoreCase) >= 0)
            {
                componentB = component;
                bMatches++;
            }
        }

        if (aMatches != 1 || bMatches != 1)
        {
            throw new InvalidOperationException(
                "Component matching must be unique among unsuppressed top-level components. " +
                "a_matches=" + aMatches + ", b_matches=" + bMatches + "."
            );
        }

        if (String.Equals(componentA.Name2, componentB.Name2, StringComparison.Ordinal))
            throw new InvalidOperationException("The two component selectors resolved to the same component.");

        object closestPointA;
        object closestPointB;
        double distanceM = doc.ClosestDistance(
            componentA,
            componentB,
            out closestPointA,
            out closestPointB
        );

        object physicalComponents;
        object physicalFaces;
        object[] physicalPair = new object[] { componentA, componentB };

        assembly.ToolsCheckInterference2(
            2,
            physicalPair,
            false,
            out physicalComponents,
            out physicalFaces
        );

        object coincidentComponents;
        object coincidentFaces;
        object[] coincidentPair = new object[] { componentA, componentB };

        assembly.ToolsCheckInterference2(
            2,
            coincidentPair,
            true,
            out coincidentComponents,
            out coincidentFaces
        );

        int physicalComponentEntries = CountArray(physicalComponents);
        int physicalFaceEntries = CountArray(physicalFaces);
        int coincidentComponentEntries = CountArray(coincidentComponents);
        int coincidentFaceEntries = CountArray(coincidentFaces);

        // One micrometre is intentionally much smaller than the benchmark's
        // millimetre-scale clearances while remaining above floating-point noise.
        const double contactToleranceM = 0.000001;
        string classification;

        if (physicalComponentEntries > 0 || physicalFaceEntries > 0)
            classification = "physical_interference";
        else if (distanceM >= 0.0 && distanceM <= contactToleranceM)
            classification = "exact_contact_or_coincidence";
        else if (distanceM >= 0.0)
            classification = "clearance";
        else
            classification = "measurement_failed";

        Dictionary<string, object> result =
            new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);

        result["ok"] = (classification != "measurement_failed");
        result["adapter"] = "compiled-csharp-isldworks";
        result["document_title"] = doc.GetTitle();
        result["document_path"] = doc.GetPathName();
        result["component_a"] = componentA.Name2;
        result["component_b"] = componentB.Name2;
        result["classification"] = classification;
        result["minimum_distance_mm"] = distanceM < 0.0
            ? (object)null
            : distanceM * 1000.0;
        result["closest_point_a_mm"] = PointMillimetres(closestPointA);
        result["closest_point_b_mm"] = PointMillimetres(closestPointB);
        result["contact_tolerance_mm"] = contactToleranceM * 1000.0;
        result["physical_component_entries"] = physicalComponentEntries;
        result["physical_face_entries"] = physicalFaceEntries;
        result["coincident_component_entries"] = coincidentComponentEntries;
        result["coincident_face_entries"] = coincidentFaceEntries;
        result["source_classification"] = "verified_from_solidworks_api";
        result["api_distance"] = "IModelDoc2.ClosestDistance";
        result["api_interference"] = "IAssemblyDoc.ToolsCheckInterference2";
        result["read_only"] = true;

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

    $bridgeVersion = "local-interop-v0.3.0"
    $data = $null

    switch ($registryCommand) {
        "sw.status" {
            Write-Log "Executing local typed SOLIDWORKS status read for job $($Job.id)."

            $raw = [CadLocalBridge2026]::Status()

            $activeDocument = $null
            if ([bool]$raw["active_document"]) {
                $activeDocument = @{
                    title = $raw["document_title"]
                    path = $raw["document_path"]
                    document_type = $raw["document_type"]
                    document_type_id = $raw["document_type_id"]
                }
            }

            # Preserve the structured CADGrounded-style data contract consumed
            # by cad.ps1 and the higher-level local query scripts.
            $data = @{
                active_document = $activeDocument
                bridge_version = $bridgeVersion
                app_revision = $raw["app_revision"]
                visible = $raw["visible"]
                adapter = $raw["adapter"]
            }
        }

        "sw.query_components" {
            # This command deliberately accepts only one payload field.
            $topLevelOnly = $true

            if ($null -ne $Job.payload -and $null -ne $Job.payload.top_level_only) {
                $topLevelOnly = [bool]$Job.payload.top_level_only
            }

            Write-Log "Executing local typed component query for job $($Job.id); top_level_only=$topLevelOnly."

            $raw = [CadLocalBridge2026]::QueryComponents($topLevelOnly)

            $compatComponents = @(
                foreach ($component in @($raw["components"])) {
                    $box = $null

                    if ($null -ne $component["box_min_mm"] -and
                        $null -ne $component["box_max_mm"]) {

                        $box = @{
                            min = $component["box_min_mm"]
                            max = $component["box_max_mm"]
                            source = "Component2.GetBox(false,false)"
                            source_classification = "approximate_from_solidworks_getbox"
                        }
                    }

                    @{
                        # Canonical field names expected by cad.ps1,
                        # cad-query.ps1, cad-geometry.ps1 and
                        # cad-relative-geometry.ps1.
                        name2 = $component["name"]
                        path = $component["source_path"]
                        fixed = $component["fixed"]
                        suppressed = $component["suppressed"]
                        suppression_state = $component["suppression_state"]
                        referenced_configuration = $component["referenced_configuration"]
                        parent_name = $component["parent_name"]
                        is_top_level = $component["is_top_level"]

                        transform_array = $component["transform_array"]
                        rotation9 = $component["rotation9"]
                        translation_m = $component["translation_m"]
                        translation_mm = $component["translation_mm"]
                        scale = $component["scale"]
                        transform_source = "Component2.Transform2"
                        source_classification = "solidworks_api"

                        bounding_box_mm_approx = $box

                        # Rich aliases retained for direct/debug inspection.
                        getbox_m = $component["getbox_m"]
                        getbox_mm = $component["getbox_mm"]
                        box_min_mm = $component["box_min_mm"]
                        box_max_mm = $component["box_max_mm"]
                        geometry_note = $component["geometry_note"]
                        field_errors = $component["field_errors"]
                    }
                }
            )

            $data = @{
                document_title = $raw["document_title"]
                document_path = $raw["document_path"]
                top_level_only = $raw["top_level_only"]
                component_count = $compatComponents.Count
                components = $compatComponents
                bridge_version = $bridgeVersion
                adapter = $raw["adapter"]
            }
        }

        "sw.check_interference_pair" {
            if ($null -eq $Job.payload) {
                throw "sw.check_interference_pair requires a payload."
            }

            $payloadFields = @($Job.payload.PSObject.Properties.Name)
            $unknownFields = @(
                $payloadFields |
                    Where-Object { $_ -notin @("a_name_contains", "b_name_contains") }
            )

            if ($unknownFields.Count -gt 0) {
                throw "Unsupported sw.check_interference_pair payload field(s): $($unknownFields -join ', ')"
            }

            $aNameContains = [string]$Job.payload.a_name_contains
            $bNameContains = [string]$Job.payload.b_name_contains

            if ([string]::IsNullOrWhiteSpace($aNameContains) -or
                $aNameContains.Length -gt 128) {
                throw "a_name_contains must contain 1 to 128 characters."
            }

            if ([string]::IsNullOrWhiteSpace($bNameContains) -or
                $bNameContains.Length -gt 128) {
                throw "b_name_contains must contain 1 to 128 characters."
            }

            Write-Log "Executing exact read-only pair check for job $($Job.id): '$aNameContains' versus '$bNameContains'."

            $raw = [CadLocalBridge2026]::CheckInterferencePair(
                $aNameContains,
                $bNameContains
            )

            if (-not [bool]$raw["ok"]) {
                throw "SOLIDWORKS pair measurement failed."
            }

            $data = $raw
            $data["bridge_version"] = $bridgeVersion
        }

        default {
            throw "POLICY_BLOCK: unsupported command: $registryCommand"
        }
    }

    # Compatibility envelope:
    #
    # cad.ps1 intentionally requires:
    #   job.result.result.structuredContent.ok == true
    #   job.result.result.structuredContent.result != null
    #
    # Keep that contract even though execution is now local and no MCP call
    # occurs. This lets every existing higher-level script remain unchanged.
    $structuredCadResult = @{
        isError = $false
        structuredContent = @{
            ok = $true
            result = $data
        }
    }

    return @{
        source = "solidworks-local-interop"
        registry_command = $registryCommand
        adapter = "CadLocalBridge2026"
        policy = "read-only-worker-v0.3.0"
        result = $structuredCadResult
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
                policy = "read-only-worker-v0.3.0"
            }
    }

    return $true
}

# --------------------------------------------------------------------
# Startup
# --------------------------------------------------------------------

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " CADGrounded Local SOLIDWORKS Registry Bridge Worker v0.3.0" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Registry : $RegistryUrl"
Write-Host "Agent    : $BridgeAgentId"
Write-Host "SW root  : $SolidWorksRoot"
Write-Host "CAD path : compiled C# -> ISldWorks (NO MCP)"
Write-Host ""
Write-Host "Allowed:"
Write-Host "  sw.status"
Write-Host "  sw.query_components"
Write-Host "  sw.check_interference_pair"
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
