# CADGrounded native C# SOLIDWORKS worker v0.1

Purpose: move the SOLIDWORKS COM/API boundary out of PowerShell.

This stage is intentionally read-only. It does NOT contain registry polling yet.
Instead it exposes a stable JSON command surface that the current registry worker
can call as a thin transport shim while registry polling is migrated separately.

## Hard allowlist

- `sw.status`
- `sw.query_components`
- `sw.closest_distance_pair`

Everything else is rejected. There is no generic code-execution command and no CAD write command.

## Why `sw.closest_distance_pair` exists

The earlier combined interference command failed inside SOLIDWORKS with
`RPC_E_SERVERFAULT (0x80010105)`. This command isolates only:

`IModelDoc2.ClosestDistance(Object, Object, ref Object, ref Object)`

It deliberately does not call the assembly interference detector.

Distance alone is not treated as proof of physical interference. A zero metric
distance can represent contact or overlap, so the response states that an
independent topology/interference observation is still required.

## Build

From this directory:

    build.cmd

Requires a .NET 8 SDK and the installed SOLIDWORKS interop DLLs at:

    C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS

## Test

Keep the intended SOLIDWORKS v21 assembly open and active, then:

    smoke-v21.cmd

Or manually:

    bin\Release\net8.0-windows\win-x64\CadGrounded.SolidWorksWorker.exe status

    bin\Release\net8.0-windows\win-x64\CadGrounded.SolidWorksWorker.exe closest-distance ^
      --a "6130460_03_AR60_NATIVE_PORTABLE_V18-2" ^
      --b "BENCH_BOTTLE_D48_H180-3"

## JSON transport

One request:

    echo {"command_id":"sw.status","payload":{}} | CadGrounded.SolidWorksWorker.exe execute-json

Persistent line-delimited JSON:

    CadGrounded.SolidWorksWorker.exe serve-stdio

Example request:

    {"command_id":"sw.closest_distance_pair","payload":{"a_name_exact":"6130460_03_AR60_NATIVE_PORTABLE_V18-2","b_name_exact":"BENCH_BOTTLE_D48_H180-3"}}

## Cut-over plan

1. Verify `status` attaches to the same v21 assembly as the existing worker.
2. Verify `closest-distance` on AR60 ↔ Bottle 3.
3. Change the existing registry worker into a thin registry/stdio shim.
4. Port registry heartbeat/claim/complete HTTP code to C# only after the exact
   current registry contract is read from the repository.
5. Retire CAD COM logic from PowerShell.

Do not infer that this source has compiled successfully on a SOLIDWORKS machine
until `build.cmd` succeeds there. This bundle was generated outside Windows and
does not contain SOLIDWORKS proprietary assemblies.
