# CADGrounded — CURRENT LIVE CAD POINTER

**Purpose:** search-first handoff pointer only.

**Reconciled:** 2026-09-27T23:35Z

## Latest successful live SOLIDWORKS read

Active document:

`IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE`

Exact path:

`C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v43_PRISM_OPERATING_CANDIDATE_PORTABLE.SLDASM`

Configuration: `V43_WRAP`

Save flag: `false`

Process ID observed: `22884`

Source classification: `verified_from_solidworks_api`

## Important: live state changed during synchronization

The same sync cycle also successfully observed:

- v43 / `V43_WRAP` / clean / process `16768`;
- v27 `SPRING_ROLLER_HANDOFF_FIT_CHECK_PORTABLE` / `Default` / dirty / process `16768`;
- no active document;
- then the latest v43 / `V43_WRAP` / clean state on process `22884`.

Therefore **do not use this file as an execution precondition**. Read SOLIDWORKS again immediately before any CAD-dependent test or write.

The process-ID change is recorded as evidence of session transition only; no cause is inferred.

## GitHub project-state cross-reference

GitHub `CURRENT_PLAN.json` remains the v43 PLAN-0011 investigation:

`ACTIVE_INVESTIGATION_V43_DUAL_PIVOT_PATH_DISPROVEN_NEXT_ARCHITECTURE_REQUIRED`

The exact tested v43 dual-pivot path is `DISPROVEN / EXHAUSTED` for that tested geometry. Broader pivoting architectures remain eligible.

Read `CURRENT_PROJECT_STATE.md` for the synchronized source reconciliation.

## Mechanical acceptance

**FALSE.**

A current document title/path/configuration does not by itself prove exact geometric identity with prior evidence and does not grant mechanical acceptance.
