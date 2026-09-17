using System.Drawing;
using System.Drawing.Imaging;
using System.Net.Http.Json;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text.Json.Nodes;
using SolidWorks.Interop.sldworks;

namespace CadGrounded.VisualSweepWorker;

internal static class Program
{
    private const string Version = "0.1.0";
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true,
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower
    };

    [STAThread]
    private static async Task<int> Main(string[] args)
    {
        try
        {
            var options = Options.Parse(args);
            if (options.ShowHelp)
            {
                PrintUsage();
                return 0;
            }

            if (options.ShowVersion)
            {
                Console.WriteLine($"CadGrounded.VisualSweepWorker {Version}");
                return 0;
            }

            return options.Command switch
            {
                "capture" => RunCapture(options),
                "analyze" => await RunAnalyzeAsync(options),
                "run" => await RunFullAsync(options),
                "models" => await RunModelsAsync(options),
                _ => throw new ArgumentException($"Unknown command '{options.Command}'.")
            };
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(JsonSerializer.Serialize(new
            {
                ok = false,
                error = ex.GetType().Name,
                message = ex.Message,
                stack = ex.StackTrace
            }, JsonOptions));
            return 1;
        }
    }

    private static int RunCapture(Options options)
    {
        var result = VisualSweep.Capture(options);
        Console.WriteLine(JsonSerializer.Serialize(new { ok = true, result }, JsonOptions));
        return 0;
    }

    private static async Task<int> RunAnalyzeAsync(Options options)
    {
        var runDirectory = options.RunDirectory ??
            throw new ArgumentException("analyze requires --run <inspection-run-directory>.");

        var result = await OllamaAnalyzer.AnalyzeRunAsync(runDirectory, options);
        Console.WriteLine(JsonSerializer.Serialize(new { ok = true, result }, JsonOptions));
        return 0;
    }

    private static async Task<int> RunFullAsync(Options options)
    {
        var capture = VisualSweep.Capture(options);
        try
        {
            var analysis = await OllamaAnalyzer.AnalyzeRunAsync(capture.RunDirectory, options);
            Console.WriteLine(JsonSerializer.Serialize(new { ok = true, capture, analysis }, JsonOptions));
            return 0;
        }
        catch (NoVisionModelException ex)
        {
            ManifestStore.MarkAnalysisBlocked(capture.RunDirectory, ex.Message);
            Console.WriteLine(JsonSerializer.Serialize(new
            {
                ok = true,
                capture,
                analysis = new
                {
                    state = "BLOCKED_NO_VISION_MODEL",
                    reason = ex.Message,
                    captures_preserved = true
                }
            }, JsonOptions));
            return 0;
        }
    }

    private static async Task<int> RunModelsAsync(Options options)
    {
        using var client = new OllamaClient(options.OllamaUrl);
        var models = await client.GetModelsWithCapabilitiesAsync();
        Console.WriteLine(JsonSerializer.Serialize(new { ok = true, models }, JsonOptions));
        return 0;
    }

    private static void PrintUsage()
    {
        Console.WriteLine("""
CadGrounded.VisualSweepWorker v0.1.0

Commands:
  capture [--views 8] [--width 1600] [--height 900] [--output <directory>]
  analyze --run <directory> [--model <ollama-model>] [--ollama <url>]
  run [capture options] [--model <ollama-model>] [--ollama <url>]
  models [--ollama <url>]

Environment:
  CADGROUNDED_OLLAMA_URL           default http://127.0.0.1:11434
  CADGROUNDED_OLLAMA_VISION_MODEL optional explicit vision model

Authority boundary:
  - Model/component geometry is never modified.
  - Only the transient SOLIDWORKS model view is rotated.
  - The original view orientation, translation, and scale are restored in finally.
  - The SOLIDWORKS document is never saved by this worker.
  - VLM observations remain OBSERVED/INFERRED until deterministic CAD verification upgrades them.
""");
    }
}

internal sealed class Options
{
    public string Command { get; private set; } = "run";
    public int Views { get; private set; } = 8;
    public int Width { get; private set; } = 1600;
    public int Height { get; private set; } = 900;
    public string? OutputDirectory { get; private set; }
    public string? RunDirectory { get; private set; }
    public string? Model { get; private set; }
    public string OllamaUrl { get; private set; } =
        Environment.GetEnvironmentVariable("CADGROUNDED_OLLAMA_URL") ?? "http://127.0.0.1:11434";
    public bool ShowHelp { get; private set; }
    public bool ShowVersion { get; private set; }

