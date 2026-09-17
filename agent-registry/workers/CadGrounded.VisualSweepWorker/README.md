# CadGrounded.VisualSweepWorker v0.1

A local visual-observation pipeline for SOLIDWORKS assemblies.

The worker rotates the **model view**, not assembly components, captures repeatable viewpoints, restores the original view, sends the saved images to a **local Ollama vision model**, and sorts structured observations into fixed evidence buckets.

## Authority boundary

This worker is intentionally not a mechanical authority.

- SOLIDWORKS remains authoritative for actual geometry, transforms, contact, interference and clearance.
- The visual model may emit only `OBSERVED` or `INFERRED` evidence.
- Visual evidence cannot promote itself to `CAD_VERIFIED` or `PHYSICS_VERIFIED`.
- No components, mates, features, configurations or document geometry are modified.
- The document is never saved by this worker.
- View orientation, translation and scale are saved before the sweep and restored in `finally`.

## Pipeline

```text
Active SOLIDWORKS assembly
        |
        v
Save current view state
        |
        v
Zoom-to-fit + controlled azimuth sweep
        |
        +--> images/az000_el000.png
        +--> images/az045_el000.png
        +--> ...
        |
        v
Restore original view exactly
        |
        +--> manifest.json
        +--> geometry_snapshot.json
        |
        v
Local Ollama /api/chat
        |
        v
Strict structured visual observations
        |
        +--> analysis/<view>.json
        |
        v
Fixed evidence buckets
        |
        +--> buckets/PRODUCT_FLOW.json
        +--> buckets/PRODUCT_RESTRAINT.json
        +--> buckets/LABEL_PATH.json
        +--> buckets/PEEL_EDGE.json
        +--> buckets/APPLICATION_CONTACT.json
        +--> buckets/DRIVE_SURFACE.json
        +--> buckets/ROTATION_MECHANISM.json
        +--> buckets/CONVEYOR_CLEARANCE.json
        +--> buckets/SUPPORT_STRUCTURE.json
        +--> buckets/ADJUSTABILITY.json
        +--> buckets/INTERFERENCE.json
        +--> buckets/SAFETY_GUARDING.json
        +--> buckets/UNKNOWN_NEEDS_REVIEW.json
```

## Commands

```powershell
# Show installed Ollama models and advertised capabilities
dotnet run --project .\CadGrounded.VisualSweepWorker.csproj -- models

# Capture only; no model required
dotnet run --project .\CadGrounded.VisualSweepWorker.csproj -- capture --views 8

# Capture and analyze with an installed local vision model
dotnet run --project .\CadGrounded.VisualSweepWorker.csproj -- run --views 8 --model <vision-model>

# Analyze a previously captured run
dotnet run --project .\CadGrounded.VisualSweepWorker.csproj -- analyze --run "C:\path\to\inspection_runs\2026-09-16_20-24-26" --model <vision-model>
```

Optional environment variables:

```powershell
$env:CADGROUNDED_OLLAMA_URL = "http://127.0.0.1:11434"
$env:CADGROUNDED_OLLAMA_VISION_MODEL = "<installed-vision-model>"
```

If no model is supplied, the worker queries installed Ollama models and selects one that advertises the `vision` capability. If none exists, capture succeeds and the manifest is marked `BLOCKED_NO_VISION_MODEL`; evidence is preserved for later analysis.

## Output

By default, runs are stored beside the active SOLIDWORKS document:

```text
inspection_runs/
└── yyyy-MM-dd_HH-mm-ss/
    ├── manifest.json
    ├── geometry_snapshot.json
    ├── images/
    ├── analysis/
    └── buckets/
```

`geometry_snapshot.json` records top-level component identity, source path, transform and approximate box data from the SOLIDWORKS API. It is supporting deterministic context; visual analysis does not override it.

## v0.1 live proof

On 2026-09-16 the view-sweep core was exercised against the active `IXOR_Benchmark_v41_MAX_ROLLER2_COMPLIANCE_REFERENCE_PORTABLE` assembly through the local SOLIDWORKS bridge.

- 8 azimuth captures at 45-degree increments
- 1600 x 900 BMP capture size
- 0 capture errors
- original view restored successfully
- run directory: `C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\inspection_runs\2026-09-16_20-24-26`
- local Ollama reachable at `http://127.0.0.1:11434`
- installed model observed during the test: `qwen2.5:3b`
- that model did not advertise vision capability, so image analysis was intentionally left pending

The repository worker converts future `SaveBMP` captures to PNG before sending them to Ollama.

## Next layer

The next deterministic stage should consume each observation's `verification_request` and map it to bounded CAD checks such as component identity, minimum distance, interference, travel or known axis/DOF checks. Only that stage may promote evidence from `INFERRED` to `CAD_VERIFIED`.
