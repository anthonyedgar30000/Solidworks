# CADGrounded native C# SOLIDWORKS worker v0.4.3

Purpose: keep the SOLIDWORKS COM/API boundary inside a narrow native C# process with a hard read-only command allowlist.

There is no generic code-execution command and no CAD write command.

## Hard allowlist

- `sw.status`
- `sw.query_components`
- `sw.query_interface_contract` (local-only; not Remote Queue authorized)
- `sw.diagnose_interface_connectors` (local-only; not Remote Queue authorized)
- `sw.diagnose_feature_manager_tree` (local-only; not Remote Queue authorized)
- `sw.closest_distance_pair`
- `sw.classify_contact_pair` (native-only unless separately authorized by a transport policy)
- `sw.classify_contact_pair_at_transform` (native-only hypothetical fit check; never assigns `Component2.Transform2`)
- `sw.query_mates`

`sw.query_interface_contract` requires exact requested coordinate-system feature
names and exact requested Published Reference connector feature names. It reads
`CoordSys` transforms through the ordinary bounded `IFeature` path and
Published Reference connector identity/type through the visible FeatureManager
tree. Connector matches must be exact direct children of exactly one
`Published References` / `ConnectRefMgr` branch. It returns only those matching
records plus their bounded tree parentage, fails closed on a missing, duplicate,
null-object, non-`IFeature`, wrong-name, or wrong-type target, and reports
`write_authority: NONE` and `model_mutation: false`.

It intentionally does not infer connector-to-coordinate-system geometric
coincidence, Asset Publisher snap behavior, physical contact, collision
clearance, motion, force, or mechanical acceptance. It remains local-only
until a separate policy review; native capability does not imply Remote Queue
authorization.

`sw.diagnose_interface_connectors` is a bounded diagnostic for a failed
Published Reference discovery. For exact requested connector names, it compares
`IAssemblyDoc.FeatureByName` with the existing recursive feature traversal and
records any observed `ConnectRefMgr` / connector rows with name, type, parent,
and tree depth. It remains a preserved diagnostic record: its direct/ordinary
feature-surface result does not overwrite the separately verified
FeatureManager-tree connector reader.

`sw.diagnose_feature_manager_tree` is a separate bounded diagnostic for an API
observation-surface mismatch. It traverses the visible FeatureManager design
tree through `IModelDoc2.FeatureManager -> IFeatureManager.GetFeatureTreeRootItem2`
and returns only exact requested displayed-tree texts. For each observed node it
records tree depth/path, `ObjectType`, whether `Object` is null, the runtime
.NET/COM classification of `Object`, and `IFeature` name/type only if the
object resolves to `IFeature`. Its reviewed binding path is also used by the
interface-contract reader for exact Published References parentage, while the
separate direct/ordinary-feature observations remain preserved diagnostics.

`sw.query_mates` is an observation primitive. It requires one exact `Component2.Name2` and traverses the active assembly's mate group without selecting, editing, rebuilding, suppressing, moving, or mating any component. It reports the target's exact identity, component state, referenced configuration, parent chain, and active-assembly mate definitions that reference it, including mate entities, API type/alignment values, active-configuration suppression observation, entity parameters, and distance/angle variation values when SOLIDWORKS exposes them.

A mate definition is evidence of a SOLIDWORKS constraint, not proof of spring stiffness, preload, force, contact pressure, physical closure ownership, or operating sequence. A component with no returned mate is likewise not proof that its physical mechanism is absent; it may be a feature, a nested/external boundary, or an unmodeled/undocumented relation.

## `sw.closest_distance_pair`

This command isolates:

`IModelDoc2.ClosestDistance(Object, Object, ref Object, ref Object)`

It deliberately does not call the assembly interference detector. Distance alone is not treated as proof of physical interference. A zero metric distance can represent contact or overlap.

## `sw.classify_contact_pair`

This worker command uses `IModelDoc2.ClosestDistance` and, only for near-zero pairs, Boolean intersection on transformed temporary body copies. It does not mutate the assembly model. Remote exposure is a separate policy decision.

## `sw.classify_contact_pair_at_transform`

This is a bounded native-only hypothetical fit-check primitive. It evaluates two
exact top-level components at absolute candidate assembly-space transforms
without moving either component in the assembly.

The request must bind to the exact active document title, path, and active
configuration. Each component candidate is optional. When omitted, that
component's current `Transform2` is read and used as the evaluation transform.
When supplied, a candidate contains exactly:

- `rotation9`: nine finite doubles in SOLIDWORKS `MathTransform.ArrayData`
  rotation ordering; the matrix must already be a proper right-handed
  orthonormal rotation;
- `translation_mm`: three finite doubles in millimetres.

Example:

    {
      "command_id": "sw.classify_contact_pair_at_transform",
      "payload": {
        "document_title_exact": "IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE.SLDASM",
        "document_path_exact": "C:\\ChatGPT\\Solidworks\\IXOR\\CAB_IXOR_6130800\\IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE.SLDASM",
        "active_configuration_exact": "Default",
        "a_name_exact": "EXACT_COMPONENT_A-1",
        "b_name_exact": "EXACT_COMPONENT_B-1",
        "a_candidate_transform": {
          "rotation9": [1,0,0,0,1,0,0,0,1],
          "translation_mm": [100,200,300]
        }
      }
    }

The worker obtains source solids with `IComponent2.GetBodies3`, copies them with
`IBody2.Copy`, and applies only the evaluation transforms to those temporary
copies. It performs B-rep intersection with
`IBody2.Operations2(SWBODYINTERSECT)`. For non-intersecting temporary solids it
measures face-pair minimum distance with `IEntity.GetDistance`.

