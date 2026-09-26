using System.Globalization;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text.Json.Serialization;
using SolidWorks.Interop.sldworks;
using SwConst = SolidWorks.Interop.swconst;

namespace CadGrounded.SolidWorksWorker;

internal static class Program
{
    internal const string Version = "0.4.3";
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
                "interface-contract" => RunInterfaceContractCli(args.Skip(1).ToArray()),
                "interface-connectors-diagnostic" => RunInterfaceConnectorDiagnosticCli(args.Skip(1).ToArray()),
                "feature-manager-tree-diagnostic" => RunFeatureManagerTreeDiagnosticCli(args.Skip(1).ToArray()),
                "closest-distance" => RunClosestDistanceCli(args.Skip(1).ToArray()),
                "mates" => RunMatesCli(args.Skip(1).ToArray()),
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

    private static int RunInterfaceContractCli(string[] args)
    {
        var coordinateSystemNames = new List<string>();
        var connectorNames = new List<string>();

        for (var i = 0; i < args.Length; i++)
        {
            switch (args[i])
            {
                case "--coordinate-system":
                    coordinateSystemNames.Add(RequireNext(args, ref i, "--coordinate-system"));
                    break;
                case "--connector":
                    connectorNames.Add(RequireNext(args, ref i, "--connector"));
                    break;
                default:
                    return Fail($"Unknown interface-contract option: {args[i]}", 2);
            }
        }

        if (coordinateSystemNames.Count == 0 || connectorNames.Count == 0)
        {
            return Fail(
                "interface-contract requires one or more --coordinate-system <exact feature name> " +
                "and one or more --connector <exact feature name>.",
                2);
        }

        using var doc = JsonDocument.Parse(JsonSerializer.Serialize(new
        {
            coordinate_system_feature_names = coordinateSystemNames,
            published_reference_connector_names = connectorNames
        }));

        return RunCli("sw.query_interface_contract", doc.RootElement);
    }

    private static int RunInterfaceConnectorDiagnosticCli(string[] args)
    {
        var connectorNames = new List<string>();

        for (var i = 0; i < args.Length; i++)
        {
            switch (args[i])
            {
                case "--connector":
                    connectorNames.Add(RequireNext(args, ref i, "--connector"));
                    break;
                default:
                    return Fail($"Unknown interface-connectors-diagnostic option: {args[i]}", 2);
            }
        }

        if (connectorNames.Count == 0)
        {
            return Fail(
                "interface-connectors-diagnostic requires one or more --connector <exact feature name>.",
                2);
        }

        using var doc = JsonDocument.Parse(JsonSerializer.Serialize(new
        {
            published_reference_connector_names = connectorNames
        }));

        return RunCli("sw.diagnose_interface_connectors", doc.RootElement);
    }

