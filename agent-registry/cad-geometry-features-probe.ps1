#Requires -Version 5.1
<#
.SYNOPSIS
    Experimental deterministic read-only SOLIDWORKS B-rep geometry probe.

.DESCRIPTION
    Attaches to the already-running SOLIDWORKS instance and inspects exactly one
    UNSUPPRESSED TOP-LEVEL component by exact Component2.Name2.

    It reads only:
      - Component2.Transform2
      - Component2.GetModelDoc2
      - IPartDoc.GetBodies2(swSolidBody, false)
      - IBody2.GetFaces
      - IFace2.GetSurface / GetArea / GetBox / FaceInSurfaceSense
      - ISurface.IsCylinder / CylinderParams
      - ISurface.IsPlane / PlaneParams
      - SOLIDWORKS MathUtility for component-space -> root-assembly transforms

    It does NOT select, move, mate, rebuild, save, suppress, or modify geometry.
    It is a validation probe, not the permanent CAD control path.

    IMPORTANT:
      * face_runtime_index is NOT a durable selector.
      * face_box_local_mm is approximate IFace2.GetBox evidence only.
      * Cylinder/plane primitive parameters come from the underlying SOLIDWORKS
        surface and are transformed to root assembly space.
      * No returned geometry grants mechanical acceptance.

.EXAMPLE
    .\cad-geometry-features-probe.ps1 `
      -ComponentName2 'SP100_6130656_NATIVE_PORTABLE_V17-1' `
      -Kind Cylinder `
      -RadiusMinMm 3.3 -RadiusMaxMm 3.7

.EXAMPLE
    .\cad-geometry-features-probe.ps1 `
      -ComponentName2 '6130460_03_AR60_NATIVE_PORTABLE_V18-2' `
      -Kind Both `
      -Json
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidateLength(1,255)]
    [string]$ComponentName2,

    [ValidateSet('Cylinder','Plane','Both')]
    [string]$Kind = 'Both',

    [Nullable[double]]$RadiusMinMm,
    [Nullable[double]]$RadiusMaxMm,

    [ValidateRange(1,5000)]
    [int]$MaxFeatures = 1000,

    [string]$SolidWorksRoot = 'C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS',

    [switch]$Json
)

$ErrorActionPreference = 'Stop'

if ($RadiusMinMm.HasValue -and $RadiusMinMm.Value -lt 0) {
    throw 'RadiusMinMm must be >= 0.'
}
if ($RadiusMaxMm.HasValue -and $RadiusMaxMm.Value -lt 0) {
    throw 'RadiusMaxMm must be >= 0.'
}
if ($RadiusMinMm.HasValue -and $RadiusMaxMm.HasValue -and
    $RadiusMinMm.Value -gt $RadiusMaxMm.Value) {
    throw 'RadiusMinMm must be <= RadiusMaxMm.'
}
if (($RadiusMinMm.HasValue -or $RadiusMaxMm.HasValue) -and $Kind -eq 'Plane') {
    throw 'Radius filters apply only to Cylinder or Both.'
}

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

