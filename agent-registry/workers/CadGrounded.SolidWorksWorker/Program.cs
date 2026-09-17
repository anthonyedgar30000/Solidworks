using System.Globalization;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text.Json.Serialization;
using SolidWorks.Interop.sldworks;
using SwConst = SolidWorks.Interop.swconst;

namespace CadGrounded.SolidWorksWorker;

internal static class Program
{
    private const string Version = "0.2.0";
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
    };

    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            if (args.Length == 0)
            {
                PrintUsage();
                return 2;
            }

            return args[0].ToLowerInvariant() switch
            {
                "status" => RunCli("sw.status", JsonDocument.Parse("{}").RootElement),
                "components" => RunComponentsCli(args.Skip(1).ToArray()),
                "closest-distance" => RunClosestDistanceCli(args.Skip(1).ToArray()),
                "execute-json" => RunExecuteJson(),
                "serve-stdio" => RunServeStdio(),
                "version" or "--version" or "-v" => PrintVersion(),
                _ => Fail($"Unknown command: {args[0]}", 2)
            };
        }
        catch (Exception ex)
        {
            WriteEnvelope(new Envelope(
                ok: false,
                command_id: null,
                source_classification: null,
                data: null,
                error: ErrorObject.FromException(ex)));
            return 1;
        }
    }

    private static int PrintVersion()
    {
        Console.WriteLine($"CadGrounded.SolidWorksWorker {Version}");
        return 0;
    }

    private static int RunComponentsCli(string[] args)
    {
        var topLevelOnly = true;
        foreach (var arg in args)
        {
            if (arg == "--all")
                topLevelOnly = false;
            else
                return Fail($"Unknown components option: {arg}", 2);
        }

        using var doc = JsonDocument.Parse(JsonSerializer.Serialize(new
        {
            top_level_only = topLevelOnly
        }));

        return RunCli("sw.query_components", doc.RootElement);
    }

    private static int RunClosestDistanceCli(string[] args)
    {
        string? a = null;
        string? b = null;

        for (var i = 0; i < args.Length; i++)
        {
            switch (args[i])
            {
                case "--a":
                    a = RequireNext(args, ref i, "--a");
                    break;
                case "--b":
                    b = RequireNext(args, ref i, "--b");
                    break;
                default:
                    return Fail($"Unknown closest-distance option: {args[i]}", 2);
            }
        }

        if (string.IsNullOrWhiteSpace(a) || string.IsNullOrWhiteSpace(b))
            return Fail("closest-distance requires --a <exact Name2> and --b <exact Name2>.", 2);

        using var doc = JsonDocument.Parse(JsonSerializer.Serialize(new
        {
            a_name_exact = a,
            b_name_exact = b
        }));

        return RunCli("sw.closest_distance_pair", doc.RootElement);
    }

    private static string RequireNext(string[] args, ref int i, string option)
    {
        if (i + 1 >= args.Length)
            throw new ArgumentException($"{option} requires a value.");
        i++;
        return args[i];
    }

    private static int RunCli(string commandId, JsonElement payload)
    {
        var result = Dispatcher.Execute(commandId, payload);
        WriteEnvelope(result);
        return result.ok ? 0 : 1;
    }

    private static int RunExecuteJson()
    {
        var input = Console.In.ReadToEnd();
        if (string.IsNullOrWhiteSpace(input))
            return Fail("execute-json requires one JSON request on stdin.", 2);

        using var doc = JsonDocument.Parse(input);
        var request = Request.Parse(doc.RootElement);
        var result = Dispatcher.Execute(request.command_id, request.payload);
        WriteEnvelope(result);
        return result.ok ? 0 : 1;
    }

    private static int RunServeStdio()
    {
        string? line;
        while ((line = Console.ReadLine()) is not null)
        {
            if (string.IsNullOrWhiteSpace(line))
                continue;

            Envelope result;
            try
            {
                using var doc = JsonDocument.Parse(line);
                var request = Request.Parse(doc.RootElement);
                result = Dispatcher.Execute(request.command_id, request.payload);
            }
            catch (Exception ex)
            {
                result = new Envelope(
                    ok: false,
                    command_id: null,
                    source_classification: null,
                    data: null,
                    error: ErrorObject.FromException(ex));
            }

            Console.WriteLine(JsonSerializer.Serialize(result, JsonOptions));
            Console.Out.Flush();
        }

        return 0;
    }

    private static void WriteEnvelope(Envelope envelope)
    {
        Console.WriteLine(JsonSerializer.Serialize(envelope, JsonOptions));
    }

    private static int Fail(string message, int code)
    {
        Console.Error.WriteLine(message);
        return code;
    }

    private static void PrintUsage()
    {
        Console.WriteLine("""
CadGrounded.SolidWorksWorker v0.1.0

READ-ONLY COMMANDS
  status
  components [--all]
  closest-distance --a <exact Name2> --b <exact Name2>
  execute-json
  serve-stdio
  version

execute-json request:
  {"command_id":"sw.status","payload":{}}

serve-stdio:
  One compact JSON request per line; one compact JSON response per line.

There is intentionally no generic execute-code command and no CAD write command.
""");
    }
}