    public static Options Parse(string[] args)
    {
        var o = new Options();
        if (args.Length == 0)
            return o;

        if (args[0] is "-h" or "--help")
        {
            o.ShowHelp = true;
            return o;
        }

        if (args[0] is "-v" or "--version" or "version")
        {
            o.ShowVersion = true;
            return o;
        }

        o.Command = args[0].ToLowerInvariant();
        for (var i = 1; i < args.Length; i++)
        {
            string Next(string name)
            {
                if (++i >= args.Length)
                    throw new ArgumentException($"{name} requires a value.");
                return args[i];
            }

            switch (args[i])
            {
                case "--views":
                    o.Views = int.Parse(Next("--views"));
                    break;
                case "--width":
                    o.Width = int.Parse(Next("--width"));
                    break;
                case "--height":
                    o.Height = int.Parse(Next("--height"));
                    break;
                case "--output":
                    o.OutputDirectory = Next("--output");
                    break;
                case "--run":
                    o.RunDirectory = Next("--run");
                    break;
                case "--model":
                    o.Model = Next("--model");
                    break;
                case "--ollama":
                    o.OllamaUrl = Next("--ollama").TrimEnd('/');
                    break;
                default:
                    throw new ArgumentException($"Unknown option '{args[i]}'.");
            }
        }

        if (o.Views < 2 || o.Views > 72)
            throw new ArgumentOutOfRangeException(nameof(o.Views), "--views must be between 2 and 72.");
        if (o.Width < 320 || o.Height < 240)
            throw new ArgumentOutOfRangeException("Capture resolution is too small.");

        o.Model ??= Environment.GetEnvironmentVariable("CADGROUNDED_OLLAMA_VISION_MODEL");
        return o;
    }
}

internal static class VisualSweep
{
    public static CaptureResult Capture(Options options)
    {
        var raw = ComRot.GetActiveObject("SldWorks.Application");
        if (raw is not SldWorks app)
            throw new InvalidOperationException("Running SOLIDWORKS object could not be cast to SldWorks.");
        if (app.ActiveDoc is not IModelDoc2 doc)
            throw new InvalidOperationException("SOLIDWORKS has no active document.");
        if (doc.ActiveView is not IModelView view)
            throw new InvalidOperationException("SOLIDWORKS active document has no model view.");

        var docPath = doc.GetPathName();
        var baseDir = options.OutputDirectory;
        if (string.IsNullOrWhiteSpace(baseDir))
        {
            var parent = Path.GetDirectoryName(docPath);
            baseDir = string.IsNullOrWhiteSpace(parent)
                ? Path.Combine(Environment.CurrentDirectory, "inspection_runs")
                : Path.Combine(parent, "inspection_runs");
        }

        var runId = DateTimeOffset.Now.ToString("yyyy-MM-dd_HH-mm-ss");
        var runDir = Path.Combine(baseDir, runId);
        var imagesDir = Path.Combine(runDir, "images");
        var analysisDir = Path.Combine(runDir, "analysis");
        var bucketsDir = Path.Combine(runDir, "buckets");
        Directory.CreateDirectory(imagesDir);
        Directory.CreateDirectory(analysisDir);
        Directory.CreateDirectory(bucketsDir);

        foreach (var bucket in ProgramBuckets.All)
            File.WriteAllText(
                Path.Combine(bucketsDir, bucket + ".json"),
                JsonSerializer.Serialize(new BucketFile(bucket, []), ProgramBuckets.JsonOptions));

        var originalOrientation = ToDoubleArray(((IMathTransform)view.Orientation3).ArrayData);
        var originalTranslation = ToDoubleArray(((IMathVector)view.Translation3).ArrayData);
        var originalScale = view.Scale2;
        var captures = new List<CaptureRecord>();
        var captureErrors = new List<string>();
        var restored = false;

        try
        {
            WriteGeometrySnapshot(doc, runDir);
            doc.ViewZoomtofit2();
            doc.GraphicsRedraw2();
            Thread.Sleep(150);

            var stepRadians = 2.0 * Math.PI / options.Views;
            for (var i = 0; i < options.Views; i++)
            {
                var azimuth = 360.0 * i / options.Views;
                var stem = $"az{azimuth:000}_el000";
                var bmpPath = Path.Combine(imagesDir, stem + ".bmp");
                var pngPath = Path.Combine(imagesDir, stem + ".png");

                doc.GraphicsRedraw2();
                Thread.Sleep(100);

                if (!doc.SaveBMP(bmpPath, options.Width, options.Height))
                {
                    captureErrors.Add(stem + ": SaveBMP returned false");
                }
                else
                {
                    ConvertBmpToPng(bmpPath, pngPath);
                    var orientation = ToDoubleArray(((IMathTransform)view.Orientation3).ArrayData);
                    captures.Add(new CaptureRecord(
                        Path.GetRelativePath(runDir, pngPath).Replace('\\', '/'),
                        azimuth,
                        0,
                        orientation));
                }

                if (i < options.Views - 1)
                    view.RotateAboutCenter(0.0, stepRadians);
            }
        }
        finally
        {
            try
            {
                var math = (IMathUtility)app.GetMathUtility();
                view.Orientation3 = (MathTransform)math.CreateTransform(originalOrientation);
                view.Translation3 = (MathVector)math.CreateVector(originalTranslation);
                view.Scale2 = originalScale;
                doc.GraphicsRedraw2();
                restored = true;
            }
            catch
            {
                restored = false;
                throw;
            }
            finally
            {
                var manifest = new SweepManifest(
                    "cadgrounded.visual_sweep.v0.1",
                    runId,
                    doc.GetTitle(),
                    docPath,
                    "camera_only_read_only_geometry",
                    new SweepSettings(options.Views, options.Width, options.Height),
                    captures,
                    captureErrors,
                    restored,
                    new AnalysisState("PENDING", options.OllamaUrl, null, null));
                ManifestStore.Write(runDir, manifest);
            }
        }

        return new CaptureResult(runDir, captures.Count, captureErrors, restored);
    }

