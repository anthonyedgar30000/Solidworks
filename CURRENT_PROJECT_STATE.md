# CADGrounded — CURRENT PROJECT STATE

**Synchronized across live SOLIDWORKS, GitHub, and Google Drive:** 2026-09-27T23:35:00Z

## Authority

- **SOLIDWORKS** is authority for live geometry, active document, configuration, and component state.
- **GitHub** is authority for versioned source, policy, evidence records, reasoning state, result review, and durable project history.
- **Google Drive** is mirror / reference / archive / transport.
- API success, a file name, a candidate label, or a synchronized pointer does **not** grant mechanical acceptance.

## Fresh live SOLIDWORKS state

Source classification: `verified_from_solidworks_api`

Active assembly:

`IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE`

Exact path:

`C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE.SLDASM`

Active configuration:

`V43_WRAP`

Observed save flag at sync:

`false`

A same-session top-level component reread returned the expected v43 PRISM geometry, including both wrap support rollers, both fixed PRISM guide rails, PRISM arms, links, carrier slider, reaction base, actuator envelope, bottles, conveyor, driven wrap belt, index stops, IXOR, SP100, and support hardware.

## Current GitHub project state

Current plan:

`PLAN-0011 / P0011.4`

Current status:

`ACTIVE_INVESTIGATION_V43_DUAL_PIVOT_PATH_DISPROVEN_NEXT_ARCHITECTURE_REQUIRED`

Current evidence:

`E.V43.PRISM.DUAL_PIVOT_GUIDE_RAIL_INTERFERENCE.20260927T231617920Z`

Current result review:

`R.PLAN-0011.V43_DUAL_PIVOT_GUIDE_RAIL_INTERFERENCE.20260927T232600Z`

Source records at sync:

- `agent-registry/planning/CURRENT_PLAN.json` — blob `92e4de355c9a304f1ab79b316ec5ed90c4dd9182`
- `agent-registry/reasoning/runtime/v43-dual-pivot-exact-sweep-result-20260927T231617920Z.json` — blob `b47641e91b5673ef44a1bfac239609dab0aee68e`
- `agent-registry/orchestrator-v1/reviews/PLAN-0011-v43-dual-pivot-interference-review-20260927.json` — blob `5b5802bd47b55c1ecb516175228185c060f7465c`

## Admitted mechanical result

The **exact tested v43 dual-independent-pivot motion path is disproven for the tested geometry**.

Fresh deterministic temporary-body B-rep evidence recorded:

- Roller-1 vs fixed Guide-Rail-1 at `-37.932118385834365°`: positive intersection `36.87005661597739 mm³`.
- Roller-2 vs fixed Guide-Rail-2 at `+16.093399159748615°`: positive intersection `229.78798686025416 mm³`.
- Boolean error codes were zero for both observations.
- The live assembly was not mutated and was reverified after the bounded test.

This result is scoped narrowly. It **does not** reject every pivoting architecture, every possible pivot location, every re-authored guide layout, or the admitted closed three-contact bottle topology.

GitHub review state:

- `CANDIDATE_V43_PRISM_DUAL_INDEPENDENT_PIVOT_ARMS_V1` → `DISPROVEN / EXHAUSTED` for this exact path.
- Broader `CANDIDATE_PIVOTING_ROLLER_CARRIER` → `UNRESOLVED / ELIGIBLE`.
- `CANDIDATE_V43_PRISM_AS_PROJECT_PROPOSAL` → `WEAKENED / ACTIVE`.

## Next engineering frontier

Do not keep densifying the disproven exact dual-pivot trajectory.

The current result review points to a **different motion architecture or re-authored pivot/guide geometry**, while preserving the useful closed-state contact evidence as a reference. A translating-carrier or moving-wrap-belt architecture is also an eligible distinct investigation class.

## Mechanical acceptance

**FALSE.**

No synchronized record in this file grants CAD write authority or mechanical acceptance.

## Freshness rule

1. A newer successful live SOLIDWORKS read supersedes the live-state section immediately.
2. GitHub `CURRENT_PLAN.json` and its linked evidence/review records supersede this project-state summary if they advance.
3. Google Drive mirrors this summary for retrieval/handoff convenience and is not the authority over GitHub or live SOLIDWORKS.
4. v42 and earlier reality-sync files remain historical unless a fresh live SOLIDWORKS read returns them again.
