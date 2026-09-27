# CADGrounded — CURRENT LIVE CAD POINTER

**Purpose:** search-first freshness pointer for new chats and handoffs.

**Fresh live verification:** 2026-09-27T23:35Z

## Current active document

`IXOR_Benchmark_v27_SPRING_ROLLER_HANDOFF_FIT_CHECK_PORTABLE`

Exact live path:

`C:\ChatGPT\Solidworks\IXOR\CAB_IXOR_6130800\IXOR_Benchmark_v27_SPRING_ROLLER_HANDOFF_FIT_CHECK_PORTABLE.SLDASM`

Active configuration:

`Default`

Observed save flag:

`true`

Source classification: `verified_from_solidworks_api`

A same-session top-level component read confirmed the active v27 assembly state and spring-roller/belt/bottle-handling components.

## Important divergence from GitHub plan

GitHub `CURRENT_PLAN.json` is still the durable **v43 PLAN-0011** investigation state:

`ACTIVE_INVESTIGATION_V43_DUAL_PIVOT_PATH_DISPROVEN_NEXT_ARCHITECTURE_REQUIRED`

Therefore:

- **live CAD right now = v27**
- **current durable engineering plan/result = v43 PLAN-0011**
- **v43-specific tests require re-activating and freshly rebinding v43 before execution**

Do not silently treat the active v27 assembly as v43.

Read `CURRENT_PROJECT_STATE.md` for the synchronized cross-source handoff.

## Freshness rule

1. Prefer a fresh live SOLIDWORKS read.
2. A newer successful live read supersedes this pointer immediately.
3. GitHub evidence/reasoning records remain authoritative for their versioned test/result history.
4. Drive mirrors the current reconciliation.
5. API success, a document name, or a candidate label does not grant mechanical acceptance.

## Mechanical state

The active v27 file is a fit-check/handoff state by name. Its current save flag is true, so unsaved live changes may exist.

**Mechanical acceptance remains false.**