    private static void ConvertBmpToPng(string bmpPath, string pngPath)
    {
        using (var image = Image.FromFile(bmpPath))
            image.Save(pngPath, ImageFormat.Png);
        File.Delete(bmpPath);
    }

    private static void WriteGeometrySnapshot(IModelDoc2 doc, string runDir)
    {
        var rows = new List<object>();
        if (doc is IAssemblyDoc assembly)
        {
            var raw = assembly.GetComponents(true) as object[] ?? [];
            foreach (var item in raw)
            {
                if (item is not IComponent2 c)
                    continue;

                double[]? transform = null;
                try
                {
                    if (c.Transform2 is IMathTransform t)
                        transform = ToDoubleArray(t.ArrayData);
                }
                catch { }

                double[]? box = null;
                try { box = ToDoubleArray(c.GetBox()); } catch { }

                rows.Add(new
                {
                    name2 = c.Name2,
                    path = c.GetPathName(),
                    suppressed = c.IsSuppressed(),
                    fixed_component = SafeBool(c.IsFixed),
                    transform16 = transform,
                    approximate_box_m = box
                });
            }
        }

        File.WriteAllText(
            Path.Combine(runDir, "geometry_snapshot.json"),
            JsonSerializer.Serialize(new
            {
                source_classification = "verified_from_solidworks_api",
                scope = "top_level_components",
                document_title = doc.GetTitle(),
                components = rows
            }, ProgramBuckets.JsonOptions));
    }

    private static double[] ToDoubleArray(object? raw)
    {
        if (raw is null)
            return [];
        if (raw is double[] doubles)
            return doubles.ToArray();
        if (raw is Array array)
        {
            var result = new double[array.Length];
            for (var i = 0; i < array.Length; i++)
                result[i] = Convert.ToDouble(array.GetValue(i), System.Globalization.CultureInfo.InvariantCulture);
            return result;
        }
        throw new InvalidCastException($"Expected COM array, got {raw.GetType().FullName}.");
    }

    private static bool? SafeBool(Func<bool> action)
    {
        try { return action(); }
        catch { return null; }
    }
}