internal static class Dispatcher
{
    private static readonly HashSet<string> AllowList = new(StringComparer.Ordinal)
    {
        "sw.status",
        "sw.query_components",
        "sw.closest_distance_pair",
        "sw.classify_contact_pair"
    };

    public static Envelope Execute(string commandId, JsonElement payload)
    {
        if (!AllowList.Contains(commandId))
        {
            return new Envelope(
                ok: false,
                command_id: commandId,
                source_classification: null,
                data: null,
                error: new ErrorObject(
                    type: "blocked_command",
                    message: $"Command '{commandId}' is not in the read-only allowlist.",
                    hresult: null,
                    stack: null));
        }

        try
        {
            using var session = SolidWorksSession.Attach();

            object data = commandId switch
            {
                "sw.status" => session.Status(),
                "sw.query_components" => session.QueryComponents(
                    JsonHelpers.GetOptionalBool(payload, "top_level_only", true)),
                "sw.closest_distance_pair" => session.ClosestDistancePair(
                    JsonHelpers.GetRequiredString(payload, "a_name_exact"),
                    JsonHelpers.GetRequiredString(payload, "b_name_exact")),
                "sw.classify_contact_pair" => session.ClassifyContactPair(
                    JsonHelpers.GetRequiredString(payload, "a_name_exact"),
                    JsonHelpers.GetRequiredString(payload, "b_name_exact")),
                _ => throw new InvalidOperationException("Unreachable command dispatch.")
            };

            return new Envelope(
                ok: true,
                command_id: commandId,
                source_classification: "verified_from_solidworks_api",
                data: data,
                error: null);
        }
        catch (Exception ex)
        {
            return new Envelope(
                ok: false,
                command_id: commandId,
                source_classification: null,
                data: null,
                error: ErrorObject.FromException(ex));
        }
    }
}

internal sealed class SolidWorksSession : IDisposable
{
    private readonly SldWorks _app;
    private readonly IModelDoc2 _doc;

    private SolidWorksSession(SldWorks app, IModelDoc2 doc)
    {
        _app = app;
        _doc = doc;
    }

    public static SolidWorksSession Attach()
    {
        object raw;
        try
        {
            raw = ComRot.GetActiveObject("SldWorks.Application");
        }
        catch (COMException ex)
        {
            throw new CadGroundedException(
                "solidworks_not_running",
                "Could not obtain a running SOLIDWORKS automation object.",
                ex);
        }

        if (raw is not SldWorks app)
        {
            throw new CadGroundedException(
                "solidworks_type_mismatch",
                $"Running object could not be cast to SldWorks; actual type={raw.GetType().FullName}.");
        }

        var active = app.ActiveDoc;
        if (active is not IModelDoc2 doc)
        {
            throw new CadGroundedException(
                "no_active_document",
                "SOLIDWORKS automation object has no active IModelDoc2.");
        }

        return new SolidWorksSession(app, doc);
    }

    public object Status()
    {
        return new
        {
            worker_version = "0.1.0",
            cad_path = "native C# -> SOLIDWORKS interop (NO MCP)",
            write_authority = "NONE",
            solidworks_revision = Safe(() => _app.RevisionNumber()),
            solidworks_process_id = Safe(() => (object)_app.GetProcessID()),
            document = new
            {
                title = _doc.GetTitle(),
                path = _doc.GetPathName(),
                type = DocumentTypeName(_doc.GetType())
            }
        };
    }

