# CADGrounded — CURRENT PROJECT STATE

**Cross-source reconciliation:** 2026-09-27T23:35Z

## Authority

- **SOLIDWORKS** is authority for live geometry, active document, configuration, and current/unsaved CAD state.
- **GitHub** is authority for versioned source, policy, admitted evidence, reasoning state, result review, and durable project history.
- **Google Drive** is mirror / reference / archive / transport.
- Synchronization preserves source roles and explicit divergence; it does not force the sources to say the same thing.

## Current live SOLIDWORKS state

Latest successful live read:

- bridge: `0.3.0`
- source classification: `verified_from_solidworks_api`
- active document: **NONE / null**

There is currently no active SOLIDWORKS document bound to the live bridge.

Earlier in this same synchronization cycle, the live bridge observed:

`IXOR_Benchmark_v27_SPRING_ROLLER_HANDOFF_FIT_CHECK_PORTABLE`

at:

`C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v27_SPRING_ROLLER_HANDOFF_FIT_CHECK_PORTABLE.SLDASM`

with configuration `Default` and `save_flag=true`. That v27 observation is now **historical within the sync cycle**, not the current active document. Because it was dirty/unsaved, no claim is made that those live changes were persisted.

## Current GitHub project state

GitHub `CURRENT_PLAN.json` remains:

`PLAN-0011 / P0011.4`

Status:

`ACTIVE_INVESTIGATION_V43_DUAL_PIVOT_PATH_DISPROVEN_NEXT_ARCHITECTURE_REQUIRED`

Current evidence:

`E.V43.PRISM.DUAL_PIVOT_GUIDE_RAIL_INTERFERENCE.20260927T231617920Z`

Current result review:

`R.PLAN-0011.V43_DUAL_PIVOT_GUIDE_RAIL_INTERFERENCE.20260927T232600Z`

Authoritative versioned records:

- `agent-registry/planning/CURRENT_PLAN.json`
- `agent-registry/reasoning/runtime/v43-dual-pivot-exact-sweep-result-20260927T231617920Z.json`
- `agent-registry/orchestrator-v1/reviews/PLAN-0011-v43-dual-pivot-interference-review-20260927.json`

## Admitted v43 result

For the exact tested v43 dual-independent-pivot motion path:

- Roller-1 vs fixed Guide-Rail-1 at `-37.932118385834365°`: positive B-rep intersection `36.87005661597739 mm³`.
- Roller-2 vs fixed Guide-Rail-2 at `+16.093399159748615°`: positive B-rep intersection `229.78798686025416 mm³`.
- Boolean error codes were zero.
- The bounded v43 test did not mutate the assembly used for that test.

GitHub result review records:

- exact `CANDIDATE_V43_PRISM_DUAL_INDEPENDENT_PIVOT_ARMS_V1` path → `DISPROVEN / EXHAUSTED`;
- broader `CANDIDATE_PIVOTING_ROLLER_CARRIER` → `UNRESOLVED / ELIGIBLE`;
- `CANDIDATE_V43_PRISM_AS_PROJECT_PROPOSAL` → `WEAKENED / ACTIVE`.

This negative evidence is scoped to the exact tested v43 path and does not reject every pivot architecture or the admitted closed three-contact topology.

## Runtime/project-state relationship

Current live CAD readiness and durable project state are intentionally separate:

- live SOLIDWORKS now has **no active document**;
- GitHub's current engineering investigation is still the v43 PLAN-0011 state;
- Google Drive mirrors both facts.

Any next v43-specific CAD read/test requires the exact v43 assembly to be opened/activated and freshly rebound before execution. Do not infer v43 live state from the GitHub plan.

## Next v43 engineering frontier

The versioned v43 review says not to densify the disproven exact dual-pivot path. The next investigation requires a different motion architecture or re-authored pivot/guide geometry; translating-carrier and moving-wrap-belt classes remain eligible.

## Mechanical acceptance

**FALSE.**

No cross-source synchronization grants CAD write authority or mechanical acceptance.

## Freshness rule

1. A newer successful live SOLIDWORKS read immediately supersedes the live-state section.
2. GitHub `CURRENT_PLAN.json` and linked evidence/review records supersede the versioned project-state section when they advance.
3. Drive mirrors this reconciliation but is not authority over SOLIDWORKS or GitHub.
4. Never resolve a source mismatch by guessing.
