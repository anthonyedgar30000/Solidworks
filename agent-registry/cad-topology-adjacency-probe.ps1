#Requires -Version 5.1
<#
.SYNOPSIS
    Experimental read-only SOLIDWORKS topology-adjacency probe.

.DESCRIPTION
    Finds a cylindrical face on one exact unsuppressed TOP-LEVEL component by a
    geometric signature (radius + assembly-space axis line), then reports the
    faces directly adjacent to that cylinder through its bounding edges.

    This is a deterministic read-only validation probe. It does NOT select,
    move, mate, rebuild, save, suppress, or modify CAD.

    The target cylinder is NOT selected by runtime face index. Runtime body,
    face, and edge indexes are emitted only for debugging and MUST NOT be stored
    as durable geometry identity.

    Geometry matching:
      - exact Component2.Name2
      - cylinder radius tolerance
      - axis parallelism tolerance (axis sign ignored)
      - shortest distance from supplied assembly-space point to cylinder axis

.EXAMPLE
    # Current v21 SP100 AR60 receiver signature:
    .\cad-topology-adjacency-probe.ps1 `
      -ComponentName2 'SP100_6130656_NATIVE_PORTABLE_V17-1' `
      -RadiusMm 3.5 `
      -AxisPointAssemblyMm -164.5,-192,1037.1833333333336 `
      -AxisAssemblyUnit 0,0,1 `
      -Json

.EXAMPLE
    # Current v21 AR60 terminal shaft signature:
    .\cad-topology-adjacency-probe.ps1 `
      -ComponentName2 '6130460_03_AR60_NATIVE_PORTABLE_V18-2' `
      -RadiusMm 3.5 `
      -AxisPointAssemblyMm 518.2383325091288,486.8817644408611,1384.670110679015 `
      -AxisAssemblyUnit -1,0,0 `
      -Json
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidateLength(1,255)]
    [string]$ComponentName2,

    [Parameter(Mandatory=$true)]
    [ValidateRange(0.000001,1000000)]
    [double]$RadiusMm,

    [Parameter(Mandatory=$true)]
    [ValidateCount(3,3)]
    [double[]]$AxisPointAssemblyMm,

    [Parameter(Mandatory=$true)]
    [ValidateCount(3,3)]
    [double[]]$AxisAssemblyUnit,

    [ValidateRange(0.000001,100)]
    [double]$RadiusToleranceMm = 0.01,

    [ValidateRange(0.000001,1000)]
    [double]$AxisDistanceToleranceMm = 0.05,

    [ValidateRange(0.000001,10)]
    [double]$AxisAngularToleranceDeg = 0.05,

    [string]$SolidWorksRoot = 'C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS',

    [switch]$Json
)

$ErrorActionPreference = 'Stop'

$swDll = Join-Path $SolidWorksRoot 'SolidWorks.Interop.sldworks.dll'
$swConstDll = Join-Path $SolidWorksRoot 'SolidWorks.Interop.swconst.dll'

if (-not (Test-Path -LiteralPath $swDll -PathType Leaf)) {
    throw "SOLIDWORKS interop DLL not found: $swDll"
}
if (-not (Test-Path -LiteralPath $swConstDll -PathType Leaf)) {
    throw "SOLIDWORKS constants interop DLL not found: $swConstDll"
}

[Reflection.Assembly]::LoadFrom($swDll) | Out-Null
[Reflection.Assembly]::LoadFrom($swConstDll) | Out-Null