    public object QueryComponents(bool topLevelOnly)
    {
        var assembly = RequireAssembly();
        var components = GetComponents(assembly, topLevelOnly);

        var rows = components.Select(c =>
        {
            var fieldErrors = new List<string>();

            var suppressionState = c.GetSuppression2();
            var fixedComponent = SafeBool(() => c.IsFixed());

            IComponent2? parent = null;
            try
            {
                parent = c.GetParent() as IComponent2;
            }
            catch (Exception ex)
            {
                fieldErrors.Add("GetParent: " + ex.Message);
            }

            double[]? transformArray = null;
            double[]? rotation9 = null;
            double[]? translationM = null;
            double[]? translationMm = null;
            double? transformScale = null;

            try
            {
                var transform = c.Transform2;

                if (transform is not null)
                {
                    transformArray = ToDoubleArray(transform.ArrayData);

                    if (transformArray is { Length: >= 12 })
                    {
                        rotation9 = transformArray
                            .Take(9)
                            .ToArray();

                        translationM = new[]
                        {
                            transformArray[9],
                            transformArray[10],
                            transformArray[11]
                        };

                        translationMm = Scale(translationM, 1000.0);

                        if (transformArray.Length >= 13)
                            transformScale = transformArray[12];
                    }
                }
            }
            catch (Exception ex)
            {
                fieldErrors.Add("Transform2: " + ex.Message);
            }

            double[]? getBoxM = null;
            double[]? getBoxMm = null;
            double[]? boxMinMm = null;
            double[]? boxMaxMm = null;

            try
            {
                var rawBox = c.GetBox(false, false);
                getBoxM = ToDoubleArray(rawBox);

                if (getBoxM is { Length: >= 6 })
                {
                    getBoxMm = Scale(getBoxM, 1000.0);

                    boxMinMm = new[]
                    {
                        getBoxM[0] * 1000.0,
                        getBoxM[1] * 1000.0,
                        getBoxM[2] * 1000.0
                    };

                    boxMaxMm = new[]
                    {
                        getBoxM[3] * 1000.0,
                        getBoxM[4] * 1000.0,
                        getBoxM[5] * 1000.0
                    };
                }
            }
            catch (Exception ex)
            {
                fieldErrors.Add("GetBox: " + ex.Message);
            }

            object? boundingBoxApprox = null;

            if (boxMinMm is not null && boxMaxMm is not null)
            {
                boundingBoxApprox = new
                {
                    min = boxMinMm,
                    max = boxMaxMm,
                    source = "Component2.GetBox(false,false)",
                    source_classification =
                        "approximate_from_solidworks_getbox"
                };
            }

            return new
            {
                name2 = c.Name2,
                path = c.GetPathName(),

                referenced_configuration =
                    c.ReferencedConfiguration,

                suppression_state = suppressionState,
                suppressed =
                    suppressionState ==
                    (int)SwConst.swComponentSuppressionState_e
                        .swComponentSuppressed,

                @fixed = fixedComponent,
                fixed_component = fixedComponent,

                parent_name = parent?.Name2,
                is_top_level = parent is null,

                transform_array = transformArray,
                rotation9 = rotation9,
                translation_m = translationM,
                translation_mm = translationMm,
                scale = transformScale,

                transform_source = "Component2.Transform2",
                source_classification = "solidworks_api",

                bounding_box_mm_approx = boundingBoxApprox,

                getbox_m = getBoxM,
                getbox_mm = getBoxMm,
                box_min_mm = boxMinMm,
                box_max_mm = boxMaxMm,

                geometry_note =
                    "Component2.GetBox(false,false) is approximate screening geometry, not exact body geometry.",

                field_errors = fieldErrors.ToArray()
            };
        }).ToArray();

        return new
        {
            document = _doc.GetTitle(),
            document_title = _doc.GetTitle(),
            document_path = _doc.GetPathName(),
            top_level_only = topLevelOnly,
            component_count = rows.Length,
            components = rows
        };
    }
    public object ClosestDistancePair(string aExact, string bExact)
    {
        var assembly = RequireAssembly();
        var components = GetComponents(assembly, topLevelOnly: true);

        var aMatches = components
            .Where(c => string.Equals(c.Name2, aExact, StringComparison.Ordinal))
            .ToArray();
        var bMatches = components
            .Where(c => string.Equals(c.Name2, bExact, StringComparison.Ordinal))
            .ToArray();