    private static int RunFeatureManagerTreeDiagnosticCli(string[] args)
    {
        var treeTexts = new List<string>();

        for (var i = 0; i < args.Length; i++)
        {
            switch (args[i])
            {
                case "--tree-text":
                    treeTexts.Add(RequireNext(args, ref i, "--tree-text"));
                    break;
                default:
                    return Fail($"Unknown feature-manager-tree-diagnostic option: {args[i]}", 2);
            }
        }

        if (treeTexts.Count == 0)
        {
            return Fail(
                "feature-manager-tree-diagnostic requires one or more --tree-text <exact displayed tree text>.",
                2);
        }

        using var doc = JsonDocument.Parse(JsonSerializer.Serialize(new
        {
            displayed_tree_texts = treeTexts
        }));

        return RunCli("sw.diagnose_feature_manager_tree", doc.RootElement);
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

    private static int RunMatesCli(string[] args)
    {
        string? componentName = null;

        for (var i = 0; i < args.Length; i++)
        {
            switch (args[i])
            {
                case "--component":
                    componentName = RequireNext(args, ref i, "--component");
                    break;
                default:
                    return Fail($"Unknown mates option: {args[i]}", 2);
            }
        }

        if (string.IsNullOrWhiteSpace(componentName))
            return Fail("mates requires --component <exact Name2>.", 2);

        using var doc = JsonDocument.Parse(JsonSerializer.Serialize(new
        {
            component_name_exact = componentName
        }));

        return RunCli("sw.query_mates", doc.RootElement);
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
        Console.WriteLine($$"""
CadGrounded.SolidWorksWorker v{{Version}}

READ-ONLY COMMANDS
  status
  components [--all]
  interface-contract --coordinate-system <exact feature name> [--coordinate-system <exact feature name> ...] --connector <exact feature name> [--connector <exact feature name> ...]
  interface-connectors-diagnostic --connector <exact feature name> [--connector <exact feature name> ...]
  feature-manager-tree-diagnostic --tree-text <exact displayed tree text> [--tree-text <exact displayed tree text> ...]
  closest-distance --a <exact Name2> --b <exact Name2>
  mates --component <exact Name2>
  execute-json
  serve-stdio
  version

execute-json request:
  {"command_id":"sw.status","payload":{} }

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
        "sw.query_interface_contract",
        "sw.diagnose_interface_connectors",
        "sw.diagnose_feature_manager_tree",
        "sw.closest_distance_pair",
        "sw.classify_contact_pair",
        "sw.classify_contact_pair_at_transform",
        "sw.query_mates"
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

            if (commandId == "sw.query_interface_contract")
            {
                JsonHelpers.RequireOnlyProperties(
                    payload,
                    "coordinate_system_feature_names",
                    "published_reference_connector_names");
            }
            else if (commandId == "sw.diagnose_interface_connectors")
            {
                JsonHelpers.RequireOnlyProperties(
                    payload,
                    "published_reference_connector_names");
            }
            else if (commandId == "sw.diagnose_feature_manager_tree")
            {
                JsonHelpers.RequireOnlyProperties(
                    payload,
                    "displayed_tree_texts");
            }
            else if (commandId == "sw.classify_contact_pair_at_transform")
            {
                JsonHelpers.RequireOnlyProperties(
                    payload,
                    "document_title_exact",
                    "document_path_exact",
                    "active_configuration_exact",
                    "a_name_exact",
                    "b_name_exact",
                    "a_candidate_transform",
                    "b_candidate_transform");
            }

            object data = commandId switch
            {
                "sw.status" => session.Status(),
                "sw.query_components" => session.QueryComponents(
                    JsonHelpers.GetOptionalBool(payload, "top_level_only", true)),
                "sw.query_interface_contract" => session.QueryInterfaceContract(
                    JsonHelpers.GetRequiredUniqueStringArray(
                        payload,
                        "coordinate_system_feature_names"),
                    JsonHelpers.GetRequiredUniqueStringArray(
                        payload,
                        "published_reference_connector_names")),
                "sw.diagnose_interface_connectors" => session.DiagnoseInterfaceConnectors(
                    JsonHelpers.GetRequiredUniqueStringArray(
                        payload,
                        "published_reference_connector_names")),
                "sw.diagnose_feature_manager_tree" => session.DiagnoseFeatureManagerTree(
                    JsonHelpers.GetRequiredUniqueStringArray(
                        payload,
                        "displayed_tree_texts")),
                "sw.closest_distance_pair" => session.ClosestDistancePair(
                    JsonHelpers.GetRequiredString(payload, "a_name_exact"),
                    JsonHelpers.GetRequiredString(payload, "b_name_exact")),
                "sw.classify_contact_pair" => session.ClassifyContactPair(
                    JsonHelpers.GetRequiredString(payload, "a_name_exact"),
                    JsonHelpers.GetRequiredString(payload, "b_name_exact")),
                "sw.classify_contact_pair_at_transform" => session.ClassifyContactPairAtTransform(
                    JsonHelpers.GetRequiredString(payload, "document_title_exact"),
                    JsonHelpers.GetRequiredString(payload, "document_path_exact"),
                    JsonHelpers.GetRequiredString(payload, "active_configuration_exact"),
                    JsonHelpers.GetRequiredString(payload, "a_name_exact"),
                    JsonHelpers.GetRequiredString(payload, "b_name_exact"),
                    JsonHelpers.GetOptionalCandidateTransform(payload, "a_candidate_transform"),
                    JsonHelpers.GetOptionalCandidateTransform(payload, "b_candidate_transform")),
                "sw.query_mates" => session.QueryMates(
                    JsonHelpers.GetRequiredString(payload, "component_name_exact")),
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
            worker_version = Program.Version,
            cad_path = "native C# -> SOLIDWORKS interop (NO MCP)",
            write_authority = "NONE",
            solidworks_revision = Safe(() => _app.RevisionNumber()),
            solidworks_process_id = Safe(() => (object)_app.GetProcessID()),
            document = new
            {
                title = _doc.GetTitle(),
                path = _doc.GetPathName(),
                type = DocumentTypeName(_doc.GetType()),
                active_configuration = Safe(() => _doc.ConfigurationManager.ActiveConfiguration.Name),
                save_flag = Safe(() => (object)_doc.GetSaveFlag())
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

    public object QueryInterfaceContract(
        string[] coordinateSystemFeatureNames,
        string[] publishedReferenceConnectorNames)
    {
        // This is intentionally a local, bounded getter-only surface. It reads
        // exact CoordSys records and the exact named connector nodes beneath
        // the visible Published References / ConnectRefMgr tree branch. It
        // never selects, edits, rebuilds, saves, or creates an Asset Publisher
        // connection.
        RequireAssembly();

        var features = EnumerateFeatures().ToArray();
        var coordinateSystems = coordinateSystemFeatureNames
            .Select(name => ReadCoordinateSystemFeature(
                RequireExactFeature(features, name, "CoordSys", "coordinate system")))
            .ToArray();
        var publishedReferenceBinding =
            ReadPublishedReferenceBindingFromFeatureManagerTree(
                publishedReferenceConnectorNames);

        return new
        {
            document = ReadDocumentState(),
            request = new
            {
                coordinate_system_feature_names = coordinateSystemFeatureNames,
                published_reference_connector_names = publishedReferenceConnectorNames
            },
            coordinate_systems = coordinateSystems,
            published_reference_features = publishedReferenceBinding.published_reference_features,
            published_reference_manager = publishedReferenceBinding.published_reference_manager,
            result_scope = "EXACT_NAMED_FEATURES_ONLY",
            published_reference_manager_binding_state = "VERIFIED_FEATURE_MANAGER_TREE_BRANCH",
            published_reference_manager_binding_note =
                "The bounded FeatureManager-tree query verified the exact Published References / " +
                "ConnectRefMgr branch and exact direct-child MagneticConnectRef identities. " +
                "Connector-to-coordinate-system geometry is not inferred from this observation.",
            geometry_binding_state = "UNRESOLVED",
            interpretation_note =
                "Matching named coordinate-system frames is an interface alignment observation only. " +
                "It does not establish Published Asset geometric coincidence, snap/mate behavior, " +
                "contact, collision clearance, motion, force, or mechanical acceptance.",
            api =
                "IModelDoc2.FirstFeature/GetNextFeature + IFeature.GetFirstSubFeature/GetNextSubFeature " +
                "-> IFeature.GetDefinition() -> ICoordinateSystemFeatureData -> Transform -> " +
                "IMathTransform.ArrayData; IModelDoc2.FeatureManager -> " +
                "IFeatureManager.GetFeatureTreeRootItem2(swFeatMgrPaneBottom) -> " +
                "ITreeControlItem.Text/GetFirstChild/GetNext/Object -> IFeature.Name/GetTypeName2",
            model_mutation = false,
            write_authority = "NONE",
            evidence = "verified_from_solidworks_api"
        };
    }

    public object DiagnoseInterfaceConnectors(string[] publishedReferenceConnectorNames)
    {
        // This diagnostic intentionally compares two bounded getter-only
        // feature-observation paths. It does not repair, rename, or otherwise
        // alter any feature, and it does not select, rebuild, or save the model.
        RequireAssembly();

        var directLookups = publishedReferenceConnectorNames
            .Select(ReadDirectConnectorLookup)
            .ToArray();

        FeatureTreeObservation[] traversal;
        string? traversalError = null;
        try
        {
            traversal = EnumerateFeatureTreeObservations().ToArray();
        }
        catch (Exception ex)
        {
            traversal = Array.Empty<FeatureTreeObservation>();
            traversalError = $"{ex.GetType().Name}: {ex.Message}";
        }

        var relevantNames = new HashSet<string>(publishedReferenceConnectorNames, StringComparer.Ordinal)
        {
            "ConnectRefMgr"
        };
        var relevantTraversal = traversal
            .Where(row => relevantNames.Contains(row.feature_name))
            .ToArray();

        var connectorDiagnostics = publishedReferenceConnectorNames
            .Select(name => ClassifyConnectorDiagnostic(
                directLookups.Single(row => string.Equals(
                    row.requested_name,
                    name,
                    StringComparison.Ordinal)),
                relevantTraversal.Where(row => string.Equals(
                    row.feature_name,
                    name,
                    StringComparison.Ordinal)),
                traversalError))
            .ToArray();

        return new
        {
            document = ReadDocumentState(),
            request = new
            {
                published_reference_connector_names = publishedReferenceConnectorNames,
                traversal_anchor_feature_name = "ConnectRefMgr"
            },
            direct_lookup = directLookups,
            traversal_observations = relevantTraversal,
            traversal_error = traversalError,
            connector_diagnostics = connectorDiagnostics,
            diagnostic_state = DetermineConnectorDiagnosticState(
                connectorDiagnostics,
                traversalError),
            result_scope = "EXACT_CONNECTOR_NAMES_PLUS_CONNECT_REF_MANAGER",
            interpretation_note =
                "This diagnostic compares IAssemblyDoc.FeatureByName with the existing recursive " +
                "feature traversal. It does not establish Published Asset geometry, connector-to-coordinate-system " +
                "coincidence, snap/mate behavior, contact, clearance, motion, force, or mechanical acceptance.",
            api =
                "IAssemblyDoc.FeatureByName -> IFeature.GetTypeName2; " +
                "IModelDoc2.FirstFeature/GetNextFeature + IFeature.GetFirstSubFeature/GetNextSubFeature " +
                "-> IFeature.Name/GetTypeName2 with parent name and tree depth",
            model_mutation = false,
            write_authority = "NONE",
            remote_queue_authorized = false,
            evidence = "verified_from_solidworks_api"
        };
    }

    public object DiagnoseFeatureManagerTree(string[] displayedTreeTexts)
    {
        // This is a separate, getter-only observation of the representation
        // rendered in the FeatureManager design tree. It does not replace the
        // ordinary IFeature traversal or direct named-feature diagnostic.
        RequireAssembly();

        var requestedTexts = new HashSet<string>(displayedTreeTexts, StringComparer.Ordinal);
        var root = RequireFeatureManagerTreeRoot();
        var observations = EnumerateFeatureManagerTreeObservations(root, requestedTexts).ToArray();
        var textDiagnostics = displayedTreeTexts
            .Select(text => ClassifyFeatureManagerTreeText(
                text,
                observations.Where(row => string.Equals(
                    row.displayed_tree_text,
                    text,
                    StringComparison.Ordinal))))
            .ToArray();

        return new
        {
            document = ReadDocumentState(),
            request = new
            {
                displayed_tree_texts = displayedTreeTexts,
                feature_manager_pane = "swFeatMgrPaneBottom"
            },
            feature_manager_tree_root_available = true,
            tree_observations = observations,
            tree_text_diagnostics = textDiagnostics,
            diagnostic_state = DetermineFeatureManagerTreeDiagnosticState(textDiagnostics),
            result_scope = "EXACT_DISPLAYED_TREE_TEXTS_ONLY",
            interpretation_note =
                "This diagnostic observes exact visible FeatureManager tree text and its associated " +
                "ITreeControlItem metadata. It does not replace or erase prior direct FeatureByName or " +
                "ordinary IFeature-traversal evidence, does not establish that a tree item is an IFeature, " +
                "and does not establish Published Asset geometry, connector-to-coordinate-system coincidence, " +
                "snap/mate behavior, contact, clearance, motion, force, or mechanical acceptance.",
            api =
                "IModelDoc2.FeatureManager -> IFeatureManager.GetFeatureTreeRootItem2(swFeatMgrPaneBottom) " +
                "-> ITreeControlItem.Text/ObjectType/Object/GetFirstChild/GetNext; " +
                "IFeature.Name/GetTypeName2 only when ITreeControlItem.Object resolves to IFeature",
            model_mutation = false,
            write_authority = "NONE",
            remote_queue_authorized = false,
            evidence = "verified_from_solidworks_api"
        };
    }

    private ITreeControlItem RequireFeatureManagerTreeRoot()
    {
        var featureManager = _doc.FeatureManager;
        if (featureManager is null)
        {
            throw new CadGroundedException(
                "feature_manager_unavailable",
                "The active document does not expose IModelDoc2.FeatureManager.");
        }

        var root = featureManager.GetFeatureTreeRootItem2(
            (int)SwConst.swFeatMgrPane_e.swFeatMgrPaneBottom) as ITreeControlItem;
        if (root is null)
        {
            throw new CadGroundedException(
                "feature_manager_tree_root_unavailable",
                "IFeatureManager.GetFeatureTreeRootItem2(swFeatMgrPaneBottom) returned no tree root.");
        }

        return root;
    }

    private FeatureManagerPublishedReferenceBinding
        ReadPublishedReferenceBindingFromFeatureManagerTree(string[] connectorNames)
    {
        if (connectorNames.Distinct(StringComparer.Ordinal).Count() != connectorNames.Length)
        {
            throw new CadGroundedException(
                "published_reference_connector_request_not_unique",
                "Published Reference connector names must be exact and unique in one bounded request.");
        }

        var root = RequireFeatureManagerTreeRoot();
        var nodes = EnumerateFeatureManagerTreeNodes(root).ToArray();
        var managerMatches = nodes
            .Where(node => string.Equals(
                node.displayed_tree_text,
                "Published References",
                StringComparison.Ordinal))
            .ToArray();

        if (managerMatches.Length != 1)
        {
            throw new CadGroundedException(
                "published_reference_manager_tree_match_not_unique",
                "Exact Published References manager tree matching must be unique. " +
                $"matches={managerMatches.Length}, displayed_text='Published References'.");
        }

        var managerNode = managerMatches[0];
        var managerFeature = RequireFeatureManagerTreeFeature(
            managerNode,
            expectedDisplayedText: "Published References",
            expectedFeatureName: "Published References",
            expectedFeatureType: "ConnectRefMgr",
            featureKind: "Published References manager");
        var managerObservation = new PublishedReferenceManagerObservation(
            displayed_tree_text: managerNode.displayed_tree_text,
            feature_name: managerFeature.Name,
            feature_type: managerFeature.GetTypeName2(),
            tree_path: managerNode.tree_path);

        var connectorObservations = connectorNames
            .Select(name => ReadPublishedReferenceConnectorFromFeatureManagerTree(
                nodes,
                managerNode,
                managerObservation,
                name))
            .ToArray();

        return new FeatureManagerPublishedReferenceBinding(
            published_reference_manager: managerObservation,
            published_reference_features: connectorObservations);
    }

    private static PublishedReferenceFeatureObservation
        ReadPublishedReferenceConnectorFromFeatureManagerTree(
            IEnumerable<FeatureManagerTreeNode> nodes,
            FeatureManagerTreeNode managerNode,
            PublishedReferenceManagerObservation managerObservation,
            string connectorName)
    {
        var connectorMatches = nodes
            .Where(node => string.Equals(
                node.parent_tree_path,
                managerNode.tree_path,
                StringComparison.Ordinal))
            .Where(node => string.Equals(
                node.displayed_tree_text,
                connectorName,
                StringComparison.Ordinal))
            .ToArray();

        if (connectorMatches.Length != 1)
        {
            throw new CadGroundedException(
                "published_reference_connector_tree_match_not_unique",
                "Exact Published Reference connector tree matching must be unique under the " +
                "exact Published References / ConnectRefMgr branch. " +
                $"matches={connectorMatches.Length}, connector='{connectorName}', " +
                $"parent_tree_path='{managerNode.tree_path}'.");
        }

        var connectorNode = connectorMatches[0];
        var connectorFeature = RequireFeatureManagerTreeFeature(
            connectorNode,
            expectedDisplayedText: connectorName,
            expectedFeatureName: connectorName,
            expectedFeatureType: "MagneticConnectRef",
            featureKind: "Published Reference connector");

        return new PublishedReferenceFeatureObservation(
            connector_name: connectorFeature.Name,
            feature_type: connectorFeature.GetTypeName2(),
            tree_path: connectorNode.tree_path,
            parent_tree_text: managerObservation.displayed_tree_text,
            parent_feature_name: managerObservation.feature_name,
            parent_feature_type: managerObservation.feature_type);
    }

    private static IFeature RequireFeatureManagerTreeFeature(
        FeatureManagerTreeNode node,
        string expectedDisplayedText,
        string expectedFeatureName,
        string expectedFeatureType,
        string featureKind)
    {
        if (!string.Equals(
                node.displayed_tree_text,
                expectedDisplayedText,
                StringComparison.Ordinal))
        {
            throw new CadGroundedException(
                "feature_manager_tree_displayed_text_mismatch",
                $"{featureKind} tree text must exactly equal '{expectedDisplayedText}'. " +
                $"Observed='{node.displayed_tree_text}'.");
        }

        var itemObject = node.item.Object;
        if (itemObject is null)
        {
            throw new CadGroundedException(
                "feature_manager_tree_object_unavailable",
                $"{featureKind} tree item '{expectedDisplayedText}' has no associated object.");
        }

        if (itemObject is not IFeature feature)
        {
            throw new CadGroundedException(
                "feature_manager_tree_object_type_mismatch",
                $"{featureKind} tree item '{expectedDisplayedText}' did not resolve to IFeature. " +
                $"RuntimeType='{itemObject.GetType().FullName}'.");
        }

        if (!string.Equals(feature.Name, expectedFeatureName, StringComparison.Ordinal))
        {
            throw new CadGroundedException(
                "feature_manager_tree_feature_name_mismatch",
                $"{featureKind} IFeature.Name must exactly equal '{expectedFeatureName}'. " +
                $"Observed='{feature.Name}'.");
        }

        var featureType = feature.GetTypeName2();
        if (!string.Equals(featureType, expectedFeatureType, StringComparison.Ordinal))
        {
            throw new CadGroundedException(
                "feature_manager_tree_feature_type_mismatch",
                $"{featureKind} IFeature.GetTypeName2() must exactly equal " +
                $"'{expectedFeatureType}'. Observed='{featureType}'.");
        }

        return feature;
    }

    private static IEnumerable<FeatureManagerTreeNode> EnumerateFeatureManagerTreeNodes(
        ITreeControlItem root)
    {
        var seen = new HashSet<ITreeControlItem>();
        foreach (var node in EnumerateFeatureManagerTreeNodesBranch(
                     root,
                     treeDepth: 0,
                     treePath: "0",
                     parentDisplayedTreeText: null,
                     parentTreePath: null,
                     seen))
        {
            yield return node;
        }
    }

    private static IEnumerable<FeatureManagerTreeNode> EnumerateFeatureManagerTreeNodesBranch(
        ITreeControlItem item,
        int treeDepth,
        string treePath,
        string? parentDisplayedTreeText,
        string? parentTreePath,
        HashSet<ITreeControlItem> seen)
    {
        if (!seen.Add(item))
        {
            throw new CadGroundedException(
                "feature_manager_tree_cycle_detected",
                "FeatureManager tree traversal encountered the same ITreeControlItem more than once.");
        }

        var displayedText = item.Text ?? string.Empty;
        yield return new FeatureManagerTreeNode(
            item: item,
            displayed_tree_text: displayedText,
            tree_depth: treeDepth,
            tree_path: treePath,
            parent_displayed_tree_text: parentDisplayedTreeText,
            parent_tree_path: parentTreePath);

        var child = item.GetFirstChild() as ITreeControlItem;
        var childIndex = 0;
        while (child is not null)
        {
            foreach (var nested in EnumerateFeatureManagerTreeNodesBranch(
                         child,
                         treeDepth + 1,
                         $"{treePath}.{childIndex}",
                         displayedText,
                         treePath,
                         seen))
            {
                yield return nested;
            }

            child = child.GetNext() as ITreeControlItem;
            childIndex++;
        }
    }

    private static IEnumerable<FeatureManagerTreeObservation> EnumerateFeatureManagerTreeObservations(
        ITreeControlItem root,
        HashSet<string> requestedTexts)
    {
        var seen = new HashSet<ITreeControlItem>();
        foreach (var observation in EnumerateFeatureManagerTreeBranch(
                     root,
                     treeDepth: 0,
                     treePath: "0",
                     requestedTexts,
                     seen))
        {
            yield return observation;
        }
    }

    private static IEnumerable<FeatureManagerTreeObservation> EnumerateFeatureManagerTreeBranch(
        ITreeControlItem item,
        int treeDepth,
        string treePath,
        HashSet<string> requestedTexts,
        HashSet<ITreeControlItem> seen)
    {
        if (!seen.Add(item))
        {
            throw new CadGroundedException(
                "feature_manager_tree_cycle_detected",
                "FeatureManager tree traversal encountered the same ITreeControlItem more than once.");
        }

        var displayedText = item.Text ?? string.Empty;
        var itemObject = item.Object;
        var feature = itemObject as IFeature;
        var observation = new FeatureManagerTreeObservation(
            displayed_tree_text: displayedText,
            tree_depth: treeDepth,
            tree_path: treePath,
            object_type: item.ObjectType,
            object_is_null: itemObject is null,
            object_runtime_dotnet_type: itemObject?.GetType().FullName,
            object_is_com_object: itemObject is null ? (bool?)null : Marshal.IsComObject(itemObject),
            feature_name: feature?.Name,
            feature_type: feature?.GetTypeName2());

        if (requestedTexts.Contains(displayedText))
            yield return observation;

        var child = item.GetFirstChild() as ITreeControlItem;
        var childIndex = 0;
        while (child is not null)
        {
            foreach (var nested in EnumerateFeatureManagerTreeBranch(
                         child,
                         treeDepth + 1,
                         $"{treePath}.{childIndex}",
                         requestedTexts,
                         seen))
            {
                yield return nested;
            }

            child = child.GetNext() as ITreeControlItem;
            childIndex++;
        }
    }

    private static FeatureManagerTreeTextDiagnostic ClassifyFeatureManagerTreeText(
        string requestedText,
        IEnumerable<FeatureManagerTreeObservation> observations)
    {
        var matches = observations.ToArray();
        return new FeatureManagerTreeTextDiagnostic(
            requested_displayed_tree_text: requestedText,
            exact_match_count: matches.Length,
            classification: matches.Length switch
            {
                0 => "NOT_OBSERVED",
                1 => "OBSERVED",
                _ => "MATCH_NOT_UNIQUE"
            });
    }

    private static string DetermineFeatureManagerTreeDiagnosticState(
        IEnumerable<FeatureManagerTreeTextDiagnostic> textDiagnostics)
    {
        var classifications = textDiagnostics
            .Select(row => row.classification)
            .ToArray();
        if (classifications.All(value => value == "OBSERVED"))
            return "ALL_REQUESTED_TREE_TEXTS_OBSERVED";
        if (classifications.All(value => value == "NOT_OBSERVED"))
            return "NO_REQUESTED_TREE_TEXTS_OBSERVED";
        if (classifications.Any(value => value == "MATCH_NOT_UNIQUE"))
            return "TREE_TEXT_MATCH_NOT_UNIQUE";
        return "PARTIAL_REQUESTED_TREE_TEXTS_OBSERVED";
    }

    private object ReadDocumentState()
    {
        var configuration = _doc.ConfigurationManager.ActiveConfiguration;
        if (configuration is null || string.IsNullOrWhiteSpace(configuration.Name))
        {
            throw new CadGroundedException(
                "active_configuration_unavailable",
                "The active configuration is required for the read-only no-mutation evidence contract.");
        }

        return new
        {
            title = _doc.GetTitle(),
            path = _doc.GetPathName(),
            type = DocumentTypeName(_doc.GetType()),
            active_configuration = configuration.Name,
            save_flag = _doc.GetSaveFlag()
        };
    }

    private IEnumerable<IFeature> EnumerateFeatures()
    {
        var seen = new HashSet<IFeature>();
        var topLevel = _doc.FirstFeature() as IFeature;

        while (topLevel is not null)
        {
            foreach (var feature in EnumerateFeatureBranch(topLevel, seen))
                yield return feature;
            topLevel = topLevel.GetNextFeature() as IFeature;
        }
    }

    private IEnumerable<FeatureTreeObservation> EnumerateFeatureTreeObservations()
    {
        var seen = new HashSet<IFeature>();
        var topLevel = _doc.FirstFeature() as IFeature;
        var topLevelIndex = 0;

        while (topLevel is not null)
        {
            foreach (var row in EnumerateFeatureTreeObservationBranch(
                         topLevel,
                         parentFeatureName: null,
                         treeDepth: 0,
                         treePath: topLevelIndex.ToString(CultureInfo.InvariantCulture),
                         seen))
            {
                yield return row;
            }

            topLevel = topLevel.GetNextFeature() as IFeature;
            topLevelIndex++;
        }
    }

    private static IEnumerable<IFeature> EnumerateFeatureBranch(
        IFeature feature,
        HashSet<IFeature> seen)
    {
        if (!seen.Add(feature))
            yield break;

        yield return feature;

        var subFeature = feature.GetFirstSubFeature() as IFeature;
        while (subFeature is not null)
        {
            foreach (var nested in EnumerateFeatureBranch(subFeature, seen))
                yield return nested;
            subFeature = subFeature.GetNextSubFeature() as IFeature;
        }
    }

    private static IEnumerable<FeatureTreeObservation> EnumerateFeatureTreeObservationBranch(
        IFeature feature,
        string? parentFeatureName,
        int treeDepth,
        string treePath,
        HashSet<IFeature> seen)
    {
        if (!seen.Add(feature))
            yield break;

        var featureName = feature.Name;
        yield return new FeatureTreeObservation(
            feature_name: featureName,
            feature_type: feature.GetTypeName2(),
            parent_feature_name: parentFeatureName,
            tree_depth: treeDepth,
            is_top_level: treeDepth == 0,
            tree_path: treePath);

        var subFeature = feature.GetFirstSubFeature() as IFeature;
        var childIndex = 0;
        while (subFeature is not null)
        {
            foreach (var nested in EnumerateFeatureTreeObservationBranch(
                         subFeature,
                         parentFeatureName: featureName,
                         treeDepth: treeDepth + 1,
                         treePath: $"{treePath}.{childIndex}",
                         seen))
            {
                yield return nested;
            }

            subFeature = subFeature.GetNextSubFeature() as IFeature;
            childIndex++;
        }
    }

    private static IFeature RequireExactFeature(
        IEnumerable<IFeature> features,
        string exactName,
        string expectedType,
        string featureKind)
    {
        var matches = features
            .Where(feature => string.Equals(feature.Name, exactName, StringComparison.Ordinal))
            .ToArray();

        if (matches.Length != 1)
        {
            throw new CadGroundedException(
                "feature_match_not_unique",
                $"Exact {featureKind} feature matching must be unique. " +
                $"matches={matches.Length}, feature='{exactName}'.");
        }

        var actualType = matches[0].GetTypeName2();
        if (!string.Equals(actualType, expectedType, StringComparison.Ordinal))
        {
            throw new CadGroundedException(
                "feature_type_mismatch",
                $"Feature '{exactName}' must have type '{expectedType}', actual='{actualType}'.");
        }

        return matches[0];
    }

    private DirectConnectorLookup ReadDirectConnectorLookup(string exactName)
    {
        try
        {
            // The direct named-feature getter is assembly-specific; retain the
            // typed, read-only interop path rather than using late binding.
            var assembly = RequireAssembly();
            var feature = assembly.FeatureByName(exactName) as IFeature;
            if (feature is null)
            {
                return new DirectConnectorLookup(
                    requested_name: exactName,
                    found: false,
                    feature_name: null,
                    feature_type: null,
                    lookup_error: null);
            }

            return new DirectConnectorLookup(
                requested_name: exactName,
                found: true,
                feature_name: feature.Name,
                feature_type: feature.GetTypeName2(),
                lookup_error: null);
        }
        catch (Exception ex)
        {
            return new DirectConnectorLookup(
                requested_name: exactName,
                found: false,
                feature_name: null,
                feature_type: null,
                lookup_error: $"{ex.GetType().Name}: {ex.Message}");
        }
    }

    private static ConnectorDiagnostic ClassifyConnectorDiagnostic(
        DirectConnectorLookup directLookup,
        IEnumerable<FeatureTreeObservation> traversalMatches,
        string? traversalError)
    {
        var matches = traversalMatches.ToArray();
        var expectedTraversalMatches = matches
            .Where(row => string.Equals(
                row.feature_type,
                "MagneticConnectRef",
                StringComparison.Ordinal))
            .ToArray();
        var directLookupState = DetermineDirectLookupState(directLookup);
        var classification =
            !string.IsNullOrWhiteSpace(directLookup.lookup_error)
                ? "DIRECT_LOOKUP_ERROR"
                : !string.IsNullOrWhiteSpace(traversalError)
                    ? "TRAVERSAL_ERROR"
                    : directLookupState == "FOUND_EXPECTED_TYPE" && matches.Length == 0
                        ? "DIRECT_LOOKUP_TRAVERSAL_PATH_DEFECT"
                        : directLookupState == "NOT_FOUND" && matches.Length == 0
                            ? "LIVE_STATE_SOURCE_CONFLICT"
                            : directLookupState == "FOUND_NAME_MISMATCH"
                                ? "DIRECT_LOOKUP_NAME_MISMATCH"
                                : directLookupState == "FOUND_TYPE_MISMATCH"
                                    ? "DIRECT_LOOKUP_TYPE_MISMATCH"
                                    : matches.Length > 1
                                        ? "TRAVERSAL_MATCH_NOT_UNIQUE"
                                        : expectedTraversalMatches.Length != 1
                                            ? "TRAVERSAL_TYPE_MISMATCH"
                                            : directLookupState == "NOT_FOUND"
                                                ? "DIRECT_LOOKUP_PATH_DEFECT"
                                                : "CONSISTENT";

        return new ConnectorDiagnostic(
            requested_name: directLookup.requested_name,
            direct_lookup_state: directLookupState,
            traversal_match_count: matches.Length,
            traversal_expected_type_match_count: expectedTraversalMatches.Length,
            classification: classification);
    }

    private static string DetermineDirectLookupState(DirectConnectorLookup directLookup)
    {
        if (!string.IsNullOrWhiteSpace(directLookup.lookup_error))
            return "LOOKUP_ERROR";
        if (!directLookup.found)
            return "NOT_FOUND";
        if (!string.Equals(
                directLookup.feature_name,
                directLookup.requested_name,
                StringComparison.Ordinal))
        {
            return "FOUND_NAME_MISMATCH";
        }
        if (!string.Equals(
                directLookup.feature_type,
                "MagneticConnectRef",
                StringComparison.Ordinal))
        {
            return "FOUND_TYPE_MISMATCH";
        }
        return "FOUND_EXPECTED_TYPE";
    }

    private static string DetermineConnectorDiagnosticState(
        IEnumerable<ConnectorDiagnostic> connectorDiagnostics,
        string? traversalError)
    {
        if (!string.IsNullOrWhiteSpace(traversalError))
            return "TRAVERSAL_ERROR";

        var classifications = connectorDiagnostics
            .Select(row => row.classification)
            .ToArray();
        if (classifications.All(value => value == "CONSISTENT"))
            return "DIRECT_AND_TRAVERSAL_CONSISTENT";
        if (classifications.Any(value => value == "DIRECT_LOOKUP_TRAVERSAL_PATH_DEFECT"))
            return "DIRECT_LOOKUP_TRAVERSAL_PATH_DEFECT";
        if (classifications.All(value => value == "LIVE_STATE_SOURCE_CONFLICT"))
            return "LIVE_STATE_SOURCE_CONFLICT";
        return "CONNECTOR_OBSERVATION_CONFLICT";
    }

    private static object ReadCoordinateSystemFeature(IFeature feature)
    {
        double[] transform16;
        try
        {
            var definition = feature.GetDefinition();
            if (definition is not ICoordinateSystemFeatureData coordinateSystemData)
            {
                throw new CadGroundedException(
                    "coordinate_system_definition_unavailable",
                    $"Coordinate system feature '{feature.Name}' does not expose " +
                    "ICoordinateSystemFeatureData through IFeature.GetDefinition().");
            }

            // CoordSys transforms are obtained from the feature definition, not
            // the generic specific-feature accessor. This remains an exact,
            // getter-only interop chain with no broad automation fallback.
            var mathTransform = coordinateSystemData.Transform;
            if (mathTransform is null)
            {
                throw new CadGroundedException(
                    "coordinate_system_transform_unavailable",
                    $"Coordinate system feature '{feature.Name}' returned no Transform from " +
                    "ICoordinateSystemFeatureData.");
            }

            object rawArrayData = mathTransform.ArrayData;
            transform16 = ToDoubleArray(rawArrayData) ?? Array.Empty<double>();
        }
        catch (CadGroundedException)
        {
            throw;
        }
        catch (Exception ex)
        {
            throw new CadGroundedException(
                "coordinate_system_transform_unavailable",
                $"Could not read IMathTransform.ArrayData for coordinate system '{feature.Name}'.",
                ex);
        }

        if (transform16.Length != 16 || transform16.Any(value => !double.IsFinite(value)))
        {
            throw new CadGroundedException(
                "coordinate_system_transform_invalid",
                $"Coordinate system '{feature.Name}' must expose exactly 16 finite IMathTransform.ArrayData values.");
        }

        return new
        {
            feature_name = feature.Name,
            feature_type = feature.GetTypeName2(),
            transform16 = transform16,
            origin_mm = new[]
            {
                transform16[9] * 1000.0,
                transform16[10] * 1000.0,
                transform16[11] * 1000.0
            },
            transform_source =
                "IFeature.GetDefinition() -> ICoordinateSystemFeatureData -> Transform -> IMathTransform.ArrayData"
        };
    }

    public object QueryMates(string componentNameExact)
    {
        var assembly = RequireAssembly();
        var components = GetComponents(assembly, topLevelOnly: false);
        var matches = components
            .Where(c => string.Equals(c.Name2, componentNameExact, StringComparison.Ordinal))
            .ToArray();

        if (matches.Length != 1)
        {
            throw new CadGroundedException(
                "component_match_not_unique",
                $"Exact component matching must be unique. matches={matches.Length}, component='{componentNameExact}'.");
        }

        var target = matches[0];
        var rows = new List<object>();
        var traversalErrors = new List<string>();

        IFeature? feature = _doc.FirstFeature() as IFeature;
        IFeature? mateGroup = null;
        while (feature is not null)
        {
            if (string.Equals(feature.GetTypeName2(), "MateGroup", StringComparison.Ordinal))
            {
                mateGroup = feature;
                break;
            }
            feature = feature.GetNextFeature() as IFeature;
        }

        if (mateGroup is null)
        {
            return new
            {
                document = new { title = _doc.GetTitle(), path = _doc.GetPathName() },
                component = ComponentIdentity(target, target.GetSuppression2()),
                mate_count = 0,
                mates = Array.Empty<object>(),
                traversal_errors = traversalErrors.ToArray(),
                api = "IFeature MateGroup traversal -> IFeature.GetSpecificFeature2 -> IMate2",
                model_mutation = false,
                write_authority = "NONE",
                evidence = "verified_from_solidworks_api"
            };
        }

        var mateFeature = mateGroup.GetFirstSubFeature() as IFeature;
        while (mateFeature is not null)
        {
            try
            {
                var specific = mateFeature.GetSpecificFeature2();
                if (specific is IMate2 mate)
                {
                    var entityCount = mate.GetMateEntityCount();
                    var entities = new List<object>();
                    var involvesTarget = false;

                    for (var i = 0; i < entityCount; i++)
                    {
                        IMateEntity2? entity = null;
                        var fieldErrors = new List<string>();
                        try
                        {
                            entity = mate.MateEntity(i) as IMateEntity2;
                        }
                        catch (Exception ex)
                        {
                            fieldErrors.Add("MateEntity: " + ex.Message);
                        }

                        string? referenceName = null;
                        string? referencePath = null;
                        int? referenceType = null;
                        double[]? entityParams = null;

                        if (entity is not null)
                        {
                            try
                            {
                                var referenceComponent = entity.ReferenceComponent as IComponent2;
                                referenceName = referenceComponent?.Name2;
                                referencePath = referenceComponent?.GetPathName();
                                if (string.Equals(referenceName, componentNameExact, StringComparison.Ordinal))
                                    involvesTarget = true;
                            }
                            catch (Exception ex)
                            {
                                fieldErrors.Add("ReferenceComponent: " + ex.Message);
                            }

                            try { referenceType = entity.ReferenceType2; }
                            catch (Exception ex) { fieldErrors.Add("ReferenceType2: " + ex.Message); }

                            try { entityParams = ToDoubleArray(entity.EntityParams); }
                            catch (Exception ex) { fieldErrors.Add("EntityParams: " + ex.Message); }
                        }

                        entities.Add(new
                        {
                            index = i,
                            reference_component_name2 = referenceName,
                            reference_component_path = referencePath,
                            reference_type = referenceType,
                            entity_params = entityParams,
                            field_errors = fieldErrors.ToArray()
                        });
                    }

                    if (involvesTarget)
                    {
                        var mateType = SafeInt(() => mate.Type);
                        var alignment = SafeInt(() => mate.Alignment);
                        var minimumVariation = SafeDouble(() => mate.MinimumVariation);
                        var maximumVariation = SafeDouble(() => mate.MaximumVariation);

                        rows.Add(new
                        {
                            feature_name = mateFeature.Name,
                            feature_type = mateFeature.GetTypeName2(),
                            suppressed = SafeFeatureSuppressed(mateFeature),
                            mate_type = mateType,
                            mate_type_name = mateType.HasValue ? MateTypeName(mateType.Value) : null,
                            alignment = alignment,
                            alignment_name = alignment.HasValue ? MateAlignmentName(alignment.Value) : null,
                            mate_entity_count = entityCount,
                            entities = entities.ToArray(),
                            minimum_variation = minimumVariation,
                            maximum_variation = maximumVariation
                        });
                    }
                }
            }
            catch (Exception ex)
            {
                traversalErrors.Add($"{mateFeature.Name}: {ex.Message}");
            }

            mateFeature = mateFeature.GetNextSubFeature() as IFeature;
        }

        return new
        {
            document = new { title = _doc.GetTitle(), path = _doc.GetPathName() },
            component = ComponentIdentity(target, target.GetSuppression2()),
            mate_count = rows.Count,
            mates = rows.ToArray(),
            traversal_errors = traversalErrors.ToArray(),
            interpretation_note = "Mate definitions constrain geometry but do not by themselves prove spring stiffness, preload, force, or operating sequence.",
            api = "IFeature MateGroup traversal -> IFeature.GetSpecificFeature2 -> IMate2 / IMateEntity2",
            model_mutation = false,
            write_authority = "NONE",
            evidence = "verified_from_solidworks_api"
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

        const double contactToleranceM = 0.000001;
        const double volumeToleranceM3 = 0.000000000001;

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

    public object ClassifyContactPairAtTransform(
        string documentTitleExact,
        string documentPathExact,
        string activeConfigurationExact,
        string aExact,
        string bExact,
        CandidateTransform? aCandidate,
        CandidateTransform? bCandidate)
    {
        RequireExactActiveDocument(
            documentTitleExact,
            documentPathExact,
            activeConfigurationExact);

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
        {
            throw new CadGroundedException(
                "same_component",
                "Hypothetical contact classification requires two different components.");
        }

        var aState = a.GetSuppression2();
        var bState = b.GetSuppression2();
        if (!IsResolvedComponentState(aState) || !IsResolvedComponentState(bState))
        {
            throw new CadGroundedException(
                "component_not_resolved",
                $"Hypothetical contact classification requires resolved components. " +
                $"a_state={aState}, b_state={bState}.");
        }

        var (aCurrentTransform, aCurrentArray) = RequireComponentTransform(a, "A");
        var (bCurrentTransform, bCurrentArray) = RequireComponentTransform(b, "B");

        var aEvaluationTransform = aCandidate is null
            ? aCurrentTransform
            : CreateCandidateTransform(aCandidate, "a_candidate_transform");
        var bEvaluationTransform = bCandidate is null
            ? bCurrentTransform
            : CreateCandidateTransform(bCandidate, "b_candidate_transform");

        var aEvaluationArray = aCandidate is null
            ? aCurrentArray
            : RequireMathTransformArray(aEvaluationTransform, "a_candidate_transform");
        var bEvaluationArray = bCandidate is null
            ? bCurrentArray
            : RequireMathTransformArray(bEvaluationTransform, "b_candidate_transform");

        var aBodies = GetSolidBodies(a);
        var bBodies = GetSolidBodies(b);

        const double contactToleranceM = 0.000001;
        const double volumeToleranceM3 = 0.000000000001;
        const int maxBodyPairs = 1024;
        const long maxFacePairs = 250000;

        if (aBodies.Length == 0 || bBodies.Length == 0)
        {
            RequireExactActiveDocument(
                documentTitleExact,
                documentPathExact,
                activeConfigurationExact);

            return new
            {
                document = CurrentDocumentIdentity(),
                precondition = new
                {
                    document_title_exact = documentTitleExact,
                    document_path_exact = documentPathExact,
                    active_configuration_exact = activeConfigurationExact,
                    matched = true
                },
                component_a = ComponentIdentity(a, aState),
                component_b = ComponentIdentity(b, bState),
                current_transform_a = TransformSnapshot(aCurrentArray),
                current_transform_b = TransformSnapshot(bCurrentArray),
                evaluated_transform_a = TransformSnapshot(aEvaluationArray),
                evaluated_transform_b = TransformSnapshot(bEvaluationArray),
                evaluated_transform_source_a = aCandidate is null ? "current_component_transform" : "candidate_absolute_assembly_transform",
                evaluated_transform_source_b = bCandidate is null ? "current_component_transform" : "candidate_absolute_assembly_transform",
                minimum_distance_m = (double?)null,
                minimum_distance_mm = (double?)null,
                closest_point_a_m = (double[]?)null,
                closest_point_b_m = (double[]?)null,
                closest_point_a_mm = (double[]?)null,
                closest_point_b_mm = (double[]?)null,
                classification = "indeterminate_non_solid_geometry",
                contact_tolerance_mm = contactToleranceM * 1000.0,
                volume_tolerance_mm3 = volumeToleranceM3 * 1e9,
                solid_body_count_a = aBodies.Length,
                solid_body_count_b = bBodies.Length,
                body_pair_count = 0,
                face_pair_count = 0L,
                face_distance_failure_count = 0,
                intersection_body_count = 0,
                intersection_volume_mm3 = (double?)null,
                boolean_error_codes = Array.Empty<int>(),
                api_body_source = "IComponent2.GetBodies3(swSolidBody)",
                api_body_copy_transform = "IBody2.Copy + IBody2.ApplyTransform on temporary copies only",
                api_distance = "not_executed_non_solid_geometry",
                api_intersection = "not_executed_non_solid_geometry",
                interpretation_note = "Candidate transforms are absolute assembly-space transforms. No Component2.Transform2 setter, selection, rebuild, save, mate, suppression, or assembly mutation is used.",
                model_mutation = false,
                write_authority = "NONE",
                evidence = "verified_from_solidworks_api"
            };
        }

        var bodyPairCountLong = (long)aBodies.Length * bBodies.Length;
        if (bodyPairCountLong > maxBodyPairs)
        {
            throw new CadGroundedException(
                "hypothetical_body_pair_limit_exceeded",
                $"Hypothetical fit check requires {bodyPairCountLong} solid-body pairs; " +
                $"limit={maxBodyPairs}.");
        }

        var booleanErrorCodes = new List<int>();
        var intersectionBodyCount = 0;
        var intersectionVolumeM3 = 0.0;

        foreach (var aBody in aBodies)
        {
            foreach (var bBody in bBodies)
            {
                var aCopy = CopyAndTransformBody(
                    aBody,
                    aEvaluationTransform,
                    "A");
                var bCopy = CopyAndTransformBody(
                    bBody,
                    bEvaluationTransform,
                    "B");

                int errorCode;
                object raw;
                try
                {
                    raw = aCopy.Operations2(
                        (int)SwConst.swBodyOperationType_e.SWBODYINTERSECT,
                        bCopy,
                        out errorCode);
                }
                catch (COMException ex)
                {
                    throw new CadGroundedException(
                        "body_intersection_com_fault",
                        $"Body2.Operations2(SWBODYINTERSECT) failed for hypothetical pair " +
                        $"'{a.Name2}' and '{b.Name2}'.",
                        ex);
                }

                booleanErrorCodes.Add(errorCode);
                if (raw is not Array resultBodies)
                    continue;

                foreach (var rawBody in resultBodies)
                {
                    if (rawBody is not IBody2 resultBody)
                        continue;

                    var mass = ToDoubleArray(resultBody.GetMassProperties(1.0));
                    if (mass is null || mass.Length <= 3)
                        continue;

                    var volume = mass[3];
                    if (volume > volumeToleranceM3)
                    {
                        intersectionBodyCount++;
                        intersectionVolumeM3 += volume;
                    }
                }
            }
        }

        var distinctErrors = booleanErrorCodes
            .Distinct()
            .OrderBy(v => v)
            .ToArray();
        var hasBooleanError = distinctErrors.Any(v => v != 0);

        double? minimumDistanceM = null;
        double[]? closestPointAM = null;
        double[]? closestPointBM = null;
        long facePairCount = 0;
        var faceDistanceFailureCount = 0;
        string distanceProvenance;

        if (intersectionVolumeM3 > volumeToleranceM3 && !hasBooleanError)
        {
            // Positive exact B-rep intersection means the closed solids overlap,
            // so the minimum set distance is deterministically zero. We avoid
            // pretending IModelDoc2.ClosestDistance can measure temporary bodies;
            // SOLIDWORKS documents that temporary geometric entities are unsupported.
            minimumDistanceM = 0.0;
            distanceProvenance = "derived_zero_from_positive_brep_intersection";
        }
        else if (!hasBooleanError)
        {
            var distanceResult = MeasureTemporaryBodyDistance(
                aBodies,
                aEvaluationTransform,
                bBodies,
                bEvaluationTransform,
                maxFacePairs);

            minimumDistanceM = distanceResult.DistanceM;
            closestPointAM = distanceResult.PointAM;
            closestPointBM = distanceResult.PointBM;
            facePairCount = distanceResult.FacePairCount;
            faceDistanceFailureCount = distanceResult.FailureCount;
            distanceProvenance =
                "IEntity.GetDistance(minimum=true) over face pairs from transformed temporary body copies";
        }
        else
        {
            distanceProvenance = "not_executed_due_to_boolean_error";
        }

        string classification;
        if (hasBooleanError)
            classification = "indeterminate_boolean_error";
        else if (intersectionVolumeM3 > volumeToleranceM3)
            classification = "physical_interference";
        else if (minimumDistanceM is null)
            classification = "indeterminate_distance_unavailable";
        else if (minimumDistanceM.Value > contactToleranceM)
            classification = "clearance";
        else
            classification = "contact_or_coincidence_within_tolerance";

        // Re-read the active-document identity after the bounded operation so a
        // mid-read document/configuration switch fails closed instead of being
        // returned as if it belonged to the requested precondition.
        RequireExactActiveDocument(
            documentTitleExact,
            documentPathExact,
            activeConfigurationExact);

        return new
        {
            document = CurrentDocumentIdentity(),
            precondition = new
            {
                document_title_exact = documentTitleExact,
                document_path_exact = documentPathExact,
                active_configuration_exact = activeConfigurationExact,
                matched = true
            },
            component_a = ComponentIdentity(a, aState),
            component_b = ComponentIdentity(b, bState),
            current_transform_a = TransformSnapshot(aCurrentArray),
            current_transform_b = TransformSnapshot(bCurrentArray),
            evaluated_transform_a = TransformSnapshot(aEvaluationArray),
            evaluated_transform_b = TransformSnapshot(bEvaluationArray),
            evaluated_transform_source_a = aCandidate is null ? "current_component_transform" : "candidate_absolute_assembly_transform",
            evaluated_transform_source_b = bCandidate is null ? "current_component_transform" : "candidate_absolute_assembly_transform",
            minimum_distance_m = minimumDistanceM,
            minimum_distance_mm = minimumDistanceM * 1000.0,
            closest_point_a_m = closestPointAM,
            closest_point_b_m = closestPointBM,
            closest_point_a_mm = Scale(closestPointAM, 1000.0),
            closest_point_b_mm = Scale(closestPointBM, 1000.0),
            classification,
            contact_tolerance_mm = contactToleranceM * 1000.0,
            volume_tolerance_mm3 = volumeToleranceM3 * 1e9,
            solid_body_count_a = aBodies.Length,
            solid_body_count_b = bBodies.Length,
            body_pair_count = (int)bodyPairCountLong,
            face_pair_count = facePairCount,
            face_distance_failure_count = faceDistanceFailureCount,
            intersection_body_count = intersectionBodyCount,
            intersection_volume_mm3 = intersectionVolumeM3 * 1e9,
            boolean_error_codes = distinctErrors,
            api_body_source = "IComponent2.GetBodies3(swSolidBody)",
            api_body_copy_transform = "IBody2.Copy + IBody2.ApplyTransform on temporary copies only",
            api_distance = distanceProvenance,
            api_intersection = "IBody2.Operations2(SWBODYINTERSECT) on transformed temporary body copies",
            interpretation_note =
                "Candidate transforms are absolute assembly-space transforms using SOLIDWORKS MathTransform ArrayData ordering. " +
                "IModelDoc2.ClosestDistance is intentionally not used for the hypothetical geometry because SOLIDWORKS does not support temporary geometric entities there. " +
                "No Component2.Transform2 setter, selection, rebuild, save, mate, suppression, or assembly mutation is used.",
            model_mutation = false,
            write_authority = "NONE",
            evidence = "verified_from_solidworks_api"
        };
    }

    private void RequireExactActiveDocument(
        string titleExact,
        string pathExact,
        string configurationExact)
    {
        var actualTitle = _doc.GetTitle();
        var actualPath = _doc.GetPathName();
        var actualConfiguration = _doc.ConfigurationManager.ActiveConfiguration?.Name;

        if (!string.Equals(titleExact, actualTitle, StringComparison.Ordinal))
        {
            throw new CadGroundedException(
                "document_precondition_failed",
                $"Document title precondition failed. Expected='{titleExact}' Actual='{actualTitle}'.");
        }

        if (!string.Equals(pathExact, actualPath, StringComparison.OrdinalIgnoreCase))
        {
            throw new CadGroundedException(
                "document_precondition_failed",
                $"Document path precondition failed. Expected='{pathExact}' Actual='{actualPath}'.");
        }

        if (!string.Equals(configurationExact, actualConfiguration, StringComparison.Ordinal))
        {
            throw new CadGroundedException(
                "document_precondition_failed",
                $"Active configuration precondition failed. Expected='{configurationExact}' Actual='{actualConfiguration}'.");
        }
    }

    private object CurrentDocumentIdentity()
    {
        return new
        {
            title = _doc.GetTitle(),
            path = _doc.GetPathName(),
            active_configuration = _doc.ConfigurationManager.ActiveConfiguration?.Name
        };
    }

    private static bool IsResolvedComponentState(int state)
    {
        return state == (int)SwConst.swComponentSuppressionState_e.swComponentFullyResolved ||
               state == (int)SwConst.swComponentSuppressionState_e.swComponentResolved;
    }

    private static (MathTransform Transform, double[] Array) RequireComponentTransform(
        IComponent2 component,
        string label)
    {
        MathTransform? transform;
        try
        {
            transform = component.Transform2;
        }
        catch (COMException ex)
        {
            throw new CadGroundedException(
                "component_transform_unavailable",
                $"Could not read current Transform2 for component {label} '{component.Name2}'.",
                ex);
        }

        if (transform is null)
        {
            throw new CadGroundedException(
                "component_transform_unavailable",
                $"Current Transform2 is null for component {label} '{component.Name2}'.");
        }

        return (transform, RequireMathTransformArray(transform, $"current component {label}"));
    }

    private static double[] RequireMathTransformArray(
        MathTransform transform,
        string context)
    {
        var values = ToDoubleArray(transform.ArrayData);
        if (values is null || values.Length < 13)
        {
            throw new CadGroundedException(
                "transform_array_unavailable",
                $"{context} did not expose at least 13 MathTransform ArrayData values.");
        }

        if (values.Take(13).Any(v => !double.IsFinite(v)))
        {
            throw new CadGroundedException(
                "transform_array_invalid",
                $"{context} contains a non-finite MathTransform value.");
        }

        return values;
    }

    private MathTransform CreateCandidateTransform(
        CandidateTransform candidate,
        string context)
    {
        ValidateCandidateTransform(candidate, context);

        var transformData = new double[16];
        Array.Copy(candidate.rotation9, 0, transformData, 0, 9);
        transformData[9] = candidate.translation_mm[0] / 1000.0;
        transformData[10] = candidate.translation_mm[1] / 1000.0;
        transformData[11] = candidate.translation_mm[2] / 1000.0;
        transformData[12] = 1.0;

        var mathUtility = _app.IGetMathUtility();
        if (mathUtility is null)
        {
            throw new CadGroundedException(
                "math_utility_unavailable",
                "ISldWorks.IGetMathUtility returned null.");
        }

        var rawTransform = mathUtility.CreateTransform(transformData);
        if (rawTransform is not MathTransform transform)
        {
            throw new CadGroundedException(
                "candidate_transform_creation_failed",
                $"IMathUtility.CreateTransform returned no MathTransform for {context}.");
        }

        // CreateTransform can normalize malformed rotations. Candidate input is
        // independently validated above; verify the resulting transform still
        // represents the exact requested rigid pose within floating precision.
        var created = RequireMathTransformArray(transform, context);
        const double verificationTolerance = 1e-10;
        for (var i = 0; i < 13; i++)
        {
            if (Math.Abs(created[i] - transformData[i]) > verificationTolerance)
            {
                throw new CadGroundedException(
                    "candidate_transform_normalized",
                    $"{context} was altered by IMathUtility.CreateTransform at ArrayData[{i}]. " +
                    $"requested={transformData[i]:R}, created={created[i]:R}.");
            }
        }

        return transform;
    }

    private static void ValidateCandidateTransform(
        CandidateTransform candidate,
        string context)
    {
        if (candidate.rotation9.Length != 9)
            throw new CadGroundedException(
                "malformed_candidate_transform",
                $"{context}.rotation9 must contain exactly 9 numbers.");

        if (candidate.translation_mm.Length != 3)
            throw new CadGroundedException(
                "malformed_candidate_transform",
                $"{context}.translation_mm must contain exactly 3 numbers.");

        if (candidate.rotation9.Any(v => !double.IsFinite(v)) ||
            candidate.translation_mm.Any(v => !double.IsFinite(v)))
        {
            throw new CadGroundedException(
                "malformed_candidate_transform",
                $"{context} contains a non-finite number.");
        }

        static double Dot(double[] r, int a, int b) =>
            r[a * 3] * r[b * 3] +
            r[a * 3 + 1] * r[b * 3 + 1] +
            r[a * 3 + 2] * r[b * 3 + 2];

        const double orthonormalTolerance = 1e-6;
        for (var row = 0; row < 3; row++)
        {
            if (Math.Abs(Dot(candidate.rotation9, row, row) - 1.0) >
                orthonormalTolerance)
            {
                throw new CadGroundedException(
                    "malformed_candidate_transform",
                    $"{context}.rotation9 row {row} is not unit length within " +
                    $"tolerance={orthonormalTolerance:R}.");
            }
        }

        if (Math.Abs(Dot(candidate.rotation9, 0, 1)) > orthonormalTolerance ||
            Math.Abs(Dot(candidate.rotation9, 0, 2)) > orthonormalTolerance ||
            Math.Abs(Dot(candidate.rotation9, 1, 2)) > orthonormalTolerance)
        {
            throw new CadGroundedException(
                "malformed_candidate_transform",
                $"{context}.rotation9 rows are not mutually orthogonal within " +
                $"tolerance={orthonormalTolerance:R}.");
        }

        var r = candidate.rotation9;
        var determinant =
            r[0] * (r[4] * r[8] - r[5] * r[7]) -
            r[1] * (r[3] * r[8] - r[5] * r[6]) +
            r[2] * (r[3] * r[7] - r[4] * r[6]);

        if (Math.Abs(determinant - 1.0) > 1e-5)
        {
            throw new CadGroundedException(
                "malformed_candidate_transform",
                $"{context}.rotation9 must be a proper right-handed rotation; " +
                $"determinant={determinant:R}.");
        }
    }

    private static IBody2 CopyAndTransformBody(
        IBody2 source,
        MathTransform transform,
        string label)
    {
        var copy = source.Copy() as IBody2;
        if (copy is null)
        {
            throw new CadGroundedException(
                "temporary_body_copy_failed",
                $"IBody2.Copy did not return a temporary solid body for component {label}.");
        }

        if (!copy.ApplyTransform(transform))
        {
            throw new CadGroundedException(
                "temporary_body_transform_failed",
                $"IBody2.ApplyTransform failed for temporary component-{label} body copy.");
        }

        return copy;
    }

    private static TemporaryDistanceResult MeasureTemporaryBodyDistance(
        IBody2[] aBodies,
        MathTransform aTransform,
        IBody2[] bBodies,
        MathTransform bTransform,
        long maxFacePairs)
    {
        double? bestDistance = null;
        double[]? bestPointA = null;
        double[]? bestPointB = null;
        long facePairCount = 0;
        var failureCount = 0;

        foreach (var aBody in aBodies)
        {
            foreach (var bBody in bBodies)
            {
                var aCopy = CopyAndTransformBody(aBody, aTransform, "A");
                var bCopy = CopyAndTransformBody(bBody, bTransform, "B");
                var aFaces = GetBodyEntities(aCopy);
                var bFaces = GetBodyEntities(bCopy);

                var prospective = facePairCount + (long)aFaces.Length * bFaces.Length;
                if (prospective > maxFacePairs)
                {
                    throw new CadGroundedException(
                        "hypothetical_face_pair_limit_exceeded",
                        $"Hypothetical distance calculation would exceed face-pair limit " +
                        $"{maxFacePairs}; prospective_pairs={prospective}.");
                }

                foreach (var aFace in aFaces)
                {
                    foreach (var bFace in bFaces)
                    {
                        facePairCount++;

                        object pointA;
                        object pointB;
                        double distance;
                        int result;
                        try
                        {
                            result = aFace.GetDistance(
                                bFace,
                                true,
                                null!,
                                out pointA,
                                out pointB,
                                out distance);
                        }
                        catch (COMException)
                        {
                            failureCount++;
                            continue;
                        }

                        if (result != 0 || distance < 0.0 || !double.IsFinite(distance))
                        {
                            failureCount++;
                            continue;
                        }

                        if (bestDistance is null || distance < bestDistance.Value)
                        {
                            bestDistance = distance;
                            bestPointA = ToDoubleArray(pointA);
                            bestPointB = ToDoubleArray(pointB);
                        }
                    }
                }
            }
        }

        return new TemporaryDistanceResult(
            bestDistance,
            bestPointA,
            bestPointB,
            facePairCount,
            failureCount);
    }

    private static IEntity[] GetBodyEntities(IBody2 body)
    {
        var raw = body.GetFaces();
        if (raw is null)
            return Array.Empty<IEntity>();

        if (raw is object[] objects)
            return objects.OfType<IEntity>().ToArray();

        if (raw is Array array)
        {
            var result = new List<IEntity>();
            foreach (var item in array)
            {
                if (item is IEntity entity)
                    result.Add(entity);
            }
            return result.ToArray();
        }

        throw new CadGroundedException(
            "unexpected_face_array",
            $"IBody2.GetFaces returned unsupported type '{raw.GetType().FullName}'.");
    }

    private static object TransformSnapshot(double[] transformArray)
    {
        var rotation9 = transformArray.Take(9).ToArray();
        var translationM = new[]
        {
            transformArray[9],
            transformArray[10],
            transformArray[11]
        };

        return new
        {
            array_data = transformArray,
            rotation9,
            translation_m = translationM,
            translation_mm = Scale(translationM, 1000.0),
            scale = transformArray.Length > 12 ? transformArray[12] : (double?)null
        };
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

    private static object ComponentIdentity(IComponent2 c, int state)
    {
        // Parentage is included because a mate row without the component's
        // assembly context cannot bind a closure mechanism to a physical
        // subassembly. This is intentionally a getter-only traversal; it does
        // not select, activate, edit, rebuild, or resolve anything.
        var parentNames = new List<string>();
        var parentPaths = new List<string?>();
        var parentageErrors = new List<string>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        var current = c;

        while (true)
        {
            IComponent2? parent;
            try
            {
                parent = current.GetParent() as IComponent2;
            }
            catch (Exception ex)
            {
                parentageErrors.Add("GetParent: " + ex.Message);
                break;
            }

            if (parent is null)
                break;

            var parentName = parent.Name2;
            if (!seen.Add(parentName))
            {
                parentageErrors.Add($"GetParent cycle detected at '{parentName}'.");
                break;
            }

            parentNames.Add(parentName);
            try
            {
                parentPaths.Add(parent.GetPathName());
            }
            catch (Exception ex)
            {
                parentPaths.Add(null);
                parentageErrors.Add("GetParent.GetPathName: " + ex.Message);
            }

            current = parent;
        }

        return new
        {
            name2 = c.Name2,
            path = c.GetPathName(),
            suppression_state = state,
            referenced_configuration = Safe(() => c.ReferencedConfiguration),
            fixed_component = SafeBool(() => c.IsFixed()),
            parent_chain = parentNames.ToArray(),
            parent_chain_paths = parentPaths.ToArray(),
            parentage_errors = parentageErrors.ToArray(),
            is_top_level = parentNames.Count == 0
        };
    }

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

    private static int? SafeInt(Func<int> getter)
    {
        try { return getter(); }
        catch { return null; }
    }

    private static double? SafeDouble(Func<double> getter)
    {
        try { return getter(); }
        catch { return null; }
    }

    private static bool? SafeFeatureSuppressed(IFeature feature)
    {
        try
        {
            var raw = feature.IsSuppressed2(
                (int)SwConst.swInConfigurationOpts_e.swThisConfiguration,
                null);

            if (raw is bool single)
                return single;
            if (raw is bool[] values && values.Length > 0)
                return values[0];
            if (raw is Array array && array.Length > 0)
                return Convert.ToBoolean(array.GetValue(0), CultureInfo.InvariantCulture);
            return null;
        }
        catch
        {
            return null;
        }
    }

    private static string MateTypeName(int value)
    {
        return Enum.IsDefined(typeof(SwConst.swMateType_e), value)
            ? ((SwConst.swMateType_e)value).ToString()
            : $"unknown:{value}";
    }

    private static string MateAlignmentName(int value)
    {
        return Enum.IsDefined(typeof(SwConst.swMateAlign_e), value)
            ? ((SwConst.swMateAlign_e)value).ToString()
            : $"unknown:{value}";
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
    }

    private sealed record DirectConnectorLookup(
        string requested_name,
        bool found,
        string? feature_name,
        string? feature_type,
        string? lookup_error);

    private sealed record FeatureTreeObservation(
        string feature_name,
        string feature_type,
        string? parent_feature_name,
        int tree_depth,
        bool is_top_level,
        string tree_path);

    private sealed record ConnectorDiagnostic(
        string requested_name,
        string direct_lookup_state,
        int traversal_match_count,
        int traversal_expected_type_match_count,
        string classification);

    private sealed record FeatureManagerTreeObservation(
        string displayed_tree_text,
        int tree_depth,
        string tree_path,
        int object_type,
        bool object_is_null,
        string? object_runtime_dotnet_type,
        bool? object_is_com_object,
        string? feature_name,
        string? feature_type);

    private sealed record FeatureManagerTreeTextDiagnostic(
        string requested_displayed_tree_text,
        int exact_match_count,
        string classification);

    private sealed record FeatureManagerTreeNode(
        ITreeControlItem item,
        string displayed_tree_text,
        int tree_depth,
        string tree_path,
        string? parent_displayed_tree_text,
        string? parent_tree_path);

    private sealed record PublishedReferenceManagerObservation(
        string displayed_tree_text,
        string feature_name,
        string feature_type,
        string tree_path);

    private sealed record PublishedReferenceFeatureObservation(
        string connector_name,
        string feature_type,
        string tree_path,
        string parent_tree_text,
        string parent_feature_name,
        string parent_feature_type);

    private sealed record FeatureManagerPublishedReferenceBinding(
        PublishedReferenceManagerObservation published_reference_manager,
        PublishedReferenceFeatureObservation[] published_reference_features);
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
    public static void RequireOnlyProperties(JsonElement payload, params string[] allowedNames)
    {
        if (payload.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("payload must be a JSON object.");

        var allowed = new HashSet<string>(allowedNames, StringComparer.Ordinal);
        foreach (var property in payload.EnumerateObject())
        {
            if (!allowed.Contains(property.Name))
            {
                throw new ArgumentException(
                    $"payload contains unsupported property '{property.Name}'.");
            }
        }
    }

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

    public static CandidateTransform? GetOptionalCandidateTransform(
        JsonElement payload,
        string name)
    {
        if (payload.ValueKind != JsonValueKind.Object ||
            !payload.TryGetProperty(name, out var value))
            return null;

        if (value.ValueKind != JsonValueKind.Object)
            throw new ArgumentException($"payload.{name} must be an object.");

        RequireOnlyProperties(value, "rotation9", "translation_mm");

        return new CandidateTransform(
            GetRequiredFiniteDoubleArray(value, "rotation9", 9, $"payload.{name}"),
            GetRequiredFiniteDoubleArray(value, "translation_mm", 3, $"payload.{name}"));
    }

    private static double[] GetRequiredFiniteDoubleArray(
        JsonElement parent,
        string name,
        int expectedLength,
        string context)
    {
        if (!parent.TryGetProperty(name, out var value) ||
            value.ValueKind != JsonValueKind.Array ||
            value.GetArrayLength() != expectedLength)
        {
            throw new ArgumentException(
                $"{context}.{name} is required and must contain exactly {expectedLength} numbers.");
        }

        var result = new double[expectedLength];
        var index = 0;
        foreach (var item in value.EnumerateArray())
        {
            if (item.ValueKind != JsonValueKind.Number ||
                !item.TryGetDouble(out var number) ||
                !double.IsFinite(number))
            {
                throw new ArgumentException(
                    $"{context}.{name}[{index}] must be a finite JSON number.");
            }

            result[index++] = number;
        }

        return result;
    }

    public static string[] GetRequiredUniqueStringArray(JsonElement payload, string name)
    {
        if (payload.ValueKind != JsonValueKind.Object ||
            !payload.TryGetProperty(name, out var value) ||
            value.ValueKind != JsonValueKind.Array ||
            value.GetArrayLength() == 0)
        {
            throw new ArgumentException(
                $"payload.{name} is required and must be a non-empty array of unique non-empty strings.");
        }

        var result = new List<string>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var item in value.EnumerateArray())
        {
            if (item.ValueKind != JsonValueKind.String ||
                string.IsNullOrWhiteSpace(item.GetString()))
            {
                throw new ArgumentException(
                    $"payload.{name} must contain only non-empty strings.");
            }

            var text = item.GetString()!;
            if (!seen.Add(text))
            {
                throw new ArgumentException(
                    $"payload.{name} must not contain duplicate exact names. Duplicate='{text}'.");
            }
            result.Add(text);
        }

        return result.ToArray();
    }
}

internal sealed record CandidateTransform(
    double[] rotation9,
    double[] translation_mm);

internal sealed record TemporaryDistanceResult(
    double? DistanceM,
    double[]? PointAM,
    double[]? PointBM,
    long FacePairCount,
    int FailureCount);

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
