# CADGrounded — CURRENT PROJECT STATE

**Cross-source reconciliation:** 2026-09-27T23:35Z

## Authority

- **SOLIDWORKS** is authority for live geometry, active document, configuration, and current/unsaved CAD state.
- **GitHub** is authority for versioned source, policy, admitted evidence, reasoning state, result review, and durable project history.
- **Google Drive** is mirror / reference / archive / transport.
- Synchronization preserves source roles and explicit divergence; it never resolves ambiguity by guess.

## Live SOLIDWORKS observation sequence during this sync

The live CAD state was **volatile during synchronization**. Successful reads observed, in order:

1. `IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE` at the exact v43 path, configuration `V43_WRAP`, `save_flag=false`, process ID `16768`.
2. `IXOR_Benchmark_v27_SPRING_ROLLER_HANDOFF_FIT_CHECK_PORTABLE`, configuration `Default`, `save_flag=true`, process ID `16768`.
3. `active_document: null`.
4. Latest successful read: `IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE`, configuration `V43_WRAP`, `save_flag=false`, process ID `22884`.

The process ID changed between the earlier and latest v43 observations. No cause is inferred from that fact.

### Latest verified live state

Active assembly:

`IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE`

Exact path:

`C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE.SLDASM`

Configuration: `V43_WRAP`

Save flag: `false`

Source classification: `verified_from_solidworks_api`

Because the active document changed repeatedly during this sync, this pointer is **handoff evidence only**. Every CAD-dependent operation must perform a fresh exact document/path/configuration read immediately before execution.

Document title/path/configuration equality alone does not prove geometric identity with an earlier verification artifact.

## Current GitHub project state

GitHub `CURRENT_PLAN.json` remains:

`PLAN-0011 / P0011.4`

Status:

`ACTIVE_INVESTIGATION_V43_DUAL_PIVOT_PATH_DISPROVEN_NEXT_ARCHITECTURE_REQUIRED`

Current evidence:

`E.V43.PRISM.DUAL_PIVOT_GUIDE_RAIL_INTERFERENCE.20260927T231617920Z`

Current result review:

`R.PLAN-0011.V43_DUAL_PIVOT_GUIDE_RAIL_INTERFERENCE.20260927T232600Z`

## Admitted v43 result

For the exact tested v43 dual-independent-pivot motion path:

- Roller-1 vs fixed Guide-Rail-1 at `-37.932118385834365°`: positive B-rep intersection `36.87005661597739 mm³`.
- Roller-2 vs fixed Guide-Rail-2 at `+16.093399159748615°`: positive B-rep intersection `229.78798686025416 mm³`.
- Boolean error codes were zero.
- The bounded test did not mutate the assembly used for that test.

GitHub result review records:

- exact `CANDIDATE_V43_PRISM_DUAL_INDEPENDENT_PIVOT_ARMS_V1` path → `DISPROVEN / EXHAUSTED`;
- broader `CANDIDATE_PIVOTING_ROLLER_CARRIER` → `UNRESOLVED / ELIGIBLE`;
- `CANDIDATE_V43_PRISM_AS_PROJECT_PROPOSAL` → `WEAKENED / ACTIVE`.

This negative evidence is scoped to the exact tested path and does not reject every pivot architecture or the closed three-contact topology.

## Current engineering frontier

Do not densify the disproven exact dual-pivot path.

The versioned review points to a different motion architecture or re-authored pivot/guide geometry. Translating-carrier and moving-wrap-belt classes remain eligible.

Because live CAD was volatile during the sync, the next CAD test must begin with a fresh rebind and exact state check even though the latest observed document is v43.

## Mechanical acceptance

**FALSE.**

No synchronized pointer grants CAD write authority or mechanical acceptance.

## Freshness rule

1. Fresh live SOLIDWORKS reads outrank this summary for current CAD state.
2. GitHub `CURRENT_PLAN.json` and linked evidence/review records outrank this summary for versioned project state.
3. Drive mirrors this reconciliation only.
4. Preserve volatility, stale state, and source disagreement explicitly.