        if (aMatches.Length != 1 || bMatches.Length != 1)
        {
            throw new CadGroundedException(
                "component_match_not_unique",
                $"Exact top-level component matching must be unique. " +
                $"a_matches={aMatches.Length}, b_matches={bMatches.Length}. " +
                $"a='{aExact}', b='{bExact}'.");
        }

        var a = aMatches[0];
        var b = bMatches[0];

        var aState = a.GetSuppression2();
        var bState = b.GetSuppression2();

        var aResolved =
            aState == (int)SwConst.swComponentSuppressionState_e.swComponentFullyResolved ||
            aState == (int)SwConst.swComponentSuppressionState_e.swComponentResolved;

        var bResolved =
            bState == (int)SwConst.swComponentSuppressionState_e.swComponentFullyResolved ||
            bState == (int)SwConst.swComponentSuppressionState_e.swComponentResolved;

        if (!aResolved || !bResolved)
        {
            throw new CadGroundedException(
                "component_not_resolved",
                $"ClosestDistance requires resolved components. " +
                $"a_state={aState}, b_state={bState}.");
        }

        object pointA;
        object pointB;

        double distanceM;
        try
        {
            // This is deliberately the ONLY geometry call in this command.
            // The assembly interference detector is not invoked here.
            distanceM = _doc.ClosestDistance(a, b, out pointA, out pointB);
        }
        catch (COMException ex)
        {
            throw new CadGroundedException(
                "closest_distance_com_fault",
                $"IModelDoc2.ClosestDistance failed for '{a.Name2}' and '{b.Name2}'.",
                ex);
        }

        var aPointM = ToDoubleArray(pointA);
        var bPointM = ToDoubleArray(pointB);

        var distanceMm = distanceM * 1000.0;

        return new
        {
            document = new
            {
                title = _doc.GetTitle(),
                path = _doc.GetPathName()
            },
            component_a = ComponentIdentity(a, aState),
            component_b = ComponentIdentity(b, bState),
            minimum_distance_m = distanceM,
            minimum_distance_mm = distanceMm,
            closest_point_a_m = aPointM,
            closest_point_b_m = bPointM,
            closest_point_a_mm = Scale(aPointM, 1000.0),
            closest_point_b_mm = Scale(bPointM, 1000.0),
            metric_relation = distanceM < 0
                ? "measurement_failed_or_unsupported"
                : distanceM <= 0.000001
                    ? "zero_within_1um"
                    : "positive_clearance",
            interpretation_note =
                "Metric distance alone does not distinguish exact contact from physical interference. " +
                "No interference API was called.",
            api = "IModelDoc2.ClosestDistance",
            evidence = "verified_from_solidworks_api",
            write_authority = "NONE"
        };
    }

    public object ClassifyContactPair(string aExact, string bExact)
    {
        var assembly = RequireAssembly();
        var components = GetComponents(assembly, topLevelOnly: true);

        var aMatches = components
            .Where(c => string.Equals(c.Name2, aExact, StringComparison.Ordinal))
            .ToArray();
        var bMatches = components
            .Where(c => string.Equals(c.Name2, bExact, StringComparison.Ordinal))
            .ToArray();

        if (aMatches.Length != 1 || bMatches.Length != 1)
        {
            throw new CadGroundedException(
                "component_match_not_unique",
                $"Exact top-level component matching must be unique. " +
                $"a_matches={aMatches.Length}, b_matches={bMatches.Length}. " +
                $"a='{aExact}', b='{bExact}'.");
        }

        var a = aMatches[0];
        var b = bMatches[0];

        if (string.Equals(a.Name2, b.Name2, StringComparison.Ordinal))
            throw new CadGroundedException(
                "same_component",
                "Contact classification requires two different components.");

        var aState = a.GetSuppression2();
        var bState = b.GetSuppression2();

        var aResolved =
            aState == (int)SwConst.swComponentSuppressionState_e.swComponentFullyResolved ||
            aState == (int)SwConst.swComponentSuppressionState_e.swComponentResolved;
        var bResolved =
            bState == (int)SwConst.swComponentSuppressionState_e.swComponentFullyResolved ||
            bState == (int)SwConst.swComponentSuppressionState_e.swComponentResolved;