if (-not ('CadTopologyAdjacencyProbeV1' -as [type])) {
$source = @'
using System;
using System.Collections;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using SolidWorks.Interop.sldworks;

public static class CadTopologyAdjacencyProbeV1
{
    private const int SW_DOC_PART = 1;
    private const int SW_DOC_ASSEMBLY = 2;
    private const int SW_SOLID_BODY = 0;

    private static ISldWorks GetApp()
    {
        object raw = Marshal.GetActiveObject("SldWorks.Application");
        ISldWorks sw = raw as ISldWorks;
        if (sw == null)
            throw new InvalidOperationException("Running SOLIDWORKS object does not expose ISldWorks.");
        return sw;
    }

    private static double[] ToDoubleArray(object raw)
    {
        if (raw == null) return null;
        Array a = raw as Array;
        if (a == null) return null;

        double[] r = new double[a.Length];
        for (int i = 0; i < a.Length; i++)
            r[i] = Convert.ToDouble(a.GetValue(i));
        return r;
    }

    private static double[] Scale(double[] values, double factor)
    {
        if (values == null) return null;
        double[] r = new double[values.Length];
        for (int i = 0; i < values.Length; i++)
            r[i] = values[i] * factor;
        return r;
    }

    private static double[] Normalize(double[] v)
    {
        if (v == null || v.Length < 3) return null;
        double n = Math.Sqrt(v[0]*v[0] + v[1]*v[1] + v[2]*v[2]);
        if (n <= 0.0) return null;
        return new double[] { v[0]/n, v[1]/n, v[2]/n };
    }

    private static double Dot(double[] a, double[] b)
    {
        return a[0]*b[0] + a[1]*b[1] + a[2]*b[2];
    }

    private static double[] Cross(double[] a, double[] b)
    {
        return new double[] {
            a[1]*b[2] - a[2]*b[1],
            a[2]*b[0] - a[0]*b[2],
            a[0]*b[1] - a[1]*b[0]
        };
    }

    private static double Norm(double[] v)
    {
        return Math.Sqrt(Dot(v,v));
    }

    private static double[] Subtract(double[] a, double[] b)
    {
        return new double[] { a[0]-b[0], a[1]-b[1], a[2]-b[2] };
    }

    private static double[] TransformPoint(MathUtility math, MathTransform t, double[] p)
    {
        MathPoint mp = math.CreatePoint(new double[] { p[0], p[1], p[2] }) as MathPoint;
        if (mp == null) throw new InvalidOperationException("CreatePoint returned null.");
        MathPoint outp = mp.IMultiplyTransform(t);
        if (outp == null) throw new InvalidOperationException("MathPoint transform returned null.");
        return ToDoubleArray(outp.ArrayData);
    }

    private static double[] TransformVector(MathUtility math, MathTransform t, double[] v)
    {
        MathVector mv = math.CreateVector(new double[] { v[0], v[1], v[2] }) as MathVector;
        if (mv == null) throw new InvalidOperationException("CreateVector returned null.");
        MathVector outv = mv.IMultiplyTransform(t);
        if (outv == null) throw new InvalidOperationException("MathVector transform returned null.");
        return Normalize(ToDoubleArray(outv.ArrayData));
    }

    private static Component2 FindExactTopLevel(AssemblyDoc assembly, string exactName)
    {
        Array components = assembly.GetComponents(true) as Array;
        if (components == null)
            throw new InvalidOperationException("Top-level component array unavailable.");

        Component2 match = null;
        int count = 0;

        foreach (object raw in components)
        {
            Component2 c = raw as Component2;
            if (c == null) continue;

            if (String.Equals(c.Name2, exactName, StringComparison.Ordinal))
            {
                match = c;
                count++;
            }
        }

        if (count != 1 || match == null)
            throw new InvalidOperationException(
                "Exact top-level Component2.Name2 match must be unique; matches=" + count + ".");

        if (match.IsSuppressed())
            throw new InvalidOperationException("Target component is suppressed.");

        return match;
    }

    private static Dictionary<string, object> DescribeFace(
        Face2 face,
        MathUtility math,
        MathTransform transform)
    {
        Dictionary<string, object> d =
            new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);

        if (face == null)
        {
            d["surface_type"] = "null";
            return d;
        }

        Surface s = face.GetSurface() as Surface;
        if (s == null)
        {
            d["surface_type"] = "unknown";
            return d;
        }

        double? area = null;
        try { area = face.GetArea() * 1000000.0; } catch {}

        double[] boxMm = null;
        try { boxMm = Scale(ToDoubleArray(face.GetBox()), 1000.0); } catch {}

        d["face_area_mm2"] = area;
        d["face_box_local_mm_approx"] = boxMm;
        d["box_source"] = "IFace2.GetBox (approximate)";

        if (s.IsPlane())
        {
            double[] p = ToDoubleArray(s.PlaneParams);
            if (p != null && p.Length >= 6)
            {
                double[] nLocal = Normalize(new double[] { p[0], p[1], p[2] });
                double[] rootLocalM = new double[] { p[3], p[4], p[5] };
                d["surface_type"] = "plane";
                d["normal_assembly_unit"] =
                    TransformVector(math, transform, nLocal);
                d["root_point_assembly_mm"] =
                    Scale(TransformPoint(math, transform, rootLocalM), 1000.0);
                d["primitive_source"] = "ISurface.PlaneParams";
                return d;
            }
        }

        if (s.IsCylinder())
        {
            double[] p = ToDoubleArray(s.CylinderParams);
            if (p != null && p.Length >= 7)
            {
                double[] originLocalM = new double[] { p[0], p[1], p[2] };
                double[] axisLocal = Normalize(new double[] { p[3], p[4], p[5] });
                d["surface_type"] = "cylinder";
                d["radius_mm"] = p[6] * 1000.0;
                d["origin_assembly_mm"] =
                    Scale(TransformPoint(math, transform, originLocalM), 1000.0);
                d["axis_assembly_unit"] =
                    TransformVector(math, transform, axisLocal);
                d["primitive_source"] = "ISurface.CylinderParams";
                return d;
            }
        }

        d["surface_type"] = "other";
        return d;
    }

    public static Dictionary<string, object> Query(
        string exactName,
        double radiusMm,
        double[] targetAxisPointMm,
        double[] targetAxisUnit,
        double radiusTolMm,
        double axisDistanceTolMm,
        double angularTolDeg)
    {
        ISldWorks sw = GetApp();
        ModelDoc2 root = sw.ActiveDoc as ModelDoc2;

        if (root == null)
            throw new InvalidOperationException("No active SOLIDWORKS document.");

        if (root.GetType() != SW_DOC_ASSEMBLY)
            throw new InvalidOperationException("Active document is not an assembly.");

        AssemblyDoc assembly = root as AssemblyDoc;
        Component2 component = FindExactTopLevel(assembly, exactName);

        MathTransform transform = component.Transform2;
        if (transform == null)
            throw new InvalidOperationException("Component2.Transform2 unavailable.");

        double[] ta = ToDoubleArray(transform.ArrayData);
        if (ta == null || ta.Length < 13 || Math.Abs(ta[12] - 1.0) > 1e-12)
            throw new InvalidOperationException("Probe requires component Transform2 scale = 1.");

        ModelDoc2 componentDoc = component.GetModelDoc2() as ModelDoc2;
        if (componentDoc == null)
            throw new InvalidOperationException("Component2.GetModelDoc2 returned null.");

        if (componentDoc.GetType() != SW_DOC_PART)
            throw new InvalidOperationException("Topology probe currently supports part components only.");

        PartDoc part = componentDoc as PartDoc;
        MathUtility math = sw.IGetMathUtility();
        if (part == null || math == null)
            throw new InvalidOperationException("Required PartDoc/MathUtility unavailable.");

        double[] targetAxis = Normalize(targetAxisUnit);
        if (targetAxis == null)
            throw new ArgumentException("AxisAssemblyUnit must be non-zero.");

        double cosTol = Math.Cos(angularTolDeg * Math.PI / 180.0);

        Array bodies = part.GetBodies2(SW_SOLID_BODY, false) as Array;
        if (bodies == null)
            throw new InvalidOperationException("No solid bodies returned.");

        List<object> matches = new List<object>();
        int bodyIndex = 0;

        foreach (object rawBody in bodies)
        {
            Body2 body = rawBody as Body2;
            if (body == null) { bodyIndex++; continue; }

            Array faces = body.GetFaces() as Array;
            if (faces == null) { bodyIndex++; continue; }

            int faceIndex = 0;

            foreach (object rawFace in faces)
            {
                Face2 face = rawFace as Face2;
                if (face == null) { faceIndex++; continue; }

                Surface surface = face.GetSurface() as Surface;
                if (surface == null || !surface.IsCylinder())
                {
                    faceIndex++;
                    continue;
                }

                double[] p = ToDoubleArray(surface.CylinderParams);
                if (p == null || p.Length < 7)
                {
                    faceIndex++;
                    continue;
                }

                double candidateRadiusMm = p[6] * 1000.0;
                if (Math.Abs(candidateRadiusMm - radiusMm) > radiusTolMm)
                {
                    faceIndex++;
                    continue;
                }

                double[] localOriginM = new double[] { p[0], p[1], p[2] };
                double[] localAxis = Normalize(new double[] { p[3], p[4], p[5] });

                double[] candidateOriginMm =
                    Scale(TransformPoint(math, transform, localOriginM), 1000.0);
                double[] candidateAxis =
                    TransformVector(math, transform, localAxis);

                double absDot = Math.Abs(Dot(candidateAxis, targetAxis));
                if (absDot < cosTol)
                {
                    faceIndex++;
                    continue;
                }

                double axisDistanceMm =
                    Norm(Cross(Subtract(targetAxisPointMm, candidateOriginMm), candidateAxis));

                if (axisDistanceMm > axisDistanceTolMm)
                {
                    faceIndex++;
                    continue;
                }

                List<object> edgeRows = new List<object>();
                object rawEdges = face.GetEdges();
                Array edges = rawEdges as Array;
                int edgeIndex = 0;

                if (edges != null)
                {
                    foreach (object rawEdge in edges)
                    {
                        Edge edge = rawEdge as Edge;
                        if (edge == null) { edgeIndex++; continue; }

                        Face2 f1 = null;
                        Face2 f2 = null;

                        try
                        {
                            edge.IGetTwoAdjacentFaces2(out f1, out f2);
                        }
                        catch
                        {
                            object rawAdjacent = edge.GetTwoAdjacentFaces2();
                            Array aa = rawAdjacent as Array;
                            if (aa != null)
                            {
                                if (aa.Length > 0) f1 = aa.GetValue(0) as Face2;
                                if (aa.Length > 1) f2 = aa.GetValue(1) as Face2;
                            }
                        }

                        Dictionary<string, object> erow =
                            new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);

                        erow["edge_runtime_index"] = edgeIndex;
                        erow["edge_runtime_index_note"] =
                            "Runtime traversal index only; not a durable selector.";
                        erow["adjacent_face_1"] = DescribeFace(f1, math, transform);
                        erow["adjacent_face_2"] = DescribeFace(f2, math, transform);
                        edgeRows.Add(erow);

                        edgeIndex++;
                    }
                }

                Dictionary<string, object> match =
                    new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);

                match["body_runtime_index"] = bodyIndex;
                match["face_runtime_index"] = faceIndex;
                match["runtime_index_note"] =
                    "Runtime traversal indexes only; not durable selectors.";
                match["radius_mm"] = candidateRadiusMm;
                match["origin_assembly_mm"] = candidateOriginMm;
                match["axis_assembly_unit"] = candidateAxis;
                match["axis_distance_to_requested_line_mm"] = axisDistanceMm;
                match["absolute_axis_dot"] = absDot;
                match["edge_count_reported"] = face.GetEdgeCount();
                match["edge_count_returned"] = edgeRows.Count;
                match["edges"] = edgeRows.ToArray();

                matches.Add(match);
                faceIndex++;
            }

            bodyIndex++;
        }

        Dictionary<string, object> result =
            new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);

        result["ok"] = true;
        result["read_only"] = true;
        result["source_classification"] = "verified_from_solidworks_api";
        result["document_title"] = root.GetTitle();
        result["document_path"] = root.GetPathName();
        result["component_name2"] = component.Name2;
        result["component_path"] = component.GetPathName();

        result["requested_signature"] = new Dictionary<string, object> {
            { "radius_mm", radiusMm },
            { "axis_point_assembly_mm", targetAxisPointMm },
            { "axis_assembly_unit", targetAxis },
            { "radius_tolerance_mm", radiusTolMm },
            { "axis_distance_tolerance_mm", axisDistanceTolMm },
            { "axis_angular_tolerance_deg", angularTolDeg }
        };

        result["matching_cylinder_count"] = matches.Count;
        result["matching_cylinders"] = matches.ToArray();
        result["mechanical_acceptance_granted"] = false;

        result["notes"] = new string[] {
            "Cylinder is matched by geometric signature, not runtime face index.",
            "Adjacency is read from IFace2.GetEdges and IEdge.IGetTwoAdjacentFaces2/GetTwoAdjacentFaces2.",
            "Runtime body/face/edge indexes are debug-only and not durable geometry identity.",
            "Plane/cylinder primitive data comes from SOLIDWORKS underlying surfaces.",
            "IFace2.GetBox is approximate local screening evidence.",
            "Topology adjacency does not by itself establish seating, contact, interference, restraint, or mechanical acceptance."
        };

        return result;
    }
}
'@

    Add-Type `
        -TypeDefinition $source `
        -ReferencedAssemblies $swDll
}