internal static class OllamaAnalyzer
{
    private const string Prompt = """
You are the visual observation layer of CADGrounded. Analyze this SOLIDWORKS viewport image of industrial equipment.

Authority rules:
- The image is evidence, not engineering truth.
- Do not claim dimensions, contact, force, torque, friction, collision, clearance, or kinematic feasibility as verified from pixels.
- Use OBSERVED only for directly visible facts.
- Use INFERRED only for plausible mechanism interpretation.
- Never emit CAD_VERIFIED or PHYSICS_VERIFIED; those states belong to deterministic downstream verifiers.
- If uncertain or occluded, say so and use UNKNOWN_NEEDS_REVIEW when appropriate.

Allowed buckets:
PRODUCT_FLOW, PRODUCT_RESTRAINT, LABEL_PATH, PEEL_EDGE, APPLICATION_CONTACT, DRIVE_SURFACE,
ROTATION_MECHANISM, CONVEYOR_CLEARANCE, SUPPORT_STRUCTURE, ADJUSTABILITY, INTERFERENCE,
SAFETY_GUARDING, UNKNOWN_NEEDS_REVIEW.

Return only data matching the supplied JSON schema.
""";

    public static async Task<AnalysisResult> AnalyzeRunAsync(string runDirectory, Options options)
    {
        var manifest = ManifestStore.Read(runDirectory);
        using var client = new OllamaClient(options.OllamaUrl);
        var model = options.Model ?? await client.FindVisionModelAsync();
        if (string.IsNullOrWhiteSpace(model))
            throw new NoVisionModelException(
                "No installed Ollama model advertises the 'vision' capability. Install or select a vision-capable model, then rerun analyze; the capture set is already preserved.");

        var analysisDir = Path.Combine(runDirectory, "analysis");
        Directory.CreateDirectory(analysisDir);
        var all = new List<ViewAnalysis>();

        foreach (var capture in manifest.Captures)
        {
            var imagePath = Path.Combine(runDirectory, capture.File.Replace('/', Path.DirectorySeparatorChar));
            var view = await client.AnalyzeImageAsync(model, imagePath, Prompt);
            view.SourceView = capture.File;
            all.Add(view);
            File.WriteAllText(
                Path.Combine(analysisDir, Path.GetFileNameWithoutExtension(imagePath) + ".json"),
                JsonSerializer.Serialize(view, ProgramBuckets.JsonOptions));
        }

        Bucketize(runDirectory, all);
        ManifestStore.MarkAnalyzed(runDirectory, model, all.Count);
        return new AnalysisResult(runDirectory, model, all.Count, "ANALYZED");
    }

    private static void Bucketize(string runDirectory, IReadOnlyList<ViewAnalysis> analyses)
    {
        var bucketMap = ProgramBuckets.All.ToDictionary(
            x => x,
            _ => new List<BucketItem>(),
            StringComparer.Ordinal);

        foreach (var view in analyses)
        {
            foreach (var observation in view.Observations)
            {
                var bucket = ProgramBuckets.Set.Contains(observation.Bucket)
                    ? observation.Bucket
                    : "UNKNOWN_NEEDS_REVIEW";

                var state = observation.EvidenceState is "OBSERVED" or "INFERRED"
                    ? observation.EvidenceState
                    : "INFERRED";

                bucketMap[bucket].Add(new BucketItem(
                    view.SourceView ?? "unknown",
                    state,
                    observation.Statement,
                    Math.Clamp(observation.Confidence, 0, 1),
                    observation.Objects ?? [],
                    observation.VerificationRequest));
            }
        }

        var bucketsDir = Path.Combine(runDirectory, "buckets");
        Directory.CreateDirectory(bucketsDir);
        foreach (var pair in bucketMap)
        {
            File.WriteAllText(
                Path.Combine(bucketsDir, pair.Key + ".json"),
                JsonSerializer.Serialize(new BucketFile(pair.Key, pair.Value), ProgramBuckets.JsonOptions));
        }
    }
}

internal sealed class OllamaClient : IDisposable
{
    private readonly HttpClient _http;

    public OllamaClient(string baseUrl)
    {
        _http = new HttpClient
        {
            BaseAddress = new Uri(baseUrl.TrimEnd('/') + "/"),
            Timeout = TimeSpan.FromMinutes(5)
        };
    }