        if (!aResolved || !bResolved)
        {
            throw new CadGroundedException(
                "component_not_resolved",
                $"Contact classification requires resolved components. " +
                $"a_state={aState}, b_state={bState}.");
        }

        object pointA;
        object pointB;
        double distanceM;

        try
        {
            distanceM = _doc.ClosestDistance(a, b, out pointA, out pointB);
        }
        catch (COMException ex)
        {
            throw new CadGroundedException(
                "closest_distance_com_fault",
                $"IModelDoc2.ClosestDistance failed for '{a.Name2}' and '{b.Name2}'.",
                ex);
        }

        if (distanceM < 0.0)
        {
            throw new CadGroundedException(
                "closest_distance_failed",
                $"IModelDoc2.ClosestDistance returned {distanceM} for '{a.Name2}' and '{b.Name2}'.");
        }

        const double contactToleranceM = 0.000001;       // 0.001 mm
        const double volumeToleranceM3 = 0.000000000001; // 0.001 mm^3

        var booleanExecuted = distanceM <= contactToleranceM;
        var booleanErrorCodes = new List<int>();
        var bodyPairCount = 0;
        var intersectionBodyCount = 0;
        var intersectionVolumeM3 = 0.0;
        var aBodies = Array.Empty<IBody2>();
        var bBodies = Array.Empty<IBody2>();

        if (booleanExecuted)
        {
            aBodies = GetSolidBodies(a);
            bBodies = GetSolidBodies(b);

            if (aBodies.Length == 0 || bBodies.Length == 0)
            {
                return new { document = new { title = _doc.GetTitle(), path = _doc.GetPathName() }, component_a = ComponentIdentity(a, aState), component_b = ComponentIdentity(b, bState), minimum_distance_m = distanceM, minimum_distance_mm = distanceM * 1000.0, closest_point_a_mm = Scale(ToDoubleArray(pointA), 1000.0), closest_point_b_mm = Scale(ToDoubleArray(pointB), 1000.0), classification = "indeterminate_non_solid_geometry", contact_tolerance_mm = contactToleranceM * 1000.0, volume_tolerance_mm3 = volumeToleranceM3 * 1e9, solid_body_count_a = aBodies.Length, solid_body_count_b = bBodies.Length, boolean_executed = true, model_mutation = false, write_authority = "NONE", evidence = "verified_from_solidworks_api" };
            }

            foreach (var aBody in aBodies)
            {
                foreach (var bBody in bBodies)
                {
                    bodyPairCount++;
                    var aCopy = aBody.Copy() as IBody2;
                    var bCopy = bBody.Copy() as IBody2;
                    if (aCopy is null || bCopy is null) throw new CadGroundedException("temporary_body_copy_failed", "Body2.Copy did not return two temporary bodies.");
                    if (!aCopy.ApplyTransform(a.Transform2) || !bCopy.ApplyTransform(b.Transform2)) throw new CadGroundedException("temporary_body_transform_failed", "Failed to transform temporary body copies into assembly coordinates.");
                    int errorCode; object raw;
                    try { raw = aCopy.Operations2((int)SwConst.swBodyOperationType_e.SWBODYINTERSECT, bCopy, out errorCode); }
                    catch (COMException ex) { throw new CadGroundedException(
                        "body_intersection_com_fault",
                        $"Body2.Operations2(SWBODYINTERSECT) failed for '{a.Name2}' and '{b.Name2}'.", ex); }
                    booleanErrorCodes.Add(errorCode);
                    if (raw is not Array resultBodies) continue;
                    foreach (var rawBody in resultBodies)
                    {
                        if (rawBody is not IBody2 resultBody) continue;
                        var mass = ToDoubleArray(resultBody.GetMassProperties(1.0));
                        if (mass is null || mass.Length <= 3) continue;
                        var volume = mass[3];
                         if (volume > volumeToleranceM3) { intersectionBodyCount++; intersectionVolumeM3 += volume; }
                    }
                }
            }
        }

        var distinctErrors = booleanErrorCodes.Distinct().OrderBy(v => v).ToArray();
        var hasBooleanError = distinctErrors.Any(v => v != 0);
        string classification;

        if (distanceM > contactToleranceM) classification = "clearance";
        else if (hasBooleanError) classification = "indeterminate_boolean_error";
        else if (intersectionVolumeM3 > volumeToleranceM3) classification = "physical_interference";
        else classification = "contact_or_coincidence_within_tolerance";