$result = [CadTopologyAdjacencyProbeV1]::Query(
    $ComponentName2,
    $RadiusMm,
    $AxisPointAssemblyMm,
    $AxisAssemblyUnit,
    $RadiusToleranceMm,
    $AxisDistanceToleranceMm,
    $AxisAngularToleranceDeg
)

if ($Json) {
    $result | ConvertTo-Json -Depth 100
    return
}

[pscustomobject][ordered]@{
    Document = $result['document_title']
    Component = $result['component_name2']
    MatchingCylinders = $result['matching_cylinder_count']
    SourceClassification = $result['source_classification']
    MechanicalAcceptance = 'NOT GRANTED'
} | Format-List

foreach ($match in @($result['matching_cylinders'])) {
    Write-Host ('=' * 84)
    [pscustomobject][ordered]@{
        Radius_mm = $match['radius_mm']
        OriginAssembly_mm = @($match['origin_assembly_mm']) -join ', '
        AxisAssembly_Unit = @($match['axis_assembly_unit']) -join ', '
        AxisLineDistance_mm = $match['axis_distance_to_requested_line_mm']
        AbsAxisDot = $match['absolute_axis_dot']
        EdgeCount = $match['edge_count_returned']
    } | Format-List

    foreach ($edge in @($match['edges'])) {
        Write-Host ("Edge runtime index {0}" -f $edge['edge_runtime_index'])
        [pscustomobject][ordered]@{
            Adjacent1Type = $edge['adjacent_face_1']['surface_type']
            Adjacent1Point_mm = @($edge['adjacent_face_1']['root_point_assembly_mm']) -join ', '
            Adjacent1Normal = @($edge['adjacent_face_1']['normal_assembly_unit']) -join ', '
            Adjacent1Radius_mm = $edge['adjacent_face_1']['radius_mm']
            Adjacent1Axis = @($edge['adjacent_face_1']['axis_assembly_unit']) -join ', '
            Adjacent2Type = $edge['adjacent_face_2']['surface_type']
            Adjacent2Point_mm = @($edge['adjacent_face_2']['root_point_assembly_mm']) -join ', '
            Adjacent2Normal = @($edge['adjacent_face_2']['normal_assembly_unit']) -join ', '
            Adjacent2Radius_mm = $edge['adjacent_face_2']['radius_mm']
            Adjacent2Axis = @($edge['adjacent_face_2']['axis_assembly_unit']) -join ', '
        } | Format-List
    }
}