if (-not ('CadGeometryFeatureProbeV1' -as [type])) {
    $source = @'
using System;
using System.Collections;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using SolidWorks.Interop.sldworks;

public static class CadGeometryFeatureProbeV1
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

        double[] result = new double[a.Length];
        for (int i = 0; i < a.Length; i++)
            result[i] = Convert.ToDouble(a.GetValue(i));
        return result;
    }

    private static double[] Scale(double[] values, double factor)
    {
        if (values == null) return null;
        double[] result = new double[values.Length];
        for (int i = 0; i < values.Length; i++)
            result[i] = values[i] * factor;
        return result;
    }

    private static double[] Normalize(double[] v)
    {
        if (v == null || v.Length < 3) return null;
        double n = Math.Sqrt(v[0]*v[0] + v[1]*v[1] + v[2]*v[2]);
        if (n <= 0.0) return null;
        return new double[] { v[0]/n, v[1]/n, v[2]/n };
    }

    private static double[] TransformPoint(
        MathUtility math,
        MathTransform transform,
        double[] point)
    {
        if (point == null || point.Length < 3) return null;

        MathPoint p = math.CreatePoint(new double[] {
            point[0], point[1], point[2]
        }) as MathPoint;

        if (p == null)
            throw new InvalidOperationException("MathUtility.CreatePoint returned null.");

        MathPoint transformed = p.IMultiplyTransform(transform);
        if (transformed == null)
            throw new InvalidOperationException("MathPoint.IMultiplyTransform returned null.");

        return ToDoubleArray(transformed.ArrayData);
    }

    private static double[] TransformVector(
        MathUtility math,
        MathTransform transform,
        double[] vector)
    {
        if (vector == null || vector.Length < 3) return null;

        MathVector v = math.CreateVector(new double[] {
            vector[0], vector[1], vector[2]
        }) as MathVector;

        if (v == null)
            throw new InvalidOperationException("MathUtility.CreateVector returned null.");

        MathVector transformed = v.IMultiplyTransform(transform);
        if (transformed == null)
            throw new InvalidOperationException("MathVector.IMultiplyTransform returned null.");

        return Normalize(ToDoubleArray(transformed.ArrayData));
    }

    private static Component2 FindExactTopLevelComponent(
        AssemblyDoc assembly,
        string exactName)
    {
        Array components = assembly.GetComponents(true) as Array;
        if (components == null)
            throw new InvalidOperationException("Top-level component array is unavailable.");

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
        {
            throw new InvalidOperationException(
                "Exact top-level Component2.Name2 match must be unique. " +
                "name='" + exactName + "', matches=" + count + "."
            );
        }

        if (match.IsSuppressed())
            throw new InvalidOperationException("Target component is suppressed.");

        return match;
    }

    public static Dictionary<string, object> Query(
        string exactName,
        string kind,
        Nullable<double> radiusMinMm,
        Nullable<double> radiusMaxMm,
        int maxFeatures)
    {
        if (String.IsNullOrWhiteSpace(exactName))
            throw new ArgumentException("exactName must not be empty.");

        bool wantCylinder =
            String.Equals(kind, "Cylinder", StringComparison.OrdinalIgnoreCase) ||
            String.Equals(kind, "Both", StringComparison.OrdinalIgnoreCase);

        bool wantPlane =
            String.Equals(kind, "Plane", StringComparison.OrdinalIgnoreCase) ||
            String.Equals(kind, "Both", StringComparison.OrdinalIgnoreCase);

        if (!wantCylinder && !wantPlane)
            throw new ArgumentException("kind must be Cylinder, Plane, or Both.");

        ISldWorks sw = GetApp();
        ModelDoc2 rootDoc = sw.ActiveDoc as ModelDoc2;
        if (rootDoc == null)
            throw new InvalidOperationException("No active SOLIDWORKS document.");

        if (rootDoc.GetType() != SW_DOC_ASSEMBLY)
            throw new InvalidOperationException("Active SOLIDWORKS document is not an assembly.");

        AssemblyDoc assembly = rootDoc as AssemblyDoc;
        if (assembly == null)
            throw new InvalidOperationException("Active document does not expose AssemblyDoc.");

        Component2 component = FindExactTopLevelComponent(assembly, exactName);

        MathTransform transform = component.Transform2;
        if (transform == null)
            throw new InvalidOperationException("Component2.Transform2 is unavailable.");

        double[] transformArray = ToDoubleArray(transform.ArrayData);
        double transformScale =
            (transformArray != null && transformArray.Length >= 13)
            ? transformArray[12]
            : Double.NaN;

        ModelDoc2 componentDoc = component.GetModelDoc2() as ModelDoc2;
        if (componentDoc == null)
        {
            throw new InvalidOperationException(
                "Component2.GetModelDoc2 returned null. " +
                "The component may be lightweight or unresolved."
            );
        }

        if (componentDoc.GetType() != SW_DOC_PART)
        {
            throw new InvalidOperationException(
                "Geometry probe currently accepts part components only. " +
                "Target document type id=" + componentDoc.GetType() + "."
            );
        }

        PartDoc part = componentDoc as PartDoc;
        if (part == null)
            throw new InvalidOperationException("Component model does not expose PartDoc.");

        MathUtility math = sw.IGetMathUtility();
        if (math == null)
            throw new InvalidOperationException("ISldWorks.IGetMathUtility returned null.");

        Array bodies = part.GetBodies2(SW_SOLID_BODY, false) as Array;
        List<object> features = new List<object>();
        int bodyCount = bodies == null ? 0 : bodies.Length;
        int visitedFaces = 0;
        int emitted = 0;

        if (bodies != null)
        {
            int bodyRuntimeIndex = 0;

            foreach (object rawBody in bodies)
            {
                Body2 body = rawBody as Body2;
                if (body == null)
                {
                    bodyRuntimeIndex++;
                    continue;
                }

                Array faces = body.GetFaces() as Array;
                if (faces == null)
                {
                    bodyRuntimeIndex++;
                    continue;
                }

                int faceRuntimeIndex = 0;

                foreach (object rawFace in faces)
                {
                    Face2 face = rawFace as Face2;
                    if (face == null)
                    {
                        faceRuntimeIndex++;
                        continue;
                    }

                    visitedFaces++;

                    Surface surface = face.GetSurface() as Surface;
                    if (surface == null)
                    {
                        faceRuntimeIndex++;
                        continue;
                    }

                    bool faceSenseOpposite = false;
                    bool faceSenseAvailable = true;
                    try
                    {
                        faceSenseOpposite = face.FaceInSurfaceSense();
                    }
                    catch
                    {
                        faceSenseAvailable = false;
                    }

                    double? areaMm2 = null;
                    try
                    {
                        areaMm2 = face.GetArea() * 1000000.0;
                    }
                    catch {}

                    double[] faceBoxLocalMm = null;
                    try
                    {
                        double[] boxM = ToDoubleArray(face.GetBox());
                        faceBoxLocalMm = Scale(boxM, 1000.0);
                    }
                    catch {}

                    if (wantCylinder && surface.IsCylinder())
                    {
                        double[] p = ToDoubleArray(surface.CylinderParams);

                        if (p != null && p.Length >= 7)
                        {
                            double radiusMm = p[6] * 1000.0;

                            bool radiusAllowed =
                                (!radiusMinMm.HasValue || radiusMm >= radiusMinMm.Value) &&
                                (!radiusMaxMm.HasValue || radiusMm <= radiusMaxMm.Value);

                            if (radiusAllowed)
                            {
                                double[] originLocalM = new double[] { p[0], p[1], p[2] };
                                double[] axisLocal = Normalize(new double[] { p[3], p[4], p[5] });

                                double[] originAssemblyM =
                                    TransformPoint(math, transform, originLocalM);
                                double[] axisAssembly =
                                    TransformVector(math, transform, axisLocal);

                                Dictionary<string, object> row =
                                    new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);

                                row["surface_type"] = "cylinder";
                                row["body_runtime_index"] = bodyRuntimeIndex;
                                row["face_runtime_index"] = faceRuntimeIndex;
                                row["face_runtime_index_note"] =
                                    "Runtime traversal index only; not a durable selector.";
                                row["radius_mm_local"] = radiusMm;

                                if (!Double.IsNaN(transformScale) &&
                                    Math.Abs(transformScale - 1.0) <= 1e-12)
                                    row["radius_mm_assembly"] = radiusMm;
                                else
                                    row["radius_mm_assembly"] = null;

                                row["origin_local_mm"] = Scale(originLocalM, 1000.0);
                                row["axis_local_unit"] = axisLocal;
                                row["origin_assembly_mm"] = Scale(originAssemblyM, 1000.0);
                                row["axis_assembly_unit"] = axisAssembly;
                                row["face_area_mm2"] = areaMm2;
                                row["face_in_surface_sense"] =
                                    faceSenseAvailable ? (object)faceSenseOpposite : null;
                                row["face_box_local_mm_approx"] = faceBoxLocalMm;
                                row["primitive_source"] = "ISurface.CylinderParams";
                                row["box_source"] = "IFace2.GetBox (approximate)";

                                features.Add(row);
                                emitted++;
                            }
                        }
                    }

                    if (wantPlane && surface.IsPlane())
                    {
                        double[] p = ToDoubleArray(surface.PlaneParams);

                        if (p != null && p.Length >= 6)
                        {
                            double[] normalLocal =
                                Normalize(new double[] { p[0], p[1], p[2] });
                            double[] rootLocalM =
                                new double[] { p[3], p[4], p[5] };

                            double[] rootAssemblyM =
                                TransformPoint(math, transform, rootLocalM);
                            double[] normalAssembly =
                                TransformVector(math, transform, normalLocal);

                            Dictionary<string, object> row =
                                new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);

                            row["surface_type"] = "plane";
                            row["body_runtime_index"] = bodyRuntimeIndex;
                            row["face_runtime_index"] = faceRuntimeIndex;
                            row["face_runtime_index_note"] =
                                "Runtime traversal index only; not a durable selector.";
                            row["normal_local_unit"] = normalLocal;
                            row["root_point_local_mm"] = Scale(rootLocalM, 1000.0);
                            row["normal_assembly_unit"] = normalAssembly;
                            row["root_point_assembly_mm"] = Scale(rootAssemblyM, 1000.0);
                            row["face_area_mm2"] = areaMm2;
                            row["face_in_surface_sense"] =
                                faceSenseAvailable ? (object)faceSenseOpposite : null;
                            row["face_box_local_mm_approx"] = faceBoxLocalMm;
                            row["primitive_source"] = "ISurface.PlaneParams";
                            row["box_source"] = "IFace2.GetBox (approximate)";

                            features.Add(row);
                            emitted++;
                        }
                    }

                    if (emitted >= maxFeatures)
                        break;

                    faceRuntimeIndex++;
                }

                if (emitted >= maxFeatures)
                    break;

                bodyRuntimeIndex++;
            }
        }

        Dictionary<string, object> result =
            new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);

        result["ok"] = true;
        result["read_only"] = true;
        result["source_classification"] = "verified_from_solidworks_api";
        result["document_title"] = rootDoc.GetTitle();
        result["document_path"] = rootDoc.GetPathName();
        result["component_name2"] = component.Name2;
        result["component_path"] = component.GetPathName();
        result["component_transform_array"] = transformArray;
        result["component_scale"] =
            Double.IsNaN(transformScale) ? (object)null : transformScale;
        result["component_model_title"] = componentDoc.GetTitle();
        result["component_model_path"] = componentDoc.GetPathName();
        result["body_count_solid"] = bodyCount;
        result["faces_visited"] = visitedFaces;
        result["feature_count"] = features.Count;
        result["kind"] = kind;
        result["radius_min_mm"] =
            radiusMinMm.HasValue ? (object)radiusMinMm.Value : null;
        result["radius_max_mm"] =
            radiusMaxMm.HasValue ? (object)radiusMaxMm.Value : null;
        result["max_features"] = maxFeatures;
        result["features"] = features.ToArray();
        result["mechanical_acceptance_granted"] = false;
        result["notes"] = new string[] {
            "Exact Component2.Name2 match among unsuppressed top-level components.",
            "Primitive cylinder/plane parameters come from SOLIDWORKS underlying surfaces.",
            "Component-space points/vectors are transformed with Component2.Transform2 into root-assembly space.",
            "IFace2.GetBox values are approximate and remain in component model space.",
            "Runtime body/face indices are not persistent geometry identities.",
            "This evidence does not establish contact, interference, seating, restraint, or mechanical acceptance."
        };

        return result;
    }
}
'@

    Add-Type `
        -TypeDefinition $source `
        -ReferencedAssemblies $swDll
}