        return new { document = new { title = _doc.GetTitle(), path = _doc.GetPathName() }, component_a = ComponentIdentity(a, aState), component_b = ComponentIdentity(b, bState), minimum_distance_m = distanceM, minimum_distance_mm = distanceM * 1000.0, closest_point_a_m = ToDoubleArray(pointA), closest_point_b_m = ToDoubleArray(pointB), closest_point_a_mm = Scale(ToDoubleArray(pointA), 1000.0), closest_point_b_mm = Scale(ToDoubleArray(pointB), 1000.0), classification = classification, contact_tolerance_mm = contactToleranceM * 1000.0, volume_tolerance_mm3 = volumeToleranceM3 * 1e9, solid_body_count_a = booleanExecuted ? aBodies.Length : (int?)null, solid_body_count_b = booleanExecuted ? bBodies.Length : (int?)null, body_pair_count = booleanExecuted ? bodyPairCount : (int?)null, intersection_body_count = booleanExecuted ? intersectionBodyCount : (int?)null, intersection_volume_mm3 = booleanExecuted ? intersectionVolumeM3 * 1e9 : (double?)null, boolean_error_codes = booleanExecuted ? distinctErrors : null, boolean_executed = booleanExecuted, api_distance = "IModelDoc2.ClosestDistance", api_intersection = "IBody2.Operations2(SWBODYINTERSECT) on transformed temporary body copies", interpretation_note = "Positive clearance excludes contact. Near-zero distance is classified with exact B-rep intersection volume on temporary copies; no assembly interference manager is invoked.", model_mutation = false, write_authority = "NONE", evidence = "verified_from_solidworks_api" };
    }

    private static IBody2[] GetSolidBodies(IComponent2 component)
    {
        object bodiesInfo;
        var raw = component.GetBodies3((int)SwConst.swBodyType_e.swSolidBody, out bodiesInfo);
        if (raw is null) return Array.Empty<IBody2>();
        if (raw is object[] objects) return objects.OfType<IBody2>().ToArray();
        if (raw is Array array)
        {
            var list = new List<IBody2>();
            foreach (var item in array) if (item is IBody2 body) list.Add(body);
            return list.ToArray();
        }
        throw new CadGroundedException("unexpected_body_array", $"IComponent2.GetBodies3 returned unsupported type '{raw.GetType().FullName}'.");
    }
    private static object ComponentIdentity(IComponent2 c, int state) => new
    {
        name2 = c.Name2,
        path = c.GetPathName(),
        suppression_state = state
    };

    private IAssemblyDoc RequireAssembly()
    {
        if (_doc.GetType() != (int)SwConst.swDocumentTypes_e.swDocASSEMBLY)
        {
            throw new CadGroundedException(
                "active_document_not_assembly",
                $"Active document '{_doc.GetTitle()}' is not an assembly.");
        }

        if (_doc is not IAssemblyDoc assembly)
        {
            throw new CadGroundedException(
                "assembly_interface_unavailable",
                $"Active document '{_doc.GetTitle()}' could not be cast to IAssemblyDoc.");
        }

        return assembly;
    }

    private static IComponent2[] GetComponents(IAssemblyDoc assembly, bool topLevelOnly)
    {
        var raw = assembly.GetComponents(topLevelOnly);
        if (raw is null)
            return Array.Empty<IComponent2>();

        if (raw is object[] objects)
            return objects.OfType<IComponent2>().ToArray();

        if (raw is Array array)
        {
            var list = new List<IComponent2>();
            foreach (var item in array)
            {
                if (item is IComponent2 c)
                    list.Add(c);
            }
            return list.ToArray();
        }

        throw new CadGroundedException(
            "unexpected_component_array",
            $"IAssemblyDoc.GetComponents returned unsupported type '{raw.GetType().FullName}'.");
    }

    private static double[]? ToDoubleArray(object? value)
    {
        if (value is null)
            return null;

        if (value is double[] doubles)
            return doubles;

        if (value is Array array)
        {
            var result = new double[array.Length];
            for (var i = 0; i < array.Length; i++)
                result[i] = Convert.ToDouble(array.GetValue(i), CultureInfo.InvariantCulture);
            return result;
        }

        return null;
    }

