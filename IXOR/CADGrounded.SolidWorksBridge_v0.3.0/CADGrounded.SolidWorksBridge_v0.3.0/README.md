# v0.3.0 maximum-control upgrade

Start with **MAX_CONTROL.md**. Older instructions below describe the structured tools.

# CADGrounded.SolidWorksBridge v0.3.0

Start with [UPGRADE.md](UPGRADE.md) for installation and the new `sw_insert_component` command.
This source release adds native component insertion. Node handler tests pass; the C# add-in
requires compilation and live acceptance on Windows with your SOLIDWORKS interop libraries.
The v0.1 documentation below describes the retained tools; it is not the insertion specification.

A private, narrow bridge between ChatGPT/MCP and a running SOLIDWORKS desktop session.

This repository is deliberately **not** a generic remote-control layer. It exposes a small CAD authority surface so deterministic geometry stays authoritative and every write can be audited.

## Architecture

```text
ChatGPT custom MCP app
        |
        | Secure MCP Tunnel / remote MCP transport
        v
Local MCP server (Node.js)
        |
        | Windows named pipe
        v
CADGrounded SOLIDWORKS C# add-in
        |
        v
SOLIDWORKS API (authoritative geometry/session state)
```

The C# add-in runs in-process with SOLIDWORKS and marshals bridge requests back onto the SOLIDWORKS UI thread before touching COM objects. This avoids the external PowerShell/late-bound COM behavior seen during the benchmark work.

## v0.1 tool surface

- `sw_status` — read the active SOLIDWORKS document/session status.
- `sw_query_components` — read component identity, path, fixed/suppressed state, transform, and approximate `Component2.GetBox` bounding box.
- `sw_set_transform` — propose or apply an exact transform to one **floating** top-level component. Writes are disabled by default and audited when enabled.

There is intentionally no arbitrary VBA execution, arbitrary SOLIDWORKS command execution, generative geometry, delete operation, or filesystem wildcard insertion in v0.1.

## Safety model

`sw_set_transform` is fail-closed:

1. The MCP server validates the 3x3 rotation as finite, orthonormal, and right-handed.
2. `apply=false` is the default and performs a dry run only.
3. Actual writes require `SWBRIDGE_ALLOW_WRITES=1` on the local MCP server.
4. The target component name must match a top-level component exactly.
5. The SOLIDWORKS add-in independently validates the rotation.
6. The component must be floating; fixed components are rejected rather than silently unfixed.
7. Actual writes require the exact active document title from a prior `sw_status` read.
8. Actual writes require a complete compare-and-set `expected_before` transform from a prior component query.
9. SOLIDWORKS rebuilds after the transform.
10. The resulting transform is re-read from SOLIDWORKS and compared with the request.
11. A mismatch triggers rollback to the before transform.
12. Applied writes are appended to `%LOCALAPPDATA%\CADGrounded\SolidWorksBridge\audit.jsonl`.

See `docs/AUTHORITY_MODEL.md`.

## Prerequisites

### SOLIDWORKS side

- SOLIDWORKS 2026 desktop.
- Visual Studio or Build Tools with **MSBuild + .NET Framework 4.8** development tools. The add-in project is classic .NET Framework and does **not** require `Microsoft.NET.Sdk`.
- 64-bit build environment.

The project expects the SOLIDWORKS interop DLLs at:

```text
C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\api\redist
```

If your installation differs, pass `SolidWorksApiDir` to MSBuild or edit the project property.

### MCP side

- Node.js 20+ (Node 22 is fine).
- npm.

The MCP server uses the current split MCP TypeScript SDK packages at the time this scaffold was created:

- `@modelcontextprotocol/server` 2.0.0
- `@modelcontextprotocol/node` 2.0.0

The server itself is plain ESM JavaScript to keep the first bridge easy to inspect and run.

## 1. Build the SOLIDWORKS add-in

Open an **Administrator PowerShell** in this repository and run:

```powershell
.\scripts\build-addin.ps1
.\scripts\register-addin.ps1
```

Then restart SOLIDWORKS.

In SOLIDWORKS, open:

```text
Tools > Add-Ins
```

and ensure **CADGrounded SolidWorks Bridge** is loaded. The registration script also requests load-at-startup.

To unregister later:

```powershell
.\scripts\unregister-addin.ps1
```

## 2. Verify the local named-pipe bridge

Open `IXOR_Benchmark_v11.SLDASM` in SOLIDWORKS, then from the MCP server directory:

```powershell
cd .\src\mcp-server
node .\scripts\pipe-smoke.mjs sw_status
node .\scripts\pipe-smoke.mjs sw_query_components
npm run verify:benchmark
```

These calls bypass MCP and test only:

```text
Node -> named pipe -> SOLIDWORKS add-in -> SOLIDWORKS API
```

For the current canonical benchmark, `docs/ACCEPTANCE_TEST.md` records the expected IXOR and floor-stand state.

## 3. Start the local MCP server in read-only mode

```powershell
cd .\src\mcp-server
npm install
npm start
```

Default endpoint:

```text
http://127.0.0.1:8765/mcp
```

Health check:

```text
http://127.0.0.1:8765/health
```

The server binds to loopback by default.

## 4. Connect ChatGPT

ChatGPT does not connect directly to a developer machine's `localhost`. For a local/private MCP server, use OpenAI's **Secure MCP Tunnel** (where available for your ChatGPT plan/workspace) rather than exposing this bridge directly to the public internet.

Create a custom MCP app in ChatGPT Developer Mode using the tunnel-provided MCP endpoint, scan the tools, and keep writes disabled for the first acceptance pass.

Current OpenAI product details can change, so use the current ChatGPT Developer Mode / MCP app documentation when performing this step.

## 5. First live acceptance test

From ChatGPT with the custom app selected:

```text
Use sw_status, then sw_query_components. Do not modify anything.
```

We expect the API-returned active assembly and component transforms to match `docs/ACCEPTANCE_TEST.md`.

That round trip is the v0.1 read-path acceptance gate:

```text
ChatGPT -> MCP -> named pipe -> SOLIDWORKS API -> actual benchmark state -> ChatGPT
```

## 6. Write-path staging

Do **not** enable writes just to prove the bridge can move the already-frozen IXOR or stand.

First test a dry-run proposal:

```json
{
  "component_name": "IXOR_6130800_NATIVE-1",
  "rotation9": [1,0,0, 0,0,1, 0,-1,0],
  "translation_mm": [154.24,-200,1000],
  "apply": false
}
```

This must return a proposed operation without changing SOLIDWORKS.

For the first *actual* write, use the next intentionally floating component (for example the SP100 when inserted) and enable writes only for that controlled test:

```powershell
$env:SWBRIDGE_ALLOW_WRITES = "1"
npm start
```

The target must remain floating. Actual writes require `expected_document_title` plus a complete `expected_before` transform from live reads, so writes behave like compare-and-set operations rather than blind moves.

## Repository layout

```text
src/
  CADGrounded.SolidWorksAddin/  In-process SOLIDWORKS COM add-in
  mcp-server/                   Local MCP server + named-pipe client
scripts/                        Build/register/unregister PowerShell

docs/
  ACCEPTANCE_TEST.md
  AUTHORITY_MODEL.md
```

## What v0.1 does not claim

- `Component2.GetBox` is an approximate SOLIDWORKS bounding box sanity check, not a precision B-rep measurement.
- A successful transform does not prove mechanical feasibility.
- The bridge does not infer CAD identity, dimensions, product flow, clearances, or machine functionality.
- ChatGPT/MCP is an orchestration layer; SOLIDWORKS and source CAD remain the geometry authority.
