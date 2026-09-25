# CADGrounded native C# SOLIDWORKS worker v0.3.1

Purpose: keep the SOLIDWORKS COM/API boundary inside a narrow native C# process with a hard read-only command allowlist.

There is no generic code-execution command and no CAD write command.

## Hard allowlist

- `sw.status`
- `sw.query_components`
- `sw.closest_distance_pair`
- `sw.classify_contact_pair` (native-only unless separately authorized by a transport policy)
- `sw.query_mates`

`sw.query_mates` is an observation primitive. It requires one exact `Component2.Name2` and traverses the active assembly's mate group without selecting, editing, rebuilding, suppressing, moving, or mating any component. It reports the target's exact identity, component state, referenced configuration, parent chain, and active-assembly mate definitions that reference it, including mate entities, API type/alignment values, active-configuration suppression observation, entity parameters, and distance/angle variation values when SOLIDWORKS exposes them.

A mate definition is evidence of a SOLIDWORKS constraint, not proof of spring stiffness, preload, force, contact pressure, physical closure ownership, or operating sequence. A component with no returned mate is likewise not proof that its physical mechanism is absent; it may be a feature, a nested/external boundary, or an unmodeled/undocumented relation.

## `sw.closest_distance_pair`

This command isolates:

`IModelDoc2.ClosestDistance(Object, Object, ref Object, ref Object)`

It deliberately does not call the assembly interference detector. Distance alone is not treated as proof of physical interference. A zero metric distance can represent contact or overlap.

## `sw.classify_contact_pair`

This worker command uses `IModelDoc2.ClosestDistance` and, only for near-zero pairs, Boolean intersection on transformed temporary body copies. It does not mutate the assembly model. Remote exposure is a separate policy decision.

## `sw.query_mates`

CLI example:

    bin\Release\net8.0-windows\win-x64\CadGrounded.SolidWorksWorker.exe mates ^
      --component "FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-2"

JSON example:

    {"command_id":"sw.query_mates","payload":{"component_name_exact":"FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-2"}}

The query fails closed unless the exact component name resolves uniquely in the active assembly.

## Build

From this directory:

    build.cmd

Requires a .NET 8 SDK and the installed SOLIDWORKS interop DLLs at:

    C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS

## CI compile gate

GitHub Actions compiles this same `net8.0-windows` / `win-x64` project on a Windows runner with `UseNuGetSolidWorksInterop=true`. That property is CI-only: it supplies pinned interop metadata solely to compile the worker source and does not start, connect to, or modify SOLIDWORKS.

A passing CI compile catches C# source and Windows-target build regressions before a worker change is considered verification-ready. It does **not** replace the required native-host `build.cmd` result, nor does it establish any live CAD fact or no-mutation result.

## Verification before transport exposure

1. The GitHub Actions Windows compile gate must pass.\n2. Build successfully on the SOLIDWORKS Windows host with `build.cmd` (installed interop DLLs).
3. Run `version` and verify worker version `0.3.1`.
4. Run `status` and verify `write_authority: NONE` and the exact active document.
5. Run `mates --component <exact Name2>` against a known component.
6. For the v42 capture-owner investigation, run `Verify-QueryMates-V42.ps1` against the exact active v42 assembly. It compares document identity/configuration/save state, target component state/transforms, and assembly file evidence before and after the three target mate reads.
7. Only then expose `sw.query_mates` through a separately reviewed Remote Queue validator/schema/allowlist.

Do not infer that repository source has compiled successfully on a SOLIDWORKS machine until `build.cmd` succeeds there. Repository review is not runtime verification.

The local v42 evidence contract and result-interpretation limits are in
`../../docs/V42_CAPTURE_OWNER_BINDING_EVIDENCE_CONTRACT.md`. This worker change
does not alter any Remote Queue file, allowlist, or authority.
