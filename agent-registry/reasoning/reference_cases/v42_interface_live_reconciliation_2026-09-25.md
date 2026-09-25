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

The smallest next test is the separate local-only
`sw.diagnose_feature_manager_tree` read: traverse the visible FeatureManager
tree, retain only the exact tree texts `Published References`, `Ground Plane`,
`Connector1`, and `Connector2`, and record their `ITreeControlItem` metadata.
The unchanged exact `sw.query_interface_contract` reader remains fail-closed
until an authoritative read path is separately established and reviewed.
