# CADGrounded — CURRENT PROJECT STATE

**Cross-source reconciliation:** 2026-09-27T23:35Z

## Authority

- **SOLIDWORKS** is authority for live geometry, active document, configuration, and unsaved/current component state.
- **GitHub** is authority for versioned source, policy, admitted evidence records, reasoning state, result review, and durable project history.
- **Google Drive** is mirror / reference / archive / transport.
- These sources are synchronized by preserving their different authority roles; they are not forced to report the same document when live CAD has moved.

## Current live SOLIDWORKS state

Source classification: `verified_from_solidworks_api`

Active assembly:

`IXOR_Benchmark_v27_SPRING_ROLLER_HANDOFF_FIT_CHECK_PORTABLE`

Exact path:

`C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v27_SPRING_ROLLER_HANDOFF_FIT_CHECK_PORTABLE.SLDASM`

Active configuration:

`Default`

Observed save flag:

`true`

This means the currently active v27 document is dirty/unsaved at the time of reconciliation. GitHub and Drive must **not** be treated as mirrors of those unsaved live geometry changes.

A same-session top-level component reread returned the v27 spring-roller/belt/bottle-handling assembly state. The active top-level inventory included the driven wrap belt, two wrap support rollers, bottles, conveyor, IXOR/SP100/support hardware and carriage hardware. The v43 PRISM component names were not present in this active top-level inventory.

## Cross-source divergence

The live CAD document is currently **v27**, while the current GitHub engineering plan/evidence remains the **v43 / PLAN-0011** investigation state.

This is a legitimate authority split, not something to guess away:

- current live geometry/state → v27, from SOLIDWORKS;
- current durable engineering investigation/result disposition → v43 PLAN-0011, from GitHub;
- Google Drive mirrors both facts and the divergence.

Do **not** apply v43 geometry conclusions directly to the active v27 assembly.

## Current GitHub project state

Current plan:

`PLAN-0011 / P0011.4`

Current status:

`ACTIVE_INVESTIGATION_V43_DUAL_PIVOT_PATH_DISPROVEN_NEXT_ARCHITECTURE_REQUIRED`

Current evidence:

`E.V43.PRISM.DUAL_PIVOT_GUIDE_RAIL_INTERFERENCE.20260927T231617920Z`

Current result review:

`R.PLAN-0011.V43_DUAL_PIVOT_GUIDE_RAIL_INTERFERENCE.20260927T232600Z`

Source records:

- `agent-registry/planning/CURRENT_PLAN.json` — blob `92e4de355c9a304f1ab79b316ec5ed90c4dd9182`
- `agent-registry/reasoning/runtime/v43-dual-pivot-exact-sweep-result-20260927T231617920Z.json` — blob `b47641e91b5673ef44a1bfac239609dab0aee68e`
- `agent-registry/orchestrator-v1/reviews/PLAN-0011-v43-dual-pivot-interference-review-20260927.json` — blob `5b5802bd47b55c1ecb516175228185c060f7465c`

## Admitted v43 mechanical result

For the **exact tested v43 dual-independent-pivot motion path**:

- Roller-1 vs fixed Guide-Rail-1 at `-37.932118385834365°`: positive B-rep intersection `36.87005661597739 mm³`.
- Roller-2 vs fixed Guide-Rail-2 at `+16.093399159748615°`: positive B-rep intersection `229.78798686025416 mm³`.
- Boolean error codes were zero.
- The bounded v43 test did not mutate the live assembly used for that test.

GitHub result review therefore records:

- `CANDIDATE_V43_PRISM_DUAL_INDEPENDENT_PIVOT_ARMS_V1` → `DISPROVEN / EXHAUSTED` for that exact path.
- broader `CANDIDATE_PIVOTING_ROLLER_CARRIER` → `UNRESOLVED / ELIGIBLE`.
- `CANDIDATE_V43_PRISM_AS_PROJECT_PROPOSAL` → `WEAKENED / ACTIVE`.

This result does not reject every pivot architecture or the closed three-contact topology.

## Current engineering frontier

GitHub's current v43 result review says not to keep densifying the disproven exact dual-pivot trajectory. The next v43 investigation requires a different motion architecture or re-authored pivot/guide geometry; a translating-carrier or moving-wrap-belt class remains eligible.

Before executing any v43-specific next test, **freshly activate/rebind the exact v43 document**. The currently active v27 document does not satisfy a v43 precondition.

## Mechanical acceptance

**FALSE.**

No cross-source synchronization grants CAD write authority or mechanical acceptance.

## Freshness rule

1. A newer successful live SOLIDWORKS read immediately supersedes the live-state section.
2. GitHub `CURRENT_PLAN.json` and linked evidence/review records supersede the GitHub-state section when they advance.
3. Drive mirrors this reconciliation but is not authority over live SOLIDWORKS or GitHub.
4. Never resolve a SOLIDWORKS/GitHub mismatch by guessing; preserve it as explicit live-state/project-state divergence.