$probe = [CadGeometryFeatureProbeV1]::Query(
    $ComponentName2,
    $Kind,
    $RadiusMinMm,
    $RadiusMaxMm,
    $MaxFeatures
)

if ($Json) {
    $probe | ConvertTo-Json -Depth 100
    return
}

[pscustomobject][ordered]@{
    Document = $probe['document_title']
    Component = $probe['component_name2']
    ComponentPath = $probe['component_path']
    Kind = $probe['kind']
    SolidBodies = $probe['body_count_solid']
    FacesVisited = $probe['faces_visited']
    FeaturesReturned = $probe['feature_count']
    ComponentScale = $probe['component_scale']
    SourceClassification = $probe['source_classification']
    MechanicalAcceptance = 'NOT GRANTED'
} | Format-List

foreach ($feature in @($probe['features'])) {
    Write-Host ('=' * 82)

    if ($feature['surface_type'] -eq 'cylinder') {
        [pscustomobject][ordered]@{
            SurfaceType = 'cylinder'
            BodyRuntimeIndex = $feature['body_runtime_index']
            FaceRuntimeIndex = $feature['face_runtime_index']
            Radius_mm_Local = $feature['radius_mm_local']
            Radius_mm_Assembly = $feature['radius_mm_assembly']
            OriginAssembly_mm = @($feature['origin_assembly_mm']) -join ', '
            AxisAssembly_Unit = @($feature['axis_assembly_unit']) -join ', '
            FaceArea_mm2 = $feature['face_area_mm2']
            FaceInSurfaceSense = $feature['face_in_surface_sense']
            FaceBoxLocal_mm_Approx = @($feature['face_box_local_mm_approx']) -join ', '
        } | Format-List
    } else {
        [pscustomobject][ordered]@{
            SurfaceType = 'plane'
            BodyRuntimeIndex = $feature['body_runtime_index']
            FaceRuntimeIndex = $feature['face_runtime_index']
            RootPointAssembly_mm = @($feature['root_point_assembly_mm']) -join ', '
            NormalAssembly_Unit = @($feature['normal_assembly_unit']) -join ', '
            FaceArea_mm2 = $feature['face_area_mm2']
            FaceInSurfaceSense = $feature['face_in_surface_sense']
            FaceBoxLocal_mm_Approx = @($feature['face_box_local_mm_approx']) -join ', '
        } | Format-List
    }
}