    public async Task<object> GetModelsWithCapabilitiesAsync()
    {
        var result = new List<object>();
        foreach (var name in await ListModelNamesAsync())
        {
            var caps = await GetCapabilitiesAsync(name);
            result.Add(new { name, capabilities = caps });
        }
        return result;
    }

    public async Task<string?> FindVisionModelAsync()
    {
        foreach (var name in await ListModelNamesAsync())
        {
            var caps = await GetCapabilitiesAsync(name);
            if (caps.Contains("vision", StringComparer.OrdinalIgnoreCase))
                return name;
        }
        return null;
    }

    public async Task<ViewAnalysis> AnalyzeImageAsync(string model, string imagePath, string prompt)
    {
        var bytes = await File.ReadAllBytesAsync(imagePath);
        var base64 = Convert.ToBase64String(bytes);
        var schema = JsonNode.Parse(AnalysisSchema)
            ?? throw new InvalidOperationException("Could not build analysis JSON schema.");

        var payload = new JsonObject
        {
            ["model"] = model,
            ["stream"] = false,
            ["format"] = schema,
            ["options"] = new JsonObject { ["temperature"] = 0 },
            ["messages"] = new JsonArray
            {
                new JsonObject
                {
                    ["role"] = "user",
                    ["content"] = prompt,
                    ["images"] = new JsonArray(base64)
                }
            }
        };

        using var response = await _http.PostAsJsonAsync("api/chat", payload);
        var body = await response.Content.ReadAsStringAsync();
        if (!response.IsSuccessStatusCode)
            throw new InvalidOperationException($"Ollama /api/chat failed ({(int)response.StatusCode}): {body}");

        using var outer = JsonDocument.Parse(body);
        var content = outer.RootElement.GetProperty("message").GetProperty("content").GetString()
            ?? throw new InvalidOperationException("Ollama response did not contain message.content.");

        return JsonSerializer.Deserialize<ViewAnalysis>(content, ProgramBuckets.JsonOptions)
            ?? throw new InvalidOperationException("Ollama returned an empty analysis object.");
    }

    private async Task<List<string>> ListModelNamesAsync()
    {
        var json = await _http.GetStringAsync("api/tags");
        using var doc = JsonDocument.Parse(json);
        var names = new List<string>();
        if (doc.RootElement.TryGetProperty("models", out var models))
        {
            foreach (var m in models.EnumerateArray())
            {
                if (m.TryGetProperty("name", out var name) && name.GetString() is { Length: > 0 } s)
                    names.Add(s);
            }
        }
        return names;
    }

    private async Task<string[]> GetCapabilitiesAsync(string model)
    {
        using var response = await _http.PostAsJsonAsync("api/show", new { model });
        if (!response.IsSuccessStatusCode)
            return [];

        using var doc = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        if (!doc.RootElement.TryGetProperty("capabilities", out var caps) || caps.ValueKind != JsonValueKind.Array)
            return [];

        return caps.EnumerateArray()
            .Select(x => x.GetString())
            .Where(x => x is not null)
            .Cast<string>()
            .ToArray();
    }

    public void Dispose() => _http.Dispose();

    private const string AnalysisSchema = """
{
  "type": "object",
  "properties": {
    "summary": {"type": "string"},
    "observations": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "bucket": {"type": "string", "enum": ["PRODUCT_FLOW","PRODUCT_RESTRAINT","LABEL_PATH","PEEL_EDGE","APPLICATION_CONTACT","DRIVE_SURFACE","ROTATION_MECHANISM","CONVEYOR_CLEARANCE","SUPPORT_STRUCTURE","ADJUSTABILITY","INTERFERENCE","SAFETY_GUARDING","UNKNOWN_NEEDS_REVIEW"]},
          "evidence_state": {"type": "string", "enum": ["OBSERVED","INFERRED"]},
          "statement": {"type": "string"},
          "confidence": {"type": "number", "minimum": 0, "maximum": 1},
          "objects": {"type": "array", "items": {"type": "string"}},
          "verification_request": {"type": ["string", "null"]}
        },
        "required": ["bucket","evidence_state","statement","confidence","objects","verification_request"]
      }
    }
  },
  "required": ["summary","observations"]
}
""";
}

internal static class ManifestStore
{
    public static string PathFor(string runDirectory) => Path.Combine(runDirectory, "manifest.json");