`IModelDoc2.ClosestDistance` is deliberately **not** used for hypothetical
geometry because SOLIDWORKS documents that temporary geometric entities are
unsupported by that method. Positive B-rep intersection deterministically
implies zero set distance; otherwise the face-pair distance is reported when
available. Body-pair and face-pair work are explicitly bounded and fail closed
when limits are exceeded.

The response includes current and evaluated transforms, exact component
identities, distance evidence when available, intersection volume,
classification, API provenance, `model_mutation: false`, and
`write_authority: "NONE"`.

This command never assigns `Component2.Transform2`; it does not select, move,
mate, rebuild, save, suppress, or otherwise modify the assembly. Native
capability does **not** authorize Remote Queue exposure. Remote Queue schema,
validator, config, and allowlist remain unchanged until separately reviewed.

## `sw.query_mates`

CLI example:

    bin\Release\net8.0-windows\win-x64\CadGrounded.SolidWorksWorker.exe mates ^
      --component "FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-2"

JSON example:

    {"command_id":"sw.query_mates","payload":{"component_name_exact":"FITCHECK_WRAP_SUPPORT_ROLLER_D30_H93_V25-2"}}

The query fails closed unless the exact component name resolves uniquely in the active assembly.

## `sw.query_interface_contract`

CLI example:

    bin\Release\net8.0-windows\win-x64\CadGrounded.SolidWorksWorker.exe interface-contract ^
      --coordinate-system "PRODUCT_ENTRY_CS" ^
      --coordinate-system "PRODUCT_EXIT_CS" ^
      --connector "Connector2" ^
      --connector "Connector1"

JSON example:

    {"command_id":"sw.query_interface_contract","payload":{"coordinate_system_feature_names":["PRODUCT_ENTRY_CS","PRODUCT_EXIT_CS"],"published_reference_connector_names":["Connector2","Connector1"]}}

For the v42 reference assembly, use `Verify-InterfaceContract-V42.ps1`. It
compares pre/post complete component state, document state, and stable shared
file evidence, first for the two local diagnostics and then for the bounded
exact interface query. Both diagnostics write their raw/summary artifacts even
if the query subsequently fails closed. A pass verifies only the declared
feature/frame baseline at that fresh checkpoint.

All JSON evidence artifacts from this verifier are written through an explicit
.NET UTF-8-without-BOM writer. This avoids Windows PowerShell 5.1's BOM-emitting
`Set-Content -Encoding UTF8` behavior for the raw observation consumed by the
strict Python drift/authority verifier. The writer affects only evidence files;
it has no SOLIDWORKS or Remote Queue authority.

## `sw.diagnose_interface_connectors`

CLI example:

    bin\Release\net8.0-windows\win-x64\CadGrounded.SolidWorksWorker.exe interface-connectors-diagnostic ^
      --connector "Connector2" ^
      --connector "Connector1"

This command is diagnostic-only. `DIRECT_LOOKUP_TRAVERSAL_PATH_DEFECT` means
the direct API resolved an exact `MagneticConnectRef` while the existing
recursive traversal did not; it is not connector acceptance and does not alter
the reader. `LIVE_STATE_SOURCE_CONFLICT` means neither observation path found a
requested connector and no connector evidence may be invented.

## `sw.diagnose_feature_manager_tree`

CLI example:

    bin\Release\net8.0-windows\win-x64\CadGrounded.SolidWorksWorker.exe feature-manager-tree-diagnostic ^
      --tree-text "Published References" ^
      --tree-text "Ground Plane" ^
      --tree-text "Connector1" ^
      --tree-text "Connector2"

This diagnostic distinguishes the visible FeatureManager representation from
the ordinary model-feature surface. Its observations are not connector
acceptance: a visible label does not prove `MagneticConnectRef`, geometry,
coordinate-system coincidence, snap behavior, or mechanical acceptance.

## Build

From this directory:

    build.cmd

Requires a .NET 8 SDK and the installed SOLIDWORKS interop DLLs at:

    C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS

## CI compile gate

GitHub Actions compiles this same `net8.0-windows` / `win-x64` project on a Windows runner with `UseNuGetSolidWorksInterop=true`. That property is CI-only: it supplies pinned interop metadata solely to compile the worker source and does not start, connect to, or modify SOLIDWORKS.

A passing CI compile catches C# source and Windows-target build regressions before a worker change is considered verification-ready. It does **not** replace the required native-host `build.cmd` result, nor does it establish any live CAD fact or no-mutation result.

## Verification before transport exposure

1. The GitHub Actions Windows compile gate must pass.
2. Build successfully on the SOLIDWORKS Windows host with `build.cmd` (installed interop DLLs).
3. Run `version` and verify worker version `0.4.3`.
4. Run `status` and verify `write_authority: NONE` and the exact active document.
5. Run `mates --component <exact Name2>` against a known component.
6. For the v42 capture-owner investigation, run `Verify-QueryMates-V42.ps1` against the exact active v42 assembly. It compares document identity/configuration/save state, target component state/transforms, and assembly file evidence before and after the three target mate reads.
7. For v42 interface consumption, run `Verify-InterfaceContract-V42.ps1` against `IXOR_Benchmark_v42_ASSET_INTERFACE_TEST_PORTABLE.SLDASM`. It does not materialize the complementary asset.
8. Only then expose any native command through a separately reviewed Remote Queue validator/schema/allowlist.

Do not infer that repository source has compiled successfully on a SOLIDWORKS machine until `build.cmd` succeeds there. Repository review is not runtime verification.

The local v42 evidence contract and result-interpretation limits are in
`../../docs/V42_CAPTURE_OWNER_BINDING_EVIDENCE_CONTRACT.md`. This worker change
does not alter any Remote Queue file, allowlist, or authority.
