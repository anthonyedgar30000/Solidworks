# v42 interface live-state reconciliation — 2026-09-25

## Source precedence applied

- GitHub `main` was reread at commit `8749d25907a3abcbe13d70f60fe34ad1e21d4dd2` (merged PR #19).
- The current source contract is `v42_product_flow.cad-interface-contract.v1.json` from that main baseline.
- A fresh read-only SOLIDWORKS bridge `sw.status` observation identified the active assembly as `IXOR_Benchmark_v42_ASSET_INTERFACE_TEST_PORTABLE.SLDASM` at `C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v42_ASSET_INTERFACE_TEST_PORTABLE.SLDASM`.
- A fresh read-only `components --all` observation for that same active document reported 55 component records.

This document records source binding only. It does not turn a repository fixture or a component inventory into a coordinate-system or Published Asset geometry observation.

## Current evidence boundary

The bridge observation establishes the active document identity and component inventory under SOLIDWORKS API authority. It does **not** expose:

- `PRODUCT_ENTRY_CS` or `PRODUCT_EXIT_CS` feature identity/type/transform;
- `Connector1` or `Connector2` feature identity/type;
- Published References manager grouping; or
- Published Asset ↔ coordinate-system geometric coincidence.

Accordingly, the declared v42 coordinate-system baseline is `STALE_STATE` for current-live verification purposes until a Windows host runs the bounded local `sw.query_interface_contract` evidence contract and its pre/post no-mutation verifier. Published Asset ↔ coordinate-system geometric coincidence remains `UNRESOLVED`.

No conclusion about snap behavior, contact, clearance, motion, force, preload, temporal operation, or mechanical acceptance follows from this reconciliation.

## Host diagnostic progression: API surface mismatch

At PR #20 head `757378c83763d4f3aadde0081a35349a5fd76a20`, the Windows/SOLIDWORKS
host verifier reached the unchanged `sw.query_interface_contract` call and
failed closed there. Before that failure, its local-only
`sw.diagnose_interface_connectors` artifact completed with:

- `Connector1` and `Connector2`: direct `IAssemblyDoc.FeatureByName` =
  `NOT_FOUND`;
- ordinary `IModelDoc2.FirstFeature/GetNextFeature` plus recursive subfeature
  traversal: neither connector and no `ConnectRefMgr` observed;
- classification: `LIVE_STATE_SOURCE_CONFLICT`;
- `model_mutation: false`, `write_authority: NONE`.

Those are negative observations of two API surfaces, not proof that the
Published References are absent. Fresh human-observed live SOLIDWORKS UI
evidence from the same active v42 assembly shows the Asset Publisher
PropertyManager entries `Connector1` and `Connector2`; `Connector2` visibly
retains its Connect Point edge and Connect Direction face. This human/UI
evidence has its own authority and creates an unresolved
**API-observation-surface / representation mismatch**. It does not transform
either API-negative result into verified connector geometry, and it does not
authorize a contract rebaseline or a CAD change.

At PR #20 head `17d6c6a61b7af4fa596ee2b865117406e9fe0cb7`, the subsequent
local-only `sw.diagnose_feature_manager_tree` observation established the
missing representation binding:

- exactly one `Published References` node at tree path `0.8`, with a non-null
  COM object resolving to `IFeature`, `Name="Published References"`, and
  `GetTypeName2()="ConnectRefMgr"`;
- exactly one `Ground Plane` node at `0.8.0`, resolving to an `IFeature` of
  type `MagneticConnectRef`;
- exactly one `Connector1` node at `0.8.1`, resolving to `IFeature`,
  `Name="Connector1"`, type `MagneticConnectRef`; and
- exactly one `Connector2` node at `0.8.2`, resolving to `IFeature`,
  `Name="Connector2"`, type `MagneticConnectRef`.

The diagnostic state was `ALL_REQUESTED_TREE_TEXTS_OBSERVED` with
`model_mutation=false`, `write_authority=NONE`, and
`remote_queue_authorized=false`. This resolves the **API observation-surface /
representation mismatch** for connector identity and parentage: the Asset
Publisher objects are exposed under the visible FeatureManager-tree surface,
not by `IAssemblyDoc.FeatureByName` or ordinary model-feature traversal. The
earlier negatives remain preserved evidence about those two distinct API
surfaces; they do not become a CAD-state failure.

The bounded `sw.query_interface_contract` reader is therefore updated to use
the reviewed FeatureManager-tree branch for Published Reference identity/type
and direct parentage while retaining the already verified `CoordSys`
`GetDefinition()` transform path. A fresh run of that updated query and its
pre/post no-mutation verifier is still required before any interface state can
be `VERIFIED_CURRENT`. Connector point/direction geometry and Published Asset
↔ coordinate-system geometric coincidence remain `UNRESOLVED`; no mechanical
acceptance follows.

At PR #20 head `04a1788dcd1a4f2a0759e82da1f5da633c8fea62`, the Windows host
advanced through the native interface query and strict PowerShell interface
normalization. It then failed at the deterministic Python verifier input
boundary because Windows PowerShell 5.1 emitted a UTF-8 BOM in the raw JSON
artifact through `Set-Content -Encoding UTF8`; Python deliberately reads this
evidence with strict `utf-8`. This is an artifact-producer failure, not a CAD,
connector, coordinate-system, or no-mutation finding. The resulting interface
state remains not-current until the verifier is rerun with BOM-free evidence.
