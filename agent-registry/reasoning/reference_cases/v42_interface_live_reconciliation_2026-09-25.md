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