    private static double[]? Scale(double[]? values, double factor)
    {
        if (values is null)
            return null;

        var result = new double[values.Length];
        for (var i = 0; i < values.Length; i++)
            result[i] = values[i] * factor;
        return result;
    }

    private static object? Safe(Func<object?> getter)
    {
        try { return getter(); }
        catch { return null; }
    }

    private static bool? SafeBool(Func<bool> getter)
    {
        try { return getter(); }
        catch { return null; }
    }

    private static string DocumentTypeName(int value)
    {
        return value switch
        {
            (int)SwConst.swDocumentTypes_e.swDocPART => "part",
            (int)SwConst.swDocumentTypes_e.swDocASSEMBLY => "assembly",
            (int)SwConst.swDocumentTypes_e.swDocDRAWING => "drawing",
            _ => $"unknown:{value}"
        };
    }

    public void Dispose()
    {
        // This process does not own SOLIDWORKS. Do not force-release its shared app/doc RCWs.
    }
}


internal static class ComRot
{
    [DllImport("ole32.dll", CharSet = CharSet.Unicode)]
    private static extern int CLSIDFromProgID(
        string lpszProgID,
        out Guid lpclsid);

    [DllImport("oleaut32.dll", PreserveSig = false)]
    [return: MarshalAs(UnmanagedType.Interface)]
    private static extern object GetActiveObject(
        ref Guid rclsid,
        IntPtr pvReserved);

    public static object GetActiveObject(string progId)
    {
        var hr = CLSIDFromProgID(progId, out var clsid);

        if (hr != 0)
            Marshal.ThrowExceptionForHR(hr);

        return GetActiveObject(ref clsid, IntPtr.Zero);
    }
}
internal static class JsonHelpers
{
    public static string GetRequiredString(JsonElement payload, string name)
    {
        if (payload.ValueKind != JsonValueKind.Object ||
            !payload.TryGetProperty(name, out var value) ||
            value.ValueKind != JsonValueKind.String ||
            string.IsNullOrWhiteSpace(value.GetString()))
        {
            throw new ArgumentException($"payload.{name} is required and must be a non-empty string.");
        }

        return value.GetString()!;
    }

    public static bool GetOptionalBool(JsonElement payload, string name, bool defaultValue)
    {
        if (payload.ValueKind != JsonValueKind.Object ||
            !payload.TryGetProperty(name, out var value))
            return defaultValue;

        return value.ValueKind switch
        {
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            _ => throw new ArgumentException($"payload.{name} must be true or false.")
        };
    }
}

internal sealed record Request(string command_id, JsonElement payload)
{
    public static Request Parse(JsonElement root)
    {
        if (root.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("Request must be a JSON object.");

        if (!root.TryGetProperty("command_id", out var commandIdElement) ||
            commandIdElement.ValueKind != JsonValueKind.String ||
            string.IsNullOrWhiteSpace(commandIdElement.GetString()))
        {
            throw new ArgumentException("request.command_id is required.");
        }

        JsonElement payload;
        if (root.TryGetProperty("payload", out var payloadElement))
            payload = payloadElement.Clone();
        else
            payload = JsonDocument.Parse("{}").RootElement.Clone();

        return new Request(commandIdElement.GetString()!, payload);
    }
}

internal sealed record Envelope(
    bool ok,
    string? command_id,
    string? source_classification,
    object? data,
    ErrorObject? error);

internal sealed record ErrorObject(
    string type,
    string message,
    string? hresult,
    string? stack)
{
    public static ErrorObject FromException(Exception ex)
    {
        var root = ex is CadGroundedException cg && cg.InnerException is not null
            ? cg.InnerException
            : ex;

        var hr = root is COMException com
            ? $"0x{com.HResult:X8}"
            : ex.HResult != 0
                ? $"0x{ex.HResult:X8}"
                : null;

        return new ErrorObject(
            type: ex is CadGroundedException cge ? cge.Code : ex.GetType().Name,
            message: ex.Message,
            hresult: hr,
            stack: ex.StackTrace);
    }
}

internal sealed class CadGroundedException : Exception
{
    public string Code { get; }

    public CadGroundedException(string code, string message) : base(message)
    {
        Code = code;
    }

    public CadGroundedException(string code, string message, Exception inner) : base(message, inner)
    {
        Code = code;
    }
}