    public static SweepManifest Read(string runDirectory) =>
        JsonSerializer.Deserialize<SweepManifest>(
            File.ReadAllText(PathFor(runDirectory)),
            ProgramBuckets.JsonOptions)
        ?? throw new InvalidOperationException("Could not parse visual-sweep manifest.");

    public static void Write(string runDirectory, SweepManifest manifest) =>
        File.WriteAllText(
            PathFor(runDirectory),
            JsonSerializer.Serialize(manifest, ProgramBuckets.JsonOptions));

    public static void MarkAnalyzed(string runDirectory, string model, int count)
    {
        var m = Read(runDirectory);
        Write(runDirectory, m with
        {
            Analysis = new AnalysisState(
                "ANALYZED",
                m.Analysis.OllamaUrl,
                model,
                $"{count} view(s) analyzed")
        });
    }

    public static void MarkAnalysisBlocked(string runDirectory, string reason)
    {
        var m = Read(runDirectory);
        Write(runDirectory, m with
        {
            Analysis = new AnalysisState(
                "BLOCKED_NO_VISION_MODEL",
                m.Analysis.OllamaUrl,
                null,
                reason)
        });
    }
}

internal static class ProgramBuckets
{
    public static readonly string[] All =
    [
        "PRODUCT_FLOW", "PRODUCT_RESTRAINT", "LABEL_PATH", "PEEL_EDGE",
        "APPLICATION_CONTACT", "DRIVE_SURFACE", "ROTATION_MECHANISM",
        "CONVEYOR_CLEARANCE", "SUPPORT_STRUCTURE", "ADJUSTABILITY",
        "INTERFERENCE", "SAFETY_GUARDING", "UNKNOWN_NEEDS_REVIEW"
    ];

    public static readonly HashSet<string> Set = new(All, StringComparer.Ordinal);
    public static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true,
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower
    };
}

internal static class ComRot
{
    [DllImport("ole32.dll", CharSet = CharSet.Unicode)]
    private static extern int CLSIDFromProgID(string lpszProgID, out Guid lpclsid);

    [DllImport("oleaut32.dll", PreserveSig = false)]
    [return: MarshalAs(UnmanagedType.Interface)]
    private static extern object GetActiveObject(ref Guid rclsid, IntPtr pvReserved);

    public static object GetActiveObject(string progId)
    {
        var hr = CLSIDFromProgID(progId, out var clsid);
        if (hr != 0)
            Marshal.ThrowExceptionForHR(hr);
        return GetActiveObject(ref clsid, IntPtr.Zero);
    }
}

internal sealed class NoVisionModelException(string message) : Exception(message);

internal sealed record CaptureResult(
    string RunDirectory,
    int CaptureCount,
    IReadOnlyList<string> CaptureErrors,
    bool ViewRestored);

internal sealed record AnalysisResult(
    string RunDirectory,
    string Model,
    int ViewCount,
    string State);

internal sealed record SweepSettings(int Views, int Width, int Height);
internal sealed record AnalysisState(string State, string OllamaUrl, string? Model, string? Note);
internal sealed record CaptureRecord(string File, double AzimuthDeg, double ElevationDeg, double[] Orientation16);

internal sealed record SweepManifest(
    string Schema,
    string RunId,
    string DocumentTitle,
    string DocumentPath,
    string Mode,
    SweepSettings Sweep,
    IReadOnlyList<CaptureRecord> Captures,
    IReadOnlyList<string> CaptureErrors,
    bool ViewRestored,
    AnalysisState Analysis);

internal sealed class ViewAnalysis
{
    public string Summary { get; set; } = "";
    public List<VisualObservation> Observations { get; set; } = [];
    public string? SourceView { get; set; }
}

internal sealed class VisualObservation
{
    public string Bucket { get; set; } = "UNKNOWN_NEEDS_REVIEW";
    public string EvidenceState { get; set; } = "INFERRED";
    public string Statement { get; set; } = "";
    public double Confidence { get; set; }
    public string[]? Objects { get; set; }
    public string? VerificationRequest { get; set; }
}

internal sealed record BucketItem(
    string SourceView,
    string EvidenceState,
    string Statement,
    double Confidence,
    IReadOnlyList<string> Objects,
    string? VerificationRequest);

internal sealed record BucketFile(string Bucket, IReadOnlyList<BucketItem> Items);
