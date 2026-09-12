# CADGrounded SOLIDWORKS Bridge v0.3.0

This source upgrade adds sw_execute_code to the existing status, component query,
transform and insertion tools. It accepts complete C# source through MCP and
runs it inside SOLIDWORKS using the existing UI-thread dispatcher. There is no
need to paste each new operation into the VBA editor or add an MCP tool for each API.

## Install on your Windows PC

1. Save CAD work and close SOLIDWORKS. Stop the old Node bridge server with Ctrl+C.
2. Extract the ZIP. Open Administrator PowerShell in the folder containing
   scripts, src, and this file (not the outer Downloads folder).
3. Run:

```powershell
.\scripts\upgrade.ps1
```

The project now copies the three SOLIDWORKS interop DLLs beside the add-in for
registration. The existing add-in identity is retained.

4. Reopen SOLIDWORKS and the v12 assembly. Enable CADGrounded in Add-Ins if needed.
5. From this same extracted project folder run:

```powershell
.\scripts\start-server.ps1 -MaxControl
```

Keep that terminal open. Use your existing tunnel to port 8765. The upgrade does
not create a new tunnel or change your credentials. Check locally:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
```

Expect version 0.3.0, writes_enabled true and max_control_enabled true. Refresh
or rescan the connected app's tool list so sw_execute_code and
sw_insert_component are visible. Selecting the plugin alone does not update an
older tool catalog. sw_status reports the add-in version; /health reports the
Node server version. Both need to be 0.3.0.

## Execution contract

Submit complete source defining:

```csharp
public static object BridgeScript.Run(SolidWorks.Interop.sldworks.SldWorks app)
```

See examples/InspectActive.cs for a complete first test. Use C# 5-compatible
syntax with the Windows .NET Framework CodeDOM compiler. Reference assemblies
include System, System.Core, Microsoft.CSharp, System.Web.Extensions, and the
installed SOLIDWORKS sldworks/swconst interop DLLs.

First call sw_status. Pass its exact title and path to sw_execute_code with
apply=false and the full example source string. Empty title/path together mean
no active document; an unsaved document has its real title and empty path.
Compilation does not invoke Run. Successful compilation returns diagnostics,
a source hash and a random single-use preflight_token valid for ten minutes.
Call again with identical source/title/path, that token, and apply=true.
Only the previously compiled entry point runs. The token is consumed before
execution. This guards document identity, not arbitrary geometry changes:
scripts must check any required component/feature state themselves.

Return plain JSON-compatible primitives, arrays, anonymous objects or dictionaries.
Do not return COM objects. Check API return values and errors in scripts; read
back resulting document/component state afterward. The handler's success means
the script returned and its result serialized, not that a design is correct.

## Scope of maximum control

Scripts can call document open/create/save APIs, build sketches/features,
create mates, set dimensions/configurations, inspect geometry, export files,
and invoke an existing supported macro through app.RunMacro2. These are API
capabilities accessed by writing the appropriate script, not individually
implemented or live-tested workflows in this package. A .bas text module is not
a runnable .swp macro; C# execution avoids that conversion entirely.

MaxControl implies AllowWrites. It permits trusted arbitrary C# under the
Windows account running SOLIDWORKS, including filesystem/process access. This is
not a sandbox or a UI remote-control driver. Code can save, delete or close
files if explicitly written to do so. The bridge does not automatically save.
The MCP mode gate is in Node; the named pipe remains a trusted local transport,
not a separate authentication boundary. Retain the existing tunnel controls.

A timeout/disconnection DOES NOT cancel queued or running code. Scripts run on
the SOLIDWORKS UI thread and can block it. Do not use endless loops, modal
prompts, long sleeps, or background COM calls. After an uncertain result inspect
CAD state and the existing audit log before preparing another execution. There
is no automatic rollback, retry, or guaranteed cancellation. Source and hash are
audited before Run. Partial changes may remain on any runtime error.

Prepared code is limited to eight pending tokens. Compiled assemblies remain
loaded for the SOLIDWORKS session even after token expiry; restart SOLIDWORKS
periodically during heavy scripting. For lower access, restart Node without
-MaxControl (or with only -AllowWrites for the structured tools).

## Validation and rollback

Node tests cover disabled gates, compilation forwarding, required token,
execution forwarding, and no retry after transport failure, plus insertion
handler regression tests. Windows compilation, COM execution and a live CAD
smoke test must be completed on your machine; they were not run in the Linux
build workspace. Start with InspectActive, then ZoomToFit, before geometry edits.

To roll back: close SOLIDWORKS and stop Node; register the previous package's
add-in, reopen SOLIDWORKS, and start the previous Node server.

Implementation reference: Microsoft CSharpCodeProvider / CompileAssemblyFromSource
https://learn.microsoft.com/en-us/dotnet/api/microsoft.csharp.csharpcodeprovider?view=netframework-4.8.1
